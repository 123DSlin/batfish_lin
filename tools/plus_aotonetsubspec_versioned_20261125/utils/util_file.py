#!/usr/bin/env python3
"""
File utilities

This module provides utility functions for loading and saving files.
"""

import re
import os
import logging
from typing import List, Tuple, Optional, Dict, Set
from pathlib import Path

from utils import util_keyword
from utils import util_log

logger = logging.getLogger(__name__)


# ============================================================================
# Metadata (extract / find)
# ============================================================================

def extract_synthesis_metadata(synthesis_file_path: str) -> Tuple[List[str], List[str]]:
    """Extract metadata from synthesis file:
    1. All VAR type declarations (declare-fun)
    2. All commented Config variable assignments ;(assert (= Config_XXX value))
    """
    declare_funs = []
    commented_config_asserts = []

    if not os.path.exists(synthesis_file_path):
        logger.warning(f"Synthesis file not found: {synthesis_file_path}")
        return declare_funs, commented_config_asserts

    with open(synthesis_file_path, 'r') as f:
        lines = f.readlines()

    current_declare = []
    in_declare = False
    depth = 0

    for line in lines:
        stripped = line.strip()

        if '(declare-fun' in stripped:
            if in_declare:
                declare_fun_str = ' '.join(current_declare)
                declare_funs.append(declare_fun_str)
                current_declare = []
                in_declare = False
                depth = 0
            in_declare = True
            current_declare = [stripped]
            depth = stripped.count('(') - stripped.count(')')
            if depth == 0:
                declare_fun_str = ' '.join(current_declare)
                declare_funs.append(declare_fun_str)
                current_declare = []
                in_declare = False
                depth = 0
        elif in_declare:
            if stripped:
                current_declare.append(stripped)
                depth += stripped.count('(') - stripped.count(')')
            if depth == 0:
                declare_fun_str = ' '.join(current_declare)
                declare_funs.append(declare_fun_str)
                current_declare = []
                in_declare = False
                depth = 0

        if not in_declare and stripped.startswith(';') and '(assert (= Config_' in stripped:
            assert_part = stripped.lstrip(';').strip()
            if assert_part.startswith('(assert (= Config_'):
                if assert_part.count('(') == assert_part.count(')'):
                    commented_config_asserts.append(stripped)

    if in_declare and current_declare:
        declare_fun_str = ' '.join(current_declare)
        declare_funs.append(declare_fun_str)

    return declare_funs, commented_config_asserts


def find_metadata_file(
    config_name: str,
    device: str,
    metadata_type: str,
    metadata_dir: Path
) -> Optional[Path]:
    """Find metadata file for a given Config variable name, device, and metadata type."""
    safe_config_name = config_name.replace('/', '_').replace(':', '_').replace(' ', '_')
    expected_filename = f"synthesis_metadata_{metadata_type}_{device}_{safe_config_name}.txt"
    metadata_file = metadata_dir / expected_filename

    if metadata_file.exists():
        return metadata_file

    pattern = f"synthesis_metadata_{metadata_type}_{device}_{safe_config_name}*.txt"
    matching_files = list(metadata_dir.glob(pattern))
    if matching_files:
        return matching_files[0]

    pattern = f"synthesis_metadata_{metadata_type}_*_{safe_config_name}*.txt"
    matching_files = list(metadata_dir.glob(pattern))
    if matching_files:
        return matching_files[0]

    return None


# ============================================================================
# Load Functions
# ============================================================================

def load_model_igp(work_dir: Path) -> bool:
    """Load the model igp flag from 0_model_igp.txt.

    The file must contain either "0" or "1".
    """
    model_igp_file = work_dir / util_keyword.MODEL_IGP_FILE

    try:
        value = model_igp_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        util_log.log_error(
            f"Failed to load model IGP flag from {model_igp_file}: {exc}"
        )

    if value not in {"0", "1"}:
        util_log.log_error(
            f"Invalid model IGP flag in {model_igp_file}: "
            f"expected '0' or '1', got {value!r}"
        )

    util_log.log_info(f"Loaded model_igp.txt from {model_igp_file}: {value}")
    return value == "1"

def load_target_dst_ip(work_dir: Path) -> Optional[str]:
    """Load target dst-ip from 0_dst_ips.txt file if it exists."""
    dst_ip_file = work_dir / util_keyword.DST_IPS_FILE
    if dst_ip_file.exists():
        try:
            with open(dst_ip_file, 'r') as f:
                line = f.readline().strip()
                if line:
                    logger.info(f"Loaded target_dst_ip from {dst_ip_file}: {line}")
                    return line
        except Exception as e:
            logger.warning(f"Failed to read {dst_ip_file}: {e}")
    return None


def load_hostnames(work_dir: Path) -> List[str]:
    """Load device names from 0_hostnames.txt file."""
    hostnames_file = work_dir / "0_hostnames.txt"
    if not hostnames_file.exists():
        raise FileNotFoundError(f"Hostnames file not found: {hostnames_file}")

    devices = []
    with open(hostnames_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                devices.append(line)

    logger.info(f"Loaded {len(devices)} devices from {hostnames_file}: {devices}")
    return devices


def load_device_info(
    work_dir: Path,
    device_filter: Optional[str] = None
) -> List[str]:
    """Load device information from sliced SMT files."""
    logger.info("Loading device information...")

    if device_filter:
        hostnames_file = work_dir / "0_hostnames.txt"
        valid_devices = []

        if hostnames_file.exists():
            with open(hostnames_file, 'r') as f:
                valid_devices = [line.strip() for line in f if line.strip()]

            if device_filter not in valid_devices:
                error_msg = f"Device '{device_filter}' not found in 0_hostnames.txt\n"
                error_msg += f"Available devices: {', '.join(valid_devices)}"
                raise ValueError(error_msg)
            logger.info(f"Device '{device_filter}' validated against 0_hostnames.txt")
        else:
            logger.warning("0_hostnames.txt not found, will validate device from sliced SMT files")

    sliced_dir = work_dir / "1_sliced_device_smt_encoding"
    if not sliced_dir.exists():
        raise FileNotFoundError(f"Sliced SMT directory not found: {sliced_dir}")

    smt_files = list(sliced_dir.glob("sliced_*_smt_encoding.smt2"))
    devices = []
    all_devices_from_smt = []

    for smt_file in smt_files:
        match = re.search(r'sliced_(.+?)_smt_encoding\.smt2', smt_file.name)
        if match:
            device = match.group(1)
            all_devices_from_smt.append(device)
            if device_filter is None or device == device_filter:
                devices.append(device)

    if device_filter:
        if not devices:
            error_msg = f"Device '{device_filter}' not found in sliced SMT files\n"
            if all_devices_from_smt:
                error_msg += f"Available devices from SMT files: {', '.join(sorted(set(all_devices_from_smt)))}"
            raise ValueError(error_msg)
        logger.info(f"Filtered to device: {devices[0]}")
    else:
        logger.info(f"Found {len(devices)} devices: {devices}")

    return devices


# ============================================================================
# Save Functions
# ============================================================================

def save_synthesis_metadata(
    device: str,
    identifier: str,
    synthesis_file_path: str,
    metadata_dir: Path,
    metadata_type: str = "field"
) -> None:
    """Save synthesis file metadata to file."""
    declare_funs, commented_config_asserts = extract_synthesis_metadata(synthesis_file_path)

    safe_identifier = identifier.replace('/', '_').replace(':', '_').replace(' ', '_')
    output_file = metadata_dir / f"synthesis_metadata_{metadata_type}_{device}_{safe_identifier}.txt"

    with open(output_file, 'w') as f:
        f.write(f"; Synthesis file metadata for {metadata_type}-level subspec calculation\n")
        f.write(f"; Device: {device}\n")
        f.write(f"; Identifier: {identifier}\n")
        f.write(f"; Source file: {synthesis_file_path}\n")
        f.write("; " + "="*80 + "\n\n")

        f.write("; All VAR type declarations (declare-fun)\n")
        f.write("; " + "-"*78 + "\n")
        if declare_funs:
            for declare_fun in declare_funs:
                f.write(f"{declare_fun}\n")
        else:
            f.write("; No declare-fun declarations found\n")
        f.write("\n")

        f.write("; All commented Config variable assignments ;(assert (= Config_XXX value))\n")
        f.write("; " + "-"*78 + "\n")
        if commented_config_asserts:
            for commented_assert in commented_config_asserts:
                f.write(f"{commented_assert}\n")
        else:
            f.write("; No commented Config variable assignments found\n")
        f.write("\n")

        f.write("; " + "="*78 + "\n")
        f.write(f"; Summary: {len(declare_funs)} declare-fun declarations, {len(commented_config_asserts)} commented Config assignments\n")

    logger.info(f"    Synthesis metadata saved to: {output_file}")


def save_field_level_subspecs(
    output_file: Path,
    subspecs: Dict[str, Set[str]],
    exclude_config_names: Optional[Set[str]] = None,
) -> None:
    """Save field-level subspecs to file."""
    if exclude_config_names:
        subspecs = {k: v for k, v in subspecs.items() if k not in exclude_config_names}
    with open(output_file, 'w') as f:
        f.write("Field-Level Subspecs\n")
        f.write("====================\n\n")

        if not subspecs:
            f.write("No field-level subspecs found.\n")
        else:
            for config_name in sorted(subspecs.keys()):
                subspecs_set = subspecs[config_name]
                if subspecs_set and "empty" in subspecs_set and any(s != "empty" for s in subspecs_set):
                    subspecs_set = {s for s in subspecs_set if s != "empty"}
                f.write(f"Config Variable: {config_name}\n")
                if subspecs_set:
                    f.write(f"Subspecs ({len(subspecs_set)}):\n")
                    for i, subspec in enumerate(sorted(subspecs_set), 1):
                        if subspec.startswith("same_as_Line"):
                            line_num_match = re.match(r'same_as_Line(\d+)$', subspec)
                            if line_num_match:
                                line_num = line_num_match.group(1)
                                f.write(f"  {i}. same as Line{line_num}\n")
                            else:
                                line_num = subspec.replace("same_as_Line", "")
                                f.write(f"  {i}. same as Line{line_num}\n")
                        else:
                            f.write(f"  {i}. {subspec}\n")
                else:
                    f.write("No subspecs found.\n")
                f.write("-" * 50 + "\n\n")


def save_line_level_subspecs(
    output_file: Path,
    line_level_subspecs: Dict[str, Set[str]]
) -> None:
    """Save line-level subspecs to file."""
    with open(output_file, 'w') as f:
        f.write("Line-Level Subspecs\n")
        f.write("==================\n\n")

        if not line_level_subspecs:
            f.write("No line-level subspecs found.\n")
        else:
            for line_group_key in sorted(line_level_subspecs.keys()):
                subspecs_set = line_level_subspecs[line_group_key]
                f.write(f"Line Group: {line_group_key}\n")
                if subspecs_set:
                    f.write(f"Subspecs ({len(subspecs_set)}):\n")
                    for i, subspec in enumerate(sorted(subspecs_set), 1):
                        if subspec.startswith("same_as_Line"):
                            line_num_match = re.match(r'same_as_Line(\d+)$', subspec)
                            if line_num_match:
                                line_num = line_num_match.group(1)
                                f.write(f"  {i}. same as Line{line_num}\n")
                            else:
                                line_num = subspec.replace("same_as_Line", "")
                                f.write(f"  {i}. same as Line{line_num}\n")
                        else:
                            f.write(f"  {i}. {subspec}\n")
                else:
                    f.write("No subspecs found.\n")
                f.write("-" * 50 + "\n\n")


def load_line_level_subspecs_from_file(file_path: Path) -> Dict[str, List[str]]:
    """Load line-level subspecs from a line_level_subspecs.txt-format file."""
    subspecs: Dict[str, List[str]] = {}
    current_line_group: Optional[str] = None
    current_subspecs: List[str] = []

    if not file_path.exists():
        return subspecs

    subspec_line_re = re.compile(r'^\s*\d+\.\s+(.+)$', re.DOTALL)
    subspec_count_re = re.compile(r'Subspecs\s*\((\d+)\)\s*:?')

    try:
        with open(file_path, 'r') as f:
            lines = list(f)
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if line.startswith('Line Group:'):
                if current_line_group is not None:
                    subspecs[current_line_group] = current_subspecs
                current_line_group = line.replace('Line Group:', '').strip()
                current_subspecs = []
            elif line.startswith('Subspecs ('):
                m = subspec_count_re.match(line)
                if m:
                    n = int(m.group(1))
                    for _ in range(n):
                        if i >= len(lines):
                            break
                        next_line = lines[i].strip()
                        i += 1
                        subm = subspec_line_re.match(next_line)
                        if subm:
                            content = subm.group(1).strip()
                            if content.lower() != 'empty':
                                if content.startswith('same as Line'):
                                    line_num = content.replace('same as Line', '').strip()
                                    current_subspecs.append(f"same_as_Line{line_num}")
                                else:
                                    current_subspecs.append(content)
            elif line.startswith('-' * 50) or line == '':
                continue
        if current_line_group is not None:
            subspecs[current_line_group] = current_subspecs
    except Exception as e:
        logger.error(f"Failed to load line-level subspecs from {file_path}: {e}")
        return {}
    return subspecs


def _load_subspecs_from_output_file(
    file_path: Path,
    location_label: str,
) -> Dict[str, List[str]]:
    """Parse field_level_subspecs.txt / line_level_subspecs.txt into name -> subspec strings."""
    subspecs: Dict[str, List[str]] = {}
    current_name: Optional[str] = None
    current_subspecs: List[str] = []

    if not file_path.exists():
        return subspecs

    prefix = f"{location_label}:"
    subspec_line_re = re.compile(r'^\s*\d+\.\s+(.+)$')
    subspec_count_re = re.compile(r'Subspecs\s*\((\d+)\)\s*:?')

    try:
        with open(file_path, 'r') as f:
            lines = list(f)
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if line.startswith(prefix):
                if current_name is not None:
                    subspecs[current_name] = current_subspecs
                current_name = line[len(prefix):].strip()
                current_subspecs = []
            elif line.startswith('Subspecs ('):
                m = subspec_count_re.match(line)
                if m:
                    n = int(m.group(1))
                    for _ in range(n):
                        if i >= len(lines):
                            break
                        next_line = lines[i].strip()
                        i += 1
                        subm = subspec_line_re.match(next_line)
                        if subm:
                            current_subspecs.append(subm.group(1).strip())
            elif line.startswith('No subspecs found'):
                current_subspecs = []
            elif line.startswith('-' * 50) or line == '':
                continue
        if current_name is not None:
            subspecs[current_name] = current_subspecs
    except Exception as e:
        logger.error(f"Failed to load subspecs from {file_path}: {e}")
        return {}
    return subspecs


def load_field_level_subspecs_from_file(file_path: Path) -> Dict[str, List[str]]:
    """Load field-level subspecs from a field_level_subspecs.txt-format file."""
    return _load_subspecs_from_output_file(file_path, "Config Variable")


def nonempty_subspec_location_names(
    file_path: Path,
    *,
    level: str,
) -> Set[str]:
    """Return location names with at least one non-empty subspec entry."""
    if level == "field":
        parsed = _load_subspecs_from_output_file(file_path, "Config Variable")
    elif level == "line":
        parsed = _load_subspecs_from_output_file(file_path, "Line Group")
    else:
        raise ValueError(f"level must be 'field' or 'line', got {level!r}")

    nonempty: Set[str] = set()
    for name, entries in parsed.items():
        if any(entry.lower() != "empty" for entry in entries):
            nonempty.add(name)
    return nonempty


# ============================================================================
# Helper Functions
# ============================================================================

def get_subspec_output_file_path(
    subspec_files_dir: Path,
    subspec_type: str,
    device_filter: Optional[str] = None
) -> Path:
    """Get output file path for subspecs."""
    if device_filter:
        filename = f"{subspec_type}_level_subspecs_{device_filter}.txt"
    else:
        filename = f"{subspec_type}_level_subspecs.txt"

    return subspec_files_dir / filename
