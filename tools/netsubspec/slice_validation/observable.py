"""Independent MAIN-RIB observables; no RouteBinder or seed expectations.

Scope: one destination, direct numbered eBGP, connected/local terminal routes.
Unsupported protocols, parallel peer mappings and unresolved provenance fail closed.
"""
import ipaddress
import json
import re


def evaluate(node, links):
    op = node['operator']
    if op == 'TRUE':
        return True
    if op == 'FALSE':
        return False
    if op == 'VARIABLE':
        return links[node['variableId']]
    children = [evaluate(child, links) for child in node.get('children', [])]
    if op == 'AND':
        return all(children)
    if op == 'OR':
        return any(children)
    if op == 'NOT' and len(children) == 1:
        return not children[0]
    raise ValueError(f'Unsupported guard operator/arity: {node}')


class Observables:
    def __init__(self, directory):
        self.data = json.loads((directory / 'symbolic_route.json').read_text())
        destinations = (directory / '0_dst_ips.txt').read_text().split()
        if len(destinations) != 1:
            raise ValueError('Observable comparison requires exactly one destination')
        self.destination = ipaddress.ip_address(destinations[0].split('/')[0])
        self.peers = {}
        for line in (directory / '0_ebgp_neighbors.txt').read_text().splitlines():
            match = re.fullmatch(r'([^,]+),(.+?) \([^)]*\) -> ([^,]+),(.+?) \([^)]*\)', line)
            if not match:
                raise ValueError(f'Unsupported neighbor record: {line}')
            router, interface, peer, _ = match.groups()
            key = router, peer
            if key in self.peers and self.peers[key] != interface:
                raise ValueError(f'Parallel sessions require next-hop IP mapping: {key}')
            self.peers[key] = interface

    def expected(self, router, failed, declared):
        links = {}
        for variable in self.data['guardVariables']:
            if variable['kind'] != 'LINK_AVAILABILITY' or variable['polarity'] != 'UP':
                raise ValueError('Unsupported failure variable semantics')
            edge = variable['link']
            forward = f'|0_FAILED-EDGE_{edge["firstRouter"]}_{edge["secondRouter"]}|'
            reverse = f'|0_FAILED-EDGE_{edge["secondRouter"]}_{edge["firstRouter"]}|'
            matches = [symbol for symbol in (forward, reverse) if symbol in declared]
            if len(matches) != 1:
                raise ValueError(f'Expected one canonical failure variable: {variable}')
            links[variable['variableId']] = matches[0] not in failed
        active = [c for c in self.data['candidates'] if c['plane'] == 'MAIN'
                  and c['router'] == router and c['vrf'] == 'default'
                  and self.destination in ipaddress.ip_network(c['prefix'])
                  and evaluate(c['selectionGuard']['ast'], links)]
        if active:
            length = max(ipaddress.ip_network(c['prefix']).prefixlen for c in active)
            active = [c for c in active if ipaddress.ip_network(c['prefix']).prefixlen == length]
        interfaces = set()
        for candidate in active:
            protocol = candidate['protocol']
            if protocol in ('CONNECTED', 'LOCAL'):
                continue  # Local delivery is not an outgoing forwarding interface.
            if protocol != 'BGP':
                raise ValueError(f'Unsupported observable protocol: {protocol}')
            contributors = [c for c in candidate['contributions']
                            if evaluate(c['selectionGuard']['ast'], links)]
            if not contributors:
                raise ValueError('Active BGP route has no active provenance')
            for contribution in contributors:
                peer = contribution['provenance'].get('previousRouter')
                interfaces.add(self.peers[(router, peer)])
        expected = [f'(assert (= |0_{router}_OVERALL_BEST_None_permitted| {str(bool(active)).lower()}))']
        for plane in ('CONTROL', 'DATA'):
            prefix = f'|0_{plane}-FORWARDING_{router}_'
            symbols = sorted(s for s in declared if s.startswith(prefix))
            if not symbols:
                raise ValueError(f'Missing forwarding observables for {router}')
            known = {s[len(prefix):-1] for s in symbols}
            if not interfaces <= known:
                raise ValueError(f'Missing interfaces: {interfaces - known}')
            expected.extend(f'(assert (= {s} {str(s[len(prefix):-1] in interfaces).lower()}))' for s in symbols)
        return expected, {'has_route': bool(active), 'interfaces': sorted(interfaces),
                          'candidate_ids': [c['candidateId'] for c in active]}
