"""MAIN communities must come from the selected route's protocol."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = (Path(__file__).resolve().parents[2]
          / "auto-netsubspec-Traverse/0_auto-netsubspec/utils/util_route_community_bitvec.py")
SPEC = importlib.util.spec_from_file_location("traverse_main_community", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MainCommunityTest(unittest.TestCase):
    def encoder(self, communities=None):
        lookup = Mock(return_value=[
            SimpleNamespace(communities=["65050:10"] if communities is None else communities)
        ])
        host = SimpleNamespace(
            smt_var_prefix="0_",
            _smt_var_name=lambda name: "|" + name + "|",
            _is_bgp_family=lambda protocol: protocol.lower() in {"bgp", "ibgp"},
            get_all_bgp_info=lookup,
        )
        encoder = MODULE.BitVecCommunityEncoder(host)
        encoder.community_bit_width = 4
        encoder.community_to_index = {"65050:10": 0, "65050:99": 1}
        return encoder, lookup

    def test_non_bgp_main_ignores_same_prefix_bgp_advertisement(self):
        for protocol in ["connected", "static", "ospf"]:
            for count in [1, 2]:
                with self.subTest(protocol=protocol, routes=count):
                    encoder, lookup = self.encoder()
                    routes = [SimpleNamespace(protocol=protocol, network="5.5.5.5/32")
                              for _ in range(count)]
                    self.assertEqual(encoder.generate_community_variables("i", routes),
                                     {"|0_i_OVERALL_BEST_None_community|": "#b0000"})
                    self.assertEqual(encoder.generate_community_variables("i", routes, True),
                                     "(not (= |0_i_OVERALL_BEST_None_community| #b0000))")
                    lookup.assert_not_called()

    def test_bgp_and_ibgp_main_keep_communities(self):
        for protocol in ["bgp", "ibgp", "BGP"]:
            with self.subTest(protocol=protocol):
                encoder, lookup = self.encoder()
                routes = [SimpleNamespace(protocol=protocol, network="5.5.5.5/32")]
                self.assertEqual(encoder.generate_community_variables("t", routes),
                                 {"|0_t_OVERALL_BEST_None_community|": "#b0001"})
                self.assertEqual(encoder.generate_community_variables("t", routes, True),
                                 "(not (= |0_t_OVERALL_BEST_None_community| #b0001))")
                lookup.assert_called_with("t", "5.5.5.5/32")

    def test_bgp_ecmp_keeps_distinct_community_sets(self):
        encoder, lookup = self.encoder()
        lookup.return_value = [SimpleNamespace(communities=["65050:10"]),
                               SimpleNamespace(communities=["65050:99"])]
        routes = [SimpleNamespace(protocol="bgp", network="5.5.5.5/32") for _ in range(2)]
        normal = encoder.generate_community_variables("t", routes)["_overall_or_constraint"]
        self.assertIn("(= |0_t_OVERALL_BEST_None_community| #b0001)", normal)
        self.assertIn("(= |0_t_OVERALL_BEST_None_community| #b0010)", normal)
        self.assertEqual(encoder.generate_community_variables("t", routes, True),
                         "(not " + normal + ")")

    def test_no_main_route_has_empty_communities(self):
        encoder, lookup = self.encoder()
        self.assertEqual(encoder.generate_community_variables("i", []),
                         {"|0_i_OVERALL_BEST_None_community|": "#b0000"})
        self.assertEqual(encoder.generate_community_variables("i", [], True),
                         "(not (= |0_i_OVERALL_BEST_None_community| #b0000))")
        lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
