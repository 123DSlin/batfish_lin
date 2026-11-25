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


class DiscardInterfacePreparationTest(unittest.TestCase):
    def prepare(self, root, *, inventoried=True, pinned=True):
        source, concrete = root / 'source', root / 'concrete'
        source.mkdir(); concrete.mkdir()
        (source / '0_hostnames.txt').write_text('c\ni\n')
        (source / '0_interfaces.txt').write_text('c,Ethernet0\ni,Ethernet0\n' +
                                               ('i,null_interface\n' if inventoried else ''))
        encoding = ('(declare-fun |0_FAILED-EDGE_c_i| () Int)\n'
                    '(declare-fun |0_FAILED-EDGE_i_null_interface| () Int)\n' +
                    ('(assert (= |0_FAILED-EDGE_i_null_interface| 0))\n' if pinned else '') +
                    '(check-sat)\n')
        (source / 'smt_encoding.smt2').write_text(encoding)
        (concrete / '0_dataplane.txt').write_text(
            'FAILED c:Ethernet0--i:Ethernet0\n\nNode VRF Network\n')
        (concrete / '0_ebgp_routes.txt').write_text('Node VRF Network\n')
        output = root / 'out'
        MODULE.prepare(source, concrete, output, ['c', 'i'])
        return (output / 'smt_encoding.smt2').read_text()

    def test_fixed_discard_is_preserved_and_only_real_link_is_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = self.prepare(Path(tmp))
            self.assertIn('(assert (= |0_FAILED-EDGE_c_i| 1))', text)
            self.assertEqual(text.count('(assert (= |0_FAILED-EDGE_i_null_interface| 0))'), 1)
            self.assertNotIn('(assert (= |0_FAILED-EDGE_i_null_interface| 1))', text)

    def test_uninventoried_or_unpinned_discard_variable_is_rejected(self):
        for kwargs in ({'inventoried': False}, {'pinned': False}):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(ValueError, 'Unrecognized physical failure variable'):
                    self.prepare(Path(tmp), **kwargs)


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
