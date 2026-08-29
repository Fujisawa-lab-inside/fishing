from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/results/stage20-barrage-observation-validator-gap-audit-v1/report.json"
FIXTURE = ROOT / "tests/fixtures/stage20-barrage-gate-physics-observation-pack-v1/synthetic-complete-pack.json"
VALIDATOR_PATH = ROOT / "tools/stage20_barrage_gate_physics_observation_pack_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_gate_physics_observation_pack_v1_gap_audit", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class Stage20BarrageObservationValidatorGapAuditV1Tests(unittest.TestCase):
    def test_audit_binds_exact_evidence(self) -> None:
        report = json.loads(REPORT.read_text())
        for binding in report["evidenceBindings"]:
            path = ROOT / binding["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), binding["sha256"])

    def test_event_threshold_mismatch_is_recorded(self) -> None:
        report = json.loads(REPORT.read_text())
        finding = next(item for item in report["findings"] if item["id"] == "EVENT_DESIGN_THRESHOLD_MISMATCH")
        self.assertEqual(finding["validatorMinimumDistinctEvents"], 3)
        self.assertEqual(finding["registeredPlanMinimumIndependentEvents"], 18)

    def test_relabel_gap_is_reproducible_but_never_authorized(self) -> None:
        synthetic = json.loads(FIXTURE.read_text())
        self.assertFalse(VALIDATOR.assess(synthetic)["physicalObservationReady"])
        relabelled = copy.deepcopy(synthetic)
        relabelled["classification"] = "physical_observation"
        self.assertTrue(VALIDATOR.assess(relabelled)["physicalObservationReady"])
        report = json.loads(REPORT.read_text())
        self.assertFalse(report["decisionBoundary"]["physicalObservationReady"])
        self.assertFalse(report["decisionBoundary"]["parameterFitPermitted"])
        self.assertFalse(report["decisionBoundary"]["solverRunPermitted"])


if __name__ == "__main__":
    unittest.main()
