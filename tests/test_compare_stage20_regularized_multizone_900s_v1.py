from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/compare_stage20_regularized_multizone_900s_v1.py"
SPEC = importlib.util.spec_from_file_location("compare_regularized_900s_v1", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CompareRegularizedMultizone900sV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = MODULE.build_report()

    def test_dynamic_equivalence_passes_without_adoption(self) -> None:
        self.assertTrue(self.report["decision"]["dynamicEquivalencePass"])
        self.assertFalse(self.report["decision"]["meshAdopted"])
        self.assertIn("STILL_UNADOPTED", self.report["status"])

    def test_required_zones_and_thresholds_are_evaluated(self) -> None:
        self.assertEqual(set(self.report["zones"]), {"full_domain", "barrage_100m", "confluence"})
        for zone in self.report["zones"].values():
            self.assertTrue(zone["passWaterSurfaceBothWeightings"])
            self.assertTrue(zone["passVelocityAllWeightingsAndWetThresholds"])

    def test_contract_ambiguity_is_covered_by_sensitivity(self) -> None:
        mapping = self.report["mapping"]
        self.assertTrue(mapping["contractUnderspecificationHandledByRobustness"])
        self.assertEqual(mapping["weightingSensitivity"], ["cell_equal", "R1C_cell_area"])
        self.assertEqual(mapping["wetDepthThresholdSensitivityM"], [0.0, 0.01, 0.05, 0.1])

    def test_full_domain_metrics_are_below_frozen_limits(self) -> None:
        full = self.report["zones"]["full_domain"]
        eta = full["waterSurface"]
        self.assertLessEqual(max(eta["cellWeightedRmseM"], eta["areaWeightedRmseM"]), 0.1)
        for record in full["velocitySensitivity"].values():
            self.assertLessEqual(
                max(record["cellWeightedVectorRmseMPerS"], record["areaWeightedVectorRmseMPerS"]),
                0.01,
            )


if __name__ == "__main__":
    unittest.main()
