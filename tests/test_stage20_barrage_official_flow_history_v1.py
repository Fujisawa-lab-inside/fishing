from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_official_flow_history_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_official_flow_history_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
HISTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HISTORY)


FIXTURE = """
<html><body>08/29 12:50 の更新情報
<pre>
■12時間履歴
      堰流入量 堰放流量
12時     9.2↑    0.0→
11時     8.5↑    0.0→
10時     4.9↑    0.0→
09時     4.4↑    0.0↓
08時     4.3↓    0.3→
07時     4.4↑    0.3→
06時     4.3↓    0.3→
05時     4.5↑    0.3→
04時     4.4↓    0.3→
03時     4.5↑    0.3→
02時     4.4→    0.3→
01時     4.4↓    0.3→
</pre>先頭へ
</body></html>
"""


class Stage20BarrageOfficialFlowHistoryV1Tests(unittest.TestCase):
    def test_parser_preserves_twelve_hourly_point_rows(self) -> None:
        result = HISTORY.parse_official_flow_history(
            FIXTURE,
            fetched_at=datetime(2026, 8, 29, 12, 59, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        self.assertEqual(result["summary"]["rowCount"], 12)
        self.assertEqual(result["summary"]["distinctReleaseM3S"], [0.0, 0.3])
        self.assertEqual(result["summary"]["releaseTransitionCount"], 1)
        self.assertEqual(result["hourlyRowsNewestFirst"][0]["timestampJst"], "2026-08-29T12:00+09:00")
        self.assertEqual(result["hourlyRowsNewestFirst"][-1]["timestampJst"], "2026-08-29T01:00+09:00")

    def test_history_cannot_be_promoted_to_gate_operation_or_physics(self) -> None:
        result = HISTORY.parse_official_flow_history(
            FIXTURE,
            fetched_at=datetime(2026, 8, 29, 12, 59, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        classification = result["classification"]
        self.assertFalse(classification["gateByGateOpeningObserved"])
        self.assertFalse(classification["upstreamDownstreamLevelHistoryObserved"])
        self.assertFalse(classification["physicalLawIdentified"])

    def test_missing_hour_fails_closed(self) -> None:
        with self.assertRaisesRegex(HISTORY.OfficialFlowHistoryError, "exactly 12"):
            HISTORY.parse_official_flow_history(
                FIXTURE.replace("01時     4.4↓    0.3→\n", ""),
                fetched_at=datetime(2026, 8, 29, 12, 59, tzinfo=ZoneInfo("Asia/Tokyo")),
            )


if __name__ == "__main__":
    unittest.main()
