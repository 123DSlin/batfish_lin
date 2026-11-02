#!/usr/bin/env python3
"""Project symbolic traffic loads to exact configuration-field subspecifications.

The traffic encoder already embeds the control-plane branches in each symbolic
load expression.  This stage therefore projects failures per capacity property
and intersects the resulting link-local constraints.  It does not enumerate
route branches or failure assignments.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Optional

# K=2 traffic encodings contain several thousand nested ``let`` nodes in a
# single load expression.  The shared S-expression helpers are recursive, so
# allow the depth emitted by Minesweeper while retaining Python's guardrail.
sys.setrecursionlimit(max(sys.getrecursionlimit(), 20_000))

from utils.util_smt import (
    parse_smt2_sexpr,
    serialize_smt2_sexpr,
    subspec_string_to_list,
    subspec_string_to_smt2_and,
    tokenize_smt2_sexpr,
)
from utils.util_symbolic import (
    ConfigPin,
    SmtDocument,
    SmtSolver,
    SubspecificationError,
    and_expression,
    collect_declared_symbols,
    integer_interval,
    interval_expression,
    residual_declared_symbols,
    serialize_subspec_expression,
    substitute_symbols,
)


class TrafficSubspecificationError(RuntimeError):
    """Raised when traffic projection cannot be established exactly."""


@dataclass(frozen=True)
class LinkProjection:
    load_variable: str
    capacity_assertion: str
    constraint: str
    solver_seconds: float
    equivalence_check: str = "UNSAT"


@dataclass(frozen=True)
class WeightSubspecification:
    target_weights: tuple[str, ...]
    original_values: dict[str, str]
    constraint: str
    link_projections: tuple[LinkProjection, ...]
    universal_failure_variables: tuple[str, ...]
    non_target_weights_pinned: tuple[str, ...]
    equivalence_check: str = "UNSAT"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["target_weights"] = list(self.target_weights)
        result["link_projections"] = [asdict(item) for item in self.link_projections]
        result["universal_failure_variables"] = list(
            self.universal_failure_variables
        )
        result["non_target_weights_pinned"] = list(self.non_target_weights_pinned)
        return result


@dataclass(frozen=True)
class FieldSubspecification:
    device: str
    field: str
    constraint: str
    exact_constraint: str
    interval: Optional[dict[str, int]]
    equivalence_check: str = "UNSAT"


@dataclass(frozen=True)
class LineSubspecification:
    device: str
    line: str
    members: tuple[str, ...]
    constraint: str
    equivalence_check: str = "UNSAT"


@dataclass(frozen=True)
class TrafficSubspecificationReport:
    generated_at: str
    source_smt: str
    source_sha256: str
    failure_semantics: str
    weight_domain: str
    joint: WeightSubspecification
    localized: tuple[WeightSubspecification, ...]
    field_level: tuple[FieldSubspecification, ...]
    line_level: tuple[LineSubspecification, ...]
    joint_feasible: bool
    schema_name: str = "tolerance-symbolic-traffic-subspec-report"
    schema_version: int = 2
    status: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "status": self.status,
            "generated_at": self.generated_at,
            "source_smt": self.source_smt,
            "source_sha256": self.source_sha256,
            "failure_semantics": self.failure_semantics,
            "weight_domain": self.weight_domain,
            "joint_feasible": self.joint_feasible,
            "intersection_semantics": (
                "conjunction-of-universally-safe-link-capacity-projections"
            ),
            "joint": self.joint.to_dict(),
            "localized": [item.to_dict() for item in self.localized],
            "devices": self._devices_dict(),
        }

    def _devices_dict(self) -> dict[str, Any]:
        devices: dict[str, Any] = {}
        for item in self.field_level:
            device = devices.setdefault(
                item.device, {"field_level": {}, "line_level": {}}
            )
            device["field_level"][item.field] = {
                "constraint": item.constraint,
                "exact_constraint": item.exact_constraint,
                "interval": item.interval,
                "equivalence_check": item.equivalence_check,
            }
        for item in self.line_level:
            device = devices.setdefault(
                item.device, {"field_level": {}, "line_level": {}}
            )
            device["line_level"][item.line] = {
                "members": list(item.members),
                "constraint": item.constraint,
                "equivalence_check": item.equivalence_check,
            }
        return devices

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    def to_text(self) -> str:
        output = [
            "=" * 80,
            "SYMBOLIC TRAFFIC-ENGINEERING SUBSPECIFICATION",
            "=" * 80,
            "",
            f"Overall status: {self.status}",
            f"Source: {self.source_smt}",
            "Semantics: all encoded links remain below capacity for every failure",
            "assignment admitted by the encoded failure budget.",
            "",
            "Joint exact configuration region:",
            f"  Targets: {', '.join(self.joint.target_weights)}",
            f"  Constraint: {self.joint.constraint}",
            f"  Feasible: {'yes' if self.joint_feasible else 'no'}",
            f"  Equivalence check: {self.joint.equivalence_check}",
            "",
            "Device field/line subspecifications:",
        ]
        for device, contents in sorted(self._devices_dict().items()):
            output.extend([f"  Device {device}:", "    Fields:"])
            for name, item in contents["field_level"].items():
                output.extend([f"      {name}:", f"        {item['constraint']}"])
            output.append("    Lines:")
            for name, item in contents["line_level"].items():
                output.extend([f"      {name}:", f"        {item['constraint']}"])
        return "\n".join(output) + "\n"

    def field_level_text(self) -> str:
        output = ["Field-Level Traffic Subspecifications", "=" * 38, ""]
        current = None
        for item in sorted(self.field_level, key=lambda value: (value.device, value.field)):
            if item.device != current:
                current = item.device
                output.extend([f"Device: {current}", "-" * (8 + len(current))])
            output.extend(
                [
                    f"Field: {item.field}",
                    f"Constraint: {item.constraint}",
                    f"Exact constraint: {item.exact_constraint}",
                    f"Equivalence check: {item.equivalence_check}",
                    "",
                ]
            )
        return "\n".join(output) + "\n"

    def line_level_text(self) -> str:
        output = ["Line-Level Traffic Subspecifications", "=" * 37, ""]
        current = None
        for item in sorted(self.line_level, key=lambda value: (value.device, value.line)):
            if item.device != current:
                current = item.device
                output.extend([f"Device: {current}", "-" * (8 + len(current))])
            output.extend(
                [
                    f"Line: {item.line}",
                    f"Members: {', '.join(item.members)}",
                    f"Constraint: {item.constraint}",
                    f"Equivalence check: {item.equivalence_check}",
                    "",
                ]
            )
        return "\n".join(output) + "\n"


@dataclass(frozen=True)
class _TrafficEncoding:
    document: SmtDocument
    weights: tuple[ConfigPin, ...]
    failure_variables: tuple[str, ...]
    failure_budget: object
    weight_domains: dict[str, tuple[object, ...]]
    load_definitions: dict[str, object]
    capacities: tuple[tuple[str, object], ...]


class TrafficSubspecificationEngine:
    """Derive joint and localized exact constraints over traffic-affecting Config_* fields."""

    _SMT_FILE = "smt_traffic_encoding.smt2"
    _OUTPUT_DIRECTORY = "5_traffic_subspecs"

    def __init__(
        self,
        work_directory: Path | str,
        *,
        z3_path: Optional[Path | str] = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.work_directory = Path(work_directory).resolve()
        self.source_path = self.work_directory / self._SMT_FILE
        self.solver = SmtSolver(z3_path=z3_path, timeout_seconds=timeout_seconds)

    def run(
        self,
        *,
        targets: Optional[tuple[str, ...]] = None,
        output_directory: Optional[Path | str] = None,
    ) -> TrafficSubspecificationReport:
        if not self.source_path.is_file():
            raise TrafficSubspecificationError(
                f"missing traffic SMT encoding: {self.source_path}"
            )
        source_bytes = self.source_path.read_bytes()
        encoding = self._parse(source_bytes.decode("utf-8"))
        available = tuple(pin.name for pin in encoding.weights)
        selected = available if targets is None else tuple(dict.fromkeys(targets))
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise TrafficSubspecificationError(
                "unknown traffic configuration target(s): " + ", ".join(unknown)
            )
        if not selected:
            raise TrafficSubspecificationError(
                "traffic encoding contains no selected Config_* targets"
            )

        joint = self._derive(encoding, frozenset(selected))
        localized = tuple(
            self._derive(encoding, frozenset((target,))) for target in selected
        )
        field_level = tuple(
            self._field_subspecification(encoding, item) for item in localized
        )
        grouped: dict[tuple[str, str], list[str]] = {}
        for target in selected:
            grouped.setdefault((_device_name(target), _line_name(target)), []).append(target)
        line_level_items: list[LineSubspecification] = []
        for (device, line), members in sorted(grouped.items()):
            member_set = frozenset(members)
            derived = joint if member_set == frozenset(selected) else self._derive(
                encoding, member_set
            )
            line_level_items.append(
                self._line_subspecification(
                    encoding,
                    derived,
                    device,
                    line,
                    tuple(sorted(members)),
                )
            )
        report = TrafficSubspecificationReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_smt=str(self.source_path),
            source_sha256=hashlib.sha256(source_bytes).hexdigest(),
            failure_semantics="universal-within-encoded-at-most-k-budget",
            weight_domain="positive-uint32",
            joint=joint,
            localized=localized,
            field_level=field_level,
            line_level=tuple(line_level_items),
            joint_feasible=self.solver.satisfiable(
                encoding.document, joint.constraint
            ),
        )
        output = (
            Path(output_directory).resolve()
            if output_directory is not None
            else self.work_directory / self._OUTPUT_DIRECTORY
        )
        self._write_report(output, report, encoding.document)
        return report

    def _field_subspecification(
        self,
        encoding: _TrafficEncoding,
        localized: WeightSubspecification,
    ) -> FieldSubspecification:
        target = localized.target_weights[0]
        if not self.solver.satisfiable(encoding.document, localized.constraint):
            return FieldSubspecification(
                device=_device_name(target),
                field=target,
                constraint="UNSAT",
                exact_constraint=localized.constraint,
                interval=None,
            )
        exact_expression = parse_smt2_sexpr(
            tokenize_smt2_sexpr(
                subspec_string_to_smt2_and(localized.constraint) or "true"
            )
        )
        domain_expression = _clean_and(encoding.weight_domains[target])
        bounds = integer_interval(domain_expression, target)
        normalized = localized.constraint
        interval_payload: Optional[dict[str, int]] = None
        if bounds is not None:
            domain_lower, domain_upper = bounds
            if domain_lower is not None and domain_upper is not None:
                lower, upper = self._solution_interval(
                    encoding.document,
                    localized.constraint,
                    target,
                    domain_lower,
                    domain_upper,
                )
                if lower is not None and upper is not None:
                    candidate_expression = interval_expression(target, lower, upper)
                    candidate = serialize_subspec_expression(candidate_expression)
                    equivalent, _ = self.solver.equivalent(
                        encoding.document, exact_expression, candidate
                    )
                    if equivalent:
                        normalized = _display_interval_constraint(
                            target,
                            lower,
                            upper,
                            domain_lower,
                            domain_upper,
                        )
                        interval_payload = {"lo": lower, "hi": upper}
        return FieldSubspecification(
            device=_device_name(target),
            field=target,
            constraint=normalized,
            exact_constraint=localized.constraint,
            interval=interval_payload,
        )

    def _solution_interval(
        self,
        document: SmtDocument,
        constraint: str,
        target: str,
        domain_lower: int,
        domain_upper: int,
    ) -> tuple[Optional[int], Optional[int]]:
        if not self.solver.satisfiable(document, constraint):
            return None, None

        left, right = domain_lower, domain_upper
        lower = domain_upper
        while left <= right:
            middle = (left + right) // 2
            query = constraint + f" AND (<= {target} {middle})"
            if self.solver.satisfiable(document, query):
                lower = middle
                right = middle - 1
            else:
                left = middle + 1

        left, right = domain_lower, domain_upper
        upper = domain_lower
        while left <= right:
            middle = (left + right) // 2
            query = constraint + f" AND (>= {target} {middle})"
            if self.solver.satisfiable(document, query):
                upper = middle
                left = middle + 1
            else:
                right = middle - 1
        return lower, upper

    def _line_subspecification(
        self,
        encoding: _TrafficEncoding,
        derived: WeightSubspecification,
        device: str,
        line: str,
        members: tuple[str, ...],
    ) -> LineSubspecification:
        """Remove domain-only atoms from a line view and prove it unchanged."""
        if not self.solver.satisfiable(encoding.document, derived.constraint):
            return LineSubspecification(
                device=device,
                line=line,
                members=members,
                constraint="UNSAT",
            )
        domain = _clean_and(
            expression
            for member in members
            for expression in encoding.weight_domains[member]
        )
        kept: list[str] = []
        for atom_text in subspec_string_to_list(derived.constraint):
            atom = parse_smt2_sexpr(tokenize_smt2_sexpr(atom_text))
            if not self.solver.entails(encoding.document, domain, atom):
                kept.append(atom_text)
        constraint = " AND ".join(kept) or "empty"
        display_expression = parse_smt2_sexpr(
            tokenize_smt2_sexpr(subspec_string_to_smt2_and(constraint) or "true")
        )
        candidate = serialize_subspec_expression(
            _clean_and((domain, display_expression))
        )
        exact_expression = parse_smt2_sexpr(
            tokenize_smt2_sexpr(
                subspec_string_to_smt2_and(derived.constraint) or "true"
            )
        )
        equivalent, _ = self.solver.equivalent(
            encoding.document, exact_expression, candidate
        )
        if not equivalent:
            raise TrafficSubspecificationError(
                f"device line formatting changed semantics for {line}"
            )
        return LineSubspecification(
            device=device,
            line=line,
            members=members,
            constraint=constraint,
        )

    def _derive(
        self, encoding: _TrafficEncoding, target_names: frozenset[str]
    ) -> WeightSubspecification:
        document = encoding.document
        replacements = {
            pin.name: parse_smt2_sexpr(tokenize_smt2_sexpr(pin.original_value))
            for pin in encoding.weights
            if pin.name not in target_names
        }
        target_pins = tuple(
            pin for pin in encoding.weights if pin.name in target_names
        )
        domain = and_expression(
            substitute_symbols(expression, replacements)
            for name in sorted(target_names)
            for expression in encoding.weight_domains[name]
        )

        expected_links: list[object] = []
        projected_links: list[object] = []
        reports: list[LinkProjection] = []
        for load_name, capacity in encoding.capacities:
            load_expression = substitute_symbols(
                encoding.load_definitions[load_name], replacements
            )
            capacity_expression = substitute_symbols(
                substitute_symbols(capacity, {load_name: load_expression}),
                replacements,
            )
            robust: object = [
                "=>",
                encoding.failure_budget,
                capacity_expression,
            ]
            if encoding.failure_variables:
                robust = [
                    "forall",
                    document.quantifier_bindings(list(encoding.failure_variables)),
                    robust,
                ]
            expected_links.append(robust)
            started = time.monotonic()
            projected = self.solver.project(
                document,
                target_pins,
                robust,
                f"traffic projection for {load_name}",
            )
            elapsed = time.monotonic() - started
            residual = residual_declared_symbols(
                projected, document.declarations, target_names
            )
            if residual:
                raise TrafficSubspecificationError(
                    f"traffic projection for {load_name} retained symbols: "
                    + ", ".join(residual)
                )
            equivalent, _ = self.solver.equivalent(document, robust, projected)
            if not equivalent:
                raise TrafficSubspecificationError(
                    f"traffic projection for {load_name} failed equivalence check"
                )
            projected_expression = parse_smt2_sexpr(
                tokenize_smt2_sexpr(subspec_string_to_smt2_and(projected) or "true")
            )
            projected_links.append(projected_expression)
            reports.append(
                LinkProjection(
                    load_variable=load_name,
                    capacity_assertion=serialize_smt2_sexpr(capacity_expression),
                    constraint=projected,
                    solver_seconds=elapsed,
                )
            )

        expected = _clean_and((domain, *expected_links))
        candidate_expression = _clean_and((domain, *projected_links))
        constraint = serialize_subspec_expression(candidate_expression)
        equivalent, _ = self.solver.equivalent(document, expected, constraint)
        if not equivalent:
            raise TrafficSubspecificationError(
                "intersected traffic subspecification failed equivalence check"
            )
        residual = residual_declared_symbols(
            constraint, document.declarations, target_names
        )
        if residual:
            raise TrafficSubspecificationError(
                "intersected traffic subspecification retained symbols: "
                + ", ".join(residual)
            )
        return WeightSubspecification(
            target_weights=tuple(sorted(target_names)),
            original_values={pin.name: pin.original_value for pin in target_pins},
            constraint=constraint,
            link_projections=tuple(reports),
            universal_failure_variables=encoding.failure_variables,
            non_target_weights_pinned=tuple(sorted(replacements)),
        )

    @staticmethod
    def _parse(text: str) -> _TrafficEncoding:
        document = SmtDocument.parse(text)
        # Every Config_* pin referenced by the traffic formula is a valid projection target.
        # This includes SR candidate weights and IS-IS interface costs.
        weights = tuple(document.config_pins)
        weight_names = frozenset(pin.name for pin in weights)
        bool_names = frozenset(
            name for name, sort in document.declarations.items() if sort == "Bool"
        )
        load_names = frozenset(
            name for name, sort in document.declarations.items()
            if name.startswith("load_") and sort == "Real"
        )
        pin_indices = frozenset(pin.assertion_index for pin in weights)
        domains: dict[str, list[object]] = {name: [] for name in weight_names}
        load_definitions: dict[str, object] = {}
        capacities: list[tuple[str, object]] = []
        budgets: list[object] = []
        unclassified: list[str] = []

        for index, assertion in enumerate(document.assertions):
            if index in pin_indices:
                continue
            symbols = collect_declared_symbols(assertion, document.declarations)
            assertion_loads = symbols.intersection(load_names)
            assertion_weights = symbols.intersection(weight_names)
            assertion_bools = symbols.intersection(bool_names)
            definition = TrafficSubspecificationEngine._load_definition(
                assertion, load_names
            )
            if definition is not None:
                name, expression = definition
                if name in load_definitions:
                    raise TrafficSubspecificationError(
                        f"load variable {name} has multiple definitions"
                    )
                load_definitions[name] = expression
            elif assertion_loads:
                if len(assertion_loads) != 1 or not TrafficSubspecificationEngine._is_capacity_assertion(
                    assertion, next(iter(assertion_loads))
                ):
                    unclassified.append(serialize_smt2_sexpr(assertion))
                else:
                    capacities.append((next(iter(assertion_loads)), assertion))
            elif assertion_weights and not assertion_bools:
                if len(assertion_weights) != 1:
                    unclassified.append(serialize_smt2_sexpr(assertion))
                else:
                    domains[next(iter(assertion_weights))].append(assertion)
            elif assertion_bools and not assertion_weights:
                budgets.append(assertion)
            elif assertion == "true":
                continue
            else:
                unclassified.append(serialize_smt2_sexpr(assertion))

        if unclassified:
            raise TrafficSubspecificationError(
                "unclassified traffic SMT assertion(s): " + "; ".join(unclassified)
            )
        missing = sorted(load_names - set(load_definitions))
        if missing:
            raise TrafficSubspecificationError(
                "load variables without definitions: " + ", ".join(missing)
            )
        if not capacities:
            raise TrafficSubspecificationError("traffic encoding has no capacity assertions")
        for load_name, _ in capacities:
            if load_name not in load_definitions:
                raise TrafficSubspecificationError(
                    f"capacity references undefined load variable {load_name}"
                )
        empty_domains = sorted(name for name, values in domains.items() if not values)
        if empty_domains:
            raise TrafficSubspecificationError(
                "configuration variables without domain constraints: "
                + ", ".join(empty_domains)
            )
        return _TrafficEncoding(
            document=document,
            weights=tuple(sorted(weights, key=lambda pin: pin.name)),
            failure_variables=tuple(sorted(bool_names)),
            failure_budget=and_expression(budgets),
            weight_domains={name: tuple(values) for name, values in domains.items()},
            load_definitions=load_definitions,
            capacities=tuple(capacities),
        )

    @staticmethod
    def _load_definition(
        assertion: object, load_names: frozenset[str]
    ) -> Optional[tuple[str, object]]:
        if not isinstance(assertion, list) or len(assertion) != 3 or assertion[0] != "=":
            return None
        left, right = assertion[1], assertion[2]
        if isinstance(left, str) and left in load_names:
            return left, right
        if isinstance(right, str) and right in load_names:
            return right, left
        return None

    @staticmethod
    def _is_capacity_assertion(assertion: object, load_name: str) -> bool:
        return (
            isinstance(assertion, list)
            and len(assertion) == 3
            and assertion[0] in {"<", "<=", ">", ">="}
            and (assertion[1] == load_name or assertion[2] == load_name)
        )

    @staticmethod
    def _write_report(
        output: Path,
        report: TrafficSubspecificationReport,
        document: SmtDocument,
    ) -> None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "traffic_subspecs.json").write_text(
            report.to_json(), encoding="utf-8"
        )
        (output / "traffic_subspecs.txt").write_text(
            report.to_text(), encoding="utf-8"
        )
        (output / "field_level_subspecs.txt").write_text(
            report.field_level_text(), encoding="utf-8"
        )
        (output / "line_level_subspecs.txt").write_text(
            report.line_level_text(), encoding="utf-8"
        )
        constraint = subspec_string_to_smt2_and(report.joint.constraint) or "true"
        query = document.query(
            f"(assert {constraint})",
            "(check-sat)",
            ";(get-model)",
        )
        (output / "joint_weight_subspec.smt2").write_text(query, encoding="utf-8")


def _positive_float(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _device_name(config_name: str) -> str:
    """Return the owning device from a SpecLens ``Config_<device>_*`` atom."""
    if not config_name.startswith("Config_"):
        return "unknown"
    remainder = config_name[len("Config_") :]
    return remainder.split("_", 1)[0] or "unknown"


def _line_name(config_name: str) -> str:
    """Collapse traffic fields to their owning configuration line."""
    if "_Path_" in config_name:
        return config_name.split("_Path_", 1)[0]
    if config_name.endswith("_cost"):
        return config_name[: -len("_cost")]
    return config_name


def _display_interval_constraint(
    target: str,
    lower: int,
    upper: int,
    domain_lower: int,
    domain_upper: int,
) -> str:
    """Render only restrictions beyond the configuration field's base domain."""
    if lower == domain_lower and upper == domain_upper:
        return "empty"
    if lower == upper:
        return f"(= {target} {lower})"
    parts: list[str] = []
    if lower > domain_lower:
        parts.append(f"(>= {target} {lower})")
    if upper < domain_upper:
        parts.append(f"(<= {target} {upper})")
    return " AND ".join(parts) or "empty"


def _clean_and(expressions: Any) -> object:
    """Build a conjunction without true operands or nested conjunctions."""

    values: list[object] = []
    for expression in expressions:
        if expression == "true":
            continue
        if isinstance(expression, list) and expression and expression[0] == "and":
            values.extend(item for item in expression[1:] if item != "true")
        else:
            values.append(expression)
    return and_expression(values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Derive failure-aware traffic-engineering subspecifications from "
            "smt_traffic_encoding.smt2."
        )
    )
    parser.add_argument("work_directory", type=Path)
    parser.add_argument(
        "--target",
        action="append",
        dest="targets",
        help="Config_* field to release (repeatable; default: all fields)",
    )
    parser.add_argument("--z3", type=Path, help="optional Z3 executable")
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=30.0,
        help="solver timeout per query in seconds (default: 30)",
    )
    parser.add_argument("--output", type=Path, help="optional output directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = TrafficSubspecificationEngine(
            args.work_directory,
            z3_path=args.z3,
            timeout_seconds=args.timeout,
        ).run(
            targets=None if args.targets is None else tuple(args.targets),
            output_directory=args.output,
        )
    except (OSError, SubspecificationError, TrafficSubspecificationError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Traffic subspecification status: {report.status}")
    print(f"Joint targets: {len(report.joint.target_weights)}")
    print(f"Joint feasible: {'yes' if report.joint_feasible else 'no'}")
    print(f"Joint constraint: {report.joint.constraint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
