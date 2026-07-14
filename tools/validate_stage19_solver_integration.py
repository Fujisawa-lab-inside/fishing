#!/usr/bin/env python3
"""Synthetic-only validation for the Stage 19 shallow-water integration.

This program uses two triangular cells.  It never loads the Onga production
mesh and cannot start a 64-case run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from stage19_shallow_water_kernel_v1 import (
    advance_one_step,
    build_solver_geometry,
    flux_residual,
)
from stage19_solver_inputs import fishway_discharge_m3s, tide_anomaly_m


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage19-synthetic] {message}")


def fixture(boundary_tags: tuple[int, int, int, int] = (0, 0, 0, 0)) -> tuple[dict, dict]:
    # Unit square split along the diagonal from (0, 0) to (1, 1).
    package = {
        "vertex_local_mm": np.asarray(
            [[0, 0], [1000, 0], [1000, 1000], [0, 1000]], dtype=np.int64
        ),
        "triangles": np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        "internal_face_vertices": np.asarray([[0, 2]], dtype=np.int64),
        "internal_face_cells": np.asarray([[0, 1]], dtype=np.int64),
        "boundary_face_vertices": np.asarray(
            [[0, 1], [1, 2], [2, 3], [3, 0]], dtype=np.int64
        ),
        "boundary_face_cell": np.asarray([0, 0, 1, 1], dtype=np.int64),
        "boundary_face_tag": np.asarray(boundary_tags, dtype=np.uint8),
        "barrage_face_ids": np.asarray([0], dtype=np.int64),
        "fishway_cells": np.asarray([0, 1], dtype=np.int64),
    }
    return package, build_solver_geometry(package)


def fields(*, transmissivity: float = 1.0, bed: tuple[float, float] = (-1.0, -1.0)) -> dict:
    return {
        "bedElevationM": np.asarray(bed, dtype=np.float64),
        "manningN": np.asarray([0.03, 0.03], dtype=np.float64),
        "barrageTransmissivity": transmissivity,
        "boundaryDischargeM3S": {"N": 0.0, "O": 0.0, "G": 0.0},
        "tide": {"phaseShiftMinutes": 0.0, "amplitudeMultiplier": 1.0, "meanOffsetM": None},
        "fishway": {
            "mode": "disabled",
            "effectiveDischargeCoefficient": 0.5,
            "effectiveAreaM2": 0.5,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tide-candidate", default="config/stage19_m_boundary_tide_candidate_v1.json"
    )
    parser.add_argument(
        "--output", default="config/stage19_solver_integration_synthetic_validation_v1.json"
    )
    args = parser.parse_args()
    candidate = json.loads(Path(args.tide_candidate).read_text(encoding="utf-8"))

    checks: dict[str, bool] = {}
    package, geometry = fixture()

    # A constant free surface over a sloping bed must remain exactly at rest,
    # including when the internal face is treated as a closed/partial barrage.
    for transmissivity in (0.0, 0.3, 1.0):
        local_fields = fields(transmissivity=transmissivity, bed=(-1.0, -1.4))
        state = np.asarray([[1.0, 0.0, 0.0], [1.4, 0.0, 0.0]], dtype=np.float64)
        residual, _, boundary_outflow = flux_residual(
            state, 0.0, local_fields, geometry, package, candidate
        )
        next_state, _, diagnostics = advance_one_step(
            state, 0.0, local_fields, geometry, package, candidate
        )
        key = f"lakeAtRestTransmissivity{transmissivity:g}"
        checks[key] = bool(
            np.max(np.abs(residual)) < 1e-12
            and np.max(np.abs(next_state - state)) < 1e-12
            and abs(boundary_outflow) < 1e-12
            and diagnostics["maxCfl"] <= 0.120000000001
        )

    # Each inflow boundary must contribute its requested inward discharge.
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        inflow_package, inflow_geometry = fixture((tag, 0, 0, 0))
        local_fields = fields()
        local_fields["boundaryDischargeM3S"][boundary_id] = 0.2
        state = np.asarray([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
        _, _, boundary_outflow = flux_residual(
            state, 0.0, local_fields, inflow_geometry, inflow_package, candidate
        )
        checks[f"{boundary_id}ExactPrescribedInflow"] = abs(boundary_outflow + 0.2) < 1e-12

    # The barrage parameter must alter transport away from equilibrium while
    # preserving the same mesh and initial state.
    moving = np.asarray([[1.0, 0.35, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    closed_residual, _, _ = flux_residual(
        moving, 0.0, fields(transmissivity=0.0), geometry, package, candidate
    )
    open_residual, _, _ = flux_residual(
        moving, 0.0, fields(transmissivity=1.0), geometry, package, candidate
    )
    checks["barrageTransmissivityChangesTransport"] = bool(
        np.max(np.abs(closed_residual - open_residual)) > 1e-6
    )

    # M is a relative anomaly only: phase and amplitude change its value, while
    # assigning an absolute offset is rejected by the input function.
    low_tide = {"phaseShiftMinutes": -90.0, "amplitudeMultiplier": 0.6, "meanOffsetM": None}
    high_tide = {"phaseShiftMinutes": 90.0, "amplitudeMultiplier": 1.4, "meanOffsetM": None}
    checks["mPhaseAndAmplitudeAreActive"] = abs(
        tide_anomaly_m(3600.0, low_tide, candidate)
        - tide_anomaly_m(3600.0, high_tide, candidate)
    ) > 1e-4
    rejected_offset = False
    try:
        tide_anomaly_m(
            3600.0,
            {"phaseShiftMinutes": 0.0, "amplitudeMultiplier": 1.0, "meanOffsetM": 0.2},
            candidate,
        )
    except ValueError:
        rejected_offset = True
    checks["mAbsoluteOffsetRejected"] = rejected_offset

    # Fishway transfer must disable cleanly, reverse with head, and scale with
    # coefficient and effective area exactly as the approved relation states.
    base_fields = fields()
    head_positive = np.asarray([[1.2, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    head_negative = np.asarray([[1.0, 0.0, 0.0], [1.2, 0.0, 0.0]], dtype=np.float64)
    q_disabled = fishway_discharge_m3s(head_positive, base_fields, package)
    active = fields()
    active["fishway"]["mode"] = "head_difference_relation_ensemble"
    q_positive = fishway_discharge_m3s(head_positive, active, package)
    q_negative = fishway_discharge_m3s(head_negative, active, package)
    scaled = fields()
    scaled["fishway"].update(
        {
            "mode": "head_difference_relation_ensemble",
            "effectiveDischargeCoefficient": 1.0,
            "effectiveAreaM2": 1.0,
        }
    )
    q_scaled = fishway_discharge_m3s(head_positive, scaled, package)
    checks["fishwayDisabledIsZero"] = q_disabled == 0.0
    checks["fishwayReversesWithHead"] = q_positive > 0.0 and q_negative < 0.0 and abs(q_positive + q_negative) < 1e-12
    checks["fishwayCoefficientAndAreaScaleFlow"] = abs(q_scaled / q_positive - 4.0) < 1e-12

    require(all(checks.values()), "one or more synthetic checks failed")
    report = {
        "schema": "onga-stage19-solver-integration-synthetic-validation-v1",
        "status": "passed",
        "checks": checks,
        "safeguards": {
            "syntheticFixtureOnly": True,
            "productionMeshLoaded": False,
            "productionMeshNumericalCaseStarted": False,
            "full64RunEnabled": False,
            "externalContactPerformed": False,
            "physicalValidationClaimAllowed": False,
        },
    }
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
