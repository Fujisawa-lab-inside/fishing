#!/usr/bin/env python3
"""Validate the inactive Stage 20 physical pilot v2 execution candidate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    candidate = load("config/stage20_physical_pilot_v2_candidate_v1.json")
    contract = load("config/stage20_physical_pilot_v2_contract_v1.json")
    benchmark = load("config/stage20_kernel_v2_synthetic_benchmark_v1.json")
    old_gate = load("config/stage20_hybrid_physical_pilot_gate_v1.json")
    plan = load("config/stage20_offline_response_precompute_plan_v2.json")
    require(candidate["schema"] == "onga-stage20-physical-pilot-v2-candidate-v1", "candidate schema mismatch")
    require(candidate["status"] == "awaiting_visual_execution_decision", "candidate status mismatch")
    require(contract["schema"] == "onga-stage20-physical-pilot-v2-contract-v1", "contract schema mismatch")
    require(contract["executionAuthorized"] is False, "contract self-authorized execution")
    require(contract["mesh"]["sha256"] == "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659", "mesh digest mismatch")
    require(contract["kernel"]["sha256"] == sha256(contract["kernel"]["path"]), "kernel digest mismatch")
    require(contract["kernel"]["syntheticBenchmarkSha256"] == sha256(contract["kernel"]["syntheticBenchmark"]), "benchmark digest mismatch")
    require(contract["runner"]["sha256"] == sha256(contract["runner"]["path"]), "runner digest mismatch")
    require(contract["runner"]["workflowSha256"] == sha256(contract["runner"]["workflowPath"]), "workflow digest mismatch")
    for item in contract["postprocessing"]:
        require(item["sha256"] == sha256(item["path"]), f"postprocessing digest mismatch: {item['path']}")
    require(candidate["decisionImage"]["sha256"] == sha256(candidate["decisionImage"]["path"]), "decision image digest mismatch")
    require(benchmark["status"] == "passed_nonphysical_fixture_only", "synthetic benchmark did not pass")
    require(benchmark["equivalence"]["maximumRelativeStateDifference"] <= benchmark["equivalence"]["tolerance"], "kernel equivalence failed")
    require(benchmark["speedup"]["combinedV2VersusV1"] > 1.0, "candidate did not improve synthetic throughput")
    require(old_gate["state"] == "consumed", "old one-time gate is unexpectedly reusable")
    require(plan["execution"]["authorized"] is False and plan["execution"]["physicalExecutorConnected"] is False, "precompute plan unexpectedly enables execution")
    authorization = Path("config/stage20_physical_pilot_v2_authorization_v1.json")
    gate = Path("config/stage20_physical_pilot_v2_gate_v1.json")
    require(not authorization.exists() and not gate.exists(), "v2 authorization or gate exists before user approval")

    contract_check = subprocess.run(
        [sys.executable, contract["runner"]["path"], "--contract-only"],
        check=True,
        text=True,
        capture_output=True,
    )
    contract_result = json.loads(contract_check.stdout)
    require(contract_result["status"] == "passed_inactive_contract_only", "inactive contract check failed")
    require(contract_result["numericalStepCalled"] is False, "contract check called the numerical kernel")
    require(contract_result["authorizationPresent"] is False and contract_result["gatePresent"] is False, "contract check found activation files")

    with tempfile.TemporaryDirectory(prefix="stage20-v2-fail-closed-") as temporary:
        output = Path(temporary) / "attempt"
        blocked = subprocess.run(
            [sys.executable, contract["runner"]["path"], "--output-dir", str(output)],
            text=True,
            capture_output=True,
        )
        require(blocked.returncode != 0, "runner executed without authorization")
        stop = json.loads((output / "pilot-stop.json").read_text(encoding="utf-8"))
        require("authorization is absent" in stop["error"], "runner stopped for an unexpected reason")

    print(json.dumps({
        "schema": "onga-stage20-physical-pilot-v2-candidate-validation-v1",
        "status": "passed_inactive_fail_closed",
        "meshSha256": contract["mesh"]["sha256"],
        "kernelSha256": contract["kernel"]["sha256"],
        "runnerSha256": contract["runner"]["sha256"],
        "workflowSha256": contract["runner"]["workflowSha256"],
        "decisionImageSha256": candidate["decisionImage"]["sha256"],
        "syntheticCombinedSpeedup": benchmark["speedup"]["combinedV2VersusV1"],
        "projectedWallMinutes": benchmark["planningProjection"]["projectedWallMinutesFor600PhysicalSeconds"],
        "oldGateConsumed": True,
        "newAuthorizationPresent": False,
        "newGatePresent": False,
        "unauthorizedExecutionBlockedBeforeNumericalStep": True,
        "physicalSolverExecuted": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
