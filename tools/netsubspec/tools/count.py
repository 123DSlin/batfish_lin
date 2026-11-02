#!/usr/bin/env python3
"""
Count non-empty vs all-empty subspec entries in field_level / line_level files.

Input: a directory.

If it contains smt_* subdirectories, scan each <subdir>/4_subspec_files and write
per-subdir stats plus cross-subdir averages to counts_NNNN.txt and counts.txt
(same pattern as times_NNNN.txt / times.txt).

If there are no smt_* subdirectories, treat the input directory itself as one case
(look for <dir>/4_subspec_files).

For each Config Variable (field level) or Line Group (line level) block:
  - If every listed subspec is "empty"  -> all-empty entry
  - If at least one subspec is non-empty -> non-empty entry

Reported metrics (field_level, line_level, total):
  - non_empty_subspec: entries with at least one non-empty subspec
  - all_subspec: total entries (non-empty + all-empty)
  - non_empty_pct: 100 * non_empty / all_subspec, rounded to 4 decimal places
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, NamedTuple

SUBSPEC_COUNT_RE = re.compile(r"Subspecs\s*\((\d+)\)\s*:?")
SUBSPEC_LINE_RE = re.compile(r"^\s*\d+\.\s+(.+)$")
SEPARATOR_RE = re.compile(r"^-{50}$")


class LevelStats(NamedTuple):
    all_empty: set[str]
    non_empty: set[str]

    @property
    def non_empty_subspec(self) -> int:
        return len(self.non_empty)

    @property
    def all_subspec(self) -> int:
        return len(self.all_empty) + len(self.non_empty)

    @property
    def non_empty_pct(self) -> float:
        total = self.all_subspec
        if total == 0:
            return 0.0
        return round(100.0 * self.non_empty_subspec / total, 4)


@dataclass
class CountMetrics:
    non_empty_subspec: int | float
    all_subspec: int | float
    non_empty_pct: float


@dataclass
class CaseCounts:
    name: str
    field_level: LevelStats
    line_level: LevelStats

    @property
    def total(self) -> CountMetrics:
        non_empty = self.field_level.non_empty_subspec + self.line_level.non_empty_subspec
        total = self.field_level.all_subspec + self.line_level.all_subspec
        pct = round(100.0 * non_empty / total, 4) if total else 0.0
        return CountMetrics(non_empty, total, pct)


def is_empty_subspec(content: str) -> bool:
    return content.strip().lower() == "empty"


def parse_subspec_file(file_path: Path, entry_label: str) -> LevelStats:
    all_empty: set[str] = set()
    non_empty: set[str] = set()

    current_name: str | None = None
    subspecs: list[str] = []

    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        i += 1

        if stripped.startswith(entry_label):
            current_name = stripped[len(entry_label) :].strip()
            subspecs = []
            continue

        match = SUBSPEC_COUNT_RE.match(stripped)
        if match and current_name is not None:
            expected = int(match.group(1))
            subspecs = []
            for _ in range(expected):
                if i >= len(lines):
                    break
                sub_line = lines[i].strip()
                i += 1
                sub_match = SUBSPEC_LINE_RE.match(sub_line)
                if sub_match:
                    subspecs.append(sub_match.group(1).strip())
            continue

        if SEPARATOR_RE.match(stripped):
            if current_name is not None and subspecs:
                if all(is_empty_subspec(s) for s in subspecs):
                    all_empty.add(current_name)
                else:
                    non_empty.add(current_name)
            current_name = None
            subspecs = []

    return LevelStats(all_empty, non_empty)


def collect_stats(directory: Path, pattern: str, entry_label: str) -> LevelStats:
    merged_all_empty: set[str] = set()
    merged_non_empty: set[str] = set()

    for file_path in sorted(directory.glob(pattern)):
        stats = parse_subspec_file(file_path, entry_label)
        merged_all_empty.update(stats.all_empty)
        merged_non_empty.update(stats.non_empty)

    return LevelStats(merged_all_empty, merged_non_empty)


def count_subspec_dir(subspec_dir: Path) -> tuple[LevelStats, LevelStats]:
    if not subspec_dir.is_dir():
        raise FileNotFoundError(f"Missing directory: {subspec_dir}")

    field_level = collect_stats(subspec_dir, "field_level_subspecs_*.txt", "Config Variable:")
    line_level = collect_stats(subspec_dir, "line_level_subspecs_*.txt", "Line Group:")
    return field_level, line_level


def find_smt_subdirs(base_dir: Path) -> list[Path]:
    return sorted(
        d for d in base_dir.iterdir()
        if d.is_dir() and d.name.startswith("smt_")
    )


def resolve_cases(base_dir: Path) -> list[tuple[str, Path]]:
    smt_subdirs = find_smt_subdirs(base_dir)
    if smt_subdirs:
        return [(d.name, d / "4_subspec_files") for d in smt_subdirs]

    subspec_dir = base_dir / "4_subspec_files"
    if subspec_dir.is_dir():
        return [(base_dir.name, subspec_dir)]

    return []


def get_next_counts_file(base_dir: Path) -> Path:
    max_found = 0
    for n in range(1, 10000):
        path = base_dir / f"counts_{n:04d}.txt"
        if path.exists():
            max_found = n
    return base_dir / f"counts_{max_found + 1:04d}.txt"


def format_level_block(prefix: str, stats: LevelStats | CountMetrics) -> list[str]:
    if isinstance(stats, LevelStats):
        non_empty = stats.non_empty_subspec
        total = stats.all_subspec
        pct = stats.non_empty_pct
    else:
        non_empty = stats.non_empty_subspec
        total = stats.all_subspec
        pct = stats.non_empty_pct
    if isinstance(non_empty, float):
        non_empty_s = f"{non_empty:.4f}"
        total_s = f"{total:.4f}"
    else:
        non_empty_s = str(non_empty)
        total_s = str(total)
    return [
        f"{prefix}:",
        f"  non_empty_subspec={non_empty_s}",
        f"  all_subspec={total_s}",
        f"  non_empty_pct={pct:.4f}",
    ]


@dataclass
class AverageMetrics:
    non_empty_subspec: float
    all_subspec: float
    non_empty_pct: float


def average_metrics(items: Iterable[LevelStats | CountMetrics]) -> AverageMetrics:
    values = list(items)
    if not values:
        return AverageMetrics(0.0, 0.0, 0.0)
    n = len(values)

    def non_empty(v: LevelStats | CountMetrics) -> int | float:
        return v.non_empty_subspec if isinstance(v, CountMetrics) else v.non_empty_subspec

    def total(v: LevelStats | CountMetrics) -> int | float:
        return v.all_subspec if isinstance(v, CountMetrics) else v.all_subspec

    def pct(v: LevelStats | CountMetrics) -> float:
        return v.non_empty_pct if isinstance(v, CountMetrics) else v.non_empty_pct

    return AverageMetrics(
        non_empty_subspec=round(sum(non_empty(v) for v in values) / n, 4),
        all_subspec=round(sum(total(v) for v in values) / n, 4),
        non_empty_pct=round(sum(pct(v) for v in values) / n, 4),
    )


def format_average_block(prefix: str, avg: AverageMetrics) -> list[str]:
    return [
        f"{prefix}:",
        f"  non_empty_subspec={avg.non_empty_subspec:.4f}",
        f"  all_subspec={avg.all_subspec:.4f}",
        f"  non_empty_pct={avg.non_empty_pct:.4f}",
    ]


def build_report_lines(base_dir: Path, cases: list[CaseCounts]) -> list[str]:
    lines = [
        "=" * 80,
        "Subspec Count Results",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Work dir: {base_dir}",
        "=" * 80,
        "",
    ]

    for case in cases:
        lines.append("[DIRECTORY]")
        lines.append(f"name={case.name}")
        lines.extend(format_level_block("field_level", case.field_level))
        lines.extend(format_level_block("line_level", case.line_level))
        lines.extend(format_level_block("total", case.total))
        lines.append("")

    if len(cases) > 1:
        lines.append("[AVERAGE]")
        lines.append(f"cases={len(cases)}")
        lines.extend(
            format_average_block(
                "field_level",
                average_metrics(c.field_level for c in cases),
            )
        )
        lines.extend(
            format_average_block(
                "line_level",
                average_metrics(c.line_level for c in cases),
            )
        )
        lines.extend(
            format_average_block(
                "total",
                average_metrics(c.total for c in cases),
            )
        )
        lines.append("")

    return lines


def append_to_counts_log(base_dir: Path, preserved_name: str, body_lines: list[str]) -> Path:
    dest = base_dir / "counts.txt"
    if not dest.exists():
        with open(dest, "w", encoding="utf-8") as f:
            f.write(f"Subspec count log\nWork dir: {base_dir}\n")

    with open(dest, "a", encoding="utf-8") as f:
        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write(f"Recorded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Source: {preserved_name}\n")
        f.write("=" * 80 + "\n")
        f.write("\n".join(body_lines))
        if body_lines and body_lines[-1] != "":
            f.write("\n")

    return dest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count subspec entries and write counts_NNNN.txt / counts.txt."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory with smt_* subdirs, or a single smt case directory",
    )
    args = parser.parse_args()
    base_dir = args.directory.resolve()

    if not base_dir.is_dir():
        print(f"Error: not a directory: {base_dir}", file=sys.stderr)
        sys.exit(1)

    case_targets = resolve_cases(base_dir)
    if not case_targets:
        print(
            f"Error: no smt_* subdirectories and no 4_subspec_files under {base_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    cases: list[CaseCounts] = []
    for name, subspec_dir in case_targets:
        try:
            field_level, line_level = count_subspec_dir(subspec_dir)
        except FileNotFoundError as exc:
            print(f"Warning: skipping {name}: {exc}", file=sys.stderr)
            continue
        cases.append(CaseCounts(name=name, field_level=field_level, line_level=line_level))

    if not cases:
        print("Error: no cases could be counted", file=sys.stderr)
        sys.exit(1)

    report_lines = build_report_lines(base_dir, cases)
    report_text = "\n".join(report_lines)

    counts_file = get_next_counts_file(base_dir)
    with open(counts_file, "w", encoding="utf-8") as f:
        f.write(report_text)
        if not report_text.endswith("\n"):
            f.write("\n")

    counts_log = append_to_counts_log(base_dir, counts_file.name, report_lines)

    print(report_text)
    print(f"Results written to: {counts_file}")
    print(f"Results appended to: {counts_log}")


if __name__ == "__main__":
    main()
