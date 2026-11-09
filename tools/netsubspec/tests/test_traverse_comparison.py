"""The optional checker consumes saved outputs and must reject disagreements."""
import importlib.util
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('traverse_comparison',ROOT.parent/'auto-netsubspec-Traverse/compare_traverse_results.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TraverseComparisonTest(unittest.TestCase):
    def test_original_nested_AND_format_preserves_grouping(self):
        value = MODULE.conjunction(['((>= Config_x_a 0) AND (<= Config_x_a 2)) AND ((= Config_x_b true))'])
        self.assertEqual(value,'(and (and (>= Config_x_a 0) (<= Config_x_a 2)) (= Config_x_b true))')

    def test_no_projection_and_wrong_saved_result_is_rejected(self):
        doc = MODULE.SmtDocument.parse('(declare-fun Config_x_a () Int)\n')
        solver = MODULE.SmtSolver(timeout_seconds=2)
        with tempfile.TemporaryDirectory() as tmp, patch.object(solver,'project',side_effect=AssertionError('Projection is forbidden')):
            same = MODULE.compare_target(('field','Config_x_a','(= Config_x_a 1)','(= Config_x_a 1)'),doc,solver,Path(tmp))
            wrong = MODULE.compare_target(('field','Config_x_a','(= Config_x_a 2)','(= Config_x_a 1)'),doc,solver,Path(tmp))
        self.assertEqual(same['status'],'EQUIVALENT')
        self.assertEqual(wrong['status'],'NOT_EQUIVALENT')

    def test_missing_target_is_not_silently_true(self):
        result = MODULE.compare_target(('field','Config_x_a','true',None),None,None,None)
        self.assertEqual(result['status'],'MISSING_TARGET')

    def test_state_variables_are_not_silently_projected_away(self):
        doc = MODULE.SmtDocument.parse('(declare-fun Config_x_a () Int)\n(declare-fun route_state () Int)\n')
        solver = MODULE.SmtSolver(timeout_seconds=2)
        with tempfile.TemporaryDirectory() as tmp:
            result=MODULE.compare_target(('field','Config_x_a','true','(= route_state 1)'),doc,solver,Path(tmp))
        self.assertEqual(result['status'],'TRAVERSE_HAS_STATE_VARIABLES')
        self.assertTrue(result['traverse_state_variables'])

    def test_implicit_field_bounds_match_explicit_bounds(self):
        doc=MODULE.SmtDocument.parse('(declare-fun Config_x_a_length () Int)\n(declare-fun Config_x_a_prefix_range_start () Int)\n(declare-fun Config_x_a_prefix_range_end () Int)\n(assert (= Config_x_a_length 32))\n(assert (= Config_x_a_prefix_range_start 32))\n(assert (= Config_x_a_prefix_range_end 32))\n')
        solver=MODULE.SmtSolver(timeout_seconds=2)
        with tempfile.TemporaryDirectory() as tmp:
            result=MODULE.compare_target(('field','Config_x_a_length','(and (>= Config_x_a_length 0) (<= Config_x_a_length 32))','true',['Config_x_a_length']),doc,solver,Path(tmp))
        self.assertEqual(result['status'],'EQUIVALENT')

    def test_released_original_value_must_not_hide_disagreement(self):
        doc=MODULE.SmtDocument.parse('(declare-fun Config_x_a () Int)\n(assert (= Config_x_a 1))\n')
        solver=MODULE.SmtSolver(timeout_seconds=2)
        with tempfile.TemporaryDirectory() as tmp:
            result=MODULE.compare_target(('field','Config_x_a','(= Config_x_a 2)','(= Config_x_a 1)',['Config_x_a']),doc,solver,Path(tmp))
        self.assertEqual(result['status'],'NOT_EQUIVALENT')
        self.assertEqual(result['comparison_context'],'true')

    def test_input_hash_mismatch_stops_before_solver(self):
        run_root = os.environ.get('NETSUBSPEC_RUN_0083')
        if not run_root:
            self.skipTest('Set NETSUBSPEC_RUN_0083 to the parent of the symbolic and traverse runs')
        fixture = Path(run_root)
        metadata=json.loads((fixture/'traverse/report.json').read_text())
        metadata['source_sha256']['smt_encoding.smt2']='changed'
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);reference=tmp/'traverse';reference.mkdir()
            (reference/'report.json').write_text(json.dumps(metadata))
            output=tmp/'verification/report.json'
            argv=['compare',str(fixture/'symbolic'),'--traverse-results',str(reference),'--output',str(output)]
            with patch.object(sys,'argv',argv), patch.object(MODULE,'SmtSolver',side_effect=AssertionError('No solver should run')):
                self.assertEqual(MODULE.main(),1)
            report=json.loads(output.read_text())
            self.assertEqual(report['status'],'ERROR')
            self.assertIn('input mismatch',report['errors'][0])
            self.assertEqual(report['checks'],[])


if __name__=='__main__': unittest.main()
