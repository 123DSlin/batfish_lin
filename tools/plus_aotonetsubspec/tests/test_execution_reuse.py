"""Isolation, cache provenance and fail-closed incremental solver behavior."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from region_context import RegionContext
from region_smt import QueryRunner, RegionFailure, Status
from solver_session import SolverSession
from utils.util_symbolic import SmtDocument

Z3 = shutil.which('z3')

@unittest.skipUnless(Z3, 'Z3 required')
class ExecutionReuseTest(unittest.TestCase):
    def test_queries_are_isolated_and_declarations_can_grow(self):
        doc = SmtDocument.parse('(declare-fun x () Int)')
        session = SolverSession()
        try:
            with tempfile.TemporaryDirectory() as directory:
                runner = QueryRunner(doc, Path(Z3), 5, Path(directory), session=session)
                self.assertEqual(runner.check('first', ['=', 'x', '1']), 'sat')
                self.assertEqual(runner.check('second', ['=', 'x', '2']), 'sat')
                self.assertEqual(runner.check('contradiction', ['and', ['=', 'x', '1'], ['=', 'x', '2']]), 'unsat')
                runner.document = SmtDocument.parse(doc.query('(declare-fun y () Bool)'))
                self.assertEqual(runner.check('new_declaration', 'y'), 'sat')
                runner.document = doc
                self.assertEqual(runner.check('smaller_context', ['=', 'x', '3']), 'sat')
                self.assertEqual(session.starts, 1)
                for query in Path(directory).glob('*.smt2'):
                    result = subprocess.run([Z3, str(query)], capture_output=True, text=True, check=True)
                    self.assertEqual(result.stdout, query.with_suffix('.log').read_text())
        finally:
            session.close()

    def test_changed_sort_restarts_instead_of_reusing_a_declaration(self):
        session = SolverSession()
        try:
            session.execute(Z3, SmtDocument.parse('(declare-fun x () Int)'), ['(check-sat)'], 5)
            result = session.execute(Z3, SmtDocument.parse('(declare-fun x () Bool)'),
                                     ['(assert x)', '(check-sat)'], 5)
            self.assertEqual(result.strip(), 'sat')
            self.assertEqual(session.starts, 2)
        finally:
            session.close()

    def test_solver_error_discards_session_and_can_recover(self):
        session = SolverSession()
        try:
            with tempfile.TemporaryDirectory() as directory:
                runner = QueryRunner(SmtDocument.parse(''), Path(Z3), 5, Path(directory), session=session)
                with self.assertRaises(RegionFailure) as caught:
                    runner.invoke('invalid', '(assert missing)', '(check-sat)')
                self.assertEqual(caught.exception.status, Status.ERROR)
                self.assertIsNone(session.process)
                self.assertEqual(runner.check('recovery', 'true'), 'sat')
                self.assertEqual(session.starts, 2)
        finally:
            session.close()

    def test_reference_cache_is_query_content_addressed(self):
        context = RegionContext()
        try:
            with tempfile.TemporaryDirectory() as directory:
                runner = QueryRunner(SmtDocument.parse('(declare-fun f () Int)'), Path(Z3), 5,
                                     Path(directory), session=context.session)
                first = context.reference_check(runner, 'first', ['and', 'true', ['=', 'f', '0']])
                second = context.reference_check(runner, 'same', ['=', 'f', '0'])
                different = context.reference_check(runner, 'different', ['=', 'f', '1'])
                self.assertFalse(first['cache_hit'])
                self.assertTrue(second['cache_hit'])
                self.assertEqual(first['source_query'], second['source_query'])
                self.assertFalse(different['cache_hit'])
                self.assertEqual(len(runner.queries), 2)
        finally:
            context.close()

    def test_timeout_discards_process_and_next_query_restarts(self):
        session = SolverSession()
        try:
            with tempfile.TemporaryDirectory() as directory:
                runner = QueryRunner(SmtDocument.parse(''), Path(Z3), 5, Path(directory), session=session)
                with self.assertRaises(RegionFailure) as caught:
                    runner.invoke('bounded', '(check-sat)', timeout=1e-12)
                self.assertEqual(caught.exception.status, Status.INCOMPLETE)
                self.assertIsNone(session.process)
                self.assertEqual(runner.check('after_timeout', 'true'), 'sat')
        finally:
            session.close()

    def test_native_model_reuse_invalidates_on_input_edit(self):
        from unittest.mock import patch
        context = RegionContext()
        try:
            with tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                source = work / 'smt_encoding.smt2'
                source.write_text('first')
                model, first, second = object(), object(), object()
                with patch('property_regions.full_model', side_effect=[first, second]) as load:
                    self.assertIs(context.full_model(model, work), first)
                    self.assertIs(context.full_model(model, work), first)
                    source.write_text('changed')
                    self.assertIs(context.full_model(model, work), second)
                    self.assertEqual(load.call_count, 2)
        finally:
            context.close()


@unittest.skipUnless(Z3, 'Z3 required')
class SymbolicCoverageTest(unittest.TestCase):
    def test_symbolic_support_does_not_visit_fault_assignments(self):
        from unittest.mock import patch
        from test_property_regions import toy_model, ENABLE, COST
        from property_subspec import _parse_pins
        from property_regions import RegionSolver
        model = toy_model()
        with tempfile.TemporaryDirectory() as directory:
            runner = QueryRunner(model.document, Path(Z3), 10, Path(directory))
            engine = RegionSolver(model, _parse_pins(model, [ENABLE, COST], (0, 7)), 1, runner)
            with patch.object(engine, 'scenarios', side_effect=AssertionError('enumerated faults')):
                report = engine.solve()
            self.assertEqual(report['fault_assignments_enumerated'], 0)
            self.assertEqual(report['support_strategy'], 'symbolic')
            self.assertEqual(report['support_cases'][0]['strategy'], 'symbolic')

if __name__ == '__main__':
    unittest.main()
