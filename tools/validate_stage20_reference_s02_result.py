#!/usr/bin/env python3
"""Validate the retained Stage 20 reference-s02 result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path("docs/results/stage20-reference-s02-29434250546")
S01_ROOT = Path("docs/results/stage20-reference-s01-canary-29415527789")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    result = load(Path("config/stage20_reference_s02_result_v1.json"))
    analysis = load(Path("config/stage20_reference_s02_analysis_v1.json"))
    report = load(ROOT / "segment-report.json")
    progress = load(ROOT / "progress.json")
    receipt = load(ROOT / "execution-receipt.json")
    evidence = load(ROOT / "evidence-manifest.json")
    visual = load(ROOT / "visual-manifest.json")
    gate = load(Path("config/stage20_reference_s02_gate_v1.json"))
    authorization = load(Path("config/stage20_reference_s02_authorization_v1.json"))

    require(result["github"]["runId"] == 29434250546, "run ID mismatch")
    require(result["github"]["runAttempt"] == 1 and result["github"]["conclusion"] == "success", "workflow result mismatch")
    require(receipt["githubRunId"] == "29434250546", "receipt run ID mismatch")
    require(receipt["githubSha"] == result["github"]["executionCommit"], "execution commit mismatch")
    require(gate["state"] == "consumed", "one-time gate is not consumed")
    require(gate["consumedBy"]["githubRunId"] == result["github"]["runId"], "gate consumption mismatch")
    require(gate["authorizationId"] == authorization["authorizationId"] == report["authorizationId"], "authorization identity mismatch")
    require(gate["automaticRetryAllowed"] is False and gate["additionalRunAllowed"] is False, "gate safeguard mismatch")

    require(report["status"] == "passed_numerical_checks_not_physical_validation", "report status mismatch")
    require(progress["status"] == "complete", "progress is incomplete")
    require(report["run"]["jobId"] == "reference-s02", "job identity mismatch")
    require(report["run"]["modelHourStart"] == -16 and report["run"]["modelHourEnd"] == -8, "model-hour scope mismatch")
    require(report["run"]["simulatedSeconds"] >= 28800, "physical-time target not reached")
    require(report["run"]["wallSeconds"] < 18000, "wall-time stop exceeded")
    require(len(progress["checkpoints"]) == len(report["outputs"]["checkpoints"]) == 8, "checkpoint count mismatch")
    require(len(progress["snapshots"]) == len(report["outputs"]["snapshots"]) == 5, "snapshot count mismatch")
    require([item["modelHour"] for item in report["outputs"]["snapshots"]] == [-12, -11, -10, -9, -8], "snapshot hours mismatch")
    require(report["diagnostics"]["maximumCfl"] <= 0.95, "CFL acceptance failed")
    require(report["diagnostics"]["maximumRelativeMassBalanceError"] <= 1e-8, "mass-balance acceptance failed")
    require(report["diagnostics"]["nonFiniteValueCount"] == 0, "non-finite result values")
    require(report["diagnostics"]["negativeDepthCount"] == 0, "negative result depth")

    s01_restart_sha = sha256(S01_ROOT / "restart-final.npz")
    require(receipt["inputRestartSha256"] == result["chain"]["inputRestartSha256"] == s01_restart_sha, "S01 restart chain mismatch")
    require(report["run"]["startStep"] == result["chain"]["startStep"] == 2979347, "start step mismatch")

    require(sha256(ROOT / "evidence-manifest.json") == result["evidence"]["manifestSha256"], "evidence digest mismatch")
    require(sha256(Path(result["evidence"]["analysis"])) == result["evidence"]["analysisSha256"], "analysis digest mismatch")
    require(len(evidence["files"]) == result["evidence"]["fileCount"] == 18, "evidence file count mismatch")
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

    for snapshot_record in report["outputs"]["snapshots"]:
        snapshot_path = ROOT / snapshot_record["path"]
        require(sha256(snapshot_path) == snapshot_record["sha256"], f"snapshot digest mismatch: {snapshot_record['modelHour']}")
        with np.load(snapshot_path, allow_pickle=False) as fields:
            for name in ("waterDepthM", "velocityUms", "velocityVms"):
                require(fields[name].shape == (50199,), f"snapshot shape mismatch: {snapshot_record['modelHour']} {name}")
                require(np.isfinite(fields[name]).all(), f"non-finite snapshot: {snapshot_record['modelHour']} {name}")
            require(np.all(fields["waterDepthM"] >= 0), f"negative snapshot depth: {snapshot_record['modelHour']}")

    require(sha256(ROOT / "restart-final.npz") == report["outputs"]["restartSha256"] == result["numerical"]["restartSha256"], "restart digest mismatch")
    require(sha256(ROOT / "segment-final-fields.npz") == report["outputs"]["fieldsSha256"] == result["numerical"]["finalFieldsSha256"], "final-fields digest mismatch")
    require(report["outputs"]["checkpoints"][-1]["sha256"] == report["outputs"]["restartSha256"], "last checkpoint is not final restart")
    require(report["outputs"]["snapshots"][-1]["sha256"] == report["outputs"]["fieldsSha256"], "last snapshot is not final fields")

    require(sha256(Path(result["evidence"]["visualManifest"])) == result["evidence"]["visualManifestSha256"], "visual manifest digest mismatch")
    require(visual["commonScaleAcrossViews"] is True and visual["displayCeilingMPS"] == 0.23, "visual scale mismatch")
    require(len(visual["views"]) == result["evidence"]["diagnosticMapCount"] == 5, "diagnostic map count mismatch")
    for item in visual["views"]:
        require(sha256(ROOT / item["map"]) == item["mapSha256"], f"map digest mismatch: {item['modelHour']}")
        require(sha256(ROOT / item["childManifest"]) == item["childManifestSha256"], f"child visual manifest mismatch: {item['modelHour']}")
    next_decision = result["nextDecision"]
    require(sha256(Path(next_decision["decisionImage"])) == next_decision["decisionImageSha256"], "next decision image digest mismatch")
    require(next_decision["additionalPhysicalRunAuthorized"] is False, "next physical run was implicitly authorized")

    require(analysis["status"] == "passed_digest_chain_and_state_analysis_not_physical_validation", "analysis status mismatch")
    require(analysis["s01ToS02ChainVerified"] is True, "analysis chain mismatch")
    safeguards = result["safeguards"]
    require(all(safeguards[key] is False for key in (
        "additionalRunAuthorized",
        "remainingSegmentsAuthorized",
        "campaignAuthorized",
        "paidResourceAuthorized",
        "publicSimulatorConnected",
        "mainMergeAuthorized",
        "physicalValidationClaimAllowed",
        "dailyForecastClaimAllowed",
    )), "result safeguard mismatch")

    print(json.dumps({
        "schema": "onga-stage20-reference-s02-result-validation-v1",
        "status": "passed_not_physical_validation",
        "githubRunId": result["github"]["runId"],
        "simulatedSeconds": report["run"]["simulatedSeconds"],
        "wallSeconds": report["run"]["wallSeconds"],
        "checkpointCount": len(progress["checkpoints"]),
        "snapshotCount": len(progress["snapshots"]),
        "evidenceFileCount": len(evidence["files"]),
        "diagnosticMapCount": len(visual["views"]),
        "s01ToS02ChainVerified": True,
        "gateConsumed": True,
        "additionalRunAuthorized": False,
        "remainingSegmentsAuthorized": False,
        "physicalValidationClaimAllowed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
