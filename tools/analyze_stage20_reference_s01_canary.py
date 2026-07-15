#!/usr/bin/env python3
"""Analyze and digest-verify the retained Stage 20 reference-s01 canary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="docs/results/stage20-reference-s01-canary-29415527789")
    parser.add_argument("--output", default="config/stage20_reference_s01_canary_analysis_v1.json")
    args = parser.parse_args()
    root = Path(args.root)
    evidence = load(root / "evidence-manifest.json")
    report = load(root / "segment-report.json")
    require(evidence["status"] == "sealed_complete_not_physical_validation", "evidence status mismatch")
    for item in evidence["files"]:
        path = root / item["path"]
        require(path.stat().st_size == item["byteLength"], f"byte length mismatch: {item['path']}")
        require(sha256(path) == item["sha256"], f"digest mismatch: {item['path']}")

    hourly = []
    previous_velocity = None
    for path in sorted((root / "checkpoints").glob("checkpoint-*.npz")):
        with np.load(path, allow_pickle=False) as checkpoint:
            state = checkpoint["state"]
            require(state.shape == (50199, 3), f"state shape mismatch: {path.name}")
            require(np.isfinite(state).all(), f"non-finite checkpoint: {path.name}")
            depth = state[:, 0]
            require(np.all(depth >= 0), f"negative depth checkpoint: {path.name}")
            u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
            v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
            speed = np.hypot(u, v)
            rms_change = None
            if previous_velocity is not None:
                rms_change = float(np.sqrt(np.mean((u - previous_velocity[0]) ** 2 + (v - previous_velocity[1]) ** 2)))
            hourly.append({
                "checkpoint": path.name,
                "sha256": sha256(path),
                "elapsedSeconds": float(checkpoint["elapsed_seconds"]),
                "step": int(checkpoint["step"]),
                "meanDepthM": float(depth.mean()),
                "maximumDepthM": float(depth.max()),
                "meanSpeedMPS": float(speed.mean()),
                "medianSpeedMPS": float(np.median(speed)),
                "maximumSpeedMPS": float(speed.max()),
                "rmsVelocityChangeFromPriorMPS": rms_change,
            })
            previous_velocity = (u.copy(), v.copy())

    require(len(hourly) == 8, "hourly checkpoint count mismatch")
    with np.load(root / "restart-final.npz", allow_pickle=False) as restart, np.load(root / "segment-final-fields.npz", allow_pickle=False) as fields:
        state = restart["state"]
        depth = state[:, 0]
        u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
        v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
        require(np.array_equal(depth, fields["waterDepthM"]), "final depth mismatch")
        require(np.array_equal(u, fields["velocityUms"]), "final u mismatch")
        require(np.array_equal(v, fields["velocityVms"]), "final v mismatch")

    wall_seconds = float(report["run"]["wallSeconds"])
    actual_per_segment_hours = wall_seconds / 3600.0
    result = {
        "schema": "onga-stage20-reference-s01-canary-analysis-v1",
        "status": "passed_digest_and_state_analysis_not_physical_validation",
        "githubRunId": 29415527789,
        "evidenceManifestSha256": sha256(root / "evidence-manifest.json"),
        "evidenceFilesVerified": len(evidence["files"]),
        "finalStateMatchesFieldsExactly": True,
        "hourly": hourly,
        "resourceUpdate": {
            "actualWallSecondsPerEightHourReferenceSegment": wall_seconds,
            "actualWallHoursPerEightHourReferenceSegment": actual_per_segment_hours,
            "marginToFiveHourStopSeconds": 18000.0 - wall_seconds,
            "simpleProjectionOneSixSegmentReferenceBasisRunnerHours": actual_per_segment_hours * 6.0,
            "simpleProjectionAllSixtySixSegmentsRunnerHours": actual_per_segment_hours * 66.0,
            "notAGuaranteeForOtherBasisSegments": True,
        },
        "interpretation": {
            "dynamicTideResponseContinuesAcrossHourlyCheckpoints": True,
            "staticSteadyStateClaimAllowed": False,
            "warmupSufficiencyProven": False,
            "reason": "the_forcing_is_time_varying_and_the_last_hour_rms_velocity_change_is_nonzero",
        },
        "safeguards": {
            "additionalRunAuthorized": False,
            "remainingSegmentsAuthorized": False,
            "campaignAuthorized": False,
            "physicalValidationClaimAllowed": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
