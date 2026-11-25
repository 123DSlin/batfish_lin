#!/usr/bin/env python3
"""Run a BGP-only router scale sweep and write an English TXT report.

Ring and sparse use exact router counts. FatTree takes even switch radix k
and has 5*k*k/4 routers (hosts are omitted).
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from ipaddress import IPv4Address
import json
import math
from mmap import ACCESS_READ, mmap
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

SCALE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCALE_DIRECTORY.parent / "time"))
from compare_0083 import ROOT, generate, generation_phases


SIZES = (4, 8, 16, 32, 64, 128, 256, 512, 1000)
FAT_TREE_RADICES = (4, 8, 16, 28)
POLICIES = ("uniform", "neighbor-preference")
SMT_VARIABLE = re.compile(
    rb"^\s*\((?:declare-const\s|declare-fun\s+(?:\|[^|]*\||[^\s()]+)\s*\(\s*\))",
    re.M,
)
SMT_ASSERTION = re.compile(rb"^\s*\(assert(?=[\s(])", re.M)


def topology(kind, size):
    if kind in ("ring", "sparse"):
        edges = [(i, (i + 1) % size) for i in range(size)]
        if kind == "sparse":
            edges.extend((i, i + size // 2) for i in range(size // 2))
        return size, edges, size // 2
    half = size // 2
    core = size * size
    edges = []
    for pod in range(size):
        base = pod * size
        for edge in range(half):
            for agg in range(half):
                edges.append((base + edge, base + half + agg))
        for agg in range(half):
            for slot in range(half):
                edges.append((base + half + agg, core + agg * half + slot))
    return core + half * half, edges, (size - 1) * size


def write_configs(directory, count, edges, policy):
    neighbors = defaultdict(list)
    for i, (left, right) in enumerate(edges):
        address = IPv4Address("10.0.0.0") + i * 4
        neighbors[left].append((right, address + 1, address + 2))
        neighbors[right].append((left, address + 2, address + 1))

    configs = directory / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    for router in range(count):
        lines = [
            f"hostname r{router}",
            "ip prefix-list DESTINATION seq 5 permit 5.5.5.5/32",
        ]
        preferred_neighbor = min(neighbor for neighbor, _, _ in neighbors[router])
        preferences = {
            neighbor: 250 if policy == "neighbor-preference" and neighbor == preferred_neighbor else 200
            for neighbor, _, _ in neighbors[router]
        }
        for preference in sorted(set(preferences.values())):
            name = "IMPORT_DESTINATION" if preference == 200 else "IMPORT_PREFERRED"
            lines.extend([f"route-map {name} permit 10",
                          " match ip address prefix-list DESTINATION",
                          f" set local-preference {preference}", "!"])
        for index, (_, local, _) in enumerate(neighbors[router]):
            lines.extend([f"interface GigabitEthernet0/{index}",
                          f" ip address {local} 255.255.255.252", "!"])
        if router == 0:
            lines.extend(["interface Loopback0", " ip address 5.5.5.5 255.255.255.255",
                          "!", "route-map ORIGINATE permit 10",
                          " match ip address prefix-list DESTINATION", "!"])
        lines.extend([f"router bgp {64512 + router}",
                      f" bgp router-id {IPv4Address('192.0.2.1') + router}"])
        for neighbor, _, peer in neighbors[router]:
            name = "IMPORT_PREFERRED" if preferences[neighbor] == 250 else "IMPORT_DESTINATION"
            lines.extend([f" neighbor {peer} remote-as {64512 + neighbor}",
                          f" neighbor {peer} route-map {name} in"])
        if router == 0:
            lines.append(" redistribute connected route-map ORIGINATE")
        (configs / f"r{router}.cfg").write_text("\n".join([*lines, "!", ""]))


def process_tree(root_pid):
    output = subprocess.check_output(["ps", "-axo", "pid=,ppid=,rss="], text=True,
                                     stderr=subprocess.DEVNULL)
    children = defaultdict(list)
    rss = {}
    for line in output.splitlines():
        pid, parent, memory = map(int, line.split())
        children[parent].append(pid)
        rss[pid] = memory
    pending = [root_pid]
    tree = {}
    while pending:
        pid = pending.pop()
        tree[pid] = rss.get(pid, 0)
        pending.extend(children[pid])
    return tree


def stop_process_tree(process):
    # Bazel's test wrapper starts the JVM in a separate process group. Take
    # the descendant snapshot while the parent still owns the test process.
    try:
        descendants = list(process_tree(process.pid))[1:]
    except (OSError, subprocess.CalledProcessError):
        descendants = []
    for pid in reversed(descendants):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def monitored_run(command, log, deadline, resources):
    started = time.monotonic()
    # Keep Bazel and the Batfish test JVM in the monitored process tree.
    if command[0] == "bazel":
        command = ["bazel", "--batch", *(
            "--test_output=streamed" if arg == "--test_output=all" else arg
            for arg in command[1:]
        ), f"--test_timeout={max(1, math.ceil(deadline - started))}"]
    env = {**os.environ, "NETSUBSPEC_SCALE_PROFILE": "1"}
    peak_kib = None
    with log.open("w") as stream, subprocess.Popen(
        command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
        start_new_session=True,
    ) as process:
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, deadline - started)
                try:
                    sample = sum(process_tree(process.pid).values())
                    peak_kib = max(peak_kib or 0, sample)
                except (OSError, subprocess.CalledProcessError):
                    pass
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, command)
        finally:
            if process.poll() is None:
                stop_process_tree(process)
            resources[log.name] = {"wall_seconds": time.monotonic() - started,
                                   "peak_rss_mib": None if peak_kib is None else peak_kib / 1024}
    return resources[log.name]["wall_seconds"]


def read_json(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def smt_metrics(paths):
    totals = Counter(files=0, variables=0, assertions=0, bytes=0)
    for path in paths:
        totals["files"] += 1
        size = path.stat().st_size
        totals["bytes"] += size
        if not size:
            continue
        # Minesweeper can put a declaration's empty argument list on the next line.
        with path.open("rb") as stream:
            with mmap(stream.fileno(), 0, access=ACCESS_READ) as encoding:
                totals["variables"] += sum(1 for _ in SMT_VARIABLE.finditer(encoding))
                totals["assertions"] += sum(1 for _ in SMT_ASSERTION.finditer(encoding))
    return dict(totals)


def event_times(events, *kinds):
    selected = [e for e in events if e["kind"] in kinds]
    wall, end = 0.0, 0.0
    for event in sorted(selected, key=lambda e: e["start_seconds"]):
        wall += max(0.0, event["end_seconds"] - max(end, event["start_seconds"]))
        end = max(end, event["end_seconds"])
    return {"calls": len(selected), "active_wall_s": round(wall, 6),
            "task_sum_s": round(sum(e["elapsed_seconds"] for e in selected), 6)}


def metrics(source):
    rib = read_json(source / "symbolic_route.json")
    candidates = rib.get("candidates", [])
    guards = [c[key]["ast"] for c in candidates for key in ("availabilityGuard", "selectionGuard")
              if c.get(key) and c[key].get("ast") is not None]
    consistency = read_json(source / "2_consistency_check/consistency_report.json")
    branches = read_json(source / "3_branch_subspecs/branch_subspecs.json")
    final = read_json(source / "4_final_subspecs/final_subspecs.json")
    runtime_paths = sorted(source.glob("runtime_profile/*/runtime_report.json"))
    runtime = read_json(runtime_paths[-1]) if runtime_paths else {}
    result = {}
    if rib:
        result["symbolic_routes"] = {
            "candidates": len(candidates),
            "candidates_by_plane": dict(Counter(c["plane"] for c in candidates)),
            "target_prefix_main_candidates": sum(c["plane"] == "MAIN" and c["prefix"] == "5.5.5.5/32"
                                                 for c in candidates),
            "guard_occurrences": len(guards),
            "distinct_guard_asts": len({json.dumps(g, sort_keys=True) for g in guards}),
            "guard_variables": len(rib.get("guardVariables", [])),
        }
    result["smt_encoding"] = {
        "base": smt_metrics(path for path in [source / "smt_encoding.smt2"] if path.is_file()),
        "device_slices": smt_metrics(path for path in (source / "1_sliced_device_smt_encoding").glob("*.smt2")
                                     if path.name != "sliced_smt_encoding.smt2"),
        "seeds": smt_metrics((source / "2_consistency_check/seeds").rglob("*.smt2")),
    }
    if consistency:
        result["consistency"] = {key: consistency[key] for key in
                                 ("status", "eligible_branches", "checked_branches", "sat_branches")}
    for key, data, records in (
        ("branch_subspecs", branches, (target for branch in branches.get("branches", [])
                                    for level in ("lines", "fields") for target in branch[level])),
        ("final_subspecs", final, (target for level in ("lines", "fields") for target in final.get(level, []))),
    ):
        if data:
            targets = list(records)
            result[key] = {"status": data["status"], "branches": data["branch_count"],
                           "targets": len(targets),
                           "constrained_targets": sum(not t["unrestricted"] for t in targets),
                           "constraint_atom_occurrences": sum(len(t["constraint_ids"]) for t in targets)}
    phases = {row["stage"]: row for row in runtime.get("stages", [])}
    result["pipeline_stage_wall_s"] = {row["label"]: round(row["wall_seconds"], 6) for row in phases.values()}
    result["pipeline_stage_exit_codes"] = {row["label"]: row["returncode"] for row in phases.values()}
    if all(number in phases for number in (3, 4)):
        result["subspec_derivation_wall_s"] = round(sum(phases[n]["wall_seconds"] for n in (3, 4)), 6)
    simplifications = {
        3: ("symbolic_scope_reduction", "reference_simplification", "field_simplification"),
        4: ("intersection_simplification",),
    }
    for number, kinds in (
        (2, ("seed_construction", "consistency_F_query", "z3_process")),
        (3, (*simplifications[3], "z3_process")),
        (4, (*simplifications[4], "z3_process")),
    ):
        if number in phases:
            events = phases[number]["details"].get("events", [])
            result[f"stage_{number}_subtimings"] = {kind: event_times(events, kind) for kind in kinds}
            if number in simplifications:
                result[f"stage_{number}_subtimings"]["simplification_union"] = event_times(
                    events, *simplifications[number]
                )
    return result


def compare_with_traverse(work, source, count, generation_args, args):
    resources = {}
    result = {"status": "NOT_RUN", "comparison": {"status": "NOT_RUN"}, "commands": resources}
    started = time.monotonic()
    deadline = started + args.traverse_timeout
    baseline_output = work / "traverse"

    def run(command, log):
        return monitored_run(command, log, deadline, resources)

    try:
        baseline, _, log = generate(work / "traverse_input", True, runner=run, **generation_args)
        result["generation_subtimings_s"] = generation_phases(log)
        run([
            sys.executable, "tools/auto-netsubspec-Traverse/run_traverse_baseline.py",
            "--source", str(baseline), "--config-directory", str(generation_args["config_directory"]),
            "--output", str(baseline_output), "--devices", ",".join(f"r{i}" for i in range(count)),
            "--workers", str(args.workers), "--k", str(generation_args["k"]),
        ], work / "traverse.log")
        result["status"] = "PASS"
    except subprocess.TimeoutExpired:
        result.update(status="TIMEOUT", error=f"Traverse wall limit of {args.traverse_timeout:g} seconds exceeded")
    except (subprocess.CalledProcessError, OSError, ValueError, IndexError) as error:
        result.update(status="FAIL", error=str(error))
    result["total_runtime_s"] = round(time.monotonic() - started, 6)
    peaks = [r["peak_rss_mib"] for r in resources.values() if r["peak_rss_mib"] is not None]
    result["peak_sampled_process_tree_rss_mib"] = max(peaks, default=None)
    baseline_report = baseline_output / "report.json"
    if baseline_report.is_file():
        baseline_data = read_json(baseline_report)
        result["report"] = str(baseline_report)
        for key in ("input_scenarios", "selected_scenarios", "concrete_export",
                    "preparation_and_AG_wall_seconds", "constraint_solving_wall_seconds",
                    "intersection_seconds"):
            result[key] = baseline_data[key]
    if result["status"] != "PASS":
        return result

    output = source / "failure_intersection_check/report.json"
    comparison = result["comparison"]
    validation_resources = {}
    try:
        monitored_run([
            sys.executable, "tools/auto-netsubspec-Traverse/compare_traverse_results.py",
            str(source), "--traverse-results", str(baseline_output), "--output", str(output),
            "--workers", str(args.workers), "--timeout", str(args.query_timeout),
        ], work / "subspec_comparison.log", time.monotonic() + args.traverse_timeout,
            validation_resources)
        comparison["status"] = "PASS"
    except subprocess.TimeoutExpired:
        comparison.update(status="TIMEOUT", error=f"Validation wall limit of {args.traverse_timeout:g} seconds exceeded")
    except (subprocess.CalledProcessError, OSError) as error:
        comparison.update(status="FAIL", error=str(error))
    comparison.update(validation_resources.get("subspec_comparison.log", {}))
    if output.is_file():
        payload = read_json(output)
        comparison.update(report=str(output), equivalent_targets=payload.get("equivalent_count", 0),
                          total_targets=len(payload["checks"]), outcomes=payload.get("status_counts", {}),
                          errors=payload["errors"])
    return result


def case_name(kind, size, policy):
    name = f"{kind}_{size}"
    return name if policy == "uniform" else f"{name}_{policy}"


def run_case(kind, size, count, edges, ingress, policy, work, args):
    config_directory = SCALE_DIRECTORY / "cases" / case_name(kind, size, policy)
    work.mkdir()
    resources = {}
    started = time.monotonic()
    deadline = started + args.case_timeout

    def run(command, log):
        return monitored_run(command, log, deadline, resources)

    result = {"topology": kind, "radix": size if kind == "fattree" else None,
              "policy": policy,
              "routers": count, "links": len(edges), "mean_degree": 2 * len(edges) / count,
              "ingress": f"r{ingress}", "egress": "r0", "status": "PASS",
              "configuration": str(config_directory / "configs"), "artifacts": str(work)}
    source = None
    generation_args = dict(ingress=f"r{ingress}", destination_router="r0", k=1,
                           config_directory=config_directory)
    try:
        source, _, _ = generate(work / "generation", False, runner=run, **generation_args)
        command = [sys.executable, "tools/netsubspec/tools/run.py", str(source), "--k", "1",
                   "--workers", str(args.workers), "--consistency-workers", str(args.workers),
                   "--timeout", str(args.query_timeout), "--profile"]
        run(command, work / "symbolic_pipeline.log")
    except subprocess.TimeoutExpired:
        phase = "Batfish generation" if source is None else "symbolic pipeline"
        result.update(status="TIMEOUT", error=f"{phase}: wall limit of {args.case_timeout:g} seconds exceeded")
    except (subprocess.CalledProcessError, OSError, ValueError, IndexError) as error:
        result.update(status="FAIL", error=str(error))
    finally:
        result["total_runtime_s"] = round(time.monotonic() - started, 6)
        peaks = [r["peak_rss_mib"] for r in resources.values() if r["peak_rss_mib"] is not None]
        result["peak_sampled_process_tree_rss_mib"] = max(peaks, default=None)
        result["commands"] = resources
    generation_log = work / "generation/generation.log"
    if generation_log.is_file():
        log = generation_log.read_text()
        result["generation_subtimings_s"] = generation_phases(log)
        route_time = re.findall(r"^CONFIG_TO_SYMBOLIC_ROUTE_SECONDS=(.+)$", log, re.M)
        if route_time:
            result["configuration_to_symbolic_route_s"] = float(route_time[-1])
    if source is None:
        source = next(iter((work / "generation").glob("smt_output_*")), None)
    if source is not None:
        try:
            result.update(metrics(source))
            if result["status"] == "PASS" and (
                len(result["pipeline_stage_exit_codes"]) != 4
                or result.get("final_subspecs", {}).get("status") != "PASS"
            ):
                result.update(status="FAIL", error="Missing successful stage 1–4 results")
        except (OSError, ValueError, KeyError) as error:
            result["metrics_error"] = str(error)
    if count > args.traverse_max_routers:
        result["traverse"] = {"status": "SKIPPED", "reason": "above Traverse router limit"}
    elif result["status"] != "PASS":
        result["traverse"] = {"status": "SKIPPED", "reason": "Symbolic did not finish successfully"}
    else:
        try:
            result["traverse"] = compare_with_traverse(work, source, count, generation_args, args)
        except (OSError, ValueError, KeyError) as error:
            result["traverse"] = {"status": "FAIL", "error": str(error)}
    return result


def write_report(report, header, results):
    lines = [
        header, "",
        f"{'Topology':<10}{'Policy':<21}{'Routers':>7}{'Links':>7}{'Branches':>10}"
        f"{'Sym (s)':>10}{'Peak MiB':>10}{'Traverse (s)':>14}  Symbolic / Traverse / Diff",
        "-" * 124,
    ]
    for result in results:
        branches = result.get("consistency", {}).get("eligible_branches", "-")
        peak = result["peak_sampled_process_tree_rss_mib"]
        memory = "-" if peak is None else f"{peak:.1f}"
        traverse = result["traverse"]
        traverse_time = f"{traverse['total_runtime_s']:.3f}" if "total_runtime_s" in traverse else "-"
        comparison_status = traverse.get("comparison", {}).get("status", "NOT_RUN")
        lines.append(
            f"{result['topology']:<10}{result['policy']:<21}{result['routers']:>7}"
            f"{result['links']:>7}{branches:>10}{result['total_runtime_s']:>10.3f}"
            f"{memory:>10}{traverse_time:>14}  "
            f"{result['status']} / {traverse['status']} / {comparison_status}"
        )

    def detail(values, indent="  "):
        for name, value in values.items():
            label = indent + name.replace("_", " ")
            if isinstance(value, dict):
                lines.append(label)
                detail(value, indent + "  ")
            elif isinstance(value, float):
                lines.append(f"{label:<54}{value:>12.6f}")
            else:
                lines.append(f"{label:<54}{str(value) if value is not None else '-':>12}")

    for result in results:
        lines.extend(["", f"{result['topology'].upper()} | {result['routers']} ROUTERS | {result['policy']}",
                      "-" * 78])
        detail(result)
    report.write_text("\n".join(lines) + "\n")
    json_report = report.with_suffix(".json")
    pending = json_report.with_suffix(".json.tmp")
    pending.write_text(json.dumps({"description": header, "cases": results}, indent=2) + "\n")
    pending.replace(json_report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topologies", nargs="+", choices=("ring", "sparse", "fattree"),
                        default=("ring", "sparse", "fattree"))
    parser.add_argument("--routers", nargs="+", type=int, choices=SIZES, default=SIZES)
    parser.add_argument("--fat-tree-k", nargs="+", type=int, default=FAT_TREE_RADICES)
    parser.add_argument("--policies", nargs="+", choices=POLICIES, default=("uniform",))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--generate-only", action="store_true",
                        help="write the selected configurations and exit")
    parser.add_argument("--case-timeout", type=float, default=600)
    parser.add_argument("--query-timeout", type=float, default=30)
    parser.add_argument("--traverse-max-routers", type=int, default=32,
                        help="compare cases at or below this size (0 disables Traverse)")
    parser.add_argument("--traverse-timeout", type=float, default=240,
                        help="wall limit in seconds, applied separately to Traverse and equivalence")
    args = parser.parse_args()
    if args.workers <= 0 or any(not math.isfinite(value) or value <= 0
                                for value in (args.case_timeout, args.query_timeout, args.traverse_timeout)):
        parser.error("workers and timeouts must be positive")
    if args.traverse_max_routers < 0:
        parser.error("Traverse router limit must be nonnegative")
    if any(k < 4 or k > 28 or k % 2 for k in args.fat_tree_k):
        parser.error("FatTree radix must be even and between 4 and 28")
    cases = [(kind, size, *topology(kind, size), policy)
             for kind in dict.fromkeys(args.topologies)
             for size in dict.fromkeys(args.fat_tree_k if kind == "fattree" else args.routers)
             for policy in dict.fromkeys(args.policies)]
    for kind, size, count, edges, _, policy in cases:
        write_configs(SCALE_DIRECTORY / "cases" / case_name(kind, size, policy), count, edges, policy)
    if args.generate_only:
        print(SCALE_DIRECTORY / "cases")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    work = SCALE_DIRECTORY / "runs" / stamp
    work.mkdir(parents=True)
    report = SCALE_DIRECTORY / "reports" / f"router_scale_{stamp}.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "BGP ROUTER SCALE | one advertised prefix (5.5.5.5/32) | k=1\n"
        f"Workers: {args.workers} | case timeout: {args.case_timeout:g} s | "
        f"symbolic/comparison query timeout: {args.query_timeout:g} s\nArtifacts: {work}\n"
        f"Traverse router limit: {args.traverse_max_routers} | "
        f"Traverse and comparison wall limits: {args.traverse_timeout:g} s each\n"
        "Import policy: uniform = 200; neighbor-preference = 250 for the lowest-ID neighbor.\n"
        "Guard counts include availability and selection ASTs. SMT counts are summed per file.\n"
        "Active wall is the union of parallel intervals; task sums count each task separately.\n"
        "Derivation is stage 3 + 4 wall. Simplification can include Z3 time.\n"
        "Z3 time measures stage 2–4 subprocesses, including tactic calls and process I/O.\n"
        "Peak memory is sampled summed process-tree RSS (MiB); shared pages can be counted twice.\n"
        "Symbolic and Traverse totals include their own Batfish/Bazel commands. "
        "Subspec equivalence runs separately."
    )
    results = []
    write_report(report, header, results)
    print(report, flush=True)
    for kind, size, count, edges, ingress, policy in cases:
        print(f"{kind} {count} routers | {policy}", flush=True)
        results.append(run_case(kind, size, count, edges, ingress, policy,
                                work / case_name(kind, size, policy), args))
        write_report(report, header, results)
    return int(any(r["status"] != "PASS" or "metrics_error" in r
                   or r["traverse"]["status"] not in ("PASS", "SKIPPED")
                   or r["traverse"].get("comparison", {}).get("status") not in (None, "PASS")
                   for r in results))


if __name__ == "__main__":
    sys.exit(main())
