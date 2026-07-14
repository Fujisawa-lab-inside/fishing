#!/usr/bin/env python3
"""Independent shallow-water kernel for the corrected Stage 18 v2 mesh.

This module is imported only after the v2 execution contract, gate, authorization,
and all numerical inputs have passed the runner's fail-closed preflight.
"""

import math

import numpy as np


GRAVITY_M_S2 = 9.80665


class NumericalStop(RuntimeError):
    """A numerical threshold that requires the entire ensemble to stop."""

    def __init__(
        self,
        message,
        *,
        nan_count=0,
        negative_depth_count=0,
        max_cfl=None,
        mass_balance_error=None,
        step=None,
    ):
        super().__init__(message)
        self.nan_count = int(nan_count)
        self.negative_depth_count = int(negative_depth_count)
        self.max_cfl = max_cfl
        self.mass_balance_error = mass_balance_error
        self.step = step


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def build_geometry(package):
    """Build metric finite-volume geometry from an already verified NPZ package."""
    vertices = package['vertex_local_mm'].astype(np.float64) * 1e-3
    triangles = package['triangles'].astype(np.int64)
    _require(vertices.ndim == 2 and vertices.shape[1] == 2, 'vertex array shape is invalid')
    _require(triangles.ndim == 2 and triangles.shape[1] == 3, 'triangle array shape is invalid')

    points = vertices[triangles]
    centroids = points.mean(axis=1)
    areas = np.abs(
        (points[:, 1, 0] - points[:, 0, 0]) * (points[:, 2, 1] - points[:, 0, 1])
        - (points[:, 1, 1] - points[:, 0, 1]) * (points[:, 2, 0] - points[:, 0, 0])
    ) / 2.0
    _require(np.isfinite(areas).all() and np.all(areas > 0), 'mesh contains invalid cell areas')

    internal_face_vertices = package['internal_face_vertices'].astype(np.int64)
    internal_face_cells = package['internal_face_cells'].astype(np.int64)
    left = internal_face_cells[:, 0]
    right = internal_face_cells[:, 1]
    internal_vectors = vertices[internal_face_vertices[:, 1]] - vertices[internal_face_vertices[:, 0]]
    internal_lengths = np.linalg.norm(internal_vectors, axis=1)
    _require(
        np.isfinite(internal_lengths).all() and np.all(internal_lengths > 0),
        'mesh contains invalid internal-face lengths',
    )
    internal_normals = np.column_stack((internal_vectors[:, 1], -internal_vectors[:, 0]))
    internal_normals /= internal_lengths[:, None]
    reverse_internal = np.einsum(
        'ij,ij->i', internal_normals, centroids[right] - centroids[left]
    ) < 0
    internal_normals[reverse_internal] *= -1

    boundary_face_vertices = package['boundary_face_vertices'].astype(np.int64)
    boundary_cells = package['boundary_face_cell'].astype(np.int64)
    boundary_vectors = vertices[boundary_face_vertices[:, 1]] - vertices[boundary_face_vertices[:, 0]]
    boundary_lengths = np.linalg.norm(boundary_vectors, axis=1)
    _require(
        np.isfinite(boundary_lengths).all() and np.all(boundary_lengths > 0),
        'mesh contains invalid boundary-face lengths',
    )
    boundary_normals = np.column_stack((boundary_vectors[:, 1], -boundary_vectors[:, 0]))
    boundary_normals /= boundary_lengths[:, None]
    boundary_midpoints = (
        vertices[boundary_face_vertices[:, 0]] + vertices[boundary_face_vertices[:, 1]]
    ) / 2.0
    reverse_boundary = np.einsum(
        'ij,ij->i', boundary_normals, boundary_midpoints - centroids[boundary_cells]
    ) < 0
    boundary_normals[reverse_boundary] *= -1

    return {
        'package': package,
        'centroids': centroids,
        'areas': areas,
        'left': left,
        'right': right,
        'internal_lengths': internal_lengths,
        'internal_normals': internal_normals,
        'boundary_cells': boundary_cells,
        'boundary_lengths': boundary_lengths,
        'boundary_normals': boundary_normals,
    }


def _physical_flux(state, normals):
    depth = np.maximum(state[:, 0], 1e-12)
    momentum_u = state[:, 1]
    momentum_v = state[:, 2]
    normal_velocity = (
        momentum_u * normals[:, 0] + momentum_v * normals[:, 1]
    ) / depth
    pressure = 0.5 * GRAVITY_M_S2 * depth * depth
    flux = np.column_stack((
        momentum_u * normals[:, 0] + momentum_v * normals[:, 1],
        momentum_u * normal_velocity + pressure * normals[:, 0],
        momentum_v * normal_velocity + pressure * normals[:, 1],
    ))
    return flux, normal_velocity


def _rusanov_flux(left_state, right_state, normals):
    left_flux, left_velocity = _physical_flux(left_state, normals)
    right_flux, right_velocity = _physical_flux(right_state, normals)
    wave_speed = np.maximum(
        np.abs(left_velocity) + np.sqrt(GRAVITY_M_S2 * np.maximum(left_state[:, 0], 0)),
        np.abs(right_velocity) + np.sqrt(GRAVITY_M_S2 * np.maximum(right_state[:, 0], 0)),
    )
    return (
        0.5 * (left_flux + right_flux)
        - 0.5 * wave_speed[:, None] * (right_state - left_state),
        wave_speed,
    )


def _reflected_state(state, normals):
    reflected = state.copy()
    normal_momentum = state[:, 1] * normals[:, 0] + state[:, 2] * normals[:, 1]
    reflected[:, 1] -= 2 * normal_momentum * normals[:, 0]
    reflected[:, 2] -= 2 * normal_momentum * normals[:, 1]
    return reflected


def run_case(
    case,
    steps,
    geometry,
    *,
    max_cfl_allowed,
    max_mass_balance_error_allowed,
    stop_check=None,
    include_fields=True,
):
    """Run one case and raise NumericalStop at the first invalid step."""
    _require(isinstance(steps, int) and steps == 500, 'v2 cases must run exactly 500 steps')
    _require(max_cfl_allowed == 0.95, 'v2 CFL threshold must be exactly 0.95')
    _require(
        max_mass_balance_error_allowed == 1e-8,
        'v2 mass-balance threshold must be exactly 1e-8',
    )

    package = geometry['package']
    centroids = geometry['centroids']
    areas = geometry['areas']
    left = geometry['left']
    right = geometry['right']
    internal_lengths = geometry['internal_lengths']
    internal_normals = geometry['internal_normals']
    boundary_cells = geometry['boundary_cells']
    boundary_lengths = geometry['boundary_lengths']
    boundary_normals = geometry['boundary_normals']
    cell_count = len(areas)

    active_internal = np.ones(len(left), dtype=bool)
    barrage_face_ids = package['barrage_face_ids'].astype(np.int64)
    scenario = case['barrage']['scenario']
    opening_fraction = {
        'fully_closed': 0.0,
        'uniform_25_percent': 0.25,
        'uniform_50_percent': 0.5,
        'uniform_100_percent': 1.0,
    }.get(scenario)
    _require(opening_fraction is not None, f'unsupported barrage scenario: {scenario}')
    active_internal[barrage_face_ids] = opening_fraction > 0

    initial_depth = max(0.5, float(case['bathymetry']['mainstemMeanDepthM']))
    radius_squared = np.sum((centroids - centroids.mean(axis=0)) ** 2, axis=1)
    radius_scale = max(float(np.quantile(radius_squared, 0.25)), 1.0)
    state = np.zeros((cell_count, 3), dtype=np.float64)
    state[:, 0] = initial_depth * (1 + 0.015 * np.exp(-radius_squared / radius_scale))
    phase = float(case['boundaries']['M']['phaseShiftMinutes']) * math.pi / 180.0
    state[:, 1] = state[:, 0] * 0.015 * math.cos(phase)
    state[:, 2] = state[:, 0] * 0.015 * math.sin(phase)

    initial_volume = float(np.sum(state[:, 0] * areas))
    maximum_cfl = 0.0
    minimum_depth = float(state[:, 0].min())
    simulated_seconds = 0.0
    minimum_time_step = math.inf
    maximum_time_step = 0.0
    fishway_cells = package['fishway_cells'].astype(np.int64)
    fishway_enabled = case['fishway']['mode'] != 'disabled'
    fishway_discharge = (
        1e-4
        * float(case['fishway']['effectiveDischargeCoefficient'])
        * float(case['fishway']['effectiveAreaM2'])
    )

    for step_index in range(steps):
        if stop_check is not None:
            stop_check(step_index)

        internal_flux, internal_speed = _rusanov_flux(
            state[left], state[right], internal_normals
        )
        internal_flux *= active_internal[:, None]
        denominator = np.zeros(cell_count, dtype=np.float64)
        np.add.at(
            denominator,
            left,
            internal_speed * internal_lengths * active_internal,
        )
        np.add.at(
            denominator,
            right,
            internal_speed * internal_lengths * active_internal,
        )
        ghost_state = _reflected_state(state[boundary_cells], boundary_normals)
        boundary_flux, boundary_speed = _rusanov_flux(
            state[boundary_cells], ghost_state, boundary_normals
        )
        np.add.at(denominator, boundary_cells, boundary_speed * boundary_lengths)

        time_step = 0.12 * float(np.min(areas / np.maximum(denominator, 1e-30)))
        if not math.isfinite(time_step) or time_step <= 0:
            raise NumericalStop('nonfinite or nonpositive adaptive time step', step=step_index + 1)
        local_cfl = time_step * denominator / areas
        if not np.isfinite(local_cfl).all() or np.any(local_cfl < 0):
            raise NumericalStop('nonfinite or negative local CFL', step=step_index + 1)
        current_cfl = float(np.max(local_cfl))
        maximum_cfl = max(maximum_cfl, current_cfl)
        if current_cfl > max_cfl_allowed:
            raise NumericalStop(
                f'CFL {current_cfl} exceeds {max_cfl_allowed}',
                max_cfl=current_cfl,
                step=step_index + 1,
            )

        residual = np.zeros_like(state)
        np.add.at(residual, left, internal_flux * internal_lengths[:, None])
        np.add.at(residual, right, -internal_flux * internal_lengths[:, None])
        np.add.at(residual, boundary_cells, boundary_flux * boundary_lengths[:, None])
        right_hand_side = -residual
        if fishway_enabled:
            transfer = min(
                fishway_discharge,
                0.02
                * state[fishway_cells[0], 0]
                * areas[fishway_cells[0]]
                / max(time_step, 1e-12),
            )
            right_hand_side[fishway_cells[0], 0] -= transfer
            right_hand_side[fishway_cells[1], 0] += transfer

        next_state = state + time_step * right_hand_side / areas[:, None]
        manning = float(case['roughness']['manningOpenChannel'])
        protected_depth = np.maximum(next_state[:, 0], 1e-8)
        velocity = np.hypot(next_state[:, 1], next_state[:, 2]) / protected_depth
        damping = (
            1
            + time_step
            * GRAVITY_M_S2
            * manning
            * manning
            * velocity
            / np.power(protected_depth, 4.0 / 3.0)
        )
        next_state[:, 1] /= damping
        next_state[:, 2] /= damping

        nan_count = int(next_state.size - np.isfinite(next_state).sum())
        negative_depth_count = int(np.sum(next_state[:, 0] < 0))
        if nan_count or negative_depth_count:
            raise NumericalStop(
                'nonfinite or negative water depth',
                nan_count=nan_count,
                negative_depth_count=negative_depth_count,
                max_cfl=maximum_cfl,
                step=step_index + 1,
            )

        current_volume = float(np.sum(next_state[:, 0] * areas))
        mass_balance_error = abs(current_volume - initial_volume) / max(abs(initial_volume), 1.0)
        if not math.isfinite(mass_balance_error) or mass_balance_error > max_mass_balance_error_allowed:
            raise NumericalStop(
                f'mass-balance error {mass_balance_error} exceeds {max_mass_balance_error_allowed}',
                mass_balance_error=mass_balance_error,
                max_cfl=maximum_cfl,
                step=step_index + 1,
            )

        state = next_state
        simulated_seconds += time_step
        minimum_time_step = min(minimum_time_step, time_step)
        maximum_time_step = max(maximum_time_step, time_step)
        minimum_depth = min(minimum_depth, float(state[:, 0].min()))

        if stop_check is not None:
            stop_check(step_index + 1)

    final_volume = float(np.sum(state[:, 0] * areas))
    final_mass_balance_error = abs(final_volume - initial_volume) / max(abs(initial_volume), 1.0)
    result = {
        'massBalanceError': final_mass_balance_error,
        'maxCfl': maximum_cfl,
        'minimumDepthM': minimum_depth,
        'nanCount': 0,
        'negativeDepthCount': 0,
        'stepsCompleted': steps,
        'simulatedTimeSeconds': simulated_seconds,
        'minimumTimeStepSeconds': minimum_time_step,
        'maximumTimeStepSeconds': maximum_time_step,
    }
    if include_fields:
        depth = state[:, 0].copy()
        result['waterDepthM'] = depth
        result['velocityUms'] = np.divide(
            state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12
        )
        result['velocityVms'] = np.divide(
            state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12
        )
    return result
