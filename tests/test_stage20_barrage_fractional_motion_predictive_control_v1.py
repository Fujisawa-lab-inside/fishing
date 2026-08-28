from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_barrage_fractional_motion_predictive_control_v1 as control  # noqa: E402
import stage20_barrage_fractional_motion_r1c_adapter_v1 as adapter  # noqa: E402


def policy(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": control.POLICY_SCHEMA,
        # Diagnostic fixture values only; these are not adopted real settings.
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


def request() -> np.ndarray:
    return np.asarray([0, 0, 1, 1, 1, 1, 0, 0], dtype=np.float64)


def resolve(
    state: dict[str, object],
    *,
    mean_head: float | None = 0.12,
    local_head: float | None = 0.10,
    prediction: float | None = 0.09,
    head_age: float | None = 0.0,
    forecast_age: float | None = 0.0,
    coverage: float | None = 300.0,
    requested: np.ndarray | None = None,
) -> dict[str, object]:
    return control.resolve_motion_target(
        requested_capacity_by_gate_id_1_to_8=(
            request() if requested is None else requested
        ),
        controller_state=state,
        mean_head_difference_m=mean_head,
        minimum_local_head_difference_m=local_head,
        head_observation_age_s=head_age,
        predicted_minimum_control_head_difference_m=prediction,
        forecast_age_s=forecast_age,
        forecast_remaining_coverage_s=coverage,
        policy=policy(),
    )


class FractionalPredictiveControlTests(unittest.TestCase):
    def test_opening_requires_full_safe_dwell_then_ramps(self) -> None:
        state = control.initial_controller_state()
        waiting = resolve(state)
        self.assertEqual(waiting["classification"], "INTERLOCK_CLOSED_OPENING_SAFE_DWELL")
        self.assertTrue(waiting["openingEligible"])
        state = control.advance_controller_state(
            controller_state=state,
            decision=waiting,
            elapsed_seconds=300.0,
            policy=policy(),
        )
        self.assertEqual(state["continuousOpeningEligibleDurationS"], 300.0)

        allowed = resolve(state)
        self.assertEqual(allowed["classification"], "FRACTIONAL_OPENING_ALLOWED")
        state = control.advance_controller_state(
            controller_state=state,
            decision=allowed,
            elapsed_seconds=30.0,
            policy=policy(),
        )
        np.testing.assert_allclose(
            state["capacityByGateId1To8"],
            np.asarray([0, 0, 0.1, 0.1, 0.1, 0.1, 0, 0]),
        )
        self.assertEqual(state["continuousOpeningEligibleDurationS"], 0.0)

    def test_hysteresis_holds_intent_below_open_but_above_close_margin(self) -> None:
        state = {
            "capacityByGateId1To8": [0, 0, 0.5, 0.5, 0.5, 0.5, 0, 0],
            "openingIntent": True,
            "continuousOpeningEligibleDurationS": 0.0,
        }
        decision = resolve(state, mean_head=0.06, local_head=0.055, prediction=0.06)
        self.assertEqual(
            decision["classification"], "OPENING_INTENT_HELD_WITHIN_HYSTERESIS"
        )
        advanced = control.advance_controller_state(
            controller_state=state,
            decision=decision,
            elapsed_seconds=30.0,
            policy=policy(),
        )
        np.testing.assert_allclose(
            advanced["capacityByGateId1To8"],
            np.asarray([0, 0, 0.6, 0.6, 0.6, 0.6, 0, 0]),
        )

    def test_predictive_closure_starts_before_live_head_becomes_adverse(self) -> None:
        state = {
            "capacityByGateId1To8": [0, 0, 0.8, 0.8, 0.8, 0.8, 0, 0],
            "openingIntent": True,
            "continuousOpeningEligibleDurationS": 0.0,
        }
        decision = resolve(state, mean_head=0.12, local_head=0.10, prediction=0.04)
        self.assertEqual(
            decision["classification"],
            "PREDICTIVE_CLOSING_FORECAST_BELOW_CLOSE_MARGIN",
        )
        advanced = control.advance_controller_state(
            controller_state=state,
            decision=decision,
            elapsed_seconds=30.0,
            policy=policy(),
        )
        np.testing.assert_allclose(
            advanced["capacityByGateId1To8"],
            np.asarray([0, 0, 0.7, 0.7, 0.7, 0.7, 0, 0]),
        )
        self.assertFalse(advanced["openingIntent"])

    def test_missing_stale_or_short_forecast_fails_closed(self) -> None:
        state = {
            "capacityByGateId1To8": [0, 0, 0.4, 0.4, 0.4, 0.4, 0, 0],
            "openingIntent": True,
            "continuousOpeningEligibleDurationS": 0.0,
        }
        missing = resolve(state, prediction=None)
        stale = resolve(state, forecast_age=61.0)
        short = resolve(state, coverage=299.0)
        self.assertEqual(missing["classification"], "INTERLOCK_CLOSING_MISSING_FORECAST")
        self.assertEqual(stale["classification"], "INTERLOCK_CLOSING_STALE_FORECAST")
        self.assertEqual(
            short["classification"],
            "INTERLOCK_CLOSING_FORECAST_COVERAGE_TOO_SHORT",
        )
        for decision in (missing, stale, short):
            np.testing.assert_array_equal(
                decision["targetCapacityByGateId1To8"], np.zeros(8)
            )

    def test_missing_local_head_fails_closed_even_when_mean_is_safe(self) -> None:
        decision = resolve(control.initial_controller_state(), local_head=None)
        self.assertEqual(
            decision["classification"], "INTERLOCK_CLOSING_MISSING_LIVE_HEAD"
        )
        self.assertFalse(decision["openingIntent"])

    def test_worst_local_face_blocks_opening_despite_safe_mean_head(self) -> None:
        state = control.initial_controller_state()
        state["continuousOpeningEligibleDurationS"] = 300.0
        decision = resolve(state, mean_head=0.20, local_head=-0.01, prediction=0.10)
        self.assertEqual(
            decision["classification"], "INTERLOCK_CLOSED_BELOW_OPEN_MARGIN"
        )
        self.assertFalse(decision["openingIntent"])

    def test_stale_live_head_starts_closing(self) -> None:
        state = {
            "capacityByGateId1To8": [0, 0, 0.5, 0.5, 0.5, 0.5, 0, 0],
            "openingIntent": True,
            "continuousOpeningEligibleDurationS": 0.0,
        }
        decision = resolve(state, head_age=31.0)
        self.assertEqual(
            decision["classification"], "INTERLOCK_CLOSING_STALE_LIVE_HEAD"
        )
        np.testing.assert_array_equal(
            decision["targetCapacityByGateId1To8"], np.zeros(8)
        )

    def test_closing_gate_cannot_reverse_until_fully_closed_and_rearmed(self) -> None:
        state = {
            "capacityByGateId1To8": [0, 0, 0.2, 0.2, 0.2, 0.2, 0, 0],
            "openingIntent": False,
            "continuousOpeningEligibleDurationS": 0.0,
        }
        decision = resolve(state)
        self.assertEqual(
            decision["classification"],
            "INTERLOCK_CLOSING_REARM_ONLY_AFTER_FULL_CLOSURE",
        )
        closed = control.advance_controller_state(
            controller_state=state,
            decision=decision,
            elapsed_seconds=60.0,
            policy=policy(),
        )
        np.testing.assert_allclose(closed["capacityByGateId1To8"], np.zeros(8))
        self.assertEqual(closed["continuousOpeningEligibleDurationS"], 0.0)
        rearming = resolve(closed)
        self.assertEqual(
            rearming["classification"], "INTERLOCK_CLOSED_OPENING_SAFE_DWELL"
        )

    def test_slew_rate_is_bounded_without_overshoot(self) -> None:
        opened = control.advance_fractional_capacity(
            np.zeros(8),
            np.ones(8),
            elapsed_seconds=30.0,
            full_opening_stroke_seconds=300.0,
            full_closing_stroke_seconds=150.0,
        )
        closed = control.advance_fractional_capacity(
            np.full(8, 0.8),
            np.zeros(8),
            elapsed_seconds=30.0,
            full_opening_stroke_seconds=300.0,
            full_closing_stroke_seconds=150.0,
        )
        saturated = control.advance_fractional_capacity(
            np.zeros(8),
            np.full(8, 0.25),
            elapsed_seconds=300.0,
            full_opening_stroke_seconds=300.0,
            full_closing_stroke_seconds=150.0,
        )
        np.testing.assert_allclose(opened, np.full(8, 0.1))
        np.testing.assert_allclose(closed, np.full(8, 0.6))
        np.testing.assert_allclose(saturated, np.full(8, 0.25))

    def test_oscillation_inside_hysteresis_does_not_chatter(self) -> None:
        state = {
            "capacityByGateId1To8": [0, 0, 1, 1, 1, 1, 0, 0],
            "openingIntent": True,
            "continuousOpeningEligibleDurationS": 0.0,
        }
        intent_transitions = 0
        previous_intent = True
        for sample in range(120):
            # Oscillate across the opening threshold's neighbourhood while
            # remaining above the separate closing threshold.
            local_head = 0.06 + 0.015 * np.sin(sample * 0.7)
            decision = resolve(
                state,
                mean_head=local_head + 0.01,
                local_head=float(local_head),
                prediction=0.06,
            )
            current_intent = bool(decision["openingIntent"])
            intent_transitions += int(current_intent != previous_intent)
            previous_intent = current_intent
            state = control.advance_controller_state(
                controller_state=state,
                decision=decision,
                elapsed_seconds=1.0,
                policy=policy(),
            )
        self.assertEqual(intent_transitions, 0)
        np.testing.assert_allclose(state["capacityByGateId1To8"], request())

    def test_policy_rejects_no_hysteresis_and_short_prediction_horizon(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than closing"):
            control.validate_policy(policy(openingHeadMarginM=0.04))
        with self.assertRaisesRegex(ValueError, "full closing stroke"):
            control.validate_policy(policy(requiredForecastCoverageS=299.0))


class FractionalR1CAdapterTests(unittest.TestCase):
    def test_head_diagnostics_expose_worst_local_face_not_only_mean(self) -> None:
        geometry = {
            "left": np.asarray([0, 2], dtype=np.int64),
            "right": np.asarray([1, 3], dtype=np.int64),
            "internalLengths": np.asarray([1.0, 3.0], dtype=np.float64),
        }
        state = np.asarray(
            [
                [1.2, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.9, 0.0, 0.0],
            ]
        )
        result = adapter.gate_head_diagnostics(
            state,
            np.zeros(4),
            geometry,
            np.asarray([0, 1]),
            np.asarray([0, 3]),
        )
        self.assertAlmostEqual(result["meanHeadDifferenceM"], -0.025)
        self.assertAlmostEqual(result["minimumLocalHeadDifferenceM"], -0.1)
        np.testing.assert_allclose(result["localHeadDifferenceM"], [0.2, -0.1])

    def test_partial_capacity_adverse_flux_remains_a_hard_rejection(self) -> None:
        capacity = np.zeros(8)
        capacity[2] = 0.25
        with self.assertRaisesRegex(ValueError, "result rejected without clipping"):
            adapter.validate_fractional_active_flux(
                np.asarray([-0.01]),
                np.asarray([2]),
                capacity,
                tolerance_m3_s=1.0e-10,
            )


if __name__ == "__main__":
    unittest.main()
