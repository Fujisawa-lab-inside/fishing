#!/usr/bin/env python3

import ast
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "stage20_micro_adjustment_gate_local_q_sensitivity_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_micro_adjustment_gate_local_q_sensitivity_v1", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MicroAdjustmentGateLocalQSensitivityTest(unittest.TestCase):
    def test_contract_bindings_scope_and_boundary(self):
        contract = MODULE.read_and_verify_contract()
        self.assertEqual(contract["scope"]["requestedDischargeGridM3S"], [0.0, 6.0, 12.0, 18.0, 24.0])
        self.assertEqual(contract["scope"]["durationSeconds"], 60.0)
        self.assertIn("not a gate rating", contract["scope"]["physicalMeaning"])
        boundary = contract["decisionBoundary"]
        self.assertTrue(boundary["localOneStepAndShortDurationPermitted"])
        for key, value in boundary.items():
            if key != "localOneStepAndShortDurationPermitted":
                self.assertFalse(value, key)

    def test_real_context_one_step_grid_passes(self):
        report = MODULE.run_one_step_grid()
        self.assertEqual(report["status"], "PASS_LOCAL_UNCALIBRATED_Q_GRID_ONE_STEP_NOT_PHYSICAL")
        self.assertEqual(report["cellCount"], 28746)
        self.assertEqual([row["requestedDischargeM3S"] for row in report["cases"]], [0.0, 6.0, 12.0, 18.0, 24.0])
        self.assertTrue(report["cases"][0]["qZeroStateBitExact"])
        self.assertEqual(report["cases"][0]["effectiveDischargeM3S"], 0.0)
        self.assertTrue(all(row["negativeDepthCount"] == 0 for row in report["cases"]))
        self.assertTrue(all(row["nonFiniteValueCount"] == 0 for row in report["cases"]))
        self.assertTrue(all(abs(row["massResidualM3S"]) <= 1e-12 for row in report["cases"]))
        self.assertTrue(any(row["effectiveDischargeM3S"] > 0.0 for row in report["cases"][1:]))
        self.assertEqual(report["outputCreationCount"], 0)
        self.assertEqual(report["yodaConnectionCount"], 0)

    def test_module_has_no_remote_or_output_capability(self):
        tree = ast.parse(MODULE_PATH.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse(
            [name for name in imported if any(token in name.lower() for token in ("ssh", "paramiko", "fabric", "requests"))]
        )
        source = MODULE_PATH.read_text()
        self.assertNotIn("write_text(", source)
        self.assertNotIn("open(", source)

    def test_duration_report_if_present(self):
        report_path = ROOT / "docs/results/stage20-micro-adjustment-gate-local-q-sensitivity-v1/report.json"
        if not report_path.is_file():
            self.skipTest("duration report is created only after one-step gate passes")
        report = json.loads(report_path.read_text())
        self.assertEqual(report["status"], "PASS_LOCAL_60S_UNCALIBRATED_Q_SENSITIVITY_NOT_PHYSICAL")
        self.assertTrue(report["allCasesNumericallySafe"])
        self.assertFalse(report["physicalDischargeLawImplemented"])
        self.assertFalse(report["a8CombinedScenarioEvaluated"])
        self.assertEqual(report["yodaConnectionCount"], 0)
        for row in report["cases"]:
            self.assertEqual(row["simulatedSeconds"], 60.0)
            self.assertEqual(row["negativeDepthCount"], 0)
            self.assertEqual(row["nonFiniteValueCount"], 0)
            self.assertLessEqual(row["maximumRelativeMassBalanceError"], 1e-10)


if __name__ == "__main__":
    unittest.main()
