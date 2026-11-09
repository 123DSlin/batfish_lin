#!/usr/bin/env python3
"""Profile one existing symbolic seed without changing its solving algorithm.

Nested operations have inclusive and exclusive times. Only exclusive category
sums partition elapsed time. Output equivalence is checked after timing stops.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from functools import wraps
from importlib import import_module
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils.util_smt import parse_smt2_sexpr, tokenize_smt2_sexpr, subspec_string_to_smt2_and
from utils.util_symbolic import SmtDocument, SmtSolver


class Recorder:
    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.events = []
        self.processes = []
        self.stack = []
        self.identity = {}
        self.undo = []

    @contextmanager
    def span(self, name, category, **metadata):
        started = self.clock()
        event = dict(self.identity, **metadata, name=name, category=category,
                     parent=self.stack[-1]['name'] if self.stack else None,
                     children_seconds=0.0, status='OK')
        self.stack.append(event)
        try:
            yield event
        except BaseException:
            event['status'] = 'ERROR'
            raise
        finally:
            elapsed = self.clock() - started
            self.stack.pop()
            event.update(inclusive_seconds=elapsed,
                         exclusive_seconds=max(0.0, elapsed-event.pop('children_seconds')))
            if self.stack: self.stack[-1]['children_seconds'] += elapsed
            self.events.append(event)

    def replace(self, owner, name, replacement):
        original = getattr(owner,name)
        self.undo.append((owner,name,original))
        setattr(owner,name,replacement)
        return original

    def wrap(self, owner, name, category):
        original = getattr(owner,name)
        @wraps(original)
        def measured(*args,**kwargs):
            with self.span(name,category) as event:
                result = original(*args,**kwargs)
                if name == 'equivalent': event['equivalent'] = result[0]
                if name == 'entails': event['entailed'] = result
                if name == 'project': event['operation'] = args[4] if len(args)>4 else kwargs.get('operation')
                return result
        self.replace(owner,name,measured)

    def install(self,module):
        for name,category in [('project','projection'),('simplify','simplification'),
                              ('equivalent','equivalence'),('entails','implication'),
                              ('remove_redundant_atoms','simplification'),
                              ('reference_simplify','reference_simplification')]:
            self.wrap(module.SmtSolver,name,category)
        self.wrap(module.SmtSolver, 'solve_reference_seed', 'reference_simplification')
        self.wrap(module._SmtDocument, 'quantified_projection', 'formula_construction')
        self.wrap(module._SmtDocument, 'reference_seed_expression', 'scope_preparation')
        original_project = module.SymbolicSubspecifier._project
        @wraps(original_project)
        def target(*args,**kwargs):
            before = self.identity
            self.identity = dict(level=kwargs['level'],target=kwargs['identifier'])
            try:
                with self.span('target','target_overhead'):
                    return original_project(*args,**kwargs)
            finally: self.identity = before
        self.replace(module.SymbolicSubspecifier,'_project',target)
        original_fields = module._field_targets
        recorder = self
        class TargetTuple(tuple):
            def __iter__(self):
                for identifier,pins in tuple.__iter__(self):
                    before = recorder.identity
                    recorder.identity = dict(level='field',target=identifier)
                    try:
                        with recorder.span('field_target','target_overhead'):
                            yield identifier,pins
                    finally: recorder.identity = before
        def fields(pins): return TargetTuple(original_fields(pins))
        self.replace(module,'_field_targets',fields)
        original_invoke = module.SmtSolver._invoke
        @wraps(original_invoke)
        def invoke(solver,query,**kwargs):
            before = solver.cache_info();started = self.clock()
            try: return original_invoke(solver,query,**kwargs)
            finally:
                after = solver.cache_info()
                self.processes.append(dict(self.identity,kind='solver_invoke',
                    parent=self.stack[-1]['name'] if self.stack else None,
                    seconds=self.clock()-started, cache_hit=after['hits']>before['hits'],
                    query_bytes=len(query.encode()),query_sha256=hashlib.sha256(query.encode()).hexdigest()))
        self.replace(module.SmtSolver,'_invoke',invoke)
        original_run = subprocess.run
        @wraps(original_run)
        def run(*args,**kwargs):
            command=args[0] if args else kwargs.get('args',[])
            is_z3=isinstance(command,(list,tuple)) and command and Path(str(command[0])).name=='z3'
            started=self.clock()
            try: return original_run(*args,**kwargs)
            finally:
                if is_z3:
                    self.processes.append(dict(self.identity,kind='z3_process',
                        parent=self.stack[-1]['name'] if self.stack else None,
                        seconds=self.clock()-started))
        self.replace(subprocess,'run',run)

    def restore(self):
        for owner,name,original in reversed(self.undo): setattr(owner,name,original)
        self.undo.clear()


def summarize(events):
    categories=defaultdict(lambda:dict(calls=0,inclusive_seconds=0.0,exclusive_seconds=0.0))
    for event in events:
        row=categories[event['category']];row['calls']+=1
        row['inclusive_seconds']+=event['inclusive_seconds']
        row['exclusive_seconds']+=event['exclusive_seconds']
    return dict(categories)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work',type=Path)
    parser.add_argument('--seed',default='x-d')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--z3',type=Path)
    args=parser.parse_args()
    work,output=args.work.resolve(),args.output.resolve()
    if output.exists(): parser.error('Choose a new output directory')
    output.mkdir(parents=True)
    module=import_module('3_branch_simplifier')
    spec=module.SymbolicSubspecifier(work,z3_path=args.z3,timeout_seconds=args.timeout)
    consistency=spec._load_and_validate_consistency_report()
    wanted='seed_'+args.seed.removeprefix('seed_')
    matches=[b for b in consistency['branches'] if Path(b['seed_file']).stem==wanted]
    if len(matches)!=1: parser.error('Seed must select exactly one existing branch')
    selected=matches[0]
    reference=json.loads((work/'3_branch_subspecs/branch_subspecs.json').read_text())
    original=next(b for b in reference['branches'] if b['candidate_id']==selected['candidate_id'])
    recorder=Recorder();recorder.install(module)
    try:
        with recorder.span('branch','branch_overhead'):
            computation=spec._project_branch(consistency,selected)
    finally: recorder.restore()
    current=computation.branch.to_dict()
    if computation.errors: raise RuntimeError(str(computation.errors))
    branch_seconds=next(e['inclusive_seconds'] for e in recorder.events if e['name']=='branch')
    (output/'branch_result.json').write_text(json.dumps(current,indent=2)+'\n')
    # Independent comparison of the saved and profiled outputs, outside timed computation.
    validation_started=time.perf_counter()
    document=SmtDocument.parse((work/'2_consistency_check'/selected['seed_file']).read_text())
    verifier=SmtSolver(z3_path=args.z3,timeout_seconds=args.timeout)
    checks=[]
    for level,key,name in [('field','fields','config'),('line','lines','line_group')]:
        old={r[name]:r for r in original[key]};new={r[name]:r for r in current[key]}
        if set(old)!=set(new): raise ValueError('Profiling changed target coverage')
        for target,record in old.items():
            tree=parse_smt2_sexpr(tokenize_smt2_sexpr(subspec_string_to_smt2_and(record['constraint']) or 'true'))
            equal,seconds=verifier.equivalent(document,tree,new[target]['constraint'])
            checks.append(dict(level=level,target=target,equivalent=equal,seconds=seconds,
                               text_identical=record['constraint']==new[target]['constraint']))
    categories=summarize(recorder.events)
    per_target=[]
    for level,target in sorted({(e['level'],e['target']) for e in recorder.events if 'target' in e}):
        records=[e for e in recorder.events if e.get('level')==level and e.get('target')==target]
        roots=[e for e in records if e['name'] in ['target','field_target']]
        # Field fallback can nest a target call inside field_target.
        root=next((e for e in roots if e['name']=='field_target'),roots[-1] if roots else None)
        per_target.append(dict(level=level,target=target,wall_seconds=root['inclusive_seconds'] if root else None,
                               categories=summarize(records)))
    purposes=defaultdict(lambda:dict(calls=0,seconds=0.0,proved=0))
    for e in recorder.events:
        if e['name']=='equivalent':
            row=purposes[e['parent']];row['calls']+=1;row['seconds']+=e['inclusive_seconds'];row['proved']+=bool(e['equivalent'])
    report=dict(status='PASS' if all(c['equivalent'] for c in checks) else 'FAIL',seed=wanted,
                mode='isolated single branch; fresh solver cache; original solving algorithm',
                branch_wall_seconds=branch_seconds,categories=categories,targets=per_target,
                equivalence_by_caller=dict(purposes),cache=spec.solver.cache_info(),
                solver_invocations=len([p for p in recorder.processes if p['kind']=='solver_invoke']),
                actual_z3_processes=len([p for p in recorder.processes if p['kind']=='z3_process']),
                output_equivalence_checks=checks,output_verification_seconds=time.perf_counter()-validation_started,
                events=recorder.events,queries=recorder.processes,
                source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'3_branch_simplifier.py',ROOT/'utils/util_symbolic.py',work/'2_consistency_check'/selected['seed_file']]})
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['SYMBOLIC SEED SOLVER PROFILE',f'Seed: {wanted}',f"Mode: {report['mode']}",
           f'Branch wall seconds: {branch_seconds:.9f}',
           'This is a fresh isolated rerun, not the earlier 4-worker observation.',
           'Exclusive category times partition branch wall. Inclusive times overlap and must not be added.',
           'Output equivalence validation is outside timed solving.', '', 'CATEGORY TOTALS']
    for name,row in sorted(categories.items(),key=lambda item:-item[1]['exclusive_seconds']):
        lines.append(f"{name}: calls={row['calls']}; exclusive={row['exclusive_seconds']:.9f}; inclusive={row['inclusive_seconds']:.9f}")
    lines += ['', 'EQUIVALENCE CHECK PURPOSES (INCLUSIVE)',json.dumps(dict(purposes),indent=2),
              f"Solver invoke calls: {report['solver_invocations']}; actual Z3 subprocesses: {report['actual_z3_processes']}",
              'Cache: '+json.dumps(report['cache']), '', 'PER TARGET']
    for target in per_target:
        lines.append(f"{target['level'].upper()} {target['target']} | wall={target['wall_seconds']:.9f}")
        for name,row in sorted(target['categories'].items(),key=lambda item:-item[1]['exclusive_seconds']):
            lines.append(f"  {name}: calls={row['calls']}; exclusive={row['exclusive_seconds']:.9f}; inclusive={row['inclusive_seconds']:.9f}")
    lines += ['',f"Output equivalence: {sum(c['equivalent'] for c in checks)}/{len(checks)} PASS",
              f"Output verification wall seconds (excluded): {report['output_verification_seconds']:.9f}"]
    (output/'report.txt').write_text('\n'.join(lines)+'\n')
    rows=[]
    for target in per_target:
        row={k:v for k,v in target.items() if k!='categories'}
        for name,c in target['categories'].items():row[name+'_seconds']=c['exclusive_seconds'];row[name+'_calls']=c['calls']
        rows.append(row)
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (output/'target_times.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    for filename, entries in [('events.csv',recorder.events),('queries.csv',recorder.processes)]:
        columns=list(dict.fromkeys(key for entry in entries for key in entry))
        with (output/filename).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns)
            writer.writeheader();writer.writerows(entries)
    print(output/'report.txt')
    print(json.dumps({k:v['exclusive_seconds'] for k,v in categories.items()},indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
