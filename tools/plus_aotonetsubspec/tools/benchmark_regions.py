#!/usr/bin/env python3
"""Bounded, reproducible comparison of enumeration, direct QE and region CEGAR.

Each case runs in a separate process group; a wall timeout kills its solver too.
All backends share the native model, reference Support and candidate-scope gate.
The enumeration oracle classifies missing Support rather than aborting the domain.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from property_model import load_property_model
from property_regions import RegionSolver, full_model
from property_subspec import _parse_pins, _solve_assignments_oracle
from region_smt import QueryRunner, RegionFailure, ast
from utils.util_symbolic import SmtSolver, SubspecificationError

ENABLE = 'Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_enable'
COST = ENABLE.removesuffix('enable') + 'cost'


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path, help='prepared Demo1 input directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--upper', type=int, nargs='+', default=[10, 100, 1000, 65534])
    parser.add_argument('--backends', nargs='+', choices=['enumerate', 'direct', 'cegar'],
                        default=['enumerate', 'direct', 'cegar'])
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--wall-timeout', type=float, default=60)
    parser.add_argument('--query-timeout', type=float, default=15)
    parser.add_argument('--max-oracle-checks', type=int, default=1000000)
    parser.add_argument('--worker', choices=['enumerate', 'direct', 'cegar'], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (args.repeats < 1 or args.wall_timeout <= 0 or args.query_timeout <= 0
            or args.max_oracle_checks < 1 or any(not 0 <= value <= 65534 for value in args.upper)):
        parser.error('invalid domain or resource limit')
    return args


def worker(args):
    start = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='INCOMPLETE', backend=args.worker, cost_maximum=args.upper[0])
    runner = None
    try:
        model = full_model(load_property_model(args.work, 2), args.work)
        targets = _parse_pins(model, [ENABLE, COST], (0, args.upper[0]))
        executable = SmtSolver().z3_path
        runner = QueryRunner(model.document, executable, args.query_timeout, args.output/'evidence')
        engine = RegionSolver(model, targets, 2, runner, bad_strategy=(
                              'direct' if args.worker == 'direct' else 'cegar'))
        if args.worker != 'enumerate':
            report.update(engine.solve())
        else:
            engine.reference_support()
            engine.candidate_gate()
            engine.single_path_gate()
            result = _solve_assignments_oracle(model, targets, 2, args.output, executable,
                                              args.query_timeout, args.max_oracle_checks,
                                              classify_support=True)
            for key in ('status', 'allowed_constraint', 'bad_constraint', 'support_constraint',
                        'configuration_values_enumerated', 'model_coverage_checks'):
                report[key] = result[key]
            # This count includes solver check-sat commands, not process launches.
            invoked = [p for p in args.output.glob('*.smt2') if p.name != 'allowed.smt2']
            report['oracle_check_sat_count'] = sum(p.read_text().count('(check-sat)') for p in invoked)
            report['oracle_invocation_count'] = len(invoked)
            report['max_oracle_query_bytes'] = max((p.stat().st_size for p in args.output.glob('*.smt2')), default=0)
        report['output_bytes'] = len(report['allowed_constraint'].encode())
    except (SubspecificationError, ValueError, OSError) as exc:
        report.update(status=exc.status.value if isinstance(exc, RegionFailure) else 'INCOMPLETE', error=str(exc))
    finally:
        if runner:
            report['metrics'] = runner.metrics()
        units = 1 if sys.platform == 'darwin' else 1024
        report['max_worker_or_solver_rss_bytes'] = units * max(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        report['rss_definition'] = 'maximum individual worker/solver RSS; not simultaneous process-tree sum'
        report['total_seconds'] = time.monotonic() - start
        (args.output/'result.json').write_text(json.dumps(report, indent=2)+'\n')


def main():
    args = arguments()
    if args.worker:
        worker(args)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    version = subprocess.run([str(SmtSolver().z3_path), '--version'], capture_output=True, text=True, check=True)
    environment = dict(python=sys.version, platform=platform.platform(), z3=version.stdout.strip(),
                       work=str(args.work.resolve()), native_sha256=sha256((args.work/'smt_encoding.smt2').read_bytes()).hexdigest(),
                       wall_timeout=args.wall_timeout, query_timeout=args.query_timeout,
                       repeats=args.repeats, max_oracle_checks=args.max_oracle_checks)
    environment['source_sha256'] = {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in
                                    ('property_model.py', 'property_subspec.py', 'property_regions.py',
                                     'region_smt.py', 'utils/util_symbolic.py', 'tools/benchmark_regions.py')}
    (args.output/'environment.json').write_text(json.dumps(environment, indent=2)+'\n')
    rows = []
    for upper in args.upper:
        for backend in args.backends:
            for repeat in range(args.repeats):
                directory = args.output/f'{backend}_{upper}_{repeat}'
                command = [sys.executable, '-B', str(Path(__file__).resolve()), str(args.work.resolve()),
                           '--output', str(directory.resolve()), '--worker', backend, '--upper', str(upper),
                           '--query-timeout', str(args.query_timeout),
                           '--max-oracle-checks', str(args.max_oracle_checks)]
                start = time.monotonic()
                with (args.output/f'{directory.name}.log').open('w') as log:
                    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    try:
                        process.wait(timeout=args.wall_timeout)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                path = directory/'result.json'
                row = json.loads(path.read_text()) if path.exists() else dict(status='INCOMPLETE', error='wall timeout or worker failure')
                partial_metrics = directory/'evidence/queries.json'
                if 'metrics' not in row and partial_metrics.exists():
                    row['metrics'] = json.loads(partial_metrics.read_text())
                row.update(backend=backend, cost_maximum=upper, repeat=repeat,
                           wall_seconds=time.monotonic()-start, exit_code=process.returncode)
                rows.append(row)
                (args.output/'summary.json').write_text(json.dumps(rows, indent=2)+'\n')
                print(backend, upper, row['status'], round(row['wall_seconds'], 3), flush=True)
    # Compare successful outputs under the same domain; preserve the SMT proof.
    model = full_model(load_property_model(args.work, 2), args.work)
    checker = QueryRunner(model.document, SmtSolver().z3_path, args.query_timeout, args.output/'equivalence')
    for upper in args.upper:
        completed = [row for row in rows if row['cost_maximum'] == upper and row['status'] == 'PASS']
        for index, row in enumerate(completed[1:]):
            for key in ('bad_constraint', 'support_constraint', 'allowed_constraint'):
                checker.prove(f'compare_{upper}_{index}_{key}',
                              ['xor', ast(completed[0][key]), ast(row[key])])
    (args.output/'equivalence.json').write_text(json.dumps(checker.metrics(), indent=2)+'\n')


if __name__ == '__main__':
    main()
