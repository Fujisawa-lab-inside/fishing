#!/usr/bin/env python3
"""Evaluate R20 and approved multi-zone meshes against one sealed flow field.

This is a bounded spatial-representation diagnostic.  It does not advance the
shallow-water solver.  A sealed 600 s mesh-v2 field is sampled into each review
mesh as a piecewise-constant finite-volume field, then reconstructed on the
same source-cell centroids.  The comparison therefore measures resolution loss
from coarsening while avoiding a new physical run.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.warp import transform
from scipy.spatial import cKDTree
from shapely import points as shapely_points
from shapely import polygons as shapely_polygons
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.strtree import STRtree

import generate_stage16_metric_mesh as stage16
import generate_stage20_barrage_H2_boundary_spacing_comparison_v1 as base
import generate_stage20_fishway_F3_review_mesh_v1 as old
import run_stage20_physical_pilot_v2 as pilot
from stage19_solver_inputs import (
    build_case_fields,
    classify_branch_ownership,
    load_water_mask,
    mesh_geometry,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-R20-multizone-field-convergence-v1"
SUMMARY = OUTPUT / "convergence-summary.json"
VALIDATION = OUTPUT / "static-validation.json"
FIELDS = OUTPUT / "comparison-fields.npz"
MANIFEST = OUTPUT / "manifest.json"

APPROVAL = ROOT / "config/stage20_R20_multizone_mesh_generation_approval_v1.json"
FORMAL_MESH = ROOT / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1/review-mesh.npz"
FORMAL_SUMMARY = ROOT / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1/mesh-summary.json"
MULTIZONE_MESH = ROOT / "docs/results/stage20-R20-multizone-mesh-v1/review-mesh.npz"
MULTIZONE_SUMMARY = ROOT / "docs/results/stage20-R20-multizone-mesh-v1/mesh-summary.json"
SOURCE_CONTRACT = ROOT / "config/stage20_physical_pilot_v2_contract_v1.json"
SOURCE_FIELDS = ROOT / "docs/results/stage20-kernel-v3-physical-pilot-29411976467/pilot-final-fields.npz"
SOURCE_REPORT = ROOT / "docs/results/stage20-kernel-v3-physical-pilot-29411976467/pilot-report.json"
SOURCE_MESH_MANIFEST = ROOT / "public/data/onga/stage20/mesh-v2.json"
SOURCE_MESH_BINARY = ROOT / "public/data/onga/stage20/mesh-v2.bin"
WATER_MANIFEST = ROOT / "data/onga_unified_water_manifest_r3.json"
P2_CANDIDATE = base.P2_CANDIDATE
CUT = base.CUT

EXPECTED = {
    APPROVAL: "c1b348daf891cf7dac189fae88d127d2a0b9654d8d174f6819f2910da494fd93",
    FORMAL_MESH: "315636cb6844b4348863e92e33a342b599a2e27f70983651e81a92490d9b920e",
    FORMAL_SUMMARY: "1c778b8fba2eb36fec507c7b58e6d10ce333b04aea86feab5c6ac6f75c24ab4e",
    MULTIZONE_MESH: "05bd80d3ea80880a9589c01252aaac43e0c7447e1f37d322196cafb4b32c0bb5",
    MULTIZONE_SUMMARY: "556bd72eae7bfda949ccd76bcaf93798e1d388aa33a30db2bf086f303acf4e83",
    SOURCE_CONTRACT: "17e391749ffad8dc7ef1ea4a73bca3e0d0c5a374f9f92ee532b51be84a1d8f1f",
    SOURCE_FIELDS: "3e8fed6ee564a34761081728aa2c1d244cdccfee8a78e9203641f2c985613c3b",
    SOURCE_MESH_BINARY: "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659",
    WATER_MANIFEST: "964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7",
}

NISHIKAWA = np.asarray(old.project_many([[130.67325, 33.891666666666666]])[0])
MAGARIGAWA = np.asarray(old.project_many([[130.6752222222222, 33.894888888888886]])[0])
SCREENING_GUIDES = {
    "waterSurfaceElevationRmseM": 0.10,
    "velocityVectorRmseMPS": 0.01,
}
CIRC = 40075016.68557849


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def binding(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def mesh_arrays(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {key: np.asarray(archive[key]).copy() for key in archive.files}


def metric_vertices_to_image(vertices_m: np.ndarray, coordinate_system: dict) -> np.ndarray:
    _, lonlat_to_image = stage16.coords(coordinate_system)
    lonlat = old.unproject_many(vertices_m)
    return np.asarray(
        [lonlat_to_image(float(lat), float(lon)) for lon, lat in lonlat],
        dtype=np.float64,
    )


def image_to_metric(image_points: np.ndarray, coordinate_system: dict) -> np.ndarray:
    image_to_world, _ = stage16.coords(coordinate_system)
    slippy = np.asarray([image_to_world(point) for point in image_points], dtype=np.float64)
    web_mercator = np.column_stack((slippy[:, 0] - CIRC / 2.0, CIRC / 2.0 - slippy[:, 1]))
    east, north = transform(
        "EPSG:3857",
        "EPSG:32652",
        web_mercator[:, 0].tolist(),
        web_mercator[:, 1].tolist(),
    )
    return np.column_stack((east, north)).astype(np.float64)


class TriangleFinder:
    def __init__(self, vertices: np.ndarray, triangles: np.ndarray):
        self.polygons = shapely_polygons(vertices[triangles])
        self.tree = STRtree(self.polygons)

    def __call__(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        query = shapely_points(x, y)
        pairs = self.tree.query(query, predicate="within")
        result = np.full(len(query), -1, dtype=np.int64)
        if pairs.shape[1]:
            result[pairs[0]] = pairs[1]
        return result


def triangle_finder(vertices: np.ndarray, triangles: np.ndarray) -> TriangleFinder:
    return TriangleFinder(vertices, triangles)


def containing_cells(
    finder: Any,
    query: np.ndarray,
    fallback_centroids: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    cells = np.asarray(finder(query[:, 0], query[:, 1]), dtype=np.int64)
    missing = cells < 0
    fallback_distance = np.empty(0, dtype=np.float64)
    if np.any(missing):
        fallback_distance, fallback_cells = cKDTree(fallback_centroids).query(query[missing], k=1)
        cells[missing] = np.asarray(fallback_cells, dtype=np.int64)
    return cells, {
        "queryCount": int(len(query)),
        "outsideTriangleCount": int(np.sum(missing)),
        "outsideTriangleFraction": float(np.mean(missing)),
        "fallbackMaximumImagePixelDistance": float(fallback_distance.max()) if len(fallback_distance) else 0.0,
    }


def weighted_quantile(values: np.ndarray, weights: np.ndarray, fraction: float) -> float:
    require(len(values) > 0 and len(values) == len(weights), "weighted quantile input is empty")
    order = np.argsort(values)
    ordered = values[order]
    cumulative = np.cumsum(weights[order])
    target = float(fraction) * float(cumulative[-1])
    return float(ordered[min(len(ordered) - 1, int(np.searchsorted(cumulative, target, side="left")))])


def weighted_rmse(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sqrt(np.average(np.square(values), weights=weights)))


def metrics(
    eta: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    reference_eta: np.ndarray,
    reference_u: np.ndarray,
    reference_v: np.ndarray,
    weights: np.ndarray,
) -> dict[str, Any]:
    eta_error = eta - reference_eta
    du = u - reference_u
    dv = v - reference_v
    vector_error = np.hypot(du, dv)
    speed = np.hypot(u, v)
    reference_speed = np.hypot(reference_u, reference_v)
    active = (speed >= 0.02) & (reference_speed >= 0.02)
    if np.any(active):
        cosine = (
            u[active] * reference_u[active] + v[active] * reference_v[active]
        ) / (speed[active] * reference_speed[active])
        direction = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
        direction_p95 = weighted_quantile(direction, weights[active], 0.95)
    else:
        direction_p95 = None
    return {
        "evaluationCellCount": int(len(eta)),
        "evaluationAreaM2": float(weights.sum()),
        "waterSurfaceElevationRmseM": weighted_rmse(eta_error, weights),
        "waterSurfaceElevationMaeM": float(np.average(np.abs(eta_error), weights=weights)),
        "waterSurfaceElevationP95AbsoluteErrorM": weighted_quantile(np.abs(eta_error), weights, 0.95),
        "waterSurfaceElevationMaximumAbsoluteErrorM": float(np.max(np.abs(eta_error))),
        "velocityVectorRmseMPS": weighted_rmse(vector_error, weights),
        "velocityVectorP95ErrorMPS": weighted_quantile(vector_error, weights, 0.95),
        "velocityVectorMaximumErrorMPS": float(np.max(vector_error)),
        "speedMaeMPS": float(np.average(np.abs(speed - reference_speed), weights=weights)),
        "directionComparedCellCount": int(np.sum(active)),
        "p95DirectionErrorDeg": direction_p95,
    }


def metric_delta(multizone: dict[str, Any], formal: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "waterSurfaceElevationRmseM",
        "velocityVectorRmseMPS",
        "speedMaeMPS",
    )
    result = {}
    for key in keys:
        denominator = float(formal[key])
        result[key] = {
            "formalR20": denominator,
            "multizone": float(multizone[key]),
            "absoluteIncrease": float(multizone[key]) - denominator,
            "ratio": float(multizone[key]) / denominator if denominator > 0 else None,
        }
    return result


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for path, expected in EXPECTED.items():
        require(path.is_file(), f"missing pinned input: {path}")
        require(sha256(path) == expected, f"input hash changed: {path}")
    approval = read_json(APPROVAL)
    require(
        approval["status"]
        == "approved_generate_multizone_review_mesh_and_run_bounded_convergence_diagnostic",
        "bounded convergence diagnostic is not approved",
    )
    source_report = read_json(SOURCE_REPORT)
    require(source_report["run"]["simulatedSeconds"] >= 600.0, "sealed source run is incomplete")
    require(source_report["diagnostics"]["nonFiniteValueCount"] == 0, "sealed source has nonfinite values")
    require(source_report["diagnostics"]["negativeDepthCount"] == 0, "sealed source has negative depth")

    contract = read_json(SOURCE_CONTRACT)
    mesh_manifest, source_package = pilot.load_mesh(ROOT, contract)
    water_manifest, mask = load_water_mask(WATER_MANIFEST)
    source_geometry = mesh_geometry(source_package)
    source_owner = classify_branch_ownership(source_package, source_geometry)
    source_bathymetry = build_case_fields(
        contract["scenario"],
        source_package,
        mask,
        geometry=source_geometry,
        owner=source_owner,
    )
    with np.load(SOURCE_FIELDS, allow_pickle=False) as archive:
        source_depth = np.asarray(archive["waterDepthM"], dtype=np.float64)
        source_u = np.asarray(archive["velocityUms"], dtype=np.float64)
        source_v = np.asarray(archive["velocityVms"], dtype=np.float64)
    source_eta = source_depth + np.asarray(source_bathymetry["bedElevationM"], dtype=np.float64)
    require(np.isfinite(source_eta).all(), "source water surface elevation is nonfinite")

    source_image_vertices = (
        source_package["vertex_image_millipixel"].astype(np.float64) * 1.0e-3
    )
    source_triangles = source_package["triangles"].astype(np.int32)
    source_image_centroids = source_image_vertices[source_triangles].mean(axis=1)
    source_metric_vertices = image_to_metric(
        source_image_vertices, water_manifest["coordinateSystem"]
    )
    source_metric_points = source_metric_vertices[source_triangles]
    source_metric_centroids = source_metric_points.mean(axis=1)
    source_metric_ab = source_metric_points[:, 1] - source_metric_points[:, 0]
    source_metric_ac = source_metric_points[:, 2] - source_metric_points[:, 0]
    source_metric_areas = (
        np.abs(
            source_metric_ab[:, 0] * source_metric_ac[:, 1]
            - source_metric_ab[:, 1] * source_metric_ac[:, 0]
        )
        * 0.5
    )
    source_finder = triangle_finder(source_image_vertices, source_triangles)

    candidate_data: dict[str, dict[str, Any]] = {}
    candidate_paths = {"formalR20": FORMAL_MESH, "multizone": MULTIZONE_MESH}
    for candidate_id, path in candidate_paths.items():
        mesh = mesh_arrays(path)
        vertices_metric = np.asarray(mesh["vertices_m"], dtype=np.float64)
        triangles = np.asarray(mesh["triangles"], dtype=np.int32)
        vertices_image = metric_vertices_to_image(
            vertices_metric, water_manifest["coordinateSystem"]
        )
        image_centroids = vertices_image[triangles].mean(axis=1)
        source_cell, source_mapping = containing_cells(
            source_finder, image_centroids, source_image_centroids
        )
        candidate_data[candidate_id] = {
            "mesh": mesh,
            "verticesMetric": vertices_metric,
            "triangles": triangles,
            "verticesImage": vertices_image,
            "imageCentroids": image_centroids,
            "metricCentroids": vertices_metric[triangles].mean(axis=1),
            "finder": triangle_finder(vertices_image, triangles),
            "eta": source_eta[source_cell],
            "u": source_u[source_cell],
            "v": source_v[source_cell],
            "sourceMapping": source_mapping,
        }

    formal_eval = np.asarray(
        candidate_data["formalR20"]["finder"](
            source_image_centroids[:, 0], source_image_centroids[:, 1]
        ),
        dtype=np.int64,
    )
    multizone_eval = np.asarray(
        candidate_data["multizone"]["finder"](
            source_image_centroids[:, 0], source_image_centroids[:, 1]
        ),
        dtype=np.int64,
    )
    formal_inside = formal_eval >= 0
    multizone_inside = multizone_eval >= 0
    domain_disagreement = formal_inside ^ multizone_inside
    valid = formal_inside & multizone_inside
    require(np.any(valid), "no common evaluation cells")
    eval_ids = np.flatnonzero(valid)
    eval_area = source_metric_areas[eval_ids]
    reference_eta = source_eta[eval_ids]
    reference_u = source_u[eval_ids]
    reference_v = source_v[eval_ids]
    formal_cells = formal_eval[eval_ids]
    multizone_cells = multizone_eval[eval_ids]
    formal_eta = candidate_data["formalR20"]["eta"][formal_cells]
    formal_u = candidate_data["formalR20"]["u"][formal_cells]
    formal_v = candidate_data["formalR20"]["v"][formal_cells]
    multizone_eta = candidate_data["multizone"]["eta"][multizone_cells]
    multizone_u = candidate_data["multizone"]["u"][multizone_cells]
    multizone_v = candidate_data["multizone"]["v"][multizone_cells]
    eval_metric = source_metric_centroids[eval_ids]

    cut_geojson = read_json(CUT)
    cut_features = cut_geojson["features"]
    cut_line = MultiLineString(
        [
            old.project_many(feature["geometry"]["coordinates"])
            for feature in cut_features
            if feature["geometry"]["type"] == "LineString"
        ]
    )
    p2_source = read_json(P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_polygons = {
        side: Polygon(old.project_many(p2_source[side]["footprint"]["coordinates"][0][:-1]))
        for side in ("upstream", "downstream")
    }
    barrage_distance = np.asarray(
        [cut_line.distance(Point(point)) for point in eval_metric], dtype=np.float64
    )
    p2_mask = np.asarray(
        [
            p2_polygons["upstream"].covers(Point(point))
            or p2_polygons["downstream"].covers(Point(point))
            for point in eval_metric
        ],
        dtype=bool,
    )
    regions = {
        "fullConfirmedDomain": np.ones(len(eval_ids), dtype=bool),
        "barrageWithin100M": barrage_distance <= 100.0,
        "nishikawaConfluenceWithin150M": np.linalg.norm(eval_metric - NISHIKAWA, axis=1)
        <= 150.0,
        "magarigawaConfluenceWithin180M": np.linalg.norm(eval_metric - MAGARIGAWA, axis=1)
        <= 180.0,
        "fishwayP2Footprints": p2_mask,
    }
    multizone_targets = np.asarray(
        candidate_data["multizone"]["mesh"]["triangle_maximum_area_m2"],
        dtype=np.float64,
    )[multizone_cells]
    for target in (3.0, 30.0, 60.0, 90.0):
        regions[f"multizoneTarget{int(target)}M2"] = np.isclose(multizone_targets, target)

    rows = []
    for region_id, region_mask in regions.items():
        require(np.any(region_mask), f"empty diagnostic region: {region_id}")
        weights = eval_area[region_mask]
        formal_metrics = metrics(
            formal_eta[region_mask],
            formal_u[region_mask],
            formal_v[region_mask],
            reference_eta[region_mask],
            reference_u[region_mask],
            reference_v[region_mask],
            weights,
        )
        multizone_metrics = metrics(
            multizone_eta[region_mask],
            multizone_u[region_mask],
            multizone_v[region_mask],
            reference_eta[region_mask],
            reference_u[region_mask],
            reference_v[region_mask],
            weights,
        )
        direct_metrics = metrics(
            multizone_eta[region_mask],
            multizone_u[region_mask],
            multizone_v[region_mask],
            formal_eta[region_mask],
            formal_u[region_mask],
            formal_v[region_mask],
            weights,
        )
        rows.append(
            {
                "regionId": region_id,
                "formalR20VsSealedSource": formal_metrics,
                "multizoneVsSealedSource": multizone_metrics,
                "multizoneVsFormalR20": direct_metrics,
                "resolutionRegression": metric_delta(multizone_metrics, formal_metrics),
            }
        )

    full = next(row for row in rows if row["regionId"] == "fullConfirmedDomain")
    screening = {
        key: {
            "guideMaximum": limit,
            "measured": full["multizoneVsFormalR20"][key],
            "passed": full["multizoneVsFormalR20"][key] <= limit,
        }
        for key, limit in SCREENING_GUIDES.items()
    }
    screening["meaning"] = (
        "non_authoritative_spatial_screening_guides_reused_from_prior_holdout_scale;"
        "_not_physical_validation_and_not_final_mesh_acceptance"
    )
    formal_count = int(len(candidate_data["formalR20"]["triangles"]))
    multizone_count = int(len(candidate_data["multizone"]["triangles"]))
    source_area_inside = float(eval_area.sum())
    formal_points = candidate_data["formalR20"]["verticesMetric"][
        candidate_data["formalR20"]["triangles"]
    ]
    formal_ab = formal_points[:, 1] - formal_points[:, 0]
    formal_ac = formal_points[:, 2] - formal_points[:, 0]
    formal_area = float(
        np.sum(np.abs(formal_ab[:, 0] * formal_ac[:, 1] - formal_ab[:, 1] * formal_ac[:, 0]) * 0.5)
    )

    eta_error_formal = formal_eta - reference_eta
    eta_error_multizone = multizone_eta - reference_eta
    velocity_error_formal = np.hypot(formal_u - reference_u, formal_v - reference_v)
    velocity_error_multizone = np.hypot(
        multizone_u - reference_u, multizone_v - reference_v
    )
    eta_error_multizone_vs_formal = multizone_eta - formal_eta
    velocity_error_multizone_vs_formal = np.hypot(
        multizone_u - formal_u, multizone_v - formal_v
    )
    np.savez_compressed(
        FIELDS,
        source_evaluation_cell_ids=eval_ids.astype(np.int32),
        evaluation_metric_centroids_m=eval_metric.astype(np.float64),
        evaluation_image_centroids=source_image_centroids[eval_ids].astype(np.float64),
        evaluation_area_m2=eval_area.astype(np.float64),
        reference_water_surface_elevation_m=reference_eta.astype(np.float64),
        reference_velocity_u_mps=reference_u.astype(np.float64),
        reference_velocity_v_mps=reference_v.astype(np.float64),
        formal_R20_water_surface_elevation_error_m=eta_error_formal.astype(np.float64),
        multizone_water_surface_elevation_error_m=eta_error_multizone.astype(np.float64),
        formal_R20_velocity_vector_error_mps=velocity_error_formal.astype(np.float64),
        multizone_velocity_vector_error_mps=velocity_error_multizone.astype(np.float64),
        multizone_minus_formal_R20_water_surface_elevation_error_m=eta_error_multizone_vs_formal.astype(np.float64),
        multizone_vs_formal_R20_velocity_vector_error_mps=velocity_error_multizone_vs_formal.astype(np.float64),
        formal_R20_evaluation_cell_ids=formal_cells.astype(np.int32),
        multizone_evaluation_cell_ids=multizone_cells.astype(np.int32),
        multizone_target_area_m2=multizone_targets.astype(np.float64),
        barrage_distance_m=barrage_distance.astype(np.float64),
        fishway_P2_mask=p2_mask.astype(np.uint8),
    )

    summary = {
        "schema": "onga-stage20-R20-multizone-field-convergence-v1",
        "version": 1,
        "status": "bounded_spatial_diagnostic_complete_pending_user_mesh_adoption",
        "method": {
            "type": "sealed_flow_field_piecewise_constant_resampling",
            "sourceField": {
                "description": "sealed 600 s kernel-v3 field numerically identical to kernel-v2 pilot",
                "physicalValidationClaimAllowed": False,
                "waterSurfaceElevationDefinition": "waterDepthM_plus_reconstructed_source_bedElevationM",
            },
            "candidateCellValue": "sealed source triangle containing candidate centroid",
            "commonEvaluation": "sealed source cell centroids contained in both confirmed-domain meshes",
            "weighting": "sealed source cell area",
            "newSolverRunPerformed": False,
            "solverDynamicsConvergenceClaimAllowed": False,
            "spatialRepresentationConvergenceClaimAllowed": True,
        },
        "mesh": {
            "formalR20CellCount": formal_count,
            "multizoneCellCount": multizone_count,
            "cellCountReduction": formal_count - multizone_count,
            "cellCountReductionPercent": 100.0 * (formal_count - multizone_count) / formal_count,
            "perStepWorkProxyRatio": multizone_count / formal_count,
            "minimumEdgeUnchangedM": 0.3870142296069747,
            "cflTimeStepImprovementExpected": False,
        },
        "mapping": {
            "formalR20CandidateCentroidsToSource": candidate_data["formalR20"]["sourceMapping"],
            "multizoneCandidateCentroidsToSource": candidate_data["multizone"]["sourceMapping"],
            "sourceEvaluationCellCount": int(len(eval_ids)),
            "sourceEvaluationAreaM2": source_area_inside,
            "formalMeshAreaM2": formal_area,
            "sourceCentroidAreaCoverageRatio": source_area_inside / formal_area,
            "formalAndMultizoneDomainDisagreementSourceCellCount": int(np.sum(domain_disagreement)),
        },
        "screening": screening,
        "regionalMetrics": rows,
        "interpretation": {
            "adoptionAutomaticallyAuthorized": False,
            "resultUse": "judge_whether_35.6_percent_cell_reduction_preserves_the_sealed_flow_field_at_required_spatial_scale",
            "limitations": [
                "does_not_advance_the_H2_solver",
                "does_not_validate_the_new_gate_or_P2_hydraulic_law",
                "inherits_the_inferred_bathymetry_and_boundary_conditions_of_the_sealed_600_second_source",
                "requires_user_visual_judgment_before_formal_mesh_replacement",
            ],
        },
        "bindings": {
            "approval": binding(APPROVAL),
            "formalMesh": binding(FORMAL_MESH),
            "formalSummary": binding(FORMAL_SUMMARY),
            "multizoneMesh": binding(MULTIZONE_MESH),
            "multizoneSummary": binding(MULTIZONE_SUMMARY),
            "sourceContract": binding(SOURCE_CONTRACT),
            "sourceFields": binding(SOURCE_FIELDS),
            "sourceReport": binding(SOURCE_REPORT),
            "sourceMeshManifest": binding(SOURCE_MESH_MANIFEST),
            "sourceMeshBinary": binding(SOURCE_MESH_BINARY),
            "waterManifest": binding(WATER_MANIFEST),
            "comparisonFields": binding(FIELDS),
        },
        "safeguards": {
            "formalMeshReplaced": False,
            "productionPrecomputeRun": False,
            "solverSourceChanged": False,
            "publicRuntimeChanged": False,
            "responsePackChanged": False,
            "mainMerged": False,
        },
    }
    write_json(SUMMARY, summary)

    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, observed: Any) -> None:
        checks.append({"id": check_id, "passed": bool(passed), "observed": observed})

    check("all_pinned_inputs_match", True, len(EXPECTED))
    check("sealed_source_is_finite", bool(np.isfinite(source_eta).all()), True)
    check(
        "candidate_centroid_source_fallback_bounded",
        candidate_data["formalR20"]["sourceMapping"]["outsideTriangleFraction"] <= 0.05
        and candidate_data["multizone"]["sourceMapping"]["outsideTriangleFraction"] <= 0.05
        and candidate_data["formalR20"]["sourceMapping"][
            "fallbackMaximumImagePixelDistance"
        ]
        <= 25.0
        and candidate_data["multizone"]["sourceMapping"][
            "fallbackMaximumImagePixelDistance"
        ]
        <= 25.0,
        {
            "formal": candidate_data["formalR20"]["sourceMapping"],
            "multizone": candidate_data["multizone"]["sourceMapping"],
        },
    )
    check("common_domain_nonempty", len(eval_ids) > 0, len(eval_ids))
    check(
        "formal_multizone_domain_agreement",
        int(np.sum(domain_disagreement)) == 0,
        int(np.sum(domain_disagreement)),
    )
    check(
        "source_centroid_area_coverage_within_3_percent",
        abs(source_area_inside / formal_area - 1.0) <= 0.03,
        source_area_inside / formal_area,
    )
    check("all_regions_nonempty", all(row["formalR20VsSealedSource"]["evaluationCellCount"] > 0 for row in rows), len(rows))
    check("comparison_fields_finite", bool(np.isfinite(eta_error_multizone).all() and np.isfinite(velocity_error_multizone).all()), True)
    check(
        "full_domain_spatial_guides_pass",
        all(item["passed"] for key, item in screening.items() if isinstance(item, dict)),
        screening,
    )
    check("formal_mesh_not_replaced", summary["safeguards"]["formalMeshReplaced"] is False, False)
    check("no_new_solver_run", summary["method"]["newSolverRunPerformed"] is False, False)
    check("public_runtime_unchanged", summary["safeguards"]["publicRuntimeChanged"] is False, False)
    failed = [item for item in checks if not item["passed"]]
    validation = {
        "schema": "onga-stage20-R20-multizone-field-convergence-v1-static-validation",
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "checks": checks,
    }
    write_json(VALIDATION, validation)
    require(not failed, f"static validation failed: {[item['id'] for item in failed]}")

    manifest = {
        "schema": "onga-stage20-R20-multizone-field-convergence-v1-manifest",
        "status": "complete_pending_user_mesh_adoption",
        "files": [
            binding(SUMMARY),
            binding(VALIDATION),
            binding(FIELDS),
        ],
        "safeguards": summary["safeguards"],
    }
    write_json(MANIFEST, manifest)
    print(
        json.dumps(
            {
                "result": "PASS_BOUNDED_SPATIAL_CONVERGENCE_DIAGNOSTIC",
                "summary": binding(SUMMARY),
                "validation": binding(VALIDATION),
                "fields": binding(FIELDS),
                "manifest": binding(MANIFEST),
                "cellCount": {
                    "formalR20": formal_count,
                    "multizone": multizone_count,
                    "reductionPercent": summary["mesh"]["cellCountReductionPercent"],
                },
                "fullDomain": full,
                "screening": screening,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
