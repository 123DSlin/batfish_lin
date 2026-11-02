import hashlib
from importlib import import_module
import json
from pathlib import Path
import tempfile
import unittest

_branch_intersection = import_module("4_branch_intersection")
IntersectionError = _branch_intersection.IntersectionError
IntersectionReport = _branch_intersection.IntersectionReport
SymbolicIntersection = _branch_intersection.SymbolicIntersection
from utils.util_file import (
    load_field_level_subspecs_from_file,
    load_line_level_subspecs_from_file,
)


REPOSITORY = Path(__file__).resolve().parents[1]
WORK_DIRECTORY = REPOSITORY / "symbolic_output_0010"


class SymbolicIntersectionIntegrationTest(unittest.TestCase):
    temporary: tempfile.TemporaryDirectory[str]
    output: Path
    engine: SymbolicIntersection
    report: IntersectionReport

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / "stage4"
        cls.engine = SymbolicIntersection(WORK_DIRECTORY)
        cls.report = cls.engine.run(output_directory=cls.output)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _local_preference(self, neighbor: str):
        return next(
            item
            for item in self.report.fields
            if f"R4_IN_FROM_{neighbor}" in item.target
            and "set_localpreference" in item.target
        )

    def test_intersects_every_branch_target(self) -> None:
        self.assertEqual(self.report.status, "PASS")
        self.assertEqual(self.report.branch_count, 7)
        self.assertEqual(len(self.report.fields), 19)
        self.assertEqual(len(self.report.lines), 9)
        self.assertTrue(
            all(item.equivalence_check == "UNSAT" for item in self.report.fields)
        )
        self.assertTrue(
            all(item.equivalence_check == "UNSAT" for item in self.report.lines)
        )

    def test_final_local_preference_intervals_are_exact_and_readable(self) -> None:
        r1 = self._local_preference("R1")
        r2 = self._local_preference("R2")
        r3 = self._local_preference("R3")
        self.assertEqual(
            r1.constraint,
            f"(>= {r1.target} 50) AND (< {r1.target} 200)",
        )
        self.assertEqual(
            r2.constraint,
            f"(> {r2.target} 100) AND (<= {r2.target} 4294967295)",
        )
        self.assertEqual(
            r3.constraint,
            f"(>= {r3.target} 0) AND (<= {r3.target} 100)",
        )

    def test_final_atoms_retain_exact_branch_sources(self) -> None:
        r1 = self._local_preference("R1")
        provenance = {
            item["formula"]: [source["branch_name"] for source in item["sources"]]
            for item in r1.constraint_provenance
        }
        self.assertEqual(provenance[f"(>= {r1.target} 50)"], ["r4-r1"])
        self.assertEqual(provenance[f"(< {r1.target} 200)"], ["r4-r2-r1"])
        self.assertEqual(
            {source.branch_name for source in r1.sources},
            {"r4-r1", "r4-r2-r1"},
        )

    def test_writes_one_final_formula_per_target(self) -> None:
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {
                "final_subspecs.json",
                "final_subspecs.txt",
                "r1",
                "r2",
                "r3",
                "r4",
            },
        )
        r1_fields = load_field_level_subspecs_from_file(
            self.output / "r1" / "field_level_subspecs.txt"
        )
        r2_fields = load_field_level_subspecs_from_file(
            self.output / "r2" / "field_level_subspecs.txt"
        )
        r3_fields = load_field_level_subspecs_from_file(
            self.output / "r3" / "field_level_subspecs.txt"
        )
        r4_fields = load_field_level_subspecs_from_file(
            self.output / "r4" / "field_level_subspecs.txt"
        )
        r4_lines = load_line_level_subspecs_from_file(
            self.output / "r4" / "line_level_subspecs.txt"
        )
        self.assertEqual(len(r1_fields), 7)
        self.assertEqual(len(r2_fields), 0)
        self.assertEqual(len(r3_fields), 0)
        self.assertEqual(len(r4_fields), 12)
        self.assertEqual(len(r4_lines), 7)
        self.assertTrue(all(name.startswith("Config_r1_") for name in r1_fields))
        self.assertTrue(all(name.startswith("Config_r4_") for name in r4_fields))
        self.assertTrue(all(len(values) == 1 for values in r4_fields.values()))
        unrestricted_lines = {
            item.target
            for item in self.report.lines
            if item.router == "r4" and item.unrestricted
        }
        self.assertTrue(
            all(
                len(values) == (0 if target in unrestricted_lines else 1)
                for target, values in r4_lines.items()
            )
        )
        summary = (self.output / "final_subspecs.txt").read_text(encoding="utf-8")
        self.assertIn("r1: fields 7", summary)
        self.assertIn("r2: fields 0", summary)
        self.assertIn("r3: fields 0", summary)

    def test_results_use_config_owner_and_retain_verification_router(self) -> None:
        r1 = [item for item in self.report.fields if item.router == "r1"]
        self.assertTrue(r1)
        self.assertTrue(all(item.config_owner == "r1" for item in r1))
        self.assertTrue(all(item.target.startswith("Config_r1_") for item in r1))
        self.assertEqual(
            {source.router for item in r1 for source in item.sources},
            {"r2", "r3", "r4"},
        )

    def test_structured_report_is_bound_to_stage3_and_seed_hashes(self) -> None:
        source = WORK_DIRECTORY / "3_branch_subspecs" / "branch_subspecs.json"
        payload = json.loads(
            (self.output / "final_subspecs.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            payload["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest()
        )
        self.assertEqual(
            payload["intersection_semantics"],
            "conjunction-across-symbolic-branches-per-config-owner",
        )
        self.assertEqual(len(payload["branch_provenance"]), 7)

        source_report = json.loads(source.read_text(encoding="utf-8"))
        changed = dict(source_report["branches"][-1])
        changed["seed_sha256"] = "0" * 64
        fresh = SymbolicIntersection(WORK_DIRECTORY)
        with self.assertRaisesRegex(IntersectionError, "seed changed after stage 3"):
            fresh._document_for(changed)


if __name__ == "__main__":
    unittest.main()
