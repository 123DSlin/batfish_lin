#!/usr/bin/env python3
"""Run AutoNetSubspec on independently computed concrete failure RIBs.

F is the scheduling unit. Export/preparation, AG, constraint solving, intersection,
and report writing are timed separately. A failed AG gate never produces a valid baseline.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


TRAVERSE_DIRECTORY = Path(__file__).resolve().parent
TOOLS_DIRECTORY = TRAVERSE_DIRECTORY.parent
ORIGINAL_SCRIPTS = TRAVERSE_DIRECTORY / '0_auto-netsubspec'
TRAVERSE_INTERSECTION = TRAVERSE_DIRECTORY / 'intersect_failure_subspecs.py'


def prepare(source, concrete, output, devices):
    output.mkdir(parents=True, exist_ok=False)
    for path in source.glob('0_*.txt'):
        if not path.name.startswith('0_symbolic_'):
            shutil.copy2(path, output / path.name)
    text = (concrete / '0_dataplane.txt').read_text()
    failed = re.findall(r'^FAILED (.+)$', text, re.M)
    pairs = {tuple(sorted((line.split(':', 1)[0], line.split('--', 1)[1].split(':', 1)[0]))) for line in failed}
    encoding = (source / 'smt_encoding.smt2').read_text()
    variables = re.findall(r'\(declare-fun \|(\d+_FAILED-EDGE_[^|]+)\| \(\) Int\)', encoding)
    pins = []
    represented = set()
    nodes = source.joinpath('0_hostnames.txt').read_text().split()
    for variable in variables:
        suffix = variable.split('FAILED-EDGE_', 1)[1]
        matching = [(a,b) for a in nodes for b in nodes if a != b and suffix == f'{a}_{b}']
        if not matching:
            if 'Loopback' in suffix:
                continue
            raise ValueError(f'Unrecognized physical failure variable: {variable}')
        if len(matching) != 1:
            raise ValueError(f'Ambiguous physical failure variable: {variable}')
        pair = tuple(sorted(matching[0]))
        represented.add(pair)
        pins.append(f'(assert (= |{variable}| {int(pair in pairs)}))')
    if pairs - represented:
        raise ValueError(f'Failure links absent from SMT encoding: {pairs - represented}')
    encoding = encoding.replace('(check-sat)', '') + '\n' + '\n'.join(pins) + '\n(check-sat)\n'
    (output / 'smt_encoding.smt2').write_text(encoding)
    table_start = re.search(r'^Node\s+VRF\s+', text, re.M)
    if not table_start:
        raise ValueError(f'Missing concrete RIB table: {concrete}')
    (output / '0_data_plane.txt').write_text(text[table_start.start():])
    (output / 'rib.txt').write_text(text)
    (output / '0_k_set.txt').write_text('mode=EXACT\n' + ''.join(f'FAILED {line}\n' for line in failed))
    shutil.copy2(concrete / '0_ebgp_routes.txt', output / '0_ebgp_routes.txt')
    (output / '0_hostnames.txt').write_text('\n'.join(devices) + '\n')
    return failed


def run_case(case, args, solve_only=False, previous=None):
    work = args.output / 'cases' / case.name
    if solve_only:
        result = previous
        result["status"] = "ERROR"
    else:
        started = time.perf_counter()
        failed = prepare(args.source, case, work, args.devices)
        result = {'scenario': case.name, 'failed_links': failed, 'status': 'ERROR', 'stages': {}}
        result['preparation_seconds'] = time.perf_counter() - started
    commands = [('route_analysis', '1_route_analyzer.py', []),
                ('slicing', '2_smt_slicer.py', []),
                ('assume_guarantee', '3_assume_guarantee_tester.py', [])]
    flags = ['-o']
    if args.scripts != ORIGINAL_SCRIPTS.resolve():
        flags.append('-c')
    solving_commands = [('line_solving', '4_subspec_simplifier.py', [*flags, '-l']),
                        ('field_solving', '4_subspec_simplifier.py', [*flags, '-f'])]
    for name, script, flags in (solving_commands if solve_only else commands):
        start = time.perf_counter()
        with (work / f'{name}.log').open('w') as log:
            proc = subprocess.run([sys.executable, str(args.scripts / script), *flags, str(work)],
                                  stdout=log, stderr=subprocess.STDOUT)
        result['stages'][name] = {'seconds': time.perf_counter() - start, 'exit_code': proc.returncode}
        if proc.returncode:
            result['error'] = f'{name} returned {proc.returncode}'
            return result
        if name == 'assume_guarantee':
            summary = work / '3_assume_guarantee_test/test_summary.txt'
            content = summary.read_text() if summary.exists() else ''
            rows = re.findall(r'^Device\s+.*Status:\s+(PASS|FAIL)', content, re.M)
            if len(rows) != len(args.devices) or any(row != 'PASS' for row in rows):
                result['status'] = 'AG_FAILED'
                result['error'] = 'Original Traverse forward/reverse checks did not pass for every selected device.'
                return result
    if solve_only:
        expected = [work / '4_subspec_files' / f'{level}_level_subspecs.txt' for level in ['line','field']]
        if not all(path.exists() for path in expected):
            result['error'] = 'Original solver returned success but omitted subspec output files.'
            return result
    result['status'] = 'PASS' if solve_only else 'AG_PASS'
    return result


def validate_failure_universe(source, cases, k):
    """Reject omitted/duplicated scenarios before reporting a complete baseline."""
    nodes = source.joinpath('0_hostnames.txt').read_text().split()
    encoding = source.joinpath('smt_encoding.smt2').read_text()
    suffixes = re.findall(r'\(declare-fun \|\d+_FAILED-EDGE_([^|]+)\| \(\) Int\)', encoding)
    links = sorted({tuple(sorted((a,b))) for suffix in suffixes for a in nodes for b in nodes
                    if a != b and suffix == f'{a}_{b}'})
    expected = {frozenset(combo) for n in range(min(k,len(links))+1)
                for combo in itertools.combinations(links, n)}
    actual = []
    for case in cases:
        text = (case / '0_dataplane.txt').read_text()
        failed = re.findall(r'^FAILED (.+)$', text, re.M)
        actual.append(frozenset(tuple(sorted((line.split(':',1)[0], line.split('--',1)[1].split(':',1)[0])))
                                for line in failed))
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError(f'Incomplete failure universe: expected {len(expected)}, received {len(actual)}, '
                         f'missing {len(expected-set(actual))}, unexpected {len(set(actual)-expected)}')
    return len(links)


def export_concrete(args):
    """Run Batfish failure injection and independent iBDP computation first."""
    repository = TOOLS_DIRECTORY.parent
    destination = args.output / 'concrete'
    destination.mkdir(parents=True)
    log_path = args.output / 'concrete_export.log'
    command = ['bazel', 'test', '//projects/allinone:smt_tests', '--nocache_test_results',
               '--test_output=all',
               '--test_filter=org.batfish.minesweeper.smt.SmtReachabilityTest#testFailureDataplaneEnumeration',
               '--strategy=TestRunner=standalone', '--spawn_strategy=local']
    env = {'SMT_DIRECTORY_PREFIX': str(destination), 'SMT_NETWORK': args.network,
           'SMT_SYMBOLIC': 'false', 'SMT_PROTOCOLS': 'BGP',
           'SMT_ENUMERATE_FAILURES': 'true', 'FAIL_K': str(args.k), 'FAIL_MODE': 'AT_MOST_K'}
    command.extend(f'--test_env={key}={value}' for key,value in env.items())
    start = time.perf_counter()
    with log_path.open('w') as log:
        result = subprocess.run(command, cwd=repository, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Batfish concrete export failed; see {log_path}')
    matches = re.findall(r'^CONCRETE_FAILURE_OUTPUT_DIRECTORY=(.+)$', log_path.read_text(), re.M)
    if not matches:
        raise ValueError(f'Batfish did not report its output directory; see {log_path}')
    root = Path(matches[-1].strip())
    args.concrete = root / 'failure_enumeration' / f'failures_AT_MOST_K_k{args.k}'
    return {'command_wall_seconds_including_build': time.perf_counter()-start,
            'summary': (root / 'failure_export_summary.txt').read_text()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--concrete', type=Path, help='Reuse exported failures_AT_MOST_K_kN inputs')
    mode.add_argument('--network', help='Run Batfish failure injection and export for this network first')
    parser.add_argument('--scripts', type=Path, default=ORIGINAL_SCRIPTS,
                        help='Script directory (default: %(default)s)')
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    parser.add_argument('--devices', type=lambda s: s.split(','), required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--k', type=int, default=2)
    parser.add_argument('--limit', type=int, help='Diagnostic subset; never reported as a complete baseline')
    args = parser.parse_args()
    for key in ['source', 'concrete', 'scripts', 'output']:
        if getattr(args,key) is not None:
            setattr(args, key, getattr(args, key).resolve())
    if args.scripts == TRAVERSE_DIRECTORY:
        args.scripts = ORIGINAL_SCRIPTS.resolve()
    intersection_script = (
        TRAVERSE_INTERSECTION if args.scripts == ORIGINAL_SCRIPTS.resolve()
        else args.scripts / '7_intersection_at_most_k.py'
    )
    if not intersection_script.is_file():
        parser.error(f'Intersection script does not exist: {intersection_script}')
    if args.workers < 1: parser.error('--workers must be positive')
    if (args.source/'0_protocols.txt').read_text().strip().lower() != 'bgp':
        parser.error('The independent Traverse adapter currently requires a BGP-only source')
    if args.output.exists(): parser.error('Output directory already exists; choose a new directory')
    if args.k < 0: parser.error('--k must be nonnegative')
    args.output.mkdir(parents=True)
    export = export_concrete(args) if args.network else {'reused_concrete': str(args.concrete)}
    cases = sorted(p for p in args.concrete.glob('fail*') if p.is_dir() and (p / '0_dataplane.txt').exists())
    if not cases: parser.error('No exported concrete failure scenarios found')
    link_count = validate_failure_universe(args.source, cases, args.k)
    selected = cases[:args.limit] if args.limit else cases
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(lambda case: run_case(case, args), selected))
    preparation_ag_wall = time.perf_counter() - start
    solve_wall = None
    if all(r['status'] == 'AG_PASS' for r in results):
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(lambda item: run_case(item[0], args, True, item[1]), zip(selected, results)))
        solve_wall = time.perf_counter() - start
    complete = len(selected) == len(cases) and all(r['status'] == 'PASS' for r in results)
    intersection_seconds = None
    if complete:
        start = time.perf_counter()
        with (args.output / 'intersection.log').open('w') as log:
            proc = subprocess.run([sys.executable, str(intersection_script),
                                   str(args.output / 'cases'), '--k', str(args.k)], stdout=log, stderr=subprocess.STDOUT)
        intersection_seconds = time.perf_counter() - start
        complete = proc.returncode == 0
    report = {'status': 'PASS' if complete else 'INCOMPLETE', 'equivalence_with_symbolic': 'NOT_CHECKED', 'scripts': str(args.scripts),
              'intersection_script': str(intersection_script),
              'intersection_script_sha256': hashlib.sha256(intersection_script.read_bytes()).hexdigest(),
              'source': str(args.source), 'k': args.k, 'protocols': ['bgp'], 'concrete_export': export,
              'source_sha256': {name: hashlib.sha256((args.source/name).read_bytes()).hexdigest()
                                for name in ['smt_encoding.smt2', '0_dst_ips.txt', '0_ebgp_neighbors.txt', '0_protocols.txt']},
              'intersection_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in (args.output/f'failure_intersection_at_most_k{args.k}').glob('*level_subspecs.txt')},
              'script_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.scripts.glob('[1-47]_*.py')},
              'physical_link_count': link_count, 'input_scenarios': len(cases), 'selected_scenarios': len(selected), 'devices': args.devices,
              'workers': args.workers, 'parallel_unit': 'failure scenario', 'results': results,
              'preparation_and_AG_wall_seconds': preparation_ag_wall,
              'constraint_solving_wall_seconds': solve_wall,
              'baseline_solve_and_intersection_wall_seconds': solve_wall + intersection_seconds if complete else None,
              'constraint_solver_task_seconds': sum(s['seconds'] for r in results for n,s in r['stages'].items() if n in ['line_solving','field_solving']),
              'intersection_seconds': intersection_seconds,
              'note': 'No valid solve-time comparison is available unless all AG checks and all scenario solves pass. Export and AG costs are separate from constraint solving.'}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    lines = [f"Status: {report['status']}", 'Equivalence with symbolic subspecs: NOT_CHECKED', f'Original scripts: {args.scripts}',
             f'Physical links: {link_count}; k={args.k}', f'Concrete scenarios: {len(selected)}/{len(cases)}', f'Workers: {args.workers} (parallel across F)',
             f'Preparation and AG wall seconds (excluded): {preparation_ag_wall:.6f}',
             f'Constraint solving wall seconds: {solve_wall}',
             f'Intersection wall seconds: {intersection_seconds}',
             f"Baseline solve + intersection wall seconds: {report['baseline_solve_and_intersection_wall_seconds']}",
             'Solver time covers original line/field program invocations, including their internal normalization and file output.',
             report['note'], '']
    for result in results:
        lines.extend([f"Scenario: {result['scenario']}", f"Failed links: {', '.join(result['failed_links']) or 'none'}",
                      f"Status: {result['status']}", *[f"  {name}: {value['seconds']:.6f} seconds" for name,value in result['stages'].items()],
                      f"Detail: {result.get('error', 'Completed')}", ''])
    (args.output / 'report.txt').write_text('\n'.join(lines))
    print(args.output / 'report.txt')
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
