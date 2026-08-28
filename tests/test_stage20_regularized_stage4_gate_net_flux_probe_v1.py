from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_regularized_stage4_gate_net_flux_probe_v1.py"
SPEC = importlib.util.spec_from_file_location("stage4_gate_net_flux_probe_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class Stage4GateNetFluxProbeV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = PROBE.prescribed.load_runtime_context()

    def test_nominal_mid_ramp_all_stage4_gate_totals_are_outward(self) -> None:
        latched = np.zeros(8, dtype=bool)
        result = PROBE.prepare_gate_step(
            self.context["state"], self.context, 150.0, latched
        )
        active = [row for row in result["effectivePerGate"] if row["active"]]
        self.assertEqual([row["gateId"] for row in active], [3, 4, 5, 6])
        self.assertTrue(all(row["totalSignedOutwardDischargeM3S"] > 0.0 for row in active))
        self.assertEqual(result["newNetReverseTripGateIds"], [])

    def test_local_micro_reverse_with_positive_gate_total_does_not_close(self) -> None:
        workspace = self.context["workspace"]
        gate_index = workspace["gateIndexBySelectedFace"]
        synthetic = np.zeros(len(gate_index), dtype=np.float64)
        active = np.isin(gate_index, [2, 3, 4, 5])
        synthetic[active] = 1.0
        gate6 = np.flatnonzero(gate_index == 5)
        synthetic[gate6[0]] = -1.0e-4
        latched = np.zeros(8, dtype=bool)
        with mock.patch.object(
            PROBE.flux_adapter,
            "signed_outward_gate_discharge_m3_s",
            return_value=synthetic,
        ):
            result = PROBE.prepare_gate_step(
                self.context["state"], self.context, 600.0, latched
            )
        self.assertEqual(result["newNetReverseTripGateIds"], [])
        self.assertFalse(latched.any())
        gate6_row = result["effectivePerGate"][5]
        self.assertEqual(gate6_row["adverseFaceCount"], 1)
        self.assertGreater(gate6_row["totalSignedOutwardDischargeM3S"], 0.0)

    def test_gate_net_reverse_latches_only_affected_gate(self) -> None:
        workspace = self.context["workspace"]
        gate_index = workspace["gateIndexBySelectedFace"]
        synthetic = np.zeros(len(gate_index), dtype=np.float64)
        active = np.isin(gate_index, [2, 3, 4, 5])
        synthetic[active] = 1.0
        synthetic[gate_index == 5] = -1.0
        latched = np.zeros(8, dtype=bool)
        calls = [synthetic, np.where(gate_index == 5, 0.0, synthetic)]
        with mock.patch.object(
            PROBE.flux_adapter,
            "signed_outward_gate_discharge_m3_s",
            side_effect=calls,
        ):
            result = PROBE.prepare_gate_step(
                self.context["state"], self.context, 600.0, latched
            )
        self.assertEqual(result["newNetReverseTripGateIds"], [6])
        self.assertEqual((np.flatnonzero(latched) + 1).tolist(), [6])
        self.assertEqual(result["effectiveCapacity"].tolist(), [0, 0, 1, 1, 1, 0, 0, 0])

    def test_one_step_keeps_fishway_zero(self) -> None:
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
