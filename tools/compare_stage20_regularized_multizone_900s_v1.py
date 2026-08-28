#!/usr/bin/env python3
"""Compare the regularized 900 s result with the frozen R1C baseline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiLineString, Point


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import evaluate_stage20_R20_multizone_field_convergence_v1 as spatial
import generate_stage20_fishway_F3_review_mesh_v1 as projection
import stage20_depth_weighted_boundary_kernel_candidate_v2 as kernel


BASELINE_MESH = ROOT / "docs/results/stage20-barrage-candidate-C-R1C-next-stage-review-approval-v1/review-mesh.npz"
BASELINE_FIELDS = ROOT / "docs/results/stage20-constrained-bathymetry-continuity-v2-20260828/continuity-fields.npz"
BASELINE_STATE = ROOT / "docs/results/stage20-continuous-all-closed-900s-yoda-canary-20260828-v3/final-state.npy"
CANDIDATE_MESH = ROOT / "docs/results/stage20-regularized-multizone-mesh-candidate-v1/regularized-multizone-review-mesh.npz"
CANDIDATE_FIELDS = ROOT / "docs/results/stage20-regularized-multizone-continuous-fields-v1/continuous-fields.npz"
CANDIDATE_STATE = ROOT / "docs/results/stage20-regularized-multizone-900s-yoda-canary-20260828-v1/final-state.npy"
CONTRACT = ROOT / "config/stage20_regularized_multizone_900s_runner_v1.json"
CUT = ROOT / "config/stage20_barrage_bank_to_bank_cut_authority_v1.geojson"
OUTPUT = ROOT / "docs/results/stage20-regularized-multizone-900s-dynamic-equivalence-v1"
REPORT = OUTPUT / "report.json"

EXPECTED_SHA = {
    BASELINE_MESH: "7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164",
    BASELINE_FIELDS: "7d345f98185d592bc0af50787b4eea98753e6ab17bf1f8f7104a19cdc0b2320c",
    BASELINE_STATE: "b8591ef28321439ceeb91d3789a5cfea9731a7a0e263d2e1597074d92247a3aa",
    CANDIDATE_MESH: "d42d5bcf2809eb89b358afc02dfe2f338f7006e2f7eae18305e7e9139a610ae6",
    CANDIDATE_FIELDS: "afc48e005c02a671eb84bc184bdd45b615bcf05a401cd5f0c2ecd6844ba1ec6b",
    CANDIDATE_STATE: "9582bda64348dbcbc52467d6a1932884eb4233eef4870da464618f6909d07419",
    CONTRACT: "468e74fa6b34a339ee2ddd624005de32d6a157ce5d4b5c3ccee2eb4f53cdaf2d",
}
WET_THRESHOLDS_M = (0.0, 0.01, 0.05, 0.1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def map_componentwise(
    source_points: np.ndarray,
    source_component: np.ndarray,
    values: np.ndarray,
    query_points: np.ndarray,
    query_component: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    result = np.empty(len(query_points), dtype=np.float64)
    fallback_count = 0
    fallback_maximum_distance = 0.0
    for source_mask, query_mask in (
        (source_component, query_component),
        (~source_component, ~query_component),
    ):
        points = source_points[source_mask]
        query = query_points[query_mask]
        mapped = np.asarray(
            LinearNDInterpolator(points, values[source_mask], fill_value=np.nan)(query),
            dtype=np.float64,
        )
        missing = ~np.isfinite(mapped)
        if np.any(missing):
            distances, indices = cKDTree(points).query(query[missing], k=1)
            mapped[missing] = values[source_mask][np.asarray(indices, dtype=np.int64)]
            fallback_count += int(np.sum(missing))
            fallback_maximum_distance = max(
                fallback_maximum_distance, float(np.max(distances))
            )
        result[query_mask] = mapped
    return result, {
        "fallbackCellCount": fallback_count,
        "fallbackMaximumDistanceM": fallback_maximum_distance,
    }


def weighted_rmse(error: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sqrt(np.sum(weights * error * error) / np.sum(weights)))


def zone_masks(centroids: np.ndarray) -> dict[str, np.ndarray]:
    cut = json.loads(CUT.read_text(encoding="utf-8"))
    lines = [
        LineString(projection.project_many(feature["geometry"]["coordinates"]))
        for feature in cut["features"]
    ]
    barrage = MultiLineString(lines)
    barrage_mask = np.asarray(
        [barrage.distance(Point(float(x), float(y))) <= 100.0 for x, y in centroids],
        dtype=bool,
    )
    confluence_mask = (
        np.linalg.norm(centroids - spatial.NISHIKAWA, axis=1) <= 150.0
    ) | (
        np.linalg.norm(centroids - spatial.MAGARIGAWA, axis=1) <= 180.0
    )
    return {
        "full_domain": np.ones(len(centroids), dtype=bool),
        "barrage_100m": barrage_mask,
        "confluence": confluence_mask,
    }


def build_report() -> dict[str, Any]:
    actual_sha = {str(path.relative_to(ROOT)): sha256(path) for path in EXPECTED_SHA}
    require(
        all(actual_sha[str(path.relative_to(ROOT))] == digest for path, digest in EXPECTED_SHA.items()),
        "input identity mismatch",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    thresholds = contract["acceptance"]["postRunDynamicEquivalenceRequiredForMeshAdoption"]
    baseline_geometry = kernel.build_review_geometry(kernel.mesh_arrays(BASELINE_MESH))
    candidate_geometry = kernel.build_review_geometry(kernel.mesh_arrays(CANDIDATE_MESH))
    baseline_state = np.load(BASELINE_STATE, allow_pickle=False)
    candidate_state = np.load(CANDIDATE_STATE, allow_pickle=False)
    with np.load(BASELINE_FIELDS, allow_pickle=False) as archive:
        baseline_bed = np.asarray(archive["continuous_candidate_bed_elevation_m"], dtype=np.float64)
        baseline_component = np.asarray(archive["upstream_component_mask"], dtype=np.uint8).astype(bool)
    with np.load(CANDIDATE_FIELDS, allow_pickle=False) as archive:
        candidate_bed = np.asarray(archive["continuous_bed_elevation_m"], dtype=np.float64)
        candidate_component = np.asarray(archive["upstream_component_mask"], dtype=np.uint8).astype(bool)
    require(baseline_state.shape == (37724, 3), "baseline state shape changed")
    require(candidate_state.shape == (28746, 3), "candidate state shape changed")

    baseline_values = {
        "depth": baseline_state[:, 0],
        "eta": baseline_state[:, 0] + baseline_bed,
        "u": np.divide(baseline_state[:, 1], baseline_state[:, 0], out=np.zeros(37724), where=baseline_state[:, 0] > 1e-12),
        "v": np.divide(baseline_state[:, 2], baseline_state[:, 0], out=np.zeros(37724), where=baseline_state[:, 0] > 1e-12),
    }
    candidate_values = {
        "depth": candidate_state[:, 0],
        "eta": candidate_state[:, 0] + candidate_bed,
        "u": np.divide(candidate_state[:, 1], candidate_state[:, 0], out=np.zeros(28746), where=candidate_state[:, 0] > 1e-12),
        "v": np.divide(candidate_state[:, 2], candidate_state[:, 0], out=np.zeros(28746), where=candidate_state[:, 0] > 1e-12),
    }
    mapped: dict[str, np.ndarray] = {}
    mapping: dict[str, Any] = {}
    for name, values in candidate_values.items():
        mapped[name], mapping[name] = map_componentwise(
            candidate_geometry["centroids"], candidate_component, values,
            baseline_geometry["centroids"], baseline_component,
        )

    metrics: dict[str, Any] = {}
    all_pass = True
    for zone, zone_mask in zone_masks(baseline_geometry["centroids"]).items():
        areas = baseline_geometry["areas"][zone_mask]
        eta_error = mapped["eta"][zone_mask] - baseline_values["eta"][zone_mask]
        eta_metrics = {
            "cellWeightedRmseM": float(np.sqrt(np.mean(eta_error * eta_error))),
            "areaWeightedRmseM": weighted_rmse(eta_error, areas),
            "maximumAbsoluteDifferenceM": float(np.max(np.abs(eta_error))),
        }
        velocity_metrics: dict[str, Any] = {}
        velocity_pass = True
        for wet_threshold in WET_THRESHOLDS_M:
            wet = zone_mask & (baseline_values["depth"] >= wet_threshold) & (mapped["depth"] >= wet_threshold)
            squared = (
                (mapped["u"][wet] - baseline_values["u"][wet]) ** 2
                + (mapped["v"][wet] - baseline_values["v"][wet]) ** 2
            )
            area = baseline_geometry["areas"][wet]
            record = {
                "cellCount": int(np.sum(wet)),
                "cellWeightedVectorRmseMPerS": float(np.sqrt(np.mean(squared))),
                "areaWeightedVectorRmseMPerS": float(np.sqrt(np.sum(area * squared) / np.sum(area))),
                "maximumVectorDifferenceMPerS": float(np.sqrt(np.max(squared))),
            }
            record["passBothWeightings"] = (
                max(record["cellWeightedVectorRmseMPerS"], record["areaWeightedVectorRmseMPerS"])
                <= thresholds["maximumVelocityVectorRmseMPerS"]
            )
            velocity_pass &= record["passBothWeightings"]
            velocity_metrics[f"minimumDepth{wet_threshold:g}M"] = record
        eta_pass = max(eta_metrics["cellWeightedRmseM"], eta_metrics["areaWeightedRmseM"]) <= thresholds["maximumWaterSurfaceRmseM"]
        metrics[zone] = {
            "cellCount": int(np.sum(zone_mask)),
            "waterSurface": eta_metrics,
            "velocitySensitivity": velocity_metrics,
            "passWaterSurfaceBothWeightings": eta_pass,
            "passVelocityAllWeightingsAndWetThresholds": velocity_pass,
        }
        all_pass &= eta_pass and velocity_pass
    return {
        "schema": "onga-stage20-regularized-multizone-900s-dynamic-equivalence-v1",
        "version": 1,
        "status": (
            "PASS_DYNAMIC_EQUIVALENCE_ROBUST_TO_WEIGHTING_AND_WET_THRESHOLD_MESH_STILL_UNADOPTED"
            if all_pass else "FAIL_DYNAMIC_EQUIVALENCE_MESH_REJECTED"
        ),
        "classification": "MATCHED_ALL_CLOSED_NUMERICAL_COMPARISON_NOT_PHYSICAL_VALIDATION_NOT_FORECAST_NOT_RELEASE",
        "inputSha256": actual_sha,
        "mapping": {
            "method": thresholds["mapping"],
            "candidateToR1CFallback": mapping,
            "weightingSensitivity": ["cell_equal", "R1C_cell_area"],
            "wetDepthThresholdSensitivityM": list(WET_THRESHOLDS_M),
            "contractUnderspecificationHandledByRobustness": True,
        },
        "thresholds": thresholds,
        "zones": metrics,
        "decision": {
            "dynamicEquivalencePass": all_pass,
            "meshAdopted": False,
            "reason": "all-closed 900 s equivalence does not validate opened gates, fishway, adverse head, physical correctness, or forecast use",
            "next": "bounded opened-gate and adverse-head canaries before operational mesh adoption",
        },
    }


def main() -> None:
    report = build_report()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
