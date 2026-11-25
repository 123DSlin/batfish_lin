"""Connect device equations to an exported single-ingress reachability query."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import ipaddress
import json
from pathlib import Path
import re

from consistency.branch_loader import SymbolicRib
from utils.util_smt import parse_smt2_sexpr, serialize_smt2_sexpr as smt, tokenize_smt2_sexpr
from utils.util_symbolic import (
    SmtDocument,
    SubspecificationError,
    collect_declared_symbols,
)

SLICE_DIRECTORY = "1_sliced_device_smt_encoding"
FAILURE_PREFIX = "|0_FAILED-EDGE_"
REACHABILITY = re.compile(r"\|0__reachable(?:-id)?_[^|]+\|")
METRIC_DOMAIN_FILE = "0_metric_domains.json"
ENCODING_SEMANTICS_FILE = "0_encoding_semantics.json"


@dataclass(frozen=True)
class PropertyModel:
    document: SmtDocument
    destination: str
    ingress: str
    property_symbol: str
    failure_symbols: dict[str, str]
    forwarding: dict[str, dict[str, str]]
    community_width: int = 0
    community_indices: Mapping[str, int] = field(default_factory=dict)
    unused_config_fields: frozenset[str] = frozenset()
    metric_domains: Mapping[str, object] = field(default_factory=dict)
    encoding_semantics: Mapping[str, object] = field(default_factory=dict)


def load_encoding_semantics(work: Path) -> dict[str, object]:
    path = work / ENCODING_SEMANTICS_FILE
    if not path.exists():
        return {}
    try:
        policy = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise SubspecificationError(f'cannot read encoding semantics: {path}') from exc
    if (not isinstance(policy, dict) or policy.get('schema') != 'batfish-smt-encoding-semantics'
            or type(policy.get('version')) is not int or policy['version'] != 1
            or policy.get('symbolic_prefix_length_ranges') != 'variable-inclusive-bounds'):
        raise SubspecificationError('unsupported encoding semantics metadata')
    return policy


def load_metric_domains(work: Path) -> dict[str, object]:
    """Read exported domain assumptions; never rewrite legacy SMT constraints."""
    path = work / METRIC_DOMAIN_FILE
    if not path.exists():
        return dict(schema="unannotated-export", version=0, bgp_as_path_length="unspecified")
    try:
        policy = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise SubspecificationError(f"cannot read metric domain metadata: {path}") from exc
    expected = dict(schema="batfish-smt-metric-domains", version=1,
                    bgp_as_path_length="nonnegative-integer", bgp_only_best="nonnegative-integer",
                    environment_exclusive_upper_bound=256, other_metric_exclusive_upper_bound=65536)
    if (not isinstance(policy, dict) or any(type(policy.get(key)) is not type(value)
            or policy.get(key) != value for key, value in expected.items())
            or type(policy.get("model_overflow")) is not bool):
        raise SubspecificationError("unsupported or malformed metric domain metadata")
    return policy


def compose(documents: list[SmtDocument]) -> SmtDocument:
    declarations: dict[str, tuple[str, str]] = {}
    assertions = {}
    for document in documents:
        if document.definition_forms:
            raise SubspecificationError("property mode expects expanded device equations")
        for (name, sort), form in zip(document.declarations.items(), document.declaration_forms):
            if declarations.setdefault(name, (sort, form))[0] != sort:
                raise SubspecificationError(f"conflicting device declarations for {name}")
        assertions.update(dict.fromkeys(smt(expr) for expr in document.assertions))
    return SmtDocument.parse("\n".join([
        *(form for _, form in declarations.values()),
        *(f"(assert {expr})" for expr in assertions),
    ]))


def _data_plane_property(native, sliced, property_symbol):
    properties = {name for name in native.declarations if REACHABILITY.fullmatch(name)}
    if native.declarations.get(property_symbol) != "Bool" or property_symbol not in properties:
        raise SubspecificationError("missing exported reachability predicate")
    negated_query = ["not", ["and", "true", property_symbol]]
    if native.assertions.count(negated_query) != 1:
        raise SubspecificationError("expected exactly one native counterexample query")
    if properties & sliced.declarations.keys():
        raise SubspecificationError("device equations contain native reachability symbols")

    definitions = []
    for assertion in native.assertions:
        used = collect_declared_symbols(assertion, native.declarations)
        if assertion != negated_query and used & properties:
            unknown = {name for name in used - properties
                       if sliced.declarations.get(name) != native.declarations[name]}
            if unknown:
                raise SubspecificationError(
                    f"property references symbols outside the device equations: {sorted(unknown)}")
            definitions.append(assertion)
    if not any(property_symbol in collect_declared_symbols(expr, native.declarations)
               for expr in definitions):
        raise SubspecificationError("reachability predicate has no device-state definition")
    property_document = SmtDocument.parse("\n".join([
        *(form for name, form in zip(native.declarations, native.declaration_forms)
          if name in properties),
        *(f"(assert {smt(expr)})" for expr in definitions),
    ]))
    return compose([sliced, property_document])


def _encoded_budget(native, physical):
    budgets = []
    for expression in native.assertions:
        if (isinstance(expression, list) and len(expression) == 3 and expression[0] == "<="
                and isinstance(expression[1], list) and expression[1][0] == "+"
                and physical.issubset(expression[1][1:]) and str(expression[2]).isdigit()):
            budgets.append(int(expression[2]))
    if len(budgets) != 1:
        raise SubspecificationError("cannot identify a unique native physical-link budget")
    return budgets[0]


def _restore_unused_config_pins(native, slices):
    pin_indices = {pin.assertion_index for pin in native.config_pins}
    equations = [expr for i, expr in enumerate(native.assertions) if i not in pin_indices]
    equations += [parse_smt2_sexpr(tokenize_smt2_sexpr(form)) for form in native.definition_forms]
    referenced = set()
    for expr in equations:
        referenced.update(collect_declared_symbols(expr, native.declarations))
    unused = frozenset(pin.name for pin in native.config_pins if pin.name not in referenced)
    missing = unused - slices.declarations.keys()
    if missing:
        declarations = [form for name, form in zip(native.declarations, native.declaration_forms)
                        if name in missing]
        pins = [f"(assert {smt(native.assertions[pin.assertion_index])})"
                for pin in native.config_pins if pin.name in missing]
        slices = compose([slices, SmtDocument.parse("\n".join(declarations + pins))])
    return slices, unused


def load_property_model(work: Path, k: int, *, include_unused_configs: bool = False) -> PropertyModel:
    if (work / "0_protocols.txt").read_text().strip().lower() != "bgp":
        raise SubspecificationError("property mode currently supports BGP-only exports")
    if (work / "0_model_igp.txt").read_text().strip() != "0":
        raise SubspecificationError("property mode currently requires IGP modeling disabled")
    props = (work / "0_properties_variables.txt").read_text().split()
    if len(props) != 1 or not re.fullmatch(r"\|0__reachable_[^|]+\|", props[0]):
        raise SubspecificationError("expected one native ingress reachability property")
    property_symbol = props[0]
    ingress = property_symbol.removeprefix("|0__reachable_").removesuffix("|")
    destinations = (work / "0_dst_ips.txt").read_text().split()
    if len(destinations) != 1:
        raise SubspecificationError("expected one exported IPv4 destination address")
    try:
        destination = ipaddress.IPv4Network(destinations[0])
        if destination.prefixlen != 32:
            raise ValueError("destination is not a singleton")
    except ValueError as exc:
        raise SubspecificationError("property mode currently supports a single IPv4 /32") from exc

    rib = SymbolicRib.from_work_directory(work)
    routers = set(rib.topology.routers())
    hostnames = set((work / "0_hostnames.txt").read_text().split())
    if routers != hostnames or ingress not in routers:
        raise SubspecificationError("expected every device to participate in the exported eBGP topology")
    native = SmtDocument.parse((work / "smt_encoding.smt2").read_text())
    slices = compose([
        SmtDocument.parse((work / SLICE_DIRECTORY / f"sliced_{router}_smt_encoding.smt2").read_text())
        for router in sorted(routers)
    ])
    unused = frozenset()
    if include_unused_configs:
        slices, unused = _restore_unused_config_pins(native, slices)
    document = _data_plane_property(native, slices, property_symbol)

    edges = {}
    for variable in rib.guard_variables:
        endpoints = tuple(sorted((variable.first_router, variable.second_router)))
        if endpoints[0] == endpoints[1] or endpoints in edges:
            raise SubspecificationError(f"non-unique physical link guard for {endpoints}")
        candidates = [f"{FAILURE_PREFIX}{a}_{b}|" for a, b in (endpoints, endpoints[::-1])]
        recorded = [name for name in candidates if document.declarations.get(name) == "Int"]
        if len(recorded) != 1:
            raise SubspecificationError(f"expected one integer failure symbol for link {endpoints}")
        edges[endpoints] = recorded[0]
    if not edges:
        raise SubspecificationError("missing physical-link failure inventory")

    forwarding = {}
    topology_edges = set()
    for router in sorted(routers):
        next_hops = {}
        for link in sorted(rib.topology.links(router), key=lambda item: item.remote.router):
            peer = link.remote.router
            topology_edges.add(tuple(sorted((router, peer))))
            data = f"|0_DATA-FORWARDING_{router}_{link.local.interface}|"
            if peer in next_hops or document.declarations.get(data) != "Bool":
                raise SubspecificationError(f"unsupported forwarding adjacency {router}->{peer}")
            next_hops[peer] = data
        forwarding[router] = next_hops
    if topology_edges != set(edges):
        raise SubspecificationError("eBGP topology and physical failure inventory differ")
    physical = set(edges.values())
    if k > _encoded_budget(native, physical):
        raise SubspecificationError("requested fault budget exceeds the input encoding; regenerate the input")

    for name in document.declarations:
        if name.startswith((FAILURE_PREFIX, "|0_FAILED-NODE_")) and name not in physical:
            if ["=", name, "0"] not in document.assertions:
                raise SubspecificationError(f"non-physical failure symbol is not fixed to zero: {name}")

    return PropertyModel(document, destination.with_prefixlen, ingress, property_symbol,
                         {"--".join(key): edges[key] for key in sorted(edges)}, forwarding,
                         rib.community_width, rib.community_indices, unused, load_metric_domains(work),
                         load_encoding_semantics(work))
