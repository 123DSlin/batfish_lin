#!/usr/bin/env python3
"""Derive field- and line-level subspecifications per symbolic-route branch.

This stage reuses AutoNetSubspec's configuration domains, target grouping,
normalization, and report writers. Its solving semantics are intentionally
different: symbolic failure and destination variables are universally
quantified, device/control-plane state is existentially quantified, and only
the selected configuration field or line remains free. Every subspecification
formula is derived from this symbolic projection; no concrete candidate path is
used.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Optional

from utils.util_smt import (
    get_bounds_for_multiple_config_variables,
    is_ip_mask_pair,
    parse_smt2_sexpr,
    serialize_smt2_sexpr,
    subspec_string_to_smt2_and,
    subspec_string_to_list,
    tokenize_smt2_sexpr,
)
from utils.util_file import (
    find_metadata_file,
    load_target_dst_ip,
    save_field_level_subspecs,
    save_line_level_subspecs,
    save_synthesis_metadata,
)
from utils.util_norm import normalize_subspec
from utils.util_symbolic import (
    ConfigPin,
    SmtDocument as _SharedSmtDocument,
    SmtSolver,
    SubspecificationError,
    and_expression as _and_expression,
    collect_declared_symbols as _collect_declared_symbols,
    configuration_value_operation as _configuration_value_operation,
    constraint_ids as _constraint_ids,
    integer_interval as _integer_interval,
    interval_expression as _interval_expression,
    preferred_strict_lower_bound as _preferred_strict_lower_bound,
    preferred_strict_upper_bound as _preferred_strict_upper_bound,
    residual_declared_symbols as _residual_declared_symbols,
    serialize_subspec_expression as _serialize_subspec_expression,
    strict_thresholds as _strict_lower_thresholds,
    substitute_symbols as _substitute_symbols,
)


@dataclass(frozen=True)
class BranchFieldSubspec:
    config: str
    released_configs: tuple[str, ...]
    sort: str
    original_value: str
    constraint: str
    unrestricted: bool
    derivation: str
    solver_seconds: float
    constraint_ids: tuple[str, ...]
    projection: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["released_configs"] = list(self.released_configs)
        result["constraint_ids"] = list(self.constraint_ids)
        return result


@dataclass(frozen=True)
class BranchLineSubspec:
    line_group: str
    configs: tuple[str, ...]
    constraint: str
    unrestricted: bool
    derivation: str
    solver_seconds: float
    constraint_ids: tuple[str, ...]
    projection: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["configs"] = list(self.configs)
        result["constraint_ids"] = list(self.constraint_ids)
        return result


@dataclass(frozen=True)
class BranchSubspec:
    candidate_id: str
    router: str
    destination: str
    prefix: str
    protocol: str
    selected_peer: Optional[str]
    selection_guard: str
    selection_guard_assertion: str
    selection_guard_smt: str
    failure_budget_assertion: str
    failure_budget_smt: str
    failure_variables: tuple[str, ...]
    seed_file: str
    seed_sha256: str
    fields: tuple[BranchFieldSubspec, ...]
    lines: tuple[BranchLineSubspec, ...]

    @property
    def branch_name(self) -> str:
        return Path(self.seed_file).stem.removeprefix("seed_")

    @property
    def provenance_id(self) -> str:
        digest = hashlib.sha256(self.candidate_id.encode("utf-8")).hexdigest()[:16]
        return f"provenance-v1-{digest}"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["branch_name"] = self.branch_name
        result["provenance_id"] = self.provenance_id
        result["failure_variables"] = list(self.failure_variables)
        result["fields"] = [item.to_dict() for item in self.fields]
        result["lines"] = [item.to_dict() for item in self.lines]
        return result


@dataclass(frozen=True)
class SubspecificationReport:
    status: str
    generated_at: str
    source_consistency_report: str
    scope: dict[str, Any]
    branch_count: int
    field_evaluations: int
    constrained_field_evaluations: int
    line_evaluations: int
    constrained_line_evaluations: int
    branches: tuple[BranchSubspec, ...]
    errors: tuple[str, ...] = ()
    schema_name: str = "tolerance-symbolic-branch-subspec-report"
    schema_version: int = 5

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "status": self.status,
            "generated_at": self.generated_at,
            "source_consistency_report": self.source_consistency_report,
            "scope": self.scope,
            "branch_count": self.branch_count,
            "field_evaluations": self.field_evaluations,
            "constrained_field_evaluations": self.constrained_field_evaluations,
            "line_evaluations": self.line_evaluations,
            "constrained_line_evaluations": self.constrained_line_evaluations,
            "branches": [item.to_dict() for item in self.branches],
            "errors": list(self.errors),
        }
        result.update(self._provenance_indexes(self.branches))
        return result

    def _provenance_indexes(
        self, branches: tuple[BranchSubspec, ...]
    ) -> dict[str, list[dict[str, Any]]]:
        branch_provenance = []
        constraints: dict[str, dict[str, Any]] = {}
        for branch in branches:
            branch_provenance.append(
                {
                    "provenance_id": branch.provenance_id,
                    "candidate_id": branch.candidate_id,
                    "branch_name": branch.branch_name,
                    "router": branch.router,
                    "destination": branch.destination,
                    "prefix": branch.prefix,
                    "protocol": branch.protocol,
                    "selected_peer": branch.selected_peer,
                    "scenario_set": {
                        "representation": "symbolic-guard",
                        "route_guard": branch.selection_guard,
                        "encoded_guard_assertion": branch.selection_guard_assertion,
                        "encoded_guard": branch.selection_guard_smt,
                        "failure_budget": {
                            "semantics": "at-most",
                            "k": self.scope.get("k"),
                            "assertion": branch.failure_budget_assertion,
                            "expression": branch.failure_budget_smt,
                        },
                        "failure_variables": list(branch.failure_variables),
                        "enumerated": False,
                    },
                    "seed_file": branch.seed_file,
                    "seed_sha256": branch.seed_sha256,
                    "consistency_status": "SAT",
                }
            )
            for level, items in (("field", branch.fields), ("line", branch.lines)):
                for item in items:
                    target = item.config if level == "field" else item.line_group
                    atoms = () if item.unrestricted else subspec_string_to_list(item.constraint)
                    for constraint_id, atom in zip(item.constraint_ids, atoms):
                        record = constraints.setdefault(
                            constraint_id,
                            {
                                "constraint_id": constraint_id,
                                "level": level,
                                "target": target,
                                "formula": atom,
                                "provenance_ids": [],
                                "derivations": [],
                            },
                        )
                        if branch.provenance_id not in record["provenance_ids"]:
                            record["provenance_ids"].append(branch.provenance_id)
                            record["derivations"].append(
                                {
                                    "provenance_id": branch.provenance_id,
                                    "branch_name": branch.branch_name,
                                    "projection_method": item.derivation,
                                }
                            )
        return {
            "branch_provenance": branch_provenance,
            "constraint_provenance": list(constraints.values()),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    def to_readable_text(self) -> str:
        scope = self.scope
        field_methods = _method_counts(
            field.derivation for branch in self.branches for field in branch.fields
        )
        line_methods = _method_counts(
            line.derivation for branch in self.branches for line in branch.lines
        )
        lines = [
            "=" * 80,
            "SYMBOLIC BRANCH SUBSPECIFICATION SUMMARY",
            "=" * 80,
            "",
            f"Overall status: {self.status}",
            (
                "Scope: "
                f"{scope.get('plane', '?')} | at-most-{scope.get('k', '?')} "
                "link failures"
            ),
            (
                f"Branches: {self.branch_count} | "
                f"field evaluations: {self.field_evaluations} | "
                f"line evaluations: {self.line_evaluations}"
            ),
            "Field projection: " + _format_method_counts(field_methods),
            "Line projection: " + _format_method_counts(line_methods),
            (
                "Mode: forall guarded failure states, exists device state; "
                "no failure enumeration"
            ),
            "",
            "Branch results:",
        ]
        for branch in self.branches:
            peer = branch.selected_peer or "local"
            changed = sum(
                field.constraint != f"(= {field.config} {field.original_value})"
                for field in branch.fields
            )
            lines.append(
                f"  {branch.router} via {peer:<5} | {branch.protocol:<9} | "
                f"branch {branch.branch_name:<14} | fields {len(branch.fields):>2} | "
                f"lines {len(branch.lines):>2} | non-original {changed:>2} | "
                f"guard {branch.selection_guard}"
            )

        lines.extend(
            [
                "",
                "Exact field/line formulas are stored in the per-router reports "
                "and branch_subspecs.json; this summary does not duplicate them.",
                (
                    "Scenario provenance is stored as symbolic guards in "
                    "branch_provenance; each formula atom references it through "
                    "constraint_provenance."
                ),
            ]
        )

        if self.errors:
            lines.extend(["", "Errors:"])
            lines.extend(f"  - {error}" for error in self.errors)
        elif self.status == "PASS":
            lines.extend(["", "All branch-local subspecifications were derived. ✓"])
        return "\n".join(lines) + "\n"

    def write(self, output_directory: Path) -> tuple[Path, ...]:
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "branch_subspecs.json"
        text_path = output_directory / "branch_subspecs.txt"
        self._write_atomic(json_path, self.to_json())
        self._write_atomic(text_path, self.to_readable_text())
        paths: list[Path] = [json_path, text_path]
        routers = sorted({branch.router for branch in self.branches})
        for router in routers:
            router_directory = output_directory / _file_token(router)
            router_directory.mkdir(parents=True, exist_ok=True)
            branches = tuple(
                sorted(
                    (branch for branch in self.branches if branch.router == router),
                    key=lambda branch: branch.branch_name,
                )
            )
            router_json = router_directory / "branch_subspecs.json"
            field_text = router_directory / "field_level_subspecs.txt"
            line_text = router_directory / "line_level_subspecs.txt"
            router_payload = {
                "schema_name": "tolerance-symbolic-router-subspec-report",
                "schema_version": self.schema_version,
                "router": router,
                "branches": [branch.to_dict() for branch in branches],
            }
            router_payload.update(self._provenance_indexes(branches))
            self._write_atomic(
                router_json,
                json.dumps(router_payload, indent=2, sort_keys=False) + "\n",
            )
            save_field_level_subspecs(
                field_text, self._field_subspecs_for_writer(branches)
            )
            save_line_level_subspecs(
                line_text, self._line_subspecs_for_writer(branches)
            )
            paths.extend((router_json, field_text, line_text))
        return tuple(paths)

    @staticmethod
    def _field_subspecs_for_writer(
        branches: tuple[BranchSubspec, ...]
    ) -> dict[str, set[str]]:
        return SubspecificationReport._subspecs_for_writer(branches, "field")

    @staticmethod
    def _line_subspecs_for_writer(
        branches: tuple[BranchSubspec, ...]
    ) -> dict[str, set[str]]:
        return SubspecificationReport._subspecs_for_writer(branches, "line")

    @staticmethod
    def _subspecs_for_writer(
        branches: tuple[BranchSubspec, ...], level: str
    ) -> dict[str, set[str]]:
        grouped: dict[str, set[str]] = {}
        for branch in branches:
            items = branch.fields if level == "field" else branch.lines
            for item in items:
                target = item.config if level == "field" else item.line_group
                constraint = "empty" if item.unrestricted else item.constraint
                value = (
                    constraint
                    if constraint == "empty"
                    else f"{constraint} [from {branch.branch_name}]"
                )
                grouped.setdefault(target, set()).add(value)
        return grouped

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)


class _SmtDocument(_SharedSmtDocument):
    """Stage-3 view over the shared parsed SMT seed."""

    def metadata_source(
        self, pins: ConfigPin | tuple[ConfigPin, ...]
    ) -> str:
        """Describe released pins for the shared metadata/normalization utilities."""

        targets = (pins,) if isinstance(pins, ConfigPin) else pins
        if not targets:
            raise SubspecificationError("a simplification target cannot be empty")
        assertion_indices = {pin.assertion_index for pin in targets}
        if len(assertion_indices) != len(targets):
            raise SubspecificationError("a simplification target contains duplicates")
        assertions = [
            expression
            for index, expression in enumerate(self.assertions)
            if index not in assertion_indices
        ]
        for bound in get_bounds_for_multiple_config_variables(
            [pin.name for pin in targets]
        ):
            tree = parse_smt2_sexpr(tokenize_smt2_sexpr(bound))
            if isinstance(tree, list) and len(tree) == 2 and tree[0] == "assert":
                assertions.append(tree[1])

        return self.query(
            "; Released AutoNetSubspec target equalities (metadata)",
            *(
                f"; (assert (= {pin.name} {pin.original_value}))"
                for pin in targets
            ),
            *(
                f"(assert {serialize_smt2_sexpr(expression)})"
                for expression in assertions
            ),
        )

    def quantified_projection(
        self,
        pins: tuple[ConfigPin, ...],
        destination: str,
    ) -> "_ProjectionProblem":
        """Build the paper's branch-local symbolic projection formula.

        Symbolic link states and the destination packet are universally
        quantified. Device/control-plane state is existentially quantified.
        The only free symbols are the released configuration fields.
        """

        if not pins:
            raise SubspecificationError("a projection target cannot be empty")
        target_names = frozenset(pin.name for pin in pins)
        target_indices = {pin.assertion_index for pin in pins}
        if len(target_names) != len(pins) or len(target_indices) != len(pins):
            raise SubspecificationError("a projection target contains duplicates")

        declared_configs = {
            name for name in self.declarations if name.startswith("Config_")
        }
        pinned_configs = {pin.name for pin in self.config_pins}
        missing_pins = sorted((declared_configs - target_names) - pinned_configs)
        if missing_pins:
            raise SubspecificationError(
                "non-target configuration fields are not concretely pinned: "
                + ", ".join(missing_pins)
            )

        conditions = self.branch_conditions()
        (
            released_snapshot_indices,
            released_snapshot_names,
            dependent_route_symbols,
        ) = self._target_dependent_route_snapshots(target_names)
        antecedent: list[object] = [
            conditions.selection_guard,
            conditions.failure_budget,
        ]
        body: list[object] = []
        for index, (expression, name) in enumerate(
            zip(self.assertions, self.assertion_names)
        ):
            if index in target_indices or index in released_snapshot_indices:
                continue
            if name is not None and name.endswith("_selection_guard"):
                continue
            elif name is not None and "_at_most_" in name:
                continue
            else:
                body.append(expression)

        destination_symbol = _destination_symbol(self.declarations)
        if destination_symbol is not None:
            antecedent.append(
                _destination_prefix_expression(
                    destination_symbol,
                    self.declarations[destination_symbol],
                    destination,
                )
            )

        bound_expressions: list[object] = []
        for bound in get_bounds_for_multiple_config_variables(sorted(target_names)):
            tree = parse_smt2_sexpr(tokenize_smt2_sexpr(bound))
            if not isinstance(tree, list) or len(tree) != 2 or tree[0] != "assert":
                raise SubspecificationError(f"malformed configuration bound: {bound}")
            bound_expressions.append(tree[1])
            body.append(tree[1])

        concrete_values = {
            pin.name: parse_smt2_sexpr(tokenize_smt2_sexpr(pin.original_value))
            for pin in self.config_pins
            if pin.name not in target_names
        }
        body = [
            _substitute_symbols(expression, concrete_values)
            for expression in body
        ]
        universal_names = list(conditions.failure_variables)
        if destination_symbol is not None:
            universal_names.append(destination_symbol)
        universal_set = set(universal_names)
        body_symbols = _collect_declared_symbols(
            _and_expression(body), self.declarations
        )
        existential_names = sorted(body_symbols - target_names - universal_set)

        consequent = _and_expression(body)
        if existential_names:
            consequent = [
                "exists",
                self.quantifier_bindings(existential_names),
                consequent,
            ]
        scenario_expression: object = [
            "=>",
            _and_expression(antecedent[:2]),
            consequent,
        ]
        failure_variables = list(conditions.failure_variables)
        if failure_variables:
            scenario_expression = [
                "forall",
                self.quantifier_bindings(failure_variables),
                scenario_expression,
            ]
        if destination_symbol is not None:
            projection_expression: object = [
                "forall",
                self.quantifier_bindings([destination_symbol]),
                ["=>", antecedent[-1], scenario_expression],
            ]
        else:
            projection_expression = scenario_expression

        domain_candidate = _and_expression(
            _substitute_symbols(expression, concrete_values)
            for expression in bound_expressions
        )
        return _ProjectionProblem(
            expression=projection_expression,
            scenario_expression=scenario_expression,
            domain_candidate=domain_candidate,
            target_names=target_names,
            universal_names=tuple(universal_names),
            existential_names=tuple(existential_names),
            destination_quantified=destination_symbol is not None,
            destination_symbol=destination_symbol,
            destination_domain=(antecedent[-1] if destination_symbol is not None else None),
            released_route_attribute_bindings=released_snapshot_names,
            dependent_route_attribute_symbols=dependent_route_symbols,
        )

    def _target_dependent_route_snapshots(
        self, target_names: frozenset[str]
    ) -> tuple[frozenset[int], tuple[str, ...], tuple[str, ...]]:
        """Return concrete route snapshots that must be recomputed for a target.

        Stage 2 intentionally compares symbolic-RIB route attributes with their
        concrete values. Stage 3 keeps that checked seed, but releases any route
        attribute observation that is data-dependent on the target Config field.
        Dependencies come only from the original unnamed device equations;
        consistency bindings are observations rather than definitions. Route
        identity constraints such as ``permitted`` and control forwarding stay.
        """

        value_targets = frozenset(
            name for name in target_names if _is_route_value_target(name)
        )
        if not value_targets:
            return frozenset(), (), ()

        dependencies = _device_value_dependencies(
            self.assertions, self.assertion_names, self.declarations
        )
        dependent = set(value_targets)
        pending = list(value_targets)
        while pending:
            source = pending.pop()
            for destination_symbol in dependencies.get(source, ()):
                if destination_symbol not in dependent:
                    dependent.add(destination_symbol)
                    pending.append(destination_symbol)

        released_indices: set[int] = set()
        released_names: list[str] = []
        released_symbols: set[str] = set()
        for index, (expression, name) in enumerate(
            zip(self.assertions, self.assertion_names)
        ):
            if name is None or not _is_route_attribute_snapshot_name(name):
                continue
            affected = _literal_bound_symbols(
                expression, self.declarations
            ).intersection(dependent)
            if not affected:
                continue
            released_indices.add(index)
            released_names.append(name)
            released_symbols.update(affected)
        return (
            frozenset(released_indices),
            tuple(sorted(released_names)),
            tuple(sorted(released_symbols)),
        )

    def branch_conditions(self) -> "_BranchConditions":
        selection_guards = [
            (expression, name)
            for expression, name in zip(self.assertions, self.assertion_names)
            if name is not None and name.endswith("_selection_guard")
        ]
        failure_budgets = [
            (expression, name)
            for expression, name in zip(self.assertions, self.assertion_names)
            if name is not None and "_at_most_" in name
        ]
        if len(selection_guards) != 1 or len(failure_budgets) != 1:
            raise SubspecificationError(
                "symbolic projection requires exactly one selection guard and "
                "one at-most-k failure budget"
            )
        failure_variables = tuple(
            sorted(
                name
                for name in self.declarations
                if _is_symbolic_link_symbol(name)
            )
        )
        return _BranchConditions(
            selection_guard=selection_guards[0][0],
            selection_guard_name=str(selection_guards[0][1]),
            failure_budget=failure_budgets[0][0],
            failure_budget_name=str(failure_budgets[0][1]),
            failure_variables=failure_variables,
        )

@dataclass(frozen=True)
class _ProjectionProblem:
    expression: object
    scenario_expression: object
    domain_candidate: object
    target_names: frozenset[str]
    universal_names: tuple[str, ...]
    existential_names: tuple[str, ...]
    destination_quantified: bool
    destination_symbol: Optional[str]
    destination_domain: Optional[object]
    released_route_attribute_bindings: tuple[str, ...]
    dependent_route_attribute_symbols: tuple[str, ...]


@dataclass(frozen=True)
class _BranchConditions:
    selection_guard: object
    selection_guard_name: str
    failure_budget: object
    failure_budget_name: str
    failure_variables: tuple[str, ...]


@dataclass(frozen=True)
class _BranchComputation:
    branch: BranchSubspec
    field_evaluations: int
    constrained_field_evaluations: int
    line_evaluations: int
    constrained_line_evaluations: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _ProjectedTarget:
    name: str
    pins: tuple[ConfigPin, ...]
    constraint: str
    derivation: str
    solver_seconds: float
    projection: dict[str, Any]

    @property
    def unrestricted(self) -> bool:
        return self.constraint == "true"


@dataclass(frozen=True)
class _TargetBatch:
    targets: tuple[_ProjectedTarget, ...]
    evaluations: int
    constrained_evaluations: int
    error: Optional[str] = None


class SymbolicSubspecifier:
    """Fail-closed, non-enumerating symbolic branch subspecifier."""

    _CONSISTENCY_DIRECTORY = "2_consistency_check"
    _OUTPUT_DIRECTORY = "3_branch_subspecs"

    def __init__(
        self,
        work_directory: Path | str,
        *,
        z3_path: Optional[Path | str] = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.work_directory = Path(work_directory).resolve()
        self.consistency_directory = (
            self.work_directory / self._CONSISTENCY_DIRECTORY
        )
        self.report_path = self.consistency_directory / "consistency_report.json"
        self.solver = SmtSolver(
            z3_path=z3_path, timeout_seconds=timeout_seconds
        )
        self.target_dst_ip = load_target_dst_ip(self.work_directory)
        self.last_worker_count = 1

    def run(
        self,
        *,
        output_directory: Optional[Path | str] = None,
        max_workers: Optional[int] = None,
    ) -> SubspecificationReport:
        consistency = self._load_and_validate_consistency_report()
        source_branches = consistency["branches"]
        self.last_worker_count = self._worker_count(max_workers, len(source_branches))
        if self.last_worker_count == 1:
            computations = [
                self._project_branch(consistency, branch)
                for branch in source_branches
            ]
        else:
            with ThreadPoolExecutor(
                max_workers=self.last_worker_count,
                thread_name_prefix="symbolic-branch",
            ) as executor:
                futures = [
                    executor.submit(self._project_branch, consistency, branch)
                    for branch in source_branches
                ]
                # Resolve in source-report order so output remains deterministic.
                computations = [future.result() for future in futures]

        branches = [item.branch for item in computations]
        errors = [error for item in computations for error in item.errors]
        field_evaluations = sum(item.field_evaluations for item in computations)
        constrained_field_evaluations = sum(
            item.constrained_field_evaluations for item in computations
        )
        line_evaluations = sum(item.line_evaluations for item in computations)
        constrained_line_evaluations = sum(
            item.constrained_line_evaluations for item in computations
        )

        result = SubspecificationReport(
            status="PASS" if not errors else "FAIL",
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_consistency_report=str(self.report_path),
            scope=dict(consistency["scope"]),
            branch_count=len(branches),
            field_evaluations=field_evaluations,
            constrained_field_evaluations=constrained_field_evaluations,
            line_evaluations=line_evaluations,
            constrained_line_evaluations=constrained_line_evaluations,
            branches=tuple(branches),
            errors=tuple(errors),
        )
        output = (
            Path(output_directory).resolve()
            if output_directory is not None
            else self.work_directory / self._OUTPUT_DIRECTORY
        )
        result.write(output)
        return result

    @staticmethod
    def _worker_count(requested: Optional[int], branch_count: int) -> int:
        if requested is not None and requested <= 0:
            raise ValueError("max_workers must be positive")
        if branch_count <= 1:
            return 1
        available = requested if requested is not None else (os.cpu_count() or 1)
        return max(1, min(available, branch_count))

    def _project_branch(
        self,
        consistency: dict[str, Any],
        branch: dict[str, Any],
    ) -> _BranchComputation:
        """Project one branch without writing shared output state."""

        seed_path = self._resolve_seed_path(branch)
        seed_bytes = seed_path.read_bytes()
        document = _SmtDocument.parse(seed_bytes.decode("utf-8"))
        conditions = document.branch_conditions()
        branch_token = self._short_id(branch["candidate_id"])
        expected_guard_name = f"branch_{branch_token}_selection_guard"
        expected_budget_name = (
            f"branch_{branch_token}_at_most_{consistency['scope']['k']}_failures"
        )
        if conditions.selection_guard_name != expected_guard_name:
            raise SubspecificationError(
                f"seed {seed_path} guard assertion belongs to "
                f"{conditions.selection_guard_name}, expected {expected_guard_name}"
            )
        if conditions.failure_budget_name != expected_budget_name:
            raise SubspecificationError(
                f"seed {seed_path} failure assertion belongs to "
                f"{conditions.failure_budget_name}, expected {expected_budget_name}"
            )

        field_batch = self._project_targets(
            document, branch, branch_token, level="field"
        )
        line_batch = (
            _TargetBatch((), 0, 0)
            if field_batch.error is not None
            else self._project_targets(document, branch, branch_token, level="line")
        )
        field_results = tuple(
            BranchFieldSubspec(
                config=item.name,
                released_configs=tuple(pin.name for pin in item.pins),
                sort=item.pins[0].sort,
                original_value=item.pins[0].original_value,
                constraint=item.constraint,
                unrestricted=item.unrestricted,
                derivation=item.derivation,
                solver_seconds=item.solver_seconds,
                constraint_ids=_constraint_ids("field", item.name, item.constraint),
                projection=item.projection,
            )
            for item in field_batch.targets
        )
        line_results = tuple(
            BranchLineSubspec(
                line_group=item.name,
                configs=tuple(pin.name for pin in item.pins),
                constraint=item.constraint,
                unrestricted=item.unrestricted,
                derivation=item.derivation,
                solver_seconds=item.solver_seconds,
                constraint_ids=_constraint_ids("line", item.name, item.constraint),
                projection=item.projection,
            )
            for item in line_batch.targets
        )

        result = BranchSubspec(
            candidate_id=branch["candidate_id"],
            router=branch["router"],
            destination=branch["destination"],
            prefix=branch["prefix"],
            protocol=branch["protocol"],
            selected_peer=branch.get("selected_peer"),
            selection_guard=branch["selection_guard"],
            selection_guard_assertion=conditions.selection_guard_name,
            selection_guard_smt=serialize_smt2_sexpr(conditions.selection_guard),
            failure_budget_assertion=conditions.failure_budget_name,
            failure_budget_smt=serialize_smt2_sexpr(conditions.failure_budget),
            failure_variables=conditions.failure_variables,
            seed_file=branch["seed_file"],
            seed_sha256=hashlib.sha256(seed_bytes).hexdigest(),
            fields=field_results,
            lines=line_results,
        )
        return _BranchComputation(
            branch=result,
            field_evaluations=field_batch.evaluations,
            constrained_field_evaluations=field_batch.constrained_evaluations,
            line_evaluations=line_batch.evaluations,
            constrained_line_evaluations=line_batch.constrained_evaluations,
            errors=tuple(
                error
                for error in (field_batch.error, line_batch.error)
                if error is not None
            ),
        )

    def _project_targets(
        self,
        document: _SmtDocument,
        branch: dict[str, Any],
        branch_token: str,
        *,
        level: str,
    ) -> _TargetBatch:
        if level not in {"field", "line"}:
            raise ValueError(f"unsupported subspecification level: {level}")
        targets = (
            _field_targets(document.config_pins)
            if level == "field"
            else _group_config_pins(document.config_pins)
        )
        results: list[_ProjectedTarget] = []
        evaluations = 0
        constrained_evaluations = 0
        for identifier, pins in targets:
            evaluations += 1
            try:
                constraint, derivation, solver_seconds, projection = self._project(
                    document,
                    pins,
                    device=branch["router"],
                    destination=branch["destination"],
                    identifier=identifier,
                    level=level,
                    is_pair=level == "field" and len(pins) == 2,
                )
            except (
                OSError,
                SubspecificationError,
                subprocess.SubprocessError,
            ) as error:
                return _TargetBatch(
                    targets=tuple(results),
                    evaluations=evaluations,
                    constrained_evaluations=constrained_evaluations,
                    error=(
                        f"{branch['router']} {branch_token} {identifier}: {error}"
                    ),
                )
            results.append(
                _ProjectedTarget(
                    name=identifier,
                    pins=pins,
                    constraint=constraint,
                    derivation=derivation,
                    solver_seconds=solver_seconds,
                    projection=projection,
                )
            )
            constrained_evaluations += constraint != "true"
        return _TargetBatch(
            targets=tuple(results),
            evaluations=evaluations,
            constrained_evaluations=constrained_evaluations,
        )

    def _load_and_validate_consistency_report(self) -> dict[str, Any]:
        try:
            report = json.loads(self.report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SubspecificationError(
                f"cannot load consistency gate {self.report_path}: {error}"
            ) from error
        if report.get("schema_name") != "tolerance-symbolic-consistency-report":
            raise SubspecificationError("unsupported consistency report schema")
        scope = report.get("scope")
        if not isinstance(scope, dict) or scope.get("mode") != "global":
            raise SubspecificationError(
                "stage 3 requires an unfiltered global consistency check"
            )
        if scope.get("plane") != "MAIN":
            raise SubspecificationError("stage 3 requires MAIN symbolic branches")
        k = scope.get("k")
        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            raise SubspecificationError(
                "consistency report has an invalid at-most-k failure budget"
            )
        if report.get("status") != "PASS":
            raise SubspecificationError("consistency gate did not PASS")
        eligible = report.get("eligible_branches")
        branches = report.get("branches")
        if (
            not isinstance(eligible, int)
            or eligible <= 0
            or report.get("checked_branches") != eligible
            or report.get("sat_branches") != eligible
            or report.get("unsat_branches") != 0
            or report.get("unknown_branches") != 0
            or report.get("error_branches") != 0
            or not isinstance(branches, list)
            or len(branches) != eligible
            or any(item.get("status") != "SAT" for item in branches)
        ):
            raise SubspecificationError(
                "consistency report does not prove every eligible branch SAT"
            )
        candidate_ids = [item.get("candidate_id") for item in branches]
        if any(not isinstance(item, str) for item in candidate_ids):
            raise SubspecificationError("consistency report has a missing candidate id")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise SubspecificationError(
                "consistency report has duplicate candidate ids"
            )
        return report

    def _resolve_seed_path(self, branch: dict[str, Any]) -> Path:
        relative = branch.get("seed_file")
        if not isinstance(relative, str) or not relative:
            raise SubspecificationError(
                f"branch {branch.get('candidate_id')} has no seed file"
            )
        candidate = (self.consistency_directory / relative).resolve()
        try:
            candidate.relative_to(self.consistency_directory.resolve())
        except ValueError as error:
            raise SubspecificationError(
                f"seed path escapes consistency directory: {relative}"
            ) from error
        if not candidate.is_file():
            raise SubspecificationError(f"missing branch seed: {candidate}")
        return candidate

    def _project(
        self,
        document: _SmtDocument,
        pins: tuple[ConfigPin, ...],
        *,
        device: str,
        destination: str,
        identifier: str,
        level: str,
        is_pair: bool,
    ) -> tuple[str, str, float, dict[str, Any]]:
        if level not in {"field", "line"}:
            raise ValueError(f"unsupported subspecification level: {level}")
        started = time.monotonic()
        metadata_source = document.metadata_source(pins)
        problem = document.quantified_projection(pins, destination)

        def finish(candidate: str, method: str) -> tuple[str, str, float, dict[str, Any]]:
            constraint = self._normalize_projected_constraint(
                document,
                metadata_source,
                candidate,
                problem,
                device=device,
                identifier=identifier,
                level=level,
                is_pair=is_pair,
            )
            return (
                constraint,
                method,
                time.monotonic() - started,
                self._projection_audit(problem, method),
            )

        domain_candidate = self.solver.simplify(
            document, problem.domain_candidate
        )
        domain_candidate = _compact_integer_interval_unions(
            domain_candidate, pins, document.declarations, document.config_pins
        )
        if self._is_exact_projection(document, problem, domain_candidate):
            return finish(domain_candidate, "symbolic-domain-equivalent")

        try:
            staged = self._staged_symbolic_projection(
                document, pins, problem
            )
        except (OSError, SubspecificationError, subprocess.SubprocessError):
            staged = None
        if staged is not None:
            staged = self.solver.simplify(
                document,
                parse_smt2_sexpr(
                    tokenize_smt2_sexpr(
                        subspec_string_to_smt2_and(staged) or "true"
                    )
                ),
            )
            staged = _compact_integer_interval_unions(
                staged, pins, document.declarations, document.config_pins
            )
            if self._is_exact_projection(document, problem, staged):
                return finish(staged, "symbolic-staged-projection")

        projected = self.solver.project(
            document, pins, problem.expression, "symbolic projection"
        )
        residual = _residual_declared_symbols(
            projected, document.declarations, problem.target_names
        )
        if residual:
            raise SubspecificationError(
                "symbolic projection retained non-target symbols: "
                + ", ".join(residual)
            )
        projected = _compact_integer_interval_unions(
            projected, pins, document.declarations, document.config_pins
        )
        return finish(projected, "symbolic-quantified-projection")

    def _is_exact_projection(
        self,
        document: _SmtDocument,
        problem: _ProjectionProblem,
        candidate: str,
    ) -> bool:
        residual = _residual_declared_symbols(
            candidate, document.declarations, problem.target_names
        )
        return not residual and self.solver.equivalent(
            document, problem.expression, candidate
        )[0]

    def _staged_symbolic_projection(
        self,
        document: _SmtDocument,
        pins: tuple[ConfigPin, ...],
        problem: _ProjectionProblem,
    ) -> str:
        """Eliminate failure/device state before eliminating destination state."""

        staged = self.solver.project(
            document,
            pins,
            problem.scenario_expression,
            "staged symbolic state projection",
        )
        staged = self.solver.remove_redundant_atoms(document, staged)
        allowed = set(problem.target_names)
        if problem.destination_symbol is not None:
            allowed.add(problem.destination_symbol)
        residual = _residual_declared_symbols(
            staged, document.declarations, frozenset(allowed)
        )
        if residual:
            raise SubspecificationError(
                "staged symbolic projection retained internal symbols: "
                + ", ".join(residual)
            )
        if (
            problem.destination_symbol is not None
            and problem.destination_symbol
            in _collect_constraint_symbols(staged, document.declarations)
        ):
            return self._lift_destination_projection(
                document, pins, staged, problem
            )
        return staged

    def _lift_destination_projection(
        self,
        document: _SmtDocument,
        pins: tuple[ConfigPin, ...],
        staged: str,
        problem: _ProjectionProblem,
    ) -> str:
        symbol = problem.destination_symbol
        domain = problem.destination_domain
        if symbol is None or domain is None:
            raise SubspecificationError(
                "staged destination projection requires a destination domain"
            )
        rewritten = self._rewrite_destination_projection(
            document, pins, staged, problem
        )
        if rewritten is not None:
            return rewritten
        staged_expression = parse_smt2_sexpr(
            tokenize_smt2_sexpr(subspec_string_to_smt2_and(staged) or "true")
        )
        expression = [
            "forall",
            document.quantifier_bindings([symbol]),
            ["=>", domain, staged_expression],
        ]
        return self.solver.project(
            document, pins, expression, "destination-context projection"
        )

    def _rewrite_destination_projection(
        self,
        document: _SmtDocument,
        pins: tuple[ConfigPin, ...],
        staged: str,
        problem: _ProjectionProblem,
    ) -> Optional[str]:
        """Remove a destination context and rewrite prefix matching exactly."""

        destination_symbol = problem.destination_symbol
        destination_domain = problem.destination_domain
        if destination_symbol is None or destination_domain is None:
            return None
        target_names = frozenset(pin.name for pin in pins)
        rewritten: list[object] = []
        for atom in subspec_string_to_list(staged):
            expression = parse_smt2_sexpr(tokenize_smt2_sexpr(atom))
            symbols = _collect_declared_symbols(expression, document.declarations)
            if destination_symbol not in symbols:
                rewritten.append(expression)
                continue
            if not symbols.intersection(target_names):
                if not self.solver.entails(
                    document, destination_domain, expression
                ):
                    return None
                continue
            containment = _prefix_containment_expression(
                expression,
                destination_symbol,
                destination_domain,
                target_names,
                document.declarations,
            )
            if containment is None:
                return None
            rewritten.extend(containment)
        return self.solver.simplify(document, _and_expression(rewritten))

    def _normalize_projected_constraint(
        self,
        document: _SmtDocument,
        metadata_query: str,
        constraint: str,
        problem: _ProjectionProblem,
        *,
        device: str,
        identifier: str,
        level: str,
        is_pair: bool,
    ) -> str:
        readable_interval = self._proved_readable_value_interval(
            document, problem
        )
        if readable_interval is not None:
            return readable_interval
        if constraint == "true":
            return constraint
        normalized: Optional[str]
        try:
            normalized = self._normalize_with_auto_netsubspec(
                metadata_query,
                constraint,
                device=device,
                identifier=identifier,
                level=level,
                is_pair=is_pair,
            )
            normalized = _compact_integer_interval_unions(
                normalized,
                tuple(
                    pin
                    for pin in document.config_pins
                    if pin.name in problem.target_names
                ),
                document.declarations,
                document.config_pins,
            )
        except (OSError, SubspecificationError, subprocess.SubprocessError):
            normalized = None
        if normalized is not None and self._is_exact_projection(
            document, problem, normalized
        ):
            return normalized
        if self._is_exact_projection(document, problem, constraint):
            return constraint
        raise SubspecificationError(
            "projected constraint failed equivalence validation"
        )

    def _proved_readable_value_interval(
        self,
        document: _SmtDocument,
        problem: _ProjectionProblem,
    ) -> Optional[str]:
        """Prefer a meaningful one-field interval after proving equivalence.

        Quantifier elimination may spell an integer boundary as ``x >= 101``
        or as a larger Boolean formula. For route-value setters, candidate
        intervals are built only from legal-domain and original competing
        values, and are accepted only by the same UNSAT equivalence proof used
        for every other projection result.
        """

        if len(problem.target_names) != 1:
            return None
        target_name = next(iter(problem.target_names))
        if _configuration_value_operation(target_name) is None:
            return None
        target_pin = next(
            (pin for pin in document.config_pins if pin.name == target_name),
            None,
        )
        if target_pin is None or target_pin.sort != "Int":
            return None

        bound_expressions: list[object] = []
        for bound in get_bounds_for_multiple_config_variables([target_name]):
            tree = parse_smt2_sexpr(tokenize_smt2_sexpr(bound))
            if isinstance(tree, list) and len(tree) == 2 and tree[0] == "assert":
                bound_expressions.append(tree[1])
        domain = _integer_interval(
            _and_expression(bound_expressions), target_name
        )
        if domain is None:
            return None
        domain_lower, domain_upper = domain
        thresholds = _strict_lower_thresholds(target_pin, document.config_pins)

        lower_candidates = {domain_lower}
        upper_candidates = {domain_upper}
        for value in thresholds:
            if domain_lower is None or value >= domain_lower:
                lower_candidates.add(value)
            if domain_lower is None or value + 1 >= domain_lower:
                lower_candidates.add(value + 1)
            if domain_upper is None or value <= domain_upper:
                upper_candidates.add(value)
            if domain_upper is None or value - 1 <= domain_upper:
                upper_candidates.add(value - 1)

        def lower_key(value: Optional[int]) -> float:
            return float("-inf") if value is None else value

        def upper_key(value: Optional[int]) -> float:
            return float("inf") if value is None else value

        for lower in sorted(lower_candidates, key=lower_key):
            for upper in sorted(upper_candidates, key=upper_key, reverse=True):
                if lower is not None and upper is not None and lower > upper:
                    continue
                strict_lower = (
                    lower - 1
                    if lower is not None and lower - 1 in thresholds
                    else None
                )
                strict_upper = (
                    upper + 1
                    if upper is not None and upper + 1 in thresholds
                    else None
                )
                expression = _interval_expression(
                    target_name, lower, upper, strict_lower, strict_upper
                )
                candidate = _serialize_subspec_expression(expression)
                equivalent, _ = self.solver.equivalent(
                    document, problem.expression, candidate
                )
                if equivalent:
                    return candidate
        return None

    @staticmethod
    def _projection_audit(
        problem: _ProjectionProblem, method: str
    ) -> dict[str, Any]:
        return {
            "method": method,
            "semantics": "forall-branch-scenarios-exists-device-state",
            "universal_variables": list(problem.universal_names),
            "existential_variable_count": len(problem.existential_names),
            "destination_quantified": problem.destination_quantified,
            "failure_enumeration": False,
            "equivalence_check": "UNSAT",
            "residual_symbols": [],
            "released_route_attribute_bindings": list(
                problem.released_route_attribute_bindings
            ),
            "dependent_route_attribute_symbols": list(
                problem.dependent_route_attribute_symbols
            ),
        }

    def _normalize_with_auto_netsubspec(
        self,
        query: str,
        constraint: str,
        *,
        device: str,
        identifier: str,
        level: str,
        is_pair: bool,
    ) -> str:
        """Run the existing metadata-driven AutoNetSubspec normalizer."""

        with tempfile.TemporaryDirectory(prefix="symbolic_subspec_") as temporary:
            directory = Path(temporary)
            synthesis = directory / "compute_subspec.smt2"
            synthesis.write_text(query, encoding="utf-8")
            save_synthesis_metadata(
                device,
                identifier,
                str(synthesis),
                directory,
                level,
            )
            metadata = find_metadata_file(identifier, device, level, directory)
            if metadata is None:
                raise SubspecificationError(
                    f"AutoNetSubspec did not produce {level} metadata for {identifier}"
                )
            normalized = normalize_subspec(
                constraint,
                metadata,
                identifier,
                is_field_level=level == "field",
                is_pair=is_pair,
                target_dst_ip=self.target_dst_ip,
                max_iterations=3,
                verbose=False,
                temp_dir=directory,
            )
        if not normalized.strip():
            raise SubspecificationError(
                f"AutoNetSubspec normalization returned an empty result for {identifier}"
            )
        return normalized.strip()

    @staticmethod
    def _short_id(candidate_id: str) -> str:
        return candidate_id.removeprefix("candidate-v1-")[:12]


def _file_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return token or "unknown"


def _line_group_name(config_name: str) -> Optional[str]:
    """Return AutoNetSubspec's configuration-line prefix for one field."""

    match = re.match(
        r"^(?P<prefix>Config_.+__Line\d+(?:__[Ll]ine\d+)?)(?:__.+)?$",
        config_name,
    )
    return match.group("prefix") if match is not None else None


def _group_config_pins(
    pins: tuple[ConfigPin, ...],
) -> tuple[tuple[str, tuple[ConfigPin, ...]], ...]:
    grouped: dict[str, list[ConfigPin]] = {}
    for pin in pins:
        line_group = _line_group_name(pin.name)
        if line_group is not None:
            grouped.setdefault(line_group, []).append(pin)
    return tuple(
        (line_group, tuple(sorted(values, key=lambda item: item.name)))
        for line_group, values in sorted(grouped.items())
    )


def _field_targets(
    pins: tuple[ConfigPin, ...],
) -> tuple[tuple[str, tuple[ConfigPin, ...]], ...]:
    """Match AutoNetSubspec's field targets, including joint IP/mask pairs."""

    by_name = {pin.name: pin for pin in pins}
    consumed: set[str] = set()
    targets: list[tuple[str, tuple[ConfigPin, ...]]] = []
    for pin in pins:
        if pin.name in consumed:
            continue
        if pin.name.endswith("__ip"):
            mask = by_name.get(pin.name[:-4] + "__mask")
            if mask is not None and is_ip_mask_pair(pin.name, mask.name):
                targets.append((pin.name, (pin, mask)))
                consumed.update((pin.name, mask.name))
                continue
        if pin.name.endswith("__mask"):
            ip = by_name.get(pin.name[:-6] + "__ip")
            if ip is not None and is_ip_mask_pair(ip.name, pin.name):
                targets.append((ip.name, (ip, pin)))
                consumed.update((ip.name, pin.name))
                continue
        targets.append((pin.name, (pin,)))
        consumed.add(pin.name)
    return tuple(sorted(targets, key=lambda item: item[0]))


def _is_symbolic_link_symbol(name: str) -> bool:
    plain = name.strip("|")
    return plain.startswith("LINK-UP-") or plain.startswith("SR-LINK-")


def _destination_symbol(declarations: dict[str, str]) -> Optional[str]:
    candidates = sorted(
        name for name in declarations if name.strip("|").endswith("_dst-ip")
    )
    if len(candidates) > 1:
        raise SubspecificationError(
            "multiple destination packet symbols are unsupported: "
            + ", ".join(candidates)
        )
    return candidates[0] if candidates else None


def _destination_prefix_expression(
    symbol: str, sort: str, destination: str
) -> object:
    match = re.fullmatch(r"\(_ BitVec (\d+)\)", sort)
    if match is None:
        raise SubspecificationError(
            f"destination symbol {symbol} has non-bitvector sort {sort}"
        )
    width = int(match.group(1))
    try:
        network = ipaddress.ip_network(destination, strict=False)
    except ValueError as error:
        raise SubspecificationError(
            f"invalid symbolic destination prefix {destination!r}"
        ) from error
    expected_width = 32 if network.version == 4 else 128
    if width != expected_width:
        raise SubspecificationError(
            f"destination prefix {destination} does not match {width}-bit {symbol}"
        )
    mask = ["_", f"bv{int(network.netmask)}", str(width)]
    address = ["_", f"bv{int(network.network_address)}", str(width)]
    return ["=", ["bvand", symbol, mask], address]


def _prefix_containment_expression(
    expression: object,
    destination_symbol: str,
    destination_domain: object,
    target_names: frozenset[str],
    declarations: dict[str, str],
) -> Optional[tuple[object, object]]:
    ip_names = sorted(name for name in target_names if name.endswith("__ip"))
    mask_names = sorted(name for name in target_names if name.endswith("__mask"))
    if len(ip_names) != 1 or len(mask_names) != 1:
        return None
    ip_name, mask_name = ip_names[0], mask_names[0]
    expected_sides = (
        ["bvand", destination_symbol, mask_name],
        ["bvand", ip_name, mask_name],
    )
    canonical_left = _canonical_bitwise_and(expression[1]) if (
        isinstance(expression, list) and len(expression) == 3
    ) else None
    canonical_right = _canonical_bitwise_and(expression[2]) if (
        isinstance(expression, list) and len(expression) == 3
    ) else None
    if (
        not isinstance(expression, list)
        or len(expression) != 3
        or expression[0] != "="
        or not (
            (canonical_left == expected_sides[0] and canonical_right == expected_sides[1])
            or (canonical_right == expected_sides[0] and canonical_left == expected_sides[1])
        )
    ):
        return None
    if (
        not isinstance(destination_domain, list)
        or len(destination_domain) != 3
        or destination_domain[0] != "="
        or not isinstance(destination_domain[1], list)
        or destination_domain[1][:2] != ["bvand", destination_symbol]
    ):
        return None
    network_mask = destination_domain[1][2]
    network_address = destination_domain[2]
    width_match = re.fullmatch(r"\(_ BitVec (\d+)\)", declarations[mask_name])
    mask_literal = _bitvector_literal(network_mask)
    if width_match is None or mask_literal is None:
        return None
    width = int(width_match.group(1))
    if mask_literal[1] != width:
        return None
    all_bits = (1 << width) - 1
    host_mask = ["_", f"bv{all_bits ^ mask_literal[0]}", str(width)]
    zero = ["_", "bv0", str(width)]
    return (
        ["=", ["bvand", mask_name, host_mask], zero],
        [
            "=",
            ["bvand", network_address, mask_name],
            ["bvand", ip_name, mask_name],
        ],
    )


def _canonical_bitwise_and(expression: object) -> object:
    """Canonicalize the exact De Morgan form emitted by Minesweeper."""

    if (
        isinstance(expression, list)
        and len(expression) == 2
        and expression[0] == "bvnot"
        and isinstance(expression[1], list)
        and len(expression[1]) == 3
        and expression[1][0] == "bvor"
    ):
        left, right = expression[1][1:]
        if (
            isinstance(left, list)
            and len(left) == 2
            and left[0] == "bvnot"
            and isinstance(right, list)
            and len(right) == 2
            and right[0] == "bvnot"
        ):
            return ["bvand", left[1], right[1]]
    return expression


def _bitvector_literal(expression: object) -> Optional[tuple[int, int]]:
    if (
        isinstance(expression, list)
        and len(expression) == 3
        and expression[0] == "_"
        and isinstance(expression[1], str)
        and expression[1].startswith("bv")
        and expression[1][2:].isdigit()
        and isinstance(expression[2], str)
        and expression[2].isdigit()
    ):
        return int(expression[1][2:]), int(expression[2])
    return None


def _device_value_dependencies(
    assertions: tuple[object, ...],
    assertion_names: tuple[Optional[str], ...],
    declarations: dict[str, str],
) -> dict[str, set[str]]:
    """Build directed value-flow edges from the original device equations."""

    dependencies: dict[str, set[str]] = {}

    def add_edges(expression: object) -> None:
        if not isinstance(expression, list) or not expression:
            return
        if len(expression) == 3 and expression[0] == "=":
            left, right = expression[1], expression[2]
            left_symbol = _single_declared_symbol(left, declarations)
            right_symbol = _single_declared_symbol(right, declarations)
            left_sources = _collect_declared_symbols(left, declarations)
            right_sources = _collect_declared_symbols(right, declarations)
            if left_symbol is not None:
                for source in right_sources - {left_symbol}:
                    dependencies.setdefault(source, set()).add(left_symbol)
            if right_symbol is not None:
                for source in left_sources - {right_symbol}:
                    dependencies.setdefault(source, set()).add(right_symbol)
        for child in expression[1:]:
            add_edges(child)

    for expression, name in zip(assertions, assertion_names):
        if name is None:
            add_edges(expression)
    return dependencies


def _single_declared_symbol(
    expression: object, declarations: dict[str, str]
) -> Optional[str]:
    if not isinstance(expression, str):
        return None
    if expression in declarations:
        return expression
    quoted = f"|{expression}|"
    return quoted if quoted in declarations else None


def _is_route_attribute_snapshot_name(name: str) -> bool:
    """Recognize value observations added by RouteBinder, not branch identity."""

    if name.endswith("_permitted"):
        return False
    return any(
        marker in name
        for marker in (
            "_current_best_",
            "_selected_import_",
            "_selected_peer_",
            "_remaining_peer_",
        )
    )


def _literal_bound_symbols(
    expression: object, declarations: dict[str, str]
) -> set[str]:
    """Collect symbols fixed to literals inside a named route observation."""

    if not isinstance(expression, list) or not expression:
        return set()
    result: set[str] = set()
    if len(expression) == 3 and expression[0] == "=":
        left, right = expression[1], expression[2]
        left_symbol = _single_declared_symbol(left, declarations)
        right_symbol = _single_declared_symbol(right, declarations)
        if left_symbol is not None and not _collect_declared_symbols(
            right, declarations
        ):
            result.add(left_symbol)
        if right_symbol is not None and not _collect_declared_symbols(
            left, declarations
        ):
            result.add(right_symbol)
    for child in expression[1:]:
        result.update(_literal_bound_symbols(child, declarations))
    return result


def _collect_constraint_symbols(
    constraint: str, declarations: dict[str, str]
) -> set[str]:
    expression = parse_smt2_sexpr(
        tokenize_smt2_sexpr(subspec_string_to_smt2_and(constraint) or "true")
    )
    return _collect_declared_symbols(expression, declarations)


def _method_counts(methods: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for method in methods:
        counts[method] = counts.get(method, 0) + 1
    return counts


def _format_method_counts(counts: dict[str, int]) -> str:
    labels = {
        "symbolic-domain-equivalent": "domain-equivalent",
        "symbolic-staged-projection": "staged-symbolic",
        "symbolic-quantified-projection": "quantified",
    }
    return " | ".join(
        f"{labels.get(method, method)} {count}"
        for method, count in sorted(counts.items())
    ) or "none"


def _compact_integer_interval_unions(
    constraint: str,
    pins: tuple[ConfigPin, ...],
    declarations: dict[str, str],
    all_pins: tuple[ConfigPin, ...],
) -> str:
    """Merge adjacent integer intervals without changing SMT semantics."""

    if constraint in {"true", "false"} or len(pins) != 1:
        return constraint
    target = pins[0].name
    if declarations.get(target) != "Int":
        return constraint
    whole = parse_smt2_sexpr(
        tokenize_smt2_sexpr(subspec_string_to_smt2_and(constraint) or "true")
    )
    whole_interval = _integer_interval(whole, target)
    if whole_interval is not None:
        strict_lower = _preferred_strict_lower_bound(
            pins[0], whole_interval[0], all_pins
        )
        strict_upper = _preferred_strict_upper_bound(
            pins[0], whole_interval[1], all_pins
        )
        return _serialize_subspec_expression(
            _interval_expression(
                target, *whole_interval, strict_lower, strict_upper
            )
        )
    strict_thresholds = _strict_lower_thresholds(pins[0], all_pins)
    compacted = []
    for atom in subspec_string_to_list(constraint):
        tree = parse_smt2_sexpr(tokenize_smt2_sexpr(atom))
        atom_interval = _integer_interval(tree, target)
        if atom_interval is not None:
            strict_lower = (
                atom_interval[0] - 1
                if atom_interval[0] is not None
                and atom_interval[0] - 1 in strict_thresholds
                else None
            )
            strict_upper = (
                atom_interval[1] + 1
                if atom_interval[1] is not None
                and atom_interval[1] + 1 in strict_thresholds
                else None
            )
            tree = _interval_expression(
                target, *atom_interval, strict_lower, strict_upper
            )
        else:
            tree = _compact_interval_expression(tree, target, strict_thresholds)
        compacted.append(
            serialize_smt2_sexpr(tree)
        )
    return " AND ".join(compacted) if compacted else "true"


def _compact_interval_expression(
    expression: object, target: str, strict_thresholds: frozenset[int]
) -> object:
    if not isinstance(expression, list) or not expression:
        return expression
    rewritten = [
        expression[0],
        *(
            _compact_interval_expression(item, target, strict_thresholds)
            for item in expression[1:]
        ),
    ]
    if rewritten[0] != "or" or len(rewritten) < 2:
        return rewritten
    intervals = [_integer_interval(item, target) for item in rewritten[1:]]
    if any(interval is None for interval in intervals):
        return rewritten
    valid_intervals = [
        interval
        for interval in intervals
        if interval is not None
        and not (
            interval[0] is not None
            and interval[1] is not None
            and interval[0] > interval[1]
        )
    ]
    if not valid_intervals:
        return "false"
    merged: list[tuple[Optional[int], Optional[int]]] = []
    for lower, upper in sorted(
        valid_intervals,
        key=lambda item: float("-inf") if item[0] is None else item[0],
    ):
        if not merged:
            merged.append((lower, upper))
            continue
        previous_lower, previous_upper = merged[-1]
        touches = (
            previous_upper is None
            or lower is None
            or lower <= previous_upper + 1
        )
        if not touches:
            merged.append((lower, upper))
            continue
        new_upper = (
            None
            if previous_upper is None or upper is None
            else max(previous_upper, upper)
        )
        merged[-1] = (previous_lower, new_upper)
    expressions = [
        _interval_expression(
            target,
            *interval,
            (
                interval[0] - 1
                if interval[0] is not None
                and interval[0] - 1 in strict_thresholds
                else None
            ),
            (
                interval[1] + 1
                if interval[1] is not None
                and interval[1] + 1 in strict_thresholds
                else None
            ),
        )
        for interval in merged
    ]
    return expressions[0] if len(expressions) == 1 else ["or", *expressions]


def _is_route_value_target(name: str) -> bool:
    if name.endswith("_cost") and "_Isis_" in name:
        return True
    if _configuration_value_operation(name) is not None:
        return True
    return any(
        marker in name
        for marker in (
            "_add_community_",
            "_delete_community_",
            "_set_community_",
        )
    )


def _positive_integer(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Derive field- and line-level subspecifications for every globally "
            "consistent k-pruned symbolic branch seed."
        )
    )
    parser.add_argument("work_directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--z3", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "-j",
        "--workers",
        type=_positive_integer,
        help="parallel branch workers (default: up to the available CPUs)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        subspecifier = SymbolicSubspecifier(
            args.work_directory,
            z3_path=args.z3,
            timeout_seconds=args.timeout,
        )
        report = subspecifier.run(
            output_directory=args.output,
            max_workers=args.workers,
        )
    except (OSError, SubspecificationError, ValueError) as error:
        print(f"Symbolic branch simplification failed: {error}", file=sys.stderr)
        return 2

    output = (
        args.output.resolve()
        if args.output is not None
        else args.work_directory.resolve() / "3_branch_subspecs"
    )
    print(report.to_readable_text(), end="")
    print(f"Parallel branch workers: {subspecifier.last_worker_count}")
    print(f"Summary: {output / 'branch_subspecs.txt'}")
    print(f"Full details: {output / 'branch_subspecs.json'}")
    print(
        "Per-verification-router branch outputs "
        "(final subspecs are grouped by config owner in stage 4):"
    )
    for router in sorted({branch.router for branch in report.branches}):
        router_output = output / router
        print(
            f"  {router}: {router_output / 'field_level_subspecs.txt'} | "
            f"{router_output / 'line_level_subspecs.txt'}"
        )
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
