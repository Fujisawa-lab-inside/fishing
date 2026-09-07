from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools/stage20_downstream_external_single_gap_37_snapshot_runner_v1.py"
SPEC = importlib.util.spec_from_file_location("downstream_external_single_gap_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class DownstreamExternalSingleGap37SnapshotRunnerV1Tests(unittest.TestCase):
    def test_preflight_is_one_scenario_prepare_only(self) -> None:
        report = RUNNER.build_preflight()
        self.assertEqual(
            report["status"],
            "PASS_PREPARE_ONLY_SINGLE_GAP_BLOCKED_PENDING_ACTIVATION",
        )
        self.assertFalse(report["launchPermitted"])
        self.assertEqual(report["scenarioId"], "release-6p2_tide-large")
        self.assertEqual(report["barrageReleaseM3S"], 6.2)
        self.assertEqual(report["tideRangeClass"], "large")
        self.assertEqual(report["durationModelSeconds"], 129600)
        self.assertEqual(report["hourlySnapshotCount"], 37)
        self.assertEqual(report["parallelWorkerCount"], 1)
        self.assertEqual(report["automaticRetryCount"], 0)
        self.assertFalse(report["currentConditionReferenceAllowed"])

    def test_scenario_reuses_large_tide_and_adds_only_release_anchor(self) -> None:
        scenario = RUNNER.load_scenario()
        self.assertEqual(scenario["id"], "release-6p2_tide-large")
        self.assertEqual(scenario["releaseBand"], "low-mid-gap")
        self.assertEqual(scenario["tideRangeClass"], "large")
        self.assertEqual(scenario["boundaryInputs"]["barrageReleaseM3S"], 6.2)
        self.assertEqual(
            scenario["boundaryInputs"]["snapshotOffsetsHours"],
            list(range(-12, 25)),
        )
        self.assertEqual(
            len(scenario["boundaryInputs"]["astronomicalTideHeightMByOffset"]),
            37,
        )

    def test_input_is_diagnostic_and_unpromoted(self) -> None:
        document = json.loads(RUNNER.INPUT_PATH.read_text(encoding="utf-8"))
        self.assertIn("NOT_FORECAST", document["classification"])
        self.assertFalse(document["currentConditionReferenceAllowed"])
        self.assertFalse(document["usesUpstreamDonorVolume"])
        self.assertFalse(document["reverseFlowPermitted"])

    def test_missing_activation_stops_before_context_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "activation.json"
            with (
                mock.patch.object(RUNNER, "ACTIVATION_PATH", missing),
                mock.patch.object(RUNNER.base, "load_context") as load_context,
            ):
                with self.assertRaisesRegex(RUNNER.SingleGapStop, "activation is missing"):
                    RUNNER.execute()
                load_context.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_runner_has_no_remote_control_dependency(self) -> None:
        tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        self.assertFalse(
            [name for name in imports if any(token in name.lower() for token in ("paramiko", "fabric", "ssh"))]
        )


if __name__ == "__main__":
    unittest.main()
