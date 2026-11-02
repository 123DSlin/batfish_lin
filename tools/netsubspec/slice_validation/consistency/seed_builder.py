"""Assemble per-branch consistency seed encodings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

from .branch_loader import BranchContext, RouteEntry, SymbolicRib, SymbolicRouteFormatError
from .guard_encoder import GuardEncoder
from .route_binder import BindingDiagnostic, NamedConstraint, RouteBinder, SmtSymbolTable


class SeedBuildError(RuntimeError):
    """Raised when a seed cannot be constructed soundly."""


@dataclass(frozen=True)
class SeedArtifact:
    candidate_id: str
    router: str
    prefix: str
    k: int
    text: str
    constraints: tuple[NamedConstraint, ...]
    diagnostics: tuple[BindingDiagnostic, ...]
    output_path: Optional[Path] = None


class SeedBuilder:
    """Build a runnable SMT-LIB seed while keeping configuration fields pinned."""

    _SOLVER_COMMAND = re.compile(
        r"^\s*\((?:check-sat|get-model|get-unsat-core|exit)\b.*\)\s*$"
    )
    _CONCRETE_LINK_FAILURE_PIN = re.compile(
        r"^\s*\(assert\s+\(=\s+"
        r"(?P<symbol>\|0_FAILED-EDGE_[^|]+\|)\s+0\)\)\s*$"
    )
    _ASSERTIONS_MARKER = "; ---- Assertions ----"
    _SECTION_ORDER = (
        "Selected symbolic-route branch guard",
        "At-most-k link-failure budget",
        "Link-state bridge",
        "Current selected route",
        "Selected import route",
        "Selected peer predecessor route",
        "Remaining peer candidate routes",
        "Selected-peer link state",
        "Device control-forwarding state",
    )

    def __init__(self, rib: SymbolicRib, strict: bool = True) -> None:
        self.rib = rib
        self.strict = strict
        self.guard_encoder = GuardEncoder(rib.guard_variables)

    def build(
        self,
        context: BranchContext,
        device_smt_path: Path | str,
        *,
        k: int,
        destination: Optional[str] = None,
        output_path: Optional[Path | str] = None,
    ) -> SeedArtifact:
        if k < 0:
            raise ValueError("k must be non-negative")
        entry = context.current_entry
        if not self.guard_encoder.is_feasible_within_k(entry.guard_ast, k):
            raise SeedBuildError(
                f"candidate {entry.candidate_id} is infeasible under at-most-{k} failures"
            )

        device_smt_path = Path(device_smt_path)
        try:
            base_text = device_smt_path.read_text(encoding="utf-8")
        except OSError as error:
            raise SeedBuildError(f"cannot read {device_smt_path}: {error}") from error
        base_text, preparation_diagnostics = self._prepare_device_encoding(
            base_text, entry
        )
        symbols = SmtSymbolTable.from_text(base_text)

        constraints: list[NamedConstraint] = []
        branch_token = entry.candidate_id.removeprefix("candidate-v1-")[:12]
        constraints.append(
            NamedConstraint(
                f"branch_{branch_token}_selection_guard",
                self.guard_encoder.encode(entry.selection_guard),
                "Selected symbolic-route branch guard",
                "current branch guard",
            )
        )
        constraints.append(
            NamedConstraint(
                f"branch_{branch_token}_at_most_{k}_failures",
                self.guard_encoder.at_most_k_expression(k),
                "At-most-k link-failure budget",
                "failure budget",
            )
        )
        for index, expression in enumerate(
            self.guard_encoder.bridge_expressions(symbols.declarations)
        ):
            constraints.append(
                NamedConstraint(
                    f"branch_{branch_token}_link_bridge_{index}",
                    expression,
                    "Link-state bridge",
                    "symbolic-route/device failure-variable bridge",
                )
            )

        binding = RouteBinder(self.rib, self.guard_encoder, symbols).bind(context)
        if binding.errors and self.strict:
            details = "; ".join(f"{item.code}: {item.message}" for item in binding.errors)
            raise SeedBuildError(
                f"cannot construct seed for {entry.candidate_id}: {details}"
            )
        constraints.extend(binding.constraints)

        base_text = self._insert_guard_declarations(base_text, symbols)
        lines: list[str] = []
        if ":produce-unsat-cores" not in base_text:
            lines.append("(set-option :produce-unsat-cores true)")
        lines.append(base_text.rstrip())
        lines.append("")
        lines.append("; ---- Symbolic Route Consistency Seed ----")
        lines.append(f"; Candidate: {entry.candidate_id}")
        lines.append(f"; Device: {entry.router}")
        lines.append(f"; VRF: {entry.vrf}")
        lines.append(f"; Property destination: {destination or entry.prefix}")
        lines.append(f"; Selected route prefix: {entry.prefix}")
        lines.append(f"; Protocol: {entry.protocol}")
        lines.append(f"; Selected peer: {entry.selected_peer or 'local'}")
        lines.append(f"; Failure budget: at most {k}")
        lines.append(f"; Device encoding: {device_smt_path.name}")
        for diagnostic in preparation_diagnostics:
            lines.append(f"; Adapter: {diagnostic.message}")
        lines.extend(self._render_constraint_sections(constraints))
        lines.append("")
        lines.append("; Consistency query")
        lines.append("(check-sat)")
        text = "\n".join(lines) + "\n"

        rendered_output: Optional[Path] = None
        if output_path is not None:
            rendered_output = Path(output_path)
            rendered_output.parent.mkdir(parents=True, exist_ok=True)
            temporary = rendered_output.with_suffix(rendered_output.suffix + ".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(rendered_output)

        return SeedArtifact(
            candidate_id=entry.candidate_id,
            router=entry.router,
            prefix=entry.prefix,
            k=k,
            text=text,
            constraints=tuple(constraints),
            diagnostics=preparation_diagnostics + binding.diagnostics,
            output_path=rendered_output,
        )

    def _prepare_device_encoding(
        self, text: str, entry: RouteEntry
    ) -> tuple[str, tuple[BindingDiagnostic, ...]]:
        """Remove query commands and only the justified concrete pins.

        AutoNetSubspec's device slices originate from a concrete Minesweeper
        query.  A symbolic-route seed releases only inter-router
        ``FAILED-EDGE`` variables represented by the structured guard inventory;
        interface-local and device-failure pins remain intact.

        Older Minesweeper slices can also force a locally originated connected
        best route to be absent when its source is a loopback.  That one exact
        assertion is normalized only after the structured RIB and interface
        inventory prove the route is a local CONNECTED origin.  The route is
        then explicitly rebound by :class:`RouteBinder` and still checked by Z3.
        """

        try:
            local_interface = self.rib.local_connected_origin_interface(entry)
        except SymbolicRouteFormatError as error:
            raise SeedBuildError(str(error)) from error

        local_false_assertion: Optional[re.Pattern[str]] = None
        if local_interface is not None:
            connected_best = self._record_symbol(
                entry.router, "CONNECTED_BEST_None", "permitted"
            )
            local_false_assertion = re.compile(
                rf"^\s*\(assert\s+\(not\s+{re.escape(connected_best)}\)\)\s*$"
            )

        releasable_failures = self._releasable_failure_symbols()
        prepared: list[str] = []
        normalized_local_assertions = 0
        for line in text.splitlines():
            if self._SOLVER_COMMAND.match(line):
                continue
            failure_pin = self._CONCRETE_LINK_FAILURE_PIN.match(line)
            if (
                failure_pin is not None
                and failure_pin.group("symbol") in releasable_failures
            ):
                continue
            if local_false_assertion is not None and local_false_assertion.match(line):
                normalized_local_assertions += 1
                continue
            prepared.append(line)

        if normalized_local_assertions > 1:
            raise SeedBuildError(
                f"device slice contains {normalized_local_assertions} duplicate "
                f"CONNECTED_BEST absence assertions for {entry.router}"
            )

        diagnostics: tuple[BindingDiagnostic, ...] = ()
        if normalized_local_assertions == 1:
            assert local_interface is not None
            diagnostics = (
                BindingDiagnostic(
                    "INFO",
                    "NORMALIZED_LOCAL_CONNECTED_ORIGIN",
                    f"removed the incompatible CONNECTED_BEST=false assertion for "
                    f"proven local origin {entry.router}:{local_interface}",
                ),
            )
        return "\n".join(prepared), diagnostics

    def _releasable_failure_symbols(self) -> frozenset[str]:
        symbols: set[str] = set()
        for variable in self.rib.guard_variables:
            symbols.add(
                f"|0_FAILED-EDGE_{variable.first_router}_{variable.second_router}|"
            )
            symbols.add(
                f"|0_FAILED-EDGE_{variable.second_router}_{variable.first_router}|"
            )
        return frozenset(symbols)

    @staticmethod
    def _record_symbol(router: str, record: str, field: str) -> str:
        return f"|0_{router}_{record}_{field}|"

    def _insert_guard_declarations(
        self, base_text: str, symbols: SmtSymbolTable
    ) -> str:
        """Place symbolic link declarations in AutoNetSubspec's declaration block."""

        declarations: list[str] = []
        for variable in self.guard_encoder.variables:
            symbol = self.guard_encoder.symbol(variable.variable_id)
            existing_sort = symbols.sort(symbol)
            if existing_sort is not None:
                if existing_sort != "Bool":
                    raise SeedBuildError(
                        f"symbolic link variable {symbol} is declared as "
                        f"{existing_sort}, expected Bool"
                    )
                continue
            declarations.append(f"(declare-fun {symbol} () Bool)")
        if not declarations:
            return base_text

        marker_index = base_text.find(self._ASSERTIONS_MARKER)
        if marker_index < 0:
            raise SeedBuildError(
                "device slice is missing the AutoNetSubspec assertions marker: "
                f"{self._ASSERTIONS_MARKER}"
            )
        before = base_text[:marker_index].rstrip()
        after = base_text[marker_index:].lstrip()
        return "\n".join([before, *declarations, "", after])

    @classmethod
    def _render_constraint_sections(
        cls, constraints: list[NamedConstraint]
    ) -> list[str]:
        """Render numbered semantic blocks in the original pipeline's style."""

        sections: dict[str, list[NamedConstraint]] = {}
        for constraint in constraints:
            sections.setdefault(constraint.section, []).append(constraint)

        unexpected = sorted(set(sections) - set(cls._SECTION_ORDER))
        if unexpected:
            raise SeedBuildError(
                "consistency constraints use unknown section(s): "
                + ", ".join(unexpected)
            )

        lines: list[str] = []
        for index, section in enumerate(cls._SECTION_ORDER, 1):
            members = sections.get(section)
            if not members:
                continue
            lines.append("")
            lines.append(f"; Seed{index}: {section}")
            lines.extend(member.render() for member in members)
        return lines
