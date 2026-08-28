#!/usr/bin/env python3
"""R1C adapter for fail-closed operational barrage control.

This module keeps the existing R1C depth-weighted hydrodynamic kernel and its
SHA-bound gate-face mapping.  It measures live heads on the two sides of the
barrage, resolves the adopted operational control policy, and independently
recomputes the exact Rusanov mass flux on every active main-gate face before a
step is committed.  Adverse flux is rejected; it is never clipped.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

import stage20_barrage_operational_control_v1 as operational
import stage20_depth_weighted_boundary_kernel_candidate_v2 as hydro


ADAPTER_VERSION = "stage20-barrage-operational-control-r1c-adapter-v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{ADAPTER_VERSION}] {message}")


def downstream_cell_ids(
    geometry: Mapping[str, np.ndarray],
    gate_face_ids: np.ndarray,
    barrage_upstream_cell_id: np.ndarray,
) -> np.ndarray:
    """Return and validate the downstream cell for every selected gate face."""

    faces = np.asarray(gate_face_ids, dtype=np.int64)
    upstream = np.asarray(barrage_upstream_cell_id, dtype=np.int64)
    require(faces.ndim == 1 and len(faces) > 0, "gate face ids are required")
    require(upstream.shape == faces.shape, "upstream orientation length mismatch")
    left = np.asarray(geometry["left"], dtype=np.int64)[faces]
    right = np.asarray(geometry["right"], dtype=np.int64)[faces]
    upstream_is_left = upstream == left
    upstream_is_right = upstream == right
    require(
        bool(np.all(upstream_is_left ^ upstream_is_right)),
        "each gate face must have exactly one SHA-bound upstream cell",
    )
    result = np.where(upstream_is_left, right, left).astype(np.int64)
    require(bool(np.all(result != upstream)), "upstream/downstream cells overlap")
    return result


def length_weighted_gate_heads(
    state: np.ndarray,
    bed_elevation_m: np.ndarray,
    geometry: Mapping[str, np.ndarray],
    gate_face_ids: np.ndarray,
    barrage_upstream_cell_id: np.ndarray,
) -> dict[str, float]:
    """Measure live free-surface heads on both sides of the full barrage."""

    values = np.asarray(state, dtype=np.float64)
    bed = np.asarray(bed_elevation_m, dtype=np.float64)
    faces = np.asarray(gate_face_ids, dtype=np.int64)
    upstream = np.asarray(barrage_upstream_cell_id, dtype=np.int64)
    downstream = downstream_cell_ids(geometry, faces, upstream)
    require(values.ndim == 2 and values.shape[1] == 3, "state shape is invalid")
    require(bed.shape == (len(values),), "bed shape is invalid")
    require(bool(np.isfinite(values).all()), "state contains non-finite values")
    require(bool(np.isfinite(bed).all()), "bed contains non-finite values")
    lengths = np.asarray(geometry["internalLengths"], dtype=np.float64)[faces]
    require(bool(np.all(lengths > 0.0)), "gate face lengths must be positive")
    weight = lengths / float(np.sum(lengths))
    eta = values[:, 0] + bed
    upstream_head = float(np.sum(weight * eta[upstream]))
    downstream_head = float(np.sum(weight * eta[downstream]))
    return {
        "upstreamHeadM": upstream_head,
        "downstreamHeadM": downstream_head,
        "headDifferenceM": upstream_head - downstream_head,
    }


def requested_interface(
    capacity_by_gate_id_1_to_8: np.ndarray,
    *,
    fishway_gate_open: int = 1,
) -> dict[str, object]:
    """Convert an exact binary R1C request into the operational interface."""

    capacity = np.asarray(capacity_by_gate_id_1_to_8, dtype=np.float64)
    require(capacity.shape == (8,), "capacity vector must contain eight gates")
    require(bool(np.isfinite(capacity).all()), "capacity vector is non-finite")
    require(
        bool(np.all((capacity == 0.0) | (capacity == 1.0))),
        "operational canary accepts exact binary gate requests only",
    )
    require(type(fishway_gate_open) is int and fishway_gate_open in (0, 1), "fishway state is invalid")
    return {
        "mainGateOpenById": {
            str(gate): int(capacity[gate - 1]) for gate in range(1, 9)
        },
        "fineAdjustmentGateOpen": 0,
        "fishwayGateOpen": fishway_gate_open,
    }


def effective_capacity(
    requested_capacity: np.ndarray,
    decision: Mapping[str, Any],
    *,
    continuous_safe_head_duration_s: float,
    minimum_safe_head_dwell_s: float,
) -> tuple[np.ndarray, str]:
    """Apply immediate closure and a conservative dwell before opening."""

    requested = np.asarray(requested_capacity, dtype=np.float64)
    require(requested.shape == (8,), "requested capacity shape is invalid")
    dwell = float(continuous_safe_head_duration_s)
    minimum_dwell = float(minimum_safe_head_dwell_s)
    require(np.isfinite(dwell) and dwell >= 0.0, "safe-head dwell is invalid")
    require(
        np.isfinite(minimum_dwell) and minimum_dwell >= 0.0,
        "minimum safe-head dwell is invalid",
    )
    if not bool(decision["openingAllowed"]):
        return np.zeros(8, dtype=np.float64), str(decision["classification"])
    if dwell + 1.0e-12 < minimum_dwell:
        return np.zeros(8, dtype=np.float64), "INTERLOCK_CLOSED_SAFE_HEAD_DWELL"
    effective = decision["effectiveInterface"]["mainGateOpenById"]
    result = np.asarray(
        [float(effective[str(gate)]) for gate in range(1, 9)],
        dtype=np.float64,
    )
    require(bool(np.array_equal(result, requested)), "effective request changed unexpectedly")
    return result, str(decision["classification"])


def signed_outward_gate_discharge_m3_s(
    state: np.ndarray,
    bed_elevation_m: np.ndarray,
    geometry: Mapping[str, np.ndarray],
    gate_face_ids: np.ndarray,
    barrage_upstream_cell_id: np.ndarray,
    effective_internal_lengths: np.ndarray,
    interface_multiplier_by_face: np.ndarray,
) -> np.ndarray:
    """Recompute the exact active-face mass flux with outward-positive sign."""

    values = np.asarray(state, dtype=np.float64)
    bed = np.asarray(bed_elevation_m, dtype=np.float64)
    faces = np.asarray(gate_face_ids, dtype=np.int64)
    upstream = np.asarray(barrage_upstream_cell_id, dtype=np.int64)
    downstream_cell_ids(geometry, faces, upstream)
    left_all = np.asarray(geometry["left"], dtype=np.int64)
    right_all = np.asarray(geometry["right"], dtype=np.int64)
    normals = np.asarray(geometry["internalNormals"], dtype=np.float64)
    lengths = np.asarray(effective_internal_lengths, dtype=np.float64)
    multipliers = np.asarray(interface_multiplier_by_face, dtype=np.float64)
    require(lengths.shape == left_all.shape, "effective length shape mismatch")
    require(multipliers.shape == left_all.shape, "interface multiplier shape mismatch")
    result = np.empty(len(faces), dtype=np.float64)

    for selected_index, face in enumerate(faces):
        left = int(left_all[face])
        right = int(right_all[face])
        normal_x = float(normals[face, 0])
        normal_y = float(normals[face, 1])
        left_h = float(values[left, 0])
        left_hu = float(values[left, 1])
        left_hv = float(values[left, 2])
        right_h = float(values[right, 0])
        right_hu = float(values[right, 1])
        right_hv = float(values[right, 2])
        eta_left = left_h + float(bed[left])
        eta_right = right_h + float(bed[right])
        bed_star = max(float(bed[left]), float(bed[right]))
        reconstructed_left_h = max(eta_left - bed_star, 0.0)
        reconstructed_right_h = max(eta_right - bed_star, 0.0)
        if left_h > 1.0e-12:
            reconstructed_left_hu = reconstructed_left_h * left_hu / left_h
            reconstructed_left_hv = reconstructed_left_h * left_hv / left_h
        else:
            reconstructed_left_hu = 0.0
            reconstructed_left_hv = 0.0
        if right_h > 1.0e-12:
            reconstructed_right_hu = reconstructed_right_h * right_hu / right_h
            reconstructed_right_hv = reconstructed_right_h * right_hv / right_h
        else:
            reconstructed_right_hu = 0.0
            reconstructed_right_hv = 0.0
        flux_0, _, _, _ = hydro.compiled._rusanov_one(
            reconstructed_left_h,
            reconstructed_left_hu,
            reconstructed_left_hv,
            reconstructed_right_h,
            reconstructed_right_hu,
            reconstructed_right_hv,
            normal_x,
            normal_y,
        )
        mass_flux = (
            float(flux_0)
            * float(multipliers[face])
            * float(lengths[face])
        )
        result[selected_index] = (
            mass_flux if int(upstream[selected_index]) == left else -mass_flux
        )
    require(bool(np.isfinite(result).all()), "gate discharge contains non-finite values")
    return result


def validate_active_outward_flux(
    signed_outward_discharge_m3_s: np.ndarray,
    gate_index_by_selected_face: np.ndarray,
    effective_capacity_by_gate: np.ndarray,
    *,
    tolerance_m3_s: float,
) -> dict[str, Any]:
    """Reject reverse flux on active gates while recording closed-face scope."""

    values = np.asarray(signed_outward_discharge_m3_s, dtype=np.float64)
    gate_indices = np.asarray(gate_index_by_selected_face, dtype=np.int64)
    capacity = np.asarray(effective_capacity_by_gate, dtype=np.float64)
    require(values.shape == gate_indices.shape, "gate flux/index shape mismatch")
    require(capacity.shape == (8,), "effective capacity shape mismatch")
    active = capacity[gate_indices] > 0.0
    if not np.any(active):
        return {
            "reverseFlowPermitted": False,
            "activeFaceCount": 0,
            "adverseFaceCount": 0,
            "minimumSignedOutwardDischargeM3S": None,
            "totalSignedOutwardDischargeM3S": 0.0,
            "toleranceM3S": float(tolerance_m3_s),
        }
    validated = operational.validate_outward_gate_flux(
        values[active], tolerance_m3_s=tolerance_m3_s
    )
    return {"activeFaceCount": int(np.sum(active)), **validated}
