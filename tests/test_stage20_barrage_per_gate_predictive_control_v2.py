from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_barrage_per_gate_predictive_control_v2 as control  # noqa: E402


def legacy_policy(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": control.LEGACY_POLICY_SCHEMA,
        # Diagnostic fixture values only.  They are not real operating limits.
        "openingHeadMarginM": 0.08,
        "closingHeadMarginM": 0.04,
        "forecastUncertaintyM": 0.005,
        "maximumHeadObservationAgeS": 30.0,
        "maximumForecastAgeS": 60.0,
        "requiredForecastCoverageS": 300.0,
        "openingSafeDwellSeconds": 300.0,
        "fullOpeningStrokeSeconds": 300.0,
        "fullClosingStrokeSeconds": 300.0,
        "capacityZeroTolerance": 1.0e-12,
    }
    result.update(updates)
    return result


def hydraulic_model(**updates: object) -> dict[str, object]:
    result = control.diagnostic_provisional_hydraulic_model(
        discharge_coefficient_by_gate_id_1_to_8=[0.60] * 8,
        fully_open_effective_flow_area_m2_by_gate_id_1_to_8=[46.5] * 8,
        opening_to_area_exponent_by_gate_id_1_to_8=[1.5] * 8,
    )
    result.update(updates)
    return result


def policy(**updates: object) -> dict[str, object]:
    result = control.upgrade_v1_policy(
        legacy_policy(), diagnostic_hydraulic_model=hydraulic_model()
    )
    result.update(updates)
    return result


def stage4_request() -> np.ndarray:
    return np.asarray([0, 0, 1, 1, 1, 1, 0, 0], dtype=np.float64)


def vector(value: float | None) -> list[float | None]:
    return [value] * 8


def native_state(current: list[float]) -> dict[str, object]:
    return control.controller_state_from_per_gate(current)


def verified_positive_motion_evidence(
    *,
    local_head: list[float | None],
    head_age: list[float | None],
    prediction: list[float | None],
    forecast_age: list[float | None],
    coverage: list[float | None],
    mean_head: list[float | None] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": control.POSITIVE_MOTION_EVIDENCE_SCHEMA,
        "producerAdapterVersion": control.VERIFIED_R1C_ADAPTER_VERSION,
        "liveHeadObservationEvidenceSha256": "1" * 64,
        "forecastEvidenceSha256": "2" * 64,
        "perGateIndependentHeadVerified": True,
        "perGateIndependentForecastVerified": True,
        "controllerArgumentBindingSha256": (
            control.positive_motion_controller_argument_binding_sha256(
                mean_head_difference_m_by_gate_id_1_to_8=mean_head,
                local_head_difference_m_by_gate_id_1_to_8=local_head,
                head_observation_age_s_by_gate_id_1_to_8=head_age,
                predicted_minimum_control_head_difference_m_by_gate_id_1_to_8=(
                    prediction
                ),
                forecast_age_s_by_gate_id_1_to_8=forecast_age,
                forecast_remaining_coverage_s_by_gate_id_1_to_8=coverage,
            )
        ),
        "solverConnectionPerformed": False,
    }
    payload["evidencePackageSha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def resolve(
    state: dict[str, object],
    *,
    requested: np.ndarray | None = None,
    local_head: list[float | None] | None = None,
    prediction: list[float | None] | None = None,
    head_age: list[float | None] | None = None,
    forecast_age: list[float | None] | None = None,
    coverage: list[float | None] | None = None,
    selected_policy: dict[str, object] | None = None,
    verified: bool = True,
) -> dict[str, object]:
    selected_local = vector(0.10) if local_head is None else local_head
    selected_head_age = vector(0.0) if head_age is None else head_age
    selected_prediction = vector(0.09) if prediction is None else prediction
    selected_forecast_age = vector(0.0) if forecast_age is None else forecast_age
    selected_coverage = vector(330.0) if coverage is None else coverage
    return control.resolve_motion_target(
        requested_capacity_by_gate_id_1_to_8=(
            stage4_request() if requested is None else requested
        ),
        controller_state=state,
        local_head_difference_m_by_gate_id_1_to_8=(
            selected_local
        ),
        head_observation_age_s_by_gate_id_1_to_8=(
            selected_head_age
        ),
        predicted_minimum_control_head_difference_m_by_gate_id_1_to_8=(
            selected_prediction
        ),
        forecast_age_s_by_gate_id_1_to_8=(
            selected_forecast_age
        ),
        forecast_remaining_coverage_s_by_gate_id_1_to_8=(
            selected_coverage
        ),
        verified_positive_motion_evidence=(
            verified_positive_motion_evidence(
                local_head=selected_local,
                head_age=selected_head_age,
                prediction=selected_prediction,
                forecast_age=selected_forecast_age,
                coverage=selected_coverage,
            )
            if verified
            else None
        ),
        policy=policy() if selected_policy is None else selected_policy,
    )


def advanced_state(
    requested: np.ndarray,
) -> dict[str, object]:
    fast_policy = policy(
        openingSafeDwellSecondsByGateId1To8=[0.0] * 8,
        fullOpeningStrokeSecondsByGateId1To8=[1.0] * 8,
        fullClosingStrokeSecondsByGateId1To8=[1.0] * 8,
        requiredForecastCoverageSByGateId1To8=[1.0] * 8,
    )
    state = control.initial_controller_state()
    for _ in range(int(np.count_nonzero(requested))):
        decision = resolve(
            state,
            requested=requested,
            selected_policy=fast_policy,
            coverage=vector(2.0),
        )
        state = control.advance_controller_state(
            controller_state=state,
            decision=decision,
            elapsed_seconds=1.0,
            policy=fast_policy,
        )
    return state


class PerGatePredictiveControlV2Tests(unittest.TestCase):
    def test_legacy_policy_and_scalar_inputs_are_broadcast_without_hydraulic_guess(self) -> None:
        decision = control.resolve_motion_target(
            requested_capacity_by_gate_id_1_to_8=stage4_request(),
            controller_state=control.initial_controller_state(),
            mean_head_difference_m=0.12,
            minimum_local_head_difference_m=0.10,
            head_observation_age_s=0.0,
            predicted_minimum_control_head_difference_m=0.09,
            forecast_age_s=0.0,
            forecast_remaining_coverage_s=300.0,
            policy=legacy_policy(),
        )
        self.assertTrue(decision["legacyPolicyBroadcast"])
        self.assertFalse(decision["perGateIndependentHeadRepresented"])
        self.assertFalse(decision["perGateIndependentForecastRepresented"])
        self.assertFalse(decision["verifiedAdapterPositiveMotionEvidence"])
        self.assertEqual(decision["policySchema"], control.LEGACY_POLICY_SCHEMA)
        self.assertEqual(
            decision["classification"],
            "INTERLOCK_CLOSED_UNVERIFIED_ADAPTER_EVIDENCE",
        )
        self.assertEqual(len(decision["gateDecisionsById1To8"]), 8)
        self.assertEqual(
            decision["diagnosticHydraulics"]["classification"],
            "NOT_AVAILABLE_EXPLICIT_PROVISIONAL_MODEL_REQUIRED",
        )

    def test_explicit_vectors_report_independent_head_and_forecast_provenance(self) -> None:
        decision = resolve(control.initial_controller_state())
        self.assertTrue(decision["perGateIndependentHeadRepresented"])
        self.assertTrue(decision["perGateIndependentForecastRepresented"])
        self.assertTrue(decision["verifiedAdapterPositiveMotionEvidence"])
        self.assertEqual(
            decision["automaticRequestSemantics"],
            "STRICT_PREFIX_OF_APPROVED_OPENING_ORDER",
        )

    def test_plain_vectors_without_verified_adapter_cannot_authorize_positive_motion(self) -> None:
        closed = resolve(control.initial_controller_state(), verified=False)
        self.assertFalse(closed["verifiedAdapterPositiveMotionEvidence"])
        self.assertTrue(
            all(
                row["targetOpeningFraction"] == 0.0
                for row in closed["gateDecisionsById1To8"]
            )
        )
        self.assertEqual(
            closed["gateDecisionsById1To8"][4]["classification"],
            "INTERLOCK_CLOSED_UNVERIFIED_ADAPTER_EVIDENCE",
        )

        open_state = advanced_state(stage4_request())
        closing = resolve(open_state, verified=False)
        self.assertTrue(
            all(
                row["targetOpeningFraction"] == 0.0
                for row in closing["gateDecisionsById1To8"]
            )
        )
        self.assertEqual(
            closing["gateDecisionsById1To8"][4]["classification"],
            "INTERLOCK_CLOSING_UNVERIFIED_ADAPTER_EVIDENCE",
        )

    def test_manual_state_cannot_inject_intent_or_dwell_and_checkpoint_requires_seal(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot inject opening intent"):
            control.controller_state_from_per_gate(
                [0.0] * 8,
                opening_intent_by_gate_id_1_to_8=[False] * 4 + [True] + [False] * 3,
            )
        with self.assertRaisesRegex(ValueError, "cannot inject opening dwell"):
            control.controller_state_from_per_gate(
                [0.0] * 8,
                continuous_opening_eligible_duration_s_by_gate_id_1_to_8=(
                    [0.0] * 4 + [300.0] + [0.0] * 3
                ),
            )

        initial = control.initial_controller_state()
        restored = control.restore_controller_state_from_sealed_checkpoint(initial)
        self.assertEqual(restored["stateBindingSha256"], initial["stateBindingSha256"])
        unsealed = copy.deepcopy(initial)
        unsealed.pop("stateBindingSha256")
        with self.assertRaisesRegex(ValueError, "state keys are invalid"):
            control.restore_controller_state_from_sealed_checkpoint(unsealed)

        advanced = advanced_state(np.asarray([0, 0, 0, 0, 1, 0, 0, 0]))
        self.assertEqual(advanced["stateOrigin"], "ADVANCED")
        self.assertEqual(len(advanced["parentStateBindingSha256"]), 64)
        self.assertEqual(len(advanced["sourceDecisionBindingSha256"]), 64)

    def test_verified_adapter_package_tampering_is_rejected(self) -> None:
        local_head = vector(0.10)
        head_age = vector(0.0)
        prediction = vector(0.09)
        forecast_age = vector(0.0)
        coverage = vector(330.0)
        evidence = verified_positive_motion_evidence(
            local_head=local_head,
            head_age=head_age,
            prediction=prediction,
            forecast_age=forecast_age,
            coverage=coverage,
        )
        evidence["forecastEvidenceSha256"] = "3" * 64
        with self.assertRaisesRegex(ValueError, "package SHA mismatch"):
            control.resolve_motion_target(
                requested_capacity_by_gate_id_1_to_8=stage4_request(),
                controller_state=control.initial_controller_state(),
                policy=policy(),
                local_head_difference_m_by_gate_id_1_to_8=local_head,
                head_observation_age_s_by_gate_id_1_to_8=head_age,
                predicted_minimum_control_head_difference_m_by_gate_id_1_to_8=(
                    prediction
                ),
                forecast_age_s_by_gate_id_1_to_8=forecast_age,
                forecast_remaining_coverage_s_by_gate_id_1_to_8=coverage,
                verified_positive_motion_evidence=evidence,
            )

    def test_opening_order_starts_gate5_then_gate4_after_gate5_reaches_target(self) -> None:
        requested = np.zeros(8)
        requested[4] = 1.0  # Gate 5, first in the approved order.
        requested[3] = 1.0  # Gate 4, second.
        order_policy = policy(
            openingSafeDwellSecondsByGateId1To8=[0.0] * 8
        )
        first = resolve(
            control.initial_controller_state(),
            requested=requested,
            selected_policy=order_policy,
        )
        rows = first["gateDecisionsById1To8"]
        self.assertEqual(rows[4]["classification"], "FRACTIONAL_OPENING_ALLOWED")
        self.assertEqual(rows[4]["motionOrder"], "OPEN")
        self.assertEqual(rows[3]["classification"], "INTERLOCK_OPENING_ORDER_WAIT")
        self.assertEqual(rows[3]["orderBlockedByGateId"], 5)

        gate5_request = np.zeros(8)
        gate5_request[4] = 1.0
        gate5_ready = advanced_state(gate5_request)
        second = resolve(
            gate5_ready,
            requested=requested,
            selected_policy=order_policy,
        )
        self.assertEqual(
            second["gateDecisionsById1To8"][3]["classification"],
            "FRACTIONAL_OPENING_ALLOWED",
        )

    def test_one_gate_adverse_forecast_closes_only_that_gate(self) -> None:
        state = advanced_state(stage4_request())
        prediction = vector(0.09)
        prediction[4] = 0.04  # Gate 5: 0.04 - uncertainty falls below close margin.
        decision = resolve(state, prediction=prediction)
        rows = decision["gateDecisionsById1To8"]
        self.assertEqual(
            rows[4]["classification"],
            "PREDICTIVE_CLOSING_FORECAST_BELOW_CLOSE_MARGIN",
        )
        self.assertTrue(rows[4]["failClosed"])
        self.assertEqual(rows[4]["targetOpeningFraction"], 0.0)
        for gate_id in (3, 4, 6):
            row = rows[gate_id - 1]
            self.assertEqual(row["classification"], "OPENING_INTENT_HELD_WITHIN_HYSTERESIS")
            self.assertEqual(row["targetOpeningFraction"], 1.0)

    def test_stale_head_is_per_gate_and_fail_closed(self) -> None:
        state = advanced_state(stage4_request())
        ages = vector(0.0)
        ages[2] = 31.0  # Gate 3 only.
        decision = resolve(state, head_age=ages)
        rows = decision["gateDecisionsById1To8"]
        self.assertEqual(rows[2]["classification"], "INTERLOCK_CLOSING_STALE_LIVE_HEAD")
        self.assertEqual(rows[2]["motionOrder"], "FAIL_CLOSED")
        self.assertEqual(rows[2]["targetOpeningFraction"], 0.0)
        self.assertEqual(rows[3]["targetOpeningFraction"], 1.0)

    def test_missing_forecast_fails_only_affected_active_gate_closed(self) -> None:
        state = advanced_state(stage4_request())
        prediction = vector(0.09)
        prediction[5] = None
        decision = resolve(state, prediction=prediction)
        rows = decision["gateDecisionsById1To8"]
        self.assertEqual(rows[5]["classification"], "INTERLOCK_CLOSING_MISSING_FORECAST")
        self.assertEqual(rows[5]["targetOpeningFraction"], 0.0)
        self.assertEqual(rows[4]["targetOpeningFraction"], 1.0)

    def test_missing_unrequested_head_does_not_hide_available_gate_hydraulics(self) -> None:
        state = advanced_state(stage4_request())
        heads = vector(0.10)
        heads[0] = None  # Gate 1 is closed and unrequested.
        decision = resolve(state, local_head=heads)
        hydraulic = decision["diagnosticHydraulics"]["current"]
        self.assertFalse(hydraulic["headAvailableByGateId1To8"][0])
        self.assertIsNone(hydraulic["signedPotentialDischargeM3SByGateId1To8"][0])
        self.assertTrue(hydraulic["headAvailableByGateId1To8"][4])
        self.assertGreater(
            hydraulic["signedPotentialDischargeM3SByGateId1To8"][4], 0.0
        )

    def test_open_close_hysteresis_holds_each_gate_without_chatter(self) -> None:
        state = advanced_state(stage4_request())
        transitions = [0] * 8
        previous = list(state["openingIntentByGateId1To8"])
        for sample in range(120):
            heads = vector(0.06)
            heads[2] = 0.06 + 0.015 * math.sin(sample * 0.7)
            decision = resolve(state, local_head=heads, prediction=vector(0.06))
            current_intent = list(decision["openingIntentByGateId1To8"])
            transitions = [
                count + int(before != after)
                for count, before, after in zip(
                    transitions, previous, current_intent, strict=True
                )
            ]
            previous = current_intent
            state = control.advance_controller_state(
                controller_state=state,
                decision=decision,
                elapsed_seconds=1.0,
                policy=policy(),
            )
        self.assertEqual(transitions, [0] * 8)
        np.testing.assert_allclose(
            state["currentOpeningFractionByGateId1To8"], stage4_request()
        )

    def test_per_gate_rate_limits_use_separate_open_and_close_strokes(self) -> None:
        opened = control.advance_fractional_capacity(
            np.zeros(8),
            np.ones(8),
            elapsed_seconds=30.0,
            full_opening_stroke_seconds=[300, 150, 300, 150, 300, 150, 300, 150],
            full_closing_stroke_seconds=[120] * 8,
        )
        closed = control.advance_fractional_capacity(
            np.full(8, 0.8),
            np.zeros(8),
            elapsed_seconds=30.0,
            full_opening_stroke_seconds=[300] * 8,
            full_closing_stroke_seconds=[150, 300, 150, 300, 150, 300, 150, 300],
        )
        np.testing.assert_allclose(opened, [0.1, 0.2, 0.1, 0.2, 0.1, 0.2, 0.1, 0.2])
        np.testing.assert_allclose(closed, [0.6, 0.7, 0.6, 0.7, 0.6, 0.7, 0.6, 0.7])

    def test_dwell_and_ramp_are_independent_by_gate(self) -> None:
        requested = np.zeros(8)
        requested[4] = 1.0
        dwell_policy = policy(
            openingSafeDwellSecondsByGateId1To8=[30.0] * 8
        )
        state = control.initial_controller_state()
        waiting = resolve(
            state, requested=requested, selected_policy=dwell_policy
        )
        advanced = control.advance_controller_state(
            controller_state=state,
            decision=waiting,
            elapsed_seconds=20.0,
            policy=dwell_policy,
        )
        self.assertEqual(
            advanced["continuousOpeningEligibleDurationSByGateId1To8"][4], 20.0
        )
        waiting = resolve(
            advanced, requested=requested, selected_policy=dwell_policy
        )
        advanced = control.advance_controller_state(
            controller_state=advanced,
            decision=waiting,
            elapsed_seconds=10.0,
            policy=dwell_policy,
        )
        self.assertEqual(
            advanced["continuousOpeningEligibleDurationSByGateId1To8"][4], 30.0
        )
        allowed = resolve(
            advanced, requested=requested, selected_policy=dwell_policy
        )
        moved = control.advance_controller_state(
            controller_state=advanced,
            decision=allowed,
            elapsed_seconds=30.0,
            policy=dwell_policy,
        )
        self.assertAlmostEqual(moved["currentOpeningFractionByGateId1To8"][4], 0.1)
        self.assertEqual(moved["currentOpeningFractionByGateId1To8"][3], 0.0)

    def test_one_long_interval_cannot_manufacture_safe_dwell(self) -> None:
        requested = np.zeros(8)
        requested[4] = 1.0
        state = native_state([0.0] * 8)
        waiting = resolve(state, requested=requested)
        with self.assertRaisesRegex(ValueError, "observation-update limit"):
            control.advance_controller_state(
                controller_state=state,
                decision=waiting,
                elapsed_seconds=300.0,
                policy=policy(),
            )

        # Ten separately resolved, bounded intervals can establish the same
        # dwell because each interval has fresh bound evidence.
        for _ in range(10):
            waiting = resolve(state, requested=requested)
            state = control.advance_controller_state(
                controller_state=state,
                decision=waiting,
                elapsed_seconds=30.0,
                policy=policy(),
            )
        self.assertEqual(
            state["continuousOpeningEligibleDurationSByGateId1To8"][4], 300.0
        )
        self.assertEqual(
            resolve(state, requested=requested)["gateDecisionsById1To8"][4][
                "classification"
            ],
            "FRACTIONAL_OPENING_ALLOWED",
        )

    def test_dwell_interval_cannot_outlive_bound_observation_freshness(self) -> None:
        requested = np.zeros(8)
        requested[4] = 1.0
        state = native_state([0.0] * 8)
        almost_stale = resolve(
            state,
            requested=requested,
            head_age=vector(29.0),
            forecast_age=vector(59.0),
        )
        with self.assertRaisesRegex(ValueError, "outlives verified live-head"):
            control.advance_controller_state(
                controller_state=state,
                decision=almost_stale,
                elapsed_seconds=2.0,
                policy=policy(),
            )

    def test_positive_interval_must_retain_full_closing_forecast_at_interval_end(self) -> None:
        requested = np.zeros(8)
        requested[4] = 1.0
        state = control.initial_controller_state()
        exactly_required_at_start = resolve(
            state,
            requested=requested,
            coverage=vector(300.0),
        )
        with self.assertRaisesRegex(ValueError, "insufficient full-closing"):
            control.advance_controller_state(
                controller_state=state,
                decision=exactly_required_at_start,
                elapsed_seconds=1.0,
                policy=policy(),
            )

        sufficient = resolve(
            state,
            requested=requested,
            coverage=vector(301.0),
        )
        advanced = control.advance_controller_state(
            controller_state=state,
            decision=sufficient,
            elapsed_seconds=1.0,
            policy=policy(),
        )
        self.assertEqual(
            advanced["continuousOpeningEligibleDurationSByGateId1To8"][4],
            1.0,
        )

    def test_automatic_request_must_be_strict_prefix_but_manual_state_need_not_be(self) -> None:
        manual_gate4_only = native_state([0, 0, 0, 0.25, 0, 0, 0, 0])
        self.assertEqual(
            control.validate_controller_state(manual_gate4_only)["current"][3],
            0.25,
        )
        gate4_only = np.zeros(8)
        gate4_only[3] = 1.0
        with self.assertRaisesRegex(ValueError, "strict prefix"):
            resolve(manual_gate4_only, requested=gate4_only)

        closing = resolve(manual_gate4_only, requested=np.zeros(8))
        self.assertTrue(closing["manualObservedStateMayBeNonPrefix"])
        self.assertEqual(
            closing["automaticRequestedOpenGateIdsInApprovedOrder"], []
        )
        self.assertEqual(
            closing["gateDecisionsById1To8"][3]["targetOpeningFraction"], 0.0
        )

    def test_normal_closure_respects_reverse_order_but_safety_bypasses_it(self) -> None:
        all_open = advanced_state(np.ones(8))
        requested = np.zeros(8)
        normal = resolve(all_open, requested=requested)
        normal_rows = normal["gateDecisionsById1To8"]
        self.assertEqual(normal_rows[0]["motionOrder"], "CLOSE")  # Gate 1 first.
        self.assertEqual(normal_rows[7]["classification"], "INTERLOCK_CLOSING_ORDER_WAIT")

        missing_prediction = [None] * 8
        safety = resolve(all_open, requested=requested, prediction=missing_prediction)
        self.assertTrue(all(row["failClosed"] for row in safety["gateDecisionsById1To8"]))
        np.testing.assert_array_equal(safety["targetCapacityByGateId1To8"], np.zeros(8))

    def test_closing_latch_cannot_reverse_before_full_closure(self) -> None:
        state = native_state([0, 0, 0.2, 0.2, 0.2, 0.2, 0, 0])
        decision = resolve(state)
        active = [row for row in decision["gateDecisionsById1To8"] if row["gateId"] in (3, 4, 5, 6)]
        self.assertTrue(
            all(
                row["classification"]
                == "INTERLOCK_CLOSING_REARM_ONLY_AFTER_FULL_CLOSURE"
                for row in active
            )
        )
        np.testing.assert_array_equal(decision["targetCapacityByGateId1To8"], np.zeros(8))

    def test_nonlinear_capacity_and_signed_discharge_are_explicit(self) -> None:
        opening = np.asarray([0.0, 0.25, 0.5, 1.0, 0.5, 0.5, 0.5, 0.5])
        head = np.asarray([0.10, 0.10, 0.10, 0.10, -0.10, 0.0, 0.40, 0.10])
        result = control.nonlinear_gate_capacity_and_discharge(
            opening, head, hydraulic_model()
        )
        capacity = result["nonlinearCapacityFractionByGateId1To8"]
        discharge = result["signedPotentialDischargeM3SByGateId1To8"]
        self.assertAlmostEqual(capacity[2], 0.5**1.5)
        self.assertAlmostEqual(capacity[3], 1.0)
        self.assertLess(discharge[4], 0.0)
        self.assertEqual(discharge[5], 0.0)
        self.assertAlmostEqual(discharge[6] / discharge[7], 2.0)
        self.assertTrue(result["reversePotentialWasNotClipped"])
        self.assertFalse(result["solverFluxAcceptanceImplied"])

    def test_linear_opening_area_hypothesis_is_allowed_without_claiming_calibration(self) -> None:
        model = hydraulic_model(openingToAreaExponentByGateId1To8=[1.0] * 8)
        normalized = control.validate_hydraulic_model(model)
        self.assertFalse(normalized["physicalCalibrationClaimed"])
        result = control.nonlinear_gate_capacity_and_discharge(
            [0.5] * 8,
            [0.1] * 4 + [0.4] * 4,
            model,
        )
        np.testing.assert_allclose(
            result["nonlinearCapacityFractionByGateId1To8"],
            [0.5] * 8,
        )
        discharge = result["signedPotentialDischargeM3SByGateId1To8"]
        self.assertAlmostEqual(discharge[4] / discharge[0], 2.0)

    def test_controller_motion_does_not_claim_physical_or_solver_integration(self) -> None:
        decision = resolve(control.initial_controller_state())
        self.assertTrue(decision["diagnosticFiniteGateMotionRepresented"])
        self.assertFalse(decision["physicalGateMotionLagRepresented"])
        self.assertFalse(decision["solverMotionIntegrationImplied"])

    def test_decision_reports_negative_current_discharge_risk_while_targeting_closed(self) -> None:
        current = np.zeros(8)
        current[4] = 0.5
        state = native_state(current.tolist())
        requested = current.copy()
        heads = vector(0.10)
        heads[4] = -0.01
        decision = resolve(state, requested=requested, local_head=heads)
        gate5 = decision["gateDecisionsById1To8"][4]
        self.assertTrue(gate5["failClosed"])
        self.assertEqual(gate5["targetOpeningFraction"], 0.0)
        current_q = decision["diagnosticHydraulics"]["current"][
            "signedPotentialDischargeM3SByGateId1To8"
        ]
        target_q = decision["diagnosticHydraulics"]["target"][
            "signedPotentialDischargeM3SByGateId1To8"
        ]
        self.assertLess(current_q[4], 0.0)
        self.assertEqual(target_q[4], 0.0)

    def test_policy_rejects_order_drift_no_hysteresis_short_horizon_and_claimed_calibration(self) -> None:
        wrong_order = policy(openingOrderGateIds=[1, 2, 3, 4, 5, 6, 7, 8])
        with self.assertRaisesRegex(ValueError, "approved opening order changed"):
            control.validate_policy(wrong_order)

        no_hysteresis = policy(openingHeadMarginMByGateId1To8=[0.04] * 8)
        with self.assertRaisesRegex(ValueError, "opening margin"):
            control.validate_policy(no_hysteresis)

        short = policy(requiredForecastCoverageSByGateId1To8=[299.0] * 8)
        with self.assertRaisesRegex(ValueError, "full closing stroke"):
            control.validate_policy(short)

        claimed_model = hydraulic_model(physicalCalibrationClaimed=True)
        with self.assertRaisesRegex(ValueError, "cannot claim physical calibration"):
            control.validate_hydraulic_model(claimed_model)

    def test_state_alias_tampering_and_fail_closed_target_tampering_are_rejected(self) -> None:
        state = control.initial_controller_state()
        tampered_state = copy.deepcopy(state)
        tampered_state["capacityByGateId1To8"][0] = 0.1
        with self.assertRaisesRegex(ValueError, "state binding mismatch"):
            control.validate_controller_state(tampered_state)

        active = advanced_state(stage4_request())
        prediction = vector(0.09)
        prediction[4] = None
        decision = resolve(active, prediction=prediction)
        tampered_decision = copy.deepcopy(decision)
        tampered_decision["targetCapacityByGateId1To8"][4] = 0.1
        tampered_decision["gateDecisionsById1To8"][4]["targetOpeningFraction"] = 0.1
        with self.assertRaisesRegex(ValueError, "fail-closed gate target must be zero"):
            control.advance_controller_state(
                controller_state=active,
                decision=tampered_decision,
                elapsed_seconds=1.0,
                policy=policy(),
            )

    def test_structurally_similar_unsealed_or_mutated_decision_is_rejected(self) -> None:
        state = control.initial_controller_state()
        legitimate = resolve(state)

        unsealed = copy.deepcopy(legitimate)
        unsealed.pop("decisionBindingSha256")
        with self.assertRaisesRegex(ValueError, "not sealed"):
            control.advance_controller_state(
                controller_state=state,
                decision=unsealed,
                elapsed_seconds=1.0,
                policy=policy(),
            )

        mutated = copy.deepcopy(legitimate)
        mutated["classification"] = "FRACTIONAL_OPENING_ALLOWED"
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            control.advance_controller_state(
                controller_state=state,
                decision=mutated,
                elapsed_seconds=1.0,
                policy=policy(),
            )

    def test_atomic_resolve_and_advance_uses_same_sealed_path(self) -> None:
        local_head = vector(0.10)
        head_age = vector(0.0)
        prediction = vector(0.09)
        forecast_age = vector(0.0)
        coverage = vector(310.0)
        result = control.resolve_and_advance_controller_state(
            elapsed_seconds=10.0,
            requested_capacity_by_gate_id_1_to_8=stage4_request(),
            controller_state=control.initial_controller_state(),
            local_head_difference_m_by_gate_id_1_to_8=local_head,
            head_observation_age_s_by_gate_id_1_to_8=head_age,
            predicted_minimum_control_head_difference_m_by_gate_id_1_to_8=(
                prediction
            ),
            forecast_age_s_by_gate_id_1_to_8=forecast_age,
            forecast_remaining_coverage_s_by_gate_id_1_to_8=coverage,
            verified_positive_motion_evidence=verified_positive_motion_evidence(
                local_head=local_head,
                head_age=head_age,
                prediction=prediction,
                forecast_age=forecast_age,
                coverage=coverage,
            ),
            policy=policy(),
        )
        self.assertEqual(len(result["decision"]["decisionBindingSha256"]), 64)
        self.assertEqual(
            result["controllerState"][
                "continuousOpeningEligibleDurationSByGateId1To8"
            ][4],
            10.0,
        )


if __name__ == "__main__":
    unittest.main()
