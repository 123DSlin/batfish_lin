from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_seed_contracts import queries, parse_sections, run
import tempfile
import contextlib
import io
from validate_slices import solve


class SeedContractTest(unittest.TestCase):
    def test_default_checks_every_constructed_seed_without_guard_skips(self):
        directory = Path(__file__).resolve().parents[1] / 'generated' / 'smt_output_0001'
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            report = run(directory, Path(temporary), 2)
            self.assertEqual(report['mode'], 'constructed_seed')
            self.assertEqual(len(report['checks']), 10)
            self.assertTrue(report['admissibility_pass'])
            self.assertTrue(report['assume_guarantee_pass'])
            for record in report['checks']:
                self.assertNotIn('guard_feasible', record)
                self.assertEqual(record['constructed_seed'], 'sat')
                self.assertEqual(record['forward'], 'sat')
                self.assertEqual(record['reverse'], 'unsat')
                self.assertTrue((Path(temporary) / record['artifact_directory'] / 'reverse.smt2').exists())

    def test_reverse_does_not_assume_current_output(self):
        decl = ['(declare-fun output () Bool)']
        environment, forward, reverse = queries([], [], [], ['(assert output)'])
        self.assertEqual(environment, [])
        self.assertEqual(solve(decl, forward), 'sat')
        self.assertEqual(solve(decl, reverse), 'sat')

    def test_peer_assumption_implies_expected_output(self):
        decl = ['(declare-fun peer () Bool)', '(declare-fun output () Bool)']
        inputs, forward, reverse = queries(['(assert (= output peer))'], [],
                                          ['(assert peer)'], ['(assert output)'])
        self.assertEqual(solve(decl, inputs), 'sat')
        self.assertEqual(solve(decl, forward), 'sat')
        self.assertEqual(solve(decl, reverse), 'unsat')

    def test_empty_environment_is_not_a_valid_reverse_proof(self):
        inputs, forward, reverse = queries(['(assert false)'], [], [], ['(assert true)'])
        self.assertEqual(solve([], inputs), 'unsat')
        self.assertEqual(solve([], reverse), 'unsat')

    def test_unclassified_seed_constraints_fail_closed(self):
        with self.assertRaises(ValueError):
            parse_sections('; ---- Symbolic Route Consistency Seed ----\n; Seed1: unexpected\n(assert true)')

if __name__ == '__main__':
    unittest.main()
