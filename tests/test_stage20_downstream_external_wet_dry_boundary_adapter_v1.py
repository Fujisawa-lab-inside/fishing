from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import stage20_downstream_external_wet_dry_boundary_adapter_v1 as adapter  # noqa: E402


class DownstreamExternalWetDryBoundaryAdapterV1Tests(unittest.TestCase):
    def test_dry_bank_face_becomes_wall_while_wet_face_carries_section(self) -> None:
        state = np.asarray(
            [
                [0.5 * adapter.RIVER_BOUNDARY_DRY_DEPTH_M, 0.0, 0.0],
                [0.4, 0.0, 0.0],
                [0.2, 0.0, 0.0],
            ],
            dtype=np.float64,
        )
        cells = np.asarray([0, 1, 2], dtype=np.int64)
        lengths = np.asarray([2.0, 3.0, 4.0], dtype=np.float64)
        tags = np.asarray([2, 2, 0], dtype=np.uint8)
        discharge = np.zeros(5, dtype=np.float64)
        discharge[2] = -0.7 / 5.0
        original = tags.copy()

        result = adapter.build_safe_boundary_tags(
            state,
            cells,
            lengths,
            tags,
            discharge,
        )

        self.assertEqual(result["boundaryTags"].tolist(), [0, 2, 0])
        self.assertEqual(result["wetFaceCountByTag"][2], 1)
        self.assertEqual(result["dryFaceCountByTag"][2], 1)
        self.assertAlmostEqual(result["wetDepthLengthM2ByTag"][2], 1.2)
        self.assertTrue(np.array_equal(tags, original))

    def test_fully_dry_nonzero_section_fails_closed(self) -> None:
        state = np.zeros((2, 3), dtype=np.float64)
        discharge = np.zeros(5, dtype=np.float64)
        discharge[4] = -0.5
        with self.assertRaisesRegex(ValueError, "fully dry: tag 4"):
            adapter.build_safe_boundary_tags(
                state,
                np.asarray([0, 1], dtype=np.int64),
                np.ones(2, dtype=np.float64),
                np.asarray([4, 4], dtype=np.uint8),
                discharge,
            )

    def test_zero_discharge_fully_dry_section_is_a_wall(self) -> None:
        result = adapter.build_safe_boundary_tags(
            np.zeros((2, 3), dtype=np.float64),
            np.asarray([0, 1], dtype=np.int64),
            np.ones(2, dtype=np.float64),
            np.asarray([3, 3], dtype=np.uint8),
            np.zeros(5, dtype=np.float64),
        )
        self.assertEqual(result["boundaryTags"].tolist(), [0, 0])
        self.assertEqual(result["dryFaceCountByTag"][3], 2)

    def test_negative_boundary_depth_is_rejected(self) -> None:
        state = np.asarray([[-1.0e-12, 0.0, 0.0]], dtype=np.float64)
        with self.assertRaisesRegex(ValueError, "depth is invalid"):
            adapter.build_safe_boundary_tags(
                state,
                np.asarray([0], dtype=np.int64),
                np.asarray([1.0], dtype=np.float64),
                np.asarray([2], dtype=np.uint8),
                np.zeros(5, dtype=np.float64),
            )


if __name__ == "__main__":
    unittest.main()
