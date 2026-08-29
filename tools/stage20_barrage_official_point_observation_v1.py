#!/usr/bin/env python3
"""Parse one official Onga barrage point-observation page."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://www.qsr.mlit.go.jp/onga/imode/RealTime.html"
OUTPUT = ROOT / "docs/results/stage20-barrage-physical-validation-readiness-v1/official-point-observation.json"
TOKYO = ZoneInfo("Asia/Tokyo")
PATTERNS = {
    "barrageInflowM3S": (r"河口堰流入量\s*([+-]?\d+(?:\.\d+)?)\s*m3/s", -5000.0, 50000.0),
    "barrageReleaseM3S": (r"河口堰放流量\s*([+-]?\d+(?:\.\d+)?)\s*m3/s", -5000.0, 50000.0),
    "barrageUpstreamLevelM": (r"河口堰上水位\s*([+-]?\d+(?:\.\d+)?)\s*m", -20.0, 100.0),
    "barrageDownstreamLevelM": (r"河口堰下水位\s*([+-]?\d+(?:\.\d+)?)\s*m", -20.0, 100.0),
}


class OfficialPointObservationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OfficialPointObservationError(f"[stage20-barrage-official-point-observation-v1] {message}")


def plain_text(source: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", source)).replace("\xa0", " ")


def parse_official_point_observation(source: str, *, fetched_at: datetime | None = None) -> dict[str, Any]:
    fetched = (fetched_at or datetime.now(TOKYO)).astimezone(TOKYO)
    text = plain_text(source)
    timestamp = re.search(r"(\d{2})/(\d{2})\s+(\d{2}):(\d{2})\s*の更新情報", text)
    require(timestamp is not None, "observation timestamp is missing")
    month, day, hour, minute = (int(value) for value in timestamp.groups())
    year = fetched.year - 1 if fetched.month == 1 and month == 12 else fetched.year
    if fetched.month == 12 and month == 1:
        year += 1
    observed = datetime(year, month, day, hour, minute, tzinfo=TOKYO)
    values: dict[str, float] = {}
    for key, (pattern, minimum, maximum) in PATTERNS.items():
        match = re.search(pattern, text)
        require(match is not None, f"observation value is missing: {key}")
        value = float(match.group(1))
        require(minimum <= value <= maximum, f"observation value is outside bounds: {key}")
        values[key] = value
    return {
        "schema": "onga-current-official-barrage-observation-v1",
        "version": 1,
        "status": "CURRENT_OFFICIAL_POINT_OBSERVATION_NOT_FLOW_FIELD",
        "source": {
            "agencyJa": "国土交通省 九州地方整備局 遠賀川河川事務所",
            "titleJa": "遠賀川河口堰流量現況表",
            "url": SOURCE_URL,
        },
        "observedAt": observed.isoformat(timespec="minutes"),
        "fetchedAt": fetched.isoformat(timespec="seconds"),
        "values": values,
        "classification": {
            "officialObservation": True,
            "barragePointValuesOnly": True,
            "gateByGateOpeningObserved": False,
            "actuatorMotionObserved": False,
            "salinityObserved": False,
            "twoDimensionalFlowField": False,
            "modelPrediction": False,
            "catchPrediction": False,
        },
    }


def fetch_source() -> str:
    completed = subprocess.run(
        ["/usr/bin/curl", "-fsS", "--max-time", "15", SOURCE_URL],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    require(completed.returncode == 0, "official observation fetch failed")
    try:
        return completed.stdout.decode("cp932", errors="strict")
    except UnicodeDecodeError as error:
        raise OfficialPointObservationError("official observation encoding changed") from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--source-file", type=Path)
    args = parser.parse_args()
    require(args.fetch != (args.source_file is not None), "choose exactly one source")
    source = fetch_source() if args.fetch else args.source_file.read_text(encoding="cp932")
    result = parse_official_point_observation(source)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "observedAt": result["observedAt"], "values": result["values"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
