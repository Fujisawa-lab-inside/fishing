#!/usr/bin/env python3

import sys
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_regularized_a8_directional_capacity_sweep_v2 as sweep  # noqa: E402


class A8DirectionalCapacitySweepTest(unittest.TestCase):
    def test_initial_a8_observation_allows_outward_motion(self):
        row = sweep.initial_a8_observation()
        self.assertTrue(row["trustedForPositiveMotionObservation"])
        self.assertEqual(row["downstreamDryOrNearDryFaceCount"], 1)
        self.assertGreater(row["minimumLocalHeadDifferenceM"], 0.19)

    def test_one_step_keeps_a8_active_and_gate_net_outward(self):
        context = sweep.v1.gate_net_probe.prescribed.load_runtime_context()
        forcing = sweep.v1.gate_net_probe.prescribed.matched.base.read_json(
            sweep.v1.gate_net_probe.prescribed.FORCING_PATH
        )
        latched = np.zeros(8, dtype=bool)
        with sweep.directional_a8_schedule(0.5):
            step, guard = sweep.v1.gate_net_probe.advance_one_step(
                context["state"], context, forcing, 150.0, 0.05, latched
            )
        active = [row for row in guard["effectivePerGate"] if row["active"]]
        self.assertEqual([row["gateId"] for row in active], [8])
        self.assertGreater(active[0]["totalSignedOutwardDischargeM3S"], 0.0)
        self.assertEqual(guard["newWetnessTripGateIds"], [])
        self.assertEqual(guard["newNetReverseTripGateIds"], [])
        self.assertEqual(step.effective_fishway_discharge_m3_s, 0.0)
        self.assertTrue(np.isfinite(step.next_state).all())

    def test_context_manager_restores_original_functions(self):
        original_request = sweep.v1.gate_net_probe.prescribed.requested_capacity
        original_observe = sweep.v1.gate_net_probe.observation.observe_per_gate
        with sweep.directional_a8_schedule(0.25):
            self.assertIsNot(sweep.v1.gate_net_probe.prescribed.requested_capacity, original_request)
            self.assertIs(sweep.v1.gate_net_probe.observation.observe_per_gate, sweep.outward.observe_per_gate_outward)
        self.assertIs(sweep.v1.gate_net_probe.prescribed.requested_capacity, original_request)
        self.assertIs(sweep.v1.gate_net_probe.observation.observe_per_gate, original_observe)


if __name__ == "__main__":
    unittest.main()
