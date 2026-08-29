from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_official_point_observation_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_official_point_observation_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
POINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POINT)


FIXTURE = """
<html><body>08/29 12:50 の更新情報
河口堰流入量 <font>9.6</font>m3/s
河口堰放流量 <font>0.0</font>m3/s
河口堰上水位 <font>1.46</font>m
河口堰下水位 <font>0.93</font>m
</body></html>
"""


class Stage20BarrageOfficialPointObservationV1Tests(unittest.TestCase):
    def test_parser_preserves_point_values_without_gate_inference(self) -> None:
        result = POINT.parse_official_point_observation(
            FIXTURE,
            fetched_at=datetime(2026, 8, 29, 12, 59, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        self.assertEqual(result["observedAt"], "2026-08-29T12:50+09:00")
        self.assertEqual(result["values"]["barrageInflowM3S"], 9.6)
        self.assertEqual(result["values"]["barrageReleaseM3S"], 0.0)
        self.assertFalse(result["classification"]["gateByGateOpeningObserved"])
        self.assertFalse(result["classification"]["twoDimensionalFlowField"])
        self.assertFalse(result["classification"]["modelPrediction"])

    def test_missing_level_fails_closed(self) -> None:
        with self.assertRaisesRegex(POINT.OfficialPointObservationError, "barrageDownstreamLevelM"):
            POINT.parse_official_point_observation(
                FIXTURE.replace("河口堰下水位 <font>0.93</font>m\n", ""),
                fetched_at=datetime(2026, 8, 29, 12, 59, tzinfo=ZoneInfo("Asia/Tokyo")),
            )


if __name__ == "__main__":
    unittest.main()
