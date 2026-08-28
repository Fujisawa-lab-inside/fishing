#!/usr/bin/env python3
"""Numerically conservative micro-gate transfer primitive.

This module deliberately does not calculate a physical gate discharge.  It
only applies an externally authorised outward discharge to disjoint upstream
donor and downstream receiver cells with fail-closed numerical guards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


class MicroAdjustmentGateTransferError(RuntimeError):
    """Invalid input or failed numerical invariant."""


@dataclass(frozen=True)
class TransferSafety:
    reserve_depth_m: float
    maximum_available_volume_fraction_per_step: float
    adverse_head_shutdown_m: float


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MicroAdjustmentGateTransferError(
            f"[stage20-micro-adjustment-gate-transfer-v1] {message}"
        )


def _smoothstep01(value: float) -> float:
    x = min(max(float(value), 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def adverse_head_factor(
    head_difference_m: float,
    adverse_head_shutdown_m: float,
) -> float:
    """Return a C1-continuous outward-flow factor without selecting a Q law."""

    values = np.asarray(
        [head_difference_m, adverse_head_shutdown_m], dtype=np.float64
    )
    _require(np.isfinite(values).all(), "head inputs must be finite")
    _require(
        adverse_head_shutdown_m > 0.0,
        "adverse-head shutdown width must be positive",
    )
    tolerance = 1e-14 * max(
        1.0, abs(float(head_difference_m)), adverse_head_shutdown_m
    )
    if head_difference_m <= -adverse_head_shutdown_m + tolerance:
        return 0.0
    if head_difference_m >= -tolerance:
        return 1.0
    coordinate = (
        head_difference_m + adverse_head_shutdown_m
    ) / adverse_head_shutdown_m
    return float(_smoothstep01(coordinate))


def apply_authorized_outward_transfer(
    *,
    state_h_hu_hv: np.ndarray,
    cell_areas_m2: np.ndarray,
    upstream_donor_mask: np.ndarray,
    downstream_receiver_weights: np.ndarray,
    time_step_s: float,
    requested_outward_discharge_m3_s: float,
    head_difference_m: float,
    safety: TransferSafety,
) -> dict[str, Any]:
    """Apply an authorised Q; never infer Q from gate width or water level."""

    state = np.asarray(state_h_hu_hv, dtype=np.float64)
    areas = np.asarray(cell_areas_m2, dtype=np.float64)
    donors = np.asarray(upstream_donor_mask)
    receiver_weights = np.asarray(
        downstream_receiver_weights, dtype=np.float64
    )
    _require(
        state.ndim == 2 and state.shape[1] == 3,
        "state must have shape [cell, 3]",
    )
    cell_count = state.shape[0]
    _require(
        areas.shape == (cell_count,)
        and donors.shape == (cell_count,)
        and receiver_weights.shape == (cell_count,),
        "cell arrays do not match state",
    )
    _require(
        donors.dtype == np.bool_, "upstream donor mask must be boolean"
    )
    scalar_values = np.asarray(
        [
            time_step_s,
            requested_outward_discharge_m3_s,
            head_difference_m,
            safety.reserve_depth_m,
            safety.maximum_available_volume_fraction_per_step,
            safety.adverse_head_shutdown_m,
        ],
        dtype=np.float64,
    )
    _require(
        np.isfinite(state).all()
        and np.isfinite(areas).all()
        and np.isfinite(receiver_weights).all()
        and np.isfinite(scalar_values).all(),
        "all numerical inputs must be finite",
    )
    _require(np.all(state[:, 0] >= 0.0), "negative depth is forbidden")
    _require(np.all(areas > 0.0), "cell areas must be positive")
    _require(np.any(donors), "at least one upstream donor is required")
    _require(
        time_step_s > 0.0
        and requested_outward_discharge_m3_s >= 0.0
        and safety.reserve_depth_m >= 0.0
        and 0.0 < safety.maximum_available_volume_fraction_per_step <= 1.0,
        "invalid discharge, time step, or safety parameter",
    )
    _require(
        np.all(receiver_weights >= 0.0)
        and abs(float(np.sum(receiver_weights)) - 1.0) <= 1e-12,
        "downstream receiver weights must be nonnegative and sum to one",
    )
    _require(
        not np.any(receiver_weights[donors] > 0.0),
        "donor and receiver support must be disjoint",
    )

    factor = adverse_head_factor(
        float(head_difference_m), safety.adverse_head_shutdown_m
    )
    head_limited_request = requested_outward_discharge_m3_s * factor
    depth = state[:, 0]
    available_by_cell = np.where(
        donors,
        areas * np.maximum(depth - safety.reserve_depth_m, 0.0),
        0.0,
    )
    available_volume = float(np.sum(available_by_cell))
    safety_discharge = (
        safety.maximum_available_volume_fraction_per_step
        * available_volume
        / time_step_s
    )
    effective_discharge = min(head_limited_request, safety_discharge)

    donor_rate = np.zeros(cell_count, dtype=np.float64)
    if effective_discharge > 0.0:
        _require(
            available_volume > 0.0,
            "positive transfer requested without available donor water",
        )
        donor_rate = effective_discharge * available_by_cell / available_volume
    receiver_rate = effective_discharge * receiver_weights
    mass_rate = receiver_rate - donor_rate

    safe_depth = np.maximum(depth, 1e-12)
    hu_rate = -donor_rate * state[:, 1] / safe_depth
    hv_rate = -donor_rate * state[:, 2] / safe_depth
    post_depth = depth + time_step_s * mass_rate / areas
    removed_fraction = np.zeros(cell_count, dtype=np.float64)
    selected = donor_rate > 0.0
    removed_fraction[selected] = (
        time_step_s * donor_rate[selected] / available_by_cell[selected]
    )
    mass_residual = float(np.sum(mass_rate))

    _require(abs(mass_residual) <= 1e-12, "mass residual exceeds 1e-12 m3/s")
    _require(np.min(post_depth) >= -1e-12, "transfer creates negative depth")
    _require(
        float(np.max(removed_fraction))
        <= safety.maximum_available_volume_fraction_per_step + 1e-12,
        "donor removal exceeds the per-step safety fraction",
    )
    _require(
        np.isfinite(mass_rate).all()
        and np.isfinite(hu_rate).all()
        and np.isfinite(hv_rate).all()
        and np.isfinite(post_depth).all(),
        "transfer output contains non-finite values",
    )

    if factor == 0.0:
        limitation = "adverse_head_shutdown"
    elif effective_discharge < head_limited_request - 1e-15:
        limitation = "donor_available_volume_safety"
    elif factor < 1.0:
        limitation = "adverse_head_transition"
    else:
        limitation = "external_authorized_discharge"

    return {
        "massRateM3SByCell": mass_rate,
        "horizontalMomentumRateXByCell": hu_rate,
        "horizontalMomentumRateYByCell": hv_rate,
        "postSourceDepthM": np.maximum(post_depth, 0.0),
        "diagnostics": {
            "requestedOutwardDischargeM3S": float(
                requested_outward_discharge_m3_s
            ),
            "effectiveOutwardDischargeM3S": float(effective_discharge),
            "headDifferenceM": float(head_difference_m),
            "adverseHeadFactor": float(factor),
            "availableDonorVolumeM3": available_volume,
            "availableVolumeSafetyDischargeM3S": float(safety_discharge),
            "limitation": limitation,
            "massResidualM3S": mass_residual,
            "maximumAvailableVolumeFractionRemoved": float(
                np.max(removed_fraction)
            ),
            "minimumPostSourceDepthM": float(np.min(post_depth)),
            "receiverHorizontalMomentumAdded": 0.0,
            "donorMomentumRemovedWithWithdrawnMass": True,
            "flowDirection": "upstream_to_downstream_only",
            "physicalDischargeLawImplemented": False,
            "requestedDischargeAuthorityExternal": True,
            "gateWidthUsedToInferDischarge": False,
        },
    }
