"""Independent SMT checks of source-field and line compilation."""
from importlib import import_module
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from utils.source_commands import compile_document, source_targets
from utils.util_smt import serialize_smt2_sexpr as smt
from utils.util_symbolic import SubspecificationError

stage = import_module('3_branch_simplifier')
LINE = 'Config_x_RouteFilterList_PL__Line1'
BASE = LINE + '__5_5_5_5__'


@unittest.skipUnless(shutil.which('z3'), 'Z3 required')
class SourceCommandTest(unittest.TestCase):
    def fixture(self, root, modifiers=''):
        Path(root, 'X.cfg').write_text('hostname X\nip prefix-list PL seq 10 permit 5.5.5.5/32' + modifiers + '\n')
        values = dict(ip='#x05050505', mask='#xffffffff', length='32',
                      prefix_range_start='32', prefix_range_end='32', action='true', enable='true')
        forms = []
        for name, value in values.items():
            sort = '(_ BitVec 32)' if name in ('ip', 'mask') else 'Bool' if name in ('action', 'enable') else 'Int'
            forms += [f'(declare-fun {BASE}{name} () {sort})', f'(assert (= {BASE}{name} {value}))']
        # Independent behavior observation: this line must permit /24 or wider.
        forms += [f'(assert (or {BASE}action (= {BASE}length 24)))']
        forms += ['(assert (! true :named branch_test_selection_guard))',
                  '(assert (! true :named branch_test_at_most_0_failures))']
        doc = stage._SmtDocument.parse('\n'.join(forms))
        compiled = compile_document(doc, stage._group_config_pins, root)
        compiled.__dict__['test_native'] = doc
        return compiled

    def check(self, doc, targets, point):
        released = {p.assertion_index for p in targets}
        expressions = [body for i, body in enumerate(doc.assertions) if i not in released]
        expressions += [doc.source_domain, point]
        query = '\n'.join([*doc.declaration_forms, *(smt(['assert', e]) for e in expressions), '(check-sat)'])
        result = subprocess.run(['z3', '-in'], input=query, text=True, capture_output=True, check=True)
        self.assertNotIn('error', result.stdout + result.stderr)
        return result.stdout.strip()

    def test_cidr_releases_address_and_length_and_recompiles_derived_values(self):
        with tempfile.TemporaryDirectory() as root:
            doc = self.fixture(root)
            fields = dict(source_targets(doc, 'field'))
            self.assertEqual(set(fields), {LINE + '__action', LINE + '__prefix'})
            prefix = fields[LINE + '__prefix']
            self.assertEqual({p.name for p in prefix}, {BASE+'ip', BASE+'length'})
            self.assertNotIn(BASE+'mask', doc.declarations)
            self.assertNotIn(BASE+'enable', doc.declarations)
            self.assertEqual(self.check(doc, prefix, ['and', ['=', BASE+'length', '24'], ['=', BASE+'ip', '#x05050500']]), 'sat')
            self.assertEqual(self.check(doc, prefix, ['and', ['=', BASE+'length', '24'], ['=', BASE+'ip', '#x05050505']]), 'unsat')

    def test_line_allows_joint_change_but_field_fixes_other_arguments(self):
        with tempfile.TemporaryDirectory() as root:
            doc = self.fixture(root)
            fields = dict(source_targets(doc, 'field'))
            self.assertEqual(self.check(doc, fields[LINE+'__action'], ['not', BASE+'action']), 'unsat')
            line = source_targets(doc, 'line')[0][1]
            point = ['and', ['not', BASE+'action'], ['=', BASE+'length', '24'], ['=', BASE+'ip', '#x05050500']]
            self.assertEqual(self.check(doc, line, point), 'sat')

    def test_explicit_le_and_implicit_endpoint_have_different_field_structure(self):
        with tempfile.TemporaryDirectory() as root:
            implicit = self.fixture(root)
            explicit = self.fixture(root, ' le 32')
            self.assertEqual(len(source_targets(implicit, 'field')), 2)
            self.assertEqual(len(source_targets(explicit, 'field')), 3)
            self.assertIn(BASE+'prefix_range_end', explicit.declarations)
            self.assertNotIn(BASE+'prefix_range_end', implicit.declarations)

    def test_branch_solver_projects_joint_line_then_specializes_source_fields(self):
        with tempfile.TemporaryDirectory() as root:
            doc = self.fixture(root)
            engine = stage.SymbolicSubspecifier(root)
            lines, fields = engine._source_batches(doc.test_native, doc,
                dict(router='x', destination='5.5.5.5'), 'test')
            self.assertIsNone(lines.error)
            self.assertIsNone(fields.error)
            self.assertEqual(len(lines.targets), 1)
            self.assertEqual(len(fields.targets), 2)
            action = next(r for r in fields.targets if r.name.endswith('__action'))
            self.assertTrue(engine.solver.entails(doc,
                stage.parse_smt2_sexpr(stage.tokenize_smt2_sexpr(stage.subspec_string_to_smt2_and(action.constraint))), BASE+'action'))
            line = lines.targets[0]
            expression = stage.parse_smt2_sexpr(stage.tokenize_smt2_sexpr(stage.subspec_string_to_smt2_and(line.constraint)))
            point = ['and', ['not', BASE+'action'], ['=', BASE+'length', '24'], ['=', BASE+'ip', '#x05050500']]
            query = doc.query(smt(['assert', expression]), smt(['assert', point]), '(check-sat)')
            result = subprocess.run(['z3', '-in'], input=query, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), 'sat')
            self.assertEqual(line.projection['source_equivalence_check'], 'UNSAT')

    def test_unencoded_list_reference_is_a_fixed_line_with_reported_limitation(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'X.cfg').write_text('hostname X\nroute-map FROM_T permit 10\n match ip address prefix-list PL\n')
            name = 'Config_x_RoutingPolicy_FROM_T__Seq10__Line1__match_prefixlist_enable'
            raw = stage._SmtDocument.parse(f'(declare-fun {name} () Bool)\n(assert (= {name} true))\n'
                '(assert (! true :named branch_test_selection_guard))\n'
                '(assert (! true :named branch_test_at_most_0_failures))')
            doc = compile_document(raw, stage._group_config_pins, root)
            engine = stage.SymbolicSubspecifier(root)
            lines, fields = engine._source_batches(raw, doc, dict(router='x', destination='5.5.5.5'), 'test')
            self.assertIsNone(lines.error)
            self.assertEqual(fields.targets, ())
            self.assertEqual(len(lines.targets), 1)
            self.assertEqual(lines.targets[0].pins, ())
            self.assertEqual(lines.targets[0].constraint, 'true')
            self.assertTrue(lines.targets[0].projection['limitations'])

    def test_source_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            doc = self.fixture(root)
            Path(root, 'X.cfg').write_text('hostname X\nip prefix-list PL seq 10 permit 6.6.6.6/32\n')
            with self.assertRaisesRegex(SubspecificationError, 'source/encoding value mismatch'):
                compile_document(doc.test_native, stage._group_config_pins, root)


if __name__ == '__main__':
    unittest.main()
