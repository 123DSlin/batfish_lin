"""Protocol dispatch, shared-engine extension, and unsupported adapter isolation."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from slicing import (DeviceSemanticScope, ProtocolSliceAdapter, ProtocolSliceRules,
                     SymbolicSliceRequirements, SymbolicSliceError,
                     UnsupportedSliceProtocol, get_protocol_adapter)
spec = importlib.util.spec_from_file_location('protocol_test_slicer', ROOT / '1_smt_slicer.py')
slicer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slicer)


class ToyRules(ProtocolSliceRules):
    def should_remove(self, expression):
        return False
    def assertion_owners(self, expression):
        return {'r'} if '|0_r_result|' in expression else set()
    def dependency_keys(self, variables):
        return ('|0_r_spf|',) if '|0_r_spf|' in variables else ()


class ToyAdapter(ProtocolSliceAdapter):
    name = 'toy'
    def required_input_files(self):
        return ('smt_encoding.smt2',)
    def build_scopes(self, work_dir, declarations):
        return {'r': DeviceSemanticScope('r', (), set(), {'|0_r_spf|'},
                                         {'|0_r_result|'}, protocol='toy')}
    def build_requirements(self, work_dir, declarations, *, k, vrf):
        return SymbolicSliceRequirements({'r': {'|0_r_result|'}}, {'r': {'|0_r_result|'}})
    def create_rules(self, routers, model_igp):
        return ToyRules()


class ProtocolSlicingTest(unittest.TestCase):
    def test_default_registry_and_no_shared_state(self):
        a, b = get_protocol_adapter(), get_protocol_adapter('BGP')
        self.assertEqual(a.name, 'bgp')
        self.assertIsNot(a, b)
        self.assertIsNot(a.create_rules(['a'], False), b.create_rules(['a'], False))

    def test_unsupported_and_mixed_protocols_never_fall_back(self):
        for name in ('isis', 'IS-IS', 'IS_IS'):
            with self.subTest(name=name), self.assertRaises(UnsupportedSliceProtocol):
                get_protocol_adapter(name)
        for name in ('ospf', 'bgp,isis', 'unknown', ''):
            with self.subTest(name=name), self.assertRaises(SymbolicSliceError):
                get_protocol_adapter(name)

    def test_isis_cli_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary); output = work / '1_sliced_device_smt_encoding'
            output.mkdir(); sentinel = output / 'existing.smt2'; sentinel.write_text('original\n')
            for script in (ROOT / '1_smt_slicer.py', ROOT / 'tools' / 'run.py'):
                with self.subTest(script=script.name):
                    p = subprocess.run([sys.executable, str(script), str(work),
                                        '--k', '2', '--slicing-protocol', 'IS-IS'], text=True, capture_output=True)
                    self.assertEqual(p.returncode, 2)
                    self.assertIn('IS-IS slicing is not implemented', p.stderr)
                    self.assertEqual(list(output.iterdir()), [sentinel])
                    self.assertEqual(sentinel.read_text(), 'original\n')

    def test_shared_engine_accepts_non_bgp_adapter(self):
        declarations = ['(declare-fun |0_r_result| () Int)', '(declare-fun |0_r_spf| () Int)',
                        '(declare-fun Config_r_metric () Int)']
        assertions = ['(assert (= |0_r_result| |0_r_spf|))',
                      '(assert (= |0_r_spf| Config_r_metric))', '(assert (= Config_r_metric 7))']
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary); (work / 'smt_encoding.smt2').write_text('\n'.join(declarations + assertions))
            adapter = ToyAdapter(); slicer.InputValidator(str(work), adapter)._validate_input_files()
            scopes = adapter.build_scopes(work, declarations)
            requirements = adapter.build_requirements(work, declarations, k=0, vrf='default')
            engine = slicer.SmtSlicer(['r'], str(work / 'slices'), semantic_scopes=scopes,
                required_symbols=requirements.required_by_router,
                local_roots=requirements.local_roots_by_router, protocol_adapter=adapter)
            engine.slice_from_expressions(declarations + assertions)
            generated = (work / 'slices' / 'sliced_r_smt_encoding.smt2').read_text()
            self.assertTrue(all(a in generated for a in assertions))
            self.assertNotIn('BGP', generated)

    def test_scope_adapter_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(SymbolicSliceError, 'mismatch'):
            slicer.SmtSlicer(['r'], temporary, semantic_scopes=ToyAdapter().build_scopes(None, []))

    def test_bgp_owner_precedence_and_export_boundary(self):
        rules = get_protocol_adapter().create_rules(['a', 'x'], False)
        self.assertEqual(rules.assertion_owners(
            '(assert (=> |0_CONTROL-FORWARDING_a_G0| |0_x_BGP_IMPORT_G0_permitted|))'), {'x'})
        self.assertEqual(rules.assertion_owners(
            '(assert (= |0_x_BGP_EXPORT_G0_permitted| |0_x_OVERALL_BEST_None_permitted|))'), set())
        self.assertEqual(rules.dependency_keys(['|0_x_BGP_EXPORT_G0_metric|',
            '|0_x_BGP_EXPORT_G0_permitted|', 'Config_a_metric']), ('|0_x_BGP_EXPORT_G0_permitted|',))

    def test_auxiliary_igp_slice_rules_preserved(self):
        rules = get_protocol_adapter().create_rules(['a', 'x'], True)
        self.assertTrue(rules.should_remove('(assert |0_SLICE-MAIN__reachable_x|)'))
        self.assertFalse(rules.should_remove('(assert |0_SLICE-x__reachable_x|)'))
        self.assertEqual(rules.assertion_owners(
            '(assert (= |0_SLICE-MAIN_a_BGP_IMPORT_G0_permitted| |0_SLICE-x__reachable_x|))'), {'a'})
        self.assertEqual(rules.assertion_owners('(assert |0_SLICE-x__reachable_x|)'), {'a', 'x'})

    def test_device_names_and_shared_export(self):
        rules = get_protocol_adapter().create_rules(['r', 'r_1', 'r-1'], False)
        self.assertEqual(rules.assertion_owners('(assert |0_r_1_BGP_IMPORT_G0_permitted|)'), {'r_1'})
        self.assertEqual(rules.assertion_owners('(assert |0_r-1_BGP_IMPORT_G0_permitted|)'), {'r-1'})
        self.assertEqual(rules.dependency_keys(['|0_r_BGP_SINGLE-EXPORT_metric|']), ('|0_r_BGP_SINGLE-EXPORT_metric|',))

if __name__ == '__main__':
    unittest.main()
