#!/usr/bin/env python3
"""Run the approved E1 formal-R20 and R1C continuations, one mesh at a time."""

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
import run_stage20_barrage_candidate_C_R1C_D2_full_history_v1 as d2


ROOT = Path(__file__).resolve().parents[1]
APPROVAL = (
    ROOT
    / "config/stage20_barrage_candidate_C_R1C_E1_remaining_gate_opening_envelope_execution_approval_v1.json"
)
PLAN = (
    ROOT
    / "config/stage20_barrage_candidate_C_R1C_E1_remaining_gate_opening_envelope_plan_candidate_v1.json"
)
PLAN_RESULT = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-E1-remaining-gate-opening-envelope-plan-v1"
)
PLAN_STATIC = PLAN_RESULT / "static-validation.json"
PLAN_INDEPENDENT = PLAN_RESULT / "independent-validation.json"
SCHEDULE = PLAN_RESULT / "operation-schedule.npz"
FORMAL_SOURCE = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-C2a-standard-opening-sequence-v1"
    / "checkpoint-states.npz"
)
FORMAL_FIELDS = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-C2a-standard-opening-sequence-v1"
    / "diagnostic-fields.npz"
)
R1C_SOURCE = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-D2-full-history-v1"
    / "R1C-full-history-checkpoints.npz"
)
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
    / "docs/results/stage20-barrage-candidate-C-R1C-E1-remaining-gate-opening-envelope-v1"
)
PREFLIGHT = OUTPUT / "preflight-validation.json"
JOURNAL = OUTPUT / "execution-journal.json"
RUN_ARCHIVES = {
    "formalR20": OUTPUT / "formal-R20-continuation-checkpoints.npz",
    "R1C": OUTPUT / "R1C-continuation-checkpoints.npz",
}
RUN_REPORTS = {
    "formalR20": OUTPUT / "formal-R20-run-report.json",
    "R1C": OUTPUT / "R1C-run-report.json",
}

EXPECTED_APPROVAL_SHA = ""
MESH_IDS = ("formalR20", "R1C")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_separated_p2_candidate() -> dict[str, Any]:
    """Project the approved artifact onto the only runtime-consumed field."""

    return read_json(c1.short.P2_CANDIDATE)["candidatePairs"]["separated"]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def add(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    observed: Any = None,
) -> None:
    row: dict[str, Any] = {
        "id": check_id,
        "status": "PASS" if passed else "FAIL",
    }
    if observed is not None:
        row["observed"] = observed
    checks.append(row)


def smoothstep(value: float) -> float:
    clipped = min(1.0, max(0.0, value))
    return clipped * clipped * (3.0 - 2.0 * clipped)


def capacity_at_absolute_time(absolute_time_s: float) -> np.ndarray:
    values = np.zeros(8, dtype=np.float64)
    values[[3, 4, 5]] = 1.0
    operations = (
        (3, 1800.0, 2100.0),
        (7, 2400.0, 2700.0),
        (2, 3000.0, 3300.0),
        (8, 3600.0, 3900.0),
        (1, 4200.0, 4500.0),
    )
    for gate_id, start, end in operations:
        values[gate_id - 1] = smoothstep(
            (absolute_time_s - start) / (end - start)
        )
    return values


def protected_paths() -> dict[Path, str]:
    return d2.protected_paths()


def load_initial_states() -> dict[str, np.ndarray]:
    formal_archive = load_npz(FORMAL_SOURCE)
    r1c_archive = load_npz(R1C_SOURCE)
    formal_time = formal_archive["checkpoint_time_s"]
    r1c_time = r1c_archive["absoluteCheckpointTimeS"]
    c1.require(
        formal_time.shape == (121,)
        and formal_time[90] == 1500.0,
        "formal R20 E1 source checkpoint changed",
    )
    c1.require(
        r1c_time.shape == (421,)
        and r1c_time[150] == 1500.0,
        "R1C E1 source checkpoint changed",
    )
    formal32 = formal_archive["formal_R20_state_H_HU_HV"][90]
    r1c32 = r1c_archive["state_H_HU_HV"][150]
    c1.require(
        formal32.shape == (44880, 3)
        and r1c32.shape == (37724, 3),
        "E1 initial state shapes changed",
    )
    formal64 = formal32.astype(np.float64)
    r1c64 = r1c32.astype(np.float64)
    c1.require(
        np.array_equal(formal64.astype(np.float32), formal32)
        and np.array_equal(r1c64.astype(np.float32), r1c32),
        "E1 float32 source values changed during float64 promotion",
    )
    return {"formalR20": formal64, "R1C": r1c64}


def load_initial_capacities() -> dict[str, np.ndarray]:
    with np.load(FORMAL_FIELDS, allow_pickle=False) as archive:
        formal = np.asarray(
            archive["capacity_fraction_by_case_checkpoint_gate"][0, 90],
            dtype=np.float64,
        )
    with np.load(R1C_SOURCE, allow_pickle=False) as archive:
        r1c = np.asarray(
            archive["capacityFractionByGateId"][150],
            dtype=np.float64,
        )
    return {"formalR20": formal, "R1C": r1c}


def load_context(
    mesh_id: str,
    initial_state: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, np.ndarray],
    tuple[np.ndarray, np.ndarray],
    dict[str, Any],
    dict[str, Any],
]:
    source, tide_candidate = c1.short.initial_condition_data()
    p2_source = load_separated_p2_candidate()
    p2_polygons = {
        side: c1.Polygon(
            c1.old.project_many(
                p2_source[side]["footprint"]["coordinates"][0][:-1]
            )
        )
        for side in ("upstream", "downstream")
    }
    mesh_path = FORMAL_MESH if mesh_id == "formalR20" else R1C_MESH
    summary_path = (
        FORMAL_SUMMARY if mesh_id == "formalR20" else R1C_SUMMARY
    )
    mesh = c1.short.mesh_arrays(mesh_path)
    geometry = c1.short.build_review_geometry(mesh)
    _, bed, manning, _ = c1.short.initialize_mesh(
        mesh,
        geometry,
        source,
    )
    summary = read_json(summary_path)
    p2 = c1.short.p2_arrays(geometry, summary, p2_polygons)
    c1.require(
        initial_state.shape == (len(geometry["triangles"]), 3),
        f"E1 initial state and mesh differ: {mesh_id}",
    )
    return (
        initial_state,
        bed,
        manning,
        geometry,
        p2,
        source,
        tide_candidate,
    )


def preflight() -> tuple[dict[str, Any], dict[str, str]]:
    approval = read_json(APPROVAL)
    plan = read_json(PLAN)
    checks: list[dict[str, Any]] = []
    scope = approval["authorizedScope"]
    add(
        checks,
        "approval_is_exactly_two_E1_1500_to_4800s_runs",
        approval["status"]
        == "approved_exactly_two_E1_1500_to_4800s_runs"
        and approval["userEvidence"]["text"]
        == "E1の正式R20・R1C各1走（1500〜4800秒、合計40〜50分）を承認する"
        and scope["newSolverRunCount"] == 2
        and scope["meshIds"] == ["formalR20", "candidate_C_R1C"]
        and scope["runCountPerMesh"] == 1
        and scope["initialAbsoluteTimeS"] == 1500
        and scope["finalAbsoluteTimeS"] == 4800
        and scope["physicalSecondsPerRun"] == 3300
        and scope["checkpointCountPerRunIncludingInitial"] == 331,
        scope,
    )
    approval_bindings = []
    for name, item in approval["bindings"].items():
        path = Path(item["path"])
        if not path.is_absolute():
            path = ROOT / path
        actual = sha256(path) if path.is_file() else None
        approval_bindings.append(
            {
                "name": name,
                "path": item["path"],
                "expected": item["sha256"],
                "actual": actual,
                "passed": actual == item["sha256"],
            }
        )
    add(
        checks,
        "all_approval_bindings_match",
        all(item["passed"] for item in approval_bindings),
        approval_bindings,
    )
    add(
        checks,
        "exact_plan_hash_matches_execution_approval",
        sha256(PLAN) == approval["bindings"]["exactPlan"]["sha256"],
        sha256(PLAN),
    )
    static = read_json(PLAN_STATIC)
    independent = read_json(PLAN_INDEPENDENT)
    add(
        checks,
        "E1_plan_validations_pass_50_of_50",
        static["status"] == "PASS"
        and static["passedCount"] == 34
        and independent["status"] == "PASS"
        and independent["passedCount"] == 16,
        {
            "static": [
                static["status"],
                static["passedCount"],
                static["checkCount"],
            ],
            "independent": [
                independent["status"],
                independent["passedCount"],
                independent["checkCount"],
            ],
        },
    )
    add(
        checks,
        "plan_and_approval_scopes_match",
        plan["scope"]["newSolverRunCount"]
        == scope["newSolverRunCount"]
        and plan["scope"]["initialAbsoluteTimeS"]
        == scope["initialAbsoluteTimeS"]
        and plan["scope"]["finalAbsoluteTimeS"]
        == scope["finalAbsoluteTimeS"]
        and plan["scope"]["remainingOpeningOrderTested"]
        == scope["remainingOpeningOrder"]
        and plan["hydraulicContract"]["fishwayQ0M3S"]
        == scope["fishwayQ0M3S"],
        {
            "planScope": plan["scope"],
            "approvalScope": scope,
        },
    )
    initial = load_initial_states()
    add(
        checks,
        "both_1500s_initial_states_are_exact_shape_finite_nonnegative",
        initial["formalR20"].shape == (44880, 3)
        and initial["R1C"].shape == (37724, 3)
        and np.isfinite(initial["formalR20"]).all()
        and np.isfinite(initial["R1C"]).all()
        and np.min(initial["formalR20"][:, 0]) >= 0.0
        and np.min(initial["R1C"][:, 0]) >= 0.0,
        {
            mesh_id: {
                "shape": list(state.shape),
                "minimumDepthM": float(np.min(state[:, 0])),
                "nonFinite": int(
                    state.size - np.isfinite(state).sum()
                ),
            }
            for mesh_id, state in initial.items()
        },
    )
    required_initial = np.asarray(
        [0, 0, 0, 1, 1, 1, 0, 0],
        dtype=np.float64,
    )
    initial_capacities = load_initial_capacities()
    add(
        checks,
        "both_1500s_capacity_states_are_exactly_4_5_6_open",
        all(
            np.array_equal(values, required_initial)
            for values in initial_capacities.values()
        ),
        {
            key: values.tolist()
            for key, values in initial_capacities.items()
        },
    )
    schedule = load_npz(SCHEDULE)
    times = schedule["absolute_time_s"]
    saved = schedule["capacity_fraction_by_gate_id"]
    reconstructed = np.stack(
        [capacity_at_absolute_time(float(value)) for value in times]
    )
    add(
        checks,
        "E1_schedule_is_exact_at_all_331_checkpoints",
        np.array_equal(times, np.arange(1500.0, 4801.0, 10.0))
        and np.array_equal(saved, reconstructed),
        {
            "timeCount": int(times.size),
            "maximumAbsoluteCapacityDifference": float(
                np.max(np.abs(saved - reconstructed))
            ),
        },
    )
    add(
        checks,
        "solver_authorities_are_unchanged",
        sha256(
            ROOT
            / "tools/run_stage20_barrage_C1_local_transition_600s_v1.py"
        )
        == d2.EXPECTED_C1_RUNNER_SHA
        and sha256(
            ROOT
            / "tools/run_stage20_barrage_candidate_C_C2b_S1_all_closed_settling_v1.py"
        )
        == d2.EXPECTED_S1_RUNNER_SHA,
        {
            "C1Runner": sha256(
                ROOT
                / "tools/run_stage20_barrage_C1_local_transition_600s_v1.py"
            ),
            "S1Runner": sha256(
                ROOT
                / "tools/run_stage20_barrage_candidate_C_C2b_S1_all_closed_settling_v1.py"
            ),
        },
    )
    add(
        checks,
        "M_tide_extension_covers_4800s",
        plan["boundaryContract"]["M"]["extensionCoversThePlan"]
        is True
        and plan["boundaryContract"]["M"][
            "maximumShiftedHourAt4800S"
        ]
        <= plan["boundaryContract"]["M"][
            "nextHourExtensionMaximumShiftedHour"
        ]
        and sha256(s1.TIDE_EXTENSION)
        == s1.EXPECTED_TIDE_EXTENSION_SHA,
        plan["boundaryContract"]["M"],
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
        "no_E1_solver_outputs_exist_before_execution",
        not any(path.exists() for path in RUN_ARCHIVES.values())
        and not any(path.exists() for path in RUN_REPORTS.values())
        and not JOURNAL.exists(),
        {
            "archives": {
                key: path.exists()
                for key, path in RUN_ARCHIVES.items()
            },
            "reports": {
                key: path.exists()
                for key, path in RUN_REPORTS.items()
            },
            "journal": JOURNAL.exists(),
        },
    )
    add(
        checks,
        "unauthorized_scopes_remain_excluded",
        {
            "a_third_E1_solver_run",
            "rerun_zero_to_1500",
            "remaining_reverse_closing_execution",
            "C3_coupled_hydrograph_execution",
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
    failed = [
        item["id"] for item in checks if item["status"] == "FAIL"
    ]
    result = {
        "schema": "onga-stage20-barrage-candidate-C-R1C-E1-preflight-v1",
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "bindings": {
            "approval": binding(APPROVAL),
            "plan": binding(PLAN),
            "schedule": binding(SCHEDULE),
        },
        "protectedBefore": before,
        "safeguards": {
            "preflightOnly": True,
            "newSolverRunCount": 0,
            "precomputationRun": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
    }
    write_json(PREFLIGHT, result)
    if failed:
        raise RuntimeError(f"E1 preflight failed: {failed}")
    return result, before


def run_continuation(
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
    initial_absolute_time_s = 1500.0
    target_absolute_time_s = 4800.0
    target_seconds = target_absolute_time_s - initial_absolute_time_s
    checkpoint_interval = 10.0
    checkpoint_count = 331
    cfl_target = 0.12
    alpha = capacity_at_absolute_time(initial_absolute_time_s)
    c1.update_mapping_workspace(workspace, alpha)

    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
    capacity_checkpoints = np.zeros(
        (checkpoint_count, 8),
        dtype=np.float64,
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
    flux_checkpoints = {
        name: np.zeros((checkpoint_count, 8), dtype=np.float64)
        for name in flux_names
    }
    relative_times = np.arange(
        0.0,
        target_seconds + checkpoint_interval,
        checkpoint_interval,
    )
    absolute_times = initial_absolute_time_s + relative_times
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
    initial_volume = float(
        np.sum(state[:, 0] * geometry["areas"])
    )
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
        float(source["contract"]["run"]["tideCurveStartHour"])
        * 3600.0
        + float(
            read_json(c1.short.SOURCE_REPORT)["run"][
                "simulatedSeconds"
            ]
        )
        + initial_absolute_time_s
    )
    wall_start = time.monotonic()
    print(
        json.dumps(
            {
                "event": "E1_run_started",
                "meshId": mesh_id,
                "initialAbsoluteTimeS": initial_absolute_time_s,
                "targetAbsoluteTimeS": target_absolute_time_s,
                "physicalSeconds": target_seconds,
                "checkpointCount": checkpoint_count,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    while elapsed < target_seconds - 1e-12:
        absolute_time = initial_absolute_time_s + elapsed
        alpha = capacity_at_absolute_time(absolute_time)
        c1.update_mapping_workspace(workspace, alpha)
        maximum_capacity_change_per_step = max(
            maximum_capacity_change_per_step,
            float(np.max(np.abs(alpha - previous_alpha))),
        )
        previous_alpha[:] = alpha
        minimum_capacity = min(
            minimum_capacity,
            float(np.min(alpha)),
        )
        maximum_capacity = max(
            maximum_capacity,
            float(np.max(alpha)),
        )
        gate_residual, gate_face_residual = (
            c1._maximum_gate_mass_residual(
                state,
                bed,
                geometry["left"],
                geometry["right"],
                workspace["effectiveLengths"],
                geometry["internalNormals"],
                workspace["multipliers"],
                workspace["gateFaceIds"],
            )
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
        actual_volume = float(
            np.sum(state[:, 0] * geometry["areas"])
        )
        mass_error = abs(actual_volume - expected_volume) / max(
            abs(initial_volume),
            1.0,
        )
        maximum_cfl = max(maximum_cfl, float(cfl))
        maximum_mass_error = max(
            maximum_mass_error,
            mass_error,
        )
        maximum_fishway_source_residual = max(
            maximum_fishway_source_residual,
            abs(float(fishway_source_residual)),
        )
        minimum_effective_q = min(
            minimum_effective_q,
            float(effective_q),
        )
        maximum_effective_q = max(
            maximum_effective_q,
            float(effective_q),
        )

        if (
            elapsed >= next_checkpoint - 1e-10
            or elapsed >= target_seconds - 1e-10
        ):
            c1.require(
                next_checkpoint_index < checkpoint_count,
                "too many E1 checkpoints",
            )
            absolute_time = initial_absolute_time_s + elapsed
            alpha = capacity_at_absolute_time(absolute_time)
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
                flux_checkpoints[name][
                    next_checkpoint_index
                ] = flux[name]
            mapping_exact_count += int(mapping_exact)
            next_checkpoint_index += 1
            next_checkpoint += checkpoint_interval
            if elapsed >= next_progress - 1e-10:
                print(
                    json.dumps(
                        {
                            "event": "E1_run_progress",
                            "meshId": mesh_id,
                            "absoluteTimeS": round(
                                initial_absolute_time_s + elapsed,
                                9,
                            ),
                            "percent": round(
                                100.0 * elapsed / target_seconds,
                                1,
                            ),
                            "steps": step,
                            "wallSeconds": round(
                                time.monotonic() - wall_start,
                                3,
                            ),
                            "openGateIds": (
                                np.flatnonzero(alpha >= 1.0 - 1e-12)
                                + 1
                            ).tolist(),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                next_progress += 300.0

    c1.require(
        next_checkpoint_index == checkpoint_count,
        "missing E1 checkpoints",
    )
    approved_schedule = load_npz(SCHEDULE)[
        "capacity_fraction_by_gate_id"
    ]
    c1.require(
        np.array_equal(capacity_checkpoints, approved_schedule),
        "saved E1 capacity checkpoints differ from approved schedule",
    )
    depth = state[:, 0]
    speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(
        depth,
        1e-12,
    )
    report = {
        "meshId": mesh_id,
        "initialAbsoluteTimeS": initial_absolute_time_s,
        "finalAbsoluteTimeS": initial_absolute_time_s + elapsed,
        "simulatedContinuationSeconds": elapsed,
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
        "nonFiniteValueCount": int(
            state.size - np.isfinite(state).sum()
        ),
    }
    fields = {
        "absoluteCheckpointTimeS": absolute_times,
        "relativeCheckpointTimeS": relative_times,
        "capacityFractionByGateId": capacity_checkpoints,
        **{
            f"gateFlux__{name}": values
            for name, values in flux_checkpoints.items()
        },
    }
    print(
        json.dumps(
            {
                "event": "E1_run_complete",
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
    OUTPUT.mkdir(parents=True, exist_ok=True)
    states = np.stack(snapshots).astype(np.float32)
    np.savez_compressed(
        RUN_ARCHIVES[mesh_id],
        state_H_HU_HV=states,
        **fields,
    )
    write_json(RUN_REPORTS[mesh_id], report)
    preflight = read_json(PREFLIGHT)
    protected_after = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in protected_paths()
    }
    completed = [
        key
        for key in MESH_IDS
        if RUN_ARCHIVES[key].is_file()
        and RUN_REPORTS[key].is_file()
    ]
    write_json(
        JOURNAL,
        {
            "schema": "onga-stage20-barrage-candidate-C-R1C-E1-execution-journal-v1",
            "version": 1,
            "status": (
                "RUNS_COMPLETE"
                if len(completed) == 2
                else "RUNNING"
            ),
            "authorizedRunCount": 2,
            "completedRunCount": len(completed),
            "completedMeshIds": completed,
            "bindings": {
                key: {
                    "archive": binding(RUN_ARCHIVES[key]),
                    "report": binding(RUN_REPORTS[key]),
                }
                for key in completed
            },
            "protectedBefore": preflight["protectedBefore"],
            "protectedAfter": protected_after,
            "protectedAssetsUnchanged": (
                preflight["protectedBefore"] == protected_after
            ),
            "safeguards": {
                "thirdE1RunStarted": False,
                "zeroTo1500Rerun": False,
                "remainingReverseClosingRun": False,
                "C3Run": False,
                "precomputationRun": False,
                "publicRuntimeChanged": False,
                "mainMerged": False,
            },
        },
    )


def execute_mesh(mesh_id: str) -> None:
    if not PREFLIGHT.is_file():
        raise RuntimeError("E1 preflight must pass before solver execution")
    preflight = read_json(PREFLIGHT)
    c1.require(
        preflight["status"] == "PASS"
        and preflight["bindings"]["approval"]["sha256"]
        == sha256(APPROVAL),
        "E1 preflight or approval binding changed",
    )
    c1.require(
        not RUN_ARCHIVES[mesh_id].exists()
        and not RUN_REPORTS[mesh_id].exists(),
        f"E1 result already exists for {mesh_id}; overwrite refused",
    )
    completed = [
        key
        for key in MESH_IDS
        if RUN_ARCHIVES[key].is_file()
        and RUN_REPORTS[key].is_file()
    ]
    if mesh_id == "R1C":
        c1.require(
            completed == ["formalR20"],
            "formal R20 must complete before R1C",
        )
    else:
        c1.require(
            not completed,
            "formal R20 must be the first E1 run",
        )
    initial = load_initial_states()[mesh_id]
    context = load_context(mesh_id, initial)
    snapshots, report, fields = run_continuation(mesh_id, *context)
    save_run(mesh_id, snapshots, report, fields)
    print(
        json.dumps(
            {
                "event": "E1_mesh_saved",
                "meshId": mesh_id,
                "archive": binding(RUN_ARCHIVES[mesh_id]),
                "report": binding(RUN_REPORTS[mesh_id]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preflight-only",
        action="store_true",
    )
    parser.add_argument(
        "--mesh",
        choices=MESH_IDS,
    )
    args = parser.parse_args()
    if args.preflight_only:
        result, _ = preflight()
        print(
            json.dumps(
                {
                    "event": "E1_preflight_complete",
                    "status": result["status"],
                    "checks": result["checkCount"],
                    "solverRun": False,
                },
                ensure_ascii=False,
            )
        )
        return
    if args.mesh:
        execute_mesh(args.mesh)
        return
    parser.error("choose --preflight-only or --mesh")


if __name__ == "__main__":
    main()
