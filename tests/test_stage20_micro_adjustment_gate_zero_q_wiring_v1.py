#!/usr/bin/env python3

import ast
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/stage20_micro_adjustment_gate_zero_q_wiring_v1.py"
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("stage20_micro_adjustment_gate_zero_q_wiring_v1", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MicroAdjustmentGateZeroQWiringTest(unittest.TestCase):
    def test_contract_bindings_and_boundary(self):
        contract = MODULE.read_and_verify_contract()
        self.assertEqual(contract["invariants"]["requestedDischargeM3S"], 0.0)
        boundary = contract["decisionBoundary"]
        self.assertTrue(boundary["zeroQOneStepWiringPermitted"])
        for key, value in boundary.items():
            if key != "zeroQOneStepWiringPermitted":
                self.assertFalse(value, key)

    def test_real_context_zero_q_is_bit_exact(self):
        report = MODULE.run_zero_q_one_step_equivalence()
        self.assertEqual(report["status"], "PASS_LOCAL_ZERO_Q_REAL_CONTEXT_ONE_STEP_BIT_EXACT")
        self.assertEqual(report["cellCount"], 28746)
        self.assertGreater(report["donorCellCount"], 0)
        self.assertGreater(report["receiverCellCount"], 0)
        self.assertEqual(report["sourceNonzeroCount"], 0)
        self.assertTrue(report["inputStateBitExact"])
        self.assertTrue(report["oneStepStateBitExact"])
        self.assertTrue(report["oneStepScalarsBitExact"])
        self.assertFalse(report["nonzeroDischargeConnectionPermitted"])

    def test_module_cannot_request_nonzero_flow(self):
        tree = ast.parse(MODULE_PATH.read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        transfer_calls = [
            node for node in calls
            if isinstance(node.func, ast.Attribute)
            and node.func.attr == "apply_authorized_outward_transfer"
        ]
        self.assertEqual(len(transfer_calls), 1)
        keywords = {row.arg: row.value for row in transfer_calls[0].keywords}
        value = keywords["requested_outward_discharge_m3_s"]
        self.assertIsInstance(value, ast.Constant)
        self.assertEqual(value.value, 0.0)

    def test_no_remote_or_output_capability(self):
        tree = ast.parse(MODULE_PATH.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse(
            [
                name for name in imported
                if any(token in name.lower() for token in ("ssh", "paramiko", "fabric", "requests"))
            ]
        )
        source = MODULE_PATH.read_text()
        self.assertNotIn("write_text(", source)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
