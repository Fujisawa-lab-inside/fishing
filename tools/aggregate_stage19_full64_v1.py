#!/usr/bin/env python3
"""Aggregate Stage 19 endpoint fields into the five approved map statistics."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage19-aggregate] {message}")


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: str | Path, value: dict) -> None:
    destination = Path(path)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, destination)


def save_npz(path: str | Path, **arrays: np.ndarray) -> None:
    destination = Path(path)
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(temporary, destination)


def bounds(values: np.ndarray) -> dict:
    return {"minimum": float(np.min(values)), "maximum": float(np.max(values))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fields")
    parser.add_argument("report")
    parser.add_argument("--statistics-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--dry-threshold-m", type=float, default=0.05)
    parser.add_argument("--direction-speed-threshold-ms", type=float, default=1e-9)
    args = parser.parse_args()
    for output in (args.statistics_output, args.summary_output):
        require(not Path(output).exists(), f"output already exists: {output}")
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    require(report["schema"] == "onga-stage19-full64-run-report-v1" and report["status"] == "passed", "run did not pass")
    require(report["completedCaseCount"] == 64 and report["failedCaseCount"] == 0, "64/64 required")
    require(report["fieldArtifact"]["sha256"] == sha256(args.fields), "field digest mismatch")
    with np.load(args.fields, allow_pickle=False) as archive:
        require(str(archive["schema"].item()) == "onga-stage19-full64-fields-v1", "field schema")
        depth = np.asarray(archive["water_depth_m"], dtype=np.float64)
        u = np.asarray(archive["velocity_u_ms"], dtype=np.float64)
        v = np.asarray(archive["velocity_v_ms"], dtype=np.float64)
    require(depth.shape == (64, 50129) and u.shape == depth.shape and v.shape == depth.shape, "field shape")
    require(np.isfinite(depth).all() and np.isfinite(u).all() and np.isfinite(v).all(), "nonfinite field")
    speed = np.hypot(u, v)
    depth_median = np.median(depth, axis=0)
    velocity_median = np.median(speed, axis=0)
    wet_probability = np.mean(depth > args.dry_threshold_m, axis=0)
    active = (depth > args.dry_threshold_m) & (speed > args.direction_speed_threshold_ms)
    unit_u = np.divide(u, speed, out=np.zeros_like(u), where=active)
    unit_v = np.divide(v, speed, out=np.zeros_like(v), where=active)
    support_count = np.sum(active, axis=0)
    mean_u = np.divide(np.sum(unit_u, axis=0), support_count, out=np.zeros(50129), where=support_count > 0)
    mean_v = np.divide(np.sum(unit_v, axis=0), support_count, out=np.zeros(50129), where=support_count > 0)
    direction_agreement = np.hypot(mean_u, mean_v)
    support_fraction = support_count / 64.0
    save_npz(
        args.statistics_output,
        schema=np.array("onga-stage19-full64-step-matched-statistics-v1"),
        cell_id=np.arange(50129, dtype=np.int32),
        water_depth_median_m=depth_median,
        velocity_median_ms=velocity_median,
        wet_probability=wet_probability,
        flow_direction_agreement_fraction=direction_agreement,
        direction_sample_support_fraction=support_fraction,
        source_fields_sha256=np.array(sha256(args.fields)),
        source_report_sha256=np.array(sha256(args.report)),
        comparison_basis=np.array(report["comparisonBasis"]),
    )
    summary = {
        "schema": "onga-stage19-full64-step-matched-statistics-summary-v1",
        "status": "generated",
        "classification": "provisional_step_matched_outputs_not_physical_validation",
        "sourceCaseCount": 64,
        "cellCount": 50129,
        "fields": {
            "waterDepthMedianM": bounds(depth_median),
            "velocityMedianMs": bounds(velocity_median),
            "wetProbability": bounds(wet_probability),
            "flowDirectionAgreementFraction": bounds(direction_agreement),
            "directionSampleSupportFraction": bounds(support_fraction),
        },
        "source": {
            "fieldsSha256": sha256(args.fields),
            "reportSha256": sha256(args.report),
            "statisticsSha256": sha256(args.statistics_output),
        },
        "interpretationLimits": {
            "comparisonBasis": report["comparisonBasis"],
            "commonPhysicalTimeComparisonAllowed": False,
            "physicalValidationClaimAllowed": False,
            "sensitivityClaimAllowed": False,
            "publicSimulatorConnectionAllowed": False,
        },
    }
    write_json(args.summary_output, summary)
    print(json.dumps({"status": "generated", "statisticsSha256": sha256(args.statistics_output)}))


if __name__ == "__main__":
    main()
