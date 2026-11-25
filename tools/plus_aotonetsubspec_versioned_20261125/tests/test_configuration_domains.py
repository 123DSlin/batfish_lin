"""Semantic domains and numeric contracts, checked with the actual SMT solver."""
from dataclasses import replace
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from configuration_domains import DomainTargets, IntegerDomain, BitVectorDomain, prefix_domains
from property_model import PropertyModel, load_encoding_semantics
from property_regions import RegionSolver, domain_contains, domain_expression, domain_metadata
from property_subspec import _parse_pins, _line_domains, _keep_unused_fields_fixed, _solve_assignments
from region_smt import QueryRunner, ast
from utils.util_symbolic import SmtDocument, SubspecificationError
from utils.util_smt import serialize_smt2_sexpr as smt

Z3 = shutil.which('z3')
COST = 'Config_t_RoutingPolicy_FROM_I__Seq10__Line1__prepend_aspath_cost'
FAILURE = '|0_FAILED-EDGE_t_x|'
PROPERTY = '|0__reachable_x|'


def model_for(field=COST, sort='Int', original='17', property_body=None):
    body = property_body or f'(>= {field} 17)'
    document = SmtDocument.parse(f'''
      (declare-fun {field} () {sort})
      (declare-fun |0_dst-ip| () (_ BitVec 32))
      (declare-fun {FAILURE} () Int)
      (declare-fun |0_t_BGP_IMPORT_port_permitted| () Bool)
      (declare-fun {PROPERTY} () Bool)
      (assert (= {field} {original}))
      (assert |0_t_BGP_IMPORT_port_permitted|)
      (assert (= {PROPERTY} {body}))
    ''')
    return PropertyModel(document, '5.5.5.5/32', 'x', PROPERTY, {'t--x': FAILURE}, {'t': {}, 'x': {}})


class DomainMetadataTest(unittest.TestCase):
    def test_prefix_semantics_metadata_distinguishes_legacy_exports(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            self.assertEqual(load_encoding_semantics(work), {})
            path = work / '0_encoding_semantics.json'
            policy = dict(schema='batfish-smt-encoding-semantics', version=1,
                          symbolic_prefix_length_ranges='variable-inclusive-bounds')
            path.write_text(json.dumps(policy))
            self.assertEqual(load_encoding_semantics(work), policy)
            policy['symbolic_prefix_length_ranges'] = 'original-endpoint-shape'
            path.write_text(json.dumps(policy))
            with self.assertRaisesRegex(SubspecificationError, 'unsupported encoding semantics'):
                load_encoding_semantics(work)

    def test_prepend_has_no_automatic_upper_bound(self):
        model = model_for()
        targets = _parse_pins(model, [COST], None)
        domain = targets[0][1]
        self.assertIsInstance(domain, IntegerDomain)
        self.assertIsNone(domain.maximum)
        self.assertTrue(domain_contains(domain_metadata(domain), str(10 ** 100)))
        self.assertFalse(domain_contains(domain_metadata(domain), '-1'))

    def test_med_domain_contains_the_entire_unsigned_integer_range(self):
        name = 'Config_t_RoutingPolicy_FROM_C__Seq10__Line1__set_metric_10'
        model = model_for(name, original='10')
        targets, assignments = _line_domains(model, 'Config_t_RoutingPolicy_FROM_C__Seq10__Line1',
                                             list(model.document.config_pins), None)
        self.assertIsNone(assignments)
        domain = targets[0][1]
        self.assertEqual(domain.maximum, 4294967295)
        for number in (1, 7, 12, 1000000, 4294967295):
            self.assertTrue(domain.contains(str(number)))
        self.assertFalse(domain.contains('4294967296'))
        self.assertTrue(domain.contains('0'))

    def test_finite_oracle_cannot_silently_sample_a_semantic_domain(self):
        model = model_for()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SubspecificationError, 'cannot be sampled'):
                _solve_assignments(model, _parse_pins(model, [COST], None), 1, Path(directory),
                                   Path(Z3 or '/missing-z3'), 5, 100, backend='enumerate')

    def test_unbounded_domain_rejects_legacy_metric_export(self):
        model = model_for()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'input'; work.mkdir()
            text = model.document.query(*(f'(assert {smt(expr)})' for expr in model.document.assertions),
                                        f'(assert (not (and true {PROPERTY})))')
            source = work / 'smt_encoding.smt2'; source.write_text(text)
            with self.assertRaisesRegex(SubspecificationError, 'regenerate the input'):
                _solve_assignments(model, _parse_pins(model, [COST], None), 1, Path(directory),
                                   Path(Z3 or '/missing-z3'), 5, 100, native_work=work)
            self.assertEqual(source.read_text(), text)

    def test_full_prefix_length_rejects_legacy_range_equations(self):
        name = 'Config_c_RouteFilterList_TARGET__Line1__5_5_5_5__length'
        model = model_for(name, original='32')
        targets = DomainTargets([(model.document.config_pins[0], IntegerDomain(0, 32))])
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'input'; work.mkdir()
            source = work / 'smt_encoding.smt2'
            source.write_text(model.document.query(
                *(f'(assert {smt(expr)})' for expr in model.document.assertions),
                f'(assert (not (and true {PROPERTY})))'))
            with self.assertRaisesRegex(SubspecificationError, 'regenerate the input'):
                _solve_assignments(model, targets, 1, Path(directory),
                                   Path(Z3 or '/missing-z3'), 5, 100, native_work=work)


@unittest.skipUnless(Z3, 'Z3 required')
class SymbolicDomainProofTest(unittest.TestCase):
    def test_unbounded_threshold_is_inferred_without_configuration_enumeration(self):
        model = model_for()
        with tempfile.TemporaryDirectory() as directory:
            runner = QueryRunner(model.document, Path(Z3), 10, Path(directory) / 'queries')
            targets = _parse_pins(model, [COST], None)
            report = RegionSolver(model, targets, 1, runner).solve()
            self.assertEqual(report['configuration_values_enumerated'], 0)
            self.assertEqual(report['model_support_condition'], 'true')
            runner.prove('inferred_lower_bound', ['xor', ast(report['allowed_constraint']), ['>=', COST, '17']])
            runner.prove('property_condition_in_domain', ['and', ast(report['domain_constraint']),
                         ['xor', ast(report['property_condition']), ['>=', COST, '17']]])

    def test_missing_field_semantics_are_support_restrictions_not_legal_bounds(self):
        name = 'Config_t_RoutingPolicy_FROM_C__Seq10__Line1__enable'
        model = replace(model_for(name, 'Bool', 'true', 'true'), unused_config_fields=frozenset({name}))
        targets = DomainTargets([(model.document.config_pins[0], (False, True))])
        targets, assignments = _keep_unused_fields_fixed(model, targets, None)
        self.assertEqual(targets[0][1], (False, True))
        self.assertIsNone(assignments)
        with tempfile.TemporaryDirectory() as directory:
            runner = QueryRunner(model.document, Path(Z3), 10, Path(directory) / 'queries')
            report = RegionSolver(model, targets, 1, runner).solve()
            runner.prove('complete_Boolean_domain', ['not', ast(report['domain_constraint'])])
            self.assertEqual(report['property_condition'], 'true')
            runner.prove('support_only_original', ['xor', ast(report['model_support_condition']), name])

    def test_ipv4_prefix_grammar_covers_all_networks_and_rejects_invalid_syntax(self):
        prefix = 'Config_c_RouteFilterList_TARGET__Line1__5_5_5_5__'
        types = dict(action='Bool', enable='Bool', ip='(_ BitVec 32)', mask='(_ BitVec 32)',
                     length='Int', prefix_range_start='Int', prefix_range_end='Int')
        original = dict(action='true', enable='true', ip='#x05050505', mask='#xffffffff',
                        length='32', prefix_range_start='32', prefix_range_end='32')
        document = SmtDocument.parse('\n'.join(
            [*(f'(declare-fun {prefix}{key} () {sort})' for key, sort in types.items()),
             *(f'(assert (= {prefix}{key} {value}))' for key, value in original.items())]))
        targets = prefix_domains(document.config_pins)
        self.assertTrue(any(isinstance(domain, BitVectorDomain) for _, domain in targets))
        legal = domain_expression(targets)
        with tempfile.TemporaryDirectory() as directory:
            runner = QueryRunner(document, Path(Z3), 10, Path(directory) / 'queries')
            cases = [
                ('arbitrary_24', '#xc6336400', '#xffffff00', 24, 24, 32, 'sat'),
                ('default_route', '#x00000000', '#x00000000', 0, 0, 32, 'sat'),
                ('arbitrary_host', '#xcb007109', '#xffffffff', 32, 32, 32, 'sat'),
                ('host_bits', '#xc6336401', '#xffffff00', 24, 24, 32, 'unsat'),
                ('noncontiguous_mask', '#x00000000', '#xff00ff00', 16, 16, 32, 'unsat'),
                ('invalid_range', '#xc6336400', '#xffffff00', 24, 23, 32, 'unsat'),
            ]
            for label, ip, mask, length, lower, upper, expected in cases:
                bindings = dict(ip=ip, mask=mask, length=str(length), prefix_range_start=str(lower), prefix_range_end=str(upper))
                query = ['and', legal, *(['=', prefix + key, value] for key, value in bindings.items())]
                self.assertEqual(runner.check(label, query), expected)
            # Exercise projection and its independent quantified equivalence
            # check over mixed integer lengths and full-width IPv4 addresses.
            witness = '|prefix_witness|'
            extended = SmtDocument.parse(document.query(f'(declare-fun {witness} () Int)'))
            runner.document = extended
            body = ['and', legal, ['=', witness, ['+', prefix + 'length', '3']]]
            projected = runner.project('all_prefixes_project', body, {pin.name for pin, _ in targets})
            runner.prove('all_prefixes_preserved', ['xor', projected, legal])


if __name__ == '__main__':
    unittest.main()
