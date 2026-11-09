"""0083 concrete reference completeness and independent input preparation."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('traverse_baseline', ROOT / 'tools/auto-netsubspec-Traverse/run_traverse_baseline.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SOURCE = ROOT / 'smts/smt_output_0083'
EXPORT = os.environ.get('NETSUBSPEC_CONCRETE_0083')


@unittest.skipUnless(EXPORT, 'Set NETSUBSPEC_CONCRETE_0083 to the 0083 concrete failure export directory')
class TraverseBaselineTest(unittest.TestCase):
    def test_exact_failure_universe_and_missing_case(self):
        cases = sorted(p for p in Path(EXPORT).iterdir() if p.is_dir())
        self.assertEqual(MODULE.validate_failure_universe(SOURCE, cases, 2), 7)
        self.assertEqual(len(cases), 29)
        with self.assertRaisesRegex(ValueError, 'Incomplete failure universe'):
            MODULE.validate_failure_universe(SOURCE, cases[:-1], 2)
        with self.assertRaisesRegex(ValueError, 'Incomplete failure universe'):
            MODULE.validate_failure_universe(SOURCE, cases + [cases[0]], 2)

    def test_concrete_attributes_and_complete_failure_pins(self):
        case = next(p for p in Path(EXPORT).iterdir() if p.is_dir() and p.name.startswith('fail2_'))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'case'
            failed = MODULE.prepare(SOURCE, case, out, ['a','b','d','x'])
            self.assertEqual(len(failed), 2)
            self.assertEqual((out / '0_ebgp_routes.txt').read_bytes(), (case / '0_ebgp_routes.txt').read_bytes())
            text = (out / 'smt_encoding.smt2').read_text()
            pins = text[text.rfind(';(get-model)'):] if ';(get-model)' in text else text
            self.assertEqual(pins.count('(assert (= |0_FAILED-EDGE_'), 7)
            self.assertEqual(pins.count('| 1))'), 2)
            self.assertFalse((out / 'symbolic_route.json').exists())
            self.assertFalse((out / '0_symbolic_routes.txt').exists())


if __name__ == '__main__':
    unittest.main()
