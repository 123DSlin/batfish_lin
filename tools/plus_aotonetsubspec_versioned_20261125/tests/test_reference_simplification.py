"""Reference seed solving preserves the released target and symbolic scope."""
from importlib import import_module
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from utils.util_symbolic import SmtDocument,SmtSolver,SubspecificationError
from utils.util_smt import subspec_string_to_smt2_and
stage3=import_module('3_branch_simplifier')
RUN_ROOT = os.environ.get('NETSUBSPEC_RUN_0083')
WORK = Path(RUN_ROOT) / 'symbolic' if RUN_ROOT else ROOT.parents[1] / 'smts/smt_output_0083'


class ReferenceSolverTest(unittest.TestCase):
    def test_target_is_preserved_while_internal_equalities_are_eliminated(self):
        doc=SmtDocument.parse('(declare-fun Config_x_value () Int)\n(declare-fun state () Int)\n(assert (= Config_x_value 200))\n')
        solver=SmtSolver(timeout_seconds=3)
        expression=['and',['=','state',['+','Config_x_value','1']],['=','state','101']]
        candidate=solver.reference_simplify(doc,doc.config_pins,expression)
        self.assertIsNotNone(candidate)
        self.assertIn('Config_x_value',candidate)
        self.assertNotIn('__netsubspec_reference_',candidate)
        equal,_=solver.equivalent(doc,['=','Config_x_value','100'],candidate)
        self.assertTrue(equal)

    def test_ordinary_reference_chain_does_not_use_qe(self):
        doc=SmtDocument.parse('(declare-fun Config_x_value () Int)\n(assert (= Config_x_value 200))\n')
        solver=SmtSolver(timeout_seconds=3)
        captured=[];original=solver._run_goal
        def run(query,operation):
            captured.append(query);return original(query,operation)
        with patch.object(solver,'_run_goal',side_effect=run):
            solver.reference_simplify(doc,doc.config_pins,['>=','Config_x_value','100'])
        self.assertIn('(then simplify propagate-values solve-eqs ctx-solver-simplify)',captured[0])
        self.assertNotIn('qe-light',captured[0])
        self.assertNotIn('(forall',captured[0])
        self.assertNotIn('(exists',captured[0])


@unittest.skipUnless((WORK/'2_consistency_check/consistency_report.json').exists(),'Requires validated 0083 inputs')
class Reference0083Test(unittest.TestCase):
    def setUp(self):
        self.spec=stage3.SymbolicSubspecifier(WORK)
        report=self.spec._load_and_validate_consistency_report()
        branch=next(b for b in report['branches'] if Path(b['seed_file']).stem=='seed_x-d')
        self.doc=stage3._SmtDocument.parse((WORK/'2_consistency_check'/branch['seed_file']).read_text())
        self.pins=next(pins for name,pins in stage3._group_config_pins(self.doc.config_pins) if name=='Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1')
        self.problem=self.doc.quantified_projection(self.pins,'5.5.5.5')

    def test_LP_binding_is_released_without_freezing_to_original_200(self):
        config=next(pin.name for pin in self.doc.config_pins if pin.name.endswith('set_localpreference_200'))
        pins=next(pins for _,pins in stage3._group_config_pins(self.doc.config_pins) if any(pin.name==config for pin in pins))
        problem=self.doc.quantified_projection(pins,'5.5.5.5')
        expression = self.doc.reference_seed_expression(problem, '5.5.5.5')
        constraint = self.spec.solver.solve_reference_seed(self.doc, pins, expression)
        self.assertTrue(problem.released_route_attribute_bindings)
        self.assertTrue(self.spec.solver.equivalent(self.doc, problem.expression, constraint)[0])
        formula = subspec_string_to_smt2_and(constraint)
        self.assertTrue(self.spec.solver.satisfiable(self.doc, f'(and {formula} (= {config} 150))'))
        self.assertFalse(self.spec.solver.satisfiable(self.doc, f'(and {formula} (= {config} 50))'))

    def test_seed_solver_applies_all_symbolic_fault_cases(self):
        config = next(pin for pin in self.doc.config_pins if pin.name.endswith('set_localpreference_200'))
        link = '|LINK-UP-d_x|'
        expression = ['forall', [[link, 'Bool']], ['>=', config.name, ['ite', link, '100', '50']]]
        with patch.object(self.spec.solver, 'equivalent', side_effect=AssertionError('no internal proof')):
            result = self.spec.solver.solve_reference_seed(self.doc, (config,), expression)
        self.assertTrue(self.spec.solver.equivalent(self.doc, ['>=', config.name, '100'], result)[0])

    def test_internal_route_symbols_fail_closed(self):
        name = next(n for n in self.doc.declarations if 'OVERALL_BEST' in n and n.endswith('_localPref|'))
        with patch.object(self.spec.solver, 'solve_reference_seed', return_value=f'(>= {name} 0)'):
            with self.assertRaisesRegex(SubspecificationError, 'retained internal symbols'):
                self.spec._project(self.doc, self.pins, device='x', destination='5.5.5.5',
                                   identifier='test', level='line', is_pair=False)
