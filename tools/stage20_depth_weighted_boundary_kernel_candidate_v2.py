#!/usr/bin/env python3
"""Review-only H2 kernel candidate with depth-weighted inflow and wet/dry M.

The numerical core is copied from the frozen H2 diagnostic kernel.  Its only
intended change is at N/O/G: total river discharge is distributed in
proportion to the current boundary depth, producing a uniform section-normal
velocity instead of imposing equal unit-width discharge at shallow banks.
At M, the external depth follows the imposed tide down to zero instead of
creating an artificial 0.05 m layer at shoreline endpoints.  This module is
not connected to production, precompute, GUI, or public paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
from numba import njit
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiLineString, Point, Polygon

import evaluate_stage20_R20_multizone_field_convergence_v1 as spatial
import generate_stage20_barrage_H2_boundary_spacing_comparison_v1 as base
import generate_stage20_fishway_F3_review_mesh_v1 as old
import run_stage20_physical_pilot_v2 as pilot
import stage19_shallow_water_kernel_v1 as reference
import stage20_shallow_water_kernel_v3 as compiled
from stage19_solver_inputs import (
    GRAVITY_M_S2,
    build_case_fields,
    classify_branch_ownership,
    load_water_mask,
    mesh_geometry,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-R20-multizone-H2-dynamics-diagnostic-v1"
SUMMARY = OUTPUT / "diagnostic-summary.json"
VALIDATION = OUTPUT / "static-validation.json"
FIELDS = OUTPUT / "comparison-fields.npz"
MANIFEST = OUTPUT / "manifest.json"

APPROVAL = ROOT / "config/stage20_R20_multizone_H2_dynamics_diagnostic_approval_v1.json"
FORMAL_MESH = ROOT / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1/review-mesh.npz"
FORMAL_SUMMARY = ROOT / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1/mesh-summary.json"
MULTIZONE_MESH = ROOT / "docs/results/stage20-R20-multizone-mesh-v1/review-mesh.npz"
MULTIZONE_SUMMARY = ROOT / "docs/results/stage20-R20-multizone-mesh-v1/mesh-summary.json"
SOURCE_CONTRACT = ROOT / "config/stage20_physical_pilot_v2_contract_v1.json"
SOURCE_FIELDS = ROOT / "docs/results/stage20-kernel-v3-physical-pilot-29411976467/pilot-final-fields.npz"
SOURCE_REPORT = ROOT / "docs/results/stage20-kernel-v3-physical-pilot-29411976467/pilot-report.json"
WATER_MANIFEST = ROOT / "data/onga_unified_water_manifest_r3.json"
TIDE_CANDIDATE = ROOT / "config/stage19_m_boundary_tide_candidate_v1.json"
CUT = base.CUT
P2_CANDIDATE = base.P2_CANDIDATE

EXPECTED = {
    FORMAL_MESH: "315636cb6844b4348863e92e33a342b599a2e27f70983651e81a92490d9b920e",
    FORMAL_SUMMARY: "1c778b8fba2eb36fec507c7b58e6d10ce333b04aea86feab5c6ac6f75c24ab4e",
    MULTIZONE_MESH: "05bd80d3ea80880a9589c01252aaac43e0c7447e1f37d322196cafb4b32c0bb5",
    MULTIZONE_SUMMARY: "556bd72eae7bfda949ccd76bcaf93798e1d388aa33a30db2bf086f303acf4e83",
    SOURCE_CONTRACT: "17e391749ffad8dc7ef1ea4a73bca3e0d0c5a374f9f92ee532b51be84a1d8f1f",
    SOURCE_FIELDS: "3e8fed6ee564a34761081728aa2c1d244cdccfee8a78e9203641f2c985613c3b",
    WATER_MANIFEST: "964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7",
}
PROTECTED = {
    ROOT / "public/data/onga/onga_geometry.geojson":
        "8593f67c5157ed1d55b717ba6ed691674694cfa499f7f7d533fc9950acdfc536",
    ROOT / "public/data/onga/stage20/mesh-v2.bin":
        "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659",
    ROOT / "public/data/onga/stage20/response-pack-synthetic-v2.bin":
        "2d92e67d2ececf8e3c9e540003cd5546e3f6a38b234de7b5122aa4448c3478a3",
}
NISHIKAWA = spatial.NISHIKAWA
MAGARIGAWA = spatial.MAGARIGAWA
P2_RESERVE_DEPTH_M = 0.05
P2_MAXIMUM_FRACTION_PER_STEP = 0.02
GATE_MARKER_BASE = 100
FIXED_MARKER = 200
BOUNDARY_MARKER_TO_TAG = {10: 0, 11: 1, 12: 2, 13: 3, 14: 4}
LIMITER_TRACE_SCHEMA_V1 = "onga-stage20-depth-weighted-boundary-limiter-trace-v1"


class DepthWeightedBoundaryStepWithTraceV1(NamedTuple):
    """Numerical step result plus its same-pass limiter evidence.

    ``limiter_sample`` is an actual
    ``stage20_dynamic_mesh_comparison_telemetry_v1.LimiterSample``.  A caller
    can therefore pass ``accepted_dt_s`` and ``limiter_sample`` directly to
    ``DynamicMeshTelemetry.record_accepted_step`` without reconstructing any
    CFL operand outside the numerical kernel.
    """

    next_state: np.ndarray
    accepted_dt_s: float
    maximum_cfl: float
    boundary_outflow_m3_s: float
    effective_fishway_discharge_m3_s: float
    fishway_source_residual_m3_s: float
    limiter_sample: Any


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def build_review_geometry(mesh: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    vertices = np.asarray(mesh["vertices_m"], dtype=np.float64)
    triangles = np.asarray(mesh["triangles"], dtype=np.int64)
    points = vertices[triangles]
    centroids = points.mean(axis=1)
    ab = points[:, 1] - points[:, 0]
    ac = points[:, 2] - points[:, 0]
    areas = np.abs(ab[:, 0] * ac[:, 1] - ab[:, 1] * ac[:, 0]) * 0.5
    require(np.isfinite(areas).all() and np.all(areas > 0.0), "invalid mesh areas")

    marker_by_edge = {
        tuple(sorted((int(edge[0]), int(edge[1])))): int(marker)
        for edge, marker in zip(
            np.asarray(mesh["segments"], dtype=np.int64),
            np.asarray(mesh["segment_markers"], dtype=np.int64),
            strict=True,
        )
    }
    edge_cells: dict[tuple[int, int], list[int]] = {}
    for cell, triangle in enumerate(triangles):
        for left, right in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            edge_cells.setdefault(
                tuple(sorted((int(left), int(right)))),
                [],
            ).append(cell)
    require(
        all(len(cells) in (1, 2) for cells in edge_cells.values()),
        "nonmanifold mesh edge",
    )

    internal_rows = [
        (edge, cells[0], cells[1], marker_by_edge.get(edge, 0))
        for edge, cells in edge_cells.items()
        if len(cells) == 2
    ]
    boundary_rows = [
        (edge, cells[0], marker_by_edge.get(edge, 0))
        for edge, cells in edge_cells.items()
        if len(cells) == 1
    ]
    internal_vertices = np.asarray([row[0] for row in internal_rows], dtype=np.int64)
    left = np.asarray([row[1] for row in internal_rows], dtype=np.int64)
    right = np.asarray([row[2] for row in internal_rows], dtype=np.int64)
    internal_markers = np.asarray([row[3] for row in internal_rows], dtype=np.int32)
    vectors = vertices[internal_vertices[:, 1]] - vertices[internal_vertices[:, 0]]
    internal_lengths = np.linalg.norm(vectors, axis=1)
    internal_normals = np.column_stack((vectors[:, 1], -vectors[:, 0]))
    internal_normals /= internal_lengths[:, None]
    reverse = (
        np.einsum("ij,ij->i", internal_normals, centroids[right] - centroids[left])
        < 0.0
    )
    internal_normals[reverse] *= -1.0

    boundary_vertices = np.asarray([row[0] for row in boundary_rows], dtype=np.int64)
    boundary_cells = np.asarray([row[1] for row in boundary_rows], dtype=np.int64)
    boundary_markers = np.asarray([row[2] for row in boundary_rows], dtype=np.int32)
    require(
        set(int(value) for value in np.unique(boundary_markers)).issubset(
            set(BOUNDARY_MARKER_TO_TAG)
        ),
        f"unknown boundary markers: {np.unique(boundary_markers).tolist()}",
    )
    boundary_tags = np.asarray(
        [BOUNDARY_MARKER_TO_TAG[int(marker)] for marker in boundary_markers],
        dtype=np.uint8,
    )
    vectors = vertices[boundary_vertices[:, 1]] - vertices[boundary_vertices[:, 0]]
    boundary_lengths = np.linalg.norm(vectors, axis=1)
    boundary_normals = np.column_stack((vectors[:, 1], -vectors[:, 0]))
    boundary_normals /= boundary_lengths[:, None]
    midpoints = (
        vertices[boundary_vertices[:, 0]] + vertices[boundary_vertices[:, 1]]
    ) * 0.5
    reverse = (
        np.einsum(
            "ij,ij->i",
            boundary_normals,
            midpoints - centroids[boundary_cells],
        )
        < 0.0
    )
    boundary_normals[reverse] *= -1.0

    tag_length_sums = np.zeros(5, dtype=np.float64)
    np.add.at(tag_length_sums, boundary_tags, boundary_lengths)
    gate_face_counts = {
        str(gate): int(np.sum(internal_markers == GATE_MARKER_BASE + gate))
        for gate in range(1, 9)
    }
    require(all(count > 0 for count in gate_face_counts.values()), "missing gate faces")
    require(np.any(internal_markers == FIXED_MARKER), "missing fixed barrage faces")
    return {
        "vertices": vertices,
        "triangles": triangles,
        "centroids": centroids,
        "areas": areas,
        "inverseAreas": 1.0 / areas,
        "left": left,
        "right": right,
        "internalLengths": internal_lengths,
        "internalNormals": internal_normals,
        "internalMarkers": internal_markers,
        "boundaryCells": boundary_cells,
        "boundaryLengths": boundary_lengths,
        "boundaryNormals": boundary_normals,
        "boundaryTags": boundary_tags,
        "boundaryTagLengthSums": tag_length_sums,
        "gateFaceCounts": gate_face_counts,
    }


def interface_multiplier(
    geometry: dict[str, np.ndarray],
    open_gates: list[int],
) -> np.ndarray:
    result = np.ones(len(geometry["left"]), dtype=np.float64)
    markers = geometry["internalMarkers"]
    structure = markers == FIXED_MARKER
    for gate in range(1, 9):
        gate_faces = markers == GATE_MARKER_BASE + gate
        structure |= gate_faces
        result[gate_faces] = 1.0 if gate in open_gates else 0.0
    result[markers == FIXED_MARKER] = 0.0
    require(np.all(np.isin(result[structure], [0.0, 1.0])), "invalid interface state")
    return result


def p2_arrays(
    geometry: dict[str, np.ndarray],
    summary: dict[str, Any],
    polygons: dict[str, Polygon],
) -> tuple[np.ndarray, np.ndarray]:
    count = len(geometry["areas"])
    donor_overlap = np.zeros(count, dtype=np.float64)
    receiver_overlap = np.zeros(count, dtype=np.float64)
    for side, target in (
        ("upstream", donor_overlap),
        ("downstream", receiver_overlap),
    ):
        record = summary["hydraulic"]["P2"][side]
        ids = np.asarray(record["cellIds"], dtype=np.int64)
        weights = np.asarray(record["weights"], dtype=np.float64)
        require(len(ids) >= 27, f"{side} P2 has too few cells")
        require(abs(float(weights.sum()) - 1.0) <= 1e-12, f"{side} weights")
        target[ids] = weights * float(polygons[side].area)
    require(
        not np.any((donor_overlap > 0.0) & (receiver_overlap > 0.0)),
        "P2 donor and receiver overlap",
    )
    return donor_overlap, receiver_overlap


@njit(cache=True, fastmath=False)
def _advance_h2_step_depth_weighted_boundary_with_trace_core_v1(
    state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    areas: np.ndarray,
    inverse_areas: np.ndarray,
    left_cells: np.ndarray,
    right_cells: np.ndarray,
    internal_lengths: np.ndarray,
    internal_normals: np.ndarray,
    interface_multiplier_by_face: np.ndarray,
    boundary_cells: np.ndarray,
    boundary_lengths: np.ndarray,
    boundary_normals: np.ndarray,
    boundary_tags: np.ndarray,
    tide_target_m: float,
    target_discharge_by_tag: np.ndarray,
    donor_overlap_area: np.ndarray,
    receiver_overlap_area: np.ndarray,
    q0_m3_s: float,
    cfl_target: float,
    maximum_dt: float,
) -> tuple[Any, ...]:
    cell_count = len(areas)
    residual = np.zeros((cell_count, 3), dtype=np.float64)
    denominator = np.zeros(cell_count, dtype=np.float64)

    for face in range(len(left_cells)):
        left = left_cells[face]
        right = right_cells[face]
        normal_x = internal_normals[face, 0]
        normal_y = internal_normals[face, 1]
        length = internal_lengths[face]

        left_h = state[left, 0]
        left_hu = state[left, 1]
        left_hv = state[left, 2]
        right_h = state[right, 0]
        right_hu = state[right, 1]
        right_hv = state[right, 2]
        eta_left = left_h + bed[left]
        eta_right = right_h + bed[right]
        bed_star = max(bed[left], bed[right])
        reconstructed_left_h = max(eta_left - bed_star, 0.0)
        reconstructed_right_h = max(eta_right - bed_star, 0.0)
        if left_h > 1e-12:
            reconstructed_left_hu = reconstructed_left_h * left_hu / left_h
            reconstructed_left_hv = reconstructed_left_h * left_hv / left_h
        else:
            reconstructed_left_hu = 0.0
            reconstructed_left_hv = 0.0
        if right_h > 1e-12:
            reconstructed_right_hu = reconstructed_right_h * right_hu / right_h
            reconstructed_right_hv = reconstructed_right_h * right_hv / right_h
        else:
            reconstructed_right_hu = 0.0
            reconstructed_right_hv = 0.0

        flux_0, flux_1, flux_2, speed = compiled._rusanov_one(
            reconstructed_left_h,
            reconstructed_left_hu,
            reconstructed_left_hv,
            reconstructed_right_h,
            reconstructed_right_hu,
            reconstructed_right_hv,
            normal_x,
            normal_y,
        )
        left_pressure = 0.5 * GRAVITY_M_S2 * (
            left_h * left_h - reconstructed_left_h * reconstructed_left_h
        )
        right_pressure = 0.5 * GRAVITY_M_S2 * (
            right_h * right_h - reconstructed_right_h * reconstructed_right_h
        )
        left_term_0 = flux_0
        left_term_1 = flux_1 + left_pressure * normal_x
        left_term_2 = flux_2 + left_pressure * normal_y
        right_term_0 = -flux_0
        right_term_1 = -flux_1 - right_pressure * normal_x
        right_term_2 = -flux_2 - right_pressure * normal_y

        multiplier = interface_multiplier_by_face[face]
        if multiplier < 1.0:
            left_normal_momentum = left_hu * normal_x + left_hv * normal_y
            left_reflected_hu = left_hu - 2.0 * left_normal_momentum * normal_x
            left_reflected_hv = left_hv - 2.0 * left_normal_momentum * normal_y
            wall_l0, wall_l1, wall_l2, wall_left_speed = compiled._rusanov_one(
                left_h,
                left_hu,
                left_hv,
                left_h,
                left_reflected_hu,
                left_reflected_hv,
                normal_x,
                normal_y,
            )
            right_normal_x = -normal_x
            right_normal_y = -normal_y
            right_normal_momentum = (
                right_hu * right_normal_x + right_hv * right_normal_y
            )
            right_reflected_hu = (
                right_hu - 2.0 * right_normal_momentum * right_normal_x
            )
            right_reflected_hv = (
                right_hv - 2.0 * right_normal_momentum * right_normal_y
            )
            wall_r0, wall_r1, wall_r2, wall_right_speed = compiled._rusanov_one(
                right_h,
                right_hu,
                right_hv,
                right_h,
                right_reflected_hu,
                right_reflected_hv,
                right_normal_x,
                right_normal_y,
            )
            wall_fraction = 1.0 - multiplier
            left_term_0 = multiplier * left_term_0 + wall_fraction * wall_l0
            left_term_1 = multiplier * left_term_1 + wall_fraction * wall_l1
            left_term_2 = multiplier * left_term_2 + wall_fraction * wall_l2
            right_term_0 = multiplier * right_term_0 + wall_fraction * wall_r0
            right_term_1 = multiplier * right_term_1 + wall_fraction * wall_r1
            right_term_2 = multiplier * right_term_2 + wall_fraction * wall_r2
            speed = max(speed, wall_left_speed, wall_right_speed)

        residual[left, 0] += left_term_0 * length
        residual[left, 1] += left_term_1 * length
        residual[left, 2] += left_term_2 * length
        residual[right, 0] += right_term_0 * length
        residual[right, 1] += right_term_1 * length
        residual[right, 2] += right_term_2 * length
        denominator[left] += speed * length
        denominator[right] += speed * length

    boundary_depth_length_by_tag = np.zeros(5, dtype=np.float64)
    for face in range(len(boundary_cells)):
        tag = boundary_tags[face]
        if tag >= 2:
            cell = boundary_cells[face]
            boundary_depth_length_by_tag[tag] += (
                max(state[cell, 0], 0.0) * boundary_lengths[face]
            )

    boundary_outflow = 0.0
    for face in range(len(boundary_cells)):
        cell = boundary_cells[face]
        normal_x = boundary_normals[face, 0]
        normal_y = boundary_normals[face, 1]
        length = boundary_lengths[face]
        tag = boundary_tags[face]
        interior_h = state[cell, 0]
        interior_hu = state[cell, 1]
        interior_hv = state[cell, 2]

        ghost_h = interior_h
        ghost_hu = interior_hu
        ghost_hv = interior_hv
        if tag == 0:
            normal_momentum = interior_hu * normal_x + interior_hv * normal_y
            ghost_hu = interior_hu - 2.0 * normal_momentum * normal_x
            ghost_hv = interior_hv - 2.0 * normal_momentum * normal_y
        elif tag == 1:
            ghost_h = max(tide_target_m - bed[cell], 0.0)
            if interior_h > 1e-12:
                ghost_hu = ghost_h * interior_hu / interior_h
                ghost_hv = ghost_h * interior_hv / interior_h
            else:
                ghost_hu = 0.0
                ghost_hv = 0.0
        else:
            if interior_h < 1e-8:
                raise ValueError("numerically dry river boundary")
            if boundary_depth_length_by_tag[tag] <= 1e-12:
                raise ValueError("river boundary has zero wetted section")
            normal_momentum = interior_hu * normal_x + interior_hv * normal_y
            tangent_hu = interior_hu - normal_momentum * normal_x
            tangent_hv = interior_hv - normal_momentum * normal_y
            target_normal_momentum = (
                -target_discharge_by_tag[tag]
                * interior_h
                / boundary_depth_length_by_tag[tag]
            )
            ghost_normal_momentum = (
                2.0 * target_normal_momentum - normal_momentum
            )
            ghost_hu = tangent_hu + ghost_normal_momentum * normal_x
            ghost_hv = tangent_hv + ghost_normal_momentum * normal_y

        flux_0, flux_1, flux_2, speed = compiled._rusanov_one(
            interior_h,
            interior_hu,
            interior_hv,
            ghost_h,
            ghost_hu,
            ghost_hv,
            normal_x,
            normal_y,
        )
        residual[cell, 0] += flux_0 * length
        residual[cell, 1] += flux_1 * length
        residual[cell, 2] += flux_2 * length
        denominator[cell] += speed * length
        boundary_outflow += flux_0 * length

    time_step_limit = math.inf
    limiting_cell_id = -1
    limiting_cell_area = math.nan
    limiting_spectral_radius_face_length_sum = math.nan
    evaluated_cell_count = 0
    coverage_complete = True
    for cell in range(cell_count):
        cell_area = areas[cell]
        spectral_radius_face_length_sum = denominator[cell]
        candidate_time_step_limit = cell_area / max(
            spectral_radius_face_length_sum,
            1e-30,
        )
        evaluated_cell_count += 1
        if not (
            math.isfinite(cell_area)
            and cell_area > 0.0
            and math.isfinite(spectral_radius_face_length_sum)
            and spectral_radius_face_length_sum >= 0.0
            and math.isfinite(candidate_time_step_limit)
            and candidate_time_step_limit > 0.0
        ):
            coverage_complete = False
        if candidate_time_step_limit < time_step_limit:
            limiting_cell_id = cell
            limiting_cell_area = cell_area
            limiting_spectral_radius_face_length_sum = (
                spectral_radius_face_length_sum
            )
        time_step_limit = min(time_step_limit, candidate_time_step_limit)
    cfl_time_step_bound = cfl_target * time_step_limit
    time_step = min(cfl_time_step_bound, maximum_dt)
    selected_bound_index = 0 if cfl_time_step_bound <= maximum_dt else 1
    if not math.isfinite(time_step) or time_step <= 0.0:
        raise ValueError("invalid adaptive time step")

    available_volume = 0.0
    receiver_area = 0.0
    for cell in range(cell_count):
        if donor_overlap_area[cell] > 0.0:
            available_volume += donor_overlap_area[cell] * max(
                state[cell, 0] - P2_RESERVE_DEPTH_M,
                0.0,
            )
        receiver_area += receiver_overlap_area[cell]
    effective_q = min(
        q0_m3_s,
        P2_MAXIMUM_FRACTION_PER_STEP * available_volume / time_step,
    )

    fishway_mass_source = np.zeros(cell_count, dtype=np.float64)
    fishway_hu_source = np.zeros(cell_count, dtype=np.float64)
    fishway_hv_source = np.zeros(cell_count, dtype=np.float64)
    if effective_q > 0.0 and available_volume > 0.0 and receiver_area > 0.0:
        for cell in range(cell_count):
            if donor_overlap_area[cell] > 0.0:
                cell_available = donor_overlap_area[cell] * max(
                    state[cell, 0] - P2_RESERVE_DEPTH_M,
                    0.0,
                )
                local_q = effective_q * cell_available / available_volume
                fishway_mass_source[cell] -= local_q
                depth = max(state[cell, 0], 1e-12)
                fishway_hu_source[cell] -= local_q * state[cell, 1] / depth
                fishway_hv_source[cell] -= local_q * state[cell, 2] / depth
            if receiver_overlap_area[cell] > 0.0:
                fishway_mass_source[cell] += (
                    effective_q * receiver_overlap_area[cell] / receiver_area
                )

    next_state = np.empty_like(state)
    max_cfl = 0.0
    fishway_source_residual = 0.0
    for cell in range(cell_count):
        rhs_0 = -residual[cell, 0] + fishway_mass_source[cell]
        rhs_1 = -residual[cell, 1] + fishway_hu_source[cell]
        rhs_2 = -residual[cell, 2] + fishway_hv_source[cell]
        fishway_source_residual += fishway_mass_source[cell]
        next_h = state[cell, 0] + time_step * rhs_0 * inverse_areas[cell]
        next_hu = state[cell, 1] + time_step * rhs_1 * inverse_areas[cell]
        next_hv = state[cell, 2] + time_step * rhs_2 * inverse_areas[cell]
        depth = max(next_h, 1e-8)
        velocity = math.hypot(next_hu, next_hv) / depth
        damping = (
            1.0
            + time_step
            * GRAVITY_M_S2
            * manning[cell]
            * manning[cell]
            * velocity
            / depth ** (4.0 / 3.0)
        )
        next_state[cell, 0] = next_h
        next_state[cell, 1] = next_hu / damping
        next_state[cell, 2] = next_hv / damping
        if not (
            math.isfinite(next_state[cell, 0])
            and math.isfinite(next_state[cell, 1])
            and math.isfinite(next_state[cell, 2])
        ) or next_state[cell, 0] < 0.0:
            raise ValueError("nonfinite or negative-depth state")
        local_cfl = time_step * denominator[cell] * inverse_areas[cell]
        max_cfl = max(max_cfl, local_cfl)

    return (
        next_state,
        time_step,
        max_cfl,
        boundary_outflow,
        effective_q,
        fishway_source_residual,
        limiting_cell_id,
        limiting_cell_area,
        limiting_spectral_radius_face_length_sum,
        cell_count,
        evaluated_cell_count,
        coverage_complete,
        cfl_target,
        maximum_dt,
        cfl_time_step_bound,
        maximum_dt,
        selected_bound_index,
    )


@njit(cache=True, fastmath=False)
def advance_h2_step_depth_weighted_boundary(
    state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    areas: np.ndarray,
    inverse_areas: np.ndarray,
    left_cells: np.ndarray,
    right_cells: np.ndarray,
    internal_lengths: np.ndarray,
    internal_normals: np.ndarray,
    interface_multiplier_by_face: np.ndarray,
    boundary_cells: np.ndarray,
    boundary_lengths: np.ndarray,
    boundary_normals: np.ndarray,
    boundary_tags: np.ndarray,
    tide_target_m: float,
    target_discharge_by_tag: np.ndarray,
    donor_overlap_area: np.ndarray,
    receiver_overlap_area: np.ndarray,
    q0_m3_s: float,
    cfl_target: float,
    maximum_dt: float,
) -> tuple[np.ndarray, float, float, float, float, float]:
    """Compatibility entrance with the unchanged six-value return contract."""

    result = _advance_h2_step_depth_weighted_boundary_with_trace_core_v1(
        state,
        bed,
        manning,
        areas,
        inverse_areas,
        left_cells,
        right_cells,
        internal_lengths,
        internal_normals,
        interface_multiplier_by_face,
        boundary_cells,
        boundary_lengths,
        boundary_normals,
        boundary_tags,
        tide_target_m,
        target_discharge_by_tag,
        donor_overlap_area,
        receiver_overlap_area,
        q0_m3_s,
        cfl_target,
        maximum_dt,
    )
    return result[0], result[1], result[2], result[3], result[4], result[5]


def advance_h2_step_depth_weighted_boundary_with_trace_v1(
    state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    areas: np.ndarray,
    inverse_areas: np.ndarray,
    left_cells: np.ndarray,
    right_cells: np.ndarray,
    internal_lengths: np.ndarray,
    internal_normals: np.ndarray,
    interface_multiplier_by_face: np.ndarray,
    boundary_cells: np.ndarray,
    boundary_lengths: np.ndarray,
    boundary_normals: np.ndarray,
    boundary_tags: np.ndarray,
    tide_target_m: float,
    target_discharge_by_tag: np.ndarray,
    donor_overlap_area: np.ndarray,
    receiver_overlap_area: np.ndarray,
    q0_m3_s: float,
    cfl_target: float,
    maximum_dt: float,
) -> DepthWeightedBoundaryStepWithTraceV1:
    """Advance once and expose the exact, same-pass limiter evidence.

    This entrance performs one numerical-kernel call.  It never reconstructs
    face speeds, denominators, or an argmin in Python.  Non-finite or partial
    candidate scans fail closed before telemetry can consume the result.
    """

    from stage20_dynamic_mesh_comparison_telemetry_v1 import (
        CFL_DT_BOUND_NAME,
        MAXIMUM_DT_BOUND_NAME,
        LimiterSample,
    )

    result = _advance_h2_step_depth_weighted_boundary_with_trace_core_v1(
        state,
        bed,
        manning,
        areas,
        inverse_areas,
        left_cells,
        right_cells,
        internal_lengths,
        internal_normals,
        interface_multiplier_by_face,
        boundary_cells,
        boundary_lengths,
        boundary_normals,
        boundary_tags,
        tide_target_m,
        target_discharge_by_tag,
        donor_overlap_area,
        receiver_overlap_area,
        q0_m3_s,
        cfl_target,
        maximum_dt,
    )
    limiting_cell_id = int(result[6])
    limiting_cell_area = float(result[7])
    limiting_spectral_sum = float(result[8])
    expected_cell_count = int(result[9])
    evaluated_cell_count = int(result[10])
    coverage_complete = bool(result[11])
    cfl_bound = float(result[14])
    maximum_dt_bound = float(result[15])
    selected_bound_index = int(result[16])
    if not (
        coverage_complete
        and expected_cell_count > 0
        and evaluated_cell_count == expected_cell_count
        and 0 <= limiting_cell_id < expected_cell_count
        and math.isfinite(limiting_cell_area)
        and limiting_cell_area > 0.0
        and math.isfinite(limiting_spectral_sum)
        and limiting_spectral_sum >= 0.0
        and math.isfinite(cfl_bound)
        and cfl_bound > 0.0
        and math.isfinite(maximum_dt_bound)
        and maximum_dt_bound > 0.0
        and selected_bound_index in (0, 1)
    ):
        raise ValueError("incomplete or nonfinite limiter candidate scan")
    selected_bound_name = (
        CFL_DT_BOUND_NAME
        if selected_bound_index == 0
        else MAXIMUM_DT_BOUND_NAME
    )
    limiter_sample = LimiterSample(
        cell_id=limiting_cell_id,
        cell_area_m2=limiting_cell_area,
        spectral_radius_face_length_sum_m2_per_s=limiting_spectral_sum,
        cfl_target=float(result[12]),
        maximum_dt_s=maximum_dt_bound,
        expected_candidate_count=expected_cell_count,
        evaluated_candidate_count=evaluated_cell_count,
        coverage_complete=coverage_complete,
        dt_bounds_s={
            CFL_DT_BOUND_NAME: cfl_bound,
            MAXIMUM_DT_BOUND_NAME: maximum_dt_bound,
        },
        selected_bound_name=selected_bound_name,
    )
    return DepthWeightedBoundaryStepWithTraceV1(
        next_state=result[0],
        accepted_dt_s=float(result[1]),
        maximum_cfl=float(result[2]),
        boundary_outflow_m3_s=float(result[3]),
        effective_fishway_discharge_m3_s=float(result[4]),
        fishway_source_residual_m3_s=float(result[5]),
        limiter_sample=limiter_sample,
    )


def initial_condition_data() -> tuple[dict[str, Any], dict[str, Any]]:
    contract = read_json(SOURCE_CONTRACT)
    _, source_package = pilot.load_mesh(ROOT, contract)
    water_manifest, mask = load_water_mask(WATER_MANIFEST)
    source_geometry = mesh_geometry(source_package)
    source_owner = classify_branch_ownership(source_package, source_geometry)
    source_case_fields = build_case_fields(
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
    source_image_vertices = (
        source_package["vertex_image_millipixel"].astype(np.float64) * 1.0e-3
    )
    source_triangles = source_package["triangles"].astype(np.int32)
    source_image_centroids = source_image_vertices[source_triangles].mean(axis=1)
    return {
        "contract": contract,
        "waterManifest": water_manifest,
        "imageVertices": source_image_vertices,
        "triangles": source_triangles,
        "imageCentroids": source_image_centroids,
        "finder": spatial.triangle_finder(source_image_vertices, source_triangles),
        "depth": source_depth,
        "u": source_u,
        "v": source_v,
        "bed": np.asarray(source_case_fields["bedElevationM"], dtype=np.float64),
        "manning": np.asarray(source_case_fields["manningN"], dtype=np.float64),
        "boundaryDischargeM3S": dict(source_case_fields["boundaryDischargeM3S"]),
        "tide": dict(source_case_fields["tide"]),
    }, read_json(TIDE_CANDIDATE)


def initialize_mesh(
    mesh: dict[str, np.ndarray],
    geometry: dict[str, np.ndarray],
    source: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    vertices_image = spatial.metric_vertices_to_image(
        geometry["vertices"],
        source["waterManifest"]["coordinateSystem"],
    )
    image_centroids = vertices_image[geometry["triangles"]].mean(axis=1)
    source_cell, mapping = spatial.containing_cells(
        source["finder"],
        image_centroids,
        source["imageCentroids"],
    )
    depth = source["depth"][source_cell]
    u = source["u"][source_cell]
    v = source["v"][source_cell]
    state = np.column_stack((depth, depth * u, depth * v)).astype(np.float64)
    return (
        state,
        source["bed"][source_cell].copy(),
        source["manning"][source_cell].copy(),
        mapping,
    )


def run_case(
    initial_state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    geometry: dict[str, np.ndarray],
    p2: tuple[np.ndarray, np.ndarray],
    source: dict[str, Any],
    tide_candidate: dict[str, Any],
    case: dict[str, Any],
    *,
    target_seconds: float,
    cfl_target: float,
) -> tuple[np.ndarray, dict[str, Any], dict[str, np.ndarray]]:
    state = initial_state.copy()
    multiplier = interface_multiplier(geometry, list(case["openGates"]))
    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
    elapsed = 0.0
    step = 0
    next_checkpoint = 1.0
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_fishway_source_residual = 0.0
    minimum_effective_q = math.inf
    maximum_effective_q = 0.0
    time_values = [0.0]
    mean_eta_values = [
        float(np.average(state[:, 0] + bed, weights=geometry["areas"]))
    ]
    mean_speed_values = [
        float(
            np.average(
                np.hypot(state[:, 1], state[:, 2])
                / np.maximum(state[:, 0], 1e-12),
                weights=geometry["areas"],
            )
        )
    ]
    wall_start = time.monotonic()
    tide_clock_start = (
        float(source["contract"]["run"]["tideCurveStartHour"]) * 3600.0
        + float(read_json(SOURCE_REPORT)["run"]["simulatedSeconds"])
    )
    while elapsed < target_seconds - 1e-12:
        stop_at = min(target_seconds, next_checkpoint)
        maximum_dt = stop_at - elapsed
        tide_target = reference.tide_anomaly_m(
            tide_clock_start + elapsed,
            source["tide"],
            tide_candidate,
        )
        (
            state,
            dt,
            cfl,
            boundary_outflow,
            effective_q,
            fishway_source_residual,
        ) = _advance_h2_step(
            state,
            bed,
            manning,
            geometry["areas"],
            geometry["inverseAreas"],
            geometry["left"],
            geometry["right"],
            geometry["internalLengths"],
            geometry["internalNormals"],
            multiplier,
            geometry["boundaryCells"],
            geometry["boundaryLengths"],
            geometry["boundaryNormals"],
            geometry["boundaryTags"],
            tide_target,
            target_flux_by_tag,
            p2[0],
            p2[1],
            float(case["Q0M3S"]),
            cfl_target,
            maximum_dt,
        )
        elapsed += dt
        step += 1
        expected_volume -= dt * boundary_outflow
        actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        mass_error = abs(actual_volume - expected_volume) / max(
            abs(initial_volume),
            1.0,
        )
        maximum_cfl = max(maximum_cfl, float(cfl))
        maximum_mass_error = max(maximum_mass_error, mass_error)
        maximum_fishway_source_residual = max(
            maximum_fishway_source_residual,
            abs(float(fishway_source_residual)),
        )
        minimum_effective_q = min(minimum_effective_q, float(effective_q))
        maximum_effective_q = max(maximum_effective_q, float(effective_q))
        if elapsed >= next_checkpoint - 1e-10 or elapsed >= target_seconds - 1e-10:
            time_values.append(elapsed)
            mean_eta_values.append(
                float(np.average(state[:, 0] + bed, weights=geometry["areas"]))
            )
            mean_speed_values.append(
                float(
                    np.average(
                        np.hypot(state[:, 1], state[:, 2])
                        / np.maximum(state[:, 0], 1e-12),
                        weights=geometry["areas"],
                    )
                )
            )
            next_checkpoint += 1.0
    depth = state[:, 0]
    speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(depth, 1e-12)
    report = {
        "simulatedSeconds": elapsed,
        "stepsCompleted": step,
        "wallSeconds": time.monotonic() - wall_start,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "maximumAbsoluteFishwayMassSourceResidualM3S":
            maximum_fishway_source_residual,
        "minimumEffectiveFishwayDischargeM3S": minimum_effective_q,
        "maximumEffectiveFishwayDischargeM3S": maximum_effective_q,
        "fishwayQ0WasCapped": minimum_effective_q
            < float(case["Q0M3S"]) - 1e-12,
        "minimumDepthM": float(depth.min()),
        "maximumDepthM": float(depth.max()),
        "maximumSpeedMPS": float(speed.max()),
        "negativeDepthCount": int(np.sum(depth < 0.0)),
        "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
    }
    series = {
        "timeS": np.asarray(time_values, dtype=np.float64),
        "meanEtaM": np.asarray(mean_eta_values, dtype=np.float64),
        "meanSpeedMPS": np.asarray(mean_speed_values, dtype=np.float64),
    }
    return state, report, series


def direct_metrics(
    formal_state: np.ndarray,
    formal_bed: np.ndarray,
    multizone_state: np.ndarray,
    multizone_bed: np.ndarray,
    formal_to_multizone: np.ndarray,
    weights: np.ndarray,
    mask: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    formal_h = formal_state[:, 0]
    formal_u = formal_state[:, 1] / np.maximum(formal_h, 1e-12)
    formal_v = formal_state[:, 2] / np.maximum(formal_h, 1e-12)
    multizone_h = multizone_state[:, 0]
    multizone_u = multizone_state[:, 1] / np.maximum(multizone_h, 1e-12)
    multizone_v = multizone_state[:, 2] / np.maximum(multizone_h, 1e-12)
    mapped = formal_to_multizone
    formal_eta = formal_h + formal_bed
    multizone_eta = multizone_h[mapped] + multizone_bed[mapped]
    velocity_error = np.hypot(
        multizone_u[mapped] - formal_u,
        multizone_v[mapped] - formal_v,
    )
    eta_error = multizone_eta - formal_eta
    selected = np.asarray(mask, dtype=bool)
    result = spatial.metrics(
        multizone_eta[selected],
        multizone_u[mapped][selected],
        multizone_v[mapped][selected],
        formal_eta[selected],
        formal_u[selected],
        formal_v[selected],
        weights[selected],
    )
    return result, eta_error, velocity_error


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    approval = read_json(APPROVAL)
    require(
        approval["status"]
        == "approved_bounded_H2_dynamics_comparison_R20_vs_multizone",
        "H2 dynamics diagnostic is not approved",
    )
    for key, record in approval["bindings"].items():
        path = ROOT / record["path"]
        require(path.is_file(), f"missing approval binding {key}")
        require(sha256(path) == record["sha256"], f"approval binding changed: {key}")
    for path, expected in {**EXPECTED, **PROTECTED}.items():
        require(path.is_file(), f"missing pinned input: {path}")
        require(sha256(path) == expected, f"pinned input changed: {path}")

    source, tide_candidate = initial_condition_data()
    mesh_records = {
        "formalR20": {
            "path": FORMAL_MESH,
            "summaryPath": FORMAL_SUMMARY,
        },
        "multizone": {
            "path": MULTIZONE_MESH,
            "summaryPath": MULTIZONE_SUMMARY,
        },
    }
    p2_source = read_json(P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_polygons = {
        side: Polygon(
            old.project_many(
                p2_source[side]["footprint"]["coordinates"][0][:-1]
            )
        )
        for side in ("upstream", "downstream")
    }
    for mesh_id, record in mesh_records.items():
        mesh = mesh_arrays(record["path"])
        geometry = build_review_geometry(mesh)
        summary = read_json(record["summaryPath"])
        initial_state, bed, manning, mapping = initialize_mesh(
            mesh,
            geometry,
            source,
        )
        record.update(
            {
                "mesh": mesh,
                "geometry": geometry,
                "summary": summary,
                "initialState": initial_state,
                "bed": bed,
                "manning": manning,
                "sourceMapping": mapping,
                "P2": p2_arrays(geometry, summary, p2_polygons),
            }
        )

    formal = mesh_records["formalR20"]
    multizone = mesh_records["multizone"]
    multizone_finder = spatial.triangle_finder(
        multizone["geometry"]["vertices"],
        multizone["geometry"]["triangles"],
    )
    formal_centroids = formal["geometry"]["centroids"]
    formal_to_multizone, comparison_mapping = spatial.containing_cells(
        multizone_finder,
        formal_centroids,
        multizone["geometry"]["centroids"],
    )
    cut_features = read_json(CUT)["features"]
    cut_line = MultiLineString(
        [
            old.project_many(feature["geometry"]["coordinates"])
            for feature in cut_features
            if feature["geometry"]["type"] == "LineString"
        ]
    )
    barrage_distance = np.asarray(
        [cut_line.distance(Point(point)) for point in formal_centroids],
        dtype=np.float64,
    )
    p2_mask = np.asarray(
        [
            p2_polygons["upstream"].covers(Point(point))
            or p2_polygons["downstream"].covers(Point(point))
            for point in formal_centroids
        ],
        dtype=bool,
    )
    regions = {
        "fullConfirmedDomain": np.ones(len(formal_centroids), dtype=bool),
        "barrageWithin100M": barrage_distance <= 100.0,
        "fishwayP2Footprints": p2_mask,
        "nishikawaConfluenceWithin150M":
            np.linalg.norm(formal_centroids - NISHIKAWA, axis=1) <= 150.0,
        "magarigawaConfluenceWithin180M":
            np.linalg.norm(formal_centroids - MAGARIGAWA, axis=1) <= 180.0,
    }
    require(all(np.any(mask) for mask in regions.values()), "empty comparison region")

    target_seconds = float(
        approval["authorizedDiagnostic"]["targetPhysicalSecondsPerCase"]
    )
    cfl_target = float(approval["authorizedDiagnostic"]["cflTarget"])
    case_results = []
    all_eta_error = []
    all_velocity_error = []
    all_time = []
    all_eta_rmse_time = []
    all_velocity_rmse_time = []
    for case in approval["authorizedDiagnostic"]["cases"]:
        states: dict[str, np.ndarray] = {}
        reports: dict[str, dict[str, Any]] = {}
        series: dict[str, dict[str, np.ndarray]] = {}
        for mesh_id, record in mesh_records.items():
            state, report, mesh_series = run_case(
                record["initialState"],
                record["bed"],
                record["manning"],
                record["geometry"],
                record["P2"],
                source,
                tide_candidate,
                case,
                target_seconds=target_seconds,
                cfl_target=cfl_target,
            )
            states[mesh_id] = state
            reports[mesh_id] = report
            series[mesh_id] = mesh_series
        region_metrics = []
        eta_error = None
        velocity_error = None
        for region_id, region_mask in regions.items():
            measured, eta_field, velocity_field = direct_metrics(
                states["formalR20"],
                formal["bed"],
                states["multizone"],
                multizone["bed"],
                formal_to_multizone,
                formal["geometry"]["areas"],
                region_mask,
            )
            region_metrics.append({"regionId": region_id, **measured})
            if region_id == "fullConfirmedDomain":
                eta_error = eta_field
                velocity_error = velocity_field
        require(eta_error is not None and velocity_error is not None, "missing errors")
        all_eta_error.append(eta_error.astype(np.float32))
        all_velocity_error.append(velocity_error.astype(np.float32))

        checkpoint_time = series["formalR20"]["timeS"]
        require(
            np.allclose(checkpoint_time, series["multizone"]["timeS"]),
            "mesh checkpoint times differ",
        )
        # The compact time trace compares domain means.  Final regional fields
        # remain the authoritative spatial comparison.
        all_time.append(checkpoint_time)
        all_eta_rmse_time.append(
            np.abs(
                series["multizone"]["meanEtaM"]
                - series["formalR20"]["meanEtaM"]
            )
        )
        all_velocity_rmse_time.append(
            np.abs(
                series["multizone"]["meanSpeedMPS"]
                - series["formalR20"]["meanSpeedMPS"]
            )
        )
        case_results.append(
            {
                "caseId": case["caseId"],
                "openGates": case["openGates"],
                "Q0M3S": case["Q0M3S"],
                "meshRuns": reports,
                "regionalComparison": region_metrics,
            }
        )

    eta_errors = np.stack(all_eta_error)
    velocity_errors = np.stack(all_velocity_error)
    case_ids = [case["caseId"] for case in approval["authorizedDiagnostic"]["cases"]]
    max_eta_index = np.argmax(np.abs(eta_errors), axis=0)
    max_velocity_index = np.argmax(velocity_errors, axis=0)
    np.savez_compressed(
        FIELDS,
        case_ids=np.asarray(case_ids, dtype="U48"),
        formal_R20_centroids_m=formal_centroids.astype(np.float64),
        formal_R20_cell_area_m2=formal["geometry"]["areas"].astype(np.float64),
        barrage_distance_m=barrage_distance.astype(np.float64),
        fishway_P2_mask=p2_mask.astype(np.uint8),
        water_surface_elevation_error_m=eta_errors,
        velocity_vector_error_mps=velocity_errors,
        maximum_absolute_water_surface_elevation_error_m=np.max(
            np.abs(eta_errors),
            axis=0,
        ).astype(np.float32),
        maximum_water_surface_elevation_error_case_index=max_eta_index.astype(
            np.uint8
        ),
        maximum_velocity_vector_error_mps=np.max(
            velocity_errors,
            axis=0,
        ).astype(np.float32),
        maximum_velocity_error_case_index=max_velocity_index.astype(np.uint8),
        checkpoint_time_s=np.stack(all_time).astype(np.float64),
        absolute_domain_mean_eta_difference_m=np.stack(
            all_eta_rmse_time
        ).astype(np.float64),
        absolute_domain_mean_speed_difference_mps=np.stack(
            all_velocity_rmse_time
        ).astype(np.float64),
    )

    screening_guides = approval["acceptance"]["screeningGuides"]
    screenings = []
    for case in case_results:
        for region in case["regionalComparison"]:
            screenings.append(
                {
                    "caseId": case["caseId"],
                    "regionId": region["regionId"],
                    "waterSurfaceElevationRmseM": {
                        "measured": region["waterSurfaceElevationRmseM"],
                        "guideMaximum": screening_guides[
                            "waterSurfaceElevationRmseM"
                        ],
                        "passed": region["waterSurfaceElevationRmseM"]
                            <= screening_guides["waterSurfaceElevationRmseM"],
                    },
                    "velocityVectorRmseMPS": {
                        "measured": region["velocityVectorRmseMPS"],
                        "guideMaximum": screening_guides[
                            "velocityVectorRmseMPS"
                        ],
                        "passed": region["velocityVectorRmseMPS"]
                            <= screening_guides["velocityVectorRmseMPS"],
                    },
                }
            )
    worst_velocity = max(
        screenings,
        key=lambda row: row["velocityVectorRmseMPS"]["measured"],
    )
    worst_eta = max(
        screenings,
        key=lambda row: row["waterSurfaceElevationRmseM"]["measured"],
    )
    all_run_reports = [
        report
        for case in case_results
        for report in case["meshRuns"].values()
    ]
    summary = {
        "schema": "onga-stage20-R20-multizone-H2-dynamics-diagnostic-v1",
        "version": 1,
        "status": "bounded_H2_dynamics_diagnostic_complete_pending_user_judgment",
        "method": {
            "type": "same_initial_field_same_H2_laws_two_review_meshes",
            "caseCount": len(case_results),
            "meshRunCount": len(all_run_reports),
            "targetPhysicalSecondsPerCase": target_seconds,
            "newH2SolverDiagnosticRunPerformed": True,
            "productionSolverChanged": False,
            "initialCondition": (
                "sealed_600s_legacy_field_resampled_piecewise_constant_to_each_mesh;"
                "_gate_state_is_switched_at_diagnostic_time_zero"
            ),
            "mainGateLaw": approval["authorizedDiagnostic"]["mainGateLaw"],
            "fishwayLaw": approval["authorizedDiagnostic"]["fishwayLaw"],
            "physicalValidationClaimAllowed": False,
            "productionMeshAdoptionAutomaticallyAuthorized": False,
        },
        "mesh": {
            "formalR20CellCount": int(len(formal["geometry"]["triangles"])),
            "multizoneCellCount": int(len(multizone["geometry"]["triangles"])),
            "cellCountReductionPercent": 100.0
                * (
                    len(formal["geometry"]["triangles"])
                    - len(multizone["geometry"]["triangles"])
                )
                / len(formal["geometry"]["triangles"]),
            "sourceMapping": {
                "formalR20": formal["sourceMapping"],
                "multizone": multizone["sourceMapping"],
                "formalToMultizone": comparison_mapping,
            },
            "gateFaceCounts": {
                "formalR20": formal["geometry"]["gateFaceCounts"],
                "multizone": multizone["geometry"]["gateFaceCounts"],
            },
        },
        "cases": case_results,
        "screening": {
            "guideMeaning": (
                "non_authoritative_mesh_difference_screening_only;"
                "_not_physical_validation_or_automatic_adoption"
            ),
            "allCaseRegionGuideCount": len(screenings),
            "passedCount": sum(
                row["waterSurfaceElevationRmseM"]["passed"]
                and row["velocityVectorRmseMPS"]["passed"]
                for row in screenings
            ),
            "worstWaterSurfaceElevationRmse": worst_eta,
            "worstVelocityVectorRmse": worst_velocity,
            "allPassed": all(
                row["waterSurfaceElevationRmseM"]["passed"]
                and row["velocityVectorRmseMPS"]["passed"]
                for row in screenings
            ),
        },
        "numericalSafety": {
            "maximumCfl": max(report["maximumCfl"] for report in all_run_reports),
            "maximumRelativeMassBalanceError": max(
                report["maximumRelativeMassBalanceError"]
                for report in all_run_reports
            ),
            "maximumAbsoluteFishwayMassSourceResidualM3S": max(
                report["maximumAbsoluteFishwayMassSourceResidualM3S"]
                for report in all_run_reports
            ),
            "negativeDepthCount": sum(
                report["negativeDepthCount"] for report in all_run_reports
            ),
            "nonFiniteValueCount": sum(
                report["nonFiniteValueCount"] for report in all_run_reports
            ),
            "fishwayQ0CappedRunCount": sum(
                report["fishwayQ0WasCapped"] for report in all_run_reports
            ),
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
            "waterManifest": binding(WATER_MANIFEST),
            "comparisonFields": binding(FIELDS),
        },
        "safeguards": {
            "diagnosticOnly": True,
            "productionMeshChanged": False,
            "productionSolverSourceChanged": False,
            "precomputationRun": False,
            "responsePackChanged": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
    }
    write_json(SUMMARY, summary)

    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, observed: Any) -> None:
        checks.append(
            {"id": check_id, "passed": bool(passed), "observed": observed}
        )

    acceptance = approval["acceptance"]
    check("approval_binding_valid", True, binding(APPROVAL))
    check("all_12_cases_completed_on_both_meshes", len(all_run_reports) == 24, len(all_run_reports))
    check(
        "maximum_cfl_within_approved_limit",
        summary["numericalSafety"]["maximumCfl"] <= acceptance["maximumCfl"],
        summary["numericalSafety"]["maximumCfl"],
    )
    check(
        "mass_balance_within_approved_limit",
        summary["numericalSafety"]["maximumRelativeMassBalanceError"]
        <= acceptance["maximumRelativeMassBalanceError"],
        summary["numericalSafety"]["maximumRelativeMassBalanceError"],
    )
    check(
        "fishway_pair_mass_source_is_equal_and_opposite",
        summary["numericalSafety"][
            "maximumAbsoluteFishwayMassSourceResidualM3S"
        ]
        <= 1e-12,
        summary["numericalSafety"][
            "maximumAbsoluteFishwayMassSourceResidualM3S"
        ],
    )
    check(
        "negative_depth_count_zero",
        summary["numericalSafety"]["negativeDepthCount"]
        == acceptance["negativeDepthCount"],
        summary["numericalSafety"]["negativeDepthCount"],
    )
    check(
        "nonfinite_value_count_zero",
        summary["numericalSafety"]["nonFiniteValueCount"]
        == acceptance["nonFiniteValueCount"],
        summary["numericalSafety"]["nonFiniteValueCount"],
    )
    check(
        "P2_Q0_not_safety_capped",
        summary["numericalSafety"]["fishwayQ0CappedRunCount"] == 0,
        summary["numericalSafety"]["fishwayQ0CappedRunCount"],
    )
    check(
        "all_mesh_difference_screening_guides_pass",
        summary["screening"]["allPassed"],
        {
            "passed": summary["screening"]["passedCount"],
            "total": summary["screening"]["allCaseRegionGuideCount"],
        },
    )
    check(
        "protected_runtime_unchanged",
        all(sha256(path) == expected for path, expected in PROTECTED.items()),
        {str(path.relative_to(ROOT)): sha256(path) for path in PROTECTED},
    )
    check(
        "no_production_or_precompute_changes",
        not any(
            (
                summary["safeguards"]["productionMeshChanged"],
                summary["safeguards"]["productionSolverSourceChanged"],
                summary["safeguards"]["precomputationRun"],
                summary["safeguards"]["responsePackChanged"],
                summary["safeguards"]["publicRuntimeChanged"],
                summary["safeguards"]["mainMerged"],
            )
        ),
        summary["safeguards"],
    )
    failed = [item for item in checks if not item["passed"]]
    validation = {
        "schema": "onga-stage20-R20-multizone-H2-dynamics-diagnostic-v1-static-validation",
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "checks": checks,
    }
    write_json(VALIDATION, validation)

    manifest = {
        "schema": "onga-stage20-R20-multizone-H2-dynamics-diagnostic-v1-manifest",
        "status": "complete_pending_user_judgment",
        "files": [
            binding(SUMMARY),
            binding(VALIDATION),
            binding(FIELDS),
        ],
        "safeguards": summary["safeguards"],
    }
    write_json(MANIFEST, manifest)
    require(
        not failed,
        f"H2 dynamics diagnostic validation failed: {[item['id'] for item in failed]}",
    )
    print(
        json.dumps(
            {
                "result": "PASS_BOUNDED_H2_DYNAMICS_DIAGNOSTIC",
                "summary": binding(SUMMARY),
                "validation": binding(VALIDATION),
                "fields": binding(FIELDS),
                "manifest": binding(MANIFEST),
                "screening": summary["screening"],
                "numericalSafety": summary["numericalSafety"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    raise SystemExit(
        "This review-only module provides "
        "advance_h2_step_depth_weighted_boundary and has no standalone run."
    )
