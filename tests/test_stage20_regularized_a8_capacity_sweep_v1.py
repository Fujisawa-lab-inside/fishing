#!/usr/bin/env python3

import sys
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_regularized_a8_capacity_sweep_v1 as sweep  # noqa: E402


class A8CapacitySweepTest(unittest.TestCase):
    def test_schedule_only_moves_a8_with_smooth_ramp(self):
        start = sweep.requested_a8_capacity(0.0, 0.5)
        middle = sweep.requested_a8_capacity(150.0, 0.5)
        end = sweep.requested_a8_capacity(300.0, 0.5)
        self.assertEqual(start.tolist(), [0.0] * 8)
        self.assertEqual(middle[:7].tolist(), [0.0] * 7)
        self.assertAlmostEqual(middle[7], 0.25)
        self.assertEqual(end.tolist(), [0.0] * 7 + [0.5])

    def test_invalid_target_is_rejected(self):
        for value in (0.0, -0.1, 1.1, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sweep.requested_a8_capacity(0.0, value)

    def test_summary_distinguishes_held_and_closed(self):
        raw = {
            "effectiveFinalCapacityByGateId1To8": [0.0] * 7 + [0.5],
            "simulatedSeconds": 600.0,
            "acceptedSteps": 1,
            "wallSeconds": 1.0,
            "maximumCfl": 0.1,
            "maximumRelativeMassBalanceError": 0.0,
            "interlockEvents": [],
            "gateFluxAccounting": [{"gateId": gate} for gate in range(1, 9)],
            "negativeDepthCount": 0,
            "nonFiniteValueCount": 0,
            "fishwayDischargeM3S": 0.0,
        }
        held = sweep.summarize_case(raw, 0.5)
        self.assertTrue(held["targetHeldThroughRequestedHold"])
        raw["effectiveFinalCapacityByGateId1To8"][-1] = 0.0
        closed = sweep.summarize_case(raw, 0.5)
        self.assertFalse(closed["targetHeldThroughRequestedHold"])

    def test_one_step_fails_closed_a8_before_numerical_problem(self):
        context = sweep.gate_net_probe.prescribed.load_runtime_context()
        forcing = sweep.gate_net_probe.prescribed.matched.base.read_json(
            sweep.gate_net_probe.prescribed.FORCING_PATH
        )
        latched = np.zeros(8, dtype=bool)
        with sweep._a8_schedule(0.5):
            step, guard = sweep.gate_net_probe.advance_one_step(
                context["state"], context, forcing, 150.0, 0.05, latched
            )
        self.assertTrue(np.isfinite(step.next_state).all())
        self.assertEqual(step.effective_fishway_discharge_m3_s, 0.0)
        self.assertEqual(step.fishway_source_residual_m3_s, 0.0)
        active = [row["gateId"] for row in guard["effectivePerGate"] if row["active"]]
        self.assertEqual(active, [])
        self.assertEqual(guard["newWetnessTripGateIds"], [8])
        self.assertEqual(guard["newNetReverseTripGateIds"], [])

    def test_full_sweep_is_skipped_when_initial_a8_is_untrusted(self):
        report = sweep.run_sweep()
        self.assertEqual(report["status"], "BLOCKED_LOCAL_A8_NEAR_DRY_GEOMETRY_NO_SWEEP")
        self.assertEqual(report["cases"], [])
        self.assertEqual(report["numericalAdvanceCount"], 0)
        self.assertEqual(report["sweepRunCount"], 0)
        self.assertEqual(report["a8InitialObservation"]["gateId"], 8)
        self.assertFalse(
            report["a8InitialObservation"]["trustedForPositiveMotionObservation"]
        )


if __name__ == "__main__":
    unittest.main()
