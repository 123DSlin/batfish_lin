#!/usr/bin/env python3
"""Conservative dependency slicing and exhaustive fixed-failure branch validation."""
import argparse
import importlib.util
import itertools
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from observable import Observables

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('validation_slicer', ROOT / '1_smt_slicer.py')
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def body(assertion):
    return assertion[len('(assert '):-1]


def solve(declarations, assertions, timeout=20):
    text = '\n'.join(['(set-option :timeout 15000)', *declarations, *assertions, '(check-sat)'])
    try:
        result = subprocess.run([shutil.which('z3') or 'z3', '-in'], input=text,
                                text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 'timeout'
    lines = result.stdout.strip().splitlines()
    if result.returncode or any('error' in line.lower() for line in lines):
        raise RuntimeError(result.stdout + result.stderr)
    if not lines or lines[-1] not in ('sat', 'unsat', 'unknown'):
        raise RuntimeError(result.stdout + result.stderr)
    return lines[-1]


def closed_slice(assertions, declared, roots):
    """Undirected assertion hypergraph closure: never invent boundary inputs."""
    refs = [set(mod.extract_symbolic_variables(a)) & declared for a in assertions]
    symbols = set(roots)
    chosen = {i for i, ref in enumerate(refs) if not ref}
    changed = True
    while changed:
        changed = False
        for i, ref in enumerate(refs):
            if i not in chosen and ref & symbols:
                chosen.add(i)
                symbols.update(ref)
                changed = True
    return [a for i, a in enumerate(assertions) if i in chosen], symbols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / '0083')
    parser.add_argument('--closed-only', action='store_true', help='Generate conservative slices without claiming branch validation')
    parser.add_argument('--allow-historical-seeds', action='store_true', help='Audit archived seeds only; never current-input acceptance')
    parser.add_argument('--k', type=int, default=2)
    args = parser.parse_args()
    if args.k < 0:
        parser.error('k must be non-negative')
    stage_report = args.work_dir / '2_consistency_check' / 'consistency_report.json'
    if not args.allow_historical_seeds and not args.closed_only:
        status = json.loads(stage_report.read_text())
        if status.get('status') != 'PASS':
            raise RuntimeError('Current Stage 2 is not PASS; inspect its errors before baseline validation')
        manifest = args.work_dir / '2_consistency_check' / 'input_hashes.json'
        expected_hashes = {name: hashlib.sha256((args.work_dir / name).read_bytes()).hexdigest() for name in ('smt_encoding.smt2', 'symbolic_route.json')}
        if not manifest.exists() or json.loads(manifest.read_text()) != expected_hashes:
            raise RuntimeError('Missing or stale input provenance; regenerate Stage 2 in this experiment')
    args.output.mkdir(parents=True, exist_ok=True)
    declarations, assertions = mod.load_normalized_encoding(args.work_dir / 'smt_encoding.smt2')
    declared = mod._declared_symbol_set(declarations)
    # Remove the property machinery explicitly; keep destination, config and fault assumptions.
    network = [a for a in assertions if not any('reachable' in v for v in mod.extract_symbolic_variables(a))]
    edges = sorted(v for v in declared if 'FAILED-EDGE_' in v and 'Loopback' not in v)
    scopes = mod.build_device_semantic_scopes(args.work_dir, declarations)
    sizes = {}
    closed = {}
    legacy = {}
    for router, scope in scopes.items():
        sliced, symbols = closed_slice(network, declared, scope.local_symbols)
        selected_decl = [d for d in declarations if mod._declared_symbol_set([d]) & symbols]
        (args.output / f'closed_{router}.smt2').write_text('\n'.join([*selected_decl, *sliced, '(check-sat)']) + '\n')
        closed[router] = sliced
        old_path = args.work_dir / '1_sliced_device_smt_encoding' / f'sliced_{router}_smt_encoding.smt2'
        if not args.closed_only:
            _, legacy[router] = mod.load_normalized_encoding(old_path)
        sizes[router] = {'assertions': len(sliced), 'network_assertions': len(network),
                         'boundary_inputs': 0}
    if args.closed_only:
        (args.output / 'closed_slice_manifest.json').write_text(json.dumps({'branch_validation': 'NOT_RUN', 'sizes': sizes}, indent=2) + '\n')
        print(json.dumps(sizes, indent=2))
        return 0
    seed_paths = sorted((args.work_dir / '2_consistency_check' / 'seeds').rglob('*.smt2'))
    if not seed_paths:
        raise RuntimeError('No branch seeds: generate them with Stage 2 first')
    seeds = []
    for path in seed_paths:
        text = path.read_text()
        if '; ---- Symbolic Route Consistency Seed ----' not in text:
            raise RuntimeError(f'Unrecognized seed format: {path}')
        tail = text.split('; ---- Symbolic Route Consistency Seed ----', 1)[1]
        sections = {}
        current = None
        for line in tail.splitlines():
            if line.startswith('; Seed'):
                current = line.split(': ', 1)[1]
                sections[current] = []
            elif line.startswith('(assert '):
                sections.setdefault(current, []).append(line)
        guard = sections['Selected symbolic-route branch guard']
        bridges = sections.get('Link-state bridge', [])
        expected = [a for section, values in sections.items() if section not in
                    ('Selected symbolic-route branch guard', 'At-most-k link-failure budget', 'Link-state bridge') for a in values]
        # Drop :named annotations to negate conjunctions without name side effects.
        def unname(a):
            return re.sub(r'^\(assert \(! (.*) :named [^ ]+\)\)$', r'(assert \1)', a)
        guard = list(map(unname, guard))
        bridges = list(map(unname, bridges))
        expected = list(map(unname, expected))
        if not guard or not expected:
            raise RuntimeError(f'Empty guard or expected behavior: {path}')
        extra_decl = mod.extract_declare_fun_expressions(text.splitlines())
        extra_decl = [d for d in extra_decl if not (mod._declared_symbol_set([d]) & declared)]
        seeds.append((path, extra_decl, guard, bridges, expected))
    observable = Observables(args.work_dir)
    report = {'historical_seeds': args.allow_historical_seeds, 'scope': 'fixed configuration, destination, at-most-k physical link failures; MAIN/BGP',
              'k': args.k, 'source_sha256': hashlib.sha256((args.work_dir / 'smt_encoding.smt2').read_bytes()).hexdigest(), 'slice_sizes': sizes, 'scenarios': [], 'branch_checks': [], 'slice_checks': [], 'coverage_checks': [], 'observable_checks': [], 'local_abstraction_checks': []}
    for count in range(min(args.k, len(edges)) + 1):
        for failed in itertools.combinations(edges, count):
            pins = [f'(assert (= {e} {int(e in failed)}))' for e in edges]
            base = network + pins
            status = solve(declarations, base)
            report['scenarios'].append({'failed': list(failed), 'baseline': status})
            for router in scopes:
                vector, description = observable.expected(router, set(failed), declared)
                disagreement = '(assert (not (and ' + ' '.join(map(body, vector)) + ')))'
                forward = solve(declarations, base + [disagreement])
                reverse = solve(declarations, base + vector)
                record = {'router': router, 'failed': list(failed), 'expected': description,
                          'minesweeper_outside_symbolic': forward,
                          'symbolic_realizable_in_minesweeper': reverse}
                if forward == 'sat' or reverse == 'unsat':
                    name = f'observable_{len(report["observable_checks"]):04d}.smt2'
                    query = base + ([disagreement] if forward == 'sat' else vector)
                    (args.output / name).write_text('\n'.join([*declarations, *query, '(check-sat)', '(get-model)']))
                    record['artifact'] = name
                report['observable_checks'].append(record)
                local = solve(declarations, legacy[router] + pins + [disagreement])
                classification = ('ABSTRACTION_ONLY' if local == 'sat' and forward == 'unsat'
                                  else 'REAL_COUNTEREXAMPLE' if forward == 'sat'
                                  else 'NO_LOCAL_COUNTEREXAMPLE' if local == 'unsat'
                                  else 'INCONCLUSIVE')
                report['local_abstraction_checks'].append({
                    'router': router, 'failed': list(failed), 'local_counterexample': local,
                    'full_counterexample': forward, 'classification': classification})
            for router in scopes:
                omitted = [a for a in network if a not in set(closed[router])]
                # Closure makes omitted constraints symbol-disjoint from the slice.
                extension = solve(declarations, omitted + pins)
                neg = '(assert (not (and ' + ' '.join(map(body, legacy[router])) + ')))'
                necessary = solve(declarations, base + [neg])
                report['slice_checks'].append({'router': router, 'failed': list(failed),
                    'omitted_component': extension, 'full_violates_legacy': necessary})
            for router in scopes:
                group = [seed for seed in seeds if seed[0].parent.name == router]
                extras = list(dict.fromkeys(d for seed in group for d in seed[1]))
                bridges_all = list(dict.fromkeys(a for seed in group for a in seed[3]))
                guard_union = '(or ' + ' '.join('(and ' + ' '.join(map(body, seed[2])) + ')' for seed in group) + ')'
                uncovered = solve(declarations + extras, base + bridges_all + [
                    f'(assert |0_{router}_OVERALL_BEST_None_permitted|)',
                    f'(assert (not {guard_union}))'])
                report['coverage_checks'].append({'router': router, 'failed': list(failed), 'uncovered_valid_route': uncovered})
            for path, extra, guard, bridges, expected in seeds:
                domain = base + bridges + guard
                feasible = solve(declarations + extra, domain)
                record = {'seed': str(path.relative_to(args.work_dir)), 'failed': list(failed), 'feasible': feasible}
                record['symbolic_guard_feasible'] = solve(declarations + extra, pins + bridges + guard)
                if feasible == 'sat':
                    record['compatible'] = solve(declarations + extra, domain + expected)
                    negation = '(assert (not (and ' + ' '.join(map(body, expected)) + ')))'
                    record['counterexample'] = solve(declarations + extra, domain + [negation])
                    if record['counterexample'] == 'sat':
                        name = f'counterexample_{len(report["branch_checks"]):04d}.smt2'
                        (args.output / name).write_text('\n'.join([*declarations, *extra, *domain, negation, '(check-sat)', '(get-model)']))
                        record['artifact'] = name
                report['branch_checks'].append(record)
    report['passed'] = (all(s['baseline'] == 'sat' for s in report['scenarios']) and
        all(r['classification'] not in ('INCONCLUSIVE', 'REAL_COUNTEREXAMPLE') for r in report['local_abstraction_checks']) and
        all(r['minesweeper_outside_symbolic'] == 'unsat' and r['symbolic_realizable_in_minesweeper'] == 'sat' for r in report['observable_checks']) and
        all(r['uncovered_valid_route'] == 'unsat' for r in report['coverage_checks']) and
        all(r['omitted_component'] == 'sat' and r['full_violates_legacy'] == 'unsat' for r in report['slice_checks']) and
        all(r['symbolic_guard_feasible'] in ('sat', 'unsat') and r['symbolic_guard_feasible'] == r['feasible'] and r['feasible'] in ('sat', 'unsat') and (r['feasible'] == 'unsat' or
            (r.get('compatible') == 'sat' and r.get('counterexample') == 'unsat')) for r in report['branch_checks']))
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'scenarios': len(report['scenarios']),
                      'branch_checks': len(report['branch_checks']), 'slice_sizes': sizes,
                      'observable_checks': len(report['observable_checks']),
                      'no_route_checks': sum(not r['expected']['has_route'] for r in report['observable_checks']),
                      'abstraction_only': sum(r['classification'] == 'ABSTRACTION_ONLY' for r in report['local_abstraction_checks']),
                      'counterexamples': sum(r.get('counterexample') == 'sat' for r in report['branch_checks'])}, indent=2))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
