#!/usr/bin/env python3
"""Run six downstream-only diagnostic scenarios and retain 37 hourly states.

The barrage release is represented by the already-canary-tested one-way
external downstream mass-and-momentum source.  No water is borrowed from the
excluded upstream component.  Six independent CPU workers run in parallel;
any worker failure stops the batch and there is no retry.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_downstream_external_high_large_7200s_runner_v1 as canary
import stage20_downstream_external_inflow_adapter_v1 as external_adapter
import stage20_downstream_external_wet_dry_boundary_adapter_v1 as wet_dry_boundary_adapter


VERSION = "stage20-downstream-external-six-scenario-37-snapshot-runner-v1"
SCHEMA = "onga-stage20-downstream-external-six-scenario-37-snapshot-runner-v1-contract"
AUTHORIZED_ID = "stage20-downstream-external-six-scenario-37-snapshot-yoda-20260902-04"
AUTHORIZED_RUN_ID = "batch-stage20-downstream-external-six-scenario-37-snapshot-20260902-v4"
CONTRACT_PATH = ROOT / "config/stage20_downstream_external_six_scenario_37_snapshot_runner_v1.json"
ACTIVATION_PATH = ROOT / "config/stage20_downstream_external_six_scenario_37_snapshot_activation_20260902_v2.json"
INPUT_PATH = ROOT / "config/stage20_downstream_external_six_scenario_37_snapshot_input_v1.json"
SCENARIO_IDS = (
    "release-low_tide-small",
    "release-low_tide-large",
    "release-reference_tide-small",
    "release-reference_tide-large",
    "release-high_tide-small",
    "release-high_tide-large",
)
FULL_SECONDS = 36.0 * 3600.0
SNAPSHOT_COUNT = 37
CELL_COUNT = 28746
DOWNSTREAM_CELL_COUNT = 24250
PARALLEL_WORKER_COUNT = 6
MAXIMUM_WORKER_WALL_SECONDS = 32_400.0
MAXIMUM_BATCH_WALL_SECONDS = 36_000.0
MAXIMUM_ACCEPTED_STEPS_PER_WORKER = 20_000_000
MASS_BALANCE_THRESHOLD = 1.0e-10
SOURCE_RESIDUAL_RELATIVE_THRESHOLD = 1.0e-10
COMMANDED_SOURCE_RESIDUAL_RELATIVE_THRESHOLD = 1.0e-13
SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ACTIVE_WORKERS: dict[str, subprocess.Popen[Any]] = {}


class ExternalBatchStop(RuntimeError):
    """A deliberate fail-closed batch stop."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExternalBatchStop(f"[{VERSION}] {message}")


def _binding(contract: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [item for item in contract["bindings"] if item.get("role") == role]
    require(len(matches) == 1, f"binding role is not unique: {role}")
    return matches[0]


def validate_contract(contract: dict[str, Any]) -> None:
    require(contract.get("schema") == SCHEMA, "contract schema changed")
    require(contract.get("version") == 1, "contract version changed")
    require(
        contract.get("status") == "READY_PREPARE_ONLY_EXTERNAL_BATCH_ACTIVATION_REQUIRED",
        "contract status changed",
    )
    require(
        contract.get("classification")
        == "DIAGNOSTIC_EXTERNAL_DOWNSTREAM_INFLOW_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
        "classification changed",
    )
    scope = contract.get("scope", {})
    require(tuple(scope.get("scenarioIds", [])) == SCENARIO_IDS, "scenario set changed")
    require(scope.get("durationModelSeconds") == 129600, "duration changed")
    require(scope.get("hourlySnapshotCount") == SNAPSHOT_COUNT, "snapshot count changed")
    require(scope.get("parallelWorkerCount") == PARALLEL_WORKER_COUNT, "worker count changed")
    require(scope.get("cellCount") == CELL_COUNT, "cell count changed")
    require(scope.get("downstreamCellCount") == DOWNSTREAM_CELL_COUNT, "downstream count changed")
    require(scope.get("usesUpstreamDonorVolume") is False, "upstream donor was re-enabled")
    require(scope.get("reverseFlowPermitted") is False, "reverse flow was enabled")
    require(scope.get("consolidatedSnapshotOnly") is True, "snapshot storage changed")
    require(
        scope.get("riverBoundaryDryFacePolicy")
        == "INDIVIDUAL_DRY_FACE_AS_WALL_WET_SECTION_CARRIES_DISCHARGE",
        "river boundary dry-face policy changed",
    )
    runtime = contract.get("runtime", {})
    require(runtime.get("requiredHostname") == "yoda", "target host changed")
    require(runtime.get("automaticRetryCount") == 0, "automatic retry enabled")
    require(
        runtime.get("maximumWorkerWallSeconds") == int(MAXIMUM_WORKER_WALL_SECONDS),
        "worker wall guard changed",
    )
    require(
        runtime.get("maximumBatchWallSeconds") == int(MAXIMUM_BATCH_WALL_SECONDS),
        "batch wall guard changed",
    )
    require(
        runtime.get("maximumAcceptedStepCountPerWorker")
        == MAXIMUM_ACCEPTED_STEPS_PER_WORKER,
        "accepted-step guard changed",
    )
    require(
        runtime.get("requiredActivationPath") == str(ACTIVATION_PATH.relative_to(ROOT)),
        "activation path changed",
    )
    require(
        runtime.get("executeWithoutActivation")
        == "FAIL_BEFORE_CONTEXT_LOAD_KERNEL_CALL_OR_OUTPUT_CREATION",
        "missing-activation behavior changed",
    )
    acceptance = contract.get("acceptance", {})
    require(
        acceptance.get("maximumRelativeMassBalanceError") == MASS_BALANCE_THRESHOLD,
        "mass balance threshold changed",
    )
    require(
        acceptance.get("massBalanceGuardPrecision") == "LONG_DOUBLE",
        "mass balance guard precision changed",
    )
    require(
        acceptance.get("float64MassBalanceErrorTreatment") == "DIAGNOSTIC_ONLY",
        "float64 mass error became an acceptance guard",
    )
    require(
        acceptance.get("maximumSourceResidualRelative")
        == SOURCE_RESIDUAL_RELATIVE_THRESHOLD,
        "source residual relative threshold changed",
    )
    require(
        acceptance.get("maximumCommandedSourceResidualRelative")
        == COMMANDED_SOURCE_RESIDUAL_RELATIVE_THRESHOLD,
        "commanded source residual relative threshold changed",
    )
    require(
        acceptance.get("absoluteSourceResidualTreatment") == "DIAGNOSTIC_ONLY",
        "absolute source residual became an acceptance guard",
    )
    bindings = contract.get("bindings")
    require(isinstance(bindings, list) and len(bindings) >= 15, "bindings are incomplete")
    seen: set[str] = set()
    for item in bindings:
        path = item.get("path")
        digest = item.get("sha256")
        require(isinstance(path, str) and path not in seen, f"duplicate binding: {path}")
        require(
            isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None,
            f"invalid binding SHA: {path}",
        )
        seen.add(path)
    for role in (
        "runner",
        "target_test",
        "scenario_input",
        "external_inflow_adapter",
        "external_inflow_adapter_test",
        "wet_dry_boundary_adapter",
        "wet_dry_boundary_adapter_test",
        "proven_canary_runner",
        "proven_canary_contract",
        "proven_canary_input",
        "matched_runner",
        "matched_contract",
        "same_pass_limiter_kernel",
        "candidate_mesh",
        "candidate_fields",
    ):
        _binding(contract, role)


def verified_contract() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = canary.read_json(CONTRACT_PATH)
    validate_contract(contract)
    verified: list[dict[str, Any]] = []
    for item in contract["bindings"]:
        path = ROOT / item["path"]
        require(path.is_file() and not path.is_symlink(), f"binding is missing: {item['path']}")
        require(canary.sha256_file(path) == item["sha256"], f"binding SHA changed: {item['path']}")
        verified.append(item)
    return contract, verified


def load_scenarios() -> dict[str, dict[str, Any]]:
    document = canary.read_json(INPUT_PATH)
    require(
        document.get("schema")
        == "onga-stage20-downstream-external-six-scenario-37-snapshot-input-v1",
        "input schema changed",
    )
    require(document.get("currentConditionReferenceAllowed") is False, "input was promoted")
    require(document.get("usesUpstreamDonorVolume") is False, "input enables upstream donor")
    require(document.get("reverseFlowPermitted") is False, "input enables reverse flow")
    offsets = np.asarray(document.get("coverage", {}).get("snapshotOffsetsHours"), dtype=np.float64)
    require(offsets.shape == (SNAPSHOT_COUNT,), "hour-offset count changed")
    require(bool(np.array_equal(offsets, np.arange(-12.0, 25.0))), "hour offsets changed")
    release_by_id = {
        item.get("id"): float(item.get("barrageReleaseM3S", -1.0))
        for item in document.get("releaseBands", [])
    }
    require(release_by_id == {"low": 0.1, "reference": 24.5, "high": 73.0}, "release bands changed")
    tide_by_id: dict[str, dict[str, Any]] = {}
    for item in document.get("tideRanges", []):
        values = np.asarray(item.get("astronomicalTideHeightMByOffset"), dtype=np.float64)
        require(values.shape == (SNAPSHOT_COUNT,), f"tide count changed: {item.get('id')}")
        require(bool(np.isfinite(values).all()), f"tide is nonfinite: {item.get('id')}")
        tide_by_id[str(item.get("id"))] = item
    require(set(tide_by_id) == {"small", "large"}, "tide ranges changed")

    raw_scenarios = document.get("scenarios", [])
    require(tuple(item.get("id") for item in raw_scenarios) == SCENARIO_IDS, "scenario order changed")
    scenarios: dict[str, dict[str, Any]] = {}
    pairs: set[tuple[str, str]] = set()
    for item in raw_scenarios:
        scenario_id = str(item.get("id"))
        release_band = str(item.get("releaseBand"))
        tide_range = str(item.get("tideRangeClass"))
        require(release_band in release_by_id and tide_range in tide_by_id, f"unknown input class: {scenario_id}")
        pairs.add((release_band, tide_range))
        scenarios[scenario_id] = {
            "id": scenario_id,
            "releaseBand": release_band,
            "tideRangeClass": tide_range,
            "currentConditionReferenceAllowed": False,
            "boundaryInputs": {
                "barrageReleaseM3S": release_by_id[release_band],
                "snapshotOffsetsHours": offsets.astype(np.int64).tolist(),
                "astronomicalTideHeightMByOffset": list(
                    tide_by_id[tide_range]["astronomicalTideHeightMByOffset"]
                ),
                "tideStationCode": tide_by_id[tide_range]["tideStationCode"],
                "tideCenterTimeJst": tide_by_id[tide_range]["representativeCenterTimeJst"],
            },
        }
    require(len(pairs) == 6 and len(scenarios) == 6, "six-condition matrix is incomplete")
    return scenarios


def tide_at(scenario: dict[str, Any], model_seconds: float) -> float:
    values = np.asarray(
        scenario["boundaryInputs"]["astronomicalTideHeightMByOffset"],
        dtype=np.float64,
    )
    return float(np.interp(model_seconds, np.arange(SNAPSHOT_COUNT) * 3600.0, values))


def build_discharge(geometry: dict[str, np.ndarray]) -> np.ndarray:
    return canary.build_discharge(geometry)


def load_context() -> dict[str, Any]:
    context = canary.load_context()
    layout = context["externalLayout"]
    require(layout["downstreamCellCount"] == DOWNSTREAM_CELL_COUNT, "downstream count changed")
    require(layout["upstreamExcludedCellCount"] == 4496, "upstream exclusion changed")
    require(layout["usesUpstreamDonorVolume"] is False, "external layout gained upstream donor")
    return context


def condition_snapshot(
    state: np.ndarray,
    context: dict[str, Any],
    release_m3_s: float,
) -> dict[str, float]:
    return {
        "barrageInflowM3S": float(release_m3_s),
        "barrageReleaseM3S": float(release_m3_s),
        "barrageUpstreamLevelM": canary._weighted_eta(
            state,
            context["bed"],
            context["upstreamLevelReferenceM2"],
        ),
        "barrageDownstreamLevelM": canary._weighted_eta(
            state,
            context["bed"],
            context["downstreamLevelReferenceM2"],
        ),
    }


def require_external_source_conservation(
    external: dict[str, Any],
    release_m3_s: float,
) -> None:
    """Apply one consistent relative guard plus a strict command guard."""

    release = float(release_m3_s)
    scale = max(release, 1.0)
    requested = float(external["requestedReleaseM3S"])
    effective = float(external["effectiveReleaseM3S"])
    residual = float(external["sourceResidualM3S"])
    relative_residual = float(external["sourceResidualRelative"])
    commanded_residual = float(external["commandedSourceResidualM3S"])
    commanded_relative_residual = float(
        external["commandedSourceResidualRelative"]
    )
    require(
        all(
            math.isfinite(value)
            for value in (
                release,
                requested,
                effective,
                residual,
                relative_residual,
                commanded_residual,
                commanded_relative_residual,
            )
        ),
        "external source conservation telemetry is nonfinite",
    )
    require(
        math.isclose(requested, release, rel_tol=0.0, abs_tol=0.0),
        "external release request changed",
    )
    require(
        math.isclose(
            effective - release,
            residual,
            rel_tol=0.0,
            abs_tol=np.finfo(np.float64).eps * scale,
        ),
        "external source residual telemetry is inconsistent",
    )
    require(
        math.isclose(
            relative_residual,
            residual / scale,
            rel_tol=1.0e-12,
            abs_tol=1.0e-18,
        ),
        "external source relative residual telemetry is inconsistent",
    )
    require(
        math.isclose(
            commanded_relative_residual,
            commanded_residual / scale,
            rel_tol=1.0e-12,
            abs_tol=1.0e-18,
        ),
        "commanded source relative residual telemetry is inconsistent",
    )
    require(
        abs(commanded_relative_residual)
        <= COMMANDED_SOURCE_RESIDUAL_RELATIVE_THRESHOLD,
        "commanded external source is not conservative",
    )
    require(
        abs(relative_residual) <= SOURCE_RESIDUAL_RELATIVE_THRESHOLD,
        "external source is not conservative",
    )


def advance_once(
    state: np.ndarray,
    context: dict[str, Any],
    scenario: dict[str, Any],
    model_seconds: float,
    maximum_dt_s: float,
) -> tuple[Any, dict[str, Any]]:
    canary._require_closed(context)
    geometry = context["geometry"]
    kernel = context["kernel"]
    zeros = np.zeros(CELL_COUNT, dtype=np.float64)
    release_m3_s = float(scenario["boundaryInputs"]["barrageReleaseM3S"])
    target_discharge = build_discharge(geometry)
    river_boundary = wet_dry_boundary_adapter.build_safe_boundary_tags(
        state,
        geometry["boundaryCells"],
        geometry["boundaryLengths"],
        geometry["boundaryTags"],
        target_discharge,
    )
    step = kernel.advance_h2_step_depth_weighted_boundary_with_trace_v1(
        state,
        context["bed"],
        context["manning"],
        geometry["areas"],
        geometry["inverseAreas"],
        geometry["left"],
        geometry["right"],
        geometry["internalLengths"],
        geometry["internalNormals"],
        context["multipliers"],
        geometry["boundaryCells"],
        geometry["boundaryLengths"],
        geometry["boundaryNormals"],
        river_boundary["boundaryTags"],
        tide_at(scenario, model_seconds),
        target_discharge,
        zeros,
        zeros,
        0.0,
        0.12,
        maximum_dt_s,
    )
    external = external_adapter.apply_external_inflow(
        step.next_state,
        geometry["areas"],
        context["externalLayout"],
        release_m3_s,
        float(step.accepted_dt_s),
        minimum_flow_depth_m=0.05,
        maximum_inflow_velocity_m_s=5.0,
    )
    require_external_source_conservation(external, release_m3_s)
    require(external["upstreamStateChanged"] is False, "external source changed upstream state")
    external["riverBoundaryWetFaceCountByTag"] = river_boundary["wetFaceCountByTag"]
    external["riverBoundaryDryFaceCountByTag"] = river_boundary["dryFaceCountByTag"]
    external["riverBoundaryWetDepthLengthM2ByTag"] = river_boundary["wetDepthLengthM2ByTag"]
    return step, external


def mass_balance_errors(
    state: np.ndarray,
    areas_float64: np.ndarray,
    areas_longdouble: np.ndarray,
    *,
    initial_volume_float64: float,
    initial_volume_longdouble: np.longdouble,
    expected_volume_float64: float,
    expected_volume_longdouble: np.longdouble,
) -> dict[str, float]:
    actual_volume_float64 = float(np.sum(state[:, 0] * areas_float64))
    actual_volume_longdouble = np.sum(
        state[:, 0].astype(np.longdouble) * areas_longdouble,
        dtype=np.longdouble,
    )
    relative_float64 = abs(actual_volume_float64 - expected_volume_float64) / max(
        abs(initial_volume_float64),
        1.0,
    )
    relative_longdouble = abs(actual_volume_longdouble - expected_volume_longdouble) / max(
        abs(initial_volume_longdouble),
        np.longdouble(1.0),
    )
    return {
        "relativeMassBalanceErrorLongDouble": float(relative_longdouble),
        "relativeMassBalanceErrorFloat64Diagnostic": float(relative_float64),
    }


def run_local_matrix_one_step() -> dict[str, Any]:
    verified_contract()
    scenarios = load_scenarios()
    context = load_context()
    areas = np.asarray(context["geometry"]["areas"], dtype=np.float64)
    areas_longdouble = areas.astype(np.longdouble)
    initial_state = np.asarray(context["state"], dtype=np.float64)
    initial_volume_float64 = float(np.sum(initial_state[:, 0] * areas))
    initial_volume_longdouble = np.sum(
        initial_state[:, 0].astype(np.longdouble) * areas_longdouble,
        dtype=np.longdouble,
    )
    rows: list[dict[str, Any]] = []
    for scenario_id in SCENARIO_IDS:
        scenario = scenarios[scenario_id]
        step, external = advance_once(initial_state, context, scenario, 0.0, 0.05)
        next_state = np.asarray(external["nextState"], dtype=np.float64)
        expected_volume_float64 = (
            initial_volume_float64
            - float(step.accepted_dt_s) * float(step.boundary_outflow_m3_s)
            + float(external["addedVolumeM3"])
        )
        expected_volume_longdouble = (
            initial_volume_longdouble
            - np.longdouble(step.accepted_dt_s) * np.longdouble(step.boundary_outflow_m3_s)
            + np.longdouble(external["addedVolumeM3"])
        )
        mass_errors = mass_balance_errors(
            next_state,
            areas,
            areas_longdouble,
            initial_volume_float64=initial_volume_float64,
            initial_volume_longdouble=initial_volume_longdouble,
            expected_volume_float64=expected_volume_float64,
            expected_volume_longdouble=expected_volume_longdouble,
        )
        require(
            mass_errors["relativeMassBalanceErrorLongDouble"] <= MASS_BALANCE_THRESHOLD,
            f"one-step long-double mass guard failed: {scenario_id}",
        )
        require(bool(np.isfinite(next_state).all()), f"nonfinite one-step state: {scenario_id}")
        require(bool(np.all(next_state[:, 0] >= 0.0)), f"negative one-step depth: {scenario_id}")
        rows.append({
            "scenarioId": scenario_id,
            "releaseM3S": scenario["boundaryInputs"]["barrageReleaseM3S"],
            "initialTideM": tide_at(scenario, 0.0),
            "effectiveReleaseM3S": external["effectiveReleaseM3S"],
            "inflowVelocityMPS": external["inflowVelocityMPS"],
            "relativeMassBalanceError": mass_errors["relativeMassBalanceErrorLongDouble"],
            "relativeMassBalanceErrorFloat64Diagnostic": mass_errors[
                "relativeMassBalanceErrorFloat64Diagnostic"
            ],
            "massBalanceGuardPrecision": "LONG_DOUBLE",
            "upstreamStateChangedBySource": external["upstreamStateChanged"],
            "riverBoundaryDryFaceCountByTag": external[
                "riverBoundaryDryFaceCountByTag"
            ].tolist(),
        })
    return {
        "status": "PASS_LOCAL_SIX_SCENARIO_ONE_STEP_EXTERNAL_MATRIX",
        "scenarioCount": len(rows),
        "rows": rows,
        "negativeDepthCount": 0,
        "nonFiniteValueCount": 0,
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
    }


def build_preflight() -> dict[str, Any]:
    contract, bindings = verified_contract()
    scenarios = load_scenarios()
    return {
        "schema": "onga-stage20-downstream-external-six-scenario-37-snapshot-preflight-v1",
        "status": "PASS_PREPARE_ONLY_BATCH_BLOCKED_PENDING_ACTIVATION",
        "launchPermitted": False,
        "activationPresent": ACTIVATION_PATH.is_file(),
        "allBindingsVerified": True,
        "bindingCount": len(bindings),
        "scenarioCount": len(scenarios),
        "durationModelSeconds": contract["scope"]["durationModelSeconds"],
        "hourlySnapshotCount": contract["scope"]["hourlySnapshotCount"],
        "parallelWorkerCount": contract["scope"]["parallelWorkerCount"],
        "massBalanceGuardPrecision": contract["acceptance"]["massBalanceGuardPrecision"],
        "float64MassBalanceErrorTreatment": contract["acceptance"][
            "float64MassBalanceErrorTreatment"
        ],
        "maximumSourceResidualRelative": contract["acceptance"][
            "maximumSourceResidualRelative"
        ],
        "maximumCommandedSourceResidualRelative": contract["acceptance"][
            "maximumCommandedSourceResidualRelative"
        ],
        "absoluteSourceResidualTreatment": contract["acceptance"][
            "absoluteSourceResidualTreatment"
        ],
        "riverBoundaryDryFacePolicy": contract["scope"]["riverBoundaryDryFacePolicy"],
        "automaticRetryCount": 0,
    }


def _parse_utc(value: Any, field: str) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"), f"{field} is not UTC")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    require(parsed.tzinfo is not None, f"{field} is timezone-naive")
    return parsed.astimezone(timezone.utc)


def validate_activation(activation: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    contract, _ = verified_contract()
    require(
        activation.get("schema")
        == "onga-stage20-downstream-external-six-scenario-37-snapshot-single-use-activation-v1",
        "activation schema changed",
    )
    require(activation.get("status") == "AUTHORIZED", "activation is not authorized")
    require(activation.get("mode") == "EXECUTE_DIAGNOSTIC_BATCH_ONCE", "activation mode changed")
    require(
        activation.get("authorizationId") == AUTHORIZED_ID,
        "authorization id changed",
    )
    require(
        activation.get("runId") == AUTHORIZED_RUN_ID,
        "run id changed",
    )
    require(activation.get("requiredHostname") == "yoda", "activation host changed")
    require(activation.get("maximumUseCount") == 1 and activation.get("retryCount") == 0, "single-use/no-retry changed")
    require(tuple(activation.get("scenarioIds", [])) == SCENARIO_IDS, "activation scenarios changed")
    require(activation.get("durationModelSeconds") == 129600, "activation duration changed")
    require(activation.get("snapshotCountPerScenario") == SNAPSHOT_COUNT, "activation snapshot count changed")
    require(activation.get("parallelWorkerCount") == PARALLEL_WORKER_COUNT, "activation worker count changed")
    require(activation.get("runnerSha256") == canary.sha256_file(Path(__file__).resolve()), "runner SHA changed")
    require(activation.get("contractSha256") == canary.sha256_file(CONTRACT_PATH), "contract SHA changed")
    require(activation.get("scenarioInputSha256") == canary.sha256_file(INPUT_PATH), "input SHA changed")
    require(
        activation.get("externalAdapterSha256")
        == canary.sha256_file(Path(external_adapter.__file__).resolve()),
        "external adapter SHA changed",
    )
    require(
        activation.get("wetDryBoundaryAdapterSha256")
        == canary.sha256_file(Path(wet_dry_boundary_adapter.__file__).resolve()),
        "wet/dry boundary adapter SHA changed",
    )
    require(
        activation.get("provenCanaryRunnerSha256")
        == canary.sha256_file(Path(canary.__file__).resolve()),
        "proven canary runner SHA changed",
    )
    now = datetime.now(timezone.utc)
    require(_parse_utc(activation.get("notBefore"), "notBefore") <= now, "activation is not active")
    require(now <= _parse_utc(activation.get("expiresAt"), "expiresAt"), "activation expired")
    output_relative = activation.get("outputRelativePath")
    expected = f"{contract['runtime']['outputBase']}/{activation['runId']}"
    require(output_relative == expected, "output path changed")
    relative = Path(str(output_relative))
    require(not relative.is_absolute() and ".." not in relative.parts, "output escapes package")
    return contract, ROOT / relative


def _atomic_savez_new(path: Path, **arrays: np.ndarray) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing to overwrite {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp.npz")
    require(not temporary.exists(), "temporary snapshot path exists")
    np.savez(temporary, **arrays)
    os.replace(temporary, path)


def _require_output_in_package(path: Path) -> None:
    resolved_root = ROOT.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ExternalBatchStop(f"[{VERSION}] worker output escapes package") from exc


def _run_scenario(scenario_id: str, output_text: str) -> int:
    require(socket.gethostname().lower() == "yoda", "worker host is not yoda")
    require(ACTIVATION_PATH.is_file() and not ACTIVATION_PATH.is_symlink(), "activation is missing")
    validate_activation(canary.read_json(ACTIVATION_PATH))
    scenarios = load_scenarios()
    require(scenario_id in scenarios, "worker scenario is not authorized")
    output = Path(output_text)
    require(output.is_absolute(), "worker output is not absolute")
    _require_output_in_package(output)
    require(not output.exists() and not output.is_symlink(), "worker output is not fresh")
    output.mkdir(parents=True, mode=0o700)

    scenario = scenarios[scenario_id]
    release_m3_s = float(scenario["boundaryInputs"]["barrageReleaseM3S"])
    context = load_context()
    geometry = context["geometry"]
    output_mask = np.asarray(context["externalLayout"]["downstreamOutputCellMask"], dtype=np.uint8).astype(bool)
    downstream_ids = np.flatnonzero(output_mask).astype(np.int64)
    require(len(downstream_ids) == DOWNSTREAM_CELL_COUNT, "worker downstream count changed")
    state = np.asarray(context["state"], dtype=np.float64).copy()
    areas = np.asarray(geometry["areas"], dtype=np.float64)
    areas_longdouble = areas.astype(np.longdouble)
    initial_volume_float64 = float(np.sum(state[:, 0] * areas))
    initial_volume_longdouble = np.sum(
        state[:, 0].astype(np.longdouble) * areas_longdouble,
        dtype=np.longdouble,
    )
    expected_volume_float64 = initial_volume_float64
    expected_volume_longdouble = initial_volume_longdouble
    model_seconds = 0.0
    accepted_steps = 0
    maximum_cfl = 0.0
    maximum_mass_error_longdouble = 0.0
    maximum_mass_error_float64_diagnostic = 0.0
    maximum_source_residual = 0.0
    maximum_source_residual_relative = 0.0
    maximum_commanded_source_residual_relative = 0.0
    minimum_inflow_velocity = math.inf
    maximum_inflow_velocity = -math.inf
    maximum_dry_river_faces_by_tag = np.zeros(5, dtype=np.int64)
    minimum_wet_river_faces_by_tag = np.zeros(5, dtype=np.int64)
    minimum_wet_river_faces_by_tag[2:] = np.iinfo(np.int64).max
    next_safety_check = 600.0
    next_snapshot = 3600.0
    snapshot_times = [0.0]
    snapshot_states = [state[output_mask].copy()]
    snapshot_conditions = [condition_snapshot(state, context, release_m3_s)]
    wall_started = time.monotonic()

    canary.atomic_write_new(
        output / "start-receipt.json",
        canary.canonical_bytes({
            "schema": "onga-stage20-downstream-external-scenario-start-v1",
            "status": "STARTED_DIAGNOSTIC_NO_RETRY",
            "scenarioId": scenario_id,
            "durationModelSeconds": FULL_SECONDS,
            "processId": os.getpid(),
            "startedAtUtc": datetime.now(timezone.utc).isoformat(),
        }),
    )
    try:
        while model_seconds < FULL_SECONDS - 1.0e-12:
            require(
                time.monotonic() - wall_started <= MAXIMUM_WORKER_WALL_SECONDS,
                "worker wall-time limit exceeded",
            )
            require(
                accepted_steps < MAXIMUM_ACCEPTED_STEPS_PER_WORKER,
                "worker accepted-step limit exceeded",
            )
            maximum_dt = min(0.05, FULL_SECONDS - model_seconds, next_snapshot - model_seconds)
            require(maximum_dt > 0.0, "nonpositive worker time step")
            step, external = advance_once(state, context, scenario, model_seconds, maximum_dt)
            dt = float(step.accepted_dt_s)
            state = np.asarray(external["nextState"], dtype=np.float64)
            model_seconds += dt
            accepted_steps += 1
            expected_volume_float64 -= dt * float(step.boundary_outflow_m3_s)
            expected_volume_float64 += float(external["addedVolumeM3"])
            expected_volume_longdouble -= np.longdouble(dt) * np.longdouble(step.boundary_outflow_m3_s)
            expected_volume_longdouble += np.longdouble(external["addedVolumeM3"])
            maximum_cfl = max(maximum_cfl, float(step.maximum_cfl))
            maximum_source_residual = max(
                maximum_source_residual,
                abs(float(external["sourceResidualM3S"])),
            )
            maximum_source_residual_relative = max(
                maximum_source_residual_relative,
                abs(float(external["sourceResidualRelative"])),
            )
            maximum_commanded_source_residual_relative = max(
                maximum_commanded_source_residual_relative,
                abs(float(external["commandedSourceResidualRelative"])),
            )
            minimum_inflow_velocity = min(minimum_inflow_velocity, float(external["inflowVelocityMPS"]))
            maximum_inflow_velocity = max(maximum_inflow_velocity, float(external["inflowVelocityMPS"]))
            dry_faces = np.asarray(external["riverBoundaryDryFaceCountByTag"], dtype=np.int64)
            wet_faces = np.asarray(external["riverBoundaryWetFaceCountByTag"], dtype=np.int64)
            maximum_dry_river_faces_by_tag = np.maximum(
                maximum_dry_river_faces_by_tag,
                dry_faces,
            )
            for tag in (2, 3, 4):
                minimum_wet_river_faces_by_tag[tag] = min(
                    minimum_wet_river_faces_by_tag[tag],
                    wet_faces[tag],
                )
            if model_seconds >= next_safety_check - 1.0e-9 or model_seconds >= FULL_SECONDS - 1.0e-9:
                require(bool(np.isfinite(state).all()), "nonfinite state")
                require(bool(np.all(state[:, 0] >= 0.0)), "negative depth")
                mass_errors = mass_balance_errors(
                    state,
                    areas,
                    areas_longdouble,
                    initial_volume_float64=initial_volume_float64,
                    initial_volume_longdouble=initial_volume_longdouble,
                    expected_volume_float64=expected_volume_float64,
                    expected_volume_longdouble=expected_volume_longdouble,
                )
                maximum_mass_error_longdouble = max(
                    maximum_mass_error_longdouble,
                    mass_errors["relativeMassBalanceErrorLongDouble"],
                )
                maximum_mass_error_float64_diagnostic = max(
                    maximum_mass_error_float64_diagnostic,
                    mass_errors["relativeMassBalanceErrorFloat64Diagnostic"],
                )
                require(
                    mass_errors["relativeMassBalanceErrorLongDouble"] <= MASS_BALANCE_THRESHOLD,
                    "long-double mass balance guard failed",
                )
                next_safety_check += 600.0
            if model_seconds >= next_snapshot - 1.0e-9:
                snapshot_times.append(model_seconds)
                snapshot_states.append(state[output_mask].copy())
                snapshot_conditions.append(condition_snapshot(state, context, release_m3_s))
                next_snapshot += 3600.0

        require(len(snapshot_states) == SNAPSHOT_COUNT, "snapshot count changed")
        expected_times = np.arange(SNAPSHOT_COUNT, dtype=np.float64) * 3600.0
        require(bool(np.allclose(snapshot_times, expected_times, rtol=0.0, atol=1.0e-8)), "snapshot times changed")
        require(math.isclose(model_seconds, FULL_SECONDS, abs_tol=1.0e-8), "duration changed")
        result = {
            "schema": "onga-stage20-downstream-external-scenario-result-v1",
            "status": "PASS_NUMERICAL_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
            "scenarioId": scenario_id,
            "durationModelSeconds": model_seconds,
            "snapshotCount": len(snapshot_states),
            "acceptedSteps": accepted_steps,
            "wallSeconds": time.monotonic() - wall_started,
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error_longdouble,
            "maximumRelativeMassBalanceErrorFloat64Diagnostic": (
                maximum_mass_error_float64_diagnostic
            ),
            "massBalanceGuardPrecision": "LONG_DOUBLE",
            "maximumSourceResidualM3S": maximum_source_residual,
            "maximumSourceResidualRelative": maximum_source_residual_relative,
            "maximumCommandedSourceResidualRelative": (
                maximum_commanded_source_residual_relative
            ),
            "absoluteSourceResidualTreatment": "DIAGNOSTIC_ONLY",
            "minimumInflowVelocityMPS": minimum_inflow_velocity,
            "maximumInflowVelocityMPS": maximum_inflow_velocity,
            "maximumDryRiverBoundaryFaceCountByTag": maximum_dry_river_faces_by_tag.tolist(),
            "minimumWetRiverBoundaryFaceCountByTag": minimum_wet_river_faces_by_tag.tolist(),
            "riverBoundaryDryFacePolicy": (
                "INDIVIDUAL_DRY_FACE_AS_WALL_WET_SECTION_CARRIES_DISCHARGE"
            ),
            "requestedReleaseM3S": release_m3_s,
            "effectiveReleaseM3S": release_m3_s,
            "negativeDepthCount": int(np.sum(state[:, 0] < 0.0)),
            "nonFiniteValueCount": int(state.size - np.count_nonzero(np.isfinite(state))),
            "downstreamCellCount": len(downstream_ids),
            "upstreamExcludedCellCount": int(np.sum(~output_mask)),
            "usesUpstreamDonorVolume": False,
            "reverseFlowPermitted": False,
            "forecastProvided": False,
            "catchProbabilityProvided": False,
        }
        _atomic_savez_new(
            output / "hourly-downstream-state.npz",
            model_seconds=np.asarray(snapshot_times, dtype=np.float64),
            snapshot_offsets_hours=np.arange(-12, 25, dtype=np.int64),
            downstream_cell_ids=downstream_ids,
            state=np.asarray(snapshot_states, dtype=np.float64),
        )
        canary.atomic_write_new(output / "result.json", canary.canonical_bytes(result))
        canary.atomic_write_new(
            output / "conditions-by-snapshot.json",
            canary.canonical_bytes({
                "schema": "onga-stage20-downstream-external-scenario-conditions-v1",
                "scenarioId": scenario_id,
                "snapshotOffsetsHours": list(range(-12, 25)),
                "modelSeconds": snapshot_times,
                "conditionsBySnapshot": snapshot_conditions,
            }),
        )
        canary.atomic_write_new(
            output / "completion-receipt.json",
            canary.canonical_bytes({
                "schema": "onga-stage20-downstream-external-scenario-completion-v1",
                "status": result["status"],
                "scenarioId": scenario_id,
                "resultSha256": canary.sha256_file(output / "result.json"),
                "snapshotSha256": canary.sha256_file(output / "hourly-downstream-state.npz"),
                "conditionsSha256": canary.sha256_file(output / "conditions-by-snapshot.json"),
            }),
        )
        return 0
    except BaseException as exc:
        failure = output / "failure-receipt.json"
        if not failure.exists():
            canary.atomic_write_new(
                failure,
                canary.canonical_bytes({
                    "schema": "onga-stage20-downstream-external-scenario-failure-v1",
                    "status": "FAILED_NO_RETRY",
                    "scenarioId": scenario_id,
                    "durationModelSeconds": FULL_SECONDS,
                    "modelSeconds": model_seconds,
                    "acceptedSteps": accepted_steps,
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                }),
            )
        raise


def _terminate_active_workers() -> None:
    for process in list(_ACTIVE_WORKERS.values()):
        if process.poll() is None:
            process.terminate()


def _termination_handler(signum: int, _frame: Any) -> None:
    _terminate_active_workers()
    raise ExternalBatchStop(f"[{VERSION}] termination signal received: {signum}")


def _run_parallel_batch(batch_output: Path) -> list[dict[str, Any]]:
    scenario_root = batch_output / "scenarios"
    scenario_root.mkdir(mode=0o700)
    processes: dict[str, tuple[subprocess.Popen[Any], Any]] = {}
    failed: tuple[str, int] | None = None
    try:
        for scenario_id in SCENARIO_IDS:
            output = scenario_root / scenario_id
            log = (scenario_root / f"{scenario_id}.log").open("xb")
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--scenario",
                scenario_id,
                "--output",
                str(output),
            ]
            environment = dict(os.environ)
            environment.update({
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "NUMBA_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            })
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)
            processes[scenario_id] = (process, log)
            _ACTIVE_WORKERS[scenario_id] = process
        while processes:
            for scenario_id, (process, log) in list(processes.items()):
                code = process.poll()
                if code is None:
                    continue
                log.close()
                del processes[scenario_id]
                _ACTIVE_WORKERS.pop(scenario_id, None)
                if code != 0 and failed is None:
                    failed = (scenario_id, code)
                    _terminate_active_workers()
            if processes:
                time.sleep(5.0)
        require(failed is None, f"scenario worker failed without retry: {failed}")
    finally:
        _terminate_active_workers()
        for scenario_id, (process, log) in list(processes.items()):
            try:
                process.wait(timeout=30.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10.0)
            if not log.closed:
                log.close()
            _ACTIVE_WORKERS.pop(scenario_id, None)

    results: list[dict[str, Any]] = []
    for scenario_id in SCENARIO_IDS:
        result_path = scenario_root / scenario_id / "result.json"
        require(result_path.is_file(), f"missing result: {scenario_id}")
        result = canary.read_json(result_path)
        require(
            result.get("status")
            == "PASS_NUMERICAL_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
            f"non-pass result: {scenario_id}",
        )
        require(result.get("snapshotCount") == SNAPSHOT_COUNT, f"snapshot count failed: {scenario_id}")
        results.append(result)
    return results


def _recursive_manifest(root: Path, run_id: str) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "manifest.json"):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "byteLength": path.stat().st_size,
            "sha256": canary.sha256_file(path),
        })
    return {
        "schema": "onga-stage20-downstream-external-six-scenario-37-snapshot-manifest-v1",
        "runId": run_id,
        "files": files,
    }


def execute() -> dict[str, Any]:
    require(ACTIVATION_PATH.is_file() and not ACTIVATION_PATH.is_symlink(), "activation is missing")
    activation = canary.read_json(ACTIVATION_PATH)
    _, output = validate_activation(activation)
    require(socket.gethostname().lower() == "yoda", "runner host is not yoda")
    require(not output.exists() and not output.is_symlink(), "fresh batch output is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    canary.atomic_write_new(
        output / "claim.json",
        canary.canonical_bytes({
            "schema": "onga-stage20-downstream-external-six-scenario-37-snapshot-claim-v1",
            "status": "CLAIMED_SINGLE_USE_NO_RETRY",
            "authorizationId": activation["authorizationId"],
            "runId": activation["runId"],
            "claimedAtUtc": datetime.now(timezone.utc).isoformat(),
            "activationSha256": canary.sha256_file(ACTIVATION_PATH),
            "processId": os.getpid(),
            "retryCount": 0,
        }),
    )
    canary.atomic_write_new(
        output / "start-receipt.json",
        canary.canonical_bytes({
            "schema": "onga-stage20-downstream-external-six-scenario-37-snapshot-start-v1",
            "status": "STARTED_ALL_SIX_DIAGNOSTIC_NO_RETRY",
            "runId": activation["runId"],
            "scenarioCount": PARALLEL_WORKER_COUNT,
            "parallelWorkerCount": PARALLEL_WORKER_COUNT,
            "durationModelSeconds": FULL_SECONDS,
            "snapshotCountPerScenario": SNAPSHOT_COUNT,
            "automaticRetryCount": 0,
        }),
    )
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, _termination_handler)
    signal.signal(signal.SIGINT, _termination_handler)
    try:
        wall_started = time.monotonic()
        results = _run_parallel_batch(output)
        wall_seconds = time.monotonic() - wall_started
        require(wall_seconds <= MAXIMUM_BATCH_WALL_SECONDS, "batch wall-time limit exceeded")
        result = {
            "schema": "onga-stage20-downstream-external-six-scenario-37-snapshot-batch-result-v1",
            "status": "PASS_ALL_SIX_DIAGNOSTIC_PRECOMPUTES_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
            "runId": activation["runId"],
            "scenarioCount": len(results),
            "snapshotCountPerScenario": SNAPSHOT_COUNT,
            "wallSeconds": wall_seconds,
            "maximumCfl": max(float(item["maximumCfl"]) for item in results),
            "maximumRelativeMassBalanceError": max(
                float(item["maximumRelativeMassBalanceError"]) for item in results
            ),
            "maximumRelativeMassBalanceErrorFloat64Diagnostic": max(
                float(item["maximumRelativeMassBalanceErrorFloat64Diagnostic"])
                for item in results
            ),
            "massBalanceGuardPrecision": "LONG_DOUBLE",
            "maximumSourceResidualM3S": max(
                float(item["maximumSourceResidualM3S"]) for item in results
            ),
            "maximumSourceResidualRelative": max(
                float(item["maximumSourceResidualRelative"]) for item in results
            ),
            "maximumCommandedSourceResidualRelative": max(
                float(item["maximumCommandedSourceResidualRelative"])
                for item in results
            ),
            "absoluteSourceResidualTreatment": "DIAGNOSTIC_ONLY",
            "results": results,
            "usesUpstreamDonorVolume": False,
            "reverseFlowPermitted": False,
            "forecastProvided": False,
            "catchProbabilityProvided": False,
            "guiIntegrated": False,
        }
        canary.atomic_write_new(output / "result.json", canary.canonical_bytes(result))
        canary.atomic_write_new(
            output / "completion-receipt.json",
            canary.canonical_bytes({
                "schema": "onga-stage20-downstream-external-six-scenario-37-snapshot-completion-v1",
                "status": result["status"],
                "authorizationId": activation["authorizationId"],
                "runId": activation["runId"],
                "completedAtUtc": datetime.now(timezone.utc).isoformat(),
                "resultSha256": canary.sha256_file(output / "result.json"),
            }),
        )
        canary.atomic_write_new(
            output / "manifest.json",
            canary.canonical_bytes(_recursive_manifest(output, activation["runId"])),
        )
        return result
    except BaseException as exc:
        failure = output / "failure-receipt.json"
        if not failure.exists():
            canary.atomic_write_new(
                failure,
                canary.canonical_bytes({
                    "schema": "onga-stage20-downstream-external-six-scenario-37-snapshot-failure-v1",
                    "status": "FAILED_NO_RETRY",
                    "authorizationId": activation.get("authorizationId"),
                    "runId": activation.get("runId"),
                    "failedAtUtc": datetime.now(timezone.utc).isoformat(),
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                }),
            )
        raise
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--local-matrix-one-step", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scenario", help=argparse.SUPPRESS)
    parser.add_argument("--output", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        require(args.scenario is not None and args.output is not None, "worker arguments are missing")
        return _run_scenario(args.scenario, args.output)
    require(
        sum((args.preflight, args.local_matrix_one_step, args.execute)) <= 1,
        "choose at most one mode",
    )
    if args.execute:
        report = execute()
    elif args.local_matrix_one_step:
        report = run_local_matrix_one_step()
    else:
        report = build_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
