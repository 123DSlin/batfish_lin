#!/usr/bin/env python3
"""Run both 0083 BGP pipelines and write one timing report per comparison."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from statistics import median
import subprocess
import sys
import tempfile
import time


REPORT_DIRECTORY = Path(__file__).resolve().parent
ROOT = REPORT_DIRECTORY.parents[1]
NETWORK = "tolerance_sr_te_demo_bgp_x_b"
TEST = "org.batfish.minesweeper.smt.SmtReachabilityTest"


def run(command, log):
    started = time.perf_counter()
    with log.open("w") as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
    return time.perf_counter() - started


def generate(work, skip_symbolic_routes, force_solver=False):
    work.mkdir()
    env = {
        "SMT_DIRECTORY_PREFIX": str(work),
        "SMT_NETWORK": NETWORK,
        "SMT_SYMBOLIC": "false",
        "SMT_PROTOCOLS": "BGP",
        "SMT_ENUMERATE_FAILURES": "false",
        "SMT_SKIP_SYMBOLIC_ROUTES": str(skip_symbolic_routes).lower(),
        "SMT_PROFILE_GENERATION": "true",
        "SMT_GUARD_FORCE_SOLVER": str(force_solver).lower(),
        "SMT_INGRESS": "x",
        "SMT_FINAL": "d",
        "SMT_DST": "5.5.5.5/32",
        "SMT_FAILURES": "2",
    }
    generation_log = work / "generation.log"
    generation_wall = run([
        "bazel", "test", "//projects/allinone:smt_tests", "--nocache_test_results",
        "--test_output=all", f"--test_filter={TEST}#testReachability",
        "--strategy=TestRunner=standalone", "--spawn_strategy=local",
        *(f"--test_env={key}={value}" for key, value in env.items()),
    ], generation_log)
    log = generation_log.read_text()
    source = Path(re.findall(r"^SMT_OUTPUT_DIRECTORY=(.+)$", log, re.M)[-1])
    return source, generation_wall, log


def generation_phases(log):
    return {name: float(seconds) for name, seconds in
            re.findall(r"^GENERATION_PHASE=([^,]+),(.+)$", log, re.M)}


def guard_trial(log):
    matches, queries = map(int, re.findall(r"^GUARD_EQUIVALENCE=(.+)$", log, re.M)[-1].split(","))
    return generation_phases(log)["symbolic_convergence"], matches, queries


def guard_comparison(work, reference):
    measurements = {False: [], True: []}
    for index, force_solver in enumerate((True, False, False, True), 1):
        output, _, log = generate(work / f"guard_trial_{index}", False, force_solver)
        for name in ("symbolic_route.json", "smt_encoding.smt2"):
            if (output / name).read_bytes() != (reference / name).read_bytes():
                raise ValueError(f"Guard trial {index} changed {name}")
        measurements[force_solver].append(guard_trial(log))
    return measurements


def format_comparison(profile, traverse, route_seconds, generation_wall,
                      baseline_generation_wall, traverse_wall, symbolic_phases,
                      traverse_phases, guard_trials=None):
    symbolic = json.loads(profile.read_text())
    baseline = json.loads((traverse / "report.json").read_text())
    verification = profile.parents[2] / "failure_intersection_check/report.json"
    comparison = json.loads(verification.read_text())
    stages = {row["stage"]: row["wall_seconds"] for row in symbolic["stages"]}
    symbolic_total = generation_wall + symbolic["pipeline_wall_seconds"]
    traverse_total = baseline_generation_wall + traverse_wall
    export = float(re.search(r"Export wall seconds: (.+)",
                             baseline["concrete_export"]["summary"])[1])
    rule = "-" * 67

    def row(label, seconds):
        return f"{label:<55}{seconds:>12.3f}"

    def generation_rows(phases, indent, include_encoding=True):
        labels = {
            "configuration_load": "Load configuration",
            "no_failure_dataplane": "Compute no-failure dataplane",
            "concrete_rib_export": "Export concrete RIB",
            "symbolic_input_build": "Build symbolic input",
            "symbolic_convergence": "Converge symbolic routes",
            "symbolic_text_export": "Export symbolic route text",
            "symbolic_json_export": "Write symbolic route JSON",
            "minesweeper_encode_and_verify": "Encode and verify with Minesweeper",
        }
        rows = []
        for phase, seconds in phases.items():
            if not include_encoding and phase == "minesweeper_encode_and_verify":
                continue
            rows.append(row(indent + labels[phase], seconds))
            if phase == "symbolic_convergence" and guard_trials:
                before, after = guard_trials[True], guard_trials[False]
                rows.extend([
                    row("      Solver-only median (2 trials)", median(sample[0] for sample in before)),
                    row("      Fast-path median (2 trials)", median(sample[0] for sample in after)),
                    "      Z3 equivalence queries: "
                    f"{median(sample[2] for sample in before):.0f} -> "
                    f"{median(sample[2] for sample in after):.0f}; route JSON and SMT identical",
                ])
        return rows

    preparation = baseline["preparation_and_AG_wall_breakdown"]
    solving_wall = baseline["constraint_solving_wall_breakdown"]

    lines = [
        f"{'TRAVERSE':<55}{'Seconds':>12}", rule,
        row("1. Generate base SMT from configuration", baseline_generation_wall),
        *generation_rows(traverse_phases, "  "),
        row("2. Inject failures and export dataplanes (Bazel)",
            baseline["concrete_export"]["command_wall_seconds_including_build"]),
        row("  Batfish fault injection and export", export),
        row("3. Per-failure preparation, slicing and AG", baseline["preparation_and_AG_wall_seconds"]),
        row("  Scenario input preparation only", preparation["prepare"]),
        row("  Route analysis only", preparation["route_analysis"]),
        row("  Device slicing only", preparation["slicing"]),
        row("  Assume-guarantee checks only", preparation["assume_guarantee"]),
        row("  Multiple preparation stages active", preparation["overlap"]),
        row("  Scheduling and idle time", preparation["overhead"]),
        row("4. Solve line and field constraints", baseline["constraint_solving_wall_seconds"]),
        row("  Only line solving active", solving_wall["line_solving"]),
        row("  Only field solving active", solving_wall["field_solving"]),
        row("  Line and field solving active together", solving_wall["overlap"]),
        row("  Scheduling and idle time", solving_wall["overhead"]),
        row("5. Intersect results across failures", baseline["intersection_seconds"]),
        rule,
        row("TOTAL | Configuration to final subspec", traverse_total),
        row("Baseline subtotal | Solving + intersection", baseline["baseline_solve_and_intersection_wall_seconds"]),
        f"Scenarios: {baseline['selected_scenarios']}/{baseline['input_scenarios']} ({baseline['status']})",
        "",
        f"{'SYMBOLIC':<55}{'Seconds':>12}", rule,
        row("1. Generate symbolic routes and SMT from configuration", generation_wall),
        row("  Configuration to symbolic_route.json", route_seconds),
        *generation_rows(symbolic_phases, "    ", include_encoding=False),
        row("  Encode and verify with Minesweeper", symbolic_phases["minesweeper_encode_and_verify"]),
        row("2. Slice device SMT", stages[1]),
        row("3. Check consistency across legal failures", stages[2]),
        row("4. Solve branch seeds", stages[3]),
        row("5. Intersect branch results", stages[4]),
        rule,
        row("TOTAL | Configuration to final subspec", symbolic_total),
        "",
        f"{'SYMBOLIC DETAIL':<55}{'Seconds':>12}", rule,
    ]
    details = {stage["stage"]: stage for stage in symbolic["stages"]}
    slicing = {item["device"]: item["exclusive_attributed_seconds"]
               for item in details[1]["details"]["devices"]}
    consistency = {item["device"]: item["task_elapsed_sum_seconds"]
                   for item in details[2]["device_totals"]}
    solving = {item["device"]: item["task_elapsed_sum_seconds"]
               for item in details[3]["device_totals"]}
    seeds = [event for event in details[3]["details"]["events"]
             if event["kind"] == "symbolic_seed"]
    for device in sorted(set(slicing) | set(consistency) | set(solving)):
        lines.append(f"Device {device}")
        for label, times in (("Slicing (attributed)", slicing),
                             ("Consistency check (task sum)", consistency),
                             ("Branch solving (task sum)", solving)):
            if device in times:
                lines.append(row(f"  {label}", times[device]))
        for seed in sorted(seeds, key=lambda event: event["seed"]):
            if seed["device"] == device:
                lines.append(row(f"    {seed['seed']}", seed["elapsed_seconds"]))
        lines.append("")
    lines.extend([
        rule,
        row("Traverse minus Symbolic", traverse_total - symbolic_total),
        row(f"Optional equivalence: {comparison['equivalent_count']}/{len(comparison['checks'])}"
            f" ({comparison['status']})", stages[6]),
        "",
        "Totals include Bazel and exclude equivalence. Device slicing excludes shared work.",
        "Indented rows are subtimings or benchmark samples. Totals use top-level wall times.",
        "Traverse steps 3 and 4 partition wall time by active worker stages.",
        "Symbolic device task sums can exceed wall time because workers run in parallel.",
        "",
        "Detailed reports",
        f"  Per device and seed: {profile.with_suffix('.txt')}",
        f"  Per failure:         {traverse / 'report.txt'}",
        f"  Equivalence:         {verification.with_suffix('.txt')}",
    ])
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--compare-guards", action="store_true",
                        help="compare generation with and without the guard equality fast path")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    workers = str(args.workers)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    report = REPORT_DIRECTORY / f"0083_{stamp}.txt"
    work = Path(tempfile.mkdtemp(prefix="netsubspec-0083-")).resolve()
    lines = [f"0083 | BGP | k=2 | workers={workers}", f"Run artifacts: {work}", ""]
    try:
        symbolic, generation_wall, log = generate(work / "symbolic", False)
        route_seconds = float(re.findall(r"^CONFIG_TO_SYMBOLIC_ROUTE_SECONDS=(.+)$", log, re.M)[-1])
        lines.extend([
            f"Configuration input to symbolic_route.json: {route_seconds:.6f} s",
            f"Batfish symbolic generation + SMT command (including Bazel): {generation_wall:.6f} s",
        ])

        baseline, baseline_generation_wall, baseline_log = generate(work / "traverse_input", True)
        traverse = work / "traverse"
        traverse_wall = run([
            sys.executable, "tools/auto-netsubspec-Traverse/run_traverse_baseline.py",
            "--source", str(baseline), "--network", NETWORK, "--output", str(traverse),
            "--devices", "a,b,d,x", "--workers", workers, "--k", "2",
        ], work / "traverse.log")
        run([
            sys.executable, "tools/netsubspec/tools/run.py", str(symbolic),
            "--k", "2", "--workers", workers, "--consistency-workers", workers,
            "--profile", "--check-failure-intersection", "--traverse-results", str(traverse),
        ], work / "symbolic.log")
        profile = next((symbolic / "runtime_profile").glob("*/runtime_report.json"))
        guard_trials = guard_comparison(work, symbolic) if args.compare_guards else None
        lines = lines[:3] + format_comparison(
            profile, traverse, route_seconds, generation_wall,
            baseline_generation_wall, traverse_wall,
            generation_phases(log), generation_phases(baseline_log), guard_trials,
        )

    except (subprocess.CalledProcessError, OSError, ValueError, IndexError, StopIteration) as error:
        lines.extend(["", f"Comparison failed: {error}"])
        raise
    finally:
        report.write_text("\n".join(lines) + "\n")
        print(report, flush=True)


if __name__ == "__main__":
    main()
