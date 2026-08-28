#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_micro_adjustment_gate_transfer_primitive_v1 as transfer


CONTRACT_PATH = ROOT / "config/stage20_micro_adjustment_gate_transfer_primitive_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MicroAdjustmentGateTransferPrimitiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text())
        p = cls.contract["safetyParameters"]
        cls.safety = transfer.TransferSafety(
            reserve_depth_m=p["reserveDepthM"],
            maximum_available_volume_fraction_per_step=p[
                "maximumAvailableVolumeFractionPerStep"
            ],
            adverse_head_shutdown_m=p["adverseHeadShutdownM"],
        )
        cls.state = np.asarray(
            [[1.0, 0.2, -0.1], [0.5, -0.1, 0.05], [0.1, 0.0, 0.0], [0.2, 0.0, 0.0]],
            dtype=np.float64,
        )
        cls.areas = np.asarray([10.0, 20.0, 30.0, 40.0])
        cls.donors = np.asarray([True, True, False, False])
        cls.receivers = np.asarray([0.0, 0.0, 0.25, 0.75])

    def apply(self, **overrides):
        inputs = {
            "state_h_hu_hv": self.state,
            "cell_areas_m2": self.areas,
            "upstream_donor_mask": self.donors,
            "downstream_receiver_weights": self.receivers,
            "time_step_s": 0.1,
            "requested_outward_discharge_m3_s": 5.0,
            "head_difference_m": 0.1,
            "safety": self.safety,
        }
        inputs.update(overrides)
        return transfer.apply_authorized_outward_transfer(**inputs)

    def test_contract_binding_and_fail_closed_boundary(self):
        binding = self.contract["binding"]["readiness"]
        self.assertEqual(sha256(ROOT / binding["path"]), binding["sha256"])
        boundary = self.contract["decisionBoundary"]
        self.assertTrue(boundary["pureNumericalPrimitiveReady"])
        for key, value in boundary.items():
            if key != "pureNumericalPrimitiveReady":
                self.assertFalse(value, key)

    def test_available_volume_limit_and_exact_mass_conservation(self):
        before = self.state.copy()
        result = self.apply()
        diagnostics = result["diagnostics"]
        self.assertAlmostEqual(diagnostics["availableDonorVolumeM3"], 18.5)
        self.assertAlmostEqual(diagnostics["effectiveOutwardDischargeM3S"], 3.7)
        self.assertLessEqual(abs(diagnostics["massResidualM3S"]), 1e-12)
        self.assertAlmostEqual(
            diagnostics["maximumAvailableVolumeFractionRemoved"], 0.02
        )
        self.assertGreaterEqual(np.min(result["postSourceDepthM"]), 0.0)
        np.testing.assert_array_equal(self.state, before)

    def test_adverse_head_shutdown_and_transition(self):
        stopped = self.apply(head_difference_m=-0.03)
        self.assertEqual(stopped["diagnostics"]["adverseHeadFactor"], 0.0)
        self.assertEqual(stopped["diagnostics"]["effectiveOutwardDischargeM3S"], 0.0)
        transition = self.apply(
            head_difference_m=-0.01,
            requested_outward_discharge_m3_s=1.0,
        )
        self.assertAlmostEqual(transition["diagnostics"]["adverseHeadFactor"], 0.5)
        self.assertAlmostEqual(transition["diagnostics"]["effectiveOutwardDischargeM3S"], 0.5)

    def test_discharge_is_external_not_inferred_from_width(self):
        diagnostics = self.apply(
            requested_outward_discharge_m3_s=1.234
        )["diagnostics"]
        self.assertAlmostEqual(diagnostics["effectiveOutwardDischargeM3S"], 1.234)
        self.assertTrue(diagnostics["requestedDischargeAuthorityExternal"])
        self.assertFalse(diagnostics["physicalDischargeLawImplemented"])
        self.assertFalse(diagnostics["gateWidthUsedToInferDischarge"])

    def test_receiver_and_donor_overlap_fails_closed(self):
        with self.assertRaises(transfer.MicroAdjustmentGateTransferError):
            self.apply(
                downstream_receiver_weights=np.asarray([0.1, 0.0, 0.2, 0.7])
            )

    def test_invalid_inputs_fail_closed(self):
        for overrides in (
            {"requested_outward_discharge_m3_s": -1.0},
            {"time_step_s": 0.0},
            {"head_difference_m": float("nan")},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(transfer.MicroAdjustmentGateTransferError):
                    self.apply(**overrides)


if __name__ == "__main__":
    unittest.main()
