from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools/stage20_downstream_external_boundary_dry_continuation_diagnostic_v1.py"
SPEC = importlib.util.spec_from_file_location("boundary_dry_continuation", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class BoundaryDryContinuationDiagnosticV1Tests(unittest.TestCase):
    def test_preflight_is_single_scenario_and_no_retry(self) -> None:
        report = RUNNER.build_preflight()
        self.assertFalse(report["launchPermitted"])
        self.assertEqual(report["scenarioId"], "release-high_tide-large")
        self.assertEqual(report["continuationSeconds"], 6000.0)
        self.assertEqual(report["automaticRetryCount"], 0)
        self.assertFalse(report["physicalValidation"])
        self.assertFalse(report["forecast"])

    def test_runner_has_no_remote_control_import(self) -> None:
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
