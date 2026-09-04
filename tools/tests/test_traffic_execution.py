import importlib.util
import pathlib
import sys
import unittest
from fractions import Fraction


SCRIPT = pathlib.Path(__file__).parents[1] / "traffic_execution.py"
SPEC = importlib.util.spec_from_file_location("traffic_execution", SCRIPT)
TRAFFIC = importlib.util.module_from_spec(SPEC)
sys.modules["traffic_execution"] = TRAFFIC
SPEC.loader.exec_module(TRAFFIC)


class TrafficExecutionMathTest(unittest.TestCase):
    def test_d_x_failure_induces_h_le_93(self):
        load = (Fraction(20), Fraction(4, 5))  # 20 + 0.8h
        interval = TRAFFIC._safe_interval(load, Fraction(95))
        self.assertEqual(interval, (0, 93))
        self.assertEqual(TRAFFIC.format_interval(interval, "h"), "h <= 93")

    def test_unrestricted_when_capacity_holds_for_all_h(self):
        load = (Fraction(80), Fraction(-4, 5))  # 80 - 0.8h
        interval = TRAFFIC._safe_interval(load, Fraction(95))
        self.assertEqual(interval, (0, 100))


if __name__ == "__main__":
    unittest.main()
