#!/usr/bin/env python3

import ast
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "stage20_stage4_facewise_capacity_backoff_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_stage4_facewise_capacity_backoff_v1", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Stage4FacewiseCapacityBackoffTest(unittest.TestCase):
    def evidence(self, safe_scale: float, *, closed_leak: bool = False):
        gate_index = np.asarray([2, 2, 3, 3, 4, 4, 5, 5], dtype=np.int64)
        rows = []
        for scale in MODULE.CANDIDATE_SCALES:
            capacity = MODULE.stage4_capacity_for_scale(scale)
            flux = np.full(8, 1.0, dtype=np.float64)
            if scale > safe_scale:
                flux[0] = -1e-4
                flux[1] = 10.0
            if scale == 0.0:
                flux[:] = 0.0
                if closed_leak:
                    flux[0] = 1e-4
            rows.append({
                "scale": scale,
                "capacityByGateId1To8": capacity,
                "signedOutwardFluxM3SBySelectedFace": flux,
                "gateIndexBySelectedFace": gate_index,
            })
        return rows

    def test_contract_and_candidate_grid_are_fixed(self):
        contract = MODULE.read_and_verify_contract()
        self.assertEqual(contract["scope"]["activeGateIds"], [3, 4, 5, 6])
        candidates = MODULE.candidate_capacities()
        self.assertEqual(len(candidates), 9)
        self.assertEqual(candidates[0].tolist(), [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
        self.assertEqual(candidates[-1].tolist(), [0.0] * 8)

    def test_positive_gate_sum_cannot_hide_one_adverse_face(self):
        result = MODULE.select_largest_safe_candidate(self.evidence(0.5))
        self.assertEqual(result["selectedScale"], 0.5)
        full = result["candidateDiagnostics"][0]
        self.assertEqual(full["adverseActiveFaceCount"], 1)
        self.assertFalse(full["safe"])
        self.assertFalse(result["fluxClipped"])

    def test_first_safe_descending_candidate_is_selected(self):
        result = MODULE.select_largest_safe_candidate(self.evidence(0.75))
        self.assertEqual(result["selectedScale"], 0.75)
        self.assertEqual(result["evaluatedCandidateCountThroughSelection"], 3)
        self.assertTrue(result["acceptedStateMustComeFromSelectedCandidateTrial"])

    def test_all_closed_leakage_fails_instead_of_becoming_false_safe(self):
        rows = self.evidence(-1.0, closed_leak=True)
        with self.assertRaisesRegex(MODULE.FacewiseCapacityBackoffError, "no safe candidate"):
            MODULE.select_largest_safe_candidate(rows)

    def test_module_has_no_kernel_remote_or_output_capability(self):
        tree = ast.parse(MODULE_PATH.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse([name for name in imported if any(token in name.lower() for token in ("ssh", "paramiko", "fabric", "requests", "kernel"))])
        source = MODULE_PATH.read_text()
        self.assertNotIn("write_text(", source)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
