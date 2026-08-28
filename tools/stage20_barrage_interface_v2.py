#!/usr/bin/env python3
"""Fail-closed Stage 20 barrage interface classification.

The eight numbered main gates are binary and individually addressable. The
fine-adjustment gate and fishway gate have separate controls. Fixed piers and
the fixed outer structure are permanent walls. The unresolved west segment has
its own fail-closed role: it is always disabled, but is not claimed to be a
permanent structure. This module is synthetic/code-only; it does not infer the
future mesh face assignment.
"""

from __future__ import annotations

import numpy as np


CONTRACT_VERSION = "stage20-barrage-interface-contract-v2"
ROLE_MAIN_GATE = 1
ROLE_FIXED_PIER = 2
ROLE_FIXED_OUTER_STRUCTURE = 3
ROLE_FINE_ADJUSTMENT_GATE = 4
ROLE_FISHWAY_GATE = 5
ROLE_RESERVED_DISABLED_UNKNOWN = 6
ROLE_NAMES = {
    ROLE_MAIN_GATE: "main_gate_1_through_8",
    ROLE_FIXED_PIER: "fixed_pier",
    ROLE_FIXED_OUTER_STRUCTURE: "fixed_outer_structure",
    ROLE_FINE_ADJUSTMENT_GATE: "fine_adjustment_gate",
    ROLE_FISHWAY_GATE: "fishway_gate",
    ROLE_RESERVED_DISABLED_UNKNOWN: "reserved_disabled_unknown",
}
PERMANENT_STRUCTURE_ROLES = frozenset({ROLE_FIXED_PIER, ROLE_FIXED_OUTER_STRUCTURE})
ALWAYS_ZERO_TRANSMISSIVITY_ROLES = frozenset({
    ROLE_FIXED_PIER,
    ROLE_FIXED_OUTER_STRUCTURE,
    ROLE_FISHWAY_GATE,
    ROLE_RESERVED_DISABLED_UNKNOWN,
})
MAIN_GATE_IDS = tuple(range(1, 9))
FORBIDDEN_UNIFORM_KEYS = {
    "barrageTransmissivity",
    "opening_fraction",
    "openingFraction",
    "uniformOpening",
    "uniformOpeningFraction",
    "scenario",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{CONTRACT_VERSION}] {message}")


def _binary(value: object, label: str) -> int:
    require(type(value) is int and value in (0, 1), f"{label} must be exact integer 0 or 1")
    return int(value)


def resolve_barrage_interface(
    *,
    internal_face_count: int,
    structure_face_ids: np.ndarray,
    structure_face_roles: np.ndarray,
    structure_main_gate_ids: np.ndarray,
    input_contract: dict,
) -> dict:
    """Validate the structure inventory and return per-internal-face controls."""

    count = int(internal_face_count)
    require(count > 0, "internal face count must be positive")
    face_ids = np.asarray(structure_face_ids)
    roles = np.asarray(structure_face_roles)
    gate_ids = np.asarray(structure_main_gate_ids)
    require(
        face_ids.ndim == roles.ndim == gate_ids.ndim == 1
        and len(face_ids) == len(roles) == len(gate_ids)
        and len(face_ids) > 0,
        "structure face arrays must be nonempty equal-length vectors",
    )
    require(np.issubdtype(face_ids.dtype, np.integer), "structure face ids must be integers")
    require(np.issubdtype(roles.dtype, np.integer), "structure roles must be integers")
    require(np.issubdtype(gate_ids.dtype, np.integer), "main gate ids must be integers")
    face_ids = face_ids.astype(np.int64, copy=False)
    roles = roles.astype(np.int64, copy=False)
    gate_ids = gate_ids.astype(np.int64, copy=False)
    require(np.all((face_ids >= 0) & (face_ids < count)), "structure face id out of range")
    require(len(np.unique(face_ids)) == len(face_ids), "duplicate structure face id")
    require(set(np.unique(roles)).issubset(ROLE_NAMES), "unknown structure role")
    require(ROLE_FIXED_PIER in roles, "at least one fixed-pier face is required")
    require(
        ROLE_FIXED_OUTER_STRUCTURE in roles,
        "at least one fixed-outer-structure face is required",
    )
    require(
        ROLE_RESERVED_DISABLED_UNKNOWN in roles,
        "at least one reserved-disabled-unknown face is required",
    )
    main_mask = roles == ROLE_MAIN_GATE
    require(np.all(gate_ids[main_mask] >= 1) and np.all(gate_ids[main_mask] <= 8),
            "main-gate faces require ids 1 through 8")
    require(set(np.unique(gate_ids[main_mask])) == set(MAIN_GATE_IDS),
            "main-gate face ids must cover exactly gates 1 through 8")
    require(np.all(gate_ids[~main_mask] == 0),
            "non-main-gate structure faces must use gate id 0")

    require(isinstance(input_contract, dict), "barrageInterface input object is required")
    forbidden = sorted(FORBIDDEN_UNIFORM_KEYS.intersection(input_contract))
    require(not forbidden, f"uniform/scenario barrage inputs are forbidden: {forbidden}")
    required_keys = {
        "mainGateOpenById",
        "fineAdjustmentGateOpen",
        "fishwayGateOpen",
    }
    require(set(input_contract) == required_keys,
            "barrageInterface keys must be exactly mainGateOpenById, "
            "fineAdjustmentGateOpen, fishwayGateOpen")
    main_states = input_contract["mainGateOpenById"]
    require(isinstance(main_states, dict), "mainGateOpenById must be an object")
    expected_gate_keys = {str(gate_id) for gate_id in MAIN_GATE_IDS}
    require(set(main_states) == expected_gate_keys,
            "mainGateOpenById keys must be exactly strings 1 through 8")
    normalised_main = {
        gate_id: _binary(main_states[str(gate_id)], f"main gate {gate_id}")
        for gate_id in MAIN_GATE_IDS
    }
    fine_state = _binary(input_contract["fineAdjustmentGateOpen"], "fine-adjustment gate")
    fishway_state = _binary(input_contract["fishwayGateOpen"], "fishway gate")
    fine_interface_classified = bool(np.any(roles == ROLE_FINE_ADJUSTMENT_GATE))
    fishway_interface_classified = bool(np.any(roles == ROLE_FISHWAY_GATE))
    require(
        fine_state == 0 or fine_interface_classified,
        "fine-adjustment gate cannot open without an exact classified interface",
    )
    require(
        fishway_state == 0 or fishway_interface_classified,
        "fishway gate cannot open without an exact classified interface",
    )

    multipliers = np.ones(count, dtype=np.float64)
    structure_multipliers = np.zeros(len(face_ids), dtype=np.float64)
    for index, role in enumerate(roles):
        if role == ROLE_MAIN_GATE:
            structure_multipliers[index] = normalised_main[int(gate_ids[index])]
        elif role == ROLE_FINE_ADJUSTMENT_GATE:
            structure_multipliers[index] = fine_state
        elif role in ALWAYS_ZERO_TRANSMISSIVITY_ROLES:
            # Fishway transfer is represented only by the separate conservative
            # head-driven source/sink pair. Keeping these cut faces at zero
            # prevents double counting through the main barrage interface. The
            # reserved-disabled-unknown role is also exactly zero, but unlike
            # the fixed-pier and fixed-outer roles it makes no permanent-
            # structure claim and has no opening input.
            structure_multipliers[index] = 0.0
        else:  # guarded above, kept as a defensive assertion
            raise AssertionError(role)
    multipliers[face_ids] = structure_multipliers
    require(np.isfinite(multipliers).all(), "nonfinite interface multiplier")

    return {
        "version": CONTRACT_VERSION,
        "mainGateOpenById": normalised_main,
        "fineAdjustmentGateOpen": fine_state,
        "fishwayGateOpen": fishway_state,
        "fineAdjustmentInterfaceClassified": fine_interface_classified,
        "fishwayInterfaceClassified": fishway_interface_classified,
        "fishwayTransferMultiplier": float(fishway_state),
        "internalFaceMultiplier": multipliers,
        "structureFaceMultiplier": structure_multipliers,
        "structureFaceIds": face_ids,
        "structureFaceRoles": roles,
        "structureMainGateIds": gate_ids,
        "fixedWallFaceCount": int(np.sum(np.isin(
            roles, tuple(PERMANENT_STRUCTURE_ROLES)
        ))),
        "permanentStructureFaceCount": int(np.sum(np.isin(
            roles, tuple(PERMANENT_STRUCTURE_ROLES)
        ))),
        "alwaysZeroTransmissivityFaceCount": int(np.sum(np.isin(
            roles, tuple(ALWAYS_ZERO_TRANSMISSIVITY_ROLES)
        ))),
        "reservedDisabledUnknownFaceCount": int(np.sum(
            roles == ROLE_RESERVED_DISABLED_UNKNOWN
        )),
        "reservedDisabledUnknownOpeningAllowed": False,
    }


def assert_no_scalar_barrage_input(fields: dict) -> None:
    require(isinstance(fields, dict), "fields object is required")
    forbidden = sorted(FORBIDDEN_UNIFORM_KEYS.intersection(fields))
    require(not forbidden, f"legacy scalar/uniform barrage fields are forbidden: {forbidden}")
