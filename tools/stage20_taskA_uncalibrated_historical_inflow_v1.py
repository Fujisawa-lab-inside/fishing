#!/usr/bin/env python3
"""Task A: uncalibrated historical rainfall-to-inflow pipeline.

This module is intentionally independent from the Stage 20 mesh, solver, GUI,
and public assets.  It consumes preserved JMA hourly observations, applies a
transparent linear-reservoir reference model, and can prepare a 37-hour input
proposal without changing the existing input fixture.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import math
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PIPELINE_VERSION = "stage20-taskA-uncalibrated-historical-inflow-v1"
WEATHER_SCHEMA = "onga-stage20-taskA-official-hourly-weather-input-v1"
MODEL_SCHEMA = "onga-stage20-taskA-uncalibrated-inflow-model-v1"
RESULT_SCHEMA = "onga-stage20-taskA-uncalibrated-historical-inflow-result-v1"
HYBRID_PROPOSAL_SCHEMA = "onga-stage20-taskA-hybrid37-input-proposal-v1"
CLASSIFICATION = "未較正・モデル参考値"
JST = timezone(timedelta(hours=9))
HOURS = tuple(range(-12, 25))
RIVER_KEYS = {
    "N": ("nishikawa", "nishiDischargeM3S"),
    "O": ("ongagawa", "ongaDischargeM3S"),
    "G": ("magarigawa", "magariDischargeM3S"),
}
OFFICIAL_JMA_HOSTS = {
    "www.data.jma.go.jp",
    "data.jma.go.jp",
    "ds.data.jma.go.jp",
    "www.jma.go.jp",
}
RESPONSE_PACK_ENVELOPE = {
    "ongaDischargeM3S": (5.0, 180.0),
    "nishiDischargeM3S": (0.2, 12.0),
    "magariDischargeM3S": (0.1, 8.0),
}


class ContractError(ValueError):
    """Raised when an input violates the independent Task A contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _finite(value: Any, label: str) -> float:
    number = float(value)
    _require(math.isfinite(number), f"{label} must be finite")
    return number


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_no_duplicate_object)
    _require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def write_new_json(path: str | Path, value: dict[str, Any]) -> None:
    """Write a new artifact and refuse to overwrite any existing path."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def parse_timestamp(value: str, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} is not valid ISO-8601: {value}") from error
    _require(parsed.tzinfo is not None, f"{label} must include a timezone offset")
    return parsed


def parse_hour(value: str, label: str) -> datetime:
    parsed = parse_timestamp(value, label)
    _require(
        parsed.minute == 0 and parsed.second == 0 and parsed.microsecond == 0,
        f"{label} must be aligned to an exact hour",
    )
    return parsed


def jst_iso(value: datetime) -> str:
    return value.astimezone(JST).isoformat(timespec="seconds")


def _validate_official_source(source: Any) -> dict[str, Any]:
    _require(isinstance(source, dict), "weather source metadata is required")
    _require(
        source.get("provider") == "Japan Meteorological Agency",
        "weather source provider must be Japan Meteorological Agency",
    )
    url = source.get("url")
    _require(isinstance(url, str), "weather source URL is required")
    parsed = urlparse(url)
    _require(
        parsed.scheme == "https" and (parsed.hostname or "").lower() in OFFICIAL_JMA_HOSTS,
        "weather source URL must use an allowed official JMA HTTPS host",
    )
    digest = source.get("sourceFileSha256")
    _require(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
        "sourceFileSha256 must be a lowercase SHA-256 digest",
    )
    retrieved = parse_timestamp(source.get("retrievedAt"), "source.retrievedAt")
    return {
        "provider": source["provider"],
        "dataset": str(source.get("dataset", "")),
        "url": url,
        "retrievedAt": jst_iso(retrieved),
        "sourceFileSha256": digest,
    }


def validate_weather(
    weather: dict[str, Any],
    accepted_quality_codes: set[int],
) -> tuple[dict[str, dict[datetime, float]], dict[str, Any]]:
    _require(weather.get("schema") == WEATHER_SCHEMA, "weather schema mismatch")
    _require(weather.get("timezone") == "Asia/Tokyo", "weather timezone must be Asia/Tokyo")
    _require(
        weather.get("intervalSemantics") == "preceding_hour_ending_at_timestamp",
        "weather interval semantics mismatch",
    )
    source = _validate_official_source(weather.get("source"))
    retrieved_at = parse_timestamp(source["retrievedAt"], "source.retrievedAt")
    stations = weather.get("stations")
    _require(isinstance(stations, list) and stations, "at least one weather station is required")

    series_by_station: dict[str, dict[datetime, float]] = {}
    metadata_by_station: dict[str, Any] = {}
    for station_index, station in enumerate(stations):
        _require(isinstance(station, dict), f"station[{station_index}] must be an object")
        station_id = station.get("id")
        _require(
            isinstance(station_id, str) and re.fullmatch(r"[a-z0-9_-]+", station_id) is not None,
            f"station[{station_index}].id is invalid",
        )
        _require(station_id not in series_by_station, f"duplicate station id: {station_id}")
        samples = station.get("samples")
        _require(isinstance(samples, list) and samples, f"{station_id} samples are required")
        station_series: dict[datetime, float] = {}
        previous: datetime | None = None
        for sample_index, sample in enumerate(samples):
            _require(
                isinstance(sample, dict),
                f"{station_id}.samples[{sample_index}] must be an object",
            )
            timestamp = parse_hour(
                sample.get("timestamp"),
                f"{station_id}.samples[{sample_index}].timestamp",
            )
            _require(
                timestamp.utcoffset() == timedelta(hours=9),
                f"{station_id} timestamps must use JST (+09:00)",
            )
            _require(timestamp <= retrieved_at, f"{station_id} contains data after retrievedAt")
            if previous is not None:
                _require(
                    timestamp - previous == timedelta(hours=1),
                    f"{station_id} timestamps must be strictly contiguous at one-hour intervals",
                )
            previous = timestamp
            quality = int(sample.get("qualityCode"))
            _require(
                quality in accepted_quality_codes,
                f"{station_id} quality code {quality} is not accepted",
            )
            precipitation = _finite(
                sample.get("precipitationMm"),
                f"{station_id}.samples[{sample_index}].precipitationMm",
            )
            _require(precipitation >= 0, f"{station_id} precipitation must be nonnegative")
            _require(timestamp not in station_series, f"{station_id} has a duplicate timestamp")
            station_series[timestamp] = precipitation
        series_by_station[station_id] = station_series
        metadata_by_station[station_id] = {
            "name": str(station.get("name", "")),
            "providerStationCode": str(station.get("providerStationCode", "")),
            "sampleCount": len(samples),
            "firstTimestamp": jst_iso(next(iter(station_series))),
            "lastTimestamp": jst_iso(next(reversed(station_series))),
        }
    return series_by_station, {"source": source, "stations": metadata_by_station}


def validate_model(model: dict[str, Any]) -> dict[str, Any]:
    _require(model.get("schema") == MODEL_SCHEMA, "model schema mismatch")
    _require(model.get("classification") == CLASSIFICATION, "model classification mismatch")
    warmup_hours = int(model.get("warmupHours"))
    _require(24 <= warmup_hours <= 720, "warmupHours must be in [24, 720]")
    quality_codes = model.get("acceptedJmaQualityCodes")
    _require(
        isinstance(quality_codes, list)
        and quality_codes
        and all(isinstance(value, int) for value in quality_codes),
        "acceptedJmaQualityCodes must be a non-empty integer array",
    )
    basins = model.get("basins")
    _require(isinstance(basins, dict) and set(basins) == set(RIVER_KEYS), "basins must be exactly N/O/G")

    normalised_basins: dict[str, Any] = {}
    for boundary_id in RIVER_KEYS:
        basin = basins[boundary_id]
        _require(isinstance(basin, dict), f"basin {boundary_id} must be an object")
        area = _finite(basin.get("catchmentAreaKm2"), f"{boundary_id}.catchmentAreaKm2")
        baseflow = _finite(basin.get("baseflowM3S"), f"{boundary_id}.baseflowM3S")
        coefficient = _finite(basin.get("runoffCoefficient"), f"{boundary_id}.runoffCoefficient")
        tau = _finite(basin.get("reservoirTimeConstantHours"), f"{boundary_id}.reservoirTimeConstantHours")
        _require(area > 0, f"{boundary_id} catchment area must be positive")
        _require(baseflow >= 0, f"{boundary_id} baseflow must be nonnegative")
        _require(0 <= coefficient <= 1, f"{boundary_id} runoff coefficient must be in [0, 1]")
        _require(tau > 0, f"{boundary_id} reservoir time constant must be positive")
        weights = basin.get("rainfallWeights")
        _require(isinstance(weights, dict) and weights, f"{boundary_id} rainfall weights are required")
        numeric_weights = {
            station_id: _finite(weight, f"{boundary_id}.rainfallWeights.{station_id}")
            for station_id, weight in weights.items()
        }
        _require(
            all(re.fullmatch(r"[a-z0-9_-]+", station_id) for station_id in numeric_weights),
            f"{boundary_id} has an invalid station id",
        )
        _require(all(weight >= 0 for weight in numeric_weights.values()), f"{boundary_id} weights must be nonnegative")
        _require(
            abs(sum(numeric_weights.values()) - 1.0) <= 1e-12,
            f"{boundary_id} rainfall weights must sum to one",
        )
        _require(
            basin.get("parameterBasis") == "uncalibrated_assumption_not_official_observation",
            f"{boundary_id} parameter basis must remain explicitly uncalibrated",
        )
        normalised_basins[boundary_id] = {
            "labelJa": str(basin.get("labelJa", "")),
            "catchmentAreaKm2": area,
            "baseflowM3S": baseflow,
            "runoffCoefficient": coefficient,
            "reservoirTimeConstantHours": tau,
            "rainfallWeights": numeric_weights,
            "parameterBasis": basin["parameterBasis"],
        }
    return {
        "warmupHours": warmup_hours,
        "acceptedJmaQualityCodes": set(quality_codes),
        "basins": normalised_basins,
        "sensitivityFactors": model.get("sensitivityFactors"),
    }


def _validate_sensitivity_factors(raw: Any) -> dict[str, list[float]]:
    _require(isinstance(raw, dict), "sensitivityFactors are required")
    result: dict[str, list[float]] = {}
    for key in ("baseflow", "runoffCoefficient", "reservoirTimeConstant"):
        values = raw.get(key)
        _require(isinstance(values, list) and 1.0 in values, f"sensitivityFactors.{key} must include 1.0")
        numbers = [_finite(value, f"sensitivityFactors.{key}") for value in values]
        _require(all(value > 0 for value in numbers), f"sensitivityFactors.{key} must be positive")
        result[key] = numbers
    return result


def _weighted_rainfall(
    times: list[datetime],
    station_series: dict[str, dict[datetime, float]],
    weights: dict[str, float],
    boundary_id: str,
) -> list[float]:
    missing_stations = sorted(set(weights) - set(station_series))
    _require(not missing_stations, f"{boundary_id} missing stations: {missing_stations}")
    rainfall: list[float] = []
    for timestamp in times:
        missing = [station_id for station_id in weights if timestamp not in station_series[station_id]]
        _require(
            not missing,
            f"{boundary_id} missing required observations at {jst_iso(timestamp)}: {missing}",
        )
        rainfall.append(sum(station_series[station_id][timestamp] * weight for station_id, weight in weights.items()))
    return rainfall


def _route_linear_reservoir(
    rainfall_mm: list[float],
    area_km2: float,
    baseflow_m3_s: float,
    runoff_coefficient: float,
    time_constant_hours: float,
) -> tuple[list[float], dict[str, float]]:
    decay = math.exp(-1.0 / time_constant_hours)
    storage_mm = 0.0
    discharge: list[float] = []
    effective_total_mm = 0.0
    released_total_mm = 0.0
    for rain_mm in rainfall_mm:
        effective_mm = runoff_coefficient * rain_mm
        effective_total_mm += effective_mm
        available_mm = storage_mm + effective_mm
        released_mm = available_mm * (1.0 - decay)
        storage_mm = available_mm * decay
        released_total_mm += released_mm
        quickflow_m3_s = released_mm * area_km2 * 1000.0 / 3600.0
        discharge.append(baseflow_m3_s + quickflow_m3_s)
    residual_mm = effective_total_mm - released_total_mm - storage_mm
    return discharge, {
        "effectiveRainfallTotalMm": effective_total_mm,
        "releasedRunoffTotalMm": released_total_mm,
        "finalStorageMm": storage_mm,
        "massBalanceResidualMm": residual_mm,
    }


def estimate_historical_inflows(
    weather: dict[str, Any],
    model: dict[str, Any],
    anchor_time: str,
) -> dict[str, Any]:
    """Estimate the N/O/G series on the existing -12..+24 hourly grid."""

    model_values = validate_model(model)
    sensitivity = _validate_sensitivity_factors(model_values["sensitivityFactors"])
    station_series, provenance = validate_weather(
        weather,
        model_values["acceptedJmaQualityCodes"],
    )
    anchor = parse_hour(anchor_time, "anchorTime")
    _require(anchor.utcoffset() == timedelta(hours=9), "anchorTime must use JST (+09:00)")
    output_times = [anchor + timedelta(hours=hour) for hour in HOURS]
    route_start = output_times[0] - timedelta(hours=model_values["warmupHours"])
    route_times = [
        route_start + timedelta(hours=index)
        for index in range(model_values["warmupHours"] + len(HOURS))
    ]
    output_start_index = model_values["warmupHours"]

    river_results: dict[str, Any] = {}
    for boundary_id, (river_id, hybrid_key) in RIVER_KEYS.items():
        basin = model_values["basins"][boundary_id]
        rainfall = _weighted_rainfall(
            route_times,
            station_series,
            basin["rainfallWeights"],
            boundary_id,
        )
        scenario_series: list[list[float]] = []
        reference_series: list[float] | None = None
        reference_balance: dict[str, float] | None = None
        for base_factor, runoff_factor, tau_factor in itertools.product(
            sensitivity["baseflow"],
            sensitivity["runoffCoefficient"],
            sensitivity["reservoirTimeConstant"],
        ):
            coefficient = min(1.0, basin["runoffCoefficient"] * runoff_factor)
            routed, balance = _route_linear_reservoir(
                rainfall,
                basin["catchmentAreaKm2"],
                basin["baseflowM3S"] * base_factor,
                coefficient,
                basin["reservoirTimeConstantHours"] * tau_factor,
            )
            selected = routed[output_start_index:]
            scenario_series.append(selected)
            if base_factor == runoff_factor == tau_factor == 1.0:
                reference_series = selected
                reference_balance = balance
        _require(reference_series is not None and reference_balance is not None, "reference scenario is missing")
        low = [min(series[index] for series in scenario_series) for index in range(len(HOURS))]
        high = [max(series[index] for series in scenario_series) for index in range(len(HOURS))]
        output_rainfall = rainfall[output_start_index:]
        samples = [
            {
                "timestamp": jst_iso(output_times[index]),
                "hour": HOURS[index],
                "basinRainfallMm": round(output_rainfall[index], 6),
                "referenceDischargeM3S": round(reference_series[index], 6),
                "sensitivityLowM3S": round(low[index], 6),
                "sensitivityHighM3S": round(high[index], 6),
            }
            for index in range(len(HOURS))
        ]
        river_results[boundary_id] = {
            "riverId": river_id,
            "labelJa": basin["labelJa"],
            "hybridInputKey": hybrid_key,
            "signConvention": "nonnegative_positive_inflow_into_domain",
            "parameterBasis": basin["parameterBasis"],
            "parameters": {
                key: basin[key]
                for key in (
                    "catchmentAreaKm2",
                    "baseflowM3S",
                    "runoffCoefficient",
                    "reservoirTimeConstantHours",
                    "rainfallWeights",
                )
            },
            "samples": samples,
            "diagnostics": {
                **{key: round(value, 12) for key, value in reference_balance.items()},
                "sensitivityScenarioCount": len(scenario_series),
                "sensitivityMeaning": "parameter_sweep_envelope_not_probability_interval",
            },
        }

    return {
        "schema": RESULT_SCHEMA,
        "pipelineVersion": PIPELINE_VERSION,
        "status": CLASSIFICATION,
        "classificationCode": "uncalibrated_model_reference_values",
        "anchorTime": jst_iso(anchor),
        "hours": list(HOURS),
        "timeConvention": {
            "timezone": "Asia/Tokyo",
            "rainfall": "preceding_hour_ending_at_timestamp",
            "discharge": "hourly_mean_assigned_to_same_ending_timestamp",
        },
        "provenance": provenance,
        "model": {
            "schema": MODEL_SCHEMA,
            "method": "weighted_hourly_rainfall_plus_linear_reservoir_and_fixed_baseflow",
            "warmupHours": model_values["warmupHours"],
            "acceptedJmaQualityCodes": sorted(model_values["acceptedJmaQualityCodes"]),
            "sensitivityFactors": sensitivity,
        },
        "rivers": river_results,
        "limitations": [
            "v1で流量応答に使う公式気象要素は時別降水量だけであり、気温、風、湿度等は使わない。",
            "境界互換の流量観測による較正・検証を行っていない。",
            "三流域への面積配分、基底流量、流出係数、応答時間、雨量局重みは仮定である。",
            "感度幅は確率的信頼区間ではなく、指定パラメータ倍率の包絡である。",
            "河口堰操作、取排水、貯留、潮汐背水、空間的降雨の未観測部分を同定していない。",
        ],
        "safeguards": {
            "meshChanged": False,
            "solverChanged": False,
            "publicGuiChanged": False,
            "mainChanged": False,
            "physicalAccuracyClaimAllowed": False,
            "automaticPublicConnectionAllowed": False,
        },
    }


def build_hybrid37_proposal(
    result: dict[str, Any],
    existing_template: dict[str, Any],
) -> dict[str, Any]:
    """Merge only the three river arrays into a copied 37-hour template."""

    _require(result.get("schema") == RESULT_SCHEMA, "result schema mismatch")
    _require(result.get("hours") == list(HOURS), "result does not use the 37-hour grid")
    _require(
        existing_template.get("schema") == "onga-stage20-hybrid-hourly-input-v1",
        "hybrid template schema mismatch",
    )
    _require(existing_template.get("hours") == list(HOURS), "hybrid template hour grid mismatch")
    for preserved_key in ("tideRelativeM", "barrageOpeningFraction"):
        values = existing_template.get(preserved_key)
        _require(
            isinstance(values, list)
            and len(values) == len(HOURS)
            and all(isinstance(value, (int, float)) and math.isfinite(value) for value in values),
            f"hybrid template {preserved_key} is invalid",
        )

    proposed = deepcopy(existing_template)
    proposed["status"] = "uncalibrated_model_reference_values_not_public_gui_fixture"
    proposed["sourceLabel"] = CLASSIFICATION
    for boundary_id, (_, hybrid_key) in RIVER_KEYS.items():
        reference_values = [
            sample["referenceDischargeM3S"]
            for sample in result["rivers"][boundary_id]["samples"]
        ]
        _require(
            len(reference_values) == len(HOURS)
            and all(
                isinstance(value, (int, float))
                and math.isfinite(value)
                and value >= 0
                for value in reference_values
            ),
            f"{boundary_id} reference series must contain 37 finite nonnegative values",
        )
        proposed[hybrid_key] = reference_values

    violations: list[dict[str, Any]] = []
    for key, (minimum, maximum) in RESPONSE_PACK_ENVELOPE.items():
        for index, value in enumerate(proposed[key]):
            if value < minimum or value > maximum:
                violations.append(
                    {
                        "series": key,
                        "index": index,
                        "hour": HOURS[index],
                        "value": value,
                        "minimum": minimum,
                        "maximum": maximum,
                    }
                )
    return {
        "schema": HYBRID_PROPOSAL_SCHEMA,
        "status": CLASSIFICATION,
        "sourceResultSchema": RESULT_SCHEMA,
        "proposedHourlyInput": proposed,
        "compatibility": {
            "targetSchema": "onga-stage20-hybrid-hourly-input-v1",
            "shapeCompatible": True,
            "responsePackEnvelopeCompatible": not violations,
            "responsePackEnvelopeViolations": violations,
            "valuesClipped": False,
            "currentPublicGuiAcceptsStatus": False,
            "reason": "current GUI intentionally accepts only synthetic_browser_benchmark_only",
        },
        "integration": {
            "performed": False,
            "authorized": False,
            "requiredReview": [
                "流域・流出パラメータの較正",
                "境界互換流量観測での独立検証",
                "応答パック包絡外値がある場合の物理再計算",
                "未較正表示を維持する別入力経路の承認",
            ],
        },
    }


def _decode_jma_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ContractError("JMA CSV must be UTF-8 with BOM or CP932")


def _parse_jma_datetime_literal(value: str) -> datetime:
    literal = value.strip()
    match_24 = re.fullmatch(r"(\d{4}/\d{1,2}/\d{1,2}) 24(?::00(?::00)?)?", literal)
    if match_24:
        base = datetime.strptime(match_24.group(1), "%Y/%m/%d").replace(tzinfo=JST)
        return base + timedelta(days=1)
    for pattern in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d %H"):
        try:
            return datetime.strptime(literal, pattern).replace(tzinfo=JST)
        except ValueError:
            continue
    raise ContractError(f"unsupported JMA date literal: {value}")


def normalise_jma_download_csv(
    raw: bytes,
    station_specs: list[dict[str, str]],
    retrieved_at: str,
    source_url: str = "https://www.data.jma.go.jp/risk/obsdl/index.php",
) -> dict[str, Any]:
    """Convert a preserved numeric-mode JMA hourly CSV into the input contract."""

    text = _decode_jma_csv(raw)
    rows = list(csv.reader(io.StringIO(text)))
    header_index = next(
        (
            index
            for index, row in enumerate(rows)
            if any("年月日時" in cell.replace(" ", "") for cell in row)
        ),
        None,
    )
    _require(header_index is not None and header_index >= 1, "JMA hourly header was not found")
    _require(header_index + 1 < len(rows), "JMA detail header is missing")
    station_header = rows[header_index - 1]
    element_header = rows[header_index]
    detail_header = rows[header_index + 1]
    width = max(len(station_header), len(element_header), len(detail_header))
    station_header += [""] * (width - len(station_header))
    element_header += [""] * (width - len(element_header))
    detail_header += [""] * (width - len(detail_header))
    timestamp_index = next(
        index
        for index, cell in enumerate(element_header)
        if "年月日時" in cell.replace(" ", "")
    )

    parsed_stations: list[dict[str, Any]] = []
    for spec in station_specs:
        station_id = spec.get("id")
        station_name = spec.get("name")
        _require(
            isinstance(station_id, str) and isinstance(station_name, str),
            "station spec requires id and name",
        )
        value_candidates = [
            index
            for index in range(width)
            if station_header[index].strip() == station_name
            and "降水量" in element_header[index]
            and detail_header[index].strip() == ""
        ]
        quality_candidates = [
            index
            for index in range(width)
            if station_header[index].strip() == station_name
            and "降水量" in element_header[index]
            and detail_header[index].strip() == "品質情報"
        ]
        _require(
            len(value_candidates) == 1 and len(quality_candidates) == 1,
            f"could not identify one precipitation value/quality pair for {station_name}",
        )
        value_index = value_candidates[0]
        quality_index = quality_candidates[0]
        samples: list[dict[str, Any]] = []
        for row in rows[header_index + 2 :]:
            if not row or timestamp_index >= len(row) or not row[timestamp_index].strip():
                continue
            _require(
                max(value_index, quality_index) < len(row),
                f"short JMA CSV row for {station_name}",
            )
            timestamp = _parse_jma_datetime_literal(row[timestamp_index])
            raw_value = row[value_index].strip()
            raw_quality = row[quality_index].strip()
            _require(raw_value != "", f"blank precipitation value for {station_name} at {jst_iso(timestamp)}")
            _require(raw_quality != "", f"blank quality code for {station_name} at {jst_iso(timestamp)}")
            precipitation = _finite(raw_value, f"{station_name} precipitation")
            quality = int(raw_quality)
            samples.append(
                {
                    "timestamp": jst_iso(timestamp),
                    "precipitationMm": precipitation,
                    "qualityCode": quality,
                }
            )
        _require(samples, f"no data rows found for {station_name}")
        parsed_stations.append(
            {
                "id": station_id,
                "name": station_name,
                "providerStationCode": str(spec.get("providerStationCode", "")),
                "samples": samples,
            }
        )
    retrieved = parse_timestamp(retrieved_at, "retrievedAt")
    _require(retrieved.utcoffset() == timedelta(hours=9), "retrievedAt must use JST (+09:00)")
    return {
        "schema": WEATHER_SCHEMA,
        "status": "official_observations_not_river_flow",
        "timezone": "Asia/Tokyo",
        "intervalSemantics": "preceding_hour_ending_at_timestamp",
        "source": {
            "provider": "Japan Meteorological Agency",
            "dataset": "past_weather_download_hourly_numeric_csv",
            "url": source_url,
            "retrievedAt": jst_iso(retrieved),
            "sourceFileSha256": hashlib.sha256(raw).hexdigest(),
        },
        "stations": parsed_stations,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalise = subparsers.add_parser("normalise-jma-csv")
    normalise.add_argument("--csv", required=True)
    normalise.add_argument("--station-specs", required=True)
    normalise.add_argument("--retrieved-at", required=True)
    normalise.add_argument("--output", required=True)

    estimate = subparsers.add_parser("estimate")
    estimate.add_argument("--weather", required=True)
    estimate.add_argument("--model", required=True)
    estimate.add_argument("--anchor", required=True)
    estimate.add_argument("--result-output", required=True)
    estimate.add_argument("--hybrid-template")
    estimate.add_argument("--hybrid-output")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "normalise-jma-csv":
        specs_document = load_json(args.station_specs)
        specs = specs_document.get("stations")
        _require(isinstance(specs, list) and specs, "station-specs JSON requires stations")
        weather = normalise_jma_download_csv(
            Path(args.csv).read_bytes(),
            specs,
            args.retrieved_at,
        )
        write_new_json(args.output, weather)
        return 0

    _require(
        bool(args.hybrid_template) == bool(args.hybrid_output),
        "--hybrid-template and --hybrid-output must be supplied together",
    )
    result = estimate_historical_inflows(
        load_json(args.weather),
        load_json(args.model),
        args.anchor,
    )
    write_new_json(args.result_output, result)
    if args.hybrid_template:
        proposal = build_hybrid37_proposal(result, load_json(args.hybrid_template))
        write_new_json(args.hybrid_output, proposal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
