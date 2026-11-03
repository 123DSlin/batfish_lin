#!/usr/bin/env python3
"""Per-seed local assume/guarantee checks inspired by auto-netsubspec.

Forward SAT is seed admissibility; reverse UNSAT is the stronger guarantee
under peer assumptions, not a second definition of seed admissibility.
"""
import argparse
import itertools
import json
from pathlib import Path
import re
import validate_slices as baseline

ASSUMPTIONS = {'Selected peer predecessor route', 'Remaining peer candidate routes',
               'Selected-peer link state'}
GUARANTEES = {'Current selected route', 'Selected import route',
              'Device control-forwarding state'}
DOMAIN = {'Selected symbolic-route branch guard', 'At-most-k link-failure budget',
          'Link-state bridge'}


def parse_sections(text):
    marker = '; ---- Symbolic Route Consistency Seed ----'
    if marker not in text:
        raise ValueError('Missing seed marker')
    sections = {}
    current = None
    for line in text.split(marker, 1)[1].splitlines():
        if line.startswith('; Seed'):
            current = line.split(': ', 1)[1]
        elif line.startswith('(assert '):
            if current not in ASSUMPTIONS | GUARANTEES | DOMAIN:
                raise ValueError(f'Unclassified assertion section: {current}')
            assertion = re.sub(r'^\(assert \(! (.*) :named [^ ]+\)\)$', r'(assert \1)', line)
            sections.setdefault(current, []).append(assertion)
    if not sections.get('Current selected route') or not sections.get('Selected symbolic-route branch guard'):
        raise ValueError('Missing current-route guarantee or branch guard')
    return sections


def select(sections, names):
    return [a for name, assertions in sections.items() if name in names for a in assertions]


def queries(local, domain, assumptions, guarantees):
    if not guarantees:
        raise ValueError('Empty guarantee')
    inputs = local + domain + assumptions
    reverse = inputs + ['(assert (not (and ' + ' '.join(map(baseline.body, guarantees)) + ')))']
    return inputs, inputs + guarantees, reverse


def run(work, output, k, per_scenario=False):
    output.mkdir(parents=True, exist_ok=True)
    report_path = work / '2_consistency_check' / 'input_hashes.json'
    hashes = {name: baseline.hashlib.sha256((work / name).read_bytes()).hexdigest()
              for name in ('smt_encoding.smt2', 'symbolic_route.json')}
    if not report_path.exists() or json.loads(report_path.read_text()) != hashes:
        raise ValueError('Stale/missing Stage 2 input provenance')
    stage_report = json.loads((work / '2_consistency_check' / 'consistency_report.json').read_text())
    if stage_report['scope']['k'] != k:
        raise ValueError('Requested k differs from constructed seeds; regenerate Stage 2')
    declarations, _ = baseline.mod.load_normalized_encoding(work / 'smt_encoding.smt2')
    declared = baseline.mod._declared_symbol_set(declarations)
    edges = sorted(v for v in declared if 'FAILED-EDGE_' in v and 'Loopback' not in v)
    results = []
    paths = sorted((work / '2_consistency_check' / 'seeds').rglob('*.smt2'))
    if not paths:
        raise ValueError('No seeds')
    for path in paths:
        sections = parse_sections(path.read_text())
        router = path.parent.name
        local_decl, local = baseline.mod.load_normalized_encoding(
            work / '1_sliced_device_smt_encoding' / f'sliced_{router}_smt_encoding.smt2')
        seed_decl = baseline.mod.extract_declare_fun_expressions(path.read_text().splitlines())
        decl = list(dict.fromkeys(declarations + local_decl + seed_decl))
        assumptions = select(sections, ASSUMPTIONS)
        guarantees = select(sections, GUARANTEES)
        if per_scenario:
            cases = [failed for count in range(min(k, len(edges)) + 1)
                     for failed in itertools.combinations(edges, count)]
        else:
            cases = [None]  # Preserve all symbolic conditions in the constructed seed.
        _, literal_seed = baseline.mod.load_normalized_encoding(path)
        literal_status = baseline.solve(decl, literal_seed)
        for failed in cases:
            pins = [] if failed is None else [
                f'(assert (= {edge} {int(edge in failed)}))' for edge in edges]
            domain = pins + select(sections, DOMAIN)
            record = {'seed': str(path.relative_to(work)),
                      'seed_sha256': baseline.hashlib.sha256(path.read_bytes()).hexdigest(),
                      'constructed_seed': literal_status}
            if failed is not None:
                record['failed'] = list(failed)
                applicable = baseline.solve(decl, domain)
                record['guard_feasible'] = applicable
                if applicable != 'sat':
                    record['status'] = 'OUTSIDE_GUARD' if applicable == 'unsat' else 'GUARD_INCONCLUSIVE'
                    results.append(record)
                    continue
            inputs, forward, reverse = queries(local, domain, assumptions, guarantees)
            record.update(environment=baseline.solve(decl, inputs),
                          forward=baseline.solve(decl, forward),
                          reverse=baseline.solve(decl, reverse))
            if record['environment'] != 'sat':
                record['status'] = 'INVALID_OR_INCONCLUSIVE_ENVIRONMENT'
            elif literal_status != 'sat' or record['forward'] != 'sat':
                record['status'] = 'SEED_NOT_ADMISSIBLE_OR_INCONCLUSIVE'
            elif record['reverse'] == 'unsat':
                record['status'] = 'FORWARD_AND_REVERSE_PASS'
            elif record['reverse'] == 'sat':
                record['status'] = 'ADMISSIBLE_WITH_ALTERNATIVE_BEHAVIOR'
            else:
                record['status'] = 'REVERSE_INCONCLUSIVE'
            folder = output / router / path.stem
            if failed is not None:
                folder = folder / f'case_{len(results):04d}'
            folder.mkdir(parents=True, exist_ok=True)
            for name, query in [('environment', inputs), ('forward', forward), ('reverse', reverse)]:
                (folder / f'{name}.smt2').write_text('\n'.join([*decl, *query, '(check-sat)']) + '\n')
            record['artifact_directory'] = str(folder.relative_to(output))
            results.append(record)
    active = [r for r in results if r.get('guard_feasible', 'sat') == 'sat']
    report = {'input_hashes': hashes, 'mode': 'per_scenario_audit' if per_scenario else 'constructed_seed', 'k': k, 'checks': results,
              'admissibility_pass': bool(active) and all(r.get('forward') == 'sat' and r['constructed_seed'] == 'sat' for r in active)
                  and all(r.get('guard_feasible', 'sat') in ('sat', 'unsat') for r in results),
              'assume_guarantee_pass': bool(active) and all(r['status'] == 'FORWARD_AND_REVERSE_PASS' for r in active)
                  and all(r.get('guard_feasible', 'sat') in ('sat', 'unsat') for r in results)}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    from collections import Counter
    print(json.dumps({key: report[key] for key in ('admissibility_pass', 'assume_guarantee_pass')} |
                     {'statuses': dict(Counter(r['status'] for r in results))}, indent=2))
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--per-scenario', action='store_true', help='Optional exhaustive scenario audit; default checks each complete seed')
    parser.add_argument('--k', type=int, default=2)
    args = parser.parse_args()
    if args.k < 0:
        parser.error('k must be nonnegative')
    result = run(args.work_dir, args.output, args.k, args.per_scenario)
    raise SystemExit(0 if result['assume_guarantee_pass'] else 1)
