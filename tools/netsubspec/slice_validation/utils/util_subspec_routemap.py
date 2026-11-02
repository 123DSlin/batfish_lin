#!/usr/bin/env python3
"""
Route-Map Subspec Calculator: route-map level subspecs from forward verification models.
"""

import re
import os
import logging
import subprocess
import tempfile
from typing import Dict, List, Set, Optional
from pathlib import Path

from utils.util_smt import prefix_string_to_constraint

logger = logging.getLogger(__name__)


class RoutemapSubspecCalculator:
    """Calculate route-map level subspecs from forward verification models"""

    def __init__(self, work_dir: Path, devices: List[str], test_output_dir: Path, device_filter: Optional[str] = None):
        self.work_dir = work_dir
        self.devices = devices
        self.test_output_dir = test_output_dir
        self.device_filter = device_filter
        self.subspec_files_dir = self.work_dir / "3_subspec_files"
        self.subspec_files_dir.mkdir(exist_ok=True, parents=True)

    def _extract_routemap_prefix(self, var_name: str) -> Optional[str]:
        if not var_name.startswith('|0_') or not var_name.endswith('|'):
            return None
        inner = var_name[3:-1]
        if '_BGP_' not in inner:
            return None
        if '__' in inner:
            double_underscore_pos = inner.find('__')
            if double_underscore_pos > 0:
                return '|0_' + inner[:double_underscore_pos]
        if '_BGP_IMPORT_' in inner or '_BGP_EXPORT_' in inner:
            if '_BGP_IMPORT_' in inner:
                bgp_type_end = inner.find('_BGP_IMPORT_') + len('_BGP_IMPORT_')
            else:
                bgp_type_end = inner.find('_BGP_EXPORT_') + len('_BGP_EXPORT_')
            attribute_patterns = [
                r'_community_\^[^_]+_\w+$',
                r'_community_[^_]+$',
                r'_permitted$', r'_prefixLength$', r'_metric$', r'_med$', r'_choice$',
            ]
            for pattern in attribute_patterns:
                match = re.search(pattern, inner)
                if match:
                    return '|0_' + inner[:match.start()]
            for keyword in ['_permitted', '_prefixLength', '_metric', '_med', '_choice', '_community_']:
                if keyword in inner:
                    keyword_pos = inner.find(keyword)
                    if keyword_pos > bgp_type_end:
                        return '|0_' + inner[:keyword_pos]
        return None

    def _parse_z3_model(self, model_output: str) -> Dict[str, str]:
        model = {}
        lines = model_output.split('\n')
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith('(define-fun'):
                var_match = re.search(r'\(define-fun\s+(\|[^|]+\|)', stripped)
                if var_match:
                    var_name = var_match.group(1)
                    type_pattern = r'\(\)\s+((?:[^\s\(\)]+|\([^\)]+\))+)'
                    type_match = re.search(type_pattern, stripped)
                    if type_match:
                        type_end = type_match.end()
                        remaining_on_line = stripped[type_end:].strip()
                        if remaining_on_line and not remaining_on_line.startswith('('):
                            value = remaining_on_line.rstrip(')').strip()
                        else:
                            value_parts = []
                            j = i + 1
                            paren_depth = 1
                            while j < len(lines) and paren_depth > 0:
                                next_line = lines[j].strip()
                                paren_depth += next_line.count('(') - next_line.count(')')
                                if paren_depth == 0:
                                    if next_line.endswith(')'):
                                        value_parts.append(next_line[:-1].strip())
                                    value = ' '.join(value_parts).strip() if value_parts else ''
                                    i = j
                                    break
                                else:
                                    value_parts.append(next_line)
                                j += 1
                            else:
                                value = ' '.join(value_parts).strip() if value_parts else ''
                                i = j - 1
                        if value:
                            model[var_name] = re.sub(r'\s+', ' ', value.strip())
            i += 1
        return model

    def _sort_routemap_variables(self, variables: List[str]) -> List[str]:
        choice_vars, permitted_vars, prefixLength_vars, metric_vars, med_vars = [], [], [], [], []
        other_vars, exact_community_vars, other_community_vars, regex_community_vars = [], [], [], []
        for var in variables:
            if var.endswith('_choice|'):
                choice_vars.append(var)
            elif var.endswith('_permitted|'):
                permitted_vars.append(var)
            elif var.endswith('_prefixLength|'):
                prefixLength_vars.append(var)
            elif var.endswith('_metric|'):
                metric_vars.append(var)
            elif var.endswith('_med|'):
                med_vars.append(var)
            elif '_community_' in var:
                if '_community_^' in var and var.endswith('_OTHER|'):
                    other_community_vars.append(var)
                elif '_community_^' in var and var.endswith('_REGEX|'):
                    regex_community_vars.append(var)
                else:
                    exact_community_vars.append(var)
            else:
                other_vars.append(var)
        for lst in (choice_vars, permitted_vars, prefixLength_vars, metric_vars, med_vars,
                   other_vars, exact_community_vars, other_community_vars, regex_community_vars):
            lst.sort()
        return (choice_vars + permitted_vars + prefixLength_vars + metric_vars + med_vars
                + other_vars + exact_community_vars + other_community_vars + regex_community_vars)

    def _format_routemap_name(self, routemap_prefix: str) -> str:
        formatted = routemap_prefix[1:] if routemap_prefix.startswith('|') else routemap_prefix
        return re.sub(r'(\d+)/(\d+)', r'\1_\2', formatted)

    def _load_prefix_constraints(self) -> Optional[str]:
        dst_ips_file = self.work_dir / "0_dst_ips.txt"
        if not dst_ips_file.exists():
            logger.warning(f"Destination IPs file not found: {dst_ips_file}")
            return None
        prefix_constraints = []
        with open(dst_ips_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    constraint = prefix_string_to_constraint(line)
                    if constraint:
                        prefix_constraints.append(constraint)
        if not prefix_constraints:
            return None
        return " AND ".join(prefix_constraints)

    def _build_subspec_from_model(self, routemap_prefix: str, model: Dict[str, str], prefix_constraints: Optional[str] = None) -> str:
        prefix_vars = [var for var in model.keys() if var.startswith(routemap_prefix)]
        if not prefix_vars:
            return ""
        choice_vars = [var for var in prefix_vars if var.endswith('_choice|')]
        if len(choice_vars) == len(prefix_vars) and len(choice_vars) > 0:
            return "non route-map"
        permitted_vars = [var for var in prefix_vars if var.endswith('_permitted|')]
        if permitted_vars and model.get(permitted_vars[0], "").strip().lower() == "false":
            return "empty"
        filtered_vars = [var for var in prefix_vars
                        if not (var.endswith('_permitted|') or var.endswith('_choice|')) and '_community_' not in var]
        constraints = []
        if prefix_constraints:
            constraints.append(prefix_constraints)
        if not filtered_vars:
            return " AND ".join(constraints) if constraints else ""
        sorted_vars = self._sort_routemap_variables(filtered_vars)
        for var in sorted_vars:
            constraints.append(f"(= {var} {model[var]})")
        return " AND ".join(constraints)

    def _get_all_possible_communities(self) -> Set[str]:
        communities = set()
        communities_file = self.work_dir / "0_regex_communities.txt"
        if not communities_file.exists():
            return communities
        with open(communities_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '_REGEX' in line or '_OTHER' in line or line.startswith('^'):
                    continue
                community = line.split()[0] if line.split() else line
                if ':' in community and not community.startswith('^'):
                    communities.add(community)
        return communities

    def _extract_community_variables_for_routemap(self, routemap_prefix: str, model: Dict[str, str]) -> List[str]:
        return sorted(var_name for var_name in model.keys()
                      if var_name.startswith(routemap_prefix) and '_community_' in var_name
                      and '_OTHER' not in var_name and '_REGEX' not in var_name)

    def _test_community_configurable(self, device: str, routemap_prefix: str,
                                     community_vars: List[str], test_community: Optional[str],
                                     forward_file_path: Path) -> bool:
        with open(forward_file_path, 'r') as f:
            smt_content = f.read()
        check_sat_pos = smt_content.find('(check-sat)')
        if check_sat_pos == -1:
            return False
        if test_community is None:
            community_constraints = [f"(assert (= {var_name} false))" for var_name in community_vars]
            comment = ";case: community = none (all false)"
        else:
            community_constraints = []
            for var_name in community_vars:
                m = re.search(r'community_([0-9]+:[0-9]+)', var_name)
                if m:
                    community_constraints.append(f"(assert (= {var_name} true))" if m.group(1) == test_community else f"(assert (= {var_name} false))")
            comment = f";case: community = {test_community}"
        modified_content = smt_content[:check_sat_pos] + "\n" + comment + "\n" + "\n".join(community_constraints) + "\n" + smt_content[check_sat_pos:]
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.smt2', delete=False) as f:
                f.write(modified_content)
                temp_file = f.name
            result = subprocess.run(['z3', temp_file], capture_output=True, text=True)
            if result.returncode != 0:
                return False
            output_lower = result.stdout.strip().lower()
            return output_lower.startswith('sat') and not output_lower.startswith('unsat')
        except Exception:
            return False
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass

    def _calculate_routemap_community_subspecs(self, device: str, routemap_prefix: str,
                                                base_subspec: str, model: Dict[str, str],
                                                forward_file_path: Path) -> str:
        if base_subspec in ("non route-map", "empty"):
            return base_subspec
        community_vars = self._extract_community_variables_for_routemap(routemap_prefix, model)
        if not community_vars:
            return base_subspec
        all_communities = self._get_all_possible_communities()
        if not all_communities:
            return base_subspec
        available_communities = set()
        for var_name in community_vars:
            m = re.search(r'community_([0-9]+:[0-9]+)', var_name)
            if m:
                available_communities.add(m.group(1))
        if not available_communities:
            return base_subspec
        configurable_communities = [c for c in sorted(available_communities)
                                   if self._test_community_configurable(device, routemap_prefix, community_vars, c, forward_file_path)]
        if self._test_community_configurable(device, routemap_prefix, community_vars, None, forward_file_path):
            configurable_communities.append("none")
        if configurable_communities:
            return f"{base_subspec} AND configurable = {{{', '.join(configurable_communities)}}}"
        return base_subspec

    def calculate_routemap_level_subspecs(self) -> None:
        devices_to_process = [self.device_filter] if self.device_filter else self.devices
        if self.device_filter and self.device_filter not in self.devices:
            logger.error(f"Device {self.device_filter} not found in available devices: {self.devices}")
            return
        prefix_constraints = self._load_prefix_constraints()
        routemap_subspecs = {}
        for device in devices_to_process:
            forward_file = self.test_output_dir / f"complete_forward_{device}.smt2"
            if not forward_file.exists():
                logger.warning(f"Forward verification file not found: {forward_file}")
                continue
            with open(forward_file, 'r') as f:
                smt_content = f.read()
            smt_content = smt_content.replace('(check-sat)', '(check-sat)\n(get-model)') if '(check-sat)' in smt_content else smt_content + "\n(check-sat)\n(get-model)\n"
            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.smt2', delete=False) as f:
                    f.write(smt_content)
                    temp_file = f.name
                result = subprocess.run(['z3', temp_file], capture_output=True, text=True)
                if result.returncode != 0 or '(error' in result.stdout or 'define-fun' not in result.stdout:
                    continue
                output = result.stdout.strip()
                model = self._parse_z3_model(output)
                bgp_vars = {}
                for var_name in model.keys():
                    if '_BGP_' in var_name:
                        prefix = self._extract_routemap_prefix(var_name)
                        if prefix:
                            bgp_vars.setdefault(prefix, []).append(var_name)
                for routemap_prefix, _ in bgp_vars.items():
                    routemap_subspecs.setdefault(routemap_prefix, set())
                    subspec = self._build_subspec_from_model(routemap_prefix, model, prefix_constraints)
                    if subspec:
                        if subspec not in ("non route-map", "empty"):
                            extended = self._calculate_routemap_community_subspecs(device, routemap_prefix, subspec, model, forward_file)
                            routemap_subspecs[routemap_prefix].add(extended)
                        else:
                            routemap_subspecs[routemap_prefix].add(subspec)
            finally:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except Exception:
                        pass
        output_file = self.subspec_files_dir / (f"routemap_level_subspecs_{self.device_filter}.txt" if self.device_filter else "routemap_level_subspecs.txt")
        with open(output_file, 'w') as f:
            f.write("Route-Map Level Subspecs\n========================\n\n")
            if not routemap_subspecs:
                f.write("No route-map level subspecs found.\n")
            else:
                for routemap_prefix in sorted(routemap_subspecs.keys()):
                    subspecs_set = routemap_subspecs[routemap_prefix]
                    f.write(f"RouteMap: {self._format_routemap_name(routemap_prefix)}\n")
                    if subspecs_set:
                        f.write(f"Subspecs ({len(subspecs_set)}):\n")
                        for i, subspec in enumerate(sorted(subspecs_set), 1):
                            f.write(f"  {i}. {subspec}\n")
                    else:
                        f.write("No subspecs found.\n")
                    f.write("-" * 50 + "\n\n")
        logger.info(f"Route-map level subspecs saved to: {output_file}")
