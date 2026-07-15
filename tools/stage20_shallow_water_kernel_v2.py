#!/usr/bin/env python3
"""Stage 20 shallow-water kernel v2 with cached geometry and fast cell reduction.

The numerical flux, hydrostatic reconstruction, boundary conditions, friction,
and CFL rule are inherited from the Stage 19 reference kernel. Only repeated
index conversion and face-to-cell accumulation are changed. Physical execution
remains separately gated.
"""

from __future__ import annotations

import math

import numpy as np

import stage19_shallow_water_kernel_v1 as reference
from stage19_solver_inputs import GRAVITY_M_S2


NumericalStop = reference.NumericalStop


def build_solver_geometry(package: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    geometry = reference.build_solver_geometry(package)
    left = geometry["left"]
    right = geometry["right"]
    lengths = geometry["internalLengths"]
    geometry.update({
        "cellCount": np.asarray(len(geometry["areas"]), dtype=np.int64),
        "inverseAreas": 1.0 / geometry["areas"],
        "internalCellIds": np.concatenate((left, right)),
        "internalLengthFactors": np.concatenate((lengths, lengths)),
        "barrageIds": package["barrage_face_ids"].astype(np.int64, copy=False),
        "fishwayCells": package["fishway_cells"].astype(np.int64, copy=False),
    })
    return geometry


def _reduce_faces(
    cell_ids: np.ndarray,
    vector_weights: np.ndarray,
    scalar_weights: np.ndarray,
    cell_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    residual = np.empty((cell_count, 3), dtype=np.float64)
    for component in range(3):
        residual[:, component] = np.bincount(
            cell_ids,
            weights=vector_weights[:, component],
            minlength=cell_count,
        )
    denominator = np.bincount(cell_ids, weights=scalar_weights, minlength=cell_count)
    return residual, denominator


def flux_residual(
    state: np.ndarray,
    simulated_seconds: float,
    fields: dict,
    geometry: dict,
    package: dict,
    candidate: dict,
) -> tuple[np.ndarray, np.ndarray, float]:
    cell_count = int(geometry["cellCount"])
    left = geometry["left"]
    right = geometry["right"]
    lengths = geometry["internalLengths"]
    left_term, right_term, speed = reference._hydrostatic_internal_terms(
        state, fields["bedElevationM"], geometry
    )

    barrage_ids = geometry["barrageIds"]
    if len(barrage_ids):
        transmissivity = float(fields["barrageTransmissivity"])
        normals = geometry["internalNormals"][barrage_ids]
        left_wall, left_wall_speed = reference._wall_flux(state[left[barrage_ids]], normals)
        right_wall, right_wall_speed = reference._wall_flux(state[right[barrage_ids]], -normals)
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

    vector_weights = np.concatenate((left_term, right_term), axis=0)
    vector_weights *= geometry["internalLengthFactors"][:, None]
    scalar_weights = np.concatenate((speed, speed)) * geometry["internalLengthFactors"]
    residual, denominator = _reduce_faces(
        geometry["internalCellIds"], vector_weights, scalar_weights, cell_count
    )

    boundary_cells = geometry["boundaryCells"]
    boundary_lengths = geometry["boundaryLengths"]
    boundary_normals = geometry["boundaryNormals"]
    ghost, _ = reference._boundary_ghosts(
        state, simulated_seconds, fields, geometry, candidate
    )
    boundary_flux, boundary_speed = reference._rusanov(
        state[boundary_cells], ghost, boundary_normals
    )
    weighted_boundary_flux = boundary_flux * boundary_lengths[:, None]
    for component in range(3):
        residual[:, component] += np.bincount(
            boundary_cells,
            weights=weighted_boundary_flux[:, component],
            minlength=cell_count,
        )
    denominator += np.bincount(
        boundary_cells,
        weights=boundary_speed * boundary_lengths,
        minlength=cell_count,
    )
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
    local_cfl = time_step * denominator * geometry["inverseAreas"]
    integrated_rhs = -residual

    raw_fishway = reference.fishway_discharge_m3s(state, fields, package)
    fishway_cells = geometry["fishwayCells"]
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

    next_state = state + time_step * integrated_rhs * geometry["inverseAreas"][:, None]
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
