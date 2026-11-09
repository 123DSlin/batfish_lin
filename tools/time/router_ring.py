"""Generate a degree-two eBGP ring with one advertised destination."""

from ipaddress import IPv4Address
from pathlib import Path


def write_ring(directory: Path, size: int) -> None:
    if not 4 <= size <= 256:
        raise ValueError("Ring size must be between 4 and 256")
    configs = directory / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    for node in range(size):
        left = (node - 1) % size
        right = (node + 1) % size
        left_base = IPv4Address("10.0.0.0") + 4 * left
        right_base = IPv4Address("10.0.0.0") + 4 * node
        lines = [
            f"hostname r{node}",
            "!",
            "interface GigabitEthernet0/0",
            f" ip address {left_base + 2} 255.255.255.252",
            "!",
            "interface GigabitEthernet0/1",
            f" ip address {right_base + 1} 255.255.255.252",
            "!",
            "ip prefix-list DESTINATION seq 5 permit 5.5.5.5/32",
            "route-map FROM_LEFT permit 10",
            " match ip address prefix-list DESTINATION",
            " set local-preference 200",
            "route-map FROM_RIGHT permit 10",
            " match ip address prefix-list DESTINATION",
            " set local-preference 100",
            "!",
        ]
        if node == 0:
            lines.extend([
                "interface Loopback0",
                " ip address 5.5.5.5 255.255.255.255",
                "route-map ORIGINATE permit 10",
                " match ip address prefix-list DESTINATION",
                "!",
            ])
        lines.extend([
            f"router bgp {65000 + node}",
            f" bgp router-id {IPv4Address('192.0.2.0') + node + 1}",
            f" neighbor {left_base + 1} remote-as {65000 + left}",
            f" neighbor {left_base + 1} route-map FROM_LEFT in",
            f" neighbor {right_base + 2} remote-as {65000 + right}",
            f" neighbor {right_base + 2} route-map FROM_RIGHT in",
        ])
        if node == 0:
            lines.append(" redistribute connected route-map ORIGINATE")
        (configs / f"r{node}.cfg").write_text("\n".join([*lines, "!", ""]))
