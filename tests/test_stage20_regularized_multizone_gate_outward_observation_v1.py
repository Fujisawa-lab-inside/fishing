#!/usr/bin/env python3

import sys
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_regularized_multizone_gate_observation_v1 as bound  # noqa: E402
import stage20_regularized_multizone_gate_outward_observation_v1 as outward  # noqa: E402


class OutwardGateObservationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = bound.load_bound_context()
        cls.state = np.load(cls.context["statePath"], allow_pickle=False)

    def test_a8_downstream_dry_face_is_recorded_but_outward_motion_is_trusted(self):
        report = outward.observe_per_gate_outward(self.state, self.context)
        gate8 = report["perGate"][7]
        self.assertGreater(gate8["minimumUpstreamSelectedFaceDepthM"], 0.2)
        self.assertLess(gate8["minimumDownstreamSelectedFaceDepthM"], 1.0e-4)
        self.assertGreater(gate8["minimumLocalHeadDifferenceM"], 0.19)
        self.assertEqual(gate8["downstreamDryOrNearDryFaceCount"], 1)
        self.assertTrue(gate8["trustedForPositiveMotionObservation"])
        self.assertFalse(report["downstreamDrynessAloneBlocksOutwardMotion"])
        self.assertFalse(report["localHeadReversalAloneBlocksOutwardMotion"])
        self.assertEqual(report["headTrustBasis"], "LENGTH_WEIGHTED_GATE_MEAN")
        self.assertTrue(report["gateNetFluxCheckStillRequired"])

    def test_dry_upstream_face_fails_closed(self):
        state = self.state.copy()
        gate8 = self.context["gateIds"] == 8
        state[self.context["upstream"][gate8][0], 0] = 0.0
        report = outward.observe_per_gate_outward(state, self.context)
        self.assertFalse(report["perGate"][7]["trustedForPositiveMotionObservation"])
        self.assertEqual(
            report["perGate"][7]["failClosedReason"],
            "DRY_OR_NEAR_DRY_UPSTREAM_SELECTED_FACE_SIDE",
        )

    def test_adverse_local_head_fails_closed(self):
        state = self.state.copy()
        gate8 = self.context["gateIds"] == 8
        upstream = self.context["upstream"][gate8]
        downstream = self.context["downstream"][gate8]
        state[downstream, 0] = state[upstream, 0] + 1.0
        report = outward.observe_per_gate_outward(state, self.context)
        self.assertFalse(report["perGate"][7]["trustedForPositiveMotionObservation"])
        self.assertEqual(
            report["perGate"][7]["failClosedReason"],
            "ADVERSE_OR_INSUFFICIENT_LOCAL_HEAD",
        )

    def test_one_local_head_reversal_is_recorded_but_gate_mean_controls(self):
        state = self.state.copy()
        gate8 = self.context["gateIds"] == 8
        upstream = self.context["upstream"][gate8][0]
        downstream = self.context["downstream"][gate8][0]
        upstream_eta = state[upstream, 0] + self.context["bed"][upstream]
        state[downstream, 0] = upstream_eta - self.context["bed"][downstream] + 1.0e-6
        report = outward.observe_per_gate_outward(state, self.context)
        gate = report["perGate"][7]
        self.assertLess(gate["minimumLocalHeadDifferenceM"], 0.0)
        self.assertGreater(gate["weightedMeanHeadDifferenceM"], 0.0)
        self.assertEqual(gate["adverseOrInsufficientLocalHeadFaceCount"], 1)
        self.assertTrue(gate["trustedForPositiveMotionObservation"])

    def test_positive_margin_is_explicit_and_can_block(self):
        report = outward.observe_per_gate_outward(
            self.state, self.context, minimum_outward_head_margin_m=0.25
        )
        self.assertEqual(report["minimumOutwardHeadMarginM"], 0.25)
        self.assertFalse(report["perGate"][7]["trustedForPositiveMotionObservation"])


if __name__ == "__main__":
    unittest.main()
