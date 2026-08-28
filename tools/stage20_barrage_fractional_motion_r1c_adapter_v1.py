#!/usr/bin/env python3
"""R1C observations and hard flux gate for fractional barrage motion."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

import stage20_barrage_operational_control_r1c_adapter_v1 as base


ADAPTER_VERSION = "stage20-barrage-fractional-motion-r1c-adapter-v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{ADAPTER_VERSION}] {message}")


def gate_head_diagnostics(
    state: np.ndarray,
    bed_elevation_m: np.ndarray,
    geometry: Mapping[str, np.ndarray],
    gate_face_ids: np.ndarray,
    barrage_upstream_cell_id: np.ndarray,
) -> dict[str, Any]:
    """Return full-barrage and worst local free-surface head differences."""

    values = np.asarray(state, dtype=np.float64)
    bed = np.asarray(bed_elevation_m, dtype=np.float64)
    faces = np.asarray(gate_face_ids, dtype=np.int64)
    upstream = np.asarray(barrage_upstream_cell_id, dtype=np.int64)
    downstream = base.downstream_cell_ids(geometry, faces, upstream)
    require(values.ndim == 2 and values.shape[1] == 3, "state shape is invalid")
    require(bed.shape == (len(values),), "bed shape is invalid")
    require(bool(np.isfinite(values).all()), "state contains non-finite values")
    require(bool(np.isfinite(bed).all()), "bed contains non-finite values")
    lengths = np.asarray(geometry["internalLengths"], dtype=np.float64)[faces]
    require(bool(np.all(np.isfinite(lengths) & (lengths > 0.0))), "face lengths are invalid")
    eta = values[:, 0] + bed
    upstream_head = eta[upstream]
    downstream_head = eta[downstream]
    local_difference = upstream_head - downstream_head
    weights = lengths / float(np.sum(lengths))
    weighted_upstream = float(np.sum(weights * upstream_head))
    weighted_downstream = float(np.sum(weights * downstream_head))
    return {
        "upstreamHeadM": weighted_upstream,
        "downstreamHeadM": weighted_downstream,
        "meanHeadDifferenceM": weighted_upstream - weighted_downstream,
        "minimumLocalHeadDifferenceM": float(np.min(local_difference)),
        "p05LocalHeadDifferenceM": float(np.percentile(local_difference, 5.0)),
        "maximumLocalHeadDifferenceM": float(np.max(local_difference)),
        "localHeadDifferenceM": local_difference,
        "selectedGateFaceCount": int(len(faces)),
    }


def validate_fractional_active_flux(
    signed_outward_discharge_m3_s: np.ndarray,
    gate_index_by_selected_face: np.ndarray,
    current_capacity_by_gate_id_1_to_8: np.ndarray,
    *,
    tolerance_m3_s: float,
) -> dict[str, Any]:
    """Reject adverse flux on any nonzero fractional-capacity gate face."""

    capacity = np.asarray(current_capacity_by_gate_id_1_to_8, dtype=np.float64)
    require(capacity.shape == (8,), "fractional capacity must contain eight gates")
    require(bool(np.isfinite(capacity).all()), "fractional capacity is non-finite")
    require(
        bool(np.all((capacity >= 0.0) & (capacity <= 1.0))),
        "fractional capacity must remain within 0..1",
    )
    return base.validate_active_outward_flux(
        signed_outward_discharge_m3_s,
        gate_index_by_selected_face,
        capacity,
        tolerance_m3_s=tolerance_m3_s,
    )
