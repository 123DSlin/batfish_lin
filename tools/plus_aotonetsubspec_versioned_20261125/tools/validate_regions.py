#!/usr/bin/env python3
"""Recompute real prepend configurations with iBDP and audit region predictions.

This validation deliberately enumerates selected configuration samples and all
budgeted faults. It is an independent validation layer, never a production
region-solving path. RIB forwarding is compared at every modeled router.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from concrete_validation import (
    ValidationError, configuration_hashes, delivery, prepare_prepend_snapshot,
    read_concrete_scenarios, run_batfish,
)
from property_model import load_property_model
from property_regions import RegionSolver, full_model
from property_subspec import _parse_pins, solve
from region_smt import QueryRunner, ast
from utils.util_symbolic import SmtSolver, SubspecificationError, and_expression, substitute_symbols


def signature(model, scenario, actual_property):
    expressions = [["=", model.property_symbol, 'true' if actual_property else 'false']]
    for router, peers in model.forwarding.items():
        selected = scenario.routes.get(router)
        for peer, symbol in peers.items():
            expressions.append(["=", symbol, 'true' if selected and selected.peer == peer else 'false'])
        discard = f'|0_CONTROL-FORWARDING_{router}_null_interface|'
        if discard in model.document.declarations:
            expressions.append(["=", discard, 'true' if selected and selected.interface == 'null_interface' else 'false'])
    return and_expression(expressions)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', type=Path, required=True,
                        help='case directory containing configs/, problem.json and prepared input/')
    parser.add_argument('--input-subdirectory', default='all_configs/input')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, default=ROOT.parents[1]/'bazel-bin/projects/allinone/smt_tests')
    parser.add_argument('--java-binary', type=Path, help='Java runtime compatible with the Bazel test launcher')
    parser.add_argument('--router', default='t')
    parser.add_argument('--policy', default='FROM_ISP')
    parser.add_argument('--sequence', type=int, default=20)
    parser.add_argument('--asn', type=int, default=65105)
    parser.add_argument('--enable-target', default='Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_enable')
    parser.add_argument('--cost-target', default='Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_cost')
    parser.add_argument('--costs', nargs='+', type=int, default=[0, 1, 2, 65532, 65533, 65534])
    parser.add_argument('--domain-maximum', type=int, default=65534)
    parser.add_argument('--query-timeout', type=float, default=20)
    parser.add_argument('--export-timeout', type=float, default=120)
    args = parser.parse_args()
    if (not 0 <= args.domain_maximum <= 65534 or any(not 0 <= value <= args.domain_maximum for value in args.costs)
            or args.query_timeout <= 0 or args.export_timeout <= 0):
        parser.error('invalid configuration domain or timeout')
    if args.output.exists() or any(args.output.resolve().is_relative_to(case.resolve()) for case in args.case):
        parser.error('use a fresh output directory outside every input case')
    return args


def audit_variant(model, report, engine, runner, values, scenarios, finals):
    support_cases = {frozenset(name for name, value in case['failures'].items() if value == '1'):
                     ast(case['constraint']) for case in report['support_cases']}
    rows = []
    for index, scenario in enumerate(scenarios.values()):
        failure = {symbol: str(int(link in scenario.failed_links)) for link, symbol in model.failure_symbols.items()}
        physical = delivery(scenario, model.ingress, finals)
        source = substitute_symbols(engine.state(failure), values)
        observed = signature(model, scenario, physical['delivered'])
        match = runner.check(f'match_{index:04d}', and_expression([source, observed]))
        supported = match == 'sat'
        if not supported and runner.check(f'existence_{index:04d}', source) == 'sat':
            raise ValidationError(f'iBDP/SMT forwarding or property mismatch at {sorted(scenario.failed_links)}')
        if supported:
            runner.prove(f'all_states_match_{index:04d}', and_expression([source, ['not', observed]]))
        key = frozenset(symbol for symbol, value in failure.items() if value == '1')
        if key not in support_cases:
            raise ValidationError('region report omitted a legal fault Support projection')
        predicted_support = runner.check(f'projected_support_{index:04d}',
                                         substitute_symbols(support_cases[key], values)) == 'sat'
        if predicted_support != supported:
            raise ValidationError('Support projection disagrees with independently fixed-state existence')
        selected_peers = {}
        for router in model.forwarding:
            route = scenario.routes.get(router)
            selected_peers[router] = (None if route is None else 'discard'
                if route.interface == 'null_interface' else route.peer or 'local')
        rows.append(dict(failed_links=sorted(scenario.failed_links), source=str(scenario.source),
                         model_supported=supported, selected_peers=selected_peers, **physical))
    supported_all = all(row['model_supported'] for row in rows)
    physical_safe = all(row['delivered'] for row in rows)
    bad_in_supported_states = any(row['model_supported'] and not row['delivered'] for row in rows)
    expected = dict(support_constraint=supported_all, bad_constraint=bad_in_supported_states,
                    allowed_constraint=supported_all and physical_safe)
    for key, value in expected.items():
        predicted = runner.check('configuration_' + key, substitute_symbols(ast(report[key]), values)) == 'sat'
        if predicted != value:
            raise ValidationError(f'{key} disagrees with concrete forwarding and model support')
    return dict(configuration=values, status='VERIFIED_SUPPORTED' if supported_all else 'OUTSIDE_MODEL_SUPPORT',
                actual_property_all_faults=physical_safe, allowed=expected['allowed_constraint'],
                support_gap_count=sum(not row['model_supported'] for row in rows), scenarios=rows)


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    overall = dict(status='INCOMPLETE', purpose='independent iBDP forwarding/property audit',
                   candidate_identity='directed BGP IMPORT slot; not full path identity', cases={}, variants=[],
                   scope='selected configurations only; supports neither ECMP nor proof of all configuration values')
    overall['source_sha256'] = {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in
        ('concrete_validation.py', 'property_regions.py', 'region_smt.py', 'tools/validate_regions.py')}
    try:
        loaded = []
        fingerprints = []
        solver = SmtSolver().z3_path
        for number, directory in enumerate(args.case):
            spec = json.loads((directory/'problem.json').read_text())
            hashes = configuration_hashes(directory/'configs')
            if hashes != spec['configuration_sha256']:
                raise ValidationError(f'configuration hashes differ from problem.json: {directory}')
            fingerprints.append(hashes)
            work = directory/args.input_subdirectory
            model = load_property_model(work, spec['max_link_failures'])
            if model.destination != spec['destination'] or model.ingress != spec['ingress_node']:
                raise ValidationError('property manifest differs from encoded ingress or destination')
            output = args.output/f'contract_{number:02d}'
            output.mkdir()
            report = solve(model, [args.enable_target, args.cost_target], (0, args.domain_maximum),
                           spec['max_link_failures'], output, solver, args.query_timeout, 10000, native_work=work)
            model = full_model(model, work)
            pins = _parse_pins(model, [args.enable_target, args.cost_target], (0, args.domain_maximum))
            original = {pin.name: pin.original_value for pin, _ in pins}
            if original != {args.enable_target: 'true', args.cost_target: '1'}:
                raise ValidationError('snapshot mutator requires original enable=true, cost=1')
            loaded.append((spec, model, report, pins, output))
            overall['cases'][spec['case_id']] = dict(source=str(directory.resolve()),
                configuration_sha256=hashes, native_sha256=sha256((work/'smt_encoding.smt2').read_bytes()).hexdigest(),
                region_report=str(output/'region_report.json'), configurations=[])
        if not all(item == fingerprints[0] for item in fingerprints):
            raise ValidationError('shared concrete export requires identical physical configurations')
        base_spec, base_model, *_ = loaded[0]
        if any((spec['destination'], spec['max_link_failures'], set(model.failure_symbols)) !=
               (base_spec['destination'], base_spec['max_link_failures'], set(base_model.failure_symbols))
               for spec, model, *_ in loaded):
            raise ValidationError('shared concrete export requires the same destination and fault universe')
        variants = [(False, min(1, args.domain_maximum)),
                    *((True, value) for value in dict.fromkeys(args.costs))]
        cache = {}
        for variant_number, (enabled, cost) in enumerate(variants):
            effective_cost = cost if enabled else 0
            if effective_cost not in cache:
                folder = args.output/f'physical_prepend_{effective_cost}'
                snapshot = folder/'snapshot'
                hashes = prepare_prepend_snapshot(args.case[0]/'configs', snapshot, args.router, args.policy,
                                                   args.sequence, args.asn, effective_cost)
                exported = run_batfish(snapshot, folder/'concrete', args.launcher, ingress=base_model.ingress,
                    destination=base_model.destination, k=base_spec['max_link_failures'], timeout=args.export_timeout,
                    java_binary=args.java_binary)
                cache[effective_cost] = read_concrete_scenarios(exported, set(base_model.forwarding),
                    set(base_model.failure_symbols), base_model.destination, base_spec['max_link_failures'])
                overall['variants'].append(dict(effective_cost=effective_cost, configuration_sha256=hashes,
                                                export=str(exported)))
            for spec, model, report, pins, output in loaded:
                evidence = output/f'validation_{variant_number:02d}'
                runner = QueryRunner(model.document, solver, args.query_timeout, evidence)
                engine = RegionSolver(model, pins, spec['max_link_failures'], runner)
                values = {args.enable_target: 'true' if enabled else 'false', args.cost_target: str(cost)}
                result = audit_variant(model, report, engine, runner, values, cache[effective_cost],
                                       set(spec['allowed_final_nodes']))
                result['metrics'] = runner.metrics()
                overall['cases'][spec['case_id']]['configurations'].append(result)
                print(spec['case_id'], enabled, cost, result['status'], 'safe=',result['actual_property_all_faults'], flush=True)
            (args.output/'report.json').write_text(json.dumps(overall, indent=2)+'\n')
        rows = [row for case in overall['cases'].values() for row in case['configurations']]
        overall['supported_configurations'] = sum(row['status']=='VERIFIED_SUPPORTED' for row in rows)
        overall['out_of_support_configurations'] = len(rows)-overall['supported_configurations']
        overall['status'] = 'PASS_WITH_SUPPORT_GAPS' if overall['out_of_support_configurations'] else 'PASS'
    except (ValidationError, SubspecificationError, OSError, ValueError, KeyError) as exc:
        overall.update(status='FAIL', error=str(exc))
        print(str(exc), file=sys.stderr)
    finally:
        overall['seconds'] = time.monotonic()-started
        (args.output/'report.json').write_text(json.dumps(overall, indent=2)+'\n')
    return 0 if overall['status'] in {'PASS', 'PASS_WITH_SUPPORT_GAPS'} else 1


if __name__ == '__main__':
    raise SystemExit(run(arguments()))
