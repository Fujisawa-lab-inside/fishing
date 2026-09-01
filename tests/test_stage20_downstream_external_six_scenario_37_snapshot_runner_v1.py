from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools/stage20_downstream_external_six_scenario_37_snapshot_runner_v1.py"
SPEC = importlib.util.spec_from_file_location("downstream_external_six37_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class DownstreamExternalSixScenario37SnapshotRunnerV1Tests(unittest.TestCase):
    def test_preflight_is_prepare_only_and_no_retry(self) -> None:
        report = RUNNER.build_preflight()
        self.assertEqual(
            report["status"],
            "PASS_PREPARE_ONLY_BATCH_BLOCKED_PENDING_ACTIVATION",
        )
        self.assertFalse(report["launchPermitted"])
        self.assertEqual(report["scenarioCount"], 6)
        self.assertEqual(report["durationModelSeconds"], 129600)
        self.assertEqual(report["hourlySnapshotCount"], 37)
        self.assertEqual(report["parallelWorkerCount"], 6)
        self.assertEqual(report["automaticRetryCount"], 0)

    def test_input_matrix_has_exact_six_conditions(self) -> None:
        scenarios = RUNNER.load_scenarios()
        self.assertEqual(tuple(scenarios), RUNNER.SCENARIO_IDS)
        pairs = {(item["releaseBand"], item["tideRangeClass"]) for item in scenarios.values()}
        self.assertEqual(
            pairs,
            {
                ("low", "small"),
                ("low", "large"),
                ("reference", "small"),
                ("reference", "large"),
                ("high", "small"),
                ("high", "large"),
            },
        )
        self.assertEqual(
            {item["boundaryInputs"]["barrageReleaseM3S"] for item in scenarios.values()},
            {0.1, 24.5, 73.0},
        )

    def test_timeline_is_minus12_through_plus24(self) -> None:
        for scenario in RUNNER.load_scenarios().values():
            boundary = scenario["boundaryInputs"]
            self.assertEqual(boundary["snapshotOffsetsHours"], list(range(-12, 25)))
            self.assertEqual(len(boundary["astronomicalTideHeightMByOffset"]), 37)

    def test_onga_upstream_boundary_does_not_supply_release(self) -> None:
        geometry = {"boundaryTagLengthSums": np.array([0.0, 0.0, 7.0, 11.0, 5.0])}
        discharge = RUNNER.build_discharge(geometry)
        self.assertAlmostEqual(discharge[2], -0.1)
        self.assertEqual(discharge[3], 0.0)
        self.assertAlmostEqual(discharge[4], -0.1)

    def test_missing_activation_stops_before_context_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "activation.json"
            with (
                mock.patch.object(RUNNER, "ACTIVATION_PATH", missing),
                mock.patch.object(RUNNER, "load_context") as load_context,
            ):
                with self.assertRaisesRegex(RUNNER.ExternalBatchStop, "activation is missing"):
                    RUNNER.execute()
                load_context.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_snapshot_writer_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hourly.npz"
            RUNNER._atomic_savez_new(path, x=np.asarray([1.0]))
            with self.assertRaises(RUNNER.ExternalBatchStop):
                RUNNER._atomic_savez_new(path, x=np.asarray([2.0]))

    def test_contract_keeps_external_source_and_diagnostic_boundary(self) -> None:
        contract = json.loads(RUNNER.CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertIn("NOT_PHYSICAL_VALIDATION", contract["classification"])
        self.assertFalse(contract["scope"]["usesUpstreamDonorVolume"])
        self.assertFalse(contract["scope"]["reverseFlowPermitted"])
        self.assertTrue(contract["scope"]["consolidatedSnapshotOnly"])
        self.assertEqual(contract["runtime"]["automaticRetryCount"], 0)
        self.assertNotIn("canaryGate", contract["runtime"])

    def test_module_uses_external_adapter_and_has_no_remote_control_import(self) -> None:
        tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertIn("stage20_downstream_external_inflow_adapter_v1", imported)
        self.assertNotIn("stage20_downstream_prescribed_release_adapter_v1", imported)
        self.assertFalse(
            [name for name in imported if any(token in name.lower() for token in ("paramiko", "fabric", "ssh"))]
        )

    @unittest.skipUnless(socket.gethostname().lower() == "yoda", "YODA numerical context required")
    def test_yoda_one_step_matrix_is_safe_and_uses_no_upstream_source(self) -> None:
        report = RUNNER.run_local_matrix_one_step()
        self.assertEqual(
            report["status"],
            "PASS_LOCAL_SIX_SCENARIO_ONE_STEP_EXTERNAL_MATRIX",
        )
        self.assertEqual(report["scenarioCount"], 6)
        self.assertEqual(report["outputCreationCount"], 0)
        self.assertEqual(report["yodaConnectionCount"], 0)
        for row in report["rows"]:
            self.assertAlmostEqual(row["effectiveReleaseM3S"], row["releaseM3S"], delta=1.0e-10)
            self.assertFalse(row["upstreamStateChangedBySource"])
            self.assertLessEqual(row["relativeMassBalanceError"], 1.0e-10)


if __name__ == "__main__":
    unittest.main()
