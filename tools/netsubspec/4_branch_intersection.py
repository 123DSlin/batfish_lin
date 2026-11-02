#!/usr/bin/env python3
"""Intersect branch-local symbolic subspecifications into final subspecs."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Optional

from utils.util_file import (
    load_hostnames,
    save_field_level_subspecs,
    save_line_level_subspecs,
)
from utils.util_smt import (
    parse_smt2_sexpr,
    subspec_string_to_smt2_and,
    subspec_string_to_list,
    tokenize_smt2_sexpr,
)
from utils.util_symbolic import (
    ConfigPin,
    SmtDocument,
    SmtSolver,
    SubspecificationError,
    and_expression,
    constraint_ids as make_constraint_ids,
    integer_interval,
    interval_expression,
    preferred_strict_lower_bound,
    preferred_strict_upper_bound,
    residual_declared_symbols,
    serialize_subspec_expression,
)


class IntersectionError(RuntimeError):
    """Raised when final intersection cannot be established exactly."""


@dataclass(frozen=True)
class IntersectionSource:
    provenance_id: str
    candidate_id: str
    branch_name: str
    router: str
    formula: str
    unrestricted: bool
    constraint_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["constraint_ids"] = list(self.constraint_ids)
        return result


@dataclass(frozen=True)
class FinalSubspec:
    level: str
    router: str
    config_owner: str
    target: str
    configs: tuple[str, ...]
    original_values: dict[str, str]
    constraint: str
    unrestricted: bool
    source_branch_count: int
    sources: tuple[IntersectionSource, ...]
    constraint_ids: tuple[str, ...]
    constraint_provenance: tuple[dict[str, Any], ...]
    equivalence_check: str = "UNSAT"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["configs"] = list(self.configs)
        result["sources"] = [source.to_dict() for source in self.sources]
        result["constraint_ids"] = list(self.constraint_ids)
        result["constraint_provenance"] = list(self.constraint_provenance)
        return result


@dataclass(frozen=True)
class IntersectionReport:
    status: str
    generated_at: str
    source_report: str
    source_sha256: str
    scope: dict[str, Any]
    branch_count: int
    fields: tuple[FinalSubspec, ...]
    lines: tuple[FinalSubspec, ...]
    branch_provenance: tuple[dict[str, Any], ...]
    errors: tuple[str, ...] = ()
    schema_name: str = "tolerance-symbolic-final-subspec-report"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "status": self.status,
            "generated_at": self.generated_at,
            "source_report": self.source_report,
            "source_sha256": self.source_sha256,
            "scope": self.scope,
            "intersection_semantics": (
                "conjunction-across-symbolic-branches-per-config-owner"
            ),
            "branch_count": self.branch_count,
            "field_count": len(self.fields),
            "line_count": len(self.lines),
            "fields": [item.to_dict() for item in self.fields],
            "lines": [item.to_dict() for item in self.lines],
            "branch_provenance": list(self.branch_provenance),
            "errors": list(self.errors),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    def to_readable_text(self) -> str:
        routers = tuple(self.scope.get("routers", ()))
        output = [
            "=" * 80,
            "SYMBOLIC SUBSPECIFICATION INTERSECTION",
            "=" * 80,
            "",
            f"Overall status: {self.status}",
            (
                "Scope: "
                f"{self.scope.get('plane', '?')} | "
                f"at-most-{self.scope.get('k', '?')} link failures"
            ),
            (
                f"Intersected branches: {self.branch_count} | "
                f"final fields: {len(self.fields)} | final lines: {len(self.lines)}"
            ),
            (
                "Semantics: per-config-owner conjunction of every branch-local "
                "symbolic subspecification"
            ),
            "",
            "Per-router results:",
        ]
        for router in routers:
            fields = [item for item in self.fields if item.router == router]
            lines = [item for item in self.lines if item.router == router]
            summary = (
                f"  {router}: fields {len(fields)} "
                f"({sum(not item.unrestricted for item in fields)} constrained) | "
                f"lines {len(lines)} "
                f"({sum(not item.unrestricted for item in lines)} constrained)"
            )
            if not fields and not lines:
                summary += " | no owned configuration targets"
            output.append(summary)
        output.extend(
            [
                "",
                "Exact formulas are stored in the per-router field/line reports.",
                "Every final formula retains its contributing branch formulas in JSON.",
            ]
        )
        if self.errors:
            output.extend(["", "Errors:"])
            output.extend(f"  - {error}" for error in self.errors)
        elif self.status == "PASS":
            output.extend(
                ["", "All branch subspecifications were intersected exactly. ✓"]
            )
        return "\n".join(output) + "\n"

    def write(self, output_directory: Path) -> tuple[Path, ...]:
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "final_subspecs.json"
        text_path = output_directory / "final_subspecs.txt"
        _write_atomic(json_path, self.to_json())
        _write_atomic(text_path, self.to_readable_text())
        paths: list[Path] = [json_path, text_path]
        routers = tuple(self.scope.get("routers", ()))
        for router in routers:
            directory = output_directory / router
            directory.mkdir(parents=True, exist_ok=True)
            field_path = directory / "field_level_subspecs.txt"
            line_path = directory / "line_level_subspecs.txt"
            save_field_level_subspecs(
                field_path,
                {
                    item.target: {"empty" if item.unrestricted else item.constraint}
                    for item in self.fields
                    if item.router == router
                },
            )
            save_line_level_subspecs(
                line_path,
                {
                    item.target: {"empty" if item.unrestricted else item.constraint}
                    for item in self.lines
                    if item.router == router
                },
            )
            paths.extend((field_path, line_path))
        return tuple(paths)


@dataclass(frozen=True)
class _TargetOccurrence:
    branch: dict[str, Any]
    item: dict[str, Any]


class SymbolicIntersection:
    """Compute one exact final formula per field and line target."""

    _BRANCH_DIRECTORY = "3_branch_subspecs"
    _OUTPUT_DIRECTORY = "4_final_subspecs"
    _CONSISTENCY_DIRECTORY = "2_consistency_check"

    def __init__(
        self,
        work_directory: Path | str,
        *,
        z3_path: Optional[Path | str] = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.work_directory = Path(work_directory).resolve()
        self.source_path = (
            self.work_directory / self._BRANCH_DIRECTORY / "branch_subspecs.json"
        )
        self.solver = SmtSolver(
            z3_path=z3_path,
            timeout_seconds=timeout_seconds,
        )
        self.hostnames = tuple(load_hostnames(self.work_directory))
        self._documents: dict[str, SmtDocument] = {}

    def run(
        self, *, output_directory: Optional[Path | str] = None
    ) -> IntersectionReport:
        source, source_bytes = self._load_source_report()
        fields = self._intersect_level(source, "field")
        lines = self._intersect_level(source, "line")
        report = IntersectionReport(
            status="PASS",
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_report=str(self.source_path),
            source_sha256=hashlib.sha256(source_bytes).hexdigest(),
            scope=dict(source["scope"]),
            branch_count=source["branch_count"],
            fields=fields,
            lines=lines,
            branch_provenance=tuple(source["branch_provenance"]),
        )
        output = (
            Path(output_directory).resolve()
            if output_directory is not None
            else self.work_directory / self._OUTPUT_DIRECTORY
        )
        report.write(output)
        return report

    def _load_source_report(self) -> tuple[dict[str, Any], bytes]:
        try:
            source_bytes = self.source_path.read_bytes()
            report = json.loads(source_bytes)
        except (OSError, json.JSONDecodeError) as error:
            raise IntersectionError(
                f"cannot load stage 3 report {self.source_path}: {error}"
            ) from error
        branches = report.get("branches")
        scope = report.get("scope")
        if (
            report.get("schema_name") != "tolerance-symbolic-branch-subspec-report"
            or report.get("schema_version") != 5
            or report.get("status") != "PASS"
            or report.get("errors") != []
            or not isinstance(branches, list)
            or not branches
            or report.get("branch_count") != len(branches)
            or not isinstance(report.get("branch_provenance"), list)
            or any(not isinstance(branch, dict) for branch in branches)
            or any(not isinstance(item, dict) for item in report["branch_provenance"])
            or not isinstance(scope, dict)
            or scope.get("mode") != "global"
            or not isinstance(scope.get("routers"), list)
            or any(not isinstance(router, str) for router in scope["routers"])
            or len(scope["routers"]) != len(set(scope["routers"]))
            or not set(scope["routers"]).issubset(set(self.hostnames))
        ):
            raise IntersectionError(
                "stage 4 requires a complete PASS stage 3 report with schema v5"
            )
        provenance_values = [
            item.get("provenance_id") for item in report["branch_provenance"]
        ]
        if any(not isinstance(value, str) for value in provenance_values):
            raise IntersectionError("stage 3 contains malformed branch provenance")
        provenance_ids = set(provenance_values)
        if len(provenance_values) != len(provenance_ids):
            raise IntersectionError("stage 3 contains duplicate branch provenance")
        for branch in branches:
            if (
                not isinstance(branch.get("candidate_id"), str)
                or not isinstance(branch.get("branch_name"), str)
                or not isinstance(branch.get("provenance_id"), str)
                or not isinstance(branch.get("fields"), list)
                or not isinstance(branch.get("lines"), list)
            ):
                raise IntersectionError("stage 3 contains a malformed branch result")
        candidate_ids = [branch.get("candidate_id") for branch in branches]
        branch_provenance_ids = [branch.get("provenance_id") for branch in branches]
        if (
            len(candidate_ids) != len(set(candidate_ids))
            or len(branch_provenance_ids) != len(set(branch_provenance_ids))
            or set(branch_provenance_ids) != provenance_ids
        ):
            raise IntersectionError(
                "stage 3 branch identities are incomplete or duplicated"
            )
        if report.get("field_evaluations") != sum(
            len(branch["fields"]) for branch in branches
        ) or report.get("line_evaluations") != sum(
            len(branch["lines"]) for branch in branches
        ):
            raise IntersectionError("stage 3 target coverage counts are inconsistent")
        return report, source_bytes

    def _intersect_level(
        self, report: dict[str, Any], level: str
    ) -> tuple[FinalSubspec, ...]:
        item_key = "fields" if level == "field" else "lines"
        target_key = "config" if level == "field" else "line_group"
        configs_key = "released_configs" if level == "field" else "configs"
        grouped: dict[tuple[str, str], list[_TargetOccurrence]] = {}
        for branch in report["branches"]:
            for item in branch[item_key]:
                if not isinstance(item, dict):
                    raise IntersectionError(f"malformed {level} result in stage 3")
                target = item.get(target_key)
                configs = item.get(configs_key)
                if not isinstance(target, str) or not target:
                    raise IntersectionError(f"malformed {level} target in stage 3")
                if not isinstance(configs, list) or any(
                    not isinstance(name, str) for name in configs
                ):
                    raise IntersectionError(
                        f"malformed released configs for {level} target {target}"
                    )
                owners = {self._config_owner(name) for name in configs}
                if len(owners) != 1:
                    raise IntersectionError(
                        f"{level} target {target} crosses configuration-owner scopes"
                    )
                grouped.setdefault((next(iter(owners)), target), []).append(
                    _TargetOccurrence(branch, item)
                )
        return tuple(
            self._intersect_target(
                level,
                router,
                target,
                tuple(occurrences),
                configs_key,
            )
            for (router, target), occurrences in sorted(grouped.items())
        )

    def _intersect_target(
        self,
        level: str,
        config_owner: str,
        target: str,
        occurrences: tuple[_TargetOccurrence, ...],
        configs_key: str,
    ) -> FinalSubspec:
        config_shapes = {
            tuple(occurrence.item.get(configs_key, ())) for occurrence in occurrences
        }
        occurrence_branches = [
            occurrence.branch["provenance_id"] for occurrence in occurrences
        ]
        if len(occurrence_branches) != len(set(occurrence_branches)):
            raise IntersectionError(
                f"{level} target {target} occurs more than once in one branch"
            )
        if len(config_shapes) != 1:
            raise IntersectionError(
                f"{level} target {target} has inconsistent released config sets"
            )
        configs = next(iter(config_shapes))
        if not configs or any(not isinstance(name, str) for name in configs):
            raise IntersectionError(f"{level} target {target} has no valid configs")
        if any(self._config_owner(name) != config_owner for name in configs):
            raise IntersectionError(
                f"{level} target {target} crosses configuration-owner scopes"
            )

        document = self._document_for(occurrences[0].branch)
        missing = [name for name in configs if name not in document.declarations]
        if missing:
            raise IntersectionError(
                f"{level} target {target} has undeclared configs: {', '.join(missing)}"
            )
        pins = tuple(pin for pin in document.config_pins if pin.name in set(configs))
        if {pin.name for pin in pins} != set(configs):
            raise IntersectionError(
                f"{level} target {target} is missing original configuration values"
            )

        expressions = []
        sources = []
        for occurrence in occurrences:
            branch = occurrence.branch
            item = occurrence.item
            constraint = item.get("constraint")
            unrestricted = item.get("unrestricted")
            constraint_ids = item.get("constraint_ids")
            if (
                not isinstance(constraint, str)
                or not isinstance(unrestricted, bool)
                or not isinstance(constraint_ids, list)
                or any(not isinstance(value, str) for value in constraint_ids)
                or unrestricted != (constraint == "true")
                or len(constraint_ids)
                != (0 if unrestricted else len(subspec_string_to_list(constraint)))
            ):
                raise IntersectionError(
                    f"{level} target {target} has malformed branch constraint"
                )
            source_document = self._document_for(branch)
            mismatched_sorts = [
                name
                for name in configs
                if source_document.declarations.get(name) != document.declarations[name]
            ]
            if mismatched_sorts:
                raise IntersectionError(
                    f"{level} target {target} has inconsistent config sorts: "
                    + ", ".join(mismatched_sorts)
                )
            source_values = {
                pin.name: pin.original_value
                for pin in source_document.config_pins
                if pin.name in set(configs)
            }
            expected_values = {pin.name: pin.original_value for pin in pins}
            if source_values != expected_values:
                raise IntersectionError(
                    f"{level} target {target} has inconsistent original values"
                )
            residual = residual_declared_symbols(
                constraint, source_document.declarations, frozenset(configs)
            )
            if residual:
                raise IntersectionError(
                    f"{level} target {target} retains non-target symbols: "
                    + ", ".join(residual)
                )
            expressions.append(_constraint_expression(constraint))
            sources.append(
                IntersectionSource(
                    provenance_id=branch["provenance_id"],
                    candidate_id=branch["candidate_id"],
                    branch_name=branch["branch_name"],
                    router=branch["router"],
                    formula=constraint,
                    unrestricted=unrestricted,
                    constraint_ids=tuple(constraint_ids),
                )
            )

        expected = and_expression(expressions)
        constraint = self._simplify_intersection(document, pins, target, expected)
        residual = residual_declared_symbols(
            constraint, document.declarations, frozenset(configs)
        )
        if residual:
            raise IntersectionError(
                f"final {level} target {target} retains non-target symbols: "
                + ", ".join(residual)
            )
        equivalent, _ = self.solver.equivalent(
            document, expected, constraint
        )
        if not equivalent:
            raise IntersectionError(
                f"final {level} target {target} failed exact equivalence checking"
            )
        if not self._is_satisfiable(document, constraint):
            raise IntersectionError(
                f"final {level} target {target} is UNSAT; the checked original "
                "configuration should be a witness"
            )

        final_constraint_ids = make_constraint_ids(
            f"final-{level}", target, constraint
        )
        provenance = self._atom_provenance(
            document,
            level,
            target,
            constraint,
            tuple(sources),
            final_constraint_ids,
        )
        return FinalSubspec(
            level=level,
            router=config_owner,
            config_owner=config_owner,
            target=target,
            configs=tuple(configs),
            original_values={pin.name: pin.original_value for pin in pins},
            constraint=constraint,
            unrestricted=constraint == "true",
            source_branch_count=len(sources),
            sources=tuple(sorted(sources, key=lambda item: item.branch_name)),
            constraint_ids=final_constraint_ids,
            constraint_provenance=provenance,
        )

    def _simplify_intersection(
        self,
        document: SmtDocument,
        pins: tuple[ConfigPin, ...],
        target: str,
        expected: object,
    ) -> str:
        if len(pins) == 1 and pins[0].sort == "Int":
            interval = integer_interval(expected, pins[0].name)
            if interval is not None:
                strict_lower = preferred_strict_lower_bound(
                    pins[0], interval[0], document.config_pins
                )
                strict_upper = preferred_strict_upper_bound(
                    pins[0], interval[1], document.config_pins
                )
                return serialize_subspec_expression(
                    interval_expression(
                        pins[0].name,
                        interval[0],
                        interval[1],
                        strict_lower,
                        strict_upper,
                    )
                )
        simplified = self.solver.simplify(document, expected)
        return self.solver.remove_redundant_atoms(document, simplified)

    def _atom_provenance(
        self,
        document: SmtDocument,
        level: str,
        target: str,
        constraint: str,
        sources: tuple[IntersectionSource, ...],
        constraint_ids: tuple[str, ...],
    ) -> tuple[dict[str, Any], ...]:
        records = []
        for constraint_id, atom in zip(
            constraint_ids, subspec_string_to_list(constraint)
        ):
            atom_expression = parse_smt2_sexpr(tokenize_smt2_sexpr(atom))
            contributing = []
            for source in sources:
                if source.unrestricted:
                    continue
                source_expression = _constraint_expression(source.formula)
                if self.solver.entails(
                    document, source_expression, atom_expression
                ):
                    contributing.append(
                        {
                            "provenance_id": source.provenance_id,
                            "branch_name": source.branch_name,
                            "source_constraint_ids": list(source.constraint_ids),
                        }
                    )
            if not contributing:
                contributing = [
                    {
                        "provenance_id": source.provenance_id,
                        "branch_name": source.branch_name,
                        "source_constraint_ids": list(source.constraint_ids),
                    }
                    for source in sources
                    if not source.unrestricted
                ]
            records.append(
                {
                    "constraint_id": constraint_id,
                    "level": level,
                    "target": target,
                    "formula": atom,
                    "sources": contributing,
                }
            )
        return tuple(records)

    def _document_for(self, branch: dict[str, Any]) -> SmtDocument:
        seed_file = branch.get("seed_file")
        if not isinstance(seed_file, str) or not seed_file:
            raise IntersectionError("stage 3 branch has no seed file")
        cached = self._documents.get(seed_file)
        if cached is not None:
            return cached
        path = (self.work_directory / self._CONSISTENCY_DIRECTORY / seed_file).resolve()
        try:
            path.relative_to(
                (self.work_directory / self._CONSISTENCY_DIRECTORY).resolve()
            )
        except ValueError as error:
            raise IntersectionError(
                f"seed path escapes consistency output: {seed_file}"
            ) from error
        try:
            content = path.read_bytes()
        except OSError as error:
            raise IntersectionError(
                f"cannot read branch seed {path}: {error}"
            ) from error
        expected_hash = branch.get("seed_sha256")
        if expected_hash != hashlib.sha256(content).hexdigest():
            raise IntersectionError(f"branch seed changed after stage 3: {path}")
        document = SmtDocument.parse(content.decode("utf-8"))
        self._documents[seed_file] = document
        return document

    def _config_owner(self, config: str) -> str:
        matches = [
            hostname
            for hostname in self.hostnames
            if config.startswith(f"Config_{hostname}_")
        ]
        if len(matches) != 1:
            raise IntersectionError(
                f"cannot determine a unique router for configuration target {config}"
            )
        return matches[0]

    def _is_satisfiable(self, document: SmtDocument, constraint: str) -> bool:
        return self.solver.satisfiable(document, constraint)


def _constraint_expression(constraint: str) -> object:
    return parse_smt2_sexpr(
        tokenize_smt2_sexpr(subspec_string_to_smt2_and(constraint) or "true")
    )


def _write_atomic(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Intersect the exact field- and line-level constraints produced for "
            "all k-pruned symbolic branches."
        )
    )
    parser.add_argument("work_directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--z3", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = SymbolicIntersection(
            args.work_directory,
            z3_path=args.z3,
            timeout_seconds=args.timeout,
        ).run(output_directory=args.output)
    except (IntersectionError, SubspecificationError, OSError, ValueError) as error:
        print(
            f"Symbolic subspecification intersection failed: {error}",
            file=sys.stderr,
        )
        return 2

    output = (
        args.output.resolve()
        if args.output is not None
        else args.work_directory.resolve() / "4_final_subspecs"
    )
    print(report.to_readable_text(), end="")
    print(f"Summary: {output / 'final_subspecs.txt'}")
    print(f"Full details: {output / 'final_subspecs.json'}")
    print("Per-router final outputs:")
    for router in report.scope["routers"]:
        router_output = output / router
        print(
            f"  {router}: {router_output / 'field_level_subspecs.txt'} | "
            f"{router_output / 'line_level_subspecs.txt'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
