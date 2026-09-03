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
RUNNER_PATH = ROOT / "tools/stage20_downstream_external_high_large_7200s_runner_v1.py"
SPEC = importlib.util.spec_from_file_location("downstream_external_high_large_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class DownstreamExternalHighLarge7200sRunnerV1Tests(unittest.TestCase):
    def test_preflight_is_prepare_only_and_no_retry(self) -> None:
        report = RUNNER.build_preflight()
        self.assertEqual(
            report["status"],
            "PASS_PREPARE_ONLY_CANARY_BLOCKED_PENDING_ACTIVATION",
        )
        self.assertFalse(report["launchPermitted"])
        self.assertEqual(report["scenarioId"], "release-high_tide-large")
        self.assertEqual(report["durationModelSeconds"], 7200.0)
        self.assertEqual(report["automaticRetryCount"], 0)

    def test_scenario_is_exact_high_release_large_tide(self) -> None:
        scenario = RUNNER.load_scenario()
        self.assertEqual(scenario["id"], "release-high_tide-large")
        self.assertEqual(scenario["tideRangeClass"], "large")
        self.assertEqual(scenario["boundaryInputs"]["barrageReleaseM3S"], 73.0)

    def test_onga_upstream_boundary_no_longer_supplies_release(self) -> None:
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
                with self.assertRaisesRegex(RUNNER.ExternalInflowCanaryStop, "activation is missing"):
                    RUNNER.execute()
                load_context.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_contract_keeps_diagnostic_claim_and_no_upstream_donor(self) -> None:
        contract = json.loads(RUNNER.CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertIn("NOT_PHYSICAL_VALIDATION", contract["classification"])
        self.assertFalse(contract["scope"]["usesUpstreamDonorVolume"])
        self.assertFalse(contract["scope"]["reverseFlowPermitted"])
        self.assertEqual(contract["runtime"]["automaticRetryCount"], 0)
        self.assertEqual(
            contract["acceptance"]["stateDeltaSourceResidualTreatment"],
            "FLOAT64_DIAGNOSTIC_ONLY",
        )
        self.assertEqual(
            contract["acceptance"]["maximumCommandedSourceResidualRelative"],
            1.0e-13,
        )
        self.assertNotIn("maximumSourceResidualM3S", contract["acceptance"])

    def test_state_delta_residual_is_diagnostic_but_command_error_fails(self) -> None:
        external = {
            "requestedReleaseM3S": 73.0,
            "stateDeltaSourceResidualTreatment": "FLOAT64_DIAGNOSTIC_ONLY",
            "commandedSourceResidualRelative": 0.0,
        }
        RUNNER.require_external_source_conservation(external, 73.0)
        external["commandedSourceResidualRelative"] = 2.0e-13
        with self.assertRaisesRegex(
            RUNNER.ExternalInflowCanaryStop,
            "commanded external source is not conservative",
        ):
            RUNNER.require_external_source_conservation(external, 73.0)

    def test_module_has_no_remote_control_import(self) -> None:
        tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse(
            [name for name in imported if any(token in name.lower() for token in ("paramiko", "fabric", "ssh"))]
        )

    @unittest.skipUnless(socket.gethostname().lower() == "yoda", "YODA numerical context required")
    def test_yoda_one_step_has_exact_mass_momentum_and_no_upstream_source(self) -> None:
        report = RUNNER.run_local_one_step()
        self.assertEqual(
            report["status"],
            "PASS_LOCAL_ONE_STEP_EXTERNAL_DOWNSTREAM_INFLOW_HIGH_LARGE",
        )
        self.assertAlmostEqual(report["effectiveReleaseM3S"], 73.0, delta=1.0e-10)
        self.assertFalse(report["upstreamStateChangedBySource"])
        self.assertLessEqual(report["relativeMassBalanceError"], 1.0e-10)
        self.assertEqual(report["negativeDepthCount"], 0)
        self.assertEqual(report["nonFiniteValueCount"], 0)


if __name__ == "__main__":
    unittest.main()
