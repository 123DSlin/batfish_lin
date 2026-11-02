#!/usr/bin/env python3
"""
Community Subspec Calculator: CommunityList non-empty subspec calculation.
"""

import re
import os
import logging
import subprocess
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class CommunitySubspecCalculator:
    """Calculator for CommunityList non-empty subspecs"""

    def __init__(self, work_dir: Path,
                 field_level_intermediate_dir: Path, line_level_intermediate_dir: Path,
                 get_bounds_for_single_config_variable_fn, parse_z3_output_fn,
                 verification_file: Optional[Path] = None, synthesis_file: Optional[Path] = None):
        self.work_dir = work_dir
        self.assume_guarantee_dir = work_dir / "3_assume_guarantee_test"
        self.verification_file_override = verification_file
        self.synthesis_file_override = synthesis_file
        self.field_level_intermediate_dir = field_level_intermediate_dir
        self.line_level_intermediate_dir = line_level_intermediate_dir
        self._get_bounds_for_single_config_variable = get_bounds_for_single_config_variable_fn
        self._parse_z3_output = parse_z3_output_fn

    def is_community_config_variable(self, config_var_name: str) -> bool:
        if not config_var_name.endswith('_community'):
            return False
        if 'CommunityList' in config_var_name and 'exact_community' in config_var_name:
            return True
        return False

    def get_all_possible_communities(self) -> Set[str]:
        communities = set()
        communities_file = self.work_dir / "0_regex_communities.txt"
        if not communities_file.exists():
            logger.warning(f"Communities file not found: {communities_file}")
            return communities
        with open(communities_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if '_REGEX' in line or '_OTHER' in line or line.startswith('^'):
                    continue
                community = line.split()[0] if line.split() else line
                if ':' in community and not community.startswith('^'):
                    communities.add(community)
        logger.info(f"Found {len(communities)} possible community values: {sorted(communities)}")
        return communities

    def extract_community_variables_from_verification_file(self, config_var, device: str) -> Set[str]:
        safe_config_name = config_var.name.replace('/', '_').replace(':', '_').replace(' ', '_')
        if self.verification_file_override:
            verification_file = self.verification_file_override
        else:
            verification_file = self.assume_guarantee_dir / f"complete_reverse_{device}.smt2"
        if not verification_file.exists():
            logger.warning(f"Verification file not found for device {device}: {verification_file}")
            return set()
        logger.info(f"    Using verification file for CommunityList: {verification_file}")
        with open(verification_file, 'r') as f:
            verification_content = f.read()
        community_vars = set()
        pattern1 = rf'\(=\s+{re.escape(config_var.name)}\s+(\|[^|]*community[^|]*\|)\)'
        community_vars.update(re.findall(pattern1, verification_content, re.DOTALL))
        pattern2 = rf'\(=\s+(\|[^|]*community[^|]*\|)\s+{re.escape(config_var.name)}\)'
        community_vars.update(re.findall(pattern2, verification_content, re.DOTALL))
        if not community_vars:
            logger.warning(f"Could not find community variables for {config_var.name} in verification file")
            return set()
        logger.info(f"  Found {len(community_vars)} community variable(s) for {config_var.name}: {sorted(community_vars)}")
        config_line_pattern = f"(assert (= {config_var.name} {config_var.value}))"
        if config_line_pattern in verification_content:
            bounds = self._get_bounds_for_single_config_variable(config_var.name)
            if bounds:
                bounds_str = "\n".join(bounds) + "\n"
                modified_content = verification_content.replace(config_line_pattern, f"; {config_line_pattern}\n{bounds_str}")
            else:
                modified_content = verification_content.replace(config_line_pattern, f"; {config_line_pattern}")
        else:
            modified_content = verification_content
        combined_constraint_file = self.work_dir / "1_dataplane_original" / f"{device}_combined_constraint_negated.txt"
        negated_stable_pattern = f"; Guarantee1: Device {device} negated stable states"
        if negated_stable_pattern in modified_content and combined_constraint_file.exists():
            with open(combined_constraint_file, 'r') as f:
                combined_content = f.read()
            # Include all assert lines (combined constraint + e.g. OVERALL_BEST_None_prefixLength)
            combined_asserts: List[str] = []
            for line in combined_content.split('\n'):
                line = line.strip()
                if line and not line.startswith(';') and line.startswith('(assert'):
                    combined_asserts.append(line)
            if combined_asserts:
                lines = modified_content.split('\n')
                modified_lines = []
                in_negated_section = False
                for i, line in enumerate(lines):
                    if negated_stable_pattern in line:
                        in_negated_section = True
                        modified_lines.append(f"; Guarantee1: Device {device} combined constraint negated\n")
                        for a in combined_asserts:
                            modified_lines.append(a + "\n")
                    elif in_negated_section:
                        if line.strip().startswith('(check-sat'):
                            modified_lines.append("\n\n")
                            modified_lines.append(line + "\n")
                            in_negated_section = False
                        elif line.strip().startswith(';') and ('guarantee' in line.lower() or 'assume' in line.lower()) and i > 0:
                            modified_lines.append(line + "\n")
                            in_negated_section = False
                    else:
                        modified_lines.append(line + "\n")
                modified_content = ''.join(modified_lines)
        synthesis_subspec_file = self.field_level_intermediate_dir / f"synthesis_subspec_{device}_{safe_config_name}.smt2"
        with open(synthesis_subspec_file, 'w') as f:
            f.write(modified_content)
        logger.info(f"    Intermediate file saved to: {synthesis_subspec_file}")
        return community_vars

    def find_all_community_vars_in_constraints(self, config_var, content: str) -> Set[str]:
        community_vars = set()
        pattern1 = rf'\(=\s+{re.escape(config_var.name)}\s+(\|[^|]*community[^|]*\|)\)'
        community_vars.update(re.findall(pattern1, content))
        pattern2 = rf'\(=\s+(\|[^|]*community[^|]*\|)\s+{re.escape(config_var.name)}\)'
        community_vars.update(re.findall(pattern2, content))
        return community_vars

    def test_community_replacement(self, config_var, device: str,
                                   all_original_community_vars: Set[str], new_community_var: str,
                                   action_var: Optional[object] = None, action_value: Optional[bool] = None,
                                   is_line_level: bool = False) -> bool:
        logger.info(f"    Testing community replacement: {sorted(all_original_community_vars)} -> {new_community_var}")
        safe_config_name = config_var.name.replace('/', '_').replace(':', '_').replace(' ', '_')
        if self.verification_file_override:
            verification_file = self.verification_file_override
        else:
            verification_file = self.assume_guarantee_dir / f"complete_reverse_{device}.smt2"
        if not verification_file.exists():
            logger.error(f"Verification file not found for device {device}: {verification_file}")
            return False
        with open(verification_file, 'r') as f:
            content = f.read()
        found_community_vars = self.find_all_community_vars_in_constraints(config_var, content)
        all_vars_to_replace = all_original_community_vars.union(found_community_vars)
        if not all_vars_to_replace:
            logger.warning(f"    No community variables found in constraints for {config_var.name}")
            return False
        logger.info(f"    Found {len(all_vars_to_replace)} community variable(s) to replace: {sorted(all_vars_to_replace)}")
        vars_to_replace_set = set(all_vars_to_replace)
        escaped_config_var = re.escape(config_var.name)
        escaped_vars = '|'.join(re.escape(var) for var in all_vars_to_replace)
        combined_pattern = rf'\(=\s+({escaped_config_var}|{escaped_vars})\s+({escaped_config_var}|{escaped_vars})\)'

        def replacement_func(match):
            left, right = match.group(1), match.group(2)
            if left == config_var.name and right in vars_to_replace_set:
                return f"(= {config_var.name} {new_community_var})"
            if right == config_var.name and left in vars_to_replace_set:
                return f"(= {new_community_var} {config_var.name})"
            return match.group(0)

        modified_content = re.sub(combined_pattern, replacement_func, content)
        community_match = re.search(r'community_([0-9]+:[0-9]+)', new_community_var)
        if community_match:
            community_value = community_match.group(1).replace(':', '_')
        else:
            community_value = new_community_var.replace('|', '').replace(':', '_').replace('/', '_')[-20:]
        action_suffix = ""
        if action_var and action_value is not None:
            action_constraint = f"(assert (= {action_var.name} {'true' if action_value else 'false'}))\n"
            action_pattern = rf'\(assert\s+\(=\s+{re.escape(action_var.name)}\s+(true|false)\)\)'
            if re.search(action_pattern, modified_content):
                modified_content = re.sub(action_pattern,
                                        f"(assert (= {action_var.name} {'true' if action_value else 'false'}))",
                                        modified_content)
            else:
                check_sat_pos = modified_content.find('(check-sat')
                if check_sat_pos != -1:
                    modified_content = modified_content[:check_sat_pos] + action_constraint + modified_content[check_sat_pos:]
                else:
                    modified_content = modified_content + "\n" + action_constraint
            if is_line_level:
                action_suffix = f"_{'permit' if action_value else 'deny'}_{community_value}"
        intermediate_dir = self.line_level_intermediate_dir if is_line_level else self.field_level_intermediate_dir
        if action_suffix:
            output_file = intermediate_dir / f"community_replacement_test_{device}_{safe_config_name}{action_suffix}.smt2"
        else:
            output_file = intermediate_dir / f"community_replacement_test_{device}_{safe_config_name}_{community_value}.smt2"
        if "(check-sat)" not in modified_content:
            modified_content = modified_content.rstrip() + "\n(check-sat)\n"
        with open(output_file, 'w') as f:
            f.write(modified_content)
        logger.info(f"    Community replacement test file saved to: {output_file}")
        try:
            result = subprocess.run(['z3', str(output_file)],
                                  capture_output=True, text=True)
            if result.returncode != 0 and "(error" in result.stdout:
                error_lines = [line for line in result.stdout.split('\n') if line.startswith('(error')]
                if error_lines:
                    error_msg = '; '.join(error_lines)
                    if "unknown constant" in error_msg:
                        logger.info("    Marking as nonconfigurable: community variable does not exist")
                        return False
            is_sat, _ = self._parse_z3_output(result)
            if is_sat:
                logger.info(f"    Result: SAT -> CANNOT configure as {new_community_var}")
                return False
            logger.info(f"    Result: UNSAT -> CAN configure as {new_community_var}")
            return True
        except Exception as e:
            logger.error(f"    Error running Z3: {e}")
            return False

    def merge_community_subspecs(self, base_subspec: str, configurable: List[str], nonconfigurable: List[str],
                                 action_type: Optional[str] = None) -> Optional[str]:
        if base_subspec == "empty":
            return None
        parts = [base_subspec]
        if action_type:
            parts.append(f"configurable ({action_type}) = {{{', '.join(configurable)}}}" if configurable else f"configurable ({action_type}) = {{}}")
            parts.append(f"nonconfigurable ({action_type}) = {{{', '.join(nonconfigurable)}}}" if nonconfigurable else f"nonconfigurable ({action_type}) = {{}}")
        else:
            parts.append(f"configurable = {{{', '.join(configurable)}}}" if configurable else "configurable = {}")
            parts.append(f"nonconfigurable = {{{', '.join(nonconfigurable)}}}" if nonconfigurable else "nonconfigurable = {}")
        return " AND ".join(parts)

    def calculate_community_extended_subspecs(self, config_var, device: str,
                                              base_subspec: str, action_var: Optional[object] = None,
                                              action_value: Optional[bool] = None, is_line_level: bool = False) -> Optional[Tuple[List[str], List[str]]]:
        logger.info(f"  Calculating extended subspecs for community config variable: {config_var.name}")
        original_community_vars = self.extract_community_variables_from_verification_file(config_var, device)
        if not original_community_vars:
            logger.warning(f"  Could not extract community variables for {config_var.name}, skipping extended analysis")
            return None
        logger.info(f"  Found {len(original_community_vars)} community variable(s): {sorted(original_community_vars)}")
        original_community_values = set()
        base_var_patterns = []
        for original_var in original_community_vars:
            community_match = re.search(r'community_([0-9]+:[0-9]+)', original_var)
            if community_match:
                original_community_values.add(community_match.group(1))
                base_pattern = re.sub(r'community_[0-9]+:[0-9]+', 'community_PLACEHOLDER', original_var)
                base_var_patterns.append((original_var, base_pattern))
        if not original_community_values:
            logger.warning(f"  Could not extract community values from {original_community_vars}")
            return None
        all_communities = self.get_all_possible_communities()
        if not all_communities:
            logger.warning("  No communities found, skipping extended analysis")
            return None
        all_communities_to_test = all_communities
        configurable_communities = []
        non_configurable_communities = []
        logger.info(f"  Testing {len(all_communities_to_test)} communities (including original): {sorted(all_communities_to_test)}")
        for community in sorted(all_communities_to_test):
            if base_var_patterns:
                new_community_var = base_var_patterns[0][1].replace('PLACEHOLDER', community)
            else:
                first_orig_var = list(original_community_vars)[0]
                new_community_var = re.sub(r'community_[0-9]+:[0-9]+', f'community_{community}', first_orig_var)
            can_configure = self.test_community_replacement(config_var, device,
                                                           original_community_vars, new_community_var,
                                                           action_var=action_var, action_value=action_value,
                                                           is_line_level=is_line_level)
            if can_configure:
                configurable_communities.append(community)
            else:
                non_configurable_communities.append(community)
        configurable_original = [c for c in configurable_communities if c in original_community_values]
        configurable_other = [c for c in configurable_communities if c not in original_community_values]
        configurable_communities = sorted(configurable_original) + sorted(configurable_other)
        nonconfigurable_original = [c for c in non_configurable_communities if c in original_community_values]
        nonconfigurable_other = [c for c in non_configurable_communities if c not in original_community_values]
        non_configurable_communities = sorted(nonconfigurable_original) + sorted(nonconfigurable_other)
        return (configurable_communities, non_configurable_communities)

    def extract_community_and_action_vars_from_line_group(self, line_group) -> Tuple[Optional[object], Optional[object]]:
        community_var = None
        action_var = None
        for config_var in line_group.config_variables:
            if self.is_community_config_variable(config_var.name):
                community_var = config_var
            elif config_var.name.endswith('_action'):
                action_var = config_var
        return (community_var, action_var)

    def calculate_line_level_community_subspecs(self, line_group, base_subspec: str) -> List[str]:
        community_var, action_var = self.extract_community_and_action_vars_from_line_group(line_group)
        if not community_var:
            return [base_subspec]
        logger.info(f"  Found community variable: {community_var.name}")
        if action_var:
            logger.info(f"  Found action variable: {action_var.name}")
        if not action_var:
            extended_info = self.calculate_community_extended_subspecs(community_var, line_group.device, base_subspec, is_line_level=True)
            if not extended_info:
                return [base_subspec]
            configurable, nonconfigurable = extended_info
            merged_subspec = self.merge_community_subspecs(base_subspec, configurable, nonconfigurable)
            return [merged_subspec] if merged_subspec else [base_subspec]
        logger.info("  Calculating permit case (action = true)...")
        permit_extended_info = self.calculate_community_extended_subspecs(community_var, line_group.device, base_subspec,
                                                                         action_var=action_var, action_value=True, is_line_level=True)
        logger.info("  Calculating deny case (action = false)...")
        deny_extended_info = self.calculate_community_extended_subspecs(community_var, line_group.device, base_subspec,
                                                                       action_var=action_var, action_value=False, is_line_level=True)
        parts = [base_subspec]
        if permit_extended_info:
            permit_configurable, permit_nonconfigurable = permit_extended_info
            parts.append(f"configurable (permit) = {{{', '.join(permit_configurable)}}}" if permit_configurable else "configurable (permit) = {}")
            parts.append(f"nonconfigurable (permit) = {{{', '.join(permit_nonconfigurable)}}}" if permit_nonconfigurable else "nonconfigurable (permit) = {}")
        if deny_extended_info:
            deny_configurable, deny_nonconfigurable = deny_extended_info
            parts.append(f"configurable (deny) = {{{', '.join(deny_configurable)}}}" if deny_configurable else "configurable (deny) = {}")
            parts.append(f"nonconfigurable (deny) = {{{', '.join(deny_nonconfigurable)}}}" if deny_nonconfigurable else "nonconfigurable (deny) = {}")
        return [" AND ".join(parts)]
