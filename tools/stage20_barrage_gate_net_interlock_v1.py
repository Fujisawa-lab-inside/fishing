#!/usr/bin/env python3
"""Pure gate-integrated reverse-flow interlock for Stage 20 diagnostics.

The interlock does not choose a physical operating margin.  It applies an
explicit per-gate minimum outward-net-flow margin supplied by a separately
reviewed control contract, records local adverse faces without clipping them,
and latches a gate closed when its integrated outward flow falls below that
margin.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


VERSION = "stage20-barrage-gate-net-interlock-v1"
GATE_COUNT = 8


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{VERSION}] {message}")


def _vector(values: Any, *, dtype: Any, shape: tuple[int, ...], label: str) -> np.ndarray:
    result = np.asarray(values, dtype=dtype)
    require(result.shape == shape, f"{label} shape mismatch")
    return result


def gate_net_diagnostics(
    signed_outward_face_discharge_m3_s: np.ndarray,
    gate_index_by_face: np.ndarray,
    effective_capacity_by_gate: np.ndarray,
) -> list[dict[str, Any]]:
    """Summarize local and integrated discharge without changing the flux."""

    values = np.asarray(signed_outward_face_discharge_m3_s, dtype=np.float64)
    indices = _vector(
        gate_index_by_face,
        dtype=np.int64,
        shape=values.shape,
        label="gate index",
    )
    capacity = _vector(
        effective_capacity_by_gate,
        dtype=np.float64,
        shape=(GATE_COUNT,),
        label="capacity",
    )
    require(values.ndim == 1 and len(values) > 0, "face discharge is required")
    require(bool(np.isfinite(values).all()), "face discharge contains non-finite values")
    require(bool(np.isfinite(capacity).all()), "capacity contains non-finite values")
    require(bool(np.all((0.0 <= capacity) & (capacity <= 1.0))), "capacity is outside [0, 1]")
    require(bool(np.all((0 <= indices) & (indices < GATE_COUNT))), "gate index is outside 0..7")

    rows: list[dict[str, Any]] = []
    for index in range(GATE_COUNT):
        selected = values[indices == index]
        active = bool(capacity[index] > 0.0)
        require(not active or len(selected) > 0, f"active gate {index + 1} has no faces")
        adverse = selected[selected < 0.0]
        positive = selected[selected > 0.0]
        adverse_rate = float(np.sum(-adverse)) if active else 0.0
        positive_rate = float(np.sum(positive)) if active else 0.0
        rows.append(
            {
                "gateId": index + 1,
                "active": active,
                "faceCount": int(len(selected)),
                "adverseFaceCount": int(len(adverse)) if active else 0,
                "minimumSignedOutwardFaceDischargeM3S": (
                    float(np.min(selected)) if active else None
                ),
                "gateNetSignedOutwardDischargeM3S": (
                    float(np.sum(selected)) if active else 0.0
                ),
                "localAdverseDischargeRateM3S": adverse_rate,
                "positiveDischargeRateM3S": positive_rate,
                "localAdverseToPositiveRateRatio": (
                    adverse_rate / positive_rate if active and positive_rate > 0.0 else 0.0
                ),
            }
        )
    return rows


def apply_gate_net_interlock(
    signed_outward_face_discharge_m3_s: np.ndarray,
    gate_index_by_face: np.ndarray,
    requested_capacity_by_gate: np.ndarray,
    latched_closed_by_gate: np.ndarray,
    minimum_outward_net_discharge_m3_s_by_gate: np.ndarray,
    *,
    comparison_tolerance_m3_s: float = 1.0e-10,
) -> dict[str, Any]:
    """Return an effective capacity after a fail-closed gate-net check.

    A positive minimum is a sensitivity parameter, not an adopted operating
    threshold.  Physical use requires independent evidence for that value.
    """

    requested = _vector(
        requested_capacity_by_gate,
        dtype=np.float64,
        shape=(GATE_COUNT,),
        label="requested capacity",
    )
    latched = _vector(
        latched_closed_by_gate,
        dtype=bool,
        shape=(GATE_COUNT,),
        label="latched state",
    ).copy()
    margin = _vector(
        minimum_outward_net_discharge_m3_s_by_gate,
        dtype=np.float64,
        shape=(GATE_COUNT,),
        label="minimum outward net discharge",
    )
    tolerance = float(comparison_tolerance_m3_s)
    require(bool(np.isfinite(requested).all()), "requested capacity is non-finite")
    require(bool(np.all((0.0 <= requested) & (requested <= 1.0))), "requested capacity is outside [0, 1]")
    require(bool(np.isfinite(margin).all()), "minimum outward net discharge is non-finite")
    require(bool(np.all(margin >= 0.0)), "minimum outward net discharge must be nonnegative")
    require(math.isfinite(tolerance) and tolerance >= 0.0, "comparison tolerance is invalid")

    effective_before = requested.copy()
    effective_before[latched] = 0.0
    rows = gate_net_diagnostics(
        signed_outward_face_discharge_m3_s,
        gate_index_by_face,
        effective_before,
    )
    trip_indices = np.asarray(
        [
            row["gateId"] - 1
            for row in rows
            if row["active"]
            and row["gateNetSignedOutwardDischargeM3S"]
            < margin[row["gateId"] - 1] - tolerance
        ],
        dtype=np.int64,
    )
    if len(trip_indices):
        latched[trip_indices] = True
    effective_after = requested.copy()
    effective_after[latched] = 0.0
    return {
        "version": VERSION,
        "requestedCapacityByGateId1To8": requested,
        "effectiveCapacityByGateId1To8": effective_after,
        "latchedClosedByGateId1To8": latched,
        "newTripGateIds": (trip_indices + 1).tolist(),
        "minimumOutwardNetDischargeM3SByGateId1To8": margin,
        "comparisonToleranceM3S": tolerance,
        "preInterlockGateDiagnostics": rows,
        "localAdverseFacesRecorded": True,
        "localAdverseFaceFluxClipped": False,
        "physicalOperatingMarginSelected": False,
    }
