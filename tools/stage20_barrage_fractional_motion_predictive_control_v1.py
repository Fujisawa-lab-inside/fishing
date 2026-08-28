#!/usr/bin/env python3
"""Rate-limited, predictive main-gate control for the Onga River barrage.

This module is intentionally independent from the shallow-water solver.  It
turns a requested eight-gate capacity vector into a bounded actuator target,
using separate opening/closing head margins and a conservative look-ahead.

Safety semantics are fail closed:

* missing, stale, or short-horizon observations cannot open a gate;
* an already moving/open gate starts closing when the live or forecast margin
  is no longer safe;
* a closing gate must reach zero before it can re-arm;
* motion is rate limited instead of changing from zero to one instantly.

The hydrodynamic adapter must still reject adverse active-face discharge.  A
head forecast is an anticipatory control input, not a substitute for that
numerical post-condition.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np


CONTRACT_VERSION = "stage20-barrage-fractional-motion-predictive-control-v1"
POLICY_SCHEMA = "onga-stage20-barrage-fractional-motion-policy-v1"
MAIN_GATE_COUNT = 8


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{CONTRACT_VERSION}] {message}")


def _finite(value: object, label: str) -> float:
    require(not isinstance(value, (bool, np.bool_)), f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"[{CONTRACT_VERSION}] {label} must be numeric") from error
    require(math.isfinite(number), f"{label} must be finite")
    return number


def _optional_finite(value: object | None, label: str) -> float | None:
    if value is None:
        return None
    return _finite(value, label)


def _capacity_vector(value: object, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    require(result.shape == (MAIN_GATE_COUNT,), f"{label} must contain eight gates")
    require(bool(np.isfinite(result).all()), f"{label} contains non-finite values")
    require(
        bool(np.all((result >= 0.0) & (result <= 1.0))),
        f"{label} must remain within 0..1",
    )
    return result.copy()


def validate_policy(policy: Mapping[str, object]) -> dict[str, float | str]:
    """Normalize a strict policy without assigning real-world parameter truth."""

    require(isinstance(policy, Mapping), "motion policy is required")
    required = {
        "schema",
        "openingHeadMarginM",
        "closingHeadMarginM",
        "forecastUncertaintyM",
        "maximumHeadObservationAgeS",
        "maximumForecastAgeS",
        "requiredForecastCoverageS",
        "openingSafeDwellSeconds",
        "fullOpeningStrokeSeconds",
        "fullClosingStrokeSeconds",
        "capacityZeroTolerance",
    }
    require(set(policy) == required, "motion policy keys are invalid")
    require(policy["schema"] == POLICY_SCHEMA, "motion policy schema mismatch")

    opening_margin = _finite(policy["openingHeadMarginM"], "opening head margin")
    closing_margin = _finite(policy["closingHeadMarginM"], "closing head margin")
    uncertainty = _finite(policy["forecastUncertaintyM"], "forecast uncertainty")
    maximum_head_age = _finite(
        policy["maximumHeadObservationAgeS"], "maximum head observation age"
    )
    maximum_forecast_age = _finite(
        policy["maximumForecastAgeS"], "maximum forecast age"
    )
    required_coverage = _finite(
        policy["requiredForecastCoverageS"], "required forecast coverage"
    )
    dwell = _finite(policy["openingSafeDwellSeconds"], "opening safe dwell")
    opening_stroke = _finite(
        policy["fullOpeningStrokeSeconds"], "full opening stroke"
    )
    closing_stroke = _finite(
        policy["fullClosingStrokeSeconds"], "full closing stroke"
    )
    zero_tolerance = _finite(
        policy["capacityZeroTolerance"], "capacity zero tolerance"
    )

    require(closing_margin >= 0.0, "closing head margin must be nonnegative")
    require(
        opening_margin > closing_margin,
        "opening head margin must be greater than closing head margin",
    )
    require(uncertainty >= 0.0, "forecast uncertainty must be nonnegative")
    require(maximum_head_age > 0.0, "maximum head observation age must be positive")
    require(maximum_forecast_age > 0.0, "maximum forecast age must be positive")
    require(dwell >= 0.0, "opening safe dwell must be nonnegative")
    require(opening_stroke > 0.0, "full opening stroke must be positive")
    require(closing_stroke > 0.0, "full closing stroke must be positive")
    require(
        required_coverage + 1.0e-12 >= closing_stroke,
        "forecast coverage must span at least the full closing stroke",
    )
    require(
        0.0 <= zero_tolerance < 1.0e-6,
        "capacity zero tolerance must be nonnegative and smaller than 1e-6",
    )
    return {
        "schema": POLICY_SCHEMA,
        "openingHeadMarginM": opening_margin,
        "closingHeadMarginM": closing_margin,
        "forecastUncertaintyM": uncertainty,
        "maximumHeadObservationAgeS": maximum_head_age,
        "maximumForecastAgeS": maximum_forecast_age,
        "requiredForecastCoverageS": required_coverage,
        "openingSafeDwellSeconds": dwell,
        "fullOpeningStrokeSeconds": opening_stroke,
        "fullClosingStrokeSeconds": closing_stroke,
        "capacityZeroTolerance": zero_tolerance,
    }


def initial_controller_state() -> dict[str, object]:
    """Return the canonical closed and unarmed main-gate state."""

    return {
        "capacityByGateId1To8": [0.0] * MAIN_GATE_COUNT,
        "openingIntent": False,
        "continuousOpeningEligibleDurationS": 0.0,
    }


def validate_controller_state(state: Mapping[str, object]) -> dict[str, object]:
    require(isinstance(state, Mapping), "controller state is required")
    required = {
        "capacityByGateId1To8",
        "openingIntent",
        "continuousOpeningEligibleDurationS",
    }
    require(set(state) == required, "controller state keys are invalid")
    capacity = _capacity_vector(
        state["capacityByGateId1To8"], "controller capacity"
    )
    opening_intent = state["openingIntent"]
    require(type(opening_intent) is bool, "openingIntent must be boolean")
    dwell = _finite(
        state["continuousOpeningEligibleDurationS"],
        "continuous opening eligible duration",
    )
    require(dwell >= 0.0, "continuous opening eligible duration must be nonnegative")
    return {
        "capacityByGateId1To8": capacity,
        "openingIntent": opening_intent,
        "continuousOpeningEligibleDurationS": dwell,
    }


def resolve_motion_target(
    *,
    requested_capacity_by_gate_id_1_to_8: object,
    controller_state: Mapping[str, object],
    mean_head_difference_m: object | None,
    minimum_local_head_difference_m: object | None,
    head_observation_age_s: object | None,
    predicted_minimum_control_head_difference_m: object | None,
    forecast_age_s: object | None,
    forecast_remaining_coverage_s: object | None,
    policy: Mapping[str, object],
) -> dict[str, Any]:
    """Resolve the next actuator target from live and predicted conditions.

    ``predicted_minimum_control_head_difference_m`` must already be the
    conservative minimum over the relevant gate faces and the stated remaining
    horizon.  The policy uncertainty is subtracted once more here.
    """

    normalized_policy = validate_policy(policy)
    state = validate_controller_state(controller_state)
    requested = _capacity_vector(
        requested_capacity_by_gate_id_1_to_8, "requested capacity"
    )
    current = np.asarray(state["capacityByGateId1To8"], dtype=np.float64)
    zero_tolerance = float(normalized_policy["capacityZeroTolerance"])
    requested_open = bool(np.any(requested > zero_tolerance))
    current_open = bool(np.any(current > zero_tolerance))
    opening_intent_before = bool(state["openingIntent"])
    dwell = float(state["continuousOpeningEligibleDurationS"])

    mean_head = _optional_finite(mean_head_difference_m, "mean head difference")
    local_head = _optional_finite(
        minimum_local_head_difference_m, "minimum local head difference"
    )
    head_age = _optional_finite(head_observation_age_s, "head observation age")
    forecast_minimum = _optional_finite(
        predicted_minimum_control_head_difference_m,
        "predicted minimum control head difference",
    )
    forecast_age = _optional_finite(forecast_age_s, "forecast age")
    forecast_coverage = _optional_finite(
        forecast_remaining_coverage_s, "forecast remaining coverage"
    )
    if head_age is not None:
        require(head_age >= 0.0, "head observation age must be nonnegative")
    if forecast_age is not None:
        require(forecast_age >= 0.0, "forecast age must be nonnegative")
    if forecast_coverage is not None:
        require(forecast_coverage >= 0.0, "forecast coverage must be nonnegative")

    head_present = mean_head is not None and local_head is not None and head_age is not None
    head_fresh = bool(
        head_present
        and head_age <= float(normalized_policy["maximumHeadObservationAgeS"])
    )
    control_head = (
        min(float(mean_head), float(local_head)) if head_present else None
    )
    forecast_present = (
        forecast_minimum is not None
        and forecast_age is not None
        and forecast_coverage is not None
    )
    forecast_fresh = bool(
        forecast_present
        and forecast_age <= float(normalized_policy["maximumForecastAgeS"])
    )
    forecast_long_enough = bool(
        forecast_present
        and forecast_coverage
        + 1.0e-12
        >= float(normalized_policy["requiredForecastCoverageS"])
    )
    conservative_forecast_minimum = (
        float(forecast_minimum) - float(normalized_policy["forecastUncertaintyM"])
        if forecast_minimum is not None
        else None
    )

    opening_margin = float(normalized_policy["openingHeadMarginM"])
    closing_margin = float(normalized_policy["closingHeadMarginM"])
    live_open_safe = bool(
        head_fresh and control_head is not None and control_head > opening_margin
    )
    live_hold_safe = bool(
        head_fresh and control_head is not None and control_head > closing_margin
    )
    forecast_hold_safe = bool(
        forecast_fresh
        and forecast_long_enough
        and conservative_forecast_minimum is not None
        and conservative_forecast_minimum > closing_margin
    )

    opening_intent = False
    opening_eligible = False
    if not requested_open:
        classification = "REQUESTED_CLOSED"
    elif not head_present:
        classification = "INTERLOCK_CLOSING_MISSING_LIVE_HEAD"
    elif not head_fresh:
        classification = "INTERLOCK_CLOSING_STALE_LIVE_HEAD"
    elif not forecast_present:
        classification = "INTERLOCK_CLOSING_MISSING_FORECAST"
    elif not forecast_fresh:
        classification = "INTERLOCK_CLOSING_STALE_FORECAST"
    elif not forecast_long_enough:
        classification = "INTERLOCK_CLOSING_FORECAST_COVERAGE_TOO_SHORT"
    elif opening_intent_before:
        if not live_hold_safe:
            classification = "PREDICTIVE_CLOSING_LIVE_HEAD_BELOW_CLOSE_MARGIN"
        elif not forecast_hold_safe:
            classification = "PREDICTIVE_CLOSING_FORECAST_BELOW_CLOSE_MARGIN"
        else:
            opening_intent = True
            classification = "OPENING_INTENT_HELD_WITHIN_HYSTERESIS"
    elif current_open:
        classification = "INTERLOCK_CLOSING_REARM_ONLY_AFTER_FULL_CLOSURE"
    elif not live_open_safe:
        classification = "INTERLOCK_CLOSED_BELOW_OPEN_MARGIN"
    elif not forecast_hold_safe:
        classification = "INTERLOCK_CLOSED_FORECAST_BELOW_CLOSE_MARGIN"
    else:
        opening_eligible = True
        if dwell + 1.0e-12 < float(normalized_policy["openingSafeDwellSeconds"]):
            classification = "INTERLOCK_CLOSED_OPENING_SAFE_DWELL"
        else:
            opening_intent = True
            classification = "FRACTIONAL_OPENING_ALLOWED"

    target = requested.copy() if opening_intent else np.zeros(MAIN_GATE_COUNT)
    return {
        "version": CONTRACT_VERSION,
        "classification": classification,
        "openingIntent": opening_intent,
        "openingEligible": opening_eligible,
        "requestedCapacityByGateId1To8": requested,
        "currentCapacityByGateId1To8": current,
        "targetCapacityByGateId1To8": target,
        "currentCapacityIsFullyClosed": not current_open,
        "headObservationPresent": head_present,
        "headObservationFresh": head_fresh,
        "forecastPresent": forecast_present,
        "forecastFresh": forecast_fresh,
        "forecastCoverageSufficientForFullClosure": forecast_long_enough,
        "meanHeadDifferenceM": mean_head,
        "minimumLocalHeadDifferenceM": local_head,
        "controlHeadDifferenceM": control_head,
        "predictedMinimumControlHeadDifferenceM": forecast_minimum,
        "conservativePredictedMinimumControlHeadDifferenceM": (
            conservative_forecast_minimum
        ),
        "openingHeadMarginM": opening_margin,
        "closingHeadMarginM": closing_margin,
        "continuousOpeningEligibleDurationS": dwell,
        "physicalGateMotionLagRepresented": True,
        "reverseFlowPermitted": False,
        "adverseFluxMustBeRejectedWithoutClipping": True,
    }


def advance_fractional_capacity(
    current_capacity_by_gate_id_1_to_8: object,
    target_capacity_by_gate_id_1_to_8: object,
    *,
    elapsed_seconds: object,
    full_opening_stroke_seconds: object,
    full_closing_stroke_seconds: object,
) -> np.ndarray:
    """Advance every gate without exceeding the opening or closing slew rate."""

    current = _capacity_vector(current_capacity_by_gate_id_1_to_8, "current capacity")
    target = _capacity_vector(target_capacity_by_gate_id_1_to_8, "target capacity")
    elapsed = _finite(elapsed_seconds, "motion elapsed seconds")
    opening_stroke = _finite(full_opening_stroke_seconds, "full opening stroke")
    closing_stroke = _finite(full_closing_stroke_seconds, "full closing stroke")
    require(elapsed >= 0.0, "motion elapsed seconds must be nonnegative")
    require(opening_stroke > 0.0, "full opening stroke must be positive")
    require(closing_stroke > 0.0, "full closing stroke must be positive")
    opening_step = elapsed / opening_stroke
    closing_step = elapsed / closing_stroke
    result = current.copy()
    opening = target > current
    closing = target < current
    result[opening] = np.minimum(target[opening], current[opening] + opening_step)
    result[closing] = np.maximum(target[closing], current[closing] - closing_step)
    require(bool(np.all((result >= 0.0) & (result <= 1.0))), "motion left 0..1")
    return result


def advance_controller_state(
    *,
    controller_state: Mapping[str, object],
    decision: Mapping[str, object],
    elapsed_seconds: object,
    policy: Mapping[str, object],
) -> dict[str, object]:
    """Advance actuator capacity after one solver interval.

    The solver should use and validate the *current* capacity for its interval,
    then call this function with the accepted interval length.  The returned
    capacity is used on the next interval.  This avoids pretending to know the
    CFL-limited step length before the hydrodynamic step is accepted.
    """

    normalized_policy = validate_policy(policy)
    state = validate_controller_state(controller_state)
    require(isinstance(decision, Mapping), "motion decision is required")
    require(decision.get("version") == CONTRACT_VERSION, "motion decision version mismatch")
    opening_intent = decision.get("openingIntent")
    opening_eligible = decision.get("openingEligible")
    require(type(opening_intent) is bool, "decision openingIntent must be boolean")
    require(type(opening_eligible) is bool, "decision openingEligible must be boolean")
    target = _capacity_vector(
        decision.get("targetCapacityByGateId1To8"), "decision target capacity"
    )
    elapsed = _finite(elapsed_seconds, "controller elapsed seconds")
    require(elapsed >= 0.0, "controller elapsed seconds must be nonnegative")
    current = np.asarray(state["capacityByGateId1To8"], dtype=np.float64)
    next_capacity = advance_fractional_capacity(
        current,
        target,
        elapsed_seconds=elapsed,
        full_opening_stroke_seconds=normalized_policy["fullOpeningStrokeSeconds"],
        full_closing_stroke_seconds=normalized_policy["fullClosingStrokeSeconds"],
    )
    zero_tolerance = float(normalized_policy["capacityZeroTolerance"])
    current_or_next_open = bool(
        np.any(current > zero_tolerance) or np.any(next_capacity > zero_tolerance)
    )
    if opening_intent or current_or_next_open:
        next_dwell = 0.0
    elif opening_eligible:
        next_dwell = (
            float(state["continuousOpeningEligibleDurationS"]) + elapsed
        )
    else:
        next_dwell = 0.0
    return {
        "capacityByGateId1To8": next_capacity.tolist(),
        "openingIntent": opening_intent,
        "continuousOpeningEligibleDurationS": next_dwell,
    }
