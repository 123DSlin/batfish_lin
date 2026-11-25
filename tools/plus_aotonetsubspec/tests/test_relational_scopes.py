"""State pruning preserves the existence frontier of unrelated components."""
from pathlib import Path
import shutil
import tempfile
import unittest
from relational_scopes import build_scope
from property_model import PropertyModel
from region_smt import QueryRunner
from solver_session import SolverSession
from utils.util_symbolic import SmtDocument

Z3=shutil.which('z3')

@unittest.skipUnless(Z3,'Z3 required')
class RelationalScopeTest(unittest.TestCase):
 def test_shared_configuration_does_not_lose_a_remote_existence_constraint(self):
  doc=SmtDocument.parse('''
   (declare-fun Config_a_n () Int)
   (declare-fun |0_b_hidden| () Int)
   (declare-fun |0__reachable_x| () Bool)
   (assert (= Config_a_n 1))
   (assert (= |0__reachable_x| (> Config_a_n 0)))
   (assert (= |0_b_hidden| (+ Config_a_n (- 1))))
   (assert (>= |0_b_hidden| 0))''')
  model=PropertyModel(doc,'5.5.5.5/32','a','|0__reachable_x|',{}, {'a':{},'b':{}})
  session=SolverSession()
  try:
   with tempfile.TemporaryDirectory() as directory:
    relation,report=build_scope(model,{model.property_symbol},'safety',Path(Z3),10,Path(directory)/'scope',session)
    self.assertEqual(report['eliminated_state_variables'],1)
    runner=QueryRunner(doc,Path(Z3),10,Path(directory)/'check',session=session)
    runner.prove('remote_frontier',['and',relation,['=','Config_a_n','0']])
    self.assertEqual(runner.check('possible',['and',relation,['=','Config_a_n','1']]),'sat')
  finally:session.close()

 def test_unrelated_component_is_removed_but_its_input_constraint_survives(self):
  doc=SmtDocument.parse('''
   (declare-fun Config_a_n () Int)
   (declare-fun Config_b_n () Int)
   (declare-fun |0_a_selected| () Bool)
   (declare-fun |0_b_hidden| () Int)
   (declare-fun |0__reachable_x| () Bool)
   (declare-fun |0_FAILED-EDGE_a_b| () Int)
   (assert (= Config_a_n 1)) (assert (= Config_b_n 1))
   (assert (= |0_a_selected| (> Config_a_n 0)))
   (assert (= |0__reachable_x| |0_a_selected|))
   (assert (= |0_b_hidden| (+ Config_b_n 0)))
   (assert (>= |0_b_hidden| 0))
  ''')
  model=PropertyModel(doc,'5.5.5.5/32','a','|0__reachable_x|',
                     {'a--b':'|0_FAILED-EDGE_a_b|'},{'a':{},'b':{}})
  session=SolverSession()
  try:
   with tempfile.TemporaryDirectory() as directory:
    relation,report=build_scope(model,{model.property_symbol},'safety',Path(Z3),10,Path(directory)/'scope',session)
    self.assertEqual(report['eliminated_state_variables'],1)
    runner=QueryRunner(doc,Path(Z3),10,Path(directory)/'checks',session=session)
    runner.prove('frontier',['and',relation,['<','Config_b_n','0']])
    runner.prove('property',['and',relation,['>','Config_a_n','0'],['not',model.property_symbol]])
    self.assertEqual(runner.check('valid',['and',relation,['=','Config_b_n','0'],['>','Config_a_n','0']]),'sat')
  finally:session.close()

if __name__=='__main__':unittest.main()
