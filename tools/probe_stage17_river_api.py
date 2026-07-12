#!/usr/bin/env python3
"""Audit public official river.go.jp station metadata and water-level resources.

The route templates are derived from the JavaScript bundle served by the official
public application.  The probe preserves responses and metadata but does not map
stations to M，N，O，or G and does not assign any value to the physical solver.
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
    "OngaStage17PublicRiverResourceAudit/1.1 "
    "(+https://github.com/Fujisawa-lab-inside/fishing; public metadata audit)"
)
MAX_BYTES = 8 * 1024 * 1024
ORIGIN = "https://www.river.go.jp"
FILE_BASE = f"{ORIGIN}/kawabou/file/files"

STATIC_TARGETS = [
    {"id": "river_setting", "url": f"{ORIGIN}/kawabou/setting.json"},
    {"id": "river_mini_setting", "url": f"{ORIGIN}/kawabou/miniSetting.json"},
    {"id": "river_current_time", "url": f"{ORIGIN}/kawabou/file/system/tmCrntTime.json"},
    {"id": "river_edit_common", "url": f"{FILE_BASE}/master/system/editCommon.json"},
]

STATIONS = [
    {
        "id": "gion_bridge",
        "expectedName": "祇園橋",
        "river": "西川",
        "addressFragment": "船頭",
        "ofcCd": "22806",
        "itmkndCdCandidates": ["004", "4"],
        "obsCdCandidates": ["00020", "20"],
        "obsFcd": "2280600400020",
    },
    {
        "id": "karakuma",
        "expectedName": "唐熊",
        "river": "遠賀川",
        "addressFragment": "唐熊",
        "ofcCd": "22806",
        "itmkndCdCandidates": ["004", "4"],
        "obsCdCandidates": ["00005", "5"],
        "obsFcd": "2280600400005",
    },
    {
        "id": "nakama",
        "expectedName": "中間",
        "river": "遠賀川",
        "addressFragment": "中間",
        "ofcCd": "22806",
        "itmkndCdCandidates": ["004", "4"],
        "obsCdCandidates": ["00006", "6"],
        "obsFcd": "2280600400006",
    },
]


def fetch(url: str， timeout: float = 30.0) -> dict[str， Any]:
    request = urllib.request.Request(
        url，
        headers={
            "User-Agent": USER_AGENT，
            "Accept": "application/json，text/plain，*/*"，
            "Accept-Language": "ja，en;q=0.7"，
            "Referer": f"{ORIGIN}/kawabou/pc/tm"，
        }，
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request， timeout=timeout， context=ssl.create_default_context()) as response:
            body = response.read(MAX_BYTES + 1)[:MAX_BYTES]
            return {
                "requestedUrl": url，
                "finalUrl": response.geturl()，
                "status": int(getattr(response， "status"， response.getcode()))，
                "headers": {key.lower(): value for key， value in response.headers.items()}，
                "body": body，
                "elapsedSeconds": round(time.perf_counter() - started， 6)，
                "error": None，
            }
    except Exception as error:
        body = b""
        status = error.code if isinstance(error， urllib.error.HTTPError) else None
        headers: dict[str， str] = {}
        if isinstance(error， urllib.error.HTTPError):
            headers = {key.lower(): value for key， value in error.headers.items()}
            try:
                body = error.read(MAX_BYTES)
            except Exception:
                body = b""
        return {
            "requestedUrl": url，
            "finalUrl": getattr(error， "url"， None)，
            "status": int(status) if status is not None else None，
            "headers": headers，
            "body": body，
            "elapsedSeconds": round(time.perf_counter() - started， 6)，
            "error": f"{type(error).__name__}: {error}"，
        }


def decode(body: bytes， content_type: str | None = None) -> tuple[str， str]:
    encodings: list[str] = []
    if content_type:
        match = re.search(r"charset=([A-Za-z0-9._-]+)"， content_type， re.I)
        if match:
            encodings.append(match.group(1))
    encodings.extend(["utf-8"， "cp932"， "shift_jis"， "euc_jp"])
    for encoding in encodings:
        try:
            return body.decode(encoding)， encoding
        except (LookupError， UnicodeDecodeError):
            continue
    return body.decode("utf-8"， errors="replace")， "utf-8-replace"


def parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def scalar_paths(value: Any， prefix: str = "$") -> list[dict[str， Any]]:
    output: list[dict[str， Any]] = []
    if isinstance(value， dict):
        for key， child in value.items():
            output.extend(scalar_paths(child， f"{prefix}.{key}"))
    elif isinstance(value， list):
        for index， child in enumerate(value):
            output.extend(scalar_paths(child， f"{prefix}[{index}]"))
    elif isinstance(value， (str， int， float， bool)) or value is None:
        output.append({"path": prefix， "value": value})
    return output


def timestamp_candidates(value: Any) -> list[str]:
    patterns = [
        re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?$")，
        re.compile(r"^\d{4}/\d{2}/\d{2}[ T]\d{2}:\d{2}(?::\d{2})?$")，
        re.compile(r"^\d{12，14}$")，
    ]
    candidates: list[str] = []
    for entry in scalar_paths(value):
        text = str(entry["value"]).strip()
        if not any(pattern.match(text) for pattern in patterns):
            continue
        normalised = text.replace("/"， "-").replace("T"， " ")
        if re.fullmatch(r"\d{12}"， normalised):
            normalised = (
                f"{normalised[0:4]}-{normalised[4:6]}-{normalised[6:8]} "
                f"{normalised[8:10]}:{normalised[10:12]}"
            )
        elif re.fullmatch(r"\d{14}"， normalised):
            normalised = (
                f"{normalised[0:4]}-{normalised[4:6]}-{normalised[6:8]} "
                f"{normalised[8:10]}:{normalised[10:12]}:{normalised[12:14]}"
            )
        if normalised not in candidates:
            candidates.append(normalised)
    return candidates


def response_summary(result: dict[str， Any]) -> dict[str， Any]:
    body: bytes = result["body"]
    text， encoding = decode(body， result["headers"].get("content-type")) if body else (""， None)
    parsed = parse_json(text) if text else None
    return {
        "requestedUrl": result["requestedUrl"]，
        "finalUrl": result["finalUrl"]，
        "status": result["status"]，
        "contentType": result["headers"].get("content-type")，
        "receivedBytes": len(body)，
        "sha256": hashlib.sha256(body).hexdigest() if body else None，
        "encoding": encoding，
        "elapsedSeconds": result["elapsedSeconds"]，
        "error": result["error"]，
        "jsonParsed": parsed is not None，
        "scalarPaths": scalar_paths(parsed)[:10000] if parsed is not None else []，
        "textPreview": text[:1000] if parsed is None else None，
        "parsed": parsed，
    }


def key_inventory(value: Any) -> list[str]:
    keys: set[str] = set()
    if isinstance(value， dict):
        for key， child in value.items():
            keys.add(str(key))
            keys.update(key_inventory(child))
    elif isinstance(value， list):
        for child in value:
            keys.update(key_inventory(child))
    return sorted(keys)


def contains_text(value: Any， text: str) -> bool:
    return text in json.dumps(value， ensure_ascii=False) if value is not None else False


def save_response(directory: Path， name: str， summary: dict[str， Any]) -> None:
    serialisable = {key: value for key， value in summary.items() if key != "parsed"}
    (directory / f"{name}.json").write_text(
        json.dumps(serialisable， ensure_ascii=False， indent=2) + "\n"，
        encoding="utf-8"，
    )
    if summary["parsed"] is not None:
        (directory / f"{name}.payload.json").write_text(
            json.dumps(summary["parsed"]， ensure_ascii=False， indent=2) + "\n"，
            encoding="utf-8"，
        )


def compact_attempt(mode: str， identifiers: dict[str， str]， summary: dict[str， Any]， station: dict[str， Any]) -> dict[str， Any]:
    return {
        "mode": mode，
        **identifiers，
        "status": summary["status"]，
        "contentType": summary["contentType"]，
        "receivedBytes": summary["receivedBytes"]，
        "sha256": summary["sha256"]，
        "jsonParsed": summary["jsonParsed"]，
        "expectedNameFound": contains_text(summary["parsed"]， station["expectedName"])，
        "riverNameFound": contains_text(summary["parsed"]， station["river"])，
        "addressFragmentFound": contains_text(summary["parsed"]， station["addressFragment"])，
        "keyInventory": key_inventory(summary["parsed"])，
        "error": summary["error"]，
    }


def main() -> None:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--output"， default="stage17-river-api-probe")
    arguments = argument_parser.parse_args()
    output = Path(arguments.output)
    output.mkdir(parents=True， exist_ok=True)

    static_reports: list[dict[str， Any]] = []
    current_time_payload: Any | None = None
    for target in STATIC_TARGETS:
        summary = response_summary(fetch(target["url"]))
        static_reports.append({"id": target["id"]， **{k: v for k， v in summary.items() if k != "parsed"}})
        save_response(output， target["id"]， summary)
        if target["id"] == "river_current_time":
            current_time_payload = summary["parsed"]

    times = timestamp_candidates(current_time_payload)
    app_time = times[0] if times else None
    date_path = app_time[:10].replace("-"， "") if app_time else None
    minute_path = app_time[11:16].replace(":"， "") if app_time else None

    station_reports: list[dict[str， Any]] = []
    for station in STATIONS:
        attempts: list[dict[str， Any]] = []

        resource_urls: list[tuple[str， str， dict[str， str]]] = [
            (
                "static_master"，
                f"{FILE_BASE}/master/obs/stg/{station['obsFcd']}.json"，
                {"obsFcd": station["obsFcd"]}，
            )，
        ]
        if date_path and minute_path:
            resource_urls.extend([
                (
                    "static_current_time_series"，
                    f"{FILE_BASE}/tmlist/stg/{date_path}/{minute_path}/{station['obsFcd']}.json"，
                    {"obsFcd": station["obsFcd"]}，
                )，
                (
                    "static_past_day_series"，
                    f"{FILE_BASE}/tmlist/past/stg/{date_path}/{station['obsFcd']}.json"，
                    {"obsFcd": station["obsFcd"]}，
                )，
            ])

        for mode， url， identifiers in resource_urls:
            summary = response_summary(fetch(url))
            name = f"station_{station['id']}_{mode}"
            save_response(output， name， summary)
            attempt = compact_attempt(mode， identifiers， summary， station)
            attempt["savedAs"] = name
            attempts.append(attempt)

        if app_time is not None:
            encoded_time = urllib.parse.quote(app_time， safe="")
            encoded_date = urllib.parse.quote(app_time.split(" "， 1)[0]， safe="")
            for itmknd_cd in station["itmkndCdCandidates"]:
                for obs_cd in station["obsCdCandidates"]:
                    api_urls = [
                        (
                            "api_current"，
                            f"{ORIGIN}/api/tmObsStage/{station['ofcCd']}/{itmknd_cd}/{obs_cd}/{encoded_time}/true"，
                        )，
                        (
                            "api_past_datetime"，
                            f"{ORIGIN}/api/tmObsStage/past/{station['ofcCd']}/{itmknd_cd}/{obs_cd}/{encoded_time}"，
                        )，
                        (
                            "api_past_date"，
                            f"{ORIGIN}/api/tmObsStage/past/{station['ofcCd']}/{itmknd_cd}/{obs_cd}/{encoded_date}"，
                        )，
                    ]
                    for mode， url in api_urls:
                        summary = response_summary(fetch(url))
                        name = f"station_{station['id']}_{itmknd_cd}_{obs_cd}_{mode}"
                        save_response(output， name， summary)
                        attempt = compact_attempt(
                            mode，
                            {"ofcCd": station["ofcCd"]， "itmkndCd": itmknd_cd， "obsCd": obs_cd}，
                            summary，
                            station，
                        )
                        attempt["savedAs"] = name
                        attempts.append(attempt)

        master_attempt = next(item for item in attempts if item["mode"] == "static_master")
        static_series_attempts = [item for item in attempts if item["mode"].startswith("static_")]
        api_attempts = [item for item in attempts if item["mode"].startswith("api_")]
        station_reports.append({
            "id": station["id"]，
            "expectedName": station["expectedName"]，
            "river": station["river"]，
            "addressFragment": station["addressFragment"]，
            "ofcCd": station["ofcCd"]，
            "itmkndCdCandidates": station["itmkndCdCandidates"]，
            "obsCdCandidates": station["obsCdCandidates"]，
            "obsFcd": station["obsFcd"]，
            "appTime": app_time，
            "attempts": attempts，
            "masterMetadataAvailable": master_attempt["status"] == 200 and master_attempt["jsonParsed"]，
            "masterIdentityMatched": master_attempt["expectedNameFound"] and master_attempt["riverNameFound"]，
            "staticSeriesSuccessCount": sum(
                1 for item in static_series_attempts if item["status"] == 200 and item["jsonParsed"]
            )，
            "apiSuccessCount": sum(
                1 for item in api_attempts if item["status"] == 200 and item["jsonParsed"]
            )，
        })

    required_static = {"river_current_time"}
    failed_required_static = [
        item["id"] for item in static_reports
        if item["id"] in required_static and item["status"] != 200
    ]
    missing_master_metadata = [
        station["id"] for station in station_reports if not station["masterMetadataAvailable"]
    ]
    master_identity_mismatches = [
        station["id"] for station in station_reports if not station["masterIdentityMatched"]
    ]
    static_series_station_count = sum(
        1 for station in station_reports if station["staticSeriesSuccessCount"] > 0
    )
    api_station_count = sum(1 for station in station_reports if station["apiSuccessCount"] > 0)

    passed = (
        not failed_required_static
        and app_time is not None
        and not missing_master_metadata
        and not master_identity_mismatches
    )
    report = {
        "schema": "onga-stage17-public-river-resource-audit-v1"，
        "status": "passed" if passed else "partial"，
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"， time.gmtime())，
        "routeBasis": {
            "origin": ORIGIN，
            "jsonFileBase": "/kawabou/file/files"，
            "masterStageTemplate": "/master/obs/stg/{obsFcd}.json"，
            "currentStageFileTemplate": "/tmlist/stg/{YYYYMMDD}/{HHmm}/{obsFcd}.json"，
            "pastStageFileTemplate": "/tmlist/past/stg/{YYYYMMDD}/{obsFcd}.json"，
            "apiBase": "/api"，
            "apiCurrentTemplate": "/tmObsStage/{ofcCd}/{itmkndCd}/{obsCd}/{appTime}/{isCurrent}"，
            "apiPastTemplate": "/tmObsStage/past/{ofcCd}/{itmkndCd}/{obsCd}/{date}"，
            "derivedFrom": "official public application JavaScript bundle"，
        }，
        "currentTimeCandidates": times，
        "selectedProbeTime": app_time，
        "staticResources": static_reports，
        "stations": station_reports，
        "diagnostics": {
            "failedRequiredStaticResources": failed_required_static，
            "missingMasterMetadata": missing_master_metadata，
            "masterIdentityMismatches": master_identity_mismatches，
            "staticSeriesStationCount": static_series_station_count，
            "apiStationCount": api_station_count，
            "stationCount": len(STATIONS)，
        }，
        "interpretationLimits": [
            "Master metadata identifies an official station but does not establish hydraulic compatibility with a model boundary."，
            "A current or past public series is diagnostic only until period coverage，quality flags，vertical datum，and licence conditions are reviewed."，
            "Water-level availability does not imply discharge or an approved rating curve."，
            "No station is assigned to M，N，O，or G by this audit."，
        ]，
        "safeguards": {
            "approvedWaterGeometryChanged": False，
            "physicalValuesAssigned": False，
            "sourceCandidateApproved": False，
            "externalContactPerformed": False，
            "publicSimulatorConnected": False，
            "calibrationPerformed": False，
        }，
    }
    (output / "report.json").write_text(
        json.dumps(report， ensure_ascii=False， indent=2) + "\n"，
        encoding="utf-8"，
    )
    print(json.dumps({
        "status": report["status"]，
        "selectedProbeTime": app_time，
        "missingMasterMetadata": missing_master_metadata，
        "masterIdentityMismatches": master_identity_mismatches，
        "staticSeriesStationCount": static_series_station_count，
        "apiStationCount": api_station_count，
        "output": str(output / "report.json")，
    }， ensure_ascii=False， indent=2))
    if report["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
