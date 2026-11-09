#!/usr/bin/env python3
"""
Route Analysis Tool for Network Verification Explanation - Version 3.0

This tool analyzes dataplane.txt and bgpv4route.txt to find the best routes
for a given destination IP and converts them to SMT variable format for
config-level subspec generation.

Key Features:
- Multi-protocol route analysis (connected, static, BGP)
- ECMP (Equal Cost Multi-Path) support
- BGP communities processing
- Control plane stable state generation
- Device-level constraint extraction
- Normal and negated stable states

Author: Network Verification Team
Version: 3.0
"""

import re
import os
import sys
import logging
import ipaddress
from typing import List, Dict, Tuple, Optional, Set, Union
from dataclasses import dataclass
from collections import defaultdict
from pathlib import Path

# Import logging utilities
from utils.util_log import verbose_info
# Import loading and saving utilities
from utils.util_file import load_model_igp
# Import community encoder utilities
from utils.util_route_community_bool import BoolCommunityEncoder
from utils.util_route_community_bitvec import BitVecCommunityEncoder

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

##########################################################################################
### Configuration Constants
##########################################################################################

class Config:
    """Configuration constants for route analysis"""
    
    # Administrative Distance values
    AD_CONNECTED = 0
    AD_STATIC = 1
    AD_BGP = 20
    
    # File names
    DATAPLANE_FILE = "0_data_plane.txt"
    BGP_ROUTES_FILE = "0_ebgp_routes.txt"
    DST_IP_FILE = "0_dst_ips.txt"
    BGP_NEIGHBORS_FILE = "0_ebgp_neighbors.txt"
    HISTORY_ENUM_FILE = "0_overall_history_enum.txt"
    INTERFACES_FILE = "0_interfaces.txt"
    
    # SMT variable prefixes
    CONTROL_FORWARDING_PREFIX = "CONTROL-FORWARDING"
    OVERALL_BEST_PREFIX = "OVERALL_BEST"
    

##########################################################################################
### Data Models
##########################################################################################

@dataclass
class Route:
    """Represents a single route entry from dataplane.txt"""
    node: str
    vrf: str
    network: str
    protocol: str
    nexthop_ip: str
    nexthop_interface: str
    nexthop: str
    metric: int
    ad: int
    tag: str
    
    @property
    def prefix_length(self) -> int:
        """Extract prefix length from network CIDR notation"""
        if '/' in self.network:
            return int(self.network.split('/')[1])
        return 32  # Default to /32 if no prefix length specified

@dataclass
class BgpRoute:
    """Represents BGP route information from bgpv4route.txt"""
    node: str
    vrf: str
    network: str
    aspath: List[int]
    communities: List[str]
    local_pref: Optional[int] = None
    med: Optional[int] = None
    
    @property
    def aspath_length(self) -> int:
        """Get AS path length"""
        return len(self.aspath)

##########################################################################################
### Main Route Analyzer Class
##########################################################################################

class RouteAnalyzer:
    """Main class for analyzing routes and generating SMT variables"""
    
    def __init__(self, work_dir: str):
        """
        Initialize RouteAnalyzer with working directory
        
        Args:
            work_dir: Path to directory containing input files
        """
        self.work_dir = Path(work_dir)
        # When model_igp=1, generated SMT variables use prefix 0_SLICE-MAIN_ (i.e. 0_xxx -> 0_SLICE-MAIN_xxx)
        self.model_igp = load_model_igp(self.work_dir)
        self.smt_var_prefix = "0_SLICE-MAIN_" if self.model_igp else "0_"
        self.routes: List[Route] = []
        self.bgp_routes: Dict[str, List[BgpRoute]] = defaultdict(list)
        self.bgp_neighbors: Dict[str, str] = {}
        self.ebgp_neighbor_as: Dict[str, int] = {}  # key "device_neighbor" -> neighbor's AS number (for BGP loop prevention)
        self.device_as: Dict[str, int] = {}  # device -> AS number (inferred from 0_ebgp_neighbors.txt)
        self.dst_ips: List[str] = []
        self.unused_control_forwarding: Set[str] = set()
        self.history_enums: Dict[str, Dict[str, Optional[int]]] = {}  # device -> {BGP: value, CONNECTED: value, STATIC: value}
        self.history_bit_widths: Dict[str, int] = {}  # device -> bit width (1 or 2)
        self.device_interfaces: Dict[str, Set[str]] = {}  # device -> set of interfaces from 0_interfaces.txt

        # Community encoding modules (active: BitVec; Bool kept for legacy)
        self.bool_community_encoder = BoolCommunityEncoder(self)
        self.bitvec_community_encoder = BitVecCommunityEncoder(self)
        self.community_encoder = self.bitvec_community_encoder
        
        # Validate input files
        self._validate_input_files()

    @staticmethod
    def _is_bgp_family(protocol: str) -> bool:
        """True for BGP-family protocols present in 0_data_plane.txt."""
        return protocol.lower() in {"bgp", "ibgp"}

    @staticmethod
    def _consume_bracket_field(parts: List[str], start: int) -> Tuple[Optional[str], int]:
        """Consume tokens forming [...] at parts[start]. Returns inner text and index after the field."""
        if start >= len(parts) or not parts[start].startswith('['):
            return None, start
        bracket_parts: List[str] = []
        i = start
        while i < len(parts):
            bracket_parts.append(parts[i])
            if parts[i].endswith(']'):
                i += 1
                break
            i += 1
        raw = ' '.join(bracket_parts)
        if raw.startswith('[') and raw.endswith(']'):
            return raw[1:-1].strip(), i
        return None, start
    
    def _escape_smt_inner(self, inner: str) -> str:
        """Escape any | in the inner part of an SMT variable name as \\|."""
        return inner.replace('|', '\\|')
    
    def _smt_var_name(self, inner: str) -> str:
        """Build full SMT variable name |inner| with internal | escaped as \\|."""
        return f"|{self._escape_smt_inner(inner)}|"

    def _load_unused_control_forwarding(self) -> None:
        """Load unused control forwarding variables from 0_unused_control_forwarding.txt file"""
        unused_file = self.work_dir / "0_unused_control_forwarding.txt"
        if not unused_file.exists():
            logger.info("No unused control forwarding file found, skipping unused control forwarding loading")
            return
        
        logger.info(f"Loading unused control forwarding variables from {unused_file}")
        with open(unused_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # The line already contains the | symbols, so use it directly
                var_name = line.strip()
                self.unused_control_forwarding.add(var_name)
        
        logger.info(f"Loaded {len(self.unused_control_forwarding)} unused control forwarding variables")
        logger.info(f"Extracted {len(self.unused_control_forwarding)} unused control forwarding: {sorted(self.unused_control_forwarding)}")
    
    def _load_interfaces(self) -> None:
        """Load device,interface pairs from 0_interfaces.txt. Format: one line per 'device,interface'."""
        interfaces_file = self.work_dir / Config.INTERFACES_FILE
        logger.info(f"Loading interfaces from {interfaces_file}")
        with open(interfaces_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ',' not in line:
                    logger.warning(f"Skip line {line_num}: expected 'device,interface': {line}")
                    continue
                device, interface = line.split(',', 1)
                device = device.strip()
                interface = interface.strip()
                if device and interface:
                    self.device_interfaces.setdefault(device, set()).add(interface)
        logger.info(f"Loaded interfaces for {len(self.device_interfaces)} devices")
    
    def _load_history_enums(self) -> None:
        """Load history enum values from 0_overall_history_enum.txt file
        
        File format:
        |0_{device}_OVERALL_BEST_None_history| (bit_width)
            BGP : value
            IBGP : value
            CONNECTED : value
            STATIC : value
        
        If bit_width is (0), the device is ignored.
        If a protocol value is null, that protocol will not have a history variable.
        
        Note: This file is required. If it doesn't exist, validation will fail.
        """
        history_file = self.work_dir / Config.HISTORY_ENUM_FILE
        
        logger.info(f"Loading history enums from {history_file}")
        current_device = None
        current_enum = {}
        current_bit_width = None
        
        with open(history_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Check if this is a variable name (starts with |)
                if line.startswith('|') and '_OVERALL_BEST_None_history|' in line:
                    # Save previous device's enum if exists and bit_width > 0
                    if current_device and current_enum and current_bit_width and current_bit_width > 0:
                        self.history_enums[current_device] = current_enum
                        self.history_bit_widths[current_device] = current_bit_width
                    
                    # Extract device name and bit width from variable
                    # Format: |0_{device}_OVERALL_BEST_None_history| or |0_SLICE-MAIN_{device}_OVERALL_BEST_None_history| (bit_width)
                    var_name = line
                    device_part = var_name.replace('|0_', '').replace('|0_SLICE-MAIN_', '').replace('_OVERALL_BEST_None_history|', '').strip()
                    if device_part.startswith('SLICE-MAIN_'):
                        device_part = device_part[len('SLICE-MAIN_'):]
                    
                    # Extract bit width from parentheses: (0), (1), (2)
                    bit_width_match = re.search(r'\((\d+)\)', var_name)
                    if bit_width_match:
                        current_bit_width = int(bit_width_match.group(1))
                        # Extract device name (remove the bit width part)
                        device_part = var_name.split('(')[0].replace('|0_', '').replace('|0_SLICE-MAIN_', '').replace('_OVERALL_BEST_None_history|', '').strip()
                        if device_part.startswith('SLICE-MAIN_'):
                            device_part = device_part[len('SLICE-MAIN_'):]
                    else:
                        current_bit_width = None
                    
                    # Only process if bit_width > 0
                    if current_bit_width and current_bit_width > 0:
                        current_device = device_part
                        current_enum = {}
                    else:
                        # Skip devices with bit_width = 0
                        current_device = None
                        current_enum = {}
                elif current_device and current_bit_width and current_bit_width > 0:
                    # Parse enum value: "BGP : 0" or "BGP : null"
                    if ':' in line:
                        parts = line.split(':')
                        if len(parts) == 2:
                            protocol = parts[0].strip()
                            value_str = parts[1].strip()
                            
                            if value_str.lower() == 'null':
                                current_enum[protocol] = None
                            else:
                                try:
                                    current_enum[protocol] = int(value_str)
                                except ValueError:
                                    logger.warning(f"Invalid history enum value at line {line_num}: {line}")
        
        # Save last device's enum if bit_width > 0
        if current_device and current_enum and current_bit_width and current_bit_width > 0:
            self.history_enums[current_device] = current_enum
            self.history_bit_widths[current_device] = current_bit_width
        
        logger.info(f"Loaded history enums for {len(self.history_enums)} devices: {list(self.history_enums.keys())}")
        logger.info(f"Loaded history bit widths: {dict(self.history_bit_widths)}")
    
    def _load_history_bit_widths(self) -> None:
        """Load history bit widths from 0_overall_history_enum.txt file
        
        This method is now integrated into _load_history_enums().
        Bit widths are extracted directly from the enum file format: |0_{device}_OVERALL_BEST_None_history| (bit_width)
        """
        # Bit widths are now loaded in _load_history_enums() along with enum values
        # This method is kept for backward compatibility but does nothing
        pass
    
    def _get_history_value(self, device: str, protocol: str) -> Optional[str]:
        """
        Get history value for a device and protocol, formatted as binary string
        
        Args:
            device: Device hostname
            protocol: Protocol name (BGP, CONNECTED, STATIC)
            
        Returns:
            Formatted history value (e.g., "#b00", "#b01", "#b1") or None if not found
        """
        # Get enum value for this device and protocol
        enum_value = None
        if device in self.history_enums:
            protocol_upper = protocol.upper()
            if protocol_upper in self.history_enums[device]:
                enum_value = self.history_enums[device][protocol_upper]
        
        # If enum value is None (null in enum file), return None
        if enum_value is None:
            return None
        
        # Get bit width for this device
        bit_width = self.history_bit_widths.get(device, 2)  # Default to 2 if not found
        
        # Format as binary string
        binary_str = format(enum_value, f'0{bit_width}b')
        return f"#b{binary_str}"
    
    def _validate_input_files(self) -> None:
        """Validate that all required input files exist.

        Required files: 0_data_plane.txt, 0_ebgp_routes.txt, 0_dst_ips.txt,
        0_ebgp_neighbors.txt, 0_overall_history_enum.txt, 0_interfaces.txt.
        Missing any of these causes exit(1).
        """
        required_files = [
            Config.DATAPLANE_FILE,
            Config.BGP_ROUTES_FILE,
            Config.DST_IP_FILE,
            Config.BGP_NEIGHBORS_FILE,
            Config.HISTORY_ENUM_FILE,
            Config.INTERFACES_FILE,
        ]
        
        missing_files = []
        for file_name in required_files:
            file_path = self.work_dir / file_name
            if not file_path.exists():
                missing_files.append(file_name)
        
        if missing_files:
            logger.error(f"Missing required files: {', '.join(missing_files)}")
            sys.exit(1)
        
        logger.info("All required files found in " + str(self.work_dir))
    
    def _load_all_data(self) -> None:
        """Load all input data files"""
        logger.info("Step 1: Loading input data files...")
        
        self._load_dataplane()
        self.community_encoder.load()
        self._load_bgp_routes()
        self._load_destination_ips()
        self._load_bgp_neighbors()
        self._load_unused_control_forwarding()
        self._load_history_enums()  # Load history enum values and bit widths from enum file
        self._load_interfaces()
        
        logger.info(f"  -> Loaded {len(self.routes)} routes")
        logger.info(f"  -> Loaded {sum(len(routes) for routes in self.bgp_routes.values())} BGP routes")
        logger.info(f"  -> Loaded {len(self.dst_ips)} destination IPs: {self.dst_ips}")
        logger.info(f"  -> Loaded {len(self.bgp_neighbors)} BGP neighbor mappings")
        logger.info(f"  -> Loaded history enums for {len(self.history_enums)} devices")
        self.community_encoder.log_load_summary()
        logger.info("  -> All data loaded successfully")
    
    def _load_dataplane(self) -> None:
        """Load dataplane.txt file"""
        dataplane_file = self.work_dir / Config.DATAPLANE_FILE
        logger.info(f"Loading dataplane from {dataplane_file}")
        
        with open(dataplane_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Skip header lines
                if 'Node' in line and 'VRF' in line:
                    continue
                if '=' in line and len(line) > 50:  # Skip separator lines
                    continue
                
                parts = line.split()
                if len(parts) < 10:
                    logger.warning(f"Error parsing line {line_num}: {line} - insufficient fields")
                    continue
                
                try:
                    route = Route(
                        node=parts[0],
                        vrf=parts[1],
                        network=parts[2],
                        protocol=parts[3],
                        nexthop_ip=parts[4],
                        nexthop_interface=parts[5],
                        nexthop=parts[6],
                        metric=int(parts[7]),
                        ad=int(parts[8]),
                        tag=parts[9]
                    )
                    self.routes.append(route)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing line {line_num}: {line} - {e}")
                    continue
    
    def _load_bgp_routes(self) -> None:
        """Load BGP routes from bgpv4route.txt file"""
        bgp_file = self.work_dir / Config.BGP_ROUTES_FILE
        logger.info(f"Loading BGP routes from {bgp_file}")
        
        with open(bgp_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Skip header lines
                if 'Node' in line and 'VRF' in line:
                    continue
                if '=' in line and len(line) > 50:  # Skip separator lines
                    continue
                
                parts = line.split()
                if len(parts) < 4:
                    logger.warning(f"Error parsing BGP line {line_num}: {line} - insufficient fields")
                    continue
                
                try:
                    node = parts[0]
                    vrf = parts[1]
                    network = parts[2]
                    
                    # Parse AS path (handle spaces in brackets)
                    # AS path might be split across multiple parts due to spaces
                    aspath_parts = []
                    i = 3
                    while i < len(parts) and not parts[i].startswith('['):
                        i += 1
                    
                    # Collect all AS path parts until we find the closing bracket
                    while i < len(parts):
                        aspath_parts.append(parts[i])
                        if parts[i].endswith(']'):
                            break
                        i += 1
                    aspath_end_idx = i
                    
                    # Join and parse AS path
                    aspath_str = ' '.join(aspath_parts)
                    if aspath_str.startswith('[') and aspath_str.endswith(']'):
                        aspath_str = aspath_str[1:-1]  # Remove brackets
                        if aspath_str.strip():
                            aspath = [int(x.strip()) for x in aspath_str.split(',')]
                        else:
                            aspath = []
                    else:
                        aspath = []

                    # Remaining fields: Communities [..], Localpreference, Med
                    idx = aspath_end_idx + 1
                    communities: List[str] = []
                    comm_inner, idx = self._consume_bracket_field(parts, idx)
                    if comm_inner:
                        for comm_item in comm_inner.split(','):
                            comm_item = comm_item.strip()
                            if comm_item and ':' in comm_item:
                                communities.append(comm_item)

                    local_pref: Optional[int] = None
                    med: Optional[int] = None
                    numeric_tail: List[int] = []
                    while idx < len(parts):
                        if re.fullmatch(r'-?\d+', parts[idx]):
                            numeric_tail.append(int(parts[idx]))
                        idx += 1
                    if len(numeric_tail) >= 2:
                        local_pref = numeric_tail[-2]
                        med = numeric_tail[-1]
                    elif len(numeric_tail) == 1:
                        med = numeric_tail[0]
                    
                    bgp_route = BgpRoute(
                        node=node,
                        vrf=vrf,
                        network=network,
                        aspath=aspath,
                        communities=communities,
                        local_pref=local_pref,
                        med=med,
                    )
                    
                    key = f"{node}_{network}"
                    self.bgp_routes[key].append(bgp_route)
                    
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing BGP line {line_num}: {line} - {e}")
                    continue
    
    def _load_destination_ips(self) -> None:
        """Load destination IPs from dst-ip.txt file"""
        dst_file = self.work_dir / Config.DST_IP_FILE
        logger.info(f"Loading destination IPs from {dst_file}")
        
        with open(dst_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    self.dst_ips.append(line)
        
        logger.info(f"Loaded {len(self.dst_ips)} destination IPs: {self.dst_ips}")

    def _get_max_dst_prefix_length(self) -> int:
        """Max prefix length from 0_dst_ips.txt entries (host-only -> /32)."""
        if not self.dst_ips:
            return 32
        max_pl = 0
        for dst_ip in self.dst_ips:
            try:
                if '/' in dst_ip:
                    pl = ipaddress.ip_network(dst_ip, strict=False).prefixlen
                else:
                    pl = 32
                max_pl = max(max_pl, pl)
            except ValueError as e:
                logger.warning(f"Could not parse dst IP prefix length from {dst_ip!r}: {e}")
        return max_pl if max_pl > 0 else 32

    def _prefix_length_bound_asserts(self, device: str) -> List[str]:
        """Bounds for OVERALL_BEST prefixLength from 0_dst_ips.txt (not equality to best route)."""
        max_pl = self._get_max_dst_prefix_length()
        var = self._smt_var_name(
            f"{self.smt_var_prefix}{device}_{Config.OVERALL_BEST_PREFIX}_None_prefixLength"
        )
        return [
            f"(assert (<= {var} {max_pl}))",
            f"(assert (>= {var} 0))",
        ]
    
    def _load_bgp_neighbors(self) -> None:
        """Load BGP neighbors from bgpneighbors.txt file"""
        bgp_neighbors_file = self.work_dir / Config.BGP_NEIGHBORS_FILE
        if not bgp_neighbors_file.exists():
            logger.warning(f"BGP neighbors file not found: {bgp_neighbors_file}")
            return
        
        logger.info(f"Loading BGP neighbors from {bgp_neighbors_file}")
        
        with open(bgp_neighbors_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or '->' not in line:
                    continue
                
                try:
                    parts = line.split('->')
                    left_part = parts[0].strip()
                    right_part = parts[1].strip()
                    
                    # Parse left side: "device,interface (asn)"
                    left_device = left_part.split(',')[0].strip()
                    left_rest = left_part.split(',')[1].strip()
                    left_interface = left_rest.split('(')[0].strip()
                    left_as = int(left_rest.split('(')[1].split(')')[0].strip()) if '(' in left_rest and ')' in left_rest else None
                    
                    # Parse right side: "device,interface (asn)"
                    right_device = right_part.split(',')[0].strip()
                    right_rest = right_part.split(',')[1].strip()
                    right_interface = right_rest.split('(')[0].strip()
                    right_as = int(right_rest.split('(')[1].split(')')[0].strip()) if '(' in right_rest and ')' in right_rest else None
                    
                    # Store bidirectional mapping
                    self.bgp_neighbors[f"{left_device}_{right_device}"] = left_interface
                    self.bgp_neighbors[f"{right_device}_{left_device}"] = right_interface
                    # Store each device's AS (best-effort; used to infer iBGP vs eBGP)
                    if left_as is not None:
                        self.device_as.setdefault(left_device, left_as)
                    if right_as is not None:
                        self.device_as.setdefault(right_device, right_as)
                    # Store neighbor AS for BGP loop prevention (neighbor's AS number from device's perspective)
                    if right_as is not None:
                        self.ebgp_neighbor_as[f"{left_device}_{right_device}"] = right_as
                    if left_as is not None:
                        self.ebgp_neighbor_as[f"{right_device}_{left_device}"] = left_as
                    
                except Exception as e:
                    logger.warning(f"Error parsing BGP neighbor line: {line} - {e}")
                    continue
        
        logger.info(f"Loaded {len(self.bgp_neighbors)} BGP neighbor mappings")
    
    def get_bgp_info(self, device: str, network: str) -> Optional[BgpRoute]:
        """Get BGP route information for a device and network (first match)"""
        bgp_routes = self.get_all_bgp_info(device, network)
        return bgp_routes[0] if bgp_routes else None
    
    def get_all_bgp_info(self, device: str, network: str) -> List[BgpRoute]:
        """Get all BGP route information for a device and network"""
        key = f"{device}_{network}"
        return self.bgp_routes.get(key, [])
    
    def get_bgp_interface(self, device: str, peer_hostname: str) -> Optional[str]:
        """Get the local interface for a BGP peer"""
        key = f"{device}_{peer_hostname}"
        return self.bgp_neighbors.get(key)
    
    def get_ebgp_neighbor_names(self, device: str) -> List[str]:
        """Get list of eBGP neighbor device names for a device (keys device_* in bgp_neighbors)."""
        prefix = f"{device}_"
        return [key[len(prefix):] for key in self.bgp_neighbors if key.startswith(prefix)]
    
    def get_ebgp_neighbor_as(self, device: str, neighbor: str) -> Optional[int]:
        """Get neighbor's AS number for BGP loop prevention. Returns None if not available."""
        key = f"{device}_{neighbor}"
        return self.ebgp_neighbor_as.get(key)
    
    def _compute_route_from_for_device_dst(self, device: str, ecmp_routes: List[Route]) -> List[str]:
        """Compute 'route from: neighbor' for BGP loop prevention.
        
        Only when device has a BGP best route for the destination: if a neighbor's AS
        appears in the route's AS-path, the route is considered to have come from that neighbor.
        Returns list of neighbor device names to be written as 'route from: neighbor'.
        """
        result = []
        if not ecmp_routes:
            return result
        route = ecmp_routes[0]
        if route.protocol.lower() != 'bgp':
            return result
        bgp_info = self.get_bgp_info(device, route.network)
        if not bgp_info or not bgp_info.aspath:
            return result
        aspath_set = set(bgp_info.aspath)
        for neighbor in self.get_ebgp_neighbor_names(device):
            neighbor_as = self.get_ebgp_neighbor_as(device, neighbor)
            if neighbor_as is not None and neighbor_as in aspath_set:
                result.append(neighbor)
        return result
    
    def find_best_routes(self, device: str, dst_ip: str) -> List[Route]:
        """Find the best routes for a device to reach a destination IP using longest prefix match"""
        # Find all routes for this device and destination, excluding local routes
        # Local routes represent interface IP addresses and should not be used for forwarding decisions
        device_routes = [r for r in self.routes 
                        if r.node == device 
                        and r.protocol.lower() != 'local' 
                        and self._route_matches_dst(r, dst_ip)]
        
        if not device_routes:
            return []
        
        # Group routes by administrative distance
        routes_by_ad = defaultdict(list)
        for route in device_routes:
            routes_by_ad[route.ad].append(route)
        
        # Find the best (lowest) administrative distance
        best_ad = min(routes_by_ad.keys())
        candidate_routes = list(routes_by_ad[best_ad])
        
        # Among routes with the same AD, find the longest prefix match
        if len(candidate_routes) == 1:
            return candidate_routes
        
        # Find the route(s) with the longest prefix length
        max_prefix_length = max(route.prefix_length for route in candidate_routes)
        best_routes = [route for route in candidate_routes if route.prefix_length == max_prefix_length]
        
        return best_routes
    
    def _route_matches_dst(self, route: Route, dst_ip: str) -> bool:
        """Check if a route matches the destination IP using longest prefix match"""
        import ipaddress
        
        try:
            # Parse the route network and destination IP
            route_network = ipaddress.ip_network(route.network, strict=False)
            
            # Handle destination IP - it might be a single IP or a network
            if '/' in dst_ip:
                dst_network = ipaddress.ip_network(dst_ip, strict=False)
            else:
                # If no prefix length specified, treat as /32 for IPv4 or /128 for IPv6
                dst_network = ipaddress.ip_network(f"{dst_ip}/32", strict=False)
            
            # Check if the destination network is contained within the route network
            return dst_network.subnet_of(route_network)
            
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError) as e:
            logger.warning(f"Error parsing IP addresses: route={route.network}, dst={dst_ip}, error={e}")
            # Fallback to simple string matching
            route_network = route.network.split('/')[0]
            dst_network = dst_ip.split('/')[0]
            return route_network == dst_network
    
    def generate_smt_variables_for_ecmp(self, device: str, ecmp_routes: List[Route]) -> Dict[str, Union[str, Dict[str, str]]]:
        """
        Generate SMT variables for routes (single or ECMP).

        Args:
            device: Device hostname
            ecmp_routes: List of routes (single or multiple for ECMP)

        Returns:
            Dictionary of SMT variable assignments
        """
        if not ecmp_routes:
            return {
                'permitted': 'false',
                'metric': '0',
                'prefixLength': '0',
                'communities': self.generate_community_variables_for_no_routes(device),
                'control_plane': self.generate_control_plane_variables_for_ecmp(device, ecmp_routes, False)
            }
        
        # Determine if this is single route or true ECMP
        is_single_route = len(ecmp_routes) == 1
        route = ecmp_routes[0]  # All routes have same basic properties
        
        # Determine metric based on protocol
        if self._is_bgp_family(route.protocol):
            # For BGP and iBGP, use AS path length as metric (transit attribute).
            bgp_info = self.get_bgp_info(device, route.network)
            metric_value = str(bgp_info.aspath_length) if bgp_info else str(route.metric)
        else:
            # For non-BGP routes, use the route metric
            metric_value = str(route.metric)
        
        # Basic variables (same for all routes)
        variables = {
            'permitted': 'true',
            'metric': metric_value,
            'prefixLength': str(route.prefix_length),
            'communities': self.generate_community_variables(device, ecmp_routes),
            'control_plane': self.generate_control_plane_variables_for_ecmp(device, ecmp_routes, False)
        }

        # Non-transit attributes (MED, local preference): iBGP only, not propagated over eBGP.
        if route.protocol.lower() == 'ibgp':
            bgp_info = self.get_bgp_info(device, route.network)
            variables['med'] = str(bgp_info.med if (bgp_info and bgp_info.med is not None) else 0)
            variables['localPref'] = str(
                bgp_info.local_pref if (bgp_info and bgp_info.local_pref is not None) else 100
            )

        # Add history for protocols that have a history enum value.
        # History values are loaded from 0_overall_history_enum.txt
        # If the value is null in the enum file, no history variable is added
        if route.protocol.lower() == 'connected':
            history_value = self._get_history_value(device, 'CONNECTED')
            if history_value is not None:
                variables['history'] = history_value
        elif route.protocol.lower() == 'static':
            history_value = self._get_history_value(device, 'STATIC')
            if history_value is not None:
                variables['history'] = history_value
        elif route.protocol.lower() == 'ibgp':
            # Optional: allow iBGP to have its own history enum (like STATIC/CONNECTED).
            # If IBGP is absent or null in the enum file, this adds nothing.
            history_value = self._get_history_value(device, 'IBGP')
            if history_value is not None:
                variables['history'] = history_value
        # Note: local routes are excluded from route selection, so they won't appear here
        
        return variables
    
    def generate_community_variables(self, device: str, ecmp_routes: List[Route], negated_mode: bool = False) -> Union[Dict[str, str], str, None]:
        """Delegate to active community encoding module (BitVec by default)."""
        return self.community_encoder.generate_community_variables(device, ecmp_routes, negated_mode)

    def generate_community_variables_for_no_routes(self, device: str) -> Dict[str, str]:
        """Delegate to active community encoding module (BitVec by default)."""
        return self.community_encoder.generate_community_variables_for_no_routes(device)

    def generate_control_plane_variables_for_ecmp(self, device: str, ecmp_routes: List[Route], 
                                                negated_mode: bool = False) -> Dict[str, str]:
        """Generate control plane stable state variables for ECMP routes
        
        Control-Forwarding Cases (3 scenarios, each with forwarding/negated modes):
        0. No routes
        1. One route
        2. ECMP routes
        """
        control_vars = {}
        
        # Handle case where device has no routes to destination
        if not ecmp_routes:
            # Case 0: No routes
            control_vars = self._handle_control_forwarding_case_0(device, negated_mode)
            return control_vars
        
        # Get interfaces used by routes
        interfaces = self._get_route_interfaces(device, ecmp_routes)
        
        # Require every best-route interface to be in 0_interfaces.txt
        allowed = self.device_interfaces.get(device, set())
        for intf in interfaces:
            if intf not in allowed:
                logger.error(
                    f"Best route interface '{intf}' for device '{device}' is not in {Config.INTERFACES_FILE}. Exit."
                )
                sys.exit(1)
        
        # Filter out unused interfaces to get valid interfaces
        valid_interfaces = self._filter_valid_interfaces(device, interfaces)
        
        # If no valid interfaces (e.g., all routes have null NextHop), treat as Case 0: No routes
        if not valid_interfaces:
            # Case 0: No valid routes (routes exist but all have null NextHop)
            control_vars = self._handle_control_forwarding_case_0(device, negated_mode)
            return control_vars
        
        # Determine if this is still ECMP after filtering unused interfaces
        is_ecmp_after_filtering = len(valid_interfaces) > 1
        
        if len(ecmp_routes) == 1:
            # Case 1: One route
            control_vars = self._handle_control_forwarding_case_1(device, valid_interfaces, negated_mode)
        else:
            # Case 2: ECMP routes
            control_vars = self._handle_control_forwarding_case_2(device, valid_interfaces, is_ecmp_after_filtering, negated_mode)
        
        return control_vars
    
    def _get_route_interfaces(self, device: str, ecmp_routes: List[Route]) -> set:
        """Get all interfaces used by the given routes
        
        Unified handling for all protocol types:
        - Extract interface from route.nexthop_interface
        - Filtering is done later via unused_control_forwarding.txt
        - For BGP-family (bgp/ibgp) routes, also try to get interface from BGP neighbors as supplement

        NOTE: Currently, both "bgp" (eBGP) and "ibgp" routes are mapped to interface-based
        CONTROL-FORWARDING variables (e.g. CONTROL-FORWARDING_{device}_{interface}).
        """
        interfaces = set()
        for route in ecmp_routes:
            # Unified handling: extract interface from route.nexthop_interface
            # Only exclude Loopback0 and dynamic, let unused_control_forwarding.txt filter others
            if route.nexthop_interface not in ['Loopback0', 'dynamic']:
                interfaces.add(route.nexthop_interface)
            
            # For BGP-family routes, also try to get interface from BGP neighbors
            # (BGP routes typically have 'dynamic' as nexthop_interface)
            if self._is_bgp_family(route.protocol):
                if route.nexthop and route.nexthop.lower() != 'null':
                    interface = self.get_bgp_interface(device, route.nexthop)
                    if interface and interface not in ['Loopback0', 'dynamic']:
                        interfaces.add(interface)
            
            # Note: local routes are excluded from route selection, so they won't appear here
        return interfaces
    
    def _filter_valid_interfaces(self, device: str, interfaces: set) -> set:
        """Filter out unused interfaces to get valid interfaces"""
        valid_interfaces = set()
        for interface in interfaces:
            var_name = self._smt_var_name(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_{interface}")
            if var_name not in self.unused_control_forwarding:
                valid_interfaces.add(interface)
        return valid_interfaces
    
    def _get_all_device_interfaces(self, device: str) -> set:
        """Get all possible interfaces for a device from 0_interfaces.txt."""
        return set(self.device_interfaces.get(device, set()))
    
    def _handle_control_forwarding_case_0(self, device: str, negated_mode: bool) -> Dict[str, str]:
        """Case 0: No routes
        
        Normal: all interfaces = false
        Negated: (or (not (= interface1 false)) (not (= interface2 false)) ...)
                 This format is easier to compare with normal state
        """
        control_vars = {}
        all_interfaces = self._get_all_device_interfaces(device)
        
        if negated_mode:
            # For negated mode with no routes: at least one interface should be true (contradiction)
            # Format: (or (not (= interface1 false)) (not (= interface2 false)) ...)
            # This is semantically equivalent to (or interface1 interface2 ...) = true
            # but easier to compare with normal state where interfaces = false
            violation_conditions = []
            for intf in sorted(all_interfaces):
                var_name = self._smt_var_name(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_{intf}")
                # Filter out unused interfaces
                if var_name not in self.unused_control_forwarding:
                    violation_conditions.append(f"(not (= {var_name} false))")
            
            # Create overall OR constraint
            if len(violation_conditions) == 1:
                control_vars['_overall_or_constraint'] = violation_conditions[0]
            elif len(violation_conditions) > 1:
                control_vars['_overall_or_constraint'] = f"(or {' '.join(violation_conditions)})"
        else:
            # For normal mode with no routes: all interfaces should be false
            # Filter out unused interfaces
            for interface in sorted(all_interfaces):
                var_name = self._smt_var_name(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_{interface}")
                # Skip unused control forwarding variables
                if var_name in self.unused_control_forwarding:
                    continue
                control_vars[var_name] = "false"
        
        return control_vars

    def _handle_control_forwarding_case_1(self, device: str, valid_interfaces: set, negated_mode: bool) -> Dict[str, str]:
        """Case 1: One route
        
        Normal: active interface = true, others = false
        Negated: (or (not (= active_interface true)) (not (= non_active_interface1 false)) ...)
                 This format is easier to compare with normal state
        """
        control_vars = {}
        all_interfaces = self._get_all_device_interfaces(device)
        
        if negated_mode:
            # Negated mode: (or (not (= active_interface true)) (not (= non_active_interface1 false)) ...)
            # Format: (or (not (= var true)) (not (= var false)) ...)
            # This is easier to compare with normal state
            violation_conditions = []
            
            for interface in sorted(all_interfaces):
                var_name = self._smt_var_name(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_{interface}")
                
                # Skip unused control forwarding variables
                if var_name in self.unused_control_forwarding:
                    continue
                
                if interface in valid_interfaces:
                    # Active interface: violation if it's not true (i.e., false)
                    violation_conditions.append(f"(not (= {var_name} true))")
                else:
                    # Non-active interface: violation if it's not false (i.e., true)
                    violation_conditions.append(f"(not (= {var_name} false))")
            
            # Create overall OR constraint
            if len(violation_conditions) == 1:
                control_vars['_overall_or_constraint'] = violation_conditions[0]
            else:
                control_vars['_overall_or_constraint'] = f"(or {' '.join(violation_conditions)})"
        else:
            # Normal mode: active interface = true, others = false
            for interface in sorted(all_interfaces):
                var_name = self._smt_var_name(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_{interface}")
                
                if var_name in self.unused_control_forwarding:
                    continue
                
                if interface in valid_interfaces:
                    control_vars[var_name] = "true"
                else:
                    control_vars[var_name] = "false"
        
        return control_vars
    
    def _handle_control_forwarding_case_2(self, device: str, valid_interfaces: set, is_ecmp_after_filtering: bool, negated_mode: bool) -> Dict[str, str]:
        """Case 2: ECMP routes
        
        Normal: all active interfaces must be true, non-active = false
        Negated: (or (not (= active1 true)) (not (= active2 true)) ... (not (= non_active1 false)) ...)
                 At least one active interface is not true, or at least one non-active interface is not false
        """
        control_vars = {}
        all_interfaces = self._get_all_device_interfaces(device)
        
        if negated_mode:
            # Negated mode: (or (not (= active1 true)) (not (= active2 true)) ... (not (= non_active1 false)) ...)
            # Format: (or (not (= var true)) ... (not (= var false)) ...)
            # At least one active interface is not true, OR at least one non-active interface is not false
            violation_conditions = []
            
            for interface in sorted(all_interfaces):
                var_name = self._smt_var_name(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_{interface}")
                
                if var_name in self.unused_control_forwarding:
                    continue
                
                if interface in valid_interfaces:
                    # Active interface: violation if it's not true (i.e., false)
                    violation_conditions.append(f"(not (= {var_name} true))")
                else:
                    # Non-active interface: violation if it's not false (i.e., true)
                    violation_conditions.append(f"(not (= {var_name} false))")
            
            # Create overall OR constraint
            if len(violation_conditions) == 1:
                control_vars['_overall_or_constraint'] = violation_conditions[0]
            elif len(violation_conditions) > 1:
                control_vars['_overall_or_constraint'] = f"(or {' '.join(violation_conditions)})"
        else:
            # Normal mode: all active interfaces must be true, non-active = false
            for interface in sorted(all_interfaces):
                var_name = self._smt_var_name(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_{interface}")
                
                if var_name in self.unused_control_forwarding:
                    continue
                
                if interface in valid_interfaces:
                    # ECMP: all active interfaces must be true
                    control_vars[var_name] = "true"
                else:
                    control_vars[var_name] = "false"
            
            # No overall OR constraint needed for ECMP in normal mode
            # All active interfaces are already set to true
        
        return control_vars
    
    def analyze_all_devices(self) -> Dict[str, Dict[str, Dict[str, Union[str, Dict[str, str]]]]]:
        """
        Analyze all devices for all destination IPs.

        Returns:
            Dictionary containing analysis results for all devices and destinations.
        """
        logger.info(f"Step 2: Analyzing routes for {len(self.dst_ips)} destination IPs: {self.dst_ips}")
        
        results = {}
        
        for dst_ip in self.dst_ips:
            logger.info(f"\n=== Analyzing destination: {dst_ip} ===")
            results[dst_ip] = {}
            
            # Get all unique devices
            devices = set(route.node for route in self.routes)
            
            for device in sorted(devices):
                logger.info(f"\nAnalyzing device: {device}")
                
                # Find best routes for this device and destination
                best_routes = self.find_best_routes(device, dst_ip)
                
                if best_routes:
                    # Group routes by interface for ECMP detection
                    routes_by_interface = defaultdict(list)
                    for route in best_routes:
                        routes_by_interface[route.nexthop_interface].append(route)
                    
                    # Check if this is ECMP (multiple interfaces with same AD)
                    ecmp_routes = []
                    for interface_routes in routes_by_interface.values():
                        ecmp_routes.extend(interface_routes)
                    
                    logger.info(f"  Found {len(ecmp_routes)} ECMP route(s):")
                    for i, route in enumerate(ecmp_routes, 1):
                        logger.info(f"    Route {i}: {route.network} via {route.protocol} (AD={route.ad})")
                        
                        # Add BGP-specific information
                        if route.protocol.lower() == 'bgp':
                            all_bgp_routes = self.get_all_bgp_info(device, route.network)
                            if all_bgp_routes:
                                # For ECMP, show all BGP routes
                                for j, bgp_info in enumerate(all_bgp_routes):
                                    if len(all_bgp_routes) > 1:
                                        logger.info(f"      BGP Route {j+1} AS path: {bgp_info.aspath} (length={bgp_info.aspath_length})")
                                    else:
                                        logger.info(f"      BGP AS path: {bgp_info.aspath} (length={bgp_info.aspath_length})")
                                    if bgp_info.communities:
                                        logger.info(f"      BGP Communities: {bgp_info.communities}")
                else:
                    logger.info(f"  No routes found for destination {dst_ip}")
                    ecmp_routes = []  # Initialize empty list for no routes case
                
                # Generate SMT variables
                variables = self.generate_smt_variables_for_ecmp(device, ecmp_routes)
                results[dst_ip][device] = variables
        
        return results
    
    def generate_negated_route_attributes_constraint(self, device: str, device_vars: Dict[str, Union[str, Dict[str, str]]], ecmp_routes: List[Route]) -> Optional[str]:
        """Generate negated route attributes constraint for a device
        
        For static/connected best routes: only prefixLength and history (if present).
        For other protocols: prefixLength, metric, med/localPref (iBGP), and communities.
        
        Args:
            device: Device hostname
            device_vars: Dictionary containing normal state SMT variables
            ecmp_routes: List of routes (used to determine the scenario case)
        
        Returns:
            Optional[str]: Negated constraint SMT string, or None if no constraint can be generated
        """
        mismatch_conditions: List[str] = []
        prefix_length_value = device_vars.get('prefixLength', '0')
        prefix_length_var = self._smt_var_name(
            f"{self.smt_var_prefix}{device}_{Config.OVERALL_BEST_PREFIX}_None_prefixLength"
        )
        mismatch_conditions.append(f"(not (= {prefix_length_var} {prefix_length_value}))")

        is_static_or_connected = bool(
            ecmp_routes and ecmp_routes[0].protocol.lower() in ('static', 'connected')
        )

        if is_static_or_connected:
            if 'history' in device_vars:
                history_var = self._smt_var_name(
                    f"{self.smt_var_prefix}{device}_{Config.OVERALL_BEST_PREFIX}_None_history"
                )
                mismatch_conditions.append(f"(not (= {history_var} {device_vars['history']}))")
        else:
            metric_value = device_vars.get('metric', '0')
            metric_var = self._smt_var_name(
                f"{self.smt_var_prefix}{device}_{Config.OVERALL_BEST_PREFIX}_None_metric"
            )
            mismatch_conditions.append(f"(not (= {metric_var} {metric_value}))")

            for attr_key, smt_suffix in (('med', 'med'), ('localPref', 'localPref')):
                if attr_key in device_vars:
                    attr_var = self._smt_var_name(
                        f"{self.smt_var_prefix}{device}_{Config.OVERALL_BEST_PREFIX}_None_{smt_suffix}"
                    )
                    mismatch_conditions.append(f"(not (= {attr_var} {device_vars[attr_key]}))")

            community_constraint = self.generate_community_variables(device, ecmp_routes, negated_mode=True)
            if isinstance(community_constraint, str):
                mismatch_conditions.append(community_constraint)

        if not mismatch_conditions:
            return None
        if len(mismatch_conditions) == 1:
            return f"(assert {mismatch_conditions[0]})"
        return f"(assert (or {' '.join(mismatch_conditions)}))"

    def _extract_constraint_content(self, constraint: str) -> str:
        """Extract constraint content from assert statement
        
        Args:
            constraint: SMT constraint string, e.g., "(assert (= var value))" or "(assert (or ...))"
            
        Returns:
            Constraint content without assert wrapper, e.g., "(= var value)" or "(or ...)"
        """
        constraint = constraint.strip()
        if not constraint:
            return ""
        
        # Remove comment prefix if present
        if constraint.startswith(';'):
            return ""
        
        # Check if it's an assert statement
        if constraint.startswith('(assert '):
            # Remove "(assert " prefix (8 characters)
            content = constraint[8:]
            # Remove trailing ")" if present (to balance the opening parenthesis)
            # We need to be careful here - we should remove only one closing paren
            # if the content is properly balanced
            if content.endswith(')'):
                # Count opening and closing parens to ensure we only remove the outer one
                # Simple approach: remove the last ')' if it exists
                content = content[:-1]
            return content.strip()
        
        # If it's already content format (no assert wrapper), return as is
        return constraint

    def _generate_combined_constraint(self, device: str, output_dir: Path,
                                     normal_stable_states_constraints: List[str],
                                     negated_stable_states_constraints: List[str],
                                     negated_route_attributes_constraints: List[str],
                                     prefix_length_bound_asserts: Optional[List[str]] = None) -> None:
        """Generate combined constraint: (or (negated stable states) (and (normal stable states) (negated route attributes)))
        
        Args:
            device: Device hostname
            output_dir: Output directory for constraint files
            normal_stable_states_constraints: List of normal stable states constraint strings
            negated_stable_states_constraints: List of negated stable states constraint strings
            negated_route_attributes_constraints: List of negated route attributes constraint strings
            prefix_length_bound_asserts: Optional (<= / >=) bounds on OVERALL_BEST prefixLength appended after combined constraint
        """
        # Extract constraint contents (remove assert wrapper)
        negated_stable_contents = []
        for constraint in negated_stable_states_constraints:
            content = self._extract_constraint_content(constraint)
            if content:
                negated_stable_contents.append(content)
        
        normal_stable_contents = []
        for constraint in normal_stable_states_constraints:
            content = self._extract_constraint_content(constraint)
            if content:
                normal_stable_contents.append(content)
        
        negated_route_attrs_contents = []
        for constraint in negated_route_attributes_constraints:
            content = self._extract_constraint_content(constraint)
            if content:
                negated_route_attrs_contents.append(content)
        
        # Build combined constraint
        # Structure: (or (negated stable states) (and (normal stable states) (negated route attributes)))
        
        # Part 1: Negated stable states (OR of all negated stable state constraints)
        if negated_stable_contents:
            if len(negated_stable_contents) == 1:
                negated_stable_part = negated_stable_contents[0]
            else:
                negated_stable_part = f"(or {' '.join(negated_stable_contents)})"
        else:
            # If no negated stable states, use false (no violation in stable states)
            negated_stable_part = "false"
        
        # Part 2: Normal stable states (AND of all normal stable state constraints)
        if normal_stable_contents:
            if len(normal_stable_contents) == 1:
                normal_stable_part = normal_stable_contents[0]
            else:
                normal_stable_part = f"(and {' '.join(normal_stable_contents)})"
        else:
            # If no normal stable states, use true (no constraint, always satisfied)
            normal_stable_part = "true"
        
        # Part 3: Negated route attributes (AND of all negated route attribute constraints)
        if negated_route_attrs_contents:
            if len(negated_route_attrs_contents) == 1:
                negated_route_attrs_part = negated_route_attrs_contents[0]
            else:
                negated_route_attrs_part = f"(and {' '.join(negated_route_attrs_contents)})"
        else:
            # If no negated route attributes, use true (no constraint, always satisfied)
            negated_route_attrs_part = "true"
        
        # Combine: (and (normal stable states) (negated route attributes))
        # If both are true, the AND part becomes true, which simplifies the overall constraint
        if normal_stable_part == "true" and negated_route_attrs_part == "true":
            # If both parts are true, the AND part is just true
            combined_and_part = "true"
        elif normal_stable_part == "true":
            # If only normal stable states is true, the AND part is just the negated route attributes
            combined_and_part = negated_route_attrs_part
        elif negated_route_attrs_part == "true":
            # If only negated route attributes is true, the AND part is just the normal stable states
            combined_and_part = normal_stable_part
        else:
            # Both parts have constraints, combine them with AND
            combined_and_part = f"(and {normal_stable_part} {negated_route_attrs_part})"
        
        # Final: (or (negated stable states) (and (normal stable states) (negated route attributes)))
        # If negated_stable_part is false and combined_and_part is true, the result is true
        # If negated_stable_part is false and combined_and_part is false, the result is false
        # If negated_stable_part is not false, include it in the OR
        if negated_stable_part == "false" and combined_and_part == "true":
            # (or false true) = true, but this means no constraint, so we might want to skip
            # However, we'll still generate it for consistency
            combined_constraint = "true"
        elif negated_stable_part == "false":
            # (or false X) = X
            combined_constraint = combined_and_part
        elif combined_and_part == "true":
            # (or X true) = true
            combined_constraint = "true"
        else:
            # Both parts have constraints, combine them with OR
            combined_constraint = f"(or {negated_stable_part} {combined_and_part})"
        
        # Write to file
        combined_file = output_dir / f'{device}_combined_constraint_negated.txt'
        with open(combined_file, 'w') as f:
            f.write(f"; Combined constraint for device: {device}\n")
            f.write(f"; Structure: (or (negated stable states) (and (normal stable states) (negated route attributes)))\n")
            f.write(f"; Generated from route analysis\n\n")
            f.write(f"(assert {combined_constraint})\n")
            if prefix_length_bound_asserts:
                for bound_assert in prefix_length_bound_asserts:
                    f.write(f"{bound_assert}\n")
        
        logger.info(f"Combined constraint file created: {combined_file}")

    def extract_device_constraints(self, results: Dict[str, Dict[str, Dict[str, Union[str, Dict[str, str]]]]]) -> None:
        """Extract device-specific constraints and write to files"""
        logger.info("\n" + "="*60)
        logger.info("Step 3: Extracting device-specific constraints")
        logger.info("="*60)
        
        # Create output directory
        dataplane_original_dir = self.work_dir / "1_dataplane_original"
        dataplane_original_dir.mkdir(exist_ok=True)
        
        logger.info(f"Device-specific constraints extracted to: {dataplane_original_dir}")
        
        # Process each device
        for device in sorted(set(route.node for route in self.routes)):
            logger.info(f"Processing device: {device}")
            
            # Collect constraints for this device
            overall_best_constraints = []
            normal_stable_states_constraints = []
            negated_stable_states_constraints = []
            negated_route_attributes_constraints = []
            route_from_entries: Set[str] = set()  # neighbor device names for BGP loop prevention
            prefix_length_bound_asserts = self._prefix_length_bound_asserts(device)
            
            for dst_ip, devices in results.items():
                if device in devices:
                    device_vars = devices[device]
                    
                    # Extract OVERALL_BEST constraints
                    for var_name, value in device_vars.items():
                        if var_name in ['permitted', 'metric', 'med', 'localPref', 'prefixLength', 'history']:
                            overall_best_constraints.append(f"(assert (= {self._smt_var_name(f'{self.smt_var_prefix}{device}_{Config.OVERALL_BEST_PREFIX}_None_{var_name}')} {value}))")
                    
                    # Extract community constraints
                    if 'communities' in device_vars and device_vars['communities']:
                        for var_name, value in device_vars['communities'].items():
                            if var_name not in ['_overall_or_constraint', '_overall_and_constraint']:
                                if '(or (= ' in value:
                                    # Direct assert for (or (= Var true) (= Var false)) format
                                    overall_best_constraints.append(f"(assert {value})")
                                else:
                                    overall_best_constraints.append(f"(assert (= {var_name} {value}))")
                        
                        # Add overall OR constraint if present
                        if '_overall_or_constraint' in device_vars['communities']:
                            constraint = device_vars['communities']['_overall_or_constraint']
                            # constraint is already in format: (or (= var1 true) (= var2 true) ...)
                            # Direct assert, no need to wrap with (= ... true)
                            overall_best_constraints.append(f"(assert {constraint})")
                        
                        # Add overall AND constraint if present
                        if '_overall_and_constraint' in device_vars['communities']:
                            constraint = device_vars['communities']['_overall_and_constraint']
                            # constraint is already in format: (and (= var1 true) (= var2 true) ...)
                            # Direct assert, no need to wrap with (= ... true)
                            overall_best_constraints.append(f"(assert {constraint})")
                    
                    # Generate negated route attributes constraints
                    # Get the actual ECMP routes for this device and destination
                    ecmp_routes = self.find_best_routes(device, dst_ip)
                    negated_route_attrs = self.generate_negated_route_attributes_constraint(device, device_vars, ecmp_routes)
                    if negated_route_attrs:
                        negated_route_attributes_constraints.append(negated_route_attrs)
                    
                    # Extract CONTROL-FORWARDING constraints for both normal and negated modes
                    if 'control_plane' in device_vars:
                        # Get the actual ECMP routes for this device and destination
                        ecmp_routes = self.find_best_routes(device, dst_ip)
                        # BGP loop prevention: record 'route from: neighbor' when neighbor's AS is in route AS-path
                        for neighbor in self._compute_route_from_for_device_dst(device, ecmp_routes):
                            route_from_entries.add(neighbor)
                        # Generate normal mode constraints
                        normal_control_vars = self.generate_control_plane_variables_for_ecmp(device, ecmp_routes, False)
                        for var_name, value in normal_control_vars.items():
                            if var_name.startswith("|" + self._escape_smt_inner(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_")):
                                if '(or (= ' in value:
                                    # Direct assert for (or (= Var true) (= Var false)) format
                                    normal_stable_states_constraints.append(f"(assert {value})")
                                else:
                                    normal_stable_states_constraints.append(f"(assert (= {var_name} {value}))")
                            elif var_name == '_overall_or_constraint':
                                # value is already in format: (or (= interface1 true) (= interface2 true) ...)
                                # Direct assert, no need to wrap with (= ... true)
                                normal_stable_states_constraints.append(f"(assert {value})")
                        
                        # Generate negated mode constraints
                        negated_control_vars = self.generate_control_plane_variables_for_ecmp(device, ecmp_routes, True)
                        
                        # Check if all normal CONTROL-FORWARDING variables are false
                        all_false = True
                        for var_name, normal_value in normal_control_vars.items():
                            if var_name.startswith("|" + self._escape_smt_inner(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_")) and normal_value != 'false':
                                all_false = False
                                break
                        
                        # Handle Case 0 (no routes): if normal_control_vars is empty but negated_control_vars has constraints
                        # This happens when all interfaces were filtered as unused in normal mode but included in negated mode
                        if not normal_control_vars and negated_control_vars:
                            # All interfaces were unused in normal mode, but we still need negated constraints
                            for var_name, value in negated_control_vars.items():
                                if var_name == '_overall_or_constraint':
                                    # value is already in format: (or (not (= interface1 true/false)) ...)
                                    # For ECMP: (or (not (= active1 true)) (not (= active2 true)) ... (not (= non_active false)) ...)
                                    # For Case 0: (or (not (= interface1 false)) ...)
                                    negated_stable_states_constraints.append(f"(assert {value})")
                                elif var_name.startswith("|" + self._escape_smt_inner(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_")):
                                    # For single interface case, set it to true directly
                                    negated_stable_states_constraints.append(f"(assert (= {var_name} {value}))")
                        elif all_false and normal_control_vars:
                            # If all normal CONTROL-FORWARDING are false, generate overall OR constraint in negated mode
                            for var_name, value in negated_control_vars.items():
                                if var_name == '_overall_or_constraint':
                                    # value is already in format: (or (not (= interface1 false)) ...)
                                    # or single condition: (not (= interface1 false))
                                    negated_stable_states_constraints.append(f"(assert {value})")
                                elif var_name.startswith("|" + self._escape_smt_inner(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_")):
                                    # For single interface case, set it to true directly
                                    negated_stable_states_constraints.append(f"(assert (= {var_name} {value}))")
                        else:
                            # Normal case: only include interfaces that could be true in normal mode
                            for var_name, value in negated_control_vars.items():
                                if var_name.startswith("|" + self._escape_smt_inner(f"{self.smt_var_prefix}{Config.CONTROL_FORWARDING_PREFIX}_{device}_")):
                                    normal_value = normal_control_vars.get(var_name, 'false')
                                    if normal_value in ['true'] or '(or (= ' in normal_value:
                                        if '(or (= ' in value:
                                            # Direct assert for (or (= Var true) (= Var false)) format
                                            negated_stable_states_constraints.append(f"(assert {value})")
                                        else:
                                            negated_stable_states_constraints.append(f"(assert (= {var_name} {value}))")
                                elif var_name == '_overall_or_constraint':
                                    # Handle overall OR constraint for negated mode
                                    # For ECMP: (or (not (= active1 true)) (not (= active2 true)) ... (not (= non_active false)) ...)
                                    # For other cases: (or (not (= interface1 false)) ...)
                                    negated_stable_states_constraints.append(f"(assert {value})")
            
            # Write Normal route attributes (OVERALL_BEST)
            route_attrs_normal_file = dataplane_original_dir / f'{device}_route_attributes_normal.txt'
            with open(route_attrs_normal_file, 'w') as f:
                f.write(f"; Normal route attributes (OVERALL_BEST) for device: {device}\n")
                f.write(f"; Generated from route analysis\n\n")
                for constraint in overall_best_constraints:
                    f.write(f"{constraint}\n")
            
            # Write normal stable states constraints (and BGP loop prevention 'route from' lines)
            normal_stable_file = dataplane_original_dir / f'{device}_stable_states_normal.txt'
            with open(normal_stable_file, 'w') as f:
                f.write(f"; Normal stable states constraints for device: {device}\n")
                f.write(f"; Generated from dataplane analysis\n\n")
                for constraint in normal_stable_states_constraints:
                    f.write(f"{constraint}\n")
                if route_from_entries:
                    f.write(f"\n; BGP loop prevention: route origin (neighbor AS in AS-path)\n")
                    for neighbor in sorted(route_from_entries):
                        f.write(f"route from: {neighbor}\n")
            
            # Write negated stable states constraints
            negated_stable_file = dataplane_original_dir / f'{device}_stable_states_negated.txt'
            with open(negated_stable_file, 'w') as f:
                f.write(f"; Negated stable states constraints for device: {device}\n")
                f.write(f"; Generated from dataplane analysis (negated mode)\n\n")
                for constraint in negated_stable_states_constraints:
                    f.write(f"{constraint}\n")
            
            # Write negated route attributes constraints
            negated_route_attrs_file = dataplane_original_dir / f'{device}_route_attributes_negated.txt'
            with open(negated_route_attrs_file, 'w') as f:
                f.write(f"; Negated route attributes constraints for device: {device}\n")
                f.write(f"; Generated from route analysis (negated mode)\n\n")
                for constraint in negated_route_attributes_constraints:
                    f.write(f"{constraint}\n")
                for bound_assert in prefix_length_bound_asserts:
                    f.write(f"{bound_assert}\n")
            
            # Generate combined constraint: (or (negated stable states) (and (normal stable states) (negated route attributes)))
            self._generate_combined_constraint(device, dataplane_original_dir, 
                                            normal_stable_states_constraints,
                                            negated_stable_states_constraints,
                                            negated_route_attributes_constraints,
                                            prefix_length_bound_asserts=prefix_length_bound_asserts)
        
        # Write global dataplane file with all constraints
        global_file = dataplane_original_dir / 'global_dataplane_assume_guarantee.txt'
        devices = sorted(set(route.node for route in self.routes))
        with open(global_file, 'w') as f:
            f.write("; Global dataplane assume-guarantee constraints\n")
            f.write("; Generated from route analysis\n\n")
            
            for device in devices:
                f.write(f"; ===== Device: {device} =====\n\n")
                
                # 1. Read and include normal stable states
                normal_stable_file = dataplane_original_dir / f'{device}_stable_states_normal.txt'
                if normal_stable_file.exists():
                    f.write(f"; Normal stable states for {device}\n")
                    with open(normal_stable_file, 'r') as nf:
                        content = nf.read().strip()
                        if content:
                            f.write(content)
                            f.write("\n\n")
                
                # 2. Read and include normal route attributes (OVERALL_BEST)
                route_attrs_normal_file = dataplane_original_dir / f'{device}_route_attributes_normal.txt'
                if route_attrs_normal_file.exists():
                    f.write(f"; Normal route attributes (OVERALL_BEST) for {device}\n")
                    with open(route_attrs_normal_file, 'r') as of:
                        content = of.read().strip()
                        if content:
                            f.write(content)
                            f.write("\n\n")
                
                # 3. Read and include negated stable states
                negated_stable_file = dataplane_original_dir / f'{device}_stable_states_negated.txt'
                if negated_stable_file.exists():
                    f.write(f"; Negated stable states for {device}\n")
                    with open(negated_stable_file, 'r') as nf:
                        content = nf.read().strip()
                        if content:
                            f.write(content)
                            f.write("\n\n")
                
                # 4. Read and include negated route attributes
                negated_route_attrs_file = dataplane_original_dir / f'{device}_route_attributes_negated.txt'
                if negated_route_attrs_file.exists():
                    f.write(f"; Negated route attributes for {device}\n")
                    with open(negated_route_attrs_file, 'r') as nf:
                        content = nf.read().strip()
                        if content:
                            f.write(content)
                            f.write("\n\n")
                
                # 5. Read and include combined negated constraint
                combined_file = dataplane_original_dir / f'{device}_combined_constraint_negated.txt'
                if combined_file.exists():
                    f.write(f"; Combined negated constraint for {device}\n")
                    with open(combined_file, 'r') as cf:
                        content = cf.read().strip()
                        if content:
                            f.write(content)
                            f.write("\n\n")
                
                f.write("; " + "="*50 + "\n\n")
        
        devices = sorted(set(route.node for route in self.routes))
        logger.info(f"Files created for devices: {devices}")
        logger.info(f"Global dataplane file created: {global_file}")

##########################################################################################
### Main Execution
##########################################################################################

def main():
    """Main function for route analysis"""
    # Parse command line arguments (order: other, -v, -d)
    verbose = False
    delete_intermediate = False
    work_dir = None

    for arg in sys.argv[1:]:
        if arg == '-v':
            verbose = True
        elif arg == '-d':
            delete_intermediate = True
        elif not arg.startswith('-'):
            work_dir = arg

    if work_dir is None:
        print("Usage: python 1_route_analyzer.py [-v] [-d] <work_directory>")
        print("Options:")
        print("  -v          Verbose mode: Show detailed INFO logs")
        print("              Without -v: Only show WARNING/ERROR logs and completion status")
        print("  -d          Delete intermediate output files before running")
        print("Example: python 1_route_analyzer.py smt_output_network_1")
        print("         python 1_route_analyzer.py -v smt_output_network_1")
        print("         python 1_route_analyzer.py -d smt_output_network_1")
        sys.exit(1)
    
    # Set logging level based on verbose flag
    if not verbose:
        # If not verbose, only show WARNING and above
        logging.getLogger().setLevel(logging.WARNING)
    
    if not work_dir:
        logger.error("Work directory is required")
        sys.exit(1)
    
    if not os.path.exists(work_dir):
        logger.error(f"Work directory does not exist: {work_dir}")
        sys.exit(1)
    
    # Delete intermediate files if requested (-d: always show INFO for delete operations)
    if delete_intermediate:
        logging.getLogger().setLevel(logging.INFO)
        import shutil
        from pathlib import Path
        deleted_items = []
        
        # Delete 1_dataplane_original directory
        output_dir = Path(work_dir) / "1_dataplane_original"
        if output_dir.exists():
            logger.info(f"Deleting intermediate output directory: {output_dir}")
            shutil.rmtree(output_dir)
            deleted_items.append(str(output_dir))
        
        if deleted_items:
            logger.info(f"Deleted {len(deleted_items)} intermediate file(s)/directory(ies):")
            for item in deleted_items:
                logger.info(f"  - {item}")
            logger.info("Intermediate files deleted.")
        else:
            logger.info("No intermediate files found to delete.")
        sys.exit(0)
    
    verbose_info(verbose, "=" * 60)
    verbose_info(verbose, "Route Analysis Tool - Network Verification Explanation")
    verbose_info(verbose, "=" * 60)
    
    try:
        # Initialize analyzer
        logger.info("Step 1: Initializing route analyzer...")
        analyzer = RouteAnalyzer(work_dir)
        
        # Load all data
        analyzer._load_all_data()
        
        # Analyze routes
        results = analyzer.analyze_all_devices()
        
        # Extract device-specific constraints
        logger.info("Step 3: Extracting device-specific constraints...")
        analyzer.extract_device_constraints(results)
        
        verbose_info(verbose, "\n" + "=" * 60)
        verbose_info(verbose, "Route analysis completed successfully!")
        verbose_info(verbose, "=" * 60)

        if not verbose:
            print("✓ Completed")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
