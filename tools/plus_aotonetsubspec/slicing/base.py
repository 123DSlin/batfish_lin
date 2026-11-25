"""Extension contract between the shared slicing engine and protocol semantics.

Adapters select boundaries and audit requirements; rules classify assertions
without mutating engine state. The engine owns indexing, shared dependencies,
fixed-point closure, output validation and file writing. A future SPF adapter
must explicitly define its topology/level dependencies and boundary contract;
it must not merely substitute ISIS names into the BGP rules.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple
from .models import DeviceSemanticScope, SymbolicSliceRequirements


class ProtocolSliceRules(ABC):
    @abstractmethod
    def should_remove(self, expression: str) -> bool:
        """Identify property/query assertions excluded by this model boundary."""

    @abstractmethod
    def assertion_owners(self, expression: str) -> Set[str]:
        """Return devices owning the retained local equation (possibly empty)."""

    @abstractmethod
    def dependency_keys(self, variables: Sequence[str]) -> Tuple[str, ...]:
        """Index deferred protocol equations by their output symbols."""


class ProtocolSliceAdapter(ABC):
    name: str

    def ensure_supported(self) -> None:
        """Reject reserved/unimplemented adapters before reading or writing output."""

    @abstractmethod
    def required_input_files(self) -> Tuple[str, ...]:
        """Protocol-specific input contract, checked before slice generation."""

    @abstractmethod
    def build_scopes(self, work_dir: Path | str, declarations: List[str]) -> Dict[str, DeviceSemanticScope]:
        """Declare local equations, protocol roots, and external boundary symbols."""

    @abstractmethod
    def build_requirements(self, work_dir: Path | str, declarations: List[str], *,
                           k: int, vrf: str) -> SymbolicSliceRequirements:
        """Audit branch bindings against full declarations; never enlarge slices."""

    @abstractmethod
    def create_rules(self, routers: Sequence[str], model_igp: bool) -> ProtocolSliceRules:
        """Create per-run classification rules; do not share mutable run state."""
