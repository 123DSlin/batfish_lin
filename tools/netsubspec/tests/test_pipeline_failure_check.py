"""Check opt-in scheduling and fail-closed behavior without another network."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pipeline_failure_check_runner", ROOT / "tools/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class PipelineFailureCheckTest(unittest.TestCase):
    def run_pipeline(self, enabled, fail=False):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            reference = work / "traverse"
            reference.mkdir()
            (reference / "report.json").write_text("{}")
            calls = []
            def invoke(command, **kwargs):
                calls.append(command)
                is_check = command[1].endswith("compare_traverse_results.py")
                return subprocess.CompletedProcess(command, 1 if fail and is_check else 0)
            args = ["run.py", str(work), "--k", "2"]
            if enabled:
                args += ["--check-failure-intersection", "--traverse-results", str(reference), "--workers", "3", "--timeout", "12", "--z3", "/tmp/test-z3"]
            with patch.object(sys, "argv", args), patch.object(runner.subprocess, "run", side_effect=invoke), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = runner.main()
            state = json.loads((work / "failure_intersection_check_status.json").read_text())
            return code, calls, state

    def test_default_off_never_invokes_enumeration(self):
        code, calls, state = self.run_pipeline(False)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all("compare_traverse_results.py" not in c[1] for c in calls))
        self.assertEqual(state["status"], "DISABLED")

    def test_on_compares_saved_outputs_after_final_intersection(self):
        code, calls, state = self.run_pipeline(True)
        self.assertEqual(code, 0)
        self.assertTrue(calls[2][1].endswith("3_branch_simplifier.py"))
        self.assertTrue(calls[3][1].endswith("4_branch_intersection.py"))
        self.assertTrue(calls[4][1].endswith("compare_traverse_results.py"))
        self.assertIn("--output", calls[4])
        self.assertEqual(calls[4][calls[4].index("--timeout") + 1], "12.0")
        self.assertIn("--z3", calls[4])
        self.assertEqual(state["status"], "PASS")

    def test_failed_comparison_preserves_completed_symbolic_outputs(self):
        code, calls, state = self.run_pipeline(True, fail=True)
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 5)
        self.assertTrue(calls[3][1].endswith("4_branch_intersection.py"))
        self.assertEqual(state["status"], "FAIL")

    def test_enabled_without_reference_fails_before_any_pipeline_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(sys, "argv", ["run.py", temp, "--k", "2", "--check-failure-intersection"]), patch.object(runner.subprocess, "run") as invoke, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main(), 2)
            invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
