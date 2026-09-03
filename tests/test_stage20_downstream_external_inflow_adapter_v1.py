from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_downstream_external_inflow_adapter_v1.py"
SPEC = importlib.util.spec_from_file_location("downstream_external_inflow_adapter_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


def synthetic_case() -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    geometry = {
        "left": np.array([0, 3], dtype=np.int64),
        "right": np.array([1, 2], dtype=np.int64),
        "internalLengths": np.array([2.0, 1.0], dtype=np.float64),
        "internalNormals": np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64),
    }
    faces = np.array([0, 1], dtype=np.int64)
    upstream = np.array([0, 2], dtype=np.int64)
    component = np.array([1, 0, 1, 0], dtype=np.uint8)
    areas = np.array([10.0, 20.0, 30.0, 40.0], dtype=np.float64)
    return geometry, faces, upstream, component, areas


class DownstreamExternalInflowAdapterV1Tests(unittest.TestCase):
    def test_layout_orients_every_face_from_upstream_to_downstream(self) -> None:
        geometry, faces, upstream, component, areas = synthetic_case()
        layout = ADAPTER.build_external_inflow_layout(
            geometry, faces, upstream, component, areas
        )
        np.testing.assert_array_equal(layout["downstreamCellIdByFace"], [1, 3])
        np.testing.assert_allclose(
            layout["downstreamNormalByFace"], [[1.0, 0.0], [0.0, -1.0]]
        )
        np.testing.assert_array_equal(layout["downstreamOutputCellMask"], [0, 1, 0, 1])
        self.assertFalse(layout["usesUpstreamDonorVolume"])
        self.assertFalse(layout["reverseFlowPermitted"])

    def test_exact_mass_and_downstream_momentum_are_added(self) -> None:
        geometry, faces, upstream, component, areas = synthetic_case()
        layout = ADAPTER.build_external_inflow_layout(
            geometry, faces, upstream, component, areas
        )
        state = np.array(
            [[2.0, 0.0, 0.0], [1.0, 0.0, 0.0], [3.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
            dtype=np.float64,
        )
        report = ADAPTER.apply_external_inflow(state, areas, layout, 6.0, 0.5)
        next_state = report["nextState"]
        self.assertAlmostEqual(report["wetCrossSectionM2"], 4.0)
        self.assertAlmostEqual(report["inflowVelocityMPS"], 1.5)
        self.assertAlmostEqual(report["addedVolumeM3"], 3.0)
        self.assertAlmostEqual(report["effectiveReleaseM3S"], 6.0)
        self.assertAlmostEqual(report["sourceResidualM3S"], 0.0)
        self.assertAlmostEqual(report["sourceResidualRelative"], 0.0)
        self.assertEqual(
            report["stateDeltaSourceResidualTreatment"],
            "FLOAT64_DIAGNOSTIC_ONLY",
        )
        self.assertAlmostEqual(report["commandedSourceResidualM3S"], 0.0)
        self.assertAlmostEqual(report["commandedSourceResidualRelative"], 0.0)
        np.testing.assert_array_equal(next_state[[0, 2]], state[[0, 2]])
        self.assertGreater(next_state[1, 1], 0.0)
        self.assertLess(next_state[3, 2], 0.0)
        self.assertFalse(report["upstreamStateChanged"])
        self.assertGreater(report["minimumFaceDownstreamMomentumFluxM4S2"], 0.0)

    def test_zero_release_is_an_exact_no_op(self) -> None:
        geometry, faces, upstream, component, areas = synthetic_case()
        layout = ADAPTER.build_external_inflow_layout(
            geometry, faces, upstream, component, areas
        )
        state = np.ones((4, 3), dtype=np.float64)
        report = ADAPTER.apply_external_inflow(state, areas, layout, 0.0, 0.05)
        np.testing.assert_array_equal(report["nextState"], state)
        self.assertEqual(report["effectiveReleaseM3S"], 0.0)
        self.assertEqual(report["sourceResidualRelative"], 0.0)
        self.assertEqual(report["commandedSourceResidualM3S"], 0.0)
        self.assertEqual(report["commandedSourceResidualRelative"], 0.0)

    def test_hour_boundary_microstep_state_delta_residual_is_diagnostic(self) -> None:
        geometry, faces, upstream, component, areas = synthetic_case()
        layout = ADAPTER.build_external_inflow_layout(
            geometry, faces, upstream, component, areas
        )
        state = np.array(
            [[2.0, 0.0, 0.0], [50.0, 0.0, 0.0], [3.0, 0.0, 0.0], [75.0, 0.0, 0.0]],
            dtype=np.float64,
        )
        report = ADAPTER.apply_external_inflow(
            state,
            areas,
            layout,
            release_m3_s=24.5,
            accepted_dt_s=17.6785e-6,
        )
        self.assertEqual(
            report["stateDeltaSourceResidualTreatment"],
            "FLOAT64_DIAGNOSTIC_ONLY",
        )
        self.assertGreater(abs(report["sourceResidualRelative"]), 1.0e-10)
        self.assertLessEqual(
            abs(report["commandedSourceResidualRelative"]),
            ADAPTER.COMMANDED_SOURCE_RESIDUAL_RELATIVE_TOLERANCE,
        )

    def test_reverse_release_is_rejected(self) -> None:
        geometry, faces, upstream, component, areas = synthetic_case()
        layout = ADAPTER.build_external_inflow_layout(
            geometry, faces, upstream, component, areas
        )
        state = np.ones((4, 3), dtype=np.float64)
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            ADAPTER.apply_external_inflow(state, areas, layout, -1.0, 0.05)

    def test_velocity_guard_fails_without_clipping(self) -> None:
        geometry, faces, upstream, component, areas = synthetic_case()
        layout = ADAPTER.build_external_inflow_layout(
            geometry, faces, upstream, component, areas
        )
        state = np.zeros((4, 3), dtype=np.float64)
        with self.assertRaisesRegex(ValueError, "no-clipping"):
            ADAPTER.apply_external_inflow(
                state,
                areas,
                layout,
                release_m3_s=100.0,
                accepted_dt_s=0.05,
                minimum_flow_depth_m=0.01,
                maximum_inflow_velocity_m_s=1.0,
            )

    def test_misoriented_face_is_rejected(self) -> None:
        geometry, faces, upstream, component, areas = synthetic_case()
        with self.assertRaisesRegex(ValueError, "exactly one side"):
            ADAPTER.build_external_inflow_layout(
                geometry,
                faces,
                np.array([3, 2], dtype=np.int64),
                component,
                areas,
            )


if __name__ == "__main__":
    unittest.main()
