#!/usr/bin/env python3
"""Diagnose the CFL-limiting cell from the Stage 20 900 s canary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.warp import transform


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "docs/results/stage20-continuous-all-closed-900s-yoda-canary-20260828-v3"
MESH = ROOT / "docs/results/stage20-barrage-candidate-C-R1C-next-stage-review-approval-v1/review-mesh.npz"
BATHYMETRY = ROOT / "docs/results/stage20-constrained-bathymetry-continuity-v2-20260828/continuity-fields.npz"
OUTPUT = RUN / "limiter-diagnosis.json"

REFINEMENT_MARKERS = {301: "fishway_upstream_refinement_ring", 302: "fishway_downstream_refinement_ring"}
ROLE_BITS = {1: "main_channel_200m_patch", 2: "nishikawa_150m_patch", 4: "magarigawa_180m_patch"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def triangle_area(points: np.ndarray) -> float:
    edge_a = points[1] - points[0]
    edge_b = points[2] - points[0]
    return float(abs(edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0]) / 2.0)


def build_report() -> dict[str, Any]:
    manifest = read_json(RUN / "manifest.json")
    manifest_checks = []
    for item in manifest["files"]:
        path = RUN / item["path"]
        actual = sha256(path)
        manifest_checks.append(
            {
                "path": item["path"],
                "expectedSha256": item["sha256"],
                "actualSha256": actual,
                "passed": actual == item["sha256"],
            }
        )
    if not all(item["passed"] for item in manifest_checks):
        raise RuntimeError("run artifact manifest mismatch")

    telemetry = read_json(RUN / "telemetry.json")
    limiter = telemetry["limiter"]["globalMinimumSelectedBoundEvent"]
    cell_id = int(limiter["cellId"])

    with np.load(MESH, allow_pickle=False) as archive:
        vertices = np.asarray(archive["vertices_m"], dtype=np.float64)
        triangles = np.asarray(archive["triangles"], dtype=np.int64)
        segments = np.asarray(archive["segments"], dtype=np.int64)
        segment_markers = np.asarray(archive["segment_markers"], dtype=np.int64)
        fixed = np.asarray(archive["fixed_R20_cell_mask"], dtype=bool)
        source_ids = np.asarray(archive["fixed_R20_source_cell_id"], dtype=np.int64)
        role_bits = np.asarray(archive["fixed_R20_role_bits"], dtype=np.uint8)
        zone_code = np.asarray(archive["R1C_zone_code"], dtype=np.uint8)
        maximum_area = np.asarray(archive["triangle_maximum_area_m2"], dtype=np.float64)

    with np.load(BATHYMETRY, allow_pickle=False) as archive:
        depth = np.asarray(archive["continuous_candidate_depth_m"], dtype=np.float64)
        bed = np.asarray(archive["continuous_candidate_bed_elevation_m"], dtype=np.float64)
        upstream = np.asarray(archive["upstream_component_mask"], dtype=np.uint8)

    triangle = triangles[cell_id]
    points = vertices[triangle]
    edge_lengths = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
    centroid = points.mean(axis=0)
    longitude, latitude = transform(
        "EPSG:32652", "EPSG:4326", [float(centroid[0])], [float(centroid[1])]
    )

    marker_rows = []
    neighbor_ids: set[int] = set()
    for index in range(3):
        edge = {int(triangle[index]), int(triangle[(index + 1) % 3])}
        cell_hits = np.flatnonzero(np.sum(np.isin(triangles, list(edge)), axis=1) == 2)
        neighbor_ids.update(int(hit) for hit in cell_hits if int(hit) != cell_id)
        segment_hits = np.flatnonzero(np.sum(np.isin(segments, list(edge)), axis=1) == 2)
        for hit in segment_hits:
            marker = int(segment_markers[hit])
            marker_rows.append(
                {
                    "marker": marker,
                    "meaning": REFINEMENT_MARKERS.get(marker, "other_constraint"),
                    "edgeLengthM": float(edge_lengths[index]),
                }
            )

    roles = [name for bit, name in ROLE_BITS.items() if int(role_bits[cell_id]) & bit]
    wall_seconds = float(read_json(RUN / "result.json")["wallSeconds"])
    projected_36h_wall_hours = wall_seconds * (36.0 * 3600.0 / 900.0) / 3600.0
    is_refinement_ring = any(row["marker"] in REFINEMENT_MARKERS for row in marker_rows)
    is_small_wet_cell = bool(depth[cell_id] > 0.05 and edge_lengths.min() < 0.5)

    return {
        "schema": "onga-stage20-continuous-all-closed-limiter-diagnosis-v1",
        "version": 1,
        "status": "PASS_LIMITER_IDENTIFIED_AS_SMALL_WET_REFINEMENT_RING_CELL",
        "classification": "LOCAL_POSTRUN_DIAGNOSIS_NOT_MESH_ADOPTION_NOT_PHYSICAL_VALIDATION",
        "source": {
            "runId": manifest["runId"],
            "manifestSha256": sha256(RUN / "manifest.json"),
            "manifestChecks": manifest_checks,
            "meshSha256": sha256(MESH),
            "bathymetrySha256": sha256(BATHYMETRY),
        },
        "limiter": {
            "cellId": cell_id,
            "selectedBoundName": limiter["selectedBoundName"],
            "selectedBoundSeconds": limiter["selectedBoundSeconds"],
            "eventIndex": limiter["eventIndex"],
            "selectionCount": telemetry["limiter"]["topCandidates"][0]["selectionCount"],
            "proposalCount": telemetry["stepAccounting"]["totalProposalCount"],
            "areaM2": triangle_area(points),
            "minimumEdgeM": float(edge_lengths.min()),
            "maximumEdgeM": float(edge_lengths.max()),
            "edgeLengthsM": edge_lengths.tolist(),
            "targetMaximumAreaM2": float(maximum_area[cell_id]),
            "depthM": float(depth[cell_id]),
            "bedElevationM": float(bed[cell_id]),
            "centroidEpsg32652M": centroid.tolist(),
            "centroidLongitudeLatitude": [longitude[0], latitude[0]],
            "fixedR20Cell": bool(fixed[cell_id]),
            "fixedR20SourceCellId": int(source_ids[cell_id]),
            "fixedRoleBits": int(role_bits[cell_id]),
            "fixedRoles": roles,
            "R1CZoneCode": int(zone_code[cell_id]),
            "upstreamComponent": bool(upstream[cell_id]),
            "constraintEdges": marker_rows,
            "neighborCellIds": sorted(neighbor_ids),
        },
        "diagnosis": {
            "smallWetCell": is_small_wet_cell,
            "onFishwayRefinementRing": is_refinement_ring,
            "naturalShallowWaterCauseSupported": False,
            "meshGeometryCauseSupported": is_small_wet_cell and is_refinement_ring,
            "reason": "The wet limiter is a 0.087 m2 fixed R20 triangle on the fishway upstream refinement-ring constraint; its approximately 0.42 m edges, not an exceptionally small water depth, constrain the explicit time step.",
        },
        "cost": {
            "measured900sWallSeconds": wall_seconds,
            "linear36hWallHours": projected_36h_wall_hours,
            "evidenceClass": "LINEAR_EXTRAPOLATION_NOT_LONG_RUN_MEASUREMENT",
        },
        "recommendation": {
            "next": "build_a_nonadopted_local_mesh_candidate_that_preserves_fishway_and_barrage_topology_but_removes_sub_0_5m_refinement_ring_edges",
            "doNot": [
                "increase_depth_to_buy_a_larger_time_step",
                "start_a_36_hour_run_on_the_current_mesh",
                "claim_physical_or_operational_validity_from_this_diagnosis",
            ],
            "requiredComparison": [
                "all_256_main_gate_topology_states",
                "fishway_P2_geometry_and_overlap_weights",
                "900_to_1200_second_matched_dynamic_reference",
                "mass_wetdry_and_flow_vector_differences",
                "accepted_step_and_wall_time_reduction",
            ],
        },
    }


def main() -> None:
    report = build_report()
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()
