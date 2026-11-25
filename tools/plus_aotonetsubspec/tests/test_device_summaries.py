"""Device relations preserve hidden constraints and cross-device correlation."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from device_summaries import build_summaries, partition
from property_model import PropertyModel
from region_smt import QueryRunner
from solver_session import SolverSession
from utils.util_symbolic import SmtDocument, and_expression

@unittest.skipUnless(shutil.which('z3'), 'Z3 required')
class DeviceSummaryTest(unittest.TestCase):
 def test_assertion_partition_is_complete_and_nonduplicating(self):
  doc=SmtDocument.parse('''(declare-fun |0_a_x| () Int)
   (declare-fun |0_b_y| () Int)
   (assert (>= |0_a_x| 0))
   (assert (= |0_b_y| (+ |0_a_x| 1)))
   (assert (< |0_b_y| 10))''')
  groups,variables,boundary=partition(doc,['a','b'],set())
  self.assertEqual(sum(len(rows) for rows in groups.values()),len(doc.assertions))
  self.assertIn('|0_a_x|',boundary)

 def test_joint_interface_relation_and_private_unsatisfiability_are_preserved(self):
  doc=SmtDocument.parse('''
   (declare-fun Config_a_cost () Int)
   (declare-fun |0_a_private| () Int)
   (declare-fun |0_a_export| () Int)
   (declare-fun |0_b_import| () Int)
   (declare-fun |0_b_private| () Int)
   (declare-fun |0__reachable_x| () Bool)
   (declare-fun |0_FAILED-EDGE_a_b| () Int)
   (assert (= Config_a_cost 1))
   (assert (= |0_a_private| (+ Config_a_cost 2)))
   (assert (= |0_a_export| |0_a_private|))
   (assert (= |0_b_import| |0_a_export|))
   (assert (= |0_b_private| |0_b_import|))
   (assert (>= |0_b_private| 0))
   (assert (= |0__reachable_x| (= |0_b_import| 3)))
  ''')
  model=PropertyModel(doc,'5.5.5.5/32','x','|0__reachable_x|',
                      {'a--b':'|0_FAILED-EDGE_a_b|'},{'a':{},'b':{}})
  session=SolverSession()
  try:
   with tempfile.TemporaryDirectory() as directory:
    relations,report=build_summaries(model,Path(shutil.which('z3')),10,Path(directory)/'summaries',session)
    self.assertGreater(report['eliminated_private_variables'],0)
    runner=QueryRunner(doc,Path(shutil.which('z3')),10,Path(directory)/'proof',session=session)
    body=and_expression(relations)
    runner.prove('correlation',['and',body,['=', 'Config_a_cost','1'],['not','|0__reachable_x|']])
    runner.prove('negative_not_invented',['and',body,['=', 'Config_a_cost','-3']])
  finally:
   session.close()

if __name__=='__main__': unittest.main()
