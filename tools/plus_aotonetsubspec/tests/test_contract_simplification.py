"""Readable formulas must retain the complete set of allowed configurations."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contract_simplification import simplify_allowed
from region_smt import QueryRunner, ast
from utils.util_smt import serialize_smt2_sexpr as smt
from utils.util_symbolic import SmtDocument

Z3 = shutil.which('z3')
X, P, A = 'Config_x_length', 'Config_x_ip', 'Config_x_action'
DOCUMENT = f'''
(declare-fun {X} () Int)
(declare-fun {P} () (_ BitVec 32))
(declare-fun {A} () Bool)
(assert (= {X} 200))
(assert (= {P} #x01010101))
(assert (= {A} false))
'''


@unittest.skipUnless(Z3, 'Z3 required')
class CertifiedSimplificationTest(unittest.TestCase):
    def run_case(self, formula, names, expected, composition=None, invalid_normalizer=False):
        with tempfile.TemporaryDirectory() as directory:
            runner = QueryRunner(SmtDocument.parse(DOCUMENT), Path(Z3), 10, Path(directory))
            if invalid_normalizer:
                with patch('contract_simplification.normalizer2', return_value='true'):
                    result, evidence = simplify_allowed(runner, ast(formula), names,
                                                         composition=ast(composition) if composition else None)
            else:
                result, evidence = simplify_allowed(runner, ast(formula), names,
                                                     composition=ast(composition) if composition else None)
            runner.prove('independent_expected', ['xor', result, ast(expected)])
            return smt(result), evidence

    def test_fixed_free_parameter_is_retained_and_not_pinned_to_original(self):
        result, _ = self.run_case(f'(and (<= 0 {X}) (<= {X} 17) (not (<= {X} 16)))',
                                  {X}, f'(= {X} 17)')
        self.assertIn(X, result)
        self.assertNotEqual(result, 'true')
        self.assertNotIn('200', result)

    def test_one_model_does_not_replace_an_interval_with_one_value(self):
        self.run_case(f'(and (<= 1 {X}) (<= {X} 100))', {X}, f'(and (<= 1 {X}) (<= {X} 100))')

    def test_two_community_values_are_not_collapsed_to_one_model(self):
        self.run_case(f'(or (= {P} #x00000001) (= {P} #x00000002))', {P},
                      f'(or (= {P} #x00000001) (= {P} #x00000002))')

    def test_bad_legacy_normalization_candidate_is_rejected(self):
        _, evidence = self.run_case(f'(<= 1 {X})', {X}, f'(<= 1 {X})', invalid_normalizer=True)
        self.assertTrue(any(row.get('equivalence') == 'sat' and not row['accepted']
                            for row in evidence['attempts']))

    def test_true_property_does_not_erase_the_legal_domain(self):
        formula = f'(and (<= 0 {X}) (<= {X} 32))'
        result, _ = self.run_case(formula, {X}, formula, composition=f'(and {formula} true true)')
        self.assertNotEqual(result, 'true')

    def test_cidr_exact_host_collapses_to_address_length_and_action(self):
        mask = f'(bvshl #xffffffff ((_ int2bv 32) (- 32 {X})))'
        legal = f'(and (<= 0 {X}) (<= {X} 32) (= (bvand {P} {mask}) {P}))'
        bad = f'(and {legal} (or (<= {X} 31) (not (= (bvand {P} {mask}) (bvand #x05050505 {mask}))) (not {A})))'
        formula = f'(and {legal} (not {bad}))'
        expected = f'(and (= {P} #x05050505) (= {X} 32) {A})'
        result, evidence = self.run_case(formula, {P, X, A}, expected)
        self.assertNotIn('bvshl', result)
        self.assertNotIn('bvand', result)
        self.assertLess(evidence['simplified_bytes'], evidence['original_bytes'])

    def test_empty_allowed_set_stays_false(self):
        self.run_case(f'(and (= {X} 1) (= {X} 2))', {X}, 'false')


if __name__ == '__main__':
    unittest.main()
