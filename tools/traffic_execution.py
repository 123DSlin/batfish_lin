#!/usr/bin/env python3
"""Traffic layer on top of a converged symbolic control plane.

Control-plane convergence never consumes traffic.json. This module has two engines
that share one load schema:

1. Concrete enumerator: hop-by-hop on one failure assignment, using the projected
   MAIN RIB and surviving SR forwarding branches.
2. Symbolic traffic execution: YU-style forwarding over selection-guard ASTs, with
   SR weights kept as the integer parameter h. Evaluating the result at an assignment
   must match the concrete enumerator.

Neither engine encodes Minesweeper CONTROL-FORWARDING SMT. auto-netsubspec consumes
the resulting per-link affine loads as a traffic-property subspec.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import pathlib
import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


CONTROL_PLANE_FILE = "0_symbolic_control_plane.json"
SR_POLICY_FILE = "0_symbolic_sr_policies.json"
TRAFFIC_FILE = "0_traffic.json"
CONTROL_PLANE_SCHEMA = "batfish-minesweeper-symbolic-control-plane"
CONTROL_PLANE_VERSION = 2
SR_POLICY_SCHEMA = "batfish-minesweeper-symbolic-sr-policies"
SR_POLICY_VERSION = 1

LinkId = str
Node = str
Affine = Tuple[Fraction, Fraction]  # const + coeff * h, h in [0, 100]


def _read_json(path: pathlib.Path) -> Mapping[str, object]:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("cannot read {}: {}".format(path, error)) from error
    if not isinstance(value, dict):
        raise ValueError("{} must contain a JSON object".format(path))
    return value


def _require_schema(document: Mapping[str, object], path: pathlib.Path, schema: str, version: int) -> None:
    if document.get("schemaName") != schema or document.get("schemaVersion") != version:
        raise ValueError(
            "{} requires schema {!r} version {}".format(path, schema, version)
        )


def evaluate_guard(ast: object, assignment: Mapping[str, bool]) -> bool:
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
        return not evaluate_guard(children[0], assignment)
    if operator == "AND":
        return all(evaluate_guard(child, assignment) for child in children)
    if operator == "OR":
        return any(evaluate_guard(child, assignment) for child in children)
    raise ValueError("unsupported guard operator {!r}".format(operator))


def guard_ast(guard: object) -> object:
    if not isinstance(guard, dict) or "ast" not in guard:
        raise ValueError("guard is missing its structured AST")
    return guard["ast"]


def guard_variables(ast: object) -> Set[str]:
    if not isinstance(ast, dict):
        return set()
    operator = ast.get("operator")
    if operator == "VARIABLE" and isinstance(ast.get("variableId"), str):
        return {ast["variableId"]}
    variables: Set[str] = set()
    for child in ast.get("children", []):
        variables.update(guard_variables(child))
    return variables


def zero() -> Affine:
    return (Fraction(0), Fraction(0))


def add_affine(left: Affine, right: Affine) -> Affine:
    return (left[0] + right[0], left[1] + right[1])


def scale_affine(value: Affine, factor: Fraction) -> Affine:
    return (value[0] * factor, value[1] * factor)


def affine_at(value: Affine, h: int) -> Fraction:
    return value[0] + value[1] * h


def affine_to_json(value: Affine) -> Mapping[str, object]:
    const, coeff = value
    return {
        "constGbps": float(const),
        "hCoeffGbps": float(coeff),
        "asFractions": {"const": str(const), "hCoeff": str(coeff)},
    }


@dataclass(frozen=True)
class Link:
    link_id: str
    node1: str
    node2: str
    capacity: Fraction

    def other(self, node: str) -> str:
        if node == self.node1:
            return self.node2
        if node == self.node2:
            return self.node1
        raise ValueError("{} is not an endpoint of {}".format(node, self.link_id))

    def incident(self, node: str) -> bool:
        return node in (self.node1, self.node2)


@dataclass
class WeightVariable:
    name: str
    minimum: int
    maximum: int
    initial: int
    upper_candidate: str
    lower_candidate: str


@dataclass
class Flow:
    flow_id: str
    source: str
    destination: ipaddress.IPv4Network
    demand: Fraction
    forwarding: str
    color: Optional[int] = None
    policy: Optional[str] = None


@dataclass
class TrafficModel:
    links: Dict[str, Link]
    flows: List[Flow]
    weight: WeightVariable
    capacity_operator: str
    expected_subspec: str

    def link_between(self, left: str, right: str) -> Link:
        for link in self.links.values():
            if {link.node1, link.node2} == {left, right}:
                return link
        raise ValueError("no traffic.json link between {} and {}".format(left, right))

    def links_at(self, node: str) -> List[Link]:
        return [link for link in self.links.values() if link.incident(node)]


def load_traffic(path: pathlib.Path) -> TrafficModel:
    document = _read_json(path)
    links = {}
    for item in document.get("links", []):
        if not isinstance(item, dict):
            continue
        endpoint1 = item["endpoint1"]["node"]
        endpoint2 = item["endpoint2"]["node"]
        links[str(item["id"])] = Link(
            str(item["id"]),
            str(endpoint1),
            str(endpoint2),
            Fraction(item["capacityGbps"]),
        )
    flows = []
    for item in document.get("flows", []):
        destination = ipaddress.ip_network(item["destination"], strict=False)
        if not isinstance(destination, ipaddress.IPv4Network):
            raise ValueError("only IPv4 flow destinations are supported")
        flows.append(
            Flow(
                str(item["id"]),
                str(item["source"]),
                destination,
                Fraction(item["demandGbps"]),
                str(item["forwarding"]),
                item.get("color"),
                item.get("policy"),
            )
        )
    weight_raw = document["weightVariable"]
    property_raw = document.get("property", {})
    return TrafficModel(
        links=links,
        flows=flows,
        weight=WeightVariable(
            str(weight_raw["name"]),
            int(weight_raw["minimum"]),
            int(weight_raw["maximum"]),
            int(weight_raw["initial"]),
            str(weight_raw["upperCandidate"]),
            str(weight_raw["lowerCandidate"]),
        ),
        capacity_operator=str(property_raw.get("operator", "<")),
        expected_subspec=str(property_raw.get("expectedSubspecWithinDomain", "")),
    )


@dataclass
class MainBranch:
    router: str
    prefix: ipaddress.IPv4Network
    next_hop: Optional[str]
    metric: int
    protocol: str
    selection_ast: object
    local: bool


def prefix_covers(prefix: ipaddress.IPv4Network, destination: ipaddress.IPv4Network) -> bool:
    return (
        destination.network_address in prefix
        and destination.prefixlen >= prefix.prefixlen
    )


def _next_hop_node(candidate: Mapping[str, object]) -> Optional[str]:
    contributions = candidate.get("contributions") or []
    if not contributions:
        return None
    provenance = contributions[0].get("provenance") or {}
    previous = provenance.get("previousRouter")
    current = provenance.get("currentRouter") or candidate.get("router")
    if previous in (None, current):
        return None
    return str(previous)


def load_main_branches(control_plane: Mapping[str, object]) -> List[MainBranch]:
    branches: List[MainBranch] = []
    for candidate in control_plane.get("candidates", []):
        if not isinstance(candidate, dict) or candidate.get("plane") != "MAIN":
            continue
        prefix = ipaddress.ip_network(str(candidate["prefix"]), strict=False)
        if not isinstance(prefix, ipaddress.IPv4Network):
            continue
        protocol = str(candidate.get("protocol", ""))
        branches.append(
            MainBranch(
                router=str(candidate["router"]),
                prefix=prefix,
                next_hop=_next_hop_node(candidate),
                metric=int((candidate.get("route") or {}).get("attributes", {}).get("metric", 0)),
                protocol=protocol,
                selection_ast=guard_ast(candidate.get("selectionGuard")),
                local=protocol in ("CONNECTED", "LOCAL") or _next_hop_node(candidate) is None,
            )
        )
    return branches


@dataclass
class SrBranch:
    node: str
    policy: str
    color: int
    candidate: str
    segment_list: str
    weight: int
    selection_ast: object
    path_links: List[str]


def _order_path_links(traffic: TrafficModel, start: str, terminal: str, link_ids: Set[str]) -> List[str]:
    remaining = set(link_ids)
    ordered: List[str] = []
    current = start
    while remaining:
        incident = [link_id for link_id in remaining if traffic.links[link_id].incident(current)]
        if len(incident) != 1:
            raise ValueError(
                "cannot uniquely walk SR path from {} with remaining links {}".format(
                    current, sorted(remaining)
                )
            )
        link_id = incident[0]
        ordered.append(link_id)
        current = traffic.links[link_id].other(current)
        remaining.remove(link_id)
        if current == terminal:
            break
    if current != terminal:
        raise ValueError("SR path from {} did not reach {}".format(start, terminal))
    return ordered


def load_sr_branches(sr_export: Mapping[str, object], traffic: TrafficModel) -> List[SrBranch]:
    variables = {
        item["variableId"]: item
        for item in sr_export.get("guardVariables") or []
        if isinstance(item, dict) and item.get("kind") == "LINK_AVAILABILITY"
    }
    branches: List[SrBranch] = []
    for record in sr_export.get("records") or []:
        if not isinstance(record, dict) or record.get("kind") != "FORWARDING_BRANCH":
            continue
        ast = record.get("selectionGuardAst")
        link_ids = {variable for variable in guard_variables(ast) if variable in traffic.links}
        terminal = str(record.get("terminalNode") or "")
        path = _order_path_links(traffic, str(record["node"]), terminal, link_ids) if link_ids else []
        branches.append(
            SrBranch(
                node=str(record["node"]),
                policy=str(record["policy"]),
                color=int(record["color"]),
                candidate=str(record["candidate"]),
                segment_list=str(record["segmentList"]),
                weight=int(record["weight"]),
                selection_ast=ast,
                path_links=path,
            )
        )
    return branches


def selected_ip_nexthops(
    branches: Sequence[MainBranch],
    router: str,
    destination: ipaddress.IPv4Network,
    assignment: Mapping[str, bool],
) -> List[str]:
    matching = [
        branch
        for branch in branches
        if branch.router == router
        and prefix_covers(branch.prefix, destination)
        and evaluate_guard(branch.selection_ast, assignment)
    ]
    if not matching:
        return []
    longest = max(branch.prefix.prefixlen for branch in matching)
    longest_matches = [branch for branch in matching if branch.prefix.prefixlen == longest]
    if any(branch.local for branch in longest_matches):
        return []
    nexthops = []
    seen = set()
    for branch in sorted(longest_matches, key=lambda item: (item.metric, item.next_hop or "")):
        if branch.next_hop and branch.next_hop not in seen:
            seen.add(branch.next_hop)
            nexthops.append(branch.next_hop)
    return nexthops


def walk_ip_flow(
    traffic: TrafficModel,
    branches: Sequence[MainBranch],
    flow: Flow,
    assignment: Mapping[str, bool],
) -> Dict[str, Affine]:
    loads = {link_id: zero() for link_id in traffic.links}
    stack = [(flow.source, flow.demand, {flow.source})]
    while stack:
        node, volume, seen = stack.pop()
        dest_host = ipaddress.ip_network(str(flow.destination.network_address) + "/32")
        nexthops = selected_ip_nexthops(branches, node, dest_host, assignment)
        if not nexthops:
            continue
        share = volume / len(nexthops)
        for nexthop in nexthops:
            if nexthop in seen:
                raise ValueError("forwarding loop at {} -> {}".format(node, nexthop))
            link = traffic.link_between(node, nexthop)
            loads[link.link_id] = add_affine(loads[link.link_id], (share, Fraction(0)))
            stack.append((nexthop, share, seen | {nexthop}))
    return loads


def _candidate_matches(branch: SrBranch, token: str) -> bool:
    token = token.lower()
    return token in branch.candidate.lower() or token in branch.segment_list.lower()


def sr_split(
    traffic: TrafficModel,
    branches: Sequence[SrBranch],
    flow: Flow,
    assignment: Mapping[str, bool],
) -> List[Tuple[SrBranch, Affine]]:
    selected = [
        branch
        for branch in branches
        if branch.node == flow.source
        and (flow.policy is None or branch.policy == flow.policy)
        and (flow.color is None or branch.color == flow.color)
        and evaluate_guard(branch.selection_ast, assignment)
    ]
    if not selected:
        return []
    upper = [branch for branch in selected if _candidate_matches(branch, traffic.weight.upper_candidate)]
    lower = [branch for branch in selected if _candidate_matches(branch, traffic.weight.lower_candidate)]
    if len(upper) + len(lower) != len(selected):
        raise ValueError("SR branches are not partitioned by the traffic.json weightVariable")
    demand = flow.demand
    h_name = traffic.weight.name
    del h_name
    if upper and lower:
        #  demand * h/100 on each upper branch, demand * (100-h)/100 on lower.
        upper_share = (Fraction(0), demand / 100)
        lower_share = (demand, -demand / 100)
        return [(branch, scale_affine(upper_share, Fraction(1, len(upper)))) for branch in upper] + [
            (branch, scale_affine(lower_share, Fraction(1, len(lower)))) for branch in lower
        ]
    share = (demand / len(selected), Fraction(0))
    return [(branch, share) for branch in selected]


def walk_sr_flow(
    traffic: TrafficModel,
    branches: Sequence[SrBranch],
    flow: Flow,
    assignment: Mapping[str, bool],
) -> Dict[str, Affine]:
    loads = {link_id: zero() for link_id in traffic.links}
    for branch, volume in sr_split(traffic, branches, flow, assignment):
        for link_id in branch.path_links:
            loads[link_id] = add_affine(loads[link_id], volume)
    return loads


def execute_on_control_plane(
    traffic: TrafficModel,
    main_branches: Sequence[MainBranch],
    sr_branches: Sequence[SrBranch],
    assignment: Mapping[str, bool],
) -> Dict[str, Affine]:
    loads = {link_id: zero() for link_id in traffic.links}
    for flow in traffic.flows:
        if flow.forwarding == "IP":
            flow_loads = walk_ip_flow(traffic, main_branches, flow, assignment)
        elif flow.forwarding == "SR_POLICY":
            flow_loads = walk_sr_flow(traffic, sr_branches, flow, assignment)
        else:
            raise ValueError("unsupported forwarding mode {}".format(flow.forwarding))
        for link_id, value in flow_loads.items():
            loads[link_id] = add_affine(loads[link_id], value)
    return loads


def parse_dataplane_routes(path: pathlib.Path) -> Dict[str, List[Mapping[str, object]]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError("cannot read {}: {}".format(path, error)) from error
    routes: Dict[str, List[Mapping[str, object]]] = {}
    for line_number, line in enumerate(lines[2:], start=3):
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 10:
            raise ValueError("{}:{} expected 10 columns".format(path, line_number))
        node, _vrf, network, protocol, _nh_ip, _nh_iface, next_hop, metric, _ad, _tag = fields
        routes.setdefault(node, []).append(
            {
                "prefix": ipaddress.ip_network(network, strict=False),
                "protocol": protocol,
                "nextHop": None if next_hop in ("null", "-", "AUTO/NONE(-1l)") else next_hop,
                "metric": int(metric),
                "local": protocol in ("connected", "local"),
            }
        )
    return routes


def dataplane_nexthops(
    routes: Mapping[str, Sequence[Mapping[str, object]]],
    router: str,
    destination: ipaddress.IPv4Network,
) -> List[str]:
    matching = [
        route
        for route in routes.get(router, [])
        if isinstance(route["prefix"], ipaddress.IPv4Network)
        and prefix_covers(route["prefix"], destination)
    ]
    if not matching:
        return []
    longest = max(route["prefix"].prefixlen for route in matching)
    longest_matches = [route for route in matching if route["prefix"].prefixlen == longest]
    if any(route["local"] or route["nextHop"] is None for route in longest_matches):
        return []
    nexthops = []
    seen = set()
    for route in sorted(longest_matches, key=lambda item: (item["metric"], item["nextHop"] or "")):
        nexthop = route["nextHop"]
        if nexthop and nexthop not in seen:
            seen.add(nexthop)
            nexthops.append(nexthop)
    return nexthops


def walk_ip_from_dataplane(
    traffic: TrafficModel,
    routes: Mapping[str, Sequence[Mapping[str, object]]],
    flow: Flow,
    destination: ipaddress.IPv4Network,
) -> Dict[str, Affine]:
    loads = {link_id: zero() for link_id in traffic.links}
    stack = [(flow.source, flow.demand, {flow.source})]
    while stack:
        node, volume, seen = stack.pop()
        nexthops = dataplane_nexthops(routes, node, destination)
        if not nexthops:
            continue
        share = volume / len(nexthops)
        for nexthop in nexthops:
            if nexthop in seen:
                raise ValueError("dataplane forwarding loop at {} -> {}".format(node, nexthop))
            link = traffic.link_between(node, nexthop)
            loads[link.link_id] = add_affine(loads[link.link_id], (share, Fraction(0)))
            stack.append((nexthop, share, seen | {nexthop}))
    return loads


def execute_concrete_dataplane(
    traffic: TrafficModel,
    dataplane_routes: Mapping[str, Sequence[Mapping[str, object]]],
    sr_branches: Sequence[SrBranch],
    assignment: Mapping[str, bool],
) -> Dict[str, Affine]:
    """Manual baseline: concrete MAIN forwarding table plus surviving SR branches."""
    loads = {link_id: zero() for link_id in traffic.links}
    host_dest = ipaddress.ip_network("0.0.0.0/32")  # replaced per flow
    for flow in traffic.flows:
        destination = ipaddress.ip_network(str(flow.destination.network_address) + "/32")
        if flow.forwarding == "IP":
            flow_loads = walk_ip_from_dataplane(traffic, dataplane_routes, flow, destination)
        elif flow.forwarding == "SR_POLICY":
            flow_loads = walk_sr_flow(traffic, sr_branches, flow, assignment)
        else:
            raise ValueError("unsupported forwarding mode {}".format(flow.forwarding))
        for link_id, value in flow_loads.items():
            loads[link_id] = add_affine(loads[link_id], value)
    del host_dest
    return loads


def all_up_assignment(traffic: TrafficModel) -> Dict[str, bool]:
    return {link_id: True for link_id in traffic.links}


def scenario_assignment(traffic: TrafficModel, down: Iterable[str]) -> Dict[str, bool]:
    assignment = all_up_assignment(traffic)
    for variable in down:
        if variable not in assignment:
            raise ValueError("unknown down-link {}".format(variable))
        assignment[variable] = False
    return assignment


def _safe_interval(load: Affine, capacity: Fraction) -> Optional[Tuple[int, int]]:
    const, coeff = load
    if coeff == 0:
        return (0, 100) if const < capacity else None
    limit = (capacity - const) / coeff
    lo, hi = 0, 100
    if coeff > 0:
        hi = int(limit) - 1 if limit == int(limit) else int(limit)
    elif limit < 0:
        lo = 0
    else:
        lo = int(limit) + 1
    if lo > hi:
        return None
    return (max(0, lo), min(100, hi))


def intersect_intervals(intervals: Sequence[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    lo = 0
    hi = 100
    for left, right in intervals:
        lo = max(lo, left)
        hi = min(hi, right)
    return (lo, hi) if lo <= hi else None


def format_interval(interval: Optional[Tuple[int, int]], name: str) -> str:
    if interval is None:
        return "{} unsatisfiable".format(name)
    lo, hi = interval
    if lo == 0 and hi == 100:
        return "{} unrestricted".format(name)
    if lo == 0:
        return "{} <= {}".format(name, hi)
    if hi == 100:
        return "{} >= {}".format(name, lo)
    return "{} <= {} <= {}".format(lo, name, hi)


def derive_subspec(
    traffic: TrafficModel,
    scenario_loads: Mapping[str, Mapping[str, Affine]],
) -> Mapping[str, object]:
    intervals = []
    per_scenario = {}
    for name, loads in scenario_loads.items():
        scenario_intervals = []
        binding = []
        for link_id, load in loads.items():
            interval = _safe_interval(load, traffic.links[link_id].capacity)
            if interval is None:
                scenario_intervals.append((-1, -2))
                binding.append({"link": link_id, "constraint": "unsatisfiable"})
                continue
            if interval != (0, 100):
                scenario_intervals.append(interval)
                binding.append(
                    {
                        "link": link_id,
                        "constraint": format_interval(interval, traffic.weight.name),
                        "load": affine_to_json(load),
                    }
                )
        combined = intersect_intervals(scenario_intervals) if scenario_intervals else (0, 100)
        if scenario_intervals and any(item == (-1, -2) for item in scenario_intervals):
            combined = None
        per_scenario[name] = {
            "constraint": format_interval(combined, traffic.weight.name),
            "bindingLinks": binding,
        }
        if combined is None:
            intervals.append((-1, -2))
        else:
            intervals.append(combined)
    overall = None if any(item == (-1, -2) for item in intervals) else intersect_intervals(intervals)
    return {
        "variable": traffic.weight.name,
        "domain": [traffic.weight.minimum, traffic.weight.maximum],
        "faultTolerantSubspec": format_interval(overall, traffic.weight.name),
        "expectedSubspec": traffic.expected_subspec,
        "matchesExpected": format_interval(overall, traffic.weight.name) == traffic.expected_subspec,
        "perScenario": per_scenario,
    }


def loads_to_json(loads: Mapping[str, Affine]) -> Mapping[str, object]:
    return {link_id: affine_to_json(value) for link_id, value in sorted(loads.items())}


def compare_loads(left: Mapping[str, Affine], right: Mapping[str, Affine]) -> Mapping[str, object]:
    missing = sorted(set(right) - set(left))
    extra = sorted(set(left) - set(right))
    mismatched = []
    for link_id in sorted(set(left) & set(right)):
        if left[link_id] != right[link_id]:
            mismatched.append(
                {
                    "link": link_id,
                    "concrete": affine_to_json(left[link_id]),
                    "symbolic": affine_to_json(right[link_id]),
                }
            )
    return {
        "matches": not missing and not extra and not mismatched,
        "missing": missing,
        "extra": extra,
        "mismatched": mismatched,
    }


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


def run_engines(
    base: pathlib.Path,
    scenarios: Mapping[str, Tuple[pathlib.Path, Sequence[str]]],
) -> Mapping[str, object]:
    traffic = load_traffic(base / TRAFFIC_FILE)
    control_plane = _read_json(base / CONTROL_PLANE_FILE)
    sr_export = _read_json(base / SR_POLICY_FILE)
    _require_schema(control_plane, base / CONTROL_PLANE_FILE, CONTROL_PLANE_SCHEMA, CONTROL_PLANE_VERSION)
    _require_schema(sr_export, base / SR_POLICY_FILE, SR_POLICY_SCHEMA, SR_POLICY_VERSION)
    main_branches = load_main_branches(control_plane)
    symbolic_sr = load_sr_branches(sr_export, traffic)

    scenario_loads = {}
    report_scenarios = {}
    passed = True
    for name, (directory, down) in scenarios.items():
        assignment = scenario_assignment(traffic, down)
        concrete_sr_doc = _read_json(directory / SR_POLICY_FILE)
        _require_schema(concrete_sr_doc, directory / SR_POLICY_FILE, SR_POLICY_SCHEMA, SR_POLICY_VERSION)
        concrete_sr = load_sr_branches(concrete_sr_doc, traffic)
        concrete_assignment = {
            link_id: True for link_id in traffic.links if link_id not in set(down)
        }
        for link_id in down:
            concrete_assignment[link_id] = False
        dataplane = parse_dataplane_routes(directory / "0_data_plane.txt")
        concrete = execute_concrete_dataplane(traffic, dataplane, concrete_sr, concrete_assignment)
        symbolic = execute_on_control_plane(traffic, main_branches, symbolic_sr, assignment)
        comparison = compare_loads(concrete, symbolic)
        scenario_loads[name] = symbolic
        scenario_passed = comparison["matches"]
        passed = passed and scenario_passed
        report_scenarios[name] = {
            "outputDirectory": str(directory),
            "downVariables": list(down),
            "assignment": assignment,
            "concreteLoads": loads_to_json(concrete),
            "symbolicLoads": loads_to_json(symbolic),
            "numericAtInitialH": {
                link_id: float(affine_at(value, traffic.weight.initial))
                for link_id, value in symbolic.items()
            },
            "enginesMatch": comparison,
            "passed": scenario_passed,
        }
        print("{}: {}".format(name, "PASS" if scenario_passed else "FAIL"))
        if not scenario_passed:
            print("  {}".format(json.dumps(comparison, indent=2, sort_keys=True)))
    subspec = derive_subspec(traffic, scenario_loads)
    print("fault-tolerant subspec: {}".format(subspec["faultTolerantSubspec"]))
    print("expected: {}".format(subspec["expectedSubspec"]))
    return {
        "base": str(base),
        "passed": passed and bool(subspec["matchesExpected"]),
        "enginesMatch": passed,
        "subspec": subspec,
        "scenarios": report_scenarios,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=pathlib.Path)
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        metavar="NAME=OUTPUT_DIR",
        help="concrete failure output directory; may be repeated",
    )
    parser.add_argument(
        "--down",
        action="append",
        default=[],
        metavar="NAME=VAR[,VAR...]",
        help="link-UP variables assigned false in a named scenario",
    )
    parser.add_argument("--report", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        scenario_dirs = _parse_named_values(args.scenario, "--scenario")
        if not scenario_dirs:
            raise ValueError("at least one --scenario is required")
        down_values = _parse_named_values(args.down, "--down")
        unknown = set(down_values) - set(scenario_dirs)
        if unknown:
            raise ValueError("--down names unknown scenarios: {}".format(sorted(unknown)))
        scenarios = {
            name: (
                pathlib.Path(directory),
                [item for item in down_values.get(name, "").split(",") if item],
            )
            for name, directory in scenario_dirs.items()
        }
        report = run_engines(args.base, scenarios)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if report["passed"] else 1
    except ValueError as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    sys.exit(main())
