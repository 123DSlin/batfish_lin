"""Reuse must preserve complete solver contexts and target-dependent snapshots."""

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from utils.util_symbolic import SmtSolver

stage3 = import_module("3_branch_simplifier")


class SolverReuseTest(unittest.TestCase):
    def solver(self, **kwargs):
        with patch.object(SmtSolver, "_resolve_z3", return_value=Path("/test/z3")):
            return SmtSolver(**kwargs)

    def result(self, output="unsat", *, code=0, error=""):
        return subprocess.CompletedProcess([], code, output, error)

    def test_reuses_only_identical_requests_and_returns_fresh_results(self):
        solver = self.solver()
        with patch("utils.util_symbolic.subprocess.run", return_value=self.result()) as run:
            first = solver._invoke("(check-sat)")
            first.stdout = "unknown"
            self.assertEqual(solver._invoke("(check-sat)").stdout, "unsat")
            solver._invoke("(check-sat)", timeout=1)
            solver._invoke("(assert false)\n(check-sat)")
            solver.z3_path = Path("/other/z3")
            solver._invoke("(check-sat)")
            self.assertEqual(run.call_count, 4)
        self.assertEqual(solver.cache_info()["hits"], 1)

    def test_different_definitions_and_tactics_cannot_share_answers(self):
        solver = self.solver()
        queries = [
            "(define-fun p () Bool true)\n(assert p)\n(check-sat)",
            "(define-fun p () Bool false)\n(assert p)\n(check-sat)",
            "(define-fun p () Bool true)\n(assert p)\n(check-sat-using smt)",
        ]
        with patch("utils.util_symbolic.subprocess.run", side_effect=[
            self.result("sat"), self.result("unsat"), self.result("sat")
        ]) as run:
            for _ in range(2):
                self.assertEqual([solver._invoke(q).stdout for q in queries],
                                 ["sat", "unsat", "sat"])
            self.assertEqual(run.call_count, 3)

    def test_uncertain_or_failed_answers_are_not_cached(self):
        outputs = [
            self.result("unknown"), self.result(""), self.result("(error \"bad\")"),
            self.result(code=1), self.result(error="warning"),
            self.result("(goals (goal true :precision under :depth 1))"),
            self.result('(goals (goal true :precision precise :depth 1))\n(error "bad")'),
            self.result("(goals (goal"),
            self.result("(goals (goal true) (goal false))"),
        ]
        for result in outputs:
            with self.subTest(output=result):
                solver = self.solver()
                with patch("utils.util_symbolic.subprocess.run", return_value=result) as run:
                    solver._invoke("query")
                    solver._invoke("query")
                    self.assertEqual(run.call_count, 2)
                    self.assertEqual(solver.cache_info()["entries"], 0)

    def test_timeout_is_not_cached_and_can_be_retried(self):
        solver = self.solver()
        with patch("utils.util_symbolic.subprocess.run", side_effect=[
            subprocess.TimeoutExpired("z3", 1), self.result()
        ]) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                solver._invoke("query")
            self.assertEqual(solver._invoke("query").stdout, "unsat")
            self.assertEqual(run.call_count, 2)

    def test_precise_goals_are_reused(self):
        solver = self.solver()
        result = self.result("(goals (goal (>= x 1) :precision precise :depth 1))")
        with patch("utils.util_symbolic.subprocess.run", return_value=result) as run:
            self.assertEqual(solver._run_goal("query", "first"), ("(>= x 1)",))
            self.assertEqual(solver._run_goal("query", "second"), ("(>= x 1)",))
            self.assertEqual(run.call_count, 1)

    def test_lru_eviction_size_limits_and_disable(self):
        solver = self.solver(cache_entries=2)
        with patch("utils.util_symbolic.subprocess.run", return_value=self.result()) as run:
            for q in ["a", "b", "a", "c", "b"]:
                solver._invoke(q)
            self.assertEqual(run.call_count, 4)
            self.assertEqual(solver.cache_info()["entries"], 2)
            solver.clear_cache()
            self.assertEqual(solver.cache_info()["entries"], 0)
            self.assertEqual(solver.cache_info()["hits"], 0)
        for limits in [dict(cache_entries=0), dict(cache_bytes=0), dict(cache_bytes=1)]:
            solver = self.solver(**limits)
            with patch("utils.util_symbolic.subprocess.run", return_value=self.result()) as run:
                solver._invoke("query")
                solver._invoke("query")
                self.assertEqual(run.call_count, 2)
                self.assertEqual(solver.cache_info()["bytes"], 0)
        solver = self.solver(cache_bytes=35)
        with patch("utils.util_symbolic.subprocess.run", return_value=self.result()):
            for q in ["aaaa", "bbbb", "cccc"]:
                solver._invoke(q)
            self.assertEqual(solver.cache_info()["entries"], 2)
            self.assertLessEqual(solver.cache_info()["bytes"], 35)

    def test_parallel_queries_preserve_bounds_and_answers(self):
        solver = self.solver(cache_entries=2)
        with patch("utils.util_symbolic.subprocess.run", return_value=self.result("sat")):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(solver._invoke, ["a", "b", "c"] * 30))
        self.assertTrue(all(r.stdout == "sat" for r in results))
        info = solver.cache_info()
        self.assertLessEqual(info["entries"], 2)
        self.assertLessEqual(info["bytes"], info["max_bytes"])


class SnapshotReuseTest(unittest.TestCase):
    def test_index_reuse_preserves_target_specific_release_and_document_scope(self):
        text = """
        (declare-fun Config_x_set_localpreference () Int)
        (declare-fun Config_x_set_metric () Int)
        (declare-fun lp () Int)
        (declare-fun metric () Int)
        (assert (= Config_x_set_localpreference 100))
        (assert (= Config_x_set_metric 50))
        (assert (= lp (+ Config_x_set_localpreference 0)))
        (assert (= metric (+ Config_x_set_metric 0)))
        (assert (! (= lp 100) :named branch_current_best_lp))
        (assert (! (= metric 50) :named branch_selected_peer_metric))
        """
        document = stage3._SmtDocument.parse(text)
        original = stage3._device_value_dependencies
        with patch.object(stage3, "_device_value_dependencies", wraps=original) as build:
            lp = document._target_dependent_route_snapshots(
                frozenset({"Config_x_set_localpreference"}))
            metric = document._target_dependent_route_snapshots(
                frozenset({"Config_x_set_metric"}))
            both = document._target_dependent_route_snapshots(
                frozenset({"Config_x_set_localpreference", "Config_x_set_metric"}))
            self.assertEqual(build.call_count, 1)
        self.assertEqual(lp, (frozenset({4}), ("branch_current_best_lp",), ("lp",)))
        self.assertEqual(metric, (frozenset({5}), ("branch_selected_peer_metric",), ("metric",)))
        self.assertEqual(both[0], lp[0] | metric[0])
        other = stage3._SmtDocument.parse(text.replace("(= lp (+ Config_x_set_localpreference 0))",
                                                       "(= lp (+ Config_x_set_metric 0))"))
        self.assertEqual(other._target_dependent_route_snapshots(
            frozenset({"Config_x_set_localpreference"}))[0], frozenset())


if __name__ == "__main__":
    unittest.main()
