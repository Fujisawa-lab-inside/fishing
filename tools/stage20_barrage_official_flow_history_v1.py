#!/usr/bin/env python3
"""Parse the official Onga barrage 12-hour inflow/release history."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://www.qsr.mlit.go.jp/onga/imode/PastTime.html"
OUTPUT = ROOT / "docs/results/stage20-barrage-physical-validation-readiness-v1/official-12h-flow-history.json"
TOKYO = ZoneInfo("Asia/Tokyo")


class OfficialFlowHistoryError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OfficialFlowHistoryError(f"[stage20-barrage-official-flow-history-v1] {message}")


def plain_text(source: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", source)).replace("\xa0", " ")


def _observed_datetime(month: int, day: int, hour: int, minute: int, now: datetime) -> datetime:
    require(0 <= hour <= 24, "observation hour is outside bounds")
    year = now.year
    if now.month == 1 and month == 12:
        year -= 1
    elif now.month == 12 and month == 1:
        year += 1
    observed = datetime(year, month, day, 0 if hour == 24 else hour, minute, tzinfo=TOKYO)
    return observed + timedelta(days=1) if hour == 24 else observed


def parse_official_flow_history(source: str, *, fetched_at: datetime | None = None) -> dict[str, Any]:
    fetched = (fetched_at or datetime.now(TOKYO)).astimezone(TOKYO)
    text = plain_text(source)
    timestamp = re.search(r"(\d{2})/(\d{2})\s+(\d{2}):(\d{2})\s*の更新情報", text)
    require(timestamp is not None, "update timestamp is missing")
    updated = _observed_datetime(*(int(value) for value in timestamp.groups()), fetched)
    require("■12時間履歴" in text, "12-hour section is missing")
    section = text.split("■12時間履歴", 1)[1].split("先頭へ", 1)[0]
    matches = re.findall(
        r"(?m)^\s*(\d{2})時\s+([+-]?\d+(?:\.\d+)?)\s*[↑↓→]?\s+([+-]?\d+(?:\.\d+)?)",
        section,
    )
    require(len(matches) == 12, "12-hour section must contain exactly 12 hourly rows")
    rows: list[dict[str, Any]] = []
    for hour_text, inflow_text, release_text in matches:
        hour = int(hour_text)
        require(0 <= hour <= 24, "hour is outside bounds")
        timestamp_jst = updated.replace(hour=0 if hour == 24 else hour, minute=0, second=0, microsecond=0)
        if timestamp_jst > updated:
            timestamp_jst -= timedelta(days=1)
        inflow = float(inflow_text)
        release = float(release_text)
        require(-5000.0 <= inflow <= 50000.0, "inflow is outside bounds")
        require(-5000.0 <= release <= 50000.0, "release is outside bounds")
        rows.append(
            {
                "timestampJst": timestamp_jst.isoformat(timespec="minutes"),
                "barrageInflowM3S": inflow,
                "barrageReleaseM3S": release,
            }
        )
    require(len({row["timestampJst"] for row in rows}) == 12, "hourly timestamps are not unique")
    return {
        "schema": "onga-official-barrage-flow-history-v1",
        "status": "OFFICIAL_12H_POINT_FLOW_HISTORY_NOT_GATE_OPERATION_NOT_FLOW_FIELD",
        "source": {
            "agencyJa": "国土交通省 九州地方整備局 遠賀川河川事務所",
            "titleJa": "遠賀川河口堰流量履歴表",
            "url": SOURCE_URL,
        },
        "updatedAt": updated.isoformat(timespec="minutes"),
        "fetchedAt": fetched.isoformat(timespec="seconds"),
        "hourlyRowsNewestFirst": rows,
        "summary": {
            "rowCount": len(rows),
            "distinctInflowM3S": sorted({row["barrageInflowM3S"] for row in rows}),
            "distinctReleaseM3S": sorted({row["barrageReleaseM3S"] for row in rows}),
            "releaseTransitionCount": sum(
                rows[index]["barrageReleaseM3S"] != rows[index + 1]["barrageReleaseM3S"]
                for index in range(len(rows) - 1)
            ),
        },
        "classification": {
            "officialObservation": True,
            "barragePointFlowHistoryOnly": True,
            "gateByGateOpeningObserved": False,
            "upstreamDownstreamLevelHistoryObserved": False,
            "actuatorMotionObserved": False,
            "twoDimensionalFlowField": False,
            "modelPrediction": False,
            "physicalLawIdentified": False,
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
    require(completed.returncode == 0, "official history fetch failed")
    try:
        return completed.stdout.decode("cp932", errors="strict")
    except UnicodeDecodeError as error:
        raise OfficialFlowHistoryError("official history encoding changed") from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--source-file", type=Path)
    args = parser.parse_args()
    require(args.fetch != (args.source_file is not None), "choose exactly one source")
    source = fetch_source() if args.fetch else args.source_file.read_text(encoding="cp932")
    result = parse_official_flow_history(source)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], **result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
