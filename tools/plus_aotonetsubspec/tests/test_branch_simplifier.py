from importlib import import_module
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from consistency.guard_encoder import GuardEncoder

from utils.util_file import (
    load_field_level_subspecs_from_file,
    load_line_level_subspecs_from_file,
)
from utils.util_symbolic import (
    SubspecificationError,
    residual_declared_symbols as _residual_declared_symbols,
)

_branch_simplifier = import_module("3_branch_simplifier")
_SmtDocument = _branch_simplifier._SmtDocument
_field_targets = _branch_simplifier._field_targets
_group_config_pins = _branch_simplifier._group_config_pins
SubspecificationReport = _branch_simplifier.SubspecificationReport
SymbolicSubspecifier = _branch_simplifier.SymbolicSubspecifier


REPOSITORY = Path(__file__).resolve().parents[1]
WORK_DIRECTORY = REPOSITORY / "tests" / "fixtures" / "symbolic_output_0010"


class SymbolicSubspecifierIntegrationTest(unittest.TestCase):
    temporary: tempfile.TemporaryDirectory[str]
    output: Path
    subspecifier: SymbolicSubspecifier
    report: SubspecificationReport

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / "stage3"
        cls.subspecifier = SymbolicSubspecifier(WORK_DIRECTORY)
        with patch.object(GuardEncoder, "satisfying_failure_assignments", side_effect=AssertionError("stage 3 must not enumerate F")), patch.object(
            GuardEncoder, "concrete_assignment_expressions", side_effect=AssertionError("stage 3 must not pin F")
        ):
            cls.report = cls.subspecifier.run(output_directory=cls.output)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_derives_every_consistent_branch(self) -> None:
        self.assertEqual(self.report.status, "PASS")
        self.assertEqual(self.report.branch_count, 7)
        self.assertEqual(self.report.field_evaluations, 66)
        self.assertEqual(
            [len(branch.fields) for branch in self.report.branches],
            [0, 7, 7, 7, 7, 19, 19],
        )
        self.assertEqual(self.report.line_evaluations, 26)
        self.assertEqual(
            [len(branch.lines) for branch in self.report.branches],
            [0, 2, 2, 2, 2, 9, 9],
        )
        self.assertTrue(
            all(
                field.derivation
                in {
                    "symbolic-line-specialization",
                    "symbolic-reference-simplification",
                }
                for branch in self.report.branches
                for field in branch.fields
            )
        )

    def test_every_result_is_fully_projected_to_its_target_configs(self) -> None:
        for branch in self.report.branches:
            seed = self.subspecifier._resolve_seed_path(
                {
                    "candidate_id": branch.candidate_id,
                    "seed_file": branch.seed_file,
                }
            )
            document = _SmtDocument.parse(seed.read_text(encoding="utf-8"))
            for result in (*branch.fields, *branch.lines):
                allowed = frozenset(
                    result.released_configs
                    if hasattr(result, "released_configs")
                    else result.configs
                )
                self.assertEqual(
                    _residual_declared_symbols(
                        result.constraint, document.declarations, allowed
                    ),
                    (),
                    msg=f"{branch.branch_name}: {result}",
                )
                self.assertEqual(result.projection["equivalence_check"], "not-run")
                self.assertEqual(result.projection["residual_symbols"], [])
                self.assertFalse(result.projection["failure_enumeration"])

    def test_symbolic_projection_preserves_expected_local_preference_ranges(self) -> None:
        target_suffix = (
            "RoutingPolicy_R4_IN_FROM_R3__Seq10__Line2__"
            "set_localpreference_50"
        )
        expected = {
            "r4-r2-r1": (0, 200),
            "r4-r1": (0, 100),
        }
        for branch in self.report.branches:
            if branch.branch_name not in expected:
                continue
            result = next(
                field for field in branch.fields if field.config.endswith(target_suffix)
            )
            lower, upper = expected[branch.branch_name]
            self.assertIn(f"(>= {result.config} {lower})", result.constraint)
            self.assertIn(f"(<= {result.config} {upper})", result.constraint)

    def test_selected_local_preference_is_recomputed_not_frozen(self) -> None:
        via_r2 = next(
            branch
            for branch in self.report.branches
            if branch.branch_name == "r4-r2-r1"
        )
        result = next(
            field
            for field in via_r2.fields
            if field.config.endswith(
                "RoutingPolicy_R4_IN_FROM_R2__Seq10__Line2__"
                "set_localpreference_200"
            )
        )
        self.assertEqual(
            result.constraint,
            f"(> {result.config} 100) AND (<= {result.config} 4294967295)",
        )
        self.assertNotIn(f"(= {result.config} 200)", result.constraint)
        self.assertEqual(
            len(result.projection["released_route_attribute_bindings"]), 2
        )
        self.assertTrue(
            all(
                name.endswith("_localPref")
                for name in result.projection[
                    "released_route_attribute_bindings"
                ]
            )
        )

        seed = self.subspecifier._resolve_seed_path(
            {"candidate_id": via_r2.candidate_id, "seed_file": via_r2.seed_file}
        ).read_text(encoding="utf-8")
        self.assertIn("_current_best_localPref)", seed)
        self.assertIn("_selected_import_localPref)", seed)

    def test_selected_r1_local_preference_retains_tie_boundary(self) -> None:
        via_r1 = next(
            branch for branch in self.report.branches if branch.branch_name == "r4-r1"
        )
        result = next(
            field
            for field in via_r1.fields
            if field.config.endswith(
                "RoutingPolicy_R4_IN_FROM_R1__Seq10__Line2__"
                "set_localpreference_100"
            )
        )
        self.assertEqual(
            result.constraint,
            f"(>= {result.config} 50) AND (<= {result.config} 4294967295)",
        )

        via_r2 = next(
            branch
            for branch in self.report.branches
            if branch.branch_name == "r4-r2-r1"
        )
        upper_result = next(
            field
            for field in via_r2.fields
            if field.config.endswith(
                "RoutingPolicy_R4_IN_FROM_R1__Seq10__Line2__"
                "set_localpreference_100"
            )
        )
        self.assertEqual(
            upper_result.constraint,
            f"(>= {upper_result.config} 0) AND (< {upper_result.config} 200)",
        )

    def test_nontrivial_result_specializes_the_reference_simplified_line(self) -> None:
        branch = next(
            item for item in self.report.branches if item.branch_name == "r4-r2-r1"
        )
        result = next(
            field
            for field in branch.fields
            if field.config.endswith(
                "RoutingPolicy_R4_IN_FROM_R3__Seq10__Line2__"
                "set_localpreference_50"
            )
        )
        self.assertEqual(result.derivation, "symbolic-line-specialization")
        line = next(item for item in branch.lines if result.config in item.configs)
        self.assertEqual(line.derivation, "symbolic-reference-simplification")
        self.assertEqual(result.projection["source_line_group"], line.line_group)
        self.assertIn(f"(<= {result.config} 200)", result.constraint)

    def test_field_with_different_snapshot_release_is_solved_directly(self) -> None:
        branch = next(b for b in self.report.branches if b.branch_name == "r4-r2-r1")
        seed = self.subspecifier._resolve_seed_path(
            {"candidate_id": branch.candidate_id, "seed_file": branch.seed_file}
        )
        document = _SmtDocument.parse(seed.read_text())
        target = next((name, pins) for name, pins in _field_targets(document.config_pins)
                      if name.endswith("__length"))
        line_results = []
        for line in branch.lines:
            pins = tuple(pin for pin in document.config_pins if pin.name in line.configs)
            line_results.append(_branch_simplifier._ProjectedTarget(
                line.line_group, pins, line.constraint, line.derivation, 0.0, line.projection,
            ))
        batch = _branch_simplifier._TargetBatch(tuple(line_results), len(line_results), 0)
        original = _SmtDocument._target_dependent_route_snapshots

        def snapshots(doc, names):
            if target[0] in names and len(names) > 1:
                return frozenset({-1}), (), ()
            return original(doc, names)

        with patch.object(_branch_simplifier, "_field_targets", return_value=[target]), patch.object(
            _SmtDocument, "_target_dependent_route_snapshots", snapshots
        ):
            result = self.subspecifier._fields_from_lines(document, {
                "router": branch.router, "destination": branch.destination,
            }, "test", batch)
        self.assertIsNone(result.error)
        self.assertEqual(result.targets[0].projection["field_source"], "direct-field-fallback")
        expected = next(f.constraint for f in branch.fields if f.config == target[0])
        self.assertEqual(result.targets[0].constraint, expected)

    def test_releases_only_the_target_config_pin(self) -> None:
        branch = self.report.branches[-1]
        seed = self.subspecifier._resolve_seed_path(
            {
                "candidate_id": branch.candidate_id,
                "seed_file": branch.seed_file,
            }
        )
        document = _SmtDocument.parse(seed.read_text(encoding="utf-8"))
        target = document.config_pins[0]
        retained = document.config_pins[1]
        query = document.metadata_source(target)

        self.assertNotIn(
            f"\n(assert (= {target.name} {target.original_value}))", query
        )
        self.assertIn(
            f"; (assert (= {target.name} {target.original_value}))", query
        )
        self.assertIn(
            f"(assert (= {retained.name} {retained.original_value}))", query
        )
        self.assertIn("_selection_guard", seed.read_text(encoding="utf-8"))
        self.assertNotIn("(check-sat)", query)
        self.assertNotIn("(apply", query)

    def test_line_level_releases_the_complete_line_only(self) -> None:
        branch = self.report.branches[-1]
        seed = self.subspecifier._resolve_seed_path(
            {
                "candidate_id": branch.candidate_id,
                "seed_file": branch.seed_file,
            }
        )
        document = _SmtDocument.parse(seed.read_text(encoding="utf-8"))
        groups = dict(_group_config_pins(document.config_pins))
        line_name = "Config_r4_RouteFilterList_pl__Line1"
        targets = groups[line_name]
        retained = next(
            pin for pin in document.config_pins if pin not in targets
        )
        query = document.metadata_source(targets)

        self.assertEqual(len(targets), 7)
        for target in targets:
            self.assertNotIn(
                f"\n(assert (= {target.name} {target.original_value}))", query
            )
            self.assertIn(
                f"; (assert (= {target.name} {target.original_value}))", query
            )
        self.assertIn(
            f"(assert (= {retained.name} {retained.original_value}))", query
        )

    def test_ip_and_mask_are_released_as_original_field_pair(self) -> None:
        branch = self.report.branches[-1]
        seed = self.subspecifier._resolve_seed_path(
            {
                "candidate_id": branch.candidate_id,
                "seed_file": branch.seed_file,
            }
        )
        document = _SmtDocument.parse(seed.read_text(encoding="utf-8"))
        field_name, targets = next(
            target
            for target in _field_targets(document.config_pins)
            if target[0].endswith("__ip")
        )
        query = document.metadata_source(targets)

        self.assertEqual(len(targets), 2)
        self.assertTrue(field_name.endswith("__ip"))
        self.assertTrue(targets[1].name.endswith("__mask"))
        for target in targets:
            self.assertNotIn(
                f"\n(assert (= {target.name} {target.original_value}))", query
            )

        result = next(
            field
            for field in branch.fields
            if field.config.endswith("__ip")
        )
        self.assertEqual(len(result.released_configs), 2)
        self.assertLess(len(result.constraint), 500)
        self.assertNotIn("FAILED-EDGE", result.constraint)

    def test_writes_only_compact_and_structured_reports(self) -> None:
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"branch_subspecs.txt", "branch_subspecs.json", "r1", "r2", "r3", "r4"},
        )
        for router in ("r1", "r2", "r3", "r4"):
            router_directory = self.output / router
            self.assertEqual(
                {path.name for path in router_directory.iterdir()},
                {
                    "branch_subspecs.json",
                    "field_level_subspecs.txt",
                    "line_level_subspecs.txt",
                },
            )
        structured = json.loads(
            (self.output / "branch_subspecs.json").read_text(encoding="utf-8")
        )
        self.assertEqual(structured["schema_name"], "tolerance-symbolic-branch-subspec-report")
        self.assertEqual(structured["schema_version"], 5)
        self.assertEqual(
            set(structured),
            {
                "schema_name",
                "schema_version",
                "status",
                "generated_at",
                "source_consistency_report",
                "scope",
                "branch_count",
                "field_evaluations",
                "constrained_field_evaluations",
                "line_evaluations",
                "constrained_line_evaluations",
                "branches",
                "branch_provenance",
                "constraint_provenance",
                "errors",
            },
        )
        def all_keys(value: object) -> set[str]:
            if isinstance(value, dict):
                return set(value).union(
                    *(all_keys(item) for item in value.values())
                )
            if isinstance(value, list):
                return set().union(*(all_keys(item) for item in value))
            return set()

        keys = all_keys(structured)
        for forbidden in (
            "aggregate",
            "validated_failure_scenarios",
            "scenario_count",
            "scenarios",
            "released_seed_bindings",
            "exact-scenario-projection",
        ):
            self.assertNotIn(forbidden, keys)

        field_text = (self.output / "r4" / "field_level_subspecs.txt").read_text(
            encoding="utf-8"
        )
        self.assertTrue(field_text.startswith("Field-Level Subspecs\n"))
        self.assertIn("Config Variable:", field_text)
        self.assertIn("Subspecs (2):", field_text)
        self.assertIn("[from r4-r1]", field_text)
        self.assertIn("[from r4-r2-r1]", field_text)
        loaded_fields = load_field_level_subspecs_from_file(
            self.output / "r4" / "field_level_subspecs.txt"
        )
        self.assertEqual(len(loaded_fields), 19)
        self.assertTrue(
            all(1 <= len(values) <= 2 for values in loaded_fields.values())
        )
        self.assertFalse(any(name.endswith("__mask") for name in loaded_fields))

        line_text = (self.output / "r4" / "line_level_subspecs.txt").read_text(
            encoding="utf-8"
        )
        self.assertTrue(line_text.startswith("Line-Level Subspecs\n"))
        self.assertIn(
            "Line Group: Config_r4_RouteFilterList_pl__Line1", line_text
        )
        self.assertIn("Subspecs (2):", line_text)
        loaded_lines = load_line_level_subspecs_from_file(
            self.output / "r4" / "line_level_subspecs.txt"
        )
        self.assertEqual(len(loaded_lines), 9)
        self.assertTrue(all(len(values) <= 2 for values in loaded_lines.values()))

    def test_constraint_provenance_resolves_to_exact_symbolic_scenario_sets(self) -> None:
        structured = json.loads(
            (self.output / "branch_subspecs.json").read_text(encoding="utf-8")
        )
        provenance = {
            item["provenance_id"]: item
            for item in structured["branch_provenance"]
        }
        self.assertEqual(len(provenance), 7)
        for item in provenance.values():
            scenario = item["scenario_set"]
            self.assertEqual(scenario["representation"], "symbolic-guard")
            self.assertFalse(scenario["enumerated"])
            self.assertEqual(scenario["failure_budget"]["semantics"], "at-most")
            self.assertEqual(scenario["failure_budget"]["k"], 1)
            self.assertTrue(
                scenario["encoded_guard_assertion"].endswith("_selection_guard")
            )
            self.assertTrue(
                scenario["failure_budget"]["assertion"].endswith(
                    "_at_most_1_failures"
                )
            )
            self.assertTrue(
                scenario["encoded_guard"] == "true"
                or "LINK-UP-" in scenario["encoded_guard"]
            )
            self.assertIn("LINK-UP-", scenario["failure_budget"]["expression"])
            self.assertTrue(scenario["failure_variables"])
            self.assertRegex(item["seed_sha256"], r"^[0-9a-f]{64}$")

        constraints = structured["constraint_provenance"]
        self.assertTrue(constraints)
        for constraint in constraints:
            self.assertTrue(constraint["provenance_ids"])
            self.assertEqual(
                constraint["provenance_ids"],
                [item["provenance_id"] for item in constraint["derivations"]],
            )
            self.assertTrue(
                all(item in provenance for item in constraint["provenance_ids"])
            )

    def test_debug_consistency_report_cannot_open_stage3_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = json.loads(
                self.subspecifier.report_path.read_text(encoding="utf-8")
            )
            report["scope"]["mode"] = "debug-filtered"
            path = Path(directory) / "consistency_report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            original = self.subspecifier.report_path
            self.subspecifier.report_path = path
            try:
                with self.assertRaisesRegex(
                    SubspecificationError, "unfiltered global consistency check"
                ):
                    self.subspecifier._load_and_validate_consistency_report()
            finally:
                self.subspecifier.report_path = original


if __name__ == "__main__":
    unittest.main()
