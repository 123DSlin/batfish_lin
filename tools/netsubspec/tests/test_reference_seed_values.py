"""Expose guarded value equations without changing the source seed."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from utils.util_reference_seed import conditional_value_view
from utils.util_symbolic import SmtDocument,SmtSolver,collect_declared_symbols
from utils.util_smt import serialize_smt2_sexpr


class ReferenceSeedValuesTest(unittest.TestCase):
    def test_guarded_policy_values_keep_both_cases_and_target_free(self):
        symbol='|0_x_BGP_IMPORT_GigabitEthernet0/0_localPref|'
        doc=SmtDocument.parse(f'(declare-fun {symbol} () Int)\n(declare-fun Config_x_lp () Int)\n(declare-fun link () Bool)\n')
        original=['and',['=>','link',['=',symbol,'Config_x_lp']],
                  ['=>',['not','link'],['=',symbol,'0']],['>=',symbol,'50']]
        before=serialize_smt2_sexpr(original)
        adapted,audit=conditional_value_view(doc,original,())
        names=collect_declared_symbols(adapted,doc.declarations)
        self.assertEqual(names,{'Config_x_lp','link'})
        self.assertEqual(serialize_smt2_sexpr(original),before)
        self.assertEqual(audit['substituted_value_count'],1)
        expected=['exists',[[symbol,'Int']],original]
        equal,_=SmtSolver(timeout_seconds=3).equivalent(doc,expected,serialize_smt2_sexpr(adapted))
        self.assertTrue(equal)

    def test_cycles_leave_constraints_intact(self):
        a='|0_x_BGP_IMPORT_A_localPref|';b='|0_x_BGP_EXPORT_B_localPref|'
        doc=SmtDocument.parse(f'(declare-fun {a} () Int)\n(declare-fun {b} () Int)\n')
        original=['and',['=',a,b],['=',b,a]]
        adapted,audit=conditional_value_view(doc,original,())
        self.assertEqual(adapted,original)
        self.assertEqual(audit['substituted_value_count'],0)
        self.assertEqual(audit['skipped_dependency_count'],2)


if __name__=='__main__':unittest.main()
