#!/usr/bin/env python3
"""Validate the immutable, inactive Stage 19 execution-readiness package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage19-readiness] {message}")


def main() -> None:
    integration_path = ROOT / "config/stage19_solver_integration_contract_v1.json"
    execution_path = ROOT / "config/stage19_full64_execution_contract_v1.json"
    integration = load("config/stage19_solver_integration_contract_v1.json")
    execution = load("config/stage19_full64_execution_contract_v1.json")

    require(integration["schema"] == "onga-stage19-solver-integration-contract-v1", "integration schema")
    require(len(integration["parameterCoverage"]["active"]) == 16, "all 16 parameters must be active")
    require(integration["parameterCoverage"]["inactive"] == [], "inactive parameter remains")
    for section, key in (
        ("approvedInputs", "ensemble"),
        ("approvedInputs", "tideCandidate"),
        ("approvedInputs", "tideApproval"),
        ("implementation", "inputBuilder"),
        ("implementation", "kernel"),
    ):
        item = integration[section][key]
        require(sha256(ROOT / item["path"]) == item["sha256"], f"digest mismatch: {item['path']}")
    for key in ("synthetic", "darwinZeroCaseProbe"):
        item = integration["verification"][key]
        require(sha256(ROOT / item["path"]) == item["sha256"], f"evidence digest mismatch: {key}")
        evidence = load(item["path"])
        require(evidence["status"] == "passed", f"evidence not passed: {key}")
        require(evidence["safeguards"]["productionMeshNumericalCaseStarted"] is False,
                f"production case unexpectedly started: {key}")
    require(integration["verification"]["canonicalLinuxZeroCase"]["status"] == "not_yet_executed",
            "canonical preflight status changed before authorization")
    require(integration["safeguards"]["full64ExecutionAuthorized"] is False, "integration self-authorized")

    require(execution["schema"] == "onga-stage19-full64-execution-contract-v1", "execution schema")
    require(execution["status"] == "awaiting_explicit_visual_authorization", "execution status")
    require(execution["executionAuthorized"] is False and execution["authorization"] is None,
            "immutable contract self-authorized")
    require(execution["solverIntegration"]["sha256"] == sha256(integration_path),
            "execution contract is not bound to integration contract")
    require(sha256(ROOT / execution["decisionVisual"]["path"])
            == execution["decisionVisual"]["sha256"], "decision visual digest mismatch")
    require(execution["run"] == {
        "purpose": "provisional_numerical_stability_and_spatial_output_evidence_only",
        "caseCount": 64,
        "stepsPerCase": 500,
        "totalSteps": 32000,
        "caseSeed": 20260714,
        "comparisonBasis": "equal_step_count_not_equal_simulated_time",
    }, "run scope changed")
    require(execution["authorizationContract"]["oneTime"] is True, "authorization is not one-time")
    require(execution["authorizationContract"]["maxValiditySeconds"] == 86400, "authorization exceeds 24h")
    require(execution["requiredOutputs"]["mapCount"] == 5, "five-map output changed")
    require(all(value is False for key, value in execution["safeguards"].items()
                if key.endswith("Allowed")), "an execution safeguard became permissive")
    print(json.dumps({
        "schema": "onga-stage19-execution-readiness-validation-v1",
        "status": "passed",
        "integrationContractSha256": sha256(integration_path),
        "executionContractSha256": sha256(execution_path),
        "activeInputDimensions": 16,
        "syntheticValidation": "passed",
        "darwinZeroCaseProbe": "passed",
        "canonicalZeroCase": "required_before_numerical_run",
        "full64ExecutionAuthorized": False,
        "productionMeshNumericalCaseStarted": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
