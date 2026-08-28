#!/usr/bin/env python3
"""Dedicated D1 H2 kernel with the bounded fishway interface candidate.

The hydrodynamic flux, boundary, bed reconstruction, friction, and gate-face
logic are copied from the hash-bound Stage 20 H2 diagnostic kernel.  Only the
old locally capped P2 source block is replaced.  This module is diagnostic-only
and is not imported by an existing solver or public runtime.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

import stage20_shallow_water_kernel_v3 as compiled
from stage19_solver_inputs import GRAVITY_M_S2


HYDRO_SOURCE_PATH = "tools/run_stage20_R20_multizone_H2_dynamics_diagnostic_v1.py"
HYDRO_SOURCE_SHA256 = "c0ec5d16e7c369d43a8ad74bffd709d08dbf833b8d37587e2144d767ab02321b"
INTERFACE_SOURCE_PATH = "tools/stage20_fishway_internal_interface_v1.py"
INTERFACE_SOURCE_SHA256 = "e7bfed22ff49a3b049a2fe7dead7d71085a4c2d293e14694903d55a22452fbc6"


@njit(cache=True, fastmath=False)
def advance_h2_step(
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
    target_flux_by_tag: np.ndarray,
    donor_support_area_m2: np.ndarray,
    receiver_weights: np.ndarray,
    expansion_rank: np.ndarray,
    maximum_support_radius_by_rank_m: np.ndarray,
    q0_m3_s: float,
    reserve_depth_m: float,
    maximum_available_volume_fraction_per_step: float,
    maximum_expansion_rank: int,
    maximum_support_radius_m: float,
    cfl_target: float,
    maximum_dt: float,
) -> tuple[
    np.ndarray,
    float,
    float,
    float,
    float,
    float,
    int,
    int,
    float,
    float,
    float,
    float,
    float,
]:
    """Advance one adaptive step or fail before mutation on fishway shortage."""

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
            if interior_h < 1e-8:
                raise ValueError("numerically dry river boundary")
            normal_momentum = interior_hu * normal_x + interior_hv * normal_y
            tangent_hu = interior_hu - normal_momentum * normal_x
            tangent_hv = interior_hv - normal_momentum * normal_y
            ghost_normal_momentum = (
                2.0 * target_flux_by_tag[tag] - normal_momentum
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
    for cell in range(cell_count):
        time_step_limit = min(
            time_step_limit,
            areas[cell] / max(denominator[cell], 1e-30),
        )
    time_step = min(cfl_target * time_step_limit, maximum_dt)
    if not math.isfinite(time_step) or time_step <= 0.0:
        raise ValueError("invalid adaptive time step")

    maximum_rank = 0
    for cell in range(cell_count):
        maximum_rank = max(maximum_rank, int(expansion_rank[cell]))
    available_by_rank = np.zeros(maximum_rank + 1, dtype=np.float64)
    for cell in range(cell_count):
        rank = int(expansion_rank[cell])
        if rank >= 0:
            available_by_rank[rank] += donor_support_area_m2[cell] * max(
                state[cell, 0] - reserve_depth_m,
                0.0,
            )
    required_available = (
        q0_m3_s
        * time_step
        / maximum_available_volume_fraction_per_step
    )
    selected_rank = -1
    selected_available = 0.0
    for rank in range(maximum_rank + 1):
        selected_available += available_by_rank[rank]
        if selected_available + 1e-15 >= required_available:
            selected_rank = rank
            break
    if selected_rank < 0:
        raise ValueError("fishway full-Q supply unavailable")
    if selected_rank > maximum_expansion_rank:
        raise ValueError("fishway expansion rank guard exceeded")
    support_radius = maximum_support_radius_by_rank_m[selected_rank]
    if support_radius > maximum_support_radius_m + 1e-12:
        raise ValueError("fishway support radius guard exceeded")

    fishway_mass_source = np.zeros(cell_count, dtype=np.float64)
    fishway_hu_source = np.zeros(cell_count, dtype=np.float64)
    fishway_hv_source = np.zeros(cell_count, dtype=np.float64)
    selected_count = 0
    maximum_removed_fraction = 0.0
    minimum_selected_post_depth = math.inf
    for cell in range(cell_count):
        if receiver_weights[cell] > 0.0:
            fishway_mass_source[cell] += q0_m3_s * receiver_weights[cell]
        rank = int(expansion_rank[cell])
        available = 0.0
        if rank >= 0 and rank <= selected_rank:
            available = donor_support_area_m2[cell] * max(
                state[cell, 0] - reserve_depth_m,
                0.0,
            )
        if available > 0.0:
            donor_rate = q0_m3_s * available / selected_available
            fishway_mass_source[cell] -= donor_rate
            depth = max(state[cell, 0], 1e-12)
            fishway_hu_source[cell] -= donor_rate * state[cell, 1] / depth
            fishway_hv_source[cell] -= donor_rate * state[cell, 2] / depth
            removed_fraction = time_step * donor_rate / available
            maximum_removed_fraction = max(
                maximum_removed_fraction,
                removed_fraction,
            )
            selected_post_depth = (
                state[cell, 0]
                - time_step * donor_rate * inverse_areas[cell]
            )
            minimum_selected_post_depth = min(
                minimum_selected_post_depth,
                selected_post_depth,
            )
            selected_count += 1

    fishway_source_residual = 0.0
    effective_q = 0.0
    for cell in range(cell_count):
        fishway_source_residual += fishway_mass_source[cell]
        effective_q += q0_m3_s * receiver_weights[cell]
    if abs(fishway_source_residual) > 1e-12:
        raise ValueError("fishway interface mass residual exceeds limit")
    if abs(effective_q - q0_m3_s) > 1e-12:
        raise ValueError("fishway effective Q differs from prescribed Q0")
    if minimum_selected_post_depth < reserve_depth_m - 1e-12:
        raise ValueError("fishway donor reserve depth would be violated")
    if (
        maximum_removed_fraction
        > maximum_available_volume_fraction_per_step + 1e-12
    ):
        raise ValueError("fishway per-step withdrawal cap would be violated")

    next_state = np.empty_like(state)
    max_cfl = 0.0
    for cell in range(cell_count):
        rhs_0 = -residual[cell, 0] + fishway_mass_source[cell]
        rhs_1 = -residual[cell, 1] + fishway_hu_source[cell]
        rhs_2 = -residual[cell, 2] + fishway_hv_source[cell]
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
        selected_rank,
        selected_count,
        selected_available,
        required_available,
        maximum_removed_fraction,
        minimum_selected_post_depth,
        support_radius,
    )
