from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_yoda_youtube_gate_event_watch_v1 as watcher


TOKYO = ZoneInfo("Asia/Tokyo")


class YodaYouTubeGateEventWatchTests(unittest.TestCase):
    def test_01_reads_sha_bound_official_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "runs/2026/09/13/example"
            run.mkdir(parents=True)
            observation = {
                "parsed": {
                    "barragePoint": {
                        "observedAt": "2026-09-13T23:20+09:00",
                        "values": {"barrageInflowM3S": 13.6, "barrageReleaseM3S": 0.4},
                    }
                }
            }
            raw = (json.dumps(observation, sort_keys=True) + "\n").encode()
            (run / "observation.json").write_bytes(raw)
            (root / "latest.json").write_text(
                json.dumps(
                    {
                        "status": "COMPLETE_CAPTURE_NO_GATE_INFERENCE",
                        "runId": "example",
                        "runRelativePath": "runs/2026/09/13/example",
                        "observationSha256": hashlib.sha256(raw).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            actual = watcher.read_official_observation(root)
            self.assertEqual(actual["barrageReleaseM3S"], 0.4)
            self.assertEqual(actual["barrageInflowM3S"], 13.6)

    def test_02_low_release_does_not_capture(self) -> None:
        now = datetime(2026, 9, 13, 23, 50, tzinfo=TOKYO)
        decision = watcher.capture_decision(
            {"barrageReleaseM3S": 0.4},
            {"lastObservedReleaseM3S": 0.3, "lastCaptureAttemptAtJst": None},
            now,
            release_trigger_m3s=1.0,
            release_rise_trigger_m3s=0.5,
            minimum_seconds_between_attempts=3600,
        )
        self.assertEqual(decision, (False, "release_below_trigger_without_large_rise"))

    def test_03_release_rise_triggers_one_bounded_capture(self) -> None:
        now = datetime(2026, 9, 13, 23, 50, tzinfo=TOKYO)
        should_capture, reason = watcher.capture_decision(
            {"barrageReleaseM3S": 0.9},
            {"lastObservedReleaseM3S": 0.3, "lastCaptureAttemptAtJst": None},
            now,
            release_trigger_m3s=1.0,
            release_rise_trigger_m3s=0.5,
            minimum_seconds_between_attempts=3600,
        )
        self.assertTrue(should_capture)
        self.assertEqual(reason, "release_rise_trigger")

    def test_04_elevated_release_respects_hourly_cooldown(self) -> None:
        now = datetime(2026, 9, 14, 0, 30, tzinfo=TOKYO)
        decision = watcher.capture_decision(
            {"barrageReleaseM3S": 20.0},
            {"lastObservedReleaseM3S": 18.0, "lastCaptureAttemptAtJst": "2026-09-14T00:00:00+09:00"},
            now,
            release_trigger_m3s=1.0,
            release_rise_trigger_m3s=0.5,
            minimum_seconds_between_attempts=3600,
        )
        self.assertEqual(decision, (False, "capture_cooldown_active"))

    def test_05_state_preserves_non_inference_boundaries(self) -> None:
        now = datetime(2026, 9, 13, 23, 50, tzinfo=TOKYO)
        state = watcher.initial_state(
            started_at=now,
            end_at=datetime(2026, 9, 14, 13, 0, tzinfo=TOKYO),
            collection_root=Path("/observation"),
            output_root=Path("/youtube"),
            parameters={},
        )
        self.assertFalse(state["boundary"]["gateStateInferred"])
        self.assertFalse(state["boundary"]["lampAbsenceInterpretedAsClosed"])
        self.assertFalse(state["boundary"]["hydraulicSolverExecuted"])


if __name__ == "__main__":
    unittest.main()
