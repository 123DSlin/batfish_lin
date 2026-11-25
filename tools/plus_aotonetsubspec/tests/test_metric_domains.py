"""Exported domain assumptions remain explicit and do not rewrite old formulas."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from property_model import METRIC_DOMAIN_FILE, load_metric_domains, load_property_model
from property_regions import full_model
from utils.util_symbolic import SubspecificationError


def modern_policy():
    return dict(schema='batfish-smt-metric-domains', version=1,
                bgp_as_path_length='nonnegative-integer', bgp_only_best='nonnegative-integer',
                environment_exclusive_upper_bound=256, other_metric_exclusive_upper_bound=65536,
                model_overflow=False)


class MetricDomainMetadataTest(unittest.TestCase):
    def test_missing_metadata_is_explicitly_unannotated(self):
        with tempfile.TemporaryDirectory() as directory:
            policy = load_metric_domains(Path(directory))
            self.assertEqual(policy['bgp_as_path_length'], 'unspecified')
            self.assertEqual(policy['version'], 0)

    def test_modern_policy_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/METRIC_DOMAIN_FILE).write_text(json.dumps(modern_policy()))
            self.assertEqual(load_metric_domains(path), modern_policy())

    def test_malformed_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/METRIC_DOMAIN_FILE).write_text('{')
            with self.assertRaises(SubspecificationError):
                load_metric_domains(path)

    def test_future_versions_and_wrong_types_are_rejected(self):
        variants = [dict(version=2), dict(version=True), dict(version=1.0),
                    dict(model_overflow='false'), dict(environment_exclusive_upper_bound=True)]
        for change in variants:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                (path/METRIC_DOMAIN_FILE).write_text(json.dumps({**modern_policy(), **change}))
                with self.assertRaises(SubspecificationError):
                    load_metric_domains(path)

    def test_optional_overflow_policy_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/METRIC_DOMAIN_FILE).write_text(json.dumps({**modern_policy(), 'model_overflow':True}))
            self.assertTrue(load_metric_domains(path)['model_overflow'])

    def test_legacy_native_bounds_are_not_relaxed_by_loader(self):
        work = ROOT/'example_results/demo1_c_only/all_configs/input'
        model = full_model(load_property_model(work, 2), work)
        self.assertEqual(model.metric_domains['bgp_as_path_length'], 'unspecified')
        bounds = [expression for expression in model.document.assertions
                  if isinstance(expression,list) and len(expression)==3 and expression[0]=='<'
                  and str(expression[1]).endswith('_metric|') and expression[2]=='65536']
        self.assertTrue(bounds)

    def test_unrecognized_policy_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/METRIC_DOMAIN_FILE).write_text(json.dumps({**modern_policy(), 'bgp_as_path_length':'uint16'}))
            with self.assertRaises(SubspecificationError):
                load_metric_domains(path)
