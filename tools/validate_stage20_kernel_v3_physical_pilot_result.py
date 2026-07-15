#!/usr/bin/env python3
"""Validate the retained Stage 20 kernel-v3 physical pilot result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path("docs/results/stage20-kernel-v3-physical-pilot-29411976467")
OLD_ROOT = Path("docs/results/stage20-physical-pilot-v2-29396657600")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    result = load(Path("config/stage20_kernel_v3_physical_pilot_result_v1.json"))
    comparison = load(Path("config/stage20_kernel_v3_physical_pilot_comparison_v1.json"))
    report = load(ROOT / "pilot-report.json")
    progress = load(ROOT / "pilot-progress.json")
    receipt = load(ROOT / "execution-receipt.json")
    evidence = load(ROOT / "pilot-evidence-manifest.json")
    artifact_visual = load(ROOT / "pilot-visual-manifest.json")
    corrected_visual = load(ROOT / "pilot-visual-manifest-local.json")
    gate = load(Path("config/stage20_kernel_v3_physical_pilot_gate_v1.json"))
    authorization = load(Path("config/stage20_kernel_v3_physical_pilot_authorization_v1.json"))

    require(result["github"]["runId"] == 29411976467, "run ID mismatch")
    require(receipt["githubRunId"] == "29411976467", "receipt run ID mismatch")
    require(receipt["githubSha"] == result["github"]["executionCommit"], "execution commit mismatch")
    require(result["github"]["runAttempt"] == 1 and result["github"]["conclusion"] == "success", "workflow result mismatch")
    require(gate["state"] == "consumed", "one-time gate is not consumed")
    require(gate["consumedBy"]["githubRunId"] == result["github"]["runId"], "gate consumption run mismatch")
    require(gate["authorizationId"] == authorization["authorizationId"] == report["authorizationId"], "authorization identity mismatch")
    require(gate["automaticRetryAllowed"] is False and gate["additionalRunAllowed"] is False, "gate retry safeguard mismatch")

    require(report["status"] == "passed_numerical_checks_not_physical_validation", "report status mismatch")
    require(progress["status"] == "complete" and progress["simulatedSeconds"] >= 600, "physical-time target not reached")
    require(len(progress["checkpoints"]) == 10 and len(report["outputs"]["checkpoints"]) == 10, "checkpoint count mismatch")
    require(report["diagnostics"]["maximumCfl"] <= 0.95, "CFL acceptance failed")
    require(report["diagnostics"]["maximumRelativeMassBalanceError"] <= 1e-8, "mass-balance acceptance failed")
    require(report["diagnostics"]["nonFiniteValueCount"] == 0, "non-finite result values")
    require(report["diagnostics"]["negativeDepthCount"] == 0, "negative result depth")

    require(sha256(ROOT / "pilot-evidence-manifest.json") == result["evidence"]["artifactEvidenceManifestSha256"], "artifact evidence digest mismatch")
    require(sha256(ROOT / "pilot-visual-manifest-local.json") == result["evidence"]["correctedLocalVisualManifestSha256"], "corrected visual digest mismatch")
    require(sha256(Path("config/stage20_kernel_v3_physical_pilot_comparison_v1.json")) == result["evidence"]["comparisonSha256"], "comparison digest mismatch")
    require(sha256(Path(result["evidence"]["nextDecisionImage"])) == result["evidence"]["nextDecisionImageSha256"], "next decision image digest mismatch")

    retained_direct = {"execution-receipt.json", "pilot-progress.json", "pilot-report.json", "pilot-final-fields.npz", "pilot-visual-manifest.json"}
    for item in evidence["files"]:
        artifact_path = Path(item["path"])
        if item["path"] in retained_direct:
            retained = ROOT / artifact_path
        elif artifact_path.parts[0] == "maps":
            retained = ROOT / "artifact-maps" / artifact_path.name
        else:
            continue
        require(sha256(retained) == item["sha256"], f"retained artifact digest mismatch: {item['path']}")

    require(artifact_visual["fieldsSha256"] == report["outputs"]["fieldsSha256"], "artifact visual field digest mismatch")
    require(corrected_visual["fieldsSha256"] == report["outputs"]["fieldsSha256"], "corrected visual field digest mismatch")
    require(len(corrected_visual["views"]) == 4, "corrected view count mismatch")
    for view in corrected_visual["views"]:
        corrected = ROOT / "maps" / view["path"]
        previous = OLD_ROOT / "maps" / view["path"]
        require(sha256(corrected) == view["sha256"], f"corrected map digest mismatch: {view['path']}")
        require(corrected.read_bytes() == previous.read_bytes(), f"kernel v2/v3 map mismatch: {view['path']}")

    with np.load(ROOT / "pilot-final-fields.npz", allow_pickle=False) as fields:
        depth = fields["waterDepthM"]
        u = fields["velocityUms"]
        v = fields["velocityVms"]
        require(depth.size == 50199, "field cell count mismatch")
        require(np.isfinite(depth).all() and np.isfinite(u).all() and np.isfinite(v).all(), "non-finite retained fields")
        require(not np.any(depth < 0), "negative retained depth")

    require(comparison["status"] == "passed_equivalent_physical_result_and_speedup", "comparison status mismatch")
    require(comparison["equivalence"]["maximumRelativeDifferenceAcrossFields"] <= 1e-12, "kernel equivalence tolerance failed")
    require(comparison["equivalence"]["correctedMapJpegsByteIdentical"] is True, "corrected maps are not identical")
    require(comparison["speed"]["physicalPilotSpeedup"] > 1, "physical pilot did not accelerate")

    safeguards = result["safeguards"]
    require(all(safeguards[key] is False for key in (
        "additionalPhysicalRunAuthorized",
        "elevenBasisCampaignAuthorized",
        "paidResourceAuthorized",
        "publicSimulatorConnected",
        "mainMergeAuthorized",
        "physicalValidationClaimAllowed",
    )), "result safeguard mismatch")

    print(json.dumps({
        "schema": "onga-stage20-kernel-v3-physical-pilot-result-validation-v1",
        "status": "passed_equivalent_not_physical_validation",
        "githubRunId": result["github"]["runId"],
        "simulatedSeconds": report["run"]["simulatedSeconds"],
        "wallSeconds": report["run"]["wallSeconds"],
        "physicalPilotSpeedup": comparison["speed"]["physicalPilotSpeedup"],
        "maximumRelativeDifferenceAcrossFields": comparison["equivalence"]["maximumRelativeDifferenceAcrossFields"],
        "correctedMapsByteIdentical": True,
        "checkpointCount": len(progress["checkpoints"]),
        "viewCount": len(corrected_visual["views"]),
        "gateConsumed": True,
        "additionalRunAuthorized": False,
        "elevenBasisCampaignAuthorized": False,
        "physicalValidationClaimAllowed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
