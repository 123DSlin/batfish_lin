"""Shared SMT primitives for the symbolic NetSubspec pipeline.

This module contains only functionality used by more than one pipeline stage:
seed parsing, solver operations, symbol hygiene, stable constraint identifiers,
and exact integer-interval rendering. Branch projection and reporting remain in
their owning stage scripts.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
from threading import Lock
import time
from typing import Any, Optional

from utils.util_smt import (
    parse_smt2_sexpr,
    serialize_smt2_sexpr,
    subspec_string_to_list,
    subspec_string_to_smt2_and,
    tokenize_smt2_sexpr,
)


class SubspecificationError(RuntimeError):
    """Raised when symbolic subspecification cannot remain fail-closed."""


@dataclass(frozen=True)
class ConfigPin:
    name: str
    sort: str
    original_value: str
    assertion_index: int


@dataclass(frozen=True)
class SmtDocument:
    declarations: dict[str, str]
    declaration_forms: tuple[str, ...]
    definition_forms: tuple[str, ...]
    assertions: tuple[object, ...]
    assertion_names: tuple[Optional[str], ...]
    config_pins: tuple[ConfigPin, ...]

    @classmethod
    def parse(cls, text: str) -> "SmtDocument":
        declarations: dict[str, str] = {}
        declaration_forms: list[str] = []
        definition_forms: list[str] = []
        assertions: list[object] = []
        assertion_names: list[Optional[str]] = []

        for form in _split_top_level_forms(text):
            tree = parse_smt2_sexpr(tokenize_smt2_sexpr(form))
            if not isinstance(tree, list) or not tree:
                continue
            head = tree[0]
            if head == "declare-fun":
                if (
                    len(tree) != 4
                    or not isinstance(tree[1], str)
                    or tree[2] != []
                ):
                    raise SubspecificationError(
                        f"unsupported declaration in seed: {form}"
                    )
                name = tree[1]
                sort = serialize_smt2_sexpr(tree[3])
                previous = declarations.get(name)
                if previous is not None and previous != sort:
                    raise SubspecificationError(
                        f"symbol {name} has conflicting sorts {previous} and {sort}"
                    )
                declarations[name] = sort
                declaration_forms.append(form)
            elif head in {"define-fun", "define-const"}:
                definition_forms.append(form)
            elif head == "assert":
                if len(tree) != 2:
                    raise SubspecificationError(f"malformed assertion: {form}")
                expression, name = _unwrap_named_assertion(tree[1])
                assertions.append(expression)
                assertion_names.append(name)

        pins: list[ConfigPin] = []
        seen: set[str] = set()
        for index, expression in enumerate(assertions):
            pin = _config_pin(expression, declarations, index)
            if pin is None:
                continue
            if pin.name in seen:
                raise SubspecificationError(
                    f"configuration field {pin.name} has more than one equality pin"
                )
            seen.add(pin.name)
            pins.append(pin)
        return cls(
            declarations=declarations,
            declaration_forms=tuple(declaration_forms),
            definition_forms=tuple(definition_forms),
            assertions=tuple(assertions),
            assertion_names=tuple(assertion_names),
            config_pins=tuple(sorted(pins, key=lambda item: item.name)),
        )

    def query(self, *commands: str) -> str:
        """Build a Z3 query with this seed's shared declaration context."""

        return "\n".join(
            [
                "(set-option :print-success false)",
                *self.declaration_forms,
                *self.definition_forms,
                *commands,
            ]
        ) + "\n"

    def quantifier_bindings(self, names: list[str]) -> list[list[object]]:
        bindings: list[list[object]] = []
        for name in names:
            sort = self.declarations.get(name)
            if sort is None:
                raise SubspecificationError(f"cannot quantify undeclared symbol {name}")
            bindings.append(
                [name, parse_smt2_sexpr(tokenize_smt2_sexpr(sort))]
            )
        return bindings


class SmtSolver:
    """Shared fail-closed Z3 operations for symbolic pipeline stages."""

    def __init__(
        self,
        *,
        z3_path: Optional[Path | str] = None,
        timeout_seconds: float = 30.0,
        cache_entries: int = 128,
        cache_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if cache_entries < 0 or cache_bytes < 0:
            raise ValueError("solver cache limits must be nonnegative")
        self.z3_path = self._resolve_z3(z3_path)
        self.timeout_seconds = timeout_seconds
        # Exact requests only: declarations, definitions, assertions, tactics,
        # executable and timeout all participate. Never cache uncertain results.
        self._cache: OrderedDict[
            tuple[str, float, str], tuple[str, str, int]
        ] = OrderedDict()
        self._cache_lock = Lock()
        self._cache_entries = cache_entries
        self._cache_limit_bytes = cache_bytes
        self._cache_bytes = self._cache_hits = self._cache_misses = 0

    def cache_info(self) -> dict[str, int]:
        """Expose reuse; bytes counts UTF-8 payload, excluding Python overhead."""
        with self._cache_lock:
            return {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "entries": len(self._cache),
                "bytes": self._cache_bytes,
                "max_entries": self._cache_entries,
                "max_bytes": self._cache_limit_bytes,
            }

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()
            self._cache_bytes = self._cache_hits = self._cache_misses = 0

    @staticmethod
    def _resolve_z3(z3_path: Optional[Path | str]) -> Path:
        candidates: list[Path] = []
        if z3_path is not None:
            candidates.append(Path(z3_path).expanduser())
        discovered = shutil.which("z3")
        if discovered:
            candidates.append(Path(discovered))
        candidates.extend(
            [
                Path("/opt/homebrew/bin/z3"),
                Path("/usr/local/bin/z3"),
                Path("/usr/bin/z3"),
            ]
        )
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_mode & 0o111:
                return candidate.resolve()
        raise SubspecificationError(
            "cannot find a Z3 executable; install z3 or pass --z3 /path/to/z3"
        )

    def project(
        self,
        document: SmtDocument,
        pins: tuple[ConfigPin, ...],
        expression: object,
        operation: str,
    ) -> str:
        query = document.query(
            "; Released AutoNetSubspec target equalities (metadata)",
            *(f"; (assert (= {pin.name} {pin.original_value}))" for pin in pins),
            f"(assert {serialize_smt2_sexpr(expression)})",
            "(apply (then simplify qe-light qe simplify "
            "ctx-solver-simplify simplify))",
        )
        expressions = self._run_goal(query, operation)
        return " AND ".join(expressions) if expressions else "true"

    def simplify(self, document: SmtDocument, expression: object) -> str:
        query = document.query(
            f"(assert {serialize_smt2_sexpr(expression)})",
            "(apply simplify)",
        )
        expressions = self._run_goal(query, "candidate simplification")
        return " AND ".join(expressions) if expressions else "true"

    def entails(
        self, document: SmtDocument, context: object, expression: object
    ) -> bool:
        query = document.query(
            f"(assert {serialize_smt2_sexpr(context)})",
            f"(assert (not {serialize_smt2_sexpr(expression)}))",
            "(check-sat)",
        )
        try:
            result = self._invoke(query)
        except subprocess.TimeoutExpired:
            return False
        return (
            result.returncode == 0
            and not result.stderr.strip()
            and result.stdout.strip() == "unsat"
        )

    def equivalent(
        self,
        document: SmtDocument,
        expected: object,
        candidate: str,
    ) -> tuple[bool, float]:
        candidate_expression = parse_smt2_sexpr(
            tokenize_smt2_sexpr(subspec_string_to_smt2_and(candidate) or "true")
        )
        disagreement = ["not", ["=", expected, candidate_expression]]
        assertion = f"(assert {serialize_smt2_sexpr(disagreement)})"
        started = time.monotonic()
        checks = (
            ("(check-sat)", min(self.timeout_seconds, 5.0)),
            (
                "(check-sat-using (then simplify qe-light qe smt))",
                self.timeout_seconds,
            ),
        )
        for check, timeout in checks:
            try:
                result = self._invoke(
                    document.query(assertion, check), timeout=timeout
                )
            except subprocess.TimeoutExpired:
                continue
            answer = result.stdout.strip().splitlines()
            if result.returncode != 0 or result.stderr.strip():
                continue
            if answer == ["unsat"]:
                return True, time.monotonic() - started
            if answer == ["sat"]:
                return False, time.monotonic() - started
        return False, time.monotonic() - started

    def satisfiable(self, document: SmtDocument, constraint: str) -> bool:
        query = document.query(
            f"(assert {subspec_string_to_smt2_and(constraint) or 'true'})",
            "(check-sat)",
        )
        try:
            result = self._invoke(query)
        except subprocess.TimeoutExpired as error:
            raise SubspecificationError(
                "SMT satisfiability check timed out after "
                f"{self.timeout_seconds:g}s"
            ) from error
        if result.returncode != 0 or "(error " in result.stdout or result.stderr.strip():
            detail = (result.stderr or result.stdout).strip()
            raise SubspecificationError(
                f"SMT satisfiability check failed: {detail}"
            )
        answer = result.stdout.strip()
        if answer == "sat":
            return True
        if answer == "unsat":
            return False
        raise SubspecificationError(
            f"SMT satisfiability check returned {answer or 'no result'}"
        )

    def remove_redundant_atoms(
        self, document: SmtDocument, constraint: str
    ) -> str:
        atoms = [
            parse_smt2_sexpr(tokenize_smt2_sexpr(atom))
            for atom in subspec_string_to_list(constraint)
        ]
        index = len(atoms) - 1
        while index >= 0:
            context = and_expression(
                atom for position, atom in enumerate(atoms) if position != index
            )
            if self.entails(document, context, atoms[index]):
                atoms.pop(index)
            index -= 1
        return " AND ".join(serialize_smt2_sexpr(atom) for atom in atoms) or "true"

    def _run_goal(self, query: str, operation: str) -> tuple[str, ...]:
        try:
            result = self._invoke(query)
        except subprocess.TimeoutExpired as error:
            raise SubspecificationError(
                f"{operation} timed out after {self.timeout_seconds:g}s"
            ) from error
        if result.returncode != 0 or "(error " in result.stdout or result.stderr.strip():
            detail = (result.stderr or result.stdout).strip()
            raise SubspecificationError(f"{operation} failed: {detail}")
        expressions, precise = _parse_goal(result.stdout)
        if not precise:
            raise SubspecificationError(f"{operation} was not marked precise")
        return expressions

    def _invoke(
        self, query: str, *, timeout: Optional[float] = None
    ) -> subprocess.CompletedProcess[str]:
        executable = str(self.z3_path)
        effective_timeout = self.timeout_seconds if timeout is None else timeout
        key = (executable, effective_timeout, query)
        args = [executable, "-in", "-smt2"]
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._cache_hits += 1
                # CompletedProcess is mutable; never expose cached state.
                return subprocess.CompletedProcess(args, 0, cached[0], cached[1])
            self._cache_misses += 1
        result = subprocess.run(
            args,
            input=query,
            text=True,
            capture_output=True,
            timeout=effective_timeout,
            check=False,
        )
        if (
            self._cache_entries
            and self._cache_limit_bytes
            and self._cacheable(result)
        ):
            size = len(
                (executable + query + result.stdout + result.stderr).encode("utf-8")
            )
            if size <= self._cache_limit_bytes:
                with self._cache_lock:
                    previous = self._cache.pop(key, None)
                    if previous is not None:
                        self._cache_bytes -= previous[2]
                    self._cache[key] = (result.stdout, result.stderr, size)
                    self._cache_bytes += size
                    while (
                        len(self._cache) > self._cache_entries
                        or self._cache_bytes > self._cache_limit_bytes
                    ):
                        _, evicted = self._cache.popitem(last=False)
                        self._cache_bytes -= evicted[2]
        return result

    @staticmethod
    def _cacheable(result: subprocess.CompletedProcess[str]) -> bool:
        if result.returncode or result.stderr.strip() or "(error " in result.stdout:
            return False
        output = result.stdout.strip()
        if output in {"sat", "unsat"}:
            return True
        if not output.startswith("(goals"):
            return False
        try:
            _, precise = _parse_goal(output)
            return precise
        except (SubspecificationError, ValueError, IndexError):
            return False


def and_expression(expressions: Any) -> object:
    values = list(expressions)
    if not values:
        return "true"
    if len(values) == 1:
        return values[0]
    return ["and", *values]


def substitute_symbols(expression: object, replacements: dict[str, object]) -> object:
    if isinstance(expression, str):
        return replacements.get(expression, expression)
    if isinstance(expression, list):
        return [substitute_symbols(item, replacements) for item in expression]
    return expression


def collect_declared_symbols(
    expression: object, declarations: dict[str, str]
) -> set[str]:
    if isinstance(expression, str):
        if expression in declarations:
            return {expression}
        quoted = f"|{expression}|"
        return {quoted} if quoted in declarations else set()
    if isinstance(expression, list):
        result: set[str] = set()
        for item in expression:
            result.update(collect_declared_symbols(item, declarations))
        return result
    return set()


def residual_declared_symbols(
    constraint: str,
    declarations: dict[str, str],
    allowed: frozenset[str],
) -> tuple[str, ...]:
    expression = parse_smt2_sexpr(
        tokenize_smt2_sexpr(subspec_string_to_smt2_and(constraint) or "true")
    )
    return tuple(sorted(collect_declared_symbols(expression, declarations) - allowed))


def constraint_ids(level: str, target: str, constraint: str) -> tuple[str, ...]:
    if constraint == "true":
        return ()
    identifiers = []
    for atom in subspec_string_to_list(constraint):
        payload = "\0".join((level, target, atom)).encode("utf-8")
        identifiers.append(
            "constraint-v1-" + hashlib.sha256(payload).hexdigest()[:16]
        )
    return tuple(identifiers)


def integer_interval(
    expression: object, target: str
) -> Optional[tuple[Optional[int], Optional[int]]]:
    if expression == "true":
        return (None, None)
    if not isinstance(expression, list) or not expression:
        return None
    if len(expression) == 2 and expression[0] == "not":
        comparison = expression[1]
        if (
            not isinstance(comparison, list)
            or len(comparison) != 3
            or comparison[0] not in {"<=", "<", ">=", ">"}
        ):
            return None
        inverse = {"<=": ">", "<": ">=", ">=": "<", ">": "<="}
        return integer_interval(
            [inverse[comparison[0]], comparison[1], comparison[2]], target
        )
    if expression[0] == "and":
        lower: Optional[int] = None
        upper: Optional[int] = None
        for child in expression[1:]:
            interval = integer_interval(child, target)
            if interval is None:
                return None
            child_lower, child_upper = interval
            if child_lower is not None:
                lower = child_lower if lower is None else max(lower, child_lower)
            if child_upper is not None:
                upper = child_upper if upper is None else min(upper, child_upper)
        return (lower, upper)
    if len(expression) != 3 or expression[0] not in {"=", "<=", "<", ">=", ">"}:
        return None
    operator, left, right = expression
    right_value = _integer_literal(right)
    left_value = _integer_literal(left)
    if left == target and right_value is not None:
        return _comparison_interval(operator, right_value)
    if right == target and left_value is not None:
        reverse = {"=": "=", "<=": ">=", "<": ">", ">=": "<=", ">": "<"}
        return _comparison_interval(reverse[operator], left_value)
    return None


def serialize_subspec_expression(expression: object) -> str:
    if isinstance(expression, list) and expression and expression[0] == "and":
        return " AND ".join(
            serialize_smt2_sexpr(child) for child in expression[1:]
        ) or "true"
    return serialize_smt2_sexpr(expression)


def interval_expression(
    target: str,
    lower: Optional[int],
    upper: Optional[int],
    strict_lower: Optional[int] = None,
    strict_upper: Optional[int] = None,
) -> object:
    if lower is None and upper is None:
        return "true"
    if lower is not None and upper is not None and lower == upper:
        return ["=", target, str(lower)]
    terms: list[object] = []
    if lower is not None:
        operator = ">" if strict_lower is not None and strict_lower + 1 == lower else ">="
        terms.append([operator, target, str(strict_lower if operator == ">" else lower)])
    if upper is not None:
        operator = "<" if strict_upper is not None and strict_upper - 1 == upper else "<="
        terms.append([operator, target, str(strict_upper if operator == "<" else upper)])
    return and_expression(terms)


def preferred_strict_lower_bound(
    target: ConfigPin,
    lower: Optional[int],
    all_pins: tuple[ConfigPin, ...],
) -> Optional[int]:
    if lower is None:
        return None
    candidate = lower - 1
    return candidate if candidate in strict_thresholds(target, all_pins) else None


def preferred_strict_upper_bound(
    target: ConfigPin,
    upper: Optional[int],
    all_pins: tuple[ConfigPin, ...],
) -> Optional[int]:
    if upper is None:
        return None
    candidate = upper + 1
    return candidate if candidate in strict_thresholds(target, all_pins) else None


def strict_thresholds(
    target: ConfigPin, all_pins: tuple[ConfigPin, ...]
) -> frozenset[int]:
    """Return configured competing values for readable strict boundaries."""

    operation = configuration_value_operation(target.name)
    if operation is None:
        return frozenset()
    thresholds = {100} if operation == "set_localpreference" else set()
    for pin in all_pins:
        if pin.name == target.name or configuration_value_operation(pin.name) != operation:
            continue
        value = _integer_literal(
            parse_smt2_sexpr(tokenize_smt2_sexpr(pin.original_value))
        )
        if value is not None:
            thresholds.add(value)
    return frozenset(thresholds)


def configuration_value_operation(name: str) -> Optional[str]:
    for operation in ("set_localpreference", "set_metric", "prepend_aspath_cost"):
        if f"_{operation}_" in name or name.endswith(f"_{operation}"):
            return operation
    return None


def _integer_literal(expression: object) -> Optional[int]:
    if isinstance(expression, str) and re.fullmatch(r"\d+", expression):
        return int(expression)
    if (
        isinstance(expression, list)
        and len(expression) == 2
        and expression[0] == "-"
        and isinstance(expression[1], str)
        and expression[1].isdigit()
    ):
        return -int(expression[1])
    return None


def _comparison_interval(
    operator: str, value: int
) -> tuple[Optional[int], Optional[int]]:
    if operator == "=":
        return (value, value)
    if operator == "<=":
        return (None, value)
    if operator == "<":
        return (None, value - 1)
    if operator == ">=":
        return (value, None)
    return (value + 1, None)


def _split_top_level_forms(text: str) -> tuple[str, ...]:
    forms: list[str] = []
    start: Optional[int] = None
    depth = 0
    in_comment = False
    in_string = False
    in_quoted_symbol = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_comment:
            if char == "\n":
                in_comment = False
            index += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if in_quoted_symbol:
            if char == "|":
                in_quoted_symbol = False
            index += 1
            continue
        if char == ";":
            in_comment = True
        elif char == '"':
            in_string = True
        elif char == "|":
            in_quoted_symbol = True
        elif char == "(":
            if depth == 0:
                start = index
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise SubspecificationError("unbalanced closing parenthesis in seed")
            if depth == 0 and start is not None:
                forms.append(text[start : index + 1])
                start = None
        index += 1
    if depth != 0 or in_string or in_quoted_symbol:
        raise SubspecificationError("unterminated SMT form in seed")
    return tuple(forms)


def _unwrap_named_assertion(expression: object) -> tuple[object, Optional[str]]:
    if (
        isinstance(expression, list)
        and len(expression) >= 2
        and expression[0] == "!"
    ):
        name: Optional[str] = None
        for index in range(2, len(expression) - 1):
            if expression[index] == ":named" and isinstance(expression[index + 1], str):
                name = expression[index + 1]
                break
        return expression[1], name
    return expression, None


def _config_pin(
    expression: object, declarations: dict[str, str], assertion_index: int
) -> Optional[ConfigPin]:
    if not isinstance(expression, list) or len(expression) != 3 or expression[0] != "=":
        return None
    left, right = expression[1], expression[2]
    if isinstance(left, str) and left.startswith("Config_"):
        name, value = left, right
    elif isinstance(right, str) and right.startswith("Config_"):
        name, value = right, left
    else:
        return None
    sort = declarations.get(name)
    if sort is None:
        raise SubspecificationError(f"configuration field {name} is not declared")
    if _contains_declared_symbol(value, declarations):
        raise SubspecificationError(
            f"configuration pin for {name} is not a concrete value"
        )
    return ConfigPin(
        name=name,
        sort=sort,
        original_value=serialize_smt2_sexpr(value),
        assertion_index=assertion_index,
    )


def _contains_declared_symbol(
    expression: object, declarations: dict[str, str]
) -> bool:
    if isinstance(expression, str):
        return expression in declarations
    if isinstance(expression, list):
        return any(_contains_declared_symbol(item, declarations) for item in expression)
    return False


def _parse_goal(output: str) -> tuple[tuple[str, ...], bool]:
    tree = parse_smt2_sexpr(tokenize_smt2_sexpr(output))
    if not isinstance(tree, list) or not tree or tree[0] != "goals":
        raise SubspecificationError(
            f"unexpected Z3 simplification output: {output.strip()}"
        )
    goals = [item for item in tree[1:] if isinstance(item, list) and item]
    if len(goals) != 1 or goals[0][0] != "goal":
        raise SubspecificationError(
            f"simplification produced {len(goals)} goals; expected exactly one"
        )
    goal = goals[0]
    expressions: list[str] = []
    precise = False
    index = 1
    while index < len(goal):
        item = goal[index]
        if isinstance(item, str) and item.startswith(":"):
            if item == ":precision" and index + 1 < len(goal):
                precise = goal[index + 1] == "precise"
            index += 2
            continue
        expressions.append(serialize_smt2_sexpr(item))
        index += 1
    return tuple(expressions), precise
