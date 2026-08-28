#!/usr/bin/env python3
"""Run the hash-bound C2.2 four-stage standard gate cycle.

This is a dedicated review-only runner.  It keeps the existing hydrodynamic
kernel unchanged, disables the legacy constant-Q0 fishway source inside that
kernel, and applies only the C2.1 analytic-source/ULP-storage link after each
hydrodynamic step.

The module is safe to import.  A solver run can only be started through
``--run-next-stage`` after a separate execution approval and a freshly written
PASS runtime preflight exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

import run_stage20_barrage_candidate_C_R1C_E1_remaining_gate_opening_envelope_v1 as e1
import run_stage20_fishway_1d_link_C2_storage_60s_v1 as c2
import stage20_fishway_1d_link_C2_1_storage_candidate_v1 as c21


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_stage20_fishway_C2_2_coupled_standard_cycle_v1.py"
PLAN = ROOT / "config/stage20_fishway_C2_2_coupled_standard_cycle_plan_candidate_v1.json"
PLAN_VALIDATION = (
    ROOT
    / "docs/results/stage20-fishway-C2-2-coupled-standard-cycle-plan-v1"
    / "static-validation.json"
)
PREFLIGHT_CANDIDATE = (
    ROOT / "config/stage20_fishway_C2_2_execution_preflight_candidate_v1.json"
)
PREFLIGHT_CANDIDATE_VALIDATION = (
    ROOT
    / "docs/results/stage20-fishway-C2-2-execution-preflight-candidate-v1"
    / "static-validation.json"
)
APPROVAL = (
    ROOT
    / "config/stage20_fishway_C2_2_coupled_standard_cycle_execution_approval_v1.json"
)
APPROVAL_VALIDATION = (
    ROOT
    / "docs/results/stage20-fishway-C2-2-execution-approval-v1"
    / "static-validation.json"
)
TIDE_EXTENSION = (
    ROOT
    / "config/stage20_m_boundary_tide_candidate_next_two_hour_extension_candidate_v1.json"
)
JMA_SNAPSHOT = ROOT / "data/jma_hakata_2026_hourly_tide_QF.txt"

FORMAL_INITIAL_STATES = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-C1-standard-gate5-600s-v1"
    / "checkpoint-states.npz"
)
FORMAL_INITIAL_CAPACITIES = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-C1-standard-gate5-600s-v1"
    / "diagnostic-fields.npz"
)
R1C_INITIAL_STATES = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-D2-full-history-v1"
    / "R1C-full-history-checkpoints.npz"
)
FORMAL_MESH = (
    ROOT
    / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1"
    / "review-mesh.npz"
)
R1C_MESH = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-next-stage-review-approval-v1"
    / "review-mesh.npz"
)

OUTPUT = (
    ROOT / "docs/results/stage20-fishway-C2-2-coupled-standard-cycle-v1"
)
PREFLIGHT = OUTPUT / "preflight-validation.json"
JOURNAL = OUTPUT / "execution-journal.json"
SUMMARY = OUTPUT / "diagnostic-summary.json"
MANIFEST = OUTPUT / "manifest.json"

OPENING_ORDER = (5, 4, 6, 3, 7, 2, 8, 1)
CLOSING_ORDER = tuple(reversed(OPENING_ORDER))
CHECKPOINT_INTERVAL_S = 30.0
MAXIMUM_RUN_COUNT = 4
LEGACY_Q0_M3_S = 0.25
HYDRO_Q0_M3_S = 0.0
RESIDENCE_TIME_S = 60.0
TIDE_SHIFTED_HOUR_MAXIMUM = 26.0
STANDARD_REPORT_CONTEXT = "c2_2_standard_cycle"
LOCAL_REPORT_CONTEXT = "local_r1c_experiment"

EXPECTED_HASHES = {
    FORMAL_INITIAL_STATES: "787b6da1620f3e5f2c1445bb5b90b297867f55f23c61dc351fa41b9d4239eb82",
    FORMAL_INITIAL_CAPACITIES: "03ca2c557eb692e93aa305792ff86a57ded15533c745316c6fafcadcc98dd268",
    R1C_INITIAL_STATES: "2ce73ec98cd84eb7dc60d2fee474eceab0de543c3e40b875dd7a07904382182f",
    FORMAL_MESH: "315636cb6844b4348863e92e33a342b599a2e27f70983651e81a92490d9b920e",
    R1C_MESH: "7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164",
    TIDE_EXTENSION: "3b0b465bf7a30b14a84a075a887714dc0f0a9d3d98bc89aa18160fddd45eaddd",
    JMA_SNAPSHOT: "2f6339ae6d6cf3a282f5f88dce03996f1c89bd0f4a23e93ed56d98ee8a7aaee9",
}

STAGES = (
    {
        "stageId": "A_formalR20_opening_0_to_5400",
        "meshId": "formalR20",
        "phase": "opening",
        "absoluteStartS": 0.0,
        "absoluteEndS": 5400.0,
        "checkpointCount": 181,
        "initialRole": "mesh_initial_equilibrium_storage",
    },
    {
        "stageId": "B_formalR20_full_reverse_closing_5400_to_10200",
        "meshId": "formalR20",
        "phase": "closing",
        "absoluteStartS": 5400.0,
        "absoluteEndS": 10200.0,
        "checkpointCount": 161,
        "initialRole": "exact_A_float64_continuation",
    },
    {
        "stageId": "C_R1C_opening_0_to_5400",
        "meshId": "R1C",
        "phase": "opening",
        "absoluteStartS": 0.0,
        "absoluteEndS": 5400.0,
        "checkpointCount": 181,
        "initialRole": "mesh_initial_equilibrium_storage",
    },
    {
        "stageId": "D_R1C_full_reverse_closing_5400_to_10200",
        "meshId": "R1C",
        "phase": "closing",
        "absoluteStartS": 5400.0,
        "absoluteEndS": 10200.0,
        "checkpointCount": 161,
        "initialRole": "exact_C_float64_continuation",
    },
)
STAGE_BY_ID = {stage["stageId"]: stage for stage in STAGES}

REQUIRED_ARCHIVE_ARRAYS = (
    "absoluteTimeS",
    "capacityFractionByGateId",
    "gateFluxM3SByGateId",
    "upstreamP2HeadM",
    "downstreamP2HeadM",
    "headDifferenceM",
    "fishwayOutflowM3S",
    "fishwayStorageDepthM",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def binding(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {
            name: np.asarray(archive[name]).copy()
            for name in archive.files
        }


def stage_dir(stage: dict[str, Any]) -> Path:
    return OUTPUT / stage["stageId"]


def stage_archive(stage: dict[str, Any]) -> Path:
    return stage_dir(stage) / "checkpoint-archive.npz"


def stage_report(stage: dict[str, Any]) -> Path:
    return stage_dir(stage) / "run-report.json"


def continuation_archive(stage: dict[str, Any]) -> Path:
    return stage_dir(stage) / "continuation-state.npz"


def smoothstep(value: float) -> float:
    clipped = min(1.0, max(0.0, value))
    return clipped * clipped * (3.0 - 2.0 * clipped)


def capacity_at_absolute_time(absolute_time_s: float) -> np.ndarray:
    """Return the approved eight-gate capacity vector at absolute time."""
    values = np.zeros(8, dtype=np.float64)
    if absolute_time_s <= 5400.0:
        for ordinal, gate_id in enumerate(OPENING_ORDER):
            start = 600.0 * ordinal
            values[gate_id - 1] = smoothstep(
                (absolute_time_s - start) / 300.0
            )
        return values
    values[:] = 1.0
    for ordinal, gate_id in enumerate(CLOSING_ORDER):
        start = 5400.0 + 600.0 * ordinal
        values[gate_id - 1] = 1.0 - smoothstep(
            (absolute_time_s - start) / 300.0
        )
    return values


def fishway_parameters() -> c21.FishwayC2StorageParameters:
    base = c2.parameters()
    return c21.FishwayC2StorageParameters(
        basal_discharge_m3_s=base.basal_discharge_m3_s,
        head_sqrt_gain_m2p5_s=base.head_sqrt_gain_m2p5_s,
        maximum_discharge_m3_s=base.maximum_discharge_m3_s,
        adverse_head_shutdown_m=base.adverse_head_shutdown_m,
        storage_area_m2=base.storage_area_m2,
        residence_time_s=RESIDENCE_TIME_S,
        local_invert_datum_m=base.local_invert_datum_m,
        reserve_depth_m=base.reserve_depth_m,
        maximum_available_volume_fraction_per_step=(
            base.maximum_available_volume_fraction_per_step
        ),
    )


def extended_tide_anomaly(
    simulated_seconds: float,
    tide: dict[str, Any],
    candidate: dict[str, Any],
) -> float:
    """Evaluate the pinned tide without wrap, freeze, or extrapolation."""
    shifted_hour = (
        simulated_seconds / 3600.0
        + float(tide["phaseShiftMinutes"]) / 60.0
    )
    if shifted_hour <= 24.0:
        return float(
            c2.base.s1.tide_anomaly_s1(
                simulated_seconds,
                tide,
                candidate,
            )
        )
    require(
        shifted_hour <= TIDE_SHIFTED_HOUR_MAXIMUM + 1e-12,
        "C2.2 pinned M tide hour-2 extension exhausted",
    )
    derivation = read_json(TIDE_EXTENSION)["derivation"]
    if shifted_hour <= 25.0:
        lower_hour = 24.0
        lower = float(
            derivation["nextDayHour0RelativeToBaseDayMeanM"]
        )
        upper = float(
            derivation["nextDayHour1RelativeToBaseDayMeanM"]
        )
    else:
        lower_hour = 25.0
        lower = float(
            derivation["nextDayHour1RelativeToBaseDayMeanM"]
        )
        upper = float(
            derivation["nextDayHour2RelativeToBaseDayMeanM"]
        )
    reference = lower + (shifted_hour - lower_hour) * (upper - lower)
    return reference * float(tide["amplitudeMultiplier"])


def stage_report_provenance(
    report_context: str,
    maximum_shifted_hour: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind only the authority and tide inputs used by the calling context."""

    require(
        report_context in {STANDARD_REPORT_CONTEXT, LOCAL_REPORT_CONTEXT},
        "unknown C2.2 report context",
    )
    if report_context == STANDARD_REPORT_CONTEXT:
        return (
            {
                "reportContext": STANDARD_REPORT_CONTEXT,
                "planSha256": sha256(PLAN),
                "executionRecordSha256": sha256(APPROVAL),
            },
            {
                "classification": (
                    "pinned_JMA_hourly_piecewise_linear_no_extrapolation"
                ),
                "extension": binding(TIDE_EXTENSION),
                "snapshot": binding(JMA_SNAPSHOT),
                "maximumShiftedHour": TIDE_SHIFTED_HOUR_MAXIMUM,
                "periodicWrapUsed": False,
                "constantFreezeUsed": False,
                "extrapolationUsed": False,
            },
        )
    require(
        maximum_shifted_hour <= 24.0 + 1e-12,
        "local R1C experiment would require an undeclared tide extension",
    )
    return (
        {
            "reportContext": LOCAL_REPORT_CONTEXT,
            "standardCyclePlanApplied": False,
            "standardCycleExecutionApprovalApplied": False,
        },
        {
            "classification": "fixed_local_stage19_candidate_from_source_setup",
            "sourceContract": binding(c2.base.c1.short.SOURCE_CONTRACT),
            "sourceReport": binding(c2.base.c1.short.SOURCE_REPORT),
            "candidate": binding(c2.base.c1.short.TIDE_CANDIDATE),
            "maximumShiftedHour": maximum_shifted_hour,
            "hour24ExtensionUsed": False,
            "JMASnapshotReadAtRuntime": False,
            "periodicWrapUsed": False,
            "constantFreezeUsed": False,
            "extrapolationUsed": False,
        },
    )


def load_mesh_initial_state(mesh_id: str) -> np.ndarray:
    if mesh_id == "formalR20":
        state_archive = load_npz(FORMAL_INITIAL_STATES)
        capacity_archive = load_npz(FORMAL_INITIAL_CAPACITIES)
        times = state_archive["checkpoint_time_s"]
        raw = state_archive["formal_R20_state_H_HU_HV"][0]
        capacity = capacity_archive[
            "capacity_fraction_by_case_checkpoint_gate"
        ][0, 0]
        expected_shape = (44880, 3)
    elif mesh_id == "R1C":
        state_archive = load_npz(R1C_INITIAL_STATES)
        times = state_archive["absoluteCheckpointTimeS"]
        raw = state_archive["state_H_HU_HV"][0]
        capacity = state_archive["capacityFractionByGateId"][0]
        expected_shape = (37724, 3)
    else:
        raise RuntimeError(f"unknown C2.2 mesh {mesh_id}")
    require(times[0] == 0.0, f"{mesh_id} initial time is not zero")
    require(
        raw.shape == expected_shape,
        f"{mesh_id} initial state shape changed",
    )
    require(
        np.array_equal(capacity, np.zeros(8, dtype=np.float64)),
        f"{mesh_id} initial gate state is not all closed",
    )
    promoted = raw.astype(np.float64)
    require(
        np.array_equal(promoted.astype(np.float32), raw),
        f"{mesh_id} initial state changed during float64 promotion",
    )
    require(
        np.isfinite(promoted).all() and np.min(promoted[:, 0]) >= 0.0,
        f"{mesh_id} initial state is invalid",
    )
    return promoted


def previous_opening_stage(stage: dict[str, Any]) -> dict[str, Any]:
    if stage["stageId"].startswith("B_"):
        return STAGES[0]
    if stage["stageId"].startswith("D_"):
        return STAGES[2]
    raise RuntimeError(f"{stage['stageId']} does not use a continuation")


def load_exact_continuation(
    stage: dict[str, Any],
) -> tuple[np.ndarray, float, dict[str, Any]]:
    previous = previous_opening_stage(stage)
    restart_path = continuation_archive(previous)
    report_path = stage_report(previous)
    require(
        restart_path.is_file() and report_path.is_file(),
        f"missing exact continuation for {stage['stageId']}",
    )
    previous_report = read_json(report_path)
    require(
        previous_report["outcome"] == "COMPLETED"
        and previous_report["hardAcceptancePassed"] is True,
        f"{previous['stageId']} did not hard-pass",
    )
    require(
        previous_report["continuationStateSha256"]
        == sha256(restart_path),
        f"{previous['stageId']} continuation archive hash changed",
    )
    restart = load_npz(restart_path)
    state = restart["state_H_HU_HV"]
    stored = restart["storedVolumeM3"]
    absolute_time = restart["absoluteTimeS"]
    capacity = restart["capacityFractionByGateId"]
    expected_cells = 44880 if stage["meshId"] == "formalR20" else 37724
    require(
        state.dtype == np.float64
        and state.shape == (expected_cells, 3),
        "continuation state is not the exact float64 mesh state",
    )
    require(
        stored.dtype == np.float64 and stored.shape == (1,),
        "continuation storage is not one float64 scalar",
    )
    require(
        absolute_time.shape == (1,)
        and float(absolute_time[0]) == stage["absoluteStartS"],
        "continuation absolute time changed",
    )
    require(
        capacity.shape == (8,)
        and np.array_equal(capacity, np.ones(8, dtype=np.float64)),
        "continuation capacity is not all-open",
    )
    require(
        array_sha256(state) == previous_report["finalStateArraySha256"],
        "continuation state changed during save/load",
    )
    require(
        float(stored[0]) == previous_report["finalStoredVolumeM3"],
        "continuation stored volume changed during save/load",
    )
    return state.copy(), float(stored[0]), {
        "sourceStageId": previous["stageId"],
        "continuation": binding(restart_path),
        "stateArraySha256": array_sha256(state),
        "loadedWithoutMutation": True,
    }


def approval_bindings_cover(
    approval: dict[str, Any],
    required: dict[Path, str],
) -> tuple[bool, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    supplied = list(approval.get("bindings", {}).values())
    for path, expected in required.items():
        relative = str(path.relative_to(ROOT))
        matches = [
            item
            for item in supplied
            if item.get("path") == relative
            and item.get("sha256") == expected
        ]
        actual = sha256(path) if path.is_file() else None
        rows.append(
            {
                "path": relative,
                "expected": expected,
                "actual": actual,
                "approvalBindingPresent": bool(matches),
                "passed": bool(matches) and actual == expected,
            }
        )
    return all(row["passed"] for row in rows), rows


def runtime_preflight() -> dict[str, Any]:
    """Write a fresh no-solver preflight after execution approval exists."""
    require(APPROVAL.is_file(), "separate C2.2 execution approval is absent")
    approval = read_json(APPROVAL)
    require(
        APPROVAL_VALIDATION.is_file(),
        "C2.2 execution approval static validation is absent",
    )
    approval_validation = read_json(APPROVAL_VALIDATION)
    plan = read_json(PLAN)
    plan_validation = read_json(PLAN_VALIDATION)
    candidate_validation = read_json(PREFLIGHT_CANDIDATE_VALIDATION)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, observed: Any = None) -> None:
        row: dict[str, Any] = {
            "id": check_id,
            "status": "PASS" if passed else "FAIL",
        }
        if observed is not None:
            row["observed"] = observed
        checks.append(row)

    scope = approval.get("authorizedScope", {})
    add(
        "separate_approval_authorizes_exact_conditional_four_stage_scope",
        approval.get("status")
        == "approved_exactly_four_conditional_C2_2_standard_cycle_runs"
        and scope.get("executionApproved") is True
        and scope.get("maximumNewSolverRunCount") == 4
        and scope.get("maximumPhysicalSecondsAcrossRuns") == 20400
        and scope.get("checkpointIntervalS") == 30
        and scope.get("formalR20MustPassFullCycleBeforeR1CStarts") is True
        and scope.get("failStopOnAnyHardCheck") is True
        and scope.get("overwriteExistingResult") is False,
        {"status": approval.get("status"), "scope": scope},
    )
    add(
        "execution_approval_static_validation_is_PASS_and_current",
        approval_validation.get("status") == "PASS"
        and approval_validation.get("source", {}).get("sha256")
        == sha256(APPROVAL)
        and approval_validation.get("failedCount") == 0,
        {
            "status": approval_validation.get("status"),
            "source": approval_validation.get("source"),
            "failedCount": approval_validation.get("failedCount"),
        },
    )
    add(
        "plan_and_candidate_validations_remain_PASS",
        plan_validation.get("status") == "PASS"
        and plan_validation.get("passedCount") == 15
        and candidate_validation.get("status") == "PASS",
        {
            "plan": [
                plan_validation.get("status"),
                plan_validation.get("passedCount"),
            ],
            "candidate": candidate_validation.get("status"),
        },
    )
    add(
        "plan_scope_is_exact",
        plan["operationAuthority"]["openingOrder"] == list(OPENING_ORDER)
        and plan["operationAuthority"]["closingOrder"]
        == list(CLOSING_ORDER)
        and plan["fishwayCoupling"]["oldConstantFishwaySourceEnabledDuringC2_2"]
        is False
        and plan["fishwayCoupling"]["C2_1SourceEnabledDuringC2_2"] is True
        and plan["aggregateCeilings"]["maximumNewSolverRunCount"] == 4,
    )
    required = {
        **EXPECTED_HASHES,
        PLAN: sha256(PLAN),
        PLAN_VALIDATION: sha256(PLAN_VALIDATION),
        PREFLIGHT_CANDIDATE: sha256(PREFLIGHT_CANDIDATE),
        PREFLIGHT_CANDIDATE_VALIDATION: sha256(
            PREFLIGHT_CANDIDATE_VALIDATION
        ),
        RUNNER: sha256(RUNNER),
        ROOT
        / "tools/stage20_fishway_1d_link_C2_1_storage_candidate_v1.py": sha256(
            ROOT
            / "tools/stage20_fishway_1d_link_C2_1_storage_candidate_v1.py"
        ),
    }
    covered, binding_rows = approval_bindings_cover(approval, required)
    add("approval_hash_binds_all_runtime_authorities", covered, binding_rows)
    add(
        "fixed_input_hashes_match",
        all(path.is_file() and sha256(path) == expected for path, expected in EXPECTED_HASHES.items()),
    )
    add(
        "stage_outputs_are_absent_and_overwrite_is_closed",
        all(not stage_dir(stage).exists() for stage in STAGES)
        and not JOURNAL.exists(),
    )
    formal = load_mesh_initial_state("formalR20")
    r1c = load_mesh_initial_state("R1C")
    add(
        "t0_initial_states_are_exact_finite_all_closed_sources",
        formal.shape == (44880, 3)
        and r1c.shape == (37724, 3)
        and np.isfinite(formal).all()
        and np.isfinite(r1c).all(),
    )
    shifted_end = (
        float(
            e1.read_json(e1.c1.short.SOURCE_CONTRACT)["run"][
                "tideCurveStartHour"
            ]
        )
        + float(e1.read_json(e1.c1.short.SOURCE_REPORT)["run"]["simulatedSeconds"])
        / 3600.0
        + 10200.0 / 3600.0
    )
    add(
        "pinned_tide_extension_covers_10200s_without_extrapolation",
        shifted_end <= TIDE_SHIFTED_HOUR_MAXIMUM
        and read_json(TIDE_EXTENSION)["coverage"]["allowedShiftedHourMax"]
        == 26,
        shifted_end,
    )
    add(
        "no_more_than_four_conditional_stages_are_defined",
        len(STAGES) == MAXIMUM_RUN_COUNT
        and sum(
            int(stage["absoluteEndS"] - stage["absoluteStartS"])
            for stage in STAGES
        )
        == 20400,
    )
    failed = [row["id"] for row in checks if row["status"] == "FAIL"]
    result = {
        "schema": "onga-stage20-fishway-C2-2-runtime-preflight-v1",
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "solverRun": False,
        "bindings": {
            "approval": binding(APPROVAL),
            "approvalValidation": binding(APPROVAL_VALIDATION),
            "plan": binding(PLAN),
            "runner": binding(RUNNER),
            "tideExtension": binding(TIDE_EXTENSION),
            "pinnedJmaSnapshot": binding(JMA_SNAPSHOT),
        },
        "safeguards": {
            "legacyConstantQ0Enabled": False,
            "C2_1SourceEnabled": True,
            "precomputationRun": False,
            "GUIOrResponsePackChanged": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
    }
    write_json(PREFLIGHT, result)
    require(not failed, f"C2.2 runtime preflight failed: {failed}")
    return result


def checkpoint_diagnostics(
    state: np.ndarray,
    bed: np.ndarray,
    workspace: Any,
    params: c21.FishwayC2StorageParameters,
    stored_volume: float,
) -> dict[str, Any]:
    return c21.link_step(
        state,
        bed,
        workspace,
        params,
        0.01,
        stored_volume,
    )["diagnostics"]


def run_stage_solver(
    stage: dict[str, Any],
    initial_state: np.ndarray,
    initial_storage: float | None,
    continuation_evidence: dict[str, Any] | None,
    report_context: str = STANDARD_REPORT_CONTEXT,
) -> tuple[dict[str, Any], dict[str, np.ndarray], np.ndarray, float]:
    """Run the shared numerical core with context-specific provenance."""
    require(
        report_context in {STANDARD_REPORT_CONTEXT, LOCAL_REPORT_CONTEXT},
        "unknown C2.2 report context",
    )
    context = e1.load_context(stage["meshId"], initial_state)
    state, bed, manning, geometry, p2, source, tide_candidate = context
    state = state.copy()
    params = fishway_parameters()
    mapping_workspace = c2.base.c1.build_mapping_workspace(geometry)
    zero_workspace, radius_by_rank, _ = c2.base.build_interface_context(
        geometry,
        p2,
    )
    fishway_workspace = c2.C2_workspace(geometry, p2)
    if initial_storage is None:
        stored_volume = c21.equilibrium_storage_volume_m3(
            state,
            bed,
            fishway_workspace,
            params,
        )
        seam_loaded_without_mutation = True
    else:
        stored_volume = float(initial_storage)
        seam_loaded_without_mutation = bool(
            continuation_evidence
            and continuation_evidence["loadedWithoutMutation"]
        )
    initial_stored_volume = stored_volume

    start = float(stage["absoluteStartS"])
    end = float(stage["absoluteEndS"])
    duration = end - start
    checkpoint_count = int(stage["checkpointCount"])
    expected_times = np.linspace(
        start,
        end,
        checkpoint_count,
        dtype=np.float64,
    )
    snapshots = np.empty(
        (checkpoint_count, len(state), 3),
        dtype=np.float32,
    )
    capacity = np.empty((checkpoint_count, 8), dtype=np.float64)
    flux_names = (
        "openLeftM3S",
        "openRightM3S",
        "wallLeftM3S",
        "wallRightM3S",
        "blendedLeftM3S",
        "blendedRightM3S",
        "leftPlusRightResidualM3S",
    )
    gate_flux = {
        name: np.empty((checkpoint_count, 8), dtype=np.float64)
        for name in flux_names
    }
    checkpoint_fields = {
        "upstreamP2HeadM": np.empty(checkpoint_count, dtype=np.float64),
        "downstreamP2HeadM": np.empty(checkpoint_count, dtype=np.float64),
        "headDifferenceM": np.empty(checkpoint_count, dtype=np.float64),
        "fishwayOutflowM3S": np.empty(checkpoint_count, dtype=np.float64),
        "fishwayStorageDepthM": np.empty(checkpoint_count, dtype=np.float64),
        "storedVolumeM3": np.empty(checkpoint_count, dtype=np.float64),
    }
    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
    tide_clock_origin = (
        float(source["contract"]["run"]["tideCurveStartHour"]) * 3600.0
        + float(
            read_json(c2.base.c1.short.SOURCE_REPORT)["run"][
                "simulatedSeconds"
            ]
        )
    )
    maximum_shifted_hour = (
        (tide_clock_origin + end) / 3600.0
        + float(source["tide"]["phaseShiftMinutes"]) / 60.0
    )
    if report_context == LOCAL_REPORT_CONTEXT:
        require(
            maximum_shifted_hour <= 24.0 + 1e-12,
            "local R1C experiment would require an undeclared tide extension",
        )

    def record(index: int, absolute_time: float) -> bool:
        alpha = capacity_at_absolute_time(absolute_time)
        c2.base.c1.update_mapping_workspace(mapping_workspace, alpha)
        snapshots[index] = state.astype(np.float32)
        capacity[index] = alpha
        flux, exact = c2.base.c1.record_checkpoint(
            state,
            bed,
            geometry,
            mapping_workspace,
            alpha,
        )
        for name in flux_names:
            gate_flux[name][index] = flux[name]
        diag = checkpoint_diagnostics(
            state,
            bed,
            fishway_workspace,
            params,
            stored_volume,
        )
        checkpoint_fields["upstreamP2HeadM"][index] = diag["upstreamHeadM"]
        checkpoint_fields["downstreamP2HeadM"][index] = diag["downstreamHeadM"]
        checkpoint_fields["headDifferenceM"][index] = diag["headDifferenceM"]
        checkpoint_fields["fishwayOutflowM3S"][index] = diag["outflowM3S"]
        checkpoint_fields["fishwayStorageDepthM"][index] = diag[
            "storageDepthBeforeM"
        ]
        checkpoint_fields["storedVolumeM3"][index] = stored_volume
        return bool(exact)

    mapping_exact_count = int(record(0, start))
    elapsed = 0.0
    step = 0
    next_checkpoint_index = 1
    next_checkpoint = CHECKPOINT_INTERVAL_S
    initial_extended_volume = (
        float(np.sum(state[:, 0] * geometry["areas"])) + stored_volume
    )
    expected_extended_volume = initial_extended_volume
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_source_residual = 0.0
    maximum_discrete_ratio = 0.0
    maximum_removed_fraction = 0.0
    maximum_gate_residual = 0.0
    minimum_storage_depth = stored_volume / params.storage_area_m2
    minimum_post_source_depth = float(np.min(state[:, 0]))
    minimum_outflow = math.inf
    maximum_outflow = 0.0
    minimum_outflow_time: float | None = None
    adverse_head_duration = 0.0
    failure: dict[str, Any] | None = None
    wall_start = time.monotonic()
    while elapsed < duration - 1e-12:
        absolute_time = start + elapsed
        alpha = capacity_at_absolute_time(absolute_time)
        c2.base.c1.update_mapping_workspace(mapping_workspace, alpha)
        residual, _ = c2.base.c1._maximum_gate_mass_residual(
            state,
            bed,
            geometry["left"],
            geometry["right"],
            mapping_workspace["effectiveLengths"],
            geometry["internalNormals"],
            mapping_workspace["multipliers"],
            mapping_workspace["gateFaceIds"],
        )
        maximum_gate_residual = max(
            maximum_gate_residual,
            float(residual),
        )
        stop_at = min(duration, next_checkpoint)
        maximum_dt = stop_at - elapsed
        previous_state = state
        previous_storage = stored_volume
        try:
            tide_target = extended_tide_anomaly(
                tide_clock_origin + absolute_time,
                source["tide"],
                tide_candidate,
            )
            (
                hydro_state,
                dt,
                cfl,
                boundary_outflow,
                zero_q,
                zero_residual,
                _,
                _,
                _,
                _,
                _,
                _,
                _,
            ) = c2.base.d1.advance_h2_step(
                previous_state,
                bed,
                manning,
                geometry["areas"],
                geometry["inverseAreas"],
                geometry["left"],
                geometry["right"],
                mapping_workspace["effectiveLengths"],
                geometry["internalNormals"],
                mapping_workspace["multipliers"],
                geometry["boundaryCells"],
                geometry["boundaryLengths"],
                geometry["boundaryNormals"],
                geometry["boundaryTags"],
                tide_target,
                target_flux_by_tag,
                zero_workspace.donor_support_area_m2,
                zero_workspace.receiver_weights,
                zero_workspace.expansion_rank,
                radius_by_rank,
                HYDRO_Q0_M3_S,
                c2.base.RESERVE_DEPTH_M,
                c2.base.MAXIMUM_AVAILABLE_FRACTION,
                c2.base.MAXIMUM_EXPANSION_RANK,
                c2.base.MAXIMUM_SUPPORT_RADIUS_M,
                0.12,
                maximum_dt,
            )
            require(
                float(zero_q) == 0.0 and float(zero_residual) == 0.0,
                "legacy constant-Q0 fishway source became nonzero",
            )
            link = c21.link_step(
                hydro_state,
                bed,
                fishway_workspace,
                params,
                dt,
                previous_storage,
            )
            diag = link["diagnostics"]
            next_state = hydro_state.copy()
            next_state[:, 0] = link["postSourceDepthM"]
            next_state[:, 1] += (
                dt
                * link["horizontalMomentumRateXByCell"]
                * geometry["inverseAreas"]
            )
            next_state[:, 2] += (
                dt
                * link["horizontalMomentumRateYByCell"]
                * geometry["inverseAreas"]
            )
            next_storage = float(link["nextStoredVolumeM3"])
            require(
                np.isfinite(next_state).all()
                and np.isfinite(next_storage),
                "C2.1 produced a nonfinite continuation state",
            )
            require(
                np.min(next_state[:, 0]) >= -1e-12,
                "C2.1 produced negative depth",
            )
        except Exception as error:
            failure = {
                "category": "NUMERICAL_BOUNDARY_OR_C2_1_GUARD",
                "message": f"{type(error).__name__}: {error}",
                "absoluteTimeS": absolute_time,
                "stepsCompletedBeforeFailure": step,
                "stateMutationOnFailedStep": False,
                "automaticRetryAuthorized": False,
            }
            state = previous_state
            stored_volume = previous_storage
            break
        state = next_state
        stored_volume = next_storage
        elapsed += dt
        step += 1
        expected_extended_volume -= dt * float(boundary_outflow)
        actual_extended_volume = (
            float(np.sum(state[:, 0] * geometry["areas"])) + stored_volume
        )
        maximum_mass_error = max(
            maximum_mass_error,
            abs(actual_extended_volume - expected_extended_volume)
            / max(abs(initial_extended_volume), 1.0),
        )
        maximum_cfl = max(maximum_cfl, float(cfl))
        maximum_source_residual = max(
            maximum_source_residual,
            abs(float(diag["analyticSourceMassResidualM3S"])),
        )
        maximum_discrete_ratio = max(
            maximum_discrete_ratio,
            float(diag["discreteStorageIdentityErrorToToleranceRatio"]),
        )
        maximum_removed_fraction = max(
            maximum_removed_fraction,
            float(diag["maximumActualAvailableVolumeFractionRemoved"]),
        )
        minimum_storage_depth = min(
            minimum_storage_depth,
            float(diag["storageDepthAfterM"]),
        )
        minimum_post_source_depth = min(
            minimum_post_source_depth,
            float(diag["minimumPostSourceDepthM"]),
        )
        outflow = float(diag["outflowM3S"])
        if outflow < minimum_outflow:
            minimum_outflow = outflow
            minimum_outflow_time = start + elapsed
        maximum_outflow = max(maximum_outflow, outflow)
        if diag["inflowLimitation"] == "adverse_head":
            adverse_head_duration += dt
        if (
            elapsed >= next_checkpoint - 1e-10
            or elapsed >= duration - 1e-10
        ):
            require(
                next_checkpoint_index < checkpoint_count,
                "too many C2.2 checkpoints",
            )
            mapping_exact_count += int(
                record(next_checkpoint_index, start + elapsed)
            )
            next_checkpoint_index += 1
            next_checkpoint += CHECKPOINT_INTERVAL_S

    completed = failure is None and elapsed >= duration - 1e-10
    used_count = next_checkpoint_index
    archive_arrays: dict[str, np.ndarray] = {
        "state_H_HU_HV": snapshots[:used_count],
        "absoluteTimeS": expected_times[:used_count],
        "capacityFractionByGateId": capacity[:used_count],
        "gateFluxM3SByGateId": gate_flux["blendedLeftM3S"][:used_count],
        **{
            name: values[:used_count]
            for name, values in checkpoint_fields.items()
        },
        **{
            f"gateFlux__{name}": values[:used_count]
            for name, values in gate_flux.items()
        },
    }
    expected_capacity = np.stack(
        [
            capacity_at_absolute_time(float(value))
            for value in expected_times[:used_count]
        ]
    )
    depth = state[:, 0]
    nonfinite = int(state.size - np.isfinite(state).sum())
    hard_checks = {
        "completedStage": completed,
        "capacityTimelineExactlyMatchesApprovedOrder": (
            completed
            and used_count == checkpoint_count
            and np.array_equal(
                archive_arrays["capacityFractionByGateId"],
                expected_capacity,
            )
        ),
        "negativeDepthCount": int(np.sum(depth < 0.0)) == 0,
        "nonFiniteValueCount": nonfinite == 0,
        "maximumRelativeExtendedMassBalanceError": (
            maximum_mass_error <= 1e-10
        ),
        "maximumAbsoluteAnalyticFishwaySourceResidualM3S": (
            maximum_source_residual <= 1e-12
        ),
        "maximumFishwayDiscreteStorageErrorToToleranceRatio": (
            maximum_discrete_ratio <= 1.0
        ),
        "minimumFishwayStorageDepthM": (
            minimum_storage_depth >= 0.05 - 1e-12
        ),
        "maximumAvailableVolumeFractionRemovedPerStep": (
            maximum_removed_fraction <= 0.02 + 1e-12
        ),
        "minimumFishwayOutflowM3S": (
            minimum_outflow != math.inf and minimum_outflow > 0.0
        ),
        "gateMappingIdentityHoldsAtEveryCheckpoint": (
            completed and mapping_exact_count == checkpoint_count
        ),
        "storedContinuationStateLoadedWithoutMutation": (
            seam_loaded_without_mutation
        ),
    }
    authority_fields, tide_boundary_input = stage_report_provenance(
        report_context,
        maximum_shifted_hour,
    )

    report = {
        "schema": "onga-stage20-fishway-C2-2-stage-run-report-v1",
        "version": 1,
        "stageId": stage["stageId"],
        "meshId": stage["meshId"],
        "phase": stage["phase"],
        "absoluteStartS": start,
        "absoluteEndS": end,
        **authority_fields,
        "outcome": "COMPLETED" if completed else "GUARD_TRIGGERED",
        "hardAcceptancePassed": all(hard_checks.values()),
        "hardAcceptanceChecks": hard_checks,
        "physicalSecondsCompleted": elapsed,
        "stepsCompleted": step,
        "wallSeconds": time.monotonic() - wall_start,
        "checkpointCount": used_count,
        "expectedCheckpointCount": checkpoint_count,
        "capacityTimelineExactlyMatchesApprovedOrder": hard_checks[
            "capacityTimelineExactlyMatchesApprovedOrder"
        ],
        "negativeDepthCount": int(np.sum(depth < 0.0)),
        "nonFiniteValueCount": nonfinite,
        "maximumRelativeExtendedMassBalanceError": maximum_mass_error,
        "maximumAbsoluteAnalyticFishwaySourceResidualM3S": (
            maximum_source_residual
        ),
        "maximumFishwayDiscreteStorageErrorToToleranceRatio": (
            maximum_discrete_ratio
        ),
        "minimumFishwayStorageDepthM": minimum_storage_depth,
        "maximumAvailableVolumeFractionRemovedPerStep": (
            maximum_removed_fraction
        ),
        "minimumFishwayOutflowM3S": (
            None if minimum_outflow == math.inf else minimum_outflow
        ),
        "minimumFishwayOutflowAbsoluteTimeS": minimum_outflow_time,
        "gateMappingIdentityHoldsAtEveryCheckpoint": hard_checks[
            "gateMappingIdentityHoldsAtEveryCheckpoint"
        ],
        "storedContinuationStateLoadedWithoutMutation": (
            seam_loaded_without_mutation
        ),
        "adverseHeadDurationS": adverse_head_duration,
        "minimumStorageReserveMarginM": minimum_storage_depth - 0.05,
        "minimumPostSourceDepthM": minimum_post_source_depth,
        "maximumFishwayOutflowM3S": maximum_outflow,
        "maximumCfl": maximum_cfl,
        "maximumAbsoluteGateMassResidualM3S": maximum_gate_residual,
        "initialStoredVolumeM3": initial_stored_volume,
        "finalStoredVolumeM3": stored_volume,
        "finalStateArraySha256": array_sha256(state),
        "initialRole": stage["initialRole"],
        "continuationEvidence": continuation_evidence,
        "fishwayCoupling": {
            "legacyConstantQ0M3S": LEGACY_Q0_M3_S,
            "legacyConstantQ0Enabled": False,
            "hydrodynamicQ0ArgumentM3S": HYDRO_Q0_M3_S,
            "C2_1SourceEnabled": True,
            "residenceTimeS": RESIDENCE_TIME_S,
            "doubleCounting": False,
        },
        "tideBoundaryInput": tide_boundary_input,
        "failure": failure,
    }
    return report, archive_arrays, state, stored_volume


def new_journal() -> dict[str, Any]:
    return {
        "schema": "onga-stage20-fishway-C2-2-execution-journal-v1",
        "version": 1,
        "status": "AUTHORIZED_NOT_STARTED",
        "authorizedRunCount": MAXIMUM_RUN_COUNT,
        "startedRunCount": 0,
        "completedStageIds": [],
        "events": [],
        "safeguards": {
            "fifthRunStarted": False,
            "automaticRetryStarted": False,
            "stageReordered": False,
            "R1CStartedBeforeFormalFullCyclePass": False,
            "legacyConstantQ0Enabled": False,
            "precomputationRun": False,
            "GUIOrResponsePackChanged": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
    }


def load_or_create_journal() -> dict[str, Any]:
    return read_json(JOURNAL) if JOURNAL.is_file() else new_journal()


def validate_completed_prefix(journal: dict[str, Any]) -> int:
    completed = journal["completedStageIds"]
    expected = [stage["stageId"] for stage in STAGES[: len(completed)]]
    require(completed == expected, "C2.2 completed stage order changed")
    for stage in STAGES[: len(completed)]:
        report_path = stage_report(stage)
        archive_path = stage_archive(stage)
        require(
            report_path.is_file() and archive_path.is_file(),
            f"incomplete saved result for {stage['stageId']}",
        )
        report = read_json(report_path)
        require(
            report["outcome"] == "COMPLETED"
            and report["hardAcceptancePassed"] is True
            and report["checkpointArchiveSha256"] == sha256(archive_path),
            f"{stage['stageId']} is not a hash-valid hard PASS",
        )
    if len(completed) >= 2:
        for stage in STAGES[:2]:
            require(
                read_json(stage_report(stage))["hardAcceptancePassed"],
                "formal full cycle did not pass before R1C",
            )
    return len(completed)


def run_next_stage() -> dict[str, Any]:
    require(PREFLIGHT.is_file(), "C2.2 runtime preflight is absent")
    preflight = read_json(PREFLIGHT)
    require(
        preflight["status"] == "PASS"
        and preflight["bindings"]["approval"]["sha256"] == sha256(APPROVAL)
        and preflight["bindings"]["runner"]["sha256"] == sha256(RUNNER),
        "C2.2 runtime preflight binding changed",
    )
    journal = load_or_create_journal()
    require(
        journal["status"] not in ("RUNNING", "FAIL_STOP"),
        "unfinished or failed C2.2 start exists; automatic retry refused",
    )
    next_index = validate_completed_prefix(journal)
    require(next_index < MAXIMUM_RUN_COUNT, "all four C2.2 stages already ran")
    require(
        journal["startedRunCount"] == next_index
        and journal["startedRunCount"] < MAXIMUM_RUN_COUNT,
        "C2.2 solver start count does not match completed prefix",
    )
    stage = STAGES[next_index]
    require(
        not stage_dir(stage).exists(),
        f"result target exists for {stage['stageId']}; overwrite refused",
    )
    if next_index == 2:
        require(
            journal["completedStageIds"]
            == [STAGES[0]["stageId"], STAGES[1]["stageId"]],
            "R1C cannot start before the formal full cycle hard-passes",
        )
    journal["status"] = "RUNNING"
    journal["startedRunCount"] += 1
    journal["events"].append(
        {
            "event": "STARTED",
            "ordinal": journal["startedRunCount"],
            "stageId": stage["stageId"],
            "automaticRetryAuthorized": False,
        }
    )
    write_json(JOURNAL, journal)

    if stage["phase"] == "opening":
        initial_state = load_mesh_initial_state(stage["meshId"])
        initial_storage = None
        continuation_evidence = None
    else:
        (
            initial_state,
            initial_storage,
            continuation_evidence,
        ) = load_exact_continuation(stage)
    report, arrays, final_state, final_storage = run_stage_solver(
        stage,
        initial_state,
        initial_storage,
        continuation_evidence,
    )
    directory = stage_dir(stage)
    directory.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(stage_archive(stage), **arrays)
    report["checkpointArchiveSha256"] = sha256(stage_archive(stage))
    if stage["phase"] == "opening" and report["hardAcceptancePassed"]:
        np.savez_compressed(
            continuation_archive(stage),
            state_H_HU_HV=final_state.astype(np.float64, copy=False),
            storedVolumeM3=np.asarray(
                [final_storage],
                dtype=np.float64,
            ),
            absoluteTimeS=np.asarray(
                [stage["absoluteEndS"]],
                dtype=np.float64,
            ),
            capacityFractionByGateId=capacity_at_absolute_time(
                stage["absoluteEndS"]
            ),
        )
        report["continuationStateSha256"] = sha256(
            continuation_archive(stage)
        )
        loaded = load_npz(continuation_archive(stage))
        require(
            array_sha256(loaded["state_H_HU_HV"])
            == report["finalStateArraySha256"]
            and float(loaded["storedVolumeM3"][0])
            == report["finalStoredVolumeM3"],
            "saved float64 continuation changed before report commit",
        )
    else:
        report["continuationStateSha256"] = None
    write_json(stage_report(stage), report)

    journal = read_json(JOURNAL)
    journal["events"][-1]["outcome"] = report["outcome"]
    journal["events"][-1]["hardAcceptancePassed"] = report[
        "hardAcceptancePassed"
    ]
    journal["events"][-1]["report"] = binding(stage_report(stage))
    journal["events"][-1]["checkpointArchive"] = binding(
        stage_archive(stage)
    )
    if report["hardAcceptancePassed"]:
        journal["completedStageIds"].append(stage["stageId"])
        journal["status"] = (
            "RUNS_COMPLETE_AWAITING_ANALYSIS"
            if len(journal["completedStageIds"]) == MAXIMUM_RUN_COUNT
            else "READY_FOR_NEXT_STAGE"
        )
    else:
        journal["status"] = "FAIL_STOP"
    write_json(JOURNAL, journal)
    require(
        report["hardAcceptancePassed"],
        f"{stage['stageId']} hard acceptance failed; cycle stopped",
    )
    return report


def analyze() -> dict[str, Any]:
    require(JOURNAL.is_file(), "C2.2 execution journal is absent")
    journal = read_json(JOURNAL)
    require(
        validate_completed_prefix(journal) == MAXIMUM_RUN_COUNT,
        "all four hash-valid hard-PASS stages are required",
    )
    reports = {
        stage["stageId"]: read_json(stage_report(stage))
        for stage in STAGES
    }
    archives = {
        stage["stageId"]: load_npz(stage_archive(stage))
        for stage in STAGES
    }
    for opening, closing in ((STAGES[0], STAGES[1]), (STAGES[2], STAGES[3])):
        first = archives[opening["stageId"]]
        second = archives[closing["stageId"]]
        for name in REQUIRED_ARCHIVE_ARRAYS:
            require(
                np.array_equal(first[name][-1], second[name][0]),
                f"{opening['meshId']} 5400s seam differs for {name}",
            )
        require(
            np.array_equal(
                first["state_H_HU_HV"][-1],
                second["state_H_HU_HV"][0],
            ),
            f"{opening['meshId']} 5400s checkpoint state seam differs",
        )
    summary = {
        "schema": "onga-stage20-fishway-C2-2-diagnostic-summary-v1",
        "version": 1,
        "status": "PASS_REVIEW_ONLY_AWAITING_DECISION_VISUAL",
        "stageOrder": [stage["stageId"] for stage in STAGES],
        "allFourStagesHardPassed": True,
        "formalFullCyclePassedBeforeR1C": True,
        "byStage": reports,
        "minimumFishwayOutflowM3S": min(
            report["minimumFishwayOutflowM3S"]
            for report in reports.values()
        ),
        "maximumRelativeExtendedMassBalanceError": max(
            report["maximumRelativeExtendedMassBalanceError"]
            for report in reports.values()
        ),
        "maximumFishwayDiscreteStorageErrorToToleranceRatio": max(
            report["maximumFishwayDiscreteStorageErrorToToleranceRatio"]
            for report in reports.values()
        ),
        "physicalCalibration": False,
        "productionOrPrecomputationAuthorized": False,
        "decisionVisualRequiredBeforePromotion": True,
    }
    write_json(SUMMARY, summary)
    write_json(
        MANIFEST,
        {
            "schema": "onga-stage20-fishway-C2-2-manifest-v1",
            "version": 1,
            "status": "SEALED_REVIEW_ONLY_RESULT_SET",
            "bindings": {
                "plan": binding(PLAN),
                "approval": binding(APPROVAL),
                "runner": binding(RUNNER),
                "preflight": binding(PREFLIGHT),
                "journal": binding(JOURNAL),
                "summary": binding(SUMMARY),
                **{
                    f"{stage['stageId']}Report": binding(
                        stage_report(stage)
                    )
                    for stage in STAGES
                },
                **{
                    f"{stage['stageId']}Archive": binding(
                        stage_archive(stage)
                    )
                    for stage in STAGES
                },
            },
            "safeguards": {
                "productionOrPrecomputationAuthorized": False,
                "GUIOrResponsePackChanged": False,
                "publicRuntimeChanged": False,
                "mainMerged": False,
            },
        },
    )
    journal["status"] = "ANALYSIS_COMPLETE_AWAITING_DECISION_VISUAL"
    journal["summary"] = binding(SUMMARY)
    journal["manifest"] = binding(MANIFEST)
    write_json(JOURNAL, journal)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--run-next-stage", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    selected = sum(
        int(value)
        for value in (
            args.preflight_only,
            args.run_next_stage,
            args.analyze,
        )
    )
    if selected != 1:
        parser.error(
            "choose exactly one of --preflight-only, "
            "--run-next-stage, --analyze"
        )
    if args.preflight_only:
        result = runtime_preflight()
        print(
            json.dumps(
                {
                    "event": "C2_2_preflight_complete",
                    "status": result["status"],
                    "checks": result["checkCount"],
                    "solverRun": False,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    elif args.run_next_stage:
        result = run_next_stage()
        print(
            json.dumps(
                {
                    "event": "C2_2_stage_saved",
                    "stageId": result["stageId"],
                    "hardAcceptancePassed": result[
                        "hardAcceptancePassed"
                    ],
                    "wallSeconds": result["wallSeconds"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    else:
        result = analyze()
        print(
            json.dumps(
                {
                    "event": "C2_2_analysis_complete",
                    "status": result["status"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
