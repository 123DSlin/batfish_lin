"""Region contracts and saved Demo1 regressions, using the real Z3 executable."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from property_model import PropertyModel, load_property_model
from property_regions import RegionSolver, domain_contains, domain_expression
from property_subspec import _field_from_line, _parse_pins, solve
from region_smt import QueryRunner, RegionFailure, Status, ast, require_config_formula
from utils.util_smt import serialize_smt2_sexpr as smt
from utils.util_symbolic import SmtDocument, substitute_symbols

Z3 = shutil.which('z3')
ENABLE = 'Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_enable'
COST = ENABLE.removesuffix('enable') + 'cost'
FAILURE = '|0_FAILED-EDGE_t_x|'
CANDIDATE = '|0_t_BGP_IMPORT_port_permitted|'
PROPERTY = '|0__reachable_x|'


def toy_model(candidate='true', extra=''):
    document = SmtDocument.parse(f'''
        (declare-fun {ENABLE} () Bool)
        (declare-fun {COST} () Int)
        (declare-fun {FAILURE} () Int)
        (declare-fun |0_dst-ip| () (_ BitVec 32))
        (declare-fun {CANDIDATE} () Bool)
        (declare-fun {PROPERTY} () Bool)
        (assert (= {ENABLE} true))
        (assert (= {COST} 1))
        (assert (= {CANDIDATE} {candidate}))
        (assert (=> (and {ENABLE} (= {FAILURE} 1)) (<= {COST} 5)))
        (assert (= {PROPERTY} (or (= {FAILURE} 0) (and {ENABLE} (>= {COST} 1)))))
        {extra}
    ''')
    return PropertyModel(document, '5.5.5.5/32', 'x', PROPERTY, {'t--x': FAILURE}, {'t': {}, 'x': {}})


def recovery_model(*, missing_attribute=False, missing_source=False, changed_source=False,
                   missing_origin=False, partial_attribute=False):
    model = toy_model()
    origin = '|0_i_CONNECTED_IMPORT_Loopback0_'
    source = '|0_i_BGP_EXPORT_port_'
    metric = CANDIDATE.removesuffix('permitted|') + 'metric|'
    equations = [expr for expr in model.document.assertions if expr != ['=', CANDIDATE, 'true']]
    source_equation = '' if missing_source else f'''
        (assert (= {source}permitted| {origin}permitted|))
        (assert (= {source}metric| {'(+ 1 ' + COST + ')' if changed_source else '1'}))
    '''
    attribute = f'(= {metric} (+ {source}metric| {COST}))'
    if missing_attribute:
        attribute = 'true'
    elif partial_attribute:
        attribute = f'(ite (> {COST} 3) {attribute} true)'
    document = SmtDocument.parse(model.document.query(
        f'(declare-fun {origin}permitted| () Bool)', f'(declare-fun {origin}metric| () Int)',
        f'(declare-fun {source}permitted| () Bool)', f'(declare-fun {source}metric| () Int)',
        f'(declare-fun {metric} () Int)',
        *(f'(assert {smt(expr)})' for expr in equations),
        '' if missing_origin else f'''(assert (ite (= |0_dst-ip| #x05050505)
                    (and {origin}permitted| (= {origin}metric| 0)) (not {origin}permitted|)))''',
        source_equation,
        f'''(assert (ite {source}permitted|
                    (ite {ENABLE} (not {CANDIDATE})
                      (and (= {CANDIDATE} {source}permitted|)
                           {attribute}))
                    (not {CANDIDATE})))'''))
    return replace(model, document=document)


def export_recovery_model(*, missing_attribute=False):
    model = toy_model()
    origin = '|0_i_CONNECTED_IMPORT_Loopback0_'
    source = '|0_i_BGP_EXPORT_port_'
    metric = CANDIDATE.removesuffix('permitted|') + 'metric|'
    equations = [expr for expr in model.document.assertions if expr != ['=', CANDIDATE, 'true']]
    document = SmtDocument.parse(model.document.query(
        *(f'(declare-fun {prefix}{field}| () {sort})'
          for prefix in (origin, source) for field, sort in (('permitted', 'Bool'), ('metric', 'Int'))),
        f'(declare-fun {metric} () Int)',
        *(f'(assert {smt(expr)})' for expr in equations),
        f'''(assert (ite (= |0_dst-ip| #x05050505)
               (and {origin}permitted| (= {origin}metric| 0)) (not {origin}permitted|)))''',
        f'''(assert (ite {origin}permitted|
               (ite {ENABLE} (not {source}permitted|)
                 (and (= {source}permitted| {origin}permitted|)
                      {'true' if missing_attribute else f'(= {source}metric| (+ {origin}metric| {COST}))'}))
               (not {source}permitted|)))''',
        f'''(assert (ite {source}permitted|
               (and (= {CANDIDATE} {source}permitted|) (= {metric} {source}metric|))
               (not {CANDIDATE})))'''))
    return replace(model, document=document)


class HygieneTest(unittest.TestCase):
    def test_rejects_quantifiers_internal_symbols_and_fresh_helpers(self):
        for text in ['(exists ((state Int)) (= state 1))', '(= |internal| 1)', '(= k!0 1)']:
            with self.subTest(text=text), self.assertRaises(RegionFailure):
                require_config_formula(ast(text), {COST})
        require_config_formula(ast(f'(and (<= 0 {COST}) (<= {COST} 65534))'), {COST})

    def test_interval_representation_has_constant_size(self):
        targets = _parse_pins(toy_model(), [ENABLE, COST], (0, 65534))
        self.assertLess(len(smt(domain_expression(targets))), 400)
        metadata = dict(kind='integer-interval', minimum=0, maximum=65534)
        self.assertTrue(domain_contains(metadata, '65534'))
        self.assertFalse(domain_contains(metadata, '65535'))


@unittest.skipUnless(Z3, 'Z3 required')
class RegionTest(unittest.TestCase):
    def run_solver(self, directory, model=None, limit=100):
        return solve(model or toy_model(), [ENABLE, COST], (0, 7), 1, Path(directory), Z3, 10, limit)

    def checker(self, directory, model):
        return QueryRunner(model.document, Path(Z3), 10, Path(directory)/'verification')

    def test_pointwise_oracle_including_missing_support(self):
        model = toy_model()
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_solver(directory, model)
            self.assertEqual(report['status'], 'PASS')
            self.assertEqual(report['configuration_values_enumerated'], 0)
            checker = self.checker(directory, model)
            checker.prove('expected', ['xor', ast(report['allowed_constraint']),
                          ast(f'(and {ENABLE} (<= 1 {COST}) (<= {COST} 5))')])
            engine = RegionSolver(model, _parse_pins(model, [ENABLE, COST], (0, 7)), 1, checker)
            for enabled in ('false', 'true'):
                for cost in range(8):
                    bindings = {ENABLE: enabled, COST: str(cost)}
                    support, bad = True, False
                    for failure in engine.scenarios():
                        state = substitute_symbols(engine.state(failure), bindings)
                        support &= checker.check('oracle_support', state) == 'sat'
                        bad |= checker.check('oracle_bad', ['and', state, ['not', PROPERTY]]) == 'sat'
                    result = substitute_symbols(ast(report['allowed_constraint']), bindings)
                    self.assertEqual(checker.check('oracle_allowed', result) == 'sat', support and not bad)

    def test_scope_failure_precedes_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RegionFailure) as caught:
                self.run_solver(directory, toy_model(candidate=f'(not {ENABLE})'))
            self.assertEqual(caught.exception.status, Status.UNSUPPORTED)
            report = json.loads((Path(directory)/'region_report.json').read_text())
            self.assertFalse(any('project' in query['label'] for query in report['metrics']['queries']))
            self.assertFalse((Path(directory)/'allowed.smt2').exists())

    def test_complete_policy_recovery_reaches_property_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_solver(directory, recovery_model())
            self.assertEqual(report['status'], 'PASS')
            self.assertEqual(report['candidate_scope'], 'CERTIFIED_POLICY_RECOVERY')
            self.assertEqual(len(report['policy_recoveries']), 1)
            self.assertEqual(report['policy_recoveries'][0]['transfer_ambiguous'], 'UNSAT')
            self.checker(directory, recovery_model()).prove('expected', ['xor', ast(report['allowed_constraint']),
                ast(f'(and {ENABLE} (<= 1 {COST}) (<= {COST} 5))')])

    def test_incomplete_source_stays_unsupported(self):
        for option in ('missing_attribute', 'missing_source',
                       'missing_origin', 'partial_attribute'):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(RegionFailure) as caught:
                    self.run_solver(directory, recovery_model(**{option: True}))
                self.assertEqual(caught.exception.status, Status.UNSUPPORTED)
                self.assertFalse((Path(directory)/'allowed.smt2').exists())

    def test_encoded_changed_source_can_accompany_local_policy_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_solver(directory, recovery_model(changed_source=True))
            self.assertEqual(report['status'], 'PASS')
            self.assertEqual(report['candidate_scope'], 'CERTIFIED_POLICY_RECOVERY')

    def test_export_policy_recovery_and_missing_export_attribute(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_solver(directory, export_recovery_model())
            self.assertEqual(report['status'], 'PASS')
            self.assertEqual(report['policy_transfer_roots'][0]['direction'], 'EXPORT')
            self.assertEqual(report['policy_recoveries'][0]['kind'], 'export-policy-recovery')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RegionFailure):
                self.run_solver(directory, export_recovery_model(missing_attribute=True))
            self.assertFalse((Path(directory)/'allowed.smt2').exists())

    def test_line_target_need_not_occur_in_every_transfer(self):
        model = recovery_model()
        source_metric = '|0_i_BGP_EXPORT_port_metric|'

        def remove_cost(expr):
            if expr == ['+', source_metric, COST]:
                return source_metric
            return [remove_cost(item) for item in expr] if isinstance(expr, list) else expr

        document = SmtDocument.parse(model.document.query(
            *(f'(assert {smt(remove_cost(expr))})' for expr in model.document.assertions)))
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_solver(directory, replace(model, document=document))
            self.assertEqual(report['status'], 'PASS')
            root = report['policy_transfer_roots'][0]
            self.assertEqual(root['target_dependencies'], [ENABLE])
            self.assertEqual(root['other_line_targets'], [COST])

    def test_functional_helper_preserves_indirect_configuration_dependency(self):
        model = recovery_model()
        helper = '|policy_enabled|'
        expressions = [substitute_symbols(expr, {ENABLE: helper})
                       if isinstance(expr, list) and expr[0] == 'ite' and CANDIDATE in smt(expr)
                       else expr for expr in model.document.assertions]
        document = SmtDocument.parse(model.document.query(
            f'(declare-fun {helper} () Bool)', f'(assert (= {helper} (not (not {ENABLE}))))',
            *(f'(assert {smt(expr)})' for expr in expressions)))
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_solver(directory, replace(model, document=document))
            self.assertEqual(report['status'], 'PASS')
            self.assertIn(ENABLE, report['policy_transfer_roots'][0]['target_dependencies'])

    def test_counterfactual_uses_fixed_configuration_and_destination(self):
        model = recovery_model()
        fixed = 'Config_i_RoutingPolicy_ORIGINATE__Seq10__Line1__enable'
        expressions = [substitute_symbols(expr, {ENABLE:
                       ['and', ENABLE, fixed, ['=', '|0_dst-ip|', '#x05050505']]})
                       if isinstance(expr, list) and expr[0] == 'ite' and CANDIDATE in smt(expr)
                       else expr for expr in model.document.assertions]
        document = SmtDocument.parse(model.document.query(
            f'(declare-fun {fixed} () Bool)', f'(assert (= {fixed} true))',
            *(f'(assert {smt(expr)})' for expr in expressions)))
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_solver(directory, replace(model, document=document))
            self.assertEqual(report['status'], 'PASS')

    def test_downstream_activation_must_require_a_certified_policy_change(self):
        model = recovery_model()
        root = CANDIDATE.removesuffix('permitted|')
        source = '|0_t_BGP_EXPORT_other_'
        downstream = '|0_x_BGP_IMPORT_other_'
        document = SmtDocument.parse(model.document.query(
            *(f'(assert {smt(expr)})' for expr in model.document.assertions),
            '(declare-fun |uncontrolled_activation| () Bool)',
            *(f'(declare-fun {prefix}{field}| () {sort})'
              for prefix in (source, downstream) for field, sort in (('permitted', 'Bool'), ('metric', 'Int'))),
            f'(assert (= {source}permitted| (or {root}permitted| true)))',
            f'(assert (= {source}metric| (ite {root}permitted| {root}metric| 1)))',
            f'''(assert (ite {source}permitted|
                  (ite |uncontrolled_activation|
                    (and (= {downstream}permitted| {source}permitted|)
                         (= {downstream}metric| {source}metric|))
                    (not {downstream}permitted|)) (not {downstream}permitted|)))'''))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RegionFailure, 'without a certified policy change'):
                self.run_solver(directory, replace(model, document=document))
            self.assertFalse((Path(directory)/'allowed.smt2').exists())

    def test_reference_support_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RegionFailure, 'reference model has no legal state'):
                self.run_solver(directory, toy_model(extra=f'(assert (= {FAILURE} 0))'))

    def test_field_specialization_and_outside_original_domain(self):
        model = toy_model()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            report = self.run_solver(directory, model)
            pins = {pin.name: pin for pin in model.document.config_pins}
            output = directory/'field'; output.mkdir()
            field = _field_from_line(model, pins[COST], report, output, Z3, 10)
            self.assertEqual(field['fixed_same_line_fields'], {ENABLE: 'true'})
            self.checker(directory, model).prove('expected_field', ['xor', ast(field['allowed_constraint']),
                                                 ast(f'(and (<= 1 {COST}) (<= {COST} 5))')])
            outside = dict(report, target_domains={**report['target_domains'], COST:
                           dict(kind='integer-interval', minimum=2, maximum=7)})
            self.assertIsNone(_field_from_line(model, pins[ENABLE], outside, directory/'outside', Z3, 10))

    def test_one_good_state_cannot_hide_a_bad_state(self):
        model = toy_model()
        document = SmtDocument.parse(model.document.query(*(f'(assert {smt(expr)})'
            for expr in model.document.assertions if PROPERTY not in smt(expr))))
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_solver(directory, replace(model, document=document))
            self.assertEqual(report['allowed_constraint'], 'false')

    def test_unknown_is_incomplete_and_publishes_no_formula(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('region_smt.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'unknown\n', '')):
                with self.assertRaises(RegionFailure) as caught:
                    self.run_solver(directory)
            self.assertEqual(caught.exception.status, Status.INCOMPLETE)
            self.assertFalse((Path(directory)/'allowed.smt2').exists())

    def test_timeout_is_incomplete_and_keeps_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('region_smt.subprocess.run', side_effect=subprocess.TimeoutExpired('z3', 10)):
                with self.assertRaises(RegionFailure) as caught:
                    self.run_solver(directory)
            self.assertEqual(caught.exception.status, Status.INCOMPLETE)
            self.assertFalse((Path(directory)/'allowed.smt2').exists())
            self.assertTrue(list((Path(directory)/'region_evidence').glob('*.log')))

    def test_failed_projection_certificate_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.checker(directory, toy_model())
            with patch.object(runner, 'invoke', side_effect=[
                    '(goals (goal false :precision precise :depth 1))', 'sat']):
                with self.assertRaisesRegex(RegionFailure, 'equivalence'):
                    runner.project('incorrect_projection', ast(f'(>= {COST} 0)'), {COST})

    def test_fault_resource_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RegionFailure, 'fault projections'):
                self.run_solver(directory, limit=1)


FIXTURES = ROOT/'example_results'
@unittest.skipUnless(Z3 and (FIXTURES/'demo1_c_only/all_configs/input').is_dir(), 'saved Demo1 fixture required')
class DemoTest(unittest.TestCase):
    def test_c_only_and_q1_full_cost_domain(self):
        expected = {
            'demo1_c_only': f'(and {ENABLE} (<= 1 {COST}) (<= {COST} 65532))',
            'demo1_q1': f'(and (<= 0 {COST}) (<= {COST} 65534) (or (not {ENABLE}) (<= {COST} 65532)))',
        }
        for fixture, condition in expected.items():
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as directory:
                work = FIXTURES/fixture/'all_configs/input'
                model = load_property_model(work, 2)
                report = solve(model, [ENABLE, COST], (0, 65534), 2, Path(directory), Z3, 20, 100, native_work=work)
                self.assertEqual(report['legal_failures'], 29)
                self.assertEqual(report['configuration_values_enumerated'], 0)
                checker = QueryRunner(model.document, Path(Z3), 10, Path(directory)/'verification')
                checker.prove('expected_allowed', ['xor', ast(report['allowed_constraint']), ast(condition)])
                bad = (f'(and (<= 0 {COST}) (<= {COST} 65534) (or (not {ENABLE}) (= {COST} 0)))'
                       if fixture == 'demo1_c_only' else 'false')
                checker.prove('expected_bad', ['xor', ast(report['bad_constraint']), ast(bad)])

    def test_cli_defaults_to_regions_and_recovers_rejected_import(self):
        cases = [
            ('demo1_c_only/all_configs/input', [ENABLE, COST], 2, 'PASS'),
            ('demo1_community_policy/t4_candidate_recovery/input',
             ['Config_t_CommunityList_QUARANTINE__Line1__65050_99__community'], 1, 'PASS'),
        ]
        for fixture, fields, k, expected in cases:
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/'output'
                command = [sys.executable, '-B', str(ROOT/'tools/run.py'), str(FIXTURES/fixture),
                           '--property-preserving', '--k', str(k), '--output', str(output)]
                for field in fields:
                    command += ['--target', field]
                if COST in fields:
                    command += ['--cost-range', '0', '10']
                result = subprocess.run(command, text=True, capture_output=True, timeout=90)
                report = json.loads((output/'report.json').read_text())
                self.assertEqual(report['status'], expected, result.stderr)
                self.assertEqual(result.returncode, 0 if expected == 'PASS' else 1)
                self.assertEqual((output/'allowed.smt2').exists(), expected == 'PASS')
                if expected == 'PASS':
                    self.assertEqual(report['backend'], 'regions')
                    self.assertEqual(report['configuration_values_enumerated'], 0)

    def test_t4_recovery_is_checked_against_the_property(self):
        work = FIXTURES/'demo1_community_policy/t4_candidate_recovery/input'
        model = load_property_model(work, 1)
        field = 'Config_t_CommunityList_QUARANTINE__Line1__65050_99__community'
        with tempfile.TemporaryDirectory() as directory:
            report = solve(model, [field], None, 1, Path(directory), Z3, 20, 100, native_work=work)
            self.assertEqual(report['candidate_scope'], 'CERTIFIED_POLICY_RECOVERY')
            self.assertTrue(any(row['kind'] == 'downstream-propagation' for row in report['policy_recoveries']))
            checker = QueryRunner(model.document, Path(Z3), 10, Path(directory)/'verification')
            checker.prove('recovery_required', ['xor', ast(report['allowed_constraint']), ['=', field, '#x1']])
