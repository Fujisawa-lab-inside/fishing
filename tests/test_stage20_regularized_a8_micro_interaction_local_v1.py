#!/usr/bin/env python3

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "stage20_regularized_a8_micro_interaction_local_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_regularized_a8_micro_interaction_local_v1", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegularizedA8MicroInteractionLocalTest(unittest.TestCase):
    def test_contract_scope_bindings_and_fail_closed_boundary(self):
        contract = MODULE.read_and_verify_contract()
        self.assertEqual(contract["scope"]["newA8TargetCapacityGrid"], [0.5, 1.0])
        self.assertEqual(contract["scope"]["microCommandGridM3S"], [0.0, 12.0, 24.0])
        self.assertEqual(contract["scope"]["newCaseCount"], 6)
        self.assertEqual(contract["scope"]["durationSeconds"], 60.0)
        self.assertEqual(contract["scope"]["initialStateRawSha256"], MODULE.INITIAL_STATE_RAW_SHA256)
        self.assertEqual(contract["precanonicalDiagnostic"]["discardedRunCount"], 1)
        self.assertFalse(contract["precanonicalDiagnostic"]["resultAdopted"])
        self.assertFalse(contract["decisionBoundary"]["yodaLaunchPermitted"])
        self.assertFalse(contract["decisionBoundary"]["pushAuthorized"])
        self.assertFalse(contract["decisionBoundary"]["releaseAuthorized"])

    def test_three_a8_zero_cases_are_reused_without_recalculation(self):
        rows = MODULE.reused_a8_zero_cases()
        self.assertEqual([(row["targetA8Capacity"], row["requestedMicroDischargeM3S"]) for row in rows], [(0.0, 0.0), (0.0, 12.0), (0.0, 24.0)])
        self.assertTrue(all(row["reusedWithoutRecalculation"] for row in rows))

    def test_real_context_six_case_one_step_grid_passes(self):
        report = MODULE.run_one_step_grid()
        self.assertEqual(report["status"], "PASS_LOCAL_SIX_CASE_ONE_STEP_INTERACTION_NOT_PHYSICAL")
        self.assertEqual(len(report["cases"]), 6)
        self.assertTrue(report["allCasesSafe"])
        self.assertTrue(all(row["negativeDepthCount"] == 0 for row in report["cases"]))
        self.assertTrue(all(row["nonFiniteValueCount"] == 0 for row in report["cases"]))
        self.assertTrue(all(abs(row["sourceMassResidualM3S"]) <= 1e-12 for row in report["cases"]))
        self.assertTrue(all(row["qZeroStateBitExact"] for row in report["cases"] if row["requestedMicroDischargeM3S"] == 0.0))
        self.assertEqual(report["outputCreationCount"], 0)
        self.assertEqual(report["yodaConnectionCount"], 0)

    def test_combined_runtime_uses_same_initial_state_as_reused_cases(self):
        context, _ = MODULE._load_context()
        actual = hashlib.sha256(context["state"].tobytes()).hexdigest()
        self.assertEqual(actual, MODULE.INITIAL_STATE_RAW_SHA256)

    def test_module_has_no_remote_or_output_capability(self):
        tree = ast.parse(MODULE_PATH.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse([name for name in imported if any(token in name.lower() for token in ("ssh", "paramiko", "fabric", "requests"))])
        source = MODULE_PATH.read_text()
        self.assertNotIn("write_text(", source)
        self.assertNotIn("open(", source)

    def test_duration_report_if_present(self):
        report_path = ROOT / "docs/results/stage20-regularized-a8-micro-interaction-local-v1/report.json"
        if not report_path.is_file():
            self.skipTest("duration report is recorded only after one-step gate passes")
        report = json.loads(report_path.read_text())
        self.assertEqual(report["status"], "PASS_LOCAL_SPARSE_A8_MICRO_INTERACTION_NUMERICALLY_SAFE_NOT_PHYSICAL")
        self.assertEqual(report["reusedCaseCount"], 3)
        self.assertEqual(report["newlyRunCaseCount"], 6)
        self.assertEqual(len(report["cases"]), 9)
        self.assertTrue(report["allCasesNumericallySafe"])
        self.assertFalse(report["physicalA8ScheduleApproved"])
        self.assertFalse(report["physicalMicroDischargeLawApproved"])
        self.assertEqual(report["yodaConnectionCount"], 0)


if __name__ == "__main__":
    unittest.main()
