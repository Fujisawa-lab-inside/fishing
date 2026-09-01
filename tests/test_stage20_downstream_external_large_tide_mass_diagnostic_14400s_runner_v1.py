from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools/stage20_downstream_external_large_tide_mass_diagnostic_14400s_runner_v1.py"
SPEC = importlib.util.spec_from_file_location("large_tide_mass_diagnostic", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class LargeTideMassDiagnostic14400sRunnerV1Tests(unittest.TestCase):
    def test_preflight_is_prepare_only_and_no_retry(self) -> None:
        report = RUNNER.build_preflight()
        self.assertEqual(
            report["status"],
            "PASS_PREPARE_ONLY_DIAGNOSTIC_BLOCKED_PENDING_ACTIVATION",
        )
        self.assertFalse(report["launchPermitted"])
        self.assertEqual(report["scenarioCount"], 2)
        self.assertEqual(report["durationModelSeconds"], 14400.0)
        self.assertEqual(report["checkIntervalModelSeconds"], 600.0)
        self.assertEqual(report["originalRelativeMassThreshold"], 1.0e-10)
        self.assertEqual(report["automaticRetryCount"], 0)

    def test_only_two_large_tide_failure_conditions_are_selected(self) -> None:
        scenarios = RUNNER.load_scenarios()
        self.assertEqual(tuple(scenarios), RUNNER.SCENARIO_IDS)
        self.assertEqual(
            [item["boundaryInputs"]["barrageReleaseM3S"] for item in scenarios.values()],
            [24.5, 73.0],
        )
        self.assertTrue(all(item["tideRangeClass"] == "large" for item in scenarios.values()))

    def test_float64_only_crossing_is_classified_as_accumulation(self) -> None:
        classification = RUNNER.classify_checkpoint({
            "float64ThresholdCrossed": True,
            "longDoubleThresholdCrossed": False,
        })
        self.assertEqual(
            classification,
            "FLOAT64_ACCOUNTING_ACCUMULATION_ONLY_AT_ORIGINAL_THRESHOLD",
        )

    def test_long_double_crossing_is_not_dismissed_as_roundoff(self) -> None:
        classification = RUNNER.classify_checkpoint({
            "float64ThresholdCrossed": True,
            "longDoubleThresholdCrossed": True,
        })
        self.assertEqual(
            classification,
            "MASS_MISMATCH_PERSISTS_WITH_LONG_DOUBLE_ACCOUNTING",
        )

    def test_checkpoint_threshold_flags_are_json_serializable_builtin_bools(self) -> None:
        state = np.asarray([[1.0, 0.0, 0.0]], dtype=np.float64)
        areas_float64 = np.asarray([1.0], dtype=np.float64)
        with mock.patch.object(RUNNER.full, "tide_at", return_value=0.0):
            row = RUNNER._checkpoint(
                state=state,
                areas_float64=areas_float64,
                areas_longdouble=areas_float64.astype(np.longdouble),
                initial_volume_float64=1.0,
                initial_volume_longdouble=np.longdouble(1.0),
                expected_volume_float64=1.0,
                expected_volume_longdouble=np.longdouble(1.0),
                boundary_volume_float64=0.0,
                boundary_volume_longdouble=np.longdouble(0.0),
                external_volume_float64=0.0,
                external_volume_longdouble=np.longdouble(0.0),
                cumulative_source_residual_m3=np.longdouble(0.0),
                model_seconds=600.0,
                accepted_steps=1,
                scenario={"boundaryInputs": {"barrageReleaseM3S": 0.0}},
                last_step=mock.Mock(boundary_outflow_m3_s=0.0),
                last_external={"sourceResidualM3S": 0.0, "inflowVelocityMPS": 0.0},
            )

        self.assertIs(type(row["float64ThresholdCrossed"]), bool)
        self.assertIs(type(row["longDoubleThresholdCrossed"]), bool)
        encoded = RUNNER.full.canary.canonical_bytes({"telemetryRowsBeforeFailure": [row]})
        decoded = json.loads(encoded)
        self.assertIsInstance(
            decoded["telemetryRowsBeforeFailure"][0]["longDoubleThresholdCrossed"],
            bool,
        )

    def test_missing_activation_stops_before_worker_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "activation.json"
            with (
                mock.patch.object(RUNNER, "ACTIVATION_PATH", missing),
                mock.patch.object(RUNNER, "_run_parallel") as run_parallel,
            ):
                with self.assertRaisesRegex(RUNNER.MassDiagnosticStop, "activation is missing"):
                    RUNNER.execute()
                run_parallel.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_contract_stops_at_original_threshold_and_forbids_retry(self) -> None:
        contract = json.loads(RUNNER.CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertTrue(contract["scope"]["stopAtFirstOriginalThresholdCrossing"])
        self.assertEqual(contract["scope"]["originalRelativeMassThreshold"], 1.0e-10)
        self.assertFalse(contract["scope"]["usesUpstreamDonorVolume"])
        self.assertEqual(contract["runtime"]["automaticRetryCount"], 0)
        self.assertFalse(contract["promotion"]["numericalAcceptanceGranted"])

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


if __name__ == "__main__":
    unittest.main()
