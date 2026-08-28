#!/usr/bin/env python3
"""Isolated C1 candidate mapping for classified barrage faces.

This module adapts the approved continuous capacity law to the existing H2
diagnostic kernel without changing the protected binary v2 interface.  For a
gate-face length L, gate capacity alpha, and H2 width factor W, it supplies

    effective_length = L * (alpha * W + 1 - alpha)
    interface_multiplier = alpha * W / (alpha * W + 1 - alpha)

to the existing open/wall blend.  The resulting integrated face term is
exactly

    L * (alpha * W * F_open + (1 - alpha) * F_wall).

The separate binary reference in this file does not use the continuous
formula: an open gate instead receives multiplier 1 and length L * W, while a
closed gate receives multiplier 0 and length L.  That independence is used by
the mandatory pre-C1 endpoint fixture.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np


GATE_IDS = tuple(range(1, 9))
GATE_MARKER_BASE = 100
FIXED_MARKER = 200
EFFECTIVE_HYDRAULIC_WIDTH_M = 46.5


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_capacity_by_id(
    capacity_by_id: Mapping[str | int, float],
) -> dict[int, float]:
    """Return an exact 1..8 capacity map after strict domain validation."""

    _require(isinstance(capacity_by_id, Mapping), "capacity map must be a mapping")
    normalized: dict[int, float] = {}
    for raw_key, raw_value in capacity_by_id.items():
        _require(
            not isinstance(raw_key, bool),
            "boolean gate keys are not allowed",
        )
        try:
            gate = int(raw_key)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid gate key: {raw_key!r}") from error
        _require(str(gate) == str(raw_key), f"noncanonical gate key: {raw_key!r}")
        _require(gate in GATE_IDS, f"gate id outside 1..8: {gate}")
        _require(gate not in normalized, f"duplicate gate id: {gate}")
        _require(
            not isinstance(raw_value, (bool, np.bool_)),
            f"gate {gate} capacity must not be boolean",
        )
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"gate {gate} capacity is not numeric") from error
        _require(math.isfinite(value), f"gate {gate} capacity is not finite")
        _require(0.0 <= value <= 1.0, f"gate {gate} capacity outside 0..1")
        normalized[gate] = value
    _require(
        set(normalized) == set(GATE_IDS),
        "capacity map must contain exactly gates 1..8",
    )
    return normalized


def _face_arrays(
    geometry: Mapping[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    lengths = np.asarray(geometry["internalLengths"], dtype=np.float64)
    markers = np.asarray(geometry["internalMarkers"], dtype=np.int32)
    _require(lengths.ndim == 1, "internal lengths must be one-dimensional")
    _require(markers.shape == lengths.shape, "marker and length shapes differ")
    _require(
        np.isfinite(lengths).all() and np.all(lengths > 0.0),
        "internal lengths must be positive and finite",
    )
    # Other internal markers (currently P2 refinement lines 301/302) remain
    # ordinary transmissive faces.  Only 101..108 and 200 are hydraulic
    # structure roles in this candidate.
    return lengths, markers


def gate_bound_lengths_and_width_factors(
    geometry: Mapping[str, np.ndarray],
) -> tuple[dict[int, float], dict[int, float]]:
    """Recompute each gate's bound face length and exact H2 width factor."""

    lengths, markers = _face_arrays(geometry)
    bound_lengths: dict[int, float] = {}
    width_factors: dict[int, float] = {}
    for gate in GATE_IDS:
        selected = markers == GATE_MARKER_BASE + gate
        _require(np.any(selected), f"gate {gate} has no classified faces")
        bound = float(np.sum(lengths[selected], dtype=np.float64))
        _require(math.isfinite(bound) and bound > 0.0, f"gate {gate} bound length")
        bound_lengths[gate] = bound
        width_factors[gate] = EFFECTIVE_HYDRAULIC_WIDTH_M / bound
    return bound_lengths, width_factors


def _diagnostics(
    capacity: Mapping[int, float],
    bound_lengths: Mapping[int, float],
    width_factors: Mapping[int, float],
    effective_lengths: np.ndarray,
    multipliers: np.ndarray,
    markers: np.ndarray,
) -> dict[str, Any]:
    gate_rows: list[dict[str, Any]] = []
    for gate in GATE_IDS:
        alpha = float(capacity[gate])
        selected = markers == GATE_MARKER_BASE + gate
        effective_open_width = alpha * EFFECTIVE_HYDRAULIC_WIDTH_M
        wall_remainder_length = (1.0 - alpha) * bound_lengths[gate]
        gate_rows.append(
            {
                "gateId": gate,
                "capacityFraction": alpha,
                "classifiedFaceCount": int(np.sum(selected)),
                "boundMeshFaceLengthM": float(bound_lengths[gate]),
                "H2WidthFactor": float(width_factors[gate]),
                "effectiveOpenWidthM": effective_open_width,
                "wallRemainderLengthM": wall_remainder_length,
                "combinedKernelIntegrationLengthM": float(
                    np.sum(effective_lengths[selected], dtype=np.float64)
                ),
                "minimumKernelInterfaceMultiplier": float(
                    np.min(multipliers[selected])
                ),
                "maximumKernelInterfaceMultiplier": float(
                    np.max(multipliers[selected])
                ),
            }
        )
    return {
        "formula": (
            "L*(alpha*W*F_open+(1-alpha)*F_wall) represented as "
            "L*(alpha*W+1-alpha) times the existing open/wall blend"
        ),
        "effectiveHydraulicWidthMPerGate": EFFECTIVE_HYDRAULIC_WIDTH_M,
        "widthFactorApplicationCount": 1,
        "gates": gate_rows,
    }


def continuous_face_geometry(
    geometry: Mapping[str, np.ndarray],
    capacity_by_id: Mapping[str | int, float],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Map continuous capacities to isolated kernel lengths and multipliers."""

    capacity = validate_capacity_by_id(capacity_by_id)
    base_lengths, markers = _face_arrays(geometry)
    bound_lengths, width_factors = gate_bound_lengths_and_width_factors(geometry)
    effective_lengths = base_lengths.copy()
    multipliers = np.ones_like(base_lengths)
    multipliers[markers == FIXED_MARKER] = 0.0

    for gate in GATE_IDS:
        selected = markers == GATE_MARKER_BASE + gate
        alpha = capacity[gate]
        width_factor = width_factors[gate]
        combined = alpha * width_factor + (1.0 - alpha)
        _require(
            math.isfinite(combined) and combined > 0.0,
            f"gate {gate} invalid combined integration factor",
        )
        effective_lengths[selected] = base_lengths[selected] * combined
        multipliers[selected] = alpha * width_factor / combined

    _require(np.isfinite(effective_lengths).all(), "nonfinite effective length")
    _require(np.isfinite(multipliers).all(), "nonfinite interface multiplier")
    _require(
        np.all((multipliers >= 0.0) & (multipliers <= 1.0)),
        "interface multiplier outside 0..1",
    )
    return (
        effective_lengths,
        multipliers,
        _diagnostics(
            capacity,
            bound_lengths,
            width_factors,
            effective_lengths,
            multipliers,
            markers,
        ),
    )


def binary_width_enabled_face_geometry(
    geometry: Mapping[str, np.ndarray],
    open_gates: list[int] | tuple[int, ...] | set[int],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Construct an independent H2-width-enabled binary endpoint reference."""

    normalized_open: set[int] = set()
    for raw_gate in open_gates:
        _require(
            not isinstance(raw_gate, (bool, np.bool_)),
            "boolean gate ids are not allowed",
        )
        gate = int(raw_gate)
        _require(gate == raw_gate, f"non-integral gate id: {raw_gate!r}")
        _require(gate in GATE_IDS, f"gate id outside 1..8: {gate}")
        _require(gate not in normalized_open, f"duplicate open gate: {gate}")
        normalized_open.add(gate)

    base_lengths, markers = _face_arrays(geometry)
    bound_lengths, width_factors = gate_bound_lengths_and_width_factors(geometry)
    effective_lengths = base_lengths.copy()
    multipliers = np.ones_like(base_lengths)
    multipliers[markers == FIXED_MARKER] = 0.0
    capacity = {
        gate: 1.0 if gate in normalized_open else 0.0 for gate in GATE_IDS
    }

    for gate in GATE_IDS:
        selected = markers == GATE_MARKER_BASE + gate
        if gate in normalized_open:
            effective_lengths[selected] = (
                base_lengths[selected] * width_factors[gate]
            )
            multipliers[selected] = 1.0
        else:
            multipliers[selected] = 0.0

    return (
        effective_lengths,
        multipliers,
        _diagnostics(
            capacity,
            bound_lengths,
            width_factors,
            effective_lengths,
            multipliers,
            markers,
        ),
    )


def endpoint_array_comparison(
    geometry: Mapping[str, np.ndarray],
    open_gates: list[int] | tuple[int, ...] | set[int],
) -> dict[str, Any]:
    """Compare a continuous 0/1 endpoint with the independent binary form."""

    open_set = {int(gate) for gate in open_gates}
    capacity = {
        gate: 1.0 if gate in open_set else 0.0 for gate in GATE_IDS
    }
    continuous_lengths, continuous_multipliers, continuous_report = (
        continuous_face_geometry(geometry, capacity)
    )
    binary_lengths, binary_multipliers, binary_report = (
        binary_width_enabled_face_geometry(geometry, open_gates)
    )
    return {
        "lengthArraysExactlyEqual": bool(
            np.array_equal(continuous_lengths, binary_lengths)
        ),
        "multiplierArraysExactlyEqual": bool(
            np.array_equal(continuous_multipliers, binary_multipliers)
        ),
        "maximumAbsoluteLengthDifferenceM": float(
            np.max(np.abs(continuous_lengths - binary_lengths))
        ),
        "maximumAbsoluteMultiplierDifference": float(
            np.max(np.abs(continuous_multipliers - binary_multipliers))
        ),
        "continuous": continuous_report,
        "binaryReference": binary_report,
    }
