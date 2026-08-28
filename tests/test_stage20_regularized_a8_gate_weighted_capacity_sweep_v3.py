#!/usr/bin/env python3

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_regularized_a8_gate_weighted_capacity_sweep_v3 as sweep  # noqa: E402


REPORT_PATH = ROOT / "docs/results/stage20-regularized-a8-gate-weighted-capacity-sweep-v3/report.json"


class A8GateWeightedCapacitySweepTest(unittest.TestCase):
    def test_reuse_is_sha_bound_and_limited_to_three_unchanged_cases(self):
        cases = sweep.reusable_cases()
        self.assertEqual([row["targetA8Capacity"] for row in cases], [0.25, 0.5, 0.75])
        self.assertTrue(all(row["reusedFromV2ExactArtifact"] for row in cases))

    def test_build_report_does_not_claim_physical_adoption(self):
        full = {
            "targetA8Capacity": 1.0,
            "targetHeldThroughRequestedHold": True,
            "negativeDepthCount": 0,
            "nonFiniteValueCount": 0,
            "fishwayDischargeM3S": 0.0,
        }
        report = sweep.build_report(full)
        self.assertEqual(report["rerunTargetCapacities"], [1.0])
        self.assertTrue(report["allCasesNumericallySafe"])
        self.assertTrue(report["allCasesHeldThroughRequestedHold"])
        self.assertFalse(report["microAdjustmentGateHydraulicRepresentationIncluded"])
        self.assertFalse(report["regulatingMainGateRolePhysicalAdopted"])
        self.assertFalse(report["yodaLaunchPermitted"])
        self.assertFalse(report["releaseAuthorized"])

    def test_recorded_report_passes_all_four_local_cases(self):
        import json

        report = json.loads(REPORT_PATH.read_text())
        self.assertEqual(
            report["status"],
            "PASS_LOCAL_A8_GATE_WEIGHTED_SWEEP_NOT_PHYSICAL_LOW_FLOW_SCENARIO",
        )
        self.assertEqual(
            [row["targetA8Capacity"] for row in report["cases"]],
            [0.25, 0.5, 0.75, 1.0],
        )
        self.assertTrue(report["allCasesNumericallySafe"])
        self.assertTrue(report["allCasesHeldThroughRequestedHold"])
        self.assertTrue(all(not row["interlockEvents"] for row in report["cases"]))
        self.assertTrue(
            all(row["a8FluxAccounting"]["cumulativeLocalAdverseVolumeM3"] == 0.0 for row in report["cases"])
        )
        self.assertFalse(report["microAdjustmentGateHydraulicRepresentationIncluded"])
        self.assertFalse(report["yodaLaunchPermitted"])


if __name__ == "__main__":
    unittest.main()
