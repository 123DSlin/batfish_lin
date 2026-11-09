#!/usr/bin/env python3
"""
SMT Slicer - Two-stage SMT encoding slicing tool

This tool performs comprehensive SMT encoding slicing for network verification:
1. Global slicing: Based on property variables to reduce encoding size
2. Device-level slicing: Based on router hostnames for modular verification

Author: Network Verification Team
"""

import re
import os
import sys
import logging
import time
import array
from typing import List, Set, Tuple, Optional, Dict
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from utils.util_smt import (
    expand_let_expressions_ast_batch,
    expand_ssa_return_in_asserts,
    extract_symbolic_variables_let_aware
)
from utils.util_log import verbose_info

# Module-level logger (used by helper classes/functions)
logger = logging.getLogger(__name__)

##########################################################################################
### SMT2 variable regex and constant regex
##########################################################################################

# smt2 variable regex (supports quoted identifiers (|...|) and normal indentifiers)
var_regex = r'(\|[^|]*?(?:\\\|[^|]*?)*\||[^\s()]+)'
var_pattern = re.compile(var_regex)

# SSA temporary definitions: (assert (= SSA_COMMUNITIESn body)), etc.
_SSA_DEF_ASSERT_RE = re.compile(r'^\(assert \(= (SSA_[A-Z]+\d+) ')
_SSA_VAR_RE = re.compile(r'\b(SSA_[A-Z]+\d+)\b')

##########################################################################################
### extract declare-fun and assert expressions
##########################################################################################

def extract_declare_fun_expressions(smt2_lines: List[str]) -> List[str]:
    """Extract declare-fun expression from the smt encoding lines"""
    declare_fun_exprs: List[str] = []
    current_expr: str = ''
    depth: int = 0
    in_declare: bool = False

    for line in smt2_lines:
        line = line.strip()
        if not line or line.startswith(';'):
            continue

        if '(declare-fun' in line:
            in_declare = True

        if in_declare:
            current_expr += ' ' + line
            depth += line.count('(') - line.count(')')

            if depth != 0:
                continue

            if current_expr.strip().startswith('(declare-fun'):
                declare_fun_exprs.append(current_expr.strip())
            current_expr = ''
            in_declare = False

    return declare_fun_exprs


def extract_assert_expressions(smt2_lines: List[str]) -> List[str]:
    """Extract assert expression from the smt encoding lines"""
    assert_exprs: List[str] = []
    current_expr: str = ''
    depth: int = 0
    in_assert: bool = False

    for line in smt2_lines:
        line = line.strip()
        if not line or line.startswith(';'):
            continue

        if '(assert' in line:
            in_assert = True

        if in_assert:
            current_expr += ' ' + line
            depth += line.count('(') - line.count(')')

            if depth != 0:
                continue

            if current_expr.strip().startswith('(assert'):
                assert_exprs.append(current_expr.strip())
            current_expr = ''
            in_assert = False

    return assert_exprs


##########################################################################################
### slice smt encoding
##########################################################################################


def _tokenize_smt2_expression(expr: str) -> List[str]:
    """
    Fast hand-rolled tokenizer for SMT2 expressions.
    Replaces regex-based tokenization for better performance.
    Supports quoted identifiers |...| (including escaped pipes \|) and normal identifiers.
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


def slice_smt_encoding(declare_fun_exprs: List[str], assert_exprs: List[str], 
                       target_vars: Set[str]) -> List[str]:
    """Slice SMT encoding based on target variables (same logic, faster data structures).

    Conceptually this computes the dependency closure over variables:
      var -> declare-fun(var)
      var -> asserts that mention var -> vars mentioned in those asserts
    """
    logger = logging.getLogger(__name__)
    max_assert_id = len(assert_exprs)
    max_declare_id = len(declare_fun_exprs)

    # --- Symbol interning: map var string -> int id (faster than set[str]) ---
    var_to_id: Dict[str, int] = {}

    def _var_id(v: str) -> int:
        existing = var_to_id.get(v)
        if existing is not None:
            return existing
        new_id = len(var_to_id)
        var_to_id[v] = new_id
        return new_id

    # declare-fun index by var-id (filled after parsing declare-funs)
    declare_fun_id_by_varid: List[int] = []

    # assert-id -> list[var-id] (deduped within the assert)
    assert_varids: List[List[int]] = [[] for _ in range(max_assert_id)]

    # var-id -> list[assert-id] (compact int arrays)
    var_assert_ids: Dict[int, array.array] = {}

    # Build dependency map within declare-fun expressions.
    for i, expr in enumerate(declare_fun_exprs):
        symbolic_vars = extract_symbolic_variables(expr)
        if 1 < len(symbolic_vars):
            logger.error("Extract multiple variables from one declare-fun expression.")
            logger.error(f"  declare-fun expression: {expr}")
            logger.error(f"  symbolic variables: {symbolic_vars}")
            exit(1)
        var = symbolic_vars[0]
        vid = _var_id(var)
        # lazily grow mapping array
        if vid >= len(declare_fun_id_by_varid):
            declare_fun_id_by_varid.extend([-1] * (vid - len(declare_fun_id_by_varid) + 1))
        declare_fun_id_by_varid[vid] = i

    # Build dependency maps within assert expressions.
    for i, expr in enumerate(assert_exprs):
        # Let-aware extraction avoids expensive textual let expansion.
        symbolic_vars = extract_symbolic_variables_let_aware(expr)
        # Dedup within the assert to avoid repeated edges/work
        seen_vids: Set[int] = set()
        local_varids: List[int] = []
        for v in symbolic_vars:
            vid = _var_id(v)
            if vid in seen_vids:
                continue
            seen_vids.add(vid)
            local_varids.append(vid)
            arr = var_assert_ids.get(vid)
            if arr is None:
                arr = array.array('I')
                var_assert_ids[vid] = arr
            arr.append(i)
        assert_varids[i] = local_varids

    # Selected IDs using bytearray + append-list (faster than set/bitset for this workload)
    selected_decl = bytearray(max_declare_id)
    selected_decl_ids: List[int] = []
    selected_assert = bytearray(max_assert_id)
    selected_assert_ids: List[int] = []

    # BFS over var-ids
    visited_varids: Set[int] = set()
    q: deque[int] = deque()

    for v in target_vars:
        vid = var_to_id.get(v)
        if vid is None:
            # Variable not seen yet - it might only appear in asserts, not declare-fun
            # This is valid (e.g., intermediate variables), so we intern it but skip BFS
            vid = _var_id(v)
            # Don't add to queue if it has no declare-fun (will be handled via assert dependencies)
            if vid < len(declare_fun_id_by_varid) and declare_fun_id_by_varid[vid] != -1:
                if vid not in visited_varids:
                    visited_varids.add(vid)
                    q.append(vid)
            continue
        if vid not in visited_varids:
            visited_varids.add(vid)
            q.append(vid)

    while q:
        vid = q.popleft()

        if vid >= len(declare_fun_id_by_varid) or declare_fun_id_by_varid[vid] == -1:
            logger.error(f"Variable id {vid} not found in declare-fun expressions map.")
            exit(1)

        decl_id = declare_fun_id_by_varid[vid]
        if not selected_decl[decl_id]:
            selected_decl[decl_id] = 1
            selected_decl_ids.append(decl_id)

        a_ids = var_assert_ids.get(vid)
        if a_ids is None:
            continue

        for assert_id in a_ids:
            if selected_assert[assert_id]:
                continue
            selected_assert[assert_id] = 1
            selected_assert_ids.append(assert_id)

            for related_vid in assert_varids[assert_id]:
                if related_vid in visited_varids:
                    continue
                visited_varids.add(related_vid)
                q.append(related_vid)

    # Preserve stable ordering (increasing index) like the old implementation
    selected_decl_ids.sort()
    selected_assert_ids.sort()

    # --- Lightweight consistency check (debug safety): every var in selected asserts must have a declare-fun ---
    # This keeps logic unchanged; it only raises if the encoding is internally inconsistent for slicing.
    missing_decl_vars: List[str] = []
    if selected_assert_ids:
        # Build reverse map once (id -> var string) for error reporting only
        id_to_var: List[Optional[str]] = [None] * len(var_to_id)
        for s, i in var_to_id.items():
            id_to_var[i] = s
        for assert_id in selected_assert_ids:
            for v_id in assert_varids[assert_id]:
                if v_id >= len(declare_fun_id_by_varid) or declare_fun_id_by_varid[v_id] == -1:
                    vname = id_to_var[v_id] if v_id < len(id_to_var) else None
                    if vname is not None:
                        missing_decl_vars.append(vname)
        if missing_decl_vars:
            sample = ", ".join(missing_decl_vars[:10])
            logger.error(
                "Slicing consistency check failed: some variables referenced in selected asserts "
                "have no declare-fun entry. Sample: " + sample
            )
            exit(1)

    sliced_exprs: List[str] = []
    sliced_exprs.extend([declare_fun_exprs[i] for i in selected_decl_ids])
    sliced_exprs.extend([assert_exprs[i] for i in selected_assert_ids])
    return sliced_exprs


##########################################################################################
### Device-level slicing functionality
##########################################################################################

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


def _read_model_igp(work_dir: str) -> bool:
    """Read 0_model_igp.txt: 1 -> model_igp True, 0 or missing -> False."""
    path = Path(work_dir) / "0_model_igp.txt"
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    return line == "1"
    except Exception:
        pass
    return False


class SmtSlicer:
    """
    Slices a global SMT-LIB 2 encoding file into smaller, per-router files
    based on a sophisticated set of priority-based rules and dependency resolution.
    """

    def __init__(self, routers: List[str], output_dir: str, logger=None, model_igp: bool = False):
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.routers = routers
        self.output_dir = output_dir
        self.model_igp = model_igp
        os.makedirs(self.output_dir, exist_ok=True)

        # --- Data Structures ---
        self.router_data: Dict[str, Set[str]] = defaultdict(set)
        self.deferred_asserts: Dict[str, Dict[str, Set[str]]] = {
            "EXPORT": defaultdict(set),
            "CONFIG": defaultdict(set),
            "FAILED": defaultdict(set),
            "SSA": defaultdict(set),
        }
        # New: A set for global assertions to be added to all files
        self.common_asserts: Set[str] = set()
        self.unhandled_asserts: List[str] = []
        self.all_declarations: Dict[str, str] = {}
        self.all_asserts: List[str] = []

        # --- Pre-compiled Regex Patterns ---
        self._compile_regex_patterns()

    def _compile_regex_patterns(self) -> None:
        """Initializes and pre-compiles all necessary regex patterns for efficiency."""
        self.logger.info("Step 1: Initializing priority templates...")
        high_priority_templates = [
            r"_{router}_CONNECTED_IMPORT", r"_{router}_STATIC_IMPORT", r"_{router}_BGP_IMPORT",
            r"_{router}_CONNECTED_BEST", r"_{router}_STATIC_BEST", r"_{router}_BGP_BEST",
            r"_{router}_OVERALL_BEST",
        ]
        low_priority_templates = [
            r"CONTROL-FORWARDING_{router}", r"DATA-FORWARDING_{router}",
        ]
        remove_templates = [r"reachable_{router}", r"reachable-id_{router}"]

        # Longest-first order so paris_1 / paris-1 match before paris (device names xxx, xxx-1, xxx_1).
        routers_sorted_longest_first = sorted(self.routers, key=lambda r: (-len(r), r))
        routers_alt = "(?:" + "|".join(map(re.escape, routers_sorted_longest_first)) + ")"

        self.patterns = {
            "high": {r: [re.compile(p.format(router=re.escape(r))) for p in high_priority_templates] for r in self.routers},
            "low": {r: [re.compile(p.format(router=re.escape(r))) for p in low_priority_templates] for r in self.routers},
            "remove": [re.compile(p.format(router=routers_alt)) for p in remove_templates]
        }

        # Fast-path combined patterns: find routers in one pass instead of scanning all routers per line.
        self._high_any = re.compile(
            rf"_(?P<router>{routers_alt})_(?:CONNECTED_IMPORT|STATIC_IMPORT|BGP_IMPORT|CONNECTED_BEST|STATIC_BEST|BGP_BEST|OVERALL_BEST)"
        )
        self._low_any = re.compile(
            rf"(?:CONTROL-FORWARDING|DATA-FORWARDING)_(?P<router>{routers_alt})"
        )
        # When model_igp: 0_SLICE-MAIN_{router}_CONNECTED_IMPORT/BEST etc. (7 kinds)
        self._high_any_slice = re.compile(
            rf"0_SLICE-MAIN_(?P<router>{routers_alt})_(?:CONNECTED_IMPORT|STATIC_IMPORT|BGP_IMPORT|CONNECTED_BEST|STATIC_BEST|BGP_BEST|OVERALL_BEST)"
        )
        # When model_igp: 0_SLICE-MAIN_CONTROL-FORWARDING_{router}, 0_SLICE-MAIN_DATA-FORWARDING_{router} (same role as low_any)
        self._low_any_slice = re.compile(
            rf"0_SLICE-MAIN_(?:CONTROL-FORWARDING|DATA-FORWARDING)_(?P<router>{routers_alt})"
        )

    def _parse_input_file(self, input_file: str) -> None:
        """Reads the input file and separates lines into declarations and assertions."""
        with open(input_file, "r") as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                if stripped_line.startswith('(declare-fun'):
                    variables = extract_symbolic_variables(stripped_line)
                    if variables:
                        self.all_declarations[variables[0]] = stripped_line
                elif stripped_line.startswith('(assert'):
                    self.all_asserts.append(stripped_line)

    def slice_from_expressions(self, sliced_exprs: List[str]) -> None:
        """Run device slicing directly from already-sliced expressions (no re-read/parse).
        
        This is a performance optimization: global slicing already produced the reduced set
        of declarations/assertions, so we reuse it in memory instead of re-reading
        `sliced_smt_encoding.smt2`.
        """
        self.all_declarations.clear()
        self.all_asserts.clear()
        self.router_data.clear()
        self.common_asserts.clear()
        self.unhandled_asserts.clear()
        for bucket in self.deferred_asserts.values():
            bucket.clear()
        
        for expr in sliced_exprs:
            stripped = expr.strip()
            if not stripped:
                continue
            if stripped.startswith("(declare-fun"):
                variables = extract_symbolic_variables(stripped)
                if variables:
                    self.all_declarations[variables[0]] = stripped
            elif stripped.startswith("(assert"):
                self.all_asserts.append(stripped)
        
        self._classify_assertions()
        self._resolve_dependencies()
        self._write_output_files()
        self._report_unhandled_asserts()
    
    def _classify_assertions(self) -> None:
        """
        Performs the main classification pass over all assertions.
        It removes, assigns, defers, finds common assertions, or flags as unhandled.
        """
        self.logger.info("Step 2: First pass - Remove, Assign, Defer, and find Common Asserts...")
        for line in self.all_asserts:
            # 1. Match and remove
            if self.model_igp:
                # In model_igp mode:
                # - Drop 0_SLICE-MAIN__reachable statements (global reachable markers).
                # - Keep 0_SLICE-{device}__reachable statements, even if they also contain legacy reachable_* markers.
                if "0_SLICE-MAIN__reachable" in line:
                    continue
                if "0_SLICE-" in line and "__reachable" in line:
                    # Keep and let _try_assign() handle broadcasting (3.2 logic).
                    pass
                else:
                    if any(regex.search(line) for regex in self.patterns["remove"]):
                        continue
            else:
                # Default behavior (non-model_igp): filter reachable_* and reachable-id_* statements.
                if any(regex.search(line) for regex in self.patterns["remove"]):
                    continue

            # 2. Match and assign based on priority
            if self._try_assign(line):
                continue

            # 3. If unassigned, try to defer for dependency resolution
            if self._try_defer(line):
                continue
            
            # 4. New: If still unassigned, check if it's a common/global assertion
            if self._try_add_to_common(line):
                continue

            # 5. If it fails all checks, it's unhandled.
            self.unhandled_asserts.append(line)
        
        self.logger.info(f"  -> Found {len(self.common_asserts)} common assertion(s) to be added to all files.")

    def _try_assign(self, line: str) -> bool:
        """
        Tries to assign an assertion to a router. Returns True if assigned, False otherwise.
        When model_igp: use 0_SLICE-MAIN_{router}_* (7 kinds) and 0_SLICE-{router} in variables.
        When not model_igp: use _{router}_CONNECTED_IMPORT/BEST etc. and CONTROL/DATA-FORWARDING_{router}.
        """
        is_special_case = False
        if "_OVERALL_BEST" in line and ("_BGP_EXPORT" in line or "_BGP_SINGLE-EXPORT" in line):
            variables = extract_symbolic_variables(line)
            best_router = get_router_from_var(next((v for v in variables if "_OVERALL_BEST" in v), None), self.routers)
            export_router = get_router_from_var(next((v for v in variables if "_BGP_EXPORT" in v or "_BGP_SINGLE-EXPORT" in v), None), self.routers)
            if best_router and export_router and best_router == export_router:
                is_special_case = True

        if is_special_case:
            return False

        if self.model_igp:
            # 0_SLICE-MAIN_{router}_CONNECTED_IMPORT/BEST etc. (7 kinds)
            assigned_routers = {m.group("router") for m in self._high_any_slice.finditer(line)}
            # 0_SLICE-{router}* variables:
            #
            # NOTE:
            # - Some asserts mention 0_SLICE-{device}__reachable_* together with concrete per-router
            #   0_SLICE-MAIN_{router}_* symbols (e.g., *_BGP_EXPORT_* and *_BGP_IMPORT_*).
            # - In such cases, broadcasting the assert to ALL routers is too aggressive: it causes
            #   router-local BGP logic to leak into unrelated routers' slices.
            # - Therefore, we only broadcast on 0_SLICE-* reachability markers when 3.1 could not
            #   identify any owning router (assigned_routers is empty).
            if not assigned_routers:
                assign_to_all_routers = False
                for var in extract_symbolic_variables(line):
                    var_content = var.strip("|")
                    for router in sorted(self.routers, key=lambda r: (-len(r), r)):
                        prefix = "0_SLICE-" + router
                        if var_content == prefix or var_content.startswith(prefix):
                            assign_to_all_routers = True
                            break
                    if assign_to_all_routers:
                        break

                if assign_to_all_routers:
                    for router in self.routers:
                        self.router_data[router].add(line)
                    return True
            # 0_SLICE-MAIN_CONTROL-FORWARDING_{router}, 0_SLICE-MAIN_DATA-FORWARDING_{router} (same as low_any for non-model_igp)
            if not assigned_routers:
                assigned_routers = {m.group("router") for m in self._low_any_slice.finditer(line)}
        else:
            assigned_routers = {m.group("router") for m in self._high_any.finditer(line)}
            if not assigned_routers:
                assigned_routers = {m.group("router") for m in self._low_any.finditer(line)}

        if assigned_routers:
            for router in assigned_routers:
                self.router_data[router].add(line)
            return True

        return False

    def _try_defer(self, line: str) -> bool:
        """
        Collects an assertion into a deferred bucket. Returns True if deferred, False otherwise.
        """
        variables = extract_symbolic_variables(line)
        export_vars = [v for v in variables if "_BGP_EXPORT" in v or "_BGP_SINGLE-EXPORT" in v]
        config_vars = [v for v in variables if "Config_" in v]
        failed_vars = [v for v in variables if "FAILED-EDGE_" in v or "FAILED-NODE_" in v]

        if export_vars:
            key_var = next((v for v in export_vars if v.endswith('__permitted|')), export_vars[0])
            self.deferred_asserts["EXPORT"][key_var].add(line)
            return True
        elif config_vars:
            self.deferred_asserts["CONFIG"][config_vars[0]].add(line)
            return True
        elif failed_vars:
            self.deferred_asserts["FAILED"][failed_vars[0]].add(line)
            return True

        ssa_match = _SSA_DEF_ASSERT_RE.match(line)
        if ssa_match:
            self.deferred_asserts["SSA"][ssa_match.group(1)].add(line)
            return True

        return False
    
    def _try_add_to_common(self, line: str) -> bool:
        """
        New: Checks if an assertion is a 'common' one (e.g., related to dst-ip)
        and adds it to the common set. Returns True if added, False otherwise.
        """
        # NOTE:
        # We intentionally do an exact variable-token match instead of substring matching:
        # - Substring matching can accidentally classify unrelated asserts as "common".
        # - Exact matching keeps behavior stable across encodings and naming variations.
        target_vars = (
            {"|0_SLICE-MAIN_dst-ip|", "|0_SLICE-MAIN_src-ip|"}
            if self.model_igp
            else {"|0_dst-ip|", "|0_src-ip|"}
        )
        vars_in_line = set(extract_symbolic_variables_let_aware(line))
        if vars_in_line.intersection(target_vars):
            self.common_asserts.add(line)
            return True
        return False

    def _ssa_vars_in_line(self, line: str, exclude: Optional[str] = None) -> Set[str]:
        """Return SSA_* variable names mentioned in a line."""
        return {v for v in _SSA_VAR_RE.findall(line) if v != exclude}

    def _resolve_ssa_orphans_for_router(
        self,
        router: str,
        ssa_to_routers: Dict[str, Set[str]],
        _var_cache: Dict[str, Set[str]],
    ) -> bool:
        """
        Assign SSA definition asserts that are only reachable via other SSA vars.
        Example: (assert (= SSA_COMMUNITIES566 ... SSA_COMMUNITIES565 ...)) should follow
        SSA_COMMUNITIES565 into the same router slice(s).
        """
        added = False
        for ssa_var, lines in self.deferred_asserts["SSA"].items():
            if lines.issubset(self.router_data[router]):
                continue
            for line in lines:
                if line in self.router_data[router]:
                    continue
                deps = self._ssa_vars_in_line(line, exclude=ssa_var)
                if not deps:
                    continue
                target_routers: Set[str] = set()
                for dep in deps:
                    target_routers.update(ssa_to_routers.get(dep, set()))
                if router in target_routers:
                    self.router_data[router].add(line)
                    added = True
        return added

    def _resolve_dependencies(self) -> None:
        """
        Iteratively resolves dependencies by adding deferred assertions to routers
        that reference their variables. Continues until no new assertions are added.
        Optimized: cache variable extraction results to avoid repeated tokenization.
        """
        _t0 = time.time()
        self.logger.info("Step 3: Resolving dependencies...")
        
        # Cache: line -> set of variables (avoid repeated tokenization)
        _var_cache: Dict[str, Set[str]] = {}
        
        def _get_vars_cached(line: str) -> Set[str]:
            """Get variables from a line, using cache to avoid repeated tokenization."""
            cached = _var_cache.get(line)
            if cached is not None:
                return cached
            vars_set = set(extract_symbolic_variables_let_aware(line))
            _var_cache[line] = vars_set
            return vars_set

        def _build_ssa_to_routers() -> Dict[str, Set[str]]:
            ssa_to_routers: Dict[str, Set[str]] = defaultdict(set)
            for router in self.routers:
                for line in self.router_data[router]:
                    for var in _get_vars_cached(line):
                        if var.startswith("SSA_"):
                            ssa_to_routers[var].add(router)
            return ssa_to_routers
        
        for i in range(2): # Loop twice for transitivity
            self.logger.info(f"  -> Dependency resolution pass {i+1}...")
            for router in self.routers:
                # Keep resolving until no new assertions are added
                while True:
                    # Find all variables currently referenced in this router's data (cached)
                    referenced_vars = set()
                    for line in self.router_data[router]:
                        referenced_vars.update(_get_vars_cached(line))
                    
                    # Track which deferred assertions we're about to add
                    initial_size = len(self.router_data[router])
                    
                    # Add deferred lines if their key variable is referenced
                    for var_key in list(referenced_vars):
                        for bucket in ["EXPORT", "CONFIG", "FAILED", "SSA"]:
                            if var_key in self.deferred_asserts[bucket]:
                                self.router_data[router].update(self.deferred_asserts[bucket][var_key])
                    
                    ssa_to_routers = _build_ssa_to_routers()
                    self._resolve_ssa_orphans_for_router(router, ssa_to_routers, _var_cache)
                    
                    # If no new assertions were added, we're done for this router
                    if len(self.router_data[router]) == initial_size:
                        break
        self.last_resolve_dependencies_seconds = time.time() - _t0

    def _write_output_files(self) -> None:
        """Assembles the final content for each router and writes it to a file."""
        self.logger.info("Step 4: Assembling and writing final files...")
        for router in self.routers:
            # New: Combine this router's specific data with the common assertions
            final_assert_set = self.router_data[router] | self.common_asserts
            final_asserts = sorted(list(final_assert_set))
            
            # Cache variable extraction (same line may appear multiple times)
            _var_cache_write: Dict[str, Set[str]] = {}
            final_vars = set()
            for line in final_asserts:
                cached = _var_cache_write.get(line)
                if cached is not None:
                    final_vars.update(cached)
                else:
                    vars_set = set(extract_symbolic_variables(line))
                    _var_cache_write[line] = vars_set
                    final_vars.update(vars_set)
            
            final_declarations = sorted([self.all_declarations[var] for var in final_vars if var in self.all_declarations])

            # Write to file
            filepath = os.path.join(self.output_dir, f"sliced_{router}_smt_encoding.smt2")
            with open(filepath, "w") as f:
                f.write("; ---- Declarations ----\n")
                for declare_line in final_declarations:
                    f.write(declare_line + "\n")
                f.write("\n; ---- Assertions ----\n")
                for assert_line in final_asserts:
                    f.write(assert_line + "\n")
            
            self.logger.info(f"  -> Wrote file for '{router}' with {len(final_declarations)} declarations and {len(final_asserts)} asserts.")

    def _report_unhandled_asserts(self) -> None:
        """Prints any assertions that were not classified by any rule."""
        self.logger.info("\nStep 5: Reporting unhandled assertions...")
        if not self.unhandled_asserts:
            self.logger.info("  -> All assertions were successfully classified.")
        else:
            self.logger.warning(f"  -> Found {len(self.unhandled_asserts)} unhandled assertion(s):")
            for line in self.unhandled_asserts:
                self.logger.warning(f"    - {line}")

    def slice(self, input_file: str) -> None:
        """Public method to run the entire slicing pipeline."""
        self._parse_input_file(input_file)
        self._classify_assertions()
        self._resolve_dependencies()
        self._write_output_files()
        self._report_unhandled_asserts()


##########################################################################################
### Input Validation
##########################################################################################

class InputValidator:
    """Validates required input files for SMT slicing"""
    
    def __init__(self, work_dir: str):
        self.work_dir = work_dir
    
    def _validate_input_files(self) -> None:
        """Validate that all required input files exist"""
        missing_files = []
        
        # Check required files for global slicing
        smt_encoding_file = os.path.join(self.work_dir, 'smt_encoding.smt2')
        target_variables_file = os.path.join(self.work_dir, '0_properties_variables.txt')
        
        if not os.path.exists(smt_encoding_file):
            missing_files.append('smt_encoding.smt2')
        if not os.path.exists(target_variables_file):
            missing_files.append('0_properties_variables.txt')
        
        if missing_files:
            print(f"Error: Missing required input files: {', '.join(missing_files)}")
            print(f"Work directory: {self.work_dir}")
            sys.exit(1)
    
    def _validate_device_slicing_files(self) -> None:
        """Validate that all required input files for device slicing exist"""
        missing_files = []
        
        hostname_file = os.path.join(self.work_dir, '0_hostnames.txt')
        output_dir = os.path.join(self.work_dir, '2_sliced_device_smt_encoding')
        sliced_smt_encoding_file = os.path.join(output_dir, 'sliced_smt_encoding.smt2')
        
        if not os.path.exists(hostname_file):
            missing_files.append('0_hostnames.txt')
        if not os.path.exists(sliced_smt_encoding_file):
            missing_files.append('2_sliced_device_smt_encoding/sliced_smt_encoding.smt2')
        
        if missing_files:
            logger = logging.getLogger(__name__)
            logger.error(f"Missing required input files for device slicing: {', '.join(missing_files)}")
            logger.error(f"Work directory: {self.work_dir}")
            sys.exit(1)

##########################################################################################
### pipeline
##########################################################################################

def perform_global_slicing(smt_encoding_path: str, target_variables_path: str,
                         sliced_smt_encoding_path: str):
    """Perform global SMT encoding slicing based on property variables.
    All `let` expressions in output are expanded (AST-based).
    """
    logger = logging.getLogger(__name__)
    # Read smt encoding.
    with open(smt_encoding_path, 'r', encoding='utf-8') as f:
        smt_encoding = f.read()
        smt_lines = smt_encoding.splitlines()

    # Extract declare-fun and assert SMT expressions.
    declare_fun_exprs = extract_declare_fun_expressions(smt_lines)
    assert_exprs = extract_assert_expressions(smt_lines)

    # Expand let expressions (AST-based)
    _t0 = time.time()
    assert_expanded_exprs = expand_let_expressions_ast_batch(assert_exprs)
    perform_global_slicing.last_let_expand_seconds = time.time() - _t0
    logger.info(f"Expanded let expressions using AST-based substitution (took {perform_global_slicing.last_let_expand_seconds:.2f}s)")

    # Expand SSA_RETURN* temporaries: inline (assert (= SSA_RETURNn body)) and drop declare-fun for SSA_RETURN*
    _t1 = time.time()
    assert_expanded_exprs, ssa_return_names = expand_ssa_return_in_asserts(assert_expanded_exprs)
    if ssa_return_names:
        logger.info(f"Expanded {len(ssa_return_names)} SSA_RETURN* temporary variable(s) (took {time.time() - _t1:.2f}s)")
        declare_fun_exprs = [
            e for e in declare_fun_exprs
            if not (extract_symbolic_variables(e) and extract_symbolic_variables(e)[0] in ssa_return_names)
        ]

    # Read target variables.
    with open(target_variables_path, 'r', encoding='utf-8') as f:
        target_vars = set(line.strip() for line in f)

    # Slice smt encoding.
    # Note: slice_smt_encoding uses let-aware extraction internally, so it works
    # correctly whether or not we expanded let in the output.
    sliced_exprs = slice_smt_encoding(declare_fun_exprs, assert_expanded_exprs, target_vars)

    # Write sliced smt encoding to output file.
    with open(sliced_smt_encoding_path, 'w', encoding='utf-8') as f:
        for sliced_expr in sliced_exprs:
            f.write(sliced_expr + '\n')

    logger.info(f"Sliced SMT encoding written to {sliced_smt_encoding_path}.")
    return sliced_exprs


def perform_device_slicing(work_dir: str, sliced_exprs: Optional[List[str]] = None) -> Dict[str, float]:
    """Perform device-level slicing after global slicing.
    
    If `sliced_exprs` is provided, we reuse the in-memory expressions instead of
    re-reading `2_sliced_device_smt_encoding/sliced_smt_encoding.smt2`.
    """
    logger = logging.getLogger(__name__)
    
    # Validate required input files
    validator = InputValidator(work_dir)
    validator._validate_device_slicing_files()
    
    hostname_file = os.path.join(work_dir, '0_hostnames.txt')
    output_dir = os.path.join(work_dir, '2_sliced_device_smt_encoding')
    sliced_smt_encoding_file = os.path.join(output_dir, 'sliced_smt_encoding.smt2')
    
    # Read router names
    with open(hostname_file, "r", encoding="utf-8") as f:
        routers = [line.strip() for line in f if line.strip()]

    model_igp = _read_model_igp(work_dir)
    if model_igp:
        logger.info("model_igp=1: using 0_SLICE-MAIN_{router}_* and 0_SLICE-{router} for assign.")
    logger.info(f"\nStarting device-level slicing for {len(routers)} routers...")
    slicer = SmtSlicer(routers=routers, output_dir=output_dir, logger=logger, model_igp=model_igp)
    if sliced_exprs is not None:
        slicer.slice_from_expressions(sliced_exprs)
    else:
        slicer.slice(input_file=sliced_smt_encoding_file)
    logger.info(f"Device-level slicing completed. Files saved in '{output_dir}' directory.")
    return {
        "resolve_dependencies_seconds": float(getattr(slicer, "last_resolve_dependencies_seconds", 0.0))
    }

##########################################################################################
### Main Execution
##########################################################################################

def main():
    """Main function for smt encoding slicing"""
    total_start = time.time()

    # Parse command line arguments (order: other, -v, -d)
    verbose = False
    delete_intermediate = False
    work_dir = None

    for arg in sys.argv[1:]:
        if arg == '-v':
            verbose = True
        elif arg == '-d':
            delete_intermediate = True
        elif not arg.startswith('-'):
            work_dir = arg

    if work_dir is None:
        print("Usage: python 2_smt_slicer.py [-v] [-d] <work_directory>")
        print("Options:")
        print("  -v              Verbose mode: Show detailed INFO logs")
        print("                  Without -v: Only show WARNING/ERROR logs and completion status")
        print("  -d              Delete intermediate output files before running")
        print("Example: python 2_smt_slicer.py smt_output_network_1")
        print("         python 2_smt_slicer.py -v smt_output_network_1")
        print("         python 2_smt_slicer.py -d smt_output_network_1")
        sys.exit(1)
    
    # Set logging level based on verbose flag
    if not verbose:
        # If not verbose, only show WARNING and above
        logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)
    
    if not os.path.exists(work_dir):
        logger.error(f"Work directory does not exist: {work_dir}")
        sys.exit(1)
    
    # Delete intermediate files if requested (-d: always show INFO for delete operations)
    if delete_intermediate:
        logging.getLogger().setLevel(logging.INFO)
        import shutil
        
        deleted_items = []
        
        work_path = Path(work_dir)
        
        # Delete 2_sliced_device_smt_encoding directory
        output_dir = work_path / "2_sliced_device_smt_encoding"
        if output_dir.exists():
            logger.info(f"Deleting intermediate output directory: {output_dir}")
            shutil.rmtree(output_dir)
            deleted_items.append(str(output_dir))
        
        # Delete individual files in output directory (if directory doesn't exist but files might)
        sliced_files = [
            "2_sliced_device_smt_encoding/sliced_smt_encoding.smt2"
        ]
        
        for file_path_str in sliced_files:
            file_path = work_path / file_path_str
            if file_path.exists():
                logger.info(f"Deleting intermediate output file: {file_path}")
                file_path.unlink()
                deleted_items.append(str(file_path))
        
        if deleted_items:
            logger.info(f"Deleted {len(deleted_items)} intermediate file(s)/directory(ies):")
            for item in deleted_items:
                logger.info(f"  - {item}")
            logger.info("Intermediate files deleted.")
        else:
            logger.info("No intermediate files found to delete.")
        sys.exit(0)
    
    # Validate required input files
    validator = InputValidator(work_dir)
    validator._validate_input_files()
    
    smt_encoding_file = os.path.join(work_dir, 'smt_encoding.smt2')
    target_variables_file = os.path.join(work_dir, '0_properties_variables.txt')
    
    # Create output directory for sliced files
    output_dir = os.path.join(work_dir, '2_sliced_device_smt_encoding')
    os.makedirs(output_dir, exist_ok=True)
    
    sliced_smt_encoding_file = os.path.join(output_dir, 'sliced_smt_encoding.smt2')

    # Step 1: Global slicing based on property variables (let expressions are always expanded)
    logger.info("Step 1: Global SMT encoding slicing...")
    sliced_exprs = perform_global_slicing(
        smt_encoding_file,
        target_variables_file,
        sliced_smt_encoding_file
    )
    
    # Step 2: Device-level slicing
    logger.info("\nStep 2: Device-level slicing...")
    device_timing = perform_device_slicing(work_dir, sliced_exprs=sliced_exprs)
 
    verbose_info(verbose, "\nAll slicing operations completed successfully!")
    if not verbose:
        print("✓ Completed")

if __name__ == "__main__":
    main()
