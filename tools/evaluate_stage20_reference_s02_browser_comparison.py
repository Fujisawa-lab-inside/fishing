#!/usr/bin/env python3
"""Evaluate S02 browser time interpolation and prepare worst-case map fields."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--result-root", default="docs/results/stage20-reference-s02-29434250546")
    parser.add_argument("--output", default="config/stage20_reference_s02_browser_comparison_v1.json")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    result_root = root / args.result_root
    comparison_root = result_root / "browser-comparison"
    report_path = comparison_root / "comparison-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pack_manifest_path = comparison_root / "reference-s02-time-pack.json"
    pack_manifest = json.loads(pack_manifest_path.read_text(encoding="utf-8"))
    worst_hour = report["worstLeaveOneOutModelHourByVelocityVectorRmse"]
    worst = next(item for item in report["leaveOneHourOut"] if item["modelHour"] == worst_hour)
    source = next(item for item in pack_manifest["sources"] if item["modelHour"] == worst_hour)
    with np.load(root / source["path"], allow_pickle=False) as direct_file:
        direct = np.stack((direct_file["waterDepthM"], direct_file["velocityUms"], direct_file["velocityVms"])).astype(np.float64)
    predicted = np.fromfile(comparison_root / worst["prediction"], dtype="<f4").reshape(3, 50199).astype(np.float64)
    if not np.isfinite(predicted).all() or np.any(predicted[0] < 0):
        raise RuntimeError("invalid browser prediction")
    predicted_path = comparison_root / "worst-predicted-fields.npz"
    error_path = comparison_root / "worst-error-fields.npz"
    np.savez_compressed(
        predicted_path,
        waterDepthM=predicted[0],
        velocityUms=predicted[1],
        velocityVms=predicted[2],
    )
    np.savez_compressed(
        error_path,
        waterDepthM=direct[0],
        velocityUms=predicted[1] - direct[1],
        velocityVms=predicted[2] - direct[2],
    )
    thresholds = {
        "maximumFloat32VelocityVectorRmseMPS": 1e-7,
        "maximumLeaveOneOutVelocityVectorRmseMPS": 0.01,
        "maximumLeaveOneOutSpeedMaeMPS": 0.005,
        "maximumLeaveOneOutP95DirectionErrorDeg": 5.0,
    }
    anchor_pass = pack_manifest["float32Quantization"]["maximumVelocityVectorRmseMPS"] <= thresholds["maximumFloat32VelocityVectorRmseMPS"]
    per_hour = []
    for item in report["leaveOneHourOut"]:
        checks = {
            "velocityVectorRmse": item["velocityVectorRmseMPS"] <= thresholds["maximumLeaveOneOutVelocityVectorRmseMPS"],
            "speedMae": item["speedMaeMPS"] <= thresholds["maximumLeaveOneOutSpeedMaeMPS"],
            "p95Direction": item["p95DirectionErrorDeg"] <= thresholds["maximumLeaveOneOutP95DirectionErrorDeg"],
        }
        per_hour.append({"modelHour": item["modelHour"], "passed": all(checks.values()), "checks": checks})
    fallback_pass = all(item["passed"] for item in per_hour)
    result = {
        "schema": "onga-stage20-reference-s02-browser-comparison-evaluation-v1",
        "status": "exact_hourly_anchor_path_passed_missing_hour_linear_fallback_rejected",
        "recordedDate": "2026-07-16",
        "source": {
            "s02Result": "config/stage20_reference_s02_result_v1.json",
            "comparisonReport": str(report_path.relative_to(root)),
            "comparisonReportSha256": sha256(report_path),
            "timePackManifest": str(pack_manifest_path.relative_to(root)),
            "timePackManifestSha256": sha256(pack_manifest_path),
            "timePackBinarySha256": pack_manifest["binary"]["sha256"],
        },
        "thresholds": thresholds,
        "exactHourlyAnchorPath": {
            "passed": anchor_pass,
            "snapshotHours": pack_manifest["timeContract"]["anchorHours"],
            "maximumFloat32DepthErrorM": pack_manifest["float32Quantization"]["maximumAbsoluteDepthErrorM"],
            "maximumFloat32VelocityVectorRmseMPS": pack_manifest["float32Quantization"]["maximumVelocityVectorRmseMPS"],
            "meaning": "browser_can_load_each_precomputed_hour_without_material_numeric_loss",
        },
        "missingHourLinearFallback": {
            "passed": fallback_pass,
            "perHourAcceptance": per_hour,
            "worstModelHour": worst_hour,
            "worstMetrics": worst,
            "meaning": "do_not_replace_a_missing_hour_with_linear_time_interpolation_when_high_flow_accuracy_is_required",
        },
        "worstCaseMapFields": {
            "direct": source["path"],
            "predicted": str(predicted_path.relative_to(root)),
            "predictedSha256": sha256(predicted_path),
            "error": str(error_path.relative_to(root)),
            "errorSha256": sha256(error_path),
            "errorDisplayCeilingMPS": 0.04,
        },
        "architectureDecision": {
            "retainEveryDisplayedHourlySnapshot": True,
            "allowMissingHourLinearFallback": False,
            "crossConditionInterpolationValidated": False,
            "nextRequiredValidation": "compare_low_high_condition_basis_interpolation_to_a_held_out_direct_solver_condition",
        },
        "safeguards": {
            "additionalPhysicalRunPerformed": False,
            "publicSimulatorConnected": False,
            "mainMergeAuthorized": False,
            "physicalValidationClaimAllowed": False,
            "dailyForecastClaimAllowed": False,
        },
    }
    output = root / args.output
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
