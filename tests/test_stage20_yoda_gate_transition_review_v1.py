from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_yoda_gate_transition_review_v1 as review


JST = timezone(timedelta(hours=9))


def write_observation(root: Path, minute: int, release: float, *, detail: bool = True) -> dict:
    observed = datetime(2026, 9, 13, 16, 0, tzinfo=JST) + timedelta(minutes=minute)
    run_id = observed.strftime("%Y%m%dT%H%M%z")
    run = root / "runs" / observed.strftime("%Y/%m/%d") / run_id
    image_path = run / "raw/barrage-camera.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    base = np.full((480, 640, 3), 120, dtype=np.uint8)
    if detail:
        base[90:290:4, 130:610:4] = 230
    Image.fromarray(base, mode="RGB").save(image_path, format="JPEG", quality=95)
    document = {
        "runId": run_id,
        "captureStartedAtJst": (observed + timedelta(minutes=2)).isoformat(timespec="seconds"),
        "sources": {"barrageCamera": {"status": "FETCHED", "relativePath": "raw/barrage-camera.jpg"}},
        "parsed": {
            "barragePoint": {
                "observedAt": observed.isoformat(timespec="minutes"),
                "values": {
                    "barrageInflowM3S": 15.0,
                    "barrageReleaseM3S": release,
                    "barrageUpstreamLevelM": 1.4,
                    "barrageDownstreamLevelM": 0.1,
                },
            }
        },
    }
    observation_path = run / "observation.json"
    observation_path.write_text(json.dumps(document), encoding="utf-8")
    return review.load_record(observation_path)


def write_roi_config(path: Path) -> None:
    rois = []
    for offset, gate_id in enumerate(review.EXPECTED_GATE_IDS):
        x0 = 140 + offset * 40
        rois.append({"gateId": gate_id, "bboxPx": [x0, 100, x0 + 35, 180]})
    path.write_text(
        json.dumps(
            {
                "status": "CANDIDATE_REQUIRES_HUMAN_CONFIRMATION",
                "cameraImageSizePx": [640, 480],
                "candidateRoisNearToFar": rois,
                "fieldObservedStateCue": {
                    "cue": "paired rotating lamps",
                    "trainingLabelApproved": False,
                },
                "boundary": {"gateStateInferred": False, "trainingLabelGenerated": False},
            }
        ),
        encoding="utf-8",
    )


class TransitionReviewTests(unittest.TestCase):
    def test_01_selects_release_drop_and_clear_plateau_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [
                write_observation(root, 0, 55.0, detail=False),
                write_observation(root, 10, 58.0, detail=True),
                write_observation(root, 20, 57.0, detail=False),
                write_observation(root, 30, 0.1, detail=False),
                write_observation(root, 40, 0.1, detail=True),
            ]
            pair = review.select_transition_pair(rows)
            self.assertEqual(pair["transitionDirection"], "release_drop")
            self.assertEqual(pair["high"]["releaseM3S"], 58.0)
            self.assertEqual(pair["low"]["pointObservedAtJst"].minute, 40)
            self.assertGreater(pair["releaseDeltaM3S"], 50.0)

    def test_02_rejects_sequence_without_material_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [write_observation(root, 0, 5.0), write_observation(root, 10, 6.0)]
            with self.assertRaises(review.TransitionReviewError):
                review.select_transition_pair(rows)

    def test_03_roi_config_stays_candidate_and_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rois.json"
            write_roi_config(path)
            _, rois = review.load_rois(path, (640, 480))
            self.assertEqual([row["gateId"] for row in rois], review.EXPECTED_GATE_IDS)
            document = json.loads(path.read_text())
            document["candidateRoisNearToFar"].reverse()
            path.write_text(json.dumps(document))
            with self.assertRaises(review.TransitionReviewError):
                review.load_rois(path, (640, 480))

    def test_04_generates_auditable_review_without_gate_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            high = write_observation(root, 0, 59.1)
            low = write_observation(root, 10, 0.1)
            roi_path = root / "rois.json"
            write_roi_config(roi_path)
            output = root / "review"
            report = review.generate_review(
                root,
                roi_path,
                output,
                high_run_id=high["runId"],
                low_run_id=low["runId"],
            )
            self.assertEqual(report["status"], review.STATUS)
            self.assertFalse(report["boundary"]["perGateStateInferred"])
            self.assertFalse(report["boundary"]["trainingLabelGenerated"])
            self.assertFalse(report["boundary"]["rotatingLampCoordinatesConfirmed"])
            self.assertEqual(report["roiConfig"]["fieldObservedStateCue"]["cue"], "paired rotating lamps")
            self.assertTrue((output / "gate-transition-review.png").is_file())
            self.assertTrue((output / "rotating-lamp-sequence-review.png").is_file())
            self.assertEqual(report["rotatingLampSequenceReview"]["highAvailableFrameCount"], 1)
            self.assertEqual(report["rotatingLampSequenceReview"]["lowAvailableFrameCount"], 1)
            saved = json.loads((output / "report.json").read_text())
            self.assertEqual(saved["selectionMode"], "explicit")
            self.assertNotIn("reportPath", saved)

    def test_05_refuses_to_overwrite_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            high = write_observation(root, 0, 59.1)
            low = write_observation(root, 10, 0.1)
            roi_path = root / "rois.json"
            write_roi_config(roi_path)
            output = root / "review"
            output.mkdir()
            with self.assertRaises(review.TransitionReviewError):
                review.generate_review(root, roi_path, output, high_run_id=high["runId"], low_run_id=low["runId"])


if __name__ == "__main__":
    unittest.main()
