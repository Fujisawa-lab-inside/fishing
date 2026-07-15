#!/usr/bin/env python3
"""Analyze and digest-verify the retained Stage 20 reference-s02 result."""

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


def field_metrics(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as fields:
        depth = fields["waterDepthM"]
        u = fields["velocityUms"]
        v = fields["velocityVms"]
        require(depth.shape == u.shape == v.shape == (50199,), f"field shape mismatch: {path}")
        require(np.isfinite(depth).all() and np.isfinite(u).all() and np.isfinite(v).all(), f"non-finite field: {path}")
        require(np.all(depth >= 0), f"negative depth: {path}")
        speed = np.hypot(u, v)
        return {
            "meanDepthM": float(depth.mean()),
            "maximumDepthM": float(depth.max()),
            "meanSpeedMPS": float(speed.mean()),
            "medianSpeedMPS": float(np.median(speed)),
            "maximumSpeedMPS": float(speed.max()),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="docs/results/stage20-reference-s02-29434250546")
    parser.add_argument("--s01-root", default="docs/results/stage20-reference-s01-canary-29415527789")
    parser.add_argument("--output", default="config/stage20_reference_s02_analysis_v1.json")
    args = parser.parse_args()
    root = Path(args.root)
    s01_root = Path(args.s01_root)
    evidence = load(root / "evidence-manifest.json")
    report = load(root / "segment-report.json")
    progress = load(root / "progress.json")
    receipt = load(root / "execution-receipt.json")
    require(evidence["status"] == "sealed_complete_not_physical_validation", "evidence status mismatch")
    require(progress["status"] == "complete", "progress is incomplete")
    for item in evidence["files"]:
        path = root / item["path"]
        require(path.stat().st_size == item["byteLength"], f"byte length mismatch: {item['path']}")
        require(sha256(path) == item["sha256"], f"digest mismatch: {item['path']}")

    s01_restart_sha = sha256(s01_root / "restart-final.npz")
    require(receipt["inputRestartSha256"] == s01_restart_sha, "S01 input restart digest mismatch")
    require(report["run"]["startStep"] == 2979347, "S01 end step was not retained")
    require(report["run"]["endStep"] - report["run"]["startStep"] == report["run"]["stepsCompletedThisSegment"], "segment step accounting mismatch")

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
                "modelHour": -16 + round(float(checkpoint["elapsed_seconds"]) / 3600),
                "meanDepthM": float(depth.mean()),
                "maximumDepthM": float(depth.max()),
                "meanSpeedMPS": float(speed.mean()),
                "medianSpeedMPS": float(np.median(speed)),
                "maximumSpeedMPS": float(speed.max()),
                "rmsVelocityChangeFromPriorMPS": rms_change,
            })
            previous_velocity = (u.copy(), v.copy())
    require(len(hourly) == 8, "hourly checkpoint count mismatch")

    snapshots = []
    for record in report["outputs"]["snapshots"]:
        path = root / record["path"]
        require(sha256(path) == record["sha256"], f"snapshot digest mismatch: {record['modelHour']}")
        snapshots.append({
            "modelHour": record["modelHour"],
            "path": record["path"],
            "sha256": record["sha256"],
            **field_metrics(path),
        })
    require([item["modelHour"] for item in snapshots] == [-12, -11, -10, -9, -8], "snapshot hour mismatch")

    with np.load(root / "restart-final.npz", allow_pickle=False) as restart, np.load(root / "segment-final-fields.npz", allow_pickle=False) as fields:
        state = restart["state"]
        depth = state[:, 0]
        u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
        v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
        require(np.array_equal(depth, fields["waterDepthM"]), "final depth mismatch")
        require(np.array_equal(u, fields["velocityUms"]), "final u mismatch")
        require(np.array_equal(v, fields["velocityVms"]), "final v mismatch")
    require(snapshots[-1]["sha256"] == sha256(root / "segment-final-fields.npz"), "-8h snapshot is not final fields")
    require(report["outputs"]["checkpoints"][-1]["sha256"] == sha256(root / "restart-final.npz"), "last checkpoint is not final restart")

    wall_seconds = float(report["run"]["wallSeconds"])
    result = {
        "schema": "onga-stage20-reference-s02-analysis-v1",
        "status": "passed_digest_chain_and_state_analysis_not_physical_validation",
        "githubRunId": 29434250546,
        "evidenceManifestSha256": sha256(root / "evidence-manifest.json"),
        "evidenceFilesVerified": len(evidence["files"]),
        "inputRestartSha256": s01_restart_sha,
        "s01ToS02ChainVerified": True,
        "finalStateMatchesFieldsExactly": True,
        "finalSnapshotMatchesFieldsExactly": True,
        "hourly": hourly,
        "snapshots": snapshots,
        "resourceUpdate": {
            "actualWallSeconds": wall_seconds,
            "actualWallHours": wall_seconds / 3600.0,
            "marginToFiveHourStopSeconds": 18000.0 - wall_seconds,
            "differenceFromS01WallSeconds": wall_seconds - 13695.202115381,
            "notAGuaranteeForLaterSegments": True
        },
        "interpretation": {
            "firstRequestedDisplaySnapshotsPresent": True,
            "snapshotHours": [-12, -11, -10, -9, -8],
            "directSolverResultNotBrowserInterpolation": True,
            "physicalValidationClaimAllowed": False,
            "dailyForecastClaimAllowed": False
        },
        "safeguards": {
            "additionalRunAuthorized": False,
            "remainingSegmentsAuthorized": False,
            "campaignAuthorized": False,
            "publicSimulatorConnected": False,
            "mainMergeAuthorized": False
        }
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
