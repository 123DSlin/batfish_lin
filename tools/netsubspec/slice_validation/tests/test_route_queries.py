"""Independent scan-vs-index checks; every competitive candidate must survive."""
from dataclasses import replace
import ipaddress
import itertools
from pathlib import Path
import sys
from types import MappingProxyType
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from consistency.branch_loader import (RouteEntry, SymbolicRib, SymbolicRouteFormatError,
    NeighborTopology, NeighborLink, NeighborEndpoint)


def route(identifier, router='r', prefix='10.1.0.0/16', vrf='default', plane='MAIN',
          protocol='BGP', contributions=()):
    guard = MappingProxyType({'ast': {'operator': 'TRUE'}})
    return RouteEntry(identifier, plane, router, vrf, prefix, protocol, 'test',
                      MappingProxyType({}), guard, guard, contributions)


def scan_entries(rib, **filters):
    result = []
    for entry in rib.entries_all:
        if all(value is None or getattr(entry, name) ==
               (value.upper() if name in ('plane', 'protocol') else value)
               for name, value in filters.items()):
            result.append(entry)
    return tuple(sorted(result, key=lambda e: e.candidate_id))


def scan_forwarding(rib, router, vrf, destination, plane='MAIN'):
    network = ipaddress.ip_network(destination if '/' in destination else
        destination + ('/128' if ':' in destination else '/32'), strict=False)
    return tuple(e for e in scan_entries(rib, router=router, vrf=vrf, plane=plane)
        if e.protocol != 'LOCAL' and ipaddress.ip_network(e.prefix, strict=False).version == network.version
        and network.subnet_of(ipaddress.ip_network(e.prefix, strict=False)))


class RouteQueryTest(unittest.TestCase):
    def test_exact_filters_match_original_scan_and_sort(self):
        entries = [route(f'c{i:04}', r, p, v, pl, proto) for i, (r, p, v, pl, proto) in enumerate(
            itertools.product(('r', 's'), ('10.0.0.0/8', '10.1.0.0/16'),
                              ('default', 'blue'), ('MAIN', 'BGP'), ('BGP', 'CONNECTED')))]
        rib = SymbolicRib([], entries[::-1])
        for r, v, p, pl, proto in itertools.product((None, 'r', 'absent'), (None, 'blue'),
                (None, '10.1.0.0/16'), (None, 'main', 'BGP'), (None, 'bgp', 'CONNECTED')):
            filters = dict(router=r, vrf=v, prefix=p, plane=pl, protocol=proto)
            self.assertEqual(rib.entries(**filters), scan_entries(rib, **filters))

    def test_all_covering_prefixes_and_duplicate_prefix_candidates_survive(self):
        entries = [route(str(i), prefix=p) for i, p in enumerate(
            ('0.0.0.0/0', '10.0.0.0/8', '10.1.0.0/16', '10.1.2.0/24',
             '10.1.2.0/24', '10.1.2.9/32', '10.1.3.0/24', '2001:db8::/32'))]
        entries += [route('local', prefix='10.1.2.9/32', protocol='LOCAL')]
        rib = SymbolicRib([], entries)
        for destination in ('10.1.2.9', '10.1.2.0/24', '10.1.0.0/16', '11.0.0.1', '2001:db8::1'):
            self.assertEqual(rib.forwarding_entries(router='r', vrf='default', destination=destination),
                             scan_forwarding(rib, 'r', 'default', destination))
        actual = rib.forwarding_entries(router='r', vrf='default', destination='10.1.2.9')
        self.assertEqual(len(actual), 6)
        self.assertEqual(sum(e.prefix == '10.1.2.0/24' for e in actual), 2)

    def test_ipv6_scope_and_host_bits_are_preserved(self):
        rib = SymbolicRib([], [route('v6default', prefix='::/0'),
            route('v6network', prefix='2001:db8::/32'), route('v6host', prefix='2001:db8:1::9/128'),
            route('v4', prefix='0.0.0.0/0'), route('blue', prefix='::/0', vrf='blue')])
        for destination in ('2001:db8:1::9', '2001:db8:1::9/64', '2002::1'):
            self.assertEqual(rib.forwarding_entries(router='r', vrf='default', destination=destination),
                             scan_forwarding(rib, 'r', 'default', destination))

    def test_empty_results_are_cached_and_caches_are_per_rib(self):
        a = SymbolicRib([], [route('a')]); b = SymbolicRib([], [route('b')])
        args = dict(router='missing', vrf='default', destination='10.1.0.1')
        self.assertEqual(a.forwarding_entries(**args), ())
        self.assertEqual(a.forwarding_entries(**args), ())
        self.assertEqual(a.query_cache_info()['forwarding']['hits'], 1)
        self.assertEqual(b.query_cache_info()['forwarding']['hits'], 0)
        a.clear_query_caches()
        self.assertEqual(a.query_cache_info()['forwarding']['currsize'], 0)
        self.assertEqual(a.forwarding_entries(**args), ())

    def test_context_reuses_complete_peer_ribs_across_current_branches(self):
        topology = NeighborTopology([NeighborLink(NeighborEndpoint('r', 'r0'), NeighborEndpoint('s', 's0'))])
        entries = [route('r1'), route('r2'), route('s1', router='s'),
                   route('s2', router='s', prefix='10.0.0.0/8')]
        rib = SymbolicRib([], entries, topology)
        a = rib.context(entries[0], destination='10.1.1.1')
        b = rib.context(entries[1], destination='10.1.1.1')
        self.assertIs(a.device_rib, b.device_rib)
        self.assertIs(a.peer_ribs, b.peer_ribs)
        self.assertEqual(len(a.peer_ribs['s']), 2)
        self.assertEqual(rib.query_cache_info()['context_ribs']['misses'], 1)
        self.assertEqual(rib.query_cache_info()['context_ribs']['hits'], 1)
        with self.assertRaises(TypeError):
            a.peer_ribs['s'] = ()

    def test_context_without_destination_keeps_exact_prefix_and_local_entries(self):
        entries = [route('a'), route('local', protocol='LOCAL'), route('short', prefix='10.0.0.0/8')]
        rib = SymbolicRib([], entries)
        context = rib.context(entries[0])
        self.assertEqual(context.device_rib, scan_entries(rib, router='r', vrf='default', prefix='10.1.0.0/16', plane='MAIN'))
        self.assertEqual(len(context.device_rib), 2)

    def test_predecessor_cache_uses_provenance_not_only_candidate_id(self):
        a = route('a', contributions=({'id': {'messageId': 'm1'}},))
        b = route('b', contributions=({'id': {'messageId': 'm2'}},))
        current = route('c', contributions=({'provenance': {'parentMessageId': 'm1'}},))
        rib = SymbolicRib([], [a, b, current])
        changed = replace(current, contributions=({'provenance': {'parentMessageId': 'm2'}},))
        self.assertEqual(rib.predecessor_entries(current), (a,))
        self.assertEqual(rib.predecessor_entries(changed), (b,))

    def test_bad_prefix_is_not_silently_ignored(self):
        rib = SymbolicRib([], [route('bad', prefix='invalid')])
        with self.assertRaisesRegex(SymbolicRouteFormatError, 'invalid prefix'):
            rib.forwarding_entries(router='r', vrf='default', destination='10.1.0.1')
        with self.assertRaisesRegex(SymbolicRouteFormatError, 'cannot parse'):
            rib.forwarding_entries(router='r', vrf='default', destination='invalid')
        # The original implementation never parsed unrelated scopes or LOCAL entries.
        rib = SymbolicRib([], [route('bad_other', router='other', prefix='invalid'),
                              route('local', prefix='invalid', protocol='LOCAL'), route('valid')])
        self.assertEqual([e.candidate_id for e in rib.forwarding_entries(router='r', vrf='default', destination='10.1.0.1')], ['valid'])

    def test_cache_bound_does_not_limit_query_results(self):
        rib = SymbolicRib([], [route('default', prefix='0.0.0.0/0')])
        for address in range(2055):
            result = rib.forwarding_entries(router='r', vrf='default', destination=str(ipaddress.IPv4Address(address)))
            self.assertEqual(len(result), 1)
        info = rib.query_cache_info()['forwarding']
        self.assertEqual(info['currsize'], info['maxsize'])
        self.assertEqual(len(rib.forwarding_entries(router='r', vrf='default', destination='0.0.0.0')), 1)

if __name__ == '__main__':
    unittest.main()
