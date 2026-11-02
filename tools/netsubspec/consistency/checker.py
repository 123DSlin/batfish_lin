"""Formal all-branches consistency gate for the property-relevant scope."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Optional

from .branch_loader import BranchContext, SymbolicRib, SymbolicRouteFormatError
from .report import (
    BranchCheckResult,
    ConsistencyReport,
    Scope,
    ScopeCheckResult,
)
from .seed_builder import SeedBuildError, SeedBuilder


class ConsistencyCheckerError(RuntimeError):
    """Raised when the checker cannot initialize its formal checking scope."""


class ConsistencyChecker:
    """Build and solve every relevant k-pruned MAIN branch seed.

    A production run discovers routers and destination prefixes from the
    symbolic output directory.  ``router`` and ``prefix`` are optional filters
    intended only for debugging an individual portion of that complete scope.
    """

    _HOSTNAMES_FILE = "0_hostnames.txt"
    _DESTINATIONS_FILE = "0_dst_ips.txt"
    _PLANE = "MAIN"

    def __init__(
        self,
        work_directory: Path | str,
        *,
        z3_path: Optional[Path | str] = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.work_directory = Path(work_directory).resolve()
        self.timeout_seconds = timeout_seconds
        self.z3_path = self._resolve_z3(z3_path)
        try:
            self.rib = SymbolicRib.from_work_directory(self.work_directory)
        except SymbolicRouteFormatError as error:
            raise ConsistencyCheckerError(str(error)) from error
        self.seed_builder = SeedBuilder(self.rib, strict=True)

    @staticmethod
    def _resolve_z3(z3_path: Optional[Path | str]) -> Path:
        candidates: list[Path] = []
        if z3_path is not None:
            candidates.append(Path(z3_path).expanduser())
        discovered = shutil.which("z3")
        if discovered:
            candidates.append(Path(discovered))
        candidates.extend(
            [
                Path("/opt/homebrew/bin/z3"),
                Path("/usr/local/bin/z3"),
                Path("/usr/bin/z3"),
            ]
        )
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_mode & 0o111:
                return candidate.resolve()
        raise ConsistencyCheckerError(
            "cannot find a Z3 executable; install z3 or pass --z3 /path/to/z3"
        )

    def run(
        self,
        *,
        k: int,
        router: Optional[str] = None,
        prefix: Optional[str] = None,
        vrf: str = "default",
        output_directory: Optional[Path | str] = None,
    ) -> ConsistencyReport:
        if k < 0:
            raise ValueError("k must be non-negative")
        if router is not None and not router:
            raise ValueError("router filter must be non-empty")
        if prefix is not None and not prefix:
            raise ValueError("prefix filter must be non-empty")
        if not vrf:
            raise ValueError("vrf must be non-empty")

        output = (
            Path(output_directory).resolve()
            if output_directory is not None
            else self.work_directory / "2_consistency_check"
        )
        seeds_directory = output / "seeds"
        if seeds_directory.exists():
            shutil.rmtree(seeds_directory)
        seeds_directory.mkdir(parents=True, exist_ok=True)

        hostnames_file = self.work_directory / self._HOSTNAMES_FILE
        destinations_file = self.work_directory / self._DESTINATIONS_FILE
        errors: list[str] = []
        available_routers = self._load_required_values(
            hostnames_file, "device inventory", errors
        )
        session_routers = set(self.rib.topology.routers())
        available_routers = tuple(
            router for router in available_routers if router in session_routers
        )
        if not available_routers:
            errors.append("enabled BGP scope contains no session routers")
        available_prefixes = self._load_required_values(
            destinations_file, "property destination inventory", errors
        )
        routers = self._apply_filter(
            available_routers, router, "router", hostnames_file, errors
        )
        prefixes = self._apply_filter(
            available_prefixes, prefix, "prefix", destinations_file, errors
        )
        mode = "debug-filtered" if router is not None or prefix is not None else "global"
        scope = Scope(
            mode=mode,
            routers=routers,
            vrf=vrf,
            destinations=prefixes,
            plane=self._PLANE,
            k=k,
            router_filter=router,
            prefix_filter=prefix,
        )

        scope_results: list[ScopeCheckResult] = []
        branch_results: list[BranchCheckResult] = []
        seed_name_counts: dict[tuple[str, str], int] = {}
        for selected_router in routers:
            for selected_destination in prefixes:
                scope_result, results = self._check_scope(
                    router=selected_router,
                    vrf=vrf,
                    destination=selected_destination,
                    k=k,
                    seeds_directory=seeds_directory,
                    seed_name_counts=seed_name_counts,
                )
                scope_results.append(scope_result)
                branch_results.extend(results)

        expected_scope_count = len(routers) * len(prefixes)
        passed = (
            not errors
            and expected_scope_count > 0
            and len(scope_results) == expected_scope_count
            and all(item.status == "PASS" for item in scope_results)
        )
        report = ConsistencyReport(
            scope=scope,
            status="PASS" if passed else "FAIL",
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_json=str(self.work_directory / "symbolic_route.json"),
            hostnames_file=str(hostnames_file),
            destinations_file=str(destinations_file),
            solver=self._solver_version(),
            total_scope_branches=sum(item.total_branches for item in scope_results),
            eligible_branches=sum(item.eligible_branches for item in scope_results),
            checked_branches=sum(item.checked_branches for item in scope_results),
            sat_branches=sum(item.sat_branches for item in scope_results),
            unsat_branches=sum(item.unsat_branches for item in scope_results),
            unknown_branches=sum(item.unknown_branches for item in scope_results),
            error_branches=sum(item.error_branches for item in scope_results),
            scope_results=tuple(scope_results),
            branches=tuple(branch_results),
            errors=tuple(errors),
        )
        report.write(output)
        return report

    @staticmethod
    def _load_required_values(
        path: Path, description: str, errors: list[str]
    ) -> tuple[str, ...]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            errors.append(f"cannot load {description} {path}: {error}")
            return ()
        values = sorted(
            {
                line.strip()
                for line in lines
                if line.strip() and not line.lstrip().startswith("#")
            }
        )
        if not values:
            errors.append(f"{description} is empty: {path}")
        return tuple(values)

    @staticmethod
    def _apply_filter(
        available: tuple[str, ...],
        requested: Optional[str],
        kind: str,
        source: Path,
        errors: list[str],
    ) -> tuple[str, ...]:
        if requested is None:
            return available
        if requested not in available:
            errors.append(
                f"debug {kind} filter {requested!r} is not listed in {source}"
            )
            return ()
        return (requested,)

    def _check_scope(
        self,
        *,
        router: str,
        vrf: str,
        destination: str,
        k: int,
        seeds_directory: Path,
        seed_name_counts: dict[tuple[str, str], int],
    ) -> tuple[ScopeCheckResult, tuple[BranchCheckResult, ...]]:
        device_encoding = (
            self.work_directory
            / "1_sliced_device_smt_encoding"
            / f"sliced_{router}_smt_encoding.smt2"
        )
        errors: list[str] = []
        if not device_encoding.is_file():
            errors.append(f"missing device encoding: {device_encoding}")

        try:
            total_entries = self.rib.forwarding_entries(
                router=router,
                vrf=vrf,
                destination=destination,
                plane=self._PLANE,
            )
            contexts = self.rib.forwarding_branch_contexts(
                router=router,
                vrf=vrf,
                destination=destination,
                plane=self._PLANE,
                k=k,
            )
        except SymbolicRouteFormatError as error:
            errors.append(str(error))
            total_entries = ()
            contexts = ()
        if not total_entries and not errors:
            errors.append(
                "scope contains no non-LOCAL selected MAIN route branch covering "
                "the property destination; "
                "refusing to pass an empty seed set"
            )
        elif not contexts:
            errors.append(
                "no MAIN branch is feasible within the failure budget; "
                "refusing to pass an empty seed set"
            )

        results: list[BranchCheckResult] = []
        if not errors:
            for context in contexts:
                base_name = f"seed_{self._branch_path_token(context)}"
                name_key = (router, base_name)
                seed_name_counts[name_key] = seed_name_counts.get(name_key, 0) + 1
                occurrence = seed_name_counts[name_key]
                seed_name = base_name if occurrence == 1 else f"{base_name}_{occurrence}"
                results.append(
                    self._check_branch(
                        context,
                        device_encoding,
                        seeds_directory,
                        k,
                        destination,
                        seed_name,
                    )
                )

        checked = len(results)
        sat = sum(item.status == "SAT" for item in results)
        unsat = sum(item.status == "UNSAT" for item in results)
        unknown = sum(item.status == "UNKNOWN" for item in results)
        branch_errors = sum(item.status in {"ERROR", "TIMEOUT"} for item in results)
        passed = (
            not errors
            and len(contexts) > 0
            and checked == len(contexts)
            and sat == checked
        )
        scope_result = ScopeCheckResult(
            router=router,
            vrf=vrf,
            destination=destination,
            plane=self._PLANE,
            device_encoding=str(device_encoding),
            status="PASS" if passed else "FAIL",
            total_branches=len(total_entries),
            eligible_branches=len(contexts),
            checked_branches=checked,
            sat_branches=sat,
            unsat_branches=unsat,
            unknown_branches=unknown,
            error_branches=branch_errors,
            errors=tuple(errors),
        )
        return scope_result, tuple(results)

    def _check_branch(
        self,
        context: BranchContext,
        device_encoding: Path,
        seeds_directory: Path,
        k: int,
        destination: str,
        seed_name: str,
    ) -> BranchCheckResult:
        entry = context.current_entry
        router_directory = seeds_directory / self._file_token(entry.router)
        seed_path = router_directory / f"{seed_name}.smt2"
        relative_seed = str(seed_path.relative_to(seeds_directory.parent))
        started = time.monotonic()
        try:
            artifact = self.seed_builder.build(
                context,
                device_encoding,
                k=k,
                destination=destination,
                output_path=seed_path,
            )
        except (SeedBuildError, OSError, ValueError) as error:
            return self._branch_result(
                context,
                status="ERROR",
                destination=destination,
                seed_file=None,
                solver_seconds=time.monotonic() - started,
                consistency_constraints=0,
                error=str(error),
            )

        diagnostics = tuple(
            {"level": item.level, "code": item.code, "message": item.message}
            for item in artifact.diagnostics
        )
        assignments = self.seed_builder.guard_encoder.satisfying_failure_assignments(
            entry.selection_guard, k
        )
        if not assignments:
            return self._branch_result(
                context,
                status="ERROR",
                destination=destination,
                seed_file=relative_seed,
                solver_seconds=time.monotonic() - started,
                consistency_constraints=len(artifact.constraints),
                diagnostics=diagnostics,
                error="eligible branch has no concrete failure assignment",
            )

        status = "SAT"
        error_message: Optional[str] = None
        unsat_core: tuple[str, ...] = ()
        checked_assignments = 0
        for failed in assignments:
            scenario_text = self._pin_failure_assignment(artifact.text, failed)
            scenario = self._run_z3(scenario_text)
            checked_assignments += 1
            if scenario[0] == "SAT":
                continue
            status, output = scenario
            failure_label = ", ".join(sorted(failed)) or "none"
            if status == "UNSAT":
                unsat_core = self._get_unsat_core(scenario_text)
                error_message = f"inconsistent failure assignment: {failure_label}"
            elif status == "TIMEOUT":
                error_message = (
                    f"Z3 exceeded {self.timeout_seconds:g}s timeout for failure "
                    f"assignment: {failure_label}"
                )
            elif status == "UNKNOWN":
                error_message = f"Z3 returned unknown for failure assignment: {failure_label}"
            else:
                status = "ERROR"
                error_message = (
                    f"Z3 failed for failure assignment {failure_label}: {output}"
                )
            break

        diagnostics = diagnostics + (
            {
                "level": "INFO",
                "code": "P2_FAILURE_ASSIGNMENTS_CHECKED",
                "message": (
                    f"checked {checked_assignments}/{len(assignments)} concrete "
                    "failure assignments covered by the branch guard"
                ),
            },
        )

        return self._branch_result(
            context,
            status=status,
            destination=destination,
            seed_file=relative_seed,
            solver_seconds=time.monotonic() - started,
            consistency_constraints=len(artifact.constraints),
            diagnostics=diagnostics,
            unsat_core=unsat_core,
            error=error_message,
        )

    def _pin_failure_assignment(
        self, seed_text: str, failed_variables: frozenset[str]
    ) -> str:
        marker = "\n; Consistency query\n(check-sat)\n"
        if marker not in seed_text:
            raise ValueError("consistency seed is missing its final query marker")
        pins = self.seed_builder.guard_encoder.concrete_assignment_expressions(
            failed_variables
        )
        assertions = "\n".join(
            f"(assert (! {expression} :named p2_failure_assignment_{index}))"
            for index, expression in enumerate(pins)
        )
        replacement = (
            "\n; P2 concrete failure assignment\n"
            f"{assertions}\n"
            "; Consistency query\n(check-sat)\n"
        )
        return seed_text.replace(marker, replacement, 1)

    def _run_z3(self, smt_text: str) -> tuple[str, str]:
        try:
            process = subprocess.run(
                [str(self.z3_path), "-smt2", "-in"],
                input=smt_text,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT", ""
        except OSError as error:
            return "ERROR", str(error)
        if process.returncode != 0:
            return "ERROR", (process.stderr or process.stdout).strip()
        status = self._parse_status(process.stdout)
        if status not in {"SAT", "UNSAT", "UNKNOWN"}:
            return "ERROR", f"cannot parse Z3 status from output: {process.stdout!r}"
        return status, process.stdout

    @staticmethod
    def _file_token(value: str) -> str:
        token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
        return token or "unknown"

    @classmethod
    def _branch_path_token(cls, context: BranchContext) -> str:
        entry = context.current_entry
        forwarding_paths: set[tuple[str, ...]] = set()
        for path in entry.router_paths:
            if not path:
                continue
            if path[0] == entry.router:
                forwarding_paths.add(path)
            elif path[-1] == entry.router:
                forwarding_paths.add(tuple(reversed(path)))
        if len(forwarding_paths) == 1:
            path = next(iter(forwarding_paths))
        elif entry.selected_peer:
            path = (entry.router, entry.selected_peer)
        else:
            path = (entry.router,)
        return "-".join(cls._file_token(router) for router in path)

    @staticmethod
    def _branch_result(
        context: BranchContext,
        *,
        status: str,
        destination: str,
        seed_file: Optional[str],
        solver_seconds: float,
        consistency_constraints: int,
        diagnostics: tuple[dict[str, str], ...] = (),
        unsat_core: tuple[str, ...] = (),
        error: Optional[str] = None,
    ) -> BranchCheckResult:
        entry = context.current_entry
        return BranchCheckResult(
            candidate_id=entry.candidate_id,
            router=entry.router,
            vrf=entry.vrf,
            destination=destination,
            prefix=entry.prefix,
            plane=entry.plane,
            protocol=entry.protocol,
            selected_peer=entry.selected_peer,
            selection_guard=str(entry.selection_guard.get("simplified", "")),
            status=status,
            seed_file=seed_file,
            solver_seconds=solver_seconds,
            consistency_constraints=consistency_constraints,
            diagnostics=diagnostics,
            unsat_core=unsat_core,
            error=error,
        )

    @staticmethod
    def _parse_status(stdout: str) -> str:
        for line in stdout.splitlines():
            status = line.strip().lower()
            if status in {"sat", "unsat", "unknown"}:
                return status.upper()
        return "ERROR"

    def _get_unsat_core(self, seed_text: str) -> tuple[str, ...]:
        try:
            process = subprocess.run(
                [str(self.z3_path), "-smt2", "-in"],
                input=seed_text + "(get-unsat-core)\n",
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ()
        if process.returncode != 0:
            return ()
        lines = [line.strip() for line in process.stdout.splitlines() if line.strip()]
        for line in reversed(lines):
            if line.startswith("(") and line.endswith(")"):
                return tuple(line[1:-1].split())
        return ()

    def _solver_version(self) -> str:
        try:
            process = subprocess.run(
                [str(self.z3_path), "-version"],
                capture_output=True,
                text=True,
                timeout=min(self.timeout_seconds, 5.0),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return str(self.z3_path)
        version = process.stdout.strip() or process.stderr.strip()
        return version or str(self.z3_path)
