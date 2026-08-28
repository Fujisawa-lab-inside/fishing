#!/usr/bin/env python3
"""Build the identity-bound forcing for the all-closed R1C baseline canary.

The output is a deterministic diagnostic scenario.  It uses the frozen
representative Hakata astronomical relative-tide curve only to exercise the
boundary numerics; it is not an observed Onga-mouth level or a forecast.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage19_solver_inputs as tide_model  # noqa: E402


OUTPUT = ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json"
PREFLIGHT_CONTRACT = ROOT / "config/stage20_continuous_all_closed_successor_preflight_v1.json"
TIDE_CANDIDATE = ROOT / "config/stage19_m_boundary_tide_candidate_v1.json"
TIDE_EVALUATOR = ROOT / "tools/stage19_solver_inputs.py"
PILOT_REPORT = ROOT / "docs/results/stage20-kernel-v3-physical-pilot-29411976467/pilot-report.json"
BUILDER = Path(__file__).resolve()
SCHEMA = "onga-stage20-continuous-all-closed-forcing-manifest-v1"
MODEL_SECONDS = tuple(range(0, 901, 60))
START_CLOCK_SECONDS = 82680.00485789491
RIVER_DISCHARGE_M3_S = {"N": 2.0, "O": 35.0, "G": 1.0}
TIDE_PARAMETERS = {
    "phaseShiftMinutes": 0.0,
    "amplitudeMultiplier": 1.0,
    "meanOffsetM": None,
}


class ForcingBuildStop(RuntimeError):
    """Fail closed on input drift or attempted overwrite."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ForcingBuildStop(f"[stage20-all-closed-forcing-v1] {message}")


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ForcingBuildStop(f"non-canonical forcing value: {error}") from error


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ForcingBuildStop(f"nonfinite JSON token: {token}")
            ),
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ForcingBuildStop(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"{path} must contain an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _binding(role: str, path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"binding missing: {path}")
    return {
        "role": role,
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256_file(path),
        "byteLength": path.stat().st_size,
    }


def _tide_at(model_seconds: int, candidate: dict[str, Any]) -> float:
    value = float(
        tide_model.tide_anomaly_m(
            (START_CLOCK_SECONDS + float(model_seconds)) % 86400.0,
            TIDE_PARAMETERS,
            candidate,
        )
    )
    require(math.isfinite(value), "tide evaluator returned a nonfinite value")
    return value


def build_manifest() -> dict[str, Any]:
    candidate = read_json(TIDE_CANDIDATE)
    pilot = read_json(PILOT_REPORT)
    preflight = read_json(PREFLIGHT_CONTRACT)
    require(
        candidate.get("schema") == "onga-stage19-m-boundary-tide-candidate-v1",
        "tide candidate schema changed",
    )
    require(
        candidate.get("source", {}).get("stationCode") == "QF"
        and candidate.get("source", {}).get("station") == "博多",
        "diagnostic tide source identity changed",
    )
    require(
        candidate.get("selectionRule", {}).get("selectionApproved") is False,
        "representative diagnostic tide unexpectedly became approved",
    )
    simulated_seconds = float(pilot.get("run", {}).get("simulatedSeconds"))
    require(
        math.isclose(simulated_seconds, 600.0048578949198, rel_tol=0.0, abs_tol=1e-12),
        "pilot end clock changed",
    )
    require(
        preflight.get("scope", {}).get("requestedCapacityByGateId1To8")
        == [0.0] * 8
        and preflight.get("scope", {}).get("fishwayDischargeM3S") == 0.0,
        "preflight is not the all-closed zero-fishway baseline",
    )

    tide_values = [_tide_at(seconds, candidate) for seconds in MODEL_SECONDS]
    river = {
        boundary: [value for _ in MODEL_SECONDS]
        for boundary, value in RIVER_DISCHARGE_M3_S.items()
    }
    bindings = [
        _binding("forcing_builder", BUILDER),
        _binding("all_closed_preflight_contract", PREFLIGHT_CONTRACT),
        _binding("representative_relative_tide_candidate", TIDE_CANDIDATE),
        _binding("tide_evaluator", TIDE_EVALUATOR),
        _binding("pilot_clock_reference", PILOT_REPORT),
    ]
    return {
        "schema": SCHEMA,
        "version": 1,
        "recordedAtJst": "2026-08-28T15:45:00+09:00",
        "status": "PASS_IDENTITY_BOUND_DIAGNOSTIC_FORCING_NOT_LAUNCH_AUTHORITY",
        "classification": (
            "FIXED_UNCALIBRATED_DIAGNOSTIC_SCENARIO_NOT_OBSERVED_ONGA_MOUTH_"
            "NOT_TODAY_FORECAST"
        ),
        "runCompatibility": {
            "preflightSchema": preflight["schema"],
            "durationModelSeconds": 900,
            "knotCadenceModelSeconds": 60,
            "interpolation": "piecewise_linear_between_manifest_knots",
            "mainGateCapacityByGateId1To8": [0.0] * 8,
            "fishwayDischargeM3S": 0.0,
            "positiveGateMotionPermitted": False,
        },
        "timeline": {
            "modelSeconds": list(MODEL_SECONDS),
            "startClockSecondsWithinRepresentativeDay": START_CLOCK_SECONDS,
            "absoluteDateTimeAssigned": False,
            "timezoneAssigned": False,
        },
        "series": {
            "relativeTideM": tide_values,
            "riverDischargeM3S": river,
        },
        "sourceMeaning": {
            "relativeTide": (
                "mean-removed representative 2026-02-15 JMA Hakata QF "
                "astronomical prediction; secondary diagnostic reference only"
            ),
            "riverDischarge": (
                "constant uncalibrated numerical scenario N=2 O=35 G=1 m3/s; "
                "not observed river discharge"
            ),
            "ongaMouthObservedWaterLevel": False,
            "nearestOfficialOngaMouthPointUsed": False,
            "todayForecast": False,
            "forecastIssueTime": None,
        },
        "bindings": bindings,
        "doesNotAuthorize": [
            "solver_import_or_execution",
            "YODA_connection_or_execution",
            "positive_main_gate_motion",
            "fishway_flow_or_outlet_yore_claim",
            "today_or_future_onga_flow_forecast_claim",
            "physical_validation_mesh_adoption_gui_release_commit_push_or_stage_mutation",
        ],
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(manifest.get("schema") == SCHEMA, "manifest schema changed")
    require(
        manifest.get("status")
        == "PASS_IDENTITY_BOUND_DIAGNOSTIC_FORCING_NOT_LAUNCH_AUTHORITY",
        "manifest status changed",
    )
    compatibility = manifest.get("runCompatibility", {})
    require(
        compatibility.get("durationModelSeconds") == 900
        and compatibility.get("knotCadenceModelSeconds") == 60
        and compatibility.get("mainGateCapacityByGateId1To8") == [0.0] * 8
        and compatibility.get("fishwayDischargeM3S") == 0.0
        and compatibility.get("positiveGateMotionPermitted") is False,
        "run compatibility broadened",
    )
    timeline = manifest.get("timeline", {})
    require(timeline.get("modelSeconds") == list(MODEL_SECONDS), "time axis changed")
    require(
        timeline.get("absoluteDateTimeAssigned") is False
        and timeline.get("timezoneAssigned") is False,
        "diagnostic time was promoted to a dated forecast",
    )
    series = manifest.get("series", {})
    tide = series.get("relativeTideM")
    rivers = series.get("riverDischargeM3S")
    require(isinstance(tide, list) and len(tide) == len(MODEL_SECONDS), "tide shape")
    require(isinstance(rivers, dict), "river series missing")
    require(all(math.isfinite(float(value)) for value in tide), "nonfinite tide")
    for boundary, expected in RIVER_DISCHARGE_M3_S.items():
        values = rivers.get(boundary)
        require(
            isinstance(values, list)
            and len(values) == len(MODEL_SECONDS)
            and all(float(value) == expected for value in values),
            f"river series changed: {boundary}",
        )
    meaning = manifest.get("sourceMeaning", {})
    require(
        meaning.get("ongaMouthObservedWaterLevel") is False
        and meaning.get("nearestOfficialOngaMouthPointUsed") is False
        and meaning.get("todayForecast") is False
        and meaning.get("forecastIssueTime") is None,
        "diagnostic forcing meaning was promoted",
    )
    for row in manifest.get("bindings", []):
        path = ROOT / row["path"]
        require(path.is_file() and not path.is_symlink(), f"binding missing: {path}")
        require(sha256_file(path) == row["sha256"], f"binding drift: {path}")


def atomic_write_new(path: Path, payload: bytes) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    require(not temporary.exists(), f"temporary output exists: {temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.emit and not args.check:
        print(
            canonical_bytes(
                {
                    "schema": SCHEMA,
                    "status": "DISABLED_NO_WRITE",
                    "solverRunCount": 0,
                    "yodaConnectionCount": 0,
                }
            ).decode("utf-8"),
            end="",
        )
        return 0
    expected = build_manifest()
    if args.emit:
        atomic_write_new(OUTPUT, canonical_bytes(expected))
    observed = read_json(OUTPUT) if OUTPUT.exists() else expected
    validate_manifest(observed)
    require(canonical_bytes(observed) == canonical_bytes(expected), "artifact not canonical expected output")
    print(
        canonical_bytes(
            {
                "schema": SCHEMA,
                "status": "PASS",
                "outputPath": str(OUTPUT.relative_to(ROOT)),
                "outputSha256": sha256_bytes(canonical_bytes(observed)),
                "solverRunCount": 0,
                "yodaConnectionCount": 0,
            }
        ).decode("utf-8"),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
