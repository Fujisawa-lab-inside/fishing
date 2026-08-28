#!/usr/bin/env python3
"""Run the approved isolated C1 600 s continuous-transition diagnostic."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
from numba import njit
from shapely.geometry import MultiLineString, Point, Polygon

import evaluate_stage20_R20_multizone_field_convergence_v1 as spatial
import generate_stage20_fishway_F3_review_mesh_v1 as old
import run_stage20_R20_multizone_H2_dynamics_diagnostic_v1 as short
import run_stage20_R20_multizone_H3b_H2_60s_diagnostic_v1 as previous_h3b
import stage19_shallow_water_kernel_v1 as reference
import stage20_barrage_continuous_face_mapping_candidate_v1 as mapping
import stage20_barrage_sequential_operation_v1 as operation
import stage20_shallow_water_kernel_v3 as compiled


ROOT = Path(__file__).resolve().parents[1]
APPROVAL = (
    ROOT / "config/stage20_barrage_C1_local_transition_600s_approval_v1.json"
)
OUTPUT = (
    ROOT / "docs/results/stage20-barrage-C1-local-transition-600s-v1"
)
SUMMARY = OUTPUT / "diagnostic-summary.json"
VALIDATION = OUTPUT / "static-validation.json"
FIELDS = OUTPUT / "diagnostic-fields.npz"
MANIFEST = OUTPUT / "manifest.json"
RAW_RUN_REPORTS = OUTPUT / "raw-run-reports.json"
RAW_CASE_COMPARISONS = OUTPUT / "raw-case-comparisons.json"

FORMAL_MESH = (
    ROOT
    / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1"
    / "review-mesh.npz"
)
FORMAL_SUMMARY = (
    ROOT
    / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1"
    / "mesh-summary.json"
)
H3B_MESH = (
    ROOT
    / "docs/results/stage20-R20-multizone-H3b-main-channel-patch-mesh-v1"
    / "review-mesh.npz"
)
H3B_SUMMARY = (
    ROOT
    / "docs/results/stage20-R20-multizone-H3b-main-channel-patch-mesh-v1"
    / "mesh-summary.json"
)

CURRENT_BINARY_INTERFACE = ROOT / "tools/stage20_barrage_interface_v2.py"
CURRENT_BINARY_CONTRACT = (
    ROOT / "config/stage20_open_boundary_solver_contract_v2.json"
)
EXPECTED_CURRENT_BINARY_INTERFACE_SHA = (
    "3723b3afbfda4c324bb2398d7f6c3544921b0ee80ec57e90f3a8a95cbd514de0"
)
EXPECTED_CURRENT_BINARY_CONTRACT_SHA = (
    "db36dcf31e1e9063d7c2d3a1af69aa11f350a4d11955f19e2bc9656eda9b8ea3"
)


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


def build_mapping_workspace(
    geometry: dict[str, np.ndarray],
) -> dict[str, Any]:
    base_lengths = np.asarray(
        geometry["internalLengths"],
        dtype=np.float64,
    )
    markers = np.asarray(geometry["internalMarkers"], dtype=np.int32)
    bound, factors = mapping.gate_bound_lengths_and_width_factors(
        geometry
    )
    effective_lengths = base_lengths.copy()
    multipliers = np.ones_like(base_lengths)
    multipliers[markers == mapping.FIXED_MARKER] = 0.0
    gate_face_ids = []
    gate_index_by_selected_face = []
    face_ids_by_gate: list[np.ndarray] = []
    for gate in mapping.GATE_IDS:
        ids = np.flatnonzero(
            markers == mapping.GATE_MARKER_BASE + gate
        ).astype(np.int64)
        require(len(ids) > 0, f"gate {gate} has no faces")
        face_ids_by_gate.append(ids)
        gate_face_ids.extend(int(value) for value in ids)
        gate_index_by_selected_face.extend([gate - 1] * len(ids))
    return {
        "baseLengths": base_lengths,
        "effectiveLengths": effective_lengths,
        "multipliers": multipliers,
        "markers": markers,
        "boundLengths": np.asarray(
            [bound[gate] for gate in mapping.GATE_IDS],
            dtype=np.float64,
        ),
        "widthFactors": np.asarray(
            [factors[gate] for gate in mapping.GATE_IDS],
            dtype=np.float64,
        ),
        "faceIdsByGate": face_ids_by_gate,
        "gateFaceIds": np.asarray(gate_face_ids, dtype=np.int64),
        "gateIndexBySelectedFace": np.asarray(
            gate_index_by_selected_face,
            dtype=np.int64,
        ),
    }


def update_mapping_workspace(
    workspace: dict[str, Any],
    alpha: np.ndarray,
) -> None:
    require(
        alpha.shape == (8,)
        and np.isfinite(alpha).all()
        and np.all((alpha >= 0.0) & (alpha <= 1.0)),
        "invalid C1 capacity vector",
    )
    base_lengths = workspace["baseLengths"]
    effective_lengths = workspace["effectiveLengths"]
    multipliers = workspace["multipliers"]
    for gate_index, face_ids in enumerate(workspace["faceIdsByGate"]):
        value = float(alpha[gate_index])
        width_factor = float(workspace["widthFactors"][gate_index])
        combined = value * width_factor + (1.0 - value)
        effective_lengths[face_ids] = base_lengths[face_ids] * combined
        multipliers[face_ids] = value * width_factor / combined


def case_arrays(case: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    initial = np.asarray(
        [
            float(case["initialCapacityFractionByGateId"][str(gate)])
            for gate in mapping.GATE_IDS
        ],
        dtype=np.float64,
    )
    ramping = np.asarray(
        [int(gate) - 1 for gate in case["rampingGateIds"]],
        dtype=np.int64,
    )
    require(
        np.isfinite(initial).all()
        and np.all((initial >= 0.0) & (initial <= 1.0)),
        f"invalid initial capacity: {case['caseId']}",
    )
    require(
        len(ramping) > 0
        and len(np.unique(ramping)) == len(ramping)
        and np.all((ramping >= 0) & (ramping < 8)),
        f"invalid ramping gates: {case['caseId']}",
    )
    return initial, ramping


def set_capacity_at_time(
    result: np.ndarray,
    initial: np.ndarray,
    ramping: np.ndarray,
    target: float,
    time_sec: float,
    duration_sec: float,
) -> None:
    result[:] = initial
    weight = operation.smoothstep01(time_sec / duration_sec)
    for gate_index in ramping:
        start = float(initial[gate_index])
        result[gate_index] = start + (target - start) * weight


@njit(cache=True, fastmath=False)
def _maximum_gate_mass_residual(
    state: np.ndarray,
    bed: np.ndarray,
    left_cells: np.ndarray,
    right_cells: np.ndarray,
    effective_lengths: np.ndarray,
    normals: np.ndarray,
    multipliers: np.ndarray,
    gate_face_ids: np.ndarray,
) -> tuple[float, float]:
    total_residual = 0.0
    maximum_face_residual = 0.0
    for selected in range(len(gate_face_ids)):
        face = gate_face_ids[selected]
        left = left_cells[face]
        right = right_cells[face]
        normal_x = normals[face, 0]
        normal_y = normals[face, 1]
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
            reconstructed_right_hu = (
                reconstructed_right_h * right_hu / right_h
            )
            reconstructed_right_hv = (
                reconstructed_right_h * right_hv / right_h
            )
        else:
            reconstructed_right_hu = 0.0
            reconstructed_right_hv = 0.0
        open_mass, _, _, _ = compiled._rusanov_one(
            reconstructed_left_h,
            reconstructed_left_hu,
            reconstructed_left_hv,
            reconstructed_right_h,
            reconstructed_right_hu,
            reconstructed_right_hv,
            normal_x,
            normal_y,
        )
        left_normal_momentum = (
            left_hu * normal_x + left_hv * normal_y
        )
        left_reflected_hu = (
            left_hu - 2.0 * left_normal_momentum * normal_x
        )
        left_reflected_hv = (
            left_hv - 2.0 * left_normal_momentum * normal_y
        )
        wall_left_mass, _, _, _ = compiled._rusanov_one(
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
        wall_right_mass, _, _, _ = compiled._rusanov_one(
            right_h,
            right_hu,
            right_hv,
            right_h,
            right_reflected_hu,
            right_reflected_hv,
            right_normal_x,
            right_normal_y,
        )
        multiplier = multipliers[face]
        wall_fraction = 1.0 - multiplier
        length = effective_lengths[face]
        left_mass = length * (
            multiplier * open_mass
            + wall_fraction * wall_left_mass
        )
        right_mass = length * (
            multiplier * (-open_mass)
            + wall_fraction * wall_right_mass
        )
        residual = left_mass + right_mass
        total_residual += residual
        maximum_face_residual = max(
            maximum_face_residual,
            abs(residual),
        )
    return abs(total_residual), maximum_face_residual


@njit(cache=True, fastmath=False)
def _checkpoint_gate_fluxes(
    state: np.ndarray,
    bed: np.ndarray,
    left_cells: np.ndarray,
    right_cells: np.ndarray,
    effective_lengths: np.ndarray,
    normals: np.ndarray,
    multipliers: np.ndarray,
    gate_face_ids: np.ndarray,
    gate_index_by_selected_face: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    open_left = np.zeros(8, dtype=np.float64)
    open_right = np.zeros(8, dtype=np.float64)
    wall_left = np.zeros(8, dtype=np.float64)
    wall_right = np.zeros(8, dtype=np.float64)
    blended_left = np.zeros(8, dtype=np.float64)
    blended_right = np.zeros(8, dtype=np.float64)
    residual = np.zeros(8, dtype=np.float64)
    for selected in range(len(gate_face_ids)):
        face = gate_face_ids[selected]
        gate_index = gate_index_by_selected_face[selected]
        left = left_cells[face]
        right = right_cells[face]
        normal_x = normals[face, 0]
        normal_y = normals[face, 1]
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
            reconstructed_right_hu = (
                reconstructed_right_h * right_hu / right_h
            )
            reconstructed_right_hv = (
                reconstructed_right_h * right_hv / right_h
            )
        else:
            reconstructed_right_hu = 0.0
            reconstructed_right_hv = 0.0
        open_mass, _, _, _ = compiled._rusanov_one(
            reconstructed_left_h,
            reconstructed_left_hu,
            reconstructed_left_hv,
            reconstructed_right_h,
            reconstructed_right_hu,
            reconstructed_right_hv,
            normal_x,
            normal_y,
        )
        left_normal_momentum = (
            left_hu * normal_x + left_hv * normal_y
        )
        left_reflected_hu = (
            left_hu - 2.0 * left_normal_momentum * normal_x
        )
        left_reflected_hv = (
            left_hv - 2.0 * left_normal_momentum * normal_y
        )
        wall_left_mass, _, _, _ = compiled._rusanov_one(
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
        wall_right_mass, _, _, _ = compiled._rusanov_one(
            right_h,
            right_hu,
            right_hv,
            right_h,
            right_reflected_hu,
            right_reflected_hv,
            right_normal_x,
            right_normal_y,
        )
        multiplier = multipliers[face]
        wall_fraction = 1.0 - multiplier
        length = effective_lengths[face]
        local_open_left = length * multiplier * open_mass
        local_open_right = length * multiplier * (-open_mass)
        local_wall_left = length * wall_fraction * wall_left_mass
        local_wall_right = length * wall_fraction * wall_right_mass
        local_blended_left = local_open_left + local_wall_left
        local_blended_right = local_open_right + local_wall_right
        open_left[gate_index] += local_open_left
        open_right[gate_index] += local_open_right
        wall_left[gate_index] += local_wall_left
        wall_right[gate_index] += local_wall_right
        blended_left[gate_index] += local_blended_left
        blended_right[gate_index] += local_blended_right
        residual[gate_index] += (
            local_blended_left + local_blended_right
        )
    return (
        open_left,
        open_right,
        wall_left,
        wall_right,
        blended_left,
        blended_right,
        residual,
    )


def record_checkpoint(
    state: np.ndarray,
    bed: np.ndarray,
    geometry: dict[str, np.ndarray],
    workspace: dict[str, Any],
    alpha: np.ndarray,
) -> tuple[dict[str, np.ndarray], bool]:
    expected_lengths, expected_multipliers, _ = (
        mapping.continuous_face_geometry(
            geometry,
            {
                gate: float(alpha[gate - 1])
                for gate in mapping.GATE_IDS
            },
        )
    )
    mapping_exact = (
        np.array_equal(
            workspace["effectiveLengths"],
            expected_lengths,
        )
        and np.array_equal(
            workspace["multipliers"],
            expected_multipliers,
        )
    )
    values = _checkpoint_gate_fluxes(
        state,
        bed,
        geometry["left"],
        geometry["right"],
        workspace["effectiveLengths"],
        geometry["internalNormals"],
        workspace["multipliers"],
        workspace["gateFaceIds"],
        workspace["gateIndexBySelectedFace"],
    )
    names = (
        "openLeftM3S",
        "openRightM3S",
        "wallLeftM3S",
        "wallRightM3S",
        "blendedLeftM3S",
        "blendedRightM3S",
        "leftPlusRightResidualM3S",
    )
    return {
        name: np.asarray(value, dtype=np.float64)
        for name, value in zip(names, values, strict=True)
    }, mapping_exact


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
    checkpoint_interval: float,
    cfl_target: float,
) -> tuple[list[np.ndarray], dict[str, Any], dict[str, np.ndarray]]:
    state = initial_state.copy()
    workspace = build_mapping_workspace(geometry)
    initial_alpha, ramping = case_arrays(case)
    alpha = np.empty(8, dtype=np.float64)
    duration_sec = 300.0
    target = float(case["targetCapacityFraction"])
    set_capacity_at_time(
        alpha,
        initial_alpha,
        ramping,
        target,
        0.0,
        duration_sec,
    )
    update_mapping_workspace(workspace, alpha)

    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
    checkpoint_count = int(round(target_seconds / checkpoint_interval)) + 1
    capacity_checkpoints = np.zeros(
        (checkpoint_count, 8),
        dtype=np.float64,
    )
    flux_names = (
        "openLeftM3S",
        "openRightM3S",
        "wallLeftM3S",
        "wallRightM3S",
        "blendedLeftM3S",
        "blendedRightM3S",
        "leftPlusRightResidualM3S",
    )
    flux_checkpoints = {
        name: np.zeros((checkpoint_count, 8), dtype=np.float64)
        for name in flux_names
    }
    checkpoint_times = np.zeros(checkpoint_count, dtype=np.float64)
    snapshots = [state.copy()]
    checkpoint_times[0] = 0.0
    capacity_checkpoints[0] = alpha
    flux, mapping_exact = record_checkpoint(
        state,
        bed,
        geometry,
        workspace,
        alpha,
    )
    for name in flux_names:
        flux_checkpoints[name][0] = flux[name]
    mapping_exact_count = int(mapping_exact)

    elapsed = 0.0
    step = 0
    next_checkpoint_index = 1
    next_checkpoint = checkpoint_interval
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_fishway_source_residual = 0.0
    maximum_gate_mass_residual = 0.0
    maximum_gate_face_mass_residual = 0.0
    minimum_effective_q = math.inf
    maximum_effective_q = 0.0
    minimum_capacity = float(np.min(alpha))
    maximum_capacity = float(np.max(alpha))
    maximum_capacity_change_per_step = 0.0
    previous_alpha = alpha.copy()
    tide_clock_start = (
        float(source["contract"]["run"]["tideCurveStartHour"]) * 3600.0
        + float(read_json(short.SOURCE_REPORT)["run"]["simulatedSeconds"])
    )
    wall_start = time.monotonic()

    while elapsed < target_seconds - 1e-12:
        set_capacity_at_time(
            alpha,
            initial_alpha,
            ramping,
            target,
            elapsed,
            duration_sec,
        )
        update_mapping_workspace(workspace, alpha)
        maximum_capacity_change_per_step = max(
            maximum_capacity_change_per_step,
            float(np.max(np.abs(alpha - previous_alpha))),
        )
        previous_alpha[:] = alpha
        minimum_capacity = min(minimum_capacity, float(np.min(alpha)))
        maximum_capacity = max(maximum_capacity, float(np.max(alpha)))
        gate_residual, gate_face_residual = (
            _maximum_gate_mass_residual(
                state,
                bed,
                geometry["left"],
                geometry["right"],
                workspace["effectiveLengths"],
                geometry["internalNormals"],
                workspace["multipliers"],
                workspace["gateFaceIds"],
            )
        )
        maximum_gate_mass_residual = max(
            maximum_gate_mass_residual,
            float(gate_residual),
        )
        maximum_gate_face_mass_residual = max(
            maximum_gate_face_mass_residual,
            float(gate_face_residual),
        )
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
        ) = short._advance_h2_step(
            state,
            bed,
            manning,
            geometry["areas"],
            geometry["inverseAreas"],
            geometry["left"],
            geometry["right"],
            workspace["effectiveLengths"],
            geometry["internalNormals"],
            workspace["multipliers"],
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

        if (
            elapsed >= next_checkpoint - 1e-10
            or elapsed >= target_seconds - 1e-10
        ):
            require(
                next_checkpoint_index < checkpoint_count,
                "too many C1 checkpoints",
            )
            set_capacity_at_time(
                alpha,
                initial_alpha,
                ramping,
                target,
                elapsed,
                duration_sec,
            )
            update_mapping_workspace(workspace, alpha)
            snapshots.append(state.copy())
            checkpoint_times[next_checkpoint_index] = elapsed
            capacity_checkpoints[next_checkpoint_index] = alpha
            flux, mapping_exact = record_checkpoint(
                state,
                bed,
                geometry,
                workspace,
                alpha,
            )
            for name in flux_names:
                flux_checkpoints[name][next_checkpoint_index] = flux[name]
            mapping_exact_count += int(mapping_exact)
            next_checkpoint_index += 1
            next_checkpoint += checkpoint_interval

    require(
        next_checkpoint_index == checkpoint_count,
        "missing C1 checkpoints",
    )
    depth = state[:, 0]
    speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(
        depth,
        1e-12,
    )
    report = {
        "simulatedSeconds": elapsed,
        "stepsCompleted": step,
        "wallSeconds": time.monotonic() - wall_start,
        "checkpointCount": checkpoint_count,
        "checkpointTimesS": checkpoint_times.tolist(),
        "checkpointMappingIdentityCount": mapping_exact_count,
        "checkpointMappingIdentityAllPassed":
            mapping_exact_count == checkpoint_count,
        "gateMassResidualEvaluatedAtEveryStep": True,
        "gateMassResidualEvaluationCount": step,
        "maximumAbsoluteSummedLeftPlusRightGateMassResidualM3S":
            maximum_gate_mass_residual,
        "maximumAbsolutePerFaceLeftPlusRightGateMassResidualM3S":
            maximum_gate_face_mass_residual,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "maximumAbsoluteFishwayMassSourceResidualM3S":
            maximum_fishway_source_residual,
        "minimumEffectiveFishwayDischargeM3S": minimum_effective_q,
        "maximumEffectiveFishwayDischargeM3S": maximum_effective_q,
        "fishwayQ0WasCapped":
            minimum_effective_q < float(case["Q0M3S"]) - 1e-12,
        "minimumCapacityFraction": minimum_capacity,
        "maximumCapacityFraction": maximum_capacity,
        "maximumCapacityChangePerAdaptiveStep":
            maximum_capacity_change_per_step,
        "minimumDepthM": float(depth.min()),
        "maximumDepthM": float(depth.max()),
        "maximumSpeedMPS": float(speed.max()),
        "negativeDepthCount": int(np.sum(depth < 0.0)),
        "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
    }
    fields = {
        "checkpointTimeS": checkpoint_times,
        "capacityFractionByGateId": capacity_checkpoints,
        **{
            f"gateFlux__{name}": values
            for name, values in flux_checkpoints.items()
        },
    }
    return snapshots, report, fields


def comparison_values(
    formal_state: np.ndarray,
    formal_bed: np.ndarray,
    h3b_state: np.ndarray,
    h3b_bed: np.ndarray,
    formal_to_h3b: np.ndarray,
    formal_areas: np.ndarray,
    regions: dict[str, np.ndarray],
) -> tuple[dict[str, dict[str, float]], np.ndarray, np.ndarray]:
    formal_h = formal_state[:, 0]
    formal_u = formal_state[:, 1] / np.maximum(formal_h, 1e-12)
    formal_v = formal_state[:, 2] / np.maximum(formal_h, 1e-12)
    h3b_h = h3b_state[:, 0]
    h3b_u = h3b_state[:, 1] / np.maximum(h3b_h, 1e-12)
    h3b_v = h3b_state[:, 2] / np.maximum(h3b_h, 1e-12)
    mapped = formal_to_h3b
    formal_eta = formal_h + formal_bed
    h3b_eta = h3b_h[mapped] + h3b_bed[mapped]
    eta_error = h3b_eta - formal_eta
    velocity_error = np.hypot(
        h3b_u[mapped] - formal_u,
        h3b_v[mapped] - formal_v,
    )
    result = {}
    for region_id, selected in regions.items():
        result[region_id] = spatial.metrics(
            h3b_eta[selected],
            h3b_u[mapped][selected],
            h3b_v[mapped][selected],
            formal_eta[selected],
            formal_u[selected],
            formal_v[selected],
            formal_areas[selected],
        )
    return result, eta_error, velocity_error


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    approval = read_json(APPROVAL)
    require(
        approval["status"]
        == "approved_bounded_C1_600s_continuous_transition_diagnostic_only",
        "C1 diagnostic is not approved",
    )
    for key, record in approval["bindings"].items():
        path = ROOT / record["path"]
        require(path.is_file(), f"missing approval binding: {key}")
        require(
            sha256(path) == record["sha256"],
            f"approval binding changed: {key}",
        )
    protected_paths = {
        **short.PROTECTED,
        CURRENT_BINARY_INTERFACE: EXPECTED_CURRENT_BINARY_INTERFACE_SHA,
        CURRENT_BINARY_CONTRACT: EXPECTED_CURRENT_BINARY_CONTRACT_SHA,
    }
    protected_before = {}
    for path, expected in protected_paths.items():
        observed = sha256(path)
        require(observed == expected, f"protected input changed: {path}")
        protected_before[str(path.relative_to(ROOT))] = observed

    source, tide_candidate = short.initial_condition_data()
    p2_source = read_json(short.P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_polygons = {
        side: Polygon(
            old.project_many(
                p2_source[side]["footprint"]["coordinates"][0][:-1]
            )
        )
        for side in ("upstream", "downstream")
    }
    mesh_records: dict[str, dict[str, Any]] = {
        "formalR20": {
            "path": FORMAL_MESH,
            "summaryPath": FORMAL_SUMMARY,
        },
        "H3b": {
            "path": H3B_MESH,
            "summaryPath": H3B_SUMMARY,
        },
    }
    for mesh_id, record in mesh_records.items():
        mesh = short.mesh_arrays(record["path"])
        geometry = short.build_review_geometry(mesh)
        summary = read_json(record["summaryPath"])
        initial_state, bed, manning, source_mapping = (
            short.initialize_mesh(
                mesh,
                geometry,
                source,
            )
        )
        record.update(
            {
                "mesh": mesh,
                "geometry": geometry,
                "summary": summary,
                "initialState": initial_state,
                "bed": bed,
                "manning": manning,
                "sourceMapping": source_mapping,
                "P2": short.p2_arrays(
                    geometry,
                    summary,
                    p2_polygons,
                ),
            }
        )

    formal = mesh_records["formalR20"]
    h3b = mesh_records["H3b"]
    h3b_finder = spatial.triangle_finder(
        h3b["geometry"]["vertices"],
        h3b["geometry"]["triangles"],
    )
    formal_centroids = formal["geometry"]["centroids"]
    formal_to_h3b, comparison_mapping = spatial.containing_cells(
        h3b_finder,
        formal_centroids,
        h3b["geometry"]["centroids"],
    )
    cut_features = read_json(short.CUT)["features"]
    cut_line = MultiLineString(
        [
            old.project_many(feature["geometry"]["coordinates"])
            for feature in cut_features
            if feature["geometry"]["type"] == "LineString"
        ]
    )
    barrage_distance = np.asarray(
        [
            cut_line.distance(Point(point))
            for point in formal_centroids
        ],
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
    side_masks, side_mask_records, _ = previous_h3b.side_source_masks(
        len(formal_centroids)
    )
    regions = {
        "fullConfirmedDomain": np.ones(
            len(formal_centroids),
            dtype=bool,
        ),
        "barrageWithin100M": barrage_distance <= 100.0,
        "fishwayP2Footprints": p2_mask,
        "nishikawaConfluenceWithin150M":
            np.linalg.norm(
                formal_centroids - short.NISHIKAWA,
                axis=1,
            )
            <= 150.0,
        "magarigawaConfluenceWithin180M":
            np.linalg.norm(
                formal_centroids - short.MAGARIGAWA,
                axis=1,
            )
            <= 180.0,
        **side_masks,
    }
    require(
        all(np.any(mask) for mask in regions.values()),
        "empty C1 comparison region",
    )
    region_ids = list(regions)
    target_seconds = float(
        approval["authorizedDiagnostic"]["physicalSecondsPerCase"]
    )
    checkpoint_interval = float(
        approval["authorizedDiagnostic"]["checkpointIntervalSec"]
    )
    cfl_target = float(
        approval["authorizedDiagnostic"]["cflTarget"]
    )
    cases = approval["authorizedDiagnostic"]["cases"]
    checkpoint_count = int(round(target_seconds / checkpoint_interval)) + 1
    comparison_eta = np.zeros(
        (len(cases), checkpoint_count, len(region_ids)),
        dtype=np.float64,
    )
    comparison_velocity = np.zeros_like(comparison_eta)
    final_eta_errors = []
    final_velocity_errors = []
    formal_final_states = []
    h3b_final_states = []
    capacity_by_case = np.zeros(
        (len(cases), checkpoint_count, 8),
        dtype=np.float64,
    )
    mesh_flux_fields = {
        mesh_id: {
            name: np.zeros(
                (len(cases), checkpoint_count, 8),
                dtype=np.float64,
            )
            for name in (
                "openLeftM3S",
                "openRightM3S",
                "wallLeftM3S",
                "wallRightM3S",
                "blendedLeftM3S",
                "blendedRightM3S",
                "leftPlusRightResidualM3S",
            )
        }
        for mesh_id in mesh_records
    }
    case_results = []
    all_reports = []
    screening_rows = []
    raw_run_rows: list[dict[str, Any]] = []
    raw_case_rows: list[dict[str, Any]] = []
    write_json(
        RAW_RUN_REPORTS,
        {
            "schema": (
                "onga-stage20-barrage-C1-local-transition-600s-v1-"
                "raw-run-reports"
            ),
            "version": 1,
            "status": "RUNNING",
            "runs": raw_run_rows,
        },
    )
    write_json(
        RAW_CASE_COMPARISONS,
        {
            "schema": (
                "onga-stage20-barrage-C1-local-transition-600s-v1-"
                "raw-case-comparisons"
            ),
            "version": 1,
            "status": "RUNNING",
            "cases": raw_case_rows,
        },
    )
    checkpoint_times_reference: np.ndarray | None = None
    guides = approval["acceptance"]["screeningGuides"]

    for case_index, case in enumerate(cases):
        snapshots_by_mesh: dict[str, list[np.ndarray]] = {}
        reports_by_mesh: dict[str, dict[str, Any]] = {}
        fields_by_mesh: dict[str, dict[str, np.ndarray]] = {}
        for mesh_id, record in mesh_records.items():
            snapshots, report, fields = run_case(
                record["initialState"],
                record["bed"],
                record["manning"],
                record["geometry"],
                record["P2"],
                source,
                tide_candidate,
                case,
                target_seconds=target_seconds,
                checkpoint_interval=checkpoint_interval,
                cfl_target=cfl_target,
            )
            snapshots_by_mesh[mesh_id] = snapshots
            reports_by_mesh[mesh_id] = report
            fields_by_mesh[mesh_id] = fields
            all_reports.append(report)
            raw_run_rows.append(
                {
                    "caseId": case["caseId"],
                    "meshId": mesh_id,
                    "report": report,
                }
            )
            write_json(
                RAW_RUN_REPORTS,
                {
                    "schema": (
                        "onga-stage20-barrage-C1-local-transition-"
                        "600s-v1-raw-run-reports"
                    ),
                    "version": 1,
                    "status": "RUNNING",
                    "runs": raw_run_rows,
                },
            )
            print(
                json.dumps(
                    {
                        "event": "C1_mesh_run_complete",
                        "caseId": case["caseId"],
                        "meshId": mesh_id,
                        "steps": report["stepsCompleted"],
                        "wallSeconds": report["wallSeconds"],
                        "maximumCfl": report["maximumCfl"],
                        "maximumMassError":
                            report["maximumRelativeMassBalanceError"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        formal_times = np.asarray(
            fields_by_mesh["formalR20"]["checkpointTimeS"]
        )
        h3b_times = np.asarray(
            fields_by_mesh["H3b"]["checkpointTimeS"]
        )
        require(
            np.array_equal(formal_times, h3b_times),
            "formal and H3b checkpoint times differ",
        )
        if checkpoint_times_reference is None:
            checkpoint_times_reference = formal_times
        else:
            require(
                np.array_equal(
                    checkpoint_times_reference,
                    formal_times,
                ),
                "C1 case checkpoint times differ",
            )
        require(
            np.array_equal(
                fields_by_mesh["formalR20"][
                    "capacityFractionByGateId"
                ],
                fields_by_mesh["H3b"][
                    "capacityFractionByGateId"
                ],
            ),
            "C1 mesh capacity schedules differ",
        )
        capacity_by_case[case_index] = fields_by_mesh["formalR20"][
            "capacityFractionByGateId"
        ]
        for mesh_id in mesh_records:
            for name in mesh_flux_fields[mesh_id]:
                mesh_flux_fields[mesh_id][name][case_index] = (
                    fields_by_mesh[mesh_id][f"gateFlux__{name}"]
                )

        final_eta = None
        final_velocity = None
        worst_eta = None
        worst_velocity = None
        for checkpoint_index, checkpoint_time in enumerate(formal_times):
            measured, eta_error, velocity_error = comparison_values(
                snapshots_by_mesh["formalR20"][checkpoint_index],
                formal["bed"],
                snapshots_by_mesh["H3b"][checkpoint_index],
                h3b["bed"],
                formal_to_h3b,
                formal["geometry"]["areas"],
                regions,
            )
            for region_index, region_id in enumerate(region_ids):
                row = measured[region_id]
                eta_value = float(
                    row["waterSurfaceElevationRmseM"]
                )
                velocity_value = float(
                    row["velocityVectorRmseMPS"]
                )
                comparison_eta[
                    case_index,
                    checkpoint_index,
                    region_index,
                ] = eta_value
                comparison_velocity[
                    case_index,
                    checkpoint_index,
                    region_index,
                ] = velocity_value
                screen = {
                    "caseId": case["caseId"],
                    "timeS": float(checkpoint_time),
                    "regionId": region_id,
                    "waterSurfaceElevationRmseM": eta_value,
                    "velocityVectorRmseMPS": velocity_value,
                    "waterSurfacePassed":
                        eta_value
                        <= float(guides["waterSurfaceElevationRmseM"]),
                    "velocityPassed":
                        velocity_value
                        <= float(guides["velocityVectorRmseMPS"]),
                }
                screening_rows.append(screen)
                if (
                    worst_eta is None
                    or eta_value
                    > worst_eta["waterSurfaceElevationRmseM"]
                ):
                    worst_eta = screen
                if (
                    worst_velocity is None
                    or velocity_value
                    > worst_velocity["velocityVectorRmseMPS"]
                ):
                    worst_velocity = screen
            if checkpoint_index == len(formal_times) - 1:
                final_eta = eta_error
                final_velocity = velocity_error
        require(
            final_eta is not None
            and final_velocity is not None
            and worst_eta is not None
            and worst_velocity is not None,
            "missing C1 comparison fields",
        )
        final_eta_errors.append(final_eta.astype(np.float32))
        final_velocity_errors.append(final_velocity.astype(np.float32))
        formal_final_states.append(
            snapshots_by_mesh["formalR20"][-1].astype(np.float32)
        )
        h3b_final_states.append(
            snapshots_by_mesh["H3b"][-1].astype(np.float32)
        )
        case_screen_rows = [
            row
            for row in screening_rows
            if row["caseId"] == case["caseId"]
        ]
        case_results.append(
            {
                "caseId": case["caseId"],
                "classification": case["classification"],
                "rampingGateIds": case["rampingGateIds"],
                "initialCapacityFractionByGateId":
                    case["initialCapacityFractionByGateId"],
                "Q0M3S": case["Q0M3S"],
                "meshRuns": reports_by_mesh,
                "capacityAtKeyTimes": {
                    str(int(time_value)): capacity_by_case[
                        case_index,
                        int(round(time_value / checkpoint_interval)),
                    ].tolist()
                    for time_value in (0.0, 150.0, 300.0, 600.0)
                },
                "screening": {
                    "comparisonCount": len(case_screen_rows),
                    "passedCount": sum(
                        row["waterSurfacePassed"]
                        and row["velocityPassed"]
                        for row in case_screen_rows
                    ),
                    "allPassed": all(
                        row["waterSurfacePassed"]
                        and row["velocityPassed"]
                        for row in case_screen_rows
                    ),
                    "worstWaterSurfaceElevationRmse": worst_eta,
                    "worstVelocityVectorRmse": worst_velocity,
                },
            }
        )
        raw_case_rows.append(case_results[-1])
        write_json(
            RAW_CASE_COMPARISONS,
            {
                "schema": (
                    "onga-stage20-barrage-C1-local-transition-600s-v1-"
                    "raw-case-comparisons"
                ),
                "version": 1,
                "status": "RUNNING",
                "cases": raw_case_rows,
            },
        )
        print(
            json.dumps(
                {
                    "event": "C1_case_comparison_complete",
                    "caseId": case["caseId"],
                    "screeningPassed":
                        case_results[-1]["screening"]["allPassed"],
                    "worstEtaRmseM":
                        worst_eta["waterSurfaceElevationRmseM"],
                    "worstVelocityRmseMPS":
                        worst_velocity["velocityVectorRmseMPS"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    require(
        checkpoint_times_reference is not None,
        "no C1 checkpoints",
    )
    fields: dict[str, np.ndarray] = {
        "case_ids": np.asarray(
            [case["caseId"] for case in cases],
            dtype="U64",
        ),
        "gate_ids": np.asarray(mapping.GATE_IDS, dtype=np.int16),
        "region_ids": np.asarray(region_ids, dtype="U64"),
        "checkpoint_time_s": checkpoint_times_reference,
        "capacity_fraction_by_case_checkpoint_gate":
            capacity_by_case,
        "formal_vs_H3b_water_surface_elevation_rmse_m":
            comparison_eta,
        "formal_vs_H3b_velocity_vector_rmse_mps":
            comparison_velocity,
        "formal_R20_final_state_by_case":
            np.stack(formal_final_states),
        "H3b_final_state_by_case":
            np.stack(h3b_final_states),
        "final_water_surface_elevation_error_m":
            np.stack(final_eta_errors),
        "final_velocity_vector_error_mps":
            np.stack(final_velocity_errors),
        "formal_R20_centroids_m":
            formal_centroids.astype(np.float64),
        "formal_R20_cell_area_m2":
            formal["geometry"]["areas"].astype(np.float64),
        "formal_to_H3b_cell_id":
            formal_to_h3b.astype(np.int64),
    }
    for mesh_id in mesh_records:
        for name, values in mesh_flux_fields[mesh_id].items():
            fields[
                f"{mesh_id}__gate_flux__{name}"
            ] = values
    for region_id, mask in regions.items():
        fields[f"region_mask__{region_id}"] = mask.astype(np.uint8)
    np.savez_compressed(FIELDS, **fields)

    acceptance = approval["acceptance"]
    maximum_cfl = max(report["maximumCfl"] for report in all_reports)
    maximum_mass_error = max(
        report["maximumRelativeMassBalanceError"]
        for report in all_reports
    )
    maximum_fishway_residual = max(
        report["maximumAbsoluteFishwayMassSourceResidualM3S"]
        for report in all_reports
    )
    maximum_gate_residual = max(
        report[
            "maximumAbsoluteSummedLeftPlusRightGateMassResidualM3S"
        ]
        for report in all_reports
    )
    maximum_gate_face_residual = max(
        report[
            "maximumAbsolutePerFaceLeftPlusRightGateMassResidualM3S"
        ]
        for report in all_reports
    )
    negative_count = sum(
        report["negativeDepthCount"] for report in all_reports
    )
    nonfinite_count = sum(
        report["nonFiniteValueCount"] for report in all_reports
    )
    all_screening_pass = all(
        row["waterSurfacePassed"] and row["velocityPassed"]
        for row in screening_rows
    )
    worst_eta = max(
        screening_rows,
        key=lambda row: row["waterSurfaceElevationRmseM"],
    )
    worst_velocity = max(
        screening_rows,
        key=lambda row: row["velocityVectorRmseMPS"],
    )
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, observed: Any) -> None:
        checks.append(
            {"id": check_id, "passed": bool(passed), "observed": observed}
        )

    check(
        "approved_C1_scope_is_exactly_two_meshes_three_cases_six_runs",
        len(mesh_records) == 2
        and len(cases) == 3
        and len(all_reports) == 6,
        {
            "meshCount": len(mesh_records),
            "caseCount": len(cases),
            "runCount": len(all_reports),
        },
    )
    check(
        "all_runs_reached_exactly_600_physical_seconds",
        all(
            report["simulatedSeconds"] == target_seconds
            for report in all_reports
        ),
        [report["simulatedSeconds"] for report in all_reports],
    )
    check(
        "all_runs_recorded_61_required_checkpoints",
        all(
            report["checkpointCount"]
            == int(acceptance["checkpointCountIncludingZero"])
            for report in all_reports
        )
        and np.array_equal(
            checkpoint_times_reference,
            np.arange(0.0, 601.0, 10.0),
        ),
        checkpoint_times_reference.tolist(),
    )
    check(
        "continuous_mapping_matches_approved_adapter_at_every_checkpoint",
        all(
            report["checkpointMappingIdentityAllPassed"]
            for report in all_reports
        ),
        [
            report["checkpointMappingIdentityCount"]
            for report in all_reports
        ],
    )
    check(
        "gate_mass_residual_was_evaluated_at_every_adaptive_step",
        all(
            report["gateMassResidualEvaluatedAtEveryStep"]
            and report["gateMassResidualEvaluationCount"]
            == report["stepsCompleted"]
            for report in all_reports
        ),
        [
            {
                "steps": report["stepsCompleted"],
                "evaluations":
                    report["gateMassResidualEvaluationCount"],
            }
            for report in all_reports
        ],
    )
    check(
        "left_plus_right_gate_mass_residual_within_limit",
        max(maximum_gate_residual, maximum_gate_face_residual)
        <= float(
            acceptance[
                "maximumAbsoluteLeftPlusRightGateMassResidualM3S"
            ]
        ),
        {
            "summed": maximum_gate_residual,
            "perFace": maximum_gate_face_residual,
        },
    )
    check(
        "capacity_fractions_are_finite_and_within_zero_one",
        np.isfinite(capacity_by_case).all()
        and np.all(
            capacity_by_case
            >= float(acceptance["capacityFractionMinimum"])
        )
        and np.all(
            capacity_by_case
            <= float(acceptance["capacityFractionMaximum"])
        ),
        {
            "minimum": float(np.min(capacity_by_case)),
            "maximum": float(np.max(capacity_by_case)),
        },
    )
    schedule_pass = True
    schedule_rows = []
    for case_index, case in enumerate(cases):
        initial, ramping = case_arrays(case)
        expected_150 = initial.copy()
        expected_300 = initial.copy()
        for gate_index in ramping:
            expected_150[gate_index] = (
                initial[gate_index]
                + (float(case["targetCapacityFraction"])
                   - initial[gate_index])
                * 0.5
            )
            expected_300[gate_index] = float(
                case["targetCapacityFraction"]
            )
        observed = capacity_by_case[case_index]
        passed = bool(
            np.array_equal(observed[0], initial)
            and np.allclose(
                observed[15],
                expected_150,
                atol=1e-15,
                rtol=0.0,
            )
            and np.array_equal(observed[30], expected_300)
            and np.array_equal(observed[60], expected_300)
            and np.all(np.diff(observed[:, ramping], axis=0) >= -1e-15)
        )
        schedule_pass = schedule_pass and passed
        schedule_rows.append(
            {"caseId": case["caseId"], "passed": passed}
        )
    check(
        "all_three_capacity_schedules_match_approved_smoothstep_endpoints",
        schedule_pass,
        schedule_rows,
    )
    check(
        "maximum_CFL_within_limit",
        maximum_cfl <= float(acceptance["maximumCfl"]),
        maximum_cfl,
    )
    check(
        "relative_mass_balance_error_within_limit",
        maximum_mass_error
        <= float(acceptance["maximumRelativeMassBalanceError"]),
        maximum_mass_error,
    )
    check(
        "fishway_P2_conservation_residual_within_limit",
        maximum_fishway_residual
        <= float(
            acceptance[
                "maximumAbsoluteFishwayMassSourceResidualM3S"
            ]
        ),
        maximum_fishway_residual,
    )
    check(
        "fishway_P2_remained_active_in_all_runs",
        all(
            report["minimumEffectiveFishwayDischargeM3S"] > 0.0
            for report in all_reports
        ),
        [
            report["minimumEffectiveFishwayDischargeM3S"]
            for report in all_reports
        ],
    )
    check(
        "no_negative_depths",
        negative_count == int(acceptance["negativeDepthCount"]),
        negative_count,
    )
    check(
        "no_nonfinite_values",
        nonfinite_count == int(acceptance["nonFiniteValueCount"]),
        nonfinite_count,
    )
    check(
        "formal_R20_vs_H3b_screening_guides_pass_at_all_checkpoints",
        all_screening_pass,
        {
            "passed": sum(
                row["waterSurfacePassed"]
                and row["velocityPassed"]
                for row in screening_rows
            ),
            "total": len(screening_rows),
            "worstWaterSurfaceElevationRmse": worst_eta,
            "worstVelocityVectorRmse": worst_velocity,
        },
    )
    protected_after = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in protected_paths
    }
    check(
        "protected_v2_public_and_response_inputs_unchanged",
        protected_after == protected_before,
        protected_after,
    )
    failed = [row for row in checks if not row["passed"]]
    validation = {
        "schema": (
            "onga-stage20-barrage-C1-local-transition-600s-v1-"
            "static-validation"
        ),
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "checks": checks,
    }
    write_json(VALIDATION, validation)
    write_json(
        RAW_RUN_REPORTS,
        {
            "schema": (
                "onga-stage20-barrage-C1-local-transition-600s-v1-"
                "raw-run-reports"
            ),
            "version": 1,
            "status": "COMPLETE",
            "runs": raw_run_rows,
        },
    )
    write_json(
        RAW_CASE_COMPARISONS,
        {
            "schema": (
                "onga-stage20-barrage-C1-local-transition-600s-v1-"
                "raw-case-comparisons"
            ),
            "version": 1,
            "status": "COMPLETE",
            "cases": raw_case_rows,
        },
    )
    numerical_safety_pass = all(
        row["passed"]
        for row in checks
        if row["id"]
        in {
            "left_plus_right_gate_mass_residual_within_limit",
            "maximum_CFL_within_limit",
            "relative_mass_balance_error_within_limit",
            "fishway_P2_conservation_residual_within_limit",
            "fishway_P2_remained_active_in_all_runs",
            "no_negative_depths",
            "no_nonfinite_values",
        }
    )
    if not numerical_safety_pass:
        overall_status = "C1_NUMERICAL_SAFETY_FAIL_C2_BLOCKED"
    elif not all_screening_pass:
        overall_status = "C1_NUMERICALLY_SAFE_MESH_SCREENING_FAIL_C2_BLOCKED"
    elif failed:
        overall_status = "C1_CONTRACT_CHECK_FAIL_C2_BLOCKED"
    else:
        overall_status = (
            "C1_PASS_COMPLETE_PENDING_USER_JUDGMENT_BEFORE_C2"
        )
    summary = {
        "schema": "onga-stage20-barrage-C1-local-transition-600s-v1",
        "version": 1,
        "status": overall_status,
        "scope": {
            "stageId": "C1_local_transition_600s",
            "meshCount": 2,
            "caseCount": 3,
            "meshRunCount": 6,
            "physicalSecondsPerRun": target_seconds,
            "checkpointIntervalSec": checkpoint_interval,
            "C2C3RunStarted": False,
            "physicalValidationClaimAllowed": False,
            "productionMeshAdoptionAuthorized": False,
        },
        "mapping": {
            "id": "classified_face_capacity_multiplier",
            "effectiveHydraulicWidthMPerGate": 46.5,
            "capacityMeaning":
                "dimensionless model capacity multiplier, not gate lift",
            "checkpointAdapterIdentity":
                f"{sum(report['checkpointMappingIdentityCount'] for report in all_reports)}/"
                f"{sum(report['checkpointCount'] for report in all_reports)}",
        },
        "mesh": {
            "formalR20": {
                "cellCount": int(
                    len(formal["geometry"]["triangles"])
                ),
                "mesh": binding(FORMAL_MESH),
                "summary": binding(FORMAL_SUMMARY),
            },
            "H3b": {
                "cellCount": int(
                    len(h3b["geometry"]["triangles"])
                ),
                "mesh": binding(H3B_MESH),
                "summary": binding(H3B_SUMMARY),
            },
            "formalToH3b": comparison_mapping,
            "formerH3SidePatchMasks": side_mask_records,
        },
        "cases": case_results,
        "aggregate": {
            "runCount": len(all_reports),
            "totalAdaptiveSteps": sum(
                report["stepsCompleted"] for report in all_reports
            ),
            "totalWallSeconds": sum(
                report["wallSeconds"] for report in all_reports
            ),
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error,
            "maximumAbsoluteSummedLeftPlusRightGateMassResidualM3S":
                maximum_gate_residual,
            "maximumAbsolutePerFaceLeftPlusRightGateMassResidualM3S":
                maximum_gate_face_residual,
            "maximumAbsoluteFishwayMassSourceResidualM3S":
                maximum_fishway_residual,
            "negativeDepthCount": negative_count,
            "nonFiniteValueCount": nonfinite_count,
            "screeningComparisonCount": len(screening_rows),
            "screeningPassedCount": sum(
                row["waterSurfacePassed"]
                and row["velocityPassed"]
                for row in screening_rows
            ),
            "screeningAllPassed": all_screening_pass,
            "worstWaterSurfaceElevationRmse": worst_eta,
            "worstVelocityVectorRmse": worst_velocity,
            "validationStatus": validation["status"],
        },
        "bindings": {
            "approval": binding(APPROVAL),
            "continuousMappingAdapter": binding(
                ROOT
                / approval["bindings"]["continuousMappingAdapter"]["path"]
            ),
            "fields": binding(FIELDS),
            "staticValidation": binding(VALIDATION),
            "rawRunReports": binding(RAW_RUN_REPORTS),
            "rawCaseComparisons": binding(RAW_CASE_COMPARISONS),
        },
        "safeguards": {
            "protectedBefore": protected_before,
            "protectedAfter": protected_after,
            "protectedInputsUnchanged":
                protected_before == protected_after,
            "protectedBinaryV2Modified": False,
            "guiChanged": False,
            "productionMeshAdopted": False,
            "precomputationRun": False,
            "responsePackChanged": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
            "C2C3RunStarted": False,
        },
        "nextDecision": (
            "review the C1 result figure before any C2 authorization"
        ),
    }
    write_json(SUMMARY, summary)
    manifest = {
        "schema": (
            "onga-stage20-barrage-C1-local-transition-600s-v1-"
            "manifest"
        ),
        "version": 1,
        "status": validation["status"],
        "outputs": {
            "summary": binding(SUMMARY),
            "staticValidation": binding(VALIDATION),
            "fields": binding(FIELDS),
            "rawRunReports": binding(RAW_RUN_REPORTS),
            "rawCaseComparisons": binding(RAW_CASE_COMPARISONS),
        },
        "protectedInputsUnchanged": protected_before == protected_after,
    }
    write_json(MANIFEST, manifest)
    print(
        json.dumps(
            {
                "event": "C1_diagnostic_complete",
                "status": overall_status,
                "validation": validation["status"],
                "checks": (
                    f"{validation['passedCount']}/"
                    f"{validation['checkCount']}"
                ),
                "screening": (
                    f"{sum(row['waterSurfacePassed'] and row['velocityPassed'] for row in screening_rows)}/"
                    f"{len(screening_rows)}"
                ),
                "maximumCfl": maximum_cfl,
                "maximumMassError": maximum_mass_error,
                "summary": str(SUMMARY.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    if failed:
        raise RuntimeError(
            "C1 diagnostic failed: "
            + ", ".join(row["id"] for row in failed)
        )


if __name__ == "__main__":
    main()
