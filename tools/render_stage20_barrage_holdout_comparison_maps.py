#!/usr/bin/env python3
"""Render offline Stage 20 barrage 50% holdout comparison maps.

The renderer consumes only an already-evaluable post-run analysis and its
digest-declared derived fields.  It never invokes the solver or accesses the
network.  The resulting maps compare the direct 50% run with the componentwise
50:50 endpoint interpolation; they are not a physical-accuracy claim.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont


ANALYSIS_SCHEMA = "onga-stage20-barrage-holdout-recovery-postrun-analysis-v1"
MANIFEST_SCHEMA = "onga-stage20-barrage-holdout-comparison-map-manifest-v1"
MANIFEST_STATUS = "rendered_holdout_comparison_not_physical_validation"
ALLOWED_ANALYSIS_STATUSES = {
    "evaluated_passed_thresholds",
    "evaluated_failed_thresholds",
}
EXPECTED_HOURS = (-12, -11, -10, -9, -8)
REGION_ORDER = ("estuary", "barrage", "confluence", "fishway")
FIELD_KEYS = ("waterDepthM", "velocityUms", "velocityVms")
DERIVED_KINDS = ("direct", "interpolated", "velocity_error", "depth_error")
CIRCUMFERENCE_M = 40075016.68557849
PANEL_WIDTH = 500
PANEL_HEIGHT = 310
DISCLAIMER_JA = "補間整合性の比較／実測・予報精度の検証ではない"
GSI_ATTRIBUTION_JA = "背景：国土地理院「全国最新写真（シームレス）」を加工"
PANEL_TITLES = (
    "直接計算（河口堰50%）",
    "端点50:50補間（全閉＋全開）",
    "速度差（補間−直接）",
)
SPEED_STOPS = (
    (0.0, (27, 107, 174)),
    (0.32, (37, 167, 184)),
    (0.63, (246, 188, 65)),
    (1.0, (218, 69, 55)),
)
ERROR_STOPS = (
    (0.0, (68, 1, 84)),
    (0.34, (59, 82, 139)),
    (0.68, (33, 145, 140)),
    (1.0, (253, 231, 37)),
)


class RenderError(RuntimeError):
    """An invalid or incomplete presentation input."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RenderError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"JSON input is missing or not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RenderError(f"invalid JSON input {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def portable_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def output_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def prepare_output(path: Path) -> None:
    require(not path.is_symlink(), f"output may not be a symlink: {path}")
    if path.exists():
        require(path.is_file(), f"output must be a regular file path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def load_mesh(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray], dict[str, Any]]:
    manifest = load_json(path)
    require(manifest.get("schema") == "onga-stage20-browser-mesh-v2", "mesh-v2 manifest schema mismatch")
    binary_record = manifest.get("binary")
    require(isinstance(binary_record, dict), "mesh binary record is missing")
    binary_path = path.parent / str(binary_record.get("url"))
    require(binary_path.is_file() and not binary_path.is_symlink(), "mesh binary is missing or not a regular file")
    payload = binary_path.read_bytes()
    require(len(payload) == binary_record.get("byteLength"), "mesh binary length mismatch")
    binary_sha = sha256_bytes(payload)
    require(binary_sha == binary_record.get("sha256"), "mesh binary digest mismatch")
    dtype_by_name = {"int32": np.dtype("<i4"), "uint8": np.dtype("u1")}
    arrays: dict[str, np.ndarray] = {}
    descriptors = manifest.get("arrays")
    require(isinstance(descriptors, dict), "mesh array inventory is missing")
    for name, descriptor in descriptors.items():
        require(isinstance(descriptor, dict), f"mesh descriptor is invalid: {name}")
        dtype_name = descriptor.get("dtype")
        require(dtype_name in dtype_by_name, f"unsupported mesh dtype for {name}")
        shape = descriptor.get("shape")
        require(isinstance(shape, list) and shape and all(isinstance(v, int) and v > 0 for v in shape), f"invalid mesh shape for {name}")
        dtype = dtype_by_name[str(dtype_name)]
        offset = descriptor.get("byteOffset")
        byte_length = descriptor.get("byteLength")
        expected_length = math.prod(shape) * dtype.itemsize
        require(isinstance(offset, int) and offset >= 0, f"invalid mesh offset for {name}")
        require(byte_length == expected_length, f"mesh array length mismatch for {name}")
        encoded = payload[offset : offset + expected_length]
        require(len(encoded) == expected_length, f"mesh array is truncated: {name}")
        require(sha256_bytes(encoded) == descriptor.get("sha256"), f"mesh array digest mismatch for {name}")
        arrays[name] = np.frombuffer(encoded, dtype=dtype).reshape(shape).copy()
    required = {
        "vertex_local_mm",
        "vertex_image_millipixel",
        "triangles",
        "internal_face_vertices",
        "barrage_face_ids",
        "fishway_cells",
    }
    require(required.issubset(arrays), "mesh is missing a required geometry array")
    cell_count = int(manifest.get("counts", {}).get("cells", -1))
    require(cell_count == 50199 and arrays["triangles"].shape == (cell_count, 3), "mesh cell inventory mismatch")
    record = {
        "manifest": portable_path(path, path.parents[4]),
        "manifestSha256": sha256_file(path),
        "binarySha256": binary_sha,
        "cellCount": cell_count,
        "vertexCount": int(manifest.get("counts", {}).get("vertices", -1)),
    }
    return manifest, arrays, record


def load_region_masks(
    manifest_path: Path,
    repo_root: Path,
    expected_mesh_sha: str,
    expected_cells: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, np.ndarray], dict[str, Any]]:
    manifest = load_json(manifest_path)
    require(manifest.get("schema") == "onga-stage20-barrage-holdout-region-masks-v1", "regional-mask schema mismatch")
    require(manifest.get("status") == "digest_locked_before_recovery_execution", "regional masks are not digest locked")
    mesh_record = manifest.get("mesh")
    require(isinstance(mesh_record, dict), "regional-mask mesh record is missing")
    require(mesh_record.get("binarySha256") == expected_mesh_sha, "regional masks do not match mesh-v2")
    require(mesh_record.get("cellCount") == expected_cells, "regional-mask cell count mismatch")
    binary_record = manifest.get("binary")
    require(isinstance(binary_record, dict), "regional-mask binary record is missing")
    binary_path = resolve_path(repo_root, str(binary_record.get("path")))
    require(binary_path.is_file() and not binary_path.is_symlink(), "regional-mask binary is missing")
    payload = binary_path.read_bytes()
    require(len(payload) == binary_record.get("byteLength"), "regional-mask binary length mismatch")
    require(sha256_bytes(payload) == binary_record.get("sha256"), "regional-mask binary digest mismatch")
    views = manifest.get("views")
    require(isinstance(views, list), "regional-mask view inventory is missing")
    require([view.get("id") for view in views if isinstance(view, dict)] == list(REGION_ORDER), "regional-mask view order mismatch")
    masks: dict[str, np.ndarray] = {}
    for view in views:
        require(isinstance(view, dict), "regional-mask view record is invalid")
        view_id = str(view["id"])
        require(view.get("dtype") == "int32-le", f"regional-mask dtype mismatch for {view_id}")
        offset = view.get("byteOffset")
        byte_length = view.get("byteLength")
        cell_count = view.get("cellCount")
        require(isinstance(offset, int) and offset >= 0, f"regional-mask offset is invalid for {view_id}")
        require(isinstance(cell_count, int) and cell_count > 0, f"regional-mask count is invalid for {view_id}")
        require(byte_length == cell_count * 4, f"regional-mask length mismatch for {view_id}")
        encoded = payload[offset : offset + byte_length]
        require(len(encoded) == byte_length, f"regional-mask payload is truncated for {view_id}")
        require(sha256_bytes(encoded) == view.get("sha256"), f"regional-mask digest mismatch for {view_id}")
        ids = np.frombuffer(encoded, dtype="<i4").astype(np.int64)
        require(np.all((ids >= 0) & (ids < expected_cells)), f"regional-mask cell ID is out of range for {view_id}")
        require(np.array_equal(ids, np.unique(ids)), f"regional-mask IDs are not strictly unique and sorted for {view_id}")
        masks[view_id] = ids
    record = {
        "manifest": portable_path(manifest_path, repo_root),
        "manifestSha256": sha256_file(manifest_path),
        "binary": portable_path(binary_path, repo_root),
        "binarySha256": sha256_file(binary_path),
    }
    return manifest, views, masks, record


def validate_declared_file(record: Mapping[str, Any], repo_root: Path, kind: str) -> Path:
    require(record.get("kind") == kind, f"derived field kind mismatch: expected {kind}")
    value = record.get("path")
    require(isinstance(value, str) and value, f"derived field path is missing for {kind}")
    path = resolve_path(repo_root, value)
    require(path.is_file() and not path.is_symlink(), f"derived field is missing or not a regular file: {kind}")
    require(path.stat().st_size == record.get("byteLength"), f"derived field length mismatch: {kind}")
    require(sha256_file(path) == record.get("sha256"), f"derived field digest mismatch: {kind}")
    return path


def load_npz(path: Path, expected_keys: tuple[str, ...], expected_cells: int, kind: str) -> dict[str, np.ndarray]:
    try:
        with np.load(path, allow_pickle=False) as package:
            require(set(package.files) == set(expected_keys), f"NPZ key inventory mismatch: {kind}")
            arrays = {key: np.asarray(package[key]).copy() for key in expected_keys}
    except (OSError, ValueError, KeyError) as error:
        raise RenderError(f"invalid NPZ input for {kind}: {error}") from error
    for key, array in arrays.items():
        require(array.dtype == np.dtype("float64"), f"{kind}.{key} must be float64")
        require(array.shape == (expected_cells,), f"{kind}.{key} shape mismatch")
        require(np.all(np.isfinite(array)), f"{kind}.{key} contains a non-finite value")
    return arrays


def validate_analysis(
    analysis_path: Path,
    repo_root: Path,
    masks: Mapping[str, np.ndarray],
    expected_cells: int,
) -> tuple[dict[str, Any], dict[str, dict[str, np.ndarray]], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    analysis = load_json(analysis_path)
    require(analysis.get("schema") == ANALYSIS_SCHEMA, "post-run analysis schema mismatch")
    status = analysis.get("status")
    require(status in ALLOWED_ANALYSIS_STATUSES, "post-run analysis is not an evaluated pass/fail record")
    evaluation = analysis.get("holdoutEvaluation")
    require(isinstance(evaluation, dict) and evaluation.get("evaluable") is True, "holdout analysis is not evaluable")
    expected_acceptance = "passed" if status == "evaluated_passed_thresholds" else "failed"
    require(evaluation.get("acceptanceResult") == expected_acceptance, "analysis status and acceptance result disagree")
    require(evaluation.get("expectedComparisonCount") == 20, "expected comparison count mismatch")
    require(evaluation.get("evaluatedComparisonCount") == 20, "evaluated comparison count mismatch")
    thresholds = evaluation.get("thresholds")
    metric_keys = (
        "velocityVectorRmseMPS",
        "speedMaeMPS",
        "p95DirectionErrorDeg",
        "depthRmseM",
        "maximumAbsoluteDepthErrorM",
    )
    require(isinstance(thresholds, dict) and set(thresholds) == set(metric_keys), "holdout threshold inventory mismatch")
    for key in metric_keys:
        threshold = thresholds[key]
        require(isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and math.isfinite(float(threshold)) and float(threshold) >= 0.0, f"invalid threshold {key}")
    rows = evaluation.get("perHourRegion")
    require(isinstance(rows, list) and len(rows) == 20, "per-hour regional metric inventory mismatch")
    expected_pairs = [(hour, region) for hour in EXPECTED_HOURS for region in REGION_ORDER]
    actual_pairs: list[tuple[int, str]] = []
    for row in rows:
        require(isinstance(row, dict), "holdout metric row is invalid")
        hour = row.get("modelHour")
        region = row.get("regionId")
        require(isinstance(hour, int) and isinstance(region, str), "holdout metric row identity is invalid")
        require(region in masks, f"unknown holdout region: {region}")
        actual_pairs.append((hour, region))
        require(row.get("cellCount") == int(masks[region].size), f"metric cell count mismatch for {region} at hour {hour}")
        computed_checks: dict[str, bool] = {}
        for key in metric_keys:
            value = row.get(key)
            require(isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) >= 0.0, f"invalid metric {key}")
            computed_checks[key] = float(value) <= float(thresholds[key])
        require(row.get("thresholdChecks") == computed_checks, "metric threshold checks do not match the declared thresholds")
        require(isinstance(row.get("passed"), bool), "metric pass flag is invalid")
        require(row["passed"] is all(computed_checks.values()), "metric pass flag does not match its threshold checks")
    require(actual_pairs == expected_pairs, "per-hour regional metric order or coverage mismatch")
    passed_count = sum(bool(row["passed"]) for row in rows)
    failed_count = len(rows) - passed_count
    require(evaluation.get("passedComparisonCount") == passed_count, "passed comparison count mismatch")
    require(evaluation.get("failedComparisonCount") == failed_count, "failed comparison count mismatch")
    require((failed_count == 0) is (status == "evaluated_passed_thresholds"), "analysis status does not match the regional decisions")
    selection = evaluation.get("worstMapSelection")
    require(isinstance(selection, dict), "worst-map selection is missing")
    require(selection.get("metric") == "velocityVectorRmseMPS", "worst-map selection metric mismatch")
    require(selection.get("convention") == "maximum_across_five_hours_and_four_regions", "worst-map selection convention mismatch")
    worst_row = max(rows, key=lambda item: float(item["velocityVectorRmseMPS"]))
    require(selection.get("modelHour") == worst_row["modelHour"], "worst-map model hour mismatch")
    require(selection.get("regionId") == worst_row["regionId"], "worst-map region mismatch")
    require(float(selection.get("value")) == float(worst_row["velocityVectorRmseMPS"]), "worst-map value mismatch")
    model_hour = int(selection["modelHour"])
    selected_rows = [row for row in rows if row["modelHour"] == model_hour]
    require([row["regionId"] for row in selected_rows] == list(REGION_ORDER), "selected-hour region inventory mismatch")

    derived = analysis.get("derivedArtifacts")
    require(isinstance(derived, dict) and derived.get("createdThisInvocation") is True, "map-ready fields were not created by this analysis")
    derived_selection = derived.get("selectionConvention")
    require(isinstance(derived_selection, dict) and derived_selection == selection, "derived-field selection convention mismatch")
    records = derived.get("mapReadyWorstHourFields")
    require(isinstance(records, list) and len(records) == 4, "map-ready field inventory mismatch")
    require([record.get("kind") for record in records if isinstance(record, dict)] == list(DERIVED_KINDS), "map-ready field order mismatch")
    fields: dict[str, dict[str, np.ndarray]] = {}
    portable_records: list[dict[str, Any]] = []
    for kind, raw_record in zip(DERIVED_KINDS, records):
        require(isinstance(raw_record, dict), f"derived field record is invalid: {kind}")
        require(raw_record.get("modelHour") == model_hour, f"derived field model hour mismatch: {kind}")
        path = validate_declared_file(raw_record, repo_root, kind)
        expected_keys = ("waterDepthErrorM",) if kind == "depth_error" else FIELD_KEYS
        fields[kind] = load_npz(path, expected_keys, expected_cells, kind)
        portable_records.append({
            "kind": kind,
            "modelHour": model_hour,
            "path": portable_path(path, repo_root),
            "byteLength": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    direct = fields["direct"]
    interpolated = fields["interpolated"]
    velocity_error = fields["velocity_error"]
    depth_error = fields["depth_error"]["waterDepthErrorM"]
    require(np.all(direct["waterDepthM"] >= 0.0), "direct water depth contains a negative value")
    require(np.all(interpolated["waterDepthM"] >= 0.0), "interpolated water depth contains a negative value")
    require(np.array_equal(velocity_error["waterDepthM"], direct["waterDepthM"]), "velocity-error depth backdrop is not the direct depth")
    require(np.array_equal(velocity_error["velocityUms"], interpolated["velocityUms"] - direct["velocityUms"]), "velocity-error U algebra mismatch")
    require(np.array_equal(velocity_error["velocityVms"], interpolated["velocityVms"] - direct["velocityVms"]), "velocity-error V algebra mismatch")
    require(np.array_equal(depth_error, interpolated["waterDepthM"] - direct["waterDepthM"]), "depth-error algebra mismatch")
    safeguards = analysis.get("safeguards")
    require(isinstance(safeguards, dict), "analysis safeguards are missing")
    for key in ("solverInvoked", "networkAccessAttempted", "physicalValidationClaimAllowed"):
        require(safeguards.get(key) is False, f"analysis safeguard {key} must be false")
    source_record = {
        "path": portable_path(analysis_path, repo_root),
        "byteLength": analysis_path.stat().st_size,
        "sha256": sha256_file(analysis_path),
        "schema": ANALYSIS_SCHEMA,
        "status": status,
    }
    return analysis, fields, selection, selected_rows, {"analysis": source_record, "fields": portable_records}


def piecewise_map_points(
    points: np.ndarray,
    mesh: Mapping[str, Any],
    source_key: str,
    target_key: str,
) -> np.ndarray:
    """Vectorized equivalent of the approved triangle-order piecewise map."""

    require(points.ndim == 2 and points.shape[1] == 2, "piecewise-map point shape mismatch")
    anchors = mesh.get("anchors")
    triangles = mesh.get("triangles")
    require(isinstance(anchors, list) and isinstance(triangles, list), "geographic control mesh is invalid")
    result = points.astype(np.float64, copy=True)
    assigned = np.zeros(points.shape[0], dtype=bool)
    for triangle in triangles:
        require(isinstance(triangle, list) and len(triangle) == 3, "geographic control triangle is invalid")
        source = np.asarray([anchors[index][source_key] for index in triangle], dtype=np.float64)
        target = np.asarray([anchors[index][target_key] for index in triangle], dtype=np.float64)
        denominator = (source[1, 1] - source[2, 1]) * (source[0, 0] - source[2, 0]) + (source[2, 0] - source[1, 0]) * (source[0, 1] - source[2, 1])
        require(abs(float(denominator)) >= 1e-15, "degenerate geographic control triangle")
        ids = np.where(~assigned)[0]
        if ids.size == 0:
            break
        candidate = points[ids]
        u = ((source[1, 1] - source[2, 1]) * (candidate[:, 0] - source[2, 0]) + (source[2, 0] - source[1, 0]) * (candidate[:, 1] - source[2, 1])) / denominator
        v = ((source[2, 1] - source[0, 1]) * (candidate[:, 0] - source[2, 0]) + (source[0, 0] - source[2, 0]) * (candidate[:, 1] - source[2, 1])) / denominator
        w = 1.0 - u - v
        inside = (np.minimum(np.minimum(u, v), w) >= -1e-7) & (np.maximum(np.maximum(u, v), w) <= 1.0 + 1e-7)
        selected = ids[inside]
        if selected.size:
            weights = np.column_stack((u[inside], v[inside], w[inside]))
            result[selected] = weights @ target
            assigned[selected] = True
    return result


def image_points_to_world(points: np.ndarray, geographic: Mapping[str, Any], zoom: int) -> np.ndarray:
    source = piecewise_map_points(points, geographic["controlMesh"], "targetImagePixel", "sourceBasePixel")
    transform = geographic["transform"]
    a = float(transform["a"])
    b = float(transform["b"])
    tx = float(transform["tx"])
    ty = float(transform["ty"])
    world_x = tx + a * source[:, 0] - b * source[:, 1]
    world_y = ty + b * source[:, 0] + a * source[:, 1]
    scale = float(256 * (2**zoom))
    return np.column_stack((world_x / CIRCUMFERENCE_M * scale, world_y / CIRCUMFERENCE_M * scale))


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    mac_hiragino = sorted(Path("/System/Library/Fonts").glob("*W6.ttc" if bold else "*W3.ttc"))
    candidates = [
        *map(str, mac_hiragino),
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc" if bold else "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def interpolate_colour(value: float, ceiling: float, stops: tuple[tuple[float, tuple[int, int, int]], ...], alpha: int) -> tuple[int, int, int, int]:
    x = float(np.clip(value / max(ceiling, 1e-12), 0.0, 1.0))
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if x <= x1:
            fraction = (x - x0) / (x1 - x0)
            rgb = tuple(round(left + fraction * (right - left)) for left, right in zip(c0, c1))
            return rgb + (alpha,)
    return stops[-1][1] + (alpha,)


def stitch_tiles(tile_root: Path, zoom: int, tile_box: tuple[int, int, int, int]) -> tuple[Image.Image, np.ndarray, list[dict[str, Any]]]:
    x0, y0, x1, y1 = tile_box
    require(x0 <= x1 and y0 <= y1, "invalid GSI tile box")
    mosaic = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    records: list[dict[str, Any]] = []
    for tile_y in range(y0, y1 + 1):
        for tile_x in range(x0, x1 + 1):
            path = tile_root / f"z{zoom}" / f"{tile_x}-{tile_y}.jpg"
            require(path.is_file() and not path.is_symlink(), f"missing local GSI tile: {path}")
            try:
                with Image.open(path) as source:
                    tile = source.convert("RGB")
                    require(tile.size == (256, 256), f"unexpected GSI tile size: {path}")
                    mosaic.paste(tile, ((tile_x - x0) * 256, (tile_y - y0) * 256))
            except OSError as error:
                raise RenderError(f"invalid local GSI tile {path}: {error}") from error
            records.append({"path": f"z{zoom}/{tile_x}-{tile_y}.jpg", "sha256": sha256_file(path)})
    return mosaic, np.asarray([x0 * 256.0, y0 * 256.0]), records


def crop_origin_and_size(
    tile_box: tuple[int, int, int, int],
    centre: np.ndarray | None,
    crop_size: tuple[int, int] | None,
) -> tuple[np.ndarray, tuple[int, int]]:
    x0, y0, x1, y1 = tile_box
    world_origin = np.asarray([x0 * 256.0, y0 * 256.0])
    mosaic_size = ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256)
    if centre is None:
        require(crop_size is None, "uncentred view may not declare a crop size")
        return world_origin, mosaic_size
    require(crop_size is not None, "centred view is missing its crop size")
    width, height = crop_size
    left = int(round(float(centre[0] - world_origin[0] - width / 2)))
    top = int(round(float(centre[1] - world_origin[1] - height / 2)))
    return world_origin + np.asarray([left, top], dtype=np.float64), crop_size


def prepare_view(
    *,
    view: Mapping[str, Any],
    mask: np.ndarray,
    tile_root: Path,
    projected_vertices: np.ndarray,
    projected_centres: np.ndarray,
    barrage_segments: np.ndarray,
    fishway_centres: np.ndarray,
    confluence_world: np.ndarray,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    zoom = int(view["zoom"])
    tile_box = tuple(int(value) for value in view["tileBox"])
    require(len(tile_box) == 4, "regional view tile box is invalid")
    centre_kind = view.get("cropCentreKind")
    centres = {
        "barrage": barrage_segments.mean(axis=(0, 1)),
        "fishway": fishway_centres.mean(axis=0),
        "confluence": confluence_world,
    }
    centre = None if centre_kind is None else centres.get(str(centre_kind))
    require(centre_kind is None or centre is not None, f"unknown regional crop centre: {centre_kind}")
    raw_crop_size = view.get("cropSizeWorldPixels")
    crop_size = None if raw_crop_size is None else tuple(int(value) for value in raw_crop_size)
    crop_origin, expected_size = crop_origin_and_size(tile_box, centre, crop_size)
    mosaic, world_origin, tile_records = stitch_tiles(tile_root, zoom, tile_box)
    left = int(round(float(crop_origin[0] - world_origin[0])))
    top = int(round(float(crop_origin[1] - world_origin[1])))
    crop = mosaic.crop((left, top, left + expected_size[0], top + expected_size[1]))
    require(crop.size == expected_size, "regional map crop size mismatch")
    scale = min(PANEL_WIDTH / crop.width, PANEL_HEIGHT / crop.height)
    resized_size = (round(crop.width * scale), round(crop.height * scale))
    resized = crop.resize(resized_size, Image.Resampling.LANCZOS)
    resized = ImageEnhance.Brightness(resized).enhance(0.88)
    base = Image.new("RGB", (PANEL_WIDTH, PANEL_HEIGHT), (25, 38, 44))
    paste = np.asarray([(PANEL_WIDTH - resized.width) // 2, (PANEL_HEIGHT - resized.height) // 2], dtype=np.float64)
    base.paste(resized, tuple(paste.astype(int)))
    local_vertices = (projected_vertices - crop_origin) * scale + paste
    local_centres = (projected_centres - crop_origin) * scale + paste
    local_barrage = (barrage_segments - crop_origin) * scale + paste
    local_fishway = (fishway_centres - crop_origin) * scale + paste
    local_confluence = (confluence_world - crop_origin) * scale + paste
    bins: dict[tuple[int, int], list[int]] = {}
    bin_pixels = 46 if zoom == 16 else 42
    for cell in mask:
        key = (int(local_centres[cell, 0] // bin_pixels), int(local_centres[cell, 1] // bin_pixels))
        bins.setdefault(key, []).append(int(cell))
    view_id = str(view["id"])
    marks = {
        "estuary": ("barrage", "confluence"),
        "barrage": ("barrage",),
        "confluence": ("confluence",),
        "fishway": ("fishway", "barrage"),
    }[view_id]
    return {
        "id": view_id,
        "labelJa": str(view["labelJa"]),
        "zoom": zoom,
        "base": base,
        "mask": mask,
        "localVertices": local_vertices,
        "localCentres": local_centres,
        "localBarrage": local_barrage,
        "localFishway": local_fishway,
        "localConfluence": local_confluence,
        "bins": [np.asarray(ids, dtype=np.int64) for _, ids in sorted(bins.items())],
        "marks": marks,
    }, tile_records


def draw_arrow(draw: ImageDraw.ImageDraw, start: np.ndarray, vector: np.ndarray, length: float, width: int) -> None:
    magnitude = float(np.linalg.norm(vector))
    if magnitude <= 1e-12:
        return
    unit = vector / magnitude
    end = start + unit * length
    outline = (14, 28, 34, 245)
    inside = (255, 255, 255, 255)
    draw.line([tuple(start), tuple(end)], fill=outline, width=width + 3)
    draw.line([tuple(start), tuple(end)], fill=inside, width=width)
    angle = math.atan2(float(unit[1]), float(unit[0]))
    wing = max(5.0, length * 0.27)
    for delta in (-2.55, 2.55):
        point = end + wing * np.asarray([math.cos(angle + delta), math.sin(angle + delta)])
        draw.line([tuple(end), tuple(point)], fill=outline, width=width + 2)
        draw.line([tuple(end), tuple(point)], fill=inside, width=max(1, width - 1))


def draw_markers(draw: ImageDraw.ImageDraw, prepared: Mapping[str, Any]) -> None:
    if "barrage" in prepared["marks"]:
        segments = prepared["localBarrage"]
        for segment in segments:
            draw.line([tuple(segment[0]), tuple(segment[1])], fill=(17, 102, 196, 255), width=4)
        centre = segments.mean(axis=(0, 1))
        box = (centre[0] + 7, centre[1] - 30, centre[0] + 118, centre[1] - 5)
        draw.rounded_rectangle(box, 6, fill=(17, 102, 196, 232))
        draw.text((centre[0] + 13, centre[1] - 28), "河口堰位置", font=font(13, True), fill=(255, 255, 255, 255))
    if "fishway" in prepared["marks"]:
        points = prepared["localFishway"]
        for point in points:
            draw.ellipse((point[0] - 6, point[1] - 6, point[0] + 6, point[1] + 6), fill=(232, 67, 127, 255), outline=(255, 255, 255, 255), width=2)
        centre = points.mean(axis=0)
        draw.text((centre[0] + 9, centre[1] - 12), "魚道", font=font(13, True), fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(18, 32, 38, 230))
    if "confluence" in prepared["marks"]:
        point = prepared["localConfluence"]
        draw.ellipse((point[0] - 6, point[1] - 6, point[0] + 6, point[1] + 6), fill=(232, 67, 127, 255), outline=(255, 255, 255, 255), width=2)
        draw.text((point[0] + 9, point[1] - 12), "合流部", font=font(13, True), fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(18, 32, 38, 230))


def render_panel(
    *,
    prepared: Mapping[str, Any],
    triangles: np.ndarray,
    magnitude: np.ndarray,
    velocity_screen: np.ndarray,
    depth: np.ndarray,
    area: np.ndarray,
    ceiling: float,
    stops: tuple[tuple[float, tuple[int, int, int]], ...],
) -> tuple[Image.Image, int]:
    canvas = prepared["base"].convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    alpha = 108 if int(prepared["zoom"]) == 16 else 124
    vertices = prepared["localVertices"]
    draw_mesh = int(prepared["zoom"]) == 18
    for cell in prepared["mask"]:
        polygon = [tuple(point) for point in vertices[triangles[cell]]]
        draw.polygon(polygon, fill=interpolate_colour(float(magnitude[cell]), ceiling, stops, alpha))
        if draw_mesh:
            draw.line(polygon + [polygon[0]], fill=(255, 255, 255, 34), width=1)
    arrow_count = 0
    centres = prepared["localCentres"]
    for cells in prepared["bins"]:
        weights = depth[cells] * area[cells]
        total = float(np.sum(weights))
        if not math.isfinite(total) or total <= 0.0:
            continue
        vector = np.sum(velocity_screen[cells] * weights[:, None], axis=0) / total
        vector_magnitude = float(np.linalg.norm(vector))
        if vector_magnitude < max(0.004, ceiling * 0.012):
            continue
        start = np.sum(centres[cells] * weights[:, None], axis=0) / total
        length = 11.0 + 25.0 * min(vector_magnitude / max(ceiling, 1e-12), 1.0)
        draw_arrow(draw, start, vector, length, 2)
        arrow_count += 1
    draw_markers(draw, prepared)
    return Image.alpha_composite(canvas, overlay).convert("RGB"), arrow_count


def jpeg_bytes(image: Image.Image, quality: int = 88) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=False, progressive=False, subsampling=2)
    return buffer.getvalue()


def percentile_nonzero(values: np.ndarray) -> float:
    nonzero = values[values > 0.0]
    return 0.0 if nonzero.size == 0 else float(np.percentile(nonzero, 95.0))


def rounded_ceiling(value: float) -> float:
    return max(0.01, math.ceil(value * 100.0) / 100.0)


def metric_summary(row: Mapping[str, Any]) -> str:
    decision = "PASS" if row["passed"] else "FAIL"
    return (
        f"速度RMSE {float(row['velocityVectorRmseMPS']):.3f} m/s　"
        f"速度MAE {float(row['speedMaeMPS']):.3f} m/s　"
        f"方向p95 {float(row['p95DirectionErrorDeg']):.1f}°　"
        f"水深RMSE {float(row['depthRmseM']):.3f} m　"
        f"最大|水深差| {float(row['maximumAbsoluteDepthErrorM']):.3f} m　{decision}"
    )


def xml_text(value: str) -> str:
    return html.escape(value, quote=True)


def build_region_svg(
    *,
    view_id: str,
    label: str,
    model_hour: int,
    panels: list[Image.Image],
    shared_ceiling: float,
    error_ceiling: float,
    metric_row: Mapping[str, Any],
    synthetic_preview: bool,
) -> bytes:
    require(len(panels) == 3, "regional sheet requires exactly three panels")
    width = 1680
    height = 650
    panel_x = (40, 590, 1140)
    image_y = 142
    gradient_speed = f"speed-{view_id}"
    gradient_error = f"error-{view_id}"
    panel_payloads = [base64.b64encode(jpeg_bytes(panel)).decode("ascii") for panel in panels]
    decision = "PASS" if metric_row["passed"] else "FAIL"
    decision_colour = "#16794a" if metric_row["passed"] else "#b3261e"
    preview_note = "合成データ表示例（実行結果ではない）　" if synthetic_preview else ""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="&#104;ttp://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title-{view_id} desc-{view_id}">',
        f'<title id="title-{view_id}">{xml_text(label)}・河口堰50%ホールドアウト比較</title>',
        f'<desc id="desc-{view_id}">モデル内の相対時刻{model_hour}時間の直接計算、全閉と全開の50対50補間、補間から直接計算を引いた速度差。構造基準は河口堰位置。{xml_text(DISCLAIMER_JA)}。</desc>',
        '<defs>',
        f'<linearGradient id="{gradient_speed}" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#1b6bae"/><stop offset="32%" stop-color="#25a7b8"/><stop offset="63%" stop-color="#f6bc41"/><stop offset="100%" stop-color="#da4537"/></linearGradient>',
        f'<linearGradient id="{gradient_error}" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#440154"/><stop offset="34%" stop-color="#3b528b"/><stop offset="68%" stop-color="#21918c"/><stop offset="100%" stop-color="#fde725"/></linearGradient>',
        '</defs>',
        '<rect width="100%" height="100%" fill="#f4f7f8"/>',
        f'<text x="40" y="43" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\',\'Noto Sans JP\',sans-serif" font-size="30" font-weight="700" fill="#17313b">{xml_text(label)}｜河口堰50%ホールドアウト比較</text>',
        f'<text x="40" y="78" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\',\'Noto Sans JP\',sans-serif" font-size="18" fill="#526a73">{xml_text(preview_note)}最悪速度RMSE選択時刻：モデル内相対 {model_hour} h（実日時・予報時刻ではない）　同一領域で横比較</text>',
        f'<rect x="1510" y="30" width="120" height="38" rx="19" fill="{decision_colour}"/><text x="1570" y="56" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="18" font-weight="700" fill="#fff">{decision}</text>',
    ]
    for index, (x, title, payload) in enumerate(zip(panel_x, PANEL_TITLES, panel_payloads)):
        parts.extend([
            f'<g role="group" aria-label="比較パネル{index + 1}">',
            f'<text x="{x}" y="118" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\',\'Noto Sans JP\',sans-serif" font-size="21" font-weight="700" fill="#17313b">{xml_text(title)}</text>',
            f'<rect x="{x - 3}" y="{image_y - 3}" width="506" height="316" rx="5" fill="#d5dfe2"/>',
            f'<image x="{x}" y="{image_y}" width="500" height="310" href="data:image/jpeg;base64,{payload}"/>',
            '</g>',
        ])
        gradient = gradient_error if index == 2 else gradient_speed
        ceiling = error_ceiling if index == 2 else shared_ceiling
        legend_label = "速度差 |Δv|" if index == 2 else "流速"
        shared_note = "（共通）" if index < 2 else ""
        parts.extend([
            f'<rect x="{x}" y="474" width="190" height="13" rx="3" fill="url(#{gradient})"/>',
            f'<text x="{x}" y="510" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\',\'Noto Sans JP\',sans-serif" font-size="16" fill="#405a64">{xml_text(legend_label)} 0 — {ceiling:.2f} m/s {xml_text(shared_note)}</text>',
        ])
    parts.extend([
        f'<text x="40" y="555" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\',\'Noto Sans JP\',sans-serif" font-size="18" font-weight="600" fill="#17313b">{xml_text(metric_summary(metric_row))}</text>',
        f'<text x="40" y="596" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\',\'Noto Sans JP\',sans-serif" font-size="17" fill="#6a4040">{xml_text(DISCLAIMER_JA)}</text>',
        f'<text x="40" y="625" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\',\'Noto Sans JP\',sans-serif" font-size="15" fill="#526a73">{xml_text(GSI_ATTRIBUTION_JA)}</text>',
        '</svg>',
    ])
    return ("\n".join(parts) + "\n").encode("utf-8")


def build_overview(
    *,
    model_hour: int,
    view_rows: list[tuple[str, str, list[Image.Image], Mapping[str, Any]]],
    analysis_status: str,
    passed_count: int,
    failed_count: int,
    thresholds: Mapping[str, Any],
    shared_ceiling: float,
    error_ceiling: float,
    synthetic_preview: bool,
) -> Image.Image:
    width = 1260
    header_height = 166
    row_height = 278
    footer_height = 150
    height = header_height + row_height * len(view_rows) + footer_height
    canvas = Image.new("RGB", (width, height), (244, 247, 248))
    draw = ImageDraw.Draw(canvas)
    draw.text((28, 20), "河口堰50%：直接計算・端点補間・速度差", font=font(30, True), fill=(23, 49, 59))
    preview_note = "合成データ表示例（実行結果ではない）｜" if synthetic_preview else ""
    if analysis_status == "evaluated_passed_thresholds":
        overall = f"結果：{passed_count}件すべてPASS — 単純50:50補間はしきい値内"
    else:
        overall = f"結果：20件中{failed_count}件FAIL — 0%＋100%の単純50:50補間は採用不可"
    badge = (22, 121, 74) if analysis_status == "evaluated_passed_thresholds" else (179, 38, 30)
    draw.rounded_rectangle((28, 58, 1230, 98), radius=20, fill=badge)
    draw.text((629, 78), overall, anchor="mm", font=font(19, True), fill=(255, 255, 255))
    draw.text(
        (28, 112),
        f"{preview_note}最悪速度RMSE選択時刻　モデル内相対 {model_hour} h（実日時・予報時刻ではない）｜4領域を横比較",
        font=font(16 if synthetic_preview else 18),
        fill=(72, 97, 107),
    )
    column_x = (155, 520, 885)
    for x, title in zip(column_x, PANEL_TITLES):
        draw.text((x + 170, 152), title, anchor="ms", font=font(16, True), fill=(23, 49, 59))
    thumb_size = (348, 216)
    for row_index, (view_id, label, panels, metric_row) in enumerate(view_rows):
        y = header_height + row_index * row_height
        draw.rounded_rectangle((20, y + 12, 1240, y + row_height - 8), radius=12, fill=(255, 255, 255), outline=(211, 222, 226), width=2)
        display_label = "曲川・遠賀川\n合流地点付近" if view_id == "confluence" else label
        label_font = font(14 if view_id == "confluence" else 20, True)
        draw.multiline_text((36, y + 27), display_label, font=label_font, fill=(23, 49, 59), spacing=2)
        decision = "PASS" if metric_row["passed"] else "FAIL"
        decision_fill = (22, 121, 74) if metric_row["passed"] else (179, 38, 30)
        draw.rounded_rectangle((38, y + 72, 122, y + 104), radius=16, fill=decision_fill)
        draw.text((80, y + 88), decision, anchor="mm", font=font(15, True), fill=(255, 255, 255))
        draw.text((36, y + 124), f"v RMSE\n{float(metric_row['velocityVectorRmseMPS']):.3f} m/s", font=font(14), fill=(72, 97, 107), spacing=5)
        draw.text((36, y + 184), f"水深 RMSE\n{float(metric_row['depthRmseM']):.3f} m", font=font(14), fill=(72, 97, 107), spacing=5)
        for x, panel in zip(column_x, panels):
            thumb = panel.resize(thumb_size, Image.Resampling.LANCZOS)
            canvas.paste(thumb, (x, y + 34))
            draw.rectangle((x, y + 34, x + thumb_size[0], y + 34 + thumb_size[1]), outline=(184, 198, 203), width=1)
        draw.text((155, y + 264), metric_summary(metric_row), anchor="ls", font=font(13), fill=(61, 83, 91))
    footer_y = header_height + row_height * len(view_rows)
    if analysis_status == "evaluated_passed_thresholds":
        decision_text = "判断結果：単純50:50補間は全比較でしきい値内"
        decision_colour = (22, 121, 74)
    else:
        decision_text = "判断対象：A 単純補間を不採用にし、直接50%を中間基準にする（推奨）／B 条件間補間を終了"
        decision_colour = (147, 35, 29)
    draw.text((28, footer_y + 22), decision_text, font=font(16, True), fill=decision_colour)
    draw.text(
        (28, footer_y + 53),
        f"色尺度：直接・補間 共通 0–{shared_ceiling:.2f} m/s｜速度差 0–{error_ceiling:.2f} m/s",
        font=font(14),
        fill=(61, 83, 91),
    )
    draw.text(
        (28, footer_y + 79),
        "判定基準："
        f"v RMSE {float(thresholds['velocityVectorRmseMPS']):.3f} m/s以下｜"
        f"速度MAE {float(thresholds['speedMaeMPS']):.3f} m/s以下｜"
        f"方向p95 {float(thresholds['p95DirectionErrorDeg']):.0f}°以下｜"
        f"水深RMSE {float(thresholds['depthRmseM']):.2f} m以下｜"
        f"最大水深差 {float(thresholds['maximumAbsoluteDepthErrorM']):.2f} m以下",
        font=font(13),
        fill=(61, 83, 91),
    )
    draw.text((28, footer_y + 106), DISCLAIMER_JA, font=font(15, True), fill=(112, 61, 61))
    draw.text((28, footer_y + 132), GSI_ATTRIBUTION_JA, font=font(13), fill=(72, 97, 107))
    return canvas


def build_html_fragment(
    *,
    overview_payload: bytes,
    model_hour: int,
    analysis_status: str,
    metric_rows: list[Mapping[str, Any]],
    passed_count: int,
    failed_count: int,
    shared_ceiling: float,
    error_ceiling: float,
    synthetic_preview: bool,
) -> bytes:
    encoded = base64.b64encode(overview_payload).decode("ascii")
    overall = f"{passed_count}件すべてしきい値内" if analysis_status == "evaluated_passed_thresholds" else f"20件中{failed_count}件がしきい値超過"
    overall_badge_class = "viz-badge" if analysis_status == "evaluated_passed_thresholds" else "viz-badge text-destructive"
    table_rows = []
    labels = {"estuary": "河口全域", "barrage": "河口堰付近", "confluence": "曲川・遠賀川合流地点付近", "fishway": "魚道付近"}
    for row in metric_rows:
        decision = "PASS" if row["passed"] else "FAIL"
        table_rows.append(
            "<tr>"
            f"<th scope=\"row\" style=\"padding:8px 10px;text-align:left;white-space:nowrap\">{html.escape(labels[str(row['regionId'])])}</th>"
            f"<td style=\"padding:8px 10px;text-align:right\">{float(row['velocityVectorRmseMPS']):.3f}</td>"
            f"<td style=\"padding:8px 10px;text-align:right\">{float(row['speedMaeMPS']):.3f}</td>"
            f"<td style=\"padding:8px 10px;text-align:right\">{float(row['p95DirectionErrorDeg']):.1f}</td>"
            f"<td style=\"padding:8px 10px;text-align:right\">{float(row['depthRmseM']):.3f}</td>"
            f"<td class=\"{'text-destructive' if not row['passed'] else ''}\" style=\"padding:8px 10px;text-align:center;font-weight:700\">{decision}</td>"
            "</tr>"
        )
    preview_badge_line = (
        '      <span class="viz-badge">合成データ表示例（実行結果ではありません）</span>\n'
        if synthetic_preview
        else ""
    )
    fragment = f"""<section aria-labelledby="holdout-map-title">
  <div class="viz-row" style="align-items:flex-start;justify-content:space-between">
    <div>
      <h2 id="holdout-map-title">河口堰50%ホールドアウト比較</h2>
{preview_badge_line}      <p class="text-muted">モデル内相対 {model_hour} h（実日時・予報時刻ではない）：直接50%、全閉＋全開の50:50補間、その速度差を4領域で横比較</p>
    </div>
    <span class="{overall_badge_class}">{overall}</span>
  </div>
  <figure>
    <img src="data:image/jpeg;base64,{encoded}" alt="河口全域、河口堰付近、曲川・遠賀川合流地点付近、魚道付近について、直接計算、端点50対50補間、補間から直接を引いた速度差を並べた比較図" style="display:block;width:100%;height:auto">
    <figcaption class="text-small text-muted">直接と補間は共通 0–{shared_ceiling:.2f} m/s、速度差は 0–{error_ceiling:.2f} m/s の別スケール。矢印は水深×セル面積で集約。</figcaption>
  </figure>
  <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:14px">
      <caption style="padding:10px;text-align:left;font-weight:700">選択時刻の領域別指標</caption>
      <thead><tr><th style="padding:8px 10px;text-align:left">領域</th><th style="padding:8px 10px;text-align:right">速度RMSE m/s</th><th style="padding:8px 10px;text-align:right">速度MAE m/s</th><th style="padding:8px 10px;text-align:right">方向p95 °</th><th style="padding:8px 10px;text-align:right">水深RMSE m</th><th style="padding:8px 10px">判定</th></tr></thead>
      <tbody>{''.join(table_rows)}</tbody>
    </table>
  </div>
  <p class="text-destructive"><strong>{'単純50:50補間は採用不可。直接50%を中間基準にするか、条件間補間を終了するかを判断。' if analysis_status == 'evaluated_failed_thresholds' else '単純50:50補間は全比較でしきい値内。'}</strong></p>
  <p class="text-small text-muted">{DISCLAIMER_JA}。{GSI_ATTRIBUTION_JA}。</p>
</section>
"""
    return fragment.encode("utf-8")


def render(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    require(repo_root.is_dir(), "--repo-root is not a directory")
    expected_renderer = repo_root / "tools/render_stage20_barrage_holdout_comparison_maps.py"
    require(Path(__file__).resolve() == expected_renderer.resolve(), "--repo-root does not contain this renderer")
    analysis_path = output_path(args.analysis, repo_root)
    output_dir = output_path(args.output_dir, repo_root)
    manifest_output = output_path(args.manifest_output, repo_root)
    html_output = output_path(args.html_output, repo_root)
    require(not output_dir.is_symlink(), "output directory may not be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    require(output_dir.is_dir(), "output directory is invalid")
    prepare_output(manifest_output)
    prepare_output(html_output)

    mesh_path = repo_root / "public/data/onga/stage20/mesh-v2.json"
    mesh_manifest, package, mesh_record = load_mesh(mesh_path)
    cell_count = int(mesh_manifest["counts"]["cells"])
    mask_manifest_path = repo_root / "config/stage20_barrage_holdout_region_masks_v1.json"
    mask_manifest, view_records, masks, mask_record = load_region_masks(
        mask_manifest_path,
        repo_root,
        str(mesh_manifest["binary"]["sha256"]),
        cell_count,
    )
    analysis, fields, selection, metric_rows, source_records = validate_analysis(
        analysis_path,
        repo_root,
        masks,
        cell_count,
    )
    model_hour = int(selection["modelHour"])
    fixture_record = analysis.get("fixture")
    synthetic_preview = isinstance(fixture_record, dict) and fixture_record.get("synthetic") is True

    triangles = package["triangles"].astype(np.int64)
    image_vertices = package["vertex_image_millipixel"].astype(np.float64) * 0.001
    image_centres = image_vertices[triangles].mean(axis=1)
    local_vertices = package["vertex_local_mm"].astype(np.float64) * 0.001
    local_triangles = local_vertices[triangles]
    area = 0.5 * np.abs(
        (local_triangles[:, 1, 0] - local_triangles[:, 0, 0]) * (local_triangles[:, 2, 1] - local_triangles[:, 0, 1])
        - (local_triangles[:, 1, 1] - local_triangles[:, 0, 1]) * (local_triangles[:, 2, 0] - local_triangles[:, 0, 0])
    )
    require(np.all(np.isfinite(area)) and np.all(area > 0.0), "mesh contains a degenerate cell")

    water_manifest_path = repo_root / "data/onga_unified_water_manifest_r3.json"
    water_manifest = load_json(water_manifest_path)
    geographic = water_manifest.get("coordinateSystem", {}).get("geographic")
    require(isinstance(geographic, dict) and geographic.get("crs") == "EPSG:4326", "approved geographic transform is missing")
    projected: dict[int, dict[str, Any]] = {}
    internal_vertices = package["internal_face_vertices"].astype(np.int64)
    barrage_ids = package["barrage_face_ids"].astype(np.int64)
    fishway_cells = package["fishway_cells"].astype(np.int64)
    confluence_image = np.asarray([[1168.0, 441.0]], dtype=np.float64)
    speeds = {
        "direct": np.hypot(fields["direct"]["velocityUms"], fields["direct"]["velocityVms"]),
        "interpolated": np.hypot(fields["interpolated"]["velocityUms"], fields["interpolated"]["velocityVms"]),
        "velocity_error": np.hypot(fields["velocity_error"]["velocityUms"], fields["velocity_error"]["velocityVms"]),
    }
    p95_direct = percentile_nonzero(speeds["direct"])
    p95_interpolated = percentile_nonzero(speeds["interpolated"])
    p95_error = percentile_nonzero(speeds["velocity_error"])
    shared_ceiling = rounded_ceiling(max(p95_direct, p95_interpolated))
    error_ceiling = rounded_ceiling(p95_error)
    for zoom in (16, 18):
        p_vertices = image_points_to_world(image_vertices, geographic, zoom)
        p_centres = p_vertices[triangles].mean(axis=1)
        screens: dict[str, np.ndarray] = {}
        for kind in ("direct", "interpolated", "velocity_error"):
            velocity_u = fields[kind]["velocityUms"]
            velocity_v = fields[kind]["velocityVms"]
            endpoints = image_centres + np.column_stack((velocity_u, -velocity_v))
            endpoint_world = image_points_to_world(endpoints, geographic, zoom)
            direction = endpoint_world - p_centres
            norm = np.linalg.norm(direction, axis=1)
            screens[kind] = direction * np.divide(speeds[kind], np.maximum(norm, 1e-12))[:, None]
        projected[zoom] = {
            "vertices": p_vertices,
            "centres": p_centres,
            "screens": screens,
            "barrage": p_vertices[internal_vertices[barrage_ids]],
            "fishway": p_centres[fishway_cells],
            "confluence": image_points_to_world(confluence_image, geographic, zoom)[0],
        }

    tile_root = repo_root / "data/external/gsi/seamlessphoto"
    prepared_views: dict[str, dict[str, Any]] = {}
    tile_inventory: dict[str, dict[str, str]] = {}
    for view in view_records:
        zoom = int(view["zoom"])
        geometry = projected[zoom]
        prepared, tile_records = prepare_view(
            view=view,
            mask=masks[str(view["id"])],
            tile_root=tile_root,
            projected_vertices=geometry["vertices"],
            projected_centres=geometry["centres"],
            barrage_segments=geometry["barrage"],
            fishway_centres=geometry["fishway"],
            confluence_world=geometry["confluence"],
        )
        prepared_views[str(view["id"])] = prepared
        for record in tile_records:
            tile_inventory[record["path"]] = record

    metric_by_region = {str(row["regionId"]): row for row in metric_rows}
    region_outputs: list[dict[str, Any]] = []
    overview_rows: list[tuple[str, str, list[Image.Image], Mapping[str, Any]]] = []
    for view_id in REGION_ORDER:
        prepared = prepared_views[view_id]
        zoom = int(prepared["zoom"])
        panels: list[Image.Image] = []
        arrow_counts: dict[str, int] = {}
        for kind, ceiling, stops in (
            ("direct", shared_ceiling, SPEED_STOPS),
            ("interpolated", shared_ceiling, SPEED_STOPS),
            ("velocity_error", error_ceiling, ERROR_STOPS),
        ):
            panel, arrow_count = render_panel(
                prepared=prepared,
                triangles=triangles,
                magnitude=speeds[kind],
                velocity_screen=projected[zoom]["screens"][kind],
                depth=fields[kind]["waterDepthM"],
                area=area,
                ceiling=ceiling,
                stops=stops,
            )
            panels.append(panel)
            arrow_counts[kind] = arrow_count
        filename = f"stage20-barrage-holdout-comparison-{view_id}.svg"
        path = output_dir / filename
        prepare_output(path)
        svg = build_region_svg(
            view_id=view_id,
            label=str(prepared["labelJa"]),
            model_hour=model_hour,
            panels=panels,
            shared_ceiling=shared_ceiling,
            error_ceiling=error_ceiling,
            metric_row=metric_by_region[view_id],
            synthetic_preview=synthetic_preview,
        )
        path.write_bytes(svg)
        region_outputs.append({
            "id": view_id,
            "labelJa": str(prepared["labelJa"]),
            "path": filename,
            "byteLength": len(svg),
            "sha256": sha256_bytes(svg),
            "cellCount": int(masks[view_id].size),
            "panelCount": 3,
            "arrowCounts": arrow_counts,
            "metricRow": metric_by_region[view_id],
        })
        overview_rows.append((view_id, str(prepared["labelJa"]), panels, metric_by_region[view_id]))

    overview_image = build_overview(
        model_hour=model_hour,
        view_rows=overview_rows,
        analysis_status=str(analysis["status"]),
        passed_count=int(analysis["holdoutEvaluation"]["passedComparisonCount"]),
        failed_count=int(analysis["holdoutEvaluation"]["failedComparisonCount"]),
        thresholds=analysis["holdoutEvaluation"]["thresholds"],
        shared_ceiling=shared_ceiling,
        error_ceiling=error_ceiling,
        synthetic_preview=synthetic_preview,
    )
    overview_payload = jpeg_bytes(overview_image, quality=90)
    overview_path = output_dir / "comparison-overview.jpg"
    prepare_output(overview_path)
    overview_path.write_bytes(overview_payload)
    html_payload = build_html_fragment(
        overview_payload=overview_payload,
        model_hour=model_hour,
        analysis_status=str(analysis["status"]),
        metric_rows=metric_rows,
        passed_count=int(analysis["holdoutEvaluation"]["passedComparisonCount"]),
        failed_count=int(analysis["holdoutEvaluation"]["failedComparisonCount"]),
        shared_ceiling=shared_ceiling,
        error_ceiling=error_ceiling,
        synthetic_preview=synthetic_preview,
    )
    html_output.write_bytes(html_payload)

    tile_digest_payload = "".join(f"{key}\0{tile_inventory[key]['sha256']}\n" for key in sorted(tile_inventory)).encode("utf-8")
    renderer_path = Path(__file__).resolve()
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "status": MANIFEST_STATUS,
        "modelHour": model_hour,
        "selectionConvention": selection,
        "analysisAcceptanceStatus": analysis["status"],
        "sourceAnalysis": source_records["analysis"],
        "source": source_records,
        "toolchain": {
            "renderer": {
                "path": portable_path(renderer_path, repo_root),
                "sha256": sha256_file(renderer_path),
            },
            "mode": "offline_local_artifacts_only",
        },
        "mesh": {
            "manifest": portable_path(mesh_path, repo_root),
            "manifestSha256": sha256_file(mesh_path),
            "binarySha256": mesh_manifest["binary"]["sha256"],
            "cellCount": cell_count,
            "vertexCount": mesh_record["vertexCount"],
        },
        "regionalMasks": mask_record,
        "satelliteBackdrop": {
            "source": "local_GSI_seamlessphoto_tiles",
            "tileCount": len(tile_inventory),
            "inventorySha256": sha256_bytes(tile_digest_payload),
            "networkUsed": False,
        },
        "displayScales": {
            "sharedDirectInterpolatedSpeedMPS": {
                "maximumMPS": shared_ceiling,
                "unit": "m/s",
                "percentile": 95.0,
                "minimumMPS": 0.01,
                "appliesTo": ["direct", "interpolated"],
                "sourceP95MPS": {"direct": p95_direct, "interpolated": p95_interpolated},
                "rule": "ceil_0.01_of_max_nonzero_p95_with_0.01_floor",
            },
            "velocityErrorMPS": {
                "maximumMPS": error_ceiling,
                "unit": "m/s",
                "percentile": 95.0,
                "minimumMPS": 0.01,
                "appliesTo": ["velocity_error"],
                "sourceP95MPS": p95_error,
                "rule": "ceil_0.01_of_nonzero_p95_with_0.01_floor",
            },
        },
        "views": region_outputs,
        "overview": {
            "path": overview_path.name,
            "byteLength": len(overview_payload),
            "sha256": sha256_bytes(overview_payload),
            "width": overview_image.width,
            "height": overview_image.height,
        },
        "html": {
            "path": html_output.name,
            "byteLength": len(html_payload),
            "sha256": sha256_bytes(html_payload),
            "format": "literal_html_fragment",
        },
        "interpretation": {
            "comparison": "componentwise_50_50_endpoint_interpolation_versus_direct_50_percent_run",
            "passedComparisonCount": int(analysis["holdoutEvaluation"]["passedComparisonCount"]),
            "failedComparisonCount": int(analysis["holdoutEvaluation"]["failedComparisonCount"]),
            "simpleInterpolationRecommendation": (
                "within_thresholds"
                if analysis["status"] == "evaluated_passed_thresholds"
                else "do_not_adopt_use_direct_50_percent_as_middle_anchor_or_end_cross_condition_interpolation"
            ),
            "disclaimerJa": DISCLAIMER_JA,
            "gsiAttributionJa": GSI_ATTRIBUTION_JA,
            "physicalValidationClaim": False,
            "forecastValidationClaim": False,
            "syntheticPreview": synthetic_preview,
        },
        "safeguards": {
            "solverInvoked": False,
            "networkAccessAttempted": False,
            "physicalValidationClaimAllowed": False,
            "forecastValidationClaimAllowed": False,
            "sourceFieldsModified": False,
        },
    }
    manifest_payload = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_output.write_bytes(manifest_payload)
    return {
        "status": MANIFEST_STATUS,
        "modelHour": model_hour,
        "analysisStatus": analysis["status"],
        "viewCount": len(region_outputs),
        "panelCount": len(region_outputs) * 3,
        "manifest": str(manifest_output),
        "html": str(html_output),
        "overview": str(overview_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest-output", required=True)
    parser.add_argument("--html-output", required=True)
    return parser.parse_args()


def main() -> int:
    try:
        result = render(parse_args())
    except RenderError as error:
        print(json.dumps({"status": "not_rendered_invalid_or_incomplete_evidence", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except Exception as error:
        print(json.dumps({"status": "not_rendered_implementation_or_io_error", "exceptionType": type(error).__name__, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
