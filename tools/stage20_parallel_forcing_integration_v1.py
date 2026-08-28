#!/usr/bin/env python3
"""Integrate Task A inflows, Task B tide, and Task C gate semantics.

The integrated result is a 37-hour, uncalibrated model-reference forcing
document.  It can drive the existing GUI's automatic eight-gate selection,
but river and tide series are not assigned to the local R1C physics runner
until a compatible physical basis has been completed and validated.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_stage20_taskB_daily_tide_boundary_v1 as task_b  # noqa: E402
import stage20_taskA_uncalibrated_historical_inflow_v1 as task_a  # noqa: E402


REQUEST_SCHEMA = "onga-stage20-parallel-forcing-build-request-v1"
RESULT_SCHEMA = "onga-stage20-parallel-forcing-result-v1"
CAPABILITY_SCHEMA = "onga-stage20-parallel-forcing-capabilities-v1"
DISPLAY_LABEL = "未較正・モデル参考値"
HOURS = tuple(range(-12, 25))
JST = timezone(timedelta(hours=9))
GATE_OPENING_ORDER = (5, 4, 6, 3, 7, 2, 8, 1)
MAX_JMA_CSV_BYTES = 4 * 1024 * 1024
MODEL_PATH = (
    ROOT / "config/stage20_taskA_uncalibrated_inflow_model_reference_v1.json"
)
STATION_SPECS_PATH = (
    ROOT / "config/stage20_taskA_jma_station_specs_reference_v1.json"
)
ASSET_REGISTRY_PATH = ROOT / "config/stage20_runtime_assets_v2.json"
TIDE_ASSET_ROLE = "offline_forcing_tide_snapshot"
TIDE_SNAPSHOT_PATH = re.compile(
    r"data/jma_hakata_([0-9]{4})_hourly_tide_QF[.]txt"
)
RESPONSE_PACK_ENVELOPE = {
    "tideRelativeM": (-1.0, 1.0),
    "ongaDischargeM3S": (5.0, 180.0),
    "nishiDischargeM3S": (0.2, 12.0),
    "magariDischargeM3S": (0.1, 8.0),
    "barrageOpeningFraction": (0.0, 1.0),
}


class IntegrationError(ValueError):
    """Raised when parallel artifacts cannot be safely integrated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrationError(message)


def available_local_tide_snapshot_years() -> list[int]:
    """Return only registry-bound, intact, locally parseable annual snapshots."""

    try:
        registry = json.loads(ASSET_REGISTRY_PATH.read_text(encoding="utf-8"))
        assets = registry["assets"]
        if not isinstance(assets, list):
            return []
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return []

    years: list[int] = []
    root_resolved = ROOT.resolve()
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("role") != TIDE_ASSET_ROLE:
            continue
        path_value = asset.get("path")
        match = TIDE_SNAPSHOT_PATH.fullmatch(path_value or "")
        if match is None:
            return []
        path = ROOT / path_value
        try:
            if path.is_symlink():
                return []
            resolved = path.resolve(strict=True)
            resolved.relative_to(root_resolved)
            if not resolved.is_file():
                return []
            raw = resolved.read_bytes()
            if (
                len(raw) != asset.get("byteLength")
                or hashlib.sha256(raw).hexdigest() != asset.get("sha256")
            ):
                return []
            year = int(match.group(1))
            task_b.parse_jma_annual_text(
                raw,
                expected_year=year,
                locator=path_value,
                acquisition="registered_local_snapshot",
                acquired_at="registry_validation",
            )
        except (OSError, ValueError, task_b.SourceResolutionError):
            return []
        years.append(year)
    return sorted(years) if len(years) == len(set(years)) else []


def available_local_tide_date_ranges(
    years: list[int] | None = None,
) -> list[dict[str, str]]:
    available = sorted(set(
        available_local_tide_snapshot_years() if years is None else years
    ))
    if not available:
        return []
    ranges: list[dict[str, str]] = []
    start = available[0]
    end = start
    for year in available[1:]:
        if year == end + 1:
            end = year
            continue
        ranges.append(
            {
                "start": date(start, 1, 2).isoformat(),
                "end": date(end, 12, 30).isoformat(),
            }
        )
        start = end = year
    ranges.append(
        {
            "start": date(start, 1, 2).isoformat(),
            "end": date(end, 12, 30).isoformat(),
        }
    )
    return ranges


def date_is_available_offline(
    value: date,
    ranges: list[dict[str, str]],
) -> bool:
    return any(
        date.fromisoformat(item["start"]) <= value <= date.fromisoformat(item["end"])
        for item in ranges
    )


def finite_number(value: Any, label: str) -> float:
    require(
        not isinstance(value, bool) and isinstance(value, (int, float)),
        f"{label} must be numeric",
    )
    number = float(value)
    require(math.isfinite(number), f"{label} must be finite")
    return number


def gate_stage_for_reference(onga_discharge_m3s: float, tide_relative_m: float) -> int:
    """Preserve Task C's explicitly uncalibrated reference heuristic."""

    flow_pressure = (onga_discharge_m3s - 55.0) / 31.0
    tide_relief = max(-0.8, min(1.2, (0.28 - tide_relative_m) * 1.15))
    return max(0, min(8, round(flow_pressure + tide_relief)))


def gate_pattern_for_stage(stage: int) -> list[int]:
    require(isinstance(stage, int) and 0 <= stage <= 8, "gate stage must be 0..8")
    open_gates = set(GATE_OPENING_ORDER[:stage])
    return [1 if gate_id in open_gates else 0 for gate_id in range(1, 9)]


def _validate_hourly_series(
    values: Any,
    label: str,
    *,
    nonnegative: bool = False,
) -> list[float]:
    require(isinstance(values, list) and len(values) == len(HOURS), f"{label} must contain 37 values")
    normalized = [finite_number(value, f"{label}[{index}]") for index, value in enumerate(values)]
    if nonnegative:
        require(all(value >= 0 for value in normalized), f"{label} must be nonnegative")
    return normalized


def _river_series(
    inflow_result: dict[str, Any],
    boundary_id: str,
) -> tuple[list[str], list[float], list[float], list[float]]:
    river = inflow_result.get("rivers", {}).get(boundary_id)
    require(isinstance(river, dict), f"Task A boundary {boundary_id} is missing")
    samples = river.get("samples")
    require(isinstance(samples, list) and len(samples) == len(HOURS), f"Task A boundary {boundary_id} must have 37 samples")
    timestamps: list[str] = []
    reference: list[float] = []
    low: list[float] = []
    high: list[float] = []
    for index, sample in enumerate(samples):
        require(isinstance(sample, dict), f"Task A {boundary_id} sample {index} is invalid")
        require(sample.get("hour") == HOURS[index], f"Task A {boundary_id} hour grid changed")
        timestamp = sample.get("timestamp")
        require(isinstance(timestamp, str), f"Task A {boundary_id} timestamp is missing")
        timestamps.append(timestamp)
        reference_value = finite_number(
            sample.get("referenceDischargeM3S"),
            f"Task A {boundary_id} reference discharge",
        )
        low_value = finite_number(
            sample.get("sensitivityLowM3S"),
            f"Task A {boundary_id} sensitivity low",
        )
        high_value = finite_number(
            sample.get("sensitivityHighM3S"),
            f"Task A {boundary_id} sensitivity high",
        )
        require(
            0 <= low_value <= reference_value <= high_value,
            f"Task A {boundary_id} sensitivity envelope is invalid",
        )
        reference.append(reference_value)
        low.append(low_value)
        high.append(high_value)
    return timestamps, reference, low, high


def _envelope_diagnostics(series: dict[str, list[float]]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    for name, (minimum, maximum) in RESPONSE_PACK_ENVELOPE.items():
        for index, value in enumerate(series[name]):
            if value < minimum or value > maximum:
                violations.append(
                    {
                        "series": name,
                        "index": index,
                        "hour": HOURS[index],
                        "value": value,
                        "minimum": minimum,
                        "maximum": maximum,
                    }
                )
    return {
        "shapeCompatible": True,
        "responsePackEnvelopeCompatible": not violations,
        "responsePackEnvelopeViolations": violations,
        "valuesClipped": False,
        "automaticSyntheticResponsePackAssignmentAllowed": False,
        "reason": (
            "shape/envelope diagnostics do not establish physical compatibility; "
            "the current response pack remains a synthetic benchmark"
        ),
    }


def build_integrated_forcing(
    inflow_result: dict[str, Any],
    tide_result: dict[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    require(
        inflow_result.get("schema") == task_a.RESULT_SCHEMA,
        "Task A result schema mismatch",
    )
    require(
        inflow_result.get("status") == task_a.CLASSIFICATION,
        "Task A result is not an uncalibrated model reference",
    )
    require(inflow_result.get("hours") == list(HOURS), "Task A hour grid mismatch")
    require(
        tide_result.get("schema") == task_b.OUTPUT_SCHEMA,
        "Task B result schema mismatch",
    )
    require(
        tide_result.get("status")
        in {"official_prediction_transformed", "fallback_reference_curve"},
        "Task B did not produce a usable reference curve",
    )
    boundary_input = tide_result.get("boundaryInput")
    require(isinstance(boundary_input, dict), "Task B boundary input is missing")
    require(boundary_input.get("hours") == list(HOURS), "Task B hour grid mismatch")
    tide = _validate_hourly_series(
        boundary_input.get("tideRelativeM"),
        "Task B tideRelativeM",
    )

    timestamps_o, onga, onga_low, onga_high = _river_series(inflow_result, "O")
    timestamps_n, nishi, nishi_low, nishi_high = _river_series(inflow_result, "N")
    timestamps_g, magari, magari_low, magari_high = _river_series(inflow_result, "G")
    require(
        timestamps_o == timestamps_n == timestamps_g,
        "Task A river timestamps are not identical",
    )
    tide_timestamps = tide_result.get("sourceSeries", {}).get("timestampsJst")
    require(
        isinstance(tide_timestamps, list) and tide_timestamps == timestamps_o,
        "Task A and Task B timestamps do not describe the same 37 hours",
    )
    anchor_time = inflow_result.get("anchorTime")
    require(
        isinstance(anchor_time, str)
        and anchor_time.startswith(str(tide_result.get("resolvedAnchorDate")))
        and anchor_time[10:19] == "T00:00:00",
        "Task A anchor and Task B resolved date do not match at 00:00 JST",
    )

    automatic_stages = [
        gate_stage_for_reference(onga[index], tide[index])
        for index in range(len(HOURS))
    ]
    gate_patterns = [gate_pattern_for_stage(stage) for stage in automatic_stages]
    barrage_fraction = [stage / 8.0 for stage in automatic_stages]
    series = {
        "tideRelativeM": tide,
        "ongaDischargeM3S": onga,
        "nishiDischargeM3S": nishi,
        "magariDischargeM3S": magari,
        "barrageOpeningFraction": barrage_fraction,
    }
    fallback_used = tide_result.get("status") == "fallback_reference_curve"
    represented = tide_result.get("requestedDateRepresented") is True
    integration_status = (
        "reference_forcing_ready"
        if represented and not fallback_used
        else "reference_forcing_with_nonrepresentative_tide_fallback"
    )
    return {
        "schema": RESULT_SCHEMA,
        "version": 1,
        "status": integration_status,
        "displayLabel": DISPLAY_LABEL,
        "createdAt": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requestedDate": tide_result.get("requestedDate"),
        "resolvedAnchorDate": tide_result.get("resolvedAnchorDate"),
        "requestedDateRepresented": represented,
        "hours": list(HOURS),
        "timestampsJst": timestamps_o,
        "series": series,
        "sensitivity": {
            "ongaDischargeM3S": {"low": onga_low, "high": onga_high},
            "nishiDischargeM3S": {"low": nishi_low, "high": nishi_high},
            "magariDischargeM3S": {"low": magari_low, "high": magari_high},
            "meaning": "parameter_sweep_envelope_not_probability_interval",
        },
        "automaticGateOperation": {
            "classification": "uncalibrated_reference_heuristic_not_operation_instruction",
            "stageRange": [0, 8],
            "openingOrder": list(GATE_OPENING_ORDER),
            "stages": automatic_stages,
            "capacityFractionByGateId": gate_patterns,
            "formula": (
                "round(clamp((ongaDischargeM3S-55)/31 + "
                "clamp((0.28-tideRelativeM)*1.15,-0.8,1.2),0,8))"
            ),
        },
        "sourceArtifacts": {
            "inflow": {
                "schema": inflow_result["schema"],
                "pipelineVersion": inflow_result.get("pipelineVersion"),
                "provenance": inflow_result.get("provenance"),
            },
            "tide": {
                "schema": tide_result["schema"],
                "status": tide_result["status"],
                "sourceModeResolved": tide_result.get("sourceModeResolved"),
                "provenance": tide_result.get("provenance"),
            },
        },
        "compatibility": _envelope_diagnostics(series),
        "connection": {
            "guiDisplayConnected": True,
            "automaticGateSelectionConnected": True,
            "localR1CGateOnlyRunConnected": True,
            "riverAndTideBoundaryPhysicsConnected": False,
            "productionPrecomputationConnected": False,
            "publicRuntimeConnected": False,
        },
        "limitations": [
            DISPLAY_LABEL,
            "流量は公式降水量からの未較正推定であり、観測流量ではない。",
            "潮位は博多の天文潮位予測を平均除去した相対参考値で、遠賀川河口の実測水位ではない。",
            "自動開門段階はTask Cの未較正参考式で、現地操作指示ではない。",
            "現行ローカルR1C物理計算へ接続するのは8門状態だけで、河川流量・潮位境界は固定条件のままである。",
        ],
    }


def validate_client_request(payload: dict[str, Any]) -> tuple[str, bytes, str]:
    require(payload.get("schema") == REQUEST_SCHEMA, "forcing request schema mismatch")
    requested_date = payload.get("requestedDate")
    require(isinstance(requested_date, str), "requestedDate is required")
    try:
        parsed_date = datetime.strptime(requested_date, "%Y-%m-%d").date()
    except ValueError as error:
        raise IntegrationError("requestedDate must be YYYY-MM-DD") from error
    available_ranges = available_local_tide_date_ranges()
    require(
        date_is_available_offline(parsed_date, available_ranges),
        "requestedDate has no complete registered offline tide snapshot window",
    )
    encoded = payload.get("jmaCsvBase64")
    require(isinstance(encoded, str) and encoded, "jmaCsvBase64 is required")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise IntegrationError("jmaCsvBase64 is invalid") from error
    require(0 < len(raw) <= MAX_JMA_CSV_BYTES, "JMA CSV size is outside the allowed range")
    failure_policy = payload.get("tideFailurePolicy", "fail_closed")
    require(
        failure_policy in {"fail_closed", "fallback_to_preserved_representative"},
        "tideFailurePolicy is invalid",
    )
    return requested_date, raw, failure_policy


def build_from_client_request(
    payload: dict[str, Any],
    *,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    requested_date, raw_csv, failure_policy = validate_client_request(payload)
    specs_document = json.loads(STATION_SPECS_PATH.read_text(encoding="utf-8"))
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    retrieval_time = retrieved_at or datetime.now(JST).isoformat(timespec="seconds")
    weather = task_a.normalise_jma_download_csv(
        raw_csv,
        specs_document["stations"],
        retrieval_time,
    )
    anchor = f"{requested_date}T00:00:00+09:00"
    inflow_result = task_a.estimate_historical_inflows(weather, model, anchor)
    anchor_datetime = datetime.strptime(requested_date, "%Y-%m-%d").replace(
        tzinfo=JST,
    )
    required_tide_years = sorted(
        {
            (anchor_datetime + timedelta(hours=hour)).year
            for hour in HOURS
        }
    )
    tide_request = {
        "schema": task_b.INPUT_SCHEMA,
        "requestedDate": requested_date,
        "station": {"code": "QF", "name": "博多"},
        "window": {"startHour": -12, "endHour": 24, "stepHours": 1},
        "source": {
            "mode": "local_snapshot_set",
            "yearFiles": {
                str(year): f"data/jma_hakata_{year}_hourly_tide_QF.txt"
                for year in required_tide_years
            },
        },
        "failurePolicy": failure_policy,
    }
    tide_result, exit_code = task_b.execute_request(
        tide_request,
        root=ROOT,
    )
    require(
        exit_code == 0,
        "offline tide resolution failed: "
        + tide_result.get("error", {}).get("message", "local snapshot unavailable"),
    )
    integrated = build_integrated_forcing(inflow_result, tide_result)
    return {
        **integrated,
        "runtimePolicy": {
            "offlineOnly": True,
            "networkFetchAttempted": False,
            "tideSourcePolicy": "preserved_local_snapshot_or_fail_closed",
            "tideSourceModeResolved": tide_result.get("sourceModeResolved"),
        },
    }


def capability_document() -> dict[str, Any]:
    available_years = available_local_tide_snapshot_years()
    available_ranges = available_local_tide_date_ranges(available_years)
    ready = bool(available_ranges)
    preferred_default = "2026-02-15"
    default_date = preferred_default if ready and date_is_available_offline(
        date.fromisoformat(preferred_default),
        available_ranges,
    ) else (available_ranges[0]["start"] if ready else None)
    return {
        "schema": CAPABILITY_SCHEMA,
        "version": 1,
        "status": "READY_OFFLINE" if ready else "BLOCKED_OFFLINE_TIDE_UNAVAILABLE",
        "localOnly": True,
        "offlineOnly": True,
        "networkFetchAllowed": False,
        "tideSourcePolicy": "preserved_local_snapshot_or_fail_closed",
        "availableTideSnapshotYears": available_years,
        "availableRequestedDateRanges": available_ranges,
        "defaultRequestedDate": default_date,
        "acceptedRequestSchema": REQUEST_SCHEMA,
        "resultSchema": RESULT_SCHEMA,
        "hourRange": [-12, 24],
        "pointCount": 37,
        "requiredJmaStations": ["八幡", "飯塚", "添田", "宗像"],
        "maximumJmaCsvBytes": MAX_JMA_CSV_BYTES,
        "classification": DISPLAY_LABEL,
        "connection": {
            "guiDisplay": True,
            "automaticGateSelection": True,
            "localR1CGateOnlyRun": True,
            "riverAndTideBoundaryPhysics": False,
            "productionPrecomputation": False,
        },
    }
