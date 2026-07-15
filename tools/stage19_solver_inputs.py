#!/usr/bin/env python3
"""Stage 19 spatial fields and boundary inputs.

This module only prepares solver inputs. Importing it or building fields never
advances a numerical case.
"""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path

import numpy as np


GRAVITY_M_S2 = 9.80665
MINIMUM_WET_DEPTH_M = 0.05
BOUNDARY_TAGS = {"shoreline": 0, "M": 1, "N": 2, "O": 3, "G": 4}
OPENING_FRACTION = {
    "fully_closed": 0.0,
    "uniform_25_percent": 0.25,
    "uniform_50_percent": 0.5,
    "uniform_100_percent": 1.0,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_water_mask(manifest_path: str | Path) -> tuple[dict, np.ndarray]:
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mask = np.zeros((int(manifest["height"]), int(manifest["width"])), dtype=bool)
    for relative in manifest["chunks"]:
        chunk_path = (path.parent / Path(relative).name).resolve()
        chunk = json.loads(chunk_path.read_text(encoding="utf-8"))
        start = int(chunk["startRow"])
        for offset, runs in enumerate(chunk["rows"]):
            require(len(runs) % 2 == 0, f"odd water run in {chunk_path}")
            for index in range(0, len(runs), 2):
                mask[start + offset, int(runs[index]) : int(runs[index + 1]) + 1] = True
    require(int(mask.sum()) == int(manifest["pixelCount"]), "water mask count mismatch")
    return manifest, mask


def mesh_geometry(package: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    local_vertices = package["vertex_local_mm"].astype(np.float64) * 1e-3
    image_vertices = package["vertex_image_millipixel"].astype(np.float64) * 1e-3
    triangles = package["triangles"].astype(np.int64)
    local_points = local_vertices[triangles]
    local_centroids = local_points.mean(axis=1)
    image_centroids = image_vertices[triangles].mean(axis=1)
    areas = np.abs(
        (local_points[:, 1, 0] - local_points[:, 0, 0])
        * (local_points[:, 2, 1] - local_points[:, 0, 1])
        - (local_points[:, 1, 1] - local_points[:, 0, 1])
        * (local_points[:, 2, 0] - local_points[:, 0, 0])
    ) / 2.0
    require(np.isfinite(areas).all() and np.all(areas > 0), "invalid mesh areas")
    return {
        "localVertices": local_vertices,
        "imageVertices": image_vertices,
        "triangles": triangles,
        "localCentroids": local_centroids,
        "imageCentroids": image_centroids,
        "areas": areas,
    }


def _adjacency(package: dict[str, np.ndarray], centroids: np.ndarray) -> list[list[tuple[int, float]]]:
    cells = package["internal_face_cells"].astype(np.int64)
    result: list[list[tuple[int, float]]] = [[] for _ in range(len(centroids))]
    for left, right in cells:
        weight = float(np.linalg.norm(centroids[right] - centroids[left]))
        require(math.isfinite(weight) and weight > 0, "invalid adjacency weight")
        result[int(left)].append((int(right), weight))
        result[int(right)].append((int(left), weight))
    return result


def _multi_source_distances(adjacency: list[list[tuple[int, float]]], seeds: np.ndarray) -> np.ndarray:
    distances = np.full(len(adjacency), np.inf, dtype=np.float64)
    queue: list[tuple[float, int]] = []
    for seed in np.unique(seeds.astype(np.int64)):
        distances[seed] = 0.0
        heapq.heappush(queue, (0.0, int(seed)))
    require(queue, "boundary has no seed cells")
    while queue:
        distance, cell = heapq.heappop(queue)
        if distance != distances[cell]:
            continue
        for neighbour, weight in adjacency[cell]:
            candidate = distance + weight
            if candidate < distances[neighbour]:
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    require(np.isfinite(distances).all(), "mesh graph is disconnected")
    return distances


def classify_branch_ownership(package: dict[str, np.ndarray], geometry: dict) -> np.ndarray:
    tags = package["boundary_face_tag"].astype(np.uint8)
    boundary_cells = package["boundary_face_cell"].astype(np.int64)
    adjacency = _adjacency(package, geometry["localCentroids"])
    distances = []
    for tag in (1, 2, 3, 4):
        distances.append(_multi_source_distances(adjacency, boundary_cells[tags == tag]))
    owner = np.argmin(np.vstack(distances), axis=0).astype(np.uint8) + 1
    require(set(np.unique(owner).tolist()) == {1, 2, 3, 4}, "all branch owners must be represented")
    return owner


def _normalised_profile(x_from_centre: np.ndarray, sigma: float) -> np.ndarray:
    edge = math.exp(-0.5 / (sigma * sigma))
    return (np.exp(-0.5 * (x_from_centre / sigma) ** 2) - edge) / (1.0 - edge)


def shore_fields(mask: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    from scipy.ndimage import distance_transform_edt, gaussian_filter

    require(sigma in (0.28, 0.36, 0.46), "unsupported approved sigma")
    extension = 220
    padded = np.pad(mask, ((extension, extension), (1, 1)), constant_values=False)
    padded[:extension, 1:-1] = mask[0]
    padded[extension + mask.shape[0] :, 1:-1] = mask[-1]
    distance = distance_transform_edt(padded)[extension : extension + mask.shape[0], 1:-1]
    scale = float(np.percentile(distance[mask], 95.0))
    centre_fraction = np.clip(distance / max(scale, 1.0), 0.0, 1.0)
    relative_depth = _normalised_profile(1.0 - centre_fraction, sigma)
    weights = gaussian_filter(mask.astype(np.float64), sigma=1.6, mode="nearest")
    relative_depth = np.divide(
        gaussian_filter(relative_depth * mask, sigma=1.6, mode="nearest"),
        np.maximum(weights, 1e-12),
        out=np.zeros_like(relative_depth),
        where=weights > 0,
    )
    relative_depth[~mask] = 0.0
    centre_fraction[~mask] = 0.0
    return np.clip(relative_depth, 0.0, 1.0), centre_fraction


def _sample_raster(raster: np.ndarray, image_centroids: np.ndarray) -> np.ndarray:
    x = np.clip(np.rint(image_centroids[:, 0]).astype(np.int64), 0, raster.shape[1] - 1)
    y = np.clip(np.rint(image_centroids[:, 1]).astype(np.int64), 0, raster.shape[0] - 1)
    return raster[y, x].astype(np.float64)


def _mean_match_depth(
    relative: np.ndarray,
    areas: np.ndarray,
    group: np.ndarray,
    target_mean: float,
) -> np.ndarray:
    require(target_mean > MINIMUM_WET_DEPTH_M, "target mean depth is below wet floor")
    mean_relative = float(np.average(relative[group], weights=areas[group]))
    require(mean_relative > 1e-6, "relative-depth group mean is zero")
    scale = (target_mean - MINIMUM_WET_DEPTH_M) / mean_relative
    return MINIMUM_WET_DEPTH_M + scale * relative


def build_case_fields(
    case: dict,
    package: dict[str, np.ndarray],
    mask: np.ndarray,
    *,
    geometry: dict | None = None,
    owner: np.ndarray | None = None,
    shore_cache: dict[float, tuple[np.ndarray, np.ndarray]] | None = None,
) -> dict[str, np.ndarray | float | dict]:
    geometry = geometry or mesh_geometry(package)
    owner = owner if owner is not None else classify_branch_ownership(package, geometry)
    sigma = float(case["bathymetry"]["sigma"])
    shore_cache = shore_cache if shore_cache is not None else {}
    if sigma not in shore_cache:
        shore_cache[sigma] = shore_fields(mask, sigma)
    relative_raster, centre_raster = shore_cache[sigma]
    relative = _sample_raster(relative_raster, geometry["imageCentroids"])
    centre_fraction = _sample_raster(centre_raster, geometry["imageCentroids"])
    areas = geometry["areas"]
    main = np.isin(owner, [1, 3])
    tributary = np.isin(owner, [2, 4])
    require(np.all(main | tributary), "unclassified branch cell")
    depth = np.empty(len(areas), dtype=np.float64)
    main_depth = _mean_match_depth(
        relative, areas, main, float(case["bathymetry"]["mainstemMeanDepthM"])
    )
    tributary_depth = _mean_match_depth(
        relative, areas, tributary, float(case["bathymetry"]["tributaryMeanDepthM"])
    )
    depth[main] = main_depth[main]
    depth[tributary] = tributary_depth[tributary]
    require(np.isfinite(depth).all() and np.all(depth >= MINIMUM_WET_DEPTH_M), "invalid depth field")

    base_n = float(case["roughness"]["manningOpenChannel"])
    shallow_multiplier = float(case["roughness"]["shallowMarginMultiplier"])
    structure_multiplier = float(case["roughness"]["structureVicinityMultiplier"])
    manning = base_n * (1.0 + (shallow_multiplier - 1.0) * (1.0 - centre_fraction) ** 2)
    structure_cells = np.unique(np.concatenate([
        package["internal_face_cells"].astype(np.int64)[
            package["barrage_face_ids"].astype(np.int64)
        ].reshape(-1),
        package["fishway_cells"].astype(np.int64),
    ]))
    manning[structure_cells] *= structure_multiplier
    require(np.isfinite(manning).all() and np.all(manning > 0), "invalid Manning field")

    opening = OPENING_FRACTION.get(case["barrage"]["scenario"])
    require(opening is not None, "unsupported barrage scenario")
    coefficient = float(case["barrage"]["effectiveDischargeCoefficient"])
    barrage_transmissivity = float(opening * coefficient)
    require(0.0 <= barrage_transmissivity <= 1.0, "invalid barrage transmissivity")

    return {
        "geometry": geometry,
        "branchOwner": owner,
        "relativeDepthFraction": relative,
        "centreFraction": centre_fraction,
        "initialWaterDepthM": depth,
        "bedElevationM": -depth,
        "manningN": manning,
        "structureCells": structure_cells,
        "barrageTransmissivity": barrage_transmissivity,
        "boundaryDischargeM3S": {
            "N": float(case["boundaries"]["N"]["dischargeM3S"]),
            "O": float(case["boundaries"]["O"]["dischargeM3S"]),
            "G": float(case["boundaries"]["G"]["dischargeM3S"]),
        },
        "tide": {
            "phaseShiftMinutes": float(case["boundaries"]["M"]["phaseShiftMinutes"]),
            "amplitudeMultiplier": float(case["boundaries"]["M"]["amplitudeMultiplier"]),
            "meanOffsetM": case["boundaries"]["M"]["meanOffsetM"],
        },
        "fishway": {
            "mode": case["fishway"]["mode"],
            "effectiveDischargeCoefficient": float(
                case["fishway"]["effectiveDischargeCoefficient"]
            ),
            "effectiveAreaM2": float(case["fishway"]["effectiveAreaM2"]),
        },
    }


def tide_anomaly_m(simulated_seconds: float, tide: dict, candidate: dict) -> float:
    require(tide.get("meanOffsetM") is None, "absolute M offset must remain unassigned")
    curve = candidate["candidateCurve"]
    values = np.asarray(
        curve["relativeAnomalyM"] + [curve["nextDayZeroHourRelativeAnomalyM"]],
        dtype=np.float64,
    )
    shifted_hour = simulated_seconds / 3600.0 + float(tide["phaseShiftMinutes"]) / 60.0
    if shifted_hour < 0:
        shifted_hour += 24.0
    require(0.0 <= shifted_hour <= 24.0, "M tide curve exhausted before case completion")
    reference = float(np.interp(shifted_hour, np.arange(25, dtype=np.float64), values))
    return reference * float(tide["amplitudeMultiplier"])


def fishway_discharge_m3s(state: np.ndarray, fields: dict, package: dict) -> float:
    fishway = fields["fishway"]
    if fishway["mode"] == "disabled":
        return 0.0
    require(fishway["mode"] == "head_difference_relation_ensemble", "unsupported fishway mode")
    cells = package["fishway_cells"].astype(np.int64)
    bed = fields["bedElevationM"]
    eta = state[cells, 0] + bed[cells]
    head = float(eta[0] - eta[1])
    magnitude = (
        fishway["effectiveDischargeCoefficient"]
        * fishway["effectiveAreaM2"]
        * math.sqrt(2.0 * GRAVITY_M_S2 * abs(head))
    )
    return math.copysign(magnitude, head) if head else 0.0
