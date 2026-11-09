#!/usr/bin/env python3
"""
Compute subspec intersections for failure cases up to a user-specified k (AT MOST k).

This script DOES NOT do SAT/UNSAT filtering and DOES NOT infer k.

Usage:
  python3 intersect_failure_subspecs.py <failure-case-directory> --k 2

Inputs (per fail dir):
  fail*/4_subspec_files/field_level_subspecs.txt
  fail*/4_subspec_files/line_level_subspecs.txt

Outputs (under <smt_output>/failure_filter/ by default):
  - at_most_k1_cases.txt
  - at_most_k1_intersection_field_level_subspecs.txt
  - at_most_k1_intersection_line_level_subspecs.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent / '0_auto-netsubspec'))
from utils.util_file import save_field_level_subspecs, save_line_level_subspecs


RE_FAIL_DIR = re.compile(r"^fail(\d+)(?:$|_)", re.IGNORECASE)


def _iter_fail_dirs(failure_enumeration_dir: Path) -> List[Tuple[int, Path]]:
    out: List[Tuple[int, Path]] = []
    for p in failure_enumeration_dir.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name.startswith("failures_") or name.startswith("failure_") or "failure_AT" in name or "failures_AT" in name:
            continue
        m = RE_FAIL_DIR.match(name)
        if not m:
            continue
        out.append((int(m.group(1)), p))
    out.sort(key=lambda t: (t[0], t[1].name))
    return out


def _strip_from_suffix(s: str) -> str:
    # remove trailing " [from ...]" if present
    return re.sub(r"\s*\[from [^\]]+\]\s*$", "", s.strip())


def _load_field_level_subspecs(path: Path) -> Dict[str, List[str]]:
    """
    Load a field_level_subspecs.txt-format file into {config_var: [subspec_str, ...]}.
    - ignore 'empty' (treat as True)
    """
    out: Dict[str, List[str]] = {}
    if not path.exists():
        return out

    current_key: Optional[str] = None
    current_subs: List[str] = []
    subspec_line_re = re.compile(r"^\s*\d+\.\s+(.+)$")
    count_re = re.compile(r"Subspecs\s*\((\d+)\)\s*:?")

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if line.startswith("Config Variable:"):
            if current_key is not None:
                out[current_key] = current_subs
            current_key = line.replace("Config Variable:", "").strip()
            current_subs = []
        elif line.startswith("Subspecs ("):
            m = count_re.match(line)
            if not m:
                continue
            n = int(m.group(1))
            for _ in range(n):
                if i >= len(lines):
                    break
                subline = lines[i].strip()
                i += 1
                sm = subspec_line_re.match(subline)
                if not sm:
                    continue
                content = sm.group(1).strip()
                if content.lower() == "empty":
                    continue
                current_subs.append(_strip_from_suffix(content))
        else:
            continue

    if current_key is not None:
        out[current_key] = current_subs
    return out


def _load_line_level_subspecs(path: Path) -> Dict[str, List[str]]:
    """
    Load a line_level_subspecs.txt-format file into {line_group: [subspec_str, ...]}.
    - ignore 'empty' (treat as True)
    """
    out: Dict[str, List[str]] = {}
    if not path.exists():
        return out

    current_key: Optional[str] = None
    current_subs: List[str] = []
    subspec_line_re = re.compile(r"^\s*\d+\.\s+(.+)$")
    count_re = re.compile(r"Subspecs\s*\((\d+)\)\s*:?")

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if line.startswith("Line Group:"):
            if current_key is not None:
                out[current_key] = current_subs
            current_key = line.replace("Line Group:", "").strip()
            current_subs = []
        elif line.startswith("Subspecs ("):
            m = count_re.match(line)
            if not m:
                continue
            n = int(m.group(1))
            for _ in range(n):
                if i >= len(lines):
                    break
                subline = lines[i].strip()
                i += 1
                sm = subspec_line_re.match(subline)
                if not sm:
                    continue
                content = sm.group(1).strip()
                if content.lower() == "empty":
                    continue
                current_subs.append(_strip_from_suffix(content))
        else:
            continue

    if current_key is not None:
        out[current_key] = current_subs
    return out


def _logical_and_unique(constraints: Sequence[str]) -> Optional[str]:
    uniq: List[str] = []
    seen: Set[str] = set()
    for c in constraints:
        c = c.strip()
        if not c:
            continue
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    if not uniq:
        return None
    if len(uniq) == 1:
        return uniq[0]
    return " AND ".join(f"({c})" for c in uniq)


def _intersect_field_level(fail_dirs: List[Path]) -> Dict[str, Set[str]]:
    per_key_all: Dict[str, List[str]] = defaultdict(list)
    all_keys: Set[str] = set()

    for d in fail_dirs:
        f = d / "4_subspec_files" / "field_level_subspecs.txt"
        m = _load_field_level_subspecs(f)
        all_keys.update(m.keys())
        for k, subs in m.items():
            per_key_all[k].extend(subs)

    out: Dict[str, Set[str]] = {}
    for k in sorted(all_keys):
        combined = _logical_and_unique(per_key_all.get(k, []))
        out[k] = {combined} if combined else {"empty"}
    return out


def _intersect_line_level(fail_dirs: List[Path]) -> Dict[str, Set[str]]:
    per_key_all: Dict[str, List[str]] = defaultdict(list)
    all_keys: Set[str] = set()

    for d in fail_dirs:
        f = d / "4_subspec_files" / "line_level_subspecs.txt"
        m = _load_line_level_subspecs(f)
        all_keys.update(m.keys())
        for k, subs in m.items():
            per_key_all[k].extend(subs)

    out: Dict[str, Set[str]] = {}
    for k in sorted(all_keys):
        combined = _logical_and_unique(per_key_all.get(k, []))
        out[k] = {combined} if combined else {"empty"}
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Intersect subspecs for all failure cases with index <= k.")
    parser.add_argument(
        "failure_enumeration_dir",
        type=Path,
        help="Path to <smt_output>/failure_enumeration",
    )
    parser.add_argument("--k", type=int, required=True, help="Use failure cases fail0..failk (inclusive).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: <smt_output>/failure_intersection_at_most_k{k})",
    )
    args = parser.parse_args(argv)

    failure_enumeration_dir = args.failure_enumeration_dir.resolve()
    if not failure_enumeration_dir.exists():
        raise FileNotFoundError(failure_enumeration_dir)

    smt_output_dir = failure_enumeration_dir.parent
    out_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else (smt_output_dir / f"failure_intersection_at_most_k{args.k}").resolve()
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    k = args.k
    if k < 0:
        raise ValueError("--k must be >= 0")

    fail_dirs = [p for (n, p) in _iter_fail_dirs(failure_enumeration_dir) if n <= k]
    if not fail_dirs:
        raise ValueError(f"No fail dirs with index <= {k} under {failure_enumeration_dir}")

    # Save included cases
    cases_path = out_dir / f"at_most_k{k}_cases.txt"
    cases_path.write_text("\n".join(str(p) for p in fail_dirs) + "\n", encoding="utf-8")

    # Intersections
    field_inter = _intersect_field_level(fail_dirs)
    line_inter = _intersect_line_level(fail_dirs)

    field_out = out_dir / f"at_most_k{k}_intersection_field_level_subspecs.txt"
    line_out = out_dir / f"at_most_k{k}_intersection_line_level_subspecs.txt"
    save_field_level_subspecs(field_out, field_inter)
    save_line_level_subspecs(line_out, line_inter)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

