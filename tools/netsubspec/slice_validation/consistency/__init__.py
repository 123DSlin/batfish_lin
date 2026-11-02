"""Building blocks for symbolic-route/device-encoding consistency checks."""

from .branch_loader import (
    BranchContext,
    GuardVariable,
    NeighborTopology,
    RouteEntry,
    SymbolicRib,
    SymbolicRouteFormatError,
)
from .checker import ConsistencyChecker, ConsistencyCheckerError
from .guard_encoder import GuardEncodingError, GuardEncoder
from .report import BranchCheckResult, ConsistencyReport, Scope, ScopeCheckResult
from .route_binder import (
    BindingDiagnostic,
    BindingResult,
    NamedConstraint,
    RouteBinder,
    SmtSymbolTable,
)
from .seed_builder import SeedArtifact, SeedBuildError, SeedBuilder

__all__ = [
    "BindingDiagnostic",
    "BindingResult",
    "BranchCheckResult",
    "BranchContext",
    "ConsistencyChecker",
    "ConsistencyCheckerError",
    "ConsistencyReport",
    "GuardEncoder",
    "GuardEncodingError",
    "GuardVariable",
    "NamedConstraint",
    "NeighborTopology",
    "RouteBinder",
    "RouteEntry",
    "Scope",
    "ScopeCheckResult",
    "SeedArtifact",
    "SeedBuildError",
    "SeedBuilder",
    "SmtSymbolTable",
    "SymbolicRib",
    "SymbolicRouteFormatError",
]
