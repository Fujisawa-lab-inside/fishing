from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_regularized_multizone_gate_flux_guard_v1.py"
SPEC = importlib.util.spec_from_file_location("regularized_gate_flux_guard_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegularizedGateFluxGuardV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = MODULE.build_report()

    def test_stage4_outward_flux_is_monotonic_through_ramp(self) -> None:
        ramp = self.report["stage4OutwardRamp"]
        self.assertTrue(ramp["totalOutwardDischargeMonotonic"])
        self.assertTrue(ramp["allActiveFaceFluxOutward"])
        totals = [row["totalSignedOutwardDischargeM3S"] for row in ramp["rows"]]
        self.assertEqual(totals[0], 0.0)
        self.assertGreater(totals[-1], totals[1])

    def test_adverse_head_is_rejected_without_clipping(self) -> None:
        adverse = self.report["adverseHeadProbe"]
        self.assertEqual(adverse["adverseFaceCount"], adverse["activeFaceCount"])
        self.assertLess(adverse["minimumSignedOutwardFaceDischargeM3S"], 0.0)
        self.assertTrue(adverse["rejectedWithoutClipping"])
        self.assertIn("rejected without clipping", adverse["rejectionMessage"])

    def test_closed_interlock_has_exact_zero_flux(self) -> None:
        adverse = self.report["adverseHeadProbe"]
        self.assertEqual(adverse["allClosedAfterInterlockActiveFaceCount"], 0)
        self.assertEqual(adverse["allClosedMaximumAbsoluteFluxM3S"], 0.0)

    def test_no_runtime_or_adoption_claim(self) -> None:
        decision = self.report["decision"]
        self.assertTrue(decision["localFluxMechanicsPass"])
        self.assertFalse(decision["runtimeConnected"])
        self.assertFalse(decision["YodaDynamicGateCanaryAuthorized"])
        self.assertFalse(decision["meshOperationallyAdopted"])


if __name__ == "__main__":
    unittest.main()
