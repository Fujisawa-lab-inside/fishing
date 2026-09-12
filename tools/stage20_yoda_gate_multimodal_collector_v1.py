#!/usr/bin/env python3
"""Capture synchronized public inputs for later Onga barrage gate inference.

This collector is intentionally observation-only.  It stores raw public source
bytes and a small parsed index; it does not infer A1-A8 state, fit a model, run
the hydraulic solver, or publish data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_barrage_official_flow_history_v1 as flow_history
import stage20_barrage_official_point_observation_v1 as point_observation


SCHEMA = "onga-stage20-yoda-gate-multimodal-capture-v1"
TOKYO = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")
USER_AGENT = (
    "OngaStage20GateMultimodalCollector/1.0 "
    "(+https://github.com/Fujisawa-lab-inside/fishing; public research capture)"
)
CAMERA_URL = "https://www.qsr.mlit.go.jp/onga/cctv/kakou_nomal.jpg"
POINT_URL = point_observation.SOURCE_URL
HISTORY_URL = flow_history.SOURCE_URL
AMEDAS_LATEST_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
AMEDAS_MAP_PREFIX = "https://www.jma.go.jp/bosai/amedas/data/map/"
AMEDAS_STATION_ID = "82056"
AMEDAS_STATION_NAME = "八幡"
TIDE_URL_TEMPLATE = "https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/QF.txt"
ALLOWED_HOSTS = frozenset({"www.qsr.mlit.go.jp", "www.jma.go.jp", "www.data.jma.go.jp"})
DEFAULT_MAX_BYTES = 8 * 1024 * 1024


class CaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class Fetched:
    requested_url: str
    final_url: str
    body: bytes
    status: int
    content_type: str | None
    elapsed_seconds: float


Fetcher = Callable[[str, int], Fetched]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CaptureError(f"[stage20-yoda-gate-multimodal-collector-v1] {message}")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _allowed_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    require(parsed.scheme == "https", f"non-HTTPS source rejected: {url}")
    require((parsed.hostname or "").lower() in ALLOWED_HOSTS, f"source host rejected: {url}")
    return url


class _AllowlistedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _allowed_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(
    _AllowlistedRedirects(),
    urllib.request.HTTPSHandler(context=ssl.create_default_context()),
)


def fetch_url(url: str, max_bytes: int = DEFAULT_MAX_BYTES) -> Fetched:
    _allowed_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/jpeg,text/plain,text/html,application/json,*/*;q=0.5",
            "Accept-Language": "ja,en;q=0.7",
            "Cache-Control": "no-cache",
        },
    )
    started = time.monotonic()
    try:
        with _OPENER.open(request, timeout=25.0) as response:
            body = response.read(max_bytes + 1)
            require(len(body) <= max_bytes, f"source exceeds byte limit: {url}")
            return Fetched(
                requested_url=url,
                final_url=response.geturl(),
                body=body,
                status=int(getattr(response, "status", response.getcode())),
                content_type=response.headers.get("Content-Type"),
                elapsed_seconds=time.monotonic() - started,
            )
    except CaptureError:
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as error:
        raise CaptureError(f"fetch failed for {url}: {type(error).__name__}: {error}") from error


def parse_amedas_latest_time(raw: bytes) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as error:
        raise CaptureError("JMA AMeDAS latest time is invalid") from error
    require(parsed.utcoffset() == timedelta(hours=9), "JMA AMeDAS latest time is not JST")
    require(parsed.second == 0 and parsed.microsecond == 0 and parsed.minute % 10 == 0, "JMA AMeDAS time is not ten-minute aligned")
    return parsed


def amedas_map_url(observed_at: datetime) -> str:
    require(observed_at.utcoffset() == timedelta(hours=9), "AMeDAS map time must be JST")
    return f"{AMEDAS_MAP_PREFIX}{observed_at.strftime('%Y%m%d%H%M00')}.json"


def extract_amedas_rain(raw: bytes, observed_at: datetime) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureError("JMA AMeDAS map is not UTF-8 JSON") from error
    require(isinstance(payload, dict), "JMA AMeDAS map must be an object")
    station = payload.get(AMEDAS_STATION_ID)
    require(isinstance(station, dict), f"AMeDAS station {AMEDAS_STATION_ID} is absent")
    values: dict[str, Any] = {}
    for name in ("precipitation10m", "precipitation1h", "precipitation3h", "precipitation24h"):
        item = station.get(name)
        if item is None:
            values[name] = None
            continue
        require(isinstance(item, list) and len(item) == 2, f"AMeDAS {name} shape changed")
        value, quality = item
        require(isinstance(value, (int, float)) and not isinstance(value, bool), f"AMeDAS {name} value is invalid")
        require(isinstance(quality, int) and not isinstance(quality, bool), f"AMeDAS {name} quality is invalid")
        require(0.0 <= float(value) <= 2000.0, f"AMeDAS {name} is outside screening bounds")
        values[name] = {"valueMm": float(value), "qualityCode": quality}
    require(values["precipitation10m"] is not None, "AMeDAS ten-minute precipitation is missing")
    return {
        "provider": "気象庁",
        "stationId": AMEDAS_STATION_ID,
        "stationNameJa": AMEDAS_STATION_NAME,
        "observedAt": observed_at.isoformat(timespec="minutes"),
        "values": values,
        "classification": "official_point_rainfall_not_basin_average",
    }


def jpeg_dimensions(raw: bytes) -> tuple[int, int]:
    require(len(raw) >= 4 and raw[:2] == b"\xff\xd8", "camera body is not JPEG")
    position = 2
    while position + 4 <= len(raw):
        if raw[position] != 0xFF:
            position += 1
            continue
        while position < len(raw) and raw[position] == 0xFF:
            position += 1
        require(position < len(raw), "truncated JPEG marker")
        marker = raw[position]
        position += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        require(position + 2 <= len(raw), "truncated JPEG segment")
        length = int.from_bytes(raw[position : position + 2], "big")
        require(length >= 2 and position + length <= len(raw), "invalid JPEG segment length")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            require(length >= 7, "invalid JPEG frame segment")
            height = int.from_bytes(raw[position + 3 : position + 5], "big")
            width = int.from_bytes(raw[position + 5 : position + 7], "big")
            require(width > 0 and height > 0, "invalid JPEG dimensions")
            return width, height
        position += length
    raise CaptureError("JPEG dimensions are absent")


def _source_record(fetched: Fetched, relative_path: str) -> dict[str, Any]:
    return {
        "status": "FETCHED",
        "requestedUrl": fetched.requested_url,
        "finalUrl": fetched.final_url,
        "httpStatus": fetched.status,
        "contentType": fetched.content_type,
        "relativePath": relative_path,
        "byteLength": len(fetched.body),
        "sha256": sha256_bytes(fetched.body),
        "elapsedSeconds": round(fetched.elapsed_seconds, 6),
    }


def _safe_fetch(
    sources: dict[str, Any],
    name: str,
    url: str,
    relative_path: str,
    staging: Path,
    fetcher: Fetcher,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Fetched | None:
    try:
        fetched = fetcher(url, max_bytes)
        require(fetched.status == 200, f"HTTP status is not 200 for {name}")
        require(bool(fetched.body), f"empty response for {name}")
        destination = staging / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(fetched.body)
        sources[name] = _source_record(fetched, relative_path)
        return fetched
    except Exception as error:
        sources[name] = {
            "status": "ERROR",
            "requestedUrl": url,
            "errorType": type(error).__name__,
            "message": str(error)[:500],
        }
        return None


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(canonical_bytes(payload))
    os.replace(temporary, path)


def _bucket_start(now_jst: datetime) -> datetime:
    require(now_jst.utcoffset() == timedelta(hours=9), "capture clock must be JST")
    return now_jst.replace(minute=(now_jst.minute // 10) * 10, second=0, microsecond=0)


def collect_once(root: Path, *, now_jst: datetime | None = None, fetcher: Fetcher = fetch_url) -> dict[str, Any]:
    started_jst = (now_jst or datetime.now(TOKYO)).astimezone(TOKYO)
    bucket = _bucket_start(started_jst)
    run_id = bucket.strftime("%Y%m%dT%H%M%z")
    relative_run = Path("runs") / bucket.strftime("%Y") / bucket.strftime("%m") / bucket.strftime("%d") / run_id
    final_run = root / relative_run
    if final_run.exists():
        return {
            "schema": SCHEMA,
            "status": "ALREADY_CAPTURED_NO_OVERWRITE",
            "runId": run_id,
            "runPath": str(final_run),
        }

    staging_parent = root / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = staging_parent / f"{run_id}.{os.getpid()}.{uuid.uuid4().hex}"
    staging.mkdir(mode=0o700)
    sources: dict[str, Any] = {}
    parsed: dict[str, Any] = {}
    try:
        camera = _safe_fetch(sources, "barrageCamera", CAMERA_URL, "raw/barrage-camera.jpg", staging, fetcher, 3 * 1024 * 1024)
        if camera is not None:
            try:
                width, height = jpeg_dimensions(camera.body)
                require((width, height) == (640, 480), "camera dimensions changed from 640x480")
                parsed["barrageCamera"] = {
                    "widthPx": width,
                    "heightPx": height,
                    "classification": "official_camera_image_no_gate_label_no_inference",
                }
            except Exception as error:
                sources["barrageCamera"]["status"] = "INVALID"
                sources["barrageCamera"]["message"] = str(error)[:500]

        point = _safe_fetch(sources, "barragePoint", POINT_URL, "raw/barrage-point.html", staging, fetcher)
        if point is not None:
            try:
                parsed["barragePoint"] = point_observation.parse_official_point_observation(
                    point.body.decode("cp932", errors="strict"), fetched_at=started_jst
                )
            except Exception as error:
                sources["barragePoint"]["status"] = "INVALID"
                sources["barragePoint"]["message"] = str(error)[:500]

        history = _safe_fetch(sources, "barrageHistory", HISTORY_URL, "raw/barrage-history.html", staging, fetcher)
        if history is not None:
            try:
                parsed["barrageHistory"] = flow_history.parse_official_flow_history(
                    history.body.decode("cp932", errors="strict"), fetched_at=started_jst
                )
            except Exception as error:
                sources["barrageHistory"]["status"] = "INVALID"
                sources["barrageHistory"]["message"] = str(error)[:500]

        latest = _safe_fetch(sources, "amedasLatestTime", AMEDAS_LATEST_URL, "raw/amedas-latest-time.txt", staging, fetcher, 4096)
        if latest is not None:
            try:
                amedas_time = parse_amedas_latest_time(latest.body)
                rain_url = amedas_map_url(amedas_time)
                rain = _safe_fetch(sources, "amedasMap", rain_url, "raw/amedas-map.json", staging, fetcher)
                if rain is not None:
                    parsed["rainfall"] = extract_amedas_rain(rain.body, amedas_time)
            except Exception as error:
                sources["amedasLatestTime"]["status"] = "INVALID"
                sources["amedasLatestTime"]["message"] = str(error)[:500]

        tide_url = TIDE_URL_TEMPLATE.format(year=started_jst.year)
        tide = _safe_fetch(sources, "hakataTideReference", tide_url, "raw/jma-hakata-tide-QF.txt", staging, fetcher)
        if tide is not None:
            parsed["hakataTideReference"] = {
                "provider": "気象庁",
                "stationCode": "QF",
                "stationNameJa": "博多",
                "year": started_jst.year,
                "classification": "official_astronomical_tide_reference_not_onga_mouth_observation",
            }

        successful = sum(row.get("status") == "FETCHED" for row in sources.values())
        complete = (
            successful == 6
            and "barrageCamera" in parsed
            and "barragePoint" in parsed
            and "barrageHistory" in parsed
            and "rainfall" in parsed
            and "hakataTideReference" in parsed
        )
        document = {
            "schema": SCHEMA,
            "version": 1,
            "status": "COMPLETE_CAPTURE_NO_GATE_INFERENCE" if complete else "PARTIAL_CAPTURE_NO_GATE_INFERENCE",
            "runId": run_id,
            "bucketStartJst": bucket.isoformat(timespec="minutes"),
            "captureStartedAtJst": started_jst.isoformat(timespec="seconds"),
            "captureStartedAtUtc": started_jst.astimezone(UTC).isoformat(timespec="seconds"),
            "host": os.uname().nodename,
            "sources": sources,
            "parsed": parsed,
            "summary": {
                "sourceCount": len(sources),
                "fetchedSourceCount": successful,
                "errorOrInvalidSourceCount": len(sources) - successful,
                "gateStateInferred": False,
                "modelFitPerformed": False,
                "hydraulicSolverExecuted": False,
                "published": False,
            },
            "limitations": [
                "Camera frames are unlabeled observations; A1-A8 state is not inferred.",
                "Yahata rainfall is one official point observation, not basin-average rainfall.",
                "Hakata tide is an astronomical reference, not observed tide at the Onga mouth.",
                "Barrage point values do not identify per-gate openings or fishway discharge.",
            ],
        }
        observation_path = staging / "observation.json"
        observation_path.write_bytes(canonical_bytes(document))
        document["observationSha256"] = sha256_bytes(observation_path.read_bytes())
        final_run.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final_run)
        latest_document = {
            "schema": "onga-stage20-yoda-gate-multimodal-latest-v1",
            "status": document["status"],
            "runId": run_id,
            "runRelativePath": str(relative_run),
            "observationSha256": document["observationSha256"],
            "updatedAtJst": datetime.now(TOKYO).isoformat(timespec="seconds"),
        }
        _atomic_json(root / "latest.json", latest_document)
        return {
            "schema": SCHEMA,
            "status": document["status"],
            "runId": run_id,
            "runPath": str(final_run),
            "fetchedSourceCount": successful,
            "sourceCount": len(sources),
            "observationSha256": document["observationSha256"],
        }
    except Exception:
        failed_parent = root / "failed"
        failed_parent.mkdir(parents=True, exist_ok=True)
        failed = failed_parent / f"{run_id}.{os.getpid()}.{uuid.uuid4().hex}"
        if staging.exists():
            os.replace(staging, failed)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True, help="YODA-local observation root")
    parser.add_argument("--once", action="store_true", help="perform exactly one capture")
    args = parser.parse_args()
    require(args.once, "only explicit --once mode is supported")
    result = collect_once(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
