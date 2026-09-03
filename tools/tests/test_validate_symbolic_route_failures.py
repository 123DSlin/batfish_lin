import importlib.util
import json
import pathlib
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "validate_symbolic_route_failures.py"
SPEC = importlib.util.spec_from_file_location("validate_symbolic_route_failures", SCRIPT)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def variable(name):
    return {"operator": "VARIABLE", "variableId": name, "children": []}


def negate(ast):
    return {"operator": "NOT", "children": [ast]}


def true_guard():
    return {"operator": "TRUE", "children": []}


def sr_record(candidate, selection_ast):
    return {
        "kind": "FORWARDING_BRANCH",
        "node": "r1",
        "vrf": "default",
        "color": 100,
        "endpoint": "2.2.2.2",
        "policy": "to-r2",
        "candidate": candidate,
        "preference": 100,
        "weight": 1,
        "segmentList": candidate,
        "labels": [16002],
        "nextHops": ["r2/default/Ethernet0"],
        "linkDependencies": [],
        "terminalNode": "r2",
        "terminalVrf": "default",
        "selectionGuardAst": selection_ast,
    }


class ValidateSymbolicRouteFailuresTest(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._temporary.name)
        self.base = self.root / "base"
        self.failed = self.root / "failed"
        self.base.mkdir()
        self.failed.mkdir()

        route_ast = variable("r1_r2")
        control_plane = {
            "schemaName": VALIDATOR.CONTROL_PLANE_SCHEMA,
            "schemaVersion": VALIDATOR.CONTROL_PLANE_VERSION,
            "guardVariables": [
                {
                    "variableId": "r1_r2",
                    "kind": "LINK_AVAILABILITY",
                    "polarity": "UP",
                    "link": {"firstRouter": "r1", "secondRouter": "r2"},
                }
            ],
            "candidates": [
                {
                    "plane": "MAIN",
                    "router": "r1",
                    "vrf": "default",
                    "prefix": "10.0.0.0/24",
                    "protocol": "CONNECTED",
                    "route": {
                        "attributes": {
                            "nextHopInterface": "Ethernet0",
                            "nextHopIp": "AUTO/NONE(-1l)",
                            "administrativeCost": 0,
                            "tag": -1,
                        }
                    },
                    "selectionGuard": {"ast": route_ast},
                }
            ],
        }
        self._write_json(self.base / VALIDATOR.CONTROL_PLANE_FILE, control_plane)

        base_sr = self._sr_export(
            [sr_record("primary", route_ast), sr_record("backup", negate(route_ast))]
        )
        failed_sr = self._sr_export([sr_record("backup", true_guard())])
        self._write_json(self.base / VALIDATOR.SR_POLICY_FILE, base_sr)
        self._write_json(self.failed / VALIDATOR.SR_POLICY_FILE, failed_sr)
        self._write_data_plane(
            self.base,
            "r1 default 10.0.0.0/24 connected AUTO/NONE(-1l) Ethernet0 null 0 0 -\n",
        )
        self._write_data_plane(self.failed, "")

    def tearDown(self):
        self._temporary.cleanup()

    @staticmethod
    def _write_json(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def _sr_export(records):
        return {
            "schemaName": VALIDATOR.SR_POLICY_SCHEMA,
            "schemaVersion": VALIDATOR.SR_POLICY_VERSION,
            "guardVariables": [
                {
                    "variableId": "r1_r2",
                    "kind": "LINK_AVAILABILITY",
                    "polarity": "UP",
                    "link": {"firstRouter": "r1", "secondRouter": "r2"},
                }
            ],
            "records": records,
        }

    @staticmethod
    def _write_data_plane(directory, rows):
        header = "Node VRF Network Protocol NextHopIP NextHopInterface NextHop Metric AD Tag\n"
        (directory / VALIDATOR.DATA_PLANE_FILE).write_text(
            header + "=" * 80 + "\n" + rows, encoding="utf-8"
        )

    def test_all_up_and_one_link_failure_match(self):
        exit_code = VALIDATOR.main(
            [
                "--base",
                str(self.base),
                "--scenario",
                "all-up={}".format(self.base),
                "--scenario",
                "r1-r2={}".format(self.failed),
                "--down",
                "r1-r2=r1_r2",
            ]
        )
        self.assertEqual(exit_code, 0)

    def test_guard_ast_uses_explicit_assignment(self):
        ast = {"operator": "AND", "children": [variable("a"), negate(variable("b"))]}
        self.assertTrue(VALIDATOR._evaluate_guard(ast, {"a": True, "b": False}))
        self.assertFalse(VALIDATOR._evaluate_guard(ast, {"a": True, "b": True}))


if __name__ == "__main__":
    unittest.main()
