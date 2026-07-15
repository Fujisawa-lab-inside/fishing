#!/usr/bin/env python3
"""Stage 20 compiled shallow-water kernel v3.

The mesh, numerical flux, hydrostatic reconstruction, boundary conditions,
friction, CFL rule, and float64 state are inherited from kernel v2. Numba only
fuses the face, boundary, update, and friction loops. Physical execution remains
separately gated.
"""

from __future__ import annotations

import math

import numpy as np

import stage19_shallow_water_kernel_v1 as reference
import stage20_shallow_water_kernel_v2 as kernel_v2
from stage19_solver_inputs import GRAVITY_M_S2

try:
    from numba import njit
except ImportError as exc:  # pragma: no cover - exercised by dependency preflight
    raise ImportError(
        "kernel v3 requires numba; install tools/requirements-stage20-kernel-v3.txt"
    ) from exc


NumericalStop = reference.NumericalStop


def build_solver_geometry(package: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    geometry = kernel_v2.build_solver_geometry(package)
    barrage_mask = np.zeros(len(geometry["left"]), dtype=np.uint8)
    barrage_mask[geometry["barrageIds"]] = 1
    tag_length_sums = np.zeros(5, dtype=np.float64)
    np.add.at(tag_length_sums, geometry["boundaryTags"], geometry["boundaryLengths"])
    geometry.update({
        "barrageMask": barrage_mask,
        "boundaryTagLengthSums": tag_length_sums,
    })
    return geometry


@njit(cache=True, fastmath=False)
def _rusanov_one(
    left_h: float,
    left_hu: float,
    left_hv: float,
    right_h: float,
    right_hu: float,
    right_hv: float,
    normal_x: float,
    normal_y: float,
) -> tuple[float, float, float, float]:
    left_depth = max(left_h, 1e-12)
    right_depth = max(right_h, 1e-12)
    left_normal_velocity = (left_hu * normal_x + left_hv * normal_y) / left_depth
    right_normal_velocity = (right_hu * normal_x + right_hv * normal_y) / right_depth
    left_pressure = 0.5 * GRAVITY_M_S2 * left_depth * left_depth
    right_pressure = 0.5 * GRAVITY_M_S2 * right_depth * right_depth

    left_flux_0 = left_hu * normal_x + left_hv * normal_y
    left_flux_1 = left_hu * left_normal_velocity + left_pressure * normal_x
    left_flux_2 = left_hv * left_normal_velocity + left_pressure * normal_y
    right_flux_0 = right_hu * normal_x + right_hv * normal_y
    right_flux_1 = right_hu * right_normal_velocity + right_pressure * normal_x
    right_flux_2 = right_hv * right_normal_velocity + right_pressure * normal_y

    speed = max(
        abs(left_normal_velocity) + math.sqrt(GRAVITY_M_S2 * max(left_h, 0.0)),
        abs(right_normal_velocity) + math.sqrt(GRAVITY_M_S2 * max(right_h, 0.0)),
    )
    flux_0 = 0.5 * (left_flux_0 + right_flux_0) - 0.5 * speed * (right_h - left_h)
    flux_1 = 0.5 * (left_flux_1 + right_flux_1) - 0.5 * speed * (right_hu - left_hu)
    flux_2 = 0.5 * (left_flux_2 + right_flux_2) - 0.5 * speed * (right_hv - left_hv)
    return flux_0, flux_1, flux_2, speed


@njit(cache=True, fastmath=False)
def _advance_one_step_compiled(
    state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    areas: np.ndarray,
    inverse_areas: np.ndarray,
    left_cells: np.ndarray,
    right_cells: np.ndarray,
    internal_lengths: np.ndarray,
    internal_normals: np.ndarray,
    barrage_mask: np.ndarray,
    barrage_transmissivity: float,
    boundary_cells: np.ndarray,
    boundary_lengths: np.ndarray,
    boundary_normals: np.ndarray,
    boundary_tags: np.ndarray,
    tide_target_m: float,
    target_flux_by_tag: np.ndarray,
    fishway_cells: np.ndarray,
    raw_fishway_discharge: float,
    cfl_target: float,
) -> tuple[np.ndarray, float, float, float, float]:
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

        flux_0, flux_1, flux_2, speed = _rusanov_one(
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

        if barrage_mask[face] != 0:
            left_normal_momentum = left_hu * normal_x + left_hv * normal_y
            left_reflected_hu = left_hu - 2.0 * left_normal_momentum * normal_x
            left_reflected_hv = left_hv - 2.0 * left_normal_momentum * normal_y
            wall_l0, wall_l1, wall_l2, wall_left_speed = _rusanov_one(
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
            right_normal_momentum = right_hu * right_normal_x + right_hv * right_normal_y
            right_reflected_hu = right_hu - 2.0 * right_normal_momentum * right_normal_x
            right_reflected_hv = right_hv - 2.0 * right_normal_momentum * right_normal_y
            wall_r0, wall_r1, wall_r2, wall_right_speed = _rusanov_one(
                right_h,
                right_hu,
                right_hv,
                right_h,
                right_reflected_hu,
                right_reflected_hv,
                right_normal_x,
                right_normal_y,
            )
            wall_fraction = 1.0 - barrage_transmissivity
            left_term_0 = barrage_transmissivity * left_term_0 + wall_fraction * wall_l0
            left_term_1 = barrage_transmissivity * left_term_1 + wall_fraction * wall_l1
            left_term_2 = barrage_transmissivity * left_term_2 + wall_fraction * wall_l2
            right_term_0 = barrage_transmissivity * right_term_0 + wall_fraction * wall_r0
            right_term_1 = barrage_transmissivity * right_term_1 + wall_fraction * wall_r1
            right_term_2 = barrage_transmissivity * right_term_2 + wall_fraction * wall_r2
            speed = max(speed, wall_left_speed, wall_right_speed)

        residual[left, 0] += left_term_0 * length
        residual[left, 1] += left_term_1 * length
        residual[left, 2] += left_term_2 * length
        residual[right, 0] += right_term_0 * length
        residual[right, 1] += right_term_1 * length
        residual[right, 2] += right_term_2 * length
        denominator[left] += speed * length
        denominator[right] += speed * length

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
            ghost_h = max(tide_target_m - bed[cell], 0.05)
            if interior_h > 1e-12:
                ghost_hu = ghost_h * interior_hu / interior_h
                ghost_hv = ghost_h * interior_hv / interior_h
            else:
                ghost_hu = 0.0
                ghost_hv = 0.0
        else:
            depth = max(interior_h, 0.05)
            velocity_x = interior_hu / depth
            velocity_y = interior_hv / depth
            normal_velocity = velocity_x * normal_x + velocity_y * normal_y
            tangent_x = velocity_x - normal_velocity * normal_x
            tangent_y = velocity_y - normal_velocity * normal_y
            ghost_normal_velocity = 2.0 * target_flux_by_tag[tag] / depth - normal_velocity
            ghost_velocity_x = tangent_x + ghost_normal_velocity * normal_x
            ghost_velocity_y = tangent_y + ghost_normal_velocity * normal_y
            ghost_h = depth
            ghost_hu = depth * ghost_velocity_x
            ghost_hv = depth * ghost_velocity_y

        flux_0, flux_1, flux_2, speed = _rusanov_one(
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
    for cell in range(cell_count):
        time_step_limit = min(time_step_limit, areas[cell] / max(denominator[cell], 1e-30))
    time_step = cfl_target * time_step_limit
    if not math.isfinite(time_step) or time_step <= 0.0:
        raise ValueError("invalid adaptive time step")

    fishway_discharge = raw_fishway_discharge
    donor = -1
    receiver = -1
    signed_fishway_discharge = 0.0
    donor_velocity_x = 0.0
    donor_velocity_y = 0.0
    if raw_fishway_discharge != 0.0:
        donor_index = 0 if raw_fishway_discharge > 0.0 else 1
        receiver_index = 1 - donor_index
        donor = fishway_cells[donor_index]
        receiver = fishway_cells[receiver_index]
        maximum = 0.02 * max(state[donor, 0] - 0.05, 0.0) * areas[donor] / time_step
        magnitude = min(abs(raw_fishway_discharge), maximum)
        fishway_discharge = math.copysign(magnitude, raw_fishway_discharge)
        donor_depth = max(state[donor, 0], 1e-12)
        donor_velocity_x = state[donor, 1] / donor_depth
        donor_velocity_y = state[donor, 2] / donor_depth
        signed_fishway_discharge = abs(fishway_discharge)

    next_state = np.empty_like(state)
    max_cfl = 0.0
    for cell in range(cell_count):
        rhs_0 = -residual[cell, 0]
        rhs_1 = -residual[cell, 1]
        rhs_2 = -residual[cell, 2]
        if cell == donor:
            rhs_0 -= signed_fishway_discharge
            rhs_1 -= signed_fishway_discharge * donor_velocity_x
            rhs_2 -= signed_fishway_discharge * donor_velocity_y
        elif cell == receiver:
            rhs_0 += signed_fishway_discharge
            rhs_1 += signed_fishway_discharge * donor_velocity_x
            rhs_2 += signed_fishway_discharge * donor_velocity_y

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

    return next_state, time_step, max_cfl, boundary_outflow, fishway_discharge


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
    tide_target = reference.tide_anomaly_m(simulated_seconds, fields["tide"], candidate)
    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        length_sum = float(geometry["boundaryTagLengthSums"][tag])
        if length_sum <= 0.0:
            raise NumericalStop(f"boundary tag {tag} has zero length")
        target_flux_by_tag[tag] = -float(fields["boundaryDischargeM3S"][boundary_id]) / length_sum
    raw_fishway = reference.fishway_discharge_m3s(state, fields, package)
    try:
        next_state, time_step, max_cfl, boundary_outflow, fishway_discharge = (
            _advance_one_step_compiled(
                state,
                fields["bedElevationM"],
                fields["manningN"],
                geometry["areas"],
                geometry["inverseAreas"],
                geometry["left"],
                geometry["right"],
                geometry["internalLengths"],
                geometry["internalNormals"],
                geometry["barrageMask"],
                float(fields["barrageTransmissivity"]),
                geometry["boundaryCells"],
                geometry["boundaryLengths"],
                geometry["boundaryNormals"],
                geometry["boundaryTags"],
                tide_target,
                target_flux_by_tag,
                geometry["fishwayCells"],
                raw_fishway,
                cfl_target,
            )
        )
    except ValueError as exc:
        raise NumericalStop(str(exc)) from exc
    return next_state, time_step, {
        "maxCfl": float(max_cfl),
        "boundaryOutflowM3S": float(boundary_outflow),
        "fishwayDischargeM3S": float(fishway_discharge),
    }
