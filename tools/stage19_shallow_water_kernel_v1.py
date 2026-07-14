#!/usr/bin/env python3
"""Well-balanced provisional Stage 19 shallow-water kernel.

Production execution remains disabled by configuration. Synthetic fixtures may
exercise this module; a production-mesh case requires a separate authorization.
"""

from __future__ import annotations

import math

import numpy as np

from stage19_solver_inputs import GRAVITY_M_S2, fishway_discharge_m3s, tide_anomaly_m


class NumericalStop(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def build_solver_geometry(package: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    vertices = package["vertex_local_mm"].astype(np.float64) * 1e-3
    triangles = package["triangles"].astype(np.int64)
    points = vertices[triangles]
    centroids = points.mean(axis=1)
    areas = np.abs(
        (points[:, 1, 0] - points[:, 0, 0]) * (points[:, 2, 1] - points[:, 0, 1])
        - (points[:, 1, 1] - points[:, 0, 1]) * (points[:, 2, 0] - points[:, 0, 0])
    ) / 2.0
    require(np.isfinite(areas).all() and np.all(areas > 0), "invalid cell areas")

    internal_vertices = package["internal_face_vertices"].astype(np.int64)
    internal_cells = package["internal_face_cells"].astype(np.int64)
    left = internal_cells[:, 0]
    right = internal_cells[:, 1]
    vectors = vertices[internal_vertices[:, 1]] - vertices[internal_vertices[:, 0]]
    internal_lengths = np.linalg.norm(vectors, axis=1)
    internal_normals = np.column_stack((vectors[:, 1], -vectors[:, 0]))
    internal_normals /= internal_lengths[:, None]
    reverse = np.einsum("ij,ij->i", internal_normals, centroids[right] - centroids[left]) < 0
    internal_normals[reverse] *= -1

    boundary_vertices = package["boundary_face_vertices"].astype(np.int64)
    boundary_cells = package["boundary_face_cell"].astype(np.int64)
    vectors = vertices[boundary_vertices[:, 1]] - vertices[boundary_vertices[:, 0]]
    boundary_lengths = np.linalg.norm(vectors, axis=1)
    boundary_normals = np.column_stack((vectors[:, 1], -vectors[:, 0]))
    boundary_normals /= boundary_lengths[:, None]
    midpoints = (vertices[boundary_vertices[:, 0]] + vertices[boundary_vertices[:, 1]]) / 2.0
    reverse = np.einsum(
        "ij,ij->i", boundary_normals, midpoints - centroids[boundary_cells]
    ) < 0
    boundary_normals[reverse] *= -1
    return {
        "centroids": centroids,
        "areas": areas,
        "left": left,
        "right": right,
        "internalLengths": internal_lengths,
        "internalNormals": internal_normals,
        "boundaryCells": boundary_cells,
        "boundaryLengths": boundary_lengths,
        "boundaryNormals": boundary_normals,
        "boundaryTags": package["boundary_face_tag"].astype(np.uint8),
    }


def _physical_flux(state: np.ndarray, normals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    depth = np.maximum(state[:, 0], 1e-12)
    normal_velocity = (state[:, 1] * normals[:, 0] + state[:, 2] * normals[:, 1]) / depth
    pressure = 0.5 * GRAVITY_M_S2 * depth * depth
    flux = np.column_stack((
        state[:, 1] * normals[:, 0] + state[:, 2] * normals[:, 1],
        state[:, 1] * normal_velocity + pressure * normals[:, 0],
        state[:, 2] * normal_velocity + pressure * normals[:, 1],
    ))
    return flux, normal_velocity


def _rusanov(
    left_state: np.ndarray, right_state: np.ndarray, normals: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    left_flux, left_velocity = _physical_flux(left_state, normals)
    right_flux, right_velocity = _physical_flux(right_state, normals)
    speed = np.maximum(
        np.abs(left_velocity) + np.sqrt(GRAVITY_M_S2 * np.maximum(left_state[:, 0], 0)),
        np.abs(right_velocity) + np.sqrt(GRAVITY_M_S2 * np.maximum(right_state[:, 0], 0)),
    )
    flux = 0.5 * (left_flux + right_flux) - 0.5 * speed[:, None] * (right_state - left_state)
    return flux, speed


def _reflected(state: np.ndarray, normals: np.ndarray) -> np.ndarray:
    result = state.copy()
    normal_momentum = state[:, 1] * normals[:, 0] + state[:, 2] * normals[:, 1]
    result[:, 1] -= 2.0 * normal_momentum * normals[:, 0]
    result[:, 2] -= 2.0 * normal_momentum * normals[:, 1]
    return result


def _hydrostatic_internal_terms(
    state: np.ndarray,
    bed: np.ndarray,
    geometry: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    left = geometry["left"]
    right = geometry["right"]
    normals = geometry["internalNormals"]
    left_state = state[left]
    right_state = state[right]
    eta_left = left_state[:, 0] + bed[left]
    eta_right = right_state[:, 0] + bed[right]
    bed_star = np.maximum(bed[left], bed[right])
    h_left = np.maximum(eta_left - bed_star, 0.0)
    h_right = np.maximum(eta_right - bed_star, 0.0)
    reconstructed_left = left_state.copy()
    reconstructed_right = right_state.copy()
    velocity_left = np.divide(
        left_state[:, 1:], left_state[:, :1], out=np.zeros_like(left_state[:, 1:]),
        where=left_state[:, :1] > 1e-12,
    )
    velocity_right = np.divide(
        right_state[:, 1:], right_state[:, :1], out=np.zeros_like(right_state[:, 1:]),
        where=right_state[:, :1] > 1e-12,
    )
    reconstructed_left[:, 0] = h_left
    reconstructed_left[:, 1:] = h_left[:, None] * velocity_left
    reconstructed_right[:, 0] = h_right
    reconstructed_right[:, 1:] = h_right[:, None] * velocity_right
    common_flux, speed = _rusanov(reconstructed_left, reconstructed_right, normals)
    left_correction = np.zeros_like(common_flux)
    right_correction = np.zeros_like(common_flux)
    left_pressure = 0.5 * GRAVITY_M_S2 * (left_state[:, 0] ** 2 - h_left ** 2)
    right_pressure = 0.5 * GRAVITY_M_S2 * (right_state[:, 0] ** 2 - h_right ** 2)
    left_correction[:, 1:] = left_pressure[:, None] * normals
    right_correction[:, 1:] = right_pressure[:, None] * normals
    return common_flux + left_correction, -common_flux - right_correction, speed


def _wall_flux(state: np.ndarray, normals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return _rusanov(state, _reflected(state, normals), normals)


def _boundary_ghosts(
    state: np.ndarray,
    simulated_seconds: float,
    fields: dict,
    geometry: dict,
    candidate: dict,
) -> tuple[np.ndarray, np.ndarray]:
    cells = geometry["boundaryCells"]
    tags = geometry["boundaryTags"]
    normals = geometry["boundaryNormals"]
    lengths = geometry["boundaryLengths"]
    interior = state[cells]
    ghost = interior.copy()
    open_mask = tags > 0
    shoreline = tags == 0
    ghost[shoreline] = _reflected(interior[shoreline], normals[shoreline])

    m_mask = tags == 1
    if np.any(m_mask):
        eta_target = tide_anomaly_m(simulated_seconds, fields["tide"], candidate)
        target_depth = np.maximum(eta_target - fields["bedElevationM"][cells[m_mask]], 0.05)
        velocity = np.divide(
            interior[m_mask, 1:], interior[m_mask, :1],
            out=np.zeros_like(interior[m_mask, 1:]), where=interior[m_mask, :1] > 1e-12,
        )
        ghost[m_mask, 0] = target_depth
        ghost[m_mask, 1:] = target_depth[:, None] * velocity

    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        mask = tags == tag
        if not np.any(mask):
            continue
        discharge = float(fields["boundaryDischargeM3S"][boundary_id])
        target_flux = -discharge / float(lengths[mask].sum())
        depth = np.maximum(interior[mask, 0], 0.05)
        velocity = interior[mask, 1:] / depth[:, None]
        normal_velocity = np.einsum("ij,ij->i", velocity, normals[mask])
        tangential_velocity = velocity - normal_velocity[:, None] * normals[mask]
        ghost_normal_velocity = 2.0 * target_flux / depth - normal_velocity
        ghost_velocity = tangential_velocity + ghost_normal_velocity[:, None] * normals[mask]
        ghost[mask, 0] = depth
        ghost[mask, 1:] = depth[:, None] * ghost_velocity
    require(np.isfinite(ghost[open_mask]).all(), "invalid open-boundary ghost state")
    return ghost, open_mask


def flux_residual(
    state: np.ndarray,
    simulated_seconds: float,
    fields: dict,
    geometry: dict,
    package: dict,
    candidate: dict,
) -> tuple[np.ndarray, np.ndarray, float]:
    cell_count = len(geometry["areas"])
    residual = np.zeros((cell_count, 3), dtype=np.float64)
    denominator = np.zeros(cell_count, dtype=np.float64)
    left = geometry["left"]
    right = geometry["right"]
    lengths = geometry["internalLengths"]
    left_term, right_term, speed = _hydrostatic_internal_terms(
        state, fields["bedElevationM"], geometry
    )

    barrage_ids = package["barrage_face_ids"].astype(np.int64)
    if len(barrage_ids):
        transmissivity = float(fields["barrageTransmissivity"])
        normals = geometry["internalNormals"][barrage_ids]
        left_wall, left_wall_speed = _wall_flux(state[left[barrage_ids]], normals)
        right_wall, right_wall_speed = _wall_flux(state[right[barrage_ids]], -normals)
        left_term[barrage_ids] = (
            transmissivity * left_term[barrage_ids]
            + (1.0 - transmissivity) * left_wall
        )
        right_term[barrage_ids] = (
            transmissivity * right_term[barrage_ids]
            + (1.0 - transmissivity) * right_wall
        )
        speed[barrage_ids] = np.maximum(
            speed[barrage_ids], np.maximum(left_wall_speed, right_wall_speed)
        )

    np.add.at(residual, left, left_term * lengths[:, None])
    np.add.at(residual, right, right_term * lengths[:, None])
    np.add.at(denominator, left, speed * lengths)
    np.add.at(denominator, right, speed * lengths)

    boundary_cells = geometry["boundaryCells"]
    boundary_lengths = geometry["boundaryLengths"]
    boundary_normals = geometry["boundaryNormals"]
    ghost, _ = _boundary_ghosts(state, simulated_seconds, fields, geometry, candidate)
    boundary_flux, boundary_speed = _rusanov(
        state[boundary_cells], ghost, boundary_normals
    )
    np.add.at(residual, boundary_cells, boundary_flux * boundary_lengths[:, None])
    np.add.at(denominator, boundary_cells, boundary_speed * boundary_lengths)
    net_boundary_outflow = float(np.sum(boundary_flux[:, 0] * boundary_lengths))
    return residual, denominator, net_boundary_outflow


def advance_one_step(
    state: np.ndarray,
    simulated_seconds: float,
    fields: dict,
    geometry: dict,
    package: dict,
    candidate: dict,
    *,
    cfl_target: float = 0.12,
) -> tuple[np.ndarray, float, dict]:
    residual, denominator, boundary_outflow = flux_residual(
        state, simulated_seconds, fields, geometry, package, candidate
    )
    areas = geometry["areas"]
    time_step = cfl_target * float(np.min(areas / np.maximum(denominator, 1e-30)))
    if not math.isfinite(time_step) or time_step <= 0:
        raise NumericalStop("invalid adaptive time step")
    local_cfl = time_step * denominator / areas
    integrated_rhs = -residual

    raw_fishway = fishway_discharge_m3s(state, fields, package)
    fishway_cells = package["fishway_cells"].astype(np.int64)
    fishway_discharge = raw_fishway
    if raw_fishway != 0:
        donor_index = 0 if raw_fishway > 0 else 1
        receiver_index = 1 - donor_index
        donor = int(fishway_cells[donor_index])
        receiver = int(fishway_cells[receiver_index])
        maximum = 0.02 * max(state[donor, 0] - 0.05, 0.0) * areas[donor] / time_step
        magnitude = min(abs(raw_fishway), maximum)
        fishway_discharge = math.copysign(magnitude, raw_fishway)
        donor_velocity = state[donor, 1:] / max(state[donor, 0], 1e-12)
        signed = abs(fishway_discharge)
        integrated_rhs[donor, 0] -= signed
        integrated_rhs[receiver, 0] += signed
        integrated_rhs[donor, 1:] -= signed * donor_velocity
        integrated_rhs[receiver, 1:] += signed * donor_velocity

    next_state = state + time_step * integrated_rhs / areas[:, None]
    depth = np.maximum(next_state[:, 0], 1e-8)
    velocity = np.hypot(next_state[:, 1], next_state[:, 2]) / depth
    manning = fields["manningN"]
    damping = (
        1.0
        + time_step
        * GRAVITY_M_S2
        * manning
        * manning
        * velocity
        / np.power(depth, 4.0 / 3.0)
    )
    next_state[:, 1] /= damping
    next_state[:, 2] /= damping
    if not np.isfinite(next_state).all() or np.any(next_state[:, 0] < 0):
        raise NumericalStop("nonfinite or negative-depth state")
    return next_state, time_step, {
        "maxCfl": float(local_cfl.max()),
        "boundaryOutflowM3S": boundary_outflow,
        "fishwayDischargeM3S": fishway_discharge,
    }


def run_case(
    case: dict,
    fields: dict,
    geometry: dict,
    package: dict,
    candidate: dict,
    *,
    steps: int,
    include_fields: bool = True,
) -> dict:
    require(steps == 500, "Stage 19 production cases require exactly 500 steps")
    state = np.zeros((len(geometry["areas"]), 3), dtype=np.float64)
    state[:, 0] = fields["initialWaterDepthM"]
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    simulated_seconds = 0.0
    max_cfl = 0.0
    maximum_mass_error = 0.0
    for _ in range(steps):
        state, dt, diagnostics = advance_one_step(
            state, simulated_seconds, fields, geometry, package, candidate
        )
        expected_volume -= dt * diagnostics["boundaryOutflowM3S"]
        actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
        if mass_error > 1e-8:
            raise NumericalStop(f"mass-balance error {mass_error} exceeds 1e-8")
        simulated_seconds += dt
        max_cfl = max(max_cfl, diagnostics["maxCfl"])
        maximum_mass_error = max(maximum_mass_error, mass_error)
    result = {
        "stepsCompleted": steps,
        "simulatedTimeSeconds": simulated_seconds,
        "maxCfl": max_cfl,
        "maxAbsoluteMassBalanceError": maximum_mass_error,
        "nanCount": int(state.size - np.isfinite(state).sum()),
        "negativeDepthCount": int(np.sum(state[:, 0] < 0)),
        "minimumDepthM": float(state[:, 0].min()),
    }
    if include_fields:
        depth = state[:, 0].copy()
        result["waterDepthM"] = depth
        result["velocityUms"] = np.divide(
            state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12
        )
        result["velocityVms"] = np.divide(
            state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12
        )
    return result
