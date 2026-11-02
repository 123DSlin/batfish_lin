#!/usr/bin/env python3
"""Topology-driven, branch-independent per-device SMT slicing.

The full Minesweeper encoding is parsed and normalized once.  Each device
slice retains its local import/best/forwarding semantics plus every directly
connected peer's export toward the device.  Peer best-route records are
boundary declarations whose values are supplied later by branch seeds.

The structured symbolic RIB, branch guards, and at-most-k budget do not choose
slice assertions.  The same ``RouteBinder`` used by Stage 2 is run only as a
fail-closed audit proving that every k-feasible branch can be represented by
the independently constructed device slice. ``sliced_smt_encoding.smt2`` is a
deduplicated audit union, not an intermediate slicing input.
"""

import argparse
from dataclasses import dataclass
import re
import os
import sys
import logging
import time
import array
from typing import List, Set, Tuple, Optional, Dict
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from consistency.branch_loader import (
    NeighborTopology,
    SymbolicRib,
    SymbolicRouteFormatError,
)
from consistency.guard_encoder import GuardEncoder, GuardEncodingError
from consistency.route_binder import RouteBinder, SmtSymbolTable

from utils.util_smt import (
    expand_let_expressions_ast_batch,
    expand_ssa_return_in_asserts,
    extract_symbolic_variables_let_aware
)
from utils.util_log import verbose_info

# Module-level logger (used by helper classes/functions)
logger = logging.getLogger(__name__)


class SymbolicSliceError(ValueError):
    """Raised when a sound symbolic device slice cannot be constructed."""


@dataclass(frozen=True)
class SymbolicSliceRequirements:
    """Per-device binding contract and local equation roots."""

    required_by_router: Dict[str, Set[str]]
    local_roots_by_router: Dict[str, Set[str]]


@dataclass(frozen=True)
class DeviceSemanticScope:
    """Branch-independent semantic boundary for one device.

    ``peer_boundary_symbols`` are declarations only: a branch seed supplies
    their values. ``incoming_export_symbols`` and ``local_symbols`` are roots
    whose equations belong to this device slice.
    """

    router: str
    peers: Tuple[str, ...]
    peer_boundary_symbols: Set[str]
    incoming_export_symbols: Set[str]
    local_symbols: Set[str]

    @property
    def required_declarations(self) -> Set[str]:
        return (
            set(self.peer_boundary_symbols)
            | set(self.incoming_export_symbols)
            | set(self.local_symbols)
        )


def _declared_symbol_set(declarations: List[str]) -> Set[str]:
    symbols: Set[str] = set()
    for declaration in declarations:
        found = extract_symbolic_variables(declaration)
        if found:
            symbols.add(found[0])
    return symbols


def _is_local_semantic_symbol(symbol: str, router: str) -> bool:
    """Return whether ``symbol`` is part of router-local routing semantics."""

    route_marker = f"_{router}_"
    local_records = (
        "_CONNECTED_IMPORT_",
        "_STATIC_IMPORT_",
        "_BGP_IMPORT_",
        "_OSPF_IMPORT_",
        "_CONNECTED_BEST_",
        "_STATIC_BEST_",
        "_BGP_BEST_",
        "_OSPF_BEST_",
        "_OVERALL_BEST_",
    )
    return (
        route_marker in symbol and any(marker in symbol for marker in local_records)
    ) or f"CONTROL-FORWARDING_{router}_" in symbol or f"DATA-FORWARDING_{router}_" in symbol


def build_device_semantic_scopes(
    work_dir: Path | str, declarations: List[str]
) -> Dict[str, DeviceSemanticScope]:
    """Build one topology-driven, branch-independent scope per device.

    A device owns its import/best/forwarding equations and every directly
    connected peer's export *toward* that device.  Peer OVERALL_BEST and peer
    control-forwarding records are explicit boundary inputs whose values are
    supplied later by branch seeds.
    """

    directory = Path(work_dir)
    try:
        topology = NeighborTopology.from_file(directory / "0_ebgp_neighbors.txt")
    except (OSError, SymbolicRouteFormatError) as error:
        raise SymbolicSliceError(str(error)) from error
    hostnames = set(_read_required_lines(directory / "0_hostnames.txt", "device inventory"))
    routers = [router for router in topology.routers() if router in hostnames]
    if not routers:
        raise SymbolicSliceError("enabled BGP scope contains no session routers")

    declared = _declared_symbol_set(declarations)
    scopes: Dict[str, DeviceSemanticScope] = {}
    for router in routers:
        peers = topology.peers(router)
        local_symbols = {
            symbol for symbol in declared if _is_local_semantic_symbol(symbol, router)
        }
        if not local_symbols:
            raise SymbolicSliceError(
                f"full SMT encoding has no local routing symbols for {router}"
            )

        peer_boundary: Set[str] = set()
        incoming_exports: Set[str] = set()
        for peer in peers:
            local_links = topology.links(router, peer)
            reverse_links = topology.links(peer, router)
            if not reverse_links:
                raise SymbolicSliceError(
                    f"topology has {router}->{peer} but no reverse {peer}->{router} mapping"
                )

            peer_boundary.update(
                symbol
                for symbol in declared
                if f"_{peer}_OVERALL_BEST_" in symbol
                or f"CONTROL-FORWARDING_{peer}_" in symbol
                or f"DATA-FORWARDING_{peer}_" in symbol
                # SINGLE-EXPORT records are shared, directionless boundary
                # records in this Minesweeper encoding. Their one producer is
                # selected by the legacy export dependency rule; treating all
                # assertions that mention the shared record as roots would
                # pull other devices' best-route equations into this slice.
                or f"_{peer}_BGP_SINGLE-EXPORT_" in symbol
            )
            peer_interfaces = {link.local.interface for link in reverse_links}
            incoming_exports.update(
                symbol
                for symbol in declared
                if f"_{peer}_" in symbol
                and "_BGP_EXPORT_" in symbol
                and any(
                    f"_{peer}_BGP_EXPORT_{interface}_" in symbol
                    for interface in peer_interfaces
                )
            )

            if not any(f"_{peer}_OVERALL_BEST_" in symbol for symbol in peer_boundary):
                raise SymbolicSliceError(
                    f"device {router} peer {peer} has no OVERALL_BEST boundary record"
                )
            peer_has_single_export = any(
                f"_{peer}_BGP_SINGLE-EXPORT_" in symbol for symbol in peer_boundary
            )
            local_interfaces = {link.local.interface for link in local_links}
            peer_has_local_import = any(
                any(
                    f"_{router}_BGP_IMPORT_{interface}_" in symbol
                    for interface in local_interfaces
                )
                and (
                    symbol.endswith("_permitted|")
                    or symbol.endswith("_choice|")
                )
                for symbol in local_symbols
            )
            if not peer_has_local_import and not peer_has_single_export:
                raise SymbolicSliceError(
                    f"device {router} peer {peer} has no local BGP IMPORT permitted record"
                )
            peer_has_directional_export = bool(incoming_exports.intersection(
                {
                    symbol
                    for symbol in declared
                    if f"_{peer}_" in symbol
                    and any(
                        f"_{peer}_BGP_EXPORT_{interface}_" in symbol
                        for interface in peer_interfaces
                    )
                }
            ))
            if not peer_has_directional_export and not peer_has_single_export:
                raise SymbolicSliceError(
                    f"device {router} peer {peer} has no incoming EXPORT record"
                )

        scopes[router] = DeviceSemanticScope(
            router=router,
            peers=peers,
            peer_boundary_symbols=peer_boundary,
            incoming_export_symbols=incoming_exports,
            local_symbols=local_symbols,
        )
    return scopes

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

    def __init__(
        self,
        routers: List[str],
        output_dir: str,
        logger=None,
        model_igp: bool = False,
        semantic_scopes: Optional[Dict[str, DeviceSemanticScope]] = None,
        required_symbols: Optional[Dict[str, Set[str]]] = None,
        local_roots: Optional[Dict[str, Set[str]]] = None,
    ):
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.routers = routers
        self.output_dir = output_dir
        self.model_igp = model_igp
        self.semantic_scopes = dict(semantic_scopes or {})
        self.required_symbols: Dict[str, Set[str]] = {
            router: set((required_symbols or {}).get(router, set()))
            for router in routers
        }
        self.local_roots: Dict[str, Set[str]] = {
            router: set((local_roots or {}).get(router, set())) for router in routers
        }
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
        self.device_assertions: Dict[str, Set[str]] = {}
        self.device_declarations: Dict[str, Set[str]] = {}
        self._assertion_vars: Dict[str, Set[str]] = {}
        self._assertions_by_symbol: Dict[str, Set[str]] = defaultdict(set)

        # --- Pre-compiled Regex Patterns ---
        self._compile_regex_patterns()

        missing_scopes = sorted(set(routers) - self.semantic_scopes.keys())
        if missing_scopes:
            raise SymbolicSliceError(
                "missing branch-independent semantic scope for: "
                + ", ".join(missing_scopes)
            )

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
        """Seed every device with all local equations and incoming exports.

        This step is deliberately independent of symbolic branches and ``k``.
        Branch-derived symbols are audited later but never enlarge the slice.
        """

        for router, scope in self.semantic_scopes.items():
            # Local import/best/forwarding equations were assigned by the
            # owner classifier. Do not select every assertion that merely
            # *uses* a local OVERALL_BEST record: those include this router's
            # outgoing exports and belong to neighboring device slices.
            roots = set(scope.incoming_export_symbols)
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

        # Export/config/failure assertions are definitional.  Index an export
        # equation by its output record (prefer ``permitted``), rather than by
        # every input symbol it mentions; indexing every input makes one local
        # config field pull complete peer device encodings into the slice.
        if export_vars:
            key = next(
                (variable for variable in export_vars if variable.endswith("_permitted|")),
                export_vars[0],
            )
            self.deferred_asserts["EXPORT"][key].add(line)
            return True
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
                referenced_vars = set()
                for line in self.router_data[router]:
                    referenced_vars.update(_get_vars_cached(line))

                initial_size = len(self.router_data[router])
                for var_key in referenced_vars:
                    for bucket in ["EXPORT", "CONFIG", "FAILED", "SSA"]:
                        self.router_data[router].update(
                            self.deferred_asserts[bucket].get(var_key, set())
                        )

                ssa_to_routers = _build_ssa_to_routers()
                self._resolve_ssa_orphans_for_router(
                    router, ssa_to_routers, _var_cache
                )
                if len(self.router_data[router]) != initial_size:
                    changed = True
            if not changed:
                break
        self.last_resolve_dependencies_seconds = time.time() - _t0

    def _write_output_files(self) -> None:
        """Assembles the final content for each router and writes it to a file."""
        self.logger.info("Step 4: Assembling and writing final files...")
        for router in self.routers:
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
                    | set(scope.incoming_export_symbols)
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
            relevant_symbols.update(scope.incoming_export_symbols)
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
    
    def __init__(self, work_dir: str):
        self.work_dir = work_dir
    
    def _validate_input_files(self) -> None:
        """Validate that all required input files exist"""
        missing_files = []

        for filename in (
            "smt_encoding.smt2",
            "symbolic_route.json",
            "0_hostnames.txt",
            "0_dst_ips.txt",
            "0_ebgp_neighbors.txt",
            "0_interfaces.txt",
            "0_overall_history_enum.txt",
            "0_communities_index.txt",
        ):
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


def _read_required_lines(path: Path, description: str) -> List[str]:
    try:
        values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except OSError as error:
        raise SymbolicSliceError(f"cannot read {description} {path}: {error}") from error
    result = [value for value in values if value]
    if not result:
        raise SymbolicSliceError(f"{description} is empty: {path}")
    return result


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


def build_symbolic_device_requirements(
    work_dir: Path | str,
    declarations: List[str],
    *,
    k: int,
    vrf: str = "default",
) -> SymbolicSliceRequirements:
    """Return the exact full-encoding symbols required by each branch scope.

    Requirements are derived by running the same ``RouteBinder`` used by Stage
    2 against the *full* declaration table.  This avoids the circular behavior
    where a field removed by Stage 1 becomes invisible to the later binder.
    """

    if k < 0:
        raise SymbolicSliceError("k must be non-negative")
    directory = Path(work_dir)
    try:
        topology = NeighborTopology.from_file(directory / "0_ebgp_neighbors.txt")
    except (OSError, SymbolicRouteFormatError) as error:
        raise SymbolicSliceError(str(error)) from error
    hostnames = set(_read_required_lines(directory / "0_hostnames.txt", "device inventory"))
    routers = [router for router in topology.routers() if router in hostnames]
    if not routers:
        raise SymbolicSliceError("enabled BGP scope contains no session routers")
    destinations = _read_required_lines(
        directory / "0_dst_ips.txt", "property destination inventory"
    )
    try:
        rib = SymbolicRib.from_work_directory(directory)
        guard_encoder = GuardEncoder(rib.guard_variables)
        full_symbols = SmtSymbolTable.from_text("\n".join(declarations))
    except (OSError, ValueError, SymbolicRouteFormatError, GuardEncodingError) as error:
        raise SymbolicSliceError(str(error)) from error

    required_by_router: Dict[str, Set[str]] = {router: set() for router in routers}
    local_roots_by_router: Dict[str, Set[str]] = {router: set() for router in routers}
    for router in routers:
        branch_count = 0
        for destination in destinations:
            try:
                contexts = rib.forwarding_branch_contexts(
                    router=router,
                    vrf=vrf,
                    destination=destination,
                    plane="MAIN",
                    k=k,
                    guard_encoder=guard_encoder,
                )
            except (ValueError, SymbolicRouteFormatError, GuardEncodingError) as error:
                raise SymbolicSliceError(
                    f"cannot build symbolic branch scope for {router}/{destination}: {error}"
                ) from error
            if not contexts:
                raise SymbolicSliceError(
                    f"no k-feasible MAIN branch for {router}/{destination}"
                )
            branch_count += len(contexts)

            for context in contexts:
                binding = RouteBinder(rib, guard_encoder, full_symbols).bind(context)
                if binding.errors:
                    details = "; ".join(
                        f"{item.code}: {item.message}" for item in binding.errors
                    )
                    raise SymbolicSliceError(
                        f"cannot derive slice requirements for "
                        f"{context.current_entry.candidate_id}: {details}"
                    )
                binding_symbols = _binding_symbols(
                    [constraint.expression for constraint in binding.constraints],
                    full_symbols,
                )
                required_by_router[router].update(binding_symbols)
                local_prefixes = (
                    f"|0_{router}_",
                    f"|0_CONTROL-FORWARDING_{router}_",
                    f"|0_DATA-FORWARDING_{router}_",
                )
                local_roots_by_router[router].update(
                    symbol
                    for symbol in binding_symbols
                    if symbol.startswith(local_prefixes)
                )

        if branch_count == 0 or not required_by_router[router]:
            raise SymbolicSliceError(
                f"symbolic scope produced no slice requirements for {router}"
            )
    return SymbolicSliceRequirements(
        required_by_router=required_by_router,
        local_roots_by_router=local_roots_by_router,
    )

def perform_device_slicing(
    work_dir: str,
    normalized_exprs: List[str],
    semantic_scopes: Dict[str, DeviceSemanticScope],
    requirements: SymbolicSliceRequirements,
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
        InputValidator(str(work_dir))._validate_input_files()
        declarations, assertions = load_normalized_encoding(
            work_dir / "smt_encoding.smt2"
        )
        semantic_scopes = build_device_semantic_scopes(work_dir, declarations)
        requirements = build_symbolic_device_requirements(
            work_dir,
            declarations,
            k=args.k,
            vrf=args.vrf,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        timing = perform_device_slicing(
            str(work_dir),
            [*declarations, *assertions],
            semantic_scopes,
            requirements,
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
