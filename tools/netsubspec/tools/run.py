#!/usr/bin/env python3
"""Run the symbolic tolerance pipeline and optional traffic projection."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import uuid
from pathlib import Path
import subprocess
import sys
import time


PIPELINE = (
    (1, "SMT slicing", "1_smt_slicer.py"),
    (2, "consistency checking", "2_consistency_checker.py"),
    (3, "branch simplification", "3_branch_simplifier.py"),
    (4, "branch intersection", "4_branch_intersection.py"),
)

TRAFFIC_STAGE = (5, "traffic subspecification", "5_traffic_subspecification.py")
FAILURE_CHECK = (6, "saved Traverse vs symbolic output verification",
                 "../auto-netsubspec-Traverse/compare_traverse_results.py")


def non_negative_integer(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def positive_integer(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def positive_float(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the four symbolic NetSubspec stages and, optionally, the "
            "traffic-engineering projection."
        )
    )
    parser.add_argument("work_directory", type=Path)
    parser.add_argument("--profile", action="store_true", help="write detailed wall/task timings")
    parser.add_argument("--consistency-workers", type=positive_integer, default=1, help="parallel consistency devices (default: 1)")
    parser.add_argument("--check-failure-intersection", action="store_true",
                        help="compare final symbolic subspecs with saved Traverse intersections; default off")
    parser.add_argument("--traverse-results", type=Path,
                        help="completed independent Traverse run; required when verification is enabled")
    parser.add_argument(
        "--k",
        required=True,
        type=non_negative_integer,
        help="at-most-k link failures used by the symbolic route output",
    )
    parser.add_argument(
        "--traffic",
        action="store_true",
        help=(
            "after the four control-plane stages, project "
            "smt_traffic_encoding.smt2 to SR-weight constraints"
        ),
    )
    parser.add_argument("--slicing-protocol", default="bgp",
                        help="stage-1 adapter (default: bgp; IS-IS reserved)")
    parser.add_argument("--z3", type=Path, help="optional Z3 executable")
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=30.0,
        help="solver timeout per query in seconds (default: 30)",
    )
    parser.add_argument(
        "-v",
        "--verbose-slicer",
        action="store_true",
        help="show verbose stage-1 slicing logs",
    )
    parser.add_argument(
        "-j",
        "--workers",
        type=positive_integer,
        help="parallel stage-3 branch workers (default: available CPUs)",
    )
    return parser.parse_args()


def stage_command(
    stage: int,
    script: Path,
    work_directory: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [sys.executable, str(script)]
    if stage == 1 and args.verbose_slicer:
        command.append("-v")
    command.append(str(work_directory))
    if stage == 6:
        command.extend(("--output", str(work_directory / "failure_intersection_check/report.json"),
                        "--traverse-results", str(args.traverse_results.resolve())))
        if args.workers is not None:
            command.extend(("--workers", str(args.workers)))
    if stage == 1:
        command.extend(("--slicing-protocol", args.slicing_protocol))
    if stage in {1, 2}:
        command.extend(("--k", str(args.k)))
    if stage == 2:
        command.extend(("--workers", str(getattr(args, "consistency_workers", 1))))
    if stage == 3 and args.workers is not None:
        command.extend(("--workers", str(args.workers)))
    if stage >= 2:
        command.extend(("--timeout", str(args.timeout)))
        if args.z3 is not None:
            command.extend(("--z3", str(args.z3.resolve())))
    return command


def main() -> int:
    args = parse_args()
    work_directory = args.work_directory.resolve()
    project_root = Path(__file__).resolve().parent.parent

    if not work_directory.is_dir():
        print(
            f"Error: work directory does not exist: {work_directory}",
            file=sys.stderr,
        )
        return 2

    if args.check_failure_intersection and (args.traverse_results is None or not (args.traverse_results / "report.json").is_file()):
        print("Error: --check-failure-intersection requires --traverse-results with a completed Traverse report.json", file=sys.stderr)
        return 2
    pipeline = PIPELINE + ((TRAFFIC_STAGE,) if args.traffic else ())
    pipeline += ((FAILURE_CHECK,) if args.check_failure_intersection else ())
    missing = [name for _, _, name in pipeline if not (project_root / name).is_file()]
    if missing:
        print(
            "Error: missing pipeline scripts: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    pipeline_start = time.monotonic()
    measured_stages = []
    official_wall = 0.0
    optional_wall = 0.0
    runtime_base = work_directory / "runtime_profile"
    runtime_dir = runtime_base / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    if args.profile:
        from profile_runtime import write_summary
        runtime_dir.mkdir(parents=True, exist_ok=True)
        write_summary(runtime_dir, measured_stages, 0.0)
    check_state = work_directory / "failure_intersection_check_status.json"
    def write_check_state(status):
        check_state.write_text(json.dumps({
            "enabled": args.check_failure_intersection, "status": status,
            "report": "failure_intersection_check/report.json" if args.check_failure_intersection else None,
            "reference": str(args.traverse_results.resolve()) if args.traverse_results else None,
            "method": "compare-existing-traverse-output",
        }, indent=2) + "\n")
    write_check_state("PENDING" if args.check_failure_intersection else "DISABLED")
    for ordinal, (stage, label, script_name) in enumerate(pipeline, 1):
        print("=" * 80, flush=True)
        print(f"Stage {ordinal}/{len(pipeline)}: {label}", flush=True)
        print("=" * 80, flush=True)
        stage_start = time.monotonic()
        command = stage_command(
            stage, project_root / script_name, work_directory, args
        )
        if args.profile:
            command = [sys.executable, str(project_root / "tools/profile_runtime.py"),
                       "--worker", "--stage", str(stage), "--output", str(runtime_dir / f"stage_{stage}.json"),
                       "--arguments", json.dumps(command[2:])]
        try:
            result = subprocess.run(command, cwd=project_root, check=False)
        except KeyboardInterrupt:
            if args.check_failure_intersection:
                write_check_state("INTERRUPTED")
            print(f"\nInterrupted during stage {ordinal} ({label}).", file=sys.stderr)
            return 130
        elapsed = time.monotonic() - stage_start
        if stage == 6:
            optional_wall += elapsed
        else:
            official_wall += elapsed
        if args.profile:
            workers = (args.consistency_workers if stage == 2 else (args.workers or "auto") if stage in {3,6} else 1)
            measured_stages.append(dict(stage=stage,label=label,wall_seconds=elapsed,workers=workers,returncode=result.returncode))
            write_summary(runtime_dir, measured_stages, time.monotonic() - pipeline_start)
            (runtime_base / "latest.json").write_text(json.dumps({"run_directory": str(runtime_dir),
                "returncode": result.returncode, "completed_stages": len(measured_stages)}, indent=2)+"\n")
            print(f"Runtime report: {runtime_dir / 'runtime_report.txt'}", flush=True)
        if stage == 6:
            write_check_state("PASS" if result.returncode == 0 else "FAIL")
        if result.returncode != 0:
            if stage == 6:
                print("Optional output verification failed; completed symbolic pipeline outputs are retained.", file=sys.stderr)
            if stage != 6 and args.check_failure_intersection:
                write_check_state("NOT_RUN_UPSTREAM_FAILED")
            print(
                f"Pipeline stopped: stage {ordinal} ({label}) failed "
                f"with exit code {result.returncode} after {elapsed:.2f}s.",
                file=sys.stderr,
            )
            return result.returncode
        print(f"Stage {stage} completed in {elapsed:.2f}s.\n", flush=True)

    elapsed = time.monotonic() - pipeline_start
    print("=" * 80)
    print(f"Official pipeline completed in {official_wall:.2f}s (validation excluded).")
    print(f"Optional verification: {optional_wall:.2f}s; observed command wall: {elapsed:.2f}s.")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
