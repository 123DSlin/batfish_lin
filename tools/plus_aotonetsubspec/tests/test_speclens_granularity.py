"""Source-granularity regressions, with independent SMT equivalence checks."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from configuration_domains import prefix_domains
from property_regions import domain_expression, domain_metadata
from region_smt import QueryRunner, ast
from speclens_granularity import SourceCommand, build_plan, command_plans, derive_contract
from utils.util_symbolic import SmtDocument, SubspecificationError
from utils.util_smt import serialize_smt2_sexpr as smt

Z3 = shutil.which('z3')
LINE = 'Config_x_RouteFilterList_TARGET__Line1'
BASE = LINE + '__5_5_5_5__'


def fixture(directory, prefix='5.5.5.5/32', modifiers='', lower=32, upper=32):
    import ipaddress
    network = ipaddress.IPv4Network(prefix)
    path = Path(directory) / 'X.cfg'
    command = f'ip prefix-list TARGET seq 5 permit {prefix}' + (' ' + modifiers if modifiers else '')
    path.write_text('hostname X\n' + command + '\n')
    types = dict(action='Bool', enable='Bool', ip='(_ BitVec 32)', mask='(_ BitVec 32)',
                 length='Int', prefix_range_start='Int', prefix_range_end='Int')
    values = dict(action='true', enable='true', ip=f'#x{int(network.network_address):08x}',
                  mask=f'#x{int(network.netmask):08x}', length=str(network.prefixlen),
                  prefix_range_start=str(lower), prefix_range_end=str(upper))
    document = SmtDocument.parse('\n'.join([
        *(f'(declare-fun {BASE}{key} () {sort})' for key, sort in types.items()),
        *(f'(assert (= {BASE}{key} {value}))' for key, value in values.items())]))
    targets = prefix_domains(document.config_pins)
    report = dict(owner='x', original_values={BASE + key: value for key, value in values.items()},
                  target_domains={pin.name: domain_metadata(domain) for pin, domain in targets},
                  domain_constraint=smt(domain_expression(targets)), bad_constraint='false',
                  support_constraint=smt(domain_expression(targets)),
                  allowed_constraint=smt(domain_expression(targets)),
                  property_condition='true', model_support_condition='true', legal_failures=29)
    plan = command_plans({LINE: report}, directory)[LINE]
    return document, report, plan


class MappingTest(unittest.TestCase):
    def test_cidr_is_one_field_and_enable_mask_length_are_not_separate_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, plan = fixture(directory)
            self.assertEqual([field['label'] for field in plan.fields], ['action', 'prefix'])
            self.assertEqual(plan.fields[1]['symbols'], [BASE + 'ip', BASE + 'length'])

    def test_equal_endpoint_values_do_not_hide_explicit_le_syntax(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, exact = fixture(directory)
            _, _, explicit = fixture(directory, modifiers='le 32')
            self.assertEqual(exact.compilation[BASE + 'prefix_range_end'], BASE + 'length')
            self.assertEqual(explicit.compilation[BASE + 'prefix_range_end'], BASE + 'prefix_range_end')
            self.assertEqual([field['label'] for field in explicit.fields], ['action', 'prefix', 'le'])

    def test_wrong_source_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, _ = fixture(directory)
            path = Path(directory) / 'X.cfg'
            path.write_text(path.read_text().replace('5.5.5.5/32', '6.6.6.6/32'))
            with self.assertRaisesRegex(SubspecificationError, 'source/encoding value mismatch'):
                command_plans({LINE: report}, directory)

    def test_native_sequence_label_maps_to_actual_cli_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'X.cfg'
            path.write_text('hostname X\nroute-map FROM_T permit 10\n set as-path prepend 65103\n')
            line = 'Config_x_RoutingPolicy_FROM_T__Seq20__Line1'
            original = {line + '__prepend_aspath_cost': '1', line + '__prepend_aspath_enable': 'true'}
            plan = command_plans({line: dict(owner='x', original_values=original)}, directory)[line]
            self.assertEqual(plan.source.number, 3)
            self.assertEqual(plan.source.sequence, 10)
            self.assertEqual(len(plan.fields), 1)


@unittest.skipUnless(Z3, 'Z3 required')
class CompilerProofTest(unittest.TestCase):
    def test_unencoded_list_name_is_not_reported_as_empty(self):
        from property_reports import write_subspecs
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'X.cfg'
            text = 'match ip address prefix-list TARGET'
            path.write_text(text + '\n')
            line = 'Config_x_RoutingPolicy_NO_TRANSIT__Seq10__Line1'
            enable = line + '__match_prefixlist_enable'
            command = SourceCommand(path, 1, text, 'match-prefix', 'NO_TRANSIT', 10, tuple(text.split()))
            plan = build_plan(line, {enable: 'true'}, command)
            document = SmtDocument.parse(f'(declare-fun {enable} () Bool)')
            report = dict(owner='x', original_values={enable: 'true'}, target_domains={enable: [False, True]},
                          domain_constraint='true', allowed_constraint='true', support_constraint='true',
                          bad_constraint='false', property_condition='true', model_support_condition='true')
            result = derive_contract(plan, report, document, Z3, 10, Path(directory) / 'proof')
            self.assertEqual(result['edit_status'], 'NOT_PARAMETERIZED')
            write_subspecs(Path(directory), {}, {line: result})
            displayed = (Path(directory) / '4_final_subspecs/x/line_level_subspecs.txt').read_text()
            self.assertIn('NOT_PARAMETERIZED', displayed)
            self.assertNotIn('1. empty', displayed)

    def test_preserved_prepend_command_requires_nonempty_asn_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'X.cfg'
            path.write_text('set as-path prepend 65103\n')
            line = 'Config_x_RoutingPolicy_FROM_T__Seq20__Line1'
            cost, enable = line + '__prepend_aspath_cost', line + '__prepend_aspath_enable'
            original = {cost: '1', enable: 'true'}
            command = SourceCommand(path, 1, path.read_text().strip(), 'prepend', 'FROM_T', 10,
                                    ('set', 'as-path', 'prepend', '65103'))
            plan = build_plan(line, original, command)
            document = SmtDocument.parse(f'(declare-fun {cost} () Int)\n(declare-fun {enable} () Bool)')
            report = dict(owner='x', original_values=original, target_domains={cost: {}, enable: [False, True]},
                          domain_constraint=f'(<= 0 {cost})', allowed_constraint=f'(<= 0 {cost})',
                          support_constraint=f'(<= 0 {cost})', bad_constraint='false',
                          property_condition='true', model_support_condition='true')
            result = derive_contract(plan, report, document, Z3, 10, Path(directory) / 'proof')
            runner = QueryRunner(document, Path(Z3), 10, Path(directory) / 'independent')
            runner.prove('nonempty', ['xor', ast(result['allowed_constraint']), ['<=', '1', cost]])

    def check_contract(self, root, document, report, plan, label='field', field=None):
        field = plan.fields[1] if field is None else field
        result = derive_contract(plan, report, document, Z3, 10, Path(root) / label, field)
        return result, QueryRunner(document, Path(Z3), 10, Path(root) / (label + '_independent'))

    def test_prefix_32_can_change_to_24_with_derived_mask_and_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            document, report, plan = fixture(directory)
            result, runner = self.check_contract(directory, document, report, plan)
            allowed = ast(result['allowed_constraint'])
            point = ['and', allowed, ['=', BASE + 'ip', '#x05050500'], ['=', BASE + 'length', '24']]
            self.assertEqual(runner.check('change_to_24', point), 'sat')
            self.assertEqual(result['property_condition'], 'true')
            # Compare against an independently written CIDR domain, including /0.
            expected = ast(f'''(and (<= 0 {BASE}length) (<= {BASE}length 32)
                (= (bvand {BASE}ip (bvshl #xffffffff ((_ int2bv 32) (- 32 {BASE}length)))) {BASE}ip))''')
            runner.prove('all_and_only_cidrs', ['xor', allowed, expected])
            self.assertEqual(runner.check('reject_host_bits', ['and', allowed,
                ['=', BASE + 'ip', '#x05050505'], ['=', BASE + 'length', '24']]), 'unsat')

    def test_default_le_32_keeps_le_and_recompiles_implicit_start(self):
        with tempfile.TemporaryDirectory() as directory:
            document, report, plan = fixture(directory, '0.0.0.0/0', 'le 32', 0, 32)
            # A property sensitive to range boundaries catches freezing S at 0.
            report['property_condition'] = f'(= {BASE}prefix_range_start {BASE}length)'
            report['allowed_constraint'] = f"(and {report['domain_constraint']} {report['property_condition']})"
            result, runner = self.check_contract(directory, document, report, plan)
            self.assertEqual(result['property_condition'], 'true')
            self.assertEqual(runner.check('prefix_24_le_32', ['and', ast(result['allowed_constraint']),
                ['=', BASE + 'ip', '#x05050500'], ['=', BASE + 'length', '24']]), 'sat')
            self.assertEqual(result['compilation'][BASE + 'prefix_range_end'], '32')
            self.assertEqual(result['compilation'][BASE + 'prefix_range_start'], BASE + 'length')

    def test_explicit_ge_le_are_fixed_when_only_prefix_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            document, report, plan = fixture(directory, '0.0.0.0/0', 'ge 16 le 24', 16, 24)
            result, runner = self.check_contract(directory, document, report, plan)
            allowed = ast(result['allowed_constraint'])
            self.assertEqual(runner.check('prefix_8', ['and', allowed, ['=', BASE + 'ip', '#x0a000000'],
                                                      ['=', BASE + 'length', '8']]), 'sat')
            self.assertEqual(runner.check('prefix_exceeds_fixed_ge', ['and', allowed,
                                                      ['=', BASE + 'length', '20']]), 'unsat')
            self.assertEqual(set(result['fixed_source_fields']), {LINE + '__action', LINE + '__ge', LINE + '__le'})

    def test_joint_line_changes_are_not_existentially_used_for_a_field(self):
        with tempfile.TemporaryDirectory() as directory:
            document, report, plan = fixture(directory)
            action, length = BASE + 'action', BASE + 'length'
            report['property_condition'] = f'(or {action} (= {length} 24))'
            report['allowed_constraint'] = f"(and {report['domain_constraint']} {report['property_condition']})"
            action_field = plan.fields[0]
            result, runner = self.check_contract(directory, document, report, plan, field=action_field)
            self.assertEqual(runner.check('deny_with_original_prefix', ['and', ast(result['allowed_constraint']),
                                                                       ['not', action]]), 'unsat')
            line = derive_contract(plan, report, document, Z3, 10, Path(directory) / 'line')
            self.assertEqual(runner.check('joint_deny_24', ['and', ast(line['allowed_constraint']),
                ['not', action], ['=', length, '24'], ['=', BASE + 'ip', '#x05050500']]), 'sat')


if __name__ == '__main__':
    unittest.main()
