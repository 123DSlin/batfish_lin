"""Translate structured symbolic-route guards into auditable SMT-LIB."""

from __future__ import annotations

from itertools import combinations
from functools import lru_cache
import re
from typing import Any, Iterable, Mapping, Sequence

from .branch_loader import GuardVariable, JsonObject


class GuardEncodingError(ValueError):
    """Raised when a guard cannot be encoded without changing its semantics."""


def _smt_symbol(text: str) -> str:
    if "|" in text or "\\" in text:
        raise GuardEncodingError(f"unsupported character in SMT symbol: {text!r}")
    return f"|{text}|"


class GuardEncoder:
    """Encode guard ASTs and the at-most-k link-failure model.

    Each exported guard variable receives an independent Boolean symbol.  When
    the corresponding Minesweeper ``FAILED-EDGE`` variable exists in a device
    slice, :meth:`bridge_expressions` connects the two representations.  Remote
    links remain symbolic but still participate in the global failure budget.
    """

    SUPPORTED_OPERATORS = {"TRUE", "FALSE", "VARIABLE", "NOT", "AND", "OR"}

    def __init__(self, guard_variables: Sequence[GuardVariable]) -> None:
        self.variables = tuple(guard_variables)
        self.variable_index = {item.variable_id: item for item in self.variables}
        if len(self.variable_index) != len(self.variables):
            raise GuardEncodingError("duplicate guard variableId")
        self._feasibility_cache = {}

    def symbol(self, variable_id: str) -> str:
        if variable_id not in self.variable_index:
            raise GuardEncodingError(f"unknown guard variable {variable_id!r}")
        variable = self.variable_index[variable_id]
        safe = re.sub(r"[^A-Za-z0-9_.:-]", "_", variable_id)
        return _smt_symbol(f"LINK-{variable.polarity}-{safe}")

    def declarations(self) -> tuple[str, ...]:
        return tuple(
            f"(declare-fun {self.symbol(item.variable_id)} () Bool)"
            for item in self.variables
        )

    def encode(self, guard: JsonObject) -> str:
        ast: Mapping[str, Any]
        if "ast" in guard:
            raw_ast = guard.get("ast")
            if not isinstance(raw_ast, Mapping):
                raise GuardEncodingError("guard.ast must be an object")
            ast = raw_ast
        else:
            ast = guard
        return self._encode_ast(ast)

    def _encode_ast(self, ast: Mapping[str, Any]) -> str:
        operator = ast.get("operator")
        if not isinstance(operator, str):
            raise GuardEncodingError("guard node is missing operator")
        operator = operator.upper()
        if operator not in self.SUPPORTED_OPERATORS:
            raise GuardEncodingError(f"unsupported guard operator {operator!r}")
        if operator == "TRUE":
            return "true"
        if operator == "FALSE":
            return "false"
        if operator == "VARIABLE":
            variable_id = ast.get("variableId")
            if not isinstance(variable_id, str):
                raise GuardEncodingError("VARIABLE node is missing variableId")
            return self.symbol(variable_id)

        children = ast.get("children")
        if not isinstance(children, list):
            raise GuardEncodingError(f"{operator} node must contain children")
        encoded = [self._encode_ast(self._mapping(child, operator)) for child in children]
        if operator == "NOT":
            if len(encoded) != 1:
                raise GuardEncodingError("NOT must have exactly one child")
            return f"(not {encoded[0]})"
        if operator == "AND":
            if not encoded:
                return "true"
            if len(encoded) == 1:
                return encoded[0]
            return f"(and {' '.join(encoded)})"
        if not encoded:
            return "false"
        if len(encoded) == 1:
            return encoded[0]
        return f"(or {' '.join(encoded)})"

    @staticmethod
    def _mapping(value: Any, parent: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise GuardEncodingError(f"{parent} child must be an object")
        return value

    def variables_in(self, guard: JsonObject) -> frozenset[str]:
        result: set[str] = set()

        def visit(ast: Mapping[str, Any]) -> None:
            if ast.get("operator") == "VARIABLE":
                variable_id = ast.get("variableId")
                if not isinstance(variable_id, str) or variable_id not in self.variable_index:
                    raise GuardEncodingError(f"unknown guard variable {variable_id!r}")
                result.add(variable_id)
            children = ast.get("children", [])
            if children is None:
                return
            if not isinstance(children, list):
                raise GuardEncodingError("guard children must be an array")
            for child in children:
                visit(self._mapping(child, str(ast.get("operator"))))

        ast = guard.get("ast") if "ast" in guard else guard
        visit(self._mapping(ast, "guard"))
        return frozenset(result)

    def evaluate(self, guard: JsonObject, failed_variables: Iterable[str]) -> bool:
        failed = frozenset(failed_variables)

        def evaluate_ast(ast: Mapping[str, Any]) -> bool:
            operator = str(ast.get("operator", "")).upper()
            if operator == "TRUE":
                return True
            if operator == "FALSE":
                return False
            if operator == "VARIABLE":
                variable_id = ast.get("variableId")
                if variable_id not in self.variable_index:
                    raise GuardEncodingError(f"unknown guard variable {variable_id!r}")
                variable = self.variable_index[variable_id]
                if variable.polarity == "UP":
                    return variable_id not in failed
                return variable_id in failed
            children = ast.get("children")
            if not isinstance(children, list):
                raise GuardEncodingError(f"{operator} node must contain children")
            values = [evaluate_ast(self._mapping(child, operator)) for child in children]
            if operator == "NOT":
                if len(values) != 1:
                    raise GuardEncodingError("NOT must have exactly one child")
                return not values[0]
            if operator == "AND":
                return all(values)
            if operator == "OR":
                return any(values)
            raise GuardEncodingError(f"unsupported guard operator {operator!r}")

        ast = guard.get("ast") if "ast" in guard else guard
        return evaluate_ast(self._mapping(ast, "guard"))

    def is_feasible_within_k(self, guard: JsonObject, k: int) -> bool:
        """Memoized Boolean restriction with a failure budget, without fault-set expansion."""

        if k < 0:
            raise ValueError("k must be non-negative")
        def simplify(op, children):
            if op == 'NOT':
                child = children[0]
                return not child if isinstance(child, bool) else (child[1] if child[0] == 'NOT' else ('NOT', child))
            identity = op == 'AND'
            if any(child is (not identity) for child in children):
                return not identity
            terms = {child for child in children if child is not identity}
            if any(simplify('NOT', (child,)) in terms for child in terms):
                return not identity
            if not terms:
                return identity
            return next(iter(terms)) if len(terms) == 1 else (op, *sorted(terms, key=repr))

        def compile_ast(node):
            op = str(node.get('operator', '')).upper()
            if op in ('TRUE', 'FALSE'):
                return op == 'TRUE'
            if op == 'VARIABLE':
                variable = node.get('variableId')
                if variable not in self.variable_index:
                    raise GuardEncodingError(f'unknown guard variable {variable!r}')
                return ('VARIABLE', variable)
            children = node.get('children')
            if op not in ('NOT', 'AND', 'OR') or not isinstance(children, list) or (op == 'NOT' and len(children) != 1):
                raise GuardEncodingError(f'invalid guard node: {op}')
            return simplify(op, tuple(compile_ast(self._mapping(child, op)) for child in children))

        @lru_cache(None)
        def restrict(expr, variable, value):
            if isinstance(expr, bool):
                return expr
            if expr[0] == 'VARIABLE':
                return value if expr[1] == variable else expr
            return simplify(expr[0], tuple(restrict(child, variable, value) for child in expr[1:]))

        @lru_cache(None)
        def zero(expr):
            if isinstance(expr, bool):
                return expr
            if expr[0] == 'VARIABLE':
                return self.variable_index[expr[1]].polarity == 'UP'
            if expr[0] == 'NOT':
                return not zero(expr[1])
            values = (zero(child) for child in expr[1:])
            return all(values) if expr[0] == 'AND' else any(values)

        def decision(expr, wanted=True):
            if expr[0] == 'VARIABLE':
                return expr[1]
            if expr[0] == 'NOT':
                return decision(expr[1], not wanted)
            child = next(item for item in expr[1:] if zero(item) != wanted)
            return decision(child, wanted)

        @lru_cache(None)
        def feasible(expr, budget):
            if isinstance(expr, bool):
                return expr
            if zero(expr):
                return True
            if budget == 0:
                return False
            variable = decision(expr)
            up = self.variable_index[variable].polarity == 'UP'
            return feasible(restrict(expr, variable, not up), budget - 1) or feasible(
                restrict(expr, variable, up), budget)

        expr = compile_ast(self._mapping(guard.get('ast', guard), 'guard'))
        key = expr, k
        if key not in self._feasibility_cache:
            self._feasibility_cache[key] = feasible(expr, k)
        return self._feasibility_cache[key]

    def satisfying_failure_assignments(
        self, guard: JsonObject, k: int
    ) -> tuple[frozenset[str], ...]:
        """Enumerate every at-most-``k`` failure set covered by ``guard``.

        Retained as an explicit regression oracle. Production Stage 2 proves
        symbolic fault coverage and does not call this enumerator.
        """

        if k < 0:
            raise ValueError("k must be non-negative")
        variable_ids = tuple(sorted(self.variable_index))
        result: list[frozenset[str]] = []
        for failure_count in range(min(k, len(variable_ids)) + 1):
            for failed in combinations(variable_ids, failure_count):
                failure_set = frozenset(failed)
                if self.evaluate(guard, failure_set):
                    result.append(failure_set)
        return tuple(result)

    def concrete_assignment_expressions(
        self, failed_variables: Iterable[str]
    ) -> tuple[str, ...]:
        """Pin every exported guard variable to one concrete failure state."""

        failed = frozenset(failed_variables)
        unknown = failed - self.variable_index.keys()
        if unknown:
            raise GuardEncodingError(
                f"unknown failed guard variable(s): {', '.join(sorted(unknown))}"
            )
        expressions: list[str] = []
        for variable in self.variables:
            is_failed = variable.variable_id in failed
            value = not is_failed if variable.polarity == "UP" else is_failed
            expressions.append(
                f"(= {self.symbol(variable.variable_id)} {'true' if value else 'false'})"
            )
        return tuple(expressions)

    def failure_term(self, variable: GuardVariable) -> str:
        symbol = self.symbol(variable.variable_id)
        failure = f"(not {symbol})" if variable.polarity == "UP" else symbol
        return f"(ite {failure} 1 0)"

    def at_most_k_expression(self, k: int) -> str:
        if k < 0:
            raise ValueError("k must be non-negative")
        if not self.variables:
            return "true"
        terms = " ".join(self.failure_term(item) for item in self.variables)
        return f"(<= (+ {terms}) {k})"

    def bridge_expressions(self, declared_symbols: Iterable[str]) -> tuple[str, ...]:
        declared = frozenset(declared_symbols)
        result: list[str] = []
        for variable in self.variables:
            candidates = (
                _smt_symbol(
                    f"0_FAILED-EDGE_{variable.first_router}_{variable.second_router}"
                ),
                _smt_symbol(
                    f"0_FAILED-EDGE_{variable.second_router}_{variable.first_router}"
                ),
            )
            failure_symbol = next((item for item in candidates if item in declared), None)
            if failure_symbol is None:
                continue
            is_up = f"(= {failure_symbol} 0)"
            meaning = is_up if variable.polarity == "UP" else f"(not {is_up})"
            result.append(f"(= {self.symbol(variable.variable_id)} {meaning})")
        return tuple(result)

    def disjunction(self, guards: Iterable[JsonObject]) -> str:
        encoded = tuple(self.encode(guard) for guard in guards)
        if not encoded:
            return "false"
        if len(encoded) == 1:
            return encoded[0]
        return f"(or {' '.join(encoded)})"
