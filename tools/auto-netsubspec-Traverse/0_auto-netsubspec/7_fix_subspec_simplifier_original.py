#!/usr/bin/env python3
"""
Subspec Simplifier

Modes (mutually exclusive):
  -s  Single-location: AG check, then per config field / line impact + subspec
  -m  Multi-location: AG check, MaxSMT soft localization on complete_forward_*,
      then joint subspec on each AG-fail slice only (up to REPAIR_OPTION_COUNT options)

Single-location pipeline (-s):
1. Load device information and extract Config variables from complete_forward files
2. Check assume-guarantee baselines per device; skip devices with forward SAT + reverse UNSAT
3. Impact check: complete_forward (device-level) + symbolic one config location
4. Subspec compute: same complete_forward baseline + Z3 simplify
5. Normalize and save subspecs

Multi-location pipeline (-m):
1. Load device information; run assume-guarantee baseline check
2. For each AG-fail slice: MaxSMT-enumerate up to REPAIR_OPTION_COUNT location sets
   (block prior soft-violation sets between solves); expand ip/mask partners
3. For each repair option: joint subspec on that option's per-slice locations
4. Save under 7_subspec_files/{REPAIR_OPTION_DIR_PREFIX}_{i}/ (locations + joint_subspecs.txt)

Author: Network Verification Team
Version: 1.0
"""

import re
import os
import sys
import logging
import subprocess
import tempfile
from typing import List, Dict, Set, Tuple, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field

# Import subspec normalizer
from utils.util_norm import normalize_subspec
# Import subspec utilities
from utils.util_smt import (
    extract_config_constraints_from_z3_goal,
    subspec_string_to_list,
    get_bounds_for_single_config_variable,
    get_bounds_for_multiple_config_variables,
    strip_subspec_suffixes,
    is_ip_mask_pair,
    extract_base_name_for_ip_mask,
    get_mask_variable_names_from_pairs,
    parse_z3_output,
    get_device_for_config_var,
    ModelConfigEqualitiesStore,
)
from utils.util_subspec import (
    ImpactCheckWriteMode,
    check_impact_reverse,
    emit_per_device_repair_summary,
    is_nonempty_subspec,
)
from utils.util_maxsmt import (
    MaxSmtLocalizeResult,
    expand_with_ip_mask_partners,
    list_config_equality_names,
    localize_k_violated_configs_from_forward,
)
from utils.util_subspec_joint import run_joint_for_localized_locations
from utils.util_keyword import (
    REPAIR_OPTION_COUNT,
    REPAIR_OPTION_DIR_PREFIX,
)
# Import subspec file utilities
from utils.util_file import (
    load_target_dst_ip,
    save_synthesis_metadata,
    load_hostnames,
    save_field_level_subspecs,
    save_line_level_subspecs,
    get_subspec_output_file_path,
    find_metadata_file,
)
# Import logging utilities
from utils.util_log import verbose_info, verbose_debug

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Stage-local dirs for multi-location (-m) path
JOINT_INTERMEDIATE_DIR = "7_intermediate_subspec_joint_files"
JOINT_OUTPUT_DIR = "7_subspec_files"
SOFT_INTERMEDIATE_DIR = "7_intermediate_subspec_soft_files"


@dataclass
class LocalizedRepairOption:
    """One MaxSMT repair option: per-host locations + model equalities for joint."""
    option_id: int
    locations_by_host: Dict[str, List[str]] = field(default_factory=dict)
    model_store: ModelConfigEqualitiesStore = field(
        default_factory=ModelConfigEqualitiesStore
    )

    @property
    def output_dir_name(self) -> str:
        return f"{JOINT_OUTPUT_DIR}/{REPAIR_OPTION_DIR_PREFIX}_{self.option_id}"

    @property
    def intermediate_dir_name(self) -> str:
        return f"{JOINT_INTERMEDIATE_DIR}/{REPAIR_OPTION_DIR_PREFIX}_{self.option_id}"


@dataclass
class ConfigVariable:
    """Represents a Config variable found in SMT files"""
    name: str
    value: str
    line_number: int
    file_path: str

@dataclass
class ConfigVariablePair:
    """Represents a pair of Config variables (e.g., ip/mask) that should be processed together"""
    ip_var: ConfigVariable
    mask_var: ConfigVariable
    base_name: str  # The common prefix (e.g., "Config_edge-19_RoutingPolicy_BGP_COMMON_EXPORT_POLICY_default__Line1__70_0_19_0")

@dataclass
class LineLevelConfigGroup:
    """Represents a group of Config variables that belong to the same LineX"""
    device: str
    line_id: str  # e.g., "Line1", "Line2"
    config_variables: List[ConfigVariable]  # All config variables in this line
    line_prefix: str  # e.g., "Config_r1_RouteFilterList_isp1_network__Line1__"

class SubspecSimplifier:
    """Main class for calculating field-level, line-level, or multi-location joint subspecs"""
    
    def __init__(self, 
                 work_dir: str, 
                 field_level_only: bool = False, 
                 line_level_only: bool = False, 
                 verbose: bool = False, 
                 device_filter: Optional[str] = None,
                 multi_location: bool = False):
        self.work_dir = Path(work_dir)
        self.verbose = verbose
        self.temp_dir_obj = None  # Reference to TemporaryDirectory object to prevent early cleanup
        self.device_filter = device_filter  # Optional device name filter for parallel processing
        self.multi_location = multi_location  # -m: MaxSMT localize + joint subspec
        
        self.devices = []
        self.config_variables = []
        self.subspecs = {}  # Dict[str, Set[str]] - Config variable name -> set of subspecs
        
        # Model-derived (= Config_... value) from impact check; used when Z3 simplify omits config vars.
        self.model_config_equalities = ModelConfigEqualitiesStore()
        
        # Line-level subspec related attributes
        self.line_level_groups = {}  # Dict[str, List[LineLevelConfigGroup]] - device -> list of line groups
        self.line_level_subspecs = {}  # Dict[str, Set[str]] - line group key -> set of subspecs
        
        # IP/Mask pair related attributes
        self.config_variable_pairs = []  # List[ConfigVariablePair] - ip/mask pairs
        self.pair_subspecs = {}  # Dict[str, Set[str]] - base_name -> set of subspecs
        
        # Multi-location (-m): MaxSMT repair options (option_id -> per-host locations)
        self.localized_repair_options: List[LocalizedRepairOption] = []
        
        # Computation summary (populated during calculate_*; printed once at the end of run())
        # Keys: "field", "pair", "line"
        self.subspec_compute_summary: Dict[str, Dict[str, int]] = {}
        
        # Load target_dst_ip for normalization
        self.target_dst_ip = load_target_dst_ip(self.work_dir)
        
        # Level selection flags (-s only; ignored for -m)
        self.field_level_only = field_level_only
        self.line_level_only = line_level_only
        
        # Validate that both flags are not set at the same time
        if self.field_level_only and self.line_level_only:
            raise ValueError("Cannot specify both -f and -l flags at the same time")
        if self.multi_location and (self.field_level_only or self.line_level_only):
            raise ValueError("Cannot combine -m with -f or -l")
        
        # Validate required input files/directories
        self._validate_input_files()

        # Initialize output directories (final outputs always go under work_dir;
        # intermediate dirs go under work_dir in verbose mode, otherwise a temp dir).
        self._init_output_dirs()

        # Devices with forward SAT + reverse UNSAT (skip impact check); filled by check_baseline().
        self.devices_ag_passed: Set[str] = set()
        # AG-fail devices that received at least one non-empty subspec (field/line/pair/joint).
        self.devices_with_repair_subspec: Set[str] = set()

    def _init_output_dirs(self) -> None:
        """Create output directories and decide where intermediate files live.

        - Verbose: keep intermediates under work_dir for inspection.
        - Non-verbose: write intermediates into a TemporaryDirectory (auto-cleaned).
        """
        base_dir: Path
        if self.verbose:
            base_dir = self.work_dir
        else:
            self.temp_dir_obj = tempfile.TemporaryDirectory()
            base_dir = Path(self.temp_dir_obj.name)
            logger.info(
                "Verbose mode disabled. Intermediate files will be stored in temporary directory: "
                f"{base_dir}"
            )

        # Final output files are always stored in work_dir.
        self.subspec_files_dir = self.work_dir / "7_subspec_files"
        self.subspec_files_dir.mkdir(exist_ok=True, parents=True)

        # Intermediate files.
        self.subspec_baseline_files_dir = base_dir / "7_intermediate_subspec_metadata_files"
        self.subspec_baseline_files_dir.mkdir(exist_ok=True, parents=True)

        self.field_level_intermediate_dir = base_dir / "7_intermediate_subspec_field_files"
        self.field_level_intermediate_dir.mkdir(exist_ok=True, parents=True)

        self.line_level_intermediate_dir = base_dir / "7_intermediate_subspec_line_files"
        self.line_level_intermediate_dir.mkdir(exist_ok=True, parents=True)

        # Soft MaxSMT intermediates (-m); kept under work_dir when verbose.
        self.soft_intermediate_dir = base_dir / SOFT_INTERMEDIATE_DIR
        self.soft_intermediate_dir.mkdir(exist_ok=True, parents=True)
    
    def _validate_input_files(self) -> None:
        """Validate that all required input files and directories exist"""
        missing_items = []
        
        # Check sliced device directory
        sliced_dir = self.work_dir / "2_sliced_device_smt_encoding"
        if not sliced_dir.exists():
            missing_items.append("2_sliced_device_smt_encoding/ (directory)")
        else:
            # Check if directory contains at least one sliced SMT file
            smt_files = list(sliced_dir.glob("sliced_*_smt_encoding.smt2"))
            if not smt_files:
                missing_items.append("2_sliced_device_smt_encoding/ (no sliced SMT files found)")
        
        # Check assume-guarantee complete files directory
        ag_dir = self.work_dir / "3_assume_guarantee_test"
        if not ag_dir.exists():
            missing_items.append("3_assume_guarantee_test/ (directory)")
        else:
            forward_files = list(ag_dir.glob("complete_forward_*.smt2"))
            reverse_files = list(ag_dir.glob("complete_reverse_*.smt2"))
            if not forward_files:
                missing_items.append("3_assume_guarantee_test/complete_forward_*.smt2 (missing)")
            if not reverse_files:
                missing_items.append("3_assume_guarantee_test/complete_reverse_*.smt2 (missing)")
        
        if missing_items:
            logger.error(f"Missing required input files/directories: {', '.join(missing_items)}")
            logger.error(f"Work directory: {self.work_dir}")
            logger.error("Hint: run `python3 2_smt_slicer.py <work_dir>` after `1_route_analyzer.py` to generate complete_forward/reverse.")
            sys.exit(1)
        
        logger.info("All required input files/directories found")
    
    def load_device_info(self) -> None:
        """Load device names from 0_hostnames.txt (single source of truth).
        When device_filter is set, validate and use only that device.
        extract_config_variables and pair check/compute use a canonical order (devices that have the required files, sorted) so result does not depend on hostnames order."""
        devices = load_hostnames(self.work_dir)
        if self.device_filter:
            if self.device_filter not in devices:
                error_msg = f"Device '{self.device_filter}' not found in 0_hostnames.txt\n"
                error_msg += f"Available devices: {', '.join(devices)}"
                raise ValueError(error_msg)
            devices = [self.device_filter]
            logger.info(f"Filtered to device: {devices[0]}")
        self.devices = devices

    def _devices_with_complete_forward(self) -> List[str]:
        """Devices in self.devices that have complete_forward file, in sorted order."""
        return sorted(
            d for d in self.devices
            if self._impact_check_baseline_file(d).exists()
        )

    def _impact_check_baseline_file(self, device: str) -> Path:
        return self.work_dir / "3_assume_guarantee_test" / f"complete_forward_{device}.smt2"

    def _devices_with_complete_forward_and_reverse(self) -> List[str]:
        """Devices in self.devices that have both AG baseline files, in sorted order."""
        ag_dir = self.work_dir / "3_assume_guarantee_test"
        return sorted(
            d for d in self.devices
            if (ag_dir / f"complete_forward_{d}.smt2").exists()
            and (ag_dir / f"complete_reverse_{d}.smt2").exists()
        )

    def _run_z3_on_smt2_file(self, smt2_path: Path) -> Tuple[bool, str]:
        """Run Z3 on an SMT2 file; return (is_sat, status_message)."""
        try:
            result = subprocess.run(['z3', str(smt2_path)], capture_output=True, text=True)
            return parse_z3_output(result)
        except Exception as e:
            logger.error(f"Error running Z3 on {smt2_path}: {e}")
            return False, str(e)

    def check_baseline(self) -> bool:
        """Run AG baseline check per device; populate self.devices_ag_passed.

        Returns:
            True if at least one device needs impact check, False if all tested devices passed AG.
        """
        logger.info("Checking assume-guarantee baselines before impact check...")
        self.devices_ag_passed = set()
        ag_dir = self.work_dir / "3_assume_guarantee_test"
        devices = self._devices_with_complete_forward_and_reverse()
        if not devices:
            msg = (
                "No devices with both complete_forward and complete_reverse files; "
                "cannot run baseline check."
            )
            logger.error(msg)
            print(msg)
            return False

        devices_needing_impact_check: Set[str] = set()
        for device in devices:
            forward_path = ag_dir / f"complete_forward_{device}.smt2"
            reverse_path = ag_dir / f"complete_reverse_{device}.smt2"
            forward_sat, forward_status = self._run_z3_on_smt2_file(forward_path)
            reverse_sat, reverse_status = self._run_z3_on_smt2_file(reverse_path)
            passed = forward_sat and not reverse_sat
            verbose_info(
                self.verbose,
                f"  {device}: forward={'SAT' if forward_sat else 'UNSAT'} ({forward_status}), "
                f"reverse={'SAT' if reverse_sat else 'UNSAT'} ({reverse_status}), "
                f"AG={'pass' if passed else 'fail'}",
            )
            if passed:
                self.devices_ag_passed.add(device)
            else:
                devices_needing_impact_check.add(device)

        if self.devices_ag_passed:
            logger.info(
                f"Devices passing AG testing (skip impact check): {sorted(self.devices_ag_passed)}"
            )
        if devices_needing_impact_check:
            logger.info(
                f"Devices needing impact check: {sorted(devices_needing_impact_check)}"
            )

        if not devices_needing_impact_check:
            msg = (
                "All complete_forward files are SAT and all complete_reverse files are UNSAT: "
                "assume-guarantee verification passes under the current configuration. "
                "Skipping impact check and subspec computation."
            )
            logger.warning(msg)
            print(msg)
            return False

        return True

    def _should_run_impact_check_for_device(self, device: str) -> bool:
        """True if this device's Config locations should run impact check + subspec compute."""
        return device not in self.devices_ag_passed

    def _devices_needing_repair(self) -> Set[str]:
        """Devices that failed AG testing and may need a repair subspec."""
        return {
            d for d in self._devices_with_complete_forward_and_reverse()
            if d not in self.devices_ag_passed
        }

    def _record_device_repair_subspec(self, device: Optional[str], subspec: Optional[str]) -> None:
        if device and is_nonempty_subspec(subspec):
            self.devices_with_repair_subspec.add(device)

    def _emit_repair_summary(self) -> None:
        emit_per_device_repair_summary(
            self._devices_needing_repair(),
            self.devices_with_repair_subspec,
        )

    def _devices_with_sliced(self) -> List[str]:
        """Devices in self.devices that have sliced SMT file, in sorted order (canonical for extract_line_level_config_groups)."""
        return sorted(
            d for d in self.devices
            if (self.work_dir / "2_sliced_device_smt_encoding" / f"sliced_{d}_smt_encoding.smt2").exists()
        )
    
    def extract_ip_mask_pairs(self) -> None:
        """Extract ip/mask pairs from config variables"""
        logger.info("Extracting ip/mask pairs from config variables...")
        
        self.config_variable_pairs = []
        
        # Group config variables by their base names, but only keep unique variables
        base_name_to_vars = {}  # Dict[str, Dict[str, ConfigVariable]] - base_name -> {var_name: config_var}
        
        for config_var in self.config_variables:
            base_name = extract_base_name_for_ip_mask(config_var.name)
            if base_name != config_var.name:  # Only process ip/mask variables
                if base_name not in base_name_to_vars:
                    base_name_to_vars[base_name] = {}
                # Only keep the first occurrence of each variable name
                if config_var.name not in base_name_to_vars[base_name]:
                    base_name_to_vars[base_name][config_var.name] = config_var
        
        # Find pairs
        for base_name, vars_dict in base_name_to_vars.items():
            vars_list = list(vars_dict.values())
            if len(vars_list) == 2:
                # Check if this is an ip/mask pair
                var1, var2 = vars_list[0], vars_list[1]
                if is_ip_mask_pair(var1.name, var2.name):
                    # Determine which is ip and which is mask
                    if var1.name.endswith('__ip'):
                        ip_var, mask_var = var1, var2
                    else:
                        ip_var, mask_var = var2, var1
                    
                    pair = ConfigVariablePair(
                        ip_var=ip_var,
                        mask_var=mask_var,
                        base_name=base_name
                    )
                    self.config_variable_pairs.append(pair)
                    logger.info(f"Found ip/mask pair: {ip_var.name} + {mask_var.name}")
                else:
                    logger.warning(f"Two variables with same base name but not ip/mask pair: {var1.name}, {var2.name}")
            elif len(vars_list) > 2:
                logger.warning(f"More than 2 variables with same base name: {base_name}")
                logger.warning(f"Variables: {[var.name for var in vars_list]}")
            elif len(vars_list) == 1:
                logger.info(f"Only one variable found for base name {base_name}: {vars_list[0].name}")
        
        logger.info(f"Found {len(self.config_variable_pairs)} ip/mask pairs")
    
    def extract_line_level_config_groups(self) -> None:
        """Extract line-level config groups from sliced SMT files"""
        logger.info("Extracting line-level config groups...")
        
        self.line_level_groups = {}
        # Use canonical order (devices that have sliced file, sorted) so consistent with other steps
        for device in self._devices_with_sliced():
            logger.info(f"Extracting line-level config groups for device: {device}")
            device_groups = []
            
            # Load sliced SMT file
            sliced_file = self.work_dir / "2_sliced_device_smt_encoding" / f"sliced_{device}_smt_encoding.smt2"
            if not sliced_file.exists():
                logger.warning(f"Sliced SMT file not found for device {device}: {sliced_file}")
                continue
            
            with open(sliced_file, 'r') as f:
                lines = f.readlines()
            
            # Extract Config variables with LineX pattern
            line_configs = {}  # Dict[str, List[ConfigVariable]] - line_prefix -> list of configs
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Look for Config variable assignments (both active and commented)
                match = re.search(r'^;?\s*\(assert \(= (Config_\S+) (\S+)\)\)', line)
                if match:
                    config_name = match.group(1)
                    config_value = match.group(2)
                    is_commented = line.strip().startswith(';')
                    
                    # Check if this is a LineX config variable (__Linei or __Linei__linej)
                    line_prefix = self._get_line_prefix_from_config_name(config_name)
                    if line_prefix:
                        config_var = ConfigVariable(
                            name=config_name,
                            value=config_value,
                            line_number=line_num,
                            file_path=str(sliced_file)
                        )
                        
                        if line_prefix not in line_configs:
                            line_configs[line_prefix] = []
                        line_configs[line_prefix].append(config_var)
                        
                        logger.info(f"    Found LineX config: {config_name} = {config_value}")
            
            # Group configs by LineX and create LineLevelConfigGroup objects
            for line_prefix, config_vars in line_configs.items():
                # Extract line ID: "Line1", "Line2" or "Line1__line1", "Line1__line2" when __linej present
                line_id_match = re.search(r'__Line(\d+)__[Ll]ine(\d+)$', line_prefix)
                if line_id_match:
                    line_id = f"Line{line_id_match.group(1)}__line{line_id_match.group(2)}"
                else:
                    line_id_match = re.search(r'__Line(\d+)$', line_prefix)
                    if line_id_match:
                        line_id = f"Line{line_id_match.group(1)}"
                    else:
                        line_id = line_prefix
                
                line_group = LineLevelConfigGroup(
                    device=device,
                    line_id=line_id,
                    config_variables=config_vars,
                    line_prefix=line_prefix
                )
                device_groups.append(line_group)
                logger.info(f"  Created line group: {device} - {line_id} with {len(config_vars)} config variables")
            
            self.line_level_groups[device] = device_groups
            logger.info(f"Found {len(device_groups)} line-level config groups for device {device}")
        
        # Log summary
        total_groups = sum(len(groups) for groups in self.line_level_groups.values())
        logger.info(f"Total line-level config groups found: {total_groups}")
    
    def extract_config_variables(self) -> None:
        """Extract Config variables from complete_forward files.

        When --device is specified, extracts all Config variables from the device-specific
        complete_forward_{device}.smt2 file. The file itself is already device-specific,
        so no additional filtering by Config variable name prefix is needed.
        """
        logger.info("Extracting Config variables from complete_forward files...")
        
        self.config_variables = []
        self.config_vars_by_name = {}  # Dict[str, List[ConfigVariable]] - config name -> list of variables
        self.config_vars_by_device = {}  # Dict[str, List[ConfigVariable]] - device -> list of variables
        
        for device in self._devices_with_complete_forward():
            logger.info(f"Extracting Config variables from complete_forward file for device: {device}")
            device_config_vars = []
            
            complete_forward_file = self._impact_check_baseline_file(device)
            if not complete_forward_file.exists():
                logger.warning(f"Complete forward file not found for device {device}: {complete_forward_file}")
                continue
            
            with open(complete_forward_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Look for Config variable assignments (both active and commented)
                    match = re.search(r'^;?\s*\(assert \(= (Config_\S+) (\S+)\)\)', line)
                    if match:
                        config_name = match.group(1)
                        config_value = match.group(2)
                        is_commented = line.strip().startswith(';')
                        
                        config_var = ConfigVariable(
                            name=config_name,
                            value=config_value,
                            line_number=line_num,
                            file_path=str(complete_forward_file)
                        )
                        device_config_vars.append(config_var)
                        
                        # Group by config name
                        if config_name not in self.config_vars_by_name:
                            self.config_vars_by_name[config_name] = []
                        self.config_vars_by_name[config_name].append(config_var)
                        
                        logger.info(f"    Found {'commented' if is_commented else 'active'} Config variable: {config_name} = {config_value}")
            
            self.config_vars_by_device[device] = device_config_vars
            self.config_variables.extend(device_config_vars)
            logger.info(f"Found {len(device_config_vars)} Config variables in complete_forward file for device {device}")
        
        logger.info(f"Total Config variable instances found: {len(self.config_variables)}")
        logger.info(f"Unique Config variables found: {len(self.config_vars_by_name)}")
        for config_name, vars_list in self.config_vars_by_name.items():
            devices = [get_device_for_config_var(var, self.devices) for var in vars_list]
            devices_filtered = [d for d in devices if d is not None]
            if devices_filtered:
                logger.info(f"  {config_name}: found in {len(vars_list)} complete_forward files: {sorted(set(devices_filtered))}")
            else:
                logger.warning(f"  {config_name}: found in {len(vars_list)} complete_forward files, but could not determine device names")
    
    def _get_line_prefix_from_config_name(self, config_name: str) -> Optional[str]:
        """Extract line prefix for 'same line' grouping. Supports two formats:
        - __Linei only: prefix = ...__Linei (same line = same __Linei)
        - __Linei__linej: prefix = ...__Linei__linej (same line = same __Linei__linej only)
        """
        # Support both __line and __Line for linej.
        m = re.search(r'(Config_\S+__Line\d+__[Ll]ine\d+)', config_name)
        if m:
            return m.group(1)
        m = re.search(r'(Config_\S+__Line\d+)', config_name)
        if m:
            return m.group(1)
        return None

    def _extract_line_prefix_from_config_name(self, config_name: str) -> Optional[str]:
        """Extract line prefix from a Config variable name (RouteFilterList / line-level stats).
        Supports both __Linei and __Linei__linej formats.
        """
        m = re.search(r'(Config_\S+_RouteFilterList_\S+__Line\d+__[Ll]ine\d+)', config_name)
        if m:
            return m.group(1)
        m = re.search(r'(Config_\S+_RouteFilterList_\S+__Line\d+)', config_name)
        if m:
            return m.group(1)
        m = re.search(r'(Config_\S+__Line\d+__[Ll]ine\d+)', config_name)
        if m:
            return m.group(1)
        m = re.search(r'(Config_\S+__Line\d+)', config_name)
        if m:
            return m.group(1)
        return None
    
    def _get_ip_mask_variable_names(self) -> Set[str]:
        """Get all ip/mask variable names that should be skipped in individual processing"""
        ip_mask_variable_names = set()
        for config_pair in self.config_variable_pairs:
            ip_mask_variable_names.add(config_pair.ip_var.name)
            ip_mask_variable_names.add(config_pair.mask_var.name)
        return ip_mask_variable_names
    
    def _calculate_field_level_statistics(self, ip_mask_variable_names: Set[str]) -> None:
        """Calculate and store statistics for field-level subspec computation"""
        rfl_total = 0
        rfl_compute = 0
        other_total = 0
        other_compute = 0
        config_vars_to_process = self.config_vars_by_name
        
        for config_name in self.config_vars_by_name.keys():
            if config_name in ip_mask_variable_names:
                continue
            if self._extract_line_prefix_from_config_name(config_name):
                rfl_total += 1
                if config_name in config_vars_to_process:
                    rfl_compute += 1
            else:
                other_total += 1
                if config_name in config_vars_to_process:
                    other_compute += 1
        
        self.subspec_compute_summary["field"] = {
            "total": rfl_total + other_total,
            "compute": rfl_compute + other_compute,
            "skipped": (rfl_total + other_total) - (rfl_compute + other_compute),
            "rfl_total": rfl_total,
            "rfl_compute": rfl_compute,
            "other_total": other_total,
            "other_compute": other_compute,
        }

    def _prepare_metadata_file(self, config_var: ConfigVariable, device: str) -> Optional[str]:
        """Prepare metadata file for normalization
        
        Returns:
            Path to metadata file if successful, None otherwise
        """
        safe_config_name = config_var.name.replace('/', '_').replace(':', '_').replace(' ', '_')
        compute_subspec_file = self.field_level_intermediate_dir / f"compute_subspec_from_{device}_{safe_config_name}.smt2"
        
        if not compute_subspec_file.exists():
            logger.warning(f"Compute subspec file not found: {compute_subspec_file}")
            return None
        
        if not self.subspec_baseline_files_dir:
            return None
        
        # Save metadata file for normalization (always needed, but saved to temp dir in non-verbose mode)
        save_synthesis_metadata(device, config_var.name, str(compute_subspec_file), self.subspec_baseline_files_dir, "field")
        # Find the metadata file we just created
        metadata_file = find_metadata_file(config_var.name, device, "field", self.subspec_baseline_files_dir)
        return metadata_file
    
    def _normalize_subspec_with_metadata(
        self, 
        subspec: str, 
        config_var: ConfigVariable, 
        metadata_file: Optional[str]
    ) -> str:
        """Normalize subspec using metadata file
        
        Returns:
            Normalized subspec, or original subspec if normalization fails
        """
        if not metadata_file:
            verbose_debug(self.verbose, f"  Metadata file not found for {config_var.name}, skipping normalization")
            return subspec
        
        try:
            core, suffix = strip_subspec_suffixes(subspec)
            normalized_subspec = normalize_subspec(
                core,
                metadata_file,
                config_var.name,
                is_field_level=True,
                is_pair=False,
                target_dst_ip=self.target_dst_ip,
                max_iterations=3,
                verbose=self.verbose,
                temp_dir=self.field_level_intermediate_dir
            )
            verbose_info(self.verbose, f"  Normalized subspec: {normalized_subspec}")
            return normalized_subspec + suffix
        except Exception as e:
            logger.warning(f"  Failed to normalize subspec for {config_var.name}: {e}")
            return subspec
    
    def _calculate_subspec_for_config_var(
        self,
        config_var: ConfigVariable,
        device: str,
        config_name: str
    ) -> Optional[str]:
        """Calculate subspec for a single config variable occurrence
        
        Returns:
            Subspec string if found, None if no subspec (empty simplification output), "empty" if no impact
        """
        # Check if variable has impact on synthesis-style forward baseline
        if not self._check_subspec_field_level(config_var, device):
            logger.info(f"  Empty subspec (no impact on synthesis forward baseline)")
            return "empty"
        
        # Calculate subspec using synthesis
        subspec = self._compute_subspec_field_level(config_var, device)
        if not subspec:
            logger.info(f"  No subspec found (empty simplification output)")
            return None
        
        # Prepare metadata file for normalization
        metadata_file = self._prepare_metadata_file(config_var, device)
        
        # Normalize subspec
        normalized_subspec = self._normalize_subspec_with_metadata(subspec, config_var, metadata_file)
        logger.info(f"  Subspec: {normalized_subspec}")
        return normalized_subspec
    
    def _process_single_config_variable(self, config_name: str, config_vars_list: List[ConfigVariable], ip_mask_variable_names: Set[str]) -> None:
        """Process a single config variable (all occurrences)"""
        # Skip ip/mask variables that are part of pairs
        if config_name in ip_mask_variable_names:
            logger.info(f"Skipping {config_name} - will be processed as part of ip/mask pair")
            return
        
        logger.info(f"Processing Config variable: {config_name}")
        logger.info(f"  Found in {len(config_vars_list)} sliced files")
        
        # Initialize set for collecting subspecs
        if config_name not in self.subspecs:
            self.subspecs[config_name] = set()
        
        # Process each occurrence of this Config variable
        for config_var in config_vars_list:
            device = get_device_for_config_var(config_var, self.devices)
            if not device:
                logger.warning(f"Could not determine device for Config variable {config_var.name}")
                continue
            
            logger.info(f"  Processing for device: {device}")

            if not self._should_run_impact_check_for_device(device):
                logger.info(f"  Skipping device {device} (passed assume-guarantee testing)")
                self.subspecs[config_name].add("empty")
                continue
            
            # Calculate subspec for this occurrence
            subspec = self._calculate_subspec_for_config_var(config_var, device, config_name)
            if subspec:
                self.subspecs[config_name].add(subspec)
                self._record_device_repair_subspec(device, subspec)
            # Delete field-level intermediate files and field metadata for this occurrence when not -v
            if device:
                safe_config_name = config_var.name.replace('/', '_').replace(':', '_').replace(' ', '_')
                self._delete_intermediate_files_for_target(self.field_level_intermediate_dir, device, safe_config_name)
                self._delete_metadata_file_for_target("field", device, safe_config_name)
        
        # Log final subspecs for this Config variable
        if self.subspecs[config_name]:
            logger.info(f"  Final subspecs for {config_name}: {list(self.subspecs[config_name])}")
        else:
            logger.info(f"  No subspecs found for {config_name}")
        
    def calculate_subspecs(self) -> None:
        """Calculate field-level subspecs: single config vars and ip-mask pairs (same pipeline, flag distinguishes)."""
        logger.info("Calculating field-level subspecs (single config vars and ip-mask pairs)...")
        
        ip_mask_variable_names = self._get_ip_mask_variable_names()
        self._calculate_field_level_statistics(ip_mask_variable_names)
        
        # Phase 1: single config variables (skip names that are part of ip-mask pairs)
        for config_name, config_vars_list in self.config_vars_by_name.items():
            self._process_single_config_variable(config_name, config_vars_list, ip_mask_variable_names)
        
        # Phase 2: ip-mask pairs (same canonical device set/order as extract_config_variables)
        self._process_field_level_pairs()
    
    def _process_field_level_pairs(self) -> None:
        """Process all ip-mask pairs at field-level (check + compute + normalize + merge into subspecs)."""
        canonical_devices = self._devices_with_complete_forward()
        available_devices = set(canonical_devices)
        device_to_index = {d: i for i, d in enumerate(canonical_devices)}
        config_pairs_in_scope = [
            p for p in self.config_variable_pairs
            if get_device_for_config_var(p.ip_var, self.devices) in available_devices
        ]
        config_pairs_to_process = [
            p for p in config_pairs_in_scope
            if self._should_run_impact_check_for_device(get_device_for_config_var(p.ip_var, self.devices))
        ]
        skipped = len(config_pairs_in_scope) - len(config_pairs_to_process)
        if skipped:
            logger.info(
                f"Skipping {skipped} pair(s) (passed AG testing; recording empty subspec)"
            )
        config_pairs_in_scope.sort(
            key=lambda p: (
                device_to_index.get(get_device_for_config_var(p.ip_var, self.devices), 999),
                p.base_name,
            )
        )
        rfl_total = rfl_compute = other_total = other_compute = 0
        base_names = {p.base_name for p in config_pairs_in_scope}
        for config_pair in config_pairs_in_scope:
            if self._extract_line_prefix_from_config_name(config_pair.ip_var.name):
                rfl_total += 1
                if config_pair.base_name in base_names:
                    rfl_compute += 1
            else:
                other_total += 1
                if config_pair.base_name in base_names:
                    other_compute += 1
        self.subspec_compute_summary["pair"] = {
            "total": rfl_total + other_total,
            "compute": rfl_compute + other_compute,
            "skipped": (rfl_total + other_total) - (rfl_compute + other_compute),
            "rfl_total": rfl_total,
            "rfl_compute": rfl_compute,
            "other_total": other_total,
            "other_compute": other_compute,
        }
        for config_pair in config_pairs_in_scope:
            logger.info(f"Processing config pair: {config_pair.base_name}")
            logger.info(f"  IP variable: {config_pair.ip_var.name}")
            logger.info(f"  Mask variable: {config_pair.mask_var.name}")
            if config_pair.base_name not in self.pair_subspecs:
                self.pair_subspecs[config_pair.base_name] = set()
            device = get_device_for_config_var(config_pair.ip_var, self.devices)
            if not self._should_run_impact_check_for_device(device):
                logger.info(f"  Skipping device {device} (passed assume-guarantee testing)")
                self.pair_subspecs[config_pair.base_name].add("empty")
            elif self._check_subspec_field_level_pair(config_pair):
                subspec = self._compute_subspec_field_level_pair(config_pair)
                if subspec:
                    normalized_subspec = subspec
                    if device:
                        safe_base_name = config_pair.base_name.replace('/', '_').replace(':', '_').replace(' ', '_')
                        compute_subspec_file = self.field_level_intermediate_dir / f"compute_subspec_from_{device}_{safe_base_name}.smt2"
                        metadata_file = None
                        if compute_subspec_file.exists() and self.subspec_baseline_files_dir:
                            save_synthesis_metadata(device, config_pair.base_name, str(compute_subspec_file), self.subspec_baseline_files_dir, "pair")
                            metadata_file = find_metadata_file(config_pair.base_name, device, "pair", self.subspec_baseline_files_dir)
                        elif not compute_subspec_file.exists():
                            logger.warning(f"Compute subspec file not found: {compute_subspec_file}")
                        if metadata_file:
                            try:
                                core, suffix = strip_subspec_suffixes(subspec)
                                normalized_subspec = normalize_subspec(
                                    core, metadata_file, config_pair.base_name,
                                    is_field_level=True, is_pair=True, target_dst_ip=self.target_dst_ip,
                                    max_iterations=3, verbose=self.verbose, temp_dir=self.field_level_intermediate_dir
                                )
                                normalized_subspec = normalized_subspec + suffix
                                verbose_info(self.verbose, f"  Normalized subspec: {normalized_subspec}")
                            except Exception as e:
                                logger.warning(f"  Failed to normalize subspec for {config_pair.base_name}: {e}")
                        else:
                            verbose_debug(self.verbose, f"  Metadata file not found for {config_pair.base_name}, skipping normalization")
                    self.pair_subspecs[config_pair.base_name].add(normalized_subspec)
                    self._record_device_repair_subspec(device, normalized_subspec)
                    logger.info(f"  Subspec: {normalized_subspec}")
                else:
                    logger.info(f"  No subspec found (empty simplification output)")
            else:
                logger.info(f"  Empty subspec (no impact on synthesis forward baseline)")
                self.pair_subspecs[config_pair.base_name].add("empty")
            ip_var_name = config_pair.ip_var.name
            if ip_var_name not in self.subspecs:
                self.subspecs[ip_var_name] = set()
            self.subspecs[ip_var_name].update(self.pair_subspecs[config_pair.base_name])
            if self.pair_subspecs[config_pair.base_name]:
                logger.info(f"  Final subspecs for {config_pair.base_name}: {list(self.pair_subspecs[config_pair.base_name])}")
                logger.info(f"  Added to IP variable {ip_var_name} field-level subspecs")
            else:
                logger.info(f"  No subspecs found for {config_pair.base_name}")
            # Delete ip-mask pair intermediate files and pair metadata when not -v
            if device:
                safe_base_name = config_pair.base_name.replace('/', '_').replace(':', '_').replace(' ', '_')
                self._delete_intermediate_files_for_target(self.field_level_intermediate_dir, device, safe_base_name)
                self._delete_metadata_file_for_target("pair", device, safe_base_name)
    
    def _comment_config_var_equality_and_add_bounds(self, lines: List[str], config_var: ConfigVariable) -> Tuple[List[str], bool]:
        """Comment out the config var equality line and add bounds for this single field (field-level).

        Returns:
            (modified_lines, config_line_found)
        """
        modified_lines = []
        config_line_found = False
        config_line_pattern = f"= {config_var.name} {config_var.value}"
        first_commented_index: Optional[int] = None
        for line in lines:
            if config_line_pattern in line and not line.strip().startswith(';'):
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

    def _delete_intermediate_files_for_target(
        self, intermediate_dir: Path, device: str, safe_name: str,
    ) -> None:
        """Delete check/compute/norm_iter intermediate files for one target (when not -v)."""
        if self.verbose or not intermediate_dir.exists():
            return
        to_remove = [
            intermediate_dir / f"check_subspec_from_{device}_{safe_name}.smt2",
            intermediate_dir / f"compute_subspec_from_{device}_{safe_name}.smt2",
        ]
        for p in to_remove:
            if p.exists():
                try:
                    os.unlink(p)
                except OSError:
                    pass
        for p in intermediate_dir.glob(f"compute_subspec_from_{device}_{safe_name}_norm_iter*.smt2"):
            try:
                os.unlink(p)
            except OSError:
                pass

    def _delete_metadata_file_for_target(self, metadata_type: str, device: str, safe_name: str) -> None:
        """Delete synthesis_metadata_{type}_{device}_{safe_name}.txt for field/pair only (when not -v). Line-level metadata is kept."""
        if self.verbose or metadata_type == "line" or not device or not self.subspec_baseline_files_dir or not self.subspec_baseline_files_dir.exists():
            return
        p = self.subspec_baseline_files_dir / f"synthesis_metadata_{metadata_type}_{device}_{safe_name}.txt"
        if p.exists():
            try:
                os.unlink(p)
            except OSError:
                pass
        for q in self.subspec_baseline_files_dir.glob(f"synthesis_metadata_{metadata_type}_{device}_{safe_name}*.txt"):
            try:
                os.unlink(q)
            except OSError:
                pass

    def _run_z3_simplify_and_parse(
        self, smt2_path: Path, log_label: str, parse_fn: Callable[[str], Optional[str]], cleanup_after: bool = False
    ) -> Optional[str]:
        """Run Z3 simplify on SMT2 file, log output, parse with parse_fn(stdout). Optionally unlink file after."""
        try:
            result = subprocess.run(['z3', str(smt2_path)], capture_output=True, text=True)
            output = result.stdout.strip()
            if result.stderr.strip():
                logger.warning(f"    Z3 stderr: {result.stderr.strip()}")
            if result.returncode != 0 and ("(error" in output or not output):
                logger.warning(f"    Z3 return code: {result.returncode}")
            if "(error" in output:
                error_lines = [l for l in output.split('\n') if l.startswith('(error')]
                if error_lines:
                    logger.warning(f"    Z3 compatibility issue detected: {'; '.join(error_lines)}")
            logger.info(f"    Z3 Simplification Results for {log_label}:")
            logger.info("    " + "=" * 60)
            for line in output.split('\n'):
                logger.info(f"    {line}")
            logger.info("    " + "=" * 60)
            return parse_fn(output)
        except Exception as e:
            logger.error(f"    Error running Z3: {e}")
            return None
        finally:
            if cleanup_after and smt2_path and os.path.exists(smt2_path):
                try:
                    os.unlink(smt2_path)
                except OSError:
                    pass

    def _check_subspec_field_level(self, config_var: ConfigVariable, device: str) -> bool:
        """Check if Config variable has impact on synthesis forward baseline. Returns True if SAT, False if UNSAT."""
        logger.info(f"  Checking synthesis forward impact for {config_var.name}")
        safe_config_name = config_var.name.replace('/', '_').replace(':', '_').replace(' ', '_')
        return check_impact_reverse(
            self._impact_check_baseline_file(device),
            [config_var],
            self.field_level_intermediate_dir,
            device,
            safe_config_name,
            self.model_config_equalities,
            baseline_has_check_sat=True,
            write_mode=ImpactCheckWriteMode.PERSISTENT,
            verbose=self.verbose,
            info_fn=lambda msg: verbose_info(self.verbose, msg),
        )

    def _write_compute_smt2_field_level(self, config_var: ConfigVariable, device: str) -> Optional[Path]:
        """Build and write compute SMT2 for field-level; return output path or None."""
        complete_forward_file = self._impact_check_baseline_file(device)
        if not complete_forward_file.exists():
            logger.error(f"Complete forward file not found for device {device}: {complete_forward_file}")
            return None
        with open(complete_forward_file, 'r') as f:
            lines = f.readlines()
        modified_lines, config_line_found = self._comment_config_var_equality_and_add_bounds(lines, config_var)
        if not config_line_found:
            logger.warning(f"Config variable {config_var.name} not found in complete_forward file")
            return None
        modified_content = ''.join(modified_lines)
        if "(check-sat)" in modified_content:
            modified_content = modified_content.replace(
                "(check-sat)",
                "; (check-sat)\n(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))"
            )
        elif "(check-sat)" not in modified_content:
            modified_content = modified_content.rstrip() + "\n; (check-sat)\n(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))\n"
        safe_config_name = config_var.name.replace('/', '_').replace(':', '_').replace(' ', '_')
        output_file = self.field_level_intermediate_dir / f"compute_subspec_from_{device}_{safe_config_name}.smt2"
        with open(output_file, 'w') as f:
            f.write(modified_content)
        logger.info(f"    Synthesis subspec file saved to: {output_file}")
        return output_file

    def _compute_subspec_field_level(self, config_var: ConfigVariable, device: str) -> Optional[str]:
        """Calculate subspec using synthesis file (Step 2)."""
        logger.info(f"  Calculating synthesis subspec for {config_var.name}")
        path = self._write_compute_smt2_field_level(config_var, device)
        return self._run_z3_simplify_and_parse(path, config_var.name, lambda o: self._parse_simplification_output(o, config_var)) if path else None
    
    def _parse_simplification_output(self, output: str, config_var: ConfigVariable) -> Optional[str]:
        """Parse Z3 simplification output to extract subspec"""
        logger.info(f"    Parsing simplification output for {config_var.name}")
        
        # Use utility function to extract constraints from Z3 goal
        config_names = {config_var.name}
        subspec = extract_config_constraints_from_z3_goal(output, config_names)
        
        if subspec:
            logger.info(f"    Config variable found in constraints: {subspec}")
            return subspec
        
        # Fallback: use model-correct equality from impact check
        subspec = self.model_config_equalities.equality_for(config_var.name)
        logger.info(f"    Config variable not in simplified goals; using model equality: {subspec}")
        return subspec
    
    def _comment_out_line_group(self, file_path: str, line_group: LineLevelConfigGroup, comment: bool = True) -> str:
        """Comment out or uncomment all config variables in a line group"""
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        modified_lines = []
        commented_var_names: List[str] = []
        first_commented_index: Optional[int] = None
        for i, line in enumerate(lines):
            line_num = i + 1
            line_content = line.strip()
            
            # Check if this line contains any config variable from the line group
            should_modify = False
            matching_config_var = None
            for config_var in line_group.config_variables:
                # Only check simple assert statements: (assert (= Config_xxx_LineX_... value))
                # Don't modify complex assert statements that contain multiple config variables
                if config_var.name in line_content and line_content.startswith('(assert (= Config_') and line_content.endswith('))'):
                    should_modify = True
                    matching_config_var = config_var
                    break
            
            if should_modify:
                if comment:
                    if not line_content.startswith(';'):
                        modified_lines.append(f"; {line_content}\n")
                        if first_commented_index is None:
                            first_commented_index = len(modified_lines) - 1
                        commented_var_names.append(matching_config_var.name)
                    else:
                        modified_lines.append(line)
                else:
                    if line_content.startswith(';'):
                        modified_lines.append(line[1:])
                    else:
                        modified_lines.append(line)
            else:
                modified_lines.append(line)
        
        # Insert deduplicated bounds once after the first commented equality line
        if comment and commented_var_names and first_commented_index is not None:
            bounds_to_add = get_bounds_for_multiple_config_variables(commented_var_names)
            if bounds_to_add:
                insert_pos = first_commented_index + 1
                bounds_lines = [f"{b}\n" for b in bounds_to_add]
                modified_lines = modified_lines[:insert_pos] + bounds_lines + modified_lines[insert_pos:]
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.smt2', delete=False) as temp_file:
            temp_file.writelines(modified_lines)
            return temp_file.name
    
    def _check_subspec_line_level(self, line_group: LineLevelConfigGroup) -> bool:
        """Check if line group has impact on synthesis forward baseline. Returns True if SAT, False if UNSAT."""
        logger.info(f"  Checking synthesis forward impact for line group: {line_group.device} - {line_group.line_id}")
        safe_line_prefix = line_group.line_prefix.replace('/', '_').replace(':', '_').replace(' ', '_')
        return check_impact_reverse(
            self._impact_check_baseline_file(line_group.device),
            line_group.config_variables,
            self.line_level_intermediate_dir,
            line_group.device,
            safe_line_prefix,
            self.model_config_equalities,
            baseline_has_check_sat=True,
            write_mode=ImpactCheckWriteMode.TEMP_WITH_DEBUG,
            verbose=self.verbose,
            info_fn=lambda msg: verbose_info(self.verbose, msg),
            cleanup_after=True,
        )

    def _write_compute_smt2_line_level(self, line_group: LineLevelConfigGroup) -> Optional[Path]:
        """Build and write one compute SMT2 file per line group (named up to __LineX only). Return path for Z3."""
        complete_forward_file = self._impact_check_baseline_file(line_group.device)
        if not complete_forward_file.exists():
            logger.error(f"Complete forward file not found for device {line_group.device}: {complete_forward_file}")
            return None
        temp_file_path = self._comment_out_line_group(str(complete_forward_file), line_group, comment=True)
        if not os.path.exists(temp_file_path):
            return None
        with open(temp_file_path, 'r') as f:
            content = f.read()
        if "(check-sat)" in content:
            content = content.replace(
                "(check-sat)",
                "; (check-sat)\n(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))"
            )
        elif "(check-sat)" not in content:
            content = content.rstrip() + "\n; (check-sat)\n(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))\n"
        safe_line_prefix = line_group.line_prefix.replace('/', '_').replace(':', '_').replace(' ', '_')
        out_file = self.line_level_intermediate_dir / f"compute_subspec_from_{line_group.device}_{safe_line_prefix}.smt2"
        with open(out_file, 'w') as f:
            f.write(content)
        logger.info(f"    Compute subspec file saved to: {out_file}")
        try:
            os.unlink(temp_file_path)
        except OSError:
            pass
        return out_file

    def _compute_subspec_line_level(self, line_group: LineLevelConfigGroup) -> Optional[str]:
        """Calculate subspec using synthesis file for a line group."""
        logger.info(f"  Calculating synthesis subspec for line group: {line_group.device} - {line_group.line_id}")
        path = self._write_compute_smt2_line_level(line_group)
        if not path:
            return None
        label = f"{line_group.device} - {line_group.line_id}"
        return self._run_z3_simplify_and_parse(path, label, lambda o: self._parse_line_group_simplification_output(o, line_group))
    
    def _parse_line_group_simplification_output(self, output: str, line_group: LineLevelConfigGroup) -> Optional[str]:
        """Parse Z3 simplification output to extract subspec for a line group"""
        logger.info(f"    Parsing simplification output for line group: {line_group.device} - {line_group.line_id}")
        
        # Use utility function to extract constraints from Z3 goal
        config_names = {config_var.name for config_var in line_group.config_variables}
        subspec = extract_config_constraints_from_z3_goal(output, config_names)
        
        # Convert to list for easier manipulation
        if subspec:
            subspec_parts = subspec_string_to_list(subspec)
        else:
            subspec_parts = []
        
        # Add model-correct equalities for config vars omitted by Z3 simplify
        self.model_config_equalities.append_missing_to_subspec(
            subspec_parts, line_group.config_variables, info=logger.info
        )
        
        if subspec_parts:
            subspec = " AND ".join(subspec_parts)
            logger.info(f"    Line group subspec (including replaced variables): {subspec}")
            return subspec
        
        subspec_parts = [
            self.model_config_equalities.equality_for(config_var.name)
            for config_var in line_group.config_variables
        ]
        subspec = " AND ".join(subspec_parts)
        logger.info(f"    Line group fallback model equalities: {subspec}")
        return subspec
    
    def _comment_out_config_pair(self, file_path: str, config_pair: ConfigVariablePair, comment: bool = True) -> str:
        """Comment out or uncomment both ip and mask variables in a config pair"""
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        modified_lines = []
        first_commented_index: Optional[int] = None
        for i, line in enumerate(lines):
            line_num = i + 1
            line_content = line.strip()
            
            should_modify = False
            if (config_pair.ip_var.name in line_content and line_content.startswith('(assert (= Config_') and line_content.endswith('))')):
                should_modify = True
            elif (config_pair.mask_var.name in line_content and line_content.startswith('(assert (= Config_') and line_content.endswith('))')):
                should_modify = True
            
            if should_modify:
                if comment:
                    if not line_content.startswith(';'):
                        modified_lines.append(f"; {line_content}\n")
                        if first_commented_index is None:
                            first_commented_index = len(modified_lines) - 1
                    else:
                        modified_lines.append(line)
                else:
                    if line_content.startswith(';'):
                        modified_lines.append(line[1:])
                    else:
                        modified_lines.append(line)
            else:
                modified_lines.append(line)
        
        if comment and first_commented_index is not None:
            bounds_to_add = get_bounds_for_multiple_config_variables(
                [config_pair.ip_var.name, config_pair.mask_var.name]
            )
            if bounds_to_add:
                insert_pos = first_commented_index + 1
                bounds_lines = [f"{b}\n" for b in bounds_to_add]
                modified_lines = modified_lines[:insert_pos] + bounds_lines + modified_lines[insert_pos:]
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.smt2', delete=False) as temp_file:
            temp_file.writelines(modified_lines)
            return temp_file.name
    
    def _check_subspec_field_level_pair(self, config_pair: ConfigVariablePair) -> bool:
        """Check if config pair has impact on synthesis forward baseline. Returns True if SAT, False if UNSAT."""
        logger.info(f"  Checking synthesis forward impact for config pair: {config_pair.base_name}")
        device = get_device_for_config_var(config_pair.ip_var, self.devices)
        if not device:
            logger.warning(f"Could not determine device for config pair {config_pair.base_name}")
            return False
        safe_base_name = config_pair.base_name.replace('/', '_').replace(':', '_').replace(' ', '_')
        return check_impact_reverse(
            self._impact_check_baseline_file(device),
            [config_pair.ip_var, config_pair.mask_var],
            self.field_level_intermediate_dir,
            device,
            safe_base_name,
            self.model_config_equalities,
            baseline_has_check_sat=True,
            write_mode=ImpactCheckWriteMode.TEMP_WITH_DEBUG,
            verbose=self.verbose,
            info_fn=lambda msg: verbose_info(self.verbose, msg),
            cleanup_after=True,
        )

    def _write_compute_smt2_field_level_pair(self, config_pair: ConfigVariablePair) -> Optional[Path]:
        """Build and write compute SMT2 for field-level pair; return output path (permanent)."""
        device = get_device_for_config_var(config_pair.ip_var, self.devices)
        if not device:
            logger.warning(f"Could not determine device for config pair {config_pair.base_name}")
            return None
        complete_forward_file = self._impact_check_baseline_file(device)
        if not complete_forward_file.exists():
            logger.error(f"Complete forward file not found for device {device}: {complete_forward_file}")
            return None
        temp_file_path = self._comment_out_config_pair(str(complete_forward_file), config_pair, comment=True)
        with open(temp_file_path, 'r') as f:
            content = f.read()
        if "(check-sat)" in content:
            content = content.replace(
                "(check-sat)",
                "; (check-sat)\n(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))"
            )
        elif "(check-sat)" not in content:
            content = content.rstrip() + "\n; (check-sat)\n(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))\n"
        safe_base_name = config_pair.base_name.replace('/', '_').replace(':', '_').replace(' ', '_')
        out_file = self.field_level_intermediate_dir / f"compute_subspec_from_{device}_{safe_base_name}.smt2"
        with open(out_file, 'w') as f:
            f.write(content)
        logger.info(f"    Compute subspec file saved to: {out_file}")
        try:
            os.unlink(temp_file_path)
        except OSError:
            pass
        return out_file

    def _compute_subspec_field_level_pair(self, config_pair: ConfigVariablePair) -> Optional[str]:
        """Calculate subspec using synthesis file for a config pair."""
        logger.info(f"  Calculating synthesis subspec for config pair: {config_pair.base_name}")
        path = self._write_compute_smt2_field_level_pair(config_pair)
        return self._run_z3_simplify_and_parse(path, config_pair.base_name, lambda o: self._parse_config_pair_simplification_output(o, config_pair)) if path else None
    
    def _parse_config_pair_simplification_output(self, output: str, config_pair: ConfigVariablePair) -> Optional[str]:
        """Parse Z3 simplification output to extract subspec for a config pair"""
        logger.info(f"    Parsing simplification output for config pair: {config_pair.base_name}")
        
        # Use utility function to extract constraints from Z3 goal
        config_names = {config_pair.ip_var.name, config_pair.mask_var.name}
        subspec = extract_config_constraints_from_z3_goal(output, config_names)
        
        # Convert to list for easier manipulation
        if subspec:
            subspec_parts = subspec_string_to_list(subspec)
        else:
            subspec_parts = []
        
        config_vars_to_check = [config_pair.ip_var, config_pair.mask_var]
        self.model_config_equalities.append_missing_to_subspec(
            subspec_parts, config_vars_to_check, info=logger.info
        )
        
        if subspec_parts:
            subspec = " AND ".join(subspec_parts)
            logger.info(f"    Config pair subspec (including replaced variables): {subspec}")
            return subspec
        
        subspec_parts = [
            self.model_config_equalities.equality_for(config_pair.ip_var.name),
            self.model_config_equalities.equality_for(config_pair.mask_var.name),
        ]
        subspec = " AND ".join(subspec_parts)
        logger.info(f"    Config pair fallback model equalities: {subspec}")
        return subspec
    
    def calculate_line_level_subspecs(self) -> None:
        """Calculate line-level subspecs for all line groups"""
        logger.info("Calculating line-level subspecs...")
        
        line_groups_to_process = {
            device: groups
            for device, groups in self.line_level_groups.items()
            if self._should_run_impact_check_for_device(device)
        }
        skipped_devices = set(self.line_level_groups) - set(line_groups_to_process)
        if skipped_devices:
            logger.info(
                f"Skipping line-level subspecs for devices that passed AG testing: "
                f"{sorted(skipped_devices)}"
            )
            for device in sorted(skipped_devices):
                for line_group in self.line_level_groups[device]:
                    line_group_key = line_group.line_prefix
                    if line_group_key not in self.line_level_subspecs:
                        self.line_level_subspecs[line_group_key] = set()
                    self.line_level_subspecs[line_group_key].add("empty")
                    logger.info(
                        f"  Recorded empty subspec for {line_group_key} "
                        f"(device {device} passed assume-guarantee testing)"
                    )
        
        # Record line groups (same stats shape as 5_subspec_simplifier_original).
        all_line_prefixes: Set[str] = set()
        for device, line_groups in self.line_level_groups.items():
            for line_group in line_groups:
                all_line_prefixes.add(line_group.line_prefix)
        compute_line_prefixes: Set[str] = set()
        for device, line_groups in self.line_level_groups.items():
            for line_group in line_groups:
                compute_line_prefixes.add(line_group.line_prefix)
        rfl_total = sum(1 for p in all_line_prefixes if re.search(r'(Config_\S+_RouteFilterList_\S+)__Line(\d+)$', p))
        other_total = len(all_line_prefixes) - rfl_total
        rfl_compute = sum(1 for p in compute_line_prefixes if re.search(r'(Config_\S+_RouteFilterList_\S+)__Line(\d+)$', p))
        other_compute = len(compute_line_prefixes) - rfl_compute
        self.subspec_compute_summary["line"] = {
            "total": rfl_total + other_total,
            "compute": rfl_compute + other_compute,
            "skipped": (rfl_total + other_total) - (rfl_compute + other_compute),
            "rfl_total": rfl_total,
            "rfl_compute": rfl_compute,
            "other_total": other_total,
            "other_compute": other_compute,
        }
        
        # Process each device's line groups
        for device, line_groups in line_groups_to_process.items():
            logger.info(f"Processing line groups for device: {device}")
            
            for line_group in line_groups:
                # Use the exact line prefix as the line group key
                line_group_key = line_group.line_prefix
                safe_line_prefix = line_group.line_prefix.replace('/', '_').replace(':', '_').replace(' ', '_')
                logger.info(f"Processing line group: {line_group_key}")
                logger.info(f"  Contains {len(line_group.config_variables)} config variables")
                
                # Initialize set for collecting subspecs
                if line_group_key not in self.line_level_subspecs:
                    self.line_level_subspecs[line_group_key] = set()
                
                # Step 1: Check if line group has impact on synthesis forward baseline
                if self._check_subspec_line_level(line_group):
                    # Step 2: Calculate subspec using synthesis
                    subspec = self._compute_subspec_line_level(line_group)
                    if subspec:
                        # Save metadata for non-empty subspec (needed for normalization)
                        metadata_file = None
                        if self.subspec_baseline_files_dir and line_group.config_variables:
                            compute_subspec_file = self.line_level_intermediate_dir / f"compute_subspec_from_{line_group.device}_{safe_line_prefix}.smt2"
                            if compute_subspec_file.exists():
                                save_synthesis_metadata(line_group.device, line_group_key, str(compute_subspec_file), self.subspec_baseline_files_dir, "line")
                                metadata_file = find_metadata_file(line_group_key, line_group.device, "line", self.subspec_baseline_files_dir)
                            else:
                                logger.warning(f"Compute subspec file not found: {compute_subspec_file}")
                        
                        # Step 2.5: Normalize subspec immediately after calculation
                        normalized_subspec = subspec
                        if metadata_file:
                            try:
                                core, suffix = strip_subspec_suffixes(subspec)
                                normalized_subspec = normalize_subspec(
                                    core,
                                    metadata_file,
                                    line_group_key,
                                    is_field_level=False,
                                    is_pair=False,
                                    target_dst_ip=self.target_dst_ip,
                                    max_iterations=3,
                                    verbose=self.verbose,
                                    temp_dir=self.line_level_intermediate_dir
                                )
                                normalized_subspec = normalized_subspec + suffix
                                verbose_info(self.verbose, f"  Normalized subspec: {normalized_subspec}")
                            except Exception as e:
                                logger.warning(f"  Failed to normalize subspec for {line_group_key}: {e}")
                                # Continue with original subspec
                        else:
                            verbose_debug(self.verbose, f"  Metadata file not found for {line_group_key}, skipping normalization")
                        
                        self.line_level_subspecs[line_group_key].add(normalized_subspec)
                        self._record_device_repair_subspec(line_group.device, normalized_subspec)
                        logger.info(f"  Subspec: {normalized_subspec}")
                    else:
                        logger.info(f"  No subspec found (empty simplification output)")
                else:
                    # UNSAT: no impact, empty subspec
                    logger.info(f"  Empty subspec (no impact on synthesis forward baseline)")
                    self.line_level_subspecs[line_group_key].add("empty")
                
                # Log final subspecs for this line group
                if self.line_level_subspecs[line_group_key]:
                    logger.info(f"  Final subspecs for {line_group_key}: {list(self.line_level_subspecs[line_group_key])}")
                else:
                    logger.info(f"  No subspecs found for {line_group_key}")
                # Delete line-level intermediate files for this group when not -v
                self._delete_intermediate_files_for_target(
                    self.line_level_intermediate_dir, line_group.device, safe_line_prefix,
                )
        
    def _emit_subspec_compute_summary(self) -> None:
        """Emit a compact summary of how many subspecs were actually computed (printed once at end)."""
        if not self.subspec_compute_summary:
            return
        
        def _merge_field_and_pair_stats() -> Optional[Dict[str, int]]:
            """Merge field and pair statistics since pair subspecs are included in field-level subspecs"""
            field_stats = self.subspec_compute_summary.get("field")
            pair_stats = self.subspec_compute_summary.get("pair")
            
            if not field_stats:
                return pair_stats
            if not pair_stats:
                return field_stats
            
            # Merge statistics
            merged = {
                "total": field_stats["total"] + pair_stats["total"],
                "compute": field_stats["compute"] + pair_stats["compute"],
                "skipped": field_stats["skipped"] + pair_stats["skipped"],
                "rfl_total": field_stats["rfl_total"] + pair_stats["rfl_total"],
                "rfl_compute": field_stats["rfl_compute"] + pair_stats["rfl_compute"],
                "other_total": field_stats["other_total"] + pair_stats["other_total"],
                "other_compute": field_stats["other_compute"] + pair_stats["other_compute"],
            }
            return merged

        def _fmt_stats(stats: Dict[str, int], label: str) -> str:
            """Format statistics for output"""
            return (
                f"{label}: {stats['compute']}/{stats['total']} (skipped {stats['skipped']}) | "
                f"RouteFilterList {stats['rfl_compute']}/{stats['rfl_total']}, Other {stats['other_compute']}/{stats['other_total']}"
            )

        lines = ["Subspec computation summary (computed/total):"]
        
        # Field-level subspecs (including pair subspecs)
        if not self.line_level_only:
            merged_field_stats = _merge_field_and_pair_stats()
            if merged_field_stats:
                lines.append(f"  - {_fmt_stats(merged_field_stats, 'Field-level subspecs')}")
        
        # Line-level subspecs
        if not self.field_level_only:
            line_stats = self.subspec_compute_summary.get("line")
            if line_stats:
                lines.append(f"  - {_fmt_stats(line_stats, 'Line-level subspecs')}")

        # Ensure the summary is visible even when -v is not set (root logger at WARNING).
        # Use print() to ensure output regardless of logging level, similar to completion message
        for l in lines:
            print(l)
    
    
    def save_results(self) -> None:
        """Save calculated subspecs to file"""
        if self.field_level_only:
            logger.info("Saving field-level subspecs...")
        elif self.line_level_only:
            logger.info("Saving line-level subspecs...")
        else:
            logger.info("Saving field-level and line-level subspecs...")
        
        # Save field-level subspecs (including pair subspecs which are already merged; exclude mask vars)
        if not self.line_level_only:
            field_output_file = get_subspec_output_file_path(self.subspec_files_dir, "field", self.device_filter)
            mask_names = get_mask_variable_names_from_pairs(
                [(p.ip_var.name, p.mask_var.name) for p in self.config_variable_pairs]
            )
            save_field_level_subspecs(field_output_file, self.subspecs, exclude_config_names=mask_names)
            logger.info(f"Field-level results saved to: {field_output_file}")
        
        # Save line-level subspecs
        if not self.field_level_only:
            line_output_file = get_subspec_output_file_path(self.subspec_files_dir, "line", self.device_filter)
            save_line_level_subspecs(line_output_file, self.line_level_subspecs)
            logger.info(f"Line-level results saved to: {line_output_file}")
        
        # Note: Pair subspecs are now included in field_level_subspecs.txt
        # No need to save them to a separate file
        
        # Log intermediate files location
        logger.info(f"Field-level intermediate files saved to: {self.field_level_intermediate_dir}")
        logger.info("  - check_subspec_from_*.smt2: Files used for subspec impact checks")
        logger.info("  - compute_subspec_from_*.smt2: Files used for subspec computation")
        
        logger.info(f"Line-level intermediate files saved to: {self.line_level_intermediate_dir}")
        
        # Log final output files
        logger.info("")
        logger.info("=" * 60)
        logger.info("Final Output Files:")
        logger.info("=" * 60)
        if not self.line_level_only:
            if self.device_filter:
                field_output_file = self.subspec_files_dir / f"field_level_subspecs_{self.device_filter}.txt"
            else:
                field_output_file = self.subspec_files_dir / "field_level_subspecs.txt"
            logger.info(f"1. {field_output_file}")
            logger.info("   - Field-level subspecs: Simplified SMT constraints for individual config variables")
            logger.info("   - Each config variable has its own subspecs that represent the minimal constraints")
            logger.info("   - Format: Config Variable -> List of subspecs")
            logger.info("")
            logger.info("Note: Pair subspecs are now included in field_level_subspecs.txt")
        if not self.field_level_only:
            if self.device_filter:
                line_output_file = self.subspec_files_dir / f"line_level_subspecs_{self.device_filter}.txt"
            else:
                line_output_file = self.subspec_files_dir / "line_level_subspecs.txt"
            logger.info(f"{'1' if self.line_level_only else '2'}. {line_output_file}")
            logger.info("   - Line-level subspecs: Simplified SMT constraints for groups of config variables")
            logger.info("   - Config variables from the same configuration line are grouped together")
            logger.info("   - Format: Line Group -> List of subspecs")
            logger.info("")
        logger.info("=" * 60)
    
    def _localize_k_options_for_device(self, device: str) -> List[MaxSmtLocalizeResult]:
        """MaxSMT-enumerate up to REPAIR_OPTION_COUNT violated Config_* sets for one slice."""
        forward_path = self._impact_check_baseline_file(device)
        if not forward_path.exists():
            logger.error(f"Complete forward not found for device {device}: {forward_path}")
            return []

        soft_dir: Optional[Path] = None
        soft_base: Optional[str] = None
        if self.verbose:
            soft_dir = self.soft_intermediate_dir
            soft_base = f"soft_complete_forward_{device}"

        options = localize_k_violated_configs_from_forward(
            forward_path,
            k=REPAIR_OPTION_COUNT,
            soft_smt_output_dir=soft_dir,
            soft_smt_basename=soft_base,
        )
        if not options:
            return []

        first = options[0]
        logger.info(
            f"  MaxSMT localization on {device}: converted={first.converted_count}, "
            f"options={len(options)}, first_status={first.status}"
        )
        if first.status != "sat":
            logger.warning(
                f"  Slice {device}: MaxSMT did not return sat ({first.status}); no locations"
            )
            return []
        if not first.violated_names:
            logger.info(f"  Slice {device}: no soft constraints violated")
            return []

        # Keep only sat options that actually violated soft constraints.
        return [opt for opt in options if opt.status == "sat" and opt.violated_names]

    def _expand_option_locations(
        self, device: str, loc: MaxSmtLocalizeResult
    ) -> List[str]:
        """Expand ip/mask partners for one MaxSMT option's violated names."""
        forward_path = self._impact_check_baseline_file(device)
        available = list_config_equality_names(forward_path.read_text())
        expanded = expand_with_ip_mask_partners(loc.violated_names, available)
        if len(expanded) != len(loc.violated_names):
            logger.info(
                f"  Slice {device} option {loc.option_id}: expanded ip/mask partners -> "
                f"{len(expanded)} locations (was {len(loc.violated_names)})"
            )
        verbose_info(
            self.verbose,
            f"  Slice {device} option {loc.option_id}: "
            f"localized locations: {', '.join(expanded)}",
        )
        return expanded

    def _ensure_repair_option(self, option_id: int) -> LocalizedRepairOption:
        """Return (creating if needed) the LocalizedRepairOption for ``option_id``."""
        for opt in self.localized_repair_options:
            if opt.option_id == option_id:
                return opt
        created = LocalizedRepairOption(option_id=option_id)
        self.localized_repair_options.append(created)
        self.localized_repair_options.sort(key=lambda o: o.option_id)
        return created

    def _save_localized_locations_for_option(self, option: LocalizedRepairOption) -> Path:
        """Write per-host localized Config_* under repair_option_{id}/."""
        out_dir = self.work_dir / option.output_dir_name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "multiple_locations_localized.txt"
        with open(out_path, "w") as f:
            f.write(
                f"# Localized multi-location Config_* "
                f"(repair option {option.option_id}, per AG-fail slice)\n"
            )
            for host in sorted(option.locations_by_host.keys()):
                f.write(f"\n# slice {host}\n")
                for name in option.locations_by_host[host]:
                    f.write(f"{name}\n")
        logger.info(
            f"Localized multiple locations (option {option.option_id}) saved to: {out_path}"
        )
        print(f"localized locations saved (option {option.option_id}): {out_path}")
        return out_path

    def calculate_multi_location_subspecs(self) -> bool:
        """-m path: enumerate MaxSMT location sets, then joint subspec per repair option."""
        logger.info(
            "Calculating multi-location joint subspecs "
            f"(MaxSMT localize up to {REPAIR_OPTION_COUNT} options + joint)..."
        )
        devices = sorted(self._devices_needing_repair())
        if not devices:
            msg = "No AG-fail devices; skipping multi-location localization and joint subspec."
            logger.warning(msg)
            print(msg)
            return False

        self.localized_repair_options = []
        for device in devices:
            logger.info(f"Localizing multiple locations for AG-fail slice: {device}")
            loc_options = self._localize_k_options_for_device(device)
            for loc in loc_options:
                expanded = self._expand_option_locations(device, loc)
                if not expanded:
                    continue
                repair_opt = self._ensure_repair_option(loc.option_id)
                repair_opt.locations_by_host[device] = expanded
                repair_opt.model_store.update_from_assignments(
                    loc.model,
                    set(expanded),
                    info=logger.info if self.verbose else None,
                )

        if not self.localized_repair_options:
            msg = (
                "MaxSMT localization found no violated Config_* on any AG-fail slice; "
                "skipping joint subspec."
            )
            logger.warning(msg)
            print(msg)
            return False

        for option in self.localized_repair_options:
            self._save_localized_locations_for_option(option)

            intermediate_dir_name = option.intermediate_dir_name
            if self.verbose:
                (self.work_dir / intermediate_dir_name).mkdir(parents=True, exist_ok=True)

            logger.info(
                f"Computing joint subspec for repair option {option.option_id} "
                f"({len(option.locations_by_host)} slice(s))..."
            )
            joint_result = run_joint_for_localized_locations(
                self.work_dir,
                option.locations_by_host,
                verbose=self.verbose,
                intermediate_dir_name=intermediate_dir_name,
                output_dir_name=option.output_dir_name,
                model_store=option.model_store,
            )

            for slice_result in joint_result.per_slice:
                if any(is_nonempty_subspec(g.subspec) for g in slice_result.groups):
                    self.devices_with_repair_subspec.add(slice_result.host)

        return True

    def run(self) -> bool:
        """Run single-location (-s) or multi-location (-m) subspec calculation.

        Returns:
            True if subspec computation completed, False if skipped (e.g. AG baseline check passed).
        """
        if self.multi_location:
            logger.info("Starting multi-location (-m) subspec calculation...")
        else:
            logger.info("Starting single-location (-s) field/line subspec calculation...")
        
        try:
            # Step 1: Load device information
            self.load_device_info()

            # Step 2: Assume-guarantee baseline check
            if not self.check_baseline():
                return False

            if self.multi_location:
                return self.calculate_multi_location_subspecs()
            
            # --- Single-location (-s) path ---
            # Extract Config variables (from complete_forward files)
            self.extract_config_variables()
            self.extract_ip_mask_pairs()
            
            # Field-level and line-level are independent: can be calculated separately
            if not self.line_level_only:
                self.calculate_subspecs()  # field-level: single config vars + ip-mask pairs
            
            if not self.field_level_only:
                self.extract_line_level_config_groups()
                self.calculate_line_level_subspecs()
            
            self.save_results()

            # Print compute summary (repair summary is emitted from main() before "Completed").
            self._emit_subspec_compute_summary()
            
            if self.field_level_only:
                logger.info("Field-level subspec calculation completed successfully!")
            elif self.line_level_only:
                logger.info("Line-level subspec calculation completed successfully!")
            else:
                logger.info("Field-level and line-level subspec calculation completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Error in subspec calculation: {e}")
            raise


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print(
            "Usage: python 7_fix_subspec_simplifier_original.py [-s|-m] [-f] [-l] [-v] [-d] "
            "[--device DEVICE] <work_directory>"
        )
        print("Options:")
        print("  -s           Single-location mode: per config field / line subspec (default)")
        print("  -m           Multi-location mode: MaxSMT soft localize (up to "
              f"{REPAIR_OPTION_COUNT} options) + joint subspec on AG-fail slices")
        print("               (-s and -m are mutually exclusive)")
        print(f"               Outputs under 7_subspec_files/{REPAIR_OPTION_DIR_PREFIX}_*/")
        print("  -f           Only calculate field-level subspecs (-s only)")
        print("  -l           Only calculate line-level subspecs (-s only)")
        print("  -v           Verbose mode: Show detailed INFO logs and keep intermediate files")
        print("               Without -v: Only show WARNING/ERROR logs and completion status")
        print("  -d           Delete all intermediate output files before running")
        print("  --device     Process only the specified device (for parallel evaluation)")
        print("Example: python 7_fix_subspec_simplifier_original.py -s smt_output_network_1")
        print("         python 7_fix_subspec_simplifier_original.py -m smt_output_network_1")
        print("         python 7_fix_subspec_simplifier_original.py -s -f smt_output_network_1")
        print("         python 7_fix_subspec_simplifier_original.py -m -v smt_output_network_1")
        print("         python 7_fix_subspec_simplifier_original.py -d smt_output_network_1")
        print("         python 7_fix_subspec_simplifier_original.py --device r1 -s smt_output_network_1")
        sys.exit(1)
    
    # Parse command line arguments
    delete_intermediate = False
    field_level_only = False
    line_level_only = False
    verbose = False
    single_location = False
    multi_location = False
    device_filter = None
    work_dir = None
    
    # Parse flags
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '-d':
            delete_intermediate = True
        elif sys.argv[i] == '-s':
            single_location = True
        elif sys.argv[i] == '-m':
            multi_location = True
        elif sys.argv[i] == '-f':
            field_level_only = True
        elif sys.argv[i] == '-l':
            line_level_only = True
        elif sys.argv[i] == '-v':
            verbose = True
        elif sys.argv[i] == '--device':
            if i + 1 >= len(sys.argv):
                print("Error: --device requires a device name")
                sys.exit(1)
            device_filter = sys.argv[i + 1]
            i += 1
        elif sys.argv[i].startswith('-'):
            print(f"Error: Unknown option: {sys.argv[i]}")
            sys.exit(1)
        else:
            if work_dir is None:
                work_dir = sys.argv[i]
            else:
                print("Error: Multiple work directories specified")
                sys.exit(1)
        i += 1
    
    # -s / -m mutually exclusive; default to -s when neither is given
    if single_location and multi_location:
        print("Error: Cannot specify both -s and -m flags at the same time")
        sys.exit(1)
    if not single_location and not multi_location:
        single_location = True

    # Validate that both -f and -l are not specified at the same time
    if field_level_only and line_level_only:
        print("Error: Cannot specify both -f and -l flags at the same time")
        sys.exit(1)
    if multi_location and (field_level_only or line_level_only):
        print("Error: -m cannot be combined with -f or -l")
        sys.exit(1)
    
    if work_dir is None:
        print("Error: Work directory not specified")
        sys.exit(1)
    
    if not os.path.exists(work_dir):
        print(f"Error: Work directory does not exist: {work_dir}")
        sys.exit(1)
    
    # Delete intermediate files if requested
    if delete_intermediate:
        import shutil
        deleted_items = []
        
        work_path = Path(work_dir)
        
        dirs_to_delete = [
            "7_intermediate_subspec_field_files",  # Field/ip-mask pair: compute_subspec_from_*.smt2, check_subspec_from_*.smt2
            "7_intermediate_subspec_line_files",   # Line-level intermediate files
            "7_intermediate_subspec_metadata_files",
            SOFT_INTERMEDIATE_DIR,                 # Soft MaxSMT intermediates (-m)
            JOINT_INTERMEDIATE_DIR,               # Joint multi-location intermediates (-m)
            JOINT_OUTPUT_DIR,                     # Final outputs (field/line/joint)
        ]
        
        for dir_name in dirs_to_delete:
            dir_path = work_path / dir_name
            if dir_path.exists():
                logger.info(f"Deleting intermediate output directory: {dir_path}")
                shutil.rmtree(dir_path)
                deleted_items.append(str(dir_path))
        
        if deleted_items:
            logger.info(f"Deleted {len(deleted_items)} intermediate file(s)/directory(ies):")
            for item in deleted_items:
                logger.info(f"  - {item}")
            logger.info("Intermediate files and output files deleted.")
        else:
            logger.info("No intermediate files found to delete.")
        sys.exit(0)
    
    # Set logging level based on verbose flag
    if not verbose:
        # If not verbose, only show WARNING and above
        logging.getLogger().setLevel(logging.WARNING)
    
    # Serial execution (default behavior)
    calculator = SubspecSimplifier(
        work_dir,
        field_level_only=field_level_only,
        line_level_only=line_level_only,
        verbose=verbose,
        device_filter=device_filter,
        multi_location=multi_location,
    )
    if not calculator.run():
        sys.exit(0)

    if calculator.multi_location:
        n_options = len(calculator.localized_repair_options)
        n_hosts = len(
            {
                host
                for opt in calculator.localized_repair_options
                for host in opt.locations_by_host
            }
        )
        n_locs = sum(
            len(locs)
            for opt in calculator.localized_repair_options
            for locs in opt.locations_by_host.values()
        )
        print(
            f"multi-location: {n_options} repair option(s), "
            f"{n_hosts} AG-fail slice(s), {n_locs} localized Config location(s)"
        )
        calculator._emit_repair_summary()
        if not verbose:
            if device_filter:
                print(f"Device {device_filter}: ✓ Completed (multi-location)")
            else:
                print("All devices: ✓ Completed (multi-location)")
        return

    # Always print field-level and line-level summary (number of configs, number of empty subspecs)
    def _is_all_empty(s) -> bool:
        """A config is 'empty' if all its subspecs are empty (no non-empty subspec)."""
        return not s or s == {"empty"}

    mask_names = get_mask_variable_names_from_pairs(
        [(p.ip_var.name, p.mask_var.name) for p in calculator.config_variable_pairs]
    )
    if not calculator.line_level_only:
        field_subspecs = {k: v for k, v in calculator.subspecs.items() if k not in mask_names}
        n_field = len(field_subspecs)
        n_field_empty = sum(1 for v in field_subspecs.values() if _is_all_empty(v))
        print(f"field-level: {n_field} config field, {n_field_empty} empty subspec")
    if not calculator.field_level_only:
        n_line = len(calculator.line_level_subspecs)
        n_line_empty = sum(1 for v in calculator.line_level_subspecs.values() if _is_all_empty(v))
        print(f"line-level: {n_line} config line, {n_line_empty} empty subspec")

    calculator._emit_repair_summary()

    # If not verbose, print completion message
    if not verbose:
        if device_filter:
            print(f"Device {device_filter}: ✓ Completed")
        else:
            print("All devices: ✓ Completed")

if __name__ == "__main__":
    main()

