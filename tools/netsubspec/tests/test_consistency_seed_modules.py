from dataclasses import replace
from pathlib import Path
import re
import shutil
import tempfile
from types import MappingProxyType
import unittest
from unittest import mock

from consistency import (
    ConsistencyChecker,
    GuardEncoder,
    SeedBuilder,
    SeedBuildError,
    SmtSymbolTable,
    SymbolicRib,
    SymbolicRouteFormatError,
)


REPOSITORY = Path(__file__).resolve().parents[1]
WORK_DIRECTORY = REPOSITORY / "tests" / "fixtures" / "symbolic_output_0010"


class GuardEncoderTest(unittest.TestCase):
    rib: SymbolicRib
    encoder: GuardEncoder

    @classmethod
    def setUpClass(cls) -> None:
        cls.rib = SymbolicRib.from_work_directory(WORK_DIRECTORY)
        cls.encoder = GuardEncoder(cls.rib.guard_variables)

    def test_exact_at_most_k_feasibility(self) -> None:
        entries = self.rib.entries(
            router="r4", prefix="10.0.0.0/24", plane="MAIN"
        )
        feasibility = {
            entry.selected_peer: self.encoder.is_feasible_within_k(entry.guard_ast, 1)
            for entry in entries
        }
        self.assertEqual(feasibility, {"r1": True, "r2": True, "r3": False})

    def test_guard_uses_structured_ast(self) -> None:
        via_r2 = next(
            entry
            for entry in self.rib.entries(
                router="r4", prefix="10.0.0.0/24", plane="MAIN"
            )
            if entry.selected_peer == "r2"
        )
        encoded = self.encoder.encode(via_r2.selection_guard)
        self.assertEqual(
            encoded,
            "(and true |LINK-UP-r1_r2| |LINK-UP-r2_r4|)",
        )

    def test_failure_budget_counts_down_links(self) -> None:
        expression = self.encoder.at_most_k_expression(1)
        self.assertEqual(expression.count("(ite (not |LINK-UP-"), 5)
        self.assertTrue(expression.endswith(" 1)"))

    def test_enumerates_every_guarded_failure_assignment(self) -> None:
        via_r2 = next(
            entry
            for entry in self.rib.entries(
                router="r4", prefix="10.0.0.0/24", plane="MAIN"
            )
            if entry.selected_peer == "r2"
        )
        assignments = self.encoder.satisfying_failure_assignments(
            via_r2.selection_guard, 1
        )
        self.assertEqual(
            assignments,
            (
                frozenset(),
                frozenset({"r1_r3"}),
                frozenset({"r1_r4"}),
                frozenset({"r3_r4"}),
            ),
        )

    def test_concrete_assignment_respects_guard_variable_polarity(self) -> None:
        expressions = self.encoder.concrete_assignment_expressions({"r1_r2"})
        self.assertIn("(= |LINK-UP-r1_r2| false)", expressions)
        self.assertIn("(= |LINK-UP-r1_r3| true)", expressions)


class BranchLoaderTest(unittest.TestCase):
    rib: SymbolicRib

    @classmethod
    def setUpClass(cls) -> None:
        cls.rib = SymbolicRib.from_work_directory(WORK_DIRECTORY)

    def test_loads_complete_structured_export(self) -> None:
        self.assertEqual(len(self.rib.guard_variables), 5)
        self.assertEqual(len(self.rib.entries_all), 41)

    def test_context_keeps_complete_device_rib_and_predecessor(self) -> None:
        contexts = self.rib.branch_contexts(
            router="r4", prefix="10.0.0.0/24", k=1
        )
        self.assertEqual(len(contexts), 2)
        for context in contexts:
            self.assertEqual(len(context.device_rib), 3)
            self.assertEqual(len(context.predecessor_entries), 1)
            self.assertEqual(set(context.peer_ribs), {"r1", "r2", "r3"})

    def test_neighbor_interface_mapping(self) -> None:
        link = self.rib.topology.resolve_unique("r4", "r2")
        self.assertEqual(link.local.interface, "Ethernet42")
        self.assertEqual(link.remote.interface, "Ethernet24")

    def test_property_destination_matches_non_local_covering_prefix(self) -> None:
        entries = self.rib.forwarding_entries(
            router="r4",
            vrf="default",
            destination="192.0.14.2",
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].prefix, "192.0.14.0/30")
        self.assertEqual(entries[0].protocol, "CONNECTED")

    def test_property_destination_retains_selected_fallback_prefixes(self) -> None:
        primary = next(
            entry
            for entry in self.rib.entries(
                router="r4", prefix="10.0.0.0/24", plane="MAIN"
            )
            if entry.selected_peer == "r1"
        )
        fallback_guard = MappingProxyType(
            {
                "ast": {
                    "operator": "NOT",
                    "children": [
                        {"operator": "VARIABLE", "variableId": "r1_r4"}
                    ],
                },
                "simplified": "(not r1_r4)",
            }
        )
        fallback = replace(
            primary,
            candidate_id="candidate-test-fallback-prefix",
            prefix="10.0.0.0/16",
            selection_guard=fallback_guard,
            availability_guard=fallback_guard,
        )
        rib = SymbolicRib(
            self.rib.guard_variables,
            (primary, fallback),
            topology=self.rib.topology,
        )

        entries = rib.forwarding_entries(
            router="r4", vrf="default", destination="10.0.0.1"
        )
        self.assertEqual(
            {entry.prefix for entry in entries},
            {"10.0.0.0/24", "10.0.0.0/16"},
        )

        contexts = rib.forwarding_branch_contexts(
            router="r4", vrf="default", destination="10.0.0.1", k=1
        )
        self.assertEqual(len(contexts), 2)
        for context in contexts:
            self.assertEqual(
                {entry.prefix for entry in context.device_rib},
                {"10.0.0.0/24", "10.0.0.0/16"},
            )

    def test_property_context_keeps_all_covering_peer_prefixes(self) -> None:
        current = next(
            entry
            for entry in self.rib.entries(
                router="r4", prefix="10.0.0.0/24", plane="MAIN"
            )
            if entry.selected_peer == "r2"
        )
        peer_primary = self.rib.entries(
            router="r1", prefix="10.0.0.0/24", plane="MAIN"
        )[0]
        peer_fallback = replace(
            peer_primary,
            candidate_id="candidate-test-peer-fallback-prefix",
            prefix="10.0.0.0/16",
        )
        rib = SymbolicRib(
            self.rib.guard_variables,
            (current, peer_primary, peer_fallback),
            topology=self.rib.topology,
        )

        context = rib.context(current, destination="10.0.0.1")
        self.assertEqual(
            {entry.prefix for entry in context.peer_ribs["r1"]},
            {"10.0.0.0/24", "10.0.0.0/16"},
        )

    def test_local_connected_origin_is_proven_by_route_and_interface_data(self) -> None:
        loopback = self.rib.entries(
            router="r1", prefix="10.0.0.0/24", plane="MAIN"
        )[0]
        self.assertEqual(
            self.rib.local_connected_origin_interface(loopback), "Loopback0"
        )

        physical = self.rib.entries(
            router="r1", prefix="192.0.12.0/30", plane="MAIN"
        )[0]
        self.assertEqual(
            self.rib.local_connected_origin_interface(physical), "Ethernet12"
        )
        self.assertEqual(physical.selection_guard.get("simplified"), "r1_r2")

    def test_local_connected_adapter_fails_closed_for_unknown_interface(self) -> None:
        loopback = self.rib.entries(
            router="r1", prefix="10.0.0.0/24", plane="MAIN"
        )[0]
        attributes = dict(loopback.attributes)
        attributes["nextHopInterface"] = "NotInInventory"
        malformed = replace(loopback, attributes=MappingProxyType(attributes))
        with self.assertRaises(SymbolicRouteFormatError):
            self.rib.local_connected_origin_interface(malformed)


class RouteBinderAndSeedBuilderTest(unittest.TestCase):
    rib: SymbolicRib
    device_smt: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.rib = SymbolicRib.from_work_directory(WORK_DIRECTORY)
        cls.device_smt = (
            WORK_DIRECTORY
            / "1_sliced_device_smt_encoding"
            / "sliced_r4_smt_encoding.smt2"
        )

    def test_symbol_table_reads_control_forwarding(self) -> None:
        symbols = SmtSymbolTable.from_text(self.device_smt.read_text(encoding="utf-8"))
        pattern = re.compile(r"\|0_CONTROL-FORWARDING_r4_[^|]+\|")
        self.assertEqual(len(symbols.symbols_matching(pattern)), 3)

    def test_builds_runnable_seed_for_each_k_pruned_r4_branch(self) -> None:
        builder = SeedBuilder(self.rib)
        contexts = self.rib.branch_contexts(
            router="r4", prefix="10.0.0.0/24", k=1
        )
        for context in contexts:
            artifact = builder.build(
                context,
                self.device_smt,
                k=1,
                destination="10.0.0.1",
            )
            self.assertFalse(
                artifact.diagnostics,
                [f"{item.code}: {item.message}" for item in artifact.diagnostics],
            )
            self.assertTrue(artifact.text.endswith("(check-sat)\n"))
            self.assertEqual(artifact.text.count("(check-sat)"), 1)
            self.assertEqual(
                artifact.text.count(":named branch_"), len(artifact.constraints)
            )
            self.assertIn("; ---- Declarations ----", artifact.text)
            self.assertIn("; ---- Assertions ----", artifact.text)
            self.assertIn(
                "; ---- Symbolic Route Consistency Seed ----", artifact.text
            )
            self.assertIn("; Property destination: 10.0.0.1", artifact.text)
            self.assertIn("; Selected route prefix: 10.0.0.0/24", artifact.text)
            self.assertIn("; Seed1: Selected symbolic-route branch guard", artifact.text)
            self.assertIn("; Seed2: At-most-k link-failure budget", artifact.text)
            self.assertIn("; Seed3: Link-state bridge", artifact.text)
            self.assertIn("; Seed4: Current selected route", artifact.text)
            self.assertIn("; Seed5: Selected import route", artifact.text)
            self.assertIn("; Seed6: Selected peer predecessor route", artifact.text)
            self.assertIn("; Seed7: Remaining peer candidate routes", artifact.text)
            self.assertIn("; Seed8: Selected-peer link state", artifact.text)
            self.assertIn("; Seed9: Device control-forwarding state", artifact.text)
            assertions_marker = artifact.text.index("; ---- Assertions ----")
            consistency_marker = artifact.text.index(
                "; ---- Symbolic Route Consistency Seed ----"
            )
            for declaration in builder.guard_encoder.declarations():
                declaration_index = artifact.text.index(declaration)
                self.assertLess(declaration_index, assertions_marker)
                self.assertLess(declaration_index, consistency_marker)
            self.assertNotIn(
                "\n(assert (= |0_FAILED-EDGE_r1_r4| 0))\n", artifact.text
            )
            source_config_pins = {
                line
                for line in self.device_smt.read_text(encoding="utf-8").splitlines()
                if line.startswith("(assert (= Config_")
            }
            self.assertTrue(source_config_pins)
            self.assertTrue(
                source_config_pins.issubset(set(artifact.text.splitlines()))
            )
            for interface in ("Ethernet41", "Ethernet42", "Ethernet43"):
                self.assertRegex(
                    artifact.text,
                    rf"\(= \|0_CONTROL-FORWARDING_r4_{interface}\| .*\)",
                )
            # Peer CF variables occur in r4's import equations. Bind each one
            # to the guards of the peer routes whose selected next hop is r4;
            # a final peer selection branch must not be deleted to approximate
            # the immediate return-loop state.
            for router, interface in (
                ("r1", "Ethernet14"),
                ("r2", "Ethernet24"),
                ("r3", "Ethernet34"),
            ):
                self.assertRegex(
                    artifact.text,
                    rf"\(= \|0_CONTROL-FORWARDING_{router}_{interface}\| .*\)",
                )

            # The selected peer predecessor and the remaining peer candidates
            # carry route attributes needed by Minesweeper's export equations.
            self.assertRegex(
                artifact.text,
                r"selected_peer_.*_predecessor_candidate_0_metric",
            )
            self.assertRegex(
                artifact.text,
                r"remaining_peer_.*_candidate_0_metric",
            )
            self.assertIn("_selected_peer_link_up", artifact.text)

            if context.current_entry.selected_peer == "r2":
                # r3 has three final MAIN selection branches in the fixture:
                # one via r1 and two whose selected next hop is r4. All three
                # remain in r3's true OVERALL_BEST boundary binding.
                self.assertEqual(
                    artifact.text.count("remaining_peer_r3_candidate_0_metric"),
                    1,
                )
                self.assertEqual(
                    artifact.text.count("remaining_peer_r3_candidate_1_metric"),
                    1,
                )
                self.assertEqual(
                    artifact.text.count("remaining_peer_r3_candidate_2_metric"),
                    1,
                )

            if context.current_entry.selected_peer == "r1":
                self.assertIn(
                    "selected_peer_r1_predecessor_candidate_0_history",
                    artifact.text,
                )

    def test_local_connected_origin_is_normalized_then_formally_bound(self) -> None:
        entry = self.rib.entries(
            router="r1", prefix="10.0.0.0/24", plane="MAIN"
        )[0]
        device_smt = (
            WORK_DIRECTORY
            / "1_sliced_device_smt_encoding"
            / "sliced_r1_smt_encoding.smt2"
        )
        artifact = SeedBuilder(self.rib).build(
            self.rib.context(entry),
            device_smt,
            k=1,
            destination="10.0.0.0/24",
        )

        self.assertEqual(
            [item.code for item in artifact.diagnostics],
            ["NORMALIZED_LOCAL_CONNECTED_ORIGIN"],
        )
        self.assertNotIn(
            "(assert (not |0_r1_CONNECTED_BEST_None_permitted|))",
            artifact.text,
        )
        self.assertIn(
            "(= |0_r1_CONNECTED_BEST_None_permitted| true)", artifact.text
        )
        self.assertIn(
            "(= |0_r1_CONNECTED_BEST_None_prefixLength| 24)", artifact.text
        )
        self.assertIn(
            "; Adapter: removed the incompatible CONNECTED_BEST=false assertion "
            "for proven local origin r1:Loopback0",
            artifact.text,
        )
        source_config_pins = {
            line
            for line in device_smt.read_text(encoding="utf-8").splitlines()
            if line.startswith("(assert (= Config_")
        }
        self.assertTrue(source_config_pins.issubset(set(artifact.text.splitlines())))

    def test_missing_predecessor_record_fails_closed(self) -> None:
        context = next(
            item
            for item in self.rib.branch_contexts(
                router="r4", prefix="10.0.0.0/24", k=1
            )
            if item.current_entry.selected_peer == "r1"
        )
        source = self.device_smt.read_text(encoding="utf-8")
        malformed = "\n".join(
            line
            for line in source.splitlines()
            if not line.startswith("(declare-fun |0_r1_OVERALL_BEST_None_")
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "missing_predecessor_record.smt2"
            path.write_text(malformed, encoding="utf-8")
            with self.assertRaisesRegex(
                SeedBuildError, "PEER_BEST_NOT_IN_SLICE"
            ):
                SeedBuilder(self.rib).build(
                    context,
                    path,
                    k=1,
                    destination="10.0.0.0/24",
                )

    def test_only_symbolic_inter_router_failure_pins_are_released(self) -> None:
        entry = self.rib.entries(
            router="r4", prefix="10.0.0.0/24", plane="MAIN"
        )[0]
        source = "\n".join(
            [
                "(assert (= |0_FAILED-EDGE_r1_r2| 0))",
                "(assert (= |0_FAILED-EDGE_r1_Loopback0| 0))",
            ]
        )
        prepared, diagnostics = SeedBuilder(self.rib)._prepare_device_encoding(
            source, entry
        )
        self.assertFalse(diagnostics)
        self.assertNotIn("FAILED-EDGE_r1_r2", prepared)
        self.assertIn("FAILED-EDGE_r1_Loopback0", prepared)


class FormalConsistencyCheckerTest(unittest.TestCase):
    z3: Path

    @classmethod
    def setUpClass(cls) -> None:
        discovered = shutil.which("z3")
        fallback = Path("/opt/homebrew/bin/z3")
        cls.z3 = Path(discovered) if discovered else fallback
        if not cls.z3.is_file():
            raise unittest.SkipTest("Z3 executable is unavailable")

    def test_global_scope_discovers_all_devices_and_property_prefixes(self) -> None:
        checker = ConsistencyChecker(WORK_DIRECTORY, z3_path=self.z3)
        with tempfile.TemporaryDirectory() as temporary:
            report = checker.run(k=1, output_directory=temporary)
            self.assertEqual(report.scope.mode, "global")
            self.assertEqual(report.scope.routers, ("r1", "r2", "r3", "r4"))
            self.assertEqual(report.scope.destinations, ("10.0.0.0/24",))
            self.assertEqual(report.status, "PASS")
            self.assertEqual(len(report.scope_results), 4)
            self.assertEqual(report.total_scope_branches, 10)
            self.assertEqual(report.eligible_branches, 7)
            self.assertEqual(report.checked_branches, 7)
            self.assertEqual(report.sat_branches, 7)
            self.assertEqual(report.unsat_branches, 0)
            self.assertEqual(
                {item.router: item.status for item in report.scope_results},
                {"r1": "PASS", "r2": "PASS", "r3": "PASS", "r4": "PASS"},
            )
            seed_directory = Path(temporary) / "seeds"
            router_directories = sorted(
                path.name for path in seed_directory.iterdir() if path.is_dir()
            )
            self.assertEqual(router_directories, ["r1", "r2", "r3", "r4"])
            seed_files = sorted(seed_directory.glob("*/*.smt2"))
            self.assertEqual(len(seed_files), 7)
            self.assertEqual(
                {str(path.relative_to(seed_directory)) for path in seed_files},
                {
                    "r1/seed_r1.smt2",
                    "r2/seed_r2-r1.smt2",
                    "r2/seed_r2-r4-r1.smt2",
                    "r3/seed_r3-r1.smt2",
                    "r3/seed_r3-r4-r2-r1.smt2",
                    "r4/seed_r4-r1.smt2",
                    "r4/seed_r4-r2-r1.smt2",
                },
            )
            self.assertFalse(
                [
                    path
                    for router_dir in seed_directory.iterdir()
                    if router_dir.is_dir()
                    for path in router_dir.iterdir()
                    if path.is_dir()
                ]
            )
            self.assertTrue((Path(temporary) / "consistency_report.json").is_file())
            readable = report.to_readable_text()
            self.assertIn("SYMBOLIC ROUTE CONSISTENCY CHECK SUMMARY", readable)
            self.assertIn("Overall status: PASS", readable)
            self.assertIn("Eligible 1/1 | SAT 1/1 | Status PASS", readable)
            self.assertIn("Local CONNECTED origins normalized: 1", readable)
            self.assertIn("All eligible branches are consistent. ✓", readable)
            self.assertNotIn("candidate-v1-018e885404f47225", readable)
            self.assertNotIn("solver=", readable)

    def test_optional_router_and_prefix_filters_are_debug_scope(self) -> None:
        checker = ConsistencyChecker(WORK_DIRECTORY, z3_path=self.z3)
        with tempfile.TemporaryDirectory() as temporary:
            report = checker.run(
                k=1,
                router="r4",
                prefix="10.0.0.0/24",
                output_directory=temporary,
            )
            self.assertEqual(report.scope.mode, "debug-filtered")
            self.assertEqual(report.scope.routers, ("r4",))
            self.assertEqual(report.scope.destinations, ("10.0.0.0/24",))
            self.assertEqual(report.status, "PASS")
            self.assertEqual(report.total_scope_branches, 3)
            self.assertEqual(report.eligible_branches, 2)
            self.assertEqual(report.checked_branches, 2)
            self.assertEqual(report.sat_branches, 2)
            self.assertTrue((Path(temporary) / "consistency_report.json").is_file())
            readable = report.to_readable_text()
            self.assertIn(
                "Debug filter: router=r4, destination=10.0.0.0/24", readable
            )
            self.assertIn("All eligible branches are consistent. ✓", readable)

    def test_checks_every_failure_assignment_not_only_one_witness(self) -> None:
        checker = ConsistencyChecker(WORK_DIRECTORY, z3_path=self.z3)
        declarations = "\n".join(checker.seed_builder.guard_encoder.declarations())
        seed = (
            "(set-option :produce-unsat-cores true)\n"
            f"{declarations}\n"
            "(assert |LINK-UP-r1_r2|)\n"
            "(assert |LINK-UP-r1_r3|)\n"
            "\n; Consistency query\n(check-sat)\n"
        )
        no_failures = checker._pin_failure_assignment(seed, frozenset())
        r1_r3_failed = checker._pin_failure_assignment(
            seed, frozenset({"r1_r3"})
        )
        self.assertEqual(checker._run_z3(no_failures)[0], "SAT")
        self.assertEqual(checker._run_z3(r1_r3_failed)[0], "UNSAT")

    def test_branch_fails_when_a_later_guarded_assignment_is_unsat(self) -> None:
        checker = ConsistencyChecker(WORK_DIRECTORY, z3_path=self.z3)
        context = next(
            item
            for item in checker.rib.forwarding_branch_contexts(
                router="r4",
                vrf="default",
                destination="10.0.0.0/24",
                k=1,
            )
            if item.current_entry.selected_peer == "r2"
        )
        device_encoding = (
            WORK_DIRECTORY
            / "1_sliced_device_smt_encoding"
            / "sliced_r4_smt_encoding.smt2"
        )
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(
                checker,
                "_run_z3",
                side_effect=(("SAT", "sat\n"), ("UNSAT", "unsat\n")),
            ) as solve:
                with mock.patch.object(checker, "_get_unsat_core", return_value=()):
                    result = checker._check_branch(
                        context,
                        device_encoding,
                        Path(temporary),
                        1,
                        "10.0.0.0/24",
                        "seed_p2_regression",
                    )
        self.assertEqual(result.status, "UNSAT")
        self.assertEqual(solve.call_count, 2)
        self.assertIn("checked 2/4", result.diagnostics[-1]["message"])

    def test_empty_scope_fails_closed(self) -> None:
        checker = ConsistencyChecker(WORK_DIRECTORY, z3_path=self.z3)
        with tempfile.TemporaryDirectory() as temporary:
            report = checker.run(
                k=1,
                router="does-not-exist",
                output_directory=temporary,
            )
            self.assertEqual(report.status, "FAIL")
            self.assertEqual(report.scope.mode, "debug-filtered")
            self.assertEqual(report.scope.routers, ())
            self.assertEqual(report.eligible_branches, 0)
            self.assertEqual(report.checked_branches, 0)
            self.assertTrue(report.errors)


if __name__ == "__main__":
    unittest.main()
