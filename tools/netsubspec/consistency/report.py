"""Structured and readable reports for the formal consistency gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class Scope:
    """The complete production scope, or an explicitly filtered debug scope."""

    mode: str
    routers: tuple[str, ...]
    vrf: str
    destinations: tuple[str, ...]
    plane: str
    k: int
    router_filter: Optional[str] = None
    prefix_filter: Optional[str] = None


@dataclass(frozen=True)
class BranchCheckResult:
    candidate_id: str
    router: str
    vrf: str
    destination: str
    prefix: str
    plane: str
    protocol: str
    selected_peer: Optional[str]
    selection_guard: str
    status: str
    seed_file: Optional[str]
    solver_seconds: float
    consistency_constraints: int
    diagnostics: tuple[dict[str, str], ...] = ()
    unsat_core: tuple[str, ...] = ()
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["diagnostics"] = list(self.diagnostics)
        result["unsat_core"] = list(self.unsat_core)
        return result


@dataclass(frozen=True)
class ScopeCheckResult:
    """Coverage and solver outcome for one device/destination pair."""

    router: str
    vrf: str
    destination: str
    plane: str
    device_encoding: str
    status: str
    total_branches: int
    eligible_branches: int
    checked_branches: int
    sat_branches: int
    unsat_branches: int
    unknown_branches: int
    error_branches: int
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["errors"] = list(self.errors)
        return result


@dataclass(frozen=True)
class ConsistencyReport:
    scope: Scope
    status: str
    generated_at: str
    source_json: str
    hostnames_file: str
    destinations_file: str
    solver: str
    total_scope_branches: int
    eligible_branches: int
    checked_branches: int
    sat_branches: int
    unsat_branches: int
    unknown_branches: int
    error_branches: int
    scope_results: tuple[ScopeCheckResult, ...] = ()
    branches: tuple[BranchCheckResult, ...] = ()
    errors: tuple[str, ...] = ()
    schema_name: str = "tolerance-symbolic-consistency-report"
    schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["scope_results"] = [item.to_dict() for item in self.scope_results]
        result["branches"] = [item.to_dict() for item in self.branches]
        result["errors"] = list(self.errors)
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    def to_readable_text(self) -> str:
        local_origin_normalizations = sum(
            diagnostic.get("code") == "NORMALIZED_LOCAL_CONNECTED_ORIGIN"
            for branch in self.branches
            for diagnostic in branch.diagnostics
        )
        lines = [
            "=" * 80,
            "SYMBOLIC ROUTE CONSISTENCY CHECK SUMMARY",
            "=" * 80,
            "",
            f"Overall status: {self.status}",
            (
                "Scope: "
                f"{self.scope.mode} | VRF {self.scope.vrf} | "
                f"{self.scope.plane} | at-most-{self.scope.k} link failures"
            ),
            f"Routers: {', '.join(self.scope.routers) or 'none'}",
            f"Destinations: {', '.join(self.scope.destinations) or 'none'}",
            (
                "Branches: "
                f"eligible={self.eligible_branches}/{self.total_scope_branches} | "
                f"checked={self.checked_branches}"
            ),
            (
                "Results: "
                f"SAT {self.sat_branches} | UNSAT {self.unsat_branches} | "
                f"UNKNOWN {self.unknown_branches} | ERROR {self.error_branches}"
            ),
        ]
        if local_origin_normalizations:
            lines.append(
                "Local CONNECTED origins normalized: "
                f"{local_origin_normalizations}"
            )
        lines.append("")
        if self.scope.mode == "debug-filtered":
            router_filter = self.scope.router_filter or "all"
            prefix_filter = self.scope.prefix_filter or "all"
            lines.extend(
                [
                    f"Debug filter: router={router_filter}, destination={prefix_filter}",
                    "",
                ]
            )
        if self.errors:
            lines.append("Global errors:")
            lines.extend(f"  - {error}" for error in self.errors)
            lines.append("")

        lines.append("Device results:")
        if not self.scope_results:
            lines.append("  (none)")
        for item in self.scope_results:
            lines.append(
                f"  Device {item.router:<8} | Destination {item.destination:<18} | "
                f"Eligible {item.eligible_branches}/{item.total_branches} | "
                f"SAT {item.sat_branches}/{item.checked_branches} | "
                f"Status {item.status}"
            )
            lines.extend(f"    error: {error}" for error in item.errors)
        lines.append("")

        failed_branches = tuple(
            branch for branch in self.branches if branch.status != "SAT"
        )
        if not failed_branches and not self.errors:
            lines.append("All eligible branches are consistent. ✓")
            return "\n".join(lines) + "\n"

        lines.append(f"Failed branches ({len(failed_branches)}):")
        if not failed_branches:
            lines.append("  (none; see errors above)")
        for branch in failed_branches:
            peer = branch.selected_peer or "local"
            seed = Path(branch.seed_file).stem if branch.seed_file else self._short_id(
                branch.candidate_id
            )
            lines.append(
                f"  {branch.status:<7} {seed} | Device {branch.router} | "
                f"Destination {branch.destination} | Route {branch.prefix} | "
                f"{branch.protocol} via {peer}"
            )
            lines.append(f"    guard: {branch.selection_guard}")
            if branch.unsat_core:
                lines.append(f"    unsat core: {' '.join(branch.unsat_core)}")
            if branch.error:
                lines.append(f"    error: {branch.error}")
            for diagnostic in branch.diagnostics:
                lines.append(
                    f"    {diagnostic.get('level', 'INFO').lower()}: "
                    f"{diagnostic.get('code', 'DIAGNOSTIC')} - "
                    f"{diagnostic.get('message', '')}"
                )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _short_id(candidate_id: str) -> str:
        return candidate_id.removeprefix("candidate-v1-")[:12]

    def write(self, output_directory: Path) -> tuple[Path, Path]:
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "consistency_report.json"
        text_path = output_directory / "consistency_report.txt"
        self._write_atomic(json_path, self.to_json())
        self._write_atomic(text_path, self.to_readable_text())
        return json_path, text_path

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
