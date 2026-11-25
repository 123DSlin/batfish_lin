from importlib import import_module
import json
from pathlib import Path
import tempfile
import unittest


_traffic = import_module("5_traffic_subspecification")
TrafficSubspecificationEngine = _traffic.TrafficSubspecificationEngine
TrafficSubspecificationError = _traffic.TrafficSubspecificationError


ENCODING = """
(declare-fun failed_a () Bool)
(declare-fun Config_r_policy_path_a_weight () Int)
(declare-fun Config_r_policy_path_b_weight () Int)
(assert (<= (+ (ite failed_a 1 0)) 1))
(assert (= Config_r_policy_path_a_weight 5))
(assert (>= Config_r_policy_path_a_weight 1))
(assert (<= Config_r_policy_path_a_weight 100))
(assert (= Config_r_policy_path_b_weight 5))
(assert (>= Config_r_policy_path_b_weight 1))
(assert (<= Config_r_policy_path_b_weight 100))
(declare-fun load_a () Real)
(assert (= load_a (ite failed_a
    (to_real Config_r_policy_path_a_weight)
    (to_real Config_r_policy_path_b_weight))))
(assert (< load_a 10.0))
(declare-fun load_b () Real)
(assert (= load_b 0.0))
(assert (< load_b 10.0))
(check-sat)
"""


class TrafficSubspecificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.work = Path(self.temporary.name)
        (self.work / "smt_traffic_encoding.smt2").write_text(
            ENCODING, encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_joint_projection_quantifies_failures_and_intersects_links(self) -> None:
        report = TrafficSubspecificationEngine(self.work).run()
        self.assertEqual(report.status, "PASS")
        self.assertEqual(
            set(report.joint.target_weights),
            {
                "Config_r_policy_path_a_weight",
                "Config_r_policy_path_b_weight",
            },
        )
        self.assertEqual(report.joint.universal_failure_variables, ("failed_a",))
        self.assertNotIn("failed_a", report.joint.constraint)
        self.assertTrue(
            all(item.equivalence_check == "UNSAT" for item in report.joint.link_projections)
        )
        self.assertEqual(report.joint.equivalence_check, "UNSAT")

    def test_localized_projection_pins_other_weight(self) -> None:
        report = TrafficSubspecificationEngine(self.work).run()
        localized = {
            item.target_weights[0]: item for item in report.localized
        }
        a = localized["Config_r_policy_path_a_weight"]
        self.assertEqual(
            a.non_target_weights_pinned,
            ("Config_r_policy_path_b_weight",),
        )
        self.assertNotIn("Config_r_policy_path_b_weight", a.constraint)
        self.assertNotIn("failed_a", a.constraint)

    def test_writes_auditable_artifacts(self) -> None:
        output = self.work / "out"
        TrafficSubspecificationEngine(self.work).run(output_directory=output)
        self.assertEqual(
            {path.name for path in output.iterdir()},
            {
                "field_level_subspecs.txt",
                "line_level_subspecs.txt",
                "traffic_subspecs.json",
                "traffic_subspecs.txt",
                "joint_weight_subspec.smt2",
            },
        )
        payload = json.loads(
            (output / "traffic_subspecs.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["joint_feasible"])
        self.assertEqual(
            payload["intersection_semantics"],
            "conjunction-of-universally-safe-link-capacity-projections",
        )
        self.assertIn("r", payload["devices"])
        self.assertEqual(
            set(payload["devices"]["r"]), {"field_level", "line_level"}
        )
        self.assertIn(
            "Device: r",
            (output / "field_level_subspecs.txt").read_text(encoding="utf-8"),
        )
        self.assertIn("(check-sat)", (output / "joint_weight_subspec.smt2").read_text())

    def test_groups_sr_path_fields_into_one_device_line(self) -> None:
        path = self.work / "smt_traffic_encoding.smt2"
        path.write_text(
            ENCODING.replace(
                "Config_r_policy_path_a_weight",
                "Config_r_SrPolicy_split_to_D_Path_a_weight",
            ).replace(
                "Config_r_policy_path_b_weight",
                "Config_r_SrPolicy_split_to_D_Path_b_weight",
            ),
            encoding="utf-8",
        )
        report = TrafficSubspecificationEngine(self.work).run()
        self.assertEqual(len(report.line_level), 1)
        self.assertEqual(report.line_level[0].device, "r")
        self.assertEqual(
            report.line_level[0].line, "Config_r_SrPolicy_split_to_D"
        )
        self.assertEqual(len(report.line_level[0].members), 2)

    def test_reports_unsatisfiable_device_field_and_line_views(self) -> None:
        path = self.work / "smt_traffic_encoding.smt2"
        path.write_text(
            ENCODING.replace("(assert (< load_a 10.0))", "(assert (< load_a 1.0))"),
            encoding="utf-8",
        )
        report = TrafficSubspecificationEngine(self.work).run()
        self.assertFalse(report.joint_feasible)
        self.assertTrue(all(item.constraint == "UNSAT" for item in report.field_level))
        self.assertTrue(all(item.constraint == "UNSAT" for item in report.line_level))

    def test_rejects_unclassified_assertion(self) -> None:
        path = self.work / "smt_traffic_encoding.smt2"
        path.write_text(
            ENCODING.replace("(check-sat)", "(assert (> 3 2))\n(check-sat)"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            TrafficSubspecificationError, "unclassified traffic SMT assertion"
        ):
            TrafficSubspecificationEngine(self.work).run()

    def test_projects_isis_interface_cost_as_config_field(self) -> None:
        cost = "Config_r_Interface_Ethernet0_Isis_L2_cost"
        encoding = ENCODING.replace(
            "(declare-fun load_a () Real)",
            f"""(declare-fun {cost} () Int)
(assert (= {cost} 10))
(assert (>= {cost} 1))
(assert (<= {cost} 16777215))
(declare-fun load_a () Real)""",
        ).replace(
            "(to_real Config_r_policy_path_a_weight)",
            f"(ite (<= {cost} 20) (to_real Config_r_policy_path_a_weight) 20.0)",
        )
        (self.work / "smt_traffic_encoding.smt2").write_text(
            encoding, encoding="utf-8"
        )
        report = TrafficSubspecificationEngine(self.work).run(targets=(cost,))
        self.assertEqual(report.joint.target_weights, (cost,))
        self.assertIn(cost, report.joint.constraint)
        self.assertNotIn("failed_a", report.joint.constraint)
        self.assertEqual(report.joint.equivalence_check, "UNSAT")


if __name__ == "__main__":
    unittest.main()
