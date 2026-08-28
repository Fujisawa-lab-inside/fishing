#!/usr/bin/env python3
"""C2.1 fishway storage candidate with numerically stable mass guards.

The physical C2 equations, state update, geometry, and safety limits are
unchanged.  C2.1 only separates two numerical checks:

1. the analytic source identity, checked in discharge units at 1e-12 m3/s;
2. the discrete stored-volume update, checked against an explicit float64 ULP
   scale in volume units.

This avoids subtracting two nearly equal large storage volumes and dividing
the rounded difference by a small hydrodynamic time step.
"""

from __future__ import annotations

from typing import Any

import numpy as np

import stage20_fishway_1d_link_C2_storage_candidate_v1 as c2


FishwayC2StorageError = c2.FishwayC2StorageError
FishwayC2StorageWorkspace = c2.FishwayC2StorageWorkspace
FishwayC2StorageParameters = c2.FishwayC2StorageParameters
build_workspace = c2.build_workspace
equilibrium_storage_volume_m3 = c2.equilibrium_storage_volume_m3
measure_heads = c2.measure_heads
smoothstep01 = c2.smoothstep01


def link_step(
    state_h_hu_hv: np.ndarray,
    bed_elevation_m: np.ndarray,
    workspace: FishwayC2StorageWorkspace,
    parameters: FishwayC2StorageParameters,
    time_step_s: float,
    stored_volume_m3: float,
) -> dict[str, Any]:
    """Evaluate one C2 step with analytic and ULP-scaled mass checks."""

    params = c2._validate_parameters(parameters)
    state = c2._array(
        "state_h_hu_hv",
        state_h_hu_hv,
        dtype=np.float64,
        ndim=2,
    )
    bed = c2._array(
        "bed_elevation_m",
        bed_elevation_m,
        dtype=np.float64,
    )
    cell_count = len(workspace.cell_areas_m2)
    if state.shape != (cell_count, 3) or bed.shape != (cell_count,):
        raise FishwayC2StorageError(
            "state or bed shape does not match C2.1 workspace"
        )
    if np.any(state[:, 0] < 0.0):
        raise FishwayC2StorageError("state contains negative depth")
    if not np.isfinite(time_step_s) or time_step_s <= 0.0:
        raise FishwayC2StorageError(
            "time_step_s must be positive and finite"
        )
    if not np.isfinite(stored_volume_m3):
        raise FishwayC2StorageError(
            "stored_volume_m3 must be finite"
        )

    reserve_storage = (
        params.storage_area_m2 * params.reserve_depth_m
    )
    storage_tolerance = 1e-12 * max(1.0, reserve_storage)
    if stored_volume_m3 < reserve_storage - storage_tolerance:
        raise FishwayC2StorageError(
            "stored volume is below the approved 5 cm link reserve"
        )
    storage = max(float(stored_volume_m3), reserve_storage)
    heads = measure_heads(state, bed, workspace)
    law = c2._head_command(heads["headDifferenceM"], params)

    depth = state[:, 0]
    available_by_cell = np.zeros(cell_count, dtype=np.float64)
    ids = workspace.upstream_component_cell_ids
    available_by_cell[ids] = (
        workspace.cell_areas_m2[ids]
        * np.maximum(depth[ids] - params.reserve_depth_m, 0.0)
    )
    available_volume = float(np.sum(available_by_cell))
    safety_discharge = (
        params.maximum_available_volume_fraction_per_step
        * available_volume
        / time_step_s
    )
    inflow = min(law["commandM3S"], safety_discharge)

    releasable_storage = max(storage - reserve_storage, 0.0)
    residence_release = (
        releasable_storage / params.residence_time_s
    )
    step_release = releasable_storage / time_step_s
    outflow = min(
        params.maximum_discharge_m3_s,
        residence_release,
        step_release,
    )
    analytic_storage_rate = inflow - outflow
    storage_increment = time_step_s * analytic_storage_rate
    next_storage = storage + storage_increment
    if next_storage < reserve_storage - storage_tolerance:
        raise FishwayC2StorageError(
            "linear storage release violates the link reserve"
        )
    next_storage = max(next_storage, reserve_storage)

    donor_rate = np.zeros(cell_count, dtype=np.float64)
    if inflow > 0.0:
        if available_volume <= 0.0:
            raise FishwayC2StorageError(
                "positive inflow without upstream component supply"
            )
        donor_rate = inflow * available_by_cell / available_volume
    receiver_rate = outflow * workspace.downstream_head_weights
    mass_rate = receiver_rate - donor_rate
    safe_depth = np.maximum(depth, 1e-12)
    hu_rate = -donor_rate * state[:, 1] / safe_depth
    hv_rate = -donor_rate * state[:, 2] / safe_depth
    post_depth = (
        depth
        + time_step_s
        * mass_rate
        / workspace.cell_areas_m2
    )
    removed_fraction = np.zeros(cell_count, dtype=np.float64)
    selected = donor_rate > 0.0
    removed_fraction[selected] = (
        time_step_s
        * donor_rate[selected]
        / available_by_cell[selected]
    )

    two_d_mass_rate = float(np.sum(mass_rate))
    analytic_residual = two_d_mass_rate + analytic_storage_rate
    if abs(analytic_residual) > 1e-12:
        raise FishwayC2StorageError(
            "analytic 2D-plus-storage source residual exceeds "
            "1e-12 m3/s"
        )
    discrete_identity_error = (
        (next_storage - storage) - storage_increment
    )
    float_epsilon = np.finfo(np.float64).eps
    storage_scale = max(abs(storage), abs(next_storage), 1.0)
    ulp_scale = max(
        abs(float(np.spacing(storage))),
        abs(float(np.spacing(next_storage))),
        float_epsilon * storage_scale,
    )
    discrete_tolerance = 4.0 * ulp_scale
    if abs(discrete_identity_error) > discrete_tolerance:
        raise FishwayC2StorageError(
            "discrete storage identity exceeds the 4-ULP bound"
        )
    legacy_subtractive_storage_rate = (
        (next_storage - storage) / time_step_s
    )
    legacy_subtractive_residual = (
        two_d_mass_rate + legacy_subtractive_storage_rate
    )
    if np.min(post_depth) < -1e-12:
        raise FishwayC2StorageError(
            "C2.1 source would create negative depth"
        )
    if (
        np.max(removed_fraction)
        > params.maximum_available_volume_fraction_per_step + 1e-12
    ):
        raise FishwayC2StorageError(
            "C2.1 source exceeds per-step available-volume limit"
        )

    if law["commandM3S"] <= 0.0:
        inflow_limitation = "adverse_head"
    elif inflow < law["commandM3S"] - 1e-15:
        inflow_limitation = "upstream_component_safety"
    elif law["uncappedCommandM3S"] > params.maximum_discharge_m3_s:
        inflow_limitation = "maximum_discharge"
    else:
        inflow_limitation = "constitutive_law"
    if releasable_storage <= 0.0:
        outflow_limitation = "storage_reserve"
    elif residence_release <= params.maximum_discharge_m3_s + 1e-15:
        outflow_limitation = "linear_reservoir"
    else:
        outflow_limitation = "maximum_discharge"

    return {
        "massRateM3SByCell": mass_rate,
        "horizontalMomentumRateXByCell": hu_rate,
        "horizontalMomentumRateYByCell": hv_rate,
        "postSourceDepthM": post_depth,
        "nextStoredVolumeM3": float(next_storage),
        "diagnostics": {
            "linkAvailable": True,
            "graphEdgePresent": True,
            "userControllable": False,
            "direction": "upstream_to_downstream",
            **heads,
            **law,
            "inflowM3S": float(inflow),
            "outflowM3S": float(outflow),
            "upstreamComponentAvailableVolumeM3": available_volume,
            "upstreamComponentSafetyDischargeM3S": float(
                safety_discharge
            ),
            "inflowLimitation": inflow_limitation,
            "outflowLimitation": outflow_limitation,
            "storedVolumeBeforeM3": float(storage),
            "storedVolumeAfterM3": float(next_storage),
            "storageRateM3S": float(analytic_storage_rate),
            "storageAreaM2": params.storage_area_m2,
            "storageDepthBeforeM": float(
                storage / params.storage_area_m2
            ),
            "storageDepthAfterM": float(
                next_storage / params.storage_area_m2
            ),
            "storageWaterLevelLocalDatumBeforeM": float(
                params.local_invert_datum_m
                + storage / params.storage_area_m2
            ),
            "storageWaterLevelLocalDatumAfterM": float(
                params.local_invert_datum_m
                + next_storage / params.storage_area_m2
            ),
            "reserveStorageVolumeM3": float(reserve_storage),
            "releasableStorageBeforeM3": float(releasable_storage),
            "twoDimensionalMassRateM3S": two_d_mass_rate,
            "extendedMassResidualM3S": float(analytic_residual),
            "analyticSourceMassResidualM3S": float(
                analytic_residual
            ),
            "discreteStorageIdentityErrorM3": float(
                discrete_identity_error
            ),
            "discreteStorageIdentityToleranceM3": float(
                discrete_tolerance
            ),
            "discreteStorageIdentityErrorToToleranceRatio": float(
                abs(discrete_identity_error) / discrete_tolerance
                if discrete_tolerance > 0.0
                else 0.0
            ),
            "legacySubtractiveStorageRateM3S": float(
                legacy_subtractive_storage_rate
            ),
            "legacySubtractiveExtendedResidualM3S": float(
                legacy_subtractive_residual
            ),
            "analyticAbsoluteMassGuardM3S": 1e-12,
            "discreteStorageULPMultiplier": 4.0,
            "massGuardRelaxed": False,
            "physicalEquationChanged": False,
            "maximumActualAvailableVolumeFractionRemoved": float(
                np.max(removed_fraction)
            ),
            "minimumPostSourceDepthM": float(np.min(post_depth)),
            "minimumSelectedDonorPostSourceDepthM": (
                float(np.min(post_depth[selected]))
                if np.any(selected)
                else None
            ),
            "upstreamHydraulicComponentCellCount": int(len(ids)),
            "upstreamP2CellCount": int(
                len(workspace.upstream_p2_cell_ids)
            ),
            "downstreamP2CellCount": int(
                len(workspace.downstream_p2_cell_ids)
            ),
            "receiverHorizontalMomentumAdded": 0.0,
            "donorMomentumRemovedWithWithdrawnMass": True,
            "instantaneousZeroDoesNotDisableLink": True,
            "synthetic2DP2DepthUsedAsFishwayDepth": False,
            "graphRankExpansionUsed": False,
            "internalStorageUsesIndependentLocalInvertDatum": True,
            "timeStepS": float(time_step_s),
            "numericalGuardVersion": (
                "C2_1_analytic_source_plus_ULP_storage"
            ),
        },
    }
