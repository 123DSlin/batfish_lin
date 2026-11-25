"""Shared symbol parsing helpers; preserve the original SMT token semantics."""
import re
from pathlib import Path
from typing import List, Set, Optional
from consistency.route_binder import SmtSymbolTable
from utils.util_smt import extract_symbolic_variables_let_aware
from .models import SymbolicSliceError

def _declared_symbol_set(declarations: List[str]) -> Set[str]:
    symbols: Set[str] = set()
    for declaration in declarations:
        found = extract_symbolic_variables(declaration)
        if found:
            symbols.add(found[0])
    return symbols


def _tokenize_smt2_expression(expr: str) -> List[str]:
    """
    Fast hand-rolled tokenizer for SMT2 expressions.
    Replaces regex-based tokenization for better performance.
    Supports quoted identifiers |...| (including escaped pipes \\|) and normal identifiers.
    """
    tokens: List[str] = []
    i = 0
    n = len(expr)

    while i < n:
        # Skip whitespace
        if expr[i].isspace():
            i += 1
            continue

        # Handle quoted identifier |...|
        if expr[i] == '|':
            start = i
            i += 1
            # Find closing |, handling escaped \|
            while i < n:
                if expr[i] == '|' and (i == start + 1 or expr[i-1] != '\\'):
                    # Found unescaped closing |
                    tokens.append(expr[start:i+1])
                    i += 1
                    break
                elif expr[i] == '\\' and i + 1 < n and expr[i+1] == '|':
                    # Escaped pipe, skip both chars
                    i += 2
                else:
                    i += 1
            else:
                # No closing | found, treat as normal token starting with |
                i = start + 1
                while i < n and not expr[i].isspace() and expr[i] not in '()':
                    i += 1
                tokens.append(expr[start:i])
            continue

        # Handle normal identifier (not starting with |)
        if expr[i] not in '()':
            start = i
            while i < n and not expr[i].isspace() and expr[i] not in '()':
                i += 1
            if i > start:
                tokens.append(expr[start:i])
            continue

        # Handle parentheses as separate tokens (if needed, but we skip them in filtering)
        if expr[i] in '()':
            # We skip parentheses in the tokenizer since we only care about identifiers
            i += 1
            continue

    return tokens


def extract_symbolic_variables(expr: str) -> List[str]:
    """
    Extract symbolic variables from an SMT expression.
    Uses fast hand-rolled tokenizer instead of regex for better performance.
    """
    # Use hand-rolled tokenizer instead of regex
    expr_tokens = _tokenize_smt2_expression(expr)
    symbolic_variables: List = list()

    smt2_keyword = {
        'assert', 'declare-fun', 'define-fun', 'check-sat', 'set-option',
        'not', 'and', 'or', 'ite', 'let',
        '<', '<=', '>', '>=', '=', '=>', '+', '-', '*', 'div', 'mod',
        'bvnot', 'bvor', 'bvand', 'bvule', 'bvult', 'extract',
        'true', 'false',
        'Bool', 'Int', 'BitVec', '_'
    }

    for token in expr_tokens:
        if token in smt2_keyword:
            continue
        elif re.fullmatch(r'#b[0-1]+', token):           # binary constant
            continue
        elif re.fullmatch(r'#[xX][0-9a-fA-F]+', token):  # hexadecimal constant
            continue
        elif re.fullmatch(r'\d+', token):                # decimal constant
            continue
        symbolic_variables.append(token)

    return symbolic_variables


def get_router_from_var(variable: Optional[str], routers: List[str]) -> Optional[str]:
    """Parses a variable name to determine which router it belongs to.
    Supports device names xxx, xxx-1, xxx_1 by trying longest names first (so paris_1 matches before paris).
    """
    if not variable:
        return None
    # Assumes router names are embedded in variables like `_routername_`. Try longest first.
    for router in sorted(routers, key=lambda r: (-len(r), r)):
        if f"_{router}_" in variable:
            return router
    return None


def _read_required_lines(path: Path, description: str) -> List[str]:
    try:
        values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except OSError as error:
        raise SymbolicSliceError(f"cannot read {description} {path}: {error}") from error
    result = [value for value in values if value]
    if not result:
        raise SymbolicSliceError(f"{description} is empty: {path}")
    return result


def _binding_symbols(
    binding_expressions: List[str], full_symbols: SmtSymbolTable
) -> Set[str]:
    required: Set[str] = set()
    for expression in binding_expressions:
        required.update(
            symbol
            for symbol in extract_symbolic_variables_let_aware(expression)
            if symbol in full_symbols
        )
    return required
