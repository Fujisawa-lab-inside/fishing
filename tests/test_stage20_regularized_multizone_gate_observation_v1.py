from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_regularized_multizone_gate_observation_v1.py"
SPEC = importlib.util.spec_from_file_location("regularized_gate_observation_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegularizedGateObservationV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = MODULE.load_bound_context()
        cls.report = MODULE.build_report()

    def test_bound_candidate_geometry_and_orientation_pass(self) -> None:
        self.assertEqual(len(self.context["gateFaces"]), 61)
        self.assertEqual(len(np.unique(self.context["gateIds"])), 8)
        self.assertEqual(self.report["decision"]["observationBindingPass"], True)

    def test_initial_all_gates_are_wet(self) -> None:
        observation = self.report["initialObservation"]
        self.assertEqual(observation["trustedGateIds"], list(range(1, 9)))
        self.assertEqual(observation["failClosedGateIds"], [])

    def test_900s_gate8_only_fails_closed_for_near_dry_face(self) -> None:
        observation = self.report["allClosed900sObservation"]
        self.assertEqual(observation["failClosedGateIds"], [8])
        self.assertFalse(observation["globalAllGateShutdownRequired"])
        gate8 = observation["perGate"][7]
        self.assertLess(gate8["minimumSelectedFaceSideDepthM"], 0.0001)

    def test_stage4_requested_gates_remain_observation_ready(self) -> None:
        stage4 = self.report["stage4DiagnosticRequest"]
        self.assertTrue(stage4["allRequestedGatesHaveTrustedHeadObservation"])
        self.assertEqual(stage4["requestedCapacityByGateId1To8"], stage4["nearDryFilteredCapacityByGateId1To8"])

    def test_near_dry_filter_cannot_open_untrusted_gate(self) -> None:
        observation = self.report["allClosed900sObservation"]
        filtered = MODULE.fail_closed_requested_capacity(np.ones(8), observation)
        np.testing.assert_array_equal(filtered, [1, 1, 1, 1, 1, 1, 1, 0])

    def test_no_runtime_authority_is_claimed(self) -> None:
        decision = self.report["decision"]
        self.assertFalse(decision["runtimeMotionAuthorized"])
        self.assertFalse(decision["forecastEvidenceAvailable"])
        self.assertFalse(decision["meshOperationallyAdopted"])


if __name__ == "__main__":
    unittest.main()
