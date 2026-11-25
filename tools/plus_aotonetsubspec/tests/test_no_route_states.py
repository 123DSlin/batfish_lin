"""No-route states must be covered, checked, and projected like route states."""
from dataclasses import replace
from importlib import import_module
from itertools import combinations
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from consistency import (
    ConsistencyChecker, ConsistencyReport, GuardEncoder, GuardVariable,
    NeighborTopology, NoRouteState, RouteEntry, Scope, SeedBuilder, SeedBuildError,
    SymbolicRib, SymbolicRouteFormatError,
)
from consistency.branch_loader import NeighborEndpoint, NeighborLink


FIXTURE = Path(__file__).parent / "fixtures/symbolic_output_0010"
TARGET = "5.5.5.5/32"
CONFIG = "Config_u_RoutingPolicy_IMPORT__Seq10__Line1__permit"


def make_rib(*, conditional_route=False):
    u = NeighborEndpoint("u", "Ethernet0", 65001)
    v = NeighborEndpoint("v", "Ethernet0", 65002)
    true_guard = {"ast": {"operator": "TRUE"}, "simplified": "true"}
    origin = RouteEntry(
        candidate_id="candidate-v1-peer-origin", plane="MAIN", router="v",
        vrf="default", prefix=TARGET, protocol="STATIC", route_type="StaticRoute",
        attributes={}, selection_guard=true_guard, availability_guard=true_guard,
        contributions=())
    entries = [origin]
    if conditional_route:
        guard = {"ast": {"operator": "VARIABLE", "variableId": "u_v"},
                 "simplified": "u_v"}
        entries.append(replace(origin, candidate_id="candidate-v1-device-route",
                               router="u", selection_guard=guard, availability_guard=guard))
    return SymbolicRib(
        [GuardVariable("u_v", "LINK_AVAILABILITY", "u", "v", "UP")], entries,
        topology=NeighborTopology([NeighborLink(u, v), NeighborLink(v, u)]),
        interfaces={"u": {"Ethernet0"}, "v": {"Ethernet0"}})


def encoding(*, accept=False):
    return f"""; ---- Declarations ----
(declare-fun {CONFIG} () Bool)
(declare-fun |0_FAILED-EDGE_u_v| () Int)
(declare-fun |0_u_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_v_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_u_Ethernet0| () Bool)
; ---- Assertions ----
(assert (= {CONFIG} {'true' if accept else 'false'}))
(assert (and (>= |0_FAILED-EDGE_u_v| 0) (<= |0_FAILED-EDGE_u_v| 1)))
(assert (= |0_u_OVERALL_BEST_None_permitted|
           (and (= |0_FAILED-EDGE_u_v| 0) |0_v_OVERALL_BEST_None_permitted| {CONFIG})))
(assert (= |0_CONTROL-FORWARDING_u_Ethernet0| |0_u_OVERALL_BEST_None_permitted|))
(check-sat)
"""


class NoRouteBranchTest(unittest.TestCase):
    def test_always_absent_device_has_checked_state_not_a_fake_route(self):
        rib = make_rib()
        context, = rib.forwarding_state_contexts(
            router="u", vrf="default", destination=TARGET, k=0)
        self.assertIsInstance(context.current_entry, NoRouteState)
        self.assertEqual(context.current_entry.branch_kind, "NO_ROUTE")
        self.assertFalse(rib.forwarding_entries(router="u", vrf="default", destination=TARGET))
        self.assertIsNone(context.current_entry.selected_peer)
        self.assertFalse(context.predecessor_entries)

    def test_no_route_is_exact_complement_and_pruned_by_failure_budget(self):
        rib = make_rib(conditional_route=True)
        encoder = GuardEncoder(rib.guard_variables)
        for k, kinds in [(0, ["ROUTE"]), (1, ["ROUTE", "NO_ROUTE"])]:
            contexts = rib.forwarding_state_contexts(
                router="u", vrf="default", destination=TARGET, k=k)
            self.assertEqual([c.current_entry.branch_kind for c in contexts], kinds)
        states = rib.forwarding_state_contexts(router="u", vrf="default", destination=TARGET, k=1)
        for failures in [(), ("u_v",)]:
            active = [c.current_entry.branch_kind for c in states
                      if encoder.evaluate(c.current_entry.selection_guard, failures)]
            self.assertEqual(active, ["NO_ROUTE" if failures else "ROUTE"])

    def test_complement_covers_all_fixture_failure_sets_including_fallbacks(self):
        rib = SymbolicRib.from_work_directory(FIXTURE)
        encoder = GuardEncoder(rib.guard_variables)
        contexts = rib.forwarding_state_contexts(
            router="r4", vrf="default", destination="10.0.0.1", k=3)
        self.assertTrue(any(c.current_entry.branch_kind == "NO_ROUTE" for c in contexts))
        for n in range(4):
            for failed in combinations(encoder.variable_index, n):
                active = [c.current_entry for c in contexts
                          if encoder.evaluate(c.current_entry.selection_guard, failed)]
                self.assertTrue(active)
                self.assertFalse(any(c.branch_kind == "ROUTE" for c in active)
                                 and any(c.branch_kind == "NO_ROUTE" for c in active))

    def test_unknown_device_and_missing_export_still_fail(self):
        with self.assertRaisesRegex(SymbolicRouteFormatError, "inventoried"):
            make_rib().forwarding_state_contexts(
                router="missing", vrf="default", destination=TARGET, k=0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SymbolicRouteFormatError):
                SymbolicRib.from_work_directory(tmp)

    def test_empty_peer_rib_is_retained_as_absent_boundary(self):
        rib = make_rib()
        context, = rib.forwarding_state_contexts(
            router="v", vrf="default", destination=TARGET, k=0)
        self.assertIn("u", context.peer_ribs)
        self.assertEqual(context.peer_ribs["u"], ())


@unittest.skipUnless(shutil.which("z3"), "Z3 executable unavailable")
class NoRouteSolverTest(unittest.TestCase):
    def solve(self, text):
        result = subprocess.run([shutil.which("z3"), "-in"], input=text,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def test_seed_checks_absence_in_every_guarded_failure_assignment(self):
        for conditional in (False, True):
            rib = make_rib(conditional_route=conditional)
            context = next(c for c in rib.forwarding_state_contexts(
                router="u", vrf="default", destination=TARGET, k=1)
                if c.current_entry.branch_kind == "NO_ROUTE")
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "device.smt2"
                path.write_text(encoding(accept=conditional))
                artifact = SeedBuilder(rib).build(context, path, k=1, destination=TARGET)
                self.assertIn("; Branch kind: NO_ROUTE", artifact.text)
                self.assertNotIn("Selected import route", artifact.text)
                encoder = GuardEncoder(rib.guard_variables)
                for failed in encoder.satisfying_failure_assignments(context.current_entry.selection_guard, 1):
                    pins = "\n".join(f"(assert {e})" for e in encoder.concrete_assignment_expressions(failed))
                    self.assertEqual(self.solve(artifact.text.replace("(check-sat)", pins + "\n(check-sat)")), "sat")

    def test_incomplete_route_export_is_rejected_by_seed_equations(self):
        rib = make_rib()  # Export incorrectly omits u's route.
        context, = rib.forwarding_state_contexts(router="u", vrf="default", destination=TARGET, k=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device.smt2"
            path.write_text(encoding(accept=True))  # Actual equations accept it.
            artifact = SeedBuilder(rib).build(context, path, k=0, destination=TARGET)
            self.assertEqual(self.solve(artifact.text), "unsat")

    def test_static_discard_selects_control_interface_and_keeps_data_drop(self):
        rib = make_rib()
        origin, = rib.entries(router="v", plane="MAIN")
        discard = replace(origin, candidate_id="candidate-v1-discard", router="u",
                          attributes={"nextHopInterface": "null_interface"})
        rib = SymbolicRib(rib.guard_variables, [origin, discard],
                          topology=rib.topology, interfaces={"u": {"Ethernet0", "null_interface"},
                                                             "v": {"Ethernet0"}})
        context, = rib.forwarding_branch_contexts(router="u", vrf="default", destination=TARGET, k=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device.smt2"
            path.write_text("""; ---- Declarations ----
(declare-fun |0_u_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_v_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_u_null_interface| () Bool)
(declare-fun |0_DATA-FORWARDING_u_null_interface| () Bool)
; ---- Assertions ----
(assert (= |0_CONTROL-FORWARDING_u_null_interface| |0_u_OVERALL_BEST_None_permitted|))
(assert (not |0_DATA-FORWARDING_u_null_interface|))
(check-sat)
""")
            artifact = SeedBuilder(rib).build(context, path, k=0, destination=TARGET)
            self.assertEqual(self.solve(artifact.text), "sat")
            self.assertEqual(self.solve(artifact.text.replace("(check-sat)",
                "(assert (not |0_CONTROL-FORWARDING_u_null_interface|))\n(check-sat)")), "unsat")
            self.assertEqual(self.solve(artifact.text.replace("(check-sat)",
                "(assert |0_DATA-FORWARDING_u_null_interface|)\n(check-sat)")), "unsat")

    def test_missing_neighbor_boundary_is_not_silently_accepted(self):
        rib = make_rib()
        context, = rib.forwarding_state_contexts(router="u", vrf="default", destination=TARGET, k=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device.smt2"
            path.write_text(encoding().replace("(declare-fun |0_v_OVERALL_BEST_None_permitted| () Bool)\n", ""))
            with self.assertRaisesRegex(SeedBuildError, "PEER_BEST_NOT_IN_SLICE"):
                SeedBuilder(rib).build(context, path, k=0, destination=TARGET)

    def test_no_route_seed_produces_nonempty_config_constraint_and_final_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "0_hostnames.txt").write_text("u\n")
            device_dir = work / "1_sliced_device_smt_encoding"
            device_dir.mkdir()
            (device_dir / "sliced_u_smt_encoding.smt2").write_text(encoding())
            checker = ConsistencyChecker(FIXTURE)
            checker.work_directory = work
            checker.rib = make_rib()
            checker.seed_builder = SeedBuilder(checker.rib)
            scope, branches = checker._check_scope(
                router="u", vrf="default", destination=TARGET, k=1,
                seeds_directory=work / "2_consistency_check/seeds", seed_name_counts={})
            self.assertEqual(scope.status, "PASS")
            self.assertEqual(branches[0].branch_kind, "NO_ROUTE")
            ConsistencyReport(
                scope=Scope("global", ("u",), "default", (TARGET,), "MAIN", 1),
                status="PASS", generated_at="test", source_json="", hostnames_file="",
                destinations_file="", solver=shutil.which("z3"),
                total_scope_branches=1, eligible_branches=1, checked_branches=1,
                sat_branches=1, unsat_branches=0, unknown_branches=0, error_branches=0,
                scope_results=(scope,), branches=branches,
            ).write(work / "2_consistency_check")
            stage3 = import_module("3_branch_simplifier").SymbolicSubspecifier(work).run(max_workers=1)
            self.assertEqual(stage3.status, "PASS", stage3.errors)
            self.assertEqual(stage3.branches[0].branch_kind, "NO_ROUTE")
            field, = stage3.branches[0].fields
            self.assertFalse(field.unrestricted)
            self.assertEqual(field.projection["residual_symbols"], [])
            stage4 = import_module("4_branch_intersection").SymbolicIntersection(work).run()
            self.assertEqual(stage4.status, "PASS")
            self.assertEqual(stage4.branch_provenance[0]["branch_kind"], "NO_ROUTE")
            final, = stage4.fields
            self.assertEqual(self.solve(f"(declare-fun {CONFIG} () Bool)\n(assert (= {CONFIG} true))\n(assert {final.constraint})\n(check-sat)"), "unsat")


if __name__ == "__main__":
    unittest.main()
