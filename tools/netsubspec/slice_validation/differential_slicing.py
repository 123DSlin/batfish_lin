#!/usr/bin/env python3
"""Compare an immutable pre-refactor checkout with the current slicer/pipeline.

Slices and seed files must match byte-for-byte. Reports are compared after
removing only timestamps, solver timing, work-directory paths, and the hash of
that non-deterministic source report. No route/configuration formulas or seed
hashes are ignored. Original input/output directories are never modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
VOLATILE = {'generated_at', 'solver_seconds', 'source_sha256'}


def canonical(value, work):
    if isinstance(value, dict):
        return {k: canonical(v, work) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [canonical(v, work) for v in value]
    if isinstance(value, str):
        return value.replace(str(work), '<WORK>')
    return value


def inputs(source, target):
    target.mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file() and (path.name.startswith('0_') or path.name in ('smt_encoding.smt2', 'symbolic_route.json')):
            (target / path.name).symlink_to(path.resolve())


def files(directory, suffix='.smt2'):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*' + suffix)} if directory.exists() else {}


def execute(root, work, stage, k, log, explicit=False):
    names = {1: '1_smt_slicer.py', 2: '2_consistency_checker.py',
             3: '3_branch_simplifier.py', 4: '4_branch_intersection.py'}
    cmd = [sys.executable, str(root / names[stage]), str(work)]
    if stage in (1, 2):
        cmd += ['--k', str(k)]
    if stage == 1 and explicit:
        cmd += ['--slicing-protocol', 'bgp']
    if stage == 3:
        cmd += ['--workers', '4']
    start = time.monotonic()
    with log.open('w') as stream:
        p = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, timeout=1200)
    return {'exit_code': p.returncode, 'seconds': round(time.monotonic() - start, 3), 'log': str(log)}


def run(baseline, output):
    output.mkdir(parents=True, exist_ok=True)
    runs = Path(tempfile.mkdtemp(prefix='netsubspec_adapter_diff_'))
    fixtures = ROOT / 'slice_validation'
    sources = [(f'{name}_k{k}', fixtures / name, k, False)
               for name in ('symbolic_output_0009', 'symbolic_output_0010') for k in (1, 2)]
    sources += [(f'0083_k{k}', ROOT / 'pipeline_runs' / '0083_k2', k, k == 2) for k in (1, 2)]
    sources += [('missing_json', fixtures / 'symbolic_output_0005', 1, False)]
    report = {'baseline_root': str(baseline), 'current_root': str(ROOT), 'runs_root': str(runs),
              'baseline_slicer_sha256': hashlib.sha256((baseline / '1_smt_slicer.py').read_bytes()).hexdigest(),
              'report_normalization': sorted(VOLATILE), 'meaning_of_pass': 'no behavioral regression; pre-existing failures are preserved and reported separately', 'cases': []}
    for name, source, k, full in sources:
        row = {'case': name, 'k': k, 'source': str(source), 'checks': {}, 'stages': {}}
        works = {side: runs / name / side for side in ('before', 'after', 'explicit_bgp')}
        for work in works.values():
            inputs(source, work)
        input_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()
                        if p.is_file() and p.name in ('smt_encoding.smt2', 'symbolic_route.json')}
        row['input_hashes'] = input_hashes
        for side, root in [('before', baseline), ('after', ROOT), ('explicit_bgp', ROOT)]:
            row['stages'][side] = {1: execute(root, works[side], 1, k, output / f'{name}_{side}_stage1.log', side == 'explicit_bgp')}
        codes = [row['stages'][side][1]['exit_code'] for side in works]
        row['checks']['stage1_exit_codes_equal'] = len(set(codes)) == 1
        row['checks']['stage1_expected_outcome'] = codes == ([2, 2, 2] if name == 'missing_json' else [0, 0, 0])
        if codes == [0, 0, 0]:
            snapshots = [files(works[side] / '1_sliced_device_smt_encoding') for side in works]
            row['slice_hashes'] = snapshots[0]
            row['checks']['slice_bytes_equal'] = snapshots[0] == snapshots[1] == snapshots[2] and bool(snapshots[0])
            for side, root in [('before', baseline), ('after', ROOT)]:
                row['stages'][side][2] = execute(root, works[side], 2, k, output / f'{name}_{side}_stage2.log')
            row['checks']['stage2_exit_codes_equal'] = row['stages']['before'][2]['exit_code'] == row['stages']['after'][2]['exit_code']
            row['baseline_stage2_pass'] = row['stages']['before'][2]['exit_code'] == 0
            for side in ('before', 'after'):
                path = works[side] / '2_consistency_check' / 'consistency_report.json'
                if path.exists():
                    (output / f'{name}_{side}_consistency_report.json').write_bytes(path.read_bytes())
            reports = [json.loads((works[side] / '2_consistency_check' / 'consistency_report.json').read_text()) for side in ('before', 'after')]
            row['checks']['stage2_semantic_report_equal'] = canonical(reports[0], works['before']) == canonical(reports[1], works['after'])
            if name.startswith('0083'):
                row['checks']['stage2_required_pass'] = row['baseline_stage2_pass'] and row['stages']['after'][2]['exit_code'] == 0
            all_seeds = [files(works[side] / '2_consistency_check' / 'seeds') for side in ('before', 'after')]
            row['checks']['all_generated_seed_bytes_equal'] = all_seeds[0] == all_seeds[1]
            if row['baseline_stage2_pass'] and row['stages']['after'][2]['exit_code'] == 0:
                seed_hashes = [files(works[side] / '2_consistency_check' / 'seeds') for side in ('before', 'after')]
                row['seed_count'] = len(seed_hashes[0])
                row['checks']['seed_bytes_equal'] = seed_hashes[0] == seed_hashes[1] and bool(seed_hashes[0])
                contract_codes = {}
                for side in ('before', 'after'):
                    # Generation and immutable input hashes are recorded in this run.
                    (works[side] / '2_consistency_check' / 'input_hashes.json').write_text(json.dumps(input_hashes))
                    cmd = [sys.executable, str(ROOT / 'slice_validation' / 'check_seed_contracts.py'),
                           '--work-dir', str(works[side]), '--output', str(works[side] / 'contracts'), '--k', str(k)]
                    with (output / f'{name}_{side}_contracts.log').open('w') as stream:
                        proc = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
                    contract_codes[side] = proc.returncode
                    if name.startswith('0083'):
                        row['checks'][side + '_contracts_required_pass'] = proc.returncode == 0
                a = json.loads((works['before'] / 'contracts' / 'report.json').read_text())
                b = json.loads((works['after'] / 'contracts' / 'report.json').read_text())
                row['baseline_contracts_pass'] = contract_codes['before'] == 0
                row['checks']['contracts_exit_codes_equal'] = contract_codes['before'] == contract_codes['after']
                for side, data in [('before', a), ('after', b)]:
                    (output / f'{name}_{side}_contracts_report.json').write_text(json.dumps(data, indent=2) + '\n')
                row['checks']['contracts_equal'] = canonical(a, works['before']) == canonical(b, works['after'])
                if full:
                    for stage, folder, filename in [(3, '3_branch_subspecs', 'branch_subspecs.json'),
                                                    (4, '4_final_subspecs', 'final_subspecs.json')]:
                        for side, root in [('before', baseline), ('after', ROOT)]:
                            row['stages'][side][stage] = execute(root, works[side], stage, k, output / f'{name}_{side}_stage{stage}.log')
                        row['checks'][f'stage{stage}_pass'] = all(row['stages'][side][stage]['exit_code'] == 0 for side in ('before', 'after'))
                        if not row['checks'][f'stage{stage}_pass']:
                            break
                        a = json.loads((works['before'] / folder / filename).read_text())
                        b = json.loads((works['after'] / folder / filename).read_text())
                        row['checks'][f'stage{stage}_semantic_report_equal'] = canonical(a, works['before']) == canonical(b, works['after'])
                        (output / f'{name}_before_{filename}').write_text(json.dumps(a, indent=2) + '\n')
                        (output / f'{name}_after_{filename}').write_text(json.dumps(b, indent=2) + '\n')
        row['passed'] = bool(row['checks']) and all(row['checks'].values())
        row['baseline_health'] = 'PRE_EXISTING_FAILURE' if row.get('baseline_stage2_pass') is False or row.get('baseline_contracts_pass') is False else 'EXPECTED_OUTCOME'
        report['cases'].append(row)
        report['passed'] = all(case['passed'] for case in report['cases'])
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f'{name}: {"PASS" if row["passed"] else "FAIL"} {row["checks"]}', flush=True)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.baseline_root.resolve(), args.output.resolve())
    raise SystemExit(0 if report['passed'] else 1)
