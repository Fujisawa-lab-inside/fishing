#!/usr/bin/env python3
"""Zero-case Stage 19 solver-input preflight.

The preflight constructs every approved input field but never calls a numerical
time-step function.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from stage19_solver_inputs import (
    build_case_fields,
    classify_branch_ownership,
    fishway_discharge_m3s,
    load_water_mask,
    mesh_geometry,
    tide_anomaly_m,
)


EXPECTED = {
    "ensembleSha256": "d970409f842382a2ef8c996f0c3866f3651095bbf2867707c4e240a4d2d80ce7",
    "tideCandidateSha256": "a780f618089d295731dc6a87484b6a30f8a7895aac17c507876ede06c20720ea",
    "tideApprovalSha256": "964ce38825d8a55ba5599fbda2c3f7248bd5dcc276793d53026c0c1f4b5b6912",
    "approvedTideVisualSha256": "9359041d14f4eaddbb3c53896980c7d544ac4d754d6077ccc14422bda9d142b5",
    "canonicalMeshSha256": "f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2",
    "canonicalCellCount": 50129,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--mesh-summary")
    parser.add_argument("--manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--ensemble", default="config/stage19_provisional_ensemble_cases_v1.json")
    parser.add_argument("--tide-candidate", default="config/stage19_m_boundary_tide_candidate_v1.json")
    parser.add_argument("--tide-approval", default="config/stage19_m_boundary_tide_approval_v1.json")
    parser.add_argument("--approved-visual", default="docs/visuals/stage19-m-boundary-tide-decision.png")
    parser.add_argument("--allow-probe", action="store_true")
    parser.add_argument("--output", default="stage19-solver-integration-zero-case-preflight.json")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage19-zero-case] {message}")


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def weighted_mean(values: np.ndarray, weights: np.ndarray, mask: np.ndarray) -> float:
    return float(np.average(values[mask], weights=weights[mask]))


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    require(sha256(args.ensemble) == EXPECTED["ensembleSha256"], "ensemble digest changed")
    require(sha256(args.tide_candidate) == EXPECTED["tideCandidateSha256"], "tide candidate changed")
    require(sha256(args.tide_approval) == EXPECTED["tideApprovalSha256"], "tide approval changed")
    require(sha256(args.approved_visual) == EXPECTED["approvedTideVisualSha256"], "approved tide visual changed")
    ensemble = load_json(args.ensemble)
    candidate = load_json(args.tide_candidate)
    approval = load_json(args.tide_approval)
    require(ensemble["count"] == 64 and len(ensemble["cases"]) == 64, "expected 64 cases")
    require(approval["sourceStatement"] == "この相対潮位曲線をM境界に使用してよい", "approval statement changed")
    require(approval["safeguards"]["full64RunEnabled"] is False, "approval enabled the full64 run")

    mesh_digest = sha256(args.mesh)
    canonical = mesh_digest == EXPECTED["canonicalMeshSha256"]
    if not canonical:
        require(args.allow_probe, "noncanonical mesh requires --allow-probe")
    package_file = np.load(args.mesh)
    package = {key: package_file[key] for key in package_file.files}
    geometry = mesh_geometry(package)
    require(canonical == (len(geometry["areas"]) == EXPECTED["canonicalCellCount"]),
            "mesh digest/cell-count canonical status mismatch")
    manifest, mask = load_water_mask(args.manifest)
    require(int(mask.sum()) == 680633 and manifest["version"] == "v4.8.0-candidate-r3",
            "water authority changed")
    owner = classify_branch_ownership(package, geometry)
    shore_cache: dict = {}
    area = geometry["areas"]
    main = np.isin(owner, [1, 3])
    tributary = np.isin(owner, [2, 4])

    extrema = {
        "minimumDepthM": float("inf"),
        "maximumDepthM": float("-inf"),
        "minimumManningN": float("inf"),
        "maximumManningN": float("-inf"),
        "minimumBarrageTransmissivity": float("inf"),
        "maximumBarrageTransmissivity": float("-inf"),
    }
    first_fields = None
    for case in ensemble["cases"]:
        fields = build_case_fields(
            case, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache
        )
        first_fields = first_fields or fields
        require(abs(weighted_mean(fields["initialWaterDepthM"], area, main)
                    - float(case["bathymetry"]["mainstemMeanDepthM"])) < 1e-10,
                f"{case['caseId']} main-stem mean mismatch")
        require(abs(weighted_mean(fields["initialWaterDepthM"], area, tributary)
                    - float(case["bathymetry"]["tributaryMeanDepthM"])) < 1e-10,
                f"{case['caseId']} tributary mean mismatch")
        require(fields["tide"]["meanOffsetM"] is None, "absolute M offset assigned")
        extrema["minimumDepthM"] = min(extrema["minimumDepthM"], float(np.min(fields["initialWaterDepthM"])))
        extrema["maximumDepthM"] = max(extrema["maximumDepthM"], float(np.max(fields["initialWaterDepthM"])))
        extrema["minimumManningN"] = min(extrema["minimumManningN"], float(np.min(fields["manningN"])))
        extrema["maximumManningN"] = max(extrema["maximumManningN"], float(np.max(fields["manningN"])))
        extrema["minimumBarrageTransmissivity"] = min(
            extrema["minimumBarrageTransmissivity"], float(fields["barrageTransmissivity"])
        )
        extrema["maximumBarrageTransmissivity"] = max(
            extrema["maximumBarrageTransmissivity"], float(fields["barrageTransmissivity"])
        )

    base = copy.deepcopy(ensemble["cases"][0])
    counterfactual = {}

    sigma_low = copy.deepcopy(base)
    sigma_high = copy.deepcopy(base)
    sigma_low["bathymetry"]["sigma"] = 0.28
    sigma_high["bathymetry"]["sigma"] = 0.46
    field_low = build_case_fields(sigma_low, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache)
    field_high = build_case_fields(sigma_high, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache)
    counterfactual["bathymetrySigmaChangesSpatialField"] = bool(
        np.max(np.abs(field_low["relativeDepthFraction"] - field_high["relativeDepthFraction"])) > 1e-4
    )

    for key, group, path in (
        ("mainstemDepthChangesMainMean", main, ("bathymetry", "mainstemMeanDepthM")),
        ("tributaryDepthChangesTributaryMean", tributary, ("bathymetry", "tributaryMeanDepthM")),
    ):
        low = copy.deepcopy(base)
        high = copy.deepcopy(base)
        low[path[0]][path[1]] = 2.0 if "mainstem" in key else 0.8
        high[path[0]][path[1]] = 6.0 if "mainstem" in key else 3.0
        f_low = build_case_fields(low, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache)
        f_high = build_case_fields(high, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache)
        counterfactual[key] = weighted_mean(f_high["initialWaterDepthM"], area, group) > weighted_mean(
            f_low["initialWaterDepthM"], area, group
        )

    roughness_variants = []
    for parameter, low_value, high_value in (
        ("manningOpenChannel", 0.02, 0.045),
        ("shallowMarginMultiplier", 1.0, 1.7),
        ("structureVicinityMultiplier", 1.0, 1.5),
    ):
        low = copy.deepcopy(base)
        high = copy.deepcopy(base)
        low["roughness"][parameter] = low_value
        high["roughness"][parameter] = high_value
        f_low = build_case_fields(low, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache)
        f_high = build_case_fields(high, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache)
        roughness_variants.append(bool(np.max(np.abs(f_low["manningN"] - f_high["manningN"])) > 1e-8))
    counterfactual["allThreeRoughnessInputsChangeManningField"] = all(roughness_variants)

    tide_low = {"phaseShiftMinutes": -90.0, "amplitudeMultiplier": 0.6, "meanOffsetM": None}
    tide_high = {"phaseShiftMinutes": 90.0, "amplitudeMultiplier": 1.4, "meanOffsetM": None}
    counterfactual["MPhaseAndAmplitudeChangeBoundaryValue"] = abs(
        tide_anomaly_m(3600.0, tide_low, candidate) - tide_anomaly_m(3600.0, tide_high, candidate)
    ) > 1e-4

    counterfactual["allThreeRiverDischargesReachBoundaryFields"] = all(
        first_fields["boundaryDischargeM3S"][key] == float(base["boundaries"][key]["dischargeM3S"])
        for key in ("N", "O", "G")
    )
    barrage_low = copy.deepcopy(base)
    barrage_high = copy.deepcopy(base)
    barrage_low["barrage"].update({"scenario": "fully_closed", "effectiveDischargeCoefficient": 0.45})
    barrage_high["barrage"].update({"scenario": "uniform_100_percent", "effectiveDischargeCoefficient": 0.85})
    b_low = build_case_fields(barrage_low, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache)
    b_high = build_case_fields(barrage_high, package, mask, geometry=geometry, owner=owner, shore_cache=shore_cache)
    counterfactual["BarrageScenarioAndCoefficientChangeTransmissivity"] = (
        b_low["barrageTransmissivity"] == 0.0 and b_high["barrageTransmissivity"] == 0.85
    )

    synthetic_state = np.zeros((len(area), 3), dtype=np.float64)
    synthetic_state[:, 0] = first_fields["initialWaterDepthM"]
    fish_cells = package["fishway_cells"].astype(np.int64)
    synthetic_state[fish_cells[0], 0] += 0.25
    fish_disabled = copy.deepcopy(first_fields)
    fish_disabled["fishway"] = {"mode": "disabled", "effectiveDischargeCoefficient": 0.35, "effectiveAreaM2": 0.2}
    fish_low = copy.deepcopy(first_fields)
    fish_low["fishway"] = {"mode": "head_difference_relation_ensemble", "effectiveDischargeCoefficient": 0.35, "effectiveAreaM2": 0.2}
    fish_high = copy.deepcopy(first_fields)
    fish_high["fishway"] = {"mode": "head_difference_relation_ensemble", "effectiveDischargeCoefficient": 0.85, "effectiveAreaM2": 4.0}
    q_disabled = fishway_discharge_m3s(synthetic_state, fish_disabled, package)
    q_low = fishway_discharge_m3s(synthetic_state, fish_low, package)
    q_high = fishway_discharge_m3s(synthetic_state, fish_high, package)
    counterfactual["FishwayModeCoefficientAndAreaReachHeadRelation"] = (
        q_disabled == 0.0 and 0.0 < q_low < q_high
    )
    require(all(counterfactual.values()), "one or more input counterfactuals failed")

    report = {
        "schema": "onga-stage19-solver-integration-zero-case-preflight-v1",
        "status": "passed",
        "mesh": {
            "path": args.mesh,
            "sha256": mesh_digest,
            "canonical": canonical,
            "cellCount": len(area),
        },
        "casePackage": {
            "caseCount": 64,
            "seed": ensemble["seed"],
            "sha256": EXPECTED["ensembleSha256"],
        },
        "branchOwnershipCellCounts": {
            name: int(np.sum(owner == tag)) for name, tag in (("M", 1), ("N", 2), ("O", 3), ("G", 4))
        },
        "extremaAcross64PreparedInputFields": extrema,
        "counterfactualChecks": counterfactual,
        "approvedInputDimensionsReached": 16,
        "elapsedSeconds": time.perf_counter() - started,
        "safeguards": {
            "numericalTimeStepFunctionCalled": False,
            "productionMeshNumericalCaseStarted": False,
            "full64RunEnabled": False,
            "externalContactPerformed": False,
            "publicSimulatorConnected": False,
            "physicalValidationClaimAllowed": False,
        },
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
