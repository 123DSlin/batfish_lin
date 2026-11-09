#!/usr/bin/env python3
"""Run tools/run.py with --profile, or serve an isolated instrumented worker.

Times are elapsed wall-clock seconds, NOT CPU seconds. Nested task records
must not be summed as exclusive costs. Production solving semantics are intact.
"""
import argparse
import csv
from functools import wraps
from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys
from threading import Lock, local
import time

ROOT = Path(__file__).resolve().parents[1]


def worker(stage, output, arguments):
    sys.path.insert(0, str(ROOT))
    if stage == 6:
        sys.path.insert(0, str(ROOT.parent / 'auto-netsubspec-Traverse'))
    names = {1:'1_smt_slicer',2:'2_consistency_checker',3:'3_branch_simplifier',4:'4_branch_intersection',5:'5_traffic_subspecification',6:'compare_traverse_results'}
    wall_started = time.time()
    started = time.perf_counter()
    module = import_module(names[stage])
    events, instances = [], []
    lock, context = Lock(), local()
    def record(item):
        with lock:
            events.append(item)
    def wrap(owner, name, kind, identity=lambda a,k:{}):
        original = getattr(owner, name)
        @wraps(original)
        def measured(*a, **k):
            previous = getattr(context, 'identity', {})
            parent_kind = getattr(context, 'kind', None)
            meta = {**previous, **identity(a,k)}
            context.identity = meta
            context.kind = kind
            begin = time.perf_counter()
            status = 'OK'
            try:
                value = original(*a, **k)
                if kind == 'consistency_F_query' and isinstance(value, tuple):
                    status = value[0]
                if isinstance(value,dict) and 'status' in value:
                    status = value['status']
                if hasattr(value, 'status'):
                    status = value.status
                if hasattr(value, 'errors') and value.errors:
                    status = 'FAIL'
                return value
            except BaseException:
                status = 'ERROR'
                raise
            finally:
                end = time.perf_counter()
                record(dict(meta, kind=kind, parent_kind=parent_kind, start_seconds=begin-started,
                            end_seconds=end-started, elapsed_seconds=end-begin, status=status))
                context.identity = previous
                context.kind = parent_kind
        setattr(owner,name,measured)
    if stage == 1:
        cls = module.SmtSlicer
        init = cls.__init__
        def collect(self,*a,**k):
            init(self,*a,**k);instances.append(self)
        cls.__init__ = collect
        for method in ['load_normalized_encoding','build_device_semantic_scopes','build_symbolic_device_requirements']:
            wrap(module, method, 'shared_'+method)
        for method in ['_build_assertion_index','_classify_assertions','_seed_device_semantic_roots','_resolve_dependencies','_write_output_files','write_audit_union']:
            wrap(cls, method, 'engine_phase_'+method)
    if stage == 2:
        cls = module.ConsistencyChecker
        wrap(cls,'_check_scope','consistency_scope',lambda a,k:dict(device=k['router'],destination=k['destination']))
        wrap(cls,'_check_branch','consistency_seed',lambda a,k:dict(device=a[1].current_entry.router,seed=a[6],candidate_id=a[1].current_entry.candidate_id))
        wrap(cls,'_run_z3','consistency_F_query')
    if stage == 3:
        cls = module.SymbolicSubspecifier
        wrap(cls,'_project_branch','symbolic_seed',lambda a,k:dict(device=a[2]['router'],seed=Path(a[2]['seed_file']).stem,candidate_id=a[2]['candidate_id'],destination=a[2]['destination']))
        wrap(cls,'_project','direct_projection',lambda a,k:dict(level=k['level'],target=k['identifier']))
    if stage == 6:
        wrap(module,'compare_target','traverse_equivalence_target',lambda a,k:dict(level=a[0][0],target=a[0][1],device=a[0][1].split('_')[1]))
        wrap(module,'render_report','traverse_comparison_report')
    sys.argv = [module.__file__, *arguments]
    call_start = time.perf_counter()
    code, error = 0, None
    try:
        result = module.main()
        code = result if isinstance(result,int) else 0
    except SystemExit as e:
        code = e.code if isinstance(e.code,int) else 1
    except BaseException as e:
        code, error = 2, repr(e)
        raise
    finally:
        end = time.perf_counter()
        details = {'stage':stage,'returncode':code,'error':error,
                   'worker_wall_seconds':end-started,'main_wall_seconds':end-call_start,
                   'import_setup_seconds':call_start-started,'events':events}
        if stage == 1:
            details['devices'] = [dict(device=r,exclusive_attributed_seconds=seconds,
                attribution='dependency-pass work plus assemble/audit/write; shared preparation excluded')
                for instance in instances for r,seconds in instance.device_timing.items()]
        if stage == 3:
            work = Path(arguments[0]);report = work/'3_branch_subspecs/branch_subspecs.json'
            if report.exists() and report.stat().st_mtime >= wall_started:
                payload=json.loads(report.read_text())
                details['target_timings']=[dict(device=b['router'],seed=b['branch_name'],candidate_id=b['candidate_id'],level=level,target=t.get('config',t.get('line_group')),elapsed_seconds=t['solver_seconds'],derivation=t['derivation'])
                    for b in payload['branches'] for level,key in [('field','fields'),('line','lines')] for t in b[key]]
        if stage == 6:
            source = Path(arguments[arguments.index('--output')+1])
            if source.exists() and source.stat().st_mtime >= wall_started:
                payload = json.loads(source.read_text())
                details['comparison_timing'] = payload.get('timing', {})
                details['traverse_timing'] = payload.get('traverse_timing', {})
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(details,indent=2)+'\n')
    return code


def write_summary(directory, stages, total_wall):
    rows, csv_rows = [], []
    text = ['PIPELINE RUNTIME REPORT','All durations are elapsed wall-clock seconds, not CPU time.',
            'Stage wall includes worker startup/imports/report writing. Task sums may exceed wall under concurrency.',
            'Events are nested: do NOT add scope + seed + query durations together.',
            'Stage 1 is serial: shared SSA closure is preserved. Device attribution excludes shared preparation.',
            'Stage 6 reads saved Traverse results: equivalence checking and readable report generation only.',
            'Traverse generation/solving is a separate pipeline; stage 6 never enumerates or solves subspecs.', '']
    for stage in stages:
        item=dict(stage)
        path=directory/f"stage_{stage['stage']}.json"
        details=json.loads(path.read_text()) if path.exists() else {}
        item['details']=details; rows.append(item)
        text.append(f"STAGE {stage['stage']}: {stage['label']} | wall={stage['wall_seconds']:.6f}s | workers={stage['workers']} | exit={stage['returncode']}")
        if stage['stage'] == 1:
            item['shared_and_unattributed_wall_seconds'] = max(0.0, stage['wall_seconds'] - sum(d['exclusive_attributed_seconds'] for d in details.get('devices',[])))
            text.append(f"  Shared/unattributed wall (including startup): {item['shared_and_unattributed_wall_seconds']:.6f}s")
        for device in details.get('devices',[]):
            text.append(f"  DEVICE {device['device']}: attributed slicing={device['exclusive_attributed_seconds']:.6f}s (shared cost excluded)")
        primary_kind = {2:'consistency_scope',3:'symbolic_seed',6:'traverse_equivalence_target'}.get(stage['stage'])
        per_device = {}
        for event in details.get('events',[]):
            if event['kind']==primary_kind:
                per_device.setdefault(event['device'],[]).append(event)
        item['device_totals'] = []
        for device, tasks in sorted(per_device.items()):
            aggregate = dict(device=device, task_count=len(tasks),
                task_elapsed_sum_seconds=sum(t['elapsed_seconds'] for t in tasks),
                observed_span_seconds=max(t['end_seconds'] for t in tasks)-min(t['start_seconds'] for t in tasks))
            item['device_totals'].append(aggregate)
            text.append(f"  DEVICE {device}: task sum={aggregate['task_elapsed_sum_seconds']:.6f}s, observed span={aggregate['observed_span_seconds']:.6f}s (span can include scheduling gaps)")
        for baseline in details.get('baseline_target_timings',[]):
            for f in baseline['per_F']:
                csv_rows.append(dict(stage=stage['stage'],kind='baseline_concrete_F',seed=baseline['seed'],candidate_id=baseline['candidate_id'],target=baseline['target'],level=baseline['level'],failed=';'.join(f['failed']),elapsed_seconds=f['projection_seconds']))
        if details.get('baseline_target_timings'):
            pure = sum(f['projection_seconds'] or 0 for t in details['baseline_target_timings'] for f in t['per_F'])
            text.append(f"  Pure concrete-F projection elapsed sum: {pure:.6f}s (not wall time)")
        for category in ['consistency_scope','symbolic_seed','traverse_equivalence_target','traverse_comparison_report']:
            found=[e for e in details.get('events',[]) if e['kind']==category]
            if found:
                text.append(f"  {category}: count={len(found)}, task elapsed sum={sum(e['elapsed_seconds'] for e in found):.6f}s")
        comparison=[e for e in details.get('events',[]) if e['kind']=='baseline_equivalence_query' and e.get('parent_kind')=='validation_seed']
        if comparison:
            text.append(f"  baseline-versus-symbolic comparison only: count={len(comparison)}, task elapsed sum={sum(e['elapsed_seconds'] for e in comparison):.6f}s")
        for event in details.get('events',[]):
            csv_rows.append(dict(stage=stage['stage'],**event))
            if event['kind'] in {'consistency_scope','consistency_seed','symbolic_seed','enumerated_seed','validation_seed'}:
                text.append(f"    {event['kind']} device={event.get('device','')} seed={event.get('seed','')} destination={event.get('destination','')} time={event['elapsed_seconds']:.6f}s status={event['status']}")
        for target in details.get('target_timings',[]):
            csv_rows.append(dict(stage=stage['stage'],kind='symbolic_target',**target))
            text.append(f"      {target['device']}/{target['seed']} [{target['level']}] {target['target']}: {target['elapsed_seconds']:.6f}s ({target['derivation']})")
        text.append('')
    official = sum(s['wall_seconds'] for s in stages if s['stage'] != 6)
    optional = sum(s['wall_seconds'] for s in stages if s['stage'] == 6)
    text.append(f"OFFICIAL PIPELINE WALL (validation excluded): {official:.6f}s")
    text.append(f"OPTIONAL VALIDATION WALL (not pipeline time): {optional:.6f}s")
    text.append(f"TOTAL OBSERVED COMMAND WALL (includes validation and profiling overhead): {total_wall:.6f}s")
    baseline = next((s['details'].get('baseline_timing',{}) for s in rows if s['stage']==6),{})
    text.append(f"ENUMERATED REFERENCE PROGRAM SOLVE + INTERSECTION WALL ONLY: {baseline.get('baseline_solve_and_intersection_wall_seconds', 'not run')}")
    comparison = next((s['details'].get('comparison_timing',{}) for s in rows if s['stage']==6),{})
    traverse = next((s['details'].get('traverse_timing',{}) for s in rows if s['stage']==6),{})
    text.append(f"INDEPENDENT TRAVERSE SOLVE + INTERSECTION WALL (from saved run): {traverse.get('baseline_solve_and_intersection_wall_seconds', 'not supplied')}")
    text.append(f"VALIDATION EQUIVALENCE WALL (excluded): {comparison.get('validation_equivalence_wall_seconds', 'not run')}")
    text.append(f"REPORT FORMATTING WALL (excluded): {comparison.get('report_rendering_wall_seconds', 'not run')}")
    state = 'FAIL' if any(s['returncode'] for s in stages) else 'PASS' if stages and stages[-1]['stage'] in {4,5,6} else 'RUNNING'
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'runtime_report.json').write_text(json.dumps({'schema_version':2,'status':state,'pipeline_status':('FAIL' if any(s['returncode'] for s in stages if s['stage']!=6) else 'PASS' if any(s['stage']==4 for s in stages) else 'RUNNING'),'pipeline_wall_seconds':official,'optional_validation_wall_seconds':optional,'observed_command_wall_seconds':total_wall,'baseline_timing':baseline,'traverse_timing':traverse,'comparison_timing':comparison,'stages':rows},indent=2)+'\n')
    (directory/'runtime_report.txt').write_text('\n'.join(text)+'\n')
    columns=sorted({key for row in csv_rows for key in row})
    with (directory/'runtime_events.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(csv_rows)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--stage',type=int,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--arguments',required=True)
        a=p.parse_args();raise SystemExit(worker(a.stage,a.output,json.loads(a.arguments)))
    raise SystemExit(subprocess.call([sys.executable,str(ROOT/'tools/run.py'),*sys.argv[1:],'--profile']))
