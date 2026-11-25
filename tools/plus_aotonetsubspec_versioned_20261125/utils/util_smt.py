#!/usr/bin/env python3
"""
SMT expression utilities: parsing, AST, and constraint helpers.

- AST: tokenize/parse/serialize SMT2 S-expressions, let expansion, variable extraction.
- Expression: find_matching_paren, prefix_string_to_constraint, etc.
- Z3: parse_z3_output, append_check_sat, append_get_model, model Config equality extraction.
"""

import re
import logging
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

logger = logging.getLogger(__name__)

# SMT2 keywords that should not be treated as symbolic variables
_SMT2_KEYWORDS = {
    'assert', 'declare-fun', 'define-fun', 'check-sat', 'set-option',
    'not', 'and', 'or', 'ite', 'let',
    '<', '<=', '>', '>=', '=', '=>', '+', '-', '*', 'div', 'mod',
    'bvnot', 'bvor', 'bvand', 'bvule', 'bvult', 'extract',
    'true', 'false',
    'Bool', 'Int', 'BitVec', '_'
}
_RE_BIN_CONST = re.compile(r'#b[0-1]+$')
_RE_HEX_CONST = re.compile(r'#[xX][0-9a-fA-F]+$')
_RE_DEC_CONST = re.compile(r'\d+$')


# ---------------------------------------------------------------------------
# AST: tokenize / parse / serialize
# ---------------------------------------------------------------------------

def tokenize_smt2_sexpr(expr: str) -> List[str]:
    """Tokenize an SMT2 S-expression string into tokens including parentheses."""
    tokens: List[str] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c in '()':
            tokens.append(c)
            i += 1
            continue
        if c == '|':
            start = i
            i += 1
            while i < n:
                if expr[i] == '|' and (i == start + 1 or expr[i - 1] != '\\'):
                    tokens.append(expr[start:i + 1])
                    i += 1
                    break
                elif expr[i] == '\\' and i + 1 < n and expr[i + 1] == '|':
                    i += 2
                else:
                    i += 1
            else:
                i = start + 1
                while i < n and (not expr[i].isspace()) and expr[i] not in '()':
                    i += 1
                tokens.append(expr[start:i])
            continue
        if c == '"':
            start = i
            i += 1
            while i < n:
                if expr[i] == '"' and expr[i - 1] != '\\':
                    tokens.append(expr[start:i + 1])
                    i += 1
                    break
                i += 1
            else:
                tokens.append(expr[start:])
            continue
        start = i
        while i < n and (not expr[i].isspace()) and expr[i] not in '()':
            i += 1
        tokens.append(expr[start:i])
    return tokens


def parse_smt2_sexpr(tokens: List[str]) -> Optional[object]:
    """Parse SMT2 S-expression tokens into nested list/str AST. Returns first top-level expression or None."""
    stack: List[List[object]] = [[]]
    for t in tokens:
        if t == '(':
            new_list: List[object] = []
            stack[-1].append(new_list)
            stack.append(new_list)
        elif t == ')':
            if len(stack) == 1:
                return None
            stack.pop()
        else:
            stack[-1].append(t)
    if len(stack) != 1 or not stack[0]:
        return None
    return stack[0][0] if len(stack[0]) == 1 else stack[0][0]


def serialize_smt2_sexpr(node: object) -> str:
    """Serialize S-expression AST back to SMT2 string."""
    if isinstance(node, str):
        return node
    if not isinstance(node, list):
        return str(node)
    if not node:
        return "()"
    parts = [serialize_smt2_sexpr(child) for child in node]
    return "(" + " ".join(parts) + ")"


def deep_copy_ast(node: object) -> object:
    """Deep copy an AST node."""
    if isinstance(node, str):
        return node
    if not isinstance(node, list):
        return node
    return [deep_copy_ast(child) for child in node]


def expand_let_ast(node: object, env: Dict[str, object]) -> object:
    """Expand all let expressions in an AST (simultaneous let semantics)."""
    if isinstance(node, str):
        return deep_copy_ast(env.get(node, node))
    if not isinstance(node, list) or not node:
        return node
    head = node[0]
    if head == 'let' and len(node) >= 3:
        bindings_node, body_node = node[1], node[2]
        if not isinstance(bindings_node, list):
            return [expand_let_ast(c, env) for c in node]
        new_env = dict(env)
        for b in bindings_node:
            if isinstance(b, list) and len(b) >= 2 and isinstance(b[0], str):
                new_env[b[0]] = expand_let_ast(b[1], env)
        return expand_let_ast(body_node, new_env)
    return [expand_let_ast(c, env) for c in node]


def expand_let_expressions_ast(expr: str) -> str:
    """Expand all let expressions in a single SMT expression using AST."""
    if not expr or not expr.strip():
        return expr
    try:
        tokens = tokenize_smt2_sexpr(expr)
        tree = parse_smt2_sexpr(tokens)
        if tree is None:
            return expr
        expanded_tree = expand_let_ast(tree, {})
        expanded_str = serialize_smt2_sexpr(expanded_tree)
        if expanded_str.count('(') != expanded_str.count(')'):
            return expr
        return expanded_str
    except Exception:
        return expr


def expand_let_expressions_ast_batch(exprs: List[str]) -> List[str]:
    """Expand let expressions in a list of SMT expressions."""
    return [expand_let_expressions_ast(e) for e in exprs]


# SSA_RETURN* temporary variables: (assert (= SSA_RETURNn body)) defines them; we inline body and drop declare-fun.
_RE_SSA_RETURN = re.compile(r'^SSA_RETURN\d+$')


def _is_ssa_return_definition_ast(tree: object) -> Optional[Tuple[str, object]]:
    """If tree is (assert (= SSA_RETURNn body)), return (name, body_ast); else None."""
    if not isinstance(tree, list) or len(tree) < 2:
        return None
    if tree[0] != 'assert':
        return None
    eq = tree[1]
    if not isinstance(eq, list) or len(eq) != 3 or eq[0] != '=':
        return None
    var = eq[1]
    if not isinstance(var, str) or not _RE_SSA_RETURN.match(var):
        return None
    return (var, eq[2])


def _extract_ssa_return_definitions(assert_exprs: List[str]) -> Tuple[Dict[str, object], Set[int]]:
    """Find asserts of the form (assert (= SSA_RETURNn body)). Return (name -> body_ast, defining indices)."""
    ssa_defs: Dict[str, object] = {}
    defining_indices: Set[int] = set()
    for i, expr in enumerate(assert_exprs):
        if not expr or not expr.strip():
            continue
        try:
            tokens = tokenize_smt2_sexpr(expr)
            tree = parse_smt2_sexpr(tokens)
            res = _is_ssa_return_definition_ast(tree)
            if res is not None:
                name, body_ast = res
                ssa_defs[name] = body_ast
                defining_indices.add(i)
        except Exception:
            continue
    return (ssa_defs, defining_indices)


def _substitute_ssa_return_ast(node: object, defs: Dict[str, object], substituting: Set[str]) -> object:
    """Replace every SSA_RETURNn in AST with its body (recursive; avoiding cycles)."""
    if isinstance(node, str):
        if node in defs and node not in substituting:
            body = defs[node]
            return _substitute_ssa_return_ast(deep_copy_ast(body), defs, substituting | {node})
        return node
    if not isinstance(node, list):
        return node
    return [_substitute_ssa_return_ast(c, defs, substituting) for c in node]


def expand_ssa_return_in_asserts(assert_exprs: List[str]) -> Tuple[List[str], Set[str]]:
    """
    Expand SSA_RETURN* temporaries: drop (assert (= SSA_RETURNn body)) and replace every
    occurrence of SSA_RETURNn in other asserts with body. Returns (new_assert_list, set of SSA_RETURN names).
    """
    ssa_defs, defining_indices = _extract_ssa_return_definitions(assert_exprs)
    if not ssa_defs:
        return (list(assert_exprs), set())

    new_asserts: List[str] = []
    for i, expr in enumerate(assert_exprs):
        if i in defining_indices:
            continue
        if not expr or not expr.strip():
            new_asserts.append(expr)
            continue
        try:
            tokens = tokenize_smt2_sexpr(expr)
            tree = parse_smt2_sexpr(tokens)
            if tree is None:
                new_asserts.append(expr)
                continue
            new_tree = _substitute_ssa_return_ast(tree, ssa_defs, set())
            new_asserts.append(serialize_smt2_sexpr(new_tree))
        except Exception:
            new_asserts.append(expr)
    return (new_asserts, set(ssa_defs.keys()))


def is_symbolic_atom(tok: str) -> bool:
    """True if token is a symbolic variable (not keyword or constant)."""
    if tok in _SMT2_KEYWORDS:
        return False
    if _RE_BIN_CONST.fullmatch(tok) or _RE_HEX_CONST.fullmatch(tok) or _RE_DEC_CONST.fullmatch(tok):
        return False
    return True


def extract_symbolic_variables_let_aware(expr: str) -> List[str]:
    """Extract symbolic variables from SMT expression, handling let without full expansion."""
    tokens = tokenize_smt2_sexpr(expr)
    tree = parse_smt2_sexpr(tokens)
    if tree is None:
        return []

    def fv(node: object, env: Dict[str, Set[str]]) -> Set[str]:
        if isinstance(node, str):
            if node in env:
                return env[node]
            return {node} if is_symbolic_atom(node) else set()
        if not isinstance(node, list) or not node:
            return set()
        head = node[0]
        if head == 'let' and len(node) >= 3:
            bindings_node, body_node = node[1], node[2]
            if not isinstance(bindings_node, list):
                return fv(body_node, env)
            new_bindings: Dict[str, Set[str]] = {}
            for b in bindings_node:
                if isinstance(b, list) and len(b) >= 2 and isinstance(b[0], str):
                    new_bindings[b[0]] = fv(b[1], env)
            extended = dict(env)
            extended.update(new_bindings)
            return fv(body_node, extended)
        out: Set[str] = set()
        for c in node:
            out |= fv(c, env)
        return out

    return list(fv(tree, {}))


# ---------------------------------------------------------------------------
# Expression: paren / balanced / prefix constraint
# ---------------------------------------------------------------------------

def find_matching_paren(text: str, start: int) -> int:
    """Find matching closing paren for opening paren at start. Skips string literals."""
    if start >= len(text) or text[start] != '(':
        return -1
    depth = 1
    i = start + 1
    while i < len(text) and depth > 0:
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
        elif text[i] == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == '\\' and i + 1 < len(text) else 1
            continue
        i += 1
    return i - 1 if depth == 0 else -1


def prefix_string_to_constraint_tuple(ip_mask: str, variable: str = "|0_dst-ip|") -> Optional[Tuple[int, int, str, str]]:
    """Convert IP prefix string to (high_bit, low_bit, variable, value_str) for constraint building."""
    try:
        import ipaddress
        network = ipaddress.ip_network(ip_mask, strict=False)
        prefix_length = network.prefixlen
        ip_int = int(network.network_address)
        high_bit = 31
        low_bit = 32 - prefix_length
        if prefix_length % 4 == 0:
            extracted_value = (ip_int >> (32 - prefix_length)) & ((1 << prefix_length) - 1)
            value_str = f"#x{extracted_value:x}"
        else:
            extracted_value = (ip_int >> (32 - prefix_length)) & ((1 << prefix_length) - 1)
            value_str = f"#b{format(extracted_value, f'0{prefix_length}b')}"
        return (high_bit, low_bit, variable, value_str)
    except (ValueError, AttributeError, ImportError):
        return None


def prefix_string_to_constraint(ip_mask: str, variable: str = "|0_dst-ip|") -> Optional[str]:
    """Convert IP prefix string (e.g. 192.0.2.0/24) to SMT constraint string."""
    result = prefix_string_to_constraint_tuple(ip_mask, variable)
    if not result:
        return None
    high_bit, low_bit, var, value_str = result
    return f"(= ((_ extract {high_bit} {low_bit}) {var}) {value_str})"


# ---------------------------------------------------------------------------
# Z3 output parsing and device extraction
# ---------------------------------------------------------------------------

def parse_z3_output(result) -> Tuple[bool, str]:
    """Parse Z3 output and return (is_sat, output_message).

    Handles SAT/UNSAT on the first non-empty line (supports trailing get-model output),
    errors, and compatibility for "unknown constant" errors.
    """
    output = result.stdout.strip()
    if result.stderr.strip():
        logger.warning(f"Z3 stderr: {result.stderr.strip()}")

    first_result_line = ""
    for line in output.splitlines():
        candidate = line.strip().lower()
        if candidate:
            first_result_line = candidate
            break

    # First line is authoritative even when get-model adds a model (sat) or reports
    # "(error \"model is not available\")" after unsat.
    if first_result_line == "sat":
        return True, "sat"
    if first_result_line == "unsat":
        return False, "unsat"

    if result.returncode != 0:
        logger.warning(f"Z3 return code: {result.returncode}")

    if "(error" in output:
        lines = output.split('\n')
        error_lines = [line for line in lines if line.startswith('(error')]
        if error_lines:
            error_msg = '; '.join(error_lines)
            if "unknown constant" in error_msg:
                logger.warning(f"Compatibility issue detected: {error_msg}")
                logger.info("Attempting to extract SAT/UNSAT result despite the error...")
                last_line = ""
                for line in reversed(lines):
                    line = line.strip()
                    if line and not line.startswith('(error'):
                        last_line = line
                        break
                if last_line == "sat":
                    logger.info("✓ Extracted result: SAT (compatibility mode)")
                    return True, "sat (compatibility mode)"
                if last_line == "unsat":
                    logger.info("✓ Extracted result: UNSAT (compatibility mode)")
                    return False, "unsat (compatibility mode)"
                logger.warning(f"Could not extract SAT/UNSAT. Last line: '{last_line}'")
                return False, f"Z3 error: {error_msg}"
            return False, f"Z3 error: {error_msg}"

    if output == "sat":
        return True, output
    if output == "unsat":
        return False, output
    logger.warning(f"Unexpected Z3 output: {output}")
    return False, f"Unexpected output: {output}"


def append_check_sat(content: str) -> str:
    """Append (check-sat) to SMT2 content if not already present."""
    content = content.rstrip()
    if "(check-sat)" not in content:
        content += "\n(check-sat)"
    return content + "\n"


def append_get_model(content: str) -> str:
    """Append (get-model) after (check-sat) if not already present."""
    content = content.rstrip()
    if "(get-model)" in content:
        return content + "\n"
    if "(check-sat)" in content:
        content = content.replace("(check-sat)", "(check-sat)\n(get-model)", 1)
    else:
        content += "\n(get-model)"
    return content + "\n"


def parse_z3_model_config_assignments(model_output: str) -> Dict[str, str]:
    """Parse (define-fun Config_...) value assignments from Z3 (get-model) output."""
    assignments: Dict[str, str] = {}
    lines = model_output.split('\n')
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        var_match = re.search(r'\(define-fun\s+(Config_\S+)\s+\(\)', stripped)
        if var_match:
            var_name = var_match.group(1)
            type_match = re.search(r'\(\)\s+((?:\([^\)]+\)|[^\s\(]+))', stripped)
            if type_match:
                type_end = type_match.end()
                remaining = stripped[type_end:].strip()
                if remaining and not remaining.startswith('('):
                    value = remaining.rstrip(')').strip()
                else:
                    value_parts: List[str] = []
                    j = i + 1
                    paren_depth = stripped.count('(') - stripped.count(')')
                    while j < len(lines) and paren_depth > 0:
                        next_line = lines[j].strip()
                        paren_depth += next_line.count('(') - next_line.count(')')
                        if paren_depth == 0:
                            if next_line.endswith(')'):
                                value_parts.append(next_line[:-1].strip())
                            value = ' '.join(value_parts).strip() if value_parts else ''
                            i = j
                            break
                        value_parts.append(next_line)
                        j += 1
                    else:
                        value = ' '.join(value_parts).strip() if value_parts else ''
                        i = j - 1 if value_parts else i
                if value:
                    assignments[var_name] = re.sub(r'\s+', ' ', value.strip())
        i += 1
    return assignments


def _config_location_var_names(config_vars: Iterable[Union[str, object]]) -> List[str]:
    """Extract Config variable names from strings or objects with a .name attribute."""
    names: List[str] = []
    for item in config_vars:
        if isinstance(item, str):
            names.append(item)
        else:
            names.append(item.name)
    return names


class ModelConfigEqualitiesStore:
    """Store (= Config_* value) equalities from Z3 impact-check models."""

    def __init__(self) -> None:
        self._equalities: Dict[str, str] = {}

    def update_from_assignments(
        self,
        assignments: Dict[str, str],
        config_var_names: Set[str],
        *,
        info: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Store equality constraints from a Config_* name -> value map (e.g. MaxSMT model)."""
        for name in config_var_names:
            if name in assignments:
                equality = f"(= {name} {assignments[name]})"
                self._equalities[name] = equality
                if info:
                    info(f"    Model equality for {name}: {equality}")
            else:
                logger.warning(f"    Config variable {name} not found in Z3 model")

    def update_from_z3_output(
        self,
        model_output: str,
        config_var_names: Set[str],
        *,
        info: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Parse model output and store equality constraints for the given config vars."""
        self.update_from_assignments(
            parse_z3_model_config_assignments(model_output),
            config_var_names,
            info=info,
        )

    def equality_for(self, config_var_name: str) -> str:
        """Return stored model-correct equality for a config location variable."""
        if config_var_name not in self._equalities:
            raise ValueError(
                f"No model equality for {config_var_name}; impact check should have stored it"
            )
        return self._equalities[config_var_name]

    def append_missing_to_subspec(
        self,
        subspec_parts: List[str],
        config_vars: Iterable[Union[str, object]],
        *,
        info: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Add model equalities for config vars not already present in subspec_parts."""
        log = info or logger.info
        for config_var_name in _config_location_var_names(config_vars):
            if any(config_var_name in part for part in subspec_parts):
                continue
            model_constraint = self.equality_for(config_var_name)
            subspec_parts.append(model_constraint)
            log(f"    Added model equality for {config_var_name}: {model_constraint}")


_AG_SMT2_HOST_RE = re.compile(r'complete_(?:forward|reverse)_([^.]+)\.smt2$')


def get_ag_host_device_from_smt2_path(file_path: Union[str, Path]) -> Optional[str]:
    """Return assume-guarantee slice host from complete_forward/reverse filename."""
    match = _AG_SMT2_HOST_RE.search(Path(file_path).name)
    return match.group(1) if match else None


def get_device_for_config_var(config_var, devices: List[str]) -> Optional[str]:
    """Get device for processing a Config variable occurrence.

    Prefer the AG slice host from ``complete_forward_{host}`` / ``complete_reverse_{host}``
    (the file where this assert appears). Config_* may name another router (e.g. Config_r1_*
    inside complete_reverse_r3.smt2); fall back to name prefix only for non-AG paths (e.g. sliced).
    """
    host = get_ag_host_device_from_smt2_path(config_var.file_path)
    if host:
        return host
    for device in sorted(devices, key=len, reverse=True):
        if config_var.name.startswith(f'Config_{device}_'):
            return device
    name_match = re.search(
        r'^Config_([a-zA-Z0-9_-]+?)_(RouteFilterList|RoutingPolicy|CommunityList)', config_var.name
    )
    if name_match:
        potential_device = name_match.group(1)
        if potential_device in devices:
            return potential_device
    return None


# ---------------------------------------------------------------------------
# Subspec extraction and conversion (from util_subspec)
# ---------------------------------------------------------------------------

def strip_subspec_suffixes(subspec: str) -> Tuple[str, str]:
    """Strip [from xxx] and AND configurable/nonconfigurable clauses from the end of a subspec."""
    if not subspec or subspec.strip() == "empty":
        return (subspec, "")
    rest = subspec.strip()
    suffix_parts: List[str] = []
    m_from = re.search(r"\s+\[from\s+(\S+)\]$", rest)
    if m_from:
        suffix_parts.append(f" [from {m_from.group(1)}]")
        rest = rest[: m_from.start()].strip()
    and_clause_re = re.compile(
        r"\s+AND\s+(configurable|nonconfigurable)(\s+\(permit\)|\s+\(deny\))?\s*=\s*\{[^}]*\}\s*$"
    )
    while True:
        m = and_clause_re.search(rest)
        if not m:
            break
        suffix_parts.append(rest[m.start() :])
        rest = rest[: m.start()].strip()
    suffix_to_restore = "".join(reversed(suffix_parts))
    return (rest, suffix_to_restore)


def extract_community_lists_from_line_subspec(subspec: str) -> Optional[Tuple[List[str], List[str], List[str], List[str]]]:
    """Extract configurable/nonconfigurable (permit)/(deny) community lists from a line-level subspec."""
    if not subspec or subspec.strip() == "empty":
        return None

    def parse_clause(key: str) -> List[str]:
        pat = re.compile(r"\b" + re.escape(key) + r"\s*=\s*\{([^}]*)\}", re.IGNORECASE)
        m = pat.search(subspec)
        if not m:
            return []
        inner = m.group(1).strip()
        if not inner:
            return []
        return [s.strip() for s in inner.split(",") if s.strip()]

    configurable_permit = parse_clause("configurable (permit)")
    nonconfigurable_permit = parse_clause("nonconfigurable (permit)")
    configurable_deny = parse_clause("configurable (deny)")
    nonconfigurable_deny = parse_clause("nonconfigurable (deny)")
    for key in ["configurable (permit)", "nonconfigurable (permit)", "configurable (deny)", "nonconfigurable (deny)"]:
        if re.search(r"\b" + re.escape(key) + r"\s*=\s*\{", subspec) is None:
            return None
    return (configurable_permit, nonconfigurable_permit, configurable_deny, nonconfigurable_deny)


def get_action_from_core_subspec(core_subspec: str) -> Optional[bool]:
    """Determine action (permit/deny) from core line-level subspec."""
    if not core_subspec:
        return None
    # Allow hyphen in config name for hostnames like edge-15, aggregation-12
    if re.search(r"\(\s*=\s+Config_[a-zA-Z0-9_-]+_action\s+true\s*\)", core_subspec):
        return True
    if re.search(r"\(\s*=\s+Config_[a-zA-Z0-9_-]+_action\s+false\s*\)", core_subspec):
        return False
    return None


def _extract_variables_from_line(line: str) -> Set[str]:
    variables = set()
    variables.update(re.findall(r'\|[^|]+\|', line))
    variables.update(re.findall(r'Config_[a-zA-Z0-9_-]+', line))
    return variables


def _unwrap_goal_content(content: str) -> List[str]:
    """If content is (goal A B ... :attr value), return [A, B, ...] as SMT strings (assertions only; skip :attr/value)."""
    content = content.strip()
    if not content.startswith("(goal ") and not content.startswith("(goal\n"):
        return [content]
    try:
        tokens = tokenize_smt2_sexpr(content)
        tree = parse_smt2_sexpr(tokens)
        if tree is None or not isinstance(tree, list) or not tree or tree[0] != "goal":
            return [content]
        assertions = []
        i = 1
        while i < len(tree):
            child = tree[i]
            if isinstance(child, str) and child.startswith(":"):
                i += 2
                continue
            if isinstance(child, list) and child:
                assertions.append(serialize_smt2_sexpr(child))
            i += 1
        return assertions if assertions else [content]
    except Exception:
        return [content]


def _parse_goals_structure(output: str) -> List[dict]:
    lines = output.split('\n')
    goals_data = []
    current_line = ""
    paren_count = 0
    in_goal = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("(goals") or line.startswith("(goal"):
            in_goal = True
            continue
        if not in_goal:
            continue
        for char in line:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
        current_line += " " + line
        if paren_count == 0 and current_line.strip():
            content = current_line.strip()
            if content and content != ")":
                goals_data.append({'content': content, 'line_number': len(goals_data) + 1})
            current_line = ""
    return goals_data


def replace_config_variables_in_subspec(
    subspec: str,
    line1_variable_names: Optional[Set[str]] = None,
    lineN_variable_names: Optional[Set[str]] = None,
    config_mapping: Optional[Dict[str, str]] = None
) -> str:
    """Replace Config variable names in a 'same as Line1' subspec with LineN variable names."""
    if not subspec:
        return subspec
    if config_mapping:
        mapping = config_mapping
    elif line1_variable_names and lineN_variable_names:
        mapping: Dict[str, str] = {}
        for line1_var in line1_variable_names:
            last_underscore = line1_var.rfind('_')
            if last_underscore == -1:
                continue
            field_name = line1_var[last_underscore + 1:]
            for lineN_var in lineN_variable_names:
                if lineN_var.endswith(f'_{field_name}'):
                    mapping[line1_var] = lineN_var
                    break
        if not mapping:
            return subspec
    else:
        return subspec
    result = subspec
    for old_var, new_var in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = rf'(?<![a-zA-Z0-9_-]){re.escape(old_var)}(?![a-zA-Z0-9_-])'
        result = re.sub(pattern, new_var, result)
    vars_to_check = list(mapping.keys())
    target_vars_to_check = list(mapping.values())
    if vars_to_check and target_vars_to_check:
        line1_pattern = None
        for line1_var in vars_to_check:
            prefix_match = re.search(r'(Config_[^_]+(?:__[^_]+)*__Line1__)', line1_var)
            if prefix_match:
                line1_pattern = prefix_match.group(1)
                break
        if line1_pattern:
            lineN_pattern = None
            for lineN_var in target_vars_to_check:
                prefix_match = re.search(r'(Config_[^_]+(?:__[^_]+)*__Line\d+__)', lineN_var)
                if prefix_match:
                    lineN_pattern = prefix_match.group(1)
                    break
            if lineN_pattern:
                remaining_pattern = rf'(?<![a-zA-Z0-9_-]){re.escape(line1_pattern)}[^)\s]+(?![a-zA-Z0-9_-])'
                if re.search(remaining_pattern, result):
                    def replace_remaining(match):
                        return match.group(0).replace(line1_pattern, lineN_pattern, 1)
                    result = re.sub(remaining_pattern, replace_remaining, result)
    return result


def extract_config_constraints_from_z3_goal(
    z3_output: str,
    config_names: Set[str],
    original_constraints_map: Optional[Dict[str, str]] = None
) -> str:
    """Extract Config variable constraints from Z3 simplification goal output."""
    if not z3_output or not config_names:
        return ""
    goals_data = _parse_goals_structure(z3_output)
    if not goals_data:
        logger.debug("No goals found in Z3 output")
        return ""
    config_lines = []
    for line_data in goals_data:
        content = line_data['content'].strip()
        if content and not content.startswith(':') and content not in ['(goal', ')']:
            for config_name in config_names:
                if config_name in content:
                    config_lines.append(line_data)
                    break
    if not config_lines:
        return ""
    all_variables = set()
    for line_data in config_lines:
        all_variables.update(_extract_variables_from_line(line_data['content']))
    related_lines = []
    visited_lines = set()
    max_iterations = 100
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        new_variables = set()
        for line_data in goals_data:
            content = line_data['content'].strip()
            if content and not content.startswith(':') and content not in ['(goal', ')']:
                line_variables = _extract_variables_from_line(content)
                if line_variables.intersection(all_variables):
                    line_key = (content, line_data.get('line_number', 0))
                    if line_key not in visited_lines:
                        related_lines.append(line_data)
                        visited_lines.add(line_key)
                        new_variables.update(line_variables)
        if new_variables.issubset(all_variables):
            break
        all_variables.update(new_variables)
    constraint_parts = []
    for line_data in related_lines:
        content = line_data['content'].strip()
        if content and not content.startswith(':') and content not in ['(goal', ')']:
            if content.startswith("(goal ") or content.startswith("(goal\n"):
                for assertion in _unwrap_goal_content(content):
                    if assertion and assertion != ")":
                        constraint_parts.append(assertion)
            else:
                constraint_parts.append(content)
    if original_constraints_map:
        found_config_names = set()
        for constraint in constraint_parts:
            found_config_names.update(re.findall(r'Config_[a-zA-Z0-9_-]+', constraint))
            found_config_names.update(
                m.strip("|") for m in re.findall(r'\|Config_[a-zA-Z0-9_-]+\|', constraint)
            )
        missing_config_names = config_names - found_config_names
        if missing_config_names:
            for missing_config_name in missing_config_names:
                if missing_config_name in original_constraints_map:
                    orig = original_constraints_map[missing_config_name]
                    if " AND " in orig:
                        constraint_parts.extend([p.strip() for p in orig.split(" AND ") if p.strip()])
                    else:
                        constraint_parts.append(orig)
    if constraint_parts:
        return " AND ".join(constraint_parts)
    return ""


def _iter_goal_assertion_contents(z3_output: str) -> List[str]:
    """Flat list of goal assertion strings from Z3 simplify output."""
    goals_data = _parse_goals_structure(z3_output)
    assertions: List[str] = []
    for line_data in goals_data:
        content = line_data["content"].strip()
        if not content or content.startswith(":") or content in ("(goal", ")"):
            continue
        if content.startswith("(goal ") or content.startswith("(goal\n"):
            for assertion in _unwrap_goal_content(content):
                if assertion and assertion != ")":
                    assertions.append(assertion)
        else:
            assertions.append(content)
    return assertions


def partition_configs_by_z3_goal_connectivity(
    z3_output: str,
    config_names: Sequence[str],
) -> List[List[str]]:
    """Partition location Config_* names by connected components in a simplification goal.

    Two variables are adjacent if they co-occur in the same goal assertion; connectivity
    is the transitive closure (same expansion idea as extract_config_constraints_from_z3_goal,
    via Config_* and |quoted| tokens extracted by _extract_variables_from_line).

    Config names that never appear in the goal become singleton groups (order preserved).
    Bare Config_xxx and |Config_xxx| are treated as the same node.
    """
    if not config_names:
        return []

    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Alias bare Config_xxx with |Config_xxx|
    for name in config_names:
        union(name, f"|{name}|")

    for assertion in _iter_goal_assertion_contents(z3_output or ""):
        vars_in_line = list(_extract_variables_from_line(assertion))
        if len(vars_in_line) < 2:
            if len(vars_in_line) == 1:
                find(vars_in_line[0])
            continue
        head = vars_in_line[0]
        for other in vars_in_line[1:]:
            union(head, other)

    root_to_group: Dict[str, List[str]] = {}
    root_order: List[str] = []
    for name in config_names:
        root = find(name)
        if root not in root_to_group:
            root_to_group[root] = []
            root_order.append(root)
        root_to_group[root].append(name)

    return [root_to_group[r] for r in root_order]

def subspec_string_to_list(subspec: str) -> List[str]:
    """Convert subspec string to list of constraint strings."""
    if not subspec or subspec.strip() in ("", "empty"):
        return []
    return [part.strip() for part in subspec.split(" AND ") if part.strip()]


def subspec_string_to_smt2_and(subspec: str) -> str:
    """Convert subspec string to SMT2 (and ...) format."""
    if not subspec or subspec.strip() in ("", "empty"):
        return ""
    parts = subspec_string_to_list(subspec)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(and " + " ".join(parts) + ")"


def subspec_to_smt2_asserts(subspec: str) -> List[str]:
    """Convert subspec string to list of SMT2 assert statements."""
    if subspec == "empty" or not subspec.strip():
        return []
    return subspec_string_to_list(subspec)


def extract_constraints_excluding_field(line_level_subspecs: str, field_names: List[str]) -> List[str]:
    """Extract constraints from line-level subspecs that do not contain any of the specified fields."""
    if not line_level_subspecs or line_level_subspecs.strip() in ("", "empty"):
        return []
    if not field_names:
        return subspec_string_to_list(line_level_subspecs)
    constraints = subspec_string_to_list(line_level_subspecs)
    return [c for c in constraints if not any(fn in c for fn in field_names)]


def get_bounds_for_single_config_variable(config_var_name: str) -> List[str]:
    """Get bounds constraints for a single config variable based on its suffix."""
    bounds = []
    if config_var_name.endswith('_length') or config_var_name.endswith('_prefix_range_start') or config_var_name.endswith('_prefix_range_end'):
        bounds.append(f"(assert (>= {config_var_name} 0))")
        bounds.append(f"(assert (<= {config_var_name} 32))")
        if config_var_name.endswith('_length'):
            base_name = config_var_name[:-7]
            bounds.append(f"(assert (>= {base_name}_prefix_range_start {config_var_name}))")
            bounds.append(f"(assert (>= {base_name}_prefix_range_end {config_var_name}))")
        elif config_var_name.endswith('_prefix_range_start'):
            base_name = config_var_name[:-19]
            bounds.append(f"(assert (>= {config_var_name} {base_name}_length))")
        elif config_var_name.endswith('_prefix_range_end'):
            base_name = config_var_name[:-17]
            bounds.append(f"(assert (>= {config_var_name} {base_name}_length))")
    elif config_var_name.endswith('_prepend_aspath_cost'):
        bounds.append(f"(assert (>= {config_var_name} 0))")
    elif config_var_name.endswith('_weight') and '_SrPolicy_' in config_var_name:
        # SR candidate weight domain (aligned with Batfish SrCandidatePath / RFC 9256):
        # - omit weight ⇒ default 1 (parser); SpecLens domain still requires w >= 1
        # - w = 0 is invalid encoding (not zero share); excluded by >= 1
        # - negatives excluded; upper = uint32 max (RFC has no CLI upper bound)
        bounds.append(f"(assert (>= {config_var_name} 1))")
        bounds.append(f"(assert (<= {config_var_name} 4294967295))")
    elif config_var_name.endswith('_cost') and '_Isis_' in config_var_name:
        # RFC 5305 extended IS-IS metric: unsigned 24-bit value.
        bounds.append(f"(assert (>= {config_var_name} 0))")
        bounds.append(f"(assert (<= {config_var_name} 16777215))")
    elif '_set_localpreference_' in config_var_name or '_set_metric_' in config_var_name:
        bounds.append(f"(assert (>= {config_var_name} 0))")
        bounds.append(f"(assert (<= {config_var_name} 4294967295))")
    return bounds


def get_bounds_for_multiple_config_variables(config_var_names: List[str]) -> List[str]:
    """Get bounds for multiple config variables, deduplicated."""
    seen: Set[str] = set()
    result: List[str] = []
    for name in config_var_names:
        for b in get_bounds_for_single_config_variable(name):
            if b not in seen:
                seen.add(b)
                result.append(b)
    return sorted(result)


def is_ip_mask_pair(var1_name: str, var2_name: str) -> bool:
    """Check if two config variable names form an ip/mask pair."""
    if var1_name.endswith("__ip") and var2_name.endswith("__mask"):
        return var1_name[:-4] == var2_name[:-6]
    if var1_name.endswith("__mask") and var2_name.endswith("__ip"):
        return var1_name[:-6] == var2_name[:-4]
    return False


def extract_base_name_for_ip_mask(var_name: str) -> str:
    """Extract base name from an ip or mask variable."""
    if var_name.endswith("__ip"):
        return var_name[:-4]
    if var_name.endswith("__mask"):
        return var_name[:-6]
    return var_name


def get_mask_variable_names_from_pairs(pairs: List[Tuple[str, str]]) -> Set[str]:
    """Return the set of mask variable names from a list of (ip_var_name, mask_var_name) pairs."""
    return {mask_name for (_ip_name, mask_name) in pairs}
