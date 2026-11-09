#!/usr/bin/env python3
"""BitVec (single variable) OVERALL_BEST community encoding for RouteAnalyzer."""

from __future__ import annotations

import logging
import sys
from typing import Dict, List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    Route = Any

logger = logging.getLogger(__name__)

OVERALL_BEST_PREFIX = "OVERALL_BEST"
COMMUNITIES_INDEX_FILE = "0_communities_index.txt"


class BitVecCommunityEncoder:
    """One BitVecExpr: single |..._OVERALL_BEST_None_community| with bit-set encoding."""

    def __init__(self, host) -> None:
        self._host = host
        self.community_bit_width: int = 0
        self.community_to_index: Dict[str, int] = {}

    def load(self) -> None:
        """Load community BitVec index from 0_communities_index.txt."""
        index_file = self._host.work_dir / COMMUNITIES_INDEX_FILE
        if not index_file.exists():
            logger.info(f"No communities index file found at {index_file}, skipping")
            return

        logger.info(f"Loading communities index from {index_file}")
        with open(index_file, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        if not lines:
            logger.warning(f"Communities index file {index_file} is empty")
            return

        try:
            self.community_bit_width = int(lines[0])
        except ValueError as e:
            logger.error(f"Invalid bit width in {index_file}: {lines[0]} - {e}")
            sys.exit(1)

        self.community_to_index = {}
        for line_num, line in enumerate(lines[1:], 2):
            if ':' not in line:
                logger.warning(f"Skipping malformed communities index line {line_num}: {line}")
                continue
            community_part, index_part = line.rsplit(':', 1)
            community = community_part.strip()
            try:
                index = int(index_part.strip())
            except ValueError:
                logger.warning(f"Skipping malformed communities index line {line_num}: {line}")
                continue
            if community in self.community_to_index:
                logger.warning(f"Duplicate community '{community}' in {index_file}, keeping first index")
                continue
            if index < 0 or index >= self.community_bit_width:
                logger.warning(
                    f"Community index {index} for '{community}' out of range [0, {self.community_bit_width})"
                )
            self.community_to_index[community] = index

        logger.info(
            f"Loaded communities index: width={self.community_bit_width}, "
            f"{len(self.community_to_index)} entries"
        )

    def log_load_summary(self) -> None:
        logger.info(
            f"  -> Communities index: width={self.community_bit_width}, "
            f"{len(self.community_to_index)} entries"
        )

    def _community_var_name(self, device: str) -> str:
        return self._host._smt_var_name(
            f"{self._host.smt_var_prefix}{device}_{OVERALL_BEST_PREFIX}_None_community"
        )

    def _zero_community_bitvec(self) -> str:
        if self.community_bit_width <= 0:
            return "#b0"
        return f"#b{'0' * self.community_bit_width}"

    def _communities_to_bitvec(self, communities: List[str]) -> str:
        if self.community_bit_width <= 0:
            return "#b0"
        value = 0
        for comm in communities:
            index = self.community_to_index.get(comm)
            if index is None:
                logger.warning(f"Community '{comm}' not found in communities index, skipping")
                continue
            value |= (1 << index)
        binary_str = format(value, f'0{self.community_bit_width}b')
        return f"#b{binary_str}"

    def generate_community_variables(
        self, device: str, ecmp_routes: List[Route], negated_mode: bool = False
    ) -> Union[Dict[str, str], str, None]:
        """Generate community SMT variables or negated constraints (single BitVec per device)."""
        if not self.community_to_index:
            if negated_mode:
                return None
            return {}

        var_name = self._community_var_name(device)
        zero_bv = self._zero_community_bitvec()

        if len(ecmp_routes) == 0:
            if negated_mode:
                return f"(not (= {var_name} {zero_bv}))"
            return {var_name: zero_bv}

        all_bgp_routes = (
            self._host.get_all_bgp_info(device, ecmp_routes[0].network) if ecmp_routes else []
        )

        if len(ecmp_routes) == 1:
            single_bgp_route = all_bgp_routes[0] if all_bgp_routes else None
            carried_communities = (
                single_bgp_route.communities if (single_bgp_route and single_bgp_route.communities) else []
            )
            bitvec = self._communities_to_bitvec(carried_communities)
            if negated_mode:
                return f"(not (= {var_name} {bitvec}))"
            return {var_name: bitvec}

        ecmp_route_community_combinations = []
        for bgp_route in all_bgp_routes:
            if bgp_route.communities:
                ecmp_route_community_combinations.append(tuple(sorted(bgp_route.communities)))
            else:
                ecmp_route_community_combinations.append(tuple())

        unique_community_lists = [list(combo) for combo in set(ecmp_route_community_combinations)]
        or_conditions = [
            f"(= {var_name} {self._communities_to_bitvec(comm_list)})"
            for comm_list in unique_community_lists
        ]

        if negated_mode:
            if len(or_conditions) == 1:
                return f"(not {or_conditions[0]})"
            return f"(not (or {' '.join(or_conditions)}))"

        if len(or_conditions) == 1:
            return {var_name: self._communities_to_bitvec(unique_community_lists[0])}
        return {'_overall_or_constraint': f"(or {' '.join(or_conditions)})"}

    def generate_community_variables_for_no_routes(self, device: str) -> Dict[str, str]:
        if not self.community_to_index:
            return {}
        return {self._community_var_name(device): self._zero_community_bitvec()}
