#!/usr/bin/env python3
"""Run the symbolic tolerance pipeline and optional traffic projection."""

from __future__ import annotations

import argparse
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
    if stage == 1:
        command.extend(("--slicing-protocol", args.slicing_protocol))
    if stage in {1, 2}:
        command.extend(("--k", str(args.k)))
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

    pipeline = PIPELINE + ((TRAFFIC_STAGE,) if args.traffic else ())
    missing = [name for _, _, name in pipeline if not (project_root / name).is_file()]
    if missing:
        print(
            "Error: missing pipeline scripts: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    pipeline_start = time.monotonic()
    for stage, label, script_name in pipeline:
        print("=" * 80, flush=True)
        print(f"Stage {stage}/{len(pipeline)}: {label}", flush=True)
        print("=" * 80, flush=True)
        stage_start = time.monotonic()
        command = stage_command(
            stage, project_root / script_name, work_directory, args
        )
        try:
            result = subprocess.run(command, cwd=project_root, check=False)
        except KeyboardInterrupt:
            print(f"\nInterrupted during stage {stage}.", file=sys.stderr)
            return 130
        elapsed = time.monotonic() - stage_start
        if result.returncode != 0:
            print(
                f"Pipeline stopped: stage {stage} failed "
                f"with exit code {result.returncode} after {elapsed:.2f}s.",
                file=sys.stderr,
            )
            return result.returncode
        print(f"Stage {stage} completed in {elapsed:.2f}s.\n", flush=True)

    elapsed = time.monotonic() - pipeline_start
    print("=" * 80)
    print(f"Symbolic pipeline completed successfully in {elapsed:.2f}s.")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
