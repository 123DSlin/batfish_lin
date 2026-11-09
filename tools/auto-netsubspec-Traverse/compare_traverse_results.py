#!/usr/bin/env python3
"""Compare saved Traverse intersections with saved symbolic final subspecs.

No route generation, failure enumeration, seed construction or constraint projection.
Only output parsing, input provenance checks, equivalence queries and reporting.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1] / "netsubspec"
sys.path.insert(0, str(ROOT))
from utils.util_file import load_field_level_subspecs_from_file, load_line_level_subspecs_from_file
from utils.util_smt import parse_smt2_sexpr, tokenize_smt2_sexpr, serialize_smt2_sexpr, get_bounds_for_multiple_config_variables
from utils.util_symbolic import SmtDocument, SmtSolver, residual_declared_symbols


def expression(text):
    """Read original Traverse's grouped infix AND without changing its meaning."""
    text = re.sub(r'\s*\[from [^\]]+\]\s*$', '', text.strip())
    if text.lower() in {'', 'empty'}:
        return 'true'
    tree = parse_smt2_sexpr(tokenize_smt2_sexpr('(' + text + ')'))
    def convert(node):
        if not isinstance(node, list): return node
        if any(item == 'AND' for item in node):
            if len(node) % 2 != 1 or any(node[i] != 'AND' for i in range(1,len(node),2)):
                raise ValueError('Malformed Traverse infix AND expression')
            return ['and', *[convert(node[i]) for i in range(0,len(node),2)]]
        if len(node) == 1 and isinstance(node[0], list): return convert(node[0])
        return [convert(item) for item in node]
    result = convert(tree)
    return result[0] if isinstance(result,list) and len(result)==1 else result


def conjunction(values):
    if not values: return 'true'
    trees = [expression(value) for value in values]
    return serialize_smt2_sexpr(trees[0] if len(trees)==1 else ['and', *trees])


def read_targets(root, k):
    folder = root / f'failure_intersection_at_most_k{k}'
    result = {}
    for level, loader in [('field',load_field_level_subspecs_from_file), ('line',load_line_level_subspecs_from_file)]:
        path = folder / f'at_most_k{k}_intersection_{level}_level_subspecs.txt'
        if not path.is_file(): raise ValueError(f'Missing Traverse intersection: {path}')
        values = loader(path)
        if not values: raise ValueError(f'Empty/unreadable Traverse intersection: {path}')
        result.update({(level,name): conjunction(parts) for name,parts in values.items()})
    return result


def comparison_context(document, released):
    """Reuse existing field domains and the same target-release convention.

    No behavior/network assertions are assumed, and released target values
    are never pinned. This prevents comparing an implicit legal domain with
    an explicit domain constraint as though they were different specifications.
    """
    pins = {pin.assertion_index:pin for pin in document.config_pins}
    context = [expression(bound.removeprefix('(assert ').removesuffix(')'))
               for bound in get_bounds_for_multiple_config_variables(list(released))]
    def symbols(tree):
        if isinstance(tree,str): return {tree} if tree in document.declarations else set()
        return set().union(*(symbols(child) for child in tree)) if tree else set()
    for index,tree in enumerate(document.assertions):
        if index in pins:
            if pins[index].name not in released: context.append(tree)
        else:
            names = symbols(tree)
            if names and all(name.startswith('Config_') for name in names): context.append(tree)
    return ['and', *context] if context else 'true'


def compare_target(item, document, solver, query_dir):
    level, target, symbolic, traverse = item[:4]
    released = item[4] if len(item)>4 else None
    record = {'level':level, 'target':target, 'device':target.split('_')[1],
              'symbolic_constraint':symbolic, 'traverse_intersection':traverse}
    if symbolic is None or traverse is None:
        return dict(record,status='MISSING_TARGET',seconds=0)
    try:
        expected = expression(traverse)
        symbolic_smt = serialize_smt2_sexpr(expression(symbolic))
        traverse_smt = serialize_smt2_sexpr(expected)
        state = residual_declared_symbols(traverse, document.declarations,
                                          {name for name in document.declarations if name.startswith('Config_')})
        if released is not None and (not released or set(released)-{pin.name for pin in document.config_pins}):
            raise ValueError('Invalid released configuration target set')
        context = comparison_context(document, released) if released is not None else 'true'
        if not solver.satisfiable(document, serialize_smt2_sexpr(context)):
            raise ValueError('Empty configuration comparison domain')
        expected_in_domain = ['and', context, expected]
        candidate_in_domain = serialize_smt2_sexpr(['and',context,expression(symbolic_smt)])
        equal, seconds = solver.equivalent(document, expected_in_domain, candidate_in_domain)
        record['released_configs'] = list(released) if released is not None else []
        record['comparison_context'] = serialize_smt2_sexpr(context)
        record.update(status='EQUIVALENT' if equal else 'NOT_PROVED',seconds=seconds,
                      traverse_state_variables=sorted(state))
        query = document.query(f'(assert {serialize_smt2_sexpr(context)})', f'(assert (not (= {traverse_smt} {symbolic_smt})))', '(check-sat)')
        path = query_dir / (hashlib.sha256(f'{level}:{target}'.encode()).hexdigest()[:16] + '.smt2')
        path.write_text(query)
        record['equivalence_query'] = str(path)
        if not equal:
            try:
                response = solver._invoke(query)
                answer = response.stdout.strip()
                if response.returncode == 0 and answer == 'sat' and not response.stderr.strip():
                    record['status'] = 'NOT_EQUIVALENT'
                    if released:
                        witness_query = query + '(get-value (' + ' '.join(released) + '))\n'
                        witness = solver._invoke(witness_query)
                        if witness.returncode == 0 and not witness.stderr.strip():
                            record['counterexample'] = witness.stdout.strip()
                elif response.returncode or '(error ' in answer or response.stderr.strip():
                    record.update(status='ERROR',error=(response.stderr or response.stdout).strip())
            except subprocess.TimeoutExpired:
                record['status'] = 'UNKNOWN'
        # A configuration subspec must not retain route-state inputs. Do not eliminate
        # these variables in the verifier or silently turn it into another solver pipeline.
        if state:
            record['raw_equivalence_status'] = record['status']
            record['status'] = 'TRAVERSE_HAS_STATE_VARIABLES'
        return record
    except Exception as error:
        return dict(record,status='ERROR',error=str(error),seconds=0)


def render_report(report, output):
    lines = ['TRAVERSE VS SYMBOLIC SUBSPEC VERIFICATION', f"Status: {report['status']}",
             'Independent pipeline status: ' + json.dumps(report.get('pipeline_status',{}),sort_keys=True),
             'This checker reads existing outputs and runs equivalence queries only.',
             'No failures or subspecs are regenerated by this check.',
             'Comparison uses the existing encoded target bounds; other configuration fields stay fixed.',
             'Released target fields are never pinned to their original values.',
             'Counterexamples are SMT assignments; no additional mask/CLI validity assumptions are introduced.',
             f"Traverse run: {report['traverse_directory']}",
             f"Symbolic run: {report['symbolic_directory']}",
             f"Equivalent targets: {report.get('equivalent_count',0)}/{len(report['checks'])}",
             'Validation time is excluded from both production pipelines.', '']
    lines.append('Target outcomes: ' + json.dumps(report.get('status_counts',{}),sort_keys=True))
    for error in report.get('errors',[]): lines.append('ERROR: ' + error)
    for device in sorted({c['device'] for c in report['checks']}):
        lines += ['', f'DEVICE {device}', '=' * 80]
        for check in [c for c in report['checks'] if c['device']==device]:
            lines += [f"{check['level'].upper()}: {check['target']}", f"Result: {check['status']}",
                      f"Traverse intersection: {check['traverse_intersection']}",
                      f"Symbolic constraint: {check['symbolic_constraint']}"]
            if check.get('traverse_state_variables'):
                lines.append('Uneliminated Traverse state variables: ' + ', '.join(check['traverse_state_variables']))
            if check.get('counterexample'): lines.append('Counterexample (released fields): ' + check['counterexample'])
            if check.get('error'): lines.append('ERROR: ' + check['error'])
            lines.append('')
    lines += ['PER-FAILURE TRAVERSE OUTPUTS', '='*80]
    for case in report.get('cases',[]):
        lines += [f"Scenario: {case['scenario']}", 'Failed links: ' + (', '.join(case['failed_links']) or 'none'),
                  f"Original constraints: {Path(report['traverse_directory'])/'cases'/case['scenario']/'4_subspec_files'}", '']
    output.with_suffix('.txt').write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work',type=Path)
    parser.add_argument('--traverse-results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--z3',type=Path)
    parser.add_argument('--workers',type=int,default=4)
    args = parser.parse_args()
    if args.workers < 1: parser.error('--workers must be positive')
    work, traverse, output = args.work.resolve(), args.traverse_results.resolve(), args.output.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    report = {'schema_name':'traverse-symbolic-output-comparison','status':'ERROR',
              'symbolic_directory':str(work),'traverse_directory':str(traverse),'checks':[],'errors':[]}
    started = time.perf_counter()
    try:
        baseline = json.loads((traverse/'report.json').read_text())
        symbolic = json.loads((work/'4_final_subspecs/final_subspecs.json').read_text())
        if baseline['status'] != 'PASS' or symbolic['status'] != 'PASS' or symbolic.get('errors'):
            raise ValueError('Both independent pipelines must have complete PASS outputs')
        report['pipeline_status'] = {'traverse':baseline['status'],'symbolic':symbolic['status']}
        scope = symbolic['scope']
        if baseline['k'] != scope['k'] or set(baseline['devices']) != set(scope['routers']):
            raise ValueError('Failure budget or device scopes differ')
        if baseline.get('protocols') != ['bgp'] or scope['vrf'] != 'default' or scope['plane'] != 'MAIN':
            raise ValueError('This Traverse output adapter requires BGP-only default VRF MAIN scope')
        for name in ['smt_encoding.smt2','0_dst_ips.txt','0_ebgp_neighbors.txt','0_protocols.txt']:
            actual = hashlib.sha256((work/name).read_bytes()).hexdigest()
            if baseline['source_sha256'].get(name) != actual:
                raise ValueError(f'Traverse/symbolic input mismatch: {name}')
        folder = traverse/f"failure_intersection_at_most_k{scope['k']}"
        hashes = baseline.get('intersection_sha256',{})
        for level in ['field','line']:
            name = f"at_most_k{scope['k']}_intersection_{level}_level_subspecs.txt"
            if hashes.get(name) != hashlib.sha256((folder/name).read_bytes()).hexdigest():
                raise ValueError(f'Traverse intersection changed or lacks provenance: {name}')
        doc = SmtDocument.parse((work/'smt_encoding.smt2').read_text())
        originals = read_targets(traverse, scope['k'])
        released = {(level,r['target']):r['configs'] for level,key in [('field','fields'),('line','lines')] for r in symbolic[key]}
        candidates = {(level,r['target']):r['constraint'] for level,key in [('field','fields'),('line','lines')] for r in symbolic[key]}
        query_dir = output.parent/'queries';query_dir.mkdir(exist_ok=True)
        solver = SmtSolver(z3_path=args.z3,timeout_seconds=args.timeout)
        tasks = [(level,target,candidates.get((level,target)),originals.get((level,target)),released.get((level,target),[target])) for level,target in sorted(set(candidates)|set(originals))]
        comparison_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            report['checks'] = list(pool.map(lambda item:compare_target(item,doc,solver,query_dir),tasks))
        report['timing'] = {'validation_equivalence_wall_seconds':time.perf_counter()-comparison_started}
        report['cases'] = baseline['results']
        report['traverse_timing'] = {k:baseline[k] for k in ['constraint_solving_wall_seconds','intersection_seconds','baseline_solve_and_intersection_wall_seconds']}
        report['status_counts'] = {status:sum(c['status']==status for c in report['checks']) for status in sorted({c['status'] for c in report['checks']})}
        report['equivalent_count'] = sum(c['status']=='EQUIVALENT' for c in report['checks'])
        report['status'] = 'PASS' if report['checks'] and report['equivalent_count']==len(report['checks']) else 'FAIL'
        report['source_sha256'] = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [traverse/'report.json',work/'4_final_subspecs/final_subspecs.json']}
    except Exception as error:
        report['errors'].append(str(error))
    report.setdefault('timing',{})['validation_wall_before_render_seconds'] = time.perf_counter()-started
    render_started = time.perf_counter();render_report(report,output)
    report['timing']['report_rendering_wall_seconds'] = time.perf_counter()-render_started
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"Traverse output comparison: {report['status']}; report: {output.with_suffix('.txt')}")
    return 0 if report['status']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
