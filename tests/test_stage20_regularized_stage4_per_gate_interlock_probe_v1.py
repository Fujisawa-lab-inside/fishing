from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_regularized_stage4_per_gate_interlock_probe_v1.py"
SPEC = importlib.util.spec_from_file_location("stage4_per_gate_interlock_probe_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class Stage4PerGateInterlockProbeV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = PROBE.prescribed.load_runtime_context()

    def test_nominal_mid_ramp_keeps_stage4_gates_available(self) -> None:
        latched = np.zeros(8, dtype=bool)
        result = PROBE.prepare_interlocked_gate_step(
            self.context["state"], self.context, 150.0, latched
        )
        self.assertEqual(result["newReverseTripGateIds"], [])
        self.assertEqual(result["newWetnessTripGateIds"], [])
        self.assertEqual(result["effectiveCapacity"].tolist(), [0, 0, 0.5, 0.5, 0.5, 0.5, 0, 0])
        self.assertFalse(latched.any())

    def test_adverse_faces_latch_affected_gates_before_step(self) -> None:
        state = self.context["state"].copy()
        selected = np.isin(self.context["gate"]["gateIds"], [3, 4, 5, 6])
        downstream = np.unique(self.context["gate"]["downstream"][selected])
        state[downstream, 0] += 0.30
        latched = np.zeros(8, dtype=bool)
        result = PROBE.prepare_interlocked_gate_step(
            state, self.context, 150.0, latched
        )
        self.assertEqual(result["newReverseTripGateIds"], [3, 4, 5, 6])
        self.assertEqual(
            [row["gateId"] for row in result["preTripGateDiagnostics"]],
            [3, 4, 5, 6],
        )
        self.assertTrue(
            all(row["totalSignedOutwardDischargeM3S"] < 0.0 for row in result["preTripGateDiagnostics"])
        )
        self.assertEqual(result["effectiveCapacity"].tolist(), [0.0] * 8)
        self.assertEqual((np.flatnonzero(latched) + 1).tolist(), [3, 4, 5, 6])
        self.assertEqual(result["validation"]["activeFaceCount"], 0)

    def test_latched_gate_cannot_reopen(self) -> None:
        latched = np.asarray([False, False, False, False, False, True, False, False])
        result = PROBE.prepare_interlocked_gate_step(
            self.context["state"], self.context, 600.0, latched
        )
        self.assertEqual(result["effectiveCapacity"].tolist(), [0, 0, 1, 1, 1, 0, 0, 0])
        self.assertTrue(latched[5])

    def test_one_step_preserves_fishway_zero(self) -> None:
        forcing = PROBE.prescribed.matched.base.read_json(PROBE.prescribed.FORCING_PATH)
        latched = np.zeros(8, dtype=bool)
        step, _ = PROBE.advance_one_step(
            self.context["state"], self.context, forcing, 150.0, 0.05, latched
        )
        self.assertEqual(step.effective_fishway_discharge_m3_s, 0.0)
        self.assertEqual(step.fishway_source_residual_m3_s, 0.0)
        self.assertTrue(np.isfinite(step.next_state).all())


if __name__ == "__main__":
    unittest.main()
