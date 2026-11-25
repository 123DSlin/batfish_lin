"""Auditable, fail-closed SMT operations for configuration region projection.

Every solver invocation has a saved query, output and timing entry. Projection
uses quantifier elimination only: equation-solving tactics must not eliminate
free configuration parameters through a hidden model converter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
import subprocess
import time

from utils.util_smt import (
    expand_let_ast, parse_smt2_sexpr, serialize_smt2_sexpr as smt,
    tokenize_smt2_sexpr,
)
from utils.util_symbolic import (
    SmtDocument, SubspecificationError, and_expression,
    collect_declared_symbols, parse_precise_goal,
)


def ast(text: str) -> object:
    return parse_smt2_sexpr(tokenize_smt2_sexpr(text))


class Status(str, Enum):
    PASS = "PASS"
    UNSUPPORTED = "UNSUPPORTED"
    INCOMPLETE = "INCOMPLETE"
    ERROR = "ERROR"


class RegionFailure(SubspecificationError):
    """An unsuccessful proof with a machine-readable disposition."""

    def __init__(self, status: Status, message: str):
        super().__init__(message)
        self.status = status


# The supported model uses quantifier-free Bool/Int/BV configuration formulas.
_OPERATORS = frozenset("and or not => xor = distinct ite + - * / div mod rem abs "
                       "< <= > >= bvand bvor bvnot bvxor bvadd bvsub bvmul bvneg "
                       "bvudiv bvsdiv bvurem bvsrem bvshl bvlshr bvashr bvult bvule "
                       "bvugt bvuge bvslt bvsle bvsgt bvsge concat bv2int int2bv ubv_to_int sbv_to_int".split())
_NUMBER = re.compile(r"(?:[0-9]+(?:\.[0-9]+)?|#x[0-9a-fA-F]+|#b[01]+)")


def require_config_formula(expression: object, targets: set[str]) -> None:
    """Reject residual quantifiers, internal symbols and fresh solver helpers."""
    if isinstance(expression, str):
        if expression not in targets | {"true", "false"} and not _NUMBER.fullmatch(expression):
            raise RegionFailure(Status.INCOMPLETE, f"non-configuration symbol in projection: {expression}")
        return
    if not isinstance(expression, list) or not expression:
        raise RegionFailure(Status.INCOMPLETE, "malformed configuration projection")
    head = expression[0]
    if head == "_" and len(expression) == 3 and re.fullmatch(r"bv\d+", str(expression[1])):
        if str(expression[2]).isdigit():
            return
    if isinstance(head, list) and head and head[0] == "_":
        if len(head) < 3 or head[1] not in {"extract", "zero_extend", "sign_extend", "int2bv", "int_to_bv"}:
            raise RegionFailure(Status.INCOMPLETE, "unsupported indexed operator in projection")
        if not all(str(value).isdigit() for value in head[2:]):
            raise RegionFailure(Status.INCOMPLETE, "invalid indexed operator in projection")
    elif not isinstance(head, str) or head not in _OPERATORS:
        raise RegionFailure(Status.INCOMPLETE, f"unsupported or quantified projection: {head}")
    for child in expression[1:]:
        require_config_formula(child, targets)


@dataclass
class QueryRunner:
    document: SmtDocument
    executable: Path
    timeout: float
    output: Path
    queries: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)
    formulas: list[dict] = field(default_factory=list)
    projection_certificates: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("solver timeout must be positive")
        self.output.mkdir(parents=True, exist_ok=True)
        if self.document.definition_forms:
            raise RegionFailure(Status.UNSUPPORTED, "region projection requires expanded model equations")

    def invoke(self, label: str, *commands: str, timeout: float | None = None) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", label):
            raise ValueError("invalid evidence label")
        path = self.output / f"{len(self.queries):04d}_{label}.smt2"
        query = self.document.query(*commands)
        path.write_text(query)
        start = time.monotonic()
        query_timeout = self.timeout if timeout is None else timeout
        row = dict(label=label, query=path.name, query_bytes=len(query.encode()), status="ERROR",
                   timeout_seconds=query_timeout,
                   check_sat_count=sum(command.count("(check-sat") for command in commands))
        try:
            result = subprocess.run([str(self.executable), "-in", "-smt2"], input=query,
                                    capture_output=True, text=True, timeout=query_timeout, check=False)
            (path.with_suffix(".log")).write_text(result.stdout + result.stderr)
            if result.returncode or result.stderr.strip() or "(error" in result.stdout:
                raise RegionFailure(Status.ERROR, f"solver failed; see {path.name}")
            row["status"] = "COMPLETE"
            return result.stdout.strip()
        except subprocess.TimeoutExpired as exc:
            row["status"] = "TIMEOUT"
            path.with_suffix(".log").write_text(f"timeout after {query_timeout:g} seconds\n")
            raise RegionFailure(Status.INCOMPLETE, f"{label} timed out after {query_timeout:g}s") from exc
        except OSError as exc:
            path.with_suffix(".log").write_text(str(exc) + "\n")
            raise RegionFailure(Status.ERROR, f"{label} could not start solver: {exc}") from exc
        finally:
            row["seconds"] = time.monotonic() - start
            self.queries.append(row)
            (self.output / "queries.json").write_text(json.dumps(self.metrics(), indent=2) + "\n")

    def metrics(self) -> dict:
        return dict(query_count=len(self.queries), solver_seconds=sum(q["seconds"] for q in self.queries),
                    check_sat_count=sum(q["check_sat_count"] for q in self.queries),
                    elapsed_seconds=time.monotonic() - self.started,
                    max_query_bytes=max((q["query_bytes"] for q in self.queries), default=0),
                    max_formula_bytes=max((f["bytes"] for f in self.formulas), default=0),
                    max_formula_dag_nodes=max((f["dag_nodes"] for f in self.formulas), default=0),
                    queries=self.queries, projection_certificates=self.projection_certificates)

    def record_formula(self, expression: object) -> None:
        nodes = set()

        def freeze(node):
            value = tuple(freeze(child) for child in node) if isinstance(node, list) else str(node)
            nodes.add(value)
            return value

        freeze(expression)
        self.formulas.append(dict(bytes=len(smt(expression).encode()), dag_nodes=len(nodes)))

    def check(self, label: str, expression: object) -> str:
        result = self.invoke(label, f"(assert {smt(expression)})", "(check-sat)")
        if result not in {"sat", "unsat"}:
            raise RegionFailure(Status.INCOMPLETE, f"{label} returned {result[:100]}")
        return result

    def prove(self, label: str, counterexample: object) -> None:
        if self.check(label, counterexample) != "unsat":
            raise RegionFailure(Status.INCOMPLETE, f"{label} has a counterexample")

    def values(self, label: str, expression: object, names: list[str]) -> dict[str, object]:
        if not names:
            return {}
        raw = self.invoke(label, f"(assert {smt(expression)})", "(check-sat)",
                          f"(get-value ({' '.join(names)}))")
        status, _, body = raw.partition("\n")
        if status != "sat":
            raise RegionFailure(Status.INCOMPLETE, f"{label} could not recover a witness")
        try:
            values = dict(ast(body))
        except (TypeError, ValueError) as exc:
            raise RegionFailure(Status.ERROR, f"malformed witness in {label}") from exc
        if set(values) != set(names):
            raise RegionFailure(Status.INCOMPLETE, f"incomplete witness in {label}")
        return values

    def simplify(self, label: str, expression: object) -> object:
        raw = self.invoke(label, f"(assert {smt(expression)})",
                          "(apply (then simplify ctx-solver-simplify simplify))")
        result = self._goal(raw)
        self.prove(label + "_equivalence", ["xor", expression, result])
        self.record_formula(result)
        return result

    def within_domain(self, label: str, expression: object, domain: object) -> object:
        """Simplify Boolean structure relative to the legal configuration domain.

        Only solver-proved implications remove bounds. The returned condition
        is explicitly relative to domain, not a new unrestricted theorem.
        """
        cache = {}

        def visit(expr):
            key = smt(expr)
            if key in cache:
                return cache[key]
            if expr in ('true', 'false'):
                return expr
            number = len(cache)
            cache[key] = expr
            if self.check(f'{label}_{number:04d}_implied', and_expression([domain, ['not', expr]])) == 'unsat':
                result = 'true'
            elif self.check(f'{label}_{number:04d}_excluded', and_expression([domain, expr])) == 'unsat':
                result = 'false'
            elif isinstance(expr, list) and expr[0] in ('and', 'or', 'not', '=>', 'xor'):
                result = [expr[0], *(visit(item) for item in expr[1:])]
                if result[0] in ('and', 'or') and len(result) <= 33:
                    items = result[1:]
                    index = 0
                    while len(items) > 1 and index < len(items):
                        others = items[:index] + items[index + 1:]
                        premise = (and_expression([domain, *others, ['not', items[index]]])
                                   if result[0] == 'and' else
                                   and_expression([domain, items[index], ['not', ['or', *others]]]))
                        if self.check(f'{label}_redundant_{len(self.queries):04d}', premise) == 'unsat':
                            items.pop(index)
                        else:
                            index += 1
                    result = [result[0], *items]
                if (result[0] == 'not' and isinstance(result[1], list) and len(result[1]) == 3
                        and result[1][0] == '=' and isinstance(result[1][1], str)
                        and self.document.declarations.get(result[1][1]) == 'Int'
                        and isinstance(result[1][2], str) and result[1][2].isdigit()):
                    variable, threshold = result[1][1:]
                    if self.check(f'{label}_integer_lower_{len(self.queries):04d}',
                                  and_expression([domain, ['<', variable, threshold]])) == 'unsat':
                        result = ['>=', variable, str(int(threshold) + 1)]
            else:
                result = expr
            cache[key] = result
            return result

        candidate = self.simplify(label + '_simplify', visit(expression))
        self.prove(label + '_relative_equivalence', and_expression([domain, ['xor', expression, candidate]]))
        return candidate

    @staticmethod
    def _goal(raw: str) -> object:
        try:
            terms = parse_precise_goal(raw)
        except (SubspecificationError, ValueError, IndexError) as exc:
            raise RegionFailure(Status.INCOMPLETE, "unparseable projection goal") from exc
        return and_expression(expand_let_ast(ast(term), {}) for term in terms)

    def project(self, label: str, expression: object, targets: set[str]) -> object:
        hidden = sorted(collect_declared_symbols(expression, self.document.declarations) - targets)
        quantified = (["exists", self.document.quantifier_bindings(hidden), expression]
                      if hidden else expression)
        raw = self.invoke(label, f"(assert {smt(quantified)})",
                          "(apply (then simplify qe-light qe2 simplify))")
        result = self._goal(raw)
        require_config_formula(result, targets)
        self.record_formula(result)
        # A separate query checks the relation to the original quantified body.
        # This is a model-relative proof, not an independent protocol oracle.
        # Variable IPv4 prefix lengths mix Int and full-width bitvector
        # targets. Re-running aggressive qe2 on the equivalence formula can
        # explode even when ordinary SMT discharges the same theorem quickly.
        mixed_targets = (any(self.document.declarations[name].startswith('(_ BitVec') for name in targets)
                         and any(self.document.declarations[name] == 'Int' for name in targets))
        tactics = [('qe2', '(then simplify qe-light qe2 smt)')]
        if mixed_targets:
            tactics += [('qe', '(then simplify qe-light qe smt)'), ('smt', '(then simplify qe-light smt)')]
        started = time.monotonic()
        attempts = []
        proof = 'unknown'
        for index, (name, tactic) in enumerate(tactics):
            remaining = self.timeout - (time.monotonic() - started)
            if remaining <= 0:
                break
            budget = min(5.0, remaining / 3) if index < len(tactics) - 1 else remaining
            proof_label = label + '_equivalence' + (f'_{name}' if index else '')
            try:
                proof = self.invoke(proof_label, f"(assert {smt(['xor', result, quantified])})",
                                    f'(check-sat-using {tactic})', timeout=budget)
            except RegionFailure as exc:
                if exc.status != Status.INCOMPLETE:
                    raise
                proof = 'timeout'
            attempts.append(dict(tactic=name, query=(self.queries[-1]['query'] if self.queries
                                                     else proof_label + '.smt2'), result=proof))
            if proof in ('sat', 'unsat'):
                break
        if proof != "unsat":
            raise RegionFailure(Status.INCOMPLETE, f"{label} equivalence returned {proof[:100]}")
        self.projection_certificates.append(dict(label=label, status='UNSAT',
                                                  query=attempts[-1]['query'], attempts=attempts))
        (self.output / 'queries.json').write_text(json.dumps(self.metrics(), indent=2) + '\n')
        return result
