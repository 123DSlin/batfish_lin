#!/usr/bin/env python3
"""
Subspec Simplifier (Full Symbolic)

This script implements the field-level and line-level subspec calculation process
based on the global synthesis baseline file:
1. Extract Config variables from sliced_smt_encoding_synthesis.smt2
2. Check synthesis baseline is UNSAT; exit if SAT
3. Use synthesis baseline to check if a config location has impact
4. Use the same synthesis baseline to calculate subspecs for locations with impact
5. Normalize subspecs immediately after calculation
6. Use Z3 solver for simplification

Note: This version uses sliced_smt_encoding_synthesis.smt2 from 2_sliced_device_smt_encoding.
Per-device files sliced_{device}_smt_encoding.smt2 are never used.

Author: Network Verification Team
Version: 2.0 (Full Symbolic - Refactored)
"""

import re
import os
import sys
import logging
import subprocess
import tempfile
from typing import List, Dict, Set, Tuple, Optional, Callable
from pathlib import Path
from dataclasses import dataclass

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
    dict_has_nonempty_subspec,
    emit_global_repair_summary,
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

class GlobalSpecificationSubspecSimplifier:
    """Main class for calculating field-level and line-level subspecs"""
    
    def __init__(self, work_dir: str, field_level_only: bool = False, line_level_only: bool = False, verbose: bool = False, device_filter: Optional[str] = None):
        import shutil
        self.work_dir = Path(work_dir)
        self.verbose = verbose
        self.temp_dir_obj = None  # Reference to TemporaryDirectory object to prevent early cleanup
        self.device_filter = device_filter  # Optional device name filter for parallel processing
        
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
        
        # Synthesis baseline file (used for config extraction, impact check, and subspec compute)
        self.synthesis_baseline_file = (
            self.work_dir / "2_sliced_device_smt_encoding" / "sliced_smt_encoding_synthesis.smt2"
        )
        
        # Level selection flags
        self.field_level_only = field_level_only
        self.line_level_only = line_level_only
        
        # Validate that both flags are not set at the same time
        if self.field_level_only and self.line_level_only:
            raise ValueError("Cannot specify both -f and -l flags at the same time")
        
        # Validate required input files/directories
        self._validate_input_files()
        
        # Load target_dst_ip for normalization
        self.target_dst_ip = load_target_dst_ip(self.work_dir)

        # Initialize output directories (final outputs always go under work_dir;
        # intermediate dirs go under work_dir in verbose mode, otherwise a temp dir).
        self._init_output_dirs()

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
        self.subspec_files_dir = self.work_dir / "8_subspec_files"
        self.subspec_files_dir.mkdir(exist_ok=True, parents=True)

        # Intermediate files.
        self.subspec_baseline_files_dir = base_dir / "8_intermediate_subspec_metadata_files"
        self.subspec_baseline_files_dir.mkdir(exist_ok=True, parents=True)

        self.field_level_intermediate_dir = base_dir / "8_intermediate_subspec_field_files"
        self.field_level_intermediate_dir.mkdir(exist_ok=True, parents=True)

        self.line_level_intermediate_dir = base_dir / "8_intermediate_subspec_line_files"
        self.line_level_intermediate_dir.mkdir(exist_ok=True, parents=True)
    
    def _validate_input_files(self) -> None:
        """Validate that all required input files and directories exist"""
        missing_items = []
        
        if not self.synthesis_baseline_file.exists():
            missing_items.append("2_sliced_device_smt_encoding/sliced_smt_encoding_synthesis.smt2")
        
        if missing_items:
            logger.error(f"Missing required input files/directories: {', '.join(missing_items)}")
            logger.error(f"Work directory: {self.work_dir}")
            sys.exit(1)
        
        logger.info("All required input files/directories found")

    def _write_synthesis_baseline_sat_check_smt2(self) -> Path:
        """Write synthesis baseline with (check-sat) for the pre-impact baseline check."""
        with open(self.synthesis_baseline_file, 'r') as f:
            content = f.read()
        if "(check-sat)" not in content:
            content = content.rstrip() + "\n(check-sat)\n"
        output_file = self.field_level_intermediate_dir / "check_synthesis_baseline.smt2"
        with open(output_file, 'w') as f:
            f.write(content)
        verbose_info(self.verbose, f"Synthesis baseline check file saved to: {output_file}")
        return output_file

    def _emit_repair_summary(self) -> None:
        """Global synthesis: any one non-empty field or line subspec means repair is possible."""
        has_subspec = False
        if not self.line_level_only and dict_has_nonempty_subspec(self.subspecs):
            has_subspec = True
        if not self.field_level_only and dict_has_nonempty_subspec(self.line_level_subspecs):
            has_subspec = True
        emit_global_repair_summary(has_subspec)

    def check_baseline(self) -> bool:
        """Return True if synthesis baseline is UNSAT (proceed), False if SAT (stop)."""
        logger.info("Checking synthesis baseline SAT/UNSAT before impact check...")
        smt2_path = self._write_synthesis_baseline_sat_check_smt2()
        try:
            result = subprocess.run(['z3', str(smt2_path)], capture_output=True, text=True)
            is_sat, status = parse_z3_output(result)
            if is_sat:
                msg = (
                    "Synthesis baseline (sliced_smt_encoding_synthesis.smt2) is SAT: "
                    "the property holds under the current configuration. "
                    "Skipping impact check and subspec computation."
                )
                logger.warning(msg)
                print(msg)
                return False
            logger.info("Synthesis baseline is UNSAT; proceeding with impact check and subspec computation.")
            return True
        except Exception as e:
            logger.error(f"Error checking synthesis baseline: {e}")
            print(f"Error checking synthesis baseline: {e}")
            return False

    def load_device_info(self) -> None:
        """Load device information from 0_hostnames.txt for full symbolic mode"""
        # Load devices from 0_hostnames.txt using utility function
        devices = load_hostnames(self.work_dir)
        
        # Validate device_filter if specified
        if self.device_filter:
            if self.device_filter not in devices:
                error_msg = f"Device '{self.device_filter}' not found in 0_hostnames.txt\n"
                error_msg += f"Available devices: {', '.join(devices)}"
                raise ValueError(error_msg)
            devices = [self.device_filter]
            logger.info(f"Filtered to device: {devices[0]}")
        
        self.devices = devices
    
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
        """Extract line-level config groups from already-extracted config variables.
        
        Groups Config variables by device and line prefix (__Linei or __Linei__linej)
        so that variables from the same configuration line are in one group.
        """
        logger.info("Extracting line-level config groups...")
        
        self.line_level_groups = {}
        
        # Build line-level groups from self.config_variables (already loaded from synthesis baseline)
        if not self.config_variables:
            logger.warning("No config variables available; run extract_config_variables first.")
            total_groups = sum(len(groups) for groups in self.line_level_groups.values())
            logger.info(f"Total line-level config groups found: {total_groups}")
            return
        
        logger.info("Building line-level config groups from extracted config variables")
        
        # Dict[device, Dict[line_prefix, List[ConfigVariable]]]
        device_line_configs = {}
        
        for config_var in self.config_variables:
            line_prefix = self._get_line_prefix_from_config_name(config_var.name)
            if not line_prefix:
                continue
            device = get_device_for_config_var(config_var, self.devices)
            if not device:
                continue
            if self.device_filter and device != self.device_filter:
                continue
            
            if device not in device_line_configs:
                device_line_configs[device] = {}
            if line_prefix not in device_line_configs[device]:
                device_line_configs[device][line_prefix] = []
            device_line_configs[device][line_prefix].append(config_var)
        
        # Group configs by device and LineX, then create LineLevelConfigGroup objects
        for device, line_configs in device_line_configs.items():
            logger.info(f"Processing line-level config groups for device: {device}")
            device_groups = []
            
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
    
    def extract_config_variables(self) -> None:
        """Extract Config variables from synthesis baseline file (sliced_smt_encoding_synthesis.smt2).

        Reads (assert (= Config_... value)) from the synthesis baseline.
        When --device is specified, extracts Config variables with Config_{device}_ prefix.
        """
        logger.info("Extracting Config variables from sliced_smt_encoding_synthesis.smt2...")
        
        self.config_variables = []
        self.config_vars_by_name = {}  # Dict[str, List[ConfigVariable]] - config name -> list of variables
        self.config_vars_by_device = {}  # Dict[str, List[ConfigVariable]] - device -> list of variables
        
        if not self.synthesis_baseline_file.exists():
            logger.error(f"Synthesis baseline file not found: {self.synthesis_baseline_file}")
            return
        
        with open(self.synthesis_baseline_file, 'r') as f:
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
                    
                    # Extract device name from config name (e.g., Config_r1_... -> r1)
                    device = get_device_for_config_var(
                        ConfigVariable(name=config_name, value=config_value, line_number=line_num, file_path=""),
                        self.devices
                    )
                    
                    # If device_filter is specified, only include Config variables with Config_{device}_ prefix
                    if self.device_filter:
                        if not device or device != self.device_filter:
                            continue
                    
                    config_var = ConfigVariable(
                        name=config_name,
                        value=config_value,
                        line_number=line_num,
                        file_path=str(self.synthesis_baseline_file)
                    )
                    self.config_variables.append(config_var)
                    
                    # Group by config name
                    if config_name not in self.config_vars_by_name:
                        self.config_vars_by_name[config_name] = []
                    self.config_vars_by_name[config_name].append(config_var)
                    
                    # Group by device
                    if device:
                        if device not in self.config_vars_by_device:
                            self.config_vars_by_device[device] = []
                        self.config_vars_by_device[device].append(config_var)
                    
                    logger.info(f"    Found {'commented' if is_commented else 'active'} Config variable: {config_name} = {config_value}")
        
        # Log summary
        logger.info(f"Total Config variable instances found: {len(self.config_variables)}")
        logger.info(f"Unique Config variables found: {len(self.config_vars_by_name)}")
        for config_name, vars_list in self.config_vars_by_name.items():
            devices = [get_device_for_config_var(var, self.devices) for var in vars_list]
            # Filter out None values before sorting
            devices_filtered = [d for d in devices if d is not None]
            if devices_filtered:
                logger.info(f"  {config_name}: found in {len(vars_list)} file(s): {sorted(set(devices_filtered))}")
            else:
                logger.warning(f"  {config_name}: found in {len(vars_list)} file(s), but could not determine device names")
    
    def calculate_subspecs(self) -> None:
        """Calculate field-level subspecs for all unique Config variables"""
        logger.info("Calculating field-level subspecs...")
        
        # Get all ip/mask variable names that should be skipped in individual processing
        ip_mask_variable_names = set()
        for config_pair in self.config_variable_pairs:
            ip_mask_variable_names.add(config_pair.ip_var.name)
            ip_mask_variable_names.add(config_pair.mask_var.name)
        
        # Process each unique Config variable
        for config_name, config_vars_list in self.config_vars_by_name.items():
            # Skip ip/mask variables that are part of pairs - they will be processed separately
            if config_name in ip_mask_variable_names:
                logger.info(f"Skipping {config_name} - will be processed as part of ip/mask pair")
                continue
                
            logger.info(f"Processing Config variable: {config_name}")
            logger.info(f"  Found in {len(config_vars_list)} sliced files")
            
            # Initialize set for collecting subspecs
            if config_name not in self.subspecs:
                self.subspecs[config_name] = set()
            
            # Process each occurrence of this Config variable
            for config_var in config_vars_list:
                # Determine the device for this Config variable
                device = get_device_for_config_var(config_var, self.devices)
                if not device:
                    logger.warning(f"Could not determine device for Config variable {config_var.name}")
                    continue
                
                logger.info(f"  Processing for device: {device}")
                
                # Step 1: Check if variable has impact on synthesis baseline
                if self._check_subspec_field_level(config_var, device):
                    # Step 2: Calculate subspec using synthesis
                    subspec = self._compute_subspec_field_level(config_var, device)
                    if not subspec:
                        logger.info(f"  No subspec found (empty simplification output)")
                        continue
                    
                    # Step 3: Prepare metadata file for normalization
                    metadata_file = self._prepare_metadata_file(config_var, device)
                    
                    # Step 4: Normalize subspec immediately after calculation
                    normalized_subspec = self._normalize_subspec_with_metadata(subspec, config_var, metadata_file)
                    logger.info(f"  Subspec: {normalized_subspec}")
                    self.subspecs[config_name].add(normalized_subspec)
                else:
                    # UNSAT: no impact, empty subspec
                    logger.info(f"  Empty subspec (no impact on synthesis baseline)")
                    self.subspecs[config_name].add("empty")
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
        """Check if Config variable has impact on synthesis baseline. Returns True if SAT, False if UNSAT."""
        logger.info(f"  Checking synthesis impact for {config_var.name}")
        safe_config_name = config_var.name.replace('/', '_').replace(':', '_').replace(' ', '_')
        return check_impact_reverse(
            self.synthesis_baseline_file,
            [config_var],
            self.field_level_intermediate_dir,
            device,
            safe_config_name,
            self.model_config_equalities,
            baseline_has_check_sat=False,
            write_mode=ImpactCheckWriteMode.PERSISTENT,
            verbose=self.verbose,
            info_fn=lambda msg: verbose_info(self.verbose, msg),
        )

    def _write_compute_smt2_field_level(self, config_var: ConfigVariable, device: str) -> Optional[Path]:
        """Build and write compute SMT2 for field-level; return output path or None."""
        if not self.synthesis_baseline_file.exists():
            logger.error(f"Synthesis baseline file not found: {self.synthesis_baseline_file}")
            return None
        with open(self.synthesis_baseline_file, 'r') as f:
            lines = f.readlines()
        modified_lines, config_line_found = self._comment_config_var_equality_and_add_bounds(lines, config_var)
        if not config_line_found:
            logger.warning(f"Config variable {config_var.name} not found in synthesis file")
            return None
        content_str = ''.join(modified_lines)
        if "(apply (then simplify" not in content_str and "apply (then simplify" not in content_str:
            modified_lines = [line for line in modified_lines if "(check-sat)" not in line.strip() and line.strip() != "(check-sat)"]
            while modified_lines and not modified_lines[-1].strip():
                modified_lines.pop()
            modified_lines.append("; (check-sat)\n")
            modified_lines.append("(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))\n")
        safe_config_name = config_var.name.replace('/', '_').replace(':', '_').replace(' ', '_')
        output_file = self.field_level_intermediate_dir / f"compute_subspec_from_{device}_{safe_config_name}.smt2"
        with open(output_file, 'w') as f:
            f.writelines(modified_lines)
        logger.info(f"    Compute subspec file saved to: {output_file}")
        return output_file

    def _compute_subspec_field_level(self, config_var: ConfigVariable, device: str) -> Optional[str]:
        """Calculate subspec using synthesis baseline file."""
        logger.info(f"  Calculating synthesis subspec for {config_var.name}")
        path = self._write_compute_smt2_field_level(config_var, device)
        return self._run_z3_simplify_and_parse(path, config_var.name, lambda o: self._parse_simplification_output(o, config_var)) if path else None
    
    def _parse_simplification_output(self, output: str, config_var: ConfigVariable) -> Optional[str]:
        """Parse Z3 simplification output to extract subspec using utils method"""
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
            
            should_modify = False
            matching_config_var = None
            for config_var in line_group.config_variables:
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
        
        if comment and commented_var_names and first_commented_index is not None:
            bounds_to_add = get_bounds_for_multiple_config_variables(commented_var_names)
            if bounds_to_add:
                insert_pos = first_commented_index + 1
                bounds_lines = [f"{b}\n" for b in bounds_to_add]
                modified_lines = modified_lines[:insert_pos] + bounds_lines + modified_lines[insert_pos:]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.smt2', delete=False) as temp_file:
            temp_file.writelines(modified_lines)
            return temp_file.name
    
    def _check_subspec_line_level(self, line_group: LineLevelConfigGroup) -> bool:
        """Check if line group has impact on synthesis baseline. Returns True if SAT, False if UNSAT."""
        logger.info(f"  Checking synthesis impact for line group: {line_group.device} - {line_group.line_id}")
        safe_line_prefix = line_group.line_prefix.replace('/', '_').replace(':', '_').replace(' ', '_')
        return check_impact_reverse(
            self.synthesis_baseline_file,
            line_group.config_variables,
            self.line_level_intermediate_dir,
            line_group.device,
            safe_line_prefix,
            self.model_config_equalities,
            baseline_has_check_sat=False,
            write_mode=ImpactCheckWriteMode.TEMP_WITH_DEBUG,
            verbose=self.verbose,
            info_fn=lambda msg: verbose_info(self.verbose, msg),
            cleanup_after=True,
        )

    def _write_compute_smt2_line_level(self, line_group: LineLevelConfigGroup) -> Optional[Path]:
        """Build and write one compute SMT2 file per line group (named up to __LineX only). Return path for Z3."""
        if not self.synthesis_baseline_file.exists():
            logger.error(f"Synthesis baseline file not found: {self.synthesis_baseline_file}")
            return None
        temp_file_path = self._comment_out_line_group(str(self.synthesis_baseline_file), line_group, comment=True)
        with open(temp_file_path, 'r') as f:
            temp_content = f.read()
        if "(apply (then simplify" not in temp_content and "apply (then simplify" not in temp_content:
            lines = temp_content.split('\n')
            lines = [line for line in lines if "(check-sat)" not in line.strip()]
            temp_content = '\n'.join(lines).rstrip() + "\n; (check-sat)\n(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))\n"
            with open(temp_file_path, 'w') as f:
                f.write(temp_content)
        import shutil
        safe_line_prefix = line_group.line_prefix.replace('/', '_').replace(':', '_').replace(' ', '_')
        out_file = self.line_level_intermediate_dir / f"compute_subspec_from_{line_group.device}_{safe_line_prefix}.smt2"
        shutil.copy2(temp_file_path, out_file)
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
        
        config_names = {config_var.name for config_var in line_group.config_variables}
        subspec = extract_config_constraints_from_z3_goal(output, config_names)
        
        if subspec:
            subspec_parts = subspec_string_to_list(subspec)
        else:
            subspec_parts = []
        
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
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.smt2', delete=False) as temp_file:
            temp_file.writelines(modified_lines)
            return temp_file.name
    
    def _check_subspec_field_level_pair(self, config_pair: ConfigVariablePair) -> bool:
        """Check if config pair has impact on synthesis baseline. Returns True if SAT, False if UNSAT."""
        logger.info(f"  Checking synthesis impact for config pair: {config_pair.base_name}")
        device = get_device_for_config_var(config_pair.ip_var, self.devices)
        if not device:
            logger.warning(f"Could not determine device for config pair {config_pair.base_name}")
            return False
        safe_base_name = config_pair.base_name.replace('/', '_').replace(':', '_').replace(' ', '_')
        return check_impact_reverse(
            self.synthesis_baseline_file,
            [config_pair.ip_var, config_pair.mask_var],
            self.field_level_intermediate_dir,
            device,
            safe_base_name,
            self.model_config_equalities,
            baseline_has_check_sat=False,
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
        if not self.synthesis_baseline_file.exists():
            logger.error(f"Synthesis baseline file not found: {self.synthesis_baseline_file}")
            return None
        temp_file_path = self._comment_out_config_pair(str(self.synthesis_baseline_file), config_pair, comment=True)
        with open(temp_file_path, 'r') as f:
            temp_content = f.read()
        if "(apply (then simplify" not in temp_content and "apply (then simplify" not in temp_content:
            lines = temp_content.split('\n')
            lines = [line for line in lines if "(check-sat)" not in line.strip()]
            temp_content = '\n'.join(lines).rstrip() + "\n; (check-sat)\n(apply (then simplify propagate-values solve-eqs ctx-solver-simplify))\n"
            with open(temp_file_path, 'w') as f:
                f.write(temp_content)
        safe_base_name = config_pair.base_name.replace('/', '_').replace(':', '_').replace(' ', '_')
        out_file = self.field_level_intermediate_dir / f"compute_subspec_from_{device}_{safe_base_name}.smt2"
        import shutil
        shutil.copy2(temp_file_path, out_file)
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
        
        config_names = {config_pair.ip_var.name, config_pair.mask_var.name}
        subspec = extract_config_constraints_from_z3_goal(output, config_names)
        
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
    
    def calculate_config_pair_subspecs(self) -> None:
        """Calculate field-level subspecs for all ip/mask pairs"""
        logger.info("Calculating field-level subspecs for ip/mask pairs...")
        
        # Process each ip/mask pair
        for config_pair in self.config_variable_pairs:
            logger.info(f"Processing config pair: {config_pair.base_name}")
            logger.info(f"  IP variable: {config_pair.ip_var.name}")
            logger.info(f"  Mask variable: {config_pair.mask_var.name}")
            
            # Initialize set for collecting subspecs
            if config_pair.base_name not in self.pair_subspecs:
                self.pair_subspecs[config_pair.base_name] = set()
            
            # Step 1: Check if config pair has impact on synthesis baseline
            if self._check_subspec_field_level_pair(config_pair):
                # Step 2: Calculate subspec using synthesis
                subspec = self._compute_subspec_field_level_pair(config_pair)
                if not subspec:
                    logger.info(f"  No subspec found (empty simplification output)")
                else:
                    # Step 3: Prepare metadata file for normalization
                    device = get_device_for_config_var(config_pair.ip_var, self.devices)
                    metadata_file = None
                    if device:
                        safe_base_name = config_pair.base_name.replace('/', '_').replace(':', '_').replace(' ', '_')
                        compute_subspec_file = self.field_level_intermediate_dir / f"compute_subspec_from_{device}_{safe_base_name}.smt2"
                        if compute_subspec_file.exists() and self.subspec_baseline_files_dir:
                            # Save metadata file for normalization
                            save_synthesis_metadata(device, config_pair.base_name, str(compute_subspec_file), self.subspec_baseline_files_dir, "pair")
                            # Find the metadata file we just created
                            metadata_file = find_metadata_file(config_pair.base_name, device, "pair", self.subspec_baseline_files_dir)
                        elif not compute_subspec_file.exists():
                            logger.warning(f"Compute subspec file not found: {compute_subspec_file}")
                    
                    # Step 4: Normalize subspec immediately after calculation
                    normalized_subspec = subspec
                    if metadata_file:
                        try:
                            core, suffix = strip_subspec_suffixes(subspec)
                            normalized_subspec = normalize_subspec(
                                core,
                                metadata_file,
                                config_pair.base_name,
                                is_field_level=True,
                                is_pair=True,
                                target_dst_ip=self.target_dst_ip,
                                max_iterations=3,
                                verbose=self.verbose,
                                temp_dir=self.field_level_intermediate_dir
                            )
                            normalized_subspec = normalized_subspec + suffix
                            verbose_info(self.verbose, f"  Normalized subspec: {normalized_subspec}")
                        except Exception as e:
                            logger.warning(f"  Failed to normalize subspec for {config_pair.base_name}: {e}")
                    else:
                        verbose_debug(self.verbose, f"  Metadata file not found for {config_pair.base_name}, skipping normalization")
                    
                    # Store normalized subspec
                    self.pair_subspecs[config_pair.base_name].add(normalized_subspec)
                    logger.info(f"  Subspec: {normalized_subspec}")
            else:
                # UNSAT: no impact, empty subspec
                logger.info(f"  Empty subspec (no impact on synthesis baseline)")
                self.pair_subspecs[config_pair.base_name].add("empty")
            
            
            # Add the ip/mask pair subspecs to the IP variable's field-level subspecs
            ip_var_name = config_pair.ip_var.name
            if ip_var_name not in self.subspecs:
                self.subspecs[ip_var_name] = set()
            self.subspecs[ip_var_name].update(self.pair_subspecs[config_pair.base_name])
            
            # Log final subspecs for this config pair
            if self.pair_subspecs[config_pair.base_name]:
                logger.info(f"  Final subspecs for {config_pair.base_name}: {list(self.pair_subspecs[config_pair.base_name])}")
                logger.info(f"  Added to IP variable {ip_var_name} field-level subspecs")
            else:
                logger.info(f"  No subspecs found for {config_pair.base_name}")
            # Delete ip-mask pair intermediate files and pair metadata when not -v
            device = get_device_for_config_var(config_pair.ip_var, self.devices)
            if device:
                safe_base_name = config_pair.base_name.replace('/', '_').replace(':', '_').replace(' ', '_')
                self._delete_intermediate_files_for_target(self.field_level_intermediate_dir, device, safe_base_name)
                self._delete_metadata_file_for_target("pair", device, safe_base_name)
    
    
    def calculate_line_level_subspecs(self) -> None:
        """Calculate line-level subspecs for all line groups"""
        logger.info("Calculating line-level subspecs...")
        
        # Process each device's line groups
        for device, line_groups in self.line_level_groups.items():
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
                
                # Step 1: Check if line group has impact on synthesis baseline
                if self._check_subspec_line_level(line_group):
                    # Step 2: Calculate subspec using synthesis
                    subspec = self._compute_subspec_line_level(line_group)
                    if not subspec:
                        logger.info(f"  No subspec found (empty simplification output)")
                    else:
                        # Step 3: Prepare metadata file for normalization (named by line prefix up to __LineX only)
                        metadata_file = None
                        if self.subspec_baseline_files_dir and line_group.config_variables:
                            compute_subspec_file = self.line_level_intermediate_dir / f"compute_subspec_from_{line_group.device}_{safe_line_prefix}.smt2"
                            if compute_subspec_file.exists():
                                # Save line-level metadata for normalization
                                save_synthesis_metadata(line_group.device, line_group_key, str(compute_subspec_file), self.subspec_baseline_files_dir, "line")
                                # Find the metadata file we just created
                                metadata_file = find_metadata_file(line_group_key, line_group.device, "line", self.subspec_baseline_files_dir)
                            else:
                                logger.warning(f"Compute subspec file not found: {compute_subspec_file}")
                        
                        # Step 4: Normalize subspec immediately after calculation
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
                        else:
                            verbose_debug(self.verbose, f"  Metadata file not found for {line_group_key}, skipping normalization")
                        
                        self.line_level_subspecs[line_group_key].add(normalized_subspec)
                        logger.info(f"  Subspec: {normalized_subspec}")
                else:
                    # UNSAT: no impact, empty subspec
                    logger.info(f"  Empty subspec (no impact on synthesis baseline)")
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
        
    def save_results(self) -> None:
        """Save calculated subspecs to file using utils methods"""
        if self.field_level_only:
            logger.info("Saving field-level subspecs...")
        elif self.line_level_only:
            logger.info("Saving line-level subspecs...")
        else:
            logger.info("Saving field-level and line-level subspecs...")
        
        # Save field-level subspecs (including pair subspecs which are already merged; exclude mask vars)
        if not self.line_level_only:
            # Determine output file name based on device_filter
            if self.device_filter:
                field_filename = f"field_level_subspecs_{self.device_filter}.txt"
            else:
                field_filename = "field_level_subspecs.txt"
            field_output_file = self.subspec_files_dir / field_filename
            mask_names = get_mask_variable_names_from_pairs(
                [(p.ip_var.name, p.mask_var.name) for p in self.config_variable_pairs]
            )
            # Use utils method but customize header for full symbolic mode
            with open(field_output_file, 'w') as f:
                f.write("Field-Level Subspecs (Full Symbolic)\n")
                f.write("====================\n\n")
                
                if not self.subspecs:
                    f.write("No field-level subspecs found.\n")
                else:
                    # Sort by config_name to ensure consistent ordering; skip mask vars
                    for config_name in sorted(self.subspecs.keys()):
                        if config_name in mask_names:
                            continue
                        subspecs_set = self.subspecs[config_name]
                        f.write(f"Config Variable: {config_name}\n")
                        if subspecs_set:
                            f.write(f"Subspecs ({len(subspecs_set)}):\n")
                            for i, subspec in enumerate(sorted(subspecs_set), 1):
                                    f.write(f"  {i}. {subspec}\n")
                        else:
                            f.write("No subspecs found.\n")
                        f.write("-" * 50 + "\n\n")
            
            logger.info(f"Field-level results saved to: {field_output_file}")
        
        # Save line-level subspecs
        if not self.field_level_only:
            # Determine output file name based on device_filter
            if self.device_filter:
                line_filename = f"line_level_subspecs_{self.device_filter}.txt"
            else:
                line_filename = "line_level_subspecs.txt"
            line_output_file = self.subspec_files_dir / line_filename
            
            # Use utils method but customize header for full symbolic mode
            with open(line_output_file, 'w') as f:
                f.write("Line-Level Subspecs (Full Symbolic)\n")
                f.write("===================\n\n")
                
                if not self.line_level_subspecs:
                    f.write("No line-level subspecs found.\n")
                else:
                    # Sort by line_group_key to ensure consistent ordering
                    for line_group_key in sorted(self.line_level_subspecs.keys()):
                        subspecs_set = self.line_level_subspecs[line_group_key]
                        f.write(f"Line Group: {line_group_key}\n")
                        if subspecs_set:
                            f.write(f"Subspecs ({len(subspecs_set)}):\n")
                            for i, subspec in enumerate(sorted(subspecs_set), 1):
                                    f.write(f"  {i}. {subspec}\n")
                        else:
                            f.write("No subspecs found.\n")
                        f.write("-" * 50 + "\n\n")
            
            logger.info(f"Line-level results saved to: {line_output_file}")
        
        # Note: Pair subspecs are now included in field_level_subspecs.txt
        # No need to save them to a separate file
        
        # Log baseline files location
        logger.info(f"Using baseline file: {self.synthesis_baseline_file}")
        
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
    
    def run(self) -> bool:
        """Run the complete field-level and line-level subspec calculation process.

        Returns:
            True if subspec computation completed, False if skipped (e.g. synthesis baseline SAT).
        """
        logger.info("Starting field-level and line-level subspec calculation...")
        
        try:
            # Step 1: Load device information
            self.load_device_info()
            
            # Step 2: Extract Config variables
            self.extract_config_variables()
            
            # Step 3: Extract ip/mask pairs
            self.extract_ip_mask_pairs()

            # Step 4: Synthesis baseline must be UNSAT before impact check
            if not self.check_baseline():
                return False
            
            # Step 5: Calculate field-level subspecs (if not line-level only)
            if not self.line_level_only:
                self.calculate_subspecs()
                
                # Step 6: Calculate config pair subspecs
                self.calculate_config_pair_subspecs()
            
            # Step 7: Extract line-level config groups (if not field-level only)
            if not self.field_level_only:
                self.extract_line_level_config_groups()
                
                # Step 8: Calculate line-level subspecs
                self.calculate_line_level_subspecs()
            
            # Step 9: Save results
            self.save_results()
            
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
        print("Usage: python 8_fix_subspec_simplifier_fullsym.py [-f] [-l] [-v] [-d] [--device DEVICE] <work_directory>")
        print("Options:")
        print("  -f           Only calculate field-level subspecs")
        print("  -l           Only calculate line-level subspecs")
        print("  -v           Verbose mode: Show detailed INFO logs and keep intermediate files (8_*_intermediate_files, 8_subspec_metadata_files)")
        print("               Without -v: Only show WARNING/ERROR logs and completion status")
        print("  -d           Delete all intermediate output files before running")
        print("  --device     Process only the specified device (for parallel evaluation)")
        print("Example: python 8_fix_subspec_simplifier_fullsym.py smt_output_network_1")
        print("         python 8_fix_subspec_simplifier_fullsym.py -f smt_output_network_1")
        print("         python 8_fix_subspec_simplifier_fullsym.py -l smt_output_network_1")
        print("         python 8_fix_subspec_simplifier_fullsym.py -v smt_output_network_1")
        print("         python 8_fix_subspec_simplifier_fullsym.py -d smt_output_network_1")
        print("         python 8_fix_subspec_simplifier_fullsym.py --device r1 smt_output_network_1")
        sys.exit(1)
    
    # Parse command line arguments
    delete_intermediate = False
    field_level_only = False
    line_level_only = False
    verbose = False
    device_filter = None
    work_dir = None
    
    # Parse flags
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '-d':
            delete_intermediate = True
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
    
    # Validate that both -f and -l are not specified at the same time
    if field_level_only and line_level_only:
        print("Error: Cannot specify both -f and -l flags at the same time")
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
        from pathlib import Path
        deleted_items = []
        
        work_path = Path(work_dir)
        
        dirs_to_delete = [
            "8_intermediate_subspec_field_files",  # Field/ip-mask pair: compute_subspec_from_*.smt2, check_subspec_from_*.smt2
            "8_intermediate_subspec_line_files",   # Line-level intermediate files
            "8_intermediate_subspec_metadata_files",
            "8_subspec_files"  # Contains final output files (field_level_subspecs*.txt, line_level_subspecs*.txt)
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
    
    calculator = GlobalSpecificationSubspecSimplifier(work_dir,
                                   field_level_only=field_level_only, line_level_only=line_level_only,
                                   verbose=verbose, device_filter=device_filter)
    if not calculator.run():
        sys.exit(0)

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

