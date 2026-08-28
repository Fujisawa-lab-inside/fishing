#!/usr/bin/env python3
"""Transfer the continuous R1C bathymetry to the regularized multizone mesh."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

import build_stage20_constrained_bathymetry_continuity_v2_20260828 as continuity
import evaluate_stage20_R20_multizone_field_convergence_v1 as spatial
import generate_stage20_barrage_H2_boundary_spacing_comparison_v1 as mesh_base
import run_stage20_R20_multizone_H2_dynamics_diagnostic_v1 as short
import run_stage20_barrage_C1_local_transition_600s_v1 as c1
import stage20_depth_weighted_boundary_kernel_candidate_v2 as hydro


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MESH = ROOT / "docs/results/stage20-barrage-candidate-C-R1C-next-stage-review-approval-v1/review-mesh.npz"
SOURCE_FIELDS = ROOT / "docs/results/stage20-constrained-bathymetry-continuity-v2-20260828/continuity-fields.npz"
CANDIDATE_ROOT = ROOT / "docs/results/stage20-regularized-multizone-mesh-candidate-v1"
CANDIDATE_MESH = CANDIDATE_ROOT / "regularized-multizone-review-mesh.npz"
CANDIDATE_REPORT = CANDIDATE_ROOT / "report.json"
P2_CANDIDATE = mesh_base.P2_CANDIDATE
OUTPUT = ROOT / "docs/results/stage20-regularized-multizone-continuous-fields-v1"
FIELDS = OUTPUT / "continuous-fields.npz"
REPORT = OUTPUT / "report.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def load_mesh(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: np.asarray(archive[name]).copy() for name in archive.files}


def hydraulic_component_mask(
    geometry: dict[str, np.ndarray], upstream_reference: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    count = len(geometry["areas"])
    parent = np.arange(count, dtype=np.int64)

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = int(parent[value])
        return value

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    left = np.asarray(geometry["left"], dtype=np.int64)
    right = np.asarray(geometry["right"], dtype=np.int64)
    markers = np.asarray(geometry["internalMarkers"], dtype=np.int64)
    structure = markers == hydro.FIXED_MARKER
    for gate in range(1, 9):
        structure |= markers == hydro.GATE_MARKER_BASE + gate
    for a, b in zip(left[~structure], right[~structure], strict=True):
        union(int(a), int(b))
    roots = np.asarray([find(index) for index in range(count)], dtype=np.int64)
    unique, counts = np.unique(roots, return_counts=True)
    if len(unique) != 2:
        raise RuntimeError(f"all-closed candidate must have two main components: {len(unique)}")
    nearest = int(
        np.argmin(
            np.linalg.norm(
                np.asarray(geometry["centroids"], dtype=np.float64)
                - np.asarray(upstream_reference, dtype=np.float64),
                axis=1,
            )
        )
    )
    upstream_root = roots[nearest]
    mask = roots == upstream_root
    return mask, {
        "componentCount": len(unique),
        "componentCellCounts": counts.tolist(),
        "upstreamReferenceCellId": nearest,
    }


def interpolate_componentwise(
    source_centroids: np.ndarray,
    source_depth: np.ndarray,
    source_upstream: np.ndarray,
    candidate_centroids: np.ndarray,
    candidate_upstream: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    result = np.empty(len(candidate_centroids), dtype=np.float64)
    fallback_count = 0
    fallback_maximum_distance = 0.0
    for source_mask, candidate_mask in (
        (source_upstream, candidate_upstream),
        (~source_upstream, ~candidate_upstream),
    ):
        source_points = source_centroids[source_mask]
        source_values = source_depth[source_mask]
        query = candidate_centroids[candidate_mask]
        interpolated = np.asarray(
            LinearNDInterpolator(source_points, source_values, fill_value=np.nan)(query),
            dtype=np.float64,
        )
        missing = ~np.isfinite(interpolated)
        if np.any(missing):
            distances, indices = cKDTree(source_points).query(query[missing], k=1)
            interpolated[missing] = source_values[np.asarray(indices, dtype=np.int64)]
            fallback_count += int(np.sum(missing))
            fallback_maximum_distance = max(
                fallback_maximum_distance, float(np.max(distances))
            )
        result[candidate_mask] = interpolated
    return result, {
        "method": "separate_upstream_downstream_linear_centroid_interpolation_with_nearest_fallback",
        "fallbackCellCount": fallback_count,
        "fallbackMaximumDistanceM": fallback_maximum_distance,
    }


def main() -> None:
    source_mesh = load_mesh(SOURCE_MESH)
    candidate_mesh = load_mesh(CANDIDATE_MESH)
    source_geometry = short.build_review_geometry(source_mesh)
    candidate_geometry = short.build_review_geometry(candidate_mesh)
    with np.load(SOURCE_FIELDS, allow_pickle=False) as archive:
        source_depth = np.asarray(
            archive["continuous_candidate_depth_m"], dtype=np.float64
        )
        source_upstream = np.asarray(
            archive["upstream_component_mask"], dtype=np.uint8
        ).astype(bool)
        reference_eta = float(np.asarray(archive["reference_eta_m"])[0])

    p2_source = json.loads(P2_CANDIDATE.read_text(encoding="utf-8"))[
        "candidatePairs"
    ]["separated"]
    p2_polygons = {
        side: Polygon(
            c1.old.project_many(
                p2_source[side]["footprint"]["coordinates"][0][:-1]
            )
        )
        for side in ("upstream", "downstream")
    }
    upstream_reference = np.asarray(p2_polygons["upstream"].centroid.coords[0])
    candidate_upstream, component_info = hydraulic_component_mask(
        candidate_geometry, upstream_reference
    )
    raw_depth, mapping = interpolate_componentwise(
        np.asarray(source_geometry["centroids"], dtype=np.float64),
        source_depth,
        source_upstream,
        np.asarray(candidate_geometry["centroids"], dtype=np.float64),
        candidate_upstream,
    )
    if not np.isfinite(raw_depth).all() or np.min(raw_depth) < continuity.MINIMUM_WET_DEPTH_M:
        raise RuntimeError("interpolated depth is invalid")

    source_areas = np.asarray(source_geometry["areas"], dtype=np.float64)
    candidate_areas = np.asarray(candidate_geometry["areas"], dtype=np.float64)
    target_volumes = {
        True: float(np.sum(source_depth[source_upstream] * source_areas[source_upstream])),
        False: float(np.sum(source_depth[~source_upstream] * source_areas[~source_upstream])),
    }
    volume_matched = raw_depth.copy()
    volume_offsets = {}
    for upstream in (True, False):
        mask = candidate_upstream if upstream else ~candidate_upstream
        current_volume = float(np.sum(volume_matched[mask] * candidate_areas[mask]))
        offset = (target_volumes[upstream] - current_volume) / float(
            np.sum(candidate_areas[mask])
        )
        volume_matched[mask] += offset
        volume_offsets["upstream" if upstream else "downstream"] = offset
    if np.min(volume_matched) < continuity.MINIMUM_WET_DEPTH_M:
        raise RuntimeError("component volume matching violates wet-depth floor")

    depth, limiter = continuity.conservative_slope_limited_depth(
        candidate_geometry,
        volume_matched,
        candidate_upstream,
    )
    bed = reference_eta - depth
    source_data, _ = short.initial_condition_data()
    _, _, manning, manning_mapping = short.initialize_mesh(
        candidate_mesh, candidate_geometry, source_data
    )
    candidate_report = json.loads(CANDIDATE_REPORT.read_text(encoding="utf-8"))
    summary = {"hydraulic": candidate_report["candidate"]["hydraulic"]}
    p2 = hydro.p2_arrays(candidate_geometry, summary, p2_polygons)

    mapping_workspace = c1.build_mapping_workspace(candidate_geometry)
    gate_faces = np.asarray(mapping_workspace["gateFaceIds"], dtype=np.int64)
    gate_left = np.asarray(candidate_geometry["left"], dtype=np.int64)[gate_faces]
    gate_right = np.asarray(candidate_geometry["right"], dtype=np.int64)[gate_faces]
    if not np.all(candidate_upstream[gate_left] ^ candidate_upstream[gate_right]):
        raise RuntimeError("candidate gate faces do not separate hydraulic components")
    barrage_upstream_cell = np.where(
        candidate_upstream[gate_left], gate_left, gate_right
    ).astype(np.int64)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        FIELDS,
        cell_id=np.arange(len(depth), dtype=np.int64),
        continuous_depth_m=depth,
        continuous_bed_elevation_m=bed,
        manning_n=np.asarray(manning, dtype=np.float64),
        upstream_component_mask=candidate_upstream.astype(np.uint8),
        p2_donor_overlap_area_m2=np.asarray(p2[0], dtype=np.float64),
        p2_receiver_overlap_area_m2=np.asarray(p2[1], dtype=np.float64),
        gate_face_id=gate_faces,
        barrage_upstream_cell_id=barrage_upstream_cell,
        reference_eta_m=np.asarray([reference_eta], dtype=np.float64),
    )
    final_volumes = {
        "upstream": float(np.sum(depth[candidate_upstream] * candidate_areas[candidate_upstream])),
        "downstream": float(np.sum(depth[~candidate_upstream] * candidate_areas[~candidate_upstream])),
    }
    checks = {
        "finiteDepthBedManning": bool(
            np.isfinite(depth).all() and np.isfinite(bed).all() and np.isfinite(manning).all()
        ),
        "minimumWetDepth": float(np.min(depth)) >= continuity.MINIMUM_WET_DEPTH_M,
        "constantInitialSurface": float(np.max(np.abs(depth + bed - reference_eta))) <= 1e-14,
        "upstreamVolumeMatched": abs(final_volumes["upstream"] - target_volumes[True])
        / target_volumes[True]
        <= 1e-12,
        "downstreamVolumeMatched": abs(final_volumes["downstream"] - target_volumes[False])
        / target_volumes[False]
        <= 1e-12,
        "ordinaryFaceSlopeLimited": limiter["remainingActiveFaceCount"] == 0,
        "gateFacesSeparateComponents": True,
        "P2DonorReceiverDisjoint": bool(
            not np.any((np.asarray(p2[0]) > 0.0) & (np.asarray(p2[1]) > 0.0))
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"continuous-field gate failed: {checks}")

    report = {
        "schema": "onga-stage20-regularized-multizone-continuous-fields-v1",
        "version": 1,
        "status": "PASS_LOCAL_FIELDS_READY_MATCHED_DYNAMIC_CANARY_NOT_AUTHORIZED",
        "classification": "UNADOPTED_NUMERICAL_CANDIDATE_NOT_PHYSICAL_VALIDATION_NOT_FORECAST_NOT_RELEASE",
        "source": {
            "meshSha256": sha256(SOURCE_MESH),
            "fieldsSha256": sha256(SOURCE_FIELDS),
            "cellCount": len(source_depth),
        },
        "candidate": {
            "meshSha256": sha256(CANDIDATE_MESH),
            "cellCount": len(depth),
            "fieldArtifact": {
                "path": str(FIELDS.relative_to(ROOT)),
                "sha256": sha256(FIELDS),
                "byteLength": FIELDS.stat().st_size,
            },
        },
        "mapping": mapping,
        "manningMapping": manning_mapping,
        "component": component_info,
        "componentVolumeOffsetM": volume_offsets,
        "targetVolumeM3": {
            "upstream": target_volumes[True],
            "downstream": target_volumes[False],
        },
        "finalVolumeM3": final_volumes,
        "limiter": limiter,
        "arrays": {
            "depthSha256": array_sha256(depth),
            "bedSha256": array_sha256(bed),
            "manningSha256": array_sha256(np.asarray(manning, dtype=np.float64)),
            "upstreamMaskSha256": array_sha256(candidate_upstream.astype(np.uint8)),
            "p2DonorSha256": array_sha256(np.asarray(p2[0], dtype=np.float64)),
            "p2ReceiverSha256": array_sha256(np.asarray(p2[1], dtype=np.float64)),
            "gateFaceSha256": array_sha256(gate_faces),
            "barrageUpstreamCellSha256": array_sha256(barrage_upstream_cell),
        },
        "ranges": {
            "minimumDepthM": float(np.min(depth)),
            "maximumDepthM": float(np.max(depth)),
            "minimumBedElevationM": float(np.min(bed)),
            "maximumBedElevationM": float(np.max(bed)),
        },
        "checks": checks,
        "decision": {
            "adopted": False,
            "YodaRunAuthorized": False,
            "next": "freeze_matched_900_second_dynamic_acceptance_contract_and_run_local_one_step_equivalence",
        },
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "report": str(REPORT)}))


if __name__ == "__main__":
    main()
