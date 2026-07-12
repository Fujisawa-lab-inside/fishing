#!/usr/bin/env python3
"""Audit official water-level stations against the frozen Stage 16 domain.

The audit uses official public station metadata and public water-level resources.
It computes geodetic and image-space relationships to the approved domain but
never assigns a station to a boundary and never writes observations to the solver.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import ssl
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

CIRCUMFERENCE_M = 40075016.68557849
EARTH_RADIUS_M = 6371008.8
ORIGIN = "https://www.river.go.jp"
FILE_BASE = f"{ORIGIN}/kawabou/file/files"
USER_AGENT = (
    "OngaStage17StationBoundaryAudit/1.0 "
    "(+https://github.com/Fujisawa-lab-inside/fishing; public metadata audit)"
)

STATIONS = [
    {
        "id": "gion_bridge",
        "obsFcd": "2280600400020",
        "expectedName": "祇園橋",
        "expectedRiver": "西川",
    },
    {
        "id": "karakuma",
        "obsFcd": "2280600400005",
        "expectedName": "唐熊",
        "expectedRiver": "遠賀川",
    },
    {
        "id": "nakama",
        "obsFcd": "2280600400006",
        "expectedName": "中間",
        "expectedRiver": "遠賀川",
    },
]


def fetch_json(url: str, timeout: float = 30.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,*/*",
            "Referer": f"{ORIGIN}/kawabou/pc/tm",
        },
    )
    with urllib.request.urlopen(
        request,
        timeout=timeout,
        context=ssl.create_default_context(),
    ) as response:
        body = response.read()
    for encoding in ("utf-8", "cp932", "shift_jis"):
        try:
            return json.loads(body.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise RuntimeError(f"cannot decode JSON resource {url}")


def parse_time(value: str) -> datetime:
    for pattern in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    raise ValueError(f"unsupported time {value}")


def scalar_items(value: Any, prefix: str = "$") -> list[tuple[str, Any]]:
    output: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            output.extend(scalar_items(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            output.extend(scalar_items(child, f"{prefix}[{index}]"))
    elif isinstance(value, (str, int, float, bool)) or value is None:
        output.append((prefix, value))
    return output


def current_application_time(payload: Any) -> datetime:
    candidates: list[datetime] = []
    for _, value in scalar_items(payload):
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not re.fullmatch(r"(?:\d{4}[-/]\d{2}[-/]\d{2} \d{2}:\d{2}|\d{12})", text):
            continue
        try:
            candidates.append(parse_time(text))
        except ValueError:
            pass
    if not candidates:
        raise RuntimeError("official application current time not found")
    return candidates[0]


def load_water(manifest_path: Path) -> tuple[dict[str, Any], list[list[int]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[list[int] | None] = [None] * int(manifest["height"])
    root = manifest_path.parent.parent
    for relative in manifest["chunks"]:
        chunk_path = root / relative.removeprefix("./")
        chunk = json.loads(chunk_path.read_text(encoding="utf-8"))
        start = int(chunk["startRow"])
        for offset, row in enumerate(chunk["rows"]):
            rows[start + offset] = [int(value) for value in row]
    if any(row is None for row in rows):
        raise RuntimeError("approved water rows are incomplete")
    typed_rows = [row for row in rows if row is not None]
    pixel_count = sum(
        x1 - x0 + 1
        for row in typed_rows
        for x0, x1 in zip(row[0::2], row[1::2])
    )
    if pixel_count != 679791 or pixel_count != int(manifest["pixelCount"]):
        raise RuntimeError(f"approved water pixel count mismatch {pixel_count}")
    return manifest, typed_rows


def row_contains(row: list[int], x: int) -> bool:
    return any(x0 <= x <= x1 for x0, x1 in zip(row[0::2], row[1::2]))


def water_contains(rows: list[list[int]], width: int, height: int, x: float, y: float) -> bool:
    ix = int(round(x))
    iy = int(round(y))
    return 0 <= ix < width and 0 <= iy < height and row_contains(rows[iy], ix)


def barycentric(point: list[float], a: list[float], b: list[float], c: list[float]) -> list[float]:
    denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(denominator) < 1e-15:
        raise RuntimeError("degenerate georeference triangle")
    u = ((b[1] - c[1]) * (point[0] - c[0]) + (c[0] - b[0]) * (point[1] - c[1])) / denominator
    v = ((c[1] - a[1]) * (point[0] - c[0]) + (a[0] - c[0]) * (point[1] - c[1])) / denominator
    return [u, v, 1.0 - u - v]


def piecewise_map(
    point: list[float],
    mesh: dict[str, Any],
    source_key: str,
    target_key: str,
) -> list[float]:
    anchors = mesh["anchors"]
    for triangle in mesh["triangles"]:
        source = [anchors[index][source_key] for index in triangle]
        weights = barycentric(point, source[0], source[1], source[2])
        if min(weights) >= -1e-7 and max(weights) <= 1.0 + 1e-7:
            target = [anchors[index][target_key] for index in triangle]
            return [
                sum(weights[index] * float(target[index][axis]) for index in range(3))
                for axis in range(2)
            ]
    return [float(point[0]), float(point[1])]


def latlon_to_image(lat: float, lon: float, geographic: dict[str, Any]) -> list[float]:
    latitude = max(-85.05112878, min(85.05112878, float(lat)))
    sine = math.sin(math.radians(latitude))
    world_x = (float(lon) + 180.0) / 360.0 * CIRCUMFERENCE_M
    world_y = (
        0.5 - math.log((1.0 + sine) / (1.0 - sine)) / (4.0 * math.pi)
    ) * CIRCUMFERENCE_M
    transform = geographic["transform"]
    a = float(transform["a"])
    b = float(transform["b"])
    tx = float(transform["tx"])
    ty = float(transform["ty"])
    determinant = a * a + b * b
    dx = world_x - tx
    dy = world_y - ty
    source_pixel = [
        (a * dx + b * dy) / determinant,
        (-b * dx + a * dy) / determinant,
    ]
    return piecewise_map(
        source_pixel,
        geographic["controlMesh"],
        "sourceBasePixel",
        "targetImagePixel",
    )


def image_to_latlon(x: float, y: float, geographic: dict[str, Any]) -> list[float]:
    source_pixel = piecewise_map(
        [float(x), float(y)],
        geographic["controlMesh"],
        "targetImagePixel",
        "sourceBasePixel",
    )
    transform = geographic["transform"]
    a = float(transform["a"])
    b = float(transform["b"])
    world_x = float(transform["tx"]) + a * source_pixel[0] - b * source_pixel[1]
    world_y = float(transform["ty"]) + b * source_pixel[0] + a * source_pixel[1]
    lon = world_x / CIRCUMFERENCE_M * 360.0 - 180.0
    lat = math.degrees(
        math.atan(math.sinh(math.pi * (1.0 - 2.0 * world_y / CIRCUMFERENCE_M)))
    )
    return [lat, lon]


def haversine_m(left: list[float], right: list[float]) -> float:
    lat1, lon1 = map(math.radians, left)
    lat2, lon2 = map(math.radians, right)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(value))


def flatten_keys(value: Any) -> set[str]:
    output: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            output.add(str(key))
            output.update(flatten_keys(child))
    elif isinstance(value, list):
        for child in value:
            output.update(flatten_keys(child))
    return output


def series_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("min10Values", "hrValues", "pastValues"):
        values = payload.get(key)
        if isinstance(values, list):
            entries.extend(item for item in values if isinstance(item, dict))
    return entries


def series_summary(payload: dict[str, Any]) -> dict[str, Any]:
    entries = series_entries(payload)
    times: list[datetime] = []
    for entry in entries:
        value = entry.get("obsTime")
        if isinstance(value, str):
            try:
                times.append(parse_time(value))
            except ValueError:
                pass
    quality_codes = Counter(str(entry.get("stgCcd")) for entry in entries)
    quality_flags = Counter(str(entry.get("stgQmflg")) for entry in entries)
    keys = flatten_keys(payload)
    discharge_keys = sorted(
        key for key in keys
        if re.search(r"(?:dsch|discharge|flow|流量)", key, re.I)
    )
    return {
        "entryCount": len(entries),
        "firstObservation": min(times).isoformat() if times else None,
        "lastObservation": max(times).isoformat() if times else None,
        "stageQualityCodeCounts": dict(sorted(quality_codes.items())),
        "stageQualityFlagCounts": dict(sorted(quality_flags.items())),
        "fieldNames": sorted(keys),
        "dischargeRelatedFields": discharge_keys,
        "containsDischargeField": bool(discharge_keys),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--water-manifest",
        default="data/onga_unified_water_manifest_r2.json",
    )
    parser.add_argument("--output", default="stage17-station-boundary-audit")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    manifest, rows = load_water(Path(args.water_manifest))
    width = int(manifest["width"])
    height = int(manifest["height"])
    geographic = manifest["coordinateSystem"]["geographic"]

    boundary_points: dict[str, dict[str, Any]] = {}
    for boundary in manifest["openBoundaries"]:
        x = 0.5 * (float(boundary["pixelRun"][0]) + float(boundary["pixelRun"][1]))
        y = 0.0 if boundary["edge"] == "top" else float(height - 1)
        boundary_points[boundary["id"]] = {
            "pixel": [x, y],
            "latLon": image_to_latlon(x, y, geographic),
        }

    application_time = current_application_time(
        fetch_json(f"{ORIGIN}/kawabou/file/system/tmCrntTime.json")
    )
    date_path = application_time.strftime("%Y%m%d")
    minute_path = application_time.strftime("%H%M")

    reports: list[dict[str, Any]] = []
    for station in STATIONS:
        master = fetch_json(f"{FILE_BASE}/master/obs/stg/{station['obsFcd']}.json")
        current = fetch_json(
            f"{FILE_BASE}/tmlist/stg/{date_path}/{minute_path}/{station['obsFcd']}.json"
        )
        past = fetch_json(
            f"{FILE_BASE}/tmlist/past/stg/{date_path}/{station['obsFcd']}.json"
        )
        obs = master["obsInfo"]
        cross = master.get("crs", {})
        if obs.get("obsNm") != station["expectedName"] or obs.get("rvrNm") != station["expectedRiver"]:
            raise RuntimeError(f"official station identity mismatch for {station['id']}")
        lat_lon = [float(obs["lat"]), float(obs["lon"])]
        image_pixel = latlon_to_image(lat_lon[0], lat_lon[1], geographic)
        distances = {
            boundary_id: haversine_m(lat_lon, item["latLon"])
            for boundary_id, item in boundary_points.items()
        }
        nearest_boundary = min(distances, key=distances.get)
        current_summary = series_summary(current)
        past_summary = series_summary(past)
        combined_discharge_fields = sorted(set(
            current_summary["dischargeRelatedFields"]
            + past_summary["dischargeRelatedFields"]
        ))
        inside = water_contains(rows, width, height, image_pixel[0], image_pixel[1])
        suggested_role = (
            "internal_water_level_validation_candidate"
            if inside
            else "external_upstream_water_level_candidate"
        )
        reports.append({
            "id": station["id"],
            "officialIdentity": {
                "obsFcd": station["obsFcd"],
                "ofcCd": obs.get("ofcCd"),
                "itmkndCd": obs.get("itmkndCd"),
                "obsCd": obs.get("obsCd"),
                "name": obs.get("obsNm"),
                "riverSystem": obs.get("rsysNm"),
                "river": obs.get("rvrNm"),
                "office": obs.get("jrsNm"),
                "address": obs.get("obsAdr"),
                "subaddress": obs.get("obsSadr"),
                "latitude": lat_lon[0],
                "longitude": lat_lon[1],
                "rawRiverMouthDistance": obs.get("rvrMouthDst"),
            },
            "verticalReferenceMetadata": {
                "altiStdCd": obs.get("altiStdCd"),
                "zeroHigh": obs.get("zeroHigh"),
                "zeroHighFix": obs.get("zeroHighFix"),
                "crossSectionZeroHigh": cross.get("zeroHigh"),
                "crossSectionRiverBed": cross.get("riverBed"),
                "datumMeaningResolved": False,
                "approvedForSolver": False,
            },
            "approvedDomainRelationship": {
                "imagePixel": image_pixel,
                "insideImage": 0 <= image_pixel[0] < width and 0 <= image_pixel[1] < height,
                "insideApprovedWaterAtRoundedPixel": inside,
                "boundaryDistancesM": distances,
                "nearestBoundary": nearest_boundary,
                "nearestBoundaryDistanceM": distances[nearest_boundary],
                "boundaryAssignment": None,
                "suggestedRoleForLaterReview": suggested_role,
            },
            "publicSeries": {
                "applicationTime": application_time.isoformat(),
                "currentResource": current_summary,
                "pastResource": past_summary,
                "combinedDischargeRelatedFields": combined_discharge_fields,
                "containsDischargeField": bool(combined_discharge_fields),
                "approvedForSolver": False,
            },
        })

    report = {
        "schema": "onga-stage17-station-boundary-compatibility-audit-v1",
        "status": "passed",
        "applicationTime": application_time.isoformat(),
        "approvedDomain": {
            "version": manifest["version"],
            "pixelCount": manifest["pixelCount"],
            "width": width,
            "height": height,
            "openBoundaryMidpoints": boundary_points,
        },
        "stations": reports,
        "diagnostics": {
            "stationCount": len(reports),
            "insideApprovedWaterCount": sum(
                1 for item in reports
                if item["approvedDomainRelationship"]["insideApprovedWaterAtRoundedPixel"]
            ),
            "stationWithPublicCurrentSeriesCount": sum(
                1 for item in reports
                if item["publicSeries"]["currentResource"]["entryCount"] > 0
            ),
            "stationWithPublicPastSeriesCount": sum(
                1 for item in reports
                if item["publicSeries"]["pastResource"]["entryCount"] > 0
            ),
            "stationWithDischargeFieldCount": sum(
                1 for item in reports
                if item["publicSeries"]["containsDischargeField"]
            ),
            "unresolvedVerticalDatumCount": sum(
                1 for item in reports
                if not item["verticalReferenceMetadata"]["datumMeaningResolved"]
            ),
        },
        "interpretation": [
            "A station inside the approved domain is a potential internal validation point，not automatically an open-boundary input.",
            "An upstream station outside the domain requires discharge or routing evidence before use at an inflow boundary.",
            "Published stage and local zero-height metadata do not resolve the vertical datum without an authoritative code definition.",
            "Public stage resources do not establish an approved discharge series or rating curve.",
        ],
        "safeguards": {
            "approvedWaterGeometryChanged": False,
            "stationBoundaryAssignmentPerformed": False,
            "physicalValuesAssigned": False,
            "sourceCandidateApproved": False,
            "externalContactPerformed": False,
            "legacyFlowCalculationChanged": False,
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
        "applicationTime": report["applicationTime"],
        "insideApprovedWaterCount": report["diagnostics"]["insideApprovedWaterCount"],
        "stationWithDischargeFieldCount": report["diagnostics"]["stationWithDischargeFieldCount"],
        "unresolvedVerticalDatumCount": report["diagnostics"]["unresolvedVerticalDatumCount"],
        "output": str(output / "report.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
