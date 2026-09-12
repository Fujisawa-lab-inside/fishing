from __future__ import annotations

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

import stage20_yoda_gate_multimodal_collector_v1 as collector


TOKYO = ZoneInfo("Asia/Tokyo")


def fake_jpeg(width: int = 640, height: int = 480) -> bytes:
    frame = (
        b"\xff\xc0\x00\x11\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    )
    return b"\xff\xd8" + frame + b"\xff\xd9"


def point_html() -> bytes:
    source = """<html><body>09/12 23:10 の更新情報
    河口堰流入量 7.3m3/s
    河口堰放流量 3.9m3/s
    河口堰上水位 1.50m
    河口堰下水位 1.05m
    </body></html>"""
    return source.encode("cp932")


def history_html() -> bytes:
    rows = "\n".join(f"{hour:02d}時 {7.0 + index / 10:.1f} → {3.0 + index / 10:.1f}" for index, hour in enumerate(range(23, 11, -1)))
    source = f"<html><body>09/12 23:10 の更新情報\n■12時間履歴\n{rows}\n先頭へ</body></html>"
    return source.encode("cp932")


class FakeFetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.bodies = {
            collector.CAMERA_URL: fake_jpeg(),
            collector.POINT_URL: point_html(),
            collector.HISTORY_URL: history_html(),
            collector.AMEDAS_LATEST_URL: b"2026-09-12T23:10:00+09:00",
            collector.amedas_map_url(datetime(2026, 9, 12, 23, 10, tzinfo=TOKYO)): json.dumps(
                {
                    collector.AMEDAS_STATION_ID: {
                        "precipitation10m": [0.5, 0],
                        "precipitation1h": [1.0, 0],
                        "precipitation3h": [2.0, 0],
                        "precipitation24h": [4.0, 0],
                    }
                }
            ).encode("utf-8"),
            collector.TIDE_URL_TEMPLATE.format(year=2026): b"JMA QF 2026 tide reference\n",
        }

    def __call__(self, url: str, max_bytes: int) -> collector.Fetched:
        self.calls.append(url)
        body = self.bodies[url]
        if len(body) > max_bytes:
            raise AssertionError("fixture exceeds limit")
        return collector.Fetched(url, url, body, 200, "fixture", 0.001)


class CollectorTests(unittest.TestCase):
    def test_01_parses_amedas_time_and_rain(self) -> None:
        observed = collector.parse_amedas_latest_time(b"2026-09-12T23:10:00+09:00")
        self.assertEqual(collector.amedas_map_url(observed), "https://www.jma.go.jp/bosai/amedas/data/map/20260912231000.json")
        raw = json.dumps({collector.AMEDAS_STATION_ID: {"precipitation10m": [1.5, 0]}}).encode()
        parsed = collector.extract_amedas_rain(raw, observed)
        self.assertEqual(parsed["values"]["precipitation10m"]["valueMm"], 1.5)
        self.assertEqual(parsed["classification"], "official_point_rainfall_not_basin_average")

    def test_02_rejects_wrong_camera_dimensions(self) -> None:
        self.assertEqual(collector.jpeg_dimensions(fake_jpeg()), (640, 480))
        with self.assertRaises(collector.CaptureError):
            collector.jpeg_dimensions(b"not-jpeg")

    def test_03_complete_capture_is_atomic_and_idempotent(self) -> None:
        now = datetime(2026, 9, 12, 23, 18, 3, tzinfo=TOKYO)
        fetcher = FakeFetcher()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "observations"
            first = collector.collect_once(root, now_jst=now, fetcher=fetcher)
            self.assertEqual(first["status"], "COMPLETE_CAPTURE_NO_GATE_INFERENCE")
            self.assertEqual(first["sourceCount"], 6)
            self.assertEqual(first["fetchedSourceCount"], 6)
            self.assertEqual(len(fetcher.calls), 6)
            run = Path(first["runPath"])
            self.assertTrue((run / "raw/barrage-camera.jpg").is_file())
            document = json.loads((run / "observation.json").read_text())
            self.assertEqual(document["runId"], "20260912T2310+0900")
            self.assertFalse(document["summary"]["gateStateInferred"])
            self.assertEqual(document["parsed"]["barragePoint"]["values"]["barrageReleaseM3S"], 3.9)
            latest = json.loads((root / "latest.json").read_text())
            self.assertEqual(latest["runId"], document["runId"])
            second = collector.collect_once(root, now_jst=now, fetcher=fetcher)
            self.assertEqual(second["status"], "ALREADY_CAPTURED_NO_OVERWRITE")
            self.assertEqual(len(fetcher.calls), 6)

    def test_04_partial_capture_is_retained_without_false_complete_claim(self) -> None:
        now = datetime(2026, 9, 12, 23, 28, tzinfo=TOKYO)
        fetcher = FakeFetcher()
        del fetcher.bodies[collector.CAMERA_URL]
        with tempfile.TemporaryDirectory() as temporary:
            result = collector.collect_once(Path(temporary), now_jst=now, fetcher=fetcher)
            self.assertEqual(result["status"], "PARTIAL_CAPTURE_NO_GATE_INFERENCE")
            document = json.loads((Path(result["runPath"]) / "observation.json").read_text())
            self.assertEqual(document["sources"]["barrageCamera"]["status"], "ERROR")
            self.assertFalse(document["summary"]["gateStateInferred"])


if __name__ == "__main__":
    unittest.main()
