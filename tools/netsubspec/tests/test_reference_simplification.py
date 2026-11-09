"""Reference-style candidates may replace QE only after exact validation."""
from importlib import import_module
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from utils.util_symbolic import SmtDocument,SmtSolver,SubspecificationError
from utils.util_smt import parse_smt2_sexpr,tokenize_smt2_sexpr,subspec_string_to_smt2_and
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
        audit={}
        candidate=self.spec._reference_simplification_candidate(self.doc,pins,problem,audit=audit)
        self.assertIsNotNone(candidate)
        self.assertEqual(audit['adapter'],'conditional-seed-values')
        self.assertTrue(self.spec._is_exact_projection(self.doc,problem,candidate))
        formula=subspec_string_to_smt2_and(candidate)
        self.assertTrue(self.spec.solver.satisfiable(self.doc,f'(and {formula} (= {config} 150))'))
        self.assertFalse(self.spec.solver.satisfiable(self.doc,f'(and {formula} (= {config} 50))'))
        self.assertGreater(audit['conditional_values']['guarded_equation_count'],0)

    def test_one_failure_case_candidate_cannot_replace_all_branch_cases(self):
        config=next(pin.name for pin in self.doc.config_pins if pin.name.endswith('set_localpreference_200'))
        link='|LINK-UP-d_x|'
        problem=SimpleNamespace(target_names=frozenset([config]),expression=[
            'forall',[[link,'Bool']],['>=',config,['ite',link,'100','50']]])
        self.assertFalse(self.spec._is_exact_projection(self.doc,problem,f'(>= {config} 50)'))
        self.assertTrue(self.spec._is_exact_projection(self.doc,problem,f'(>= {config} 100)'))

    def test_internal_route_symbols_are_not_dropped_to_accept_candidate(self):
        name=next(n for n in self.doc.declarations if 'OVERALL_BEST' in n and n.endswith('_localPref|'))
        with patch.object(self.spec.solver,'reference_simplify',return_value=f'(>= {name} 0)'):
            self.assertIsNone(self.spec._reference_simplification_candidate(self.doc,self.pins,self.problem))

    def check_fallback(self,candidate=None,error=None):
        expected=self.pins[0].name
        patcher=patch.object(self.spec,'_reference_simplification_candidate',side_effect=error) if error else patch.object(self.spec,'_reference_simplification_candidate',return_value=candidate)
        with patcher, patch.object(self.spec,'_staged_symbolic_projection',return_value=expected) as fallback, patch.object(self.spec,'_normalize_projected_constraint',side_effect=lambda doc,meta,value,*a,**k:value):
            constraint,method,_,audit=self.spec._project(self.doc,self.pins,device='x',destination='5.5.5.5',identifier='test',level='line',is_pair=False)
        fallback.assert_called_once()
        self.assertEqual(method,'symbolic-staged-projection')
        self.assertFalse(audit['reference_simplification']['accepted'])
        self.assertTrue(self.spec.solver.equivalent(self.doc,self.problem.expression,constraint)[0])
        return audit

    def test_wrong_candidate_is_rejected_and_original_projection_is_used(self):
        audit=self.check_fallback(candidate='true')
        self.assertEqual(audit['reference_simplification']['reason'],'equivalence-not-proved')

    def test_reference_failure_falls_back(self):
        audit=self.check_fallback(error=SubspecificationError('reference unavailable'))
        self.assertEqual(audit['reference_simplification']['reason'],'reference-error')
