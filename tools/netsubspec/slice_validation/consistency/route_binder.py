"""Bind a guarded symbolic RIB to variables in a device SMT encoding."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import Mapping, Optional

from .branch_loader import (
    BranchContext,
    RouteEntry,
    SymbolicRib,
    SymbolicRouteFormatError,
)
from .guard_encoder import GuardEncoder


def _name_token(text: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]", "_", text)
    return token or "constraint"


@dataclass(frozen=True)
class NamedConstraint:
    """An SMT expression with a stable name for diagnostics/UNSAT cores."""

    name: str
    expression: str
    section: str
    source: str

    def render(self) -> str:
        return f"(assert (! {self.expression} :named {_name_token(self.name)}))"


@dataclass(frozen=True)
class BindingDiagnostic:
    level: str
    code: str
    message: str


@dataclass(frozen=True)
class BindingResult:
    constraints: tuple[NamedConstraint, ...]
    diagnostics: tuple[BindingDiagnostic, ...]

    @property
    def errors(self) -> tuple[BindingDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.level == "ERROR")

    @property
    def warnings(self) -> tuple[BindingDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.level == "WARNING")


class SmtSymbolTable:
    """Declared constant symbols and sorts extracted from an SMT-LIB document."""

    _DECLARE = re.compile(
        r"^\s*\(declare-fun\s+(?P<name>\|(?:\\.|[^|])*\||[^\s()]+)\s+"
        r"\(\)\s+(?P<sort>.+)\)\s*$"
    )

    def __init__(self, declarations: Mapping[str, str]) -> None:
        self.declarations = dict(declarations)

    @classmethod
    def from_text(cls, smt_text: str) -> "SmtSymbolTable":
        declarations: dict[str, str] = {}
        for line_number, line in enumerate(smt_text.splitlines(), 1):
            if "declare-fun" not in line:
                continue
            match = cls._DECLARE.match(line)
            if match is None:
                raise ValueError(f"unsupported declare-fun at line {line_number}: {line!r}")
            name = match.group("name")
            sort = match.group("sort").strip()
            previous = declarations.get(name)
            if previous is not None and previous != sort:
                raise ValueError(f"symbol {name} is declared with conflicting sorts")
            declarations[name] = sort
        return cls(declarations)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self.declarations

    def sort(self, symbol: str) -> Optional[str]:
        return self.declarations.get(symbol)

    def symbols_matching(self, pattern: re.Pattern[str]) -> tuple[str, ...]:
        return tuple(sorted(name for name in self.declarations if pattern.fullmatch(name)))

    def record_fields(self, router: str, record: str) -> tuple[str, ...]:
        prefix = f"|0_{router}_{record}_"
        return tuple(
            sorted(
                symbol[len(prefix) : -1]
                for symbol in self.declarations
                if symbol.startswith(prefix) and symbol.endswith("|")
            )
        )


class RouteBinder:
    """Construct consistency bindings for one branch seed.

    The current branch fixes the selected route attributes.  Control forwarding
    is not made exactly-one: each interface is equated to the disjunction of all
    complete per-device MAIN-RIB guards that select a route through that
    interface.  Overlapping guards therefore represent ECMP naturally.
    """

    def __init__(
        self,
        rib: SymbolicRib,
        guard_encoder: GuardEncoder,
        symbols: SmtSymbolTable,
    ) -> None:
        self.rib = rib
        self.guard_encoder = guard_encoder
        self.symbols = symbols
        self._constraints: list[NamedConstraint] = []
        self._diagnostics: list[BindingDiagnostic] = []

    def bind(self, context: BranchContext) -> BindingResult:
        self._constraints = []
        self._diagnostics = []
        entry = context.current_entry
        branch_name = entry.candidate_id.removeprefix("candidate-v1-")[:12]

        self._bind_current_best(entry, branch_name)
        self._bind_current_import(entry, branch_name)
        self._bind_selected_predecessor(context, branch_name)
        self._bind_remaining_peer_ribs(context, branch_name)
        self._bind_selected_peer_link(context, branch_name)
        self._bind_control_forwarding(context, branch_name)

        return BindingResult(tuple(self._constraints), tuple(self._diagnostics))

    @staticmethod
    def _record_symbol(router: str, record: str, field: str) -> str:
        return f"|0_{router}_{record}_{field}|"

    def _add_constraint(
        self, name: str, expression: str, section: str, source: str
    ) -> None:
        self._constraints.append(
            NamedConstraint(_name_token(name), expression, section, source)
        )

    def _error(self, code: str, message: str) -> None:
        self._diagnostics.append(BindingDiagnostic("ERROR", code, message))

    def _warning(self, code: str, message: str) -> None:
        self._diagnostics.append(BindingDiagnostic("WARNING", code, message))

    def _bind_current_best(self, entry: RouteEntry, branch_name: str) -> None:
        try:
            local_connected_interface = self.rib.local_connected_origin_interface(entry)
        except SymbolicRouteFormatError as error:
            self._error("INVALID_LOCAL_CONNECTED_ORIGIN", str(error))
            return
        if local_connected_interface is not None:
            self._bind_local_connected_best(
                entry, branch_name, local_connected_interface
            )

        record = "OVERALL_BEST_None"
        permitted = self._record_symbol(entry.router, record, "permitted")
        if permitted not in self.symbols:
            self._error(
                "MISSING_CURRENT_BEST",
                f"device slice does not declare {permitted} for {entry.candidate_id}",
            )
            return
        self._add_constraint(
            f"branch_{branch_name}_current_best_permitted",
            f"(= {permitted} true)",
            "Current selected route",
            "current selected symbolic route",
        )
        self._bind_record_attributes(
            router=entry.router,
            record=record,
            entry=entry,
            condition=None,
            name_prefix=f"branch_{branch_name}_current_best",
            section="Current selected route",
            source="current selected symbolic route attributes",
        )

    def _bind_local_connected_best(
        self, entry: RouteEntry, branch_name: str, interface: str
    ) -> None:
        """Bind the device's protocol-best record for a proven local origin."""

        record = "CONNECTED_BEST_None"
        permitted = self._record_symbol(entry.router, record, "permitted")
        prefix_length = self._record_symbol(entry.router, record, "prefixLength")
        if self.symbols.sort(permitted) != "Bool":
            self._error(
                "MISSING_LOCAL_CONNECTED_BEST",
                f"device slice does not declare Bool {permitted} for local origin "
                f"{entry.router}:{interface}",
            )
            return
        if self.symbols.sort(prefix_length) != "Int":
            self._error(
                "MISSING_LOCAL_CONNECTED_PREFIX",
                f"device slice does not declare Int {prefix_length} for local origin "
                f"{entry.router}:{interface}",
            )
            return
        try:
            expected_prefix_length = ipaddress.ip_network(
                entry.prefix, strict=False
            ).prefixlen
        except ValueError as error:
            self._error("INVALID_PREFIX", f"{entry.prefix!r}: {error}")
            return

        name_prefix = f"branch_{branch_name}_local_connected_best"
        source = f"proven local CONNECTED origin {entry.router}:{interface}"
        self._add_constraint(
            f"{name_prefix}_permitted",
            f"(= {permitted} true)",
            "Current selected route",
            source,
        )
        self._add_constraint(
            f"{name_prefix}_prefixLength",
            f"(= {prefix_length} {expected_prefix_length})",
            "Current selected route",
            source,
        )

    def _bind_current_import(self, entry: RouteEntry, branch_name: str) -> None:
        peer = entry.selected_peer
        if peer is None:
            return
        try:
            link = self.rib.topology.resolve_unique(entry.router, peer)
        except SymbolicRouteFormatError as error:
            self._error("PEER_INTERFACE_MAPPING", str(error))
            return
        record = self._find_import_record(entry.router, entry.protocol, link.local.interface)
        if record is None:
            self._error(
                "MISSING_IMPORT_RECORD",
                f"no {entry.protocol} IMPORT record for {entry.router} "
                f"interface {link.local.interface}",
            )
            return
        permitted = self._record_symbol(entry.router, record, "permitted")
        if permitted in self.symbols:
            self._add_constraint(
                f"branch_{branch_name}_selected_import_permitted",
                f"(= {permitted} true)",
                "Selected import route",
                "selected peer import",
            )
        self._bind_record_attributes(
            router=entry.router,
            record=record,
            entry=entry,
            condition=None,
            name_prefix=f"branch_{branch_name}_selected_import",
            section="Selected import route",
            source="selected peer import attributes",
        )

    def _find_import_record(
        self, router: str, protocol: str, interface: str
    ) -> Optional[str]:
        protocol_tokens = [protocol.upper().replace("-", "_")]
        if protocol.upper() in {"ISIS_L1", "ISIS-LEVEL-1"}:
            protocol_tokens.extend(["ISIS_L1", "ISIS_LEVEL_1"])
        if protocol.upper() in {"ISIS_L2", "ISIS-LEVEL-2"}:
            protocol_tokens.extend(["ISIS_L2", "ISIS_LEVEL_2"])
        for token in dict.fromkeys(protocol_tokens):
            record = f"{token}_IMPORT_{interface}"
            permitted = self._record_symbol(router, record, "permitted")
            choice = self._record_symbol(router, record, "choice")
            if permitted in self.symbols or choice in self.symbols:
                return record
        return None

    def _bind_selected_predecessor(
        self, context: BranchContext, branch_name: str
    ) -> None:
        entry = context.current_entry
        peer = entry.selected_peer
        if peer is None:
            return
        if not context.predecessor_entries:
            self._error(
                "MISSING_PREDECESSOR",
                f"selected route {entry.candidate_id} has no resolvable predecessor entry",
            )
            return

        predecessor_paths = {
            path
            for predecessor in context.predecessor_entries
            if predecessor.router == peer
            for path in predecessor.router_paths
        }
        candidates = tuple(
            candidate
            for candidate in context.peer_ribs.get(peer, ())
            if predecessor_paths.intersection(candidate.router_paths)
        )
        if not candidates:
            self._error(
                "MISSING_PREDECESSOR_MAIN_ROUTE",
                f"no MAIN route at selected peer {peer} matches predecessor paths "
                f"{sorted(predecessor_paths)} for {entry.candidate_id}",
            )
            return
        self._bind_peer_record(
            peer=peer,
            entries=candidates,
            branch_name=branch_name,
            name=f"selected_peer_{peer}_predecessor",
            section="Selected peer predecessor route",
            source=f"selected peer {peer} predecessor symbolic route",
        )

    def _bind_remaining_peer_ribs(
        self, context: BranchContext, branch_name: str
    ) -> None:
        selected = context.current_entry.selected_peer
        for peer, peer_entries in sorted(context.peer_ribs.items()):
            if peer == selected:
                continue
            self._bind_peer_record(
                peer=peer,
                entries=peer_entries,
                branch_name=branch_name,
                name=f"remaining_peer_{peer}",
                section="Remaining peer candidate routes",
                source=(
                    f"all selected symbolic MAIN routes at peer {peer} covering "
                    "the property destination"
                ),
            )

    def _bind_peer_record(
        self,
        *,
        peer: str,
        entries: tuple[RouteEntry, ...],
        branch_name: str,
        name: str,
        section: str,
        source: str,
    ) -> None:
        record = "OVERALL_BEST_None"
        permitted = self._record_symbol(peer, record, "permitted")
        if permitted not in self.symbols:
            self._error(
                "PEER_BEST_NOT_IN_SLICE",
                f"device slice does not retain {peer}'s OVERALL_BEST record",
            )
            return
        active = self.guard_encoder.disjunction(
            entry.selection_guard for entry in entries
        )
        self._add_constraint(
            f"branch_{branch_name}_{name}_permitted",
            f"(= {permitted} {active})",
            section,
            source,
        )
        for index, peer_entry in enumerate(entries):
            condition = self.guard_encoder.encode(peer_entry.selection_guard)
            self._bind_record_attributes(
                router=peer,
                record=record,
                entry=peer_entry,
                condition=condition,
                name_prefix=f"branch_{branch_name}_{name}_candidate_{index}",
                section=section,
                source=source,
            )

    def _bind_selected_peer_link(
        self, context: BranchContext, branch_name: str
    ) -> None:
        entry = context.current_entry
        peer = entry.selected_peer
        if peer is None:
            return
        variables = tuple(
            variable
            for variable in self.rib.guard_variables
            if {variable.first_router, variable.second_router} == {entry.router, peer}
        )
        if len(variables) != 1:
            self._error(
                "SELECTED_LINK_GUARD",
                f"expected one link guard for {entry.router}<->{peer}, found "
                f"{len(variables)}",
            )
            return
        variable = variables[0]
        symbol = self.guard_encoder.symbol(variable.variable_id)
        link_up = symbol if variable.polarity == "UP" else f"(not {symbol})"
        self._add_constraint(
            f"branch_{branch_name}_selected_peer_link_up",
            link_up,
            "Selected-peer link state",
            f"direct link {entry.router}<->{peer} must be active",
        )

    def _bind_control_forwarding(
        self, context: BranchContext, branch_name: str
    ) -> None:
        current_router = context.current_entry.router
        pattern = re.compile(
            r"\|0_CONTROL-FORWARDING_(?P<router>[^_|]+)_"
            r"(?P<interface>[^|]+)\|"
        )
        cf_symbols = self.symbols.symbols_matching(pattern)
        declared_current: set[str] = set()
        guards_by_interface: dict[str, list[Mapping[str, object]]] = {}
        for entry in context.device_rib:
            interface = self._forwarding_interface(entry)
            if interface is not None:
                guards_by_interface.setdefault(interface, []).append(
                    entry.selection_guard
                )

        for symbol in cf_symbols:
            match = pattern.fullmatch(symbol)
            assert match is not None
            router = match.group("router")
            interface = match.group("interface")
            if router != current_router:
                continue
            declared_current.add(interface)
            expected = self.guard_encoder.disjunction(
                guards_by_interface.get(interface, ())
            )
            self._add_constraint(
                f"branch_{branch_name}_cf_{router}_{interface}",
                f"(= {symbol} {expected})",
                "Device control-forwarding state",
                "complete selected next-hop set from the device symbolic RIB",
            )

        missing = sorted(set(guards_by_interface) - declared_current)
        for interface in missing:
            self._error(
                "MISSING_CONTROL_FORWARDING",
                f"symbolic RIB selects {current_router}:{interface}, but the device "
                    "slice does not declare its CONTROL-FORWARDING variable",
            )

        # Preserve every final peer selection branch, including a branch whose
        # next hop is the current device.  Such a route is still the peer's real
        # OVERALL_BEST; it becomes non-advertisable back to the current device
        # through the peer CF state consumed by Minesweeper's import equations.
        for peer, peer_entries in sorted(context.peer_ribs.items()):
            try:
                link = self.rib.topology.resolve_unique(current_router, peer)
            except SymbolicRouteFormatError as error:
                self._error("PEER_INTERFACE_MAPPING", str(error))
                continue
            symbol = f"|0_CONTROL-FORWARDING_{peer}_{link.remote.interface}|"
            returning_guards: list[Mapping[str, object]] = []
            for peer_entry in peer_entries:
                interface = self._forwarding_interface(peer_entry)
                if interface == link.remote.interface:
                    returning_guards.append(peer_entry.selection_guard)
            expected = self.guard_encoder.disjunction(returning_guards)
            if symbol not in self.symbols:
                if returning_guards:
                    self._error(
                        "MISSING_PEER_CONTROL_FORWARDING",
                        f"symbolic RIB selects {peer}:{link.remote.interface} "
                        f"toward {current_router}, but the device slice does not "
                        "declare its CONTROL-FORWARDING variable",
                    )
                continue
            self._add_constraint(
                f"branch_{branch_name}_peer_{peer}_cf_toward_{current_router}",
                f"(= {symbol} {expected})",
                "Remaining peer candidate routes",
                f"complete peer selected next-hop set toward {current_router}",
            )

    def _forwarding_interface(self, entry: RouteEntry) -> Optional[str]:
        peer = entry.selected_peer
        if peer is not None:
            try:
                return self.rib.topology.resolve_unique(entry.router, peer).local.interface
            except SymbolicRouteFormatError as error:
                self._error("PEER_INTERFACE_MAPPING", str(error))
                return None

        # LOCAL and directly connected selected routes terminate at the device;
        # they do not identify an inter-device control-forwarding next hop.
        if entry.protocol in {"LOCAL", "CONNECTED"}:
            return None
        interface = entry.attributes.get("nextHopInterface")
        if isinstance(interface, str) and interface not in {
            "",
            "dynamic",
            "null_interface",
            "unset",
        }:
            return interface
        return None

    def _bind_record_attributes(
        self,
        *,
        router: str,
        record: str,
        entry: RouteEntry,
        condition: Optional[str],
        name_prefix: str,
        section: str,
        source: str,
    ) -> None:
        values = self._attribute_values(entry)
        history_symbol = self._record_symbol(router, record, "history")
        if history_symbol in self.symbols:
            history_map = self.rib.history_values.get(history_symbol)
            history_value = None if history_map is None else history_map.get(entry.protocol)
            if history_value is None:
                self._error(
                    "MISSING_HISTORY_VALUE",
                    f"no protocol-history value for {history_symbol} and "
                    f"protocol {entry.protocol}",
                )
            else:
                values["history"] = history_value

        community_symbol = self._record_symbol(router, record, "community")
        if community_symbol in self.symbols:
            communities = entry.attributes.get("communities", [])
            if not isinstance(communities, list) or not all(
                isinstance(item, str) for item in communities
            ):
                self._error(
                    "INVALID_COMMUNITIES",
                    f"candidate {entry.candidate_id} has non-string communities",
                )
            else:
                unknown = sorted(
                    community
                    for community in communities
                    if community not in self.rib.community_indices
                )
                if unknown:
                    self._error(
                        "UNMAPPED_COMMUNITIES",
                        f"candidate {entry.candidate_id} contains communities absent "
                        f"from 0_communities_index.txt: {unknown}",
                    )
                else:
                    values["community"] = sum(
                        1 << self.rib.community_indices[community]
                        for community in communities
                    )

        for field, value in values.items():
            symbol = self._record_symbol(router, record, field)
            sort = self.symbols.sort(symbol)
            if sort is None:
                continue
            literal = self._literal(value, sort, symbol)
            if literal is None:
                continue
            equality = f"(= {symbol} {literal})"
            expression = f"(=> {condition} {equality})" if condition else equality
            self._add_constraint(
                f"{name_prefix}_{field}",
                expression,
                section,
                f"{source}: {field}",
            )

        bound_fields = set(values)
        ignored_fields = {"choice", "permitted"}
        for field in self.symbols.record_fields(router, record):
            if field not in bound_fields and field not in ignored_fields:
                self._error(
                    "UNBOUND_ROUTE_ATTRIBUTE",
                    f"cannot bind declared route attribute "
                    f"{self._record_symbol(router, record, field)} from candidate "
                    f"{entry.candidate_id}",
                )

    def _attribute_values(self, entry: RouteEntry) -> dict[str, object]:
        attributes = entry.attributes
        try:
            prefix_length = ipaddress.ip_network(entry.prefix, strict=False).prefixlen
        except ValueError as error:
            self._error("INVALID_PREFIX", f"{entry.prefix!r}: {error}")
            prefix_length = None

        values: dict[str, object] = {
            "prefixLength": prefix_length,
            "adminDist": attributes.get("administrativeCost"),
            "localPref": attributes.get("localPreference", 100),
            "med": attributes.get("metric", 0) if entry.protocol == "BGP" else 0,
            "routerID": 0,
        }
        if entry.protocol == "BGP":
            as_path = attributes.get("asPath")
            if not isinstance(as_path, list):
                self._error(
                    "INVALID_AS_PATH",
                    f"candidate {entry.candidate_id} has no structured BGP AS path",
                )
            else:
                # Minesweeper's metric is the path cost incremented at every BGP
                # export; the structured AS-path segment count is its concrete
                # counterpart for the exported Batfish route.
                values["metric"] = len(as_path)
        else:
            values["metric"] = attributes.get("metric", 0)

        originator = attributes.get("originatorIp")
        if isinstance(originator, str):
            try:
                values["routerID"] = int(ipaddress.ip_address(originator))
            except ValueError:
                self._error(
                    "INVALID_ROUTER_ID",
                    f"candidate {entry.candidate_id} has invalid originatorIp {originator!r}",
                )
        return {key: value for key, value in values.items() if value is not None}

    def _literal(self, value: object, sort: str, symbol: str) -> Optional[str]:
        if sort == "Bool":
            if isinstance(value, bool):
                return "true" if value else "false"
            self._error("SORT_MISMATCH", f"{symbol} expects Bool, got {value!r}")
            return None
        if sort == "Int":
            if isinstance(value, bool) or not isinstance(value, int):
                self._error("SORT_MISMATCH", f"{symbol} expects Int, got {value!r}")
                return None
            return str(value)
        bit_vector = re.fullmatch(r"\(_\s+BitVec\s+(\d+)\)", sort)
        if bit_vector is not None and isinstance(value, int) and not isinstance(value, bool):
            width = int(bit_vector.group(1))
            if value < 0 or value >= 1 << width:
                self._error(
                    "BITVECTOR_RANGE", f"{value} does not fit {sort} for {symbol}"
                )
                return None
            return f"(_ bv{value} {width})"
        self._error("UNSUPPORTED_SORT", f"cannot bind {symbol} with sort {sort}")
        return None
