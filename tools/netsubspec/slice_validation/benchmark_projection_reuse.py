#!/usr/bin/env python3
"""Compare unchanged stages 3/4 with a supplied pre-optimization tools tree.

Each version runs in a fresh interpreter and an isolated copy of the same inputs.
Only timings, report paths and the stage-3 report byte hash are ignored when
comparing reports; formulas, provenance, seed hashes and audits must all match.
"""

import argparse
from importlib import import_module
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


def semantic(value):
    ignored = {"generated_at", "solver_seconds", "source_consistency_report",
               "source_report", "source_sha256"}
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if k not in ignored}
    if isinstance(value, list):
        return [semantic(v) for v in value]
    return value


def worker(tools, work, output):
    sys.path.insert(0, str(tools))
    stage3 = import_module("3_branch_simplifier")
    stage4 = import_module("4_branch_intersection")
    invoke = subprocess.run
    dependencies = stage3._device_value_dependencies
    counts = {"z3_processes": 0, "dependency_graph_builds": 0}

    def count_run(args, *positional, **kwargs):
        if isinstance(args, list) and Path(args[0]).name == "z3":
            counts["z3_processes"] += 1
        return invoke(args, *positional, **kwargs)

    def count_dependencies(*args, **kwargs):
        counts["dependency_graph_builds"] += 1
        return dependencies(*args, **kwargs)

    started = time.monotonic()
    with patch.object(subprocess, "run", side_effect=count_run), patch.object(
        stage3, "_device_value_dependencies", side_effect=count_dependencies
    ):
        projector = stage3.SymbolicSubspecifier(work)
        branches = projector.run(max_workers=1)
        if branches.status != "PASS":
            raise RuntimeError(branches.errors)
        stage3_seconds = time.monotonic() - started
        intersector = stage4.SymbolicIntersection(work)
        final = intersector.run()
    if final.status != "PASS":
        raise RuntimeError("stage 4 failed")
    payload = {
        "stage3": semantic(branches.to_dict()),
        "stage4": semantic(final.to_dict()),
        "measurements": {
            **counts, "stage3_seconds": stage3_seconds,
            "total_seconds": time.monotonic() - started,
            "stage3_cache": projector.solver.cache_info()
                if hasattr(projector.solver, "cache_info") else None,
            "stage4_cache": intersector.solver.cache_info()
                if hasattr(intersector.solver, "cache_info") else None,
        },
    }
    output.write_text(json.dumps(payload, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-tools", type=Path)
    parser.add_argument("--current-tools", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--case", type=Path, action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", nargs=2, type=Path, metavar=("TOOLS", "WORK"))
    args = parser.parse_args()
    if args.worker:
        worker(*args.worker, args.output)
        return
    if not args.baseline_tools or not args.case:
        parser.error("--baseline-tools and at least one --case are required")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="projection_reuse_") as temporary:
        for index, case in enumerate(args.case):
            payloads = []
            for label, tools in [("before", args.baseline_tools), ("after", args.current_tools)]:
                work = Path(temporary) / str(index) / label
                shutil.copytree(case, work)
                output = args.output / f"{index}_{case.name}_{label}.json"
                subprocess.run([
                    sys.executable, str(Path(__file__).resolve()),
                    "--worker", str(tools.resolve()), str(work),
                    "--output", str(output.resolve()),
                ], check=True)
                payloads.append(json.loads(output.read_text()))
            before, after = payloads
            result = {
                "case": str(case.resolve()),
                "stage3_identical": before["stage3"] == after["stage3"],
                "stage4_identical": before["stage4"] == after["stage4"],
                "before": before["measurements"], "after": after["measurements"],
            }
            results.append(result)
            print(json.dumps(result), flush=True)
    passed = all(r["stage3_identical"] and r["stage4_identical"] for r in results)
    (args.output / "report.json").write_text(json.dumps(
        {"status": "PASS" if passed else "FAIL", "cases": results}, indent=2) + "\n")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
