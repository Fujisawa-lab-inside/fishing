#!/usr/bin/env python3
"""Build an isolated 37-hour relative tide-boundary candidate.

This task-B utility does not import, modify, or invoke the solver, mesh, GUI,
precomputation, or public runtime.  It accepts only the JMA Hakata (QF)
astronomical-tide annual fixed-width text as its primary source.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import ssl
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = "onga-stage20-taskB-daily-tide-boundary-request-v1"
OUTPUT_SCHEMA = "onga-stage20-taskB-daily-tide-boundary-result-v1"
DISPLAY_LABEL = "未較正・モデル参考値"
STATION_CODE = "QF"
STATION_NAME = "博多"
WINDOW_HOURS = tuple(range(-12, 25))
JST = timezone(timedelta(hours=9), name="JST")
OFFICIAL_HOST = "www.data.jma.go.jp"
OFFICIAL_URL_TEMPLATE = (
    "https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station}.txt"
)
OFFICIAL_PAGE_URL = "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/"
OFFICIAL_FORMAT_URL = (
    "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/readme.html"
)
PRESERVED_CANDIDATE = (
    ROOT / "config/stage19_m_boundary_tide_candidate_v1.json"
)
PRESERVED_SNAPSHOT = ROOT / "data/jma_hakata_2026_hourly_tide_QF.txt"
MAX_ALLOWED_BYTES = 262_144
SYSTEM_CA_CANDIDATES = (
    Path("/etc/ssl/cert.pem"),
    Path("/etc/ssl/certs/ca-certificates.crt"),
    Path("/etc/pki/tls/certs/ca-bundle.crt"),
)


class TidePipelineError(RuntimeError):
    """Base class for explicit pipeline failures."""


class InputContractError(TidePipelineError):
    """The request does not satisfy the task-B input contract."""


class SourceResolutionError(TidePipelineError):
    """An official or local source cannot safely resolve the requested window."""


class PreservedFallbackError(TidePipelineError):
    """The preserved representative fallback failed its integrity checks."""


@dataclass(frozen=True)
class AnnualSnapshot:
    year: int
    station_code: str
    rows: dict[date, tuple[int, ...]]
    sha256: str
    byte_length: int
    locator: str
    acquisition: str
    acquired_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(raw)


def _verified_ssl_context() -> ssl.SSLContext:
    """Return a verified TLS context without ever disabling certificate checks."""

    defaults = ssl.get_default_verify_paths()
    if defaults.cafile and Path(defaults.cafile).is_file():
        return ssl.create_default_context()
    for candidate in SYSTEM_CA_CANDIDATES:
        if candidate.is_file():
            return ssl.create_default_context(cafile=str(candidate))
    return ssl.create_default_context()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InputContractError(message)


def validate_request(request: dict[str, Any]) -> date:
    _require(isinstance(request, dict), "request must be a JSON object")
    allowed = {
        "schema",
        "requestedDate",
        "station",
        "window",
        "source",
        "failurePolicy",
    }
    _require(set(request) == allowed, f"request keys must be exactly {sorted(allowed)}")
    _require(request["schema"] == INPUT_SCHEMA, "request schema mismatch")

    try:
        requested_date = date.fromisoformat(request["requestedDate"])
    except (TypeError, ValueError) as exc:
        raise InputContractError("requestedDate must be a real ISO date") from exc
    _require(
        date(2001, 1, 1) <= requested_date <= date(2098, 12, 31),
        "requestedDate must be between 2001-01-01 and 2098-12-31",
    )

    station = request["station"]
    _require(
        station == {"code": STATION_CODE, "name": STATION_NAME},
        "station must be exactly Hakata QF",
    )
    _require(
        request["window"]
        == {"startHour": -12, "endHour": 24, "stepHours": 1},
        "window must be exactly -12 through +24 at one-hour intervals",
    )
    _require(
        request["failurePolicy"]
        in {"fail_closed", "fallback_to_preserved_representative"},
        "unsupported failurePolicy",
    )

    source = request["source"]
    _require(isinstance(source, dict), "source must be an object")
    mode = source.get("mode")
    _require(
        mode in {"official_jma_annual_text", "local_snapshot_set"},
        "unsupported source mode",
    )
    if mode == "official_jma_annual_text":
        _require(
            set(source).issubset({"mode", "timeoutSeconds", "maxBytesPerYear"}),
            "official source contains unsupported keys",
        )
        timeout = source.get("timeoutSeconds", 15)
        max_bytes = source.get("maxBytesPerYear", 131_072)
        _require(
            isinstance(timeout, (int, float))
            and not isinstance(timeout, bool)
            and 1 <= timeout <= 30,
            "timeoutSeconds must be between 1 and 30",
        )
        _require(
            isinstance(max_bytes, int)
            and not isinstance(max_bytes, bool)
            and 50_000 <= max_bytes <= MAX_ALLOWED_BYTES,
            f"maxBytesPerYear must be between 50000 and {MAX_ALLOWED_BYTES}",
        )
    else:
        _require(
            set(source) == {"mode", "yearFiles"},
            "local source keys must be exactly mode and yearFiles",
        )
        year_files = source["yearFiles"]
        _require(
            isinstance(year_files, dict),
            "source.yearFiles must be an object keyed by four-digit year",
        )
        for year, path in year_files.items():
            _require(
                len(year) == 4 and year.isdigit(),
                "source.yearFiles keys must be four-digit years",
            )
            _require(
                isinstance(path, str) and bool(path.strip()),
                f"source.yearFiles[{year}] must be a non-empty path",
            )
    return requested_date


def parse_jma_annual_text(
    raw: bytes,
    *,
    expected_year: int,
    expected_station: str = STATION_CODE,
    locator: str,
    acquisition: str,
    acquired_at: str | None = None,
) -> AnnualSnapshot:
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise SourceResolutionError(f"{locator}: JMA text is not strict ASCII") from exc

    lines = text.splitlines()
    expected_days = 366 if calendar.isleap(expected_year) else 365
    if len(lines) != expected_days:
        raise SourceResolutionError(
            f"{locator}: expected {expected_days} daily rows, found {len(lines)}"
        )

    rows: dict[date, tuple[int, ...]] = {}
    for index, line in enumerate(lines, start=1):
        if len(line) != 136:
            raise SourceResolutionError(
                f"{locator}: row {index} has width {len(line)}, expected 136"
            )
        if line[78:80] != expected_station:
            raise SourceResolutionError(
                f"{locator}: row {index} station is not {expected_station}"
            )
        try:
            year_suffix = int(line[72:74])
            month = int(line[74:76])
            day = int(line[76:78])
            row_date = date(expected_year, month, day)
            hourly = tuple(
                int(line[hour * 3 : hour * 3 + 3]) for hour in range(24)
            )
        except ValueError as exc:
            raise SourceResolutionError(
                f"{locator}: row {index} contains an invalid date or hourly value"
            ) from exc
        if year_suffix != expected_year % 100:
            raise SourceResolutionError(
                f"{locator}: row {index} year suffix does not match {expected_year}"
            )
        if any(value == 999 or value < -500 or value > 500 for value in hourly):
            raise SourceResolutionError(
                f"{locator}: row {index} contains an invalid hourly prediction"
            )
        if row_date in rows:
            raise SourceResolutionError(f"{locator}: duplicate row for {row_date}")
        rows[row_date] = hourly

    expected_dates = {
        date(expected_year, 1, 1) + timedelta(days=offset)
        for offset in range(expected_days)
    }
    if set(rows) != expected_dates:
        missing = sorted(expected_dates - set(rows))
        extra = sorted(set(rows) - expected_dates)
        raise SourceResolutionError(
            f"{locator}: incomplete annual date coverage; "
            f"missing={missing[:3]}, extra={extra[:3]}"
        )
    return AnnualSnapshot(
        year=expected_year,
        station_code=expected_station,
        rows=rows,
        sha256=_sha256_bytes(raw),
        byte_length=len(raw),
        locator=locator,
        acquisition=acquisition,
        acquired_at=acquired_at or _utc_now(),
    )


def fetch_official_year(
    year: int,
    station: str,
    timeout_seconds: float,
    max_bytes: int,
) -> AnnualSnapshot:
    url = OFFICIAL_URL_TEMPLATE.format(year=year, station=station)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != OFFICIAL_HOST:
        raise SourceResolutionError("official JMA URL failed the HTTPS allowlist")

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "SeaBass-taskB-tide-boundary/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=_verified_ssl_context(),
        ) as response:
            final_url = response.geturl()
            final = urllib.parse.urlparse(final_url)
            if final.scheme != "https" or final.hostname != OFFICIAL_HOST:
                raise SourceResolutionError(
                    "official JMA request redirected outside the HTTPS allowlist"
                )
            status = getattr(response, "status", None)
            if status != 200:
                raise SourceResolutionError(
                    f"official JMA request returned HTTP {status}"
                )
            length_header = response.headers.get("Content-Length")
            if length_header is not None and int(length_header) > max_bytes:
                raise SourceResolutionError(
                    "official JMA response exceeds maxBytesPerYear"
                )
            raw = response.read(max_bytes + 1)
    except SourceResolutionError:
        raise
    except (OSError, ValueError) as exc:
        raise SourceResolutionError(
            f"official JMA request failed for {year}: {exc}"
        ) from exc
    if len(raw) > max_bytes:
        raise SourceResolutionError("official JMA response exceeds maxBytesPerYear")
    return parse_jma_annual_text(
        raw,
        expected_year=year,
        expected_station=station,
        locator=final_url,
        acquisition="official_https_fetch",
    )


def _read_local_year(
    year: int,
    station: str,
    path_value: str,
    *,
    root: Path,
) -> AnnualSnapshot:
    root_resolved = root.resolve()
    path = Path(path_value)
    candidate = path if path.is_absolute() else root_resolved / path
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root_resolved)
        if not resolved.is_file() or resolved.is_symlink():
            raise OSError("regular non-symlink file required")
        current = root_resolved
        for component in relative.parts:
            current /= component
            if current.is_symlink():
                raise OSError("symlink path component is forbidden")
        raw = resolved.read_bytes()
    except ValueError as exc:
        raise SourceResolutionError(
            f"local JMA snapshot must stay inside the runtime root for {year}"
        ) from exc
    except OSError as exc:
        raise SourceResolutionError(
            f"local JMA snapshot is unavailable for {year}"
        ) from exc
    if len(raw) > MAX_ALLOWED_BYTES:
        raise SourceResolutionError(
            f"local JMA snapshot exceeds {MAX_ALLOWED_BYTES} bytes for {year}"
        )
    return parse_jma_annual_text(
        raw,
        expected_year=year,
        expected_station=station,
        locator=relative.as_posix(),
        acquisition="local_snapshot",
    )


def _needed_years(anchor: date) -> list[int]:
    anchor_datetime = datetime.combine(anchor, time.min, tzinfo=JST)
    return sorted(
        {
            (anchor_datetime + timedelta(hours=hour)).year
            for hour in WINDOW_HOURS
        }
    )


def _load_requested_snapshots(
    request: dict[str, Any],
    anchor: date,
    *,
    root: Path,
    official_loader: Callable[[int, str, float, int], AnnualSnapshot],
) -> dict[int, AnnualSnapshot]:
    source = request["source"]
    snapshots: dict[int, AnnualSnapshot] = {}
    for year in _needed_years(anchor):
        if source["mode"] == "official_jma_annual_text":
            snapshots[year] = official_loader(
                year,
                STATION_CODE,
                float(source.get("timeoutSeconds", 15)),
                int(source.get("maxBytesPerYear", 131_072)),
            )
        else:
            path_value = source["yearFiles"].get(str(year))
            if path_value is None:
                raise SourceResolutionError(
                    f"local snapshot mapping does not contain required year {year}"
                )
            snapshots[year] = _read_local_year(
                year,
                STATION_CODE,
                path_value,
                root=root,
            )
    return snapshots


def _preserved_fallback(root: Path) -> tuple[date, dict[int, AnnualSnapshot]]:
    candidate_path = root / PRESERVED_CANDIDATE.relative_to(ROOT)
    snapshot_path = root / PRESERVED_SNAPSHOT.relative_to(ROOT)
    try:
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        raw = snapshot_path.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise PreservedFallbackError(
            "preserved representative candidate or snapshot is unavailable"
        ) from exc

    expected_hash = candidate.get("source", {}).get("retrievedTextSha256")
    actual_hash = _sha256_bytes(raw)
    if (
        candidate.get("schema") != "onga-stage19-m-boundary-tide-candidate-v1"
        or candidate.get("source", {}).get("stationCode") != STATION_CODE
        or expected_hash != actual_hash
    ):
        raise PreservedFallbackError(
            "preserved representative candidate integrity check failed"
        )
    try:
        anchor = date.fromisoformat(candidate["selectionRule"]["candidateDate"])
        snapshot = parse_jma_annual_text(
            raw,
            expected_year=anchor.year,
            expected_station=STATION_CODE,
            locator=PRESERVED_SNAPSHOT.relative_to(ROOT).as_posix(),
            acquisition="preserved_pinned_snapshot",
        )
    except (KeyError, ValueError, SourceResolutionError) as exc:
        raise PreservedFallbackError(
            "preserved representative candidate cannot be rederived"
        ) from exc

    current_row = snapshot.rows.get(anchor)
    if current_row is None:
        raise PreservedFallbackError(
            "preserved representative date is absent from its snapshot"
        )
    curve = candidate.get("candidateCurve", {})
    declared_hourly = curve.get("hourlyHeightAboveTideTableDatumCm")
    declared_mean = curve.get("dailyMeanCm")
    declared_anomaly = curve.get("relativeAnomalyM")
    rederived_mean = sum(current_row) / 24
    rederived_anomaly = [
        round((value - rederived_mean) / 100.0, 6) for value in current_row
    ]
    if (
        list(current_row) != declared_hourly
        or abs(rederived_mean - float(declared_mean)) > 1e-9
        or rederived_anomaly != declared_anomaly
    ):
        raise PreservedFallbackError(
            "preserved representative 24-hour curve changed"
        )
    return anchor, {anchor.year: snapshot}


def _source_height(
    moment: datetime,
    snapshots: dict[int, AnnualSnapshot],
) -> int:
    snapshot = snapshots.get(moment.year)
    if snapshot is None:
        raise SourceResolutionError(
            f"no parsed snapshot is available for year {moment.year}"
        )
    row = snapshot.rows.get(moment.date())
    if row is None:
        raise SourceResolutionError(
            f"no daily JMA row is available for {moment.date()}"
        )
    return row[moment.hour]


def _quality_contract() -> dict[str, Any]:
    return {
        "displayLabel": DISPLAY_LABEL,
        "calibrated": False,
        "observedWaterLevel": False,
        "absoluteAccuracyClaimAllowed": False,
        "absoluteOngaMouthLevelAssigned": False,
        "physicalValidationClaimAllowed": False,
        "useRestriction": (
            "secondary_relative_astronomical_tide_reference_only_"
            "not_observed_onga_mouth_level"
        ),
    }


def _authorization_contract() -> dict[str, bool]:
    return {
        "solverAssignmentAuthorized": False,
        "numericalRunAuthorized": False,
        "guiIntegrationAuthorized": False,
        "publicRuntimeIntegrationAuthorized": False,
        "mainMergeAuthorized": False,
    }


def _base_warnings() -> list[str]:
    return [
        DISPLAY_LABEL,
        "気象庁の天文潮位（予測値）であり、実測潮位ではありません。",
        "博多の相対曲線であり、遠賀川河口M境界の絶対水位・絶対標高を表しません。",
        "絶対精度および物理Validationを主張できません。",
    ]


def _build_success_document(
    request: dict[str, Any],
    *,
    requested_anchor: date,
    resolved_anchor: date,
    snapshots: dict[int, AnnualSnapshot],
    status: str,
    source_mode_resolved: str,
    source_failure: str | None,
) -> dict[str, Any]:
    anchor_datetime = datetime.combine(resolved_anchor, time.min, tzinfo=JST)
    current_row = snapshots[resolved_anchor.year].rows[resolved_anchor]
    daily_mean_cm = sum(current_row) / 24.0
    timestamps = [
        anchor_datetime + timedelta(hours=hour) for hour in WINDOW_HOURS
    ]
    heights = [_source_height(moment, snapshots) for moment in timestamps]
    tide_relative_m = [
        round((value - daily_mean_cm) / 100.0, 6) for value in heights
    ]
    requested_date_represented = (
        status == "official_prediction_transformed"
        and requested_anchor == resolved_anchor
    )

    warnings = _base_warnings()
    if not requested_date_represented:
        warnings.append(
            "指定日の取得に失敗したため、指定日を表さない保存済み代表参考曲線へ"
            "明示的にフォールバックしました。"
        )
    provenance = []
    for year in sorted(snapshots):
        item = snapshots[year]
        provenance.append(
            {
                "year": item.year,
                "provider": "気象庁",
                "station": STATION_NAME,
                "stationCode": item.station_code,
                "kind": "astronomical_hourly_tide_prediction",
                "locator": item.locator,
                "acquisition": item.acquisition,
                "acquiredAt": item.acquired_at,
                "sha256": item.sha256,
                "byteLength": item.byte_length,
            }
        )

    return {
        "schema": OUTPUT_SCHEMA,
        "status": status,
        "createdAt": _utc_now(),
        "requestSha256": _canonical_sha256(request),
        "requestedDate": requested_anchor.isoformat(),
        "resolvedAnchorDate": resolved_anchor.isoformat(),
        "requestedDateRepresented": requested_date_represented,
        "sourceModeResolved": source_mode_resolved,
        "failurePolicy": request["failurePolicy"],
        "sourceFailureBeforeFallback": source_failure,
        "boundaryInput": {
            "hours": list(WINDOW_HOURS),
            "tideRelativeM": tide_relative_m,
            "unit": "m",
            "interpolation": "piecewise_linear_hourly",
        },
        "sourceSeries": {
            "timestampsJst": [
                moment.isoformat(timespec="seconds") for moment in timestamps
            ],
            "heightAboveTideTableDatumCm": heights,
        },
        "transformation": {
            "anchor": "resolvedAnchorDate 00:00:00 JST",
            "window": "hour -12 through +24 inclusive",
            "pointCount": 37,
            "baselineDefinition": (
                "arithmetic mean of the resolved anchor date's "
                "24 hourly predictions"
            ),
            "baselineHeightAboveTideTableDatumCm": round(daily_mean_cm, 12),
            "formula": (
                "tideRelativeM = "
                "(heightAboveTideTableDatumCm - baselineCm) / 100"
            ),
            "meanRemoved": True,
            "absoluteOffsetAssigned": False,
            "periodicWrapUsed": False,
            "constantFreezeUsed": False,
            "extrapolationUsed": False,
            "timezone": "Asia/Tokyo (JST, UTC+09:00)",
        },
        "qualityContract": _quality_contract(),
        "warnings": warnings,
        "provenance": {
            "officialPageUrl": OFFICIAL_PAGE_URL,
            "officialFormatUrl": OFFICIAL_FORMAT_URL,
            "sourceFiles": provenance,
        },
        "authorization": _authorization_contract(),
    }


def _failed_document(
    request: dict[str, Any],
    requested_anchor: date,
    *,
    code: str,
    message: str,
) -> dict[str, Any]:
    warnings = _base_warnings()
    warnings.append(
        "指定日の37時間境界入力は生成されておらず、solverへ渡してはいけません。"
    )
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "failed_closed",
        "createdAt": _utc_now(),
        "requestSha256": _canonical_sha256(request),
        "requestedDate": requested_anchor.isoformat(),
        "requestedDateRepresented": False,
        "failurePolicy": request["failurePolicy"],
        "error": {"code": code, "message": message},
        "qualityContract": _quality_contract(),
        "warnings": warnings,
        "authorization": _authorization_contract(),
    }


def execute_request(
    request: dict[str, Any],
    *,
    root: Path = ROOT,
    official_loader: (
        Callable[[int, str, float, int], AnnualSnapshot] | None
    ) = None,
) -> tuple[dict[str, Any], int]:
    requested_anchor = validate_request(request)
    loader = official_loader or fetch_official_year
    try:
        snapshots = _load_requested_snapshots(
            request,
            requested_anchor,
            root=root,
            official_loader=loader,
        )
        result = _build_success_document(
            request,
            requested_anchor=requested_anchor,
            resolved_anchor=requested_anchor,
            snapshots=snapshots,
            status="official_prediction_transformed",
            source_mode_resolved=request["source"]["mode"],
            source_failure=None,
        )
        return result, 0
    except SourceResolutionError as source_error:
        if request["failurePolicy"] == "fail_closed":
            return (
                _failed_document(
                    request,
                    requested_anchor,
                    code="requested_source_resolution_failed",
                    message=str(source_error),
                ),
                2,
            )
        try:
            fallback_anchor, snapshots = _preserved_fallback(root)
            result = _build_success_document(
                request,
                requested_anchor=requested_anchor,
                resolved_anchor=fallback_anchor,
                snapshots=snapshots,
                status="fallback_reference_curve",
                source_mode_resolved="preserved_representative_snapshot",
                source_failure=str(source_error),
            )
            return result, 0
        except PreservedFallbackError as fallback_error:
            return (
                _failed_document(
                    request,
                    requested_anchor,
                    code="requested_source_and_preserved_fallback_failed",
                    message=f"{source_error}; fallback: {fallback_error}",
                ),
                3,
            )


def _write_json_atomic(path: Path, value: Any, *, replace: bool) -> None:
    path = path.resolve()
    if path.exists() and not replace:
        raise TidePipelineError(
            f"output already exists; pass --replace to overwrite: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch or read official JMA Hakata predictions and emit an isolated "
            "37-hour relative tide-boundary candidate."
        )
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="explicitly allow replacement of an existing output file",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        request = json.loads(args.input.read_text(encoding="utf-8"))
        result, exit_code = execute_request(request)
        _write_json_atomic(args.output, result, replace=args.replace)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code
    except (OSError, json.JSONDecodeError, TidePipelineError) as exc:
        print(f"[stage20-taskB-tide-boundary] {exc}", file=os.sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
