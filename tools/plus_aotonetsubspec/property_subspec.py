"""Property subspecification entry points and finite-domain regression oracle."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from itertools import combinations, groupby, product
import ipaddress
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

from property_model import ENCODING_SEMANTICS_FILE, METRIC_DOMAIN_FILE, PropertyModel, load_property_model
from property_regions import RegionSolver, domain_contains, full_model
from configuration_domains import (
    DomainTargets, IntegerDomain, SYMBOLIC_DOMAINS, numeric_domain, prefix_domains, specialize_targets,
)
from region_smt import QueryRunner, RegionFailure, ast, require_config_formula
from property_reports import config_owner, prepend_lines, write_subspecs
from slicing.bgp import BgpSliceAdapter
from utils.util_smt import parse_smt2_sexpr, serialize_smt2_sexpr as smt, tokenize_smt2_sexpr
from utils.util_symbolic import (
    SmtDocument,
    SmtSolver,
    SubspecificationError,
    and_expression,
    config_line_group,
    substitute_symbols,
)

INPUT_FILES = (*BgpSliceAdapter().required_input_files(), "0_protocols.txt",
               "0_model_igp.txt", "0_properties_variables.txt")
OPERATIONS = ("prepend_aspath_enable", "prepend_aspath_cost")


def _assertions(expressions):
    return [f"(assert {smt(expression)})" for expression in expressions]


def _equalities(values):
    return _assertions(["=", name, value] for name, value in values.items())


def _smt_value(value):
    return ("true" if value else "false") if isinstance(value, bool) else str(value)


def _community_target_tag(name):
    line = config_line_group(name)
    if line is None:
        return None
    if "_CommunityList_" in line:
        prefix = ""
    elif "_RoutingPolicy_" in line:
        prefix = "set_community_"
    else:
        return None
    match = re.fullmatch(prefix + r"(\d+)_(\d+)__community", name.removeprefix(line + "__"))
    return ":".join(match.groups()) if match else None


def _community_domain(model, pin, original_tag):
    width = model.community_width
    indices = model.community_indices
    if width <= 0 or pin.sort != f"(_ BitVec {width})":
        raise SubspecificationError(f"community index width disagrees with {pin.name}")
    if len(set(indices.values())) != len(indices):
        raise SubspecificationError("community index contains duplicate bit positions")
    values = {}
    for tag, index in sorted(indices.items(), key=lambda entry: entry[1]):
        if re.fullmatch(r"\d+:\d+", tag) and all(int(part) <= 65535 for part in tag.split(":")):
            mask = 1 << index
            values[tag] = f"#x{mask:0{width // 4}x}" if width % 4 == 0 else f"#b{mask:0{width}b}"
    if original_tag not in values:
        raise SubspecificationError(f"community {original_tag} is missing from the exact index")
    original_mask = 1 << indices[original_tag]
    if pin.original_value.lower() not in {
        values[original_tag], f"#b{original_mask:0{width}b}", f"(_ bv{original_mask} {width})"
    }:
        raise SubspecificationError(f"original community pin does not encode {original_tag}: {pin.name}")
    values[original_tag] = pin.original_value
    return values


def _parse_pins(model, requested, cost_range):
    pins = {p.name: p for p in model.document.config_pins}
    if not requested or len(requested) != len(set(requested)):
        raise SubspecificationError("specify each target field exactly once")
    missing = set(requested) - pins.keys()
    if missing:
        raise SubspecificationError(f"unrecognized target configuration fields: {sorted(missing)}")
    missing_pins = {name for name in model.document.declarations
                    if name.startswith("Config_") and name not in pins}
    if missing_pins:
        raise SubspecificationError(f"configurations without an original value: {sorted(missing_pins)}")

    if len(requested) == 1 and (tag := _community_target_tag(requested[0])) is not None:
        if cost_range is not None:
            raise SubspecificationError("--cost-range requires a prepend cost target")
        pin = pins[requested[0]]
        return [(pin, tuple(_community_domain(model, pin, tag).values()))]

    lines = {config_line_group(name) for name in requested}
    if len(lines) != 1 or None in lines:
        raise SubspecificationError("target fields must belong to the same configuration statement")
    if cost_range is not None and not any(name.endswith('__prepend_aspath_cost') for name in requested):
        raise SubspecificationError("--cost-range requires a prepend cost target")
    line = next(iter(lines))
    if '_RouteFilterList_' in line:
        complete = prefix_domains([pin for pin in pins.values() if config_line_group(pin.name) == line])
        return specialize_targets(complete, requested)
    return DomainTargets([(pins[name], numeric_domain(pins[name], cost_range)) for name in sorted(requested)])


def _model_commands(model, targets, k):
    released = {pin.assertion_index for pin, _ in targets}
    return _assertions(expr for i, expr in enumerate(model.document.assertions)
                       if i not in released) + _scenario_commands(model, k)


def _scenario_commands(model, k):
    address = model.destination.split("/")[0]
    address_hex = "".join(f"{int(octet):02x}" for octet in address.split("."))
    physical = list(model.failure_symbols.values())
    return _equalities({"|0_dst-ip|": f"#x{address_hex}"}) + _assertions(
        [["or", ["=", edge, "0"], ["=", edge, "1"]] for edge in physical]
        + [["<=", ["+", "0", *physical], str(k)]]
    )


def _run_query(model, commands, name, output, solver, timeout):
    path = output / f"{name}.smt2"
    path.write_text(model.document.query(*commands))
    try:
        result = subprocess.run([str(solver), str(path)], text=True, capture_output=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SubspecificationError(f"{name} exceeded {timeout:g} seconds") from exc
    (output / f"{name}.log").write_text(result.stdout + result.stderr)
    if result.returncode or result.stderr or "(error " in result.stdout:
        raise SubspecificationError(f"{name} failed; see {name}.log")
    return result.stdout.strip()


def _certify_slice(model, work, targets, assignments, k, output, solver, timeout):
    native = SmtDocument.parse((work / "smt_encoding.smt2").read_text())
    native_pins = {pin.name: pin for pin in native.config_pins}
    released = set()
    for pin, _ in targets:
        native_pin = native_pins.get(pin.name)
        if native_pin is None or (native_pin.sort, native_pin.original_value) != (pin.sort, pin.original_value):
            raise SubspecificationError(f"configuration pin differs from its native encoding: {pin.name}")
        released.add(native_pin.assertion_index)
    if any(native.declarations.get(name) != sort
           for name, sort in model.document.declarations.items()):
        raise SubspecificationError("slice declarations differ from the native encoding")

    # Under the released pin and checked domain, preserve every native legal state.
    native_query = ["not", ["and", "true", model.property_symbol]]
    native_base = _assertions(expr for i, expr in enumerate(native.assertions)
                              if i not in released and expr != native_query)
    native_base += _scenario_commands(model, k)
    sliced_released = {pin.assertion_index for pin, _ in targets}
    sliced_state = and_expression(expr for i, expr in enumerate(model.document.assertions)
                                  if i not in sliced_released)
    domain_constraint = _allowed_expression(assignments, targets)
    native_model = replace(model, document=native)
    commands = [*native_base,
                *_assertions([domain_constraint, ["not", sliced_state]]), "(check-sat)"]
    if _run_query(native_model, commands, "native_implies_slice", output, solver, timeout) != "unsat":
        raise SubspecificationError("native states could be lost by slicing; see native_implies_slice.log")
    return native_model, native_base


def _batch_check(model, common, assignments, name, output, solver, timeout):
    commands = list(common)
    for values in assignments:
        commands.extend(["(push)", *_equalities({key: _smt_value(value) for key, value in values.items()}),
                         "(check-sat)", "(pop)"])
    statuses = _run_query(model, commands, name, output, solver, timeout).splitlines()
    if len(statuses) != len(assignments) or any(value not in {"sat", "unsat"} for value in statuses):
        raise SubspecificationError(f"{name} incomplete; see {name}.log")
    return statuses


def _failure_witness(model, common, assignment, label, output, solver, timeout):
    egress = {name for next_hops in model.forwarding.values() for name in next_hops.values()}
    discard = {node: f"|0_CONTROL-FORWARDING_{node}_null_interface|" for node in model.forwarding}
    symbols = [model.property_symbol, *model.failure_symbols.values()] + sorted(egress | {
        name for name in discard.values() if name in model.document.declarations})
    query = [*common, *_equalities({key: _smt_value(value) for key, value in assignment.items()}),
             "(check-sat)", f"(get-value ({' '.join(symbols)}))"]
    status, _, raw = _run_query(model, query, label, output, solver, timeout).partition("\n")
    if status != "sat":
        raise SubspecificationError(f"unable to recover failure witness for {assignment}")
    values = dict(parse_smt2_sexpr(tokenize_smt2_sexpr(raw)))
    if values.get(model.property_symbol) != "false":
        raise SubspecificationError(f"failure witness did not falsify {model.property_symbol}")
    try:
        failed = [link for link, name in model.failure_symbols.items() if values[name] == "1"]
        forwarding = {node: [peer for peer, name in peers.items() if values[name] == "true"]
                      for node, peers in model.forwarding.items()}
    except KeyError as exc:
        raise SubspecificationError(f"incomplete failure witness: {exc}") from exc

    path = [model.ingress]
    while len(forwarding[path[-1]]) == 1:
        next_hop = forwarding[path[-1]][0]
        if next_hop in path:
            return dict(failed_links=failed, path=path + [next_hop], end="loop", forwarding=forwarding,
                        property_value=False)
        path.append(next_hop)
    last = path[-1]
    end = ("null_discard" if values.get(discard[last]) == "true" else
           "multiple_next_hops" if forwarding[last] else "no_physical_next_hop")
    return dict(failed_links=failed, path=path, end=end, forwarding=forwarding, property_value=False)


def _allowed_expression(values, targets):
    if not values:
        return "false"
    if len(targets) > 1 and not all(pin.name.endswith(OPERATIONS) for pin, _ in targets):
        clauses = [_assignment_expression(value) for value in values]
        return clauses[0] if len(clauses) == 1 else ["or", *clauses]
    cost = next((pin.name for pin, _ in targets if pin.sort == "Int"), None)
    enable = next((pin.name for pin, _ in targets if pin.sort == "Bool"), None)
    if cost is None and enable is None:
        pin, _ = targets[0]
        terms = [["=", pin.name, row[pin.name]] for row in values]
        return terms[0] if len(terms) == 1 else ["or", *terms]
    if cost is None:
        return "true" if len(values) == 2 else ["=", enable, _smt_value(values[0][enable])]
    groups = {}
    for assignment in values:
        groups.setdefault(assignment.get(enable), []).append(assignment[cost])
    if groups.keys() == {False, True} and groups[False] == groups[True]:
        groups = {None: groups[False]}
    clauses = []
    for enabled, costs in groups.items():
        guard = ["=", enable, _smt_value(enabled)] if enabled is not None else None
        for _, run in groupby(enumerate(costs), key=lambda pair: pair[1] - pair[0]):
            group = [value for _, value in run]
            bounds = [["=", cost, str(group[0])]] if len(group) == 1 else [
                ["<=", str(group[0]), cost], ["<=", cost, str(group[-1])]]
            clauses.append(and_expression(([guard] if guard else []) + bounds))
    return clauses[0] if len(clauses) == 1 else ["or", *clauses]


def _assignment_expression(assignment):
    return and_expression(["=", key, _smt_value(value)] for key, value in assignment.items())


def _check_single_path(model, base, assignments, targets, output, solver, timeout):
    # This first input scope uses the native reachability predicate for
    # single-path forwarding. ECMP requires an explicit packet-path contract.
    multi_path = []
    for router, peers in model.forwarding.items():
        ports = list(peers.values())
        discard = f"|0_CONTROL-FORWARDING_{router}_null_interface|"
        if discard in model.document.declarations:
            ports.append(discard)
        if len(ports) >= 2:
            multi_path.append([">=", ["+", *[["ite", port, "1", "0"] for port in ports]], "2"])
    if multi_path:
        commands = [*base, *_assertions([_allowed_expression(assignments, targets),
                                       ["or", *multi_path]]), "(check-sat)"]
        if _run_query(model, commands, "single_path_scope", output, solver, timeout) != "unsat":
            raise SubspecificationError("single-path scope could not be certified; see single_path_scope.log")


def solve(model: PropertyModel, requested, cost_range, k, output, solver, timeout, coverage_limit,
          *, native_work=None, backend="regions", max_regions=1000):
    targets = _parse_pins(model, requested, cost_range)
    return _solve_assignments(model, targets, k, output, solver, timeout, coverage_limit,
                              native_work=native_work, backend=backend, max_regions=max_regions)


def _solve_assignments(model, targets, k, output, solver, timeout, coverage_limit,
                       *, native_work=None, assignments=None, backend="regions", max_regions=1000,
                       context=None):
    """Dispatch without materializing a configuration product in production."""
    if backend == "enumerate":
        return _solve_assignments_oracle(model, targets, k, output, solver, timeout,
                                         coverage_limit, native_work=native_work,
                                         assignments=assignments)
    if backend != "regions":
        raise ValueError(f"unknown property backend: {backend}")
    if native_work is not None:
        model = context.full_model(model, native_work) if context is not None else full_model(model, native_work)
        pins = {pin.name: pin for pin in model.document.config_pins}
        rebound = [(pins[pin.name], domain) for pin, domain in targets]
        targets = targets.rebind(rebound) if isinstance(targets, DomainTargets) else rebound
        if any('_RouteFilterList_' in pin.name and isinstance(domain, SYMBOLIC_DOMAINS)
               for pin, domain in targets):
            if model.encoding_semantics.get('symbolic_prefix_length_ranges') != 'variable-inclusive-bounds':
                raise SubspecificationError('full IPv4 prefix domain requires variable inclusive range '
                                            'bounds in the native encoding; regenerate the input')
        if any(isinstance(domain, IntegerDomain) and domain.maximum is None for _, domain in targets):
            if (model.metric_domains.get('bgp_as_path_length') != 'nonnegative-integer'
                    or model.metric_domains.get('model_overflow') is not False):
                raise SubspecificationError('full prepend domain requires an unbounded BGP metric export '
                                            'with overflow modeling disabled; regenerate the input')
    evidence = output / "region_evidence"
    if evidence.exists() or (output / "allowed.smt2").exists() or (output / "region_report.json").exists():
        raise ValueError(f"region evidence already exists: {evidence}")
    runner = QueryRunner(model.document, Path(solver), timeout, evidence,
                         session=context.session if context is not None else None)
    engine = None
    try:
        engine = RegionSolver(model, targets, k, runner, coverage_limit, max_regions, assignments,
                              context=context)
        result = engine.solve()
    except RegionFailure as exc:
        result = dict(status=exc.status.value, exact=False, backend="regions", error=str(exc),
                      metrics=runner.metrics(), phase_seconds=engine.phase_seconds if engine else {})
        (output / "region_report.json").write_text(json.dumps(result, indent=2) + "\n")
        raise
    (output / "region_report.json").write_text(json.dumps(result, indent=2) + "\n")
    shutil.copyfile(evidence / "allowed.smt2", output / "allowed.smt2")
    return result


def _solve_assignments_oracle(model, targets, k, output, solver, timeout, coverage_limit,
                              *, native_work=None, assignments=None, classify_support=False):
    """Legacy finite-domain oracle; not the production region solver."""
    if any(isinstance(domain, SYMBOLIC_DOMAINS) for _, domain in targets):
        raise SubspecificationError('semantic domains cannot be sampled by the enumeration oracle; use regions')
    failure_names = list(model.failure_symbols.values())
    scenario_count = sum(math.comb(len(failure_names), n)
                         for n in range(min(k, len(failure_names)) + 1))
    target_count = (len(assignments) if assignments is not None
                    else math.prod(len(domain) for _, domain in targets))
    if target_count * scenario_count > coverage_limit:
        raise SubspecificationError(
            f"model coverage needs {target_count * scenario_count} checks "
            f"(limit {coverage_limit}); use a smaller target range or raise --max-coverage-checks")
    target_names = [pin.name for pin, _ in targets]
    if assignments is None:
        assignments = [dict(zip(target_names, values))
                       for values in product(*(domain for _, domain in targets))]
    base = _model_commands(model, targets, k)
    coverage_models = [(model, base, "model_coverage")]
    if native_work is not None:
        native_model, native_base = _certify_slice(
            model, native_work, targets, assignments, k, output, solver, timeout)
        coverage_models.append((native_model, native_base, "native_model_coverage"))
    _check_single_path(model, base, assignments, targets, output, solver, timeout)
    bad = [*base, f"(assert (not {model.property_symbol}))"]
    statuses = _batch_check(model, bad, assignments, "bad_configurations", output, solver, timeout)

    # Failure variables are free in each safety query. Enumerate only the
    # support check, to rule out vacuous conclusions from missing models.
    failures = [set(group) for n in range(min(k, len(failure_names)) + 1)
                for group in combinations(failure_names, n)]
    coverage = [dict(assignment, **{name: int(name in failed) for name in failure_names})
                for assignment in assignments for failed in failures]
    supported_assignments = [True] * len(assignments)
    for coverage_model, coverage_base, label in coverage_models:
        statuses_for_model = _batch_check(
            coverage_model, coverage_base, coverage, label, output, solver, timeout)
        for index in range(len(assignments)):
            supported_assignments[index] &= all(value == "sat" for value in
                statuses_for_model[index * scenario_count:(index + 1) * scenario_count])
        if "unsat" in statuses_for_model and not classify_support:
            first = coverage[statuses_for_model.index("unsat")]
            failed = [link for link, name in model.failure_symbols.items() if first[name]]
            target = {key: first[key] for key in target_names}
            raise SubspecificationError(f"no legal model for {target} under failures {failed}; see {label}.log")

    allowed = [assignment for assignment, status, supported in
               zip(assignments, statuses, supported_assignments) if status == "unsat" and supported]
    rejected = []
    for i, (assignment, status) in enumerate(zip(assignments, statuses)):
        if status == "sat":
            witness = _failure_witness(model, bad, assignment, f"witness_{i:04d}", output, solver, timeout)
            rejected.append(dict(configuration=assignment, witness=witness))

    formula = _allowed_expression(allowed, targets)
    exact = [_assignment_expression(assignment) for assignment in allowed]
    enumerated = ["or", *exact] if exact else "false"
    proof = _run_query(model, [f"(assert (xor {smt(formula)} {smt(enumerated)}))", "(check-sat)"],
                       "formula_equivalence", output, solver, timeout)
    if proof != "unsat":
        raise SubspecificationError("failed to certify the allowed configuration formula")
    (output / "allowed.smt2").write_text("\n".join([
        *(f"(declare-const {pin.name} {pin.sort})" for pin, _ in targets),
        f"(assert {smt(formula)})", "(check-sat)", "",
    ]))
    result = dict(
        status="PASS", semantics="all-legal-states-within-at-most-k",
        metric_domains=dict(model.metric_domains),
        ingress=model.ingress, destination=model.destination, property=model.property_symbol,
        max_link_failures=k, legal_failures=scenario_count, model_coverage_checks=len(coverage),
        target_domains={pin.name: list(domain) for pin, domain in targets},
        original_values={pin.name: pin.original_value for pin, _ in targets},
        original_configuration_checked=any(
            all(_smt_value(assignment[pin.name]) == pin.original_value for pin, _ in targets)
            for assignment in assignments),
        allowed_constraint=smt(formula), allowed_configurations=allowed,
        rejected_configurations=rejected,
    )
    if native_work is not None:
        result.update(native_implies_slice="UNSAT", native_model_coverage_checks=len(coverage))
    if classify_support:
        result.update(
            backend="enumerate", configuration_values_enumerated=len(assignments),
            bad_constraint=smt(_allowed_expression([row for row, status in zip(assignments, statuses)
                                                    if status == "sat"], targets)),
            support_constraint=smt(_allowed_expression([row for row, supported in
                                                        zip(assignments, supported_assignments)
                                                        if supported], targets)))
    return result


def _field_from_line(model, pin, line_report, output, solver, timeout, *, session=None):
    """Fix the other members of a solved line to their original values."""
    if line_report.get("backend") == "regions":
        return _field_from_region(model, pin, line_report, output, solver, timeout, session=session)
    domain = line_report["target_domains"][pin.name]
    fixed = {key: value for key, value in line_report["original_values"].items() if key != pin.name}
    # A Boolean field can still be derived directly if the original cost is
    # outside the requested line domain.
    if any(value not in {_smt_value(item) for item in line_report["target_domains"][key]}
           for key, value in fixed.items()):
        return None

    def matches(candidate):
        return all(_smt_value(candidate[key]) == value for key, value in fixed.items())

    allowed = [{pin.name: row[pin.name]} for row in line_report["allowed_configurations"]
               if matches(row)]
    rejected = [dict(configuration={pin.name: row["configuration"][pin.name]}, witness=row["witness"])
                for row in line_report["rejected_configurations"] if matches(row["configuration"])]
    if len(allowed) + len(rejected) != len(domain):
        raise SubspecificationError(f"joint results do not cover the field domain for {pin.name}")
    formula = _allowed_expression(allowed, [(pin, domain)])
    fixed.update(line_report.get("fixed_same_line_fields", {}))
    specialized = substitute_symbols(
        parse_smt2_sexpr(tokenize_smt2_sexpr(line_report["allowed_constraint"])), fixed)
    proof = _run_query(model, [f"(assert (xor {smt(formula)} {smt(specialized)}))", "(check-sat)"],
                       "field_specialization", output, solver, timeout)
    if proof != "unsat":
        raise SubspecificationError(f"could not certify field specialization for {pin.name}")
    return dict(status="PASS", allowed_constraint=smt(formula), target_domains={pin.name: domain},
                original_values={pin.name: pin.original_value}, fixed_same_line_fields=fixed,
                allowed_configurations=allowed, rejected_configurations=rejected,
                model_coverage_checks=len(domain) * line_report["legal_failures"],
                method="specialize-verified-line")


def _field_from_region(model, pin, line_report, output, solver, timeout, *, session=None):
    fixed = {name: ast(value) for name, value in line_report["original_values"].items()
             if name != pin.name}
    for name, value in fixed.items():
        if not domain_contains(line_report["target_domains"][name], smt(value)):
            return None
    fixed.update({name: ast(value) for name, value in line_report.get("fixed_same_line_fields", {}).items()})
    runner = QueryRunner(model.document, Path(solver), timeout, output / "region_evidence", session=session)
    formulas = {}
    keys = ['domain_constraint', 'bad_constraint', 'support_constraint', 'allowed_constraint']
    keys += [key for key in ('property_condition', 'model_support_condition') if key in line_report]
    for key in keys:
        specialized = substitute_symbols(ast(line_report[key]), fixed)
        formulas[key] = runner.simplify("specialize_" + key, specialized)
        require_config_formula(formulas[key], {pin.name})
        runner.prove("certify_" + key, ["xor", specialized, formulas[key]])
    result = dict(status="PASS", exact=True, backend="regions", **{key: smt(value) for key, value in formulas.items()},
                  metric_domains=line_report.get("metric_domains", {}),
                  encoding_semantics=line_report.get("encoding_semantics", {}),
                  condition_scope='relative-to-domain_constraint',
                  target_domains={pin.name: line_report["target_domains"][pin.name]},
                  original_values={pin.name: pin.original_value},
                  fixed_same_line_fields={key: smt(value) for key, value in fixed.items()},
                  method="specialize-verified-line", metrics=runner.metrics())
    (output / "allowed.smt2").write_text(f"(declare-fun {pin.name} () {pin.sort})\n"
                                        f"(assert {result['allowed_constraint']})\n(check-sat)\n")
    return result


def _write_community_reports(model, pin, tag, result, output, solver, timeout):
    line = config_line_group(pin.name)
    owner = config_owner(line, model.forwarding)
    fixed = {item.name: item.original_value for item in model.document.config_pins
             if item.name != pin.name and config_line_group(item.name) == line}
    line_result = dict(result, owner=owner, fixed_same_line_fields=fixed, evidence=".")
    condition = result["allowed_constraint"]
    if condition != "false":
        line_result["allowed_constraint"] = smt(and_expression([
            parse_smt2_sexpr(tokenize_smt2_sexpr(condition)),
            *(["=", name, value] for name, value in fixed.items()),
        ]))
    evidence = output / "3_property_subspecs/field_0001"
    evidence.mkdir(parents=True)
    field = _field_from_line(model, pin, line_result, evidence, solver, timeout)
    fields = {pin.name: dict(field, owner=owner, line=line, evidence=str(evidence.relative_to(output)))}
    lines = {line: line_result}
    report = dict(result, target_scope="standard-community-field",
                  community_values=_community_domain(model, pin, tag),
                  field_level=fields, line_level=lines)
    write_subspecs(output, fields, lines)
    (output / "4_final_subspecs/final_subspecs.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _solve_all(model, targets, args, output, solver):
    stage3 = output / "3_property_subspecs"
    stage3.mkdir()
    fields, lines, errors, target_statuses = {}, {}, {}, {}
    for number, line in enumerate(targets, 1):
        directory = stage3 / f"line_{number:04d}"
        directory.mkdir()
        try:
            result = solve(model, [pin.name for pin in line.fields], args.cost_range, args.k,
                           directory, solver, args.timeout, args.max_coverage_checks,
                           native_work=output / "input" if args.property_backend == "regions" else None,
                           backend=args.property_backend, max_regions=args.max_bad_regions)
        except SubspecificationError as exc:
            errors[line.name] = str(exc)
            target_statuses[line.name] = exc.status.value if isinstance(exc, RegionFailure) else "INCOMPLETE"
            continue
        lines[line.name] = dict(result, owner=line.owner, evidence=str(directory.relative_to(output)))

        for pin in line.fields:
            field_dir = directory / ("enable" if pin.sort == "Bool" else "cost")
            field_dir.mkdir()
            try:
                field_result = _field_from_line(model, pin, result, field_dir, solver, args.timeout)
                if field_result is None:
                    field_result = solve(model, [pin.name],
                                         args.cost_range if pin.sort == "Int" else None, args.k,
                                         field_dir, solver, args.timeout, args.max_coverage_checks,
                                         native_work=output / "input" if args.property_backend == "regions" else None,
                                         backend=args.property_backend, max_regions=args.max_bad_regions)
                    field_result["method"] = "solve-with-other-fields-fixed"
                fields[pin.name] = dict(field_result, owner=line.owner, line=line.name,
                                        evidence=str(field_dir.relative_to(output)))
            except SubspecificationError as exc:
                errors[pin.name] = str(exc)
                target_statuses[pin.name] = exc.status.value if isinstance(exc, RegionFailure) else "INCOMPLETE"

    supported = {pin.name for target in targets for pin in target.fields}
    unsupported = sorted(pin.name for pin in model.document.config_pins if pin.name not in supported)
    report = dict(
        status="INCOMPLETE" if errors else "PASS",
        semantics="all-legal-states-within-at-most-k", target_scope="as-path-prepend",
        ingress=model.ingress, destination=model.destination, property=model.property_symbol,
        max_link_failures=args.k, cost_range=list(args.cost_range) if args.cost_range else None,
        numeric_domain_policy='explicit-diagnostic-restriction' if args.cost_range else 'semantic',
        field_level=fields, line_level=lines, errors=errors, target_statuses=target_statuses,
        unsupported_config_fields=unsupported,
    )
    write_subspecs(output, fields, lines)
    (output / "4_final_subspecs/final_subspecs.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _line_domains(model, line, pins, cost_range):
    if "_RouteFilterList_" in line:
        return prefix_domains(pins), None
    targets = []
    for pin in pins:
        tag = _community_target_tag(pin.name)
        if tag is not None:
            domain = tuple(_community_domain(model, pin, tag).values())
        else:
            domain = numeric_domain(pin, cost_range)
        targets.append((pin, domain))
    return DomainTargets(targets), None


def _keep_unused_fields_fixed(model, targets, assignments):
    fixed = {pin.name: pin.original_value for pin, _ in targets if pin.name in model.unused_config_fields}
    if not fixed:
        return targets, assignments
    if assignments is None:
        # A missing semantic equation is a model-coverage restriction, not a
        # smaller legal domain. Keep both Boolean values in D and expose the
        # original-value requirement in Support.
        plan = targets.rebind(targets) if isinstance(targets, DomainTargets) else DomainTargets(targets)
        plan.support = and_expression([plan.support, *(['=', name, ast(value)] for name, value in fixed.items())])
        return plan, None
    if assignments is not None:
        assignments = [row for row in assignments if all(_smt_value(row[key]) == value
                                                          for key, value in fixed.items())]
        if not assignments:
            raise SubspecificationError("no candidate retains the fields without native equations")
    restricted = []
    for pin, domain in targets:
        if pin.name in fixed:
            original = next((value for value in domain if _smt_value(value) == pin.original_value),
                            pin.original_value)
            domain = (original,)
        restricted.append((pin, domain))
    return (targets.rebind(restricted) if isinstance(targets, DomainTargets) else restricted), assignments


def _solve_all_configs(model, work, args, output, solver):
    from region_context import RegionContext
    context = RegionContext()
    try:
        return _solve_all_configs_shared(model, work, args, output, solver, context)
    finally:
        context.close()


def _solve_all_configs_shared(model, work, args, output, solver, context):
    grouped, errors, target_statuses = {}, {}, {}
    pinned = {pin.name for pin in model.document.config_pins}
    native = context.full_model(model, work).document
    encoded = {name for name in native.declarations if name.startswith("Config_")}
    errors.update(dict.fromkeys(sorted(encoded - pinned), "missing original configuration pin"))
    for pin in model.document.config_pins:
        line = config_line_group(pin.name)
        if line is None:
            errors[pin.name] = "missing configuration line mapping"
        else:
            grouped.setdefault(line, []).append(pin)

    source_plans = None
    if getattr(args, 'source_configs', None) is not None:
        from speclens_granularity import command_plans
        source_plans = command_plans({line: dict(
            original_values={pin.name: pin.original_value for pin in pins},
            owner=config_owner(line, model.forwarding)) for line, pins in grouped.items()}, args.source_configs)
    stage3 = output / "3_property_subspecs"
    stage3.mkdir()
    fields, lines = {}, {}
    for number, (line, pins) in enumerate(sorted(grouped.items()), 1):
        directory = stage3 / f"line_{number:04d}"
        directory.mkdir()
        try:
            targets, assignments = _line_domains(model, line, pins, args.cost_range)
            targets, assignments = _keep_unused_fields_fixed(model, targets, assignments)
            owner = config_owner(line, model.forwarding)
            result = _solve_assignments(model, targets, args.k, directory, solver, args.timeout,
                                        args.max_coverage_checks, native_work=work, assignments=assignments,
                                        backend=args.property_backend, max_regions=args.max_bad_regions,
                                        context=context)
        except SubspecificationError as exc:
            errors[line] = str(exc)
            target_statuses[line] = exc.status.value if isinstance(exc, RegionFailure) else "INCOMPLETE"
            continue
        lines[line] = dict(result, owner=owner, evidence=str(directory.relative_to(output)))
        if source_plans is not None:
            from speclens_granularity import derive_contract
            encoded_line = lines[line]
            (directory / 'encoded_line_result.json').write_text(json.dumps(encoded_line, indent=2) + '\n')
            plan = source_plans[line]
            lines[line] = derive_contract(plan, encoded_line, native, solver, args.timeout,
                                          directory / 'source_line', session=context.session)
            lines[line]['evidence'] = str((directory / 'source_line').relative_to(output))
            for index, source_field in enumerate(plan.fields, 1):
                field_dir = directory / f'source_field_{index:04d}'
                field = derive_contract(plan, encoded_line, native, solver, args.timeout,
                                        field_dir, source_field, session=context.session)
                fields[source_field['id']] = dict(field, evidence=str(field_dir.relative_to(output)))
            continue
        for index, (pin, field_domain) in enumerate(targets, 1):
            field_dir = directory / f"field_{index:04d}"
            field_dir.mkdir()
            try:
                specialization = result
                if assignments is not None:
                    fixed = {other.name: other.original_value for other in pins if other != pin}
                    domain = list(dict.fromkeys(row[pin.name] for row in assignments
                                                if all(_smt_value(row[key]) == value
                                                       for key, value in fixed.items())))
                    if not domain:
                        raise SubspecificationError("no line assignment retains the other fields")
                    specialization = dict(result, target_domains={**result["target_domains"], pin.name: domain})
                field = _field_from_line(model, pin, specialization, field_dir, solver, args.timeout,
                                         session=context.session)
                if field is None:
                    field = _solve_assignments(model, [(pin, field_domain)], args.k, field_dir, solver,
                                               args.timeout, args.max_coverage_checks, native_work=work,
                                               backend=args.property_backend, max_regions=args.max_bad_regions,
                                               context=context)
                    field["method"] = "solve-with-other-fields-fixed"
                    field["fixed_same_line_fields"] = {
                        other.name: other.original_value for other in pins if other != pin
                    }
                if pin.name in model.unused_config_fields:
                    field["domain_reason"] = "original-value-only-without-native-equations"
                fields[pin.name] = dict(field, owner=owner, line=line, evidence=str(field_dir.relative_to(output)))
            except SubspecificationError as exc:
                errors[pin.name] = str(exc)
                target_statuses[pin.name] = exc.status.value if isinstance(exc, RegionFailure) else "INCOMPLETE"

    report = dict(status="INCOMPLETE" if errors or not fields else "PASS",
                  semantics="all-legal-states-within-at-most-k", target_scope="all-encoded-config-fields",
                  ingress=model.ingress, destination=model.destination, property=model.property_symbol,
                  max_link_failures=args.k, encoded_fields=len(encoded), encoded_lines=len(grouped),
                  field_level=fields, line_level=lines, errors=errors, target_statuses=target_statuses,
                  unsupported_config_fields=([] if source_plans is not None else sorted(encoded - fields.keys())),
                  fixed_without_native_equations=sorted(model.unused_config_fields),
                  numeric_domain_policy='explicit-diagnostic-restriction' if args.cost_range else 'semantic',
                  cost_range=args.cost_range)
    report['granularity'] = 'speclens' if source_plans is not None else 'encoded-variables'
    if source_plans is not None:
        report['target_scope'] = 'source-command-fields-with-encoded-effects'
        report['source_fields'] = len(fields)
        report['source_lines'] = len(lines)
        report['source_mapping'] = {name: plan.metadata() for name, plan in source_plans.items()}
        report['source_limitations'] = {name: plan.limitations for name, plan in source_plans.items() if plan.limitations}
    report['execution_reuse'] = context.metrics()
    report['execution_reuse']['scope'] = 'property-regions-and-field-specialization'
    consistency_path = work / '2_consistency_check/consistency_report.json'
    if consistency_path.exists():
        consistency = json.loads(consistency_path.read_text())
        report['consistency_stage'] = dict(
            coverage_strategy=consistency.get('coverage_strategy', 'legacy-enumeration'),
            checked_branches=consistency['checked_branches'],
            fault_assignments_enumerated=consistency.get('fault_assignments_enumerated'),
            report=str(consistency_path.resolve()))
    write_subspecs(output, fields, lines)
    (output / "4_final_subspecs/final_subspecs.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _stage(project, script, work, args, output):
    command = [sys.executable, "-B", str(project / script), str(work), "--k", str(args.k)]
    if script.startswith("2_"):
        command += ["--workers", str(args.consistency_workers), "--timeout", str(args.timeout)]
        if args.z3 is not None:
            command += ["--z3", str(args.z3.resolve())]
    with (output / f"{script}.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise SubspecificationError(f"{script} exited {result.returncode}; see its log")


def run(args, project: Path) -> int:
    source, output = args.work_directory.resolve(), args.output.resolve()
    if (not source.is_dir() or output.exists() or output.is_relative_to(source)):
        print("Property mode requires an existing input and a fresh output outside it", file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    work = output / "input"
    work.mkdir()
    report = {"status": "INCOMPLETE", "source": str(source)}
    try:
        if args.all_configs and args.property_backend != 'regions':
            raise SubspecificationError('all-configs uses complete semantic domains; use the regions backend')
        for filename in INPUT_FILES:
            shutil.copyfile(source / filename, work / filename)
        optional = [name for name in (METRIC_DOMAIN_FILE, ENCODING_SEMANTICS_FILE)
                    if (source / name).is_file()]
        for filename in optional:
            shutil.copyfile(source / filename, work / filename)
        report["input_sha256"] = {name: sha256((work / name).read_bytes()).hexdigest()
                                  for name in (*INPUT_FILES, *optional)}
        _stage(project, "1_smt_slicer.py", work, args, output)
        model = load_property_model(work, args.k, include_unused_configs=args.all_configs)
        report["metric_domains"] = dict(model.metric_domains)
        if args.target:
            selected = _parse_pins(model, args.target, args.cost_range)
        elif not args.all_configs:
            targets = prepend_lines(model.document.config_pins, model.forwarding)
            if not targets:
                raise SubspecificationError("no supported AS-path prepend targets in this export")
            _parse_pins(model, [pin.name for pin in targets[0].fields], args.cost_range)
        _stage(project, "2_consistency_checker.py", work, args, output)
        solver = SmtSolver(z3_path=args.z3, timeout_seconds=args.timeout).z3_path
        if args.target:
            tag = _community_target_tag(args.target[0])
            result = solve(model, args.target, args.cost_range, args.k, output,
                           solver, args.timeout, args.max_coverage_checks,
                           native_work=work if args.property_backend == "regions" or tag is not None else None,
                           backend=args.property_backend, max_regions=args.max_bad_regions)
            if tag is not None:
                result = _write_community_reports(model, selected[0][0], tag, result, output,
                                                  solver, args.timeout)
            elif len(args.target) == 1:
                field = args.target[0]
                write_subspecs(output, {field: dict(result, owner=config_owner(field, model.forwarding))}, {})
            else:
                line = config_line_group(args.target[0])
                write_subspecs(output, {}, {line: dict(result, owner=config_owner(line, model.forwarding))})
            report.update(result)
        elif args.all_configs:
            report.update(_solve_all_configs(model, work, args, output, solver))
        else:
            report.update(_solve_all(model, targets, args, output, solver))
    except (OSError, SubspecificationError, ValueError) as exc:
        report["status"] = (exc.status.value if isinstance(exc, RegionFailure) else
                            "ERROR" if isinstance(exc, (OSError, ValueError)) else "INCOMPLETE")
        report["error"] = str(exc)
        print(f"Property mode incomplete: {exc}", file=sys.stderr)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "PASS":
        return 1
    if args.target:
        print(report["allowed_constraint"])
    else:
        print(f"Derived {len(report['field_level'])} field and {len(report['line_level'])} line subspecs")
        print(f"Subspecs: {output / '4_final_subspecs'}")
    print(f"Report: {output / 'report.json'}")
    return 0
