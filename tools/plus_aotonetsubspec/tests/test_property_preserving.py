"""Regression tests for the Plus property-preserving entry point."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from property_model import PropertyModel, load_property_model
from property_subspec import _model_commands, _parse_pins, solve
from consistency.branch_loader import SymbolicRib
from utils.util_symbolic import SmtDocument, SubspecificationError, config_line_group
from utils.util_file import load_field_level_subspecs_from_file, load_line_level_subspecs_from_file

DEMO = ROOT.parents[2] / "DEMOIDEA"
Q1 = DEMO / "demo1/Q1/result/symbolic"
DEMO2 = DEMO / "demo2/result/forwarding/symbolic"
Q1_ENABLE = "Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_enable"
DEMO2_COST = "Config_c_RoutingPolicy_C_from_I__Seq10__Line2__prepend_aspath_cost"
DEMO3_ENABLE = "Config_t_RoutingPolicy_FROM_ISP__Seq10__Line2__prepend_aspath_enable"
DEMO3_ENV = os.environ.get("PLUS_DEMO3_INPUT")
Z3 = shutil.which("z3")
COMMUNITY_DEMO = ROOT / "example_results/demo1_community_policy"
T3_FIELD = "Config_i_RoutingPolicy_ORIGINATE__Seq10__Line2__set_community_65050_10__community"
T4_FIELD = "Config_t_CommunityList_QUARANTINE__Line1__65050_99__community"
I_EXPORT = "|0_i_BGP_EXPORT_GigabitEthernet0/0_"
T_IMPORT = "|0_t_BGP_IMPORT_GigabitEthernet0/2_"


@unittest.skipUnless(Z3, "Z3 is required for property-preserving proofs")
class PropertySolveTest(unittest.TestCase):
    def make_model(self, extra=""):
        document = SmtDocument.parse(f"""
            (declare-fun {Q1_ENABLE} () Bool)
            (declare-fun |0_dst-ip| () (_ BitVec 32))
            (declare-fun |0_FAILED-EDGE_t_x| () Int)
            (declare-fun |0_DATA-FORWARDING_x_to_t| () Bool)
            (declare-fun |0__reachable_x| () Bool)
            (assert (= {Q1_ENABLE} true))
            (assert (= |0_DATA-FORWARDING_x_to_t| (= |0_FAILED-EDGE_t_x| 0)))
            (assert (=> (or (not {Q1_ENABLE}) (= |0_FAILED-EDGE_t_x| 0)) |0__reachable_x|))
            {extra}
        """)
        return PropertyModel(document, "5.5.5.5/32", "x", "|0__reachable_x|",
                             {"t--x": "|0_FAILED-EDGE_t_x|"},
                             {"x": {"t": "|0_DATA-FORWARDING_x_to_t|"}, "t": {}})

    def test_one_bad_legal_state_excludes_a_configuration_with_good_states(self):
        model = self.make_model()
        commands = _model_commands(model, _parse_pins(model, [Q1_ENABLE], None), 1)
        commands += [f"(assert {Q1_ENABLE})", "(assert (= |0_FAILED-EDGE_t_x| 1))"]
        for predicate in [model.property_symbol, f"(not {model.property_symbol})"]:
            commands += ["(push)", f"(assert {predicate})", "(check-sat)", "(pop)"]
        states = subprocess.run([Z3, "-in"], input=model.document.query(*commands),
                                text=True, capture_output=True, timeout=10, check=True)
        self.assertEqual(states.stdout.splitlines(), ["sat", "sat"], states.stderr)
        with tempfile.TemporaryDirectory() as output:
            report = solve(model, [Q1_ENABLE], None, 1, Path(output), Z3, 5, 10, backend="enumerate")
        self.assertEqual(report["allowed_configurations"], [{Q1_ENABLE: False}])
        self.assertEqual(report["rejected_configurations"][0]["witness"]["failed_links"], ["t--x"])

    def test_missing_model_does_not_produce_an_allowed_formula(self):
        model = self.make_model(f"(assert (=> (not {Q1_ENABLE}) (= |0_FAILED-EDGE_t_x| 0)))")
        with tempfile.TemporaryDirectory() as output:
            output = Path(output)
            with self.assertRaisesRegex(SubspecificationError, "no legal model"):
                solve(model, [Q1_ENABLE], None, 1, output, Z3, 5, 10, backend="enumerate")
            self.assertFalse((output / "allowed.smt2").exists())


@unittest.skipUnless(Z3, "Z3 is required for the community CLI regressions")
class CommunityPropertyIntegrationTest(unittest.TestCase):
    def run_cli(self, fixture, field, k, output):
        source = COMMUNITY_DEMO / fixture / "input"
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/run.py"), str(source),
             "--property-preserving", "--property-backend", "enumerate", "--k", str(k), "--target", field,
             "--output", str(output), "--consistency-workers", "2"],
            text=True, capture_output=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["target_domains"], {field: ["#x1", "#x2"]})
        self.assertEqual(report["community_values"], {"65050:10": "#x1", "65050:99": "#x2"})
        self.assertEqual(report["native_implies_slice"], "UNSAT")
        self.assertEqual((output / "native_implies_slice.log").read_text().splitlines(), ["unsat"])
        self.assertEqual(report["native_model_coverage_checks"], report["model_coverage_checks"])
        self.assertEqual((output / "native_model_coverage.log").read_text().splitlines(),
                         ["sat"] * report["native_model_coverage_checks"])
        return report

    def assert_subspecs(self, output, report, field, line, owner, fixed):
        expected = f"(= {field} #x1)"
        line_terms = [expected, *(f"(= {name} {value})" for name, value in fixed.items())]
        self.assertEqual(report["allowed_configurations"], [{field: "#x1"}])
        self.assertEqual(set(report["field_level"]), {field})
        self.assertEqual(set(report["line_level"]), {line})
        self.assertEqual(report["field_level"][field]["fixed_same_line_fields"], fixed)
        self.assertEqual(report["line_level"][line]["fixed_same_line_fields"], fixed)
        self.assertEqual(report["line_level"][line]["allowed_constraint"],
                         f"(and {' '.join(line_terms)})")
        self.assertEqual(report["model_coverage_checks"], 16)
        self.assertEqual(len(report["rejected_configurations"]), 1)
        rejected, = report["rejected_configurations"]
        self.assertEqual(rejected["configuration"], {field: "#x2"})
        self.assertEqual(rejected["witness"]["failed_links"], ["c--t"])
        self.assertIs(rejected["witness"]["property_value"], False)
        final = output / "4_final_subspecs"
        for directory in [final, final / owner]:
            self.assertEqual(load_field_level_subspecs_from_file(directory / "field_level_subspecs.txt"),
                             {field: [expected]})
            self.assertEqual(load_line_level_subspecs_from_file(directory / "line_level_subspecs.txt"),
                             {line: [" AND ".join(line_terms)]})

    def assert_state(self, output, field, k, failures, value, required):
        model = load_property_model(output / "input", k)
        targets = _parse_pins(model, [field], None)
        commands = _model_commands(model, targets, k)
        commands += [f"(assert (= {field} {value}))",
                     *(f"(assert (= {symbol} {int(link in failures)}))"
                       for link, symbol in model.failure_symbols.items()),
                     "(check-sat)", f"(assert (not (and {' '.join(required)})))", "(check-sat)"]
        result = subprocess.run([Z3, "-in"], input=model.document.query(*commands),
                                text=True, capture_output=True, timeout=10, check=True)
        self.assertEqual(result.stdout.splitlines(), ["sat", "unsat"], result.stderr)

    def test_t3_cli_excludes_the_tag_rejected_at_import(self):
        line = "Config_i_RoutingPolicy_ORIGINATE__Seq10__Line2"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "t3"
            report = self.run_cli("t3_policy_change", T3_FIELD, 1, output)
            self.assert_subspecs(output, report, T3_FIELD, line, "i",
                                 {line + "__set_community_enable": "true"})
            self.assertEqual(report["original_values"], {T3_FIELD: "#x1"})
            self.assert_state(output, T3_FIELD, 1, {"c--t"}, "#x2",
                              [I_EXPORT + "permitted|", f"(= {I_EXPORT}community| #x2)",
                               f"(not {T_IMPORT}permitted|)", "(not |0__reachable_t|)"])

    def test_t4_cli_recovers_a_candidate_using_only_the_rejected_export(self):
        line = "Config_t_CommunityList_QUARANTINE__Line1"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "t4"
            report = self.run_cli("t4_candidate_recovery", T4_FIELD, 1, output)
            self.assert_subspecs(output, report, T4_FIELD, line, "t",
                                 {line + "__action": "true", line + "__enable": "true"})
            self.assertEqual(report["original_values"], {T4_FIELD: "#x2"})
            rib = SymbolicRib.from_work_directory(output / "input")
            baseline = rib.entries(router="t", vrf="default", prefix="5.5.5.5/32", plane="MAIN")
            self.assertEqual({route.selected_peer for route in baseline}, {"c"})
            export = [I_EXPORT + "permitted|", f"(= {I_EXPORT}community| #x2)"]
            self.assert_state(output, T4_FIELD, 1, {"c--t"}, "#x2",
                              [*export, f"(not {T_IMPORT}permitted|)", "(not |0__reachable_t|)"])
            self.assert_state(output, T4_FIELD, 1, {"c--t"}, "#x1",
                              [*export, T_IMPORT + "permitted|", f"(= {T_IMPORT}community| #x2)",
                               "|0_DATA-FORWARDING_t_GigabitEthernet0/2|", "|0__reachable_t|"])

    def test_all_allowed_community_values_still_constrain_the_bitvector(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "no-fault"
            report = self.run_cli("t4_candidate_recovery", T4_FIELD, 0, output)
            self.assertEqual(report["allowed_configurations"], [{T4_FIELD: "#x1"}, {T4_FIELD: "#x2"}])
            self.assertEqual(report["allowed_constraint"],
                             f"(or (= {T4_FIELD} #x1) (= {T4_FIELD} #x2))")

    def test_t6_no_route_is_a_legal_counterexample(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "t6"
            report = self.run_cli("t4_candidate_recovery", T4_FIELD, 2, output)
            self.assertEqual(report["model_coverage_checks"], 58)
            self.assertEqual((output / "model_coverage.log").read_text().splitlines(), ["sat"] * 58)
            self.assertEqual(report["allowed_constraint"], "false")
            self.assertEqual(report["field_level"][T4_FIELD]["allowed_constraint"], "false")
            line, = report["line_level"].values()
            self.assertEqual(line["allowed_constraint"], "false")
            witness = next(item["witness"] for item in report["rejected_configurations"]
                           if item["configuration"] == {T4_FIELD: "#x1"})
            self.assertEqual(witness["failed_links"], ["c--t", "i--t"])
            self.assertEqual(witness["forwarding"]["t"], [])
            self.assertIs(witness["property_value"], False)
            self.assert_state(output, T4_FIELD, 2, {"c--t", "i--t"}, "#x1",
                              ["(not |0_t_OVERALL_BEST_None_permitted|)", "(not |0__reachable_t|)"])


@unittest.skipUnless(Z3 and Q1.is_dir() and DEMO2.is_dir(), "saved Demo1/Q1 and Demo2 exports required")
class PropertyIntegrationTest(unittest.TestCase):
    def run_fixture(self, source, target, output, *options):
        output = Path(output)
        result = subprocess.run([
            sys.executable, "-B", str(ROOT / "tools/run.py"), str(source),
            "--property-preserving", "--property-backend", "enumerate", "--k", "2", "--target", target,
            "--output", str(output), "--consistency-workers", "2", *options,
        ], text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads((output / "report.json").read_text())

    def run_batch(self, source, low, high, output):
        result = subprocess.run([
            sys.executable, "-B", str(ROOT / "tools/run.py"), str(source),
            "--property-preserving", "--property-backend", "enumerate", "--k", "2", "--cost-range", str(low), str(high),
            "--output", str(output), "--consistency-workers", "2",
        ], text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads((output / "report.json").read_text())

    def test_demo1_batch_discovers_both_lines_and_writes_legacy_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo1-batch"
            report = self.run_batch(Q1, 0, 3, output)
            self.assertEqual(len(report["field_level"]), 4)
            self.assertEqual({item["owner"] for item in report["line_level"].values()}, {"t", "x"})
            self.assertTrue(report["unsupported_config_fields"])
            final = output / "4_final_subspecs"
            lines = load_line_level_subspecs_from_file(final / "line_level_subspecs.txt")
            line = Q1_ENABLE.removesuffix("__prepend_aspath_enable")
            cost = line + "__prepend_aspath_cost"
            self.assertEqual(set(lines), set(report["line_level"]))
            self.assertEqual(lines[line], [f"(<= 0 {cost}) AND (<= {cost} 3)"])
            field = (final / "t/field_level_subspecs.txt").read_text()
            self.assertIn(f"Config Variable: {Q1_ENABLE}\nSubspecs (1):\n  1. empty\n", field)
        self.assertEqual(report["field_level"][Q1_ENABLE]["fixed_same_line_fields"], {cost: "1"})
        self.assertIn({cost: 1, Q1_ENABLE: False}, report["line_level"][line]["allowed_configurations"])

    def test_batch_fields_keep_original_values_outside_the_line_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_batch(Q1, 2, 3, Path(directory) / "q1-outside")
        enable = report["field_level"][Q1_ENABLE]
        self.assertEqual(enable["method"], "solve-with-other-fields-fixed")
        self.assertEqual(enable["allowed_configurations"], [{Q1_ENABLE: False}, {Q1_ENABLE: True}])

    def test_full_batch_refuses_a_sampled_enumeration_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "full"
            result = subprocess.run([
                sys.executable, "-B", str(ROOT / "tools/run.py"), str(Q1), "--property-preserving", "--property-backend", "enumerate",
                "--all-configs", "--k", "2", "--cost-range", "0", "3", "--output", str(output),
                "--consistency-workers", "2",
            ], text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertIn('complete semantic domains', report['error'])
            self.assertFalse((output / '4_final_subspecs').exists())

    def test_q1_allows_omitting_prepend(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_fixture(Q1, Q1_ENABLE, Path(directory) / "q1")
        self.assertEqual(report["allowed_configurations"], [{Q1_ENABLE: False}, {Q1_ENABLE: True}])
        self.assertEqual(report["allowed_constraint"], "true")
        self.assertEqual(report["model_coverage_checks"], 58)
        self.assertFalse(report["rejected_configurations"])

    def test_demo2_excludes_null_discard_and_reports_witness(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_fixture(DEMO2, DEMO2_COST, Path(directory) / "demo2", "--cost-range", "0", "3")
        self.assertEqual(report["allowed_configurations"], [{DEMO2_COST: 2}, {DEMO2_COST: 3}])
        self.assertEqual(report["model_coverage_checks"], 116)
        rejected = report["rejected_configurations"]
        self.assertEqual([entry["configuration"][DEMO2_COST] for entry in rejected], [0, 1])
        oracle = json.loads((DEMO2.parent / "report.json").read_text())
        failures_at_one = {
            tuple(sorted(link.replace("-", "--") for link in case["failed_links"]))
            for case in json.loads(
                (DEMO2.parent / "cost_validation/i_cost_1/check.json").read_text())["cases"]
            if not case["reaches_d"]
        }
        at_one = rejected[1]["witness"]
        self.assertEqual(oracle["baseline_forwarding_passes"], 29)
        self.assertEqual(at_one["path"], ["x", "c", "i"])
        self.assertEqual(at_one["end"], "null_discard")
        self.assertIn(tuple(sorted(at_one["failed_links"])), failures_at_one)

    @unittest.skipUnless(DEMO3_ENV and Path(DEMO3_ENV).is_dir(), "PLUS_DEMO3_INPUT is not configured")
    def test_demo3_recomputes_the_indirect_competitor_and_merge(self):
        cost = DEMO3_ENABLE.removesuffix("_enable") + "_cost"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo3"
            report = self.run_fixture(Path(DEMO3_ENV), DEMO3_ENABLE, output,
                                      "--target", cost, "--cost-range", "0", "2")
            self.assertEqual(len(report["allowed_configurations"]), 6)
            self.assertEqual(report["model_coverage_checks"], 276)
            self.assertEqual(report["allowed_constraint"], f"(and (<= 0 {cost}) (<= {cost} 2))")
            model = load_property_model(output / "input", 2)
            targets = _parse_pins(model, [DEMO3_ENABLE, cost], (0, 2))
            commands = _model_commands(model, targets, 2)
            commands += [f"(assert (= {DEMO3_ENABLE} false))", f"(assert (= {cost} 1))",
                         *(f"(assert (= {edge} 0))" for edge in model.failure_symbols.values()),
                         "(check-sat)"]
            path_from_z = [model.forwarding[a][b] for a, b in [("z", "y"), ("y", "b"), ("b", "c")]]
            commands += [f"(assert (not (and {' '.join(path_from_z)})))", "(check-sat)"]
            result = subprocess.run([Z3, "-in"], input=model.document.query(*commands),
                                    text=True, capture_output=True, timeout=10, check=True)
            self.assertEqual(result.stdout.splitlines(), ["sat", "unsat"], result.stderr)
