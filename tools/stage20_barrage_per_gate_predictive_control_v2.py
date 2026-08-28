#!/usr/bin/env python3
"""Per-gate, rate-limited predictive control for the Onga River barrage.

This local-only successor keeps the v1 call vocabulary while making the eight
main gates independent.  Every gate has its own current opening, target,
opening intent, safe-head dwell, live head, forecast head, and operation-order
diagnostics.  A missing or unsafe input closes the affected gate; a structural
contract error raises instead of guessing.

Positive motion additionally requires a SHA-bound package from the verified
R1C observation adapter.  Plain scalar or eight-vector arguments remain useful
for diagnostics but cannot open or hold a gate.  Controller states are sealed
and origin-labelled: initial/manual observations clear intent and dwell, while
only an accepted advance carries a parent-state/source-decision hash chain.

The hydraulic calculation in this module is deliberately diagnostic.  It is
an explicit, testable orifice-like relationship, not a calibrated description
of the real barrage::

    capacity = opening ** p
    Q_signed = sign(H) * Cd * A_full * capacity * sqrt(2 * g * abs(H))

All parameters must be supplied under an exact ``DIAGNOSTIC_PROVISIONAL``
label.  Negative potential discharge is preserved as an adverse-flow warning;
it is never clipped into a valid outward result.  The hydrodynamic adapter must
still reject adverse active-face flux.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import numpy as np


CONTRACT_VERSION = "stage20-barrage-per-gate-predictive-control-v2"
POLICY_SCHEMA = "onga-stage20-barrage-per-gate-predictive-policy-v2"
STATE_SCHEMA = "onga-stage20-barrage-per-gate-predictive-state-v2"
HYDRAULIC_MODEL_SCHEMA = (
    "onga-stage20-barrage-diagnostic-provisional-hydraulics-v2"
)
LEGACY_POLICY_SCHEMA = "onga-stage20-barrage-fractional-motion-policy-v1"
DIAGNOSTIC_PROVISIONAL = (
    "DIAGNOSTIC_PROVISIONAL_NOT_PHYSICALLY_OR_OPERATIONALLY_CALIBRATED"
)
HYDRAULIC_EQUATION = (
    "Q_signed=sign(H)*Cd*A_full*opening^p*sqrt(2*g*abs(H))"
)
MAIN_GATE_COUNT = 8
MAIN_GATE_IDS = tuple(range(1, MAIN_GATE_COUNT + 1))
DEFAULT_OPENING_ORDER = (5, 4, 6, 3, 7, 2, 8, 1)
DEFAULT_CLOSING_ORDER = tuple(reversed(DEFAULT_OPENING_ORDER))
MOTION_ORDERS = frozenset({"OPEN", "CLOSE", "HOLD", "FAIL_CLOSED"})
DECISION_INPUT_SCHEMA = "onga-stage20-barrage-per-gate-decision-inputs-v2"
POSITIVE_MOTION_EVIDENCE_SCHEMA = (
    "onga-stage20-barrage-verified-adapter-positive-motion-evidence-v2"
)
VERIFIED_R1C_ADAPTER_VERSION = (
    "stage20-barrage-per-gate-predictive-r1c-adapter-v2"
)
STATE_ORIGINS = frozenset({"INITIAL", "MANUAL_OBSERVED", "ADVANCED"})


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
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"[{CONTRACT_VERSION}] {label} must contain eight numeric gates"
        ) from error
    require(result.shape == (MAIN_GATE_COUNT,), f"{label} must contain eight gates")
    require(bool(np.isfinite(result).all()), f"{label} contains non-finite values")
    require(
        bool(np.all((result >= 0.0) & (result <= 1.0))),
        f"{label} must remain within 0..1",
    )
    return result.copy()


def _finite_gate_vector(value: object, label: str) -> np.ndarray:
    """Normalize a scalar or an eight-element numeric vector."""

    if np.isscalar(value) and not isinstance(value, (str, bytes)):
        return np.full(MAIN_GATE_COUNT, _finite(value, label), dtype=np.float64)
    try:
        raw = list(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(
            f"[{CONTRACT_VERSION}] {label} must be scalar or contain eight gates"
        ) from error
    require(len(raw) == MAIN_GATE_COUNT, f"{label} must contain eight gates")
    return np.asarray(
        [_finite(item, f"{label} gate {index + 1}") for index, item in enumerate(raw)],
        dtype=np.float64,
    )


def _optional_gate_vector(value: object | None, label: str) -> list[float | None]:
    """Normalize an optional scalar/vector while retaining per-gate missingness."""

    if value is None:
        return [None] * MAIN_GATE_COUNT
    if np.isscalar(value) and not isinstance(value, (str, bytes)):
        scalar = _optional_finite(value, label)
        return [scalar] * MAIN_GATE_COUNT
    try:
        raw = list(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(
            f"[{CONTRACT_VERSION}] {label} must be scalar or contain eight gates"
        ) from error
    require(len(raw) == MAIN_GATE_COUNT, f"{label} must contain eight gates")
    return [
        _optional_finite(item, f"{label} gate {index + 1}")
        for index, item in enumerate(raw)
    ]


def _boolean_gate_vector(value: object, label: str) -> list[bool]:
    require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
        f"{label} must contain eight booleans",
    )
    raw = list(value)
    require(len(raw) == MAIN_GATE_COUNT, f"{label} must contain eight gates")
    require(all(type(item) is bool for item in raw), f"{label} must contain booleans")
    return [bool(item) for item in raw]


def _order_vector(value: object, label: str) -> tuple[int, ...]:
    require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
        f"{label} must be an ordered gate list",
    )
    raw = list(value)
    require(
        all(type(item) is int for item in raw),
        f"{label} must contain exact integer gate ids",
    )
    result = tuple(int(item) for item in raw)
    require(len(result) == MAIN_GATE_COUNT, f"{label} must contain eight gates")
    require(set(result) == set(MAIN_GATE_IDS), f"{label} must be a permutation of 1..8")
    return result


def _json_ready(value: object) -> object:
    """Return a deterministic, finite JSON representation for contract seals."""

    if isinstance(value, np.ndarray):
        return _json_ready(value.tolist())
    if isinstance(value, np.generic):
        return _json_ready(value.item())
    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_ready(item) for item in value]
    if value is None or type(value) in (bool, int, str):
        return value
    if isinstance(value, float):
        require(math.isfinite(value), "decision binding contains a non-finite float")
        return value
    # All public numeric inputs have already been normalized before sealing.
    # Rejecting other objects avoids unstable repr()-based identities.
    raise ValueError(
        f"[{CONTRACT_VERSION}] decision binding contains an unsupported value"
    )


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        _json_ready(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _normalized_state_binding_payload(state: Mapping[str, object]) -> dict[str, object]:
    normalized = validate_controller_state(state)
    return {
        "stateBindingSha256": normalized["stateBindingSha256"],
        "stateOrigin": normalized["origin"],
    }


def _canonical_optional_call_input(value: object | None, label: str) -> object | None:
    """Preserve scalar-vs-vector provenance while normalizing replay inputs."""

    if value is None:
        return None
    if np.isscalar(value) and not isinstance(value, (str, bytes)):
        return _finite(value, label)
    return _optional_gate_vector(value, label)


def _is_explicit_eight_gate_vector(value: object | None) -> bool:
    """True only for an explicitly supplied eight-element vector, never a scalar."""

    if value is None or np.isscalar(value) or isinstance(value, (str, bytes)):
        return False
    try:
        return len(list(value)) == MAIN_GATE_COUNT  # type: ignore[arg-type]
    except TypeError:
        return False


def _positive_motion_argument_payload(
    resolution_inputs: Mapping[str, object],
) -> dict[str, object]:
    return {
        key: resolution_inputs[key]
        for key in (
            "mean_head_difference_m_by_gate_id_1_to_8",
            "local_head_difference_m_by_gate_id_1_to_8",
            "head_observation_age_s_by_gate_id_1_to_8",
            "predicted_minimum_control_head_difference_m_by_gate_id_1_to_8",
            "forecast_age_s_by_gate_id_1_to_8",
            "forecast_remaining_coverage_s_by_gate_id_1_to_8",
        )
    }


def positive_motion_controller_argument_binding_sha256(
    *,
    mean_head_difference_m_by_gate_id_1_to_8: object | None,
    local_head_difference_m_by_gate_id_1_to_8: object,
    head_observation_age_s_by_gate_id_1_to_8: object,
    predicted_minimum_control_head_difference_m_by_gate_id_1_to_8: object,
    forecast_age_s_by_gate_id_1_to_8: object,
    forecast_remaining_coverage_s_by_gate_id_1_to_8: object,
) -> str:
    """Return the controller-owned binding used by a verified adapter package."""

    inputs = {
        "mean_head_difference_m_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                mean_head_difference_m_by_gate_id_1_to_8,
                "per-gate mean head difference",
            )
        ),
        "local_head_difference_m_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                local_head_difference_m_by_gate_id_1_to_8,
                "per-gate local head difference",
            )
        ),
        "head_observation_age_s_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                head_observation_age_s_by_gate_id_1_to_8,
                "per-gate head observation age",
            )
        ),
        "predicted_minimum_control_head_difference_m_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                predicted_minimum_control_head_difference_m_by_gate_id_1_to_8,
                "per-gate predicted minimum control head difference",
            )
        ),
        "forecast_age_s_by_gate_id_1_to_8": _canonical_optional_call_input(
            forecast_age_s_by_gate_id_1_to_8,
            "per-gate forecast age",
        ),
        "forecast_remaining_coverage_s_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                forecast_remaining_coverage_s_by_gate_id_1_to_8,
                "per-gate forecast remaining coverage",
            )
        ),
    }
    require(
        inputs["mean_head_difference_m_by_gate_id_1_to_8"] is None
        or _is_explicit_eight_gate_vector(
            inputs["mean_head_difference_m_by_gate_id_1_to_8"]
        ),
        "positive-motion mean head must be absent or an explicit eight-gate input",
    )
    require(
        all(
            _is_explicit_eight_gate_vector(value)
            for key, value in inputs.items()
            if key != "mean_head_difference_m_by_gate_id_1_to_8"
        ),
        "positive-motion binding requires explicit eight-gate inputs",
    )
    return _sha256_json(inputs)


def _validate_verified_positive_motion_evidence(
    evidence: object | None,
    resolution_inputs: Mapping[str, object],
    *,
    per_gate_independent_head: bool,
    per_gate_independent_forecast: bool,
) -> bool:
    if evidence is None:
        return False
    require(isinstance(evidence, Mapping), "verified adapter evidence must be an object")
    required = {
        "schema",
        "producerAdapterVersion",
        "liveHeadObservationEvidenceSha256",
        "forecastEvidenceSha256",
        "perGateIndependentHeadVerified",
        "perGateIndependentForecastVerified",
        "controllerArgumentBindingSha256",
        "solverConnectionPerformed",
        "evidencePackageSha256",
    }
    require(set(evidence) == required, "verified adapter evidence keys are invalid")
    require(
        evidence["schema"] == POSITIVE_MOTION_EVIDENCE_SCHEMA,
        "verified adapter evidence schema mismatch",
    )
    require(
        evidence["producerAdapterVersion"] == VERIFIED_R1C_ADAPTER_VERSION,
        "positive motion requires the verified R1C adapter",
    )
    require(
        evidence["perGateIndependentHeadVerified"] is True
        and evidence["perGateIndependentForecastVerified"] is True,
        "verified adapter evidence must attest independent head and forecast",
    )
    require(
        per_gate_independent_head and per_gate_independent_forecast,
        "verified adapter evidence cannot authorize scalar/broadcast inputs",
    )
    require(
        evidence["solverConnectionPerformed"] is False,
        "offline controller evidence cannot claim solver connection",
    )
    require(
        _is_sha256(evidence["liveHeadObservationEvidenceSha256"])
        and _is_sha256(evidence["forecastEvidenceSha256"]),
        "verified adapter source evidence SHA is invalid",
    )
    expected_arguments = _sha256_json(
        _positive_motion_argument_payload(resolution_inputs)
    )
    require(
        evidence["controllerArgumentBindingSha256"] == expected_arguments,
        "verified adapter evidence does not bind controller arguments",
    )
    package = dict(evidence)
    package_sha = package.pop("evidencePackageSha256")
    require(_is_sha256(package_sha), "verified adapter package SHA is invalid")
    require(
        _sha256_json(package) == package_sha,
        "verified adapter package SHA mismatch",
    )
    return True


def diagnostic_provisional_hydraulic_model(
    *,
    discharge_coefficient_by_gate_id_1_to_8: object,
    fully_open_effective_flow_area_m2_by_gate_id_1_to_8: object,
    opening_to_area_exponent_by_gate_id_1_to_8: object,
    gravity_m_s2: object = 9.80665,
) -> dict[str, object]:
    """Build an explicitly provisional hydraulic diagnostic model.

    No default area, coefficient, or opening exponent is invented.  Callers
    must name all three so that a review can distinguish mechanics from an
    adopted physical calibration.
    """

    return {
        "schema": HYDRAULIC_MODEL_SCHEMA,
        "classification": DIAGNOSTIC_PROVISIONAL,
        "physicalCalibrationClaimed": False,
        "equation": HYDRAULIC_EQUATION,
        "dischargeCoefficientByGateId1To8": _finite_gate_vector(
            discharge_coefficient_by_gate_id_1_to_8,
            "diagnostic discharge coefficient",
        ).tolist(),
        "fullyOpenEffectiveFlowAreaM2ByGateId1To8": _finite_gate_vector(
            fully_open_effective_flow_area_m2_by_gate_id_1_to_8,
            "diagnostic fully-open effective flow area",
        ).tolist(),
        "openingToAreaExponentByGateId1To8": _finite_gate_vector(
            opening_to_area_exponent_by_gate_id_1_to_8,
            "diagnostic opening-to-area exponent",
        ).tolist(),
        "gravityMPerS2": _finite(gravity_m_s2, "diagnostic gravity"),
    }


def validate_hydraulic_model(model: Mapping[str, object]) -> dict[str, object]:
    require(isinstance(model, Mapping), "diagnostic hydraulic model is required")
    required = {
        "schema",
        "classification",
        "physicalCalibrationClaimed",
        "equation",
        "dischargeCoefficientByGateId1To8",
        "fullyOpenEffectiveFlowAreaM2ByGateId1To8",
        "openingToAreaExponentByGateId1To8",
        "gravityMPerS2",
    }
    require(set(model) == required, "diagnostic hydraulic model keys are invalid")
    require(model["schema"] == HYDRAULIC_MODEL_SCHEMA, "hydraulic schema mismatch")
    require(
        model["classification"] == DIAGNOSTIC_PROVISIONAL,
        "hydraulic model must retain the diagnostic provisional label",
    )
    require(
        model["physicalCalibrationClaimed"] is False,
        "hydraulic model cannot claim physical calibration",
    )
    require(model["equation"] == HYDRAULIC_EQUATION, "hydraulic equation mismatch")
    coefficient = _finite_gate_vector(
        model["dischargeCoefficientByGateId1To8"], "discharge coefficient"
    )
    area = _finite_gate_vector(
        model["fullyOpenEffectiveFlowAreaM2ByGateId1To8"],
        "fully-open effective flow area",
    )
    exponent = _finite_gate_vector(
        model["openingToAreaExponentByGateId1To8"],
        "opening-to-area exponent",
    )
    gravity = _finite(model["gravityMPerS2"], "gravity")
    require(bool(np.all((coefficient > 0.0) & (coefficient <= 1.0))), "Cd must be in (0,1]")
    require(bool(np.all(area > 0.0)), "fully-open effective area must be positive")
    # A linear opening-to-area map (p == 1) is a legitimate explicit
    # diagnostic hypothesis.  Nonlinearity is already present in the
    # sqrt(head) discharge relation; forcing p away from one would invent an
    # unsupported gate characteristic.
    require(bool(np.all(exponent > 0.0)), "opening exponent must be positive")
    require(gravity > 0.0, "gravity must be positive")
    return {
        "schema": HYDRAULIC_MODEL_SCHEMA,
        "classification": DIAGNOSTIC_PROVISIONAL,
        "physicalCalibrationClaimed": False,
        "equation": HYDRAULIC_EQUATION,
        "dischargeCoefficientByGateId1To8": coefficient,
        "fullyOpenEffectiveFlowAreaM2ByGateId1To8": area,
        "openingToAreaExponentByGateId1To8": exponent,
        "gravityMPerS2": gravity,
    }


def _validate_legacy_policy(policy: Mapping[str, object]) -> dict[str, float | str]:
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
    require(set(policy) == required, "legacy motion policy keys are invalid")
    require(policy["schema"] == LEGACY_POLICY_SCHEMA, "legacy policy schema mismatch")
    opening_margin = _finite(policy["openingHeadMarginM"], "opening head margin")
    closing_margin = _finite(policy["closingHeadMarginM"], "closing head margin")
    uncertainty = _finite(policy["forecastUncertaintyM"], "forecast uncertainty")
    maximum_head_age = _finite(
        policy["maximumHeadObservationAgeS"], "maximum head observation age"
    )
    maximum_forecast_age = _finite(
        policy["maximumForecastAgeS"], "maximum forecast age"
    )
    coverage = _finite(policy["requiredForecastCoverageS"], "forecast coverage")
    dwell = _finite(policy["openingSafeDwellSeconds"], "opening safe dwell")
    opening_stroke = _finite(policy["fullOpeningStrokeSeconds"], "opening stroke")
    closing_stroke = _finite(policy["fullClosingStrokeSeconds"], "closing stroke")
    tolerance = _finite(policy["capacityZeroTolerance"], "capacity zero tolerance")
    require(closing_margin >= 0.0, "closing head margin must be nonnegative")
    require(opening_margin > closing_margin, "opening margin must exceed closing margin")
    require(uncertainty >= 0.0, "forecast uncertainty must be nonnegative")
    require(maximum_head_age > 0.0, "maximum head age must be positive")
    require(maximum_forecast_age > 0.0, "maximum forecast age must be positive")
    require(dwell >= 0.0, "opening dwell must be nonnegative")
    require(opening_stroke > 0.0, "opening stroke must be positive")
    require(closing_stroke > 0.0, "closing stroke must be positive")
    require(coverage + 1.0e-12 >= closing_stroke, "forecast must cover closure stroke")
    require(0.0 <= tolerance < 1.0e-6, "capacity zero tolerance is invalid")
    return {
        "schema": LEGACY_POLICY_SCHEMA,
        "openingHeadMarginM": opening_margin,
        "closingHeadMarginM": closing_margin,
        "forecastUncertaintyM": uncertainty,
        "maximumHeadObservationAgeS": maximum_head_age,
        "maximumForecastAgeS": maximum_forecast_age,
        "requiredForecastCoverageS": coverage,
        "openingSafeDwellSeconds": dwell,
        "fullOpeningStrokeSeconds": opening_stroke,
        "fullClosingStrokeSeconds": closing_stroke,
        "capacityZeroTolerance": tolerance,
    }


def upgrade_v1_policy(
    legacy_policy: Mapping[str, object],
    *,
    diagnostic_hydraulic_model: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Broadcast a valid v1 control policy into the explicit v2 contract."""

    legacy = _validate_legacy_policy(legacy_policy)

    def repeated(key: str) -> list[float]:
        return [float(legacy[key])] * MAIN_GATE_COUNT

    return {
        "schema": POLICY_SCHEMA,
        "classification": DIAGNOSTIC_PROVISIONAL,
        "openingOrderGateIds": list(DEFAULT_OPENING_ORDER),
        "closingOrderGateIds": list(DEFAULT_CLOSING_ORDER),
        "openingHeadMarginMByGateId1To8": repeated("openingHeadMarginM"),
        "closingHeadMarginMByGateId1To8": repeated("closingHeadMarginM"),
        "forecastUncertaintyMByGateId1To8": repeated("forecastUncertaintyM"),
        "maximumHeadObservationAgeSByGateId1To8": repeated(
            "maximumHeadObservationAgeS"
        ),
        "maximumForecastAgeSByGateId1To8": repeated("maximumForecastAgeS"),
        "requiredForecastCoverageSByGateId1To8": repeated(
            "requiredForecastCoverageS"
        ),
        # A legacy contract has no separate control-sampling limit.  Reusing
        # its maximum live-head age is conservative and keeps one stale sample
        # from being credited as a long continuous safe interval.
        "maximumVerifiedControlIntervalSByGateId1To8": repeated(
            "maximumHeadObservationAgeS"
        ),
        "openingSafeDwellSecondsByGateId1To8": repeated(
            "openingSafeDwellSeconds"
        ),
        "fullOpeningStrokeSecondsByGateId1To8": repeated(
            "fullOpeningStrokeSeconds"
        ),
        "fullClosingStrokeSecondsByGateId1To8": repeated(
            "fullClosingStrokeSeconds"
        ),
        "capacityZeroTolerance": float(legacy["capacityZeroTolerance"]),
        "diagnosticHydraulicModel": (
            None
            if diagnostic_hydraulic_model is None
            else {
                key: (
                    value.tolist() if isinstance(value, np.ndarray) else value
                )
                for key, value in validate_hydraulic_model(
                    diagnostic_hydraulic_model
                ).items()
            }
        ),
    }


def validate_policy(policy: Mapping[str, object]) -> dict[str, object]:
    """Normalize v2 or broadcast a legacy v1 policy without hiding provenance."""

    require(isinstance(policy, Mapping), "motion policy is required")
    if policy.get("schema") == LEGACY_POLICY_SCHEMA:
        upgraded = upgrade_v1_policy(policy)
        normalized = validate_policy(upgraded)
        normalized["sourcePolicySchema"] = LEGACY_POLICY_SCHEMA
        normalized["legacyPolicyBroadcast"] = True
        return normalized

    required = {
        "schema",
        "classification",
        "openingOrderGateIds",
        "closingOrderGateIds",
        "openingHeadMarginMByGateId1To8",
        "closingHeadMarginMByGateId1To8",
        "forecastUncertaintyMByGateId1To8",
        "maximumHeadObservationAgeSByGateId1To8",
        "maximumForecastAgeSByGateId1To8",
        "requiredForecastCoverageSByGateId1To8",
        "maximumVerifiedControlIntervalSByGateId1To8",
        "openingSafeDwellSecondsByGateId1To8",
        "fullOpeningStrokeSecondsByGateId1To8",
        "fullClosingStrokeSecondsByGateId1To8",
        "capacityZeroTolerance",
        "diagnosticHydraulicModel",
    }
    require(set(policy) == required, "v2 motion policy keys are invalid")
    require(policy["schema"] == POLICY_SCHEMA, "v2 motion policy schema mismatch")
    require(
        policy["classification"] == DIAGNOSTIC_PROVISIONAL,
        "control constants must retain the diagnostic provisional label",
    )
    opening_order = _order_vector(policy["openingOrderGateIds"], "opening order")
    closing_order = _order_vector(policy["closingOrderGateIds"], "closing order")
    require(opening_order == DEFAULT_OPENING_ORDER, "approved opening order changed")
    require(closing_order == DEFAULT_CLOSING_ORDER, "approved closing order changed")
    opening_margin = _finite_gate_vector(
        policy["openingHeadMarginMByGateId1To8"], "opening head margin"
    )
    closing_margin = _finite_gate_vector(
        policy["closingHeadMarginMByGateId1To8"], "closing head margin"
    )
    uncertainty = _finite_gate_vector(
        policy["forecastUncertaintyMByGateId1To8"], "forecast uncertainty"
    )
    maximum_head_age = _finite_gate_vector(
        policy["maximumHeadObservationAgeSByGateId1To8"],
        "maximum head observation age",
    )
    maximum_forecast_age = _finite_gate_vector(
        policy["maximumForecastAgeSByGateId1To8"], "maximum forecast age"
    )
    required_coverage = _finite_gate_vector(
        policy["requiredForecastCoverageSByGateId1To8"],
        "required forecast coverage",
    )
    maximum_verified_interval = _finite_gate_vector(
        policy["maximumVerifiedControlIntervalSByGateId1To8"],
        "maximum verified control interval",
    )
    dwell = _finite_gate_vector(
        policy["openingSafeDwellSecondsByGateId1To8"], "opening safe dwell"
    )
    opening_stroke = _finite_gate_vector(
        policy["fullOpeningStrokeSecondsByGateId1To8"], "opening stroke"
    )
    closing_stroke = _finite_gate_vector(
        policy["fullClosingStrokeSecondsByGateId1To8"], "closing stroke"
    )
    tolerance = _finite(policy["capacityZeroTolerance"], "capacity zero tolerance")
    require(bool(np.all(closing_margin >= 0.0)), "closing margins must be nonnegative")
    require(
        bool(np.all(opening_margin > closing_margin)),
        "each opening margin must exceed its closing margin",
    )
    require(bool(np.all(uncertainty >= 0.0)), "forecast uncertainty must be nonnegative")
    require(bool(np.all(maximum_head_age > 0.0)), "maximum head ages must be positive")
    require(
        bool(np.all(maximum_forecast_age > 0.0)),
        "maximum forecast ages must be positive",
    )
    require(
        bool(np.all(maximum_verified_interval > 0.0)),
        "maximum verified control intervals must be positive",
    )
    require(
        bool(np.all(maximum_verified_interval <= maximum_head_age + 1.0e-12)),
        "maximum verified control interval cannot exceed live-head age limit",
    )
    require(
        bool(np.all(maximum_verified_interval <= maximum_forecast_age + 1.0e-12)),
        "maximum verified control interval cannot exceed forecast age limit",
    )
    require(bool(np.all(dwell >= 0.0)), "opening dwell must be nonnegative")
    require(bool(np.all(opening_stroke > 0.0)), "opening strokes must be positive")
    require(bool(np.all(closing_stroke > 0.0)), "closing strokes must be positive")
    require(
        bool(np.all(required_coverage + 1.0e-12 >= closing_stroke)),
        "each forecast must cover its gate's full closing stroke",
    )
    require(0.0 <= tolerance < 1.0e-6, "capacity zero tolerance is invalid")
    model_value = policy["diagnosticHydraulicModel"]
    hydraulic_model = (
        None
        if model_value is None
        else validate_hydraulic_model(model_value)  # type: ignore[arg-type]
    )
    return {
        "schema": POLICY_SCHEMA,
        "classification": DIAGNOSTIC_PROVISIONAL,
        "sourcePolicySchema": POLICY_SCHEMA,
        "legacyPolicyBroadcast": False,
        "openingOrderGateIds": opening_order,
        "closingOrderGateIds": closing_order,
        "openingHeadMarginMByGateId1To8": opening_margin,
        "closingHeadMarginMByGateId1To8": closing_margin,
        "forecastUncertaintyMByGateId1To8": uncertainty,
        "maximumHeadObservationAgeSByGateId1To8": maximum_head_age,
        "maximumForecastAgeSByGateId1To8": maximum_forecast_age,
        "requiredForecastCoverageSByGateId1To8": required_coverage,
        "maximumVerifiedControlIntervalSByGateId1To8": maximum_verified_interval,
        "openingSafeDwellSecondsByGateId1To8": dwell,
        "fullOpeningStrokeSecondsByGateId1To8": opening_stroke,
        "fullClosingStrokeSecondsByGateId1To8": closing_stroke,
        "capacityZeroTolerance": tolerance,
        "diagnosticHydraulicModel": hydraulic_model,
    }


def _serialize_state(
    current: np.ndarray,
    target: np.ndarray,
    intent: Sequence[bool],
    dwell: np.ndarray,
    last_order: Sequence[str],
    *,
    origin: str,
    parent_state_binding_sha256: str | None,
    source_decision_binding_sha256: str | None,
) -> dict[str, object]:
    intents = [bool(value) for value in intent]
    orders = [str(value) for value in last_order]
    require(all(value in MOTION_ORDERS for value in orders), "last motion order is invalid")
    require(origin in STATE_ORIGINS, "controller state origin is invalid")
    if origin == "ADVANCED":
        require(
            _is_sha256(parent_state_binding_sha256),
            "advanced state requires a parent state binding",
        )
        require(
            _is_sha256(source_decision_binding_sha256),
            "advanced state requires a source decision binding",
        )
    else:
        require(
            parent_state_binding_sha256 is None
            and source_decision_binding_sha256 is None,
            "initial/manual state cannot claim an advance hash chain",
        )
        require(not any(intents), "initial/manual state cannot inherit opening intent")
        require(
            bool(np.all(dwell == 0.0)),
            "initial/manual state cannot inherit opening dwell",
        )
    legacy_dwell = float(np.min(dwell))
    payload: dict[str, object] = {
        "schema": STATE_SCHEMA,
        "stateOrigin": origin,
        "parentStateBindingSha256": parent_state_binding_sha256,
        "sourceDecisionBindingSha256": source_decision_binding_sha256,
        "currentOpeningFractionByGateId1To8": current.tolist(),
        "targetOpeningFractionByGateId1To8": target.tolist(),
        "openingIntentByGateId1To8": intents,
        "continuousOpeningEligibleDurationSByGateId1To8": dwell.tolist(),
        "lastMotionOrderByGateId1To8": orders,
        # Read-compatible aliases for callers migrating from v1.  The scalar
        # dwell is only a conservative minimum; v2 decisions use the vector.
        "capacityByGateId1To8": current.tolist(),
        "openingIntent": any(intents),
        "continuousOpeningEligibleDurationS": legacy_dwell,
    }
    payload["stateBindingSha256"] = _sha256_json(payload)
    return payload


def initial_controller_state() -> dict[str, object]:
    zeros = np.zeros(MAIN_GATE_COUNT, dtype=np.float64)
    return _serialize_state(
        zeros,
        zeros,
        [False] * MAIN_GATE_COUNT,
        zeros,
        ["HOLD"] * MAIN_GATE_COUNT,
        origin="INITIAL",
        parent_state_binding_sha256=None,
        source_decision_binding_sha256=None,
    )


def controller_state_from_per_gate(
    current_opening_fraction_by_gate_id_1_to_8: object,
    *,
    target_opening_fraction_by_gate_id_1_to_8: object | None = None,
    opening_intent_by_gate_id_1_to_8: object | None = None,
    continuous_opening_eligible_duration_s_by_gate_id_1_to_8: object = 0.0,
    last_motion_order_by_gate_id_1_to_8: object | None = None,
) -> dict[str, object]:
    """Construct a sealed manual observation with all trust latches cleared.

    Observed gate openings may be non-prefix, but a manual/checkpoint caller
    cannot inject opening intent or accumulated safe dwell.  Only a state
    returned by ``advance_controller_state`` may carry those latches.
    """

    current = _capacity_vector(
        current_opening_fraction_by_gate_id_1_to_8, "current opening"
    )
    target = current.copy()
    if target_opening_fraction_by_gate_id_1_to_8 is not None:
        supplied_target = _capacity_vector(
            target_opening_fraction_by_gate_id_1_to_8, "target opening"
        )
        require(
            bool(np.array_equal(supplied_target, current)),
            "manual state target must equal observed opening",
        )
    intent = [False] * MAIN_GATE_COUNT
    if opening_intent_by_gate_id_1_to_8 is not None:
        supplied_intent = _boolean_gate_vector(
            opening_intent_by_gate_id_1_to_8, "per-gate opening intent"
        )
        require(
            not any(supplied_intent),
            "manual state cannot inject opening intent",
        )
    dwell = _finite_gate_vector(
        continuous_opening_eligible_duration_s_by_gate_id_1_to_8,
        "per-gate opening dwell",
    )
    require(
        bool(np.all(dwell == 0.0)),
        "manual state cannot inject opening dwell",
    )
    orders = ["HOLD"] * MAIN_GATE_COUNT
    if last_motion_order_by_gate_id_1_to_8 is None:
        pass
    else:
        require(
            isinstance(last_motion_order_by_gate_id_1_to_8, Sequence)
            and not isinstance(last_motion_order_by_gate_id_1_to_8, (str, bytes)),
            "last motion order must contain eight values",
        )
        supplied_orders = [
            str(value) for value in last_motion_order_by_gate_id_1_to_8
        ]
        require(
            len(supplied_orders) == MAIN_GATE_COUNT,
            "last motion order must contain eight gates",
        )
        require(
            all(value == "HOLD" for value in supplied_orders),
            "manual state cannot inject a prior motion order",
        )
    return _serialize_state(
        current,
        target,
        intent,
        dwell,
        orders,
        origin="MANUAL_OBSERVED",
        parent_state_binding_sha256=None,
        source_decision_binding_sha256=None,
    )


def validate_controller_state(state: Mapping[str, object]) -> dict[str, object]:
    """Validate a sealed v2 state, including its origin and hash-chain fields."""

    require(isinstance(state, Mapping), "controller state is required")
    native_keys = {
        "schema",
        "stateOrigin",
        "parentStateBindingSha256",
        "sourceDecisionBindingSha256",
        "stateBindingSha256",
        "currentOpeningFractionByGateId1To8",
        "targetOpeningFractionByGateId1To8",
        "openingIntentByGateId1To8",
        "continuousOpeningEligibleDurationSByGateId1To8",
        "lastMotionOrderByGateId1To8",
        "capacityByGateId1To8",
        "openingIntent",
        "continuousOpeningEligibleDurationS",
    }
    require(set(state) == native_keys, "controller state keys are invalid")
    require(state["schema"] == STATE_SCHEMA, "controller state schema mismatch")
    state_binding = state["stateBindingSha256"]
    require(_is_sha256(state_binding), "controller state binding is invalid")
    sealed_payload = dict(state)
    sealed_payload.pop("stateBindingSha256")
    require(
        _sha256_json(sealed_payload) == state_binding,
        "controller state binding mismatch",
    )
    origin = state["stateOrigin"]
    require(origin in STATE_ORIGINS, "controller state origin is invalid")
    parent_binding = state["parentStateBindingSha256"]
    source_binding = state["sourceDecisionBindingSha256"]
    if origin == "ADVANCED":
        require(
            _is_sha256(parent_binding) and _is_sha256(source_binding),
            "advanced state hash chain is incomplete",
        )
    else:
        require(
            parent_binding is None and source_binding is None,
            "initial/manual state cannot claim an advance hash chain",
        )
    current = _capacity_vector(
        state["currentOpeningFractionByGateId1To8"], "current opening"
    )
    target = _capacity_vector(
        state["targetOpeningFractionByGateId1To8"], "state target opening"
    )
    alias = _capacity_vector(state["capacityByGateId1To8"], "legacy capacity alias")
    require(bool(np.array_equal(current, alias)), "legacy capacity alias drifted")
    intent = _boolean_gate_vector(
        state["openingIntentByGateId1To8"], "per-gate opening intent"
    )
    aggregate_intent = state["openingIntent"]
    require(type(aggregate_intent) is bool, "aggregate openingIntent must be boolean")
    require(bool(aggregate_intent) == any(intent), "aggregate openingIntent drifted")
    dwell = _finite_gate_vector(
        state["continuousOpeningEligibleDurationSByGateId1To8"],
        "per-gate opening dwell",
    )
    require(bool(np.all(dwell >= 0.0)), "per-gate opening dwell must be nonnegative")
    aggregate_dwell = _finite(
        state["continuousOpeningEligibleDurationS"], "aggregate opening dwell"
    )
    require(
        abs(aggregate_dwell - float(np.min(dwell))) <= 1.0e-12,
        "aggregate opening dwell drifted",
    )
    raw_orders = state["lastMotionOrderByGateId1To8"]
    require(
        isinstance(raw_orders, Sequence) and not isinstance(raw_orders, (str, bytes)),
        "last motion order must contain eight values",
    )
    orders = [str(value) for value in raw_orders]
    require(len(orders) == MAIN_GATE_COUNT, "last motion order must contain eight gates")
    require(all(value in MOTION_ORDERS for value in orders), "last motion order is invalid")
    if origin in {"INITIAL", "MANUAL_OBSERVED"}:
        require(
            not any(intent),
            "initial/manual state cannot contain opening intent",
        )
        require(
            bool(np.all(dwell == 0.0)),
            "initial/manual state cannot contain opening dwell",
        )
        require(
            bool(np.array_equal(target, current)),
            "initial/manual state target must equal observed opening",
        )
        require(
            all(value == "HOLD" for value in orders),
            "initial/manual state cannot contain prior motion orders",
        )
    if origin == "INITIAL":
        require(
            bool(np.all(current == 0.0)),
            "initial controller state must be fully closed",
        )
    return {
        "current": current,
        "target": target,
        "intent": intent,
        "dwell": dwell,
        "lastOrder": orders,
        "inputSchema": STATE_SCHEMA,
        "origin": origin,
        "parentStateBindingSha256": parent_binding,
        "sourceDecisionBindingSha256": source_binding,
        "stateBindingSha256": state_binding,
    }


def restore_controller_state_from_sealed_checkpoint(
    checkpoint_state: Mapping[str, object],
) -> dict[str, object]:
    """Restore an exact sealed state; unsealed native/legacy snapshots fail."""

    validate_controller_state(checkpoint_state)
    restored = _json_ready(checkpoint_state)
    require(isinstance(restored, dict), "restored controller state is invalid")
    return restored


def nonlinear_gate_capacity_and_discharge(
    opening_fraction_by_gate_id_1_to_8: object,
    head_difference_m_by_gate_id_1_to_8: object,
    hydraulic_model: Mapping[str, object],
) -> dict[str, object]:
    """Evaluate the signed diagnostic discharge without hiding reverse risk."""

    opening = _capacity_vector(
        opening_fraction_by_gate_id_1_to_8, "hydraulic opening fraction"
    )
    head = _finite_gate_vector(
        head_difference_m_by_gate_id_1_to_8, "hydraulic head difference"
    )
    model = validate_hydraulic_model(hydraulic_model)
    exponent = np.asarray(model["openingToAreaExponentByGateId1To8"])
    coefficient = np.asarray(model["dischargeCoefficientByGateId1To8"])
    full_area = np.asarray(model["fullyOpenEffectiveFlowAreaM2ByGateId1To8"])
    gravity = float(model["gravityMPerS2"])
    capacity = np.power(opening, exponent)
    effective_area = full_area * capacity
    signed_root = np.sign(head) * np.sqrt(2.0 * gravity * np.abs(head))
    signed_discharge = coefficient * effective_area * signed_root
    return {
        "schema": HYDRAULIC_MODEL_SCHEMA,
        "classification": DIAGNOSTIC_PROVISIONAL,
        "physicalCalibrationClaimed": False,
        "equation": HYDRAULIC_EQUATION,
        "openingFractionByGateId1To8": opening,
        "nonlinearCapacityFractionByGateId1To8": capacity,
        "effectiveFlowAreaM2ByGateId1To8": effective_area,
        "headDifferenceMByGateId1To8": head,
        "signedPotentialDischargeM3SByGateId1To8": signed_discharge,
        "adversePotentialDischargeByGateId1To8": (signed_discharge < 0.0),
        "reversePotentialWasNotClipped": True,
        "solverFluxAcceptanceImplied": False,
    }


def _partial_nonlinear_gate_capacity_and_discharge(
    opening: np.ndarray,
    head: Sequence[float | None],
    hydraulic_model: Mapping[str, object],
) -> dict[str, object]:
    """Evaluate every available gate without suppressing siblings with missing head."""

    model = validate_hydraulic_model(hydraulic_model)
    coefficient = np.asarray(model["dischargeCoefficientByGateId1To8"])
    full_area = np.asarray(model["fullyOpenEffectiveFlowAreaM2ByGateId1To8"])
    exponent = np.asarray(model["openingToAreaExponentByGateId1To8"])
    gravity = float(model["gravityMPerS2"])
    capacity = np.power(opening, exponent)
    area = full_area * capacity
    signed_discharge: list[float | None] = []
    adverse: list[bool | None] = []
    for index, head_value in enumerate(head):
        if head_value is None:
            signed_discharge.append(None)
            adverse.append(None)
            continue
        value = (
            math.copysign(1.0, head_value) if head_value != 0.0 else 0.0
        ) * coefficient[index] * area[index] * math.sqrt(
            2.0 * gravity * abs(head_value)
        )
        signed_discharge.append(float(value))
        adverse.append(bool(value < 0.0))
    return {
        "schema": HYDRAULIC_MODEL_SCHEMA,
        "classification": DIAGNOSTIC_PROVISIONAL,
        "physicalCalibrationClaimed": False,
        "equation": HYDRAULIC_EQUATION,
        "openingFractionByGateId1To8": opening.copy(),
        "nonlinearCapacityFractionByGateId1To8": capacity,
        "effectiveFlowAreaM2ByGateId1To8": area,
        "headDifferenceMByGateId1To8": list(head),
        "signedPotentialDischargeM3SByGateId1To8": signed_discharge,
        "adversePotentialDischargeByGateId1To8": adverse,
        "headAvailableByGateId1To8": [value is not None for value in head],
        "reversePotentialWasNotClipped": True,
        "solverFluxAcceptanceImplied": False,
    }


def _choose_gate_input(
    per_gate: object | None,
    legacy_scalar: object | None,
    label: str,
) -> list[float | None]:
    return _optional_gate_vector(
        per_gate if per_gate is not None else legacy_scalar,
        label,
    )


def _all_present(*values: float | None) -> bool:
    return all(value is not None for value in values)


def _rank_by_gate(order: Sequence[int]) -> dict[int, int]:
    return {gate_id: rank for rank, gate_id in enumerate(order, start=1)}


def resolve_motion_target(
    *,
    requested_capacity_by_gate_id_1_to_8: object,
    controller_state: Mapping[str, object],
    policy: Mapping[str, object],
    mean_head_difference_m: object | None = None,
    minimum_local_head_difference_m: object | None = None,
    head_observation_age_s: object | None = None,
    predicted_minimum_control_head_difference_m: object | None = None,
    forecast_age_s: object | None = None,
    forecast_remaining_coverage_s: object | None = None,
    mean_head_difference_m_by_gate_id_1_to_8: object | None = None,
    local_head_difference_m_by_gate_id_1_to_8: object | None = None,
    head_observation_age_s_by_gate_id_1_to_8: object | None = None,
    predicted_minimum_control_head_difference_m_by_gate_id_1_to_8: object | None = None,
    forecast_age_s_by_gate_id_1_to_8: object | None = None,
    forecast_remaining_coverage_s_by_gate_id_1_to_8: object | None = None,
    verified_positive_motion_evidence: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Resolve eight independent gate targets.

    Scalar v1 head/age/forecast arguments are broadcast.  New integrations
    should supply the per-gate arguments so one local hazard does not masquerade
    as an all-gate observation.
    """

    normalized_policy = validate_policy(policy)
    state = validate_controller_state(controller_state)
    requested = _capacity_vector(
        requested_capacity_by_gate_id_1_to_8, "requested opening"
    )
    resolution_inputs = {
        "schema": DECISION_INPUT_SCHEMA,
        "requested_capacity_by_gate_id_1_to_8": requested.tolist(),
        "mean_head_difference_m": _canonical_optional_call_input(
            mean_head_difference_m, "mean head difference"
        ),
        "minimum_local_head_difference_m": _canonical_optional_call_input(
            minimum_local_head_difference_m, "minimum local head difference"
        ),
        "head_observation_age_s": _canonical_optional_call_input(
            head_observation_age_s, "head observation age"
        ),
        "predicted_minimum_control_head_difference_m": (
            _canonical_optional_call_input(
                predicted_minimum_control_head_difference_m,
                "predicted minimum control head difference",
            )
        ),
        "forecast_age_s": _canonical_optional_call_input(
            forecast_age_s, "forecast age"
        ),
        "forecast_remaining_coverage_s": _canonical_optional_call_input(
            forecast_remaining_coverage_s, "forecast remaining coverage"
        ),
        "mean_head_difference_m_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                mean_head_difference_m_by_gate_id_1_to_8,
                "per-gate mean head difference",
            )
        ),
        "local_head_difference_m_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                local_head_difference_m_by_gate_id_1_to_8,
                "per-gate local head difference",
            )
        ),
        "head_observation_age_s_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                head_observation_age_s_by_gate_id_1_to_8,
                "per-gate head observation age",
            )
        ),
        "predicted_minimum_control_head_difference_m_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                predicted_minimum_control_head_difference_m_by_gate_id_1_to_8,
                "per-gate predicted minimum control head difference",
            )
        ),
        "forecast_age_s_by_gate_id_1_to_8": _canonical_optional_call_input(
            forecast_age_s_by_gate_id_1_to_8,
            "per-gate forecast age",
        ),
        "forecast_remaining_coverage_s_by_gate_id_1_to_8": (
            _canonical_optional_call_input(
                forecast_remaining_coverage_s_by_gate_id_1_to_8,
                "per-gate forecast remaining coverage",
            )
        ),
        "verified_positive_motion_evidence": (
            None
            if verified_positive_motion_evidence is None
            else _json_ready(verified_positive_motion_evidence)
        ),
    }
    current = np.asarray(state["current"], dtype=np.float64)
    intent_before = list(state["intent"])
    dwell_before = np.asarray(state["dwell"], dtype=np.float64)
    tolerance = float(normalized_policy["capacityZeroTolerance"])

    mean_head = _choose_gate_input(
        resolution_inputs["mean_head_difference_m_by_gate_id_1_to_8"],
        resolution_inputs["mean_head_difference_m"],
        "mean head difference",
    )
    local_head = _choose_gate_input(
        resolution_inputs["local_head_difference_m_by_gate_id_1_to_8"],
        resolution_inputs["minimum_local_head_difference_m"],
        "local head difference",
    )
    head_age = _choose_gate_input(
        resolution_inputs["head_observation_age_s_by_gate_id_1_to_8"],
        resolution_inputs["head_observation_age_s"],
        "head observation age",
    )
    forecast_minimum = _choose_gate_input(
        resolution_inputs[
            "predicted_minimum_control_head_difference_m_by_gate_id_1_to_8"
        ],
        resolution_inputs["predicted_minimum_control_head_difference_m"],
        "predicted minimum control head difference",
    )
    forecast_age = _choose_gate_input(
        resolution_inputs["forecast_age_s_by_gate_id_1_to_8"],
        resolution_inputs["forecast_age_s"],
        "forecast age",
    )
    forecast_coverage = _choose_gate_input(
        resolution_inputs[
            "forecast_remaining_coverage_s_by_gate_id_1_to_8"
        ],
        resolution_inputs["forecast_remaining_coverage_s"],
        "forecast remaining coverage",
    )
    for values, label in (
        (head_age, "head observation age"),
        (forecast_age, "forecast age"),
        (forecast_coverage, "forecast coverage"),
    ):
        require(
            all(value is None or value >= 0.0 for value in values),
            f"{label} must be nonnegative",
        )

    opening_margin = np.asarray(
        normalized_policy["openingHeadMarginMByGateId1To8"], dtype=np.float64
    )
    closing_margin = np.asarray(
        normalized_policy["closingHeadMarginMByGateId1To8"], dtype=np.float64
    )
    uncertainty = np.asarray(
        normalized_policy["forecastUncertaintyMByGateId1To8"], dtype=np.float64
    )
    maximum_head_age = np.asarray(
        normalized_policy["maximumHeadObservationAgeSByGateId1To8"],
        dtype=np.float64,
    )
    maximum_forecast_age = np.asarray(
        normalized_policy["maximumForecastAgeSByGateId1To8"], dtype=np.float64
    )
    required_coverage = np.asarray(
        normalized_policy["requiredForecastCoverageSByGateId1To8"],
        dtype=np.float64,
    )
    required_dwell = np.asarray(
        normalized_policy["openingSafeDwellSecondsByGateId1To8"],
        dtype=np.float64,
    )
    maximum_verified_interval = np.asarray(
        normalized_policy["maximumVerifiedControlIntervalSByGateId1To8"],
        dtype=np.float64,
    )
    opening_order = tuple(normalized_policy["openingOrderGateIds"])
    closing_order = tuple(normalized_policy["closingOrderGateIds"])
    opening_rank = _rank_by_gate(opening_order)
    closing_rank = _rank_by_gate(closing_order)
    requested_open_gate_ids = tuple(
        gate_id for gate_id in opening_order if requested[gate_id - 1] > tolerance
    )
    require(
        requested_open_gate_ids
        == opening_order[: len(requested_open_gate_ids)],
        "automatic requested openings must be a strict prefix of approved opening order",
    )
    per_gate_independent_head = bool(
        _is_explicit_eight_gate_vector(
            resolution_inputs["local_head_difference_m_by_gate_id_1_to_8"]
        )
        and _is_explicit_eight_gate_vector(
            resolution_inputs["head_observation_age_s_by_gate_id_1_to_8"]
        )
    )
    per_gate_independent_forecast = bool(
        _is_explicit_eight_gate_vector(
            resolution_inputs[
                "predicted_minimum_control_head_difference_m_by_gate_id_1_to_8"
            ]
        )
        and _is_explicit_eight_gate_vector(
            resolution_inputs["forecast_age_s_by_gate_id_1_to_8"]
        )
        and _is_explicit_eight_gate_vector(
            resolution_inputs[
                "forecast_remaining_coverage_s_by_gate_id_1_to_8"
            ]
        )
    )
    positive_motion_evidence_verified = _validate_verified_positive_motion_evidence(
        resolution_inputs["verified_positive_motion_evidence"],
        resolution_inputs,
        per_gate_independent_head=per_gate_independent_head,
        per_gate_independent_forecast=per_gate_independent_forecast,
    )

    head_present: list[bool] = []
    head_fresh: list[bool] = []
    control_head: list[float | None] = []
    forecast_present: list[bool] = []
    forecast_fresh: list[bool] = []
    forecast_long_enough: list[bool] = []
    conservative_forecast: list[float | None] = []
    live_open_safe: list[bool] = []
    live_hold_safe: list[bool] = []
    forecast_hold_safe: list[bool] = []
    for index in range(MAIN_GATE_COUNT):
        present = _all_present(local_head[index], head_age[index])
        # The per-gate local head is authoritative in v2.  A supplied mean is
        # an additional conservative bound, not a mandatory duplicate.
        local_control = local_head[index]
        if local_control is not None and mean_head[index] is not None:
            local_control = min(local_control, mean_head[index])
        fresh = bool(
            present
            and head_age[index] is not None
            and head_age[index] <= maximum_head_age[index]
        )
        predicted_present = _all_present(
            forecast_minimum[index], forecast_age[index], forecast_coverage[index]
        )
        predicted_fresh = bool(
            predicted_present
            and forecast_age[index] is not None
            and forecast_age[index] <= maximum_forecast_age[index]
        )
        long_enough = bool(
            predicted_present
            and forecast_coverage[index] is not None
            and forecast_coverage[index] + 1.0e-12 >= required_coverage[index]
        )
        conservative = (
            None
            if forecast_minimum[index] is None
            else forecast_minimum[index] - uncertainty[index]
        )
        head_present.append(present)
        head_fresh.append(fresh)
        control_head.append(local_control)
        forecast_present.append(predicted_present)
        forecast_fresh.append(predicted_fresh)
        forecast_long_enough.append(long_enough)
        conservative_forecast.append(conservative)
        live_open_safe.append(
            bool(fresh and local_control is not None and local_control > opening_margin[index])
        )
        live_hold_safe.append(
            bool(fresh and local_control is not None and local_control > closing_margin[index])
        )
        forecast_hold_safe.append(
            bool(
                predicted_fresh
                and long_enough
                and conservative is not None
                and conservative > closing_margin[index]
            )
        )

    def opening_blocker(gate_id: int) -> int | None:
        for earlier in opening_order[: opening_rank[gate_id] - 1]:
            earlier_index = earlier - 1
            if requested[earlier_index] <= tolerance:
                continue
            ready = bool(
                current[earlier_index]
                + tolerance
                >= requested[earlier_index]
                and intent_before[earlier_index]
                and live_hold_safe[earlier_index]
                and forecast_hold_safe[earlier_index]
            )
            if not ready:
                return earlier
        return None

    def closing_blocker(gate_id: int) -> int | None:
        for earlier in closing_order[: closing_rank[gate_id] - 1]:
            earlier_index = earlier - 1
            if current[earlier_index] > requested[earlier_index] + tolerance:
                return earlier
        return None

    target = current.copy()
    intent_after = [False] * MAIN_GATE_COUNT
    opening_eligible = [False] * MAIN_GATE_COUNT
    decisions: list[dict[str, Any]] = []
    for index, gate_id in enumerate(MAIN_GATE_IDS):
        requested_open = bool(requested[index] > tolerance)
        current_open = bool(current[index] > tolerance)
        fail_closed = False
        blocker: int | None = None
        next_intent = False
        eligible = False
        gate_target = current[index]

        if not requested_open and not current_open:
            classification = "REQUESTED_CLOSED"
            gate_target = 0.0
            motion_order = "HOLD"
        elif not head_present[index]:
            classification = "INTERLOCK_CLOSING_MISSING_LIVE_HEAD"
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        elif not head_fresh[index]:
            classification = "INTERLOCK_CLOSING_STALE_LIVE_HEAD"
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        elif not forecast_present[index]:
            classification = "INTERLOCK_CLOSING_MISSING_FORECAST"
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        elif not forecast_fresh[index]:
            classification = "INTERLOCK_CLOSING_STALE_FORECAST"
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        elif not forecast_long_enough[index]:
            classification = "INTERLOCK_CLOSING_FORECAST_COVERAGE_TOO_SHORT"
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        elif not positive_motion_evidence_verified:
            classification = (
                "INTERLOCK_CLOSING_UNVERIFIED_ADAPTER_EVIDENCE"
                if current_open
                else "INTERLOCK_CLOSED_UNVERIFIED_ADAPTER_EVIDENCE"
            )
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        elif intent_before[index]:
            if not live_hold_safe[index]:
                classification = "PREDICTIVE_CLOSING_LIVE_HEAD_BELOW_CLOSE_MARGIN"
                gate_target = 0.0
                motion_order = "FAIL_CLOSED"
                fail_closed = True
            elif not forecast_hold_safe[index]:
                classification = "PREDICTIVE_CLOSING_FORECAST_BELOW_CLOSE_MARGIN"
                gate_target = 0.0
                motion_order = "FAIL_CLOSED"
                fail_closed = True
            elif requested[index] > current[index] + tolerance:
                blocker = opening_blocker(gate_id)
                next_intent = True
                if blocker is None:
                    classification = "FRACTIONAL_OPENING_ALLOWED"
                    gate_target = requested[index]
                    motion_order = "OPEN"
                else:
                    classification = "INTERLOCK_OPENING_ORDER_WAIT"
                    gate_target = current[index]
                    motion_order = "HOLD"
            elif requested[index] < current[index] - tolerance:
                blocker = closing_blocker(gate_id)
                if blocker is None:
                    classification = "REQUESTED_FRACTIONAL_CLOSING_ALLOWED"
                    gate_target = requested[index]
                    next_intent = requested_open
                    motion_order = "CLOSE"
                else:
                    classification = "INTERLOCK_CLOSING_ORDER_WAIT"
                    gate_target = current[index]
                    next_intent = True
                    motion_order = "HOLD"
            else:
                classification = "OPENING_INTENT_HELD_WITHIN_HYSTERESIS"
                gate_target = requested[index]
                next_intent = requested_open
                motion_order = "HOLD"
        elif current_open:
            classification = "INTERLOCK_CLOSING_REARM_ONLY_AFTER_FULL_CLOSURE"
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        elif not requested_open:
            classification = "REQUESTED_CLOSED"
            gate_target = 0.0
            motion_order = "HOLD"
        elif not live_open_safe[index]:
            classification = "INTERLOCK_CLOSED_BELOW_OPEN_MARGIN"
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        elif not forecast_hold_safe[index]:
            classification = "INTERLOCK_CLOSED_FORECAST_BELOW_CLOSE_MARGIN"
            gate_target = 0.0
            motion_order = "FAIL_CLOSED"
            fail_closed = True
        else:
            eligible = True
            if dwell_before[index] + 1.0e-12 < required_dwell[index]:
                classification = "INTERLOCK_CLOSED_OPENING_SAFE_DWELL"
                gate_target = 0.0
                motion_order = "HOLD"
            else:
                blocker = opening_blocker(gate_id)
                if blocker is not None:
                    classification = "INTERLOCK_OPENING_ORDER_WAIT"
                    gate_target = 0.0
                    motion_order = "HOLD"
                else:
                    classification = "FRACTIONAL_OPENING_ALLOWED"
                    gate_target = requested[index]
                    next_intent = True
                    motion_order = "OPEN"

        target[index] = gate_target
        intent_after[index] = next_intent
        opening_eligible[index] = eligible
        decisions.append(
            {
                "gateId": gate_id,
                "openingOrderRank": opening_rank[gate_id],
                "closingOrderRank": closing_rank[gate_id],
                "classification": classification,
                "motionOrder": motion_order,
                "orderBlockedByGateId": blocker,
                "failClosed": fail_closed,
                "openingIntentBefore": bool(intent_before[index]),
                "openingIntent": next_intent,
                "openingEligible": eligible,
                "requestedOpeningFraction": float(requested[index]),
                "currentOpeningFraction": float(current[index]),
                "targetOpeningFraction": float(gate_target),
                "continuousOpeningEligibleDurationS": float(dwell_before[index]),
                "requiredOpeningSafeDwellS": float(required_dwell[index]),
                "maximumVerifiedControlIntervalS": float(
                    maximum_verified_interval[index]
                ),
                "head": {
                    "present": head_present[index],
                    "fresh": head_fresh[index],
                    "meanHeadDifferenceM": mean_head[index],
                    "localHeadDifferenceM": local_head[index],
                    "controlHeadDifferenceM": control_head[index],
                    "observationAgeS": head_age[index],
                    "openingMarginM": float(opening_margin[index]),
                    "closingMarginM": float(closing_margin[index]),
                },
                "forecast": {
                    "present": forecast_present[index],
                    "fresh": forecast_fresh[index],
                    "coverageSufficientForFullClosure": forecast_long_enough[index],
                    "predictedMinimumControlHeadDifferenceM": forecast_minimum[index],
                    "conservativePredictedMinimumControlHeadDifferenceM": (
                        conservative_forecast[index]
                    ),
                    "ageS": forecast_age[index],
                    "remainingCoverageS": forecast_coverage[index],
                    "uncertaintyM": float(uncertainty[index]),
                },
            }
        )

    hydraulic_model = normalized_policy["diagnosticHydraulicModel"]
    hydraulic_diagnostics: dict[str, object] | None = None
    if hydraulic_model is not None:
        hydraulic_diagnostics = {
            "classification": DIAGNOSTIC_PROVISIONAL,
            "current": _partial_nonlinear_gate_capacity_and_discharge(
                current, control_head, hydraulic_model  # type: ignore[arg-type]
            ),
            "target": _partial_nonlinear_gate_capacity_and_discharge(
                target, control_head, hydraulic_model  # type: ignore[arg-type]
            ),
        }
    elif hydraulic_model is None:
        hydraulic_diagnostics = {
            "classification": "NOT_AVAILABLE_EXPLICIT_PROVISIONAL_MODEL_REQUIRED",
            "physicalCalibrationClaimed": False,
        }

    relevant = [
        row["classification"]
        for row in decisions
        if row["requestedOpeningFraction"] > tolerance
        or row["currentOpeningFraction"] > tolerance
    ]
    aggregate_classification = (
        "REQUESTED_ALL_CLOSED"
        if not relevant
        else relevant[0]
        if all(value == relevant[0] for value in relevant)
        else "PER_GATE_MIXED_DECISION"
    )
    finite_local = [value for value in local_head if value is not None]
    finite_control = [value for value in control_head if value is not None]
    finite_forecast = [value for value in forecast_minimum if value is not None]
    finite_conservative = [
        value for value in conservative_forecast if value is not None
    ]
    relevant_indices = [
        index
        for index in range(MAIN_GATE_COUNT)
        if requested[index] > tolerance or current[index] > tolerance
    ]
    result: dict[str, Any] = {
        "version": CONTRACT_VERSION,
        "policySchema": normalized_policy["sourcePolicySchema"],
        "legacyPolicyBroadcast": normalized_policy["legacyPolicyBroadcast"],
        "resolutionInputs": resolution_inputs,
        "policyBindingSha256": _sha256_json(normalized_policy),
        "stateBindingSha256": _sha256_json(
            _normalized_state_binding_payload(controller_state)
        ),
        "classification": aggregate_classification,
        "gateDecisionsById1To8": decisions,
        "requestedCapacityByGateId1To8": requested,
        "currentCapacityByGateId1To8": current,
        "targetCapacityByGateId1To8": target,
        "openingIntentByGateId1To8": intent_after,
        "openingEligibleByGateId1To8": opening_eligible,
        "openingIntent": any(intent_after),
        "openingEligible": any(opening_eligible),
        "currentCapacityIsFullyClosed": bool(np.all(current <= tolerance)),
        "headObservationPresent": all(head_present[index] for index in relevant_indices),
        "headObservationFresh": all(head_fresh[index] for index in relevant_indices),
        "forecastPresent": all(forecast_present[index] for index in relevant_indices),
        "forecastFresh": all(forecast_fresh[index] for index in relevant_indices),
        "forecastCoverageSufficientForFullClosure": all(
            forecast_long_enough[index] for index in relevant_indices
        ),
        "meanHeadDifferenceM": (
            _optional_finite(mean_head_difference_m, "mean head difference")
            if mean_head_difference_m_by_gate_id_1_to_8 is None
            else None
        ),
        "minimumLocalHeadDifferenceM": min(finite_local) if finite_local else None,
        "controlHeadDifferenceM": min(finite_control) if finite_control else None,
        "predictedMinimumControlHeadDifferenceM": (
            min(finite_forecast) if finite_forecast else None
        ),
        "conservativePredictedMinimumControlHeadDifferenceM": (
            min(finite_conservative) if finite_conservative else None
        ),
        "openingHeadMarginM": (
            float(opening_margin[0])
            if bool(np.all(opening_margin == opening_margin[0]))
            else None
        ),
        "closingHeadMarginM": (
            float(closing_margin[0])
            if bool(np.all(closing_margin == closing_margin[0]))
            else None
        ),
        "continuousOpeningEligibleDurationS": (
            min(float(dwell_before[index]) for index in relevant_indices)
            if relevant_indices
            else float(np.min(dwell_before))
        ),
        "diagnosticHydraulics": hydraulic_diagnostics,
        "diagnosticFiniteGateMotionRepresented": True,
        "physicalGateMotionLagRepresented": False,
        "solverMotionIntegrationImplied": False,
        "perGateIndependentStateRepresented": True,
        "perGateIndependentHeadRepresented": per_gate_independent_head,
        "perGateIndependentForecastRepresented": per_gate_independent_forecast,
        "verifiedAdapterPositiveMotionEvidence": (
            positive_motion_evidence_verified
        ),
        "capacityZeroToleranceBoundByPolicyAndDecision": True,
        "runtimeMotionAuthorityClaimed": False,
        "controlOutputIsDiagnosticMechanicsOnly": True,
        "automaticRequestSemantics": "STRICT_PREFIX_OF_APPROVED_OPENING_ORDER",
        "automaticRequestedOpenGateIdsInApprovedOrder": list(
            requested_open_gate_ids
        ),
        "manualObservedStateMayBeNonPrefix": True,
        "reverseFlowPermitted": False,
        "adverseFluxMustBeRejectedWithoutClipping": True,
    }
    result["decisionBindingSha256"] = _sha256_json(result)
    return result


def advance_fractional_capacity(
    current_capacity_by_gate_id_1_to_8: object,
    target_capacity_by_gate_id_1_to_8: object,
    *,
    elapsed_seconds: object,
    full_opening_stroke_seconds: object,
    full_closing_stroke_seconds: object,
) -> np.ndarray:
    """Advance each gate without exceeding its own opening/closing rate."""

    current = _capacity_vector(current_capacity_by_gate_id_1_to_8, "current opening")
    target = _capacity_vector(target_capacity_by_gate_id_1_to_8, "target opening")
    elapsed = _finite(elapsed_seconds, "motion elapsed seconds")
    opening_stroke = _finite_gate_vector(
        full_opening_stroke_seconds, "full opening stroke"
    )
    closing_stroke = _finite_gate_vector(
        full_closing_stroke_seconds, "full closing stroke"
    )
    require(elapsed >= 0.0, "motion elapsed seconds must be nonnegative")
    require(bool(np.all(opening_stroke > 0.0)), "opening stroke must be positive")
    require(bool(np.all(closing_stroke > 0.0)), "closing stroke must be positive")
    result = current.copy()
    opening = target > current
    closing = target < current
    result[opening] = np.minimum(
        target[opening], current[opening] + elapsed / opening_stroke[opening]
    )
    result[closing] = np.maximum(
        target[closing], current[closing] - elapsed / closing_stroke[closing]
    )
    require(bool(np.all((result >= 0.0) & (result <= 1.0))), "motion left 0..1")
    return result


def advance_controller_state(
    *,
    controller_state: Mapping[str, object],
    decision: Mapping[str, object],
    elapsed_seconds: object,
    policy: Mapping[str, object],
) -> dict[str, object]:
    """Advance the accepted interval and retain independent per-gate latches."""

    normalized_policy = validate_policy(policy)
    state = validate_controller_state(controller_state)
    require(isinstance(decision, Mapping), "motion decision is required")
    require(decision.get("version") == CONTRACT_VERSION, "motion decision version mismatch")
    current = np.asarray(state["current"], dtype=np.float64)
    decision_current = _capacity_vector(
        decision.get("currentCapacityByGateId1To8"), "decision current opening"
    )
    require(bool(np.array_equal(current, decision_current)), "decision current state drifted")
    target = _capacity_vector(
        decision.get("targetCapacityByGateId1To8"), "decision target opening"
    )
    rows = decision.get("gateDecisionsById1To8")
    require(isinstance(rows, Sequence), "per-gate decisions are required")
    require(len(rows) == MAIN_GATE_COUNT, "per-gate decisions must contain eight gates")
    intent: list[bool] = []
    eligible: list[bool] = []
    order: list[str] = []
    for index, row in enumerate(rows):
        require(isinstance(row, Mapping), f"gate decision {index + 1} must be an object")
        require(row.get("gateId") == index + 1, "gate decision order changed")
        require(
            abs(_finite(row.get("currentOpeningFraction"), "gate decision current") - current[index])
            <= 1.0e-12,
            "gate decision current opening drifted",
        )
        require(
            abs(_finite(row.get("targetOpeningFraction"), "gate decision target") - target[index])
            <= 1.0e-12,
            "gate decision target opening drifted",
        )
        gate_intent = row.get("openingIntent")
        gate_eligible = row.get("openingEligible")
        gate_order = row.get("motionOrder")
        fail_closed = row.get("failClosed")
        require(type(gate_intent) is bool, "gate opening intent must be boolean")
        require(type(gate_eligible) is bool, "gate opening eligibility must be boolean")
        require(gate_order in MOTION_ORDERS, "gate motion order is invalid")
        require(type(fail_closed) is bool, "gate fail-closed flag must be boolean")
        if fail_closed:
            require(
                target[index]
                <= float(normalized_policy["capacityZeroTolerance"]),
                "fail-closed gate target must be zero",
            )
        intent.append(bool(gate_intent))
        eligible.append(bool(gate_eligible))
        order.append(str(gate_order))

    decision_binding = decision.get("decisionBindingSha256")
    require(
        isinstance(decision_binding, str)
        and len(decision_binding) == 64
        and all(character in "0123456789abcdef" for character in decision_binding),
        "motion decision is not sealed by resolve_motion_target",
    )
    sealed_body = dict(decision)
    sealed_body.pop("decisionBindingSha256", None)
    require(
        _sha256_json(sealed_body) == decision_binding,
        "motion decision binding mismatch",
    )
    require(
        decision.get("policyBindingSha256") == _sha256_json(normalized_policy),
        "motion decision policy binding mismatch",
    )
    require(
        decision.get("stateBindingSha256")
        == _sha256_json(_normalized_state_binding_payload(controller_state)),
        "motion decision state binding mismatch",
    )
    replay_inputs = decision.get("resolutionInputs")
    require(isinstance(replay_inputs, Mapping), "motion decision inputs are missing")
    replay_required = {
        "schema",
        "requested_capacity_by_gate_id_1_to_8",
        "mean_head_difference_m",
        "minimum_local_head_difference_m",
        "head_observation_age_s",
        "predicted_minimum_control_head_difference_m",
        "forecast_age_s",
        "forecast_remaining_coverage_s",
        "mean_head_difference_m_by_gate_id_1_to_8",
        "local_head_difference_m_by_gate_id_1_to_8",
        "head_observation_age_s_by_gate_id_1_to_8",
        "predicted_minimum_control_head_difference_m_by_gate_id_1_to_8",
        "forecast_age_s_by_gate_id_1_to_8",
        "forecast_remaining_coverage_s_by_gate_id_1_to_8",
        "verified_positive_motion_evidence",
    }
    require(set(replay_inputs) == replay_required, "motion decision input keys are invalid")
    require(
        replay_inputs["schema"] == DECISION_INPUT_SCHEMA,
        "motion decision input schema mismatch",
    )
    replay_call = dict(replay_inputs)
    replay_call.pop("schema")
    expected_decision = resolve_motion_target(
        controller_state=controller_state,
        policy=policy,
        **replay_call,
    )
    require(
        expected_decision["decisionBindingSha256"] == decision_binding,
        "motion decision was not reproduced from bound inputs",
    )

    elapsed = _finite(elapsed_seconds, "controller elapsed seconds")
    require(elapsed >= 0.0, "controller elapsed seconds must be nonnegative")
    maximum_interval = np.asarray(
        normalized_policy["maximumVerifiedControlIntervalSByGateId1To8"],
        dtype=np.float64,
    )
    require(
        bool(np.all(elapsed <= maximum_interval + 1.0e-12)),
        "controller elapsed interval exceeds verified observation-update limit",
    )
    maximum_head_age = np.asarray(
        normalized_policy["maximumHeadObservationAgeSByGateId1To8"],
        dtype=np.float64,
    )
    maximum_forecast_age = np.asarray(
        normalized_policy["maximumForecastAgeSByGateId1To8"],
        dtype=np.float64,
    )
    required_forecast_coverage = np.asarray(
        normalized_policy["requiredForecastCoverageSByGateId1To8"],
        dtype=np.float64,
    )
    # Waiting-for-dwell, opening, and open-hold intervals all rely on positive
    # safety evidence.  That evidence must remain fresh through the entire
    # accepted interval.  Fail-closed motion is intentionally exempt so stale
    # evidence can never prevent closure.
    for index, row in enumerate(rows):
        positive_evidence_interval = bool(
            eligible[index]
            or order[index] == "OPEN"
            or (order[index] == "HOLD" and intent[index])
        )
        if not positive_evidence_interval:
            continue
        head = row.get("head")
        forecast = row.get("forecast")
        require(isinstance(head, Mapping), "bound live-head evidence is missing")
        require(isinstance(forecast, Mapping), "bound forecast evidence is missing")
        head_age = _finite(
            head.get("observationAgeS"), "bound head observation age"
        )
        forecast_age = _finite(forecast.get("ageS"), "bound forecast age")
        forecast_coverage = _finite(
            forecast.get("remainingCoverageS"),
            "bound forecast remaining coverage",
        )
        require(
            head_age + elapsed <= maximum_head_age[index] + 1.0e-12,
            "positive-control interval outlives verified live-head freshness",
        )
        require(
            forecast_age + elapsed <= maximum_forecast_age[index] + 1.0e-12,
            "positive-control interval outlives verified forecast freshness",
        )
        require(
            forecast_coverage + 1.0e-12
            >= required_forecast_coverage[index] + elapsed,
            "positive-control interval leaves insufficient full-closing forecast coverage",
        )
    next_current = advance_fractional_capacity(
        current,
        target,
        elapsed_seconds=elapsed,
        full_opening_stroke_seconds=normalized_policy[
            "fullOpeningStrokeSecondsByGateId1To8"
        ],
        full_closing_stroke_seconds=normalized_policy[
            "fullClosingStrokeSecondsByGateId1To8"
        ],
    )
    tolerance = float(normalized_policy["capacityZeroTolerance"])
    previous_dwell = np.asarray(state["dwell"], dtype=np.float64)
    next_dwell = np.zeros(MAIN_GATE_COUNT, dtype=np.float64)
    for index in range(MAIN_GATE_COUNT):
        if intent[index] or current[index] > tolerance or next_current[index] > tolerance:
            next_dwell[index] = 0.0
        elif eligible[index]:
            next_dwell[index] = previous_dwell[index] + elapsed
        else:
            next_dwell[index] = 0.0
    return _serialize_state(
        next_current,
        target,
        intent,
        next_dwell,
        order,
        origin="ADVANCED",
        parent_state_binding_sha256=str(state["stateBindingSha256"]),
        source_decision_binding_sha256=str(decision_binding),
    )


def resolve_and_advance_controller_state(
    *,
    elapsed_seconds: object,
    controller_state: Mapping[str, object],
    policy: Mapping[str, object],
    **resolution_inputs: object,
) -> dict[str, object]:
    """Atomically resolve and advance one bounded, observation-verified interval.

    This is the preferred integration API.  The split resolve/advance calls
    remain available for review and logging, but ``advance_controller_state``
    independently verifies the same decision seal and deterministic replay.
    """

    decision = resolve_motion_target(
        controller_state=controller_state,
        policy=policy,
        **resolution_inputs,
    )
    next_state = advance_controller_state(
        controller_state=controller_state,
        decision=decision,
        elapsed_seconds=elapsed_seconds,
        policy=policy,
    )
    return {
        "decision": decision,
        "controllerState": next_state,
    }
