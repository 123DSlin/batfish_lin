"""Validation adapters must reject missing coverage and ambiguous forwarding."""
from dataclasses import replace
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from concrete_validation import (
    ConcreteScenario, Route, ValidationError, delivery, prepare_prepend_snapshot,
    read_concrete_scenarios, run_batfish,
)

from property_model import PropertyModel
from property_regions import RegionSolver
from property_subspec import _parse_pins, solve
from region_smt import QueryRunner
from utils.util_symbolic import SmtDocument
sys.path.insert(0,str(ROOT/'tools'))
from validate_regions import audit_variant


def rib_line(node, prefix='5.5.5.5/32', protocol='bgp', interface='dynamic', peer='t'):
    return f'{node} default {prefix} {protocol} 10.0.0.1 {interface} {peer} 0 20 -\n'


def write_example_export(root, *, duplicate=False):
    for name, failure in [('fail0',''),('fail1','FAILED x:port--t:port\n')]:
        case=root/name;case.mkdir()
        text=failure+rib_line('t',protocol='connected',interface='Loopback0',peer='null')
        if not failure:text+=rib_line('x')
        (case/'0_dataplane.txt').write_text(text)
    if duplicate:
        case=root/'duplicate';case.mkdir()
        (case/'0_dataplane.txt').write_text(rib_line('t',protocol='connected',interface='Loopback0',peer='null'))


class ConcreteParsingTest(unittest.TestCase):
    def test_delivery_and_complete_failure_universe(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write_example_export(root)
            cases=read_concrete_scenarios(root,{'x','t'},{'t--x'},'5.5.5.5/32',1)
            self.assertEqual(delivery(cases[frozenset()], 'x', {'t'})['path'], ['x','t'])
            self.assertTrue(delivery(cases[frozenset()], 'x', {'t'})['delivered'])
            self.assertFalse(delivery(cases[frozenset({'t--x'})], 'x', {'t'})['delivered'])
            self.assertFalse(delivery(cases[frozenset()], 'x', {'other'})['delivered'])

    def test_missing_and_duplicated_scenarios_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write_example_export(root,duplicate=True)
            with self.assertRaisesRegex(ValidationError,'duplicate'):
                read_concrete_scenarios(root,{'x','t'},{'t--x'},'5.5.5.5/32',1)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValidationError,'incomplete'):
                read_concrete_scenarios(Path(directory),{'x','t'},{'t--x'},'5.5.5.5/32',1)

    def test_longest_prefix_and_duplicate_winners(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write_example_export(root)
            p=root/'fail0/0_dataplane.txt'
            p.write_text(p.read_text()+rib_line('x',prefix='0.0.0.0/0',peer='x'))
            cases=read_concrete_scenarios(root,{'x','t'},{'t--x'},'5.5.5.5/32',1)
            self.assertEqual(cases[frozenset()].routes['x'].peer,'t')
            p.write_text(p.read_text()+rib_line('x'))
            with self.assertRaisesRegex(ValidationError,'ECMP'):
                read_concrete_scenarios(root,{'x','t'},{'t--x'},'5.5.5.5/32',1)

    def test_loops_and_discard_are_not_delivery(self):
        scenario=ConcreteScenario(frozenset(),{
            'x':Route('t','bgp','dynamic','5.5.5.5/32'),
            't':Route('x','bgp','dynamic','5.5.5.5/32')},Path('unused'))
        self.assertEqual(delivery(scenario,'x',{'t'})['end'],'loop')
        discard=ConcreteScenario(frozenset(),{'x':Route(None,'static','null_interface','5.5.5.5/32')},Path('unused'))
        self.assertEqual(delivery(discard,'x',{'x'})['end'],'discard')


class SnapshotMutationTest(unittest.TestCase):
    def test_only_selected_stanza_changes_and_zero_omits_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configs=root/'configs';configs.mkdir()
            original=('hostname T\nroute-map KEEP permit 10\n set as-path prepend 65105\n!\n'
                      'route-map FROM_ISP permit 20\n match community LOW\n set as-path prepend 65105\n!\n')
            (configs/'T.cfg').write_text(original)
            prepare_prepend_snapshot(configs,root/'two','t','FROM_ISP',20,65105,2)
            changed=(root/'two/configs/T.cfg').read_text()
            self.assertIn('route-map KEEP permit 10\n set as-path prepend 65105\n',changed)
            self.assertIn(' set as-path prepend 65105 65105\n',changed)
            prepare_prepend_snapshot(configs,root/'zero','t','FROM_ISP',20,65105,0)
            self.assertEqual((root/'zero/configs/T.cfg').read_text().count('set as-path prepend'),1)
            self.assertEqual((configs/'T.cfg').read_text(),original)

    def test_wrong_reference_asn_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configs=root/'configs';configs.mkdir()
            (configs/'T.cfg').write_text('hostname T\nroute-map FROM_ISP permit 20\n set as-path prepend 99\n!\n')
            with self.assertRaisesRegex(ValidationError,'reference prepend'):
                prepare_prepend_snapshot(configs,root/'bad','t','FROM_ISP',20,65105,1)
            self.assertFalse((root/'bad').exists())


class MalformedRibTest(unittest.TestCase):
    def test_truncated_route_is_not_interpreted_as_no_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case=root/'fail0';case.mkdir()
            (case/'0_dataplane.txt').write_text('x default 5.5.5.5/32 bgp truncated\n')
            with self.assertRaisesRegex(ValidationError,'malformed RIB'):
                read_concrete_scenarios(root,{'x'},set(),'5.5.5.5/32',0)

    def test_null0_route_is_a_discard(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case=root/'fail0';case.mkdir()
            (case/'0_dataplane.txt').write_text(rib_line('x',protocol='static',interface='Null0',peer='null'))
            scenarios=read_concrete_scenarios(root,{'x'},set(),'5.5.5.5/32',0)
            self.assertEqual(delivery(scenarios[frozenset()],'x',{'x'})['end'],'discard')


class LauncherRuntimeTest(unittest.TestCase):
    def test_explicit_java_and_final_nodes_are_passed_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configs = root/'snapshot/configs'
            configs.mkdir(parents=True)
            (configs/'X.cfg').write_text('hostname X\n')
            launcher = root/'launcher'
            launcher.write_text('''#!/usr/bin/env python3
import json, os
from pathlib import Path
root = Path(os.environ['SMT_DIRECTORY_PREFIX'])
(root/'smt_output_0001/failure_enumeration/failures_AT_MOST_K_k0').mkdir(parents=True)
(root/'environment.json').write_text(json.dumps({key: os.environ[key] for key in ['JAVABIN','SMT_FINAL','JAVA_TOOL_OPTIONS']}))
''')
            launcher.chmod(0o755)
            result = run_batfish(root/'snapshot', root/'output', launcher, ingress='x',
                destination='5.5.5.5/32', k=0, timeout=10, final_nodes='c',
                java_binary=Path(sys.executable))
            environment = json.loads((root/'output/environment.json').read_text())
            execution = json.loads((root/'output/execution.json').read_text())
            self.assertEqual(environment['SMT_FINAL'], 'c')
            self.assertEqual(environment['JAVABIN'], str(Path(sys.executable).resolve()))
            self.assertEqual(execution['java_binary'], environment['JAVABIN'])
            self.assertIn('--add-opens=java.base/java.lang=ALL-UNNAMED', environment['JAVA_TOOL_OPTIONS'])
            self.assertTrue(result.is_dir())


Z3=shutil.which('z3')
E='Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_enable'
C=E.removesuffix('enable')+'cost'
F='|0_FAILED-EDGE_t_x|'
D='|0_DATA-FORWARDING_x_port|'
P='|0__reachable_x|'


@unittest.skipUnless(Z3,'Z3 required')
class ValidatorChecksTest(unittest.TestCase):
    def exercise(self, directory, corrupt=None):
        root=Path(directory);ribs=root/'ribs';ribs.mkdir()
        write_example_export(ribs)
        scenarios=read_concrete_scenarios(ribs,{'x','t'},{'t--x'},'5.5.5.5/32',1)
        document=SmtDocument.parse(f'''
            (declare-fun {E} () Bool)
            (declare-fun {C} () Int)
            (declare-fun {F} () Int)
            (declare-fun {D} () Bool)
            (declare-fun {P} () Bool)
            (declare-fun |0_dst-ip| () (_ BitVec 32))
            (declare-fun |0_t_BGP_IMPORT_x_permitted| () Bool)
            (assert (= {E} true))
            (assert (= {C} 1))
            (assert |0_t_BGP_IMPORT_x_permitted|)
            (assert (= {D} (= {F} 0)))
            (assert (= {P} {D}))
        ''')
        model=PropertyModel(document,'5.5.5.5/32','x',P,{'t--x':F},{'x':{'t':D},'t':{}})
        output=root/'solver';output.mkdir()
        report=solve(model,[E,C],(0,2),1,output,Z3,10,100)
        if corrupt=='forwarding':
            baseline=scenarios[frozenset()]
            scenarios[frozenset()]=replace(baseline,routes={})
        if corrupt=='support':
            report['support_cases'][0]['constraint']='false'
        runner=QueryRunner(document,Path(Z3),10,root/'validation')
        engine=RegionSolver(model,_parse_pins(model,[E,C],(0,2)),1,runner)
        return audit_variant(model,report,engine,runner,{E:'true',C:'1'},scenarios,{'t'})

    def test_matching_concrete_states_pass_even_when_global_property_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result=self.exercise(directory)
            self.assertEqual(result['status'],'VERIFIED_SUPPORTED')
            self.assertFalse(result['allowed'])
            self.assertFalse(result['actual_property_all_faults'])
            self.assertEqual(result['scenarios'][0]['selected_peers']['x'], 't')

    def test_forwarding_disagreement_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValidationError,'forwarding or property mismatch'):
                self.exercise(directory,'forwarding')

    def test_wrong_support_projection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValidationError,'Support projection disagrees'):
                self.exercise(directory,'support')
