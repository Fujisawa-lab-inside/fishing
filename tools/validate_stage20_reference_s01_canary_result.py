#!/usr/bin/env python3
"""Validate the retained Stage 20 reference-s01 canary result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path("docs/results/stage20-reference-s01-canary-29415527789")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    result = load(Path("config/stage20_reference_s01_canary_result_v1.json"))
    analysis = load(Path("config/stage20_reference_s01_canary_analysis_v1.json"))
    report = load(ROOT / "segment-report.json")
    progress = load(ROOT / "progress.json")
    receipt = load(ROOT / "execution-receipt.json")
    evidence = load(ROOT / "evidence-manifest.json")
    visual = load(ROOT / "visual-manifest.json")
    gate = load(Path("config/stage20_reference_s01_canary_gate_v1.json"))
    authorization = load(Path("config/stage20_reference_s01_canary_authorization_v1.json"))

    require(result["github"]["runId"] == 29415527789, "run ID mismatch")
    require(result["github"]["runAttempt"] == 1 and result["github"]["conclusion"] == "success", "workflow result mismatch")
    require(receipt["githubRunId"] == "29415527789", "receipt run ID mismatch")
    require(receipt["githubSha"] == result["github"]["executionCommit"], "execution commit mismatch")
    require(gate["state"] == "consumed", "one-time gate is not consumed")
    require(gate["consumedBy"]["githubRunId"] == result["github"]["runId"], "gate consumption mismatch")
    require(gate["authorizationId"] == authorization["authorizationId"] == report["authorizationId"], "authorization identity mismatch")
    require(gate["automaticRetryAllowed"] is False and gate["additionalRunAllowed"] is False, "gate safeguard mismatch")

    require(report["status"] == "passed_numerical_checks_not_physical_validation", "report status mismatch")
    require(progress["status"] == "complete", "progress is incomplete")
    require(report["run"]["jobId"] == "reference-s01", "job identity mismatch")
    require(report["run"]["modelHourStart"] == -24 and report["run"]["modelHourEnd"] == -16, "model-hour scope mismatch")
    require(report["run"]["simulatedSeconds"] >= 28800, "physical-time target not reached")
    require(report["run"]["wallSeconds"] < 18000, "wall-time stop exceeded")
    require(len(progress["checkpoints"]) == len(report["outputs"]["checkpoints"]) == 8, "checkpoint count mismatch")
    require(report["diagnostics"]["maximumCfl"] <= 0.95, "CFL acceptance failed")
    require(report["diagnostics"]["maximumRelativeMassBalanceError"] <= 1e-8, "mass-balance acceptance failed")
    require(report["diagnostics"]["nonFiniteValueCount"] == 0, "non-finite result values")
    require(report["diagnostics"]["negativeDepthCount"] == 0, "negative result depth")

    require(sha256(ROOT / "evidence-manifest.json") == result["evidence"]["manifestSha256"], "evidence digest mismatch")
    require(sha256(Path(result["evidence"]["analysis"])) == result["evidence"]["analysisSha256"], "analysis digest mismatch")
    require(sha256(Path(result["evidence"]["visualManifest"])) == result["evidence"]["visualManifestSha256"], "visual manifest digest mismatch")
    require(visual["fieldsSha256"] == result["numerical"]["finalFieldsSha256"], "visual source fields mismatch")
    require(len(visual["views"]) == result["evidence"]["diagnosticMapCount"] == 4, "diagnostic map count mismatch")
    for item in visual["views"]:
        map_path = ROOT / "maps" / item["path"]
        require(sha256(map_path) == item["sha256"], f"diagnostic map digest mismatch: {item['path']}")
    next_decision = result["nextDecision"]
    require(sha256(Path(next_decision["decisionImage"])) == next_decision["decisionImageSha256"], "next decision image digest mismatch")
    require(next_decision["executionAuthorized"] is False, "next segment was implicitly authorized")
    require(len(evidence["files"]) == result["evidence"]["fileCount"] == 13, "evidence file count mismatch")
    for item in evidence["files"]:
        path = ROOT / item["path"]
        require(path.stat().st_size == item["byteLength"], f"evidence byte length mismatch: {item['path']}")
        require(sha256(path) == item["sha256"], f"evidence digest mismatch: {item['path']}")

    for checkpoint_record in report["outputs"]["checkpoints"]:
        checkpoint_path = ROOT / checkpoint_record["path"]
        require(sha256(checkpoint_path) == checkpoint_record["sha256"], f"checkpoint digest mismatch: {checkpoint_record['path']}")
        with np.load(checkpoint_path, allow_pickle=False) as checkpoint:
            state = checkpoint["state"]
            require(state.shape == (50199, 3), "checkpoint state shape mismatch")
            require(np.isfinite(state).all(), "non-finite checkpoint state")
            require(np.all(state[:, 0] >= 0), "negative checkpoint depth")

    require(sha256(ROOT / "restart-final.npz") == report["outputs"]["restartSha256"] == result["numerical"]["restartSha256"], "restart digest mismatch")
    require(sha256(ROOT / "segment-final-fields.npz") == report["outputs"]["fieldsSha256"] == result["numerical"]["finalFieldsSha256"], "final-fields digest mismatch")
    require(report["outputs"]["checkpoints"][-1]["sha256"] == report["outputs"]["restartSha256"], "last checkpoint is not final restart")
    with np.load(ROOT / "restart-final.npz", allow_pickle=False) as restart, np.load(ROOT / "segment-final-fields.npz", allow_pickle=False) as fields:
        state = restart["state"]
        depth = state[:, 0]
        u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
        v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
        require(np.array_equal(depth, fields["waterDepthM"]), "final depth conversion mismatch")
        require(np.array_equal(u, fields["velocityUms"]), "final u conversion mismatch")
        require(np.array_equal(v, fields["velocityVms"]), "final v conversion mismatch")

    require(analysis["status"] == "passed_digest_and_state_analysis_not_physical_validation", "analysis status mismatch")
    require(analysis["interpretation"]["warmupSufficiencyProven"] is False, "warmup sufficiency overclaim")
    safeguards = result["safeguards"]
    require(all(safeguards[key] is False for key in (
        "additionalRunAuthorized",
        "remainingSegmentsAuthorized",
        "campaignAuthorized",
        "paidResourceAuthorized",
        "publicSimulatorConnected",
        "mainMergeAuthorized",
        "physicalValidationClaimAllowed",
    )), "result safeguard mismatch")

    print(json.dumps({
        "schema": "onga-stage20-reference-s01-canary-result-validation-v1",
        "status": "passed_not_physical_validation",
        "githubRunId": result["github"]["runId"],
        "simulatedSeconds": report["run"]["simulatedSeconds"],
        "wallSeconds": report["run"]["wallSeconds"],
        "checkpointCount": len(progress["checkpoints"]),
        "evidenceFileCount": len(evidence["files"]),
        "diagnosticMapCount": len(visual["views"]),
        "gateConsumed": True,
        "additionalRunAuthorized": False,
        "remainingSegmentsAuthorized": False,
        "physicalValidationClaimAllowed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
