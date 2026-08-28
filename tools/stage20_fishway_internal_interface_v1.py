#!/usr/bin/env python3
"""Standalone candidate for a mass-conserving, always-on fishway interface.

This module is intentionally not connected to the Stage 20 solver.  It replaces
silent discharge capping at a small P2 donor footprint with a fail-stop virtual
interface backed by the whole upstream hydraulic component.  The approved P2
footprints remain the interface seeds and outlet footprint.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np


class FishwayInterfaceError(ValueError):
    """Invalid interface geometry, state, or operating request."""


class FishwaySupplyError(RuntimeError):
    """The prescribed constant flow cannot be supplied without violating safety."""


@dataclass(frozen=True)
class FishwayInternalInterfaceWorkspace:
    cell_areas_m2: np.ndarray
    donor_overlap_area_m2: np.ndarray
    receiver_overlap_area_m2: np.ndarray
    donor_support_area_m2: np.ndarray
    upstream_component_mask: np.ndarray
    expansion_rank: np.ndarray
    receiver_weights: np.ndarray
    donor_seed_cell_ids: np.ndarray
    receiver_cell_ids: np.ndarray
    blocked_cut_face_ids: np.ndarray


def _array(
    name: str,
    values: np.ndarray,
    *,
    dtype: Any,
    ndim: int = 1,
) -> np.ndarray:
    result = np.asarray(values, dtype=dtype)
    if result.ndim != ndim:
        raise FishwayInterfaceError(f"{name} must have {ndim} dimensions")
    if np.issubdtype(result.dtype, np.floating) and not np.isfinite(result).all():
        raise FishwayInterfaceError(f"{name} contains non-finite values")
    return result.copy()


def build_workspace(
    cell_areas_m2: np.ndarray,
    left_cells: np.ndarray,
    right_cells: np.ndarray,
    blocked_cut_face_mask: np.ndarray,
    donor_overlap_area_m2: np.ndarray,
    receiver_overlap_area_m2: np.ndarray,
) -> FishwayInternalInterfaceWorkspace:
    """Build the immutable interface topology and upstream expansion ordering."""

    areas = _array("cell_areas_m2", cell_areas_m2, dtype=np.float64)
    left = _array("left_cells", left_cells, dtype=np.int64)
    right = _array("right_cells", right_cells, dtype=np.int64)
    blocked = _array(
        "blocked_cut_face_mask",
        blocked_cut_face_mask,
        dtype=bool,
    )
    donor_overlap = _array(
        "donor_overlap_area_m2",
        donor_overlap_area_m2,
        dtype=np.float64,
    )
    receiver_overlap = _array(
        "receiver_overlap_area_m2",
        receiver_overlap_area_m2,
        dtype=np.float64,
    )
    cell_count = len(areas)
    face_count = len(left)
    if (
        len(right) != face_count
        or len(blocked) != face_count
        or len(donor_overlap) != cell_count
        or len(receiver_overlap) != cell_count
    ):
        raise FishwayInterfaceError("interface array lengths do not agree")
    if (
        np.any(areas <= 0.0)
        or np.any(donor_overlap < 0.0)
        or np.any(receiver_overlap < 0.0)
        or np.any(left < 0)
        or np.any(right < 0)
        or np.any(left >= cell_count)
        or np.any(right >= cell_count)
    ):
        raise FishwayInterfaceError("interface geometry contains invalid values")
    if np.any(donor_overlap > areas + 1e-10) or np.any(
        receiver_overlap > areas + 1e-10
    ):
        raise FishwayInterfaceError("footprint overlap exceeds cell area")
    donor_seed_ids = np.flatnonzero(donor_overlap > 0.0).astype(np.int64)
    receiver_ids = np.flatnonzero(receiver_overlap > 0.0).astype(np.int64)
    if donor_seed_ids.size == 0 or receiver_ids.size == 0:
        raise FishwayInterfaceError("both P2 footprints need at least one cell")
    if np.intersect1d(donor_seed_ids, receiver_ids).size:
        raise FishwayInterfaceError("P2 donor and receiver cells overlap")

    adjacency: list[list[int]] = [[] for _ in range(cell_count)]
    for face_id in range(face_count):
        if blocked[face_id]:
            continue
        a = int(left[face_id])
        b = int(right[face_id])
        adjacency[a].append(b)
        adjacency[b].append(a)

    rank = np.full(cell_count, -1, dtype=np.int32)
    queue: deque[int] = deque()
    for cell_id in donor_seed_ids:
        rank[cell_id] = 0
        queue.append(int(cell_id))
    while queue:
        cell_id = queue.popleft()
        next_rank = int(rank[cell_id]) + 1
        for neighbour in adjacency[cell_id]:
            if rank[neighbour] < 0:
                rank[neighbour] = next_rank
                queue.append(neighbour)
    upstream = rank >= 0
    if np.any(upstream[receiver_ids]):
        raise FishwayInterfaceError(
            "P2 receiver remains connected to donor after removing the full barrage cut"
        )
    if not np.all(upstream[donor_seed_ids]):
        raise FishwayInterfaceError("P2 donor seeds are not in the upstream component")

    support_area = np.zeros(cell_count, dtype=np.float64)
    support_area[upstream] = areas[upstream]
    support_area[donor_seed_ids] = donor_overlap[donor_seed_ids]
    receiver_weights = receiver_overlap / float(np.sum(receiver_overlap))
    return FishwayInternalInterfaceWorkspace(
        cell_areas_m2=areas,
        donor_overlap_area_m2=donor_overlap,
        receiver_overlap_area_m2=receiver_overlap,
        donor_support_area_m2=support_area,
        upstream_component_mask=upstream,
        expansion_rank=rank,
        receiver_weights=receiver_weights,
        donor_seed_cell_ids=donor_seed_ids,
        receiver_cell_ids=receiver_ids,
        blocked_cut_face_ids=np.flatnonzero(blocked).astype(np.int64),
    )


def constant_flux_sources(
    state_h_hu_hv: np.ndarray,
    workspace: FishwayInternalInterfaceWorkspace,
    q0_m3_s: float,
    time_step_s: float,
    *,
    reserve_depth_m: float = 0.05,
    maximum_available_volume_fraction_per_step: float = 0.02,
) -> dict[str, Any]:
    """Return exact-Q0 conservative source rates without mutating the state.

    The donor search starts at the approved P2 upstream footprint and expands
    through graph layers of the upstream component.  If even the complete
    component cannot safely supply Q0, the function raises FishwaySupplyError;
    it never silently reduces the requested discharge.
    """

    state = _array(
        "state_h_hu_hv",
        state_h_hu_hv,
        dtype=np.float64,
        ndim=2,
    )
    cell_count = len(workspace.cell_areas_m2)
    if state.shape != (cell_count, 3):
        raise FishwayInterfaceError("state shape does not match the workspace")
    if (
        not np.isfinite(q0_m3_s)
        or q0_m3_s <= 0.0
        or not np.isfinite(time_step_s)
        or time_step_s <= 0.0
        or not np.isfinite(reserve_depth_m)
        or reserve_depth_m < 0.0
        or not np.isfinite(maximum_available_volume_fraction_per_step)
        or maximum_available_volume_fraction_per_step <= 0.0
        or maximum_available_volume_fraction_per_step > 1.0
    ):
        raise FishwayInterfaceError("invalid constant-flow safety parameters")
    if np.any(state[:, 0] < 0.0):
        raise FishwayInterfaceError("state contains negative depth")

    available = workspace.donor_support_area_m2 * np.maximum(
        state[:, 0] - reserve_depth_m,
        0.0,
    )
    required_available = (
        q0_m3_s
        * time_step_s
        / maximum_available_volume_fraction_per_step
    )
    ranks = workspace.expansion_rank
    maximum_rank = int(np.max(ranks))
    upstream_ranks = ranks[workspace.upstream_component_mask]
    available_by_rank = np.bincount(
        upstream_ranks,
        weights=available[workspace.upstream_component_mask],
        minlength=maximum_rank + 1,
    )
    cumulative_available = np.cumsum(available_by_rank)
    component_available = float(cumulative_available[-1])
    selected_rank = int(
        np.searchsorted(
            cumulative_available + 1e-15,
            required_available,
            side="left",
        )
    )
    if selected_rank > maximum_rank:
        raise FishwaySupplyError(
            "the complete upstream component cannot supply the prescribed "
            f"Q0={q0_m3_s} m3/s at dt={time_step_s} s: "
            f"available={component_available} m3, "
            f"required={required_available} m3"
        )

    selected = (ranks >= 0) & (ranks <= selected_rank) & (available > 0.0)
    selected_available = float(np.sum(available[selected]))
    donor_rate = np.zeros(cell_count, dtype=np.float64)
    donor_rate[selected] = q0_m3_s * available[selected] / selected_available
    receiver_rate = q0_m3_s * workspace.receiver_weights
    mass_rate = receiver_rate - donor_rate

    depth = np.maximum(state[:, 0], 1e-12)
    donor_hu_rate = -donor_rate * state[:, 1] / depth
    donor_hv_rate = -donor_rate * state[:, 2] / depth
    hu_rate = donor_hu_rate
    hv_rate = donor_hv_rate
    removed_fraction = np.zeros(cell_count, dtype=np.float64)
    removed_fraction[selected] = (
        time_step_s * donor_rate[selected] / available[selected]
    )
    post_step_depth = (
        state[:, 0]
        + time_step_s
        * mass_rate
        / workspace.cell_areas_m2
    )
    mass_residual = float(np.sum(mass_rate))
    if abs(mass_residual) > 1e-12:
        raise FishwayInterfaceError(
            f"internal interface mass residual is {mass_residual} m3/s"
        )
    if np.min(post_step_depth) < -1e-12:
        raise FishwayInterfaceError("candidate source would create negative depth")
    if (
        np.max(removed_fraction)
        > maximum_available_volume_fraction_per_step + 1e-12
    ):
        raise FishwayInterfaceError("candidate source exceeds per-step withdrawal cap")

    return {
        "massRateM3SByCell": mass_rate,
        "horizontalMomentumRateXByCell": hu_rate,
        "horizontalMomentumRateYByCell": hv_rate,
        "postSourceDepthM": post_step_depth,
        "diagnostics": {
            "requestedQ0M3S": float(q0_m3_s),
            "effectiveQ0M3S": float(np.sum(receiver_rate)),
            "massResidualM3S": mass_residual,
            "timeStepS": float(time_step_s),
            "reserveDepthM": float(reserve_depth_m),
            "maximumAvailableVolumeFractionPerStep": float(
                maximum_available_volume_fraction_per_step
            ),
            "selectedExpansionRank": selected_rank,
            "selectedDonorCellCount": int(np.sum(selected)),
            "selectedAvailableVolumeM3": selected_available,
            "requiredAvailableVolumeM3": required_available,
            "maximumActualAvailableVolumeFractionRemoved": float(
                np.max(removed_fraction)
            ),
            "minimumPostSourceDepthM": float(np.min(post_step_depth)),
            "minimumSelectedDonorPostSourceDepthM": float(
                np.min(post_step_depth[selected])
            ),
            "minimumReceiverPostSourceDepthM": float(
                np.min(post_step_depth[workspace.receiver_cell_ids])
            ),
            "receiverCellCount": int(np.sum(receiver_rate > 0.0)),
            "receiverHorizontalMomentumAdded": 0.0,
            "donorMomentumRemovedWithWithdrawnMass": True,
            "silentDischargeCapping": False,
            "fullQOrFailStop": True,
        },
    }
