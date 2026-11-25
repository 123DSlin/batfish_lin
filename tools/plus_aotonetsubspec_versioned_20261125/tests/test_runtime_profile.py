"""Timing aggregation must not confuse parallel task sums with wall time."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runtime_profiler', ROOT/'tools/profile_runtime.py')
profiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiler)


class RuntimeProfileTest(unittest.TestCase):
    def test_validation_is_excluded_from_pipeline_and_baseline_cost(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            timing = dict(baseline_solve_and_intersection_wall_seconds=4,
                          validation_equivalence_wall_seconds=2,
                          report_rendering_wall_seconds=3)
            (directory/'stage_6.json').write_text(json.dumps({'baseline_timing':timing}))
            stages=[dict(stage=3,label='symbolic',wall_seconds=5,workers=2,returncode=0),
                    dict(stage=6,label='validation',wall_seconds=10,workers=2,returncode=0),
                    dict(stage=4,label='final intersection',wall_seconds=1,workers=1,returncode=0)]
            profiler.write_summary(directory,stages,16.5)
            r=json.loads((directory/'runtime_report.json').read_text())
            self.assertEqual(r['pipeline_wall_seconds'],6)
            self.assertEqual(r['optional_validation_wall_seconds'],10)
            self.assertEqual(r['baseline_timing']['baseline_solve_and_intersection_wall_seconds'],4)

    def test_parallel_task_sum_is_kept_separate_from_wall(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            events = [dict(kind='symbolic_seed',device='x',seed=s,start_seconds=0,
                           end_seconds=2,elapsed_seconds=2,status='OK') for s in ['x-a-d','x-d']]
            (directory/'stage_3.json').write_text(json.dumps({'events':events}))
            profiler.write_summary(directory,[dict(stage=3,label='symbolic',wall_seconds=2.5,workers=2,returncode=0)],2.6)
            report=json.loads((directory/'runtime_report.json').read_text())
            stage=report['stages'][0]
            self.assertEqual(stage['wall_seconds'],2.5)
            self.assertEqual(stage['device_totals'][0]['task_elapsed_sum_seconds'],4)
            self.assertEqual(stage['device_totals'][0]['observed_span_seconds'],2)
            self.assertTrue((directory/'runtime_events.csv').is_file())

    def test_missing_worker_details_are_not_fabricated_as_zero_cost(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            profiler.write_summary(directory,[dict(stage=2,label='consistency',wall_seconds=1,workers=1,returncode=2)],1)
            report=json.loads((directory/'runtime_report.json').read_text())
            self.assertEqual(report['stages'][0]['returncode'],2)
            self.assertEqual(report['stages'][0]['details'],{})
            self.assertEqual(report['stages'][0]['device_totals'],[])


if __name__=='__main__':unittest.main()
