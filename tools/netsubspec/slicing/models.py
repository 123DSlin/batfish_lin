"""Protocol-neutral device boundaries and branch binding audit requirements."""
from dataclasses import dataclass
from typing import Dict, Set, Tuple


class SymbolicSliceError(ValueError):
    """A slice cannot be constructed within its declared semantic scope."""


class UnsupportedSliceProtocol(SymbolicSliceError):
    """An adapter is registered but its semantics are not implemented."""


@dataclass(frozen=True)
class SymbolicSliceRequirements:
    required_by_router: Dict[str, Set[str]]
    local_roots_by_router: Dict[str, Set[str]]


@dataclass(frozen=True)
class DeviceSemanticScope:
    router: str
    peers: Tuple[str, ...]
    peer_boundary_symbols: Set[str]
    protocol_equation_symbols: Set[str]
    local_symbols: Set[str]
    protocol: str = "bgp"

    @property
    def incoming_export_symbols(self) -> Set[str]:
        """Compatibility name for the BGP adapter's protocol equation roots."""
        return self.protocol_equation_symbols

    @property
    def required_declarations(self) -> Set[str]:
        return (set(self.peer_boundary_symbols)
                | set(self.protocol_equation_symbols) | set(self.local_symbols))
