import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('baseline', ROOT / 'validate_slices.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class BaselineTest(unittest.TestCase):
    def test_closure_follows_peer_feedback_and_retains_competing_candidate(self):
        assertions = ['(assert (= x a))', '(assert (= a b))',
                      '(assert (>= x c))', '(assert (= c 2))', '(assert (= z 7))']
        selected, symbols = baseline.closed_slice(assertions, {'x', 'a', 'b', 'c', 'z'}, {'x'})
        self.assertEqual(selected, assertions[:4])
        self.assertEqual(symbols, {'x', 'a', 'b', 'c'})

    def test_failed_empty_report_does_not_print_success(self):
        from consistency.report import ConsistencyReport, Scope
        report = ConsistencyReport(
            scope=Scope('global', ('a',), 'default', ('5.5.5.5',), 'MAIN', 2),
            status='FAIL', generated_at='', source_json='', hostnames_file='',
            destinations_file='', solver='', total_scope_branches=1,
            eligible_branches=1, checked_branches=0, sat_branches=0,
            unsat_branches=0, unknown_branches=0, error_branches=0)
        self.assertNotIn('All eligible branches are consistent', report.to_readable_text())

    def test_constant_contradiction_is_never_dropped(self):
        selected, _ = baseline.closed_slice(['(assert false)'], set(), set())
        self.assertEqual(selected, ['(assert false)'])

    def test_counterexample_detects_bad_behavior_that_sat_compatibility_misses(self):
        declarations = ['(declare-fun fault () Bool)', '(declare-fun route () Int)']
        network = ['(assert (= route (ite fault 2 1)))']
        expected = ['(assert (= route 1))']
        self.assertEqual(baseline.solve(declarations, network + expected), 'sat')
        self.assertEqual(baseline.solve(declarations, network + ['(assert (not (= route 1)))']), 'sat')
        self.assertEqual(baseline.solve(declarations, network + ['(assert (not (= route (ite fault 2 1))))']), 'unsat')

if __name__ == '__main__':
    unittest.main()
