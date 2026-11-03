"""Existing eBGP slicing semantics, extracted without changing assertion selection."""
import re
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple
from consistency.branch_loader import NeighborTopology, SymbolicRib, SymbolicRouteFormatError
from consistency.guard_encoder import GuardEncoder, GuardEncodingError
from consistency.route_binder import RouteBinder, SmtSymbolTable
from .base import ProtocolSliceAdapter, ProtocolSliceRules
from .models import DeviceSemanticScope, SymbolicSliceRequirements, SymbolicSliceError
from .symbols import (_declared_symbol_set, _read_required_lines, _binding_symbols,
                      extract_symbolic_variables, get_router_from_var)

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


def _build_bgp_scopes(
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
            protocol_equation_symbols=incoming_exports,
            local_symbols=local_symbols,
        )
    return scopes


def _build_bgp_requirements(
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


class BgpSliceRules(ProtocolSliceRules):
    def __init__(self, routers: Sequence[str], model_igp: bool):
        self.routers = tuple(routers)
        self.model_igp = model_igp
        self._compile_regex_patterns()

    def _compile_regex_patterns(self) -> None:
        """Initializes and pre-compiles all necessary regex patterns for efficiency."""
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


    def should_remove(self, line: str) -> bool:
        if self.model_igp:
            # In model_igp mode:
            # - Drop 0_SLICE-MAIN__reachable statements (global reachable markers).
            # - Keep 0_SLICE-{device}__reachable statements, even if they also contain legacy reachable_* markers.
            if "0_SLICE-MAIN__reachable" in line:
                return True
            if "0_SLICE-" in line and "__reachable" in line:
                # Keep and let _try_assign() handle broadcasting (3.2 logic).
                pass
            else:
                if any(regex.search(line) for regex in self.patterns["remove"]):
                    return True
        else:
            # Default behavior (non-model_igp): filter reachable_* and reachable-id_* statements.
            if any(regex.search(line) for regex in self.patterns["remove"]):
                return True

        return False

    def assertion_owners(self, line: str) -> Set[str]:
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
            return set()

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
                    return set(self.routers)
            # 0_SLICE-MAIN_CONTROL-FORWARDING_{router}, 0_SLICE-MAIN_DATA-FORWARDING_{router} (same as low_any for non-model_igp)
            if not assigned_routers:
                assigned_routers = {m.group("router") for m in self._low_any_slice.finditer(line)}
        else:
            assigned_routers = {m.group("router") for m in self._high_any.finditer(line)}
            if not assigned_routers:
                assigned_routers = {m.group("router") for m in self._low_any.finditer(line)}

        return assigned_routers


    def dependency_keys(self, variables: Sequence[str]) -> Tuple[str, ...]:
        exports = [v for v in variables if "_BGP_EXPORT" in v or "_BGP_SINGLE-EXPORT" in v]
        if not exports:
            return ()
        return (next((v for v in exports if v.endswith("_permitted|")), exports[0]),)


class BgpSliceAdapter(ProtocolSliceAdapter):
    name = "bgp"

    def required_input_files(self):
        return (
            "smt_encoding.smt2", "symbolic_route.json", "0_hostnames.txt",
            "0_dst_ips.txt", "0_ebgp_neighbors.txt", "0_interfaces.txt",
            "0_overall_history_enum.txt", "0_communities_index.txt",
        )

    def build_scopes(self, work_dir, declarations):
        return _build_bgp_scopes(work_dir, declarations)

    def build_requirements(self, work_dir, declarations, *, k, vrf):
        return _build_bgp_requirements(work_dir, declarations, k=k, vrf=vrf)

    def create_rules(self, routers, model_igp):
        return BgpSliceRules(routers, model_igp)
