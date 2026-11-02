#!/usr/bin/env python3
"""BoolExpr (per-community) OVERALL_BEST community encoding for RouteAnalyzer."""

from __future__ import annotations

import logging
import sys
from typing import Dict, List, Optional, Set, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    Route = Any

logger = logging.getLogger(__name__)

OVERALL_BEST_PREFIX = "OVERALL_BEST"
REGEX_COMMUNITIES_FILE = "0_regex_communities.txt"


class BoolCommunityEncoder:
    """Multiple BoolExpr: one SMT Bool variable per exact community on OVERALL_BEST."""

    def __init__(self, host) -> None:
        self._host = host
        self.exact_communities: Set[str] = set()
        self.all_communities: Set[str] = set()

    def load(self) -> None:
        """Load regex communities from 0_regex_communities.txt file and extract exact communities"""
        regex_file = self._host.work_dir / REGEX_COMMUNITIES_FILE
        if not regex_file.exists():
            logger.info("No regex communities file found, skipping regex community loading")
            return
        
        logger.info(f"Loading regex communities from {regex_file}")
        
        with open(regex_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Add the full community entry
                community = line.strip()
                self.all_communities.add(community)
                
                if line.endswith('_REGEX') or line.endswith('_OTHER'):
                    continue

                # TODO: temporarily filter out x:y:z-style (e.g. extended) communities; confirm later.
                if community.count(':') >= 2:
                    continue

                # Add the exact community entry
                self.exact_communities.add(community)

        logger.info(f"Loaded {len(self.all_communities)} regex community entries")
        logger.info(f"Extracted {len(self.exact_communities)} exact communities: {sorted(self.exact_communities)}")

    def generate_community_variables(self, device: str, ecmp_routes: List[Route], negated_mode: bool = False) -> Union[Dict[str, str], str]:
        """Generate community SMT variables or negated constraints according to the new specification
        
        Args:
            device: Device hostname
            ecmp_routes: List of routes (single or multiple for ECMP)
            negated_mode: If True, generate negated constraint string (without metric); if False, generate normal state variables dict
        
        Returns:
            If negated_mode=False: Dict[str, str] - community variable name and value dictionary
            If negated_mode=True: str - negated community constraint SMT string (without metric, to be combined by caller)
        
        Note: When negated_mode=True, the returned constraint does NOT include metric constraint.
              The metric constraint should be added by the caller (e.g., generate_negated_route_attributes_constraint).
        
        Community Cases (3 scenarios):
        0. No routes
        1. One route (with or without communities)
        2. ECMP routes (multiple routes)
        """
        community_vars = {}
        
        # If no communities were collected globally
        # In normal mode: return empty dict early
        # In negated mode: continue to handle Case 0 (no routes) to return None for metric constraint
        if not self.exact_communities:
            if negated_mode:
                # In negated mode, we need to handle Case 0 (no routes) specially
                # to return None, which allows generate_negated_route_attributes_constraint to generate metric constraint
                if len(ecmp_routes) == 0:
                    # Case 0: No routes - return None for metric constraint
                    return None
                else:
                    # Other cases with no communities defined - return None
                    return None
            else:
                # In normal mode, return empty dict early
                return community_vars
        
        # Collect communities from current device's routes
        device_route_communities = []
        all_bgp_routes = self._host.get_all_bgp_info(device, ecmp_routes[0].network) if ecmp_routes else []
        
        # Handle different route scenarios (simplified to 3 cases)
        if len(ecmp_routes) == 0:
            # Case 0: No routes
            result = self._handle_community_case_0(device, negated_mode)
        elif len(ecmp_routes) == 1:
            # Case 1: One route (with or without communities)
            # For single route, collect ALL communities from the route (can be zero, one, or multiple)
            single_bgp_route = all_bgp_routes[0] if all_bgp_routes else None
            carried_communities = single_bgp_route.communities if (single_bgp_route and single_bgp_route.communities) else []
            result = self._handle_community_case_1(device, carried_communities, negated_mode)
        else:
            # Case 2: ECMP routes (multiple routes)
            # Collect ALL communities from each ECMP route (can be zero, one, or multiple)
            # Then deduplicate by communities combination (using sorted tuple as key)
            ecmp_route_community_combinations = []
            for bgp_route in all_bgp_routes:
                if bgp_route.communities:
                    # Collect all communities from this route
                    # Use sorted tuple as key for deduplication
                    communities_tuple = tuple(sorted(bgp_route.communities))
                    ecmp_route_community_combinations.append(communities_tuple)
                else:
                    # Mark as empty tuple to indicate no community
                    ecmp_route_community_combinations.append(tuple())
            
            # Deduplicate: get unique community combinations
            unique_combinations = list(set(ecmp_route_community_combinations))
            # Convert back to lists for processing
            unique_community_lists = [list(combo) for combo in unique_combinations]
            
            result = self._handle_community_case_2(device, unique_community_lists, negated_mode)
        
        # Handle other-communities from 0_regex_communities.txt (only _OTHER suffix)
        # Only for normal mode (negated mode returns constraint string or None directly)
        if not negated_mode:
            community_vars = result  # type: Dict[str, str]
            for other_comm in sorted(self.all_communities):
                if other_comm.endswith('_OTHER'):
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{other_comm}")
                    community_vars[var_name] = "false"
            return community_vars
        else:
            # Negated mode: result is already a constraint string or None
            return result  # type: Union[str, None]
    
    def _handle_community_case_0(self, device: str, negated_mode: bool = False) -> Union[Dict[str, str], Optional[str]]:
        """Case 0: No routes - all communities false
        
        Normal: all communities = false
        Negated 0A: (or (not (= comm_1 false)) ...) [with communities defined] - returns constraint without metric
        Negated 0B: None [without communities defined] - no community constraint, only metric constraint needed
        """
        if negated_mode:
            if self.exact_communities:
                # Case 0A: With communities defined
                community_conditions = []
                for community in sorted(self.exact_communities):
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                    community_conditions.append(f"(not (= {var_name} false))")
                if len(community_conditions) == 1:
                    return community_conditions[0]
                else:
                    return f"(or {' '.join(community_conditions)})"
            else:
                # Case 0B: Without communities defined - return None, caller will handle metric only
                return None
        else:
            # Normal mode: return community variables
            community_vars = {}
            for community in sorted(self.exact_communities):
                var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                community_vars[var_name] = "false"
            return community_vars
    
    def _handle_community_case_1(self, device: str, carried_communities: List[str], negated_mode: bool = False) -> Union[Dict[str, str], str]:
        """Case 1: One route (with or without communities)
        
        Handles single route scenarios (same format for one or multiple communities):
        - Route with zero community: all communities = false (direct asserts)
        - Route with one community: one = true, others = false (direct asserts)
        - Route with multiple communities: carried = true, others = false (direct asserts, same as one-community)
        
        Normal mode:
        - All cases: direct variable assignments -> (assert (= comm1 true)) (assert (= comm2 false)) ...
        
        Negated mode:
        - If zero community: (or (not (= comm1 false)) ...) or None
        - If one or multiple communities: (or (not (= carried true)) (not (= other false)) ...)
        
        Args:
            device: Device hostname
            carried_communities: List of communities carried by the route (can be empty, one, or multiple)
            negated_mode: Whether to generate negated constraint
        """
        # Convert to set for easier lookup
        carried_communities_set = set(carried_communities)
        num_carried = len(carried_communities_set)
        
        # Handle simple cases (zero or one community) with direct variable assignments
        if num_carried == 0:
            # Zero community: all communities = false
            if negated_mode:
                if self.exact_communities:
                    # Negated: (or (not (= comm1 false)) (not (= comm2 false)) ...)
                    community_conditions = []
                    for comm in sorted(self.exact_communities):
                        comm_var = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                        community_conditions.append(f"(not (= {comm_var} false))")
                    
                    if len(community_conditions) == 1:
                        return community_conditions[0]
                    else:
                        return f"(or {' '.join(community_conditions)})"
                else:
                    # No communities defined - return None
                    return None
            else:
                # Normal mode: return community variables (all false)
                community_vars = {}
                for community in sorted(self.exact_communities):
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                    community_vars[var_name] = "false"
                return community_vars
        elif num_carried == 1:
            # One community: simple format - one = true, others = false
            if negated_mode:
                # Negated: (or (not (= comm1 true)) (not (= comm2 false)) ...)
                community_conditions = []
                # Negate the true community
                for comm in sorted(carried_communities_set):
                    comm_var = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                    community_conditions.append(f"(not (= {comm_var} true))")
                # Negate all false communities
                for comm in sorted(self.exact_communities):
                    if comm not in carried_communities_set:
                        comm_var = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                        community_conditions.append(f"(not (= {comm_var} false))")
                
                if len(community_conditions) == 1:
                    return community_conditions[0]
                else:
                    return f"(or {' '.join(community_conditions)})"
            else:
                # Normal mode: return simple dictionary format
                community_vars = {}
                # The one carried community = true
                for comm in sorted(carried_communities_set):
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                    community_vars[var_name] = "true"
                # All other communities = false
                for comm in sorted(self.exact_communities):
                    if comm not in carried_communities_set:
                        var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                        community_vars[var_name] = "false"
                return community_vars
        else:
            # Multiple communities: same format as one community - direct variable assignments (no AND constraint)
            if negated_mode:
                # Negated: (or (not (= comm1 true)) (not (= comm2 true)) (not (= comm3 false)) ...)
                community_conditions = []
                for comm in sorted(carried_communities_set):
                    comm_var = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                    community_conditions.append(f"(not (= {comm_var} true))")
                for comm in sorted(self.exact_communities):
                    if comm not in carried_communities_set:
                        comm_var = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                        community_conditions.append(f"(not (= {comm_var} false))")
                if len(community_conditions) == 1:
                    return community_conditions[0]
                return f"(or {' '.join(community_conditions)})"
            else:
                # Normal mode: direct assignments, same as one-community case
                community_vars = {}
                for comm in sorted(carried_communities_set):
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                    community_vars[var_name] = "true"
                for comm in sorted(self.exact_communities):
                    if comm not in carried_communities_set:
                        var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                        community_vars[var_name] = "false"
                return community_vars
    
    def _handle_community_case_3(self, device: str, unique_communities: List[str], negated_mode: bool = False) -> Union[Dict[str, str], str]:
        """Case 3: ECMP routes with different communities
        
        Normal: multiple communities can be true or false (with OR constraint)
        Note: Cannot use direct assignment because ECMP paths may come from different peers.
        Current limitation: Uses per-community (or (= var true) (= var false)) constraints which
        is less precise than ideal. Future enhancement could track specific ECMP path-to-community
        mappings for more precise encoding.
        Negated: (or (and (not (= comm_i true)) ... (not (= comm_j true))) (not (= comm_k false)) ...) - returns constraint without metric
        """
        if negated_mode:
            # Case 3: All routes have communities, but they are different
            # Negated: all true communities must be false, AND all false communities must not be false
            true_community_conditions = []
            for community in unique_communities:
                var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                true_community_conditions.append(f"(not (= {var_name} true))")
            
            # Add all false communities (other communities not in unique_communities)
            false_community_conditions = []
            for community in sorted(self.exact_communities):
                if community not in unique_communities:
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                    false_community_conditions.append(f"(not (= {var_name} false))")
            
            # Combine all conditions (without metric): AND of true communities, OR of false communities
            all_conditions = []
            if true_community_conditions:
                all_conditions.append(f"(and {' '.join(true_community_conditions)})")
            all_conditions.extend(false_community_conditions)
            
            # If no conditions, return None (should not happen in practice)
            if not all_conditions:
                return None
            
            # If only one condition, return it directly (no need for outer OR)
            if len(all_conditions) == 1:
                return all_conditions[0]
            
            return f"(or {' '.join(all_conditions)})"
        else:
            # Normal mode: return community variables
            # Note: Cannot use direct assignment (all unique communities = true) because
            # ECMP paths may come from different peers, and we cannot guarantee all communities
            # are present simultaneously. Each community variable must allow both true and false.
            # 
            # TODO/Future Enhancement: The current implementation uses (or (= var true) (= var false))
            # constraints for each community, which is less precise than ideal. In the future, we could
            # extend this to track which specific ECMP path carries which community, allowing for more
            # precise encoding. This would require additional variables to represent the mapping between
            # ECMP paths and their communities.
            community_vars = {}
            for community in unique_communities:
                var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                community_vars[var_name] = f"(or (= {var_name} true) (= {var_name} false))"
            
            # Add overall OR constraint: at least one community must be true
            # This is required because all routes have communities, so at least one path
            # will carry one of these communities
            community_vars_list = [self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{comm}")
                                 for comm in unique_communities]
            # Format: (or (= var1 true) (= var2 true) ...) for explicit comparison
            interface_conditions = [f"(= {var} true)" for var in community_vars_list]
            community_vars['_overall_or_constraint'] = f"(or {' '.join(interface_conditions)})"
            
            # Set all non-involved communities to false
            for community in sorted(self.exact_communities):
                if community not in unique_communities:
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                    community_vars[var_name] = "false"
            
            return community_vars
    
    def _handle_community_case_4(self, device: str, unique_communities: List[str], negated_mode: bool = False) -> Union[Dict[str, str], str]:
        """Case 4: ECMP routes with some having communities
        
        Normal: some communities can be true or false, others = false
        Negated: (or (not (= comm_k false)) ...) - returns constraint without metric
        """
        if negated_mode:
            # Case 4: Some routes have communities, some don't
            # Negated: all false communities must not be false (i.e., must be true)
            community_conditions = []
            for community in sorted(self.exact_communities):
                if community not in unique_communities:
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                    community_conditions.append(f"(not (= {var_name} false))")
            if len(community_conditions) == 1:
                return community_conditions[0]
            else:
                return f"(or {' '.join(community_conditions)})"
        else:
            # Normal mode: return community variables
            community_vars = {}
            for community in unique_communities:
                var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                community_vars[var_name] = f"(or (= {var_name} true) (= {var_name} false))"
            
            # No overall OR constraint since some routes have no communities
            
            # Set all non-involved communities to false
            for community in sorted(self.exact_communities):
                if community not in unique_communities:
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                    community_vars[var_name] = "false"
            
            return community_vars
    
    def _handle_community_case_5(self, device: str, negated_mode: bool = False) -> Union[Dict[str, str], Optional[str]]:
        """Case 5: ECMP routes with no communities - all communities false
        
        Normal: all communities = false
        Negated 5A: (or (not (= comm_1 false)) ...) [with communities defined] - returns constraint without metric
        Negated 5B: None [without communities defined] - no community constraint, only metric constraint needed
        """
        if negated_mode:
            if self.exact_communities:
                # Case 5A: With communities defined
                community_conditions = []
                for community in sorted(self.exact_communities):
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                    community_conditions.append(f"(not (= {var_name} false))")
                if len(community_conditions) == 1:
                    return community_conditions[0]
                else:
                    return f"(or {' '.join(community_conditions)})"
            else:
                # Case 5B: Without communities defined - return None, caller will handle metric only
                return None
        else:
            # Normal mode: return community variables
            community_vars = {}
            for community in sorted(self.exact_communities):
                var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                community_vars[var_name] = "false"
            return community_vars
    
    def _handle_community_case_6(self, device: str, carried_community: str, negated_mode: bool = False) -> Union[Dict[str, str], str]:
        """Case 6: ECMP routes with identical communities
        
        Normal: one community = true, others = false
        Negated: (or (not (= comm_i true)) (not (= comm_1 false)) ...) - returns constraint without metric
        
        Note: This function is kept for backward compatibility but is now handled by _handle_community_case_2
        """
        # Delegate to Case 2 (ECMP) handler
        # Convert single community to list format: [[carried_community]]
        return self._handle_community_case_2(device, [[carried_community]], negated_mode)
    
    def _handle_community_case_2(self, device: str, unique_community_lists: List[List[str]], negated_mode: bool = False) -> Union[Dict[str, str], str]:
        """Case 2: ECMP routes (multiple routes)
        
        ECMP community handling with support for multiple communities per route:
        - Each ECMP route can carry zero, one, or multiple communities
        - Deduplicate routes with identical community combinations
        - For each unique combination, generate AND constraint (like Case 1)
        - Combine all combinations with OR constraint
        
        Normal mode:
        (or 
            (and (comm1 = true) (comm2 = true) ... (other communities = false))  [for route1]
            (and (comm1 = true) (comm3 = true) ... (other communities = false))  [for route2]
            ...
            (and (all communities = false))  [for routes without communities]
        )
        
        Negated mode:
        (not 
            (or 
                (and (comm1 = true) (comm2 = true) ... (other communities = false))
                (and (comm1 = true) (comm3 = true) ... (other communities = false))
                ...
                (and (all communities = false))
            )
        )
        
        Args:
            device: Device hostname
            unique_community_lists: List of unique community combinations, each is a list of communities
                                   (empty list [] represents no communities)
            negated_mode: Whether to generate negated constraint
        
        Returns:
            If negated_mode=False: Dict[str, str] with '_overall_or_constraint' key
            If negated_mode=True: str - negated constraint SMT string
        """
        # Build OR constraint from all unique community combinations
        or_conditions = []
        
        # For each unique community combination, generate AND constraint (like Case 1)
        for carried_communities in unique_community_lists:
            # Convert to set for easier lookup
            carried_communities_set = set(carried_communities)
            
            # Build AND conditions for this combination
            and_conditions = []
            
            # All carried communities must be true
            for community in sorted(carried_communities_set):
                var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                and_conditions.append(f"(= {var_name} true)")
            
            # All other communities must be false
            for community in sorted(self.exact_communities):
                if community not in carried_communities_set:
                    var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
                    and_conditions.append(f"(= {var_name} false)")
            
            # Create AND clause for this combination
            if len(and_conditions) == 1:
                or_conditions.append(and_conditions[0])
            else:
                or_conditions.append(f"(and {' '.join(and_conditions)})")
        
        # Build the overall OR constraint
        if len(or_conditions) == 0:
            # No conditions - should not happen, but return None
            if negated_mode:
                return None
            else:
                return {}
        elif len(or_conditions) == 1:
            overall_or = or_conditions[0]
        else:
            overall_or = f"(or {' '.join(or_conditions)})"
        
        if negated_mode:
            # Negated mode: NOT(OR(...))
            return f"(not {overall_or})"
        else:
            # Normal mode: return with _overall_or_constraint key
            community_vars = {}
            community_vars['_overall_or_constraint'] = overall_or
            return community_vars
    
    def generate_community_variables_for_no_routes(self, device: str) -> Dict[str, str]:
        """Generate community SMT variables for devices with no routes"""
        community_vars = {}
        
        # Case c: 0 个最佳路由 - 所有 exact community 都设置为 false
        for community in sorted(self.exact_communities):
            var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{community}")
            community_vars[var_name] = "false"
        
        # Handle other-communities from 0_regex_communities.txt (only _OTHER suffix)
        for other_comm in sorted(self.all_communities):
            # Only process communities with _OTHER suffix
            if other_comm.endswith('_OTHER'):
                # Generate other-community variable
                var_name = self._host._smt_var_name(f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community_{other_comm}")
                community_vars[var_name] = "false"
        
        return community_vars

    def log_load_summary(self) -> None:
        logger.info(
            f"  -> Found {len(self.exact_communities)} unique communities: "
            f"{sorted(self.exact_communities)}"
        )
