import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from observable import Observables, evaluate
spec = importlib.util.spec_from_file_location('observable_baseline', ROOT / 'validate_slices.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class ObservableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'generated' / 'smt_output_0001'
        declarations, _ = baseline.mod.load_normalized_encoding(cls.directory / 'smt_encoding.smt2')
        cls.declared = baseline.mod._declared_symbol_set(declarations)

    def test_direct_bgp_preference_and_fallback_without_binder(self):
        oracle = Observables(self.directory)
        _, normal = oracle.expected('x', set(), self.declared)
        self.assertEqual(normal['interfaces'], ['GigabitEthernet0/0'])
        _, fallback = oracle.expected('x', {'|0_FAILED-EDGE_d_x|'}, self.declared)
        self.assertEqual(fallback['interfaces'], ['GigabitEthernet0/1'])

    def test_no_route_explicitly_disables_all_forwarding(self):
        assertions, state = Observables(self.directory).expected('a', {'|0_FAILED-EDGE_a_x|', '|0_FAILED-EDGE_a_d|'}, self.declared)
        self.assertFalse(state['has_route'])
        self.assertEqual(state['interfaces'], [])
        self.assertTrue(all(a.endswith(' false))') for a in assertions))

    def test_local_delivery_has_route_without_outgoing_forwarding(self):
        _, state = Observables(self.directory).expected('d', set(), self.declared)
        self.assertTrue(state['has_route'])
        self.assertEqual(state['interfaces'], [])

    def test_unknown_guard_cannot_silently_pass(self):
        with self.assertRaises(ValueError):
            evaluate({'operator': 'UNSUPPORTED'}, {})
        with self.assertRaises(KeyError):
            evaluate({'operator': 'VARIABLE', 'variableId': 'missing'}, {})

    def test_bad_active_next_hop_is_rejected(self):
        oracle = Observables(self.directory)
        for candidate in oracle.data['candidates']:
            if candidate['router'] == 'x' and candidate['prefix'] == '5.5.5.5/32':
                for contribution in candidate['contributions']:
                    contribution['provenance']['previousRouter'] = 'not-a-peer'
        with self.assertRaises(KeyError):
            oracle.expected('x', set(), self.declared)

if __name__ == '__main__':
    unittest.main()
