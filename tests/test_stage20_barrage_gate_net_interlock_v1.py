#!/usr/bin/env python3

import sys
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_barrage_gate_net_interlock_v1 as interlock  # noqa: E402


class GateNetInterlockTest(unittest.TestCase):
    def base(self):
        values = np.asarray([2.0, -0.1, 1.0, 1.0], dtype=np.float64)
        indices = np.asarray([2, 2, 3, 3], dtype=np.int64)
        requested = np.zeros(8, dtype=np.float64)
        requested[2:4] = 1.0
        latched = np.zeros(8, dtype=bool)
        margin = np.zeros(8, dtype=np.float64)
        return values, indices, requested, latched, margin

    def test_local_adverse_face_is_recorded_while_positive_gate_net_stays_open(self):
        result = interlock.apply_gate_net_interlock(*self.base())
        self.assertEqual(result["newTripGateIds"], [])
        self.assertEqual(result["effectiveCapacityByGateId1To8"][2], 1.0)
        gate3 = result["preInterlockGateDiagnostics"][2]
        self.assertEqual(gate3["adverseFaceCount"], 1)
        self.assertAlmostEqual(gate3["gateNetSignedOutwardDischargeM3S"], 1.9)
        self.assertFalse(result["localAdverseFaceFluxClipped"])

    def test_gate_with_negative_net_flux_latches_closed(self):
        values, indices, requested, latched, margin = self.base()
        values[:2] = [-2.0, 0.1]
        result = interlock.apply_gate_net_interlock(
            values, indices, requested, latched, margin
        )
        self.assertEqual(result["newTripGateIds"], [3])
        self.assertEqual(result["effectiveCapacityByGateId1To8"][2], 0.0)
        self.assertEqual(result["effectiveCapacityByGateId1To8"][3], 1.0)

    def test_positive_sensitivity_margin_can_close_before_zero(self):
        values, indices, requested, latched, margin = self.base()
        margin[2] = 2.0
        result = interlock.apply_gate_net_interlock(
            values, indices, requested, latched, margin
        )
        self.assertEqual(result["newTripGateIds"], [3])
        self.assertFalse(result["physicalOperatingMarginSelected"])

    def test_existing_latch_is_not_reopened(self):
        values, indices, requested, latched, margin = self.base()
        latched[2] = True
        result = interlock.apply_gate_net_interlock(
            values, indices, requested, latched, margin
        )
        self.assertEqual(result["newTripGateIds"], [])
        self.assertEqual(result["effectiveCapacityByGateId1To8"][2], 0.0)

    def test_closed_gate_faces_do_not_create_a_trip(self):
        values, indices, requested, latched, margin = self.base()
        requested[2] = 0.0
        values[:2] = [-100.0, -100.0]
        result = interlock.apply_gate_net_interlock(
            values, indices, requested, latched, margin
        )
        self.assertEqual(result["newTripGateIds"], [])
        self.assertEqual(
            result["preInterlockGateDiagnostics"][2]["gateNetSignedOutwardDischargeM3S"],
            0.0,
        )

    def test_invalid_margin_fails_closed(self):
        values, indices, requested, latched, margin = self.base()
        margin[2] = -0.1
        with self.assertRaisesRegex(ValueError, "must be nonnegative"):
            interlock.apply_gate_net_interlock(
                values, indices, requested, latched, margin
            )


if __name__ == "__main__":
    unittest.main()
