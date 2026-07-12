#!/usr/bin/env python3
"""Probe public river.go.jp metadata and water-level API responses.

The endpoint paths are derived from the official public site's downloaded
JavaScript bundle.  This diagnostic does not approve observations，does not map
stations to numerical boundaries，and does not write values into the solver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = (
    "OngaStage17PublicRiverApiProbe/1.0 "
    "(+https://github.com/Fujisawa-lab-inside/fishing; public metadata audit)"
)
MAX_BYTES = 8 * 1024 * 1024

STATIC_TARGETS = [
    {
        "id": "river_setting",
        "url": "https://www.river.go.jp/kawabou/setting.json",
    },
    {
        "id": "river_mini_setting",
        "url": "https://www.river.go.jp/kawabou/miniSetting.json",
    },
    {
        "id": "river_current_time",
        "url": "https://www.river.go.jp/kawabou/file/system/tmCrntTime.json",
    },
    {
        "id": "river_edit_common",
        "url": "https://www.river.go.jp/kawabou/file/master/system/editCommon.json",
    },
]

STATIONS = [
    {
        "id": "gion_bridge",
        "expectedName": "祇園橋",
        "river": "西川",
        "ofcCd": "22806",
        "itmkndCd": "4",
        "obsCdCandidates": ["20", "00020"],
    },
    {
        "id": "karakuma",
        "expectedName": "唐熊",
        "river": "遠賀川",
        "ofcCd": "22806",
        "itmkndCd": "4",
        "obsCdCandidates": ["5", "00005"],
    },
    {
        "id": "nakama",
        "expectedName": "中間",
        "river": "遠賀川",
        "ofcCd": "22806",
        "itmkndCd": "4",
        "obsCdCandidates": ["6", "00006"],
    },
]


def fetch(url: str, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "ja,en;q=0.7",
            "Referer": "https://www.river.go.jp/kawabou/pc/tm",
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            body = response.read(MAX_BYTES + 1)[:MAX_BYTES]
            return {
                "requestedUrl": url,
                "finalUrl": response.geturl(),
                "status": int(getattr(response, "status", response.getcode())),
                "headers": {key.lower(): value for key, value in response.headers.items()},
                "body": body,
                "elapsedSeconds": round(time.perf_counter() - started, 6),
                "error": None,
            }
    except Exception as error:
        body = b""
        status = error.code if isinstance(error, urllib.error.HTTPError) else None
        headers: dict[str, str] = {}
        if isinstance(error, urllib.error.HTTPError):
            headers = {key.lower(): value for key, value in error.headers.items()}
            try:
                body = error.read(MAX_BYTES)
            except Exception:
                body = b""
        return {
            "requestedUrl": url,
            "finalUrl": getattr(error, "url", None),
            "status": int(status) if status is not None else None,
            "headers": headers,
            "body": body,
            "elapsedSeconds": round(time.perf_counter() - started, 6),
            "error": f"{type(error).__name__}: {error}",
        }


def decode(body: bytes, content_type: str | None = None) -> tuple[str, str]:
    encodings: list[str] = []
    if content_type:
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.I)
        if match:
            encodings.append(match.group(1))
    encodings.extend(["utf-8", "cp932", "shift_jis", "euc_jp"])
    for encoding in encodings:
        try:
            return body.decode(encoding), encoding
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace"), "utf-8-replace"


def json_or_none(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def scalar_paths(value: Any, prefix: str = "$") -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            output.extend(scalar_paths(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            output.extend(scalar_paths(child, f"{prefix}[{index}]"))
    elif isinstance(value, (str, int, float, bool)) or value is None:
        output.append({"path": prefix, "value": value})
    return output


def timestamp_candidates(value: Any) -> list[str]:
    patterns = [
        re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?$"),
        re.compile(r"^\d{4}/\d{2}/\d{2}[ T]\d{2}:\d{2}(?::\d{2})?$"),
        re.compile(r"^\d{12,14}$"),
    ]
    candidates: list[str] = []
    for entry in scalar_paths(value):
        text = str(entry["value"]).strip()
        if any(pattern.match(text) for pattern in patterns):
            normalised = text.replace("/", "-").replace("T", " ")
            if re.fullmatch(r"\d{12}", normalised):
                normalised = (
                    f"{normalised[0:4]}-{normalised[4:6]}-{normalised[6:8]} "
                    f"{normalised[8:10]}:{normalised[10:12]}"
                )
            elif re.fullmatch(r"\d{14}", normalised):
                normalised = (
                    f"{normalised[0:4]}-{normalised[4:6]}-{normalised[6:8]} "
                    f"{normalised[8:10]}:{normalised[10:12]}:{normalised[12:14]}"
                )
            if normalised not in candidates:
                candidates.append(normalised)
    return candidates


def response_summary(result: dict[str, Any]) -> dict[str, Any]:
    body: bytes = result["body"]
    text, encoding = decode(body, result["headers"].get("content-type")) if body else ("", None)
    parsed = json_or_none(text) if text else None
    return {
        "requestedUrl": result["requestedUrl"],
        "finalUrl": result["finalUrl"],
        "status": result["status"],
        "contentType": result["headers"].get("content-type"),
        "receivedBytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest() if body else None,
        "encoding": encoding,
        "elapsedSeconds": result["elapsedSeconds"],
        "error": result["error"],
        "jsonParsed": parsed is not None,
        "scalarPaths": scalar_paths(parsed)[:5000] if parsed is not None else [],
        "textPreview": text[:1000] if parsed is None else None,
        "parsed": parsed,
    }


def extract_key_inventory(value: Any) -> list[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(extract_key_inventory(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(extract_key_inventory(child))
    return sorted(keys)


def contains_text(value: Any, text: str) -> bool:
    return text in json.dumps(value, ensure_ascii=False) if value is not None else False


def save_response(directory: Path, name: str, summary: dict[str, Any]) -> None:
    safe_summary = {key: value for key, value in summary.items() if key != "parsed"}
    (directory / f"{name}.json").write_text(
        json.dumps(safe_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if summary["parsed"] is not None:
        (directory / f"{name}.payload.json").write_text(
            json.dumps(summary["parsed"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--output", default="stage17-river-api-probe")
    arguments = argument_parser.parse_args()
    output = Path(arguments.output)
    output.mkdir(parents=True, exist_ok=True)

    static_reports: list[dict[str, Any]] = []
    current_time_payload: Any | None = None
    for target in STATIC_TARGETS:
        summary = response_summary(fetch(target["url"]))
        static_reports.append({"id": target["id"], **{k: v for k, v in summary.items() if k != "parsed"}})
        save_response(output, target["id"], summary)
        if target["id"] == "river_current_time":
            current_time_payload = summary["parsed"]

    times = timestamp_candidates(current_time_payload)
    api_time = times[0] if times else None
    station_reports: list[dict[str, Any]] = []
    for station in STATIONS:
        attempts: list[dict[str, Any]] = []
        if api_time is not None:
            encoded_time = urllib.parse.quote(api_time, safe="")
            date_only = api_time.split(" ", 1)[0]
            encoded_date = urllib.parse.quote(date_only, safe="")
            for obs_cd in station["obsCdCandidates"]:
                urls = [
                    (
                        "current",
                        f"https://www.river.go.jp/api/tmObsStage/"
                        f"{station['ofcCd']}/{station['itmkndCd']}/{obs_cd}/{encoded_time}/true",
                    ),
                    (
                        "past_datetime",
                        f"https://www.river.go.jp/api/tmObsStage/past/"
                        f"{station['ofcCd']}/{station['itmkndCd']}/{obs_cd}/{encoded_time}",
                    ),
                    (
                        "past_date",
                        f"https://www.river.go.jp/api/tmObsStage/past/"
                        f"{station['ofcCd']}/{station['itmkndCd']}/{obs_cd}/{encoded_date}",
                    ),
                ]
                for mode, url in urls:
                    summary = response_summary(fetch(url))
                    keys = extract_key_inventory(summary["parsed"])
                    name = f"station_{station['id']}_{obs_cd}_{mode}"
                    save_response(output, name, summary)
                    attempts.append({
                        "mode": mode,
                        "obsCd": obs_cd,
                        "status": summary["status"],
                        "contentType": summary["contentType"],
                        "receivedBytes": summary["receivedBytes"],
                        "sha256": summary["sha256"],
                        "jsonParsed": summary["jsonParsed"],
                        "expectedNameFound": contains_text(summary["parsed"], station["expectedName"]),
                        "riverNameFound": contains_text(summary["parsed"], station["river"]),
                        "keyInventory": keys,
                        "error": summary["error"],
                        "savedAs": name,
                    })
        station_reports.append({
            "id": station["id"],
            "expectedName": station["expectedName"],
            "river": station["river"],
            "ofcCd": station["ofcCd"],
            "itmkndCd": station["itmkndCd"],
            "obsCdCandidates": station["obsCdCandidates"],
            "apiTime": api_time,
            "attempts": attempts,
            "successfulJsonAttempts": sum(
                1 for attempt in attempts
                if attempt["status"] == 200 and attempt["jsonParsed"]
            ),
            "identifiedAttempts": sum(
                1 for attempt in attempts
                if attempt["expectedNameFound"] and attempt["riverNameFound"]
            ),
        })

    required_static = {"river_current_time"}
    failed_required_static = [
        report["id"] for report in static_reports
        if report["id"] in required_static and report["status"] != 200
    ]
    identified_station_count = sum(
        1 for station in station_reports if station["identifiedAttempts"] > 0
    )
    report = {
        "schema": "onga-stage17-public-river-api-probe-v1",
        "status": "passed" if not failed_required_static and api_time is not None else "partial",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apiBasis": {
            "origin": "https://www.river.go.jp",
            "basePath": "/api",
            "currentStageTemplate": "/tmObsStage/{ofcCd}/{itmkndCd}/{obsCd}/{appTime}/{isCurrent}",
            "pastStageTemplate": "/tmObsStage/past/{ofcCd}/{itmkndCd}/{obsCd}/{date}",
            "derivedFrom": "official public app JavaScript bundle",
        },
        "currentTimeCandidates": times,
        "selectedProbeTime": api_time,
        "staticResources": static_reports,
        "stations": station_reports,
        "diagnostics": {
            "failedRequiredStaticResources": failed_required_static,
            "identifiedStationCount": identified_station_count,
            "stationCount": len(STATIONS),
        },
        "interpretationLimits": [
            "A successful API response does not prove availability of an approved historical archive or discharge rating curve.",
            "Current water-level payloads are diagnostics only and are not physical model inputs.",
            "No station is assigned to M，N，O，or G by this probe.",
            "Vertical datum，quality flags，period coverage，and hydraulic compatibility require separate review.",
        ],
        "safeguards": {
            "approvedWaterGeometryChanged": False,
            "physicalValuesAssigned": False,
            "sourceCandidateApproved": False,
            "externalContactPerformed": False,
            "publicSimulatorConnected": False,
            "calibrationPerformed": False,
        },
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "selectedProbeTime": api_time,
        "identifiedStationCount": identified_station_count,
        "stationCount": len(STATIONS),
        "output": str(output / "report.json"),
    }, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
