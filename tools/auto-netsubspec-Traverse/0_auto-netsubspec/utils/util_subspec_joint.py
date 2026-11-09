"""
Joint multi-location subspecification utilities.

For a set of Config_* locations in 0_multiple_locations.txt:
  1. For each AG slice (complete_forward/reverse_{host}), find which locations
     appear in that slice file content (not by Config_{device}_ name prefix).
  2. On that slice, comment all matched equalities together, check empty
     (reverse impact), then if non-empty compute simplification goal (forward).
  3. Partition the slice locations by connected components in that goal:
     configs in the same component form one joint group; disconnected configs
     stay as separate (singleton) groups — not forced into one AND.
  4. Cross-slice AND merge only when necessary: the same inseparable multi-config
     set (size >= 2) appears as a non-empty group on two or more slices.
  5. Output ({output_dir}/joint_multi_location_subspecs.txt):
       - per-slice blocks ``joint subspec (slice H):`` (singletons separate;
         connected configs share one subspec)
       - final summary ``joint subspec:`` aggregating those presentation entries
         (necessary cross-slice AND preferred for multi-config sets).

Callers choose stage-numbered dirs (e.g. 4_* vs 5_*) via
``intermediate_dir_name`` / ``output_dir_name``; defaults match script 4.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from utils.util_file import (
    find_metadata_file,
    load_target_dst_ip,
    save_synthesis_metadata,
)
from utils.util_keyword import (
    JOINT_SUBSPEC_NORM_COUNT,
    JOINT_SUBSPEC_OUTPUT_FILE,
    MULTIPLE_LOCATIONS_FILE,
)
from utils.util_norm import normalize_subspec
from utils.util_smt import (
    ModelConfigEqualitiesStore,
    extract_config_constraints_from_z3_goal,
    partition_configs_by_z3_goal_connectivity,
    strip_subspec_suffixes,
    subspec_string_to_list,
)
from utils.util_subspec import (
    ConfigLocationVar,
    ImpactCheckWriteMode,
    check_impact_forward,
    comment_out_config_vars_to_temp,
    is_nonempty_subspec,
)

logger = logging.getLogger(__name__)

AG_DIR_NAME = "3_assume_guarantee_test"
SLICED_DIR_NAME = "2_sliced_device_smt_encoding"
# Defaults for 4_subspec_simplifier.py; scripts 5+ pass their own stage dirs.
DEFAULT_JOINT_INTERMEDIATE_DIR = "4_intermediate_subspec_joint_files"
DEFAULT_JOINT_OUTPUT_DIR = "4_subspec_files"

CONFIG_EQ_RE = re.compile(r"^;?\s*\(assert \(= (Config_\S+) (\S+)\)\)")
SIMPLIFY_APPLY = (
    "; (check-sat)\n"
    "(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))"
)


@dataclass
class JointGroupResult:
    """One joint/singleton group (per-slice or necessary multi-slice AND)."""
    hosts: List[str]
    config_names: List[str]
    subspec: str  # "empty" or constraint string joined by " AND "

    @property
    def is_multi_config(self) -> bool:
        return len(self.config_names) >= 2


@dataclass
class SliceJointResult:
    """Joint subspec result for one AG slice host (possibly multiple CC groups)."""
    host: str
    locations: List[ConfigLocationVar]
    groups: List[JointGroupResult] = field(default_factory=list)

    @property
    def is_empty_slice(self) -> bool:
        return (not self.groups) or all(
            not is_nonempty_subspec(g.subspec) for g in self.groups
        )


@dataclass
class JointMultiLocationResult:
    """Full joint multi-location run result."""
    locations: List[str]
    per_slice: List[SliceJointResult] = field(default_factory=list)
    empty_configs: List[str] = field(default_factory=list)
    # Necessary AND merges: same inseparable multi-config set on >= 2 slices.
    merged_groups: List[JointGroupResult] = field(default_factory=list)

    @property
    def empty_slices(self) -> List[SliceJointResult]:
        return [r for r in self.per_slice if r.is_empty_slice]

    @property
    def nonempty_slices(self) -> List[SliceJointResult]:
        return [r for r in self.per_slice if not r.is_empty_slice]


def collect_empty_configs(
    locations: Sequence[str],
    per_slice: Sequence[SliceJointResult],
) -> List[str]:
    """Configs whose every hitting slice has only empty group(s) for that config (or never hit)."""
    empty: List[str] = []
    for name in locations:
        hit_slices = [
            r for r in per_slice if any(v.name == name for v in r.locations)
        ]
        if not hit_slices:
            empty.append(name)
            continue
        nonempty_hit = False
        for r in hit_slices:
            groups_with_name = [g for g in r.groups if name in g.config_names]
            if any(is_nonempty_subspec(g.subspec) for g in groups_with_name):
                nonempty_hit = True
                break
        if not nonempty_hit:
            empty.append(name)
    return empty


def load_multiple_locations(work_dir: Path) -> List[str]:
    """Load Config_* names from 0_multiple_locations.txt (one per line)."""
    path = work_dir / MULTIPLE_LOCATIONS_FILE
    if not path.exists():
        raise FileNotFoundError(f"Multiple locations file not found: {path}")

    locations: List[str] = []
    seen: Set[str] = set()
    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            if not name.startswith("Config_"):
                logger.warning(
                    "Skip line %d in %s: expected Config_* name, got %s",
                    line_num,
                    path.name,
                    name,
                )
                continue
            if name in seen:
                continue
            seen.add(name)
            locations.append(name)
    if not locations:
        raise ValueError(f"No Config_* locations found in {path}")
    logger.info("Loaded %d locations from %s", len(locations), path)
    return locations


def list_ag_slice_hosts(work_dir: Path, device_filter: Optional[str] = None) -> List[str]:
    """Return sorted AG slice host names from complete_reverse_*.smt2 (fallback: sliced_*)."""
    ag_dir = work_dir / AG_DIR_NAME
    hosts: List[str] = []
    if ag_dir.exists():
        for path in sorted(ag_dir.glob("complete_reverse_*.smt2")):
            host = path.name[len("complete_reverse_") : -len(".smt2")]
            if host:
                hosts.append(host)
    if not hosts:
        sliced_dir = work_dir / SLICED_DIR_NAME
        if sliced_dir.exists():
            for path in sorted(sliced_dir.glob("sliced_*_smt_encoding.smt2")):
                m = re.search(r"sliced_(.+?)_smt_encoding\.smt2", path.name)
                if m:
                    hosts.append(m.group(1))

    if device_filter is not None:
        if device_filter not in hosts:
            raise ValueError(
                f"Device '{device_filter}' not found among AG/sliced hosts: {hosts}"
            )
        hosts = [device_filter]

    if not hosts:
        raise FileNotFoundError(
            f"No AG slice hosts found under {ag_dir} (or {work_dir / SLICED_DIR_NAME})"
        )
    return hosts


def locations_in_slice(
    locations: Sequence[str],
    work_dir: Path,
    host: str,
) -> List[str]:
    """Subset of locations that appear in this slice's AG reverse (prefer) or sliced file."""
    reverse_path = work_dir / AG_DIR_NAME / f"complete_reverse_{host}.smt2"
    forward_path = work_dir / AG_DIR_NAME / f"complete_forward_{host}.smt2"
    sliced_path = work_dir / SLICED_DIR_NAME / f"sliced_{host}_smt_encoding.smt2"

    # Prefer complete_reverse content; also accept forward/sliced if reverse missing.
    scan_paths = [p for p in (reverse_path, forward_path, sliced_path) if p.exists()]
    if not scan_paths:
        return []

    # Use reverse if present, else first available — ownership by content of the
    # primary AG reverse file when available (matches 4_ impact baseline).
    primary = reverse_path if reverse_path.exists() else scan_paths[0]
    text = primary.read_text()
    return [name for name in locations if name in text]


def resolve_config_vars_in_file(
    smt_path: Path,
    config_names: Sequence[str],
) -> List[ConfigLocationVar]:
    """Resolve (= Config_xxx value) for the given names from an SMT file."""
    wanted = set(config_names)
    found: Dict[str, str] = {}
    if not smt_path.exists():
        return []
    with open(smt_path, "r") as f:
        for line in f:
            m = CONFIG_EQ_RE.search(line.strip())
            if not m:
                continue
            name, value = m.group(1), m.group(2)
            if name in wanted and name not in found:
                found[name] = value
    missing = [n for n in config_names if n not in found]
    if missing:
        logger.warning(
            "Could not resolve equality values in %s for: %s",
            smt_path.name,
            ", ".join(missing),
        )
    # Preserve input order
    return [
        ConfigLocationVar(name=n, value=found[n])
        for n in config_names
        if n in found
    ]


def _replace_check_sat_with_simplify(content: str) -> str:
    if "(check-sat)" in content:
        return content.replace("(check-sat)", SIMPLIFY_APPLY)
    return content.rstrip() + "\n" + SIMPLIFY_APPLY + "\n"


def _restore_propagated_equalities(
    subspec: Optional[str],
    config_vars: Sequence[ConfigLocationVar],
    model_store: Optional[ModelConfigEqualitiesStore] = None,
) -> str:
    """Ensure every location Config_* appears; append equality if missing.

    For misconfiguration repair (script 7), pass ``model_store`` with get-model /
    MaxSMT values so eliminated vars use repair equalities, not the original
    (possibly wrong) Config_* values from the SMT file.
    """
    if subspec:
        parts = subspec_string_to_list(subspec)
    else:
        parts = []

    if model_store is not None:
        model_store.append_missing_to_subspec(parts, config_vars, info=logger.info)
        if parts:
            return " AND ".join(parts)
        return " AND ".join(model_store.equality_for(v.name) for v in config_vars)

    for config_var in config_vars:
        if any(config_var.name in part for part in parts):
            continue
        original = f"(= {config_var.name} {config_var.value})"
        parts.append(original)
        logger.info(
            "    Added original constraint for replaced variable %s: %s",
            config_var.name,
            original,
        )

    if parts:
        return " AND ".join(parts)

    # Fallback: all original equalities
    return " AND ".join(f"(= {v.name} {v.value})" for v in config_vars)


def _run_z3_simplify(smt2_path: Path, log_label: str) -> str:
    try:
        result = subprocess.run(["z3", str(smt2_path)], capture_output=True, text=True)
        output = result.stdout.strip()
        if result.stderr.strip():
            logger.warning("    Z3 stderr: %s", result.stderr.strip())
        if result.returncode != 0:
            logger.warning("    Z3 return code: %d", result.returncode)
        logger.info("    Z3 Simplification Results for %s:", log_label)
        logger.info("    " + "=" * 60)
        for line in output.split("\n"):
            logger.info("    %s", line)
        logger.info("    " + "=" * 60)
        return output
    except Exception as e:
        logger.error("    Error running Z3: %s", e)
        return ""


def _group_safe_name(config_names: Sequence[str], index: int) -> str:
    """Short filesystem-safe identifier for a joint group."""
    if len(config_names) == 1:
        raw = config_names[0]
    else:
        raw = f"g{index}_{len(config_names)}cfgs"
    safe = re.sub(r"[^\w.-]", "_", raw)
    return safe[:120] if len(safe) > 120 else safe


def _normalize_joint_group_subspec(
    subspec: str,
    host: str,
    safe_name: str,
    compute_smt2_path: Path,
    intermediate_dir: Path,
    *,
    target_dst_ip: Optional[str],
    verbose: bool,
) -> str:
    """Normalize a non-empty per-group joint subspec (same path as line-level)."""
    if not is_nonempty_subspec(subspec):
        return subspec

    metadata_type = "joint"
    try:
        save_synthesis_metadata(
            host, safe_name, str(compute_smt2_path), intermediate_dir, metadata_type
        )
        metadata_file = find_metadata_file(
            safe_name, host, metadata_type, intermediate_dir
        )
        if not metadata_file:
            logger.warning(
                "  Slice %s group %s: joint metadata not found after save, skip normalization",
                host,
                safe_name,
            )
            return subspec

        core, suffix = strip_subspec_suffixes(subspec)
        normalized = normalize_subspec(
            core,
            metadata_file,
            safe_name,
            is_field_level=False,
            is_pair=False,
            target_dst_ip=target_dst_ip,
            max_iterations=JOINT_SUBSPEC_NORM_COUNT,
            verbose=verbose,
            temp_dir=intermediate_dir,
        )
        normalized = normalized + suffix
        logger.info(
            "  Slice %s group %s: normalized joint subspec: %s",
            host,
            safe_name,
            normalized,
        )
        return normalized
    except Exception as e:
        logger.warning(
            "  Slice %s group %s: failed to normalize joint subspec: %s",
            host,
            safe_name,
            e,
        )
        return subspec


def compute_slice_joint_subspec(
    work_dir: Path,
    host: str,
    config_vars: Sequence[ConfigLocationVar],
    intermediate_dir: Path,
    *,
    keep_intermediate: bool = False,
    target_dst_ip: Optional[str] = None,
    verbose: bool = False,
    model_store: Optional[ModelConfigEqualitiesStore] = None,
) -> List[JointGroupResult]:
    """Comment all config_vars on this slice; return CC-partitioned joint groups."""
    if not config_vars:
        return []

    reverse_path = work_dir / AG_DIR_NAME / f"complete_reverse_{host}.smt2"
    forward_path = work_dir / AG_DIR_NAME / f"complete_forward_{host}.smt2"
    if not os.path.exists(reverse_path):
        logger.error("Complete reverse not found for slice %s: %s", host, reverse_path)
        return [
            JointGroupResult(
                hosts=[host],
                config_names=[v.name for v in config_vars],
                subspec="empty",
            )
        ]
    if not os.path.exists(forward_path):
        logger.error("Complete forward not found for slice %s: %s", host, forward_path)
        return [
            JointGroupResult(
                hosts=[host],
                config_names=[v.name for v in config_vars],
                subspec="empty",
            )
        ]

    names = [v.name for v in config_vars]
    name_to_var = {v.name: v for v in config_vars}
    logger.info(
        "  Slice %s: joint locations (%d): %s",
        host,
        len(names),
        ", ".join(names),
    )

    # 1) Empty check on reverse (comment all equalities together)
    has_impact = check_impact_forward(
        reverse_path,
        config_vars,
        intermediate_dir,
        host,
        "joint_all",
        baseline_has_check_sat=True,
        write_mode=ImpactCheckWriteMode.TEMP_WITH_DEBUG,
        cleanup_after=not keep_intermediate,
    )
    if not has_impact:
        logger.info("  Slice %s: empty subspec (no impact)", host)
        # Present each config separately when the whole-slice impact check is empty.
        return [
            JointGroupResult(hosts=[host], config_names=[n], subspec="empty")
            for n in names
        ]

    # 2) Simplification goal on forward (still comment all together)
    temp_path = comment_out_config_vars_to_temp(forward_path, config_vars, comment=True)
    try:
        with open(temp_path, "r") as f:
            content = f.read()
        content = _replace_check_sat_with_simplify(content)
        out_file = intermediate_dir / f"compute_joint_subspec_from_{host}_joint_all.smt2"
        with open(out_file, "w") as f:
            f.write(content)
        logger.info("    Compute joint subspec file saved to: %s", out_file)

        z3_out = _run_z3_simplify(out_file, f"joint@{host}")

        # 3) Partition by connected components in the goal
        partitions = partition_configs_by_z3_goal_connectivity(z3_out, names)
        logger.info(
            "  Slice %s: goal connectivity partitions (%d): %s",
            host,
            len(partitions),
            "; ".join("{" + ", ".join(g) + "}" for g in partitions),
        )

        groups: List[JointGroupResult] = []
        for idx, group_names in enumerate(partitions):
            group_vars = [name_to_var[n] for n in group_names if n in name_to_var]
            if not group_vars:
                continue
            safe_name = _group_safe_name(group_names, idx)
            extracted = extract_config_constraints_from_z3_goal(
                z3_out, set(group_names)
            )
            subspec = _restore_propagated_equalities(
                extracted, group_vars, model_store=model_store
            )
            logger.info(
                "  Slice %s group %s (%s): pre-norm: %s",
                host,
                safe_name,
                ", ".join(group_names),
                subspec,
            )
            subspec = _normalize_joint_group_subspec(
                subspec,
                host,
                safe_name,
                out_file,
                intermediate_dir,
                target_dst_ip=target_dst_ip,
                verbose=verbose,
            )
            groups.append(
                JointGroupResult(
                    hosts=[host],
                    config_names=list(group_names),
                    subspec=subspec,
                )
            )

        if not keep_intermediate and out_file.exists():
            try:
                os.unlink(out_file)
            except OSError:
                pass
        return groups
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def merge_necessary_cross_slice_groups(
    per_slice: Sequence[SliceJointResult],
) -> List[JointGroupResult]:
    """AND groups only when the same inseparable multi-config set hits >= 2 slices.

    Singletons are never cross-AND'd. A multi-config set that appears on only one
    slice stays as that per-slice group (no extra merged entry).
    """
    by_key: Dict[frozenset, List[JointGroupResult]] = defaultdict(list)
    for slice_result in per_slice:
        for group in slice_result.groups:
            if not is_nonempty_subspec(group.subspec):
                continue
            if not group.is_multi_config:
                continue
            key = frozenset(group.config_names)
            by_key[key].append(group)

    merged: List[JointGroupResult] = []
    for key, groups in by_key.items():
        hosts = sorted({h for g in groups for h in g.hosts})
        if len(hosts) < 2:
            continue
        parts: List[str] = []
        seen: Set[str] = set()
        for group in groups:
            for part in subspec_string_to_list(group.subspec):
                if part not in seen:
                    seen.add(part)
                    parts.append(part)
        config_order = list(groups[0].config_names)
        for name in key:
            if name not in config_order:
                config_order.append(name)
        formula = " AND ".join(parts) if parts else "empty"
        merged.append(
            JointGroupResult(hosts=hosts, config_names=config_order, subspec=formula)
        )
        logger.info(
            "Necessary cross-slice merge for {%s} across %s",
            ", ".join(config_order),
            ", ".join(hosts),
        )
    return merged


_DOT_SEP = "." * 50
_DASH_SEP = "-" * 50


def _expand_groups_for_presentation(
    groups: Sequence[JointGroupResult],
) -> List[JointGroupResult]:
    """Empty multi-config groups become per-config empties; nonempty groups stay intact."""
    expanded: List[JointGroupResult] = []
    for group in groups:
        if is_nonempty_subspec(group.subspec):
            expanded.append(group)
            continue
        for name in group.config_names:
            expanded.append(
                JointGroupResult(
                    hosts=list(group.hosts),
                    config_names=[name],
                    subspec="empty",
                )
            )
    return expanded


def _format_section_entries(
    title: str,
    groups: Sequence[JointGroupResult],
) -> List[str]:
    """Format one titled section matching the UI layout.

    Singleton (empty or not)::

        Config_xxx
        Subspecs (1):
          1. empty|formula
        ..................................................   # if more entries follow

    Multi-config nonempty::

        Config_yyy1
        Config_yyy2
        ..................................................
        Subspecs (1):
          1. formula

    Section ends with ``--------------------------------------------------``.
    """
    lines: List[str] = [title]
    entries = _expand_groups_for_presentation(groups)
    if not entries:
        lines.append("(none)")
        lines.append(_DASH_SEP)
        lines.append("")
        return lines

    for idx, group in enumerate(entries):
        body = group.subspec if is_nonempty_subspec(group.subspec) else "empty"
        multi_nonempty = group.is_multi_config and is_nonempty_subspec(group.subspec)

        for name in group.config_names:
            lines.append(name)

        if multi_nonempty:
            lines.append(_DOT_SEP)
            lines.append("Subspecs (1):")
            lines.append(f"  1. {body}")
        else:
            lines.append("Subspecs (1):")
            lines.append(f"  1. {body}")

        if idx < len(entries) - 1:
            lines.append(_DOT_SEP)
        else:
            lines.append(_DASH_SEP)
            lines.append("")
    return lines


def _collect_final_summary_groups(
    result: JointMultiLocationResult,
) -> List[JointGroupResult]:
    """Final ``joint subspec:`` entries: empties + nonempty (merge preferred).

    Order: locations order for empties, then necessary merges, then remaining
    per-slice nonempty groups not covered by a merge.
    """
    empty_names = list(result.empty_configs)
    empty_set = set(empty_names)
    summary: List[JointGroupResult] = [
        JointGroupResult(hosts=[], config_names=[n], subspec="empty")
        for n in empty_names
    ]

    merged_keys: Set[frozenset] = set()
    for group in result.merged_groups:
        if not is_nonempty_subspec(group.subspec):
            continue
        summary.append(group)
        merged_keys.add(frozenset(group.config_names))

    for slice_result in result.per_slice:
        for group in slice_result.groups:
            if not is_nonempty_subspec(group.subspec):
                continue
            key = frozenset(group.config_names)
            if key in merged_keys and group.is_multi_config:
                continue
            if group.config_names and all(n in empty_set for n in group.config_names):
                continue
            summary.append(group)
    return summary


def format_joint_result(result: JointMultiLocationResult) -> str:
    """Format per-slice joints, then a final aggregated ``joint subspec:`` section."""
    lines: List[str] = []
    lines.append("Joint Subspecs")
    lines.append("==============")
    lines.append("")

    if not result.per_slice:
        lines.append("No slice contained any of the locations.")
        lines.append("")
        return "\n".join(lines)

    for slice_result in result.per_slice:
        title = f"joint subspec (slice {slice_result.host}):"
        groups = slice_result.groups
        if not groups:
            groups = [
                JointGroupResult(
                    hosts=[slice_result.host],
                    config_names=[v.name for v in slice_result.locations],
                    subspec="empty",
                )
            ]
        lines.extend(_format_section_entries(title, groups))

    lines.extend(
        _format_section_entries("joint subspec:", _collect_final_summary_groups(result))
    )
    return "\n".join(lines)


def save_joint_result(
    work_dir: Path,
    result: JointMultiLocationResult,
    *,
    output_dir_name: str = DEFAULT_JOINT_OUTPUT_DIR,
) -> Path:
    """Write joint result under ``{work_dir}/{output_dir_name}/{JOINT_SUBSPEC_OUTPUT_FILE}``."""
    out_dir = work_dir / output_dir_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / JOINT_SUBSPEC_OUTPUT_FILE
    with open(out_path, "w") as f:
        f.write(format_joint_result(result))
    logger.info("Joint multi-location subspecs saved to: %s", out_path)
    return out_path


def _compute_per_slice_joint(
    work_path: Path,
    host: str,
    loc_names: Sequence[str],
    intermediate_dir: Path,
    *,
    target_dst_ip: Optional[str],
    verbose: bool,
    model_store: Optional[ModelConfigEqualitiesStore] = None,
) -> SliceJointResult:
    """Resolve equalities and compute joint groups for one slice + location list."""
    reverse_path = work_path / AG_DIR_NAME / f"complete_reverse_{host}.smt2"
    forward_path = work_path / AG_DIR_NAME / f"complete_forward_{host}.smt2"
    config_vars = resolve_config_vars_in_file(reverse_path, loc_names)
    if not config_vars:
        config_vars = resolve_config_vars_in_file(forward_path, loc_names)
    if not config_vars:
        logger.warning(
            "Slice %s: locations present but no (= Config value) found; treat as empty",
            host,
        )
        return SliceJointResult(
            host=host,
            locations=[ConfigLocationVar(name=n, value="?") for n in loc_names],
            groups=[
                JointGroupResult(
                    hosts=[host],
                    config_names=list(loc_names),
                    subspec="empty",
                )
            ],
        )

    groups = compute_slice_joint_subspec(
        work_path,
        host,
        config_vars,
        intermediate_dir,
        keep_intermediate=verbose,
        target_dst_ip=target_dst_ip,
        verbose=verbose,
        model_store=model_store,
    )
    return SliceJointResult(host=host, locations=list(config_vars), groups=groups)


def run_joint_for_localized_locations(
    work_dir: str | Path,
    locations_by_host: Dict[str, List[str]],
    *,
    verbose: bool = False,
    intermediate_dir_name: str = DEFAULT_JOINT_INTERMEDIATE_DIR,
    output_dir_name: str = DEFAULT_JOINT_OUTPUT_DIR,
    model_store: Optional[ModelConfigEqualitiesStore] = None,
) -> JointMultiLocationResult:
    """
    Compute joint subspecs for pre-localized Config_* sets, per AG-fail slice only.

    Unlike ``run_joint_multi_location_subspec``, this does not read
    ``0_multiple_locations.txt`` and does not scan every slice for membership —
    each host is solved only with the locations supplied for that host.

    ``model_store`` (optional): MaxSMT / get-model equalities for misconfiguration
    repair; used when constant propagation eliminates a Config_* from the goal.
    """
    work_path = Path(work_dir)
    target_dst_ip = load_target_dst_ip(work_path)

    intermediate_dir = work_path / intermediate_dir_name
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    temp_dir_obj = None
    if not verbose:
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="joint_subspec_")
        intermediate_dir = Path(temp_dir_obj.name)

    all_locations: List[str] = []
    seen_loc: Set[str] = set()
    for host in sorted(locations_by_host.keys()):
        for name in locations_by_host[host]:
            if name not in seen_loc:
                seen_loc.add(name)
                all_locations.append(name)

    result = JointMultiLocationResult(locations=all_locations)

    try:
        logger.info(
            "Starting localized joint subspec for %d host(s), %d unique location(s)...",
            len(locations_by_host),
            len(all_locations),
        )
        for host in sorted(locations_by_host.keys()):
            loc_names = list(locations_by_host[host])
            if not loc_names:
                logger.info("Slice %s: empty location list, skip", host)
                continue
            result.per_slice.append(
                _compute_per_slice_joint(
                    work_path,
                    host,
                    loc_names,
                    intermediate_dir,
                    target_dst_ip=target_dst_ip,
                    verbose=verbose,
                    model_store=model_store,
                )
            )

        result.empty_configs = collect_empty_configs(all_locations, result.per_slice)
        # Only one slice owns each localization set; cross-slice merge is a no-op
        # unless the same multi-config set was supplied for multiple hosts.
        result.merged_groups = merge_necessary_cross_slice_groups(result.per_slice)
        out_path = save_joint_result(
            work_path, result, output_dir_name=output_dir_name
        )

        n_slices = len(result.per_slice)
        n_empty_slices = len(result.empty_slices)
        n_nonempty_slices = len(result.nonempty_slices)
        n_groups = sum(len(r.groups) for r in result.per_slice)
        print(
            f"joint multi-location (localized): {len(all_locations)} locations, "
            f"{n_slices} slices"
        )
        print(
            f"  empty slices: {n_empty_slices}; non-empty slices: {n_nonempty_slices}; "
            f"groups: {n_groups}; empty Config: {len(result.empty_configs)}"
        )
        print(f"  necessary merged groups: {len(result.merged_groups)}")
        print(f"  saved: {out_path}")
        return result
    finally:
        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()


def run_joint_multi_location_subspec(
    work_dir: str | Path,
    *,
    verbose: bool = False,
    device_filter: Optional[str] = None,
    intermediate_dir_name: str = DEFAULT_JOINT_INTERMEDIATE_DIR,
    output_dir_name: str = DEFAULT_JOINT_OUTPUT_DIR,
) -> JointMultiLocationResult:
    """
    Entry point: compute joint multi-location subspecs for 0_multiple_locations.txt.

    Args:
        work_dir: SMT work directory containing AG files and 0_multiple_locations.txt
        verbose: keep intermediate SMT files / more logging (caller sets log level)
        device_filter: if set, only process that slice host
        intermediate_dir_name: stage-local intermediate dir under work_dir (e.g. 5_intermediate_...)
        output_dir_name: stage-local output dir under work_dir (e.g. 5_subspec_files)
    """
    work_path = Path(work_dir)
    locations = load_multiple_locations(work_path)
    hosts = list_ag_slice_hosts(work_path, device_filter=device_filter)
    target_dst_ip = load_target_dst_ip(work_path)

    intermediate_dir = work_path / intermediate_dir_name
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    temp_dir_obj = None
    if not verbose:
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="joint_subspec_")
        intermediate_dir = Path(temp_dir_obj.name)

    result = JointMultiLocationResult(locations=list(locations))

    try:
        logger.info("Starting joint multi-location subspec for %d locations...", len(locations))
        for host in hosts:
            loc_names = locations_in_slice(locations, work_path, host)
            if not loc_names:
                logger.info("Slice %s: no matching locations, skip", host)
                continue

            result.per_slice.append(
                _compute_per_slice_joint(
                    work_path,
                    host,
                    loc_names,
                    intermediate_dir,
                    target_dst_ip=target_dst_ip,
                    verbose=verbose,
                )
            )

        result.empty_configs = collect_empty_configs(locations, result.per_slice)
        result.merged_groups = merge_necessary_cross_slice_groups(result.per_slice)
        out_path = save_joint_result(
            work_path, result, output_dir_name=output_dir_name
        )

        n_slices = len(result.per_slice)
        n_empty_slices = len(result.empty_slices)
        n_nonempty_slices = len(result.nonempty_slices)
        n_groups = sum(len(r.groups) for r in result.per_slice)
        print(f"joint multi-location: {len(locations)} locations, {n_slices} slices hit")
        print(
            f"  empty slices: {n_empty_slices}; non-empty slices: {n_nonempty_slices}; "
            f"groups: {n_groups}; empty Config: {len(result.empty_configs)}"
        )
        print(f"  necessary merged groups: {len(result.merged_groups)}")
        print(f"  saved: {out_path}")
        return result
    finally:
        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()
