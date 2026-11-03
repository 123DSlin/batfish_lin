"""Load and index Batfish's structured symbolic routing information base.

The loader deliberately treats a branch as one entry in a complete per-device
symbolic RIB.  A :class:`BranchContext` therefore carries both the entry being
checked and the other entries needed to reconstruct the device/peer routing
state described by the paper's seed encoding.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import ipaddress
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import (
    Any,
    cast,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from .guard_encoder import GuardEncoder


class SymbolicRouteFormatError(ValueError):
    """Raised when a symbolic control-plane export is incomplete or malformed."""


JsonObject = Mapping[str, Any]


def _require_mapping(value: Any, location: str) -> JsonObject:
    if not isinstance(value, Mapping):
        raise SymbolicRouteFormatError(f"{location} must be a JSON object")
    return value


def _require_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise SymbolicRouteFormatError(f"{location} must be a non-empty string")
    return value


@dataclass(frozen=True)
class GuardVariable:
    """One Boolean variable used by symbolic-route guards."""

    variable_id: str
    kind: str
    first_router: str
    second_router: str
    polarity: str

    @classmethod
    def from_json(cls, raw: JsonObject, index: int) -> "GuardVariable":
        location = f"guardVariables[{index}]"
        link = _require_mapping(raw.get("link"), f"{location}.link")
        polarity = _require_string(raw.get("polarity"), f"{location}.polarity").upper()
        if polarity not in {"UP", "DOWN"}:
            raise SymbolicRouteFormatError(
                f"{location}.polarity must be UP or DOWN, got {polarity!r}"
            )
        return cls(
            variable_id=_require_string(raw.get("variableId"), f"{location}.variableId"),
            kind=_require_string(raw.get("kind"), f"{location}.kind"),
            first_router=_require_string(
                link.get("firstRouter"), f"{location}.link.firstRouter"
            ),
            second_router=_require_string(
                link.get("secondRouter"), f"{location}.link.secondRouter"
            ),
            polarity=polarity,
        )


@dataclass(frozen=True)
class NeighborEndpoint:
    router: str
    interface: str
    asn: Optional[int] = None


@dataclass(frozen=True)
class NeighborLink:
    local: NeighborEndpoint
    remote: NeighborEndpoint


class NeighborTopology:
    """Directed peer/interface mapping parsed from ``0_ebgp_neighbors.txt``."""

    _LINE = re.compile(
        r"^\s*(?P<lr>[^,\s]+),(?P<li>\S+)\s+"
        r"\((?P<la>\d+)\)\s*->\s*"
        r"(?P<rr>[^,\s]+),(?P<ri>\S+)\s+\((?P<ra>\d+)\)\s*$"
    )

    def __init__(self, links: Iterable[NeighborLink] = ()) -> None:
        directed: dict[tuple[str, str], list[NeighborLink]] = {}
        for link in links:
            directed.setdefault((link.local.router, link.remote.router), []).append(link)
        self._directed = {
            key: tuple(sorted(value, key=lambda item: item.local.interface))
            for key, value in directed.items()
        }

    @classmethod
    def from_file(cls, path: Path | str) -> "NeighborTopology":
        path = Path(path)
        links: list[NeighborLink] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            match = cls._LINE.match(line)
            if match is None:
                raise SymbolicRouteFormatError(
                    f"cannot parse {path}:{line_number}: {line!r}"
                )
            links.append(
                NeighborLink(
                    local=NeighborEndpoint(
                        match.group("lr"), match.group("li"), int(match.group("la"))
                    ),
                    remote=NeighborEndpoint(
                        match.group("rr"), match.group("ri"), int(match.group("ra"))
                    ),
                )
            )
        return cls(links)

    def links(self, router: str, peer: Optional[str] = None) -> tuple[NeighborLink, ...]:
        if peer is not None:
            return self._directed.get((router, peer), ())
        result: list[NeighborLink] = []
        for (local_router, _), links in self._directed.items():
            if local_router == router:
                result.extend(links)
        return tuple(sorted(result, key=lambda item: (item.remote.router, item.local.interface)))

    def peers(self, router: str) -> tuple[str, ...]:
        return tuple(sorted({link.remote.router for link in self.links(router)}))

    def routers(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    endpoint
                    for local, remote in self._directed
                    for endpoint in (local, remote)
                }
            )
        )

    def resolve_unique(self, router: str, peer: str) -> NeighborLink:
        links = self.links(router, peer)
        if not links:
            raise SymbolicRouteFormatError(
                f"no neighbor/interface mapping for {router!r} -> {peer!r}"
            )
        if len(links) != 1:
            interfaces = ", ".join(link.local.interface for link in links)
            raise SymbolicRouteFormatError(
                f"ambiguous neighbor/interface mapping for {router!r} -> {peer!r}: "
                f"{interfaces}"
            )
        return links[0]


@dataclass(frozen=True)
class RouteEntry:
    """A single guarded route in one protocol plane."""

    candidate_id: str
    plane: str
    router: str
    vrf: str
    prefix: str
    protocol: str
    route_type: str
    attributes: JsonObject
    selection_guard: JsonObject
    availability_guard: JsonObject
    contributions: tuple[JsonObject, ...]

    @classmethod
    def from_json(cls, raw: JsonObject, index: int) -> "RouteEntry":
        location = f"candidates[{index}]"
        route = _require_mapping(raw.get("route"), f"{location}.route")
        attributes = _require_mapping(
            route.get("attributes"), f"{location}.route.attributes"
        )
        selection_guard = _require_mapping(
            raw.get("selectionGuard"), f"{location}.selectionGuard"
        )
        availability_guard = _require_mapping(
            raw.get("availabilityGuard"), f"{location}.availabilityGuard"
        )
        contributions_raw = raw.get("contributions", [])
        if not isinstance(contributions_raw, list):
            raise SymbolicRouteFormatError(f"{location}.contributions must be an array")
        contributions = tuple(
            _require_mapping(value, f"{location}.contributions[{i}]")
            for i, value in enumerate(contributions_raw)
        )
        ast = selection_guard.get("ast")
        _require_mapping(ast, f"{location}.selectionGuard.ast")
        return cls(
            candidate_id=_require_string(raw.get("candidateId"), f"{location}.candidateId"),
            plane=_require_string(raw.get("plane"), f"{location}.plane").upper(),
            router=_require_string(raw.get("router"), f"{location}.router"),
            vrf=_require_string(raw.get("vrf"), f"{location}.vrf"),
            prefix=_require_string(raw.get("prefix"), f"{location}.prefix"),
            protocol=_require_string(raw.get("protocol"), f"{location}.protocol").upper(),
            route_type=_require_string(
                route.get("routeType"), f"{location}.route.routeType"
            ),
            attributes=MappingProxyType(dict(attributes)),
            selection_guard=MappingProxyType(dict(selection_guard)),
            availability_guard=MappingProxyType(dict(availability_guard)),
            contributions=tuple(MappingProxyType(dict(value)) for value in contributions),
        )

    @property
    def guard_ast(self) -> JsonObject:
        return _require_mapping(self.selection_guard.get("ast"), "selectionGuard.ast")

    @property
    def previous_routers(self) -> tuple[str, ...]:
        routers: set[str] = set()
        for contribution in self.contributions:
            provenance = contribution.get("provenance")
            if not isinstance(provenance, Mapping):
                continue
            previous = provenance.get("previousRouter")
            if isinstance(previous, str) and previous and previous != self.router:
                routers.add(previous)
        return tuple(sorted(routers))

    @property
    def selected_peer(self) -> Optional[str]:
        peers = self.previous_routers
        if not peers:
            return None
        if len(peers) > 1:
            raise SymbolicRouteFormatError(
                f"candidate {self.candidate_id} has multiple previous routers: {peers}"
            )
        return peers[0]

    @property
    def router_paths(self) -> tuple[tuple[str, ...], ...]:
        result: set[tuple[str, ...]] = set()
        for contribution in self.contributions:
            provenance = contribution.get("provenance")
            if not isinstance(provenance, Mapping):
                continue
            path = provenance.get("routerPath")
            if isinstance(path, list) and all(isinstance(item, str) for item in path):
                result.add(tuple(path))
        return tuple(sorted(result))

    @property
    def parent_message_ids(self) -> tuple[str, ...]:
        result: set[str] = set()
        for contribution in self.contributions:
            provenance = contribution.get("provenance")
            if isinstance(provenance, Mapping):
                parent = provenance.get("parentMessageId")
                if isinstance(parent, str) and parent:
                    result.add(parent)
            parents = contribution.get("parents")
            if isinstance(parents, list):
                for parent in parents:
                    if not isinstance(parent, Mapping):
                        continue
                    message_id = parent.get("messageId")
                    if isinstance(message_id, str) and message_id:
                        result.add(message_id)
        return tuple(sorted(result))

    @property
    def local_connected_origin_interface(self) -> Optional[str]:
        """Return the originating interface for a proven local CONNECTED route.

        This is deliberately stricter than checking only the protocol name.  The
        consistency adapter may relax a Minesweeper assertion only when the
        structured export proves that the route was created on this device and
        did not arrive from a routing neighbor.
        """

        if self.protocol != "CONNECTED" or self.selected_peer is not None:
            return None

        connected_class = "org.batfish.datamodel.ConnectedRoute"
        if self.route_type != connected_class:
            raise SymbolicRouteFormatError(
                f"candidate {self.candidate_id} is marked CONNECTED but has "
                f"routeType {self.route_type!r}"
            )
        if self.attributes.get("class") != connected_class:
            raise SymbolicRouteFormatError(
                f"candidate {self.candidate_id} is marked CONNECTED but has "
                f"route class {self.attributes.get('class')!r}"
            )
        if self.attributes.get("network") != self.prefix:
            raise SymbolicRouteFormatError(
                f"local CONNECTED candidate {self.candidate_id} has route network "
                f"{self.attributes.get('network')!r}, expected {self.prefix!r}"
            )
        interface = self.attributes.get("nextHopInterface")
        if not isinstance(interface, str) or interface in {
            "",
            "dynamic",
            "null_interface",
            "unset",
        }:
            raise SymbolicRouteFormatError(
                f"local CONNECTED candidate {self.candidate_id} has no concrete "
                "originating interface"
            )
        if not self.contributions:
            raise SymbolicRouteFormatError(
                f"local CONNECTED candidate {self.candidate_id} has no provenance"
            )
        for index, contribution in enumerate(self.contributions):
            identifier = contribution.get("id")
            if not isinstance(identifier, Mapping):
                raise SymbolicRouteFormatError(
                    f"candidate {self.candidate_id} contribution {index} has no "
                    "structured identifier"
                )
            if (
                identifier.get("sender") != self.router
                or identifier.get("receiver") != self.router
            ):
                raise SymbolicRouteFormatError(
                    f"candidate {self.candidate_id} contribution {index} is not "
                    f"local: sender={identifier.get('sender')!r}, "
                    f"receiver={identifier.get('receiver')!r}"
                )
            provenance = contribution.get("provenance")
            if not isinstance(provenance, Mapping):
                raise SymbolicRouteFormatError(
                    f"candidate {self.candidate_id} contribution {index} has no "
                    "structured provenance"
                )
            current = provenance.get("currentRouter")
            origin = provenance.get("originRouter")
            router_path = provenance.get("routerPath")
            if (
                current != self.router
                or origin != self.router
                or router_path != [self.router]
            ):
                raise SymbolicRouteFormatError(
                    f"candidate {self.candidate_id} is not a proven local origin: "
                    f"currentRouter={current!r}, originRouter={origin!r}, "
                    f"routerPath={router_path!r}"
                )
        return interface


@dataclass(frozen=True)
class BranchContext:
    """All symbolic-RIB information required to build one branch seed."""

    current_entry: RouteEntry
    device_rib: tuple[RouteEntry, ...]
    predecessor_entries: tuple[RouteEntry, ...]
    peer_ribs: Mapping[str, tuple[RouteEntry, ...]]


class SymbolicRib:
    """Validated, indexed representation of ``symbolic_route.json``."""

    _QUERY_CACHE_NAMES = ('entries', 'predecessors', 'context_ribs', 'forwarding',
                          'scope_prefixes', 'route_network', 'destination')

    SCHEMA_NAME = "batfish-minesweeper-symbolic-control-plane"
    SUPPORTED_SCHEMA_VERSIONS = {2}

    def __init__(
        self,
        guard_variables: Sequence[GuardVariable],
        entries: Sequence[RouteEntry],
        topology: Optional[NeighborTopology] = None,
        interfaces: Optional[Mapping[str, Iterable[str]]] = None,
        history_values: Optional[Mapping[str, Mapping[str, Optional[int]]]] = None,
        community_width: int = 0,
        community_indices: Optional[Mapping[str, int]] = None,
    ) -> None:
        guard_index = {item.variable_id: item for item in guard_variables}
        if len(guard_index) != len(guard_variables):
            raise SymbolicRouteFormatError("duplicate guard variableId")
        entry_index = {item.candidate_id: item for item in entries}
        if len(entry_index) != len(entries):
            raise SymbolicRouteFormatError("duplicate candidateId")
        self.guard_variables = tuple(guard_variables)
        self.guard_index = MappingProxyType(guard_index)
        self.entries_all = tuple(entries)
        self.entry_index = MappingProxyType(entry_index)
        self.topology = topology or NeighborTopology()
        self.interfaces = MappingProxyType(
            {
                router: frozenset(device_interfaces)
                for router, device_interfaces in (interfaces or {}).items()
            }
        )
        self.history_values = MappingProxyType(
            {
                symbol: MappingProxyType(dict(values))
                for symbol, values in (history_values or {}).items()
            }
        )
        self.community_width = community_width
        self.community_indices = MappingProxyType(dict(community_indices or {}))

        by_message: dict[str, list[RouteEntry]] = {}
        for entry in entries:
            self._validate_guard(entry.guard_ast, f"candidate {entry.candidate_id}")
            for contribution in entry.contributions:
                identifier = contribution.get("id")
                if not isinstance(identifier, Mapping):
                    continue
                message_id = identifier.get("messageId")
                if isinstance(message_id, str) and message_id:
                    by_message.setdefault(message_id, []).append(entry)
        self._message_index = {
            key: tuple(sorted(value, key=lambda item: item.candidate_id))
            for key, value in by_message.items()
        }

        # Stable posting lists preserve all entries, including multiple routes
        # for the same prefix. Loading validates guards exactly as before.
        self._ordered_entries = tuple(sorted(self.entries_all, key=lambda item: item.candidate_id))
        indexes = {field: {} for field in ('router', 'vrf', 'prefix', 'plane', 'protocol')}
        for entry in self._ordered_entries:
            for field, buckets in indexes.items():
                buckets.setdefault(getattr(entry, field), []).append(entry)
        self._entry_indexes = MappingProxyType({
            field: MappingProxyType({key: tuple(bucket) for key, bucket in buckets.items()})
            for field, buckets in indexes.items()})
        # Per-instance bounded caches avoid process-wide RIB retention and
        # unbounded growth as prefix/query counts increase.
        self._cached_entries = lru_cache(maxsize=2048)(self._query_entries)
        self._cached_predecessors = lru_cache(maxsize=2048)(self._query_predecessors)
        self._cached_context_ribs = lru_cache(maxsize=2048)(self._query_context_ribs)
        self._cached_forwarding = lru_cache(maxsize=2048)(self._query_forwarding)
        self._cached_scope_prefixes = lru_cache(maxsize=512)(self._query_scope_prefixes)
        self._cached_route_network = lru_cache(maxsize=4096)(
            lambda prefix: ipaddress.ip_network(prefix, strict=False))
        self._cached_destination = lru_cache(maxsize=1024)(self._destination_network)

    @classmethod
    def load(
        cls,
        json_path: Path | str,
        topology_path: Optional[Path | str] = None,
        interfaces_path: Optional[Path | str] = None,
        history_path: Optional[Path | str] = None,
        communities_path: Optional[Path | str] = None,
        protocols_path: Optional[Path | str] = None,
    ) -> "SymbolicRib":
        json_path = Path(json_path)
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SymbolicRouteFormatError(f"cannot load {json_path}: {error}") from error
        root = _require_mapping(raw, "root")
        if root.get("schemaName") != cls.SCHEMA_NAME:
            raise SymbolicRouteFormatError(
                f"unsupported schemaName: {root.get('schemaName')!r}"
            )
        if root.get("schemaVersion") not in cls.SUPPORTED_SCHEMA_VERSIONS:
            raise SymbolicRouteFormatError(
                f"unsupported schemaVersion: {root.get('schemaVersion')!r}"
            )
        guard_raw = root.get("guardVariables")
        candidates_raw = root.get("candidates")
        if not isinstance(guard_raw, list):
            raise SymbolicRouteFormatError("guardVariables must be an array")
        if not isinstance(candidates_raw, list):
            raise SymbolicRouteFormatError("candidates must be an array")
        guards = [
            GuardVariable.from_json(_require_mapping(item, f"guardVariables[{i}]"), i)
            for i, item in enumerate(guard_raw)
        ]
        entries = [
            RouteEntry.from_json(_require_mapping(item, f"candidates[{i}]"), i)
            for i, item in enumerate(candidates_raw)
        ]
        if protocols_path is not None:
            enabled_families = cls._load_protocol_families(protocols_path)
            entries = [
                entry
                for entry in entries
                if cls._protocol_is_enabled(entry.protocol, enabled_families)
            ]
        topology = NeighborTopology.from_file(topology_path) if topology_path else None
        interfaces = cls._load_interfaces(interfaces_path) if interfaces_path else None
        history_values = cls._load_history_values(history_path) if history_path else None
        community_width, community_indices = (
            cls._load_community_indices(communities_path)
            if communities_path
            else (0, {})
        )
        return cls(
            guards,
            entries,
            topology,
            interfaces,
            history_values,
            community_width,
            community_indices,
        )

    @classmethod
    def from_work_directory(cls, work_directory: Path | str) -> "SymbolicRib":
        work_directory = Path(work_directory)
        protocols_path = work_directory / "0_protocols.txt"
        return cls.load(
            work_directory / "symbolic_route.json",
            work_directory / "0_ebgp_neighbors.txt",
            work_directory / "0_interfaces.txt",
            work_directory / "0_overall_history_enum.txt",
            work_directory / "0_communities_index.txt",
            protocols_path if protocols_path.is_file() else None,
        )

    @staticmethod
    def _load_protocol_families(path: Path | str) -> frozenset[str]:
        path = Path(path)
        try:
            tokens = {
                token.strip().upper()
                for token in path.read_text(encoding="utf-8").split(",")
                if token.strip()
            }
        except OSError as error:
            raise SymbolicRouteFormatError(f"cannot load {path}: {error}") from error
        supported = {"BGP", "OSPF", "ISIS"}
        unknown = sorted(tokens - supported)
        if unknown:
            raise SymbolicRouteFormatError(
                f"unsupported protocol family in {path}: {', '.join(unknown)}"
            )
        if not tokens:
            raise SymbolicRouteFormatError(f"protocol selection is empty: {path}")
        return frozenset(tokens)

    @staticmethod
    def _protocol_is_enabled(protocol: str, enabled_families: frozenset[str]) -> bool:
        normalized = protocol.upper().replace("-", "_")
        if normalized in {"BGP", "IBGP"}:
            return "BGP" in enabled_families
        if normalized.startswith("OSPF"):
            return "OSPF" in enabled_families
        if normalized.startswith("ISIS"):
            return "ISIS" in enabled_families
        return True

    @staticmethod
    def _load_history_values(
        path: Path | str,
    ) -> Mapping[str, Mapping[str, Optional[int]]]:
        path = Path(path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise SymbolicRouteFormatError(f"cannot load {path}: {error}") from error

        header = re.compile(r"^(?P<symbol>\|[^|]+_history\|)\s+\(\d+\)\s*$")
        value_line = re.compile(
            r"^\s*(?P<protocol>[A-Za-z0-9_-]+)\s*:\s*(?P<value>null|\d+)\s*$",
            re.IGNORECASE,
        )
        result: dict[str, dict[str, Optional[int]]] = {}
        current: Optional[str] = None
        for line_number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            header_match = header.match(line)
            if header_match is not None:
                current = header_match.group("symbol")
                result.setdefault(current, {})
                continue
            value_match = value_line.match(line)
            if value_match is None or current is None:
                raise SymbolicRouteFormatError(
                    f"cannot parse {path}:{line_number}: {line!r}"
                )
            raw_value = value_match.group("value")
            result[current][value_match.group("protocol").upper()] = (
                None if raw_value.lower() == "null" else int(raw_value)
            )
        return result

    @staticmethod
    def _load_community_indices(path: Path | str) -> tuple[int, Mapping[str, int]]:
        path = Path(path)
        try:
            lines = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError as error:
            raise SymbolicRouteFormatError(f"cannot load {path}: {error}") from error
        if not lines:
            raise SymbolicRouteFormatError(f"community index is empty: {path}")
        try:
            width = int(lines[0])
        except ValueError as error:
            raise SymbolicRouteFormatError(
                f"cannot parse community width in {path}: {lines[0]!r}"
            ) from error
        if width < 0:
            raise SymbolicRouteFormatError(f"negative community width in {path}")
        indices: dict[str, int] = {}
        pattern = re.compile(r"^(?P<community>.+):\s*(?P<index>\d+)$")
        for line_number, line in enumerate(lines[1:], 2):
            match = pattern.match(line)
            if match is None:
                raise SymbolicRouteFormatError(
                    f"cannot parse {path}:{line_number}: {line!r}"
                )
            community = match.group("community").strip()
            index = int(match.group("index"))
            if index >= width:
                raise SymbolicRouteFormatError(
                    f"community index {index} exceeds width {width} in {path}"
                )
            if community in indices:
                raise SymbolicRouteFormatError(
                    f"duplicate community {community!r} in {path}"
                )
            indices[community] = index
        return width, indices

    @staticmethod
    def _load_interfaces(path: Path | str) -> Mapping[str, frozenset[str]]:
        path = Path(path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise SymbolicRouteFormatError(f"cannot load {path}: {error}") from error

        interfaces: dict[str, set[str]] = {}
        for line_number, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = [field.strip() for field in stripped.split(",")]
            if len(fields) != 2 or not all(fields):
                raise SymbolicRouteFormatError(
                    f"cannot parse {path}:{line_number}: {line!r}; expected "
                    "device,interface"
                )
            router, interface = fields
            interfaces.setdefault(router, set()).add(interface)
        if not interfaces:
            raise SymbolicRouteFormatError(f"interface inventory is empty: {path}")
        return {
            router: frozenset(device_interfaces)
            for router, device_interfaces in interfaces.items()
        }

    def local_connected_origin_interface(self, entry: RouteEntry) -> Optional[str]:
        """Validate a local CONNECTED origin against the device inventory."""

        interface = entry.local_connected_origin_interface
        if interface is None:
            return None
        device_interfaces = self.interfaces.get(entry.router)
        if device_interfaces is None:
            raise SymbolicRouteFormatError(
                f"interface inventory has no device {entry.router!r}"
            )
        if interface not in device_interfaces:
            raise SymbolicRouteFormatError(
                f"local CONNECTED candidate {entry.candidate_id} names unknown "
                f"interface {entry.router}:{interface}"
            )
        return interface

    def _validate_guard(self, ast: JsonObject, location: str) -> None:
        operator = ast.get("operator")
        if operator == "VARIABLE":
            variable_id = ast.get("variableId")
            if variable_id not in self.guard_index:
                raise SymbolicRouteFormatError(
                    f"{location} references unknown guard variable {variable_id!r}"
                )
        children = ast.get("children", [])
        if children is None:
            children = []
        if not isinstance(children, list):
            raise SymbolicRouteFormatError(f"{location} guard children must be an array")
        for index, child in enumerate(children):
            self._validate_guard(
                _require_mapping(child, f"{location}.children[{index}]"),
                f"{location}.children[{index}]",
            )

    def entries(
        self, *, router: Optional[str] = None, vrf: Optional[str] = None,
        prefix: Optional[str] = None, plane: Optional[str] = None,
        protocol: Optional[str] = None,
    ) -> tuple[RouteEntry, ...]:
        """Exact filters over the smallest immutable posting list; no route pruning."""
        return self._cached_entries(router, vrf, prefix,
                                    plane.upper() if plane is not None else None,
                                    protocol.upper() if protocol is not None else None)

    def _query_entries(self, router, vrf, prefix, plane, protocol):
        filters = dict(router=router, vrf=vrf, prefix=prefix, plane=plane, protocol=protocol)
        buckets = [self._entry_indexes[field].get(value, ())
                   for field, value in filters.items() if value is not None]
        candidates = min(buckets, key=len) if buckets else self._ordered_entries
        return tuple(entry for entry in candidates if all(
            value is None or getattr(entry, field) == value
            for field, value in filters.items()))


    def predecessor_entries(self, entry: RouteEntry) -> tuple[RouteEntry, ...]:
        # Include parent ids in the key: callers may pass a replaced RouteEntry
        # carrying the same candidate id but a different provenance snapshot.
        return self._cached_predecessors(entry.candidate_id, entry.parent_message_ids)

    def _query_predecessors(self, candidate_id, parent_message_ids):
        result: dict[str, RouteEntry] = {}
        for message_id in parent_message_ids:
            for owner in self._message_index.get(message_id, ()):
                if owner.candidate_id != candidate_id:
                    result[owner.candidate_id] = owner
        return tuple(sorted(result.values(), key=lambda item: item.candidate_id))


    def context(
        self, entry: RouteEntry, *, destination: Optional[str] = None
    ) -> BranchContext:
        """Reuse complete device/peer RIB context; only current entry varies.

        Contexts retain every covering MAIN branch, including shorter-prefix
        fallback routes and routes that forward back toward the current peer.
        No guard, route attributes or competitive route set is changed.
        """
        if entry.candidate_id not in self.entry_index:
            raise SymbolicRouteFormatError(
                f"candidate {entry.candidate_id!r} does not belong to this symbolic RIB")
        device_rib, candidate_ids, peer_ribs = self._cached_context_ribs(
            entry.router, entry.vrf, entry.plane,
            entry.prefix if destination is None else None,
            destination, self.topology.peers(entry.router))
        if destination is not None and entry.candidate_id not in candidate_ids:
            raise SymbolicRouteFormatError(
                f"candidate {entry.candidate_id} does not cover property destination {destination!r}")
        return BranchContext(current_entry=entry, device_rib=device_rib,
            predecessor_entries=self.predecessor_entries(entry), peer_ribs=peer_ribs)

    def _query_context_ribs(self, router, vrf, plane, prefix, destination, peers):
        def selected(device, selected_plane):
            if destination is None:
                return self.entries(router=device, vrf=vrf, prefix=prefix, plane=selected_plane)
            return self.forwarding_entries(router=device, vrf=vrf,
                                           destination=destination, plane=selected_plane)
        device_rib = selected(router, plane)
        peer_ribs = {}
        for peer in peers:
            peer_entries = selected(peer, 'MAIN')
            if peer_entries:
                peer_ribs[peer] = peer_entries
        return (device_rib, frozenset(e.candidate_id for e in device_rib),
                MappingProxyType(peer_ribs))


    def branch_contexts(
        self,
        *,
        router: Optional[str] = None,
        vrf: Optional[str] = None,
        prefix: Optional[str] = None,
        plane: str = "MAIN",
        protocol: Optional[str] = None,
        k: Optional[int] = None,
        guard_encoder: Optional["GuardEncoder"] = None,
    ) -> tuple[BranchContext, ...]:
        if k is not None and k < 0:
            raise ValueError("k must be non-negative")
        if k is not None and guard_encoder is None:
            from .guard_encoder import GuardEncoder

            guard_encoder = GuardEncoder(self.guard_variables)
        active_encoder = guard_encoder
        if k is not None:
            assert active_encoder is not None
        result: list[BranchContext] = []
        for entry in self.entries(
            router=router,
            vrf=vrf,
            prefix=prefix,
            plane=plane,
            protocol=protocol,
        ):
            if k is not None:
                assert active_encoder is not None
                if not active_encoder.is_feasible_within_k(entry.guard_ast, k):
                    continue
            result.append(self.context(entry))
        return tuple(result)

    def forwarding_entries(
        self, *, router: str, vrf: str, destination: str, plane: str = "MAIN",
    ) -> tuple[RouteEntry, ...]:
        """All non-LOCAL routes covering a destination, not only the longest.

        The index looks up every ancestor prefix of the destination network.
        Distinct candidates at one prefix and shorter-prefix fallbacks are all
        retained, with exactly the original candidate-id ordering.
        """
        return self._cached_forwarding(router, vrf, destination, plane.upper())

    def _query_forwarding(self, router, vrf, destination, plane):
        destination_network = self._cached_destination(destination)
        by_prefix = self._cached_scope_prefixes(router, vrf, plane)
        address = int(destination_network.network_address)
        width = destination_network.max_prefixlen
        matches = []
        for length in range(destination_network.prefixlen + 1):
            shift = width - length
            network_address = (address >> shift) << shift
            matches.extend(by_prefix.get((destination_network.version, length, network_address), ()))
        return tuple(sorted(matches, key=lambda item: item.candidate_id))

    def _query_scope_prefixes(self, router, vrf, plane):
        by_prefix = {}
        for entry in self.entries(router=router, vrf=vrf, plane=plane):
            if entry.protocol == 'LOCAL':
                continue
            try:
                network = self._cached_route_network(entry.prefix)
            except ValueError as error:
                raise SymbolicRouteFormatError(
                    f"candidate {entry.candidate_id} has invalid prefix {entry.prefix!r}: {error}") from error
            key = network.version, network.prefixlen, int(network.network_address)
            by_prefix.setdefault(key, []).append(entry)
        return MappingProxyType({key: tuple(value) for key, value in by_prefix.items()})

    @staticmethod
    def _destination_network(destination):
        try:
            if '/' in destination:
                return ipaddress.ip_network(destination, strict=False)
            address = ipaddress.ip_address(destination)
            return ipaddress.ip_network(f'{address}/{address.max_prefixlen}', strict=False)
        except ValueError as error:
            raise SymbolicRouteFormatError(
                f"cannot parse property destination {destination!r}: {error}") from error

    def query_cache_info(self) -> dict[str, dict[str, int]]:
        """Bounded, per-RIB cache statistics for profiling (not solver semantics)."""
        return {name: getattr(self, '_cached_' + name).cache_info()._asdict()
                for name in self._QUERY_CACHE_NAMES}

    def clear_query_caches(self) -> None:
        """Release derived query results; preserve immutable source indexes."""
        for name in self._QUERY_CACHE_NAMES:
            getattr(self, '_cached_' + name).cache_clear()


    def forwarding_branch_contexts(
        self,
        *,
        router: str,
        vrf: str,
        destination: str,
        plane: str = "MAIN",
        k: Optional[int] = None,
        guard_encoder: Optional["GuardEncoder"] = None,
    ) -> tuple[BranchContext, ...]:
        """Build contexts for every k-feasible selected entry covering a destination."""

        if k is not None and k < 0:
            raise ValueError("k must be non-negative")
        if k is not None and guard_encoder is None:
            from .guard_encoder import GuardEncoder

            guard_encoder = GuardEncoder(self.guard_variables)
        result: list[BranchContext] = []
        for entry in self.forwarding_entries(
            router=router,
            vrf=vrf,
            destination=destination,
            plane=plane,
        ):
            if k is not None:
                assert guard_encoder is not None
                if not guard_encoder.is_feasible_within_k(entry.guard_ast, k):
                    continue
            result.append(self.context(entry, destination=destination))
        return tuple(result)

    def __iter__(self) -> Iterator[RouteEntry]:
        return iter(self.entries_all)
