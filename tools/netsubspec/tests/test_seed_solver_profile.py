"""Profiler accounting must not double-count nested solver operations."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('seed_profile',ROOT/'tools/profile_seed_solver.py')
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SeedProfileTest(unittest.TestCase):
    def test_exclusive_times_partition_parent_wall(self):
        ticks=iter([0.,1.,3.,5.])
        recorder=MODULE.Recorder(clock=lambda:next(ticks))
        with recorder.span('parent','simplification'):
            with recorder.span('child','implication'):
                pass
        categories=MODULE.summarize(recorder.events)
        self.assertEqual(categories['simplification']['inclusive_seconds'],5.)
        self.assertEqual(categories['simplification']['exclusive_seconds'],3.)
        self.assertEqual(categories['implication']['exclusive_seconds'],2.)
        self.assertEqual(sum(c['exclusive_seconds'] for c in categories.values()),5.)

    def test_wrapping_preserves_result_errors_and_restores_method(self):
        class Subject:
            def operation(self,value):
                if value<0: raise ValueError('negative')
                return value*2
        original=Subject.operation
        recorder=MODULE.Recorder()
        recorder.wrap(Subject,'operation','projection')
        try:
            self.assertEqual(Subject().operation(3),6)
            with self.assertRaisesRegex(ValueError,'negative'):
                Subject().operation(-1)
            self.assertEqual([e['status'] for e in recorder.events],['OK','ERROR'])
        finally: recorder.restore()
        self.assertIs(Subject.operation,original)
        self.assertEqual(recorder.stack,[])


if __name__=='__main__':unittest.main()
