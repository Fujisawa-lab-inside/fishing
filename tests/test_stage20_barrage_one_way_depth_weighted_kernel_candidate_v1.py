from __future__ import annotations

import sys
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_barrage_one_way_depth_weighted_kernel_candidate_v1 as candidate  # noqa: E402
import stage20_depth_weighted_boundary_kernel_candidate_v2 as legacy  # noqa: E402
import stage20_regularized_stage4_ramp_hold_600s_runner_v1 as stage4  # noqa: E402


def two_cell_arguments(left_depth: float, right_depth: float, *, multiplier: float = 1.0):
    state = np.asarray(
        [[left_depth, 0.0, 0.0], [right_depth, 0.0, 0.0]],
        dtype=np.float64,
    )
    common = (
        state,
        np.zeros(2, dtype=np.float64),
        np.zeros(2, dtype=np.float64),
        np.ones(2, dtype=np.float64),
        np.ones(2, dtype=np.float64),
        np.asarray([0], dtype=np.int64),
        np.asarray([1], dtype=np.int64),
        np.asarray([1.0], dtype=np.float64),
        np.asarray([[1.0, 0.0]], dtype=np.float64),
        np.asarray([multiplier], dtype=np.float64),
        np.empty(0, dtype=np.int64),
        np.empty(0, dtype=np.float64),
        np.empty((0, 2), dtype=np.float64),
        np.empty(0, dtype=np.uint8),
        0.0,
        np.zeros(5, dtype=np.float64),
        np.zeros(2, dtype=np.float64),
        np.zeros(2, dtype=np.float64),
        0.0,
        0.12,
        0.01,
    )
    return common


class Stage20BarrageOneWayDepthWeightedKernelCandidateV1Tests(unittest.TestCase):
    def test_outward_two_cell_step_is_bit_exact_to_legacy(self) -> None:
        arguments = two_cell_arguments(2.0, 1.0)
        old = legacy.advance_h2_step_depth_weighted_boundary_with_trace_v1(*arguments)
        new = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
            *arguments, np.asarray([0], dtype=np.int64)
        )
        self.assertEqual(new.blocked_reverse_face_count, 0)
        self.assertEqual(new.blocked_reverse_potential_discharge_m3_s, 0.0)
        self.assertEqual(new.next_state.tobytes(), old.next_state.tobytes())
        self.assertEqual(tuple(new[1:6]), tuple(old[1:6]))
        self.assertEqual(new.limiter_sample, old.limiter_sample)

    def test_adverse_two_cell_step_blocks_mass_and_preserves_volume(self) -> None:
        arguments = two_cell_arguments(1.0, 2.0)
        state = arguments[0]
        new = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
            *arguments, np.asarray([0], dtype=np.int64)
        )
        self.assertEqual(new.blocked_reverse_face_count, 1)
        self.assertGreater(new.blocked_reverse_potential_discharge_m3_s, 0.0)
        self.assertEqual(new.next_state[:, 0].tobytes(), state[:, 0].tobytes())
        self.assertEqual(float(np.sum(new.next_state[:, 0])), float(np.sum(state[:, 0])))
        self.assertTrue(np.isfinite(new.next_state).all())
        self.assertEqual(new.limiter_sample.expected_candidate_count, 2)
        self.assertEqual(new.limiter_sample.evaluated_candidate_count, 2)
        self.assertTrue(new.limiter_sample.coverage_complete)

    def test_lake_at_rest_is_bit_exact_to_legacy(self) -> None:
        arguments = two_cell_arguments(1.0, 1.0)
        old = legacy.advance_h2_step_depth_weighted_boundary_with_trace_v1(*arguments)
        new = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
            *arguments, np.asarray([0], dtype=np.int64)
        )
        self.assertEqual(new.blocked_reverse_face_count, 0)
        self.assertEqual(new.next_state.tobytes(), old.next_state.tobytes())
        self.assertEqual(new.next_state[:, 0].tobytes(), arguments[0][:, 0].tobytes())

    def test_adverse_dry_upstream_face_is_blocked_without_negative_depth(self) -> None:
        arguments = two_cell_arguments(0.0, 1.0)
        new = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
            *arguments, np.asarray([0], dtype=np.int64)
        )
        self.assertEqual(new.blocked_reverse_face_count, 1)
        self.assertTrue(np.isfinite(new.next_state).all())
        self.assertTrue(np.all(new.next_state[:, 0] >= 0.0))
        self.assertEqual(new.next_state[:, 0].tobytes(), arguments[0][:, 0].tobytes())

    def test_closed_face_uses_wall_without_counting_reverse_branch(self) -> None:
        arguments = two_cell_arguments(1.0, 2.0, multiplier=0.0)
        new = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
            *arguments, np.asarray([0], dtype=np.int64)
        )
        self.assertEqual(new.blocked_reverse_face_count, 0)
        self.assertEqual(new.blocked_reverse_potential_discharge_m3_s, 0.0)
        self.assertEqual(new.next_state[:, 0].tobytes(), arguments[0][:, 0].tobytes())

    def test_invalid_orientation_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid one-way upstream"):
            candidate.advance_h2_step_barrage_one_way_with_trace_v1(
                *two_cell_arguments(2.0, 1.0), np.asarray([7], dtype=np.int64)
            )

    def test_real_context_outward_mid_ramp_is_bit_exact(self) -> None:
        context = stage4.load_runtime_context()
        forcing = stage4.matched.base.read_json(stage4.FORCING_PATH)
        capacity = stage4.requested_capacity(150.0)
        stage4.mapping.update_mapping_workspace(context["workspace"], capacity)
        tide, discharge = stage4._forcing_values(forcing, context["geometry"], 150.0)
        geometry = context["geometry"]
        orientation = np.full(len(geometry["left"]), -1, dtype=np.int64)
        orientation[context["gate"]["gateFaces"]] = context["gate"]["upstream"]
        arguments = (
            context["state"], context["bed"], context["manning"],
            geometry["areas"], geometry["inverseAreas"], geometry["left"],
            geometry["right"], context["workspace"]["effectiveLengths"],
            geometry["internalNormals"], context["workspace"]["multipliers"],
            geometry["boundaryCells"], geometry["boundaryLengths"],
            geometry["boundaryNormals"], geometry["boundaryTags"], tide,
            discharge, context["donor"], context["receiver"], 0.0, 0.12, 0.05,
        )
        old = legacy.advance_h2_step_depth_weighted_boundary_with_trace_v1(*arguments)
        new = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
            *arguments, orientation
        )
        self.assertEqual(new.blocked_reverse_face_count, 0)
        self.assertEqual(new.next_state.tobytes(), old.next_state.tobytes())
        self.assertEqual(tuple(new[1:6]), tuple(old[1:6]))
        self.assertEqual(new.limiter_sample, old.limiter_sample)
        self.assertEqual(new.limiter_sample.expected_candidate_count, len(context["state"]))
        self.assertEqual(new.limiter_sample.evaluated_candidate_count, len(context["state"]))
        self.assertTrue(new.limiter_sample.coverage_complete)

    def test_real_context_adverse_head_blocks_and_preserves_mass_balance(self) -> None:
        context = stage4.load_runtime_context()
        forcing = stage4.matched.base.read_json(stage4.FORCING_PATH)
        state = context["state"].copy()
        selected = np.isin(context["gate"]["gateIds"], [3, 4, 5, 6])
        downstream = np.unique(context["gate"]["downstream"][selected])
        state[downstream, 0] += 0.30
        capacity = stage4.requested_capacity(150.0)
        stage4.mapping.update_mapping_workspace(context["workspace"], capacity)
        tide, discharge = stage4._forcing_values(forcing, context["geometry"], 150.0)
        geometry = context["geometry"]
        orientation = np.full(len(geometry["left"]), -1, dtype=np.int64)
        orientation[context["gate"]["gateFaces"]] = context["gate"]["upstream"]
        step = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
            state, context["bed"], context["manning"], geometry["areas"],
            geometry["inverseAreas"], geometry["left"], geometry["right"],
            context["workspace"]["effectiveLengths"], geometry["internalNormals"],
            context["workspace"]["multipliers"], geometry["boundaryCells"],
            geometry["boundaryLengths"], geometry["boundaryNormals"],
            geometry["boundaryTags"], tide, discharge, context["donor"],
            context["receiver"], 0.0, 0.12, 0.05, orientation,
        )
        self.assertGreater(step.blocked_reverse_face_count, 0)
        self.assertGreater(step.blocked_reverse_potential_discharge_m3_s, 0.0)
        initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        final_volume = float(np.sum(step.next_state[:, 0] * geometry["areas"]))
        expected = initial_volume - step.accepted_dt_s * step.boundary_outflow_m3_s
        self.assertLessEqual(abs(final_volume - expected) / initial_volume, 1.0e-12)
        self.assertTrue(np.isfinite(step.next_state).all())
        self.assertTrue(np.all(step.next_state[:, 0] >= 0.0))
        self.assertEqual(step.effective_fishway_discharge_m3_s, 0.0)
        self.assertEqual(step.fishway_source_residual_m3_s, 0.0)
        self.assertEqual(step.limiter_sample.expected_candidate_count, len(state))
        self.assertEqual(step.limiter_sample.evaluated_candidate_count, len(state))
        self.assertTrue(step.limiter_sample.coverage_complete)


if __name__ == "__main__":
    unittest.main()
