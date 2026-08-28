#!/usr/bin/env python3
"""Run the approved Candidate C C2b-S1 two-mesh all-closed continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

import run_stage20_barrage_C1_local_transition_600s_v1 as c1


ROOT = Path(__file__).resolve().parents[1]
APPROVAL = (
    ROOT
    / "config/stage20_barrage_candidate_C_C2b_S1_all_closed_settling_approval_v1.json"
)
PLAN = (
    ROOT
    / "config/stage20_barrage_candidate_C_C2b_S1_all_closed_settling_plan_candidate_v1.json"
)
TIDE_EXTENSION = (
    ROOT
    / "config/stage20_m_boundary_tide_candidate_next_hour_extension_v1.json"
)
OUTPUT = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-C2b-S1-all-closed-settling-v1"
)
PREFLIGHT = OUTPUT / "preflight-validation.json"
FORMAL_RUN = OUTPUT / "formal-R20-continuation-checkpoints.npz"
CANDIDATE_RUN = OUTPUT / "candidate-C-continuation-checkpoints.npz"
FORMAL_REPORT = OUTPUT / "formal-R20-run-report.json"
CANDIDATE_REPORT = OUTPUT / "candidate-C-run-report.json"
JOURNAL = OUTPUT / "execution-journal.json"
RAW_RUN_REPORTS = OUTPUT / "raw-run-reports.json"
CHECKPOINT_STATES = OUTPUT / "checkpoint-states.npz"
FIELDS = OUTPUT / "diagnostic-fields.npz"
SUMMARY = OUTPUT / "diagnostic-summary.json"
VALIDATION = OUTPUT / "static-validation.json"
MANIFEST = OUTPUT / "manifest.json"

C2A_RESULT = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-C2b-reverse-closing-v1"
)
C2A_CHECKPOINTS = C2A_RESULT / "checkpoint-states.npz"
C2A_FIELDS = C2A_RESULT / "diagnostic-fields.npz"
C2A_SUMMARY = C2A_RESULT / "diagnostic-summary.json"
C2A_STATIC_VALIDATION = C2A_RESULT / "static-validation.json"
C2A_INDEPENDENT_VALIDATION = C2A_RESULT / "independent-validation.json"
PLAN_RESULT = C2A_RESULT
PLAN_STATIC_VALIDATION = C2A_RESULT / "static-validation.json"
PLAN_INDEPENDENT_VALIDATION = C2A_RESULT / "independent-validation.json"

FORMAL_MESH = (
    ROOT
    / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1"
    / "review-mesh.npz"
)
FORMAL_SUMMARY = (
    ROOT
    / "docs/results/stage20-barrage-H2-R20-approved-review-mesh-v1"
    / "mesh-summary.json"
)
CANDIDATE_MESH = (
    ROOT
    / "docs/results/stage20-R20-multizone-candidate-C-C1-review-approval-v1"
    / "review-mesh.npz"
)
CANDIDATE_SUMMARY = (
    ROOT
    / "docs/results/stage20-R20-multizone-candidate-C-review-mesh-v1"
    / "mesh-summary.json"
)

EXPECTED_APPROVAL_SHA = (
    "e675642722bb6bbaef094969b124646e8ceca8152139de0291971d46dbceab1b"
)
EXPECTED_C1_RUNNER_SHA = (
    "82e8157cc7133522605611a6fcacc13871f32eeb75a15cdca6a09d1bb2a65597"
)
EXPECTED_TIDE_EXTENSION_SHA = (
    "3dca34cdf5e89ea3efcdb39018b79c39826d59058beb6274e3d653ac9eb2b22a"
)
MESH_IDS = ("formalR20", "candidateC")
RUN_ARCHIVES = {
    "formalR20": FORMAL_RUN,
    "candidateC": CANDIDATE_RUN,
}
RUN_REPORT_PATHS = {
    "formalR20": FORMAL_REPORT,
    "candidateC": CANDIDATE_REPORT,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: np.asarray(archive[name]) for name in archive.files}


def binding(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def add(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    observed: Any = None,
) -> None:
    row: dict[str, Any] = {"id": check_id, "passed": bool(passed)}
    if observed is not None:
        row["observed"] = observed
    checks.append(row)


def protected_paths() -> dict[Path, str]:
    return {
        **c1.short.PROTECTED,
        c1.CURRENT_BINARY_INTERFACE:
            c1.EXPECTED_CURRENT_BINARY_INTERFACE_SHA,
        c1.CURRENT_BINARY_CONTRACT:
            c1.EXPECTED_CURRENT_BINARY_CONTRACT_SHA,
    }


def c2b_capacity_at_elapsed(elapsed_s: float) -> np.ndarray:
    del elapsed_s
    return np.zeros(8, dtype=np.float64)


def tide_anomaly_s1(
    simulated_seconds: float,
    tide: dict[str, Any],
    candidate: dict[str, Any],
) -> float:
    shifted_hour = (
        simulated_seconds / 3600.0
        + float(tide["phaseShiftMinutes"]) / 60.0
    )
    if shifted_hour <= 24.0:
        return c1.reference.tide_anomaly_m(
            simulated_seconds,
            tide,
            candidate,
        )
    extension = read_json(TIDE_EXTENSION)["derivation"]
    c1.require(
        shifted_hour <= 25.0,
        "C2b-S1 M tide next-hour extension exhausted",
    )
    hour0 = float(extension["nextDayHour0RelativeToBaseDayMeanM"])
    hour1 = float(extension["nextDayHour1RelativeToBaseDayMeanM"])
    reference = hour0 + (shifted_hour - 24.0) * (hour1 - hour0)
    return reference * float(tide["amplitudeMultiplier"])


def load_initial_states() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    checkpoints = load_npz(C2A_CHECKPOINTS)
    times = checkpoints["checkpoint_time_s"]
    c1.require(
        times.shape == (181,)
        and np.array_equal(times, np.arange(1800.0, 3601.0, 10.0)),
        "C2b checkpoint time axis changed",
    )
    formal32 = checkpoints["formal_R20_state_H_HU_HV"][180]
    candidate32 = checkpoints["candidate_C_state_H_HU_HV"][180]
    c1.require(
        formal32.shape == (44880, 3)
        and candidate32.shape == (34940, 3),
        "C2b final checkpoint state shape changed",
    )
    formal64 = formal32.astype(np.float64)
    candidate64 = candidate32.astype(np.float64)
    c1.require(
        np.array_equal(formal64.astype(np.float32), formal32)
        and np.array_equal(candidate64.astype(np.float32), candidate32),
        "float32 checkpoint values changed during exact float64 promotion",
    )
    return formal64, candidate64, times


def load_mesh_contexts() -> tuple[
    dict[str, dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    source, tide_candidate = c1.short.initial_condition_data()
    p2_source = read_json(c1.short.P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_polygons = {
        side: c1.Polygon(
            c1.old.project_many(
                p2_source[side]["footprint"]["coordinates"][0][:-1]
            )
        )
        for side in ("upstream", "downstream")
    }
    formal_initial, candidate_initial, _ = load_initial_states()
    records: dict[str, dict[str, Any]] = {
        "formalR20": {
            "path": FORMAL_MESH,
            "summaryPath": FORMAL_SUMMARY,
            "initialState": formal_initial,
        },
        "candidateC": {
            "path": CANDIDATE_MESH,
            "summaryPath": CANDIDATE_SUMMARY,
            "initialState": candidate_initial,
        },
    }
    for mesh_id, record in records.items():
        mesh = c1.short.mesh_arrays(record["path"])
        geometry = c1.short.build_review_geometry(mesh)
        summary = read_json(record["summaryPath"])
        _, bed, manning, source_mapping = c1.short.initialize_mesh(
            mesh,
            geometry,
            source,
        )
        c1.require(
            len(record["initialState"]) == len(geometry["triangles"]),
            f"C2b initial state and mesh differ: {mesh_id}",
        )
        record.update(
            {
                "mesh": mesh,
                "geometry": geometry,
                "summary": summary,
                "bed": bed,
                "manning": manning,
                "sourceMapping": source_mapping,
                "P2": c1.short.p2_arrays(
                    geometry,
                    summary,
                    p2_polygons,
                ),
            }
        )
    return records, source, tide_candidate


def preflight() -> tuple[dict[str, Any], dict[str, str]]:
    approval = read_json(APPROVAL)
    plan = read_json(PLAN)
    checks: list[dict[str, Any]] = []
    add(
        checks,
        "approval_file_hash_exact",
        sha256(APPROVAL) == EXPECTED_APPROVAL_SHA,
        sha256(APPROVAL),
    )
    add(
        checks,
        "approval_is_exactly_two_C2b_S1_all_closed_settling_runs",
        approval["status"]
        == "approved_exactly_two_C2b_S1_600s_all_closed_settling_continuation_runs"
        and approval["userEvidence"]["text"] == "承認する"
        and approval["authorizedScope"]["solverRunCount"] == 2
        and approval["authorizedScope"]["continuationPhysicalSecondsPerRun"]
        == 600
        and approval["authorizedScope"]["initialAbsoluteTimeS"] == 3600
        and approval["authorizedScope"]["finalAbsoluteTimeS"] == 4200
        and approval["authorizedScope"]["openMainGates"] == []
        and approval["authorizedScope"]["capacityFractionByGate1To8"]
        == [0, 0, 0, 0, 0, 0, 0, 0],
        approval["authorizedScope"],
    )
    binding_rows = []
    for name, record in approval["bindings"].items():
        path = ROOT / record["path"]
        actual = sha256(path) if path.is_file() else None
        binding_rows.append(
            {
                "name": name,
                "path": record["path"],
                "expected": record["sha256"],
                "actual": actual,
                "passed": actual == record["sha256"],
            }
        )
    add(
        checks,
        "all_approval_bindings_match",
        all(row["passed"] for row in binding_rows),
        binding_rows,
    )
    add(
        checks,
        "exact_plan_hash_matches_approval",
        sha256(PLAN) == approval["bindings"]["exactPlan"]["sha256"],
        sha256(PLAN),
    )
    add(
        checks,
        "C2b_static_and_independent_validations_pass",
        read_json(PLAN_STATIC_VALIDATION)["status"] == "PASS"
        and read_json(PLAN_STATIC_VALIDATION)["passedCount"] == 20
        and read_json(PLAN_INDEPENDENT_VALIDATION)["status"] == "PASS"
        and read_json(PLAN_INDEPENDENT_VALIDATION)["passedCount"] == 22,
        {
            "static": read_json(PLAN_STATIC_VALIDATION)["status"],
            "independent": read_json(PLAN_INDEPENDENT_VALIDATION)["status"],
        },
    )
    add(
        checks,
        "C2b_result_validations_pass",
        read_json(C2A_STATIC_VALIDATION)["status"] == "PASS"
        and read_json(C2A_INDEPENDENT_VALIDATION)["status"] == "PASS",
        {
            "static": read_json(C2A_STATIC_VALIDATION)["status"],
            "independent": read_json(C2A_INDEPENDENT_VALIDATION)["status"],
        },
    )
    formal, candidate, times = load_initial_states()
    add(
        checks,
        "C2b_index_180_is_exact_3600s_initial_state",
        times[180] == 3600.0
        and formal.shape == (44880, 3)
        and candidate.shape == (34940, 3),
        {
            "timeS": float(times[180]),
            "formalShape": list(formal.shape),
            "candidateShape": list(candidate.shape),
        },
    )
    add(
        checks,
        "initial_states_are_finite_and_nonnegative",
        np.isfinite(formal).all()
        and np.isfinite(candidate).all()
        and np.min(formal[:, 0]) >= 0.0
        and np.min(candidate[:, 0]) >= 0.0,
        {
            "formalMinimumDepthM": float(np.min(formal[:, 0])),
            "candidateMinimumDepthM": float(np.min(candidate[:, 0])),
        },
    )
    sample_times = np.asarray([0.0, 150.0, 300.0, 450.0, 600.0])
    observed_schedule = np.stack(
        [c2b_capacity_at_elapsed(value) for value in sample_times]
    )
    add(
        checks,
        "C2b_S1_capacity_schedule_is_all_closed_at_all_samples",
        np.array_equal(
            observed_schedule,
            np.zeros((len(sample_times), 8)),
        ),
        observed_schedule.tolist(),
    )
    tide_extension = read_json(TIDE_EXTENSION)
    tide_source = ROOT / tide_extension["source"]["snapshotPath"]
    tide_derivation = tide_extension["derivation"]
    add(
        checks,
        "M_tide_next_hour_extension_is_exactly_derived_from_pinned_JMA_snapshot",
        sha256(TIDE_EXTENSION) == EXPECTED_TIDE_EXTENSION_SHA
        and sha256(tide_source)
        == tide_extension["source"]["snapshotSha256"]
        and tide_extension["source"]["baseCandidateDate"] == "2026-02-15"
        and tide_derivation["nextDayDate"] == "2026-02-16"
        and tide_derivation[
            "nextDayHour0HeightAboveTideTableDatumCm"
        ]
        == 88
        and tide_derivation[
            "nextDayHour1HeightAboveTideTableDatumCm"
        ]
        == 55
        and tide_derivation["periodicWrapUsed"] is False
        and tide_derivation["constantFreezeUsed"] is False
        and tide_derivation["unpublishedExtrapolationUsed"] is False,
        binding(TIDE_EXTENSION),
    )
    c2a_fields = load_npz(C2A_FIELDS)
    region_keys = sorted(
        name
        for name in c2a_fields
        if name.startswith("region_mask__")
    )
    add(
        checks,
        "C2b_comparison_mapping_and_seven_regions_are_available",
        c2a_fields["formal_to_candidate_C_cell_id"].shape == (44880,)
        and len(region_keys) == 7
        and all(
            c2a_fields[name].shape == (44880,)
            and np.any(c2a_fields[name])
            for name in region_keys
        ),
        region_keys,
    )
    add(
        checks,
        "C1_runner_authority_is_unchanged",
        sha256(
            ROOT / "tools/run_stage20_barrage_C1_local_transition_600s_v1.py"
        )
        == EXPECTED_C1_RUNNER_SHA,
        sha256(
            ROOT / "tools/run_stage20_barrage_C1_local_transition_600s_v1.py"
        ),
    )
    before: dict[str, str] = {}
    protected_rows = []
    for path, expected in protected_paths().items():
        actual = sha256(path)
        before[str(path.relative_to(ROOT))] = actual
        protected_rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "expected": expected,
                "actual": actual,
                "passed": actual == expected,
            }
        )
    add(
        checks,
        "all_protected_runtime_inputs_match",
        all(row["passed"] for row in protected_rows),
        protected_rows,
    )
    add(
        checks,
        "no_solver_run_archive_exists_before_first_execution",
        not any(path.exists() for path in RUN_ARCHIVES.values())
        and not any(path.exists() for path in RUN_REPORT_PATHS.values())
        and not RAW_RUN_REPORTS.exists()
        and not MANIFEST.exists(),
        {
            "runArchives": {
                key: path.exists() for key, path in RUN_ARCHIVES.items()
            },
            "runReports": {
                key: path.exists()
                for key, path in RUN_REPORT_PATHS.items()
            },
            "rawRunReports": RAW_RUN_REPORTS.exists(),
            "manifest": MANIFEST.exists(),
        },
    )
    add(
        checks,
        "deferred_scopes_remain_excluded",
        {
            "C3_execution",
            "remaining_gate_sequence_execution",
            "emergency_or_nonoperational_stress_cases",
            "production_mesh_adoption",
            "precomputation",
            "public_runtime_change",
            "main_merge",
        }
        <= set(approval["doesNotAuthorize"]),
        approval["doesNotAuthorize"],
    )
    failed = [row["id"] for row in checks if not row["passed"]]
    result = {
        "schema": "onga-stage20-barrage-candidate-C-C2b-S1-all-closed-settling-preflight-v1",
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "safeguards": {
            "preflightOnly": True,
            "solverRunCount": 0,
            "C3RunStarted": False,
            "remainingGateRunStarted": False,
            "precomputationRun": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
    }
    write_json(PREFLIGHT, result)
    if failed:
        raise RuntimeError(f"C2b-S1 all-closed preflight failed: {failed}")
    return result, before


def run_c2b_continuation(
    mesh_id: str,
    initial_state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    geometry: dict[str, np.ndarray],
    p2: tuple[np.ndarray, np.ndarray],
    source: dict[str, Any],
    tide_candidate: dict[str, Any],
) -> tuple[list[np.ndarray], dict[str, Any], dict[str, np.ndarray]]:
    state = initial_state.copy()
    workspace = c1.build_mapping_workspace(geometry)
    alpha = c2b_capacity_at_elapsed(0.0)
    c1.update_mapping_workspace(workspace, alpha)
    target_seconds = 600.0
    checkpoint_interval = 10.0
    cfl_target = 0.12

    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
    checkpoint_count = 61
    capacity_checkpoints = np.zeros((checkpoint_count, 8), dtype=np.float64)
    flux_names = (
        "openLeftM3S",
        "openRightM3S",
        "wallLeftM3S",
        "wallRightM3S",
        "blendedLeftM3S",
        "blendedRightM3S",
        "leftPlusRightResidualM3S",
    )
    flux_checkpoints = {
        name: np.zeros((checkpoint_count, 8), dtype=np.float64)
        for name in flux_names
    }
    relative_times = np.zeros(checkpoint_count, dtype=np.float64)
    absolute_times = np.zeros(checkpoint_count, dtype=np.float64)
    snapshots = [state.copy()]
    relative_times[0] = 0.0
    absolute_times[0] = 3600.0
    capacity_checkpoints[0] = alpha
    flux, mapping_exact = c1.record_checkpoint(
        state,
        bed,
        geometry,
        workspace,
        alpha,
    )
    for name in flux_names:
        flux_checkpoints[name][0] = flux[name]
    mapping_exact_count = int(mapping_exact)

    elapsed = 0.0
    step = 0
    next_checkpoint_index = 1
    next_checkpoint = checkpoint_interval
    next_progress = 100.0
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_fishway_source_residual = 0.0
    maximum_gate_mass_residual = 0.0
    maximum_gate_face_mass_residual = 0.0
    minimum_effective_q = math.inf
    maximum_effective_q = 0.0
    minimum_capacity = float(np.min(alpha))
    maximum_capacity = float(np.max(alpha))
    maximum_capacity_change_per_step = 0.0
    previous_alpha = alpha.copy()
    tide_clock_start = (
        float(source["contract"]["run"]["tideCurveStartHour"]) * 3600.0
        + float(read_json(c1.short.SOURCE_REPORT)["run"]["simulatedSeconds"])
        + 3600.0
    )
    wall_start = time.monotonic()
    print(
        json.dumps(
            {
                "event": "C2b_S1_run_started",
                "meshId": mesh_id,
                "initialAbsoluteTimeS": 3600,
                "targetAbsoluteTimeS": 4200,
                "continuationSeconds": 600,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    while elapsed < target_seconds - 1e-12:
        alpha = c2b_capacity_at_elapsed(elapsed)
        c1.update_mapping_workspace(workspace, alpha)
        maximum_capacity_change_per_step = max(
            maximum_capacity_change_per_step,
            float(np.max(np.abs(alpha - previous_alpha))),
        )
        previous_alpha[:] = alpha
        minimum_capacity = min(minimum_capacity, float(np.min(alpha)))
        maximum_capacity = max(maximum_capacity, float(np.max(alpha)))
        gate_residual, gate_face_residual = c1._maximum_gate_mass_residual(
            state,
            bed,
            geometry["left"],
            geometry["right"],
            workspace["effectiveLengths"],
            geometry["internalNormals"],
            workspace["multipliers"],
            workspace["gateFaceIds"],
        )
        maximum_gate_mass_residual = max(
            maximum_gate_mass_residual,
            float(gate_residual),
        )
        maximum_gate_face_mass_residual = max(
            maximum_gate_face_mass_residual,
            float(gate_face_residual),
        )
        stop_at = min(target_seconds, next_checkpoint)
        maximum_dt = stop_at - elapsed
        tide_target = tide_anomaly_s1(
            tide_clock_start + elapsed,
            source["tide"],
            tide_candidate,
        )
        (
            state,
            dt,
            cfl,
            boundary_outflow,
            effective_q,
            fishway_source_residual,
        ) = c1.short._advance_h2_step(
            state,
            bed,
            manning,
            geometry["areas"],
            geometry["inverseAreas"],
            geometry["left"],
            geometry["right"],
            workspace["effectiveLengths"],
            geometry["internalNormals"],
            workspace["multipliers"],
            geometry["boundaryCells"],
            geometry["boundaryLengths"],
            geometry["boundaryNormals"],
            geometry["boundaryTags"],
            tide_target,
            target_flux_by_tag,
            p2[0],
            p2[1],
            0.25,
            cfl_target,
            maximum_dt,
        )
        elapsed += dt
        step += 1
        expected_volume -= dt * boundary_outflow
        actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        mass_error = abs(actual_volume - expected_volume) / max(
            abs(initial_volume),
            1.0,
        )
        maximum_cfl = max(maximum_cfl, float(cfl))
        maximum_mass_error = max(maximum_mass_error, mass_error)
        maximum_fishway_source_residual = max(
            maximum_fishway_source_residual,
            abs(float(fishway_source_residual)),
        )
        minimum_effective_q = min(minimum_effective_q, float(effective_q))
        maximum_effective_q = max(maximum_effective_q, float(effective_q))

        if (
            elapsed >= next_checkpoint - 1e-10
            or elapsed >= target_seconds - 1e-10
        ):
            c1.require(
                next_checkpoint_index < checkpoint_count,
                "too many C2b-S1 all-closed checkpoints",
            )
            alpha = c2b_capacity_at_elapsed(elapsed)
            c1.update_mapping_workspace(workspace, alpha)
            snapshots.append(state.copy())
            relative_times[next_checkpoint_index] = elapsed
            absolute_times[next_checkpoint_index] = 3600.0 + elapsed
            capacity_checkpoints[next_checkpoint_index] = alpha
            flux, mapping_exact = c1.record_checkpoint(
                state,
                bed,
                geometry,
                workspace,
                alpha,
            )
            for name in flux_names:
                flux_checkpoints[name][next_checkpoint_index] = flux[name]
            mapping_exact_count += int(mapping_exact)
            next_checkpoint_index += 1
            next_checkpoint += checkpoint_interval
            if elapsed >= next_progress - 1e-10:
                print(
                    json.dumps(
                        {
                            "event": "C2b_S1_run_progress",
                            "meshId": mesh_id,
                            "absoluteTimeS": round(3600.0 + elapsed, 9),
                            "percent": round(100.0 * elapsed / target_seconds, 1),
                            "steps": step,
                            "wallSeconds": round(time.monotonic() - wall_start, 3),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                next_progress += 100.0

    c1.require(
        next_checkpoint_index == checkpoint_count,
        "missing C2b-S1 all-closed checkpoints",
    )
    depth = state[:, 0]
    speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(
        depth,
        1e-12,
    )
    report = {
        "meshId": mesh_id,
        "initialAbsoluteTimeS": 3600.0,
        "finalAbsoluteTimeS": 3600.0 + elapsed,
        "simulatedContinuationSeconds": elapsed,
        "stepsCompleted": step,
        "wallSeconds": time.monotonic() - wall_start,
        "checkpointCount": checkpoint_count,
        "relativeCheckpointTimesS": relative_times.tolist(),
        "absoluteCheckpointTimesS": absolute_times.tolist(),
        "checkpointMappingIdentityCount": mapping_exact_count,
        "checkpointMappingIdentityAllPassed":
            mapping_exact_count == checkpoint_count,
        "gateMassResidualEvaluatedAtEveryStep": True,
        "gateMassResidualEvaluationCount": step,
        "maximumAbsoluteSummedLeftPlusRightGateMassResidualM3S":
            maximum_gate_mass_residual,
        "maximumAbsolutePerFaceLeftPlusRightGateMassResidualM3S":
            maximum_gate_face_mass_residual,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "maximumAbsoluteFishwayMassSourceResidualM3S":
            maximum_fishway_source_residual,
        "minimumEffectiveFishwayDischargeM3S": minimum_effective_q,
        "maximumEffectiveFishwayDischargeM3S": maximum_effective_q,
        "fishwayQ0WasCapped": minimum_effective_q < 0.25 - 1e-12,
        "minimumCapacityFraction": minimum_capacity,
        "maximumCapacityFraction": maximum_capacity,
        "maximumCapacityChangePerAdaptiveStep":
            maximum_capacity_change_per_step,
        "minimumDepthM": float(depth.min()),
        "maximumDepthM": float(depth.max()),
        "maximumSpeedMPS": float(speed.max()),
        "negativeDepthCount": int(np.sum(depth < 0.0)),
        "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
    }
    fields = {
        "relativeCheckpointTimeS": relative_times,
        "absoluteCheckpointTimeS": absolute_times,
        "capacityFractionByGateId": capacity_checkpoints,
        **{
            f"gateFlux__{name}": values
            for name, values in flux_checkpoints.items()
        },
    }
    print(
        json.dumps(
            {
                "event": "C2b_S1_run_complete",
                "meshId": mesh_id,
                "steps": step,
                "wallSeconds": round(report["wallSeconds"], 3),
                "maximumCfl": report["maximumCfl"],
                "maximumRelativeMassBalanceError":
                    report["maximumRelativeMassBalanceError"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return snapshots, report, fields


def save_run(
    mesh_id: str,
    snapshots: list[np.ndarray],
    report: dict[str, Any],
    fields: dict[str, np.ndarray],
) -> None:
    archive = RUN_ARCHIVES[mesh_id]
    report_path = RUN_REPORT_PATHS[mesh_id]
    states = np.stack(snapshots).astype(np.float32)
    np.savez_compressed(
        archive,
        state_H_HU_HV=states,
        **fields,
    )
    write_json(report_path, report)
    completed = [
        key
        for key in MESH_IDS
        if RUN_ARCHIVES[key].is_file()
        and RUN_REPORT_PATHS[key].is_file()
    ]
    write_json(
        JOURNAL,
        {
            "schema": "onga-stage20-barrage-candidate-C-C2b-S1-execution-journal-v1",
            "version": 1,
            "status": "RUNNING" if len(completed) < 2 else "RUNS_COMPLETE",
            "completedMeshIds": completed,
            "completedRunCount": len(completed),
            "authorizedRunCount": 2,
            "bindings": {
                key: {
                    "archive": binding(RUN_ARCHIVES[key]),
                    "report": binding(RUN_REPORT_PATHS[key]),
                }
                for key in completed
            },
            "safeguards": {
                "C3RunStarted": False,
                "remainingGateRunStarted": False,
                "precomputationRun": False,
                "publicRuntimeChanged": False,
                "mainMerged": False,
            },
        },
    )


def load_saved_run(
    mesh_id: str,
) -> tuple[np.ndarray, dict[str, Any], dict[str, np.ndarray]]:
    arrays = load_npz(RUN_ARCHIVES[mesh_id])
    report = read_json(RUN_REPORT_PATHS[mesh_id])
    fields = {
        name: values
        for name, values in arrays.items()
        if name != "state_H_HU_HV"
    }
    return arrays["state_H_HU_HV"], report, fields


def assemble_results(
    records: dict[str, dict[str, Any]],
    protected_before: dict[str, str],
) -> None:
    formal_states, formal_report, formal_fields = load_saved_run("formalR20")
    candidate_states, candidate_report, candidate_fields = load_saved_run("candidateC")
    reports = [formal_report, candidate_report]
    c1.require(
        formal_states.shape == (61, 44880, 3)
        and candidate_states.shape == (61, 34940, 3),
        "saved C2b-S1 checkpoint state shape changed",
    )
    c1.require(
        np.array_equal(
            formal_fields["absoluteCheckpointTimeS"],
            candidate_fields["absoluteCheckpointTimeS"],
        )
        and np.array_equal(
            formal_fields["capacityFractionByGateId"],
            candidate_fields["capacityFractionByGateId"],
        ),
        "C2b-S1 mesh checkpoint axes or capacity schedules differ",
    )
    times = formal_fields["absoluteCheckpointTimeS"]
    capacity = formal_fields["capacityFractionByGateId"]
    c2a_fields = load_npz(C2A_FIELDS)
    formal_to_candidate = c2a_fields["formal_to_candidate_C_cell_id"].astype(
        np.int64
    )
    region_ids = [
        name[len("region_mask__"):]
        for name in c2a_fields
        if name.startswith("region_mask__")
    ]
    regions = {
        region_id: c2a_fields[f"region_mask__{region_id}"].astype(bool)
        for region_id in region_ids
    }
    eta_rmse = np.zeros((61, len(region_ids)), dtype=np.float64)
    velocity_rmse = np.zeros_like(eta_rmse)
    final_eta_error: np.ndarray | None = None
    final_velocity_error: np.ndarray | None = None
    warnings = []
    screening_rows = []
    for time_index, absolute_time in enumerate(times):
        measured, eta_error, velocity_error = c1.comparison_values(
            formal_states[time_index].astype(np.float64),
            records["formalR20"]["bed"],
            candidate_states[time_index].astype(np.float64),
            records["candidateC"]["bed"],
            formal_to_candidate,
            records["formalR20"]["geometry"]["areas"],
            regions,
        )
        for region_index, region_id in enumerate(region_ids):
            row = measured[region_id]
            eta = float(row["waterSurfaceElevationRmseM"])
            velocity = float(row["velocityVectorRmseMPS"])
            eta_rmse[time_index, region_index] = eta
            velocity_rmse[time_index, region_index] = velocity
            screen = {
                "absoluteTimeS": float(absolute_time),
                "regionId": region_id,
                "waterSurfaceElevationRmseM": eta,
                "velocityVectorRmseMPS": velocity,
                "waterSurfaceGuideExceeded": eta > 0.1,
                "velocityGuideExceeded": velocity > 0.01,
            }
            screening_rows.append(screen)
            if screen["waterSurfaceGuideExceeded"] or screen["velocityGuideExceeded"]:
                warnings.append(screen)
        if time_index == 60:
            final_eta_error = eta_error
            final_velocity_error = velocity_error
    c1.require(
        final_eta_error is not None and final_velocity_error is not None,
        "missing final C2b-S1 comparison fields",
    )

    flux_names = (
        "openLeftM3S",
        "openRightM3S",
        "wallLeftM3S",
        "wallRightM3S",
        "blendedLeftM3S",
        "blendedRightM3S",
        "leftPlusRightResidualM3S",
    )
    field_arrays: dict[str, np.ndarray] = {
        "case_ids": np.asarray(
            ["all_main_gates_closed_settling_extension"],
            dtype="<U64",
        ),
        "gate_ids": np.arange(1, 9, dtype=np.int16),
        "region_ids": np.asarray(region_ids, dtype="<U64"),
        "checkpoint_time_s": times,
        "relative_checkpoint_time_s":
            formal_fields["relativeCheckpointTimeS"],
        "capacity_fraction_by_case_checkpoint_gate":
            capacity[np.newaxis, :, :],
        "formal_vs_candidate_C_water_surface_elevation_rmse_m":
            eta_rmse[np.newaxis, :, :],
        "formal_vs_candidate_C_velocity_vector_rmse_mps":
            velocity_rmse[np.newaxis, :, :],
        "formal_R20_final_state_by_case":
            formal_states[-1][np.newaxis, :, :],
        "candidate_C_final_state_by_case":
            candidate_states[-1][np.newaxis, :, :],
        "final_water_surface_elevation_error_m":
            final_eta_error[np.newaxis, :].astype(np.float32),
        "final_velocity_vector_error_mps":
            final_velocity_error[np.newaxis, :].astype(np.float32),
        "formal_R20_centroids_m":
            records["formalR20"]["geometry"]["centroids"],
        "formal_R20_cell_area_m2":
            records["formalR20"]["geometry"]["areas"],
        "formal_to_candidate_C_cell_id": formal_to_candidate,
    }
    for name in flux_names:
        field_arrays[f"formalR20__gate_flux__{name}"] = formal_fields[
            f"gateFlux__{name}"
        ][np.newaxis, :, :]
        field_arrays[f"candidateC__gate_flux__{name}"] = candidate_fields[
            f"gateFlux__{name}"
        ][np.newaxis, :, :]
    for region_id, mask in regions.items():
        field_arrays[f"region_mask__{region_id}"] = mask.astype(np.uint8)
    np.savez_compressed(FIELDS, **field_arrays)
    np.savez_compressed(
        CHECKPOINT_STATES,
        checkpoint_time_s=times,
        relative_checkpoint_time_s=formal_fields[
            "relativeCheckpointTimeS"
        ],
        formal_R20_state_H_HU_HV=formal_states,
        candidate_C_state_H_HU_HV=candidate_states,
    )
    write_json(
        RAW_RUN_REPORTS,
        {
            "schema": "onga-stage20-barrage-candidate-C-C2b-S1-raw-run-reports-v1",
            "version": 1,
            "status": "COMPLETE",
            "runs": [
                {"meshId": "formalR20", "report": formal_report},
                {"meshId": "candidateC", "report": candidate_report},
            ],
        },
    )

    transition_windows = {
        "allMainGatesClosedSettlingExtension3600To4200": (3600.0, 4200.0),
    }
    window_summaries = {}
    for name, (start, end) in transition_windows.items():
        selected = (times >= start) & (times <= end)
        window_summaries[name] = {
            "absolutePeriodS": [start, end],
            "maximumWaterSurfaceElevationRmseM": float(
                np.max(eta_rmse[selected])
            ),
            "maximumVelocityVectorRmseMPS": float(
                np.max(velocity_rmse[selected])
            ),
            "warningEventCount": sum(
                start <= row["absoluteTimeS"] <= end
                for row in warnings
            ),
        }
    warning_times = sorted(
        {float(row["absoluteTimeS"]) for row in warnings}
    )
    c2a_last_eta = c2a_fields[
        "formal_vs_candidate_C_water_surface_elevation_rmse_m"
    ][0, -1]
    c2a_last_velocity = c2a_fields[
        "formal_vs_candidate_C_velocity_vector_rmse_mps"
    ][0, -1]
    seam_regression = {
        "waterSurfaceElevationRmseMaximumDifferenceM": float(
            np.max(np.abs(eta_rmse[0] - c2a_last_eta))
        ),
        "velocityVectorRmseMaximumDifferenceMPS": float(
            np.max(np.abs(velocity_rmse[0] - c2a_last_velocity))
        ),
        "formalStateFloat32Exact": bool(
            np.array_equal(
                formal_states[0],
                load_npz(C2A_CHECKPOINTS)[
                    "formal_R20_state_H_HU_HV"
                ][-1],
            )
        ),
        "candidateStateFloat32Exact": bool(
            np.array_equal(
                candidate_states[0],
                load_npz(C2A_CHECKPOINTS)[
                    "candidate_C_state_H_HU_HV"
                ][-1],
            )
        ),
        "derivedComparisonToleranceMOrMPS": 1e-7,
        "toleranceBasis": (
            "C2b comparison fields were computed before float32 checkpoint "
            "archival; C2b-S1 seam metrics are recomputed from the exact archived "
            "states, so derived metric agreement uses a float32-scale tolerance "
            "while state equality remains exact"
        ),
    }
    maximum_cfl = max(report["maximumCfl"] for report in reports)
    maximum_mass_error = max(
        report["maximumRelativeMassBalanceError"] for report in reports
    )
    maximum_gate_residual = max(
        max(
            report[
                "maximumAbsoluteSummedLeftPlusRightGateMassResidualM3S"
            ],
            report[
                "maximumAbsolutePerFaceLeftPlusRightGateMassResidualM3S"
            ],
        )
        for report in reports
    )
    maximum_fishway_residual = max(
        report["maximumAbsoluteFishwayMassSourceResidualM3S"]
        for report in reports
    )
    formal_wall = formal_report["wallSeconds"]
    candidate_wall = candidate_report["wallSeconds"]
    runtime_reduction = 100.0 * (formal_wall - candidate_wall) / formal_wall
    nishikawa_index = region_ids.index("nishikawaConfluenceWithin150M")
    nishikawa_velocity = velocity_rmse[:, nishikawa_index]
    nishikawa_peak_index = int(np.argmax(nishikawa_velocity))
    last_300s = times >= 3900.0
    nishikawa_last_300s_slope = float(
        np.polyfit(times[last_300s], nishikawa_velocity[last_300s], 1)[0]
    )
    nishikawa_last_60s_change = float(
        nishikawa_velocity[-1] - nishikawa_velocity[-7]
    )
    protected_after = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in protected_paths()
    }
    summary = {
        "schema": "onga-stage20-barrage-candidate-C-C2b-S1-all-closed-settling-v1",
        "version": 1,
        "status": (
            "C2B_S1_COMPLETE_NUMERICALLY_SAFE_COMPARISON_WARNING_PENDING_USER_REVIEW"
            if warnings
            else "C2B_S1_COMPLETE_NUMERICALLY_SAFE_PENDING_USER_REVIEW"
        ),
        "scope": {
            "stageId": "candidate_C_C2b_S1_all_closed_settling_3600_to_4200",
            "meshCount": 2,
            "caseCount": 1,
            "solverRunCount": 2,
            "continuationPhysicalSecondsPerRun": 600.0,
            "checkpointIntervalS": 10.0,
            "checkpointCountPerRunIncludingInitial": 61,
            "rerunZeroTo3600": False,
            "extremeOperationalCaseUsed": False,
            "C3RunStarted": False,
            "remainingGateRunStarted": False,
            "productionMeshAdoptionAuthorized": False,
        },
        "operation": {
            "initialOpenGates": [],
            "gateTransition": False,
            "settlingExtensionAbsoluteS": [3600.0, 4200.0],
            "finalOpenGates": [],
            "fishwayP2AlwaysActive": True,
        },
        "mesh": {
            "formalR20": {
                "cellCount": 44880,
                "wallSeconds": formal_wall,
            },
            "candidateC": {
                "cellCount": 34940,
                "wallSeconds": candidate_wall,
            },
            "cellReductionPercent":
                100.0 * (44880 - 34940) / 44880,
            "runtimeReductionPercent": runtime_reduction,
        },
        "numericalSafety": {
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error,
            "maximumAbsoluteGateMassResidualM3S": maximum_gate_residual,
            "maximumAbsoluteFishwayMassSourceResidualM3S":
                maximum_fishway_residual,
            "negativeDepthCount": sum(
                report["negativeDepthCount"] for report in reports
            ),
            "nonFiniteValueCount": sum(
                report["nonFiniteValueCount"] for report in reports
            ),
        },
        "comparisonReview": {
            "regionCount": len(region_ids),
            "checkpointCount": len(times),
            "comparisonCountPerMetric": int(len(times) * len(region_ids)),
            "guides": {
                "waterSurfaceElevationRmseM": 0.1,
                "velocityVectorRmseMPS": 0.01,
                "role": "visible_warning_and_regression_reference_not_field_calibrated_hard_acceptance_limits",
                "automaticMeshRejection": False,
            },
            "warningCount": len(warnings),
            "warningTimesS": warning_times,
            "warnings": warnings,
            "maximumWaterSurfaceElevationRmseM": float(np.max(eta_rmse)),
            "maximumVelocityVectorRmseMPS": float(
                np.max(velocity_rmse)
            ),
            "windowSummaries": window_summaries,
            "at4200s": {
                "maximumWaterSurfaceElevationRmseM": float(
                    np.max(eta_rmse[-1])
                ),
                "maximumVelocityVectorRmseMPS": float(
                    np.max(velocity_rmse[-1])
                ),
                "P2WaterSurfaceElevationRmseM": float(
                    eta_rmse[-1, region_ids.index("fishwayP2Footprints")]
                ),
                "P2VelocityVectorRmseMPS": float(
                    velocity_rmse[
                        -1,
                        region_ids.index("fishwayP2Footprints"),
                    ]
                ),
            },
            "nishikawaConvergence": {
                "initialVelocityVectorRmseMPS": float(
                    nishikawa_velocity[0]
                ),
                "peakVelocityVectorRmseMPS": float(
                    nishikawa_velocity[nishikawa_peak_index]
                ),
                "peakAbsoluteTimeS": float(times[nishikawa_peak_index]),
                "finalVelocityVectorRmseMPS": float(
                    nishikawa_velocity[-1]
                ),
                "last300sLinearSlopeMPSPerS":
                    nishikawa_last_300s_slope,
                "last60sChangeMPS": nishikawa_last_60s_change,
                "atOrBelowGuideAt4200s":
                    bool(nishikawa_velocity[-1] <= 0.01),
                "decreasingOverLast60s":
                    bool(nishikawa_last_60s_change < 0.0),
            },
        },
        "C2bSeamRegression": seam_regression,
        "runs": {
            "formalR20": formal_report,
            "candidateC": candidate_report,
            "totalWallSeconds": formal_wall + candidate_wall,
        },
        "bindings": {
            "approval": binding(APPROVAL),
            "plan": binding(PLAN),
            "MBoundaryTideNextHourExtension": binding(TIDE_EXTENSION),
            "C2bCheckpointStates": binding(C2A_CHECKPOINTS),
            "C2bDiagnosticFields": binding(C2A_FIELDS),
            "formalR20Mesh": binding(FORMAL_MESH),
            "candidateCReviewMesh": binding(CANDIDATE_MESH),
            "formalRunArchive": binding(FORMAL_RUN),
            "candidateRunArchive": binding(CANDIDATE_RUN),
            "diagnosticFields": binding(FIELDS),
            "checkpointStates": binding(CHECKPOINT_STATES),
            "rawRunReports": binding(RAW_RUN_REPORTS),
        },
        "safeguards": {
            "protectedBefore": protected_before,
            "protectedAfter": protected_after,
            "protectedInputsUnchanged":
                protected_before == protected_after,
            "additionalSolverRunBeyondApprovedTwo": False,
            "rerunZeroTo3600": False,
            "C3RunStarted": False,
            "remainingGateRunStarted": False,
            "productionMeshAdopted": False,
            "solverChanged": False,
            "guiChanged": False,
            "precomputationRun": False,
            "responsePackChanged": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
        "nextDecision": (
            "review_the_C2b_S1_result_figure_and_decide_whether_to_record_"
            "C2b_pass_or_hold_for_local_mesh_revision"
        ),
    }

    plan = read_json(PLAN)
    hard = plan["hardNumericalAcceptance"]
    checks: list[dict[str, Any]] = []
    add(
        checks,
        "exactly_two_approved_solver_runs_completed",
        {report["meshId"] for report in reports}
        == {"formalR20", "candidateC"}
        and len(reports) == 2,
        [report["meshId"] for report in reports],
    )
    add(
        checks,
        "both_runs_are_exactly_600s_continuations",
        all(
            report["simulatedContinuationSeconds"] == 600.0
            and report["initialAbsoluteTimeS"] == 3600.0
            and report["finalAbsoluteTimeS"] == 4200.0
            for report in reports
        ),
        [
            {
                "meshId": report["meshId"],
                "continuationS": report[
                    "simulatedContinuationSeconds"
                ],
                "finalAbsoluteTimeS": report["finalAbsoluteTimeS"],
            }
            for report in reports
        ],
    )
    add(
        checks,
        "both_runs_recorded_all_61_absolute_checkpoints",
        all(report["checkpointCount"] == 61 for report in reports)
        and np.array_equal(times, np.arange(3600.0, 4201.0, 10.0)),
        times.tolist(),
    )
    add(
        checks,
        "C2b_3600s_checkpoint_is_the_exact_C2b_S1_initial_state",
        seam_regression["formalStateFloat32Exact"]
        and seam_regression["candidateStateFloat32Exact"],
        seam_regression,
    )
    add(
        checks,
        "C2b_to_C2b_S1_derived_comparison_seam_is_within_float32_archive_tolerance",
        seam_regression[
            "waterSurfaceElevationRmseMaximumDifferenceM"
        ]
        <= seam_regression["derivedComparisonToleranceMOrMPS"]
        and seam_regression[
            "velocityVectorRmseMaximumDifferenceMPS"
        ]
        <= seam_regression["derivedComparisonToleranceMOrMPS"],
        seam_regression,
    )
    expected_capacity = np.stack(
        [
            c2b_capacity_at_elapsed(value)
            for value in np.arange(0.0, 601.0, 10.0)
        ]
    )
    add(
        checks,
        "capacity_schedule_is_all_closed_for_all_61_checkpoints",
        np.array_equal(capacity, expected_capacity)
        and np.array_equal(
            capacity,
            np.zeros((61, 8)),
        ),
        {
            "initial": capacity[0].tolist(),
            "final": capacity[-1].tolist(),
        },
    )
    add(
        checks,
        "normal_gate_transitions_do_not_overlap",
        np.max(
            np.sum(
                np.logical_and(capacity > 0.0, capacity < 1.0),
                axis=1,
            )
        )
        <= 1,
    )
    add(
        checks,
        "continuous_mapping_matches_at_all_122_checkpoints",
        all(
            report["checkpointMappingIdentityAllPassed"]
            and report["checkpointMappingIdentityCount"] == 61
            for report in reports
        ),
        [
            report["checkpointMappingIdentityCount"]
            for report in reports
        ],
    )
    add(
        checks,
        "gate_mass_residual_was_evaluated_at_every_step",
        all(
            report["gateMassResidualEvaluatedAtEveryStep"]
            and report["gateMassResidualEvaluationCount"]
            == report["stepsCompleted"]
            for report in reports
        ),
    )
    add(
        checks,
        "maximum_CFL_within_hard_limit",
        maximum_cfl <= float(hard["maximumCfl"]),
        maximum_cfl,
    )
    add(
        checks,
        "relative_mass_balance_error_within_hard_limit",
        maximum_mass_error
        <= float(hard["maximumRelativeMassBalanceError"]),
        maximum_mass_error,
    )
    add(
        checks,
        "gate_mass_residual_within_hard_limit",
        maximum_gate_residual
        <= float(hard["maximumAbsoluteGateMassResidualM3S"]),
        maximum_gate_residual,
    )
    add(
        checks,
        "fishway_mass_residual_within_hard_limit",
        maximum_fishway_residual
        <= float(hard["maximumAbsoluteFishwayMassSourceResidualM3S"]),
        maximum_fishway_residual,
    )
    add(
        checks,
        "fishway_remained_active_and_uncapped",
        all(
            report["minimumEffectiveFishwayDischargeM3S"] == 0.25
            and report["maximumEffectiveFishwayDischargeM3S"] == 0.25
            and not report["fishwayQ0WasCapped"]
            for report in reports
        ),
    )
    add(
        checks,
        "no_negative_depths_or_nonfinite_values",
        summary["numericalSafety"]["negativeDepthCount"] == 0
        and summary["numericalSafety"]["nonFiniteValueCount"] == 0,
        summary["numericalSafety"],
    )
    add(
        checks,
        "all_427_checkpoint_region_comparisons_recorded",
        eta_rmse.shape == (61, 7)
        and velocity_rmse.shape == (61, 7),
        {
            "waterShape": list(eta_rmse.shape),
            "velocityShape": list(velocity_rmse.shape),
        },
    )
    add(
        checks,
        "comparison_warnings_are_disclosed_not_hidden_failures",
        summary["comparisonReview"]["guides"][
            "automaticMeshRejection"
        ]
        is False
        and summary["comparisonReview"]["warningCount"]
        == len(warnings),
        len(warnings),
    )
    add(
        checks,
        "all_61_checkpoint_states_are_archived_for_both_meshes",
        formal_states.shape == (61, 44880, 3)
        and candidate_states.shape == (61, 34940, 3),
        {
            "formal": list(formal_states.shape),
            "candidateC": list(candidate_states.shape),
        },
    )
    add(
        checks,
        "protected_inputs_unchanged",
        protected_before == protected_after,
        protected_after,
    )
    add(
        checks,
        "no_C3_remaining_gate_GUI_precompute_response_public_or_main_change",
        all(
            summary["safeguards"][key] is False
            for key in (
                "C3RunStarted",
                "remainingGateRunStarted",
                "productionMeshAdopted",
                "solverChanged",
                "guiChanged",
                "precomputationRun",
                "responsePackChanged",
                "publicRuntimeChanged",
                "mainMerged",
            )
        ),
    )
    failed = [row["id"] for row in checks if not row["passed"]]
    validation = {
        "schema": "onga-stage20-barrage-candidate-C-C2b-S1-all-closed-settling-static-validation-v1",
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "warningCount": len(warnings),
    }
    write_json(VALIDATION, validation)
    summary["validation"] = {
        "status": validation["status"],
        "passed": validation["passedCount"],
        "total": validation["checkCount"],
    }
    write_json(SUMMARY, summary)
    if failed:
        raise RuntimeError(f"C2b-S1 validation failed: {failed}")
    manifest = {
        "schema": "onga-stage20-barrage-candidate-C-C2b-S1-all-closed-settling-manifest-v1",
        "version": 1,
        "status": "PASS",
        "inputs": {
            "approval": binding(APPROVAL),
            "plan": binding(PLAN),
            "MBoundaryTideNextHourExtension": binding(TIDE_EXTENSION),
            "C2bCheckpointStates": binding(C2A_CHECKPOINTS),
            "C2bDiagnosticFields": binding(C2A_FIELDS),
            "formalR20Mesh": binding(FORMAL_MESH),
            "candidateCReviewMesh": binding(CANDIDATE_MESH),
            "runnerAuthority": binding(
                ROOT
                / "tools/run_stage20_barrage_C1_local_transition_600s_v1.py"
            ),
            "diagnosticRunner": binding(Path(__file__).resolve()),
        },
        "outputs": {
            "preflightValidation": binding(PREFLIGHT),
            "executionJournal": binding(JOURNAL),
            "formalRunArchive": binding(FORMAL_RUN),
            "candidateRunArchive": binding(CANDIDATE_RUN),
            "formalRunReport": binding(FORMAL_REPORT),
            "candidateRunReport": binding(CANDIDATE_REPORT),
            "rawRunReports": binding(RAW_RUN_REPORTS),
            "diagnosticFields": binding(FIELDS),
            "checkpointStates": binding(CHECKPOINT_STATES),
            "summary": binding(SUMMARY),
            "staticValidation": binding(VALIDATION),
        },
        "safeguards": summary["safeguards"],
    }
    write_json(MANIFEST, manifest)


def execute() -> None:
    if MANIFEST.exists() or SUMMARY.exists():
        raise RuntimeError(
            "C2b-S1 result already exists; refusing additional solver runs"
        )
    preflight_result, protected_before = preflight()
    c1.require(preflight_result["status"] == "PASS", "C2b-S1 preflight failed")
    records, source, tide_candidate = load_mesh_contexts()
    for mesh_id in MESH_IDS:
        archive_exists = RUN_ARCHIVES[mesh_id].exists()
        report_exists = RUN_REPORT_PATHS[mesh_id].exists()
        c1.require(
            archive_exists == report_exists,
            f"partial saved C2b-S1 run detected: {mesh_id}",
        )
        if archive_exists:
            print(
                json.dumps(
                    {
                        "event": "C2b_S1_run_reused_after_verified_resume",
                        "meshId": mesh_id,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            continue
        snapshots, report, fields = run_c2b_continuation(
            mesh_id,
            records[mesh_id]["initialState"],
            records[mesh_id]["bed"],
            records[mesh_id]["manning"],
            records[mesh_id]["geometry"],
            records[mesh_id]["P2"],
            source,
            tide_candidate,
        )
        save_run(mesh_id, snapshots, report, fields)
    assemble_results(records, protected_before)
    result = read_json(SUMMARY)
    print(
        json.dumps(
            {
                "event": "candidate_C_C2b_S1_all_closed_settling_complete",
                "status": result["status"],
                "validation": result["validation"],
                "warningCount": result["comparisonReview"][
                    "warningCount"
                ],
                "warningTimesS": result["comparisonReview"][
                    "warningTimesS"
                ],
                "totalWallSeconds": result["runs"][
                    "totalWallSeconds"
                ],
                "summary": str(SUMMARY.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def finalize_existing_runs() -> None:
    if MANIFEST.exists():
        raise RuntimeError(
            "C2b-S1 final manifest already exists; refusing duplicate finalization"
        )
    for mesh_id in MESH_IDS:
        c1.require(
            RUN_ARCHIVES[mesh_id].is_file()
            and RUN_REPORT_PATHS[mesh_id].is_file(),
            f"missing saved C2b-S1 run for finalization: {mesh_id}",
        )
    preflight_result = read_json(PREFLIGHT)
    c1.require(
        preflight_result["status"] == "PASS",
        "saved C2b-S1 preflight did not pass",
    )
    protected_before = {
        row["path"]: row["actual"]
        for check in preflight_result["checks"]
        if check["id"] == "all_protected_runtime_inputs_match"
        for row in check["observed"]
    }
    c1.require(
        len(protected_before) == len(protected_paths()),
        "saved protected-input preflight record is incomplete",
    )
    records, _, _ = load_mesh_contexts()
    assemble_results(records, protected_before)
    result = read_json(SUMMARY)
    print(
        json.dumps(
            {
                "event": "candidate_C_C2b_S1_existing_runs_finalized",
                "solverRunCountDuringFinalization": 0,
                "status": result["status"],
                "validation": result["validation"],
                "warningCount": result["comparisonReview"][
                    "warningCount"
                ],
                "totalWallSeconds": result["runs"][
                    "totalWallSeconds"
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate the exact approved scope without starting a solver run.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute exactly the two approved continuation runs.",
    )
    parser.add_argument(
        "--finalize-existing",
        action="store_true",
        help="Finalize already saved approved runs without starting a solver.",
    )
    args = parser.parse_args()
    selected = sum(
        int(value)
        for value in (
            args.preflight_only,
            args.execute,
            args.finalize_existing,
        )
    )
    if selected != 1:
        raise RuntimeError(
            "choose exactly one of --preflight-only, --execute, "
            "or --finalize-existing"
        )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.preflight_only:
        result, _ = preflight()
        print(
            json.dumps(
                {
                    "event": "C2b_S1_preflight_complete",
                    "status": result["status"],
                    "checks": result["checkCount"],
                    "solverRunCount": 0,
                    "output": str(PREFLIGHT.relative_to(ROOT)),
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        return
    if args.finalize_existing:
        finalize_existing_runs()
        return
    execute()


if __name__ == "__main__":
    main()
