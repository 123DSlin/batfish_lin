import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from consistency import ConsistencyChecker, SmtSymbolTable


REPOSITORY = Path(__file__).resolve().parents[1]
WORK_DIRECTORY = REPOSITORY / "tests" / "fixtures" / "symbolic_output_0010"


def _load_slicer_module():
    path = REPOSITORY / "1_smt_slicer.py"
    spec = importlib.util.spec_from_file_location("symbolic_smt_slicer", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SLICER = _load_slicer_module()


class SymbolicSmtSlicerTest(unittest.TestCase):
    def _copy_inputs(self, destination: Path) -> None:
        # 0_properties_variables.txt is deliberately absent: symbolic Stage 1
        # derives its scope from the structured RIB and k, not reachable_r4.
        for filename in (
            "smt_encoding.smt2",
            "symbolic_route.json",
            "0_hostnames.txt",
            "0_dst_ips.txt",
            "0_ebgp_neighbors.txt",
            "0_interfaces.txt",
            "0_overall_history_enum.txt",
            "0_communities_index.txt",
            "0_model_igp.txt",
        ):
            shutil.copy2(WORK_DIRECTORY / filename, destination / filename)

    def test_requirements_are_derived_from_all_k_feasible_device_branches(self) -> None:
        declarations, _ = SLICER.load_normalized_encoding(
            WORK_DIRECTORY / "smt_encoding.smt2"
        )
        requirements = SLICER.build_symbolic_device_requirements(
            WORK_DIRECTORY, declarations, k=1
        )

        self.assertEqual(
            set(requirements.required_by_router), {"r1", "r2", "r3", "r4"}
        )
        r4 = requirements.required_by_router["r4"]
        self.assertIn("|0_r4_OVERALL_BEST_None_permitted|", r4)
        self.assertIn("|0_r4_BGP_IMPORT_Ethernet42_localPref|", r4)
        self.assertIn("|0_r2_OVERALL_BEST_None_permitted|", r4)
        self.assertIn("|0_CONTROL-FORWARDING_r4_Ethernet42|", r4)
        self.assertFalse(any("reachable" in symbol for symbol in r4))

        local_r4 = requirements.local_roots_by_router["r4"]
        self.assertIn("|0_r4_OVERALL_BEST_None_permitted|", local_r4)
        self.assertNotIn("|0_r2_OVERALL_BEST_None_permitted|", local_r4)

    def test_device_semantic_scope_is_topology_driven_and_keeps_peer_boundaries(self) -> None:
        declarations, _ = SLICER.load_normalized_encoding(
            WORK_DIRECTORY / "smt_encoding.smt2"
        )
        scopes = SLICER.build_device_semantic_scopes(WORK_DIRECTORY, declarations)

        r4 = scopes["r4"]
        self.assertEqual(r4.peers, ("r1", "r2", "r3"))
        self.assertIn("|0_r1_OVERALL_BEST_None_permitted|", r4.peer_boundary_symbols)
        self.assertIn("|0_r2_OVERALL_BEST_None_permitted|", r4.peer_boundary_symbols)
        self.assertIn("|0_r3_OVERALL_BEST_None_permitted|", r4.peer_boundary_symbols)
        self.assertIn("|0_r1_BGP_EXPORT_Ethernet14_permitted|", r4.incoming_export_symbols)
        self.assertIn("|0_r2_BGP_EXPORT_Ethernet24_permitted|", r4.incoming_export_symbols)
        self.assertIn("|0_r3_BGP_EXPORT_Ethernet34_permitted|", r4.incoming_export_symbols)
        self.assertIn("|0_r4_BGP_IMPORT_Ethernet42_permitted|", r4.local_symbols)
        self.assertIn("|0_r4_OVERALL_BEST_None_permitted|", r4.local_symbols)
        self.assertIn("|0_CONTROL-FORWARDING_r4_Ethernet42|", r4.local_symbols)

    def test_direct_device_slices_cover_requirements_and_form_audit_union(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            self._copy_inputs(work)
            declarations, assertions = SLICER.load_normalized_encoding(
                work / "smt_encoding.smt2"
            )
            requirements = SLICER.build_symbolic_device_requirements(
                work, declarations, k=1
            )
            semantic_scopes = SLICER.build_device_semantic_scopes(work, declarations)
            SLICER.perform_device_slicing(
                str(work), [*declarations, *assertions], semantic_scopes, requirements
            )

            output = work / "1_sliced_device_smt_encoding"
            union_lines: set[str] = set()
            for router in ("r1", "r2", "r3", "r4"):
                device = output / f"sliced_{router}_smt_encoding.smt2"
                text = device.read_text(encoding="utf-8")
                symbols = SmtSymbolTable.from_text(text)
                self.assertTrue(
                    requirements.required_by_router[router].issubset(
                        symbols.declarations
                    )
                )
                self.assertNotIn("reachable_", text)
                union_lines.update(
                    line
                    for line in text.splitlines()
                    if line.startswith("(declare-fun") or line.startswith("(assert")
                )

            audit = output / "sliced_smt_encoding.smt2"
            audit_lines = {
                line
                for line in audit.read_text(encoding="utf-8").splitlines()
                if line.startswith("(declare-fun") or line.startswith("(assert")
            }
            self.assertEqual(audit_lines, union_lines)

    def test_branch_contract_audit_does_not_enlarge_device_slice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            self._copy_inputs(work)
            declarations, assertions = SLICER.load_normalized_encoding(
                work / "smt_encoding.smt2"
            )
            expressions = [*declarations, *assertions]
            scopes = SLICER.build_device_semantic_scopes(work, declarations)
            requirements = SLICER.build_symbolic_device_requirements(
                work, declarations, k=1
            )

            audited_dir = work / "audited"
            audited = SLICER.SmtSlicer(
                routers=sorted(scopes),
                output_dir=str(audited_dir),
                semantic_scopes=scopes,
                required_symbols=requirements.required_by_router,
                local_roots=requirements.local_roots_by_router,
            )
            audited.slice_from_expressions(expressions)

            unaudited_dir = work / "unaudited"
            unaudited = SLICER.SmtSlicer(
                routers=sorted(scopes),
                output_dir=str(unaudited_dir),
                semantic_scopes=scopes,
            )
            unaudited.slice_from_expressions(expressions)

            for router in sorted(scopes):
                self.assertEqual(
                    (audited_dir / f"sliced_{router}_smt_encoding.smt2").read_text(),
                    (unaudited_dir / f"sliced_{router}_smt_encoding.smt2").read_text(),
                )

    def test_generated_slices_pass_the_formal_consistency_gate(self) -> None:
        z3 = shutil.which("z3")
        if z3 is None:
            self.skipTest("Z3 executable is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            self._copy_inputs(work)
            declarations, assertions = SLICER.load_normalized_encoding(
                work / "smt_encoding.smt2"
            )
            requirements = SLICER.build_symbolic_device_requirements(
                work, declarations, k=1
            )
            semantic_scopes = SLICER.build_device_semantic_scopes(work, declarations)
            SLICER.perform_device_slicing(
                str(work), [*declarations, *assertions], semantic_scopes, requirements
            )
            report = ConsistencyChecker(work, z3_path=Path(z3)).run(k=1)
            self.assertEqual(report.status, "PASS")
            self.assertEqual(report.sat_branches, 7)


if __name__ == "__main__":
    unittest.main()
