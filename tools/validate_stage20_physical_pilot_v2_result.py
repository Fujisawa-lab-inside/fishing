#!/usr/bin/env python3
"""Validate the retained Stage 20 physical-pilot-v2 result and corrected maps."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path("docs/results/stage20-physical-pilot-v2-29396657600")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    result = load(ROOT / "run-result.json")
    report = load(ROOT / "pilot-report.json")
    progress = load(ROOT / "pilot-progress.json")
    receipt = load(ROOT / "execution-receipt.json")
    evidence = load(ROOT / "pilot-evidence-manifest.json")
    visual = load(ROOT / "pilot-visual-manifest.json")
    gate = load(Path("config/stage20_physical_pilot_v2_gate_v1.json"))
    authorization = load(Path("config/stage20_physical_pilot_v2_authorization_v1.json"))

    require(result["github"]["runId"] == 29396657600, "run ID mismatch")
    require(receipt["githubRunId"] == "29396657600", "receipt run ID mismatch")
    require(receipt["githubSha"] == result["github"]["executionCommit"], "execution commit mismatch")
    require(gate["state"] == "consumed", "one-time gate is not consumed")
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
    require(sha256(ROOT / "pilot-visual-manifest.json") == result["evidence"]["correctedLocalVisualManifestSha256"], "corrected visual manifest digest mismatch")

    retained_originals = {"execution-receipt.json", "pilot-progress.json", "pilot-report.json", "pilot-final-fields.npz"}
    for item in evidence["files"]:
        if item["path"] in retained_originals:
            require(sha256(ROOT / item["path"]) == item["sha256"], f"retained artifact digest mismatch: {item['path']}")

    require(visual["fieldsSha256"] == report["outputs"]["fieldsSha256"], "corrected visual fields digest mismatch")
    for view in visual["views"]:
        require(sha256(ROOT / "maps" / view["path"]) == view["sha256"], f"corrected map digest mismatch: {view['path']}")

    with np.load(ROOT / "pilot-final-fields.npz", allow_pickle=False) as fields:
        depth = fields["waterDepthM"]
        u = fields["velocityUms"]
        v = fields["velocityVms"]
        require(depth.size == 50199, "field cell count mismatch")
        require(np.isfinite(depth).all() and np.isfinite(u).all() and np.isfinite(v).all(), "non-finite retained fields")
        require(not np.any(depth < 0), "negative retained depth")

    decision = Path("docs/visuals/stage20-physical-pilot-v2-result-decision.jpg")
    require(sha256(decision) == result["evidence"]["visualDecisionSha256"], "decision image digest mismatch")
    print(json.dumps({
        "schema": "onga-stage20-physical-pilot-v2-result-validation-v1",
        "status": "passed_not_physical_validation",
        "githubRunId": result["github"]["runId"],
        "simulatedSeconds": report["run"]["simulatedSeconds"],
        "wallSeconds": report["run"]["wallSeconds"],
        "checkpointCount": len(progress["checkpoints"]),
        "viewCount": len(visual["views"]),
        "gateConsumed": True,
        "additionalRunAuthorized": False,
        "physicalValidationClaimAllowed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
