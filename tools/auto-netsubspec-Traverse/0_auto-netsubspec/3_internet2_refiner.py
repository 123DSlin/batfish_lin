#!/usr/bin/env python3
"""
Internet2 assume-guarantee refiner.

1. For each complete_reverse_<device>.smt2 under <work_directory>/3_assume_guarantee_test/,
   append (before check-sat) asserts that set every BGP_EXPORT_ENV *_permitted variable
   for that device to false.

2. Run Z3 on all complete_forward_<device>.smt2 and complete_reverse_<device>.smt2 files
   and check assume-guarantee conditions:
   - forward: expected SAT
   - reverse: expected UNSAT

3. If a device still fails with reverse SAT (e.g. forward UNSAT / reverse SAT), run
   complete_reverse with (get-model), extract values for variables appearing in the
   device's normal constraints and combined negated constraints, rewrite those constraint
   files, regenerate complete_forward/reverse, re-apply EXPORT_ENV patch, and re-test.

Z3 checking reuses AssumeGuaranteeTester from 3_assume_guarantee_tester.py but does NOT
regenerate SMT files during the initial pass (unlike the main tester script).

Usage:
    python3 3_internet2_refiner.py [-v] [-n] [--test-only] [--device DEVICE] <work_directory>

Example:
    python3 3_internet2_refiner.py smt_output_0032
    python3 3_internet2_refiner.py -v smt_outputs/smt_output_0001
    python3 3_internet2_refiner.py --test-only smt_output_0032
    python3 3_internet2_refiner.py --device newy-re1 smt_output_0032
"""

from __future__ import annotations

import importlib.util
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from utils.util_smt import parse_z3_output

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ASSUME_MARKER_PREFIX = "; Assume: disable all external BGP route inputs to"
EXPORT_ENV_PERMITTED_DECL_RE = re.compile(
    r"declare-fun (\|0_[^|]+_BGP_EXPORT_ENV-[^|]+_permitted\|)"
)
EXPORT_ENV_PERMITTED_ASSERT_RE = re.compile(
    r"^\(assert \(= (\|0_[^|]+_BGP_EXPORT_ENV-[^|]+_permitted\|) false\)\)$"
)
COMPLETE_REVERSE_RE = re.compile(r"^complete_reverse_(.+)\.smt2$")
COMPLETE_FORWARD_RE = re.compile(r"^complete_forward_(.+)\.smt2$")
CONSTRAINT_VAR_RE = re.compile(r"(\|[^|]+\||Config_[^\s()]+)")
SIMPLE_ASSERT_EQ_RE = re.compile(r"^\(assert \(= (\|[^|]+\|) (.+)\)\)\s*$")
NEGATED_EQ_VAR_RE = re.compile(r"\(not \(= (\|[^|]+\|) [^)]+\)\)")


def append_get_model(content: str) -> str:
    """Append (get-model) after (check-sat) if not already present."""
    content = content.rstrip()
    if "(get-model)" in content:
        return content + "\n"
    if "(check-sat)" in content:
        content = content.replace("(check-sat)", "(check-sat)\n(get-model)", 1)
    else:
        content += "\n(get-model)"
    return content + "\n"


def _parse_define_fun_assignment_at_line(
    lines: List[str], i: int
) -> Tuple[Optional[str], Optional[str], int]:
    """Parse one (define-fun NAME () TYPE VALUE) assignment."""
    stripped = lines[i].strip()
    var_match = re.search(r"\(define-fun\s+(\|[^|]+\|)\s+\(\)", stripped)
    if not var_match:
        return None, None, i

    var_name = var_match.group(1)
    type_match = re.search(r"\(\)\s+((?:\([^\)]+\)|[^\s\(]+))", stripped)
    if not type_match:
        return None, None, i

    type_end = type_match.end()
    remaining = stripped[type_end:].strip()
    if remaining and not remaining.startswith("("):
        value = remaining.rstrip(")").strip()
        return var_name, re.sub(r"\s+", " ", value.strip()), i

    value_parts: List[str] = []
    j = i + 1
    paren_depth = stripped.count("(") - stripped.count(")")
    while j < len(lines) and paren_depth > 0:
        next_line = lines[j].strip()
        paren_depth += next_line.count("(") - next_line.count(")")
        if paren_depth == 0:
            if next_line.endswith(")"):
                value_parts.append(next_line[:-1].strip())
            value = " ".join(value_parts).strip() if value_parts else ""
            if value:
                return var_name, re.sub(r"\s+", " ", value.strip()), j
            return None, None, j
        value_parts.append(next_line)
        j += 1

    value = " ".join(value_parts).strip() if value_parts else ""
    if value:
        return var_name, re.sub(r"\s+", " ", value.strip()), j - 1 if value_parts else i
    return None, None, j - 1 if value_parts else i


def parse_z3_model_assignments(model_output: str) -> Dict[str, str]:
    """Parse (define-fun |var| ...) value assignments from Z3 (get-model) output."""
    assignments: Dict[str, str] = {}
    lines = model_output.split("\n")
    i = 0
    while i < len(lines):
        var_name, value, last_i = _parse_define_fun_assignment_at_line(lines, i)
        if var_name and value:
            assignments[var_name] = value
            i = last_i + 1
        else:
            i += 1
    return assignments


def load_assume_guarantee_tester():
    """Load AssumeGuaranteeTester from sibling script (numeric module name)."""
    tester_path = Path(__file__).resolve().parent / "3_assume_guarantee_tester.py"
    if not tester_path.exists():
        raise FileNotFoundError(f"Missing tester script: {tester_path}")

    spec = importlib.util.spec_from_file_location("assume_guarantee_tester", tester_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {tester_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AssumeGuaranteeTester, module.AssumeGuaranteeFileGenerator


def extract_export_env_permitted_vars(content: str) -> list[str]:
    """Return sorted unique BGP_EXPORT_ENV *_permitted SMT identifiers."""
    return sorted(set(EXPORT_ENV_PERMITTED_DECL_RE.findall(content)), key=str.lower)


def strip_existing_export_env_assumes(lines: list[str]) -> list[str]:
    """Remove a previously injected EXPORT_ENV assume block (idempotent re-run)."""
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith(ASSUME_MARKER_PREFIX):
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if next_stripped == "":
                    i += 1
                    continue
                if EXPORT_ENV_PERMITTED_ASSERT_RE.match(next_stripped):
                    i += 1
                    continue
                break
            # Drop a single blank line left behind after the removed block.
            if i < len(lines) and lines[i].strip() == "":
                i += 1
            continue

        if EXPORT_ENV_PERMITTED_ASSERT_RE.match(stripped):
            i += 1
            continue

        cleaned.append(line)
        i += 1

    while len(cleaned) > 1 and cleaned[-1].strip() == "" and cleaned[-2].strip() == "":
        cleaned.pop()

    return cleaned


def build_assert_block(device: str, permitted_vars: list[str]) -> list[str]:
    block = [f"{ASSUME_MARKER_PREFIX} {device}"]
    block.extend(f"(assert (= {var} false))" for var in permitted_vars)
    return block


def insert_before_check_sat(lines: list[str], block: list[str]) -> list[str]:
    """Insert block before (check-sat), with one blank line on each side of the block."""
    check_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == "(check-sat)":
            check_idx = idx
            break
    if check_idx is None:
        raise ValueError("missing (check-sat)")

    prefix = lines[:check_idx]
    while prefix and prefix[-1].strip() == "":
        prefix.pop()

    suffix = lines[check_idx:]
    while len(suffix) > 1 and suffix[-1].strip() == "":
        suffix.pop()

    block_lines = [f"{line}\n" for line in block]
    return prefix + ["\n"] + block_lines + ["\n"] + suffix


def process_reverse_file(path: Path, dry_run: bool = False) -> tuple[str, int]:
    match = COMPLETE_REVERSE_RE.match(path.name)
    if not match:
        raise ValueError(f"unexpected filename: {path.name}")

    device = match.group(1)
    original = path.read_text(encoding="utf-8")
    permitted_vars = extract_export_env_permitted_vars(original)

    if not permitted_vars:
        logger.info("%s: no BGP_EXPORT_ENV *_permitted variables, skipped", path.name)
        return device, 0

    lines = original.splitlines(keepends=True)
    lines = strip_existing_export_env_assumes(lines)
    block = build_assert_block(device, permitted_vars)
    updated_lines = insert_before_check_sat(lines, block)
    updated = "".join(updated_lines)

    if updated == original:
        logger.info("%s: already up to date (%d asserts)", path.name, len(permitted_vars))
        return device, len(permitted_vars)

    if dry_run:
        logger.info("%s: would add %d EXPORT_ENV asserts", path.name, len(permitted_vars))
        return device, len(permitted_vars)

    path.write_text(updated, encoding="utf-8")
    logger.info("%s: added %d EXPORT_ENV asserts", path.name, len(permitted_vars))
    return device, len(permitted_vars)


def discover_devices(test_dir: Path, device_filter: str | None = None) -> list[str]:
    devices: set[str] = set()
    for path in test_dir.glob("complete_forward_*.smt2"):
        match = COMPLETE_FORWARD_RE.match(path.name)
        if match:
            devices.add(match.group(1))
    for path in test_dir.glob("complete_reverse_*.smt2"):
        match = COMPLETE_REVERSE_RE.match(path.name)
        if match:
            devices.add(match.group(1))

    if device_filter is not None:
        if device_filter not in devices:
            raise ValueError(
                f"Device '{device_filter}' not found in {test_dir} "
                f"(available: {', '.join(sorted(devices))})"
            )
        return [device_filter]

    return sorted(devices)


def patch_export_env_constraints(
    test_dir: Path,
    device_filter: str | None = None,
    dry_run: bool = False,
) -> tuple[int, int, int, int]:
    reverse_files = sorted(test_dir.glob("complete_reverse_*.smt2"))
    if device_filter is not None:
        reverse_files = [
            p for p in reverse_files if p.name == f"complete_reverse_{device_filter}.smt2"
        ]

    if not reverse_files:
        logger.error("No matching complete_reverse_*.smt2 files found in %s", test_dir)
        return 0, 0, 0, 1

    total_files = 0
    total_asserts = 0
    skipped = 0
    errors = 0

    for path in reverse_files:
        try:
            _, count = process_reverse_file(path, dry_run=dry_run)
            total_files += 1
            total_asserts += count
            if count == 0:
                skipped += 1
        except Exception as exc:
            errors += 1
            logger.error("%s: %s", path.name, exc)

    action = "Would update" if dry_run else "Updated"
    print(
        f"{action} {total_files} reverse file(s), "
        f"{total_asserts} EXPORT_ENV assert(s), "
        f"{skipped} skipped, "
        f"{errors} patch error(s)"
    )
    return total_files, total_asserts, skipped, errors


def extract_variables_from_constraints(constraints: str) -> Set[str]:
    return set(CONSTRAINT_VAR_RE.findall(constraints))


def parse_simple_equality_asserts(content: str) -> List[Tuple[str, str]]:
    """Return (var, value) pairs from simple (assert (= |var| value)) lines."""
    pairs: List[Tuple[str, str]] = []
    for line in content.splitlines():
        match = SIMPLE_ASSERT_EQ_RE.match(line.strip())
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def split_stable_states_normal(content: str) -> Tuple[str, str]:
    """Split stable_states_normal into constraint body and route-from footer."""
    lines = content.split("\n")
    body: List[str] = []
    footer: List[str] = []
    in_footer = False
    for line in lines:
        stripped = line.strip()
        if not in_footer and (
            stripped.startswith("route from:")
            or (
                stripped.startswith(";")
                and "BGP loop prevention" in stripped
                and "route origin" in stripped
            )
        ):
            in_footer = True
        if in_footer:
            footer.append(line)
        else:
            body.append(line)
    return "\n".join(body).rstrip(), "\n".join(footer).rstrip()


def update_simple_equality_constraint_file(path: Path, model: Dict[str, str]) -> int:
    """Rewrite simple equality asserts using model values; return number of updates."""
    if not path.exists():
        return 0

    original = path.read_text(encoding="utf-8")
    updated_lines: List[str] = []
    changes = 0

    for line in original.splitlines():
        match = SIMPLE_ASSERT_EQ_RE.match(line.strip())
        if match:
            var_name, _old_value = match.group(1), match.group(2)
            if var_name in model:
                new_value = model[var_name]
                if new_value != _old_value:
                    changes += 1
                updated_lines.append(f"(assert (= {var_name} {new_value}))")
                continue
        updated_lines.append(line)

    if changes:
        path.write_text("\n".join(updated_lines) + ("\n" if updated_lines else ""), encoding="utf-8")
    return changes


def extract_non_assert_lines(content: str) -> List[str]:
    """Return trailing non-(assert ...) lines such as prefixLength bounds."""
    lines = content.splitlines()
    tail: List[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            tail.insert(0, line)
            continue
        if stripped.startswith("(assert"):
            break
        tail.insert(0, line)
    return tail


def build_negated_or_constraint(pairs: Iterable[Tuple[str, str]]) -> str:
    parts = [f"(not (= {var} {value}))" for var, value in pairs]
    if not parts:
        return "false"
    if len(parts) == 1:
        return parts[0]
    return f"(or {' '.join(parts)})"


def regenerate_negated_stable_states(device: str, normal_content: str) -> str:
    pairs = parse_simple_equality_asserts(normal_content)
    inner = build_negated_or_constraint(pairs)
    return (
        f"; Negated stable states constraints for device: {device}\n"
        f"; Generated from dataplane analysis (negated mode)\n\n"
        f"(assert {inner})\n"
    )


def regenerate_negated_route_attributes(
    device: str,
    normal_content: str,
    negated_vars: Set[str],
    extra_lines: List[str],
) -> str:
    pairs = [(var, val) for var, val in parse_simple_equality_asserts(normal_content) if var in negated_vars]
    inner = build_negated_or_constraint(pairs)
    lines = [
        f"; Negated route attributes constraints for device: {device}",
        "; Generated from dataplane analysis (negated mode)",
        "",
        f"(assert {inner})",
    ]
    lines.extend(extra_lines)
    return "\n".join(lines) + "\n"


def _extract_constraint_content(constraint: str) -> str:
    constraint = constraint.strip()
    if constraint.startswith("(assert "):
        content = constraint[8:]
        if content.endswith(")"):
            content = content[:-1]
        return content.strip()
    return constraint


def build_combined_constraint_expr(
    normal_stable_states_constraints: List[str],
    negated_stable_states_constraints: List[str],
    negated_route_attributes_constraints: List[str],
) -> str:
    """Build combined negated constraint expression (same structure as 1_route_analyzer)."""
    negated_stable_contents = [
        c for c in (_extract_constraint_content(x) for x in negated_stable_states_constraints) if c
    ]
    normal_stable_contents = [
        c for c in (_extract_constraint_content(x) for x in normal_stable_states_constraints) if c
    ]
    negated_route_attrs_contents = [
        c for c in (_extract_constraint_content(x) for x in negated_route_attributes_constraints) if c
    ]

    if negated_stable_contents:
        negated_stable_part = (
            negated_stable_contents[0]
            if len(negated_stable_contents) == 1
            else f"(or {' '.join(negated_stable_contents)})"
        )
    else:
        negated_stable_part = "false"

    if normal_stable_contents:
        normal_stable_part = (
            normal_stable_contents[0]
            if len(normal_stable_contents) == 1
            else f"(and {' '.join(normal_stable_contents)})"
        )
    else:
        normal_stable_part = "true"

    if negated_route_attrs_contents:
        negated_route_attrs_part = (
            negated_route_attrs_contents[0]
            if len(negated_route_attrs_contents) == 1
            else f"(and {' '.join(negated_route_attrs_contents)})"
        )
    else:
        negated_route_attrs_part = "true"

    if normal_stable_part == "true" and negated_route_attrs_part == "true":
        combined_and_part = "true"
    elif normal_stable_part == "true":
        combined_and_part = negated_route_attrs_part
    elif negated_route_attrs_part == "true":
        combined_and_part = normal_stable_part
    else:
        combined_and_part = f"(and {normal_stable_part} {negated_route_attrs_part})"

    if negated_stable_part == "false" and combined_and_part == "true":
        return "true"
    if negated_stable_part == "false":
        return combined_and_part
    if combined_and_part == "true":
        return "true"
    return f"(or {negated_stable_part} {combined_and_part})"


def regenerate_combined_constraint_negated(
    device: str,
    normal_stable_content: str,
    negated_stable_content: str,
    negated_route_content: str,
    extra_lines: List[str],
) -> str:
    normal_pairs = parse_simple_equality_asserts(normal_stable_content)
    normal_stable_constraints = [f"(assert (= {var} {val}))" for var, val in normal_pairs]
    negated_stable_constraints = [line.strip() for line in negated_stable_content.splitlines() if line.strip().startswith("(assert")]
    negated_route_constraints = [
        line.strip() for line in negated_route_content.splitlines() if line.strip().startswith("(assert")
    ]
    combined_expr = build_combined_constraint_expr(
        normal_stable_constraints,
        negated_stable_constraints,
        negated_route_constraints,
    )
    lines = [
        f"; Combined constraint for device: {device}",
        "; Structure: (or (negated stable states) (and (normal stable states) (negated route attributes)))",
        "; Generated from route analysis",
        "",
        f"(assert {combined_expr})",
    ]
    lines.extend(extra_lines)
    return "\n".join(lines) + "\n"


def collect_target_constraint_vars(dataplane_dir: Path, device: str) -> Set[str]:
    """Variables from normal + combined negated constraint files for this device."""
    target_vars: Set[str] = set()
    for suffix in (
        "stable_states_normal.txt",
        "route_attributes_normal.txt",
        "combined_constraint_negated.txt",
    ):
        path = dataplane_dir / f"{device}_{suffix}"
        if path.exists():
            target_vars.update(extract_variables_from_constraints(path.read_text(encoding="utf-8")))
    return target_vars


def run_z3_get_model(smt_content: str) -> Tuple[bool, str, Dict[str, str]]:
    """Run Z3 with (get-model); return (is_sat, raw_output, assignments)."""
    content = append_get_model(smt_content.rstrip() + "\n")
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".smt2", delete=False, encoding="utf-8") as handle:
            handle.write(content)
            temp_file = handle.name

        result = subprocess.run(["z3", temp_file], capture_output=True, text=True)
        output = result.stdout.strip()
        is_sat, status = parse_z3_output(result)
        assignments = parse_z3_model_assignments(output) if is_sat else {}
        return is_sat, status if is_sat else output.splitlines()[0] if output else status, assignments
    finally:
        if temp_file:
            Path(temp_file).unlink(missing_ok=True)


def reconstruct_constraints_from_reverse_model(
    work_path: Path,
    device: str,
    model: Dict[str, str],
    *,
    verbose: bool = False,
) -> Tuple[int, List[str]]:
    """Update normal/combined constraint files using reverse SAT model values."""
    dataplane_dir = work_path / "1_dataplane_original"
    target_vars = collect_target_constraint_vars(dataplane_dir, device)
    scoped_model = {var: model[var] for var in target_vars if var in model}
    missing = sorted(var for var in target_vars if var not in model)

    if verbose:
        logger.info(
            "%s: applying model values to %d/%d constraint variable(s)",
            device,
            len(scoped_model),
            len(target_vars),
        )
    if missing and verbose:
        logger.info("%s: %d variable(s) missing from model (left unchanged)", device, len(missing))

    stable_normal_path = dataplane_dir / f"{device}_stable_states_normal.txt"
    route_normal_path = dataplane_dir / f"{device}_route_attributes_normal.txt"
    stable_negated_path = dataplane_dir / f"{device}_stable_states_negated.txt"
    route_negated_path = dataplane_dir / f"{device}_route_attributes_negated.txt"
    combined_path = dataplane_dir / f"{device}_combined_constraint_negated.txt"

    changes = 0
    changes += update_simple_equality_constraint_file(stable_normal_path, scoped_model)
    changes += update_simple_equality_constraint_file(route_normal_path, scoped_model)

    stable_normal_content = stable_normal_path.read_text(encoding="utf-8")
    route_normal_content = route_normal_path.read_text(encoding="utf-8")
    body, footer = split_stable_states_normal(stable_normal_content)
    if footer:
        stable_normal_path.write_text(body + "\n\n" + footer + "\n", encoding="utf-8")
        stable_normal_content = stable_normal_path.read_text(encoding="utf-8")

    negated_route_vars: Set[str] = set()
    if route_negated_path.exists():
        negated_route_vars = set(NEGATED_EQ_VAR_RE.findall(route_negated_path.read_text(encoding="utf-8")))
    route_extra = extract_non_assert_lines(
        route_negated_path.read_text(encoding="utf-8") if route_negated_path.exists() else ""
    )
    combined_extra = extract_non_assert_lines(
        combined_path.read_text(encoding="utf-8") if combined_path.exists() else ""
    )

    stable_negated_path.write_text(
        regenerate_negated_stable_states(device, body),
        encoding="utf-8",
    )
    route_negated_content = regenerate_negated_route_attributes(
        device,
        route_normal_content,
        negated_route_vars,
        route_extra,
    )
    route_negated_path.write_text(route_negated_content, encoding="utf-8")
    combined_path.write_text(
        regenerate_combined_constraint_negated(
            device,
            body,
            stable_negated_path.read_text(encoding="utf-8"),
            route_negated_content,
            combined_extra,
        ),
        encoding="utf-8",
    )

    updated_vars = sorted(
        var
        for var, value in scoped_model.items()
        if any(var in path.read_text(encoding="utf-8") for path in (stable_normal_path, route_normal_path))
    )
    return changes, updated_vars


def regenerate_ag_files(work_path: Path, device: str, *, verbose: bool = False) -> None:
    """Regenerate complete_forward/reverse from updated 1_dataplane_original constraints."""
    _, generator_cls = load_assume_guarantee_tester()
    generator = generator_cls(str(work_path), verbose=verbose)
    success, message = generator.generate_files_for_device(device)
    if not success:
        raise RuntimeError(message)


def refine_failed_devices_from_reverse_model(
    work_path: Path,
    results: Dict[str, Dict[str, Tuple[bool, str]]],
    *,
    device_filter: str | None = None,
    verbose: bool = False,
    dry_run: bool = False,
) -> Tuple[Dict[str, Dict[str, Tuple[bool, str]]], int]:
    """For reverse-SAT failures, rebuild constraints from reverse model and re-test."""
    test_dir = work_path / "3_assume_guarantee_test"
    candidates = [
        device
        for device, device_results in results.items()
        if device_results["reverse"][0]  # reverse SAT => counterexample available
    ]
    if device_filter is not None:
        candidates = [device for device in candidates if device == device_filter]

    if not candidates:
        return results, 0

    print(
        f"Attempting model-based constraint refinement for {len(candidates)} device(s) "
        f"with reverse SAT: {', '.join(candidates)}"
    )

    refined = 0
    for device in candidates:
        reverse_path = test_dir / f"complete_reverse_{device}.smt2"
        if not reverse_path.exists():
            logger.warning("%s: missing %s", device, reverse_path.name)
            continue

        reverse_content = reverse_path.read_text(encoding="utf-8")
        is_sat, status, model = run_z3_get_model(reverse_content)
        if not is_sat:
            logger.warning("%s: expected reverse SAT for get-model, got %s", device, status)
            continue

        if dry_run:
            target_vars = collect_target_constraint_vars(work_path / "1_dataplane_original", device)
            matched = sum(1 for var in target_vars if var in model)
            logger.info("%s: would update %d/%d constraint variable(s)", device, matched, len(target_vars))
            continue

        changes, updated_vars = reconstruct_constraints_from_reverse_model(
            work_path,
            device,
            model,
            verbose=verbose,
        )
        logger.info("%s: updated %d constraint value(s)", device, changes)
        if verbose and updated_vars:
            logger.info("%s: model-applied vars: %s", device, ", ".join(updated_vars[:10]))

        regenerate_ag_files(work_path, device, verbose=verbose)
        process_reverse_file(test_dir / f"complete_reverse_{device}.smt2")
        refined += 1

    if dry_run or refined == 0:
        return results, refined

    tester_cls, _ = load_assume_guarantee_tester()
    tester = tester_cls(str(work_path), device_filter=device_filter, verbose=verbose)
    for device in candidates[:refined]:
        forward_sat, forward_output = tester.test_forward_verification(device)
        reverse_sat, reverse_output = tester.test_reverse_verification(device)
        results[device] = {
            "forward": (forward_sat, forward_output),
            "reverse": (reverse_sat, reverse_output),
        }
        status = "PASS" if forward_sat and not reverse_sat else "FAIL"
        print(
            f"Device {device} after model refinement: {status} "
            f"(forward={'SAT' if forward_sat else 'UNSAT'}, "
            f"reverse={'SAT' if reverse_sat else 'UNSAT'})"
        )

    tester.print_summary(results)
    return results, refined


def run_assume_guarantee_tests(
    work_path: Path,
    device_filter: str | None = None,
    verbose: bool = False,
) -> tuple[Dict[str, Dict[str, Tuple[bool, str]]], bool]:
    """Run forward/reverse Z3 checks on existing complete_*.smt2 files."""
    test_dir = work_path / "3_assume_guarantee_test"
    devices = discover_devices(test_dir, device_filter=device_filter)
    if not devices:
        raise ValueError(f"No complete_forward/reverse files found in {test_dir}")

    tester_cls, _ = load_assume_guarantee_tester()
    tester = tester_cls(str(work_path), device_filter=device_filter, verbose=verbose)
    results: Dict[str, Dict[str, Tuple[bool, str]]] = {}

    print(f"Running Z3 assume-guarantee tests for {len(devices)} device(s)...")
    for device in devices:
        forward_sat, forward_output = tester.test_forward_verification(device)
        reverse_sat, reverse_output = tester.test_reverse_verification(device)
        results[device] = {
            "forward": (forward_sat, forward_output),
            "reverse": (reverse_sat, reverse_output),
        }

        forward_ok = forward_sat
        reverse_ok = not reverse_sat
        if verbose:
            logger.info(
                "%s: forward=%s reverse=%s status=%s",
                device,
                "SAT" if forward_sat else "UNSAT",
                "SAT" if reverse_sat else "UNSAT",
                "PASS" if forward_ok and reverse_ok else "FAIL",
            )
        elif forward_ok and reverse_ok:
            print(f"Device {device}: PASS (forward SAT, reverse UNSAT)")
        else:
            print(
                f"Device {device}: FAIL (forward={'SAT' if forward_sat else 'UNSAT'}, "
                f"reverse={'SAT' if reverse_sat else 'UNSAT'})"
            )

    tester.print_summary(results)
    return results, tester.all_tests_passed(results)


def main() -> None:
    verbose = False
    dry_run = False
    test_only = False
    device_filter: str | None = None
    work_dir: str | None = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-v", "--verbose"):
            verbose = True
            i += 1
        elif arg in ("-n", "--dry-run"):
            dry_run = True
            i += 1
        elif arg == "--test-only":
            test_only = True
            i += 1
        elif arg == "--device":
            if i + 1 >= len(args):
                print("Error: --device requires a value", file=sys.stderr)
                sys.exit(1)
            device_filter = args[i + 1]
            i += 2
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif not arg.startswith("-"):
            work_dir = arg
            i += 1
        else:
            print(f"Error: unknown option: {arg}", file=sys.stderr)
            sys.exit(1)

    if work_dir is None:
        print(
            "Usage: python3 3_internet2_refiner.py "
            "[-v] [-n] [--test-only] [--device DEVICE] <work_directory>",
            file=sys.stderr,
        )
        sys.exit(1)

    if not verbose:
        logging.getLogger().setLevel(logging.WARNING)

    work_path = Path(work_dir)
    if not work_path.is_dir():
        logger.error("Work directory does not exist: %s", work_dir)
        sys.exit(1)

    test_dir = work_path / "3_assume_guarantee_test"
    if not test_dir.is_dir():
        logger.error("Missing directory: %s", test_dir)
        sys.exit(1)

    patch_errors = 0
    if not test_only:
        _, _, _, patch_errors = patch_export_env_constraints(
            test_dir,
            device_filter=device_filter,
            dry_run=dry_run,
        )
        if patch_errors:
            sys.exit(1)
        if dry_run:
            print("Dry-run: skipping Z3 tests")
            return

    try:
        results, all_passed = run_assume_guarantee_tests(
            work_path,
            device_filter=device_filter,
            verbose=verbose,
        )
        if not all_passed:
            results, refined = refine_failed_devices_from_reverse_model(
                work_path,
                results,
                device_filter=device_filter,
                verbose=verbose,
                dry_run=False,
            )
            if refined:
                all_passed = load_assume_guarantee_tester()[0](
                    str(work_path), device_filter=device_filter, verbose=verbose
                ).all_tests_passed(results)
    except Exception as exc:
        logger.error("Z3 testing failed: %s", exc)
        sys.exit(1)

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
