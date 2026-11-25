"""Symbolic seed coverage matches the finite oracle, including missing states."""
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from consistency import ConsistencyChecker, GuardEncoder, SymbolicRib
from consistency.symbolic_coverage import check_seed

FIXTURE=Path(__file__).resolve().parent/'fixtures/symbolic_output_0010'
Z3=shutil.which('z3')

class GuardRestrictionTest(unittest.TestCase):
 def test_feasibility_matches_exhaustive_oracle(self):
  rib=SymbolicRib.from_work_directory(FIXTURE)
  encoder=GuardEncoder(rib.guard_variables)
  for router in rib.topology.routers():
   for entry in rib.entries(router=router,prefix='10.0.0.0/24',plane='MAIN'):
    for k in range(len(encoder.variables)+1):
     expected=bool(encoder.satisfying_failure_assignments(entry.selection_guard,k))
     with patch.object(encoder,'evaluate',side_effect=AssertionError('enumeration')):
      self.assertEqual(encoder.is_feasible_within_k(entry.selection_guard,k),expected)

 def test_wide_guard_without_failure_set_expansion(self):
  base=SymbolicRib.from_work_directory(FIXTURE).guard_variables[0]
  variables=[replace(base,variable_id=f'g{i}',polarity='UP') for i in range(1500)]
  encoder=GuardEncoder(variables)
  guard=dict(operator='AND',children=[dict(operator='VARIABLE',variableId=v.variable_id) for v in variables])
  with patch.object(encoder,'evaluate',side_effect=AssertionError('enumeration')):
   self.assertTrue(encoder.is_feasible_within_k(guard,2))

@unittest.skipUnless(Z3,'Z3 required')
class SymbolicConsistencyTest(unittest.TestCase):
 def test_pipeline_does_not_call_concrete_fault_enumerator(self):
  checker=ConsistencyChecker(FIXTURE,z3_path=Z3)
  with tempfile.TemporaryDirectory() as directory, patch.object(
    GuardEncoder,'satisfying_failure_assignments',side_effect=AssertionError('enumerated faults')), patch(
    'consistency.guard_encoder.combinations',side_effect=AssertionError('expanded fault sets')):
   report=checker.run(k=1,output_directory=directory,max_workers=2)
   self.assertEqual(report.status,'PASS')
   self.assertEqual(report.fault_assignments_enumerated,0)
   self.assertEqual(report.checked_branches,7)

 def test_one_satisfying_fault_does_not_hide_an_inconsistent_fault(self):
  encoder=GuardEncoder(SymbolicRib.from_work_directory(FIXTURE).guard_variables)
  first=encoder.variables[0]
  symbol=encoder.symbol(first.variable_id)
  up=symbol if first.polarity=='UP' else f'(not {symbol})'
  seed='\n'.join([*encoder.declarations(),f'(assert {up})'])
  with tempfile.TemporaryDirectory() as directory:
   proof=check_seed(seed,encoder,dict(operator='TRUE'),1,Z3,10,Path(directory))
   self.assertEqual(proof['status'],'UNSAT')
   self.assertEqual(proof['failed_variables'],[first.variable_id])
   self.assertEqual(proof['fault_assignments_enumerated'],0)

 def test_unknown_projection_cannot_pass_coverage(self):
  from region_smt import QueryRunner, RegionFailure, Status
  encoder=GuardEncoder(SymbolicRib.from_work_directory(FIXTURE).guard_variables)
  seed='\n'.join(encoder.declarations())
  with tempfile.TemporaryDirectory() as directory, patch.object(QueryRunner,'project',
    side_effect=RegionFailure(Status.INCOMPLETE,'unproven projection')):
   proof=check_seed(seed,encoder,dict(operator='TRUE'),1,Z3,10,Path(directory))
   self.assertEqual(proof['status'],'UNKNOWN')

if __name__=='__main__': unittest.main()
