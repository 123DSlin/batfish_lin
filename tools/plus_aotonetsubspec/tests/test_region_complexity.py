"""Multi-region and downstream-competition contracts beyond the Demo1 region."""
from dataclasses import replace
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from property_model import PropertyModel
from property_regions import RegionSolver
from property_subspec import _parse_pins, _solve_assignments_oracle, solve
from region_smt import QueryRunner, RegionFailure, Status, ast
from utils.util_smt import serialize_smt2_sexpr as smt
from utils.util_symbolic import SmtDocument

Z3 = shutil.which('z3')
ENABLE = 'Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_enable'
COST = ENABLE.removesuffix('enable')+'cost'
F1, F2 = '|0_FAILED-EDGE_t_x|', '|0_FAILED-EDGE_x_y|'
P = '|0__reachable_y|'


def multi_region_model():
    document = SmtDocument.parse(f'''
        (declare-fun {ENABLE} () Bool)
        (declare-fun {COST} () Int)
        (declare-fun {F1} () Int)
        (declare-fun {F2} () Int)
        (declare-fun |0_dst-ip| () (_ BitVec 32))
        (declare-fun |0_t_BGP_IMPORT_c_permitted| () Bool)
        (declare-fun {P} () Bool)
        (assert (= {ENABLE} true))
        (assert (= {COST} 1))
        (assert |0_t_BGP_IMPORT_c_permitted|)
        (assert (=> (= {F2} 1) (not (= {COST} 7))))
        (assert (= {P} (not (or
            (and (= {F1} 1) (<= 2 {COST}) (<= {COST} 3))
            (and (= {F2} 1) (<= 5 {COST}) (<= {COST} 6))))))
    ''')
    return PropertyModel(document, '5.5.5.5/32', 'y', P,
                         {'t--x': F1, 'x--y': F2}, {'t': {}, 'x': {}, 'y': {}})


@unittest.skipUnless(Z3, 'Z3 required')
class ComplexRegionTest(unittest.TestCase):
    def test_two_faults_require_two_distinct_bad_regions(self):
        model = multi_region_model()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = solve(model, [ENABLE, COST], (0, 7), 1, output, Z3, 10, 100)
            self.assertEqual(len(report['bad_regions']), 2)
            faults = [tuple(sorted(row['failures'].items())) for row in report['bad_regions']]
            self.assertEqual(len(set(faults)), 2)
            checker = QueryRunner(model.document, Path(Z3), 10, output/'verification')
            checker.prove('nonmonotone_allowed', ['xor', ast(report['allowed_constraint']),
                ast(f'(or (= {COST} 0) (= {COST} 1) (= {COST} 4))')])
            checker.prove('support_hole', ['xor', ast(report['support_constraint']),
                ast(f'(and (<= 0 {COST}) (< {COST} 7))')])
            direct = RegionSolver(model, _parse_pins(model, [ENABLE, COST], (0, 7)), 1,
                QueryRunner(model.document, Path(Z3), 10, output/'direct'), bad_strategy='direct').solve()
            oracle_dir=output/'oracle';oracle_dir.mkdir()
            oracle = _solve_assignments_oracle(model, _parse_pins(model, [ENABLE, COST], (0, 7)), 1,
                oracle_dir, Z3, 10, 100, classify_support=True)
            for other in (direct, oracle):
                for key in ('bad_constraint','support_constraint','allowed_constraint'):
                    checker.prove('compare_'+key, ['xor', ast(report[key]), ast(other[key])])

    def test_region_limit_never_publishes_a_partial_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            with self.assertRaises(RegionFailure) as caught:
                solve(multi_region_model(), [ENABLE,COST], (0,7), 1, output, Z3, 10, 100, max_regions=1)
            self.assertEqual(caught.exception.status, Status.INCOMPLETE)
            self.assertFalse((output/'allowed.smt2').exists())

    def test_unchanged_upstream_next_hop_does_not_freeze_downstream_competition(self):
        # X keeps T as next hop. T's changed attribute propagates through X;
        # Y must still compare that input to B's unchanged preference of 150.
        base=multi_region_model()
        document=SmtDocument.parse(f'''
            (declare-fun {ENABLE} () Bool)
            (declare-fun {COST} () Int)
            (declare-fun {F1} () Int)
            (declare-fun {F2} () Int)
            (declare-fun |0_dst-ip| () (_ BitVec 32))
            (declare-fun |0_t_BGP_IMPORT_c_permitted| () Bool)
            (declare-fun |0_x_next_t| () Bool)
            (declare-fun |0_t_attribute| () Int)
            (declare-fun |0_x_export_attribute| () Int)
            (declare-fun |0_y_competitor_b| () Int)
            (declare-fun |0_y_choose_x| () Bool)
            (declare-fun {P} () Bool)
            (assert (= {ENABLE} true))
            (assert (= {COST} 1))
            (assert |0_t_BGP_IMPORT_c_permitted|)
            (assert |0_x_next_t|)
            (assert (= |0_t_attribute| (ite {ENABLE} (+ 200 {COST}) 80)))
            (assert (= |0_x_export_attribute| |0_t_attribute|))
            (assert (= |0_y_competitor_b| 150))
            (assert (= |0_y_choose_x| (> |0_x_export_attribute| |0_y_competitor_b|)))
            (assert (= {P} |0_y_choose_x|))
        ''')
        model=replace(base,document=document)
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            report=solve(model,[ENABLE,COST],(0,7),1,output,Z3,10,100)
            checker=QueryRunner(document,Path(Z3),10,output/'verification')
            checker.prove('changed_winner', ['xor',ast(report['allowed_constraint']),
                ast(f'(and {ENABLE} (<= 0 {COST}) (<= {COST} 7))')])
            # Demoting the invariant competitor changes the answer, even
            # though X still forwards to T in both models.
            changed=SmtDocument.parse(document.query(*(f'(assert {smt(expr)})'
                for expr in document.assertions if expr != ['=', '|0_y_competitor_b|', '150']),
                '(assert (= |0_y_competitor_b| 70))'))
            other=output/'demoted';other.mkdir()
            demoted=solve(replace(model,document=changed),[ENABLE,COST],(0,7),1,other,Z3,10,100)
            checker.prove('demoted_competitor', ['xor',ast(demoted['allowed_constraint']),
                ast(f'(and (<= 0 {COST}) (<= {COST} 7))')])
