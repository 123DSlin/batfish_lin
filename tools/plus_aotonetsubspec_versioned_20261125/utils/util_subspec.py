#!/usr/bin/env python3
"""
Subspec impact-check utilities: comment-out config locations, build check SMT2, run Z3.

Entry points (by pipeline generation):
- check_impact_forward: scripts 4/5/6 — verification-style, SAT only
  - 4/5: complete_reverse baseline already has (check-sat)
  - 6: verification baseline may need append_check_sat
- check_impact_reverse: scripts 7/8 — synthesis-style, SAT + get-model + model equalities
  - 7: complete_forward baseline already has (check-sat), append get-model only
  - 8: synthesis baseline may need append_check_sat + append_get_model
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

from utils.util_smt import (
    ModelConfigEqualitiesStore,
    append_check_sat,
    append_get_model,
    get_bounds_for_multiple_config_variables,
    get_bounds_for_single_config_variable,
    parse_z3_output,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigLocationVar:
    """A Config_* variable at a configuration location (field / line / pair)."""
    name: str
    value: str


class ImpactCheckWriteMode(Enum):
    """Where to write the impact-check SMT2 file."""
    PERSISTENT = "persistent"  # field-level: check_subspec_from_{device}_{safe}.smt2
    TEMP_WITH_DEBUG = "temp_with_debug"  # line/pair: temp for Z3 + copy under intermediate_dir


def _as_config_location_var(item: Union[ConfigLocationVar, object]) -> ConfigLocationVar:
    if isinstance(item, ConfigLocationVar):
        return item
    return ConfigLocationVar(name=item.name, value=item.value)


def comment_config_var_equality_and_add_bounds(
    lines: List[str], config_var: ConfigLocationVar
) -> Tuple[List[str], bool]:
    """Comment out one (= Config_... value) line and insert bounds for that variable."""
    modified_lines: List[str] = []
    config_line_found = False
    config_line_pattern = f"= {config_var.name} {config_var.value}"
    first_commented_index: Optional[int] = None
    for line in lines:
        if config_line_pattern in line and not line.strip().startswith(";"):
            modified_lines.append(f"; {line.strip()}\n")
            config_line_found = True
            if first_commented_index is None:
                first_commented_index = len(modified_lines) - 1
        else:
            modified_lines.append(line)
    bounds_to_add = get_bounds_for_single_config_variable(config_var.name)
    if bounds_to_add and first_commented_index is not None:
        insert_pos = first_commented_index + 1
        bounds_lines = [f"{x}\n" for x in bounds_to_add]
        modified_lines = modified_lines[:insert_pos] + bounds_lines + modified_lines[insert_pos:]
    return modified_lines, config_line_found


def comment_out_config_vars_to_temp(
    baseline_path: Path,
    config_vars: Sequence[Union[ConfigLocationVar, object]],
    *,
    comment: bool = True,
) -> str:
    """Comment out simple (= Config_...) asserts for all config_vars; write temp SMT2 path."""
    vars_list = [_as_config_location_var(v) for v in config_vars]

    with open(baseline_path, "r") as f:
        lines = f.readlines()

    modified_lines: List[str] = []
    commented_var_names: List[str] = []
    first_commented_index: Optional[int] = None

    for line in lines:
        line_content = line.strip()
        should_modify = False
        matching_name: Optional[str] = None
        if comment:
            for config_var in vars_list:
                if (
                    config_var.name in line_content
                    and line_content.startswith("(assert (= Config_")
                    and line_content.endswith("))")
                ):
                    should_modify = True
                    matching_name = config_var.name
                    break

        if should_modify and matching_name is not None:
            if not line_content.startswith(";"):
                modified_lines.append(f"; {line_content}\n")
                if first_commented_index is None:
                    first_commented_index = len(modified_lines) - 1
                if matching_name not in commented_var_names:
                    commented_var_names.append(matching_name)
            else:
                modified_lines.append(line)
        elif not comment:
            if line_content.startswith(";"):
                modified_lines.append(line[1:])
            else:
                modified_lines.append(line)
        else:
            modified_lines.append(line)

    if comment and commented_var_names and first_commented_index is not None:
        bounds_to_add = get_bounds_for_multiple_config_variables(commented_var_names)
        if bounds_to_add:
            insert_pos = first_commented_index + 1
            bounds_lines = [f"{b}\n" for b in bounds_to_add]
            modified_lines = (
                modified_lines[:insert_pos] + bounds_lines + modified_lines[insert_pos:]
            )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".smt2", delete=False) as temp_file:
        temp_file.writelines(modified_lines)
        return temp_file.name


def _finalize_forward_impact_content(content: str, *, baseline_has_check_sat: bool) -> str:
    """4/5: baseline already has (check-sat). 6: append (check-sat) only."""
    if baseline_has_check_sat:
        return content if content.endswith("\n") else content + "\n"
    return append_check_sat(content)


def _finalize_reverse_impact_content(content: str, *, baseline_has_check_sat: bool) -> str:
    """7: baseline has (check-sat), append (get-model). 8: append both."""
    if not baseline_has_check_sat:
        content = append_check_sat(content)
    return append_get_model(content)


def _write_impact_check_file(
    content: str,
    intermediate_dir: Path,
    device: str,
    safe_name: str,
    write_mode: ImpactCheckWriteMode,
) -> Optional[Path]:
    """Write impact-check SMT2; return path to pass to Z3."""
    check_path = intermediate_dir / f"check_subspec_from_{device}_{safe_name}.smt2"
    if write_mode == ImpactCheckWriteMode.PERSISTENT:
        with open(check_path, "w") as f:
            f.write(content)
        logger.info(f"    Impact check file saved to: {check_path}")
        return check_path

    with tempfile.NamedTemporaryFile(mode="w", suffix=".smt2", delete=False) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    with open(check_path, "w") as f:
        f.write(content)
    logger.info(f"    Debug impact check file saved to: {check_path}")
    return temp_path


def _build_impact_check_content_from_baseline(
    baseline_path: Path,
    config_vars: Sequence[Union[ConfigLocationVar, object]],
    write_mode: ImpactCheckWriteMode,
    finalize_content: Callable[[str], str],
) -> Tuple[Optional[str], bool]:
    """Return (final_content, any_config_found)."""
    if not baseline_path.exists():
        logger.error(f"Impact-check baseline not found: {baseline_path}")
        return None, False

    vars_list = [_as_config_location_var(v) for v in config_vars]

    if write_mode == ImpactCheckWriteMode.PERSISTENT:
        if len(vars_list) != 1:
            raise ValueError("PERSISTENT write mode requires exactly one config variable")
        with open(baseline_path, "r") as f:
            lines = f.readlines()
        modified_lines, found = comment_config_var_equality_and_add_bounds(lines, vars_list[0])
        if not found:
            return None, False
        content = finalize_content("".join(modified_lines))
        return content, True

    temp_path = comment_out_config_vars_to_temp(baseline_path, vars_list, comment=True)
    try:
        with open(temp_path, "r") as f:
            raw = f.read()
        content = finalize_content(raw)
        return content, True
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _run_z3_sat_only(smt2_path: Path, *, cleanup_after: bool) -> bool:
    try:
        result = subprocess.run(["z3", str(smt2_path)], capture_output=True, text=True)
        is_sat, _ = parse_z3_output(result)
        if is_sat:
            logger.info("    Result: SAT (has impact, continue to subspec computation)")
        else:
            logger.info("    Result: UNSAT (no impact, empty subspec)")
        return is_sat
    except Exception as e:
        logger.error(f"    Error running Z3: {e}")
        return False
    finally:
        if cleanup_after and smt2_path and os.path.exists(smt2_path):
            try:
                os.unlink(smt2_path)
            except OSError:
                pass


def _run_z3_with_model(
    smt2_path: Path,
    config_var_names: Set[str],
    model_store: ModelConfigEqualitiesStore,
    *,
    verbose: bool,
    info_fn: Optional[Callable[[str], None]],
    cleanup_after: bool,
) -> bool:
    try:
        result = subprocess.run(["z3", str(smt2_path)], capture_output=True, text=True)
        is_sat, _ = parse_z3_output(result)
        if is_sat:
            logger.info("    Result: SAT (has impact, continue to subspec computation)")
            model_store.update_from_z3_output(
                result.stdout,
                config_var_names,
                info=info_fn,
            )
        else:
            logger.info("    Result: UNSAT (no impact, empty subspec)")
        return is_sat
    except Exception as e:
        logger.error(f"    Error running Z3: {e}")
        return False
    finally:
        if cleanup_after and smt2_path and os.path.exists(smt2_path):
            try:
                os.unlink(smt2_path)
            except OSError:
                pass


def check_impact_forward(
    baseline_path: Path,
    config_vars: Sequence[Union[ConfigLocationVar, object]],
    intermediate_dir: Path,
    device: str,
    safe_name: str,
    *,
    baseline_has_check_sat: bool = True,
    write_mode: ImpactCheckWriteMode = ImpactCheckWriteMode.PERSISTENT,
    cleanup_after: bool = False,
) -> bool:
    """Impact check for 4/5/6: comment out location, (check-sat) only, return SAT=has impact.

    baseline_has_check_sat:
        True for 4/5 (complete_reverse already ends with (check-sat)).
        False for 6 (verification baseline may lack (check-sat)).
    """
    content, found = _build_impact_check_content_from_baseline(
        baseline_path,
        config_vars,
        write_mode,
        lambda c: _finalize_forward_impact_content(c, baseline_has_check_sat=baseline_has_check_sat),
    )
    if not found or content is None:
        names = ", ".join(_as_config_location_var(v).name for v in config_vars)
        logger.info(f"Config location not found in baseline ({names}), assuming no impact")
        return False

    smt2_path = _write_impact_check_file(content, intermediate_dir, device, safe_name, write_mode)
    if smt2_path is None:
        return False
    return _run_z3_sat_only(smt2_path, cleanup_after=cleanup_after)


def check_impact_reverse(
    baseline_path: Path,
    config_vars: Sequence[Union[ConfigLocationVar, object]],
    intermediate_dir: Path,
    device: str,
    safe_name: str,
    model_store: ModelConfigEqualitiesStore,
    *,
    baseline_has_check_sat: bool = True,
    write_mode: ImpactCheckWriteMode = ImpactCheckWriteMode.PERSISTENT,
    verbose: bool = False,
    info_fn: Optional[Callable[[str], None]] = None,
    cleanup_after: bool = False,
) -> bool:
    """Impact check for 7/8: comment out location, (get-model), store model equalities if SAT.

    baseline_has_check_sat:
        True for 7 (complete_forward already ends with (check-sat)).
        False for 8 (synthesis baseline may lack (check-sat) and (get-model)).
    """
    content, found = _build_impact_check_content_from_baseline(
        baseline_path,
        config_vars,
        write_mode,
        lambda c: _finalize_reverse_impact_content(c, baseline_has_check_sat=baseline_has_check_sat),
    )
    if not found or content is None:
        names = ", ".join(_as_config_location_var(v).name for v in config_vars)
        logger.info(f"Config location not found in baseline ({names}), assuming no impact")
        return False

    smt2_path = _write_impact_check_file(content, intermediate_dir, device, safe_name, write_mode)
    if smt2_path is None:
        return False
    config_names = {_as_config_location_var(v).name for v in config_vars}
    return _run_z3_with_model(
        smt2_path,
        config_names,
        model_store,
        verbose=verbose,
        info_fn=info_fn,
        cleanup_after=cleanup_after,
    )


# ---------------------------------------------------------------------------
# Repair summary (7_fix per-device AG-fail, 8_fix global synthesis)
# ---------------------------------------------------------------------------

def is_nonempty_subspec(subspec: Optional[str]) -> bool:
    """True if subspec is a non-empty constraint (not missing and not the 'empty' marker)."""
    return bool(subspec and subspec.strip() and subspec != "empty")


def subspec_set_has_nonempty(subspecs: Set[str]) -> bool:
    return any(is_nonempty_subspec(s) for s in subspecs)


def dict_has_nonempty_subspec(subspecs_by_key: Dict[str, Set[str]]) -> bool:
    return any(subspec_set_has_nonempty(v) for v in subspecs_by_key.values())


def emit_per_device_repair_summary(
    devices_needing_repair: Set[str],
    devices_with_subspec: Set[str],
) -> None:
    """7_fix: each AG-fail device needs at least one non-empty subspec to be repairable."""
    if not devices_needing_repair:
        return
    not_repaired = sorted(devices_needing_repair - devices_with_subspec)
    if not not_repaired:
        print("Can repair the misconfiguration!")
    else:
        print(f"Cannot repair misconfiguration for device(s): {', '.join(not_repaired)}")


def emit_global_repair_summary(has_nonempty_subspec: bool) -> None:
    """8_fix: global synthesis encoding — any one non-empty subspec suffices."""
    if has_nonempty_subspec:
        print("Can repair the misconfiguration!")
    else:
        print("Cannot repair the misconfiguration.")
