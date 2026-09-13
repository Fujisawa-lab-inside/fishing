from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_yoda_gate_camera_temporal_derain_v1 as derain


def write_frame(path: Path, value: int, changed_pixel: tuple[int, int] | None = None) -> None:
    array = np.full((12, 16, 3), value, dtype=np.uint8)
    if changed_pixel is not None:
        array[changed_pixel] = 255
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array, mode="RGB").save(path, format="PNG")


class TemporalDerainTests(unittest.TestCase):
    def test_01_temporal_median_rejects_single_frame_occlusion(self) -> None:
        frames = np.full((3, 4, 5, 3), 40, dtype=np.uint8)
        frames[0, 1, 2] = 255
        median, dispersion = derain.temporal_median_and_dispersion(frames)
        self.assertTrue(np.all(median == 40))
        self.assertEqual(dispersion.shape, (4, 5))

    def test_02_window_must_be_odd_and_bounded(self) -> None:
        for count in (0, 2, 4, 16, 17):
            with self.assertRaises(derain.TemporalDerainError):
                derain.validate_window_size(count)
        derain.validate_window_size(3)
        derain.validate_window_size(15)

    def test_03_discovers_latest_fetched_camera_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected: list[Path] = []
            for minute in (0, 10, 20, 30):
                run = root / "runs/2026/09/13" / f"20260913T12{minute:02d}+0900"
                frame = run / "raw/barrage-camera.png"
                write_frame(frame, 30 + minute)
                observation = {
                    "runId": run.name,
                    "sources": {"barrageCamera": {"status": "FETCHED", "relativePath": "raw/barrage-camera.png"}},
                }
                (run / "observation.json").write_text(json.dumps(observation), encoding="utf-8")
                expected.append(frame)
            found = derain.discover_recent_frames(root, 3)
            self.assertEqual(found, expected[-3:])

    def test_04_generates_auditable_visual_aid_without_state_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frames = []
            for index, pixel in enumerate(((2, 3), (3, 4), (4, 5))):
                frame = root / f"frame-{index}.png"
                write_frame(frame, 50, pixel)
                frames.append(frame)
            result = derain.generate_visual_aid(frames, root / "derived")
            self.assertEqual(result["status"], derain.STATUS)
            self.assertFalse(result["boundary"]["rawImagesModified"])
            self.assertFalse(result["boundary"]["gateStateInferred"])
            self.assertFalse(result["boundary"]["trainingLabelGenerated"])
            self.assertTrue(Path(result["outputs"]["temporalMedian"]["path"]).is_file())
            report = json.loads((root / "derived/report.json").read_text())
            self.assertEqual(report["frameCount"], 3)
            self.assertNotIn("reportPath", report)


if __name__ == "__main__":
    unittest.main()
