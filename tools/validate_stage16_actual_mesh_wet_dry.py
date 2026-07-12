#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import numpy as np


def check(name, value, expected, ok):
    return {"name": name, "value": value, "expected": expected, "ok": bool(ok)}


def update_flags(depth, previous, wet_threshold, dry_threshold):
    depth = np.asarray(depth, dtype=np.float64)
    if np.any(~np.isfinite(depth)) or np.any(depth < 0):
        raise ValueError("depth must be finite and nonnegative")
    if not (0 <= dry_threshold < wet_threshold):
        raise ValueError("threshold ordering is invalid")
    if previous is None:
        wet = depth >= wet_threshold
        newly_wet = wet.copy()
        newly_dry = np.zeros_like(wet)
    else:
        previous = np.asarray(previous, dtype=bool)
        if previous.shape != depth.shape:
            raise ValueError("previous wet mask shape mismatch")
        wet = np.where(previous, depth > dry_threshold, depth >= wet_threshold)
        newly_wet = (~previous) & wet
        newly_dry = previous & (~wet)
    return wet, newly_wet, newly_dry


def regularise(depth, momentum_x, momentum_y, areas, wet, reference_depth, maximum_speed):
    h = np.asarray(depth, dtype=np.float64).copy()
    hu = np.asarray(momentum_x, dtype=np.float64).copy()
    hv = np.asarray(momentum_y, dtype=np.float64).copy()
    areas = np.asarray(areas, dtype=np.float64)
    if not (h.shape == hu.shape == hv.shape == areas.shape == wet.shape):
        raise ValueError("state vector shape mismatch")
    dry = ~wet
    removed_volume = float(np.sum(h[dry] * areas[dry]))
    h[dry] = 0
    hu[dry] = 0
    hv[dry] = 0
    denominator = np.maximum(h, reference_depth)
    u = np.divide(hu, denominator, out=np.zeros_like(hu), where=wet)
    v = np.divide(hv, denominator, out=np.zeros_like(hv), where=wet)
    speed_before = np.hypot(u, v)
    scale = np.ones_like(h)
    over = wet & (speed_before > maximum_speed)
    scale[over] = maximum_speed / speed_before[over]
    u *= scale
    v *= scale
    hu[wet] = h[wet] * u[wet]
    hv[wet] = h[wet] * v[wet]
    speed_after = np.divide(np.hypot(hu, hv), h, out=np.zeros_like(h), where=h > 0)
    return {
        "h": h,
        "hu": hu,
        "hv": hv,
        "removed_volume": removed_volume,
        "speed_before": speed_before,
        "speed_after": speed_after,
        "capped": over,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh")
    parser.add_argument("--output", default="stage16_actual_mesh_wet_dry_validation.json")
    args = parser.parse_args()

    mesh = np.load(args.mesh)
    vertices = mesh["vertex_local_mm"].astype(np.float64) * 1e-3
    triangles = mesh["triangles"].astype(np.int32)
    points = vertices[triangles]
    centroids = points.mean(axis=1)
    areas = np.abs(
        (points[:, 1, 0] - points[:, 0, 0]) * (points[:, 2, 1] - points[:, 0, 1])
        - (points[:, 1, 1] - points[:, 0, 1]) * (points[:, 2, 0] - points[:, 0, 0])
    ) / 2
    cell_count = len(triangles)

    x = (centroids[:, 0] - centroids[:, 0].min()) / np.ptp(centroids[:, 0])
    y = (centroids[:, 1] - centroids[:, 1].min()) / np.ptp(centroids[:, 1])
    bed = 0.72 * x + 0.08 * np.sin(2 * np.pi * y) + 0.03 * np.sin(4 * np.pi * x)

    wet_threshold = 0.02
    dry_threshold = 0.01
    reference_depth = wet_threshold
    maximum_speed = 3.0

    surface_sequence = [0.35, 0.48, 0.465, 0.475, 0.455, 0.62, 0.31]
    previous = None
    transition_count = 0
    hysteresis_violations = 0
    activation_violations = 0
    deactivation_violations = 0
    repeated_state_error = 0
    minimum_depth = float("inf")
    maximum_speed_after = 0
    maximum_direction_error = 0
    maximum_volume_accounting_error = 0
    maximum_threshold_removal_excess = 0
    maximum_wet_depth_change = 0
    wet_counts = []
    transition_counts = []
    removed_volumes = []

    for step, surface in enumerate(surface_sequence):
        raw_depth = np.maximum(0, surface - bed)
        wet, newly_wet, newly_dry = update_flags(
            raw_depth,
            previous,
            wet_threshold,
            dry_threshold,
        )
        if previous is not None:
            band = (raw_depth > dry_threshold) & (raw_depth < wet_threshold)
            hysteresis_violations += int(np.count_nonzero(wet[band] != previous[band]))
            activation_violations += int(np.count_nonzero(newly_wet & (raw_depth < wet_threshold)))
            deactivation_violations += int(np.count_nonzero(newly_dry & (raw_depth > dry_threshold)))
        transition_count += int(np.count_nonzero(newly_wet) + np.count_nonzero(newly_dry))

        base_u = 0.7 + 45 * np.exp(-raw_depth / 0.004)
        base_v = -0.35 + 18 * np.exp(-raw_depth / 0.006)
        hu = raw_depth * base_u
        hv = raw_depth * base_v
        regularised = regularise(
            raw_depth,
            hu,
            hv,
            areas,
            wet,
            reference_depth,
            maximum_speed,
        )

        raw_volume = float(np.sum(raw_depth * areas))
        retained_volume = float(np.sum(regularised["h"] * areas))
        accounting_error = abs(raw_volume - retained_volume - regularised["removed_volume"])
        maximum_volume_accounting_error = max(maximum_volume_accounting_error, accounting_error)
        threshold_bound = float(np.sum(areas[~wet]) * wet_threshold)
        maximum_threshold_removal_excess = max(
            maximum_threshold_removal_excess,
            regularised["removed_volume"] - threshold_bound,
        )
        if np.any(wet):
            maximum_wet_depth_change = max(
                maximum_wet_depth_change,
                float(np.max(np.abs(regularised["h"][wet] - raw_depth[wet]))),
            )
            direction_before = np.arctan2(hv[wet], hu[wet])
            direction_after = np.arctan2(regularised["hv"][wet], regularised["hu"][wet])
            finite_direction = np.hypot(hu[wet], hv[wet]) > 1e-15
            if np.any(finite_direction):
                angle_error = np.abs(
                    np.arctan2(
                        np.sin(direction_after[finite_direction] - direction_before[finite_direction]),
                        np.cos(direction_after[finite_direction] - direction_before[finite_direction]),
                    )
                )
                maximum_direction_error = max(maximum_direction_error, float(np.max(angle_error)))
        minimum_depth = min(minimum_depth, float(np.min(regularised["h"])))
        maximum_speed_after = max(maximum_speed_after, float(np.max(regularised["speed_after"])))

        repeated, _, _ = update_flags(raw_depth, wet, wet_threshold, dry_threshold)
        repeated_state_error = max(
            repeated_state_error,
            int(np.count_nonzero(repeated != wet)),
        )

        wet_counts.append(int(np.count_nonzero(wet)))
        transition_counts.append(int(np.count_nonzero(newly_wet) + np.count_nonzero(newly_dry)))
        removed_volumes.append(regularised["removed_volume"])
        previous = wet

    exact_band_depth = np.full(cell_count, 0.015)
    half = np.zeros(cell_count, dtype=bool)
    half[: cell_count // 2] = True
    retained, _, _ = update_flags(
        exact_band_depth,
        half,
        wet_threshold,
        dry_threshold,
    )
    exact_band_error = int(np.count_nonzero(retained != half))

    dry_test = np.zeros(cell_count)
    dry_wet, _, _ = update_flags(dry_test, np.zeros(cell_count, dtype=bool), wet_threshold, dry_threshold)
    dry_regularised = regularise(
        dry_test,
        np.ones(cell_count),
        -np.ones(cell_count),
        areas,
        dry_wet,
        reference_depth,
        maximum_speed,
    )
    dry_state_error = float(
        max(
            np.max(np.abs(dry_regularised["h"])),
            np.max(np.abs(dry_regularised["hu"])),
            np.max(np.abs(dry_regularised["hv"])),
        )
    )

    checks = [
        check("all cell areas positive", float(areas.min()), ">0", float(areas.min()) > 0),
        check("wet-dry state vector covers every cell", len(previous), cell_count, len(previous) == cell_count),
        check("hysteresis band retains previous state", hysteresis_violations, 0, hysteresis_violations == 0),
        check("newly wet cells satisfy wet threshold", activation_violations, 0, activation_violations == 0),
        check("newly dry cells satisfy dry threshold", deactivation_violations, 0, deactivation_violations == 0),
        check("repeated classification is idempotent", repeated_state_error, 0, repeated_state_error == 0),
        check("exact hysteresis-band relabelling", exact_band_error, 0, exact_band_error == 0),
        check("regularised depth nonnegative", minimum_depth, ">=0", minimum_depth >= 0),
        check("dry state momentum reset", dry_state_error, "<1e-12", dry_state_error < 1e-12),
        check("maximum shallow-cell speed", maximum_speed_after, "<=3", maximum_speed_after <= maximum_speed + 1e-12),
        check("velocity direction preserved", maximum_direction_error, "<1e-12", maximum_direction_error < 1e-12),
        check("wet-cell depth unchanged", maximum_wet_depth_change, "<1e-12", maximum_wet_depth_change < 1e-12),
        check("removed-volume accounting", maximum_volume_accounting_error, "<1e-8", maximum_volume_accounting_error < 1e-8),
        check("sub-threshold removal bound", maximum_threshold_removal_excess, "<=0", maximum_threshold_removal_excess <= 1e-8),
        check("dynamic sequence contains transitions", transition_count, ">0", transition_count > 0),
    ]

    report = {
        "schema": "onga-stage16-actual-mesh-wet-dry-validation-v1",
        "status": "passed" if all(item["ok"] for item in checks) else "failed",
        "counts": {
            "cells": cell_count,
            "sequenceSteps": len(surface_sequence),
            "totalTransitions": transition_count,
        },
        "diagnostics": {
            "wetThresholdM": wet_threshold,
            "dryThresholdM": dry_threshold,
            "surfaceSequenceM": surface_sequence,
            "wetCellCounts": wet_counts,
            "transitionCounts": transition_counts,
            "removedVolumesM3": removed_volumes,
            "maximumSpeedAfterMPerS": maximum_speed_after,
            "maximumDirectionErrorRad": maximum_direction_error,
            "maximumVolumeAccountingErrorM3": maximum_volume_accounting_error,
            "maximumThresholdRemovalExcessM3": maximum_threshold_removal_excess,
        },
        "safeguards": {
            "syntheticBathymetryOnly": True,
            "syntheticSurfaceSequenceOnly": True,
            "geometryCellsActivatedOrRemoved": False,
            "connectedToPublicSimulator": False,
            "approvedWaterGeometryChanged": False,
            "physicalValuesAssigned": False,
            "calibrationPerformed": False,
        },
        "checks": checks,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise RuntimeError("actual mesh wet-dry verification failed")


if __name__ == "__main__":
    main()
