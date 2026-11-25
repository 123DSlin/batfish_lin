#!/usr/bin/env python3
"""Protocol-adapted, branch-independent per-device SMT slicing.

The shared engine normalizes the full Minesweeper encoding, resolves shared
dependencies, audits declarations and writes device files. Protocol adapters
supply boundaries, assertion ownership and protocol equation dependencies.
The default BGP adapter preserves local import/best/forwarding equations and
direct peers' exports. Peer best records are inputs bound by later seeds.

Symbolic branches and k determine a structural binding audit, not which
assertions the BGP adapter selects. This audit checks representation, not a
general semantic equivalence theorem. ``sliced_smt_encoding.smt2`` is the
output audit union, never an intermediate slicing input.
"""

import argparse
import re
import os
import sys
import logging
import time
import array
from typing import List, Set, Tuple, Optional, Dict
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from slicing import (
    DeviceSemanticScope, SymbolicSliceRequirements, SymbolicSliceError,
    ProtocolSliceAdapter, get_protocol_adapter,
)
from slicing.symbols import (
    _declared_symbol_set, _read_required_lines, _binding_symbols,
    _tokenize_smt2_expression, extract_symbolic_variables, get_router_from_var,
)
from slicing.bgp import _is_local_semantic_symbol  # compatibility helper

from utils.util_smt import (
    expand_let_expressions_ast_batch,
    expand_ssa_return_in_asserts,
    extract_symbolic_variables_let_aware
)
from utils.util_log import verbose_info

# Module-level logger (used by helper classes/functions)
logger = logging.getLogger(__name__)


def build_device_semantic_scopes(work_dir, declarations, *, protocol="bgp"):
    """Compatibility entry point; semantics belong to the selected adapter."""
    return get_protocol_adapter(protocol).build_scopes(work_dir, declarations)


##########################################################################################
### SMT2 variable regex and constant regex
##########################################################################################

# smt2 variable regex (supports quoted identifiers (|...|) and normal indentifiers)
var_regex = r'(\|[^|]*?(?:\\\|[^|]*?)*\||[^\s()]+)'
var_pattern = re.compile(var_regex)

# SSA temporary definitions: (assert (= SSA_COMMUNITIESn body)), etc.
_SSA_DEF_ASSERT_RE = re.compile(r'^\(assert \(= (SSA_[A-Z]+\d+) ')
_SSA_VAR_RE = re.compile(r'\b(SSA_[A-Z]+\d+)\b')
_NON_ROUTING_PACKET_SYMBOLS = {
    "|0_dst-port|",
    "|0_src-port|",
    "|0_icmp-type|",
    "|0_icmp-code|",
    "|0_ip-protocol|",
}

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
    Shared device-slicing engine with protocol-owned classification rules.
    Dependency closure, structural audits and file output are common mechanisms.
    """

    def __init__(
        self,
        routers: List[str],
        output_dir: str,
        logger=None,
        model_igp: bool = False,
        semantic_scopes: Optional[Dict[str, DeviceSemanticScope]] = None,
        required_symbols: Optional[Dict[str, Set[str]]] = None,
        local_roots: Optional[Dict[str, Set[str]]] = None,
        protocol_adapter: Optional[ProtocolSliceAdapter] = None,
    ):
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.routers = routers
        self.output_dir = output_dir
        self.device_timing = defaultdict(float)
        self.model_igp = model_igp
        self.protocol_adapter = protocol_adapter or get_protocol_adapter("bgp")
        self.protocol_adapter.ensure_supported()
        self.semantic_scopes = dict(semantic_scopes or {})
        self.required_symbols: Dict[str, Set[str]] = {
            router: set((required_symbols or {}).get(router, set()))
            for router in routers
        }
        self.local_roots: Dict[str, Set[str]] = {
            router: set((local_roots or {}).get(router, set())) for router in routers
        }
        os.makedirs(self.output_dir, exist_ok=True)

        incompatible = [r for r, scope in self.semantic_scopes.items()
                        if scope.protocol != self.protocol_adapter.name]
        if incompatible:
            raise SymbolicSliceError("semantic scope/adapter mismatch: " + ", ".join(incompatible))

        # --- Data Structures ---
        self.router_data: Dict[str, Set[str]] = defaultdict(set)
        self.deferred_asserts: Dict[str, Dict[str, Set[str]]] = {
            "PROTOCOL": defaultdict(set),
            "CONFIG": defaultdict(set),
            "FAILED": defaultdict(set),
            "SSA": defaultdict(set),
        }
        # New: A set for global assertions to be added to all files
        self.common_asserts: Set[str] = set()
        self.unhandled_asserts: List[str] = []
        self.all_declarations: Dict[str, str] = {}
        self.all_asserts: List[str] = []
        self.device_assertions: Dict[str, Set[str]] = {}
        self.device_declarations: Dict[str, Set[str]] = {}
        self._assertion_vars: Dict[str, Set[str]] = {}
        self._assertions_by_symbol: Dict[str, Set[str]] = defaultdict(set)

        # Protocol-owned assertion classification; engine stays protocol-neutral.
        self._compile_regex_patterns()

        missing_scopes = sorted(set(routers) - self.semantic_scopes.keys())
        if missing_scopes:
            raise SymbolicSliceError(
                "missing branch-independent semantic scope for: "
                + ", ".join(missing_scopes)
            )

    def _compile_regex_patterns(self) -> None:
        """Create protocol rules once per engine instance."""
        self.protocol_rules = self.protocol_adapter.create_rules(self.routers, self.model_igp)


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
        """Run device slicing directly from normalized expressions (no re-read/parse).

        The full normalized encoding is supplied once. The audit union is an
        output, never an intermediate input to device slicing.
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

        self._build_assertion_index()

        self._classify_assertions()
        self._seed_device_semantic_roots()
        self._resolve_dependencies()
        self._report_unhandled_asserts()
        self._write_output_files()

    def _classify_assertions(self) -> None:
        """
        Performs the main classification pass over all assertions.
        It removes, assigns, defers, finds common assertions, or flags as unhandled.
        """
        self.logger.info("Step 2: First pass - Remove, Assign, Defer, and find Common Asserts...")
        for line in self.all_asserts:
            if self.protocol_rules.should_remove(line):
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

    def _vars_in_assertion(self, line: str) -> Set[str]:
        cached = self._assertion_vars.get(line)
        if cached is None:
            cached = set(extract_symbolic_variables_let_aware(line))
            self._assertion_vars[line] = cached
        return cached

    def _build_assertion_index(self) -> None:
        """Build the full symbol-to-assertion index once for all devices."""

        self._assertion_vars.clear()
        self._assertions_by_symbol.clear()
        for line in self.all_asserts:
            for symbol in self._vars_in_assertion(line):
                self._assertions_by_symbol[symbol].add(line)

    def _seed_device_semantic_roots(self) -> None:
        """Seed every device with all local equations and protocol equation roots.

        This step is deliberately independent of symbolic branches and ``k``.
        Branch-derived symbols are audited later but never enlarge the slice.
        """

        for router, scope in self.semantic_scopes.items():
            # Local import/best/forwarding equations were assigned by the
            # owner classifier. Do not select every assertion that merely
            # *uses* a local OVERALL_BEST record: those include this router's
            # outgoing exports and belong to neighboring device slices.
            roots = set(scope.protocol_equation_symbols)
            matched_assertions: Set[str] = set()
            for symbol in roots:
                matched_assertions.update(self._assertions_by_symbol.get(symbol, set()))
            self.router_data[router].update(matched_assertions)
            matched = len(matched_assertions)
            if matched == 0:
                raise SymbolicSliceError(
                    f"device {router} semantic roots match no SMT assertions"
                )

    def _try_assign(self, line: str) -> bool:
        owners = self.protocol_rules.assertion_owners(line)
        for router in owners:
            self.router_data[router].add(line)
        return bool(owners)


    def _try_defer(self, line: str) -> bool:
        """
        Collects an assertion into a deferred bucket. Returns True if deferred, False otherwise.
        """
        variables = extract_symbolic_variables(line)
        protocol_keys = self.protocol_rules.dependency_keys(variables)
        if protocol_keys:
            for key in protocol_keys:
                self.deferred_asserts["PROTOCOL"][key].add(line)
            return True
        config_vars = [v for v in variables if "Config_" in v]
        failed_vars = [v for v in variables if "FAILED-EDGE_" in v or "FAILED-NODE_" in v]

        if config_vars:
            # A relational assertion may constrain several configuration
            # fields. Index every field so closure does not depend on token
            # order in the SMT printer.
            for variable in config_vars:
                self.deferred_asserts["CONFIG"][variable].add(line)
            return True
        if failed_vars:
            for variable in failed_vars:
                self.deferred_asserts["FAILED"][variable].add(line)
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

        pass_number = 0
        while True:
            pass_number += 1
            self.logger.info(f"  -> Dependency resolution pass {pass_number}...")
            changed = False
            for router in self.routers:
                router_started = time.perf_counter()
                referenced_vars = set()
                for line in self.router_data[router]:
                    referenced_vars.update(_get_vars_cached(line))

                initial_size = len(self.router_data[router])
                for var_key in referenced_vars:
                    for bucket in ["PROTOCOL", "CONFIG", "FAILED", "SSA"]:
                        self.router_data[router].update(
                            self.deferred_asserts[bucket].get(var_key, set())
                        )

                ssa_to_routers = _build_ssa_to_routers()
                self._resolve_ssa_orphans_for_router(
                    router, ssa_to_routers, _var_cache
                )
                self.device_timing[router] += time.perf_counter() - router_started
                if len(self.router_data[router]) != initial_size:
                    changed = True
            if not changed:
                break
        self.last_resolve_dependencies_seconds = time.time() - _t0

    def _write_output_files(self) -> None:
        """Assembles the final content for each router and writes it to a file."""
        self.logger.info("Step 4: Assembling and writing final files...")
        for router in self.routers:
            router_started = time.perf_counter()
            scope = self.semantic_scopes[router]
            # New: Combine this router's specific data with the common assertions
            final_assert_set = self.router_data[router] | self.common_asserts
            final_asserts = sorted(list(final_assert_set))

            # Cache variable extraction (same line may appear multiple times)
            _var_cache_write: Dict[str, Set[str]] = {}
            # The slice is constructed exclusively from the branch-independent
            # device scope. Branch requirements below are validation contracts;
            # they must never enlarge this declaration set.
            final_vars = set(scope.required_declarations)
            assertion_vars: Set[str] = set()
            for line in final_asserts:
                cached = _var_cache_write.get(line)
                if cached is not None:
                    final_vars.update(cached)
                    assertion_vars.update(cached)
                else:
                    vars_set = set(extract_symbolic_variables(line))
                    _var_cache_write[line] = vars_set
                    final_vars.update(vars_set)
                    assertion_vars.update(vars_set)

            unencoded_local_roots = sorted(
                self.local_roots[router] - assertion_vars
            )
            if unencoded_local_roots:
                sample = ", ".join(unencoded_local_roots[:10])
                raise SymbolicSliceError(
                    f"{router} device slice retains declarations but no equations "
                    f"for required local state: {sample}"
                )

            unencoded_semantic_roots = sorted(
                (
                    set(scope.local_symbols)
                    | set(scope.protocol_equation_symbols)
                )
                - assertion_vars
            )
            if unencoded_semantic_roots:
                sample = ", ".join(unencoded_semantic_roots[:10])
                raise SymbolicSliceError(
                    f"{router} device semantic roots have no retained equation "
                    f"or domain constraint: {sample}"
                )

            missing_from_input = sorted(
                self.required_symbols[router] - self.all_declarations.keys()
            )
            if missing_from_input:
                sample = ", ".join(missing_from_input[:10])
                raise SymbolicSliceError(
                    f"{router} branch requirements are absent from the full SMT "
                    f"encoding: {sample}"
                )

            final_declarations = sorted(
                self.all_declarations[var]
                for var in final_vars
                if var in self.all_declarations
            )
            declared = {
                extract_symbolic_variables(line)[0] for line in final_declarations
            }
            missing_from_slice = sorted(self.required_symbols[router] - declared)
            if missing_from_slice:
                sample = ", ".join(missing_from_slice[:10])
                raise SymbolicSliceError(
                    f"{router} branch audit requires symbols absent from the "
                    f"independently constructed device slice: {sample}"
                )

            missing_semantic_declarations = sorted(
                scope.required_declarations - declared
            )
            if missing_semantic_declarations:
                sample = ", ".join(missing_semantic_declarations[:10])
                raise SymbolicSliceError(
                    f"{router} device slice is missing semantic declarations: {sample}"
                )

            self.device_assertions[router] = set(final_asserts)
            self.device_declarations[router] = set(final_declarations)

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
            self.device_timing[router] += time.perf_counter() - router_started

    def write_audit_union(self, output_path: Path | str) -> None:
        """Write the deduplicated union of all validated device slices."""

        declarations = set().union(*self.device_declarations.values())
        assertions = set().union(*self.device_assertions.values())
        output_path = Path(output_path)
        with output_path.open("w", encoding="utf-8") as output:
            for expression in self.all_declarations.values():
                if expression in declarations:
                    output.write(expression + "\n")
            for expression in self.all_asserts:
                if expression in assertions:
                    output.write(expression + "\n")

    def _report_unhandled_asserts(self) -> None:
        """Prints any assertions that were not classified by any rule."""
        self.logger.info("\nStep 5: Reporting unhandled assertions...")
        unexpected: List[str] = []
        ignored_packet_bounds = 0
        relevant_symbols: Set[str] = set()
        boundary_symbols: Set[str] = set()
        for router in self.routers:
            relevant_symbols.update(self.local_roots[router])
            scope = self.semantic_scopes[router]
            relevant_symbols.update(scope.local_symbols)
            relevant_symbols.update(scope.protocol_equation_symbols)
            boundary_symbols.update(scope.peer_boundary_symbols)
            for expression in self.router_data[router]:
                relevant_symbols.update(
                    extract_symbolic_variables_let_aware(expression)
                )
        ignored_out_of_scope = 0
        for line in self.unhandled_asserts:
            symbols = set(extract_symbolic_variables_let_aware(line))
            has_property_router_symbol = any(
                any(
                    f"_{router}_" in symbol
                    or f"FORWARDING_{router}_" in symbol
                    for router in self.routers
                )
                for symbol in symbols
            )
            if symbols and symbols.issubset(_NON_ROUTING_PACKET_SYMBOLS):
                ignored_packet_bounds += 1
            elif symbols and not has_property_router_symbol:
                ignored_out_of_scope += 1
            elif symbols and symbols.issubset(boundary_symbols):
                ignored_out_of_scope += 1
            elif symbols and symbols.isdisjoint(relevant_symbols):
                ignored_out_of_scope += 1
            else:
                unexpected.append(line)

        if not unexpected:
            self.logger.info("  -> All assertions were successfully classified.")
            if ignored_packet_bounds:
                self.logger.info(
                    "  -> Ignored %d non-routing packet-domain bound(s).",
                    ignored_packet_bounds,
                )
            if ignored_out_of_scope:
                self.logger.info(
                    "  -> Ignored %d assertion(s) outside the enabled session scope.",
                    ignored_out_of_scope,
                )
        else:
            sample = "\n".join(f"  - {line}" for line in unexpected[:10])
            raise SymbolicSliceError(
                f"found {len(unexpected)} unhandled assertion(s) in the full "
                f"device encoding:\n{sample}"
            )

    def slice(self, input_file: str) -> None:
        """Public method to run the entire slicing pipeline."""
        self._parse_input_file(input_file)
        self._build_assertion_index()
        self._classify_assertions()
        self._seed_device_semantic_roots()
        self._resolve_dependencies()
        self._report_unhandled_asserts()
        self._write_output_files()


##########################################################################################
### Input Validation
##########################################################################################

class InputValidator:
    """Validates required input files for SMT slicing"""

    def __init__(self, work_dir: str, protocol_adapter: Optional[ProtocolSliceAdapter] = None):
        self.work_dir = work_dir
        self.protocol_adapter = protocol_adapter or get_protocol_adapter("bgp")
        self.protocol_adapter.ensure_supported()

    def _validate_input_files(self) -> None:
        """Validate that all required input files exist"""
        missing_files = []

        for filename in self.protocol_adapter.required_input_files():
            if not os.path.exists(os.path.join(self.work_dir, filename)):
                missing_files.append(filename)

        if missing_files:
            raise SymbolicSliceError(
                f"missing required input files in {self.work_dir}: "
                + ", ".join(missing_files)
            )

##########################################################################################
### pipeline
##########################################################################################


def load_normalized_encoding(
    smt_encoding_path: Path | str,
) -> Tuple[List[str], List[str]]:
    """Parse and normalize the full Minesweeper encoding exactly once."""

    path = Path(smt_encoding_path)
    try:
        smt_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise SymbolicSliceError(f"cannot read SMT encoding {path}: {error}") from error

    declarations = extract_declare_fun_expressions(smt_lines)
    assertions = extract_assert_expressions(smt_lines)
    started = time.time()
    assertions = expand_let_expressions_ast_batch(assertions)
    logger.info(
        "Expanded let expressions using AST-based substitution (took %.2fs)",
        time.time() - started,
    )
    assertions, ssa_return_names = expand_ssa_return_in_asserts(assertions)
    if ssa_return_names:
        declarations = [
            expression
            for expression in declarations
            if not (
                extract_symbolic_variables(expression)
                and extract_symbolic_variables(expression)[0] in ssa_return_names
            )
        ]
    if not declarations or not assertions:
        raise SymbolicSliceError(
            f"SMT encoding has no declarations or assertions after normalization: {path}"
        )
    return declarations, assertions


def build_symbolic_device_requirements(work_dir, declarations, *, k, vrf="default", protocol="bgp"):
    """Dispatch the binding audit without changing branch-independent slices."""
    return get_protocol_adapter(protocol).build_requirements(work_dir, declarations, k=k, vrf=vrf)


def perform_device_slicing(
    work_dir: str,
    normalized_exprs: List[str],
    semantic_scopes: Dict[str, DeviceSemanticScope],
    requirements: SymbolicSliceRequirements,
    *,
    protocol: str = "bgp",
) -> Dict[str, float]:
    """Slice every device directly from one normalized full-encoding index."""
    logger = logging.getLogger(__name__)

    hostname_file = os.path.join(work_dir, '0_hostnames.txt')
    output_dir = os.path.join(work_dir, '1_sliced_device_smt_encoding')
    sliced_smt_encoding_file = os.path.join(output_dir, 'sliced_smt_encoding.smt2')

    # Read router names
    routers = list(requirements.required_by_router)

    model_igp = _read_model_igp(work_dir)
    if model_igp:
        logger.info("model_igp=1: using 0_SLICE-MAIN_{router}_* and 0_SLICE-{router} for assign.")
    logger.info(f"\nStarting device-level slicing for {len(routers)} routers...")
    slicer = SmtSlicer(
        routers=routers,
        output_dir=output_dir,
        logger=logger,
        model_igp=model_igp,
        semantic_scopes=semantic_scopes,
        required_symbols=requirements.required_by_router,
        local_roots=requirements.local_roots_by_router,
        protocol_adapter=get_protocol_adapter(protocol),
    )
    slicer.slice_from_expressions(normalized_exprs)
    slicer.write_audit_union(sliced_smt_encoding_file)
    logger.info(f"Device-level slicing completed. Files saved in '{output_dir}' directory.")
    return {
        "resolve_dependencies_seconds": float(getattr(slicer, "last_resolve_dependencies_seconds", 0.0)),
        "device_count": float(len(routers)),
        "required_symbol_count": float(
            sum(
                len(symbols)
                for symbols in requirements.required_by_router.values()
            )
        ),
    }

##########################################################################################
### Main Execution
##########################################################################################

def _non_negative_integer(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build branch-aware per-device slices directly from the full "
            "Minesweeper encoding."
        )
    )
    parser.add_argument("work_directory", type=Path)
    parser.add_argument("--k", required=True, type=_non_negative_integer)
    parser.add_argument("--vrf", default="default")
    parser.add_argument("--slicing-protocol", default="bgp",
                        help="slice adapter (default: bgp; IS-IS reserved, not implemented)")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "-d",
        "--delete",
        action="store_true",
        help="delete Stage-1 output and exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    work_dir = args.work_directory.resolve()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    active_logger = logging.getLogger(__name__)

    if not work_dir.is_dir():
        print(f"SMT slicer failed: work directory does not exist: {work_dir}", file=sys.stderr)
        return 2

    output_dir = work_dir / "1_sliced_device_smt_encoding"
    if args.delete:
        import shutil

        if output_dir.exists():
            shutil.rmtree(output_dir)
            print(f"Deleted {output_dir}")
        else:
            print(f"No Stage-1 output found at {output_dir}")
        return 0

    try:
        # Resolve before touching outputs; unsupported adapters never fall back to BGP.
        get_protocol_adapter(args.slicing_protocol)
        InputValidator(str(work_dir), get_protocol_adapter(args.slicing_protocol))._validate_input_files()
        declarations, assertions = load_normalized_encoding(
            work_dir / "smt_encoding.smt2"
        )
        semantic_scopes = build_device_semantic_scopes(work_dir, declarations, protocol=args.slicing_protocol)
        requirements = build_symbolic_device_requirements(
            work_dir,
            declarations,
            k=args.k,
            vrf=args.vrf,
            protocol=args.slicing_protocol,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        timing = perform_device_slicing(
            str(work_dir),
            [*declarations, *assertions],
            semantic_scopes,
            requirements,
            protocol=args.slicing_protocol,
        )
    except (OSError, ValueError, SymbolicSliceError) as error:
        active_logger.error("%s", error)
        print(f"SMT slicer failed: {error}", file=sys.stderr)
        return 2

    verbose_info(args.verbose, "\nAll symbolic device slices completed successfully!")
    print(
        "✓ Symbolic device slicing PASS | "
        f"devices={int(timing['device_count'])} | "
        f"required-symbols={int(timing['required_symbol_count'])}"
    )
    print(f"Output: {output_dir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
