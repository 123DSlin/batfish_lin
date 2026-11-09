#!/usr/bin/env python3
"""
MaxSMT utilities for multi-location Config localization.

Convert hard ``(assert (= Config_...))`` equalities to weighted ``assert-soft``,
run Z3 MaxSMT (``check-sat`` with soft constraints), and compare the model
against soft expectations to obtain violated Config_* names.

Entry points:
- convert_config_asserts_to_soft: hard Config equalities -> weighted assert-soft
- compare_soft_vs_model / localize_violated_configs_from_forward: MaxSMT + mismatch set
- localize_k_violated_configs_from_forward: enumerate up to K repair location sets
- expand_with_ip_mask_partners: bind ip/mask pairs into the localized set

Weights (``utils.util_keyword``):
- SOFT_CONSTRAINT_WEIGHT (default 1)
- ENABLE_SOFT_CONSTRAINT_WEIGHT for names ending with ``enable`` (default 10)

Enumeration (``REPAIR_OPTION_COUNT``):
After each MaxSMT solution with violated soft set V = {(VAR, soft_val), ...},
append a hard block so the next solve must satisfy at least one of those softs::

    (assert (or (= VAR1 soft_val1) (= VAR2 soft_val2) ...))
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from utils.util_keyword import (
    ENABLE_SOFT_CONSTRAINT_WEIGHT,
    REPAIR_OPTION_COUNT,
    SOFT_CONSTRAINT_WEIGHT,
)
from utils.util_smt import (
    append_check_sat,
    extract_base_name_for_ip_mask,
    is_ip_mask_pair,
    parse_z3_model_config_assignments,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Soft conversion (hard Config assert -> assert-soft)
# ---------------------------------------------------------------------------

def soft_weight_for_config_name(config_name: str) -> int:
    """Return MaxSMT weight for a Config_* name (enable flags cost more to violate)."""
    if config_name.endswith("enable"):
        return ENABLE_SOFT_CONSTRAINT_WEIGHT
    return SOFT_CONSTRAINT_WEIGHT


def convert_config_asserts_to_soft(text: str) -> Tuple[str, int, int]:
    """Convert ``(assert (= Config_...))`` to weighted ``assert-soft``.

    Multi-line asserts are collapsed to a single line. Returns
    ``(new_text, converted_count, multiline_collapsed_count)``.
    """
    result: List[str] = []
    i = 0
    converted = 0
    multiline = 0

    while i < len(text):
        if text.startswith("(assert (= Config_", i):
            start = i
            depth = 0
            j = i
            while j < len(text):
                c = text[j]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1

            raw = text[start:j]
            if "\n" in raw.strip():
                multiline += 1

            normalized = re.sub(r"\s+", " ", raw.strip())
            match = re.fullmatch(r"\(assert (\(= Config_.+\))\)", normalized)
            if not match:
                raise ValueError(f"Unexpected assert form: {normalized[:160]}")

            equality = match.group(1)
            name_match = re.match(r"\(= (\S+) ", equality)
            if not name_match:
                raise ValueError(f"Could not parse Config name from: {equality[:160]}")
            weight = soft_weight_for_config_name(name_match.group(1))
            result.append(f"(assert-soft {equality} :weight {weight})\n")
            converted += 1
            i = j
        else:
            next_pos = text.find("(assert (= Config_", i)
            if next_pos == -1:
                result.append(text[i:])
                break
            result.append(text[i:next_pos])
            i = next_pos

    out = "".join(result)
    out = re.sub(r"(\(assert-soft [^\n]+\n)\n+(?=\(assert-soft )", r"\1", out)
    return out, converted, multiline


def convert_config_asserts_to_soft_file(
    smt_path: Path,
    *,
    dry_run: bool = False,
) -> Tuple[str, int, int, int, int]:
    """Convert Config hard asserts in ``smt_path`` (optionally in place).

    Returns:
        (updated_text, converted, multiline, remaining_hard, soft_total)
    """
    original = smt_path.read_text()
    updated, converted, multiline = convert_config_asserts_to_soft(original)
    remaining = len(re.findall(r"^\(assert \(= Config_", updated, re.MULTILINE))
    soft_total = len(re.findall(r"^\(assert-soft ", updated, re.MULTILINE))
    if not dry_run and converted > 0:
        smt_path.write_text(updated)
        logger.info("Wrote soft conversion to %s (%d asserts)", smt_path, converted)
    return updated, converted, multiline, remaining, soft_total


# ---------------------------------------------------------------------------
# Soft parsing / Config name listing
# ---------------------------------------------------------------------------

def parse_active_soft_constraints(text: str) -> Dict[str, str]:
    """Parse non-commented assert-soft Config equalities -> {var: expected_value}."""
    active: Dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        match = re.match(
            r"\(assert-soft \(= (\S+) (.+)\) :weight \d+\)", stripped
        )
        if match:
            active[match.group(1)] = match.group(2).strip()
    return active


def list_config_equality_names(text: str) -> List[str]:
    """Config_* names that appear as hard or soft equality asserts (active lines)."""
    names: List[str] = []
    seen: Set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        match = re.match(r"\(assert(?:-soft)? \(= (Config_\S+) ", stripped)
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            names.append(match.group(1))
    return names


# ---------------------------------------------------------------------------
# Z3 MaxSMT: ensure commands, run, parse status / model
# ---------------------------------------------------------------------------

def ensure_z3_maxsmt_commands(text: str) -> str:
    """Ensure ``(check-sat)`` and active ``(get-model)`` for MaxSMT + model extraction.

    With ``assert-soft`` present, plain ``check-sat`` selects Z3's MaxSMT engine.
    Uncomments a trailing ``; (get-model)`` when present.
    """
    lines = text.splitlines()
    out: List[str] = []
    has_check_sat = False
    has_get_model = False

    for line in lines:
        stripped = line.strip()
        if stripped == "(check-sat)":
            has_check_sat = True
        if stripped in {"(get-model)", "; (get-model)"}:
            if stripped.startswith(";"):
                out.append("(get-model)")
                has_get_model = True
                continue
            has_get_model = True
        out.append(line)

    content = "\n".join(out)
    if text.endswith("\n"):
        content += "\n"
    if not has_check_sat:
        content = append_check_sat(content)
    if not has_get_model:
        content = content.rstrip() + "\n(get-model)\n"
    return content


def run_z3_smt_text(smt_text: str, z3_bin: str = "z3") -> str:
    """Write SMT text to a temp file and run Z3; return stdout+stderr."""
    with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as tmp:
        tmp.write(smt_text)
        tmp_path = tmp.name

    proc = subprocess.run(
        [z3_bin, tmp_path],
        capture_output=True,
        text=True,
    )
    output = proc.stdout + proc.stderr
    if not output.strip():
        raise RuntimeError(f"Z3 produced no output (exit {proc.returncode}).")
    return output


def parse_z3_status(z3_text: str) -> str:
    """Return first sat/unsat/unknown line, else ``unknown``."""
    for line in z3_text.splitlines():
        stripped = line.strip()
        if stripped in {"sat", "unsat", "unknown"}:
            return stripped
    return "unknown"


def parse_config_model(z3_text: str) -> Dict[str, str]:
    """Parse Config_* assignments from Z3 get-model output."""
    return parse_z3_model_config_assignments(z3_text)


# ---------------------------------------------------------------------------
# Soft vs model comparison
# ---------------------------------------------------------------------------

def _norm_value(value: str) -> str:
    return re.sub(r"\s+", "", value)


def compare_soft_with_model(
    active_soft: Dict[str, str], model: Dict[str, str]
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, str]]]:
    """Return (matched, violated) where violated entries are (var, soft, model)."""
    matched: List[Tuple[str, str]] = []
    violated: List[Tuple[str, str, str]] = []

    for var, expected in sorted(active_soft.items()):
        actual = model.get(var)
        if actual is None:
            violated.append((var, expected, "<missing>"))
        elif _norm_value(actual) == _norm_value(expected):
            matched.append((var, expected))
        else:
            violated.append((var, expected, actual))

    return matched, violated


@dataclass
class SoftVsModelResult:
    """Result of comparing active assert-soft Config equalities to a MaxSMT model."""
    status: str
    active_soft: Dict[str, str]
    matched: List[Tuple[str, str]]
    violated: List[Tuple[str, str, str]]
    z3_output: str = ""
    model: Dict[str, str] = field(default_factory=dict)

    @property
    def violated_names(self) -> List[str]:
        return [var for var, _soft, _model in self.violated]

    @property
    def matched_names(self) -> List[str]:
        return [var for var, _val in self.matched]


def compare_soft_vs_model(
    smt_text: str,
    *,
    z3_bin: str = "z3",
) -> SoftVsModelResult:
    """Run MaxSMT on soft-constraint SMT text and compare soft vs model."""
    active_soft = parse_active_soft_constraints(smt_text)
    if not active_soft:
        return SoftVsModelResult(
            status="no-soft",
            active_soft={},
            matched=[],
            violated=[],
        )

    z3_output = run_z3_smt_text(ensure_z3_maxsmt_commands(smt_text), z3_bin=z3_bin)
    status = parse_z3_status(z3_output)
    if status != "sat":
        return SoftVsModelResult(
            status=status,
            active_soft=active_soft,
            matched=[],
            violated=[],
            z3_output=z3_output,
        )

    model = parse_config_model(z3_output)
    matched, violated = compare_soft_with_model(active_soft, model)
    return SoftVsModelResult(
        status=status,
        active_soft=active_soft,
        matched=matched,
        violated=violated,
        z3_output=z3_output,
        model=model,
    )


def compare_soft_vs_model_file(
    smt_path: Path,
    *,
    z3_bin: str = "z3",
    report_path: Optional[Path] = None,
) -> SoftVsModelResult:
    """Load ``smt_path``, run ``compare_soft_vs_model``, optionally write a text report."""
    result = compare_soft_vs_model(smt_path.read_text(), z3_bin=z3_bin)
    if report_path is not None:
        write_soft_vs_model_report(report_path, smt_path, result)
    return result


def write_soft_vs_model_report(
    report_path: Path,
    smt_path: Path,
    result: SoftVsModelResult,
) -> None:
    """Write a human-readable soft-vs-model mismatch report."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w") as f:
        f.write(f"File: {smt_path}\n")
        f.write(f"Z3 status: {result.status}\n")
        f.write(f"Active soft constraints: {len(result.active_soft)}\n")
        f.write(f"Satisfied: {len(result.matched)}\n")
        f.write(f"Violated: {len(result.violated)}\n\n")
        for var, soft_val, model_val in result.violated:
            f.write(f"variable: {var}\n")
            f.write(f"  soft:  {soft_val}\n")
            f.write(f"  model: {model_val}\n\n")
    logger.info("Soft-vs-model report written to %s", report_path)


# ---------------------------------------------------------------------------
# Localization helpers (multi-location pipeline)
# ---------------------------------------------------------------------------

def expand_with_ip_mask_partners(
    config_names: Sequence[str],
    available_names: Sequence[str],
) -> List[str]:
    """If either ip or mask is selected, also include its partner when present."""
    available = set(available_names)
    ordered: List[str] = []
    seen: Set[str] = set()

    def _add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            ordered.append(name)

    for name in config_names:
        _add(name)
        base = extract_base_name_for_ip_mask(name)
        if base == name:
            continue
        if name.endswith("__ip"):
            partner = f"{base}__mask"
        elif name.endswith("__mask"):
            partner = f"{base}__ip"
        else:
            continue
        if partner in available and is_ip_mask_pair(name, partner):
            _add(partner)

    return ordered


@dataclass
class MaxSmtLocalizeResult:
    """MaxSMT localization result on one complete_forward file."""
    violated_names: List[str]
    matched_names: List[str]
    status: str
    converted_count: int
    model: Dict[str, str] = field(default_factory=dict)
    option_id: int = 0
    # Soft expected values for violated names (var -> soft_val); used for blocking.
    violated_soft: Dict[str, str] = field(default_factory=dict)


def format_soft_violation_block_assert(
    violated: Sequence[Tuple[str, str, str]],
) -> str:
    """Hard assert: at least one previously-violated soft equality must hold.

    ``violated`` entries are ``(var, soft_val, model_val)``. Produces::

        (assert (= VAR soft_val))                         # |V| == 1
        (assert (or (= VAR1 soft_val1) (= VAR2 soft_val2) ...))  # |V| >= 2
    """
    if not violated:
        raise ValueError("cannot build block assert from empty violated set")
    atoms = [f"(= {var} {soft_val})" for var, soft_val, _model_val in violated]
    if len(atoms) == 1:
        return f"(assert {atoms[0]})"
    return f"(assert (or {' '.join(atoms)}))"


def insert_hard_asserts_before_check_sat(
    smt_text: str,
    assert_lines: Sequence[str],
) -> str:
    """Insert hard assert line(s) immediately before the first ``(check-sat)``."""
    if not assert_lines:
        return smt_text
    block_lines = [
        (line if line.endswith("\n") else line + "\n") for line in assert_lines
    ]
    block = "".join(block_lines)

    lines = smt_text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == "(check-sat)":
            return "".join(lines[:i]) + block + "".join(lines[i:])
    # No check-sat yet; append (ensure_z3_maxsmt_commands will add it later).
    if smt_text and not smt_text.endswith("\n"):
        smt_text += "\n"
    return smt_text + block


def localize_k_violated_configs_from_forward(
    forward_smt_path: Path,
    *,
    k: int = REPAIR_OPTION_COUNT,
    soft_smt_output_dir: Optional[Path] = None,
    soft_smt_basename: Optional[str] = None,
    z3_bin: str = "z3",
) -> List[MaxSmtLocalizeResult]:
    """Enumerate up to ``k`` MaxSMT localization options on one complete_forward.

    After each sat solution with violated soft set V, appends a hard block
    requiring at least one soft in V to hold, then re-solves. Stops early on
    non-sat, empty violation set, or when ``k`` options are collected.
    """
    if k < 1:
        return []

    original = forward_smt_path.read_text()
    soft_text, converted, _multiline = convert_config_asserts_to_soft(original)
    working = soft_text
    options: List[MaxSmtLocalizeResult] = []

    for option_id in range(k):
        if soft_smt_output_dir is not None and soft_smt_basename:
            soft_smt_output_dir.mkdir(parents=True, exist_ok=True)
            out_path = soft_smt_output_dir / f"{soft_smt_basename}_option_{option_id}.smt2"
            out_path.write_text(working)
            logger.info("Soft complete_forward (option %d) saved to: %s", option_id, out_path)

        cmp = compare_soft_vs_model(working, z3_bin=z3_bin)
        if cmp.status == "no-soft":
            if option_id == 0:
                return [
                    MaxSmtLocalizeResult(
                        [], [], "no-soft", converted, option_id=0
                    )
                ]
            break
        if cmp.status != "sat":
            if option_id == 0:
                return [
                    MaxSmtLocalizeResult(
                        [], [], cmp.status, converted, option_id=0
                    )
                ]
            logger.info(
                "MaxSMT option %d: status=%s; stopping enumeration",
                option_id,
                cmp.status,
            )
            break
        if not cmp.violated:
            if option_id == 0:
                return [
                    MaxSmtLocalizeResult(
                        [],
                        cmp.matched_names,
                        cmp.status,
                        converted,
                        model=dict(cmp.model),
                        option_id=0,
                    )
                ]
            logger.info(
                "MaxSMT option %d: no soft constraints violated; stopping",
                option_id,
            )
            break

        violated_soft = {var: soft_val for var, soft_val, _m in cmp.violated}
        options.append(
            MaxSmtLocalizeResult(
                list(cmp.violated_names),
                list(cmp.matched_names),
                cmp.status,
                converted,
                model=dict(cmp.model),
                option_id=option_id,
                violated_soft=violated_soft,
            )
        )
        logger.info(
            "MaxSMT option %d: violated=%d matched=%d (%s)",
            option_id,
            len(cmp.violated_names),
            len(cmp.matched_names),
            ", ".join(cmp.violated_names),
        )

        if option_id + 1 >= k:
            break

        block = format_soft_violation_block_assert(cmp.violated)
        working = insert_hard_asserts_before_check_sat(working, [block])
        logger.info("MaxSMT option %d: added hard block: %s", option_id, block)

    return options


def localize_violated_configs_from_forward(
    forward_smt_path: Path,
    *,
    soft_smt_output: Optional[Path] = None,
    z3_bin: str = "z3",
) -> MaxSmtLocalizeResult:
    """MaxSMT-localize violated Config_* on a complete_forward file (single option).

    Converts Config hard equalities to soft, runs Z3 MaxSMT, and returns
    violated/matched names plus the full Config_* model for repair equalities.
    """
    options = localize_k_violated_configs_from_forward(
        forward_smt_path,
        k=1,
        z3_bin=z3_bin,
    )
    if soft_smt_output is not None:
        # Preserve legacy single-file soft dump (pre-enumeration naming).
        original = forward_smt_path.read_text()
        soft_text, _converted, _multiline = convert_config_asserts_to_soft(original)
        soft_smt_output.parent.mkdir(parents=True, exist_ok=True)
        soft_smt_output.write_text(soft_text)
        logger.info("Soft complete_forward saved to: %s", soft_smt_output)
    if not options:
        return MaxSmtLocalizeResult([], [], "unknown", 0)
    return options[0]
