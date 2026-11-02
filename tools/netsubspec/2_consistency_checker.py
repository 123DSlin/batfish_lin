#!/usr/bin/env python3
"""Run the formal symbolic-route/device-encoding consistency gate."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from consistency.checker import ConsistencyChecker, ConsistencyCheckerError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build and solve every property-relevant, k-pruned MAIN consistency "
            "seed. Routers and prefixes are discovered from the symbolic output."
        )
    )
    parser.add_argument("work_directory", type=Path)
    parser.add_argument("--k", required=True, type=int, help="at-most-k link failures")
    parser.add_argument("--router", help="debug only: check one discovered device")
    parser.add_argument("--prefix", help="debug only: check one property destination")
    parser.add_argument("--vrf", default="default")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--z3", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        checker = ConsistencyChecker(
            args.work_directory,
            z3_path=args.z3,
            timeout_seconds=args.timeout,
        )
        report = checker.run(
            k=args.k,
            router=args.router,
            prefix=args.prefix,
            vrf=args.vrf,
            output_directory=args.output,
        )
    except (ConsistencyCheckerError, OSError, ValueError) as error:
        print(f"Consistency checker initialization failed: {error}", file=sys.stderr)
        return 2

    output = (
        args.output.resolve()
        if args.output is not None
        else args.work_directory.resolve() / "2_consistency_check"
    )
    print(report.to_readable_text(), end="")
    print(f"Summary: {output / 'consistency_report.txt'}")
    print(f"Full details: {output / 'consistency_report.json'}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
