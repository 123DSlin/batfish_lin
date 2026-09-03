#!/usr/bin/env python3
"""Validate one symbolic control plane against concrete 0/1-link-failure snapshots.

This is an external validation oracle, not part of symbolic route convergence. It projects the
all-links-up run's MAIN-RIB and guarded SR forwarding branches under each supplied assignment and
compares that projection with a fresh Batfish run for the corresponding concrete configuration.
"""

import argparse
import json
import pathlib
import sys
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple


CONTROL_PLANE_FILE = "0_symbolic_control_plane.json"
DATA_PLANE_FILE = "0_data_plane.txt"
SR_POLICY_FILE = "0_symbolic_sr_policies.json"
CONTROL_PLANE_SCHEMA = "batfish-minesweeper-symbolic-control-plane"
CONTROL_PLANE_VERSION = 2
SR_POLICY_SCHEMA = "batfish-minesweeper-symbolic-sr-policies"
SR_POLICY_VERSION = 1

RouteKey = Tuple[str, str, str, str, str, str, int, int, str]
SrBranchKey = Tuple[object, ...]


def _read_json(path: pathlib.Path) -> Mapping[str, object]:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("cannot read {}: {}".format(path, error)) from error
    if not isinstance(value, dict):
        raise ValueError("{} must contain a JSON object".format(path))
    return value


def _require_schema(
    document: Mapping[str, object], path: pathlib.Path, schema: str, version: int
) -> None:
    if document.get("schemaName") != schema or document.get("schemaVersion") != version:
        raise ValueError(
            "{} requires schema {!r} version {}; regenerate the output with the current pipeline"
            .format(path, schema, version)
        )


def _evaluate_guard(ast: object, assignment: Mapping[str, bool]) -> bool:
    if not isinstance(ast, dict):
        raise ValueError("guard AST node must be an object")
    operator = ast.get("operator")
    children = ast.get("children", [])
    if not isinstance(children, list):
        raise ValueError("guard AST children must be a list")
    if operator == "TRUE":
        return True
    if operator == "FALSE":
        return False
    if operator == "VARIABLE":
        variable = ast.get("variableId")
        if not isinstance(variable, str) or variable not in assignment:
            raise ValueError("no assignment for guard variable {!r}".format(variable))
        return assignment[variable]
    if operator == "NOT":
        if len(children) != 1:
            raise ValueError("NOT guard must have exactly one child")
        return not _evaluate_guard(children[0], assignment)
    if operator == "AND":
        return all(_evaluate_guard(child, assignment) for child in children)
    if operator == "OR":
        return any(_evaluate_guard(child, assignment) for child in children)
    raise ValueError("unsupported guard operator {!r}".format(operator))


def _guard_ast(guard: object) -> object:
    if not isinstance(guard, dict) or "ast" not in guard:
        raise ValueError("guard is missing its structured AST")
    return guard["ast"]


def _protocol_name(protocol: str) -> str:
    return {
        "ISIS_L1": "isisL1",
        "ISIS_L2": "isisL2",
    }.get(protocol, protocol.lower())


def _symbolic_route_key(candidate: Mapping[str, object]) -> RouteKey:
    route = candidate.get("route")
    if not isinstance(route, dict):
        raise ValueError("symbolic candidate is missing typed route payload")
    attributes = route.get("attributes")
    if not isinstance(attributes, dict):
        raise ValueError("symbolic candidate route is missing attributes")
    protocol = _protocol_name(str(candidate.get("protocol")))
    next_hop_ip = str(attributes.get("nextHopIp", "AUTO/NONE(-1l)"))
    next_hop_interface = attributes.get("nextHopInterface")
    if next_hop_interface is None:
        next_hop_interface = "dynamic" if protocol in ("bgp", "ibgp") else "-"
    metric = int(attributes.get("metric", 0))
    administrative_cost = int(attributes.get("administrativeCost", 0))
    tag_value = int(attributes.get("tag", -1))
    tag = "-" if tag_value == -1 else str(tag_value)
    return (
        str(candidate.get("router")),
        str(candidate.get("vrf")),
        str(candidate.get("prefix")),
        protocol,
        next_hop_ip,
        str(next_hop_interface),
        metric,
        administrative_cost,
        tag,
    )


def _project_main_routes(
    control_plane: Mapping[str, object], assignment: Mapping[str, bool]
) -> Set[RouteKey]:
    projected: Set[RouteKey] = set()
    candidates = control_plane.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("control-plane export is missing candidates")
    for candidate_value in candidates:
        if not isinstance(candidate_value, dict) or candidate_value.get("plane") != "MAIN":
            continue
        if _evaluate_guard(_guard_ast(candidate_value.get("selectionGuard")), assignment):
            projected.add(_symbolic_route_key(candidate_value))
    return projected


def _parse_concrete_routes(path: pathlib.Path) -> Set[RouteKey]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError("cannot read {}: {}".format(path, error)) from error
    routes: Set[RouteKey] = set()
    for line_number, line in enumerate(lines[2:], start=3):
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 10:
            raise ValueError(
                "{}:{} expected 10 data-plane columns, found {}"
                .format(path, line_number, len(fields))
            )
        node, vrf, network, protocol, next_hop_ip, next_hop_interface = fields[:6]
        metric, administrative_cost, tag = fields[7:10]
        routes.add(
            (
                node,
                vrf,
                network,
                protocol,
                next_hop_ip,
                next_hop_interface,
                int(metric),
                int(administrative_cost),
                tag,
            )
        )
    return routes


def _sr_branch_key(record: Mapping[str, object]) -> SrBranchKey:
    return (
        record.get("node"),
        record.get("vrf"),
        record.get("color"),
        record.get("endpoint"),
        record.get("policy"),
        record.get("candidate"),
        record.get("preference"),
        record.get("weight"),
        record.get("segmentList"),
        tuple(record.get("labels", [])),
        tuple(record.get("nextHops", [])),
        tuple(record.get("linkDependencies", [])),
        record.get("terminalNode"),
        record.get("terminalVrf"),
    )


def _project_sr_branches(
    sr_export: Mapping[str, object], assignment: Mapping[str, bool]
) -> Set[SrBranchKey]:
    branches: Set[SrBranchKey] = set()
    records = sr_export.get("records")
    if not isinstance(records, list):
        raise ValueError("SR-policy export is missing records")
    for record_value in records:
        if not isinstance(record_value, dict) or record_value.get("kind") != "FORWARDING_BRANCH":
            continue
        if _evaluate_guard(record_value.get("selectionGuardAst"), assignment):
            branches.add(_sr_branch_key(record_value))
    return branches


def _all_up_sr_branches(
    sr_export: Mapping[str, object], explicit_values: Mapping[str, bool]
) -> Set[SrBranchKey]:
    assignment = _scenario_assignment(_variable_table(sr_export), [], explicit_values)
    return _project_sr_branches(sr_export, assignment)


def _parse_named_values(values: Iterable[str], option: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("{} requires NAME=VALUE, got {!r}".format(option, value))
        name, item = value.split("=", 1)
        if not name or not item or name in parsed:
            raise ValueError("invalid or duplicate {} value {!r}".format(option, value))
        parsed[name] = item
    return parsed


def _variable_table(control_plane: Mapping[str, object]) -> Dict[str, Mapping[str, object]]:
    variables = control_plane.get("guardVariables")
    if not isinstance(variables, list):
        raise ValueError("control-plane export is missing guardVariables")
    result: Dict[str, Mapping[str, object]] = {}
    for value in variables:
        if not isinstance(value, dict) or not isinstance(value.get("variableId"), str):
            raise ValueError("invalid guardVariables entry")
        variable = str(value["variableId"])
        if variable in result:
            raise ValueError("duplicate guard variable {!r}".format(variable))
        result[variable] = value
    return result


def _scenario_assignment(
    variables: Mapping[str, Mapping[str, object]],
    down_variables: Iterable[str],
    explicit_values: Mapping[str, bool],
) -> Dict[str, bool]:
    assignment: Dict[str, bool] = {}
    for variable, semantics in variables.items():
        if semantics.get("kind") == "LINK_AVAILABILITY" and semantics.get("polarity") == "UP":
            assignment[variable] = True
        elif variable in explicit_values:
            assignment[variable] = explicit_values[variable]
        else:
            raise ValueError(
                "uninterpreted variable {!r} requires --set VARIABLE=true|false".format(variable)
            )
    for variable in down_variables:
        semantics = variables.get(variable)
        if semantics is None:
            raise ValueError("unknown down-link guard variable {!r}".format(variable))
        if semantics.get("kind") != "LINK_AVAILABILITY" or semantics.get("polarity") != "UP":
            raise ValueError("down variable {!r} is not a link-UP variable".format(variable))
        assignment[variable] = False
    return assignment


def _diff(left: Set[Tuple[object, ...]], right: Set[Tuple[object, ...]]) -> Mapping[str, object]:
    missing = sorted(right - left, key=str)
    extra = sorted(left - right, key=str)
    return {"matches": not missing and not extra, "missing": missing, "extra": extra}


def _format_items(items: Sequence[object], limit: int = 20) -> List[str]:
    lines = ["    {}".format(item) for item in items[:limit]]
    if len(items) > limit:
        lines.append("    ... {} more".format(len(items) - limit))
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        required=True,
        type=pathlib.Path,
        help="all-scenarios symbolic output directory",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        metavar="NAME=OUTPUT_DIR",
        help="fresh concrete output to compare; may be repeated",
    )
    parser.add_argument(
        "--down",
        action="append",
        default=[],
        metavar="NAME=VAR[,VAR...]",
        help="link-UP variables assigned false in a named scenario",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="VARIABLE=BOOL",
        help="explicit assignment for an uninterpreted Boolean variable",
    )
    parser.add_argument("--report", type=pathlib.Path, help="optional JSON report path")
    args = parser.parse_args(argv)

    try:
        scenarios = _parse_named_values(args.scenario, "--scenario")
        if not scenarios:
            raise ValueError("at least one --scenario is required")
        down_values = _parse_named_values(args.down, "--down")
        unknown_scenarios = set(down_values) - set(scenarios)
        if unknown_scenarios:
            raise ValueError("--down names unknown scenarios: {}".format(sorted(unknown_scenarios)))
        explicit_text = _parse_named_values(args.set, "--set")
        explicit: Dict[str, bool] = {}
        for variable, value in explicit_text.items():
            if value.lower() not in ("true", "false"):
                raise ValueError("--set value for {!r} must be true or false".format(variable))
            explicit[variable] = value.lower() == "true"

        control_path = args.base / CONTROL_PLANE_FILE
        sr_path = args.base / SR_POLICY_FILE
        control_plane = _read_json(control_path)
        sr_export = _read_json(sr_path)
        _require_schema(control_plane, control_path, CONTROL_PLANE_SCHEMA, CONTROL_PLANE_VERSION)
        _require_schema(sr_export, sr_path, SR_POLICY_SCHEMA, SR_POLICY_VERSION)
        variables = _variable_table(control_plane)
        sr_variables = _variable_table(sr_export)
        for variable, semantics in sr_variables.items():
            if variable in variables and variables[variable] != semantics:
                raise ValueError(
                    "route and SR exports disagree on guard variable {!r}".format(variable)
                )
            variables[variable] = semantics

        report: MutableMapping[str, object] = {
            "base": str(args.base),
            "controlPlaneSchemaVersion": CONTROL_PLANE_VERSION,
            "srPolicySchemaVersion": SR_POLICY_VERSION,
            "scenarios": {},
        }
        passed = True
        for name, directory_text in scenarios.items():
            directory = pathlib.Path(directory_text)
            down = [value for value in down_values.get(name, "").split(",") if value]
            assignment = _scenario_assignment(variables, down, explicit)
            symbolic_routes = _project_main_routes(control_plane, assignment)
            concrete_routes = _parse_concrete_routes(directory / DATA_PLANE_FILE)
            route_diff = _diff(symbolic_routes, concrete_routes)

            scenario_sr_path = directory / SR_POLICY_FILE
            scenario_sr = _read_json(scenario_sr_path)
            _require_schema(scenario_sr, scenario_sr_path, SR_POLICY_SCHEMA, SR_POLICY_VERSION)
            symbolic_sr = _project_sr_branches(sr_export, assignment)
            concrete_sr = _all_up_sr_branches(scenario_sr, explicit)
            sr_diff = _diff(symbolic_sr, concrete_sr)
            scenario_passed = bool(route_diff["matches"] and sr_diff["matches"])
            passed = passed and scenario_passed
            report["scenarios"][name] = {
                "outputDirectory": str(directory),
                "downVariables": down,
                "assignment": assignment,
                "mainRib": route_diff,
                "srForwardingBranches": sr_diff,
                "passed": scenario_passed,
            }

            print("{}: {}".format(name, "PASS" if scenario_passed else "FAIL"))
            for label, comparison in (("MAIN RIB", route_diff), ("SR branches", sr_diff)):
                if comparison["matches"]:
                    print("  {}: match".format(label))
                    continue
                print("  {}: mismatch".format(label))
                for difference in ("missing", "extra"):
                    items = comparison[difference]
                    if items:
                        print("  {} from symbolic projection:".format(difference))
                        print("\n".join(_format_items(items)))

        report["passed"] = passed
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if passed else 1
    except ValueError as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    sys.exit(main())
