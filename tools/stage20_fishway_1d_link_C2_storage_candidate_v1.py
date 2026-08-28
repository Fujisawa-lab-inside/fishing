#!/usr/bin/env python3
"""Unconnected C2 fishway link with independent lumped 1D storage.

The two approved P2 circles measure the upstream/downstream free surfaces, but
their synthetic two-dimensional depths are never interpreted as fishway
internal depth.  Supply is withdrawn conservatively from the complete
upstream hydraulic component obtained after removing the approved barrage
cut.  A separate stored-volume state receives that inflow and releases it to
the downstream P2 footprint through a linear-reservoir law.

The module is a review-only candidate.  It is not imported by the production
solver and contains no calibrated physical parameter set.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np


class FishwayC2StorageError(ValueError):
    """Invalid C2 geometry, parameter, or state."""


@dataclass(frozen=True)
class FishwayC2StorageWorkspace:
    cell_areas_m2: np.ndarray
    upstream_overlap_area_m2: np.ndarray
    downstream_overlap_area_m2: np.ndarray
    upstream_head_weights: np.ndarray
    downstream_head_weights: np.ndarray
    upstream_component_mask: np.ndarray
    upstream_component_cell_ids: np.ndarray
    upstream_p2_cell_ids: np.ndarray
    downstream_p2_cell_ids: np.ndarray
    structure_face_mask: np.ndarray


@dataclass(frozen=True)
class FishwayC2StorageParameters:
    basal_discharge_m3_s: float
    head_sqrt_gain_m2p5_s: float
    maximum_discharge_m3_s: float
    adverse_head_shutdown_m: float
    storage_area_m2: float
    residence_time_s: float
    local_invert_datum_m: float = 0.0
    reserve_depth_m: float = 0.05
    maximum_available_volume_fraction_per_step: float = 0.02


def _array(
    name: str,
    values: np.ndarray,
    *,
    dtype: Any,
    ndim: int = 1,
) -> np.ndarray:
    result = np.asarray(values, dtype=dtype)
    if result.ndim != ndim:
        raise FishwayC2StorageError(
            f"{name} must have {ndim} dimensions"
        )
    if np.issubdtype(result.dtype, np.floating):
        if not np.isfinite(result).all():
            raise FishwayC2StorageError(
                f"{name} contains non-finite values"
            )
    return result.copy()


def _validate_parameters(
    parameters: FishwayC2StorageParameters,
) -> FishwayC2StorageParameters:
    values = np.asarray(
        [
            parameters.basal_discharge_m3_s,
            parameters.head_sqrt_gain_m2p5_s,
            parameters.maximum_discharge_m3_s,
            parameters.adverse_head_shutdown_m,
            parameters.storage_area_m2,
            parameters.residence_time_s,
            parameters.local_invert_datum_m,
            parameters.reserve_depth_m,
            parameters.maximum_available_volume_fraction_per_step,
        ],
        dtype=np.float64,
    )
    if not np.isfinite(values).all():
        raise FishwayC2StorageError(
            "C2 storage parameters contain non-finite values"
        )
    if (
        parameters.basal_discharge_m3_s < 0.0
        or parameters.head_sqrt_gain_m2p5_s < 0.0
        or parameters.maximum_discharge_m3_s <= 0.0
        or parameters.maximum_discharge_m3_s
        < parameters.basal_discharge_m3_s
        or parameters.adverse_head_shutdown_m <= 0.0
        or parameters.storage_area_m2 <= 0.0
        or parameters.residence_time_s <= 0.0
        or parameters.reserve_depth_m < 0.0
        or parameters.maximum_available_volume_fraction_per_step <= 0.0
        or parameters.maximum_available_volume_fraction_per_step > 1.0
    ):
        raise FishwayC2StorageError("invalid C2 storage parameters")
    return parameters


def smoothstep01(value: float) -> float:
    """C1-continuous transition from zero to one on [0, 1]."""

    x = min(max(float(value), 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def build_workspace(
    cell_areas_m2: np.ndarray,
    internal_left_cell_ids: np.ndarray,
    internal_right_cell_ids: np.ndarray,
    structure_face_mask: np.ndarray,
    upstream_overlap_area_m2: np.ndarray,
    downstream_overlap_area_m2: np.ndarray,
) -> FishwayC2StorageWorkspace:
    """Build P2 head weights and the cut-separated upstream component."""

    areas = _array("cell_areas_m2", cell_areas_m2, dtype=np.float64)
    left = _array(
        "internal_left_cell_ids",
        internal_left_cell_ids,
        dtype=np.int64,
    )
    right = _array(
        "internal_right_cell_ids",
        internal_right_cell_ids,
        dtype=np.int64,
    )
    structure = _array(
        "structure_face_mask",
        structure_face_mask,
        dtype=np.bool_,
    )
    upstream = _array(
        "upstream_overlap_area_m2",
        upstream_overlap_area_m2,
        dtype=np.float64,
    )
    downstream = _array(
        "downstream_overlap_area_m2",
        downstream_overlap_area_m2,
        dtype=np.float64,
    )
    cell_count = len(areas)
    if (
        len(upstream) != cell_count
        or len(downstream) != cell_count
        or len(left) != len(right)
        or len(left) != len(structure)
    ):
        raise FishwayC2StorageError(
            "C2 workspace array lengths do not agree"
        )
    if (
        np.any(areas <= 0.0)
        or np.any(upstream < 0.0)
        or np.any(downstream < 0.0)
        or np.any(upstream > areas + 1e-10)
        or np.any(downstream > areas + 1e-10)
        or np.any(left < 0)
        or np.any(right < 0)
        or np.any(left >= cell_count)
        or np.any(right >= cell_count)
        or np.any(left == right)
    ):
        raise FishwayC2StorageError("invalid C2 workspace geometry")
    upstream_ids = np.flatnonzero(upstream > 0.0).astype(np.int64)
    downstream_ids = np.flatnonzero(downstream > 0.0).astype(np.int64)
    if upstream_ids.size == 0 or downstream_ids.size == 0:
        raise FishwayC2StorageError(
            "both approved P2 footprints need at least one cell"
        )
    if np.intersect1d(upstream_ids, downstream_ids).size:
        raise FishwayC2StorageError(
            "upstream and downstream P2 cells overlap"
        )
    if not np.any(structure):
        raise FishwayC2StorageError(
            "the approved barrage cut has no structure faces"
        )

    adjacency: list[list[int]] = [[] for _ in range(cell_count)]
    for face in np.flatnonzero(~structure):
        a = int(left[face])
        b = int(right[face])
        adjacency[a].append(b)
        adjacency[b].append(a)
    component = np.zeros(cell_count, dtype=np.bool_)
    queue: deque[int] = deque([int(upstream_ids[0])])
    component[upstream_ids[0]] = True
    while queue:
        cell = queue.popleft()
        for neighbour in adjacency[cell]:
            if not component[neighbour]:
                component[neighbour] = True
                queue.append(neighbour)
    if not np.all(component[upstream_ids]):
        raise FishwayC2StorageError(
            "upstream P2 cells are split across hydraulic components"
        )
    if np.any(component[downstream_ids]):
        raise FishwayC2StorageError(
            "approved barrage cut does not separate the two P2 footprints"
        )
    component_ids = np.flatnonzero(component).astype(np.int64)
    upstream_total = float(np.sum(upstream))
    downstream_total = float(np.sum(downstream))
    if upstream_total <= 0.0 or downstream_total <= 0.0:
        raise FishwayC2StorageError("P2 overlap area is zero")
    return FishwayC2StorageWorkspace(
        cell_areas_m2=areas,
        upstream_overlap_area_m2=upstream,
        downstream_overlap_area_m2=downstream,
        upstream_head_weights=upstream / upstream_total,
        downstream_head_weights=downstream / downstream_total,
        upstream_component_mask=component,
        upstream_component_cell_ids=component_ids,
        upstream_p2_cell_ids=upstream_ids,
        downstream_p2_cell_ids=downstream_ids,
        structure_face_mask=structure,
    )


def measure_heads(
    state_h_hu_hv: np.ndarray,
    bed_elevation_m: np.ndarray,
    workspace: FishwayC2StorageWorkspace,
) -> dict[str, float]:
    """Measure free-surface head at P2 without using depth as link depth."""

    state = _array(
        "state_h_hu_hv",
        state_h_hu_hv,
        dtype=np.float64,
        ndim=2,
    )
    bed = _array(
        "bed_elevation_m",
        bed_elevation_m,
        dtype=np.float64,
    )
    cell_count = len(workspace.cell_areas_m2)
    if state.shape != (cell_count, 3) or bed.shape != (cell_count,):
        raise FishwayC2StorageError(
            "state or bed shape does not match C2 workspace"
        )
    if np.any(state[:, 0] < 0.0):
        raise FishwayC2StorageError("state contains negative depth")
    surface = state[:, 0] + bed
    upstream_head = float(
        np.sum(workspace.upstream_head_weights * surface)
    )
    downstream_head = float(
        np.sum(workspace.downstream_head_weights * surface)
    )
    return {
        "upstreamHeadM": upstream_head,
        "downstreamHeadM": downstream_head,
        "headDifferenceM": upstream_head - downstream_head,
        "upstreamP2OverlapWeighted2DDepthM": float(
            np.sum(
                workspace.upstream_head_weights * state[:, 0]
            )
        ),
        "downstreamP2OverlapWeighted2DDepthM": float(
            np.sum(
                workspace.downstream_head_weights * state[:, 0]
            )
        ),
    }


def _head_command(
    head_difference_m: float,
    parameters: FishwayC2StorageParameters,
) -> dict[str, float]:
    tolerance = 1e-14 * max(
        1.0,
        abs(head_difference_m),
        parameters.adverse_head_shutdown_m,
    )
    if (
        head_difference_m
        <= -parameters.adverse_head_shutdown_m + tolerance
    ):
        adverse_factor = 0.0
    elif head_difference_m >= -tolerance:
        adverse_factor = 1.0
    else:
        coordinate = (
            head_difference_m + parameters.adverse_head_shutdown_m
        ) / parameters.adverse_head_shutdown_m
        adverse_factor = smoothstep01(coordinate)
    basal = parameters.basal_discharge_m3_s * adverse_factor
    responsive = (
        parameters.head_sqrt_gain_m2p5_s
        * np.sqrt(max(head_difference_m, 0.0))
    )
    uncapped = basal + responsive
    command = min(uncapped, parameters.maximum_discharge_m3_s)
    return {
        "adverseHeadFactor": float(adverse_factor),
        "basalComponentM3S": float(basal),
        "headResponsiveComponentM3S": float(responsive),
        "uncappedCommandM3S": float(uncapped),
        "commandM3S": float(command),
    }


def equilibrium_storage_volume_m3(
    state_h_hu_hv: np.ndarray,
    bed_elevation_m: np.ndarray,
    workspace: FishwayC2StorageWorkspace,
    parameters: FishwayC2StorageParameters,
) -> float:
    """Return the diagnostic equilibrium storage for the current head."""

    params = _validate_parameters(parameters)
    head = measure_heads(state_h_hu_hv, bed_elevation_m, workspace)
    command = _head_command(head["headDifferenceM"], params)[
        "commandM3S"
    ]
    reserve_volume = params.storage_area_m2 * params.reserve_depth_m
    return float(reserve_volume + command * params.residence_time_s)


def link_step(
    state_h_hu_hv: np.ndarray,
    bed_elevation_m: np.ndarray,
    workspace: FishwayC2StorageWorkspace,
    parameters: FishwayC2StorageParameters,
    time_step_s: float,
    stored_volume_m3: float,
) -> dict[str, Any]:
    """Evaluate one conservative 2D-plus-storage C2 source step."""

    params = _validate_parameters(parameters)
    state = _array(
        "state_h_hu_hv",
        state_h_hu_hv,
        dtype=np.float64,
        ndim=2,
    )
    bed = _array(
        "bed_elevation_m",
        bed_elevation_m,
        dtype=np.float64,
    )
    cell_count = len(workspace.cell_areas_m2)
    if state.shape != (cell_count, 3) or bed.shape != (cell_count,):
        raise FishwayC2StorageError(
            "state or bed shape does not match C2 workspace"
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
    law = _head_command(heads["headDifferenceM"], params)

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
    next_storage = storage + time_step_s * (inflow - outflow)
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
    storage_rate = (next_storage - storage) / time_step_s
    extended_mass_residual = two_d_mass_rate + storage_rate
    if abs(extended_mass_residual) > 1e-12:
        raise FishwayC2StorageError(
            "2D-plus-storage mass residual exceeds 1e-12 m3/s"
        )
    if np.min(post_depth) < -1e-12:
        raise FishwayC2StorageError(
            "C2 source would create negative depth"
        )
    if (
        np.max(removed_fraction)
        > params.maximum_available_volume_fraction_per_step + 1e-12
    ):
        raise FishwayC2StorageError(
            "C2 source exceeds per-step available-volume limit"
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
            "storageRateM3S": float(storage_rate),
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
            "extendedMassResidualM3S": float(
                extended_mass_residual
            ),
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
        },
    }
