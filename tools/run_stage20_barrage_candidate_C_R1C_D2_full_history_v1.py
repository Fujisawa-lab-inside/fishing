#!/usr/bin/env python3
"""Run exactly one approved R1C D2 full-history diagnostic."""

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
import run_stage20_barrage_candidate_C_C2b_S1_all_closed_settling_v1 as s1


ROOT = Path(__file__).resolve().parents[1]
APPROVAL = (
    ROOT
    / "config/stage20_barrage_candidate_C_R1C_D2_full_history_execution_approval_v1.json"
)
PLAN = (
    ROOT
    / "config/stage20_barrage_candidate_C_R1C_D2_full_history_plan_candidate_v1.json"
)
PLAN_RESULT = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-D2-full-history-plan-v1"
)
INITIAL_STATE = PLAN_RESULT / "R1C-initial-state.npz"
SCHEDULE = PLAN_RESULT / "operation-schedule.npz"
R1C_MESH = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-next-stage-review-approval-v1"
    / "review-mesh.npz"
)
R1C_SUMMARY = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-review-mesh-v1"
    / "mesh-summary.json"
)
OUTPUT = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-D2-full-history-v1"
)
PREFLIGHT = OUTPUT / "preflight-validation.json"
RUN_ARCHIVE = OUTPUT / "R1C-full-history-checkpoints.npz"
RUN_REPORT = OUTPUT / "R1C-run-report.json"
JOURNAL = OUTPUT / "execution-journal.json"

EXPECTED_C1_RUNNER_SHA = (
    "82e8157cc7133522605611a6fcacc13871f32eeb75a15cdca6a09d1bb2a65597"
)
EXPECTED_S1_RUNNER_SHA = (
    "ca5cd5b8786614438fbac6f822e715e2ddc080315e7f77259ae8fd9166c167c7"
)


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
        return {
            name: np.asarray(archive[name]).copy()
            for name in archive.files
        }


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


def smoothstep(value: float) -> float:
    clipped = min(1.0, max(0.0, value))
    return clipped * clipped * (3.0 - 2.0 * clipped)


def capacity_at_absolute_time(absolute_time_s: float) -> np.ndarray:
    values = np.zeros(8, dtype=np.float64)
    operations = (
        (4, 0.0, 300.0, 3000.0, 3300.0),
        (3, 600.0, 900.0, 2400.0, 2700.0),
        (5, 1200.0, 1500.0, 1800.0, 2100.0),
    )
    for gate_index, open_start, open_end, close_start, close_end in operations:
        if open_start <= absolute_time_s <= open_end:
            values[gate_index] = smoothstep(
                (absolute_time_s - open_start) / (open_end - open_start)
            )
        elif open_end < absolute_time_s < close_start:
            values[gate_index] = 1.0
        elif close_start <= absolute_time_s <= close_end:
            values[gate_index] = 1.0 - smoothstep(
                (absolute_time_s - close_start) / (close_end - close_start)
            )
    return values


def protected_paths() -> dict[Path, str]:
    return s1.protected_paths()


def preflight() -> tuple[dict[str, Any], dict[str, str]]:
    approval = read_json(APPROVAL)
    plan = read_json(PLAN)
    checks: list[dict[str, Any]] = []
    scope = approval["authorizedScope"]
    add(
        checks,
        "approval_is_exactly_one_R1C_D2_run",
        approval["status"]
        == "approved_exactly_one_R1C_D2_0_to_4200s_run"
        and scope["newSolverRunCount"] == 1
        and scope["newRunMeshId"] == "candidate_C_R1C"
        and scope["referenceSolverRunCount"] == 0
        and scope["initialAbsoluteTimeS"] == 0
        and scope["finalAbsoluteTimeS"] == 4200
        and scope["physicalSeconds"] == 4200
        and scope["checkpointCountIncludingInitial"] == 421
        and scope["openingPrefix"] == [5, 4, 6]
        and scope["reverseClosingSuffix"] == [6, 4, 5]
        and scope["remainingGateIdsExcluded"] == [3, 7, 2, 8, 1],
        scope,
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
    plan_static = read_json(PLAN_RESULT / "static-validation.json")
    plan_independent = read_json(PLAN_RESULT / "independent-validation.json")
    add(
        checks,
        "D2_plan_validations_pass_37_of_37",
        plan_static["status"] == "PASS"
        and plan_static["passedCount"] == 15
        and plan_independent["status"] == "PASS"
        and plan_independent["passedCount"] == 22,
        {
            "static": [
                plan_static["status"],
                plan_static["passedCount"],
                plan_static["checkCount"],
            ],
            "independent": [
                plan_independent["status"],
                plan_independent["passedCount"],
                plan_independent["checkCount"],
            ],
        },
    )
    add(
        checks,
        "plan_and_approval_scope_match",
        plan["scope"]["newSolverRunCount"] == 1
        and plan["scope"]["physicalSeconds"] == 4200
        and plan["historyBoundary"]["openingPrefixTested"] == [5, 4, 6]
        and plan["historyBoundary"]["reverseClosingSuffixTested"]
        == [6, 4, 5]
        and scope["fishwayP2AlwaysActive"]
        and scope["fishwayQ0M3S"] == 0.25,
    )
    initial = load_npz(INITIAL_STATE)["state_H_HU_HV"]
    add(
        checks,
        "R1C_initial_state_is_exact_shape_finite_and_nonnegative",
        initial.shape == (37724, 3)
        and np.all(np.isfinite(initial))
        and np.all(initial[:, 0] >= 0.0),
        {
            "shape": list(initial.shape),
            "minimumDepthM": float(np.min(initial[:, 0])),
            "nonfinite": int(np.sum(~np.isfinite(initial))),
        },
    )
    schedule = load_npz(SCHEDULE)
    times = schedule["absolute_time_s"]
    saved = schedule["capacity_fraction_by_gate_1_to_8"]
    independent = np.stack(
        [capacity_at_absolute_time(float(value)) for value in times]
    )
    add(
        checks,
        "D2_schedule_is_exact_at_all_421_checkpoints",
        np.array_equal(times, np.arange(0.0, 4201.0, 10.0))
        and np.array_equal(saved, independent),
        float(np.max(np.abs(saved - independent))),
    )
    add(
        checks,
        "solver_authorities_are_unchanged",
        sha256(
            ROOT / "tools/run_stage20_barrage_C1_local_transition_600s_v1.py"
        )
        == EXPECTED_C1_RUNNER_SHA
        and sha256(
            ROOT
            / "tools/run_stage20_barrage_candidate_C_C2b_S1_all_closed_settling_v1.py"
        )
        == EXPECTED_S1_RUNNER_SHA,
    )
    add(
        checks,
        "M_tide_extension_authority_is_unchanged",
        sha256(s1.TIDE_EXTENSION) == s1.EXPECTED_TIDE_EXTENSION_SHA,
        sha256(s1.TIDE_EXTENSION),
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
        "no_D2_solver_result_exists_before_execution",
        not RUN_ARCHIVE.exists()
        and not RUN_REPORT.exists()
        and not JOURNAL.exists(),
        {
            "runArchive": RUN_ARCHIVE.exists(),
            "runReport": RUN_REPORT.exists(),
            "journal": JOURNAL.exists(),
        },
    )
    add(
        checks,
        "deferred_scopes_remain_excluded",
        {
            "additional_solver_run",
            "formal_R20_rerun",
            "candidate_C_rerun",
            "remaining_gate_sequence_execution",
            "production_mesh_adoption",
            "precomputation",
            "solver_change",
            "GUI_connection",
            "response_pack_change",
            "public_runtime_change",
            "main_merge",
        }
        <= set(approval["doesNotAuthorize"]),
        approval["doesNotAuthorize"],
    )
    failed = [row["id"] for row in checks if not row["passed"]]
    result = {
        "schema": "onga-stage20-barrage-candidate-C-R1C-D2-full-history-preflight-v1",
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "safeguards": {
            "preflightOnly": True,
            "newSolverRunCount": 0,
            "formalR20Rerun": False,
            "candidateCRerun": False,
            "remainingGateRunStarted": False,
            "precomputationRun": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
    }
    write_json(PREFLIGHT, result)
    if failed:
        raise RuntimeError(f"R1C D2 preflight failed: {failed}")
    return result, before


def load_context() -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, np.ndarray],
    tuple[np.ndarray, np.ndarray],
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
    mesh = c1.short.mesh_arrays(R1C_MESH)
    geometry = c1.short.build_review_geometry(mesh)
    _, bed, manning, _ = c1.short.initialize_mesh(mesh, geometry, source)
    initial = load_npz(INITIAL_STATE)["state_H_HU_HV"].astype(np.float64)
    summary = read_json(R1C_SUMMARY)
    p2 = c1.short.p2_arrays(geometry, summary, p2_polygons)
    if initial.shape != (len(geometry["triangles"]), 3):
        raise RuntimeError("R1C initial state and mesh differ")
    return initial, bed, manning, geometry, p2, source, tide_candidate


def run_full_history(
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
    alpha = capacity_at_absolute_time(0.0)
    c1.update_mapping_workspace(workspace, alpha)
    target_seconds = 4200.0
    checkpoint_interval = 10.0
    checkpoint_count = 421
    cfl_target = 0.12

    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
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
    times = np.arange(0.0, 4201.0, 10.0)
    snapshots = [state.copy()]
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
    next_progress = 300.0
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
    )
    wall_start = time.monotonic()
    print(
        json.dumps(
            {
                "event": "R1C_D2_run_started",
                "meshId": "R1C",
                "initialAbsoluteTimeS": 0,
                "targetAbsoluteTimeS": 4200,
                "physicalSeconds": 4200,
                "checkpointCount": 421,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    while elapsed < target_seconds - 1e-12:
        alpha = capacity_at_absolute_time(elapsed)
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
        tide_target = s1.tide_anomaly_s1(
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
                "too many R1C D2 checkpoints",
            )
            alpha = capacity_at_absolute_time(elapsed)
            c1.update_mapping_workspace(workspace, alpha)
            snapshots.append(state.copy())
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
                            "event": "R1C_D2_run_progress",
                            "absoluteTimeS": round(elapsed, 9),
                            "percent": round(100.0 * elapsed / target_seconds, 1),
                            "steps": step,
                            "wallSeconds": round(
                                time.monotonic() - wall_start,
                                3,
                            ),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                next_progress += 300.0

    c1.require(
        next_checkpoint_index == checkpoint_count,
        "missing R1C D2 checkpoints",
    )
    schedule = load_npz(SCHEDULE)
    c1.require(
        np.array_equal(
            capacity_checkpoints,
            schedule["capacity_fraction_by_gate_1_to_8"],
        ),
        "saved D2 capacity checkpoints differ from approved schedule",
    )
    depth = state[:, 0]
    speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(
        depth,
        1e-12,
    )
    report = {
        "meshId": "R1C",
        "initialAbsoluteTimeS": 0.0,
        "finalAbsoluteTimeS": elapsed,
        "simulatedSeconds": elapsed,
        "stepsCompleted": step,
        "wallSeconds": time.monotonic() - wall_start,
        "checkpointCount": checkpoint_count,
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
        "absoluteCheckpointTimeS": times,
        "capacityFractionByGateId": capacity_checkpoints,
        **{
            f"gateFlux__{name}": values
            for name, values in flux_checkpoints.items()
        },
    }
    print(
        json.dumps(
            {
                "event": "R1C_D2_run_complete",
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
    snapshots: list[np.ndarray],
    report: dict[str, Any],
    fields: dict[str, np.ndarray],
    protected_before: dict[str, str],
) -> None:
    np.savez_compressed(
        RUN_ARCHIVE,
        state_H_HU_HV=np.stack(snapshots).astype(np.float32),
        **fields,
    )
    write_json(RUN_REPORT, report)
    protected_after = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in protected_paths()
    }
    write_json(
        JOURNAL,
        {
            "schema": "onga-stage20-barrage-candidate-C-R1C-D2-execution-journal-v1",
            "version": 1,
            "status": "RUN_COMPLETE_AWAITING_ANALYSIS",
            "completedMeshIds": ["R1C"],
            "completedNewSolverRunCount": 1,
            "authorizedNewSolverRunCount": 1,
            "formalR20BaselineReused": True,
            "formalR20RerunCount": 0,
            "candidateCRerunCount": 0,
            "remainingGateRunCount": 0,
            "bindings": {
                "approval": binding(APPROVAL),
                "plan": binding(PLAN),
                "R1CRunArchive": binding(RUN_ARCHIVE),
                "R1CRunReport": binding(RUN_REPORT),
            },
            "safeguards": {
                "protectedBefore": protected_before,
                "protectedAfter": protected_after,
                "protectedInputsUnchanged":
                    protected_before == protected_after,
                "additionalSolverRun": False,
                "formalR20Rerun": False,
                "candidateCRerun": False,
                "remainingGateSequenceRun": False,
                "precomputationRun": False,
                "solverChanged": False,
                "guiChanged": False,
                "responsePackChanged": False,
                "publicRuntimeChanged": False,
                "mainMerged": False,
            },
        },
    )


def execute() -> None:
    if RUN_ARCHIVE.exists() or RUN_REPORT.exists() or JOURNAL.exists():
        raise RuntimeError(
            "R1C D2 result already exists; refusing an additional solver run"
        )
    preflight_result, protected_before = preflight()
    if preflight_result["status"] != "PASS":
        raise RuntimeError("R1C D2 preflight did not pass")
    context = load_context()
    snapshots, report, fields = run_full_history(*context)
    save_run(snapshots, report, fields, protected_before)
    print(
        json.dumps(
            {
                "event": "R1C_D2_execution_saved",
                "status": "RUN_COMPLETE_AWAITING_ANALYSIS",
                "wallSeconds": report["wallSeconds"],
                "runArchive": str(RUN_ARCHIVE.relative_to(ROOT)),
                "runReport": str(RUN_REPORT.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if int(args.preflight_only) + int(args.execute) != 1:
        raise RuntimeError("choose exactly one of --preflight-only or --execute")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.preflight_only:
        result, _ = preflight()
        print(
            json.dumps(
                {
                    "event": "R1C_D2_preflight_complete",
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
    execute()


if __name__ == "__main__":
    main()
