"""The concrete oracle must compute an intersection, not a union or witness."""

from importlib import import_module
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_symbolic_intersection import concrete_document
from consistency.branch_loader import GuardVariable
from consistency.guard_encoder import GuardEncoder
from utils.util_symbolic import SmtSolver, and_expression
from utils.util_smt import parse_smt2_sexpr, tokenize_smt2_sexpr, subspec_string_to_smt2_and

stage3 = import_module("3_branch_simplifier")
CONFIG = "Config_x_RoutingPolicy_P__Line1__set_localpreference_15"


class SymbolicIntersectionOracleTest(unittest.TestCase):
    def test_symbolic_range_equals_concrete_intersection_and_rejects_union(self):
        document = stage3._SmtDocument.parse(f"""
        (declare-fun {CONFIG} () Int)
        (declare-fun |LINK-UP-x_y| () Bool)
        (assert (= {CONFIG} 15))
        (assert (or (not |LINK-UP-x_y|) (>= {CONFIG} 10)))
        (assert (or |LINK-UP-x_y| (<= {CONFIG} 20)))
        (assert (! true :named branch_t_selection_guard))
        (assert (! true :named branch_t_at_most_1_failures))
        """)
        encoder = GuardEncoder((GuardVariable("x_y", "LINK", "x", "y", "UP"),))
        solver = SmtSolver()
        formulas = []
        for failed in [frozenset(), frozenset({"x_y"})]:
            concrete = concrete_document(document, encoder, failed)
            self.assertEqual(concrete.branch_conditions().failure_variables, ())
            self.assertEqual(concrete.config_pins, document.config_pins)
            problem = concrete.quantified_projection(concrete.config_pins, "1.1.1.1")
            self.assertEqual(problem.universal_names, ())
            result = solver.project(concrete, concrete.config_pins, problem.expression, "oracle test")
            formulas.append(parse_smt2_sexpr(tokenize_smt2_sexpr(subspec_string_to_smt2_and(result))))
        intersection = and_expression(formulas)
        expected = f"(>= {CONFIG} 10) AND (<= {CONFIG} 20)"
        symbolic = document.quantified_projection(document.config_pins, "1.1.1.1")
        self.assertTrue(solver.equivalent(document, intersection, expected)[0])
        self.assertTrue(solver.equivalent(document, symbolic.expression, expected)[0])
        self.assertFalse(solver.equivalent(document, ["or", *formulas], expected)[0])

    def test_definitions_cannot_reintroduce_a_free_failure_symbol(self):
        document = stage3._SmtDocument.parse("""
        (declare-fun |LINK-UP-x_y| () Bool)
        (define-fun up () Bool |LINK-UP-x_y|)
        (assert (! up :named branch_t_selection_guard))
        (assert (! true :named branch_t_at_most_1_failures))
        """)
        encoder = GuardEncoder((GuardVariable("x_y", "LINK", "x", "y", "UP"),))
        concrete = concrete_document(document, encoder, frozenset({"x_y"}))
        self.assertEqual(concrete.definition_forms, ("(define-fun up () Bool false)",))


if __name__ == "__main__":
    unittest.main()
