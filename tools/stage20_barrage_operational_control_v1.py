#!/usr/bin/env python3
"""Fail-closed operational barrage control contract.

An open barrage gate is not a hydraulic check valve.  Reverse salt-water flow
is prevented operationally by closing the gates before the downstream head can
drive an adverse discharge.  This module resolves a requested gate schedule
against fresh head observations and an explicit flood-release authority.  It
also provides the numerical post-condition used to reject any adverse gate
flux; it never clips adverse flux into a seemingly valid result.
"""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np


CONTRACT_VERSION = "stage20-barrage-operational-control-v1"
CONTROL_SCHEMA = "onga-stage20-barrage-operational-control-command-v1"
NORMAL_TIDAL = "normal_tidal"
FLOOD_RELEASE = "flood_release"
MODES = frozenset({NORMAL_TIDAL, FLOOD_RELEASE})
MAIN_GATE_IDS = tuple(range(1, 9))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{CONTRACT_VERSION}] {message}")


def _finite(value: object, label: str) -> float:
    number = float(value)
    require(math.isfinite(number), f"{label} must be finite")
    return number


def _binary(value: object, label: str) -> int:
    require(type(value) is int and value in (0, 1), f"{label} must be exact integer 0 or 1")
    return int(value)


def _validate_requested_interface(requested: Mapping[str, object]) -> dict[str, object]:
    require(isinstance(requested, Mapping), "requested barrage interface is required")
    required = {"mainGateOpenById", "fineAdjustmentGateOpen", "fishwayGateOpen"}
    require(set(requested) == required, "requested barrage interface keys are invalid")
    main = requested["mainGateOpenById"]
    require(isinstance(main, Mapping), "mainGateOpenById must be an object")
    expected = {str(gate_id) for gate_id in MAIN_GATE_IDS}
    require(set(main) == expected, "mainGateOpenById must contain strings 1 through 8")
    return {
        "mainGateOpenById": {
            str(gate_id): _binary(main[str(gate_id)], f"main gate {gate_id}")
            for gate_id in MAIN_GATE_IDS
        },
        "fineAdjustmentGateOpen": _binary(
            requested["fineAdjustmentGateOpen"], "fine-adjustment gate"
        ),
        "fishwayGateOpen": _binary(requested["fishwayGateOpen"], "fishway gate"),
    }


def resolve_operational_gate_command(
    *,
    requested_interface: Mapping[str, object],
    operational_control: Mapping[str, object],
    upstream_head_m: object,
    downstream_head_m: object,
) -> dict[str, object]:
    """Return a fail-closed effective interface and a traceable decision."""

    requested = _validate_requested_interface(requested_interface)
    require(isinstance(operational_control, Mapping), "operational control is required")
    required = {
        "schema",
        "mode",
        "minimumOutwardHeadMarginM",
        "headObservationAgeS",
        "maximumHeadObservationAgeS",
        "floodReleaseAuthorized",
        "authorizationId",
    }
    require(set(operational_control) == required, "operational control keys are invalid")
    require(operational_control["schema"] == CONTROL_SCHEMA, "operational schema mismatch")
    mode = str(operational_control["mode"])
    require(mode in MODES, "mode must be normal_tidal or flood_release")
    margin = _finite(
        operational_control["minimumOutwardHeadMarginM"],
        "minimum outward head margin",
    )
    observation_age = _finite(
        operational_control["headObservationAgeS"], "head observation age"
    )
    maximum_age = _finite(
        operational_control["maximumHeadObservationAgeS"],
        "maximum head observation age",
    )
    require(margin >= 0.0, "minimum outward head margin must be nonnegative")
    require(observation_age >= 0.0, "head observation age must be nonnegative")
    require(maximum_age > 0.0, "maximum head observation age must be positive")
    flood_authorized = operational_control["floodReleaseAuthorized"]
    require(type(flood_authorized) is bool, "floodReleaseAuthorized must be boolean")
    authorization_id = operational_control["authorizationId"]
    require(authorization_id is None or isinstance(authorization_id, str), "authorizationId is invalid")
    if isinstance(authorization_id, str):
        require(len(authorization_id.strip()) > 0, "authorizationId cannot be empty")

    upstream = _finite(upstream_head_m, "upstream head")
    downstream = _finite(downstream_head_m, "downstream head")
    head_difference = upstream - downstream
    observation_fresh = observation_age <= maximum_age
    outward_head_safe = head_difference > margin
    flood_authority_valid = (
        mode != FLOOD_RELEASE
        or (flood_authorized is True and isinstance(authorization_id, str))
    )
    opening_allowed = observation_fresh and outward_head_safe and flood_authority_valid

    if not observation_fresh:
        classification = "INTERLOCK_CLOSED_STALE_HEAD_OBSERVATION"
    elif not outward_head_safe:
        classification = "INTERLOCK_CLOSED_ADVERSE_OR_INSUFFICIENT_HEAD"
    elif not flood_authority_valid:
        classification = "INTERLOCK_CLOSED_FLOOD_AUTHORITY_MISSING"
    else:
        classification = (
            "FLOOD_RELEASE_OPENING_ALLOWED"
            if mode == FLOOD_RELEASE
            else "NORMAL_OUTWARD_RELEASE_ALLOWED"
        )

    effective_main = {
        key: value if opening_allowed else 0
        for key, value in requested["mainGateOpenById"].items()
    }
    effective = {
        "mainGateOpenById": effective_main,
        "fineAdjustmentGateOpen": (
            requested["fineAdjustmentGateOpen"] if opening_allowed else 0
        ),
        # The fishway uses a separate head-driven conservative link with its
        # own adverse-head shutdown.  Do not silently rewrite that control.
        "fishwayGateOpen": requested["fishwayGateOpen"],
    }
    return {
        "version": CONTRACT_VERSION,
        "classification": classification,
        "mode": mode,
        "openingAllowed": opening_allowed,
        "observationFresh": observation_fresh,
        "outwardHeadSafe": outward_head_safe,
        "floodAuthorityValid": flood_authority_valid,
        "upstreamHeadM": upstream,
        "downstreamHeadM": downstream,
        "headDifferenceM": head_difference,
        "minimumOutwardHeadMarginM": margin,
        "requestedOpenMainGateCount": int(sum(requested["mainGateOpenById"].values())),
        "effectiveOpenMainGateCount": int(sum(effective_main.values())),
        "requestedInterface": requested,
        "effectiveInterface": effective,
        "reverseFlowPermitted": False,
        "openGateIsModelledAsOneWayValve": False,
        "closureIsOperationalControlAction": True,
        "physicalGateMotionLagRepresented": False,
        "floodReleaseAuthorizationId": authorization_id if mode == FLOOD_RELEASE else None,
    }


def validate_outward_gate_flux(
    signed_outward_discharge_m3_s: np.ndarray,
    *,
    tolerance_m3_s: float = 1.0e-10,
) -> dict[str, float | int | bool]:
    """Reject adverse numerical gate flux instead of clipping or hiding it."""

    values = np.asarray(signed_outward_discharge_m3_s, dtype=np.float64)
    require(values.ndim == 1 and len(values) > 0, "gate discharge vector is required")
    require(np.isfinite(values).all(), "gate discharge vector contains non-finite values")
    tolerance = _finite(tolerance_m3_s, "gate reverse-flow tolerance")
    require(tolerance >= 0.0, "gate reverse-flow tolerance must be nonnegative")
    adverse = values < -tolerance
    require(
        not np.any(adverse),
        "adverse barrage discharge detected; result rejected without clipping",
    )
    return {
        "reverseFlowPermitted": False,
        "adverseFaceCount": 0,
        "minimumSignedOutwardDischargeM3S": float(np.min(values)),
        "totalSignedOutwardDischargeM3S": float(np.sum(values)),
        "toleranceM3S": tolerance,
    }
