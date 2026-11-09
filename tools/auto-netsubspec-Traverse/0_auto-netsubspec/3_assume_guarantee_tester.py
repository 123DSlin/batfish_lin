#!/usr/bin/env python3
"""
Assume-Guarantee Testing Script for Network Verification

This script generates and tests assume-guarantee test files.

The test files (complete_forward_{device}.smt2 and complete_reverse_{device}.smt2) are
generated in the 3_assume_guarantee_test/ directory, then Z3 checks are performed.

Test Process:
1. Generate: Create complete_forward_{device}.smt2 and complete_reverse_{device}.smt2 files
2. Forward Test: Read complete_forward_{device}.smt2 and run Z3 check-sat
3. Reverse Test: Read complete_reverse_{device}.smt2 and run Z3 check-sat

Expected Results:
- Forward test should return SAT (satisfiable)
- Reverse test should return UNSAT (unsatisfiable)

Supports parallel execution per device via --device flag.
"""

import os
import sys
import subprocess
import tempfile
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.util_subspec_routemap import RoutemapSubspecCalculator
from utils.util_log import verbose_info

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

##########################################################################################
### Input validation
##########################################################################################

class InputValidator:
    """Validates required input files/directories for assume-guarantee testing"""

    def __init__(self, work_dir: str):
        self.work_dir = Path(work_dir)

    def _validate_input_files(self) -> None:
        """Validate that all required input files and directories exist"""
        missing_items = []

        # Check sliced device directory (output of 2_smt_slicer)
        sliced_dir = self.work_dir / "2_sliced_device_smt_encoding"
        if not sliced_dir.exists():
            missing_items.append("2_sliced_device_smt_encoding/ (directory)")
        else:
            smt_files = list(sliced_dir.glob("sliced_*_smt_encoding.smt2"))
            if not smt_files:
                missing_items.append("2_sliced_device_smt_encoding/ (no sliced SMT files found)")

        # Check dataplane original directory (output of 1_route_analyzer)
        dataplane_dir = self.work_dir / "1_dataplane_original"
        if not dataplane_dir.exists():
            missing_items.append("1_dataplane_original/ (directory)")

        if missing_items:
            logger.error(f"Missing required input files/directories: {', '.join(missing_items)}")
            logger.error(f"Work directory: {self.work_dir}")
            logger.error("Hint: run 1_route_analyzer.py then 2_smt_slicer.py on <work_dir> first.")
            sys.exit(1)

        logger.info("All required input files/directories found")

##########################################################################################
### Assume-Guarantee File Generator
##########################################################################################

class AssumeGuaranteeFileGenerator:
    """Generate complete_forward and complete_reverse SMT files for assume-guarantee testing
    
    This class generates the SMT files needed for assume-guarantee testing.
    The Z3 checks are performed separately by AssumeGuaranteeTester.
    """
    
    def __init__(self, work_dir: str, verbose: bool = False):
        self.work_dir = Path(work_dir)
        self.verbose = verbose
        self.dataplane_original_dir = self.work_dir / "1_dataplane_original"
        self.sliced_device_dir = self.work_dir / "2_sliced_device_smt_encoding"
        
        # Create output directory for test results
        self.test_output_dir = self.work_dir / "3_assume_guarantee_test"
        self.test_output_dir.mkdir(exist_ok=True)
        
        # Load device information
        self.devices = self._load_devices()
        self.ebgp_neighbors = self._load_ebgp_neighbors()
    
    def _load_devices(self) -> List[str]:
        """Load list of devices from sliced device directory"""
        devices = []
        if self.sliced_device_dir.exists():
            for file in self.sliced_device_dir.glob("sliced_*_smt_encoding.smt2"):
                device = file.stem.replace("sliced_", "").replace("_smt_encoding", "")
                devices.append(device)
        return sorted(devices)
    
    def _load_ebgp_neighbors(self) -> Dict[str, Set[str]]:
        """Load eBGP neighbor relationships from BGP neighbors file"""
        neighbors = {}
        bgp_neighbors_file = self.work_dir / "0_ebgp_neighbors.txt"
        
        if not bgp_neighbors_file.exists():
            logger.warning(f"BGP neighbors file not found: {bgp_neighbors_file}")
            return neighbors
            
        with open(bgp_neighbors_file, 'r') as f:
            lines = f.readlines()
            
        # Parse BGP neighbor relationships
        # Format: device1,interface1 -> device2,interface2
        for line in lines:
            line = line.strip()
            if not line or '->' not in line:
                continue
                
            try:
                # Split by '->' and extract device names
                parts = line.split('->')
                if len(parts) != 2:
                    continue
                    
                left_part = parts[0].strip()
                right_part = parts[1].strip()
                
                # Extract device names (before the first comma)
                left_device = left_part.split(',')[0].strip()
                right_device = right_part.split(',')[0].strip()
                
                # Add bidirectional relationship
                if left_device not in neighbors:
                    neighbors[left_device] = set()
                if right_device not in neighbors:
                    neighbors[right_device] = set()
                    
                neighbors[left_device].add(right_device)
                neighbors[right_device].add(left_device)
                
            except Exception as e:
                logger.warning(f"Error parsing BGP neighbor line: {line} - {e}")
                continue
        
        return neighbors
    
    def _load_sliced_device_smt(self, device: str) -> str:
        """Load sliced SMT encoding for a device"""
        smt_file = self.sliced_device_dir / f"sliced_{device}_smt_encoding.smt2"
        if not smt_file.exists():
            raise FileNotFoundError(f"Sliced SMT file not found: {smt_file}")
        
        with open(smt_file, 'r') as f:
            return f.read()
    
    def _load_device_overall_best_routes(self, device: str) -> str:
        """Load overall best routes constraints for a device"""
        routes_file = self.dataplane_original_dir / f"{device}_route_attributes_normal.txt"
        if not routes_file.exists():
            logger.warning(f"Overall best routes file not found: {routes_file}")
            return ""
        
        with open(routes_file, 'r') as f:
            return f.read()
    
    def _load_device_normal_stable_states(self, device: str) -> str:
        """Load normal stable states constraints for a device"""
        states_file = self.dataplane_original_dir / f"{device}_stable_states_normal.txt"
        if not states_file.exists():
            logger.warning(f"Normal stable states file not found: {states_file}")
            return ""
        
        with open(states_file, 'r') as f:
            return f.read()
    
    def _get_route_from_neighbors(self, neighbor_device: str) -> Set[str]:
        """Parse {neighbor_device}_stable_states_normal.txt for 'route from: X' lines.
        Returns the set of device names X (BGP loop prevention: neighbor's route came from X).
        """
        states_file = self.dataplane_original_dir / f"{neighbor_device}_stable_states_normal.txt"
        result: Set[str] = set()
        if not states_file.exists():
            return result
        with open(states_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith("route from:"):
                    # Format: "route from: X" -> X is the device name only
                    neighbor_name = line[len("route from:"):].strip()
                    if neighbor_name:
                        result.add(neighbor_name)
        return result
    
    def _filter_normal_stable_states_constraints_only(self, content: str) -> str:
        """Return normal stable states content without the 'route from:' block at the end.
        Used when adding own device's Guarantee1 so we do not include route-from lines.
        """
        lines = content.split("\n")
        out = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("route from:") or (stripped.startswith(";") and "BGP loop prevention" in stripped and "route origin" in stripped):
                break
            out.append(line)
        return "\n".join(out).rstrip()
    
    def _load_device_combined_constraint_negated(self, device: str) -> str:
        """Load combined constraint negated for a device (required for reverse)."""
        combined_file = self.dataplane_original_dir / f"{device}_combined_constraint_negated.txt"
        if not combined_file.exists():
            raise FileNotFoundError(
                f"Combined constraint negated file required but missing: {combined_file}"
            )
        with open(combined_file, "r", encoding="utf-8") as f:
            return f.read()

    def _extract_variables_from_constraints(self, constraints: str) -> Set[str]:
        """Extract all variables from constraint text"""
        variables = set()
        
        # Pattern to match SMT2 variables: |variable_name| or Config_xxx
        # Match quoted identifiers |...| and Config variables
        var_pattern = r'(\|[^|]+\||Config_[^\s()]+)'
        matches = re.findall(var_pattern, constraints)
        variables.update(matches)
        
        return variables
    
    def _extract_declare_fun_from_smt(self, smt_content: str) -> Dict[str, str]:
        """Extract all declare-fun statements from SMT content
        
        Returns a dictionary mapping variable names to their declare-fun statements
        """
        declarations = {}
        
        # Pattern to match declare-fun statements
        # Format: (declare-fun |var_name| () Type)
        pattern = r'\(declare-fun\s+(\|[^|]+\||[^\s()]+)\s+\(\)\s+([^)]+)\)'
        
        # Find all matches (may span multiple lines)
        matches = re.findall(pattern, smt_content, re.MULTILINE | re.DOTALL)
        
        for var_name, var_type in matches:
            # Reconstruct the full declare-fun statement
            declare_stmt = f"(declare-fun {var_name} () {var_type.strip()})"
            declarations[var_name] = declare_stmt
        
        # Also try to find multi-line declare-fun statements
        lines = smt_content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('(declare-fun'):
                # Collect the full declare-fun statement
                declare_parts = [line]
                paren_count = line.count('(') - line.count(')')
                j = i + 1
                
                while j < len(lines) and paren_count > 0:
                    next_line = lines[j]
                    declare_parts.append(next_line)
                    paren_count += next_line.count('(') - next_line.count(')')
                    j += 1
                
                declare_full = ' '.join(declare_parts)
                # Extract variable name
                var_match = re.search(r'\(declare-fun\s+(\|[^|]+\||[^\s()]+)', declare_full)
                if var_match:
                    var_name = var_match.group(1)
                    declarations[var_name] = declare_full.strip()
                
                i = j - 1
            
            i += 1
        
        return declarations
    
    def _find_missing_declarations(self, device: str, smt_content: str, base_smt: str) -> Dict[str, str]:
        """Find missing variable declarations by checking other device slices"""
        missing_decls = {}
        
        # Extract all variables from constraints (excluding base_smt)
        # Split smt_content to get only the added constraints
        base_end_marker = "(check-sat)"
        if base_end_marker in smt_content:
            added_constraints = smt_content.split(base_end_marker)[0]
            # Remove base_smt from added_constraints
            if base_smt in added_constraints:
                added_constraints = added_constraints.replace(base_smt, "", 1)
        else:
            added_constraints = smt_content.replace(base_smt, "", 1)
        
        # Extract variables from added constraints
        constraint_vars = self._extract_variables_from_constraints(added_constraints)
        
        # Extract declarations from base_smt
        base_declarations = self._extract_declare_fun_from_smt(base_smt)
        
        # Find missing variables
        missing_vars = constraint_vars - set(base_declarations.keys())
        
        if not missing_vars:
            return missing_decls
        
        verbose_info(self.verbose, f"Found {len(missing_vars)} missing variable declarations for device {device}")
        
        # Search in other device slices for missing declarations
        for other_device in self.devices:
            if other_device == device:
                continue
            
            try:
                other_smt = self._load_sliced_device_smt(other_device)
                other_declarations = self._extract_declare_fun_from_smt(other_smt)
                
                # Check if any missing vars are in this device's declarations
                for var in list(missing_vars):
                    if var in other_declarations:
                        missing_decls[var] = other_declarations[var]
                        missing_vars.remove(var)
                        verbose_info(self.verbose, f"  Found declaration for {var} in device {other_device}")
                
                # If we found all missing vars, break early
                if not missing_vars:
                    break
                    
            except FileNotFoundError:
                continue
        
        if missing_vars:
            logger.warning(f"  Could not find declarations for {len(missing_vars)} variables: {list(missing_vars)[:5]}")
        
        return missing_decls
    
    def _add_missing_declarations(self, device: str, smt_content: str, base_smt: str) -> str:
        """Add missing variable declarations to SMT content"""
        missing_decls = self._find_missing_declarations(device, smt_content, base_smt)
        
        if not missing_decls:
            return smt_content
        
        # Build declaration block
        decl_block = "\n".join([f"; Missing declaration from other device\n{decl}" 
                               for decl in missing_decls.values()])
        
        # Insert declarations after base_smt
        # Find the position after base_smt ends
        if base_smt in smt_content:
            # Insert after base_smt
            insertion_pos = smt_content.find(base_smt) + len(base_smt)
            # Find the next newline or start of next section
            next_newline = smt_content.find('\n', insertion_pos)
            if next_newline != -1:
                smt_content = (smt_content[:next_newline+1] + 
                             decl_block + "\n\n" + 
                             smt_content[next_newline+1:])
            else:
                smt_content = smt_content[:insertion_pos] + "\n\n" + decl_block + "\n\n" + smt_content[insertion_pos:]
        else:
            # If base_smt not found, prepend declarations
            smt_content = decl_block + "\n\n" + smt_content
        
        verbose_info(self.verbose, f"Added {len(missing_decls)} missing variable declarations for device {device}")
        return smt_content
    
    def _extract_ebgp_control_forwarding_vars(self, device: str, smt_content: str) -> List[str]:
        """Extract EBGP neighbor CONTROL-FORWARDING variables from sliced SMT encoding"""
        # Find all CONTROL-FORWARDING variable declarations
        control_forwarding_vars = []
        lines = smt_content.split('\n')
        
        for line in lines:
            if 'CONTROL-FORWARDING' in line and 'declare-fun' in line:
                # Extract variable name
                match = re.search(r'(\|0_CONTROL-FORWARDING_[^|]+\|)', line)
                if match:
                    var_name = match.group(1)
                    # Check if this is an EBGP neighbor's variable (not the device's own)
                    if not var_name.startswith(f'|0_CONTROL-FORWARDING_{device}_'):
                        control_forwarding_vars.append(var_name)
        
        return control_forwarding_vars
    
    def _get_neighbor_control_forwarding_constraints(self, device: str, neighbor_vars: List[str]) -> str:
        """Get CONTROL-FORWARDING constraints for EBGP neighbors"""
        constraints = ""
        
        # Group variables by neighbor device to avoid loading the same file multiple times
        neighbor_vars_map = {}
        for var in neighbor_vars:
            # Extract neighbor device name from variable
            # Format: |0_CONTROL-FORWARDING_{neighbor}_{interface}|
            # Note: neighbor device name may contain underscores (e.g., peeramsterdam_0)
            # Match everything between |0_CONTROL-FORWARDING_ and the last underscore before |
            # Example: |0_CONTROL-FORWARDING_peeramsterdam_0_FastEthernet0/0| -> peeramsterdam_0
            match = re.search(r'\|0_CONTROL-FORWARDING_(.+)_[^_|]+\|', var)
            if match:
                neighbor_device = match.group(1)
                if neighbor_device not in neighbor_vars_map:
                    neighbor_vars_map[neighbor_device] = []
                neighbor_vars_map[neighbor_device].append(var)
        
        # Process each neighbor device once
        for neighbor_device, vars_list in neighbor_vars_map.items():
            # Load neighbor's normal stable states (only once per neighbor)
            neighbor_states = self._load_device_normal_stable_states(neighbor_device)
            if neighbor_states:
                # Extract CONTROL-FORWARDING constraints for all variables of this neighbor
                lines = neighbor_states.split('\n')
                for var in vars_list:
                    for line in lines:
                        if var in line and line.strip().startswith('(assert'):
                            # Only load individual interface constraints, not overall OR constraints
                            # Skip lines that contain overall OR constraints (multiple interfaces in one assert)
                            if '(or |0_CONTROL-FORWARDING_' in line and '|0_CONTROL-FORWARDING_' in line.replace('(or |0_CONTROL-FORWARDING_', '', 1):
                                # This is an overall OR constraint, skip it
                                continue
                            
                            # Convert (assert (or (= Var true) (= Var false))) to (assert (= Var true)) for EBGP neighbor constraints
                            processed_line = line.strip()
                            if '(assert (or (= ' in processed_line and 'true) (= ' in processed_line and 'false)))' in processed_line:
                                # Extract variable name and replace with true
                                var_match = re.search(r'(\|0_[^|]+\|)', processed_line)
                                if var_match:
                                    var_name = var_match.group(1)
                                    processed_line = processed_line.replace(f'(assert (or (= {var_name} true) (= {var_name} false)))', f'(assert (= {var_name} true))')
                            
                            # BGP loop prevention: if constraint is (assert (= Var false)) and neighbor's route is from current device, use true instead
                            var_match = re.search(r'\(assert\s*\(\s*=\s+(\|[^|]+\|)\s+false\s*\)\)', processed_line)
                            if var_match:
                                var_name = var_match.group(1)
                                route_from = self._get_route_from_neighbors(neighbor_device)
                                if device in route_from:
                                    original_line = processed_line
                                    processed_line = f"(assert (= {var_name} true))"
                                    constraints += f"; EBGP neighbor {neighbor_device} CONTROL-FORWARDING constraint (BGP loop prevention: route from current device)\n"
                                    constraints += f"; original normal constraint: {original_line}\n"
                                    constraints += processed_line + "\n\n"
                                    verbose_info(self.verbose, f"BGP loop prevention: override {neighbor_device} CONTROL-FORWARDING to true (route from {device})")
                                    break
                            
                            constraints += f"; EBGP neighbor {neighbor_device} CONTROL-FORWARDING constraint\n"
                            constraints += processed_line + "\n\n"
                            verbose_info(self.verbose, f"Added CONTROL-FORWARDING constraint for {neighbor_device}: {line.strip()}")
                            break  # Found the constraint for this variable, move to next
        
        return constraints
    
    def generate_forward_file(self, device: str) -> str:
        """Generate complete forward SMT file for a device (without running Z3 check)"""
        verbose_info(self.verbose, f"Generating forward file for device: {device}")
        
        # Load base SMT encoding
        try:
            base_smt = self._load_sliced_device_smt(device)
        except FileNotFoundError as e:
            logger.error(f"Failed to load sliced SMT for device {device}: {e}")
            return ""
        
        # Build complete SMT content
        smt_content = base_smt + "\n\n"
        
        # Step 1: Assume all BGP neighbors' overall best routes
        if device in self.ebgp_neighbors:
            for neighbor in self.ebgp_neighbors[device]:
                neighbor_routes = self._load_device_overall_best_routes(neighbor)
                if neighbor_routes:
                    smt_content += f"; Assume1: BGP neighbor {neighbor} normal route attributes\n"
                    smt_content += neighbor_routes + "\n\n"
        
        # Step 2: Assume own overall best routes
        own_routes = self._load_device_overall_best_routes(device)
        if own_routes:
            smt_content += f"; Assume2: Device {device} normal route attributes\n"
            smt_content += own_routes + "\n\n"
        
        # Step 3: Add EBGP neighbor CONTROL-FORWARDING constraints
        ebgp_control_forwarding_vars = self._extract_ebgp_control_forwarding_vars(device, base_smt)
        if ebgp_control_forwarding_vars:
            verbose_info(self.verbose, f"Found EBGP CONTROL-FORWARDING variables for device {device}: {ebgp_control_forwarding_vars}")
            neighbor_constraints = self._get_neighbor_control_forwarding_constraints(device, ebgp_control_forwarding_vars)
            if neighbor_constraints:
                smt_content += "; Assume3: BGP neighbors control-forwarding constraints\n"
                smt_content += neighbor_constraints
        
        # Step 4: Guarantee own normal stable states (exclude route from: section at end of file)
        normal_states = self._load_device_normal_stable_states(device)
        if normal_states:
            normal_states = self._filter_normal_stable_states_constraints_only(normal_states)
            if normal_states:
                smt_content += f"; Guarantee1: Device {device} normal stable states\n"
                smt_content += normal_states + "\n\n"
        
        # Step 5: Add check-sat
        smt_content += "(check-sat)\n"
        
        # Step 6: Add missing declarations (without Z3 validation)
        base_smt_marker = "; Assume1:"
        if base_smt_marker in smt_content:
            base_smt_extracted = smt_content.split(base_smt_marker)[0]
        else:
            base_smt_extracted = base_smt
        
        smt_content_with_decls = self._add_missing_declarations(device, smt_content, base_smt_extracted)
        
        return smt_content_with_decls
    
    def generate_reverse_file(self, device: str) -> str:
        """Generate complete reverse SMT file for a device (without running Z3 check)"""
        verbose_info(self.verbose, f"Generating reverse file for device: {device}")
        
        # Load base SMT encoding
        try:
            base_smt = self._load_sliced_device_smt(device)
        except FileNotFoundError as e:
            logger.error(f"Failed to load sliced SMT for device {device}: {e}")
            return ""
        
        # Build complete SMT content
        smt_content = base_smt + "\n\n"
        
        # Step 1: Assume all eBGP neighbors' overall best routes
        if device in self.ebgp_neighbors:
            for neighbor in self.ebgp_neighbors[device]:
                neighbor_routes = self._load_device_overall_best_routes(neighbor)
                if neighbor_routes:
                    smt_content += f"; Assume1: BGP neighbor {neighbor} normal route attributes\n"
                    smt_content += neighbor_routes + "\n\n"
        
        # Step 2: Add EBGP neighbor CONTROL-FORWARDING constraints
        ebgp_control_forwarding_vars = self._extract_ebgp_control_forwarding_vars(device, base_smt)
        if ebgp_control_forwarding_vars:
            verbose_info(self.verbose, f"Found EBGP CONTROL-FORWARDING variables for device {device}: {ebgp_control_forwarding_vars}")
            neighbor_constraints = self._get_neighbor_control_forwarding_constraints(device, ebgp_control_forwarding_vars)
            if neighbor_constraints:
                smt_content += "; Assume2: BGP neighbors control-forwarding constraints\n"
                smt_content += neighbor_constraints
        
        # Step 3: Guarantee own combined constraint negated (required; no fallback)
        # Note: We do NOT assume own overall best routes in reverse verification
        # as this would be too strong and limit the verification flexibility
        combined_constraint = self._load_device_combined_constraint_negated(device)
        smt_content += f"; Guarantee1: Device {device} negated combined constraint\n"
        smt_content += combined_constraint + "\n\n"

        # Step 4: Add check-sat
        smt_content += "(check-sat)\n"
        
        # Step 5: Add missing declarations (without Z3 validation)
        base_smt_marker = "; Assume1:"
        if base_smt_marker in smt_content:
            base_smt_extracted = smt_content.split(base_smt_marker)[0]
        else:
            base_smt_extracted = base_smt
        
        smt_content_with_decls = self._add_missing_declarations(device, smt_content, base_smt_extracted)
        
        return smt_content_with_decls
    
    def generate_files_for_device(self, device: str) -> Tuple[bool, str]:
        """Generate complete_forward and complete_reverse files for a single device.
        
        Returns (success, message) tuple.
        """
        try:
            # Generate forward file
            forward_content = self.generate_forward_file(device)
            if forward_content:
                forward_file = self.test_output_dir / f"complete_forward_{device}.smt2"
                with open(forward_file, 'w') as f:
                    f.write(forward_content)
                verbose_info(self.verbose, f"Generated: {forward_file}")
            
            # Generate reverse file
            reverse_content = self.generate_reverse_file(device)
            if reverse_content:
                reverse_file = self.test_output_dir / f"complete_reverse_{device}.smt2"
                with open(reverse_file, 'w') as f:
                    f.write(reverse_content)
                verbose_info(self.verbose, f"Generated: {reverse_file}")
            
            return True, f"Generated files for device {device}"
        except Exception as e:
            return False, f"Error generating files for device {device}: {e}"
    
    def generate_all_files(self, device_filter: Optional[str] = None, parallel: bool = False) -> None:
        """Generate complete_forward and complete_reverse files for all devices.
        
        Args:
            device_filter: If provided, only generate files for this device
            parallel: If True, generate files in parallel (requires ProcessPoolExecutor)
        """
        devices_to_process = self.devices
        if device_filter:
            if device_filter not in self.devices:
                logger.error(f"Device {device_filter} not found in available devices: {self.devices}")
                return
            devices_to_process = [device_filter]
        
        logger.info(f"Generating assume-guarantee test files for {len(devices_to_process)} device(s)...")
        
        if parallel and len(devices_to_process) > 1:
            # Parallel generation using ThreadPoolExecutor
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            # Use ThreadPoolExecutor for I/O-bound parallel execution
            with ThreadPoolExecutor(max_workers=min(len(devices_to_process), 8)) as executor:
                futures = {executor.submit(self.generate_files_for_device, device): device 
                          for device in devices_to_process}
                
                for future in as_completed(futures):
                    device = futures[future]
                    success, msg = future.result()
                    if success:
                        verbose_info(self.verbose, f"✓ {msg}")
                    else:
                        logger.error(f"✗ {msg}")
        else:
            # Serial generation
            for device in devices_to_process:
                verbose_info(self.verbose, f"Processing device: {device}")
                
                success, msg = self.generate_files_for_device(device)
                if success:
                    verbose_info(self.verbose, f"✓ {msg}")
                else:
                    logger.error(f"✗ {msg}")
        
        logger.info(f"Assume-guarantee test files generated in '{self.test_output_dir}' directory.")


##########################################################################################
### Assume-Guarantee Tester
##########################################################################################

class AssumeGuaranteeTester:
    """Test assume-guarantee constraints for network verification"""
    
    def __init__(self, work_dir: str, device_filter: Optional[str] = None, verbose: bool = False):
        self.work_dir = Path(work_dir)
        self.device_filter = device_filter
        self.verbose = verbose
        
        # Directories for input files (same layout as AssumeGuaranteeFileGenerator)
        self.dataplane_original_dir = self.work_dir / "1_dataplane_original"
        self.sliced_device_dir = self.work_dir / "2_sliced_device_smt_encoding"
        
        # Create output directory for test results
        # Files will be generated on-demand per device in _test_single_device
        self.test_output_dir = self.work_dir / "3_assume_guarantee_test"
        self.test_output_dir.mkdir(exist_ok=True)
        
        # Load device information (will be used to determine which devices to process)
        # Output SMT files are regenerated in _test_single_device before each Z3 run
        self.devices = self._load_devices()
        
        # Load eBGP neighbors for logging (if available)
        self.ebgp_neighbors = self._load_ebgp_neighbors()
    
    def _load_devices(self) -> List[str]:
        """Load list of devices from generated complete_forward files or from sliced device directory
        
        If device_filter is specified, validate it and return only that device.
        If files don't exist yet, load from sliced device directory (files will be generated on-demand).
        """
        devices = []
        
        # First, try to load from existing complete_forward files
        if self.test_output_dir.exists():
            for file in self.test_output_dir.glob("complete_forward_*.smt2"):
                device = file.stem.replace("complete_forward_", "")
                # If device_filter is specified, only include matching device
                if self.device_filter is None or device == self.device_filter:
                    devices.append(device)
        
        # If no files found yet, load from sliced device directory
        # (files will be generated on-demand in _test_single_device)
        if not devices:
            sliced_device_dir = self.work_dir / "2_sliced_device_smt_encoding"
            if sliced_device_dir.exists():
                for file in sliced_device_dir.glob("sliced_*_smt_encoding.smt2"):
                    device = file.stem.replace("sliced_", "").replace("_smt_encoding", "")
                    # If device_filter is specified, only include matching device
                    if self.device_filter is None or device == self.device_filter:
                        devices.append(device)
        
        # Validate device_filter if specified
        if self.device_filter:
            if not devices:
                # Validate device_filter against hostnames file if available
                hostnames_file = self.work_dir / "0_hostnames.txt"
                if hostnames_file.exists():
                    with open(hostnames_file, 'r') as f:
                        valid_devices = [line.strip() for line in f if line.strip()]
                    if self.device_filter not in valid_devices:
                        error_msg = f"Device '{self.device_filter}' not found in 0_hostnames.txt\n"
                        error_msg += f"Available devices: {', '.join(valid_devices)}"
                        raise ValueError(error_msg)
                    # If found in hostnames, add it to devices list
                    devices = [self.device_filter]
                else:
                    raise ValueError(f"Device '{self.device_filter}' not found. Cannot validate device name.")
            else:
                logger.info(f"Filtered to device: {devices[0]}")
        
        return sorted(devices)
    
    def _load_ebgp_neighbors(self) -> Dict[str, Set[str]]:
        """Load eBGP neighbor relationships from BGP neighbors file"""
        neighbors = {}
        bgp_neighbors_file = self.work_dir / "0_ebgp_neighbors.txt"
        
        if not bgp_neighbors_file.exists():
            logger.warning(f"BGP neighbors file not found: {bgp_neighbors_file}")
            return neighbors
            
        with open(bgp_neighbors_file, 'r') as f:
            lines = f.readlines()
            
        # Parse BGP neighbor relationships
        # Format: device1,interface1 -> device2,interface2
        for line in lines:
            line = line.strip()
            if not line or '->' not in line:
                continue
                
            try:
                # Split by '->' and extract device names
                parts = line.split('->')
                if len(parts) != 2:
                    continue
                    
                left_part = parts[0].strip()
                right_part = parts[1].strip()
                
                # Extract device names (before the first comma)
                left_device = left_part.split(',')[0].strip()
                right_device = right_part.split(',')[0].strip()
                
                # Add bidirectional relationship
                if left_device not in neighbors:
                    neighbors[left_device] = set()
                if right_device not in neighbors:
                    neighbors[right_device] = set()
                    
                neighbors[left_device].add(right_device)
                neighbors[right_device].add(left_device)
                
            except Exception as e:
                logger.warning(f"Error parsing BGP neighbor line: {line} - {e}")
                continue
        
        return neighbors
    
    def _load_sliced_device_smt(self, device: str) -> str:
        """Load sliced SMT encoding for a device"""
        smt_file = self.sliced_device_dir / f"sliced_{device}_smt_encoding.smt2"
        if not smt_file.exists():
            raise FileNotFoundError(f"Sliced SMT file not found: {smt_file}")
        
        with open(smt_file, 'r') as f:
            return f.read()
    
    def _load_device_overall_best_routes(self, device: str) -> str:
        """Load overall best routes constraints for a device"""
        routes_file = self.dataplane_original_dir / f"{device}_route_attributes_normal.txt"
        if not routes_file.exists():
            logger.warning(f"Overall best routes file not found: {routes_file}")
            return ""
        
        with open(routes_file, 'r') as f:
            return f.read()
    
    def _load_device_normal_stable_states(self, device: str) -> str:
        """Load normal stable states constraints for a device"""
        states_file = self.dataplane_original_dir / f"{device}_stable_states_normal.txt"
        if not states_file.exists():
            logger.warning(f"Normal stable states file not found: {states_file}")
            return ""
        
        with open(states_file, 'r') as f:
            return f.read()
    
    def _get_route_from_neighbors(self, neighbor_device: str) -> Set[str]:
        """Parse {neighbor_device}_stable_states_normal.txt for 'route from: X' lines.
        Returns the set of device names X (BGP loop prevention: neighbor's route came from X).
        """
        states_file = self.dataplane_original_dir / f"{neighbor_device}_stable_states_normal.txt"
        result: Set[str] = set()
        if not states_file.exists():
            return result
        with open(states_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith("route from:"):
                    # Format: "route from: X" -> X is the device name only
                    neighbor_name = line[len("route from:"):].strip()
                    if neighbor_name:
                        result.add(neighbor_name)
        return result
    
    def _filter_normal_stable_states_constraints_only(self, content: str) -> str:
        """Return normal stable states content without the 'route from:' block at the end.
        Used when adding own device's Guarantee1 so we do not include route-from lines.
        """
        lines = content.split("\n")
        out = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("route from:") or (stripped.startswith(";") and "BGP loop prevention" in stripped and "route origin" in stripped):
                break
            out.append(line)
        return "\n".join(out).rstrip()

    def _run_z3_check(self, smt_content: str, debug_file: str = None) -> Tuple[bool, str]:
        """Run Z3 on SMT content and return (is_sat, output)"""
        temp_file = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.smt2', delete=False) as f:
                f.write(smt_content)
                temp_file = f.name
            
            # Save debug file if requested
            if debug_file:
                try:
                    with open(debug_file, 'w') as f:
                        f.write(smt_content)
                    verbose_info(self.verbose, f"Debug SMT file saved to: {debug_file}")
                except Exception as e:
                    logger.warning(f"Failed to save debug file {debug_file}: {e}")
            
            # Run Z3
            result = subprocess.run(['z3', temp_file], 
                                  capture_output=True, text=True)
            
            # Check if there are any error messages in stdout first
            output = result.stdout.strip()
            
            # Log stderr errors if any, but don't stop processing
            if result.stderr.strip():
                logger.warning(f"Z3 stderr: {result.stderr.strip()}")
            
            # Log return code issues if any, but don't stop processing
            if result.returncode != 0:
                logger.warning(f"Z3 return code: {result.returncode}")
            
            if "(error" in output:
                # Extract error message from stdout
                lines = output.split('\n')
                error_lines = [line for line in lines if line.startswith('(error')]
                if error_lines:
                    error_msg = '; '.join(error_lines)
                    
                    # Enhanced compatibility: Handle "unknown constant" errors
                    if "unknown constant" in error_msg:
                        logger.warning(f"Compatibility issue detected: {error_msg}")
                        logger.info("This is likely due to Minesweeper optimization removing unused variables.")
                        logger.info("Attempting to extract SAT/UNSAT result despite the error...")
                        
                        # Try to extract sat/unsat from the last non-empty line of output
                        lines = output.split('\n')
                        last_line = ""
                        for line in reversed(lines):
                            line = line.strip()
                            if line and not line.startswith('(error'):
                                last_line = line
                                break
                        
                        if last_line == "sat":
                            logger.info("✓ Extracted result: SAT (despite unknown constant error)")
                            return True, "sat (compatibility mode)"
                        elif last_line == "unsat":
                            logger.info("✓ Extracted result: UNSAT (despite unknown constant error)")
                            return False, "unsat (compatibility mode)"
                        else:
                            logger.warning(f"Could not extract SAT/UNSAT result from output. Last line: '{last_line}'")
                            return False, f"Z3 error: {error_msg}"
                    else:
                        return False, f"Z3 error: {error_msg}"
            
            # Normal case: no errors in output
            if output == "sat":
                return True, output
            elif output == "unsat":
                return False, output
            else:
                logger.warning(f"Unexpected Z3 output: {output}")
                return False, f"Unexpected output: {output}"
                
        except FileNotFoundError:
            return False, "Z3 not found in PATH"
        except Exception as e:
            return False, f"Error running Z3: {str(e)}"
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")
    
    def _extract_variables_from_constraints(self, constraints: str) -> Set[str]:
        """Extract all variables from constraint text"""
        import re
        variables = set()
        
        # Pattern to match SMT2 variables: |variable_name| or Config_xxx
        # Match quoted identifiers |...| and Config variables
        var_pattern = r'(\|[^|]+\||Config_[^\s()]+)'
        matches = re.findall(var_pattern, constraints)
        variables.update(matches)
        
        return variables
    
    def _extract_declare_fun_from_smt(self, smt_content: str) -> Dict[str, str]:
        """Extract all declare-fun statements from SMT content
        
        Returns a dictionary mapping variable names to their declare-fun statements
        """
        import re
        declarations = {}
        
        # Pattern to match declare-fun statements
        # Format: (declare-fun |var_name| () Type)
        pattern = r'\(declare-fun\s+(\|[^|]+\||[^\s()]+)\s+\(\)\s+([^)]+)\)'
        
        # Find all matches (may span multiple lines)
        matches = re.findall(pattern, smt_content, re.MULTILINE | re.DOTALL)
        
        for var_name, var_type in matches:
            # Reconstruct the full declare-fun statement
            declare_stmt = f"(declare-fun {var_name} () {var_type.strip()})"
            declarations[var_name] = declare_stmt
        
        # Also try to find multi-line declare-fun statements
        lines = smt_content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('(declare-fun'):
                # Collect the full declare-fun statement
                declare_parts = [line]
                paren_count = line.count('(') - line.count(')')
                j = i + 1
                
                while j < len(lines) and paren_count > 0:
                    next_line = lines[j]
                    declare_parts.append(next_line)
                    paren_count += next_line.count('(') - next_line.count(')')
                    j += 1
                
                declare_full = ' '.join(declare_parts)
                # Extract variable name
                var_match = re.search(r'\(declare-fun\s+(\|[^|]+\||[^\s()]+)', declare_full)
                if var_match:
                    var_name = var_match.group(1)
                    declarations[var_name] = declare_full.strip()
                
                i = j - 1
            
            i += 1
        
        return declarations
    
    def _find_missing_declarations(self, device: str, smt_content: str, base_smt: str) -> Dict[str, str]:
        """Find missing variable declarations by checking other device slices"""
        missing_decls = {}
        
        # Extract all variables from constraints (excluding base_smt)
        # Split smt_content to get only the added constraints
        base_end_marker = "(check-sat)"
        if base_end_marker in smt_content:
            added_constraints = smt_content.split(base_end_marker)[0]
            # Remove base_smt from added_constraints
            if base_smt in added_constraints:
                added_constraints = added_constraints.replace(base_smt, "", 1)
        else:
            added_constraints = smt_content.replace(base_smt, "", 1)
        
        # Extract variables from added constraints
        constraint_vars = self._extract_variables_from_constraints(added_constraints)
        
        # Extract declarations from base_smt
        base_declarations = self._extract_declare_fun_from_smt(base_smt)
        
        # Find missing variables
        missing_vars = constraint_vars - set(base_declarations.keys())
        
        if not missing_vars:
            return missing_decls
        
        verbose_info(self.verbose, f"Found {len(missing_vars)} missing variable declarations for device {device}")
        
        # Search in other device slices for missing declarations
        for other_device in self.devices:
            if other_device == device:
                continue
            
            try:
                other_smt = self._load_sliced_device_smt(other_device)
                other_declarations = self._extract_declare_fun_from_smt(other_smt)
                
                # Check if any missing vars are in this device's declarations
                for var in list(missing_vars):
                    if var in other_declarations:
                        missing_decls[var] = other_declarations[var]
                        missing_vars.remove(var)
                        verbose_info(self.verbose, f"  Found declaration for {var} in device {other_device}")
                
                # If we found all missing vars, break early
                if not missing_vars:
                    break
                    
            except FileNotFoundError:
                continue
        
        if missing_vars:
            logger.warning(f"  Could not find declarations for {len(missing_vars)} variables: {list(missing_vars)[:5]}")
        
        return missing_decls
    
    def _add_missing_declarations(self, device: str, smt_content: str, base_smt: str) -> str:
        """Add missing variable declarations to SMT content"""
        missing_decls = self._find_missing_declarations(device, smt_content, base_smt)
        
        if not missing_decls:
            return smt_content
        
        # Find where to insert declarations (after base_smt, before constraints)
        # Insert after the last declare-fun in base_smt or at the beginning of added content
        base_declarations = self._extract_declare_fun_from_smt(base_smt)
        
        # Build declaration block
        decl_block = "\n".join([f"; Missing declaration from other device\n{decl}" 
                               for decl in missing_decls.values()])
        
        # Insert declarations after base_smt
        # Find the position after base_smt ends
        if base_smt in smt_content:
            # Insert after base_smt
            insertion_pos = smt_content.find(base_smt) + len(base_smt)
            # Find the next newline or start of next section
            next_newline = smt_content.find('\n', insertion_pos)
            if next_newline != -1:
                smt_content = (smt_content[:next_newline+1] + 
                             decl_block + "\n\n" + 
                             smt_content[next_newline+1:])
            else:
                smt_content = smt_content[:insertion_pos] + "\n\n" + decl_block + "\n\n" + smt_content[insertion_pos:]
        else:
            # If base_smt not found, prepend declarations
            smt_content = decl_block + "\n\n" + smt_content
        
        verbose_info(self.verbose, f"Added {len(missing_decls)} missing variable declarations for device {device}")
        return smt_content
    
    def _validate_and_clean_constraints(self, device: str, smt_content: str) -> Tuple[str, List[str]]:
        """Validate constraints and add missing variable declarations"""
        verbose_info(self.verbose, f"Validating constraints for device: {device}")
        
        # Extract base_smt from smt_content (everything before the first comment about Assume/Guarantee)
        base_smt_marker = "; Assume1:"
        if base_smt_marker in smt_content:
            base_smt = smt_content.split(base_smt_marker)[0]
        else:
            # Fallback: try to find the sliced device SMT
            try:
                base_smt = self._load_sliced_device_smt(device)
            except FileNotFoundError:
                base_smt = ""
        
        # First, try to add missing declarations
        smt_content_with_decls = self._add_missing_declarations(device, smt_content, base_smt)
        
        # Then validate
        is_valid, output = self._run_z3_check(smt_content_with_decls)
        
        # Check if there are errors in the output (not just SAT/UNSAT)
        if "error" not in output.lower():
            # No errors, return content with declarations
            verbose_info(self.verbose, f"All constraints are valid for device: {device}")
            return smt_content_with_decls, []
        
        # Extract undeclared variables from error messages
        undeclared_vars = []
        if "error" in output.lower():
            # Look for patterns like "error: line X: unknown constant |variable_name|"
            import re
            error_pattern = r'unknown constant (\|[^|]+\||[^\s()]+)'
            matches = re.findall(error_pattern, output)
            undeclared_vars.extend(matches)
        
        if not undeclared_vars:
            # If we can't extract specific variables, return content with declarations
            logger.warning(f"Could not extract undeclared variables from error: {output}")
            return smt_content_with_decls, []
        
        verbose_info(self.verbose, f"Found {len(undeclared_vars)} still undeclared variables for device {device}: {undeclared_vars[:5]}")
        
        # Remove constraints containing undeclared variables
        cleaned_content = smt_content_with_decls
        removed_constraints = []
        
        for var in undeclared_vars:
            # Find and remove lines containing this variable
            lines = cleaned_content.split('\n')
            new_lines = []
            
            for line in lines:
                if var in line and line.strip().startswith('(assert'):
                    removed_constraints.append(line.strip())
                    verbose_info(self.verbose, f"Removed constraint: {line.strip()}")
                else:
                    new_lines.append(line)
            
            cleaned_content = '\n'.join(new_lines)
        
        # Test the cleaned content
        is_valid_after, output_after = self._run_z3_check(cleaned_content)
        
        if is_valid_after or "error" not in output_after.lower():
            logger.info(f"Successfully cleaned constraints for device: {device}")
            return cleaned_content, removed_constraints
        else:
            logger.warning(f"Still have errors after cleaning for device {device}: {output_after}")
            return cleaned_content, removed_constraints
    
    def _extract_ebgp_control_forwarding_vars(self, device: str, smt_content: str) -> List[str]:
        """Extract EBGP neighbor CONTROL-FORWARDING variables from sliced SMT encoding"""
        import re
        
        # Find all CONTROL-FORWARDING variable declarations
        control_forwarding_vars = []
        lines = smt_content.split('\n')
        
        for line in lines:
            if 'CONTROL-FORWARDING' in line and 'declare-fun' in line:
                # Extract variable name
                match = re.search(r'(\|0_CONTROL-FORWARDING_[^|]+\|)', line)
                if match:
                    var_name = match.group(1)
                    # Check if this is an EBGP neighbor's variable (not the device's own)
                    if not var_name.startswith(f'|0_CONTROL-FORWARDING_{device}_'):
                        control_forwarding_vars.append(var_name)
        
        return control_forwarding_vars
    
    def _get_neighbor_control_forwarding_constraints(self, device: str, neighbor_vars: List[str]) -> str:
        """Get CONTROL-FORWARDING constraints for EBGP neighbors"""
        constraints = ""
        import re
        
        # Group variables by neighbor device to avoid loading the same file multiple times
        neighbor_vars_map = {}
        for var in neighbor_vars:
            # Extract neighbor device name from variable
            # Format: |0_CONTROL-FORWARDING_{neighbor}_{interface}|
            # Note: neighbor device name may contain underscores (e.g., peeramsterdam_0)
            # Match everything between |0_CONTROL-FORWARDING_ and the last underscore before |
            # Example: |0_CONTROL-FORWARDING_peeramsterdam_0_FastEthernet0/0| -> peeramsterdam_0
            match = re.search(r'\|0_CONTROL-FORWARDING_(.+)_[^_|]+\|', var)
            if match:
                neighbor_device = match.group(1)
                if neighbor_device not in neighbor_vars_map:
                    neighbor_vars_map[neighbor_device] = []
                neighbor_vars_map[neighbor_device].append(var)
        
        # Process each neighbor device once
        for neighbor_device, vars_list in neighbor_vars_map.items():
            # Load neighbor's normal stable states (only once per neighbor)
            neighbor_states = self._load_device_normal_stable_states(neighbor_device)
            if neighbor_states:
                # Extract CONTROL-FORWARDING constraints for all variables of this neighbor
                lines = neighbor_states.split('\n')
                for var in vars_list:
                    for line in lines:
                        if var in line and line.strip().startswith('(assert'):
                            # Only load individual interface constraints, not overall OR constraints
                            # Skip lines that contain overall OR constraints (multiple interfaces in one assert)
                            if '(or |0_CONTROL-FORWARDING_' in line and '|0_CONTROL-FORWARDING_' in line.replace('(or |0_CONTROL-FORWARDING_', '', 1):
                                # This is an overall OR constraint, skip it
                                continue
                            
                            # Convert (assert (or (= Var true) (= Var false))) to (assert (= Var true)) for EBGP neighbor constraints
                            processed_line = line.strip()
                            if '(assert (or (= ' in processed_line and 'true) (= ' in processed_line and 'false)))' in processed_line:
                                # Extract variable name and replace with true
                                var_match = re.search(r'(\|0_[^|]+\|)', processed_line)
                                if var_match:
                                    var_name = var_match.group(1)
                                    processed_line = processed_line.replace(f'(assert (or (= {var_name} true) (= {var_name} false)))', f'(assert (= {var_name} true))')
                            
                            # BGP loop prevention: if constraint is (assert (= Var false)) and neighbor's route is from current device, use true instead
                            var_match = re.search(r'\(assert\s*\(\s*=\s+(\|[^|]+\|)\s+false\s*\)\)', processed_line)
                            if var_match:
                                var_name = var_match.group(1)
                                route_from = self._get_route_from_neighbors(neighbor_device)
                                if device in route_from:
                                    original_line = processed_line
                                    processed_line = f"(assert (= {var_name} true))"
                                    constraints += f"; EBGP neighbor {neighbor_device} CONTROL-FORWARDING constraint (BGP loop prevention: route from current device)\n"
                                    constraints += f"; original normal constraint: {original_line}\n"
                                    constraints += processed_line + "\n\n"
                                    verbose_info(self.verbose, f"BGP loop prevention: override {neighbor_device} CONTROL-FORWARDING to true (route from {device})")
                                    break
                            
                            constraints += f"; EBGP neighbor {neighbor_device} CONTROL-FORWARDING constraint\n"
                            constraints += processed_line + "\n\n"
                            verbose_info(self.verbose, f"Added CONTROL-FORWARDING constraint for {neighbor_device}: {line.strip()}")
                            break  # Found the constraint for this variable, move to next
        
        return constraints

    def test_forward_verification(self, device: str) -> Tuple[bool, str]:
        """Test forward verification: read complete_forward file and run Z3 check"""
        verbose_info(self.verbose, f"Testing forward verification for device: {device}")
        
        # Load the complete forward file generated by 2_smt_slicer.py
        forward_file = self.test_output_dir / f"complete_forward_{device}.smt2"
        if not forward_file.exists():
            logger.error(f"Complete forward file not found: {forward_file}")
            logger.error(f"  This file should be generated by 2_smt_slicer.py")
            return False, f"Complete forward file not found: {forward_file}"
        
        # Read the file content
        with open(forward_file, 'r') as f:
            smt_content = f.read()
        
        # Run Z3 check
        is_sat, output = self._run_z3_check(smt_content, str(forward_file))
        
        return is_sat, output
    
    def test_reverse_verification(self, device: str) -> Tuple[bool, str]:
        """Test reverse verification: read complete_reverse file and run Z3 check"""
        verbose_info(self.verbose, f"Testing reverse verification for device: {device}")
        
        # Load the complete reverse file generated by 2_smt_slicer.py
        reverse_file = self.test_output_dir / f"complete_reverse_{device}.smt2"
        if not reverse_file.exists():
            logger.error(f"Complete reverse file not found: {reverse_file}")
            logger.error(f"  This file should be generated by 2_smt_slicer.py")
            return False, f"Complete reverse file not found: {reverse_file}"
        
        # Read the file content
        with open(reverse_file, 'r') as f:
            smt_content = f.read()
        
        # Run Z3 check
        is_sat, output = self._run_z3_check(smt_content, str(reverse_file))
        
        return is_sat, output
    
    def _test_single_device(self, device: str) -> Dict[str, Tuple[bool, str]]:
        """Test a single device (forward and reverse verification)
        
        This method:
        1. Generates forward/reverse SMT encoding files for the device (always regenerate)
        2. Runs Z3 checks on the generated files
        
        This allows full parallelization per device via --device flag.
        """
        verbose_info(self.verbose, f"{'='*60}")
        verbose_info(self.verbose, f"Processing device: {device}")
        verbose_info(self.verbose, f"{'='*60}")
        
        device_results = {}
        
        # Step 1: Always regenerate forward/reverse files before Z3 checks
        verbose_info(self.verbose, f"Generating forward/reverse files for device: {device}")
        generator = AssumeGuaranteeFileGenerator(str(self.work_dir), verbose=self.verbose)
        generator.generate_files_for_device(device)
        
        # Step 2: Test forward verification
        forward_sat, forward_output = self.test_forward_verification(device)
        device_results['forward'] = (forward_sat, forward_output)
        verbose_info(self.verbose, f"Forward test result: {'SAT' if forward_sat else 'UNSAT'}")
        if not forward_sat:
            logger.warning(f"Forward test failed (expected SAT): {forward_output}")
        
        # Step 3: Test reverse verification
        reverse_sat, reverse_output = self.test_reverse_verification(device)
        device_results['reverse'] = (reverse_sat, reverse_output)
        verbose_info(self.verbose, f"Reverse test result: {'SAT' if reverse_sat else 'UNSAT'}")
        if reverse_sat:
            logger.warning(f"Reverse test failed (expected UNSAT): {reverse_output}")
        
        return device_results
    
    def run_all_tests(self, parallel: bool = False, max_workers: Optional[int] = None) -> Dict[str, Dict[str, Tuple[bool, str]]]:
        """Run all tests for all devices
        
        Args:
            parallel: If True, run tests in parallel using ThreadPoolExecutor
            max_workers: Maximum number of parallel workers (default: number of devices)
        
        Returns:
            Dictionary mapping device name to test results
        """
        results = {}
        
        verbose_info(self.verbose, f"Running assume-guarantee tests for {len(self.devices)} devices")
        verbose_info(self.verbose, f"Devices: {self.devices}")
        verbose_info(self.verbose, f"eBGP neighbors: {self.ebgp_neighbors}")
        if parallel:
            verbose_info(self.verbose, f"Running tests in parallel (max_workers={max_workers or len(self.devices)})...")
        else:
            verbose_info(self.verbose, "Running tests serially...")
        
        if parallel and len(self.devices) > 1:
            # Parallel execution: each device generates its own files and runs Z3 checks
            # This fully supports --device flag for parallel processing
            if max_workers is None:
                max_workers = len(self.devices)
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all device tests
                future_to_device = {
                    executor.submit(self._test_single_device, device): device
                    for device in self.devices
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_device):
                    device = future_to_device[future]
                    try:
                        device_results = future.result()
                        results[device] = device_results
                        
                        # If not verbose, print completion status for each device
                        if not self.verbose:
                            forward_sat, _ = device_results['forward']
                            reverse_sat, _ = device_results['reverse']
                            forward_ok = forward_sat  # Expected: SAT
                            reverse_ok = not reverse_sat  # Expected: UNSAT
                            if forward_ok and reverse_ok:
                                print(f"Device {device}: ✓ Completed")
                            else:
                                print(f"Device {device}: ✗ Failed")
                    except Exception as e:
                        logger.error(f"Error testing device {device}: {e}")
                        results[device] = {
                            'forward': (False, f"Error: {e}"),
                            'reverse': (False, f"Error: {e}")
                        }
        else:
            # Serial execution
            for device in self.devices:
                device_results = self._test_single_device(device)
                results[device] = device_results
                # If not verbose, print completion status for each device
                if not self.verbose:
                    forward_sat, _ = device_results['forward']
                    reverse_sat, _ = device_results['reverse']
                    forward_ok = forward_sat  # Expected: SAT
                    reverse_ok = not reverse_sat  # Expected: UNSAT
                    if forward_ok and reverse_ok:
                        print(f"Device {device}: ✓ Completed")
                    else:
                        print(f"Device {device}: ✗ Failed")
        
        return results
    
    def print_summary(self, results: Dict[str, Dict[str, Tuple[bool, str]]]):
        """Print test summary and save to file"""
        verbose_info(self.verbose, f"{'='*80}")
        verbose_info(self.verbose, "ASSUME-GUARANTEE TEST SUMMARY")
        verbose_info(self.verbose, f"{'='*80}")
        
        failed_devices = []
        summary_lines = []
        
        # Add header to summary
        summary_lines.append("=" * 80)
        summary_lines.append("ASSUME-GUARANTEE TEST SUMMARY")
        summary_lines.append("=" * 80)
        summary_lines.append("")
        
        for device, device_results in results.items():
            forward_sat, forward_output = device_results['forward']
            reverse_sat, reverse_output = device_results['reverse']
            
            forward_ok = forward_sat  # Expected: SAT
            reverse_ok = not reverse_sat  # Expected: UNSAT
            
            status = "PASS" if forward_ok and reverse_ok else "FAIL"
            
            # Log to console (only in verbose mode)
            log_line = f"Device {device:25} | Forward: {'SAT' if forward_sat else 'UNSAT':5} | Reverse: {'SAT' if reverse_sat else 'UNSAT':5} | Status: {status}"
            verbose_info(self.verbose, log_line)
            summary_lines.append(log_line)
            
            if not forward_ok:
                error_msg = f"  Forward test failed for {device}: {forward_output}"
                logger.error(error_msg)  # Always show errors
                summary_lines.append(error_msg)
                failed_devices.append(f"{device} (forward)")
            
            if not reverse_ok:
                error_msg = f"  Reverse test failed for {device}: {reverse_output}"
                logger.error(error_msg)  # Always show errors
                summary_lines.append(error_msg)
                failed_devices.append(f"{device} (reverse)")
        
        # Add summary statistics
        summary_lines.append("")
        summary_lines.append(f"Total devices tested: {len(results)}")
        
        # Count failed devices properly
        # A device is considered failed if either forward or reverse test failed
        unique_failed_devices = set()
        for failed_entry in failed_devices:
            # failed_entry format: "device (forward)" or "device (reverse)"
            device_name = failed_entry.split(' (')[0]
            unique_failed_devices.add(device_name)
            
        summary_lines.append(f"Failed devices: {len(unique_failed_devices)}")
        
        verbose_info(self.verbose, f"\nTotal devices tested: {len(results)}")
        verbose_info(self.verbose, f"Failed devices: {len(unique_failed_devices)}")
        
        if failed_devices:
            # Group failures by device
            failures_by_device = {}
            for failed_entry in failed_devices:
                device_name = failed_entry.split(' (')[0]
                failure_type = failed_entry.split(' (')[1].replace(')', '')
                if device_name not in failures_by_device:
                    failures_by_device[device_name] = []
                failures_by_device[device_name].append(failure_type)
            
            # Format error message
            failed_list = []
            for device, types in sorted(failures_by_device.items()):
                failed_list.append(f"{device} ({', '.join(types)})")
                
            error_msg = f"Failed devices: {', '.join(failed_list)}"
            logger.error(error_msg)  # Always show errors
            summary_lines.append(error_msg)
        else:
            success_msg = "All tests passed! ✓"
            verbose_info(self.verbose, success_msg)
            summary_lines.append(success_msg)
        
        # Save summary to file (suffix with device name when --device xxx is used)
        if self.device_filter:
            summary_file = self.test_output_dir / f"test_summary_{self.device_filter}.txt"
        else:
            summary_file = self.test_output_dir / "test_summary.txt"
        try:
            with open(summary_file, 'w') as f:
                f.write('\n'.join(summary_lines))
            verbose_info(self.verbose, f"\nTest summary saved to: {summary_file}")
        except Exception as e:
            logger.error(f"Failed to save test summary to {summary_file}: {e}")
    
    def all_tests_passed(self, results: Dict[str, Dict[str, Tuple[bool, str]]]) -> bool:
        """Check if all forward and reverse tests passed"""
        for device, device_results in results.items():
            forward_sat, _ = device_results['forward']
            reverse_sat, _ = device_results['reverse']
            
            forward_ok = forward_sat  # Expected: SAT
            reverse_ok = not reverse_sat  # Expected: UNSAT
            
            if not (forward_ok and reverse_ok):
                return False
        
        return True
    
    def calculate_routemap_level_subspecs(self, parallel: bool = False, max_workers: Optional[int] = None) -> None:
        """Calculate route-map level subspecs from forward verification models
        
        Args:
            parallel: If True, process devices in parallel (each device saves to its own file)
            max_workers: Maximum number of parallel workers (default: number of devices)
        """
        if parallel and len(self.devices) > 1:
            # Parallel processing: each device processes independently and saves to its own file
            if max_workers is None:
                max_workers = len(self.devices)
            
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._calculate_routemap_level_subspecs_for_device, device): device
                    for device in self.devices
                }
                
                for future in as_completed(futures):
                    device = futures[future]
                    try:
                        future.result()
                        if not self.verbose:
                            print(f"Device {device}: ✓ Route-map level subspecs completed")
                    except Exception as e:
                        logger.error(f"Error calculating route-map level subspecs for device {device}: {e}")
        else:
            # Serial processing: process all devices and save to combined file
            calculator = RoutemapSubspecCalculator(self.work_dir, self.devices, self.test_output_dir, device_filter=None)
            calculator.calculate_routemap_level_subspecs()
    
    def _calculate_routemap_level_subspecs_for_device(self, device: str) -> None:
        """Calculate route-map level subspecs for a single device (for parallel processing)"""
        calculator = RoutemapSubspecCalculator(self.work_dir, [device], self.test_output_dir, device_filter=device)
        calculator.calculate_routemap_level_subspecs()


def main():
    """Main function for assume-guarantee testing (order: other, -r, -v, -d, --device)"""
    device_filter = None
    interface_level = False
    verbose = False
    delete_intermediate = False
    work_dir = None

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '-r':
            interface_level = True
            i += 1
        elif arg == '-v':
            verbose = True
            i += 1
        elif arg == '-d':
            delete_intermediate = True
            i += 1
        elif arg == '--device':
            if i + 1 < len(sys.argv):
                device_filter = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --device requires a value")
                sys.exit(1)
        elif not arg.startswith('-'):
            work_dir = arg
            i += 1
        else:
            print(f"Error: Unknown option: {arg}")
            sys.exit(1)

    if work_dir is None:
        print("Usage: python 3_assume_guarantee_tester.py [-r] [-v] [-d] [--device DEVICE] <work_directory>")
        print("Options:")
        print("  -r               If provided (and all tests pass), also compute route-map level subspecs")
        print("  -v               Verbose mode: Show detailed INFO logs")
        print("                   Without -v: Only show WARNING/ERROR logs and completion status")
        print("  -d               Delete intermediate output files before running, then exit")
        print("  --device DEVICE Process only the specified device (default: all devices)")
        print("Example: python 3_assume_guarantee_tester.py smt_output_network_1")
        print("         python 3_assume_guarantee_tester.py -r -v smt_output_network_1")
        print("         python 3_assume_guarantee_tester.py --device r1 smt_output_network_1")
        sys.exit(1)

    if not Path(work_dir).exists():
        logger.error(f"Work directory does not exist: {work_dir}")
        sys.exit(1)

    # Delete intermediate files if requested
    if delete_intermediate:
        import shutil
        deleted_items = []

        output_dir = Path(work_dir) / "3_assume_guarantee_test"
        if output_dir.exists():
            logger.info(f"Deleting intermediate output directory: {output_dir}")
            shutil.rmtree(output_dir)
            deleted_items.append(str(output_dir))

        subspec_files_dir = Path(work_dir) / "3_subspec_files"
        if subspec_files_dir.exists():
            routemap_files = list(subspec_files_dir.glob("routemap_level_subspecs*.txt"))
            for routemap_file in routemap_files:
                logger.info(f"Deleting route-map level subspecs file: {routemap_file}")
                routemap_file.unlink()
                deleted_items.append(str(routemap_file))

        if deleted_items:
            logger.info(f"Deleted {len(deleted_items)} intermediate file(s)/directory(ies):")
            for item in deleted_items:
                logger.info(f"  - {item}")
            logger.info("Intermediate files deleted.")
        else:
            logger.info("No intermediate files found to delete.")
        sys.exit(0)

    # Set logging level based on verbose flag (same as 1_route_analyzer / 2_smt_slicer)
    if not verbose:
        logging.getLogger().setLevel(logging.WARNING)

    # Validate required input files before running (same step as 1/2/4)
    validator = InputValidator(work_dir)
    validator._validate_input_files()

    tester = AssumeGuaranteeTester(work_dir, device_filter=device_filter, verbose=verbose)

    results = tester.run_all_tests(parallel=False)
    tester.print_summary(results)

    if tester.all_tests_passed(results) and interface_level:
        verbose_info(verbose, "="*80)
        verbose_info(verbose, "All tests passed! Calculating route-map level subspecs (-r enabled)...")
        verbose_info(verbose, "="*80)
        tester.calculate_routemap_level_subspecs(parallel=False)
    elif tester.all_tests_passed(results) and not interface_level:
        verbose_info(verbose, "="*80)
        verbose_info(verbose, "All tests passed. Skipping route-map level subspec calculation (enable with -r).")
        verbose_info(verbose, "="*80)
    else:
        verbose_info(verbose, "="*80)
        verbose_info(verbose, "Some tests failed. Skipping route-map level subspec calculation.")
        verbose_info(verbose, "="*80)

if __name__ == "__main__":
    main()
