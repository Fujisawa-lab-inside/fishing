#!/usr/bin/env python3
"""One-way external barrage-release source for the downstream component.

The prescribed barrage release is applied directly to cells on the downstream
side of the SHA-bound barrage faces.  It is therefore not limited by the water
volume in the excluded upstream component.  Added mass is exact and added
momentum is oriented from the barrage toward the downstream side.

This remains a diagnostic boundary surrogate.  The gate-by-gate opening,
actuator response, jet contraction, and physical discharge law are not
resolved or validated here.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np


ADAPTER_VERSION = "stage20-downstream-external-inflow-adapter-v1"
SOURCE_RESIDUAL_RELATIVE_TOLERANCE = 1.0e-10
COMMANDED_SOURCE_RESIDUAL_RELATIVE_TOLERANCE = 1.0e-13


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{ADAPTER_VERSION}] {message}")


def build_external_inflow_layout(
    geometry: Mapping[str, np.ndarray],
    gate_face_ids: np.ndarray,
    barrage_upstream_cell_id: np.ndarray,
    upstream_component_mask: np.ndarray,
    areas_m2: np.ndarray,
) -> dict[str, Any]:
    """Orient the barrage faces and identify downstream receiver cells."""

    faces = np.asarray(gate_face_ids, dtype=np.int64)
    upstream = np.asarray(barrage_upstream_cell_id, dtype=np.int64)
    component = np.asarray(upstream_component_mask, dtype=np.uint8)
    areas = np.asarray(areas_m2, dtype=np.float64)
    left = np.asarray(geometry["left"], dtype=np.int64)
    right = np.asarray(geometry["right"], dtype=np.int64)
    lengths = np.asarray(geometry["internalLengths"], dtype=np.float64)
    normals = np.asarray(geometry["internalNormals"], dtype=np.float64)

    require(faces.ndim == 1 and len(faces) > 0, "gate-face list is empty")
    require(upstream.shape == faces.shape, "gate-face and upstream-cell shapes differ")
    require(len(np.unique(faces)) == len(faces), "gate-face list contains duplicates")
    require(left.shape == right.shape == lengths.shape, "internal-face arrays differ")
    require(normals.shape == (len(left), 2), "internal normals have an invalid shape")
    require(component.ndim == 1 and areas.shape == component.shape, "cell arrays differ")
    require(bool(np.all((0 <= faces) & (faces < len(left)))), "gate-face id is out of range")
    require(bool(np.all((0 <= upstream) & (upstream < len(areas)))), "upstream cell is out of range")
    require(bool(np.all(np.isin(component, [0, 1]))), "component mask is not binary")
    require(bool(np.isfinite(areas).all()) and bool(np.all(areas > 0.0)), "cell areas are invalid")

    face_left = left[faces]
    face_right = right[faces]
    upstream_is_left = face_left == upstream
    upstream_is_right = face_right == upstream
    require(
        bool(np.all(upstream_is_left ^ upstream_is_right)),
        "upstream cell is not exactly one side of each barrage face",
    )
    downstream = np.where(upstream_is_left, face_right, face_left).astype(np.int64)
    require(bool(np.all(component[upstream] == 1)), "upstream orientation disagrees with component mask")
    require(bool(np.all(component[downstream] == 0)), "downstream receiver lies in upstream component")

    face_lengths = lengths[faces].copy()
    face_normals = normals[faces].copy()
    face_normals[upstream_is_right] *= -1.0
    normal_magnitude = np.linalg.norm(face_normals, axis=1)
    require(bool(np.isfinite(face_lengths).all()) and bool(np.all(face_lengths > 0.0)), "barrage face length is invalid")
    require(bool(np.isfinite(face_normals).all()), "barrage normal is nonfinite")
    require(bool(np.all(np.abs(normal_magnitude - 1.0) <= 1.0e-12)), "barrage normal is not unit length")

    output_mask = component == 0
    require(bool(np.any(output_mask)) and bool(np.any(~output_mask)), "component split is degenerate")
    receiver_ids = np.unique(downstream)
    return {
        "schema": "onga-stage20-downstream-external-inflow-layout-v1",
        "classification": (
            "ONE_WAY_EXTERNAL_DOWNSTREAM_MASS_AND_MOMENTUM_SOURCE_"
            "NOT_GATE_OPERATION_NOT_PHYSICAL_VALIDATION"
        ),
        "gateFaceIds": faces.copy(),
        "upstreamCellIdByFace": upstream.copy(),
        "downstreamCellIdByFace": downstream,
        "downstreamNormalByFace": face_normals,
        "faceLengthM": face_lengths,
        "downstreamOutputCellMask": output_mask.astype(np.uint8),
        "gateFaceCount": int(len(faces)),
        "receiverCellCount": int(len(receiver_ids)),
        "downstreamCellCount": int(np.sum(output_mask)),
        "upstreamExcludedCellCount": int(np.sum(~output_mask)),
        "usesUpstreamDonorVolume": False,
        "reverseFlowPermitted": False,
        "preservesGateByGateOpening": False,
        "fishwayJetResolved": False,
    }

def apply_external_inflow(
    state_after_hydraulics: np.ndarray,
    areas_m2: np.ndarray,
    layout: Mapping[str, Any],
    release_m3_s: float,
    accepted_dt_s: float,
    *,
    minimum_flow_depth_m: float = 0.05,
    maximum_inflow_velocity_m_s: float = 5.0,
) -> dict[str, Any]:
    """Add exact mass and downstream-normal momentum without clipping.

    The total wet cross-section is estimated from downstream receiver depth and
    gate-face length.  A common velocity ``Q / A`` is assigned to the injected
    parcels, while per-face discharge is proportional to that wet area.  If
    the requested discharge would exceed the explicit velocity guard, the
    source fails closed instead of silently reducing the discharge.
    """

    state = np.asarray(state_after_hydraulics, dtype=np.float64)
    areas = np.asarray(areas_m2, dtype=np.float64)
    downstream = np.asarray(layout["downstreamCellIdByFace"], dtype=np.int64)
    normals = np.asarray(layout["downstreamNormalByFace"], dtype=np.float64)
    lengths = np.asarray(layout["faceLengthM"], dtype=np.float64)
    output_mask = np.asarray(layout["downstreamOutputCellMask"], dtype=np.uint8).astype(bool)
    release = float(release_m3_s)
    dt = float(accepted_dt_s)
    minimum_depth = float(minimum_flow_depth_m)
    maximum_velocity = float(maximum_inflow_velocity_m_s)

    require(state.ndim == 2 and state.shape[1] == 3, "state must have h, hu, hv columns")
    require(areas.shape == (len(state),), "state and area counts differ")
    require(output_mask.shape == (len(state),), "output mask and state counts differ")
    require(downstream.ndim == 1 and len(downstream) > 0, "receiver face list is empty")
    require(normals.shape == (len(downstream), 2), "receiver normals have an invalid shape")
    require(lengths.shape == downstream.shape, "receiver lengths have an invalid shape")
    require(bool(np.all((0 <= downstream) & (downstream < len(state)))), "receiver cell is out of range")
    require(bool(np.all(output_mask[downstream])), "external source targets an excluded upstream cell")
    require(bool(np.isfinite(state).all()) and bool(np.all(state[:, 0] >= 0.0)), "input state is unsafe")
    require(bool(np.isfinite(areas).all()) and bool(np.all(areas > 0.0)), "cell areas are invalid")
    require(np.isfinite(release) and release >= 0.0, "release must be finite and nonnegative")
    require(np.isfinite(dt) and dt > 0.0, "accepted time step must be positive")
    require(np.isfinite(minimum_depth) and minimum_depth > 0.0, "minimum flow depth is invalid")
    require(np.isfinite(maximum_velocity) and maximum_velocity > 0.0, "velocity guard is invalid")

    next_state = state.copy()
    if release == 0.0:
        return {
            "schema": "onga-stage20-downstream-external-inflow-step-v1",
            "nextState": next_state,
            "requestedReleaseM3S": 0.0,
            "effectiveReleaseM3S": 0.0,
            "sourceResidualM3S": 0.0,
            "sourceResidualRelative": 0.0,
            "commandedSourceResidualM3S": 0.0,
            "commandedSourceResidualRelative": 0.0,
            "addedVolumeM3": 0.0,
            "inflowVelocityMPS": 0.0,
            "wetCrossSectionM2": 0.0,
            "minimumFaceDownstreamMomentumFluxM4S2": 0.0,
            "upstreamStateChanged": False,
            "reverseFlowPermitted": False,
        }

    face_depth = np.maximum(state[downstream, 0], minimum_depth)
    face_wet_area = lengths * face_depth
    wet_cross_section = float(np.sum(face_wet_area))
    require(np.isfinite(wet_cross_section) and wet_cross_section > 0.0, "wet cross-section is invalid")
    inflow_velocity = release / wet_cross_section
    require(np.isfinite(inflow_velocity), "inflow velocity is nonfinite")
    require(
        inflow_velocity <= maximum_velocity,
        "requested release exceeds the no-clipping inflow-velocity guard",
    )

    face_discharge = release * face_wet_area / wet_cross_section
    face_volume = face_discharge * dt
    inverse_receiver_area = 1.0 / areas[downstream]
    np.add.at(next_state[:, 0], downstream, face_volume * inverse_receiver_area)
    np.add.at(
        next_state[:, 1],
        downstream,
        face_volume * inflow_velocity * normals[:, 0] * inverse_receiver_area,
    )
    np.add.at(
        next_state[:, 2],
        downstream,
        face_volume * inflow_velocity * normals[:, 1] * inverse_receiver_area,
    )

    added_volume = float(np.sum((next_state[:, 0] - state[:, 0]) * areas))
    residual = added_volume / dt - release
    residual_scale = max(release, 1.0)
    relative_residual = residual / residual_scale
    commanded_added_volume = np.sum(
        np.asarray(face_volume, dtype=np.longdouble),
        dtype=np.longdouble,
    )
    commanded_residual = float(
        commanded_added_volume / np.longdouble(dt) - np.longdouble(release)
    )
    commanded_relative_residual = commanded_residual / residual_scale
    face_downstream_momentum_flux = face_discharge * inflow_velocity
    upstream_changed = not np.array_equal(next_state[~output_mask], state[~output_mask])
    require(
        abs(commanded_relative_residual)
        <= COMMANDED_SOURCE_RESIDUAL_RELATIVE_TOLERANCE,
        "commanded external source mass residual is too large",
    )
    require(
        abs(relative_residual) <= SOURCE_RESIDUAL_RELATIVE_TOLERANCE,
        "external source mass residual is too large",
    )
    require(bool(np.all(face_discharge >= 0.0)), "reverse discharge was generated")
    require(bool(np.all(face_downstream_momentum_flux >= 0.0)), "reverse momentum was generated")
    require(not upstream_changed, "external source changed the excluded upstream component")
    require(bool(np.isfinite(next_state).all()) and bool(np.all(next_state[:, 0] >= 0.0)), "external source produced an unsafe state")
    return {
        "schema": "onga-stage20-downstream-external-inflow-step-v1",
        "nextState": next_state,
        "requestedReleaseM3S": release,
        "effectiveReleaseM3S": added_volume / dt,
        "sourceResidualM3S": residual,
        "sourceResidualRelative": relative_residual,
        "commandedSourceResidualM3S": commanded_residual,
        "commandedSourceResidualRelative": commanded_relative_residual,
        "addedVolumeM3": added_volume,
        "inflowVelocityMPS": inflow_velocity,
        "wetCrossSectionM2": wet_cross_section,
        "minimumFaceDownstreamMomentumFluxM4S2": float(np.min(face_downstream_momentum_flux)),
        "upstreamStateChanged": upstream_changed,
        "reverseFlowPermitted": False,
    }
