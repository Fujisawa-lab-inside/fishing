#!/usr/bin/env python3
"""Render the offline Stage 20 barrage piecewise-opening judgment maps.

This renderer uses only the existing direct 0%, 50%, and 100% float64 fields
at model-relative hour -9.  It constructs the 25% and 75% displays in memory,
keeps the direct 50% field as the exact middle anchor, and renders the
canonical middle-anchor kink

    0.5 * F0 + 0.5 * F100 - F50

beside the five opening states.  It never invokes the physical solver, uses
the network, or connects the candidate to the public simulator.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image, ImageDraw


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import render_stage20_barrage_holdout_comparison_maps as maps  # noqa: E402


SCHEMA = "onga-stage20-barrage-piecewise-map-manifest-v1"
STATUS = "rendered_inactive_code_only_piecewise_candidate_not_physical_validation"
ANALYSIS_SCHEMA = "onga-stage20-barrage-holdout-recovery-postrun-analysis-v1"
MODEL_HOUR = -9
CELL_COUNT = 50199
SPEED_CEILING_MPS = 0.13
KINK_CEILING_MPS = 0.04
STEP_ALLCLOSE_ATOL = 4.0e-15
STATE_ORDER = (
    "direct_0",
    "interpolated_25",
    "direct_50",
    "interpolated_75",
    "direct_100",
    "canonical_kink",
)
STATE_TITLES = {
    "direct_0": "0% 直接計算",
    "interpolated_25": "25% 区間補間",
    "direct_50": "50% 直接・固定基準",
    "interpolated_75": "75% 区間補間",
    "direct_100": "100% 直接計算",
    "canonical_kink": "50%前後の刻み変化差",
}
REGION_ORDER = ("estuary", "barrage", "confluence", "fishway")
REGION_LABELS = {
    "estuary": "河口全域",
    "barrage": "河口堰付近",
    "confluence": "曲川・遠賀川合流地点付近",
    "fishway": "魚道付近",
}
FIELD_KEYS = ("waterDepthM", "velocityUms", "velocityVms")
GSI_ATTRIBUTION = "背景：国土地理院「全国最新写真（シームレス）」を加工"
DISCLAIMER = "補間候補の内部確認／実測・予報精度の検証ではない"
OUTPUT_ROOT_RELATIVE = Path("docs/results/stage20-barrage-piecewise-candidate-v1")
ANALYSIS_RELATIVE = Path("config/stage20_barrage_holdout_recovery_analysis_v1.json")
MESH_RELATIVE = Path("public/data/onga/stage20/mesh-v2.json")
MASK_RELATIVE = Path("config/stage20_barrage_holdout_region_masks_v1.json")
COORDINATE_RELATIVE = Path("data/onga_unified_water_manifest_r3.json")
TILE_ROOT_RELATIVE = Path("data/external/gsi/seamlessphoto")
BROWSER_PACK_RELATIVE = (
    OUTPUT_ROOT_RELATIVE / "barrage-piecewise-anchor-pack.json"
)
BROWSER_PACK_SCHEMA = "onga-stage20-barrage-piecewise-anchor-pack-v1"
BROWSER_PACK_MAX_VECTOR_QUANTIZATION_ERROR_MPS = 3.05e-8


class CandidateError(RuntimeError):
    """An invalid or incomplete code-only candidate input."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def portable_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def validate_source_file(
    record: Mapping[str, Any],
    repo_root: Path,
    label: str,
) -> tuple[Path, dict[str, Any]]:
    raw_path = record.get("path")
    expected_sha = record.get("sha256")
    require(isinstance(raw_path, str) and raw_path, f"{label} source path is missing")
    require(isinstance(expected_sha, str) and len(expected_sha) == 64, f"{label} source SHA-256 is missing")
    path = maps.resolve_path(repo_root, raw_path)
    require(path.is_file() and not path.is_symlink(), f"{label} source is missing or not a regular file")
    require(path.resolve().is_relative_to(repo_root.resolve()), f"{label} source is outside the repository")
    actual_sha = maps.sha256_file(path)
    require(actual_sha == expected_sha, f"{label} source SHA-256 mismatch")
    return path, {
        "path": portable_path(path, repo_root),
        "byteLength": path.stat().st_size,
        "sha256": actual_sha,
    }


def locate_anchor_records(
    analysis: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], Mapping[str, Any], Mapping[str, Any]]:
    inventory = analysis.get("snapshotInventory")
    require(isinstance(inventory, dict) and inventory.get("passed") is True, "endpoint inventory is not validated")
    require(inventory.get("actualEndpointCount") == 10, "endpoint inventory is not exactly ten snapshots")
    entries = inventory.get("entries")
    require(isinstance(entries, list), "endpoint inventory entries are missing")
    anchor_records: dict[str, Mapping[str, Any]] = {}
    for basis_id, state_id in (("barrage-closed", "direct_0"), ("barrage-open", "direct_100")):
        matches = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("basisId") == basis_id
            and entry.get("modelHour") == MODEL_HOUR
        ]
        require(len(matches) == 1, f"{state_id} anchor record is missing or duplicated")
        anchor_records[state_id] = matches[0]

    reference = analysis.get("heldOutReference")
    require(isinstance(reference, dict) and reference.get("passed") is True, "direct 50% reference is not validated")
    reference_entries = reference.get("entries")
    require(isinstance(reference_entries, list), "direct 50% reference entries are missing")
    reference_matches = [
        entry
        for entry in reference_entries
        if isinstance(entry, dict) and entry.get("modelHour") == MODEL_HOUR
    ]
    require(len(reference_matches) == 1, "direct 50% anchor record is missing or duplicated")
    anchor_records["direct_50"] = reference_matches[0]

    evaluation = analysis.get("holdoutEvaluation")
    require(isinstance(evaluation, dict) and evaluation.get("evaluable") is True, "holdout evaluation is not evaluable")
    selection = evaluation.get("worstMapSelection")
    require(isinstance(selection, dict), "worst-map selection is missing")
    require(selection.get("modelHour") == MODEL_HOUR, "selected model hour is not -9")
    require(selection.get("metric") == "velocityVectorRmseMPS", "worst-map selection metric changed")

    derived = analysis.get("derivedArtifacts")
    require(isinstance(derived, dict) and derived.get("createdThisInvocation") is True, "derived fields are unavailable")
    derived_records = derived.get("mapReadyWorstHourFields")
    require(isinstance(derived_records, list), "derived-field inventory is missing")
    velocity_matches = [
        record
        for record in derived_records
        if isinstance(record, dict)
        and record.get("kind") == "velocity_error"
        and record.get("modelHour") == MODEL_HOUR
    ]
    depth_matches = [
        record
        for record in derived_records
        if isinstance(record, dict)
        and record.get("kind") == "depth_error"
        and record.get("modelHour") == MODEL_HOUR
    ]
    require(len(velocity_matches) == 1, "existing velocity-error field is missing or duplicated")
    require(len(depth_matches) == 1, "existing depth-error field is missing or duplicated")
    return anchor_records, velocity_matches[0], depth_matches[0]


def load_inputs(
    repo_root: Path,
) -> tuple[
    dict[str, dict[str, np.ndarray]],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    analysis_path = repo_root / ANALYSIS_RELATIVE
    analysis = maps.load_json(analysis_path)
    require(analysis.get("schema") == ANALYSIS_SCHEMA, "recovery analysis schema mismatch")
    require(analysis.get("status") == "evaluated_failed_thresholds", "expected evaluated threshold-failure analysis")
    safeguards = analysis.get("safeguards")
    require(isinstance(safeguards, dict), "analysis safeguards are missing")
    for key in (
        "solverInvoked",
        "networkAccessAttempted",
        "additionalPhysicalRunPerformed",
        "publicSimulatorConnected",
        "physicalValidationClaimAllowed",
    ):
        require(safeguards.get(key) is False, f"analysis safeguard {key} must be false")

    anchor_records, velocity_record, depth_record = locate_anchor_records(analysis)
    fields: dict[str, dict[str, np.ndarray]] = {}
    source_anchors: dict[str, Any] = {}
    for state_id in ("direct_0", "direct_50", "direct_100"):
        path, source_record = validate_source_file(anchor_records[state_id], repo_root, state_id)
        fields[state_id] = maps.load_npz(path, FIELD_KEYS, CELL_COUNT, state_id)
        source_record["openingPercent"] = {"direct_0": 0, "direct_50": 50, "direct_100": 100}[state_id]
        source_record["modelHour"] = MODEL_HOUR
        source_record["dtype"] = "float64"
        source_anchors[state_id] = source_record

    fields["interpolated_25"] = {
        key: 0.5 * fields["direct_0"][key] + 0.5 * fields["direct_50"][key]
        for key in FIELD_KEYS
    }
    fields["interpolated_75"] = {
        key: 0.5 * fields["direct_50"][key] + 0.5 * fields["direct_100"][key]
        for key in FIELD_KEYS
    }
    canonical_depth = (
        0.5 * fields["direct_0"]["waterDepthM"]
        + 0.5 * fields["direct_100"]["waterDepthM"]
        - fields["direct_50"]["waterDepthM"]
    )
    fields["canonical_kink"] = {
        "waterDepthM": fields["direct_50"]["waterDepthM"].copy(),
        "velocityUms": (
            0.5 * fields["direct_0"]["velocityUms"]
            + 0.5 * fields["direct_100"]["velocityUms"]
            - fields["direct_50"]["velocityUms"]
        ),
        "velocityVms": (
            0.5 * fields["direct_0"]["velocityVms"]
            + 0.5 * fields["direct_100"]["velocityVms"]
            - fields["direct_50"]["velocityVms"]
        ),
    }

    for state_id in ("interpolated_25", "interpolated_75", "canonical_kink"):
        for key, array in fields[state_id].items():
            require(array.dtype == np.dtype("float64"), f"{state_id}.{key} is not float64")
            require(array.shape == (CELL_COUNT,), f"{state_id}.{key} shape mismatch")
            require(np.all(np.isfinite(array)), f"{state_id}.{key} contains a non-finite value")
    for state_id in ("direct_0", "interpolated_25", "direct_50", "interpolated_75", "direct_100"):
        require(np.all(fields[state_id]["waterDepthM"] >= 0.0), f"{state_id} contains a negative depth")

    velocity_path, velocity_source = validate_source_file(velocity_record, repo_root, "existing velocity error")
    existing_velocity = maps.load_npz(velocity_path, FIELD_KEYS, CELL_COUNT, "existing velocity error")
    require(
        np.array_equal(existing_velocity["waterDepthM"], fields["direct_50"]["waterDepthM"]),
        "existing velocity-error depth backdrop is not the direct 50% depth",
    )
    require(
        np.array_equal(existing_velocity["velocityUms"], fields["canonical_kink"]["velocityUms"]),
        "canonical kink U does not exactly match the existing velocity-error field",
    )
    require(
        np.array_equal(existing_velocity["velocityVms"], fields["canonical_kink"]["velocityVms"]),
        "canonical kink V does not exactly match the existing velocity-error field",
    )

    depth_path, depth_source = validate_source_file(depth_record, repo_root, "existing depth error")
    existing_depth = maps.load_npz(
        depth_path,
        ("waterDepthErrorM",),
        CELL_COUNT,
        "existing depth error",
    )["waterDepthErrorM"]
    require(
        np.array_equal(existing_depth, canonical_depth),
        "canonical depth kink does not exactly match the existing depth-error field",
    )

    step_differences: dict[str, float] = {}
    for key in FIELD_KEYS:
        step_expression = (
            (fields["interpolated_75"][key] - fields["direct_50"][key])
            - (fields["direct_50"][key] - fields["interpolated_25"][key])
        )
        canonical = canonical_depth if key == "waterDepthM" else fields["canonical_kink"][key]
        maximum_difference = float(np.max(np.abs(step_expression - canonical)))
        require(
            np.allclose(
                step_expression,
                canonical,
                rtol=0.0,
                atol=STEP_ALLCLOSE_ATOL,
            ),
            f"25%-step expression does not match canonical kink for {key}",
        )
        step_differences[key] = maximum_difference

    left_at_middle = {
        key: 0.0 * fields["direct_0"][key] + 1.0 * fields["direct_50"][key]
        for key in FIELD_KEYS
    }
    right_at_middle = {
        key: 1.0 * fields["direct_50"][key] + 0.0 * fields["direct_100"][key]
        for key in FIELD_KEYS
    }
    require(
        all(np.array_equal(left_at_middle[key], fields["direct_50"][key]) for key in FIELD_KEYS),
        "left segment does not return the direct 50% anchor exactly",
    )
    require(
        all(np.array_equal(right_at_middle[key], fields["direct_50"][key]) for key in FIELD_KEYS),
        "right segment does not return the direct 50% anchor exactly",
    )
    require(
        all(
            np.array_equal(
                fields["interpolated_25"][key],
                0.5 * fields["direct_0"][key] + 0.5 * fields["direct_50"][key],
            )
            for key in FIELD_KEYS
        ),
        "25% field algebra mismatch",
    )
    require(
        all(
            np.array_equal(
                fields["interpolated_75"][key],
                0.5 * fields["direct_50"][key] + 0.5 * fields["direct_100"][key],
            )
            for key in FIELD_KEYS
        ),
        "75% field algebra mismatch",
    )

    validation = {
        "directMiddleAnchorReusedWithoutEndpointMidpointReplacement": True,
        "leftSegmentReturnsDirect50Exactly": True,
        "rightSegmentReturnsDirect50Exactly": True,
        "valueContinuousAt50Percent": True,
        "canonicalKinkVelocityMatchesExistingErrorExactly": True,
        "canonicalKinkDepthMatchesExistingErrorExactly": True,
        "stepExpression": "(F75-F50)-(F50-F25)",
        "canonicalExpression": "0.5*F0+0.5*F100-F50",
        "stepExpressionAllclose": True,
        "stepExpressionRtol": 0.0,
        "stepExpressionAtol": STEP_ALLCLOSE_ATOL,
        "maximumAbsoluteRoundingDifference": step_differences,
        "interpolatedFieldsFinite": True,
        "interpolatedDepthsNonnegative": True,
    }
    sources = {
        "analysis": {
            "path": portable_path(analysis_path, repo_root),
            "byteLength": analysis_path.stat().st_size,
            "sha256": maps.sha256_file(analysis_path),
            "schema": analysis["schema"],
            "status": analysis["status"],
        },
        "anchors": source_anchors,
        "existingVelocityError": velocity_source,
        "existingDepthError": depth_source,
    }
    return fields, analysis, sources, validation


def compute_metrics(
    fields: Mapping[str, Mapping[str, np.ndarray]],
    masks_by_region: Mapping[str, np.ndarray],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for region_id in REGION_ORDER:
        cells = masks_by_region[region_id]
        left_u = fields["direct_50"]["velocityUms"][cells] - fields["interpolated_25"]["velocityUms"][cells]
        left_v = fields["direct_50"]["velocityVms"][cells] - fields["interpolated_25"]["velocityVms"][cells]
        right_u = fields["interpolated_75"]["velocityUms"][cells] - fields["direct_50"]["velocityUms"][cells]
        right_v = fields["interpolated_75"]["velocityVms"][cells] - fields["direct_50"]["velocityVms"][cells]
        kink_u = fields["canonical_kink"]["velocityUms"][cells]
        kink_v = fields["canonical_kink"]["velocityVms"][cells]
        left_depth = (
            fields["direct_50"]["waterDepthM"][cells]
            - fields["interpolated_25"]["waterDepthM"][cells]
        )
        right_depth = (
            fields["interpolated_75"]["waterDepthM"][cells]
            - fields["direct_50"]["waterDepthM"][cells]
        )
        depth_kink = (
            0.5 * fields["direct_0"]["waterDepthM"][cells]
            + 0.5 * fields["direct_100"]["waterDepthM"][cells]
            - fields["direct_50"]["waterDepthM"][cells]
        )
        kink_magnitude = np.hypot(kink_u, kink_v)
        rows.append(
            {
                "regionId": region_id,
                "labelJa": REGION_LABELS[region_id],
                "cellCount": int(cells.size),
                "left25StepVelocityVectorRmseMPS": float(np.sqrt(np.mean(left_u * left_u + left_v * left_v))),
                "right25StepVelocityVectorRmseMPS": float(np.sqrt(np.mean(right_u * right_u + right_v * right_v))),
                "canonicalKinkVelocityVectorRmseMPS": float(np.sqrt(np.mean(kink_u * kink_u + kink_v * kink_v))),
                "canonicalKinkVelocityMagnitudeP95MPS": float(np.percentile(kink_magnitude, 95.0)),
                "left25StepDepthRmseM": float(np.sqrt(np.mean(left_depth * left_depth))),
                "right25StepDepthRmseM": float(np.sqrt(np.mean(right_depth * right_depth))),
                "canonicalKinkDepthRmseM": float(np.sqrt(np.mean(depth_kink * depth_kink))),
                "valueContinuityAt50Percent": True,
                "slopeSmoothnessAt50Percent": False,
            }
        )
    return rows


def create_projection(
    package: Mapping[str, np.ndarray],
    fields: Mapping[str, Mapping[str, np.ndarray]],
    geographic: Mapping[str, Any],
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, np.ndarray],
    dict[int, dict[str, Any]],
]:
    triangles = package["triangles"].astype(np.int64)
    image_vertices = package["vertex_image_millipixel"].astype(np.float64) * 0.001
    image_centres = image_vertices[triangles].mean(axis=1)
    local_vertices = package["vertex_local_mm"].astype(np.float64) * 0.001
    local_triangles = local_vertices[triangles]
    area = 0.5 * np.abs(
        (local_triangles[:, 1, 0] - local_triangles[:, 0, 0])
        * (local_triangles[:, 2, 1] - local_triangles[:, 0, 1])
        - (local_triangles[:, 1, 1] - local_triangles[:, 0, 1])
        * (local_triangles[:, 2, 0] - local_triangles[:, 0, 0])
    )
    require(np.all(np.isfinite(area)) and np.all(area > 0.0), "mesh contains a degenerate cell")

    speeds = {
        state_id: np.hypot(fields[state_id]["velocityUms"], fields[state_id]["velocityVms"])
        for state_id in STATE_ORDER
    }
    state_p95 = {
        state_id: maps.percentile_nonzero(speeds[state_id])
        for state_id in STATE_ORDER
    }
    calculated_speed_ceiling = maps.rounded_ceiling(
        max(state_p95[state_id] for state_id in STATE_ORDER[:5])
    )
    calculated_kink_ceiling = maps.rounded_ceiling(state_p95["canonical_kink"])
    require(
        math.isclose(calculated_speed_ceiling, SPEED_CEILING_MPS, abs_tol=1.0e-12),
        "five-state shared speed ceiling is not 0.13 m/s",
    )
    require(
        math.isclose(calculated_kink_ceiling, KINK_CEILING_MPS, abs_tol=1.0e-12),
        "canonical-kink ceiling is not 0.04 m/s",
    )

    internal_vertices = package["internal_face_vertices"].astype(np.int64)
    barrage_ids = package["barrage_face_ids"].astype(np.int64)
    fishway_cells = package["fishway_cells"].astype(np.int64)
    confluence_image = np.asarray([[1168.0, 441.0]], dtype=np.float64)
    projected: dict[int, dict[str, Any]] = {}
    for zoom in (16, 18):
        projected_vertices = maps.image_points_to_world(image_vertices, geographic, zoom)
        projected_centres = projected_vertices[triangles].mean(axis=1)
        screens: dict[str, np.ndarray] = {}
        for state_id in STATE_ORDER:
            endpoints = image_centres + np.column_stack(
                (
                    fields[state_id]["velocityUms"],
                    -fields[state_id]["velocityVms"],
                )
            )
            endpoint_world = maps.image_points_to_world(endpoints, geographic, zoom)
            direction = endpoint_world - projected_centres
            norm = np.linalg.norm(direction, axis=1)
            screens[state_id] = direction * np.divide(
                speeds[state_id],
                np.maximum(norm, 1.0e-12),
            )[:, None]
        projected[zoom] = {
            "vertices": projected_vertices,
            "centres": projected_centres,
            "screens": screens,
            "barrage": projected_vertices[internal_vertices[barrage_ids]],
            "fishway": projected_centres[fishway_cells],
            "confluence": maps.image_points_to_world(confluence_image, geographic, zoom)[0],
        }
    return triangles, area, image_vertices, speeds, projected


def prepare_views(
    view_records: list[dict[str, Any]],
    masks_by_region: Mapping[str, np.ndarray],
    projected: Mapping[int, Mapping[str, Any]],
    repo_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    tile_root = repo_root / TILE_ROOT_RELATIVE
    require(tile_root.is_dir() and not tile_root.is_symlink(), "local GSI tile root is missing")
    prepared_views: dict[str, dict[str, Any]] = {}
    tile_inventory: dict[str, dict[str, str]] = {}
    for view in view_records:
        view_id = str(view["id"])
        zoom = int(view["zoom"])
        geometry = projected[zoom]
        prepared, tile_records = maps.prepare_view(
            view=view,
            mask=masks_by_region[view_id],
            tile_root=tile_root,
            projected_vertices=geometry["vertices"],
            projected_centres=geometry["centres"],
            barrage_segments=geometry["barrage"],
            fishway_centres=geometry["fishway"],
            confluence_world=geometry["confluence"],
        )
        prepared_views[view_id] = prepared
        for record in tile_records:
            tile_inventory[record["path"]] = record
    return prepared_views, tile_inventory


def render_panels(
    prepared_views: Mapping[str, Mapping[str, Any]],
    triangles: np.ndarray,
    area: np.ndarray,
    speeds: Mapping[str, np.ndarray],
    projected: Mapping[int, Mapping[str, Any]],
    direct_50_depth: np.ndarray,
) -> tuple[dict[str, list[Image.Image]], dict[str, dict[str, int]]]:
    panels_by_region: dict[str, list[Image.Image]] = {}
    arrows_by_region: dict[str, dict[str, int]] = {}
    for region_id in REGION_ORDER:
        prepared = prepared_views[region_id]
        zoom = int(prepared["zoom"])
        panels: list[Image.Image] = []
        arrow_counts: dict[str, int] = {}
        for state_id in STATE_ORDER:
            ceiling = KINK_CEILING_MPS if state_id == "canonical_kink" else SPEED_CEILING_MPS
            stops = maps.ERROR_STOPS if state_id == "canonical_kink" else maps.SPEED_STOPS
            panel, arrow_count = maps.render_panel(
                prepared=prepared,
                triangles=triangles,
                magnitude=speeds[state_id],
                velocity_screen=projected[zoom]["screens"][state_id],
                depth=direct_50_depth,
                area=area,
                ceiling=ceiling,
                stops=stops,
            )
            panels.append(panel)
            arrow_counts[state_id] = arrow_count
        panels_by_region[region_id] = panels
        arrows_by_region[region_id] = arrow_counts
    return panels_by_region, arrows_by_region


def draw_gradient(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    stops: tuple[tuple[float, tuple[int, int, int]], ...],
) -> None:
    left, top, right, bottom = box
    width = max(1, right - left)
    for offset in range(width):
        colour = maps.interpolate_colour(float(offset), float(max(1, width - 1)), stops, 255)[:3]
        draw.line((left + offset, top, left + offset, bottom), fill=colour)


def detail_metric_text(metric: Mapping[str, Any]) -> str:
    return (
        f"左25%刻み v変化 {float(metric['left25StepVelocityVectorRmseMPS']):.3f} m/s　"
        f"右25%刻み v変化 {float(metric['right25StepVelocityVectorRmseMPS']):.3f} m/s　"
        f"50%刻み差 {float(metric['canonicalKinkVelocityVectorRmseMPS']):.3f} m/s　"
        f"水深刻み差 {float(metric['canonicalKinkDepthRmseM']):.3f} m"
    )


def build_detail_jpg(
    region_id: str,
    panels: list[Image.Image],
    metric: Mapping[str, Any],
) -> tuple[bytes, tuple[int, int]]:
    require(len(panels) == 6, "regional detail needs six panels")
    width, height = 3240, 735
    canvas = Image.new("RGB", (width, height), (244, 247, 248))
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (42, 20),
        f"{REGION_LABELS[region_id]}｜河口堰区間別補間候補",
        font=maps.font(29, True),
        fill=(23, 49, 59),
    )
    draw.text(
        (42, 61),
        "モデル内相対 −9 h（実日時・予報時刻ではない）｜0・50・100%は直接計算、25・75%は区間補間",
        font=maps.font(17),
        fill=(72, 97, 107),
    )
    panel_x = [42 + index * 530 for index in range(6)]
    image_y = 132
    for index, (state_id, panel, x) in enumerate(zip(STATE_ORDER, panels, panel_x)):
        title = STATE_TITLES[state_id]
        title_fill = (153, 91, 8) if state_id == "direct_50" else (23, 49, 59)
        draw.text((x, 101), title, font=maps.font(18, True), fill=title_fill)
        border = (204, 133, 20) if state_id == "direct_50" else (184, 198, 203)
        border_width = 6 if state_id == "direct_50" else 2
        draw.rectangle(
            (x - border_width, image_y - border_width, x + 500 + border_width, image_y + 310 + border_width),
            outline=border,
            width=border_width,
        )
        canvas.paste(panel, (x, image_y))
        stops = maps.ERROR_STOPS if state_id == "canonical_kink" else maps.SPEED_STOPS
        ceiling = KINK_CEILING_MPS if state_id == "canonical_kink" else SPEED_CEILING_MPS
        draw_gradient(draw, (x, 461, x + 170, 472), stops)
        legend = "刻み変化差" if state_id == "canonical_kink" else "流速"
        draw.text(
            (x, 480),
            f"{legend} 0–{ceiling:.2f} m/s",
            font=maps.font(14),
            fill=(61, 83, 91),
        )
    draw.text((42, 526), detail_metric_text(metric), font=maps.font(18, True), fill=(23, 49, 59))
    draw.text(
        (42, 564),
        "値の連続・直接50%固定：保証　｜　変化率の滑らかさ：未達（既存50:50比較20件中15件が基準超過）",
        font=maps.font(17, True),
        fill=(147, 35, 29),
    )
    draw.text(
        (42, 599),
        "25%・75%は直接物理計算で未検証。矢印位置は全列で直接50%水深×セル面積を共通重みにして比較。",
        font=maps.font(16),
        fill=(61, 83, 91),
    )
    draw.text(
        (42, 626),
        "地図＝封印済みfloat64源。ブラウザ候補＝float32（速度ベクトル量子化最大誤差3.05e−8 m/s）；50%固定は候補パック内で厳密。",
        font=maps.font(14),
        fill=(72, 97, 107),
    )
    draw.text(
        (42, 657),
        "判断：A この形を公開未接続の内部コード候補として保持　／　B 不採用にして停止",
        font=maps.font(18, True),
        fill=(23, 49, 59),
    )
    draw.text((42, 706), f"{DISCLAIMER}。{GSI_ATTRIBUTION}", font=maps.font(14), fill=(72, 97, 107))
    return maps.jpeg_bytes(canvas, quality=90), canvas.size


def svg_gradient(stops: tuple[tuple[float, tuple[int, int, int]], ...]) -> str:
    parts: list[str] = []
    for offset, colour in stops:
        parts.append(
            f'<stop offset="{offset * 100:.0f}%" stop-color="#{colour[0]:02x}{colour[1]:02x}{colour[2]:02x}"/>'
        )
    return "".join(parts)


def build_detail_svg(
    region_id: str,
    panels: list[Image.Image],
    metric: Mapping[str, Any],
) -> bytes:
    require(len(panels) == 6, "regional detail needs six panels")
    width, height = 3240, 735
    panel_x = [42 + index * 530 for index in range(6)]
    payloads = [
        base64.b64encode(maps.jpeg_bytes(panel, quality=88)).decode("ascii")
        for panel in panels
    ]
    title = html.escape(REGION_LABELS[region_id], quote=True)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="&#104;ttp://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title-{region_id} desc-{region_id}">'
        ),
        f'<title id="title-{region_id}">{title}・河口堰区間別補間候補</title>',
        (
            f'<desc id="desc-{region_id}">モデル内相対マイナス9時間の0、25、50、75、100%流速と、'
            "50%前後の25%刻み変化差。50%は直接計算を固定し値は連続だが、変化率の滑らかさは未達。"
            "25%と75%は直接物理計算で未検証。</desc>"
        ),
        "<defs>",
        f'<linearGradient id="speed" x1="0" y1="0" x2="1" y2="0">{svg_gradient(maps.SPEED_STOPS)}</linearGradient>',
        f'<linearGradient id="kink" x1="0" y1="0" x2="1" y2="0">{svg_gradient(maps.ERROR_STOPS)}</linearGradient>',
        "</defs>",
        '<rect width="100%" height="100%" fill="#f4f7f8"/>',
        (
            f'<text x="42" y="46" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
            f'\'Noto Sans JP\',sans-serif" font-size="29" font-weight="700" fill="#17313b">'
            f"{title}｜河口堰区間別補間候補</text>"
        ),
        (
            '<text x="42" y="81" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
            '\'Noto Sans JP\',sans-serif" font-size="17" fill="#48616b">'
            "モデル内相対 −9 h（実日時・予報時刻ではない）｜0・50・100%は直接計算、25・75%は区間補間</text>"
        ),
    ]
    for index, (state_id, payload, x) in enumerate(zip(STATE_ORDER, payloads, panel_x)):
        title_text = html.escape(STATE_TITLES[state_id], quote=True)
        title_colour = "#995b08" if state_id == "direct_50" else "#17313b"
        border_colour = "#cc8514" if state_id == "direct_50" else "#b8c6cb"
        border_width = 6 if state_id == "direct_50" else 2
        gradient = "kink" if state_id == "canonical_kink" else "speed"
        ceiling = KINK_CEILING_MPS if state_id == "canonical_kink" else SPEED_CEILING_MPS
        legend = "刻み変化差" if state_id == "canonical_kink" else "流速"
        parts.extend(
            [
                (
                    f'<text x="{x}" y="119" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
                    f'\'Noto Sans JP\',sans-serif" font-size="18" font-weight="700" fill="{title_colour}">'
                    f"{title_text}</text>"
                ),
                (
                    f'<rect x="{x - border_width}" y="{132 - border_width}" '
                    f'width="{500 + 2 * border_width}" height="{310 + 2 * border_width}" '
                    f'fill="none" stroke="{border_colour}" stroke-width="{border_width}"/>'
                ),
                f'<image x="{x}" y="132" width="500" height="310" href="data:image/jpeg;base64,{payload}"/>',
                f'<rect x="{x}" y="461" width="170" height="11" fill="url(#{gradient})"/>',
                (
                    f'<text x="{x}" y="495" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
                    f'\'Noto Sans JP\',sans-serif" font-size="14" fill="#3d535b">'
                    f"{legend} 0–{ceiling:.2f} m/s</text>"
                ),
            ]
        )
    escaped_metric = html.escape(detail_metric_text(metric), quote=True)
    parts.extend(
        [
            (
                '<text x="42" y="544" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
                f'\'Noto Sans JP\',sans-serif" font-size="18" font-weight="700" fill="#17313b">{escaped_metric}</text>'
            ),
            (
                '<text x="42" y="582" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
                '\'Noto Sans JP\',sans-serif" font-size="17" font-weight="700" fill="#93231d">'
                "値の連続・直接50%固定：保証　｜　変化率の滑らかさ：未達（既存50:50比較20件中15件が基準超過）</text>"
            ),
            (
                '<text x="42" y="617" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
                '\'Noto Sans JP\',sans-serif" font-size="16" fill="#3d535b">'
                "25%・75%は直接物理計算で未検証。矢印位置は全列で直接50%水深×セル面積を共通重みにして比較。</text>"
            ),
            (
                '<text x="42" y="644" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
                '\'Noto Sans JP\',sans-serif" font-size="14" fill="#48616b">'
                "地図＝封印済みfloat64源。ブラウザ候補＝float32（速度ベクトル量子化最大誤差3.05e−8 m/s）；"
                "50%固定は候補パック内で厳密。</text>"
            ),
            (
                '<text x="42" y="675" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
                '\'Noto Sans JP\',sans-serif" font-size="18" font-weight="700" fill="#17313b">'
                "判断：A この形を公開未接続の内部コード候補として保持　／　B 不採用にして停止</text>"
            ),
            (
                '<text x="42" y="724" font-family="-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
                f'\'Noto Sans JP\',sans-serif" font-size="14" fill="#48616b">{html.escape(DISCLAIMER)}。'
                f"{html.escape(GSI_ATTRIBUTION)}</text>"
            ),
            "</svg>",
        ]
    )
    return ("\n".join(parts) + "\n").encode("utf-8")


def build_overview(
    panels_by_region: Mapping[str, list[Image.Image]],
    metrics_by_region: Mapping[str, Mapping[str, Any]],
) -> tuple[bytes, tuple[int, int]]:
    width = 2000
    header_height = 190
    row_height = 250
    footer_height = 300
    height = header_height + row_height * 4 + footer_height
    canvas = Image.new("RGB", (width, height), (244, 247, 248))
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (24, 16),
        "河口堰区間別補間候補｜0・25・50・75・100%と50%前後の刻み差",
        font=maps.font(30, True),
        fill=(23, 49, 59),
    )
    draw.rounded_rectangle((24, 58, 990, 96), radius=19, fill=(22, 121, 74))
    draw.text(
        (507, 77),
        "値の連続・直接50%固定：保証",
        anchor="mm",
        font=maps.font(18, True),
        fill=(255, 255, 255),
    )
    draw.rounded_rectangle((1010, 58, 1976, 96), radius=19, fill=(179, 38, 30))
    draw.text(
        (1493, 77),
        "変化率の滑らかさ：未達（既存50:50比較20件中15件が基準超過）",
        anchor="mm",
        font=maps.font(18, True),
        fill=(255, 255, 255),
    )
    draw.text(
        (24, 109),
        "モデル内相対 −9 h（実日時・予報時刻ではない）｜25%=(0%+50%)/2、75%=(50%+100%)/2",
        font=maps.font(17),
        fill=(72, 97, 107),
    )
    panel_x = [200 + index * 298 for index in range(6)]
    for state_id, x in zip(STATE_ORDER, panel_x):
        colour = (153, 91, 8) if state_id == "direct_50" else (23, 49, 59)
        draw.text(
            (x + 143, 174),
            STATE_TITLES[state_id],
            anchor="ms",
            font=maps.font(16, True),
            fill=colour,
        )

    thumb_size = (286, 177)
    for row_index, region_id in enumerate(REGION_ORDER):
        row_y = header_height + row_index * row_height
        draw.rounded_rectangle(
            (14, row_y + 10, 1986, row_y + row_height - 8),
            radius=10,
            fill=(255, 255, 255),
            outline=(211, 222, 226),
            width=2,
        )
        label = "曲川・遠賀川\n合流地点付近" if region_id == "confluence" else REGION_LABELS[region_id]
        label_font = maps.font(15 if region_id == "confluence" else 20, True)
        draw.multiline_text((28, row_y + 25), label, font=label_font, fill=(23, 49, 59), spacing=2)
        metric = metrics_by_region[region_id]
        draw.text(
            (28, row_y + 91),
            f"左Δ {float(metric['left25StepVelocityVectorRmseMPS']):.3f}",
            font=maps.font(14),
            fill=(61, 83, 91),
        )
        draw.text(
            (28, row_y + 119),
            f"右Δ {float(metric['right25StepVelocityVectorRmseMPS']):.3f}",
            font=maps.font(14),
            fill=(61, 83, 91),
        )
        draw.text(
            (28, row_y + 147),
            f"刻み差 {float(metric['canonicalKinkVelocityVectorRmseMPS']):.3f} m/s",
            font=maps.font(14, True),
            fill=(147, 35, 29),
        )
        draw.text(
            (28, row_y + 182),
            f"水深差 {float(metric['canonicalKinkDepthRmseM']):.3f} m",
            font=maps.font(14),
            fill=(61, 83, 91),
        )
        for state_id, panel, x in zip(STATE_ORDER, panels_by_region[region_id], panel_x):
            thumb = panel.resize(thumb_size, Image.Resampling.LANCZOS)
            y = row_y + 30
            border = (204, 133, 20) if state_id == "direct_50" else (184, 198, 203)
            border_width = 5 if state_id == "direct_50" else 1
            canvas.paste(thumb, (x, y))
            draw.rectangle(
                (x - border_width, y - border_width, x + thumb_size[0] + border_width, y + thumb_size[1] + border_width),
                outline=border,
                width=border_width,
            )
        draw.text(
            (200, row_y + 219),
            "0–100%の5列は共通 0–0.13 m/s　｜　刻み変化差は 0–0.04 m/s",
            font=maps.font(13),
            fill=(61, 83, 91),
        )

    footer_y = header_height + row_height * 4
    draw.text(
        (24, footer_y + 18),
        "判断：A この形を公開未接続の内部コード候補として保持　／　B 不採用にして停止",
        font=maps.font(21, True),
        fill=(23, 49, 59),
    )
    draw.text(
        (24, footer_y + 58),
        "50%は左右両区間で直接50%配列に完全一致。25%・75%は補間候補であり、直接物理計算では検証していない。",
        font=maps.font(17, True),
        fill=(147, 35, 29),
    )
    draw.text(
        (24, footer_y + 94),
        "6列目：0.5×直接0% + 0.5×直接100% − 直接50% ＝ 50%前後の25%刻み変化差。",
        font=maps.font(16),
        fill=(61, 83, 91),
    )
    draw.text(
        (24, footer_y + 128),
        "矢印位置は全列で直接50%水深×セル面積を共通重みにして固定。矢印の移動ではなく、向きと長さを比較する。",
        font=maps.font(16),
        fill=(61, 83, 91),
    )
    draw.text(
        (24, footer_y + 162),
        "地図は封印済みfloat64源。ブラウザ候補はfloat32（速度ベクトル量子化最大誤差3.05e−8 m/s）；50%固定は候補パック内で厳密。",
        font=maps.font(15),
        fill=(72, 97, 107),
    )
    draw.text(
        (24, footer_y + 194),
        f"{DISCLAIMER}。公開シミュレータ未接続。追加物理計算なし。",
        font=maps.font(16, True),
        fill=(112, 61, 61),
    )
    draw.text((24, footer_y + 230), GSI_ATTRIBUTION, font=maps.font(15), fill=(72, 97, 107))
    draw.text(
        (24, footer_y + 262),
        "左Δ=25→50%の速度変化RMSE、右Δ=50→75%の速度変化RMSE、刻み差=右Δベクトル−左ΔベクトルのRMSE",
        font=maps.font(13),
        fill=(72, 97, 107),
    )
    return maps.jpeg_bytes(canvas, quality=90), canvas.size


def prepare_output(path: Path) -> None:
    require(not path.is_symlink(), f"output may not be a symlink: {path}")
    if path.exists():
        require(path.is_file(), f"output path is not a regular file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def file_record(path: Path, repo_root: Path, width: int, height: int, format_name: str) -> dict[str, Any]:
    return {
        "path": portable_path(path, repo_root),
        "byteLength": path.stat().st_size,
        "sha256": maps.sha256_file(path),
        "width": width,
        "height": height,
        "format": format_name,
    }


def render(repo_root: Path) -> dict[str, Any]:
    expected_renderer = repo_root / "tools/render_stage20_barrage_piecewise_candidate.py"
    require(Path(__file__).resolve() == expected_renderer.resolve(), "repo root does not contain this renderer")
    output_root = repo_root / OUTPUT_ROOT_RELATIVE
    maps_dir = output_root / "maps"
    manifest_path = output_root / "piecewise-map-manifest.json"
    require(not output_root.is_symlink() and not maps_dir.is_symlink(), "candidate output path may not be a symlink")
    maps_dir.mkdir(parents=True, exist_ok=True)
    require(maps_dir.is_dir(), "candidate maps directory is invalid")

    browser_pack_path = repo_root / BROWSER_PACK_RELATIVE
    browser_pack = maps.load_json(browser_pack_path)
    require(
        browser_pack.get("schema") == BROWSER_PACK_SCHEMA,
        "browser anchor-pack schema mismatch",
    )
    browser_arrays = browser_pack.get("arrays", {}).get("anchors", {})
    require(
        browser_arrays.get("dtype") == "float32-le",
        "browser anchor pack is not float32-le",
    )
    browser_quantization = browser_pack.get("float32Quantization")
    require(
        isinstance(browser_quantization, dict)
        and browser_quantization.get("passed") is True,
        "browser anchor-pack float32 quantization is not validated",
    )
    browser_max_vector_error = float(
        browser_quantization["maximumVelocityVectorAbsoluteErrorMPS"]
    )
    require(
        browser_max_vector_error
        <= BROWSER_PACK_MAX_VECTOR_QUANTIZATION_ERROR_MPS,
        "browser anchor-pack velocity-vector quantization exceeds 3.05e-8 m/s",
    )
    require(
        browser_pack.get("openingContract", {}).get("middleAnchorRule")
        == "p_equals_0.5_returns_the_packed_direct_50_percent_anchor_exactly",
        "browser anchor-pack middle-anchor rule changed",
    )

    fields, analysis, source_records, algebra_validation = load_inputs(repo_root)
    mesh_path = repo_root / MESH_RELATIVE
    mesh_manifest, package, mesh_record = maps.load_mesh(mesh_path)
    require(int(mesh_manifest["counts"]["cells"]) == CELL_COUNT, "mesh cell count changed")
    mask_manifest_path = repo_root / MASK_RELATIVE
    _, view_records, masks_by_region, mask_record = maps.load_region_masks(
        mask_manifest_path,
        repo_root,
        str(mesh_manifest["binary"]["sha256"]),
        CELL_COUNT,
    )
    require([record["id"] for record in view_records] == list(REGION_ORDER), "fixed regional order changed")
    metrics = compute_metrics(fields, masks_by_region)
    metrics_by_region = {str(metric["regionId"]): metric for metric in metrics}

    analysis_rows = analysis["holdoutEvaluation"]["perHourRegion"]
    for metric in metrics:
        matches = [
            row
            for row in analysis_rows
            if row["modelHour"] == MODEL_HOUR and row["regionId"] == metric["regionId"]
        ]
        require(len(matches) == 1, "source holdout metric row is missing")
        require(
            math.isclose(
                float(matches[0]["velocityVectorRmseMPS"]),
                float(metric["canonicalKinkVelocityVectorRmseMPS"]),
                rel_tol=0.0,
                abs_tol=1.0e-15,
            ),
            f"canonical kink metric changed for {metric['regionId']}",
        )
        require(
            math.isclose(
                float(matches[0]["depthRmseM"]),
                float(metric["canonicalKinkDepthRmseM"]),
                rel_tol=0.0,
                abs_tol=4.0e-15,
            ),
            f"canonical depth-kink metric changed for {metric['regionId']}",
        )
        metric["sourceHoldoutPassed"] = bool(matches[0]["passed"])

    coordinate_path = repo_root / COORDINATE_RELATIVE
    coordinate_manifest = maps.load_json(coordinate_path)
    geographic = coordinate_manifest.get("coordinateSystem", {}).get("geographic")
    require(isinstance(geographic, dict) and geographic.get("crs") == "EPSG:4326", "approved geographic transform is missing")

    triangles, area, _, speeds, projected = create_projection(package, fields, geographic)
    prepared_views, tile_inventory = prepare_views(view_records, masks_by_region, projected, repo_root)
    panels_by_region, arrows_by_region = render_panels(
        prepared_views,
        triangles,
        area,
        speeds,
        projected,
        fields["direct_50"]["waterDepthM"],
    )

    view_outputs: list[dict[str, Any]] = []
    for region_id in REGION_ORDER:
        jpg_payload, jpg_size = build_detail_jpg(
            region_id,
            panels_by_region[region_id],
            metrics_by_region[region_id],
        )
        svg_payload = build_detail_svg(
            region_id,
            panels_by_region[region_id],
            metrics_by_region[region_id],
        )
        jpg_path = maps_dir / f"piecewise-candidate-{region_id}.jpg"
        svg_path = maps_dir / f"piecewise-candidate-{region_id}.svg"
        prepare_output(jpg_path)
        prepare_output(svg_path)
        jpg_path.write_bytes(jpg_payload)
        svg_path.write_bytes(svg_payload)
        view_outputs.append(
            {
                "id": region_id,
                "labelJa": REGION_LABELS[region_id],
                "cellCount": int(masks_by_region[region_id].size),
                "panelCount": 6,
                "panelOrder": list(STATE_ORDER),
                "arrowCounts": arrows_by_region[region_id],
                "commonArrowWeighting": "direct_50_percent_depth_times_cell_area_for_all_six_panels",
                "metrics": metrics_by_region[region_id],
                "jpg": file_record(jpg_path, repo_root, jpg_size[0], jpg_size[1], "JPEG"),
                "svg": file_record(svg_path, repo_root, 3240, 735, "SVG"),
            }
        )

    overview_payload, overview_size = build_overview(panels_by_region, metrics_by_region)
    overview_path = maps_dir / "piecewise-candidate-overview.jpg"
    prepare_output(overview_path)
    overview_path.write_bytes(overview_payload)

    p95_by_state = {
        state_id: maps.percentile_nonzero(speeds[state_id])
        for state_id in STATE_ORDER
    }
    tile_digest_payload = "".join(
        f"{key}\0{tile_inventory[key]['sha256']}\n"
        for key in sorted(tile_inventory)
    ).encode("utf-8")
    renderer_path = Path(__file__).resolve()
    evaluation = analysis["holdoutEvaluation"]
    manifest = {
        "schema": SCHEMA,
        "status": STATUS,
        "recordedDate": "2026-07-17",
        "modelHour": MODEL_HOUR,
        "modelHourMeaning": "model_relative_not_calendar_or_forecast_time",
        "candidate": {
            "openingPercents": [0, 25, 50, 75, 100],
            "directOpeningPercents": [0, 50, 100],
            "interpolatedOpeningPercents": [25, 75],
            "componentOrder": list(FIELD_KEYS),
            "arithmeticDtype": "float64",
            "leftSegmentFormula": "F(p)=(1-2p)*F0+2p*F50 for 0<=p<=0.5",
            "rightSegmentFormula": "F(p)=(2-2p)*F50+(2p-1)*F100 for 0.5<=p<=1",
            "middleAnchorRule": "p_equals_0.5_returns_the_direct_50_percent_arrays_exactly",
            "canonicalKinkFormula": "0.5*F0+0.5*F100-F50",
            "canonicalKinkInterpretation": "difference_between_the_right_and_left_25_percentage_point_velocity_changes",
            "valueContinuityAt50Percent": "guaranteed_by_construction",
            "slopeSmoothnessAt50Percent": "not_achieved",
            "directPhysicalValidationAt25And75Percent": False,
        },
        "browserPackContext": {
            "path": portable_path(browser_pack_path, repo_root),
            "byteLength": browser_pack_path.stat().st_size,
            "sha256": maps.sha256_file(browser_pack_path),
            "schema": browser_pack["schema"],
            "sourceMapArithmeticDtype": "float64",
            "packedAnchorDtype": browser_arrays["dtype"],
            "float32QuantizationPassed": True,
            "maximumVelocityVectorAbsoluteErrorMPS": browser_max_vector_error,
            "displayRoundedMaximumVelocityVectorAbsoluteErrorMPS": (
                BROWSER_PACK_MAX_VECTOR_QUANTIZATION_ERROR_MPS
            ),
            "middleAnchorGuarantee": (
                "exact_within_the_float32_candidate_pack_not_byte_identical_to_"
                "the_sealed_float64_source"
            ),
        },
        "source": source_records,
        "algebraValidation": algebra_validation,
        "priorHoldoutContext": {
            "expectedComparisonCount": evaluation["expectedComparisonCount"],
            "evaluatedComparisonCount": evaluation["evaluatedComparisonCount"],
            "passedComparisonCount": evaluation["passedComparisonCount"],
            "failedComparisonCount": evaluation["failedComparisonCount"],
            "acceptanceResult": evaluation["acceptanceResult"],
            "meaningForCandidate": "the_global_midpoint_error_is_the_piecewise_candidate_middle_anchor_kink",
        },
        "mesh": {
            "manifest": portable_path(mesh_path, repo_root),
            "manifestSha256": maps.sha256_file(mesh_path),
            "binarySha256": mesh_manifest["binary"]["sha256"],
            "cellCount": CELL_COUNT,
            "vertexCount": mesh_record["vertexCount"],
        },
        "regionalMasks": mask_record,
        "coordinateTransform": {
            "path": portable_path(coordinate_path, repo_root),
            "sha256": maps.sha256_file(coordinate_path),
            "crs": "EPSG:4326",
        },
        "satelliteBackdrop": {
            "source": "local_GSI_seamlessphoto_tiles",
            "attributionJa": GSI_ATTRIBUTION,
            "tileCount": len(tile_inventory),
            "inventorySha256": sha256_bytes(tile_digest_payload),
            "networkUsed": False,
        },
        "display": {
            "panelOrder": list(STATE_ORDER),
            "speedScale": {
                "appliesTo": list(STATE_ORDER[:5]),
                "minimumMPS": 0.0,
                "maximumMPS": SPEED_CEILING_MPS,
                "sourceNonzeroP95MPS": {
                    state_id: p95_by_state[state_id]
                    for state_id in STATE_ORDER[:5]
                },
                "rule": "fixed_0_to_0.13_after_verified_max_nonzero_p95_rounded_to_0.01",
            },
            "canonicalKinkScale": {
                "appliesTo": ["canonical_kink"],
                "minimumMPS": 0.0,
                "maximumMPS": KINK_CEILING_MPS,
                "sourceNonzeroP95MPS": p95_by_state["canonical_kink"],
                "rule": "fixed_0_to_0.04_after_verified_nonzero_p95_rounded_to_0.01",
            },
            "arrowAggregation": {
                "bins": "same_fixed_view_bins_for_all_panels",
                "positionAndVectorWeights": "direct_50_percent_water_depth_times_cell_area_for_all_panels",
                "reason": "hold_arrow_positions_constant_so_visual_jitter_is_not_misread_as_field_discontinuity",
            },
            "overview": file_record(
                overview_path,
                repo_root,
                overview_size[0],
                overview_size[1],
                "JPEG",
            ),
            "views": view_outputs,
        },
        "decision": {
            "questionJa": "50%固定と値の連続を保証する一方で変化率の折れが残るこの形をどう扱うか",
            "optionA": "retain_as_isolated_internal_code_candidate_not_connected_to_public_simulator",
            "optionB": "reject_candidate_and_stop_cross_condition_interpolation",
            "optionALabelJa": "この形を公開未接続の内部コード候補として保持",
            "optionBLabelJa": "不採用にして停止",
        },
        "limitations": {
            "direct25PercentPhysicalTruthAvailable": False,
            "direct75PercentPhysicalTruthAvailable": False,
            "observedAccuracyValidated": False,
            "forecastAccuracyValidated": False,
            "thirtySixHourServiceSupported": False,
            "timeVaryingBarrageOperationSupported": False,
            "disclaimerJa": DISCLAIMER,
        },
        "toolchain": {
            "renderer": {
                "path": portable_path(renderer_path, repo_root),
                "sha256": maps.sha256_file(renderer_path),
            },
            "reusedMapRenderer": {
                "path": portable_path(TOOLS / "render_stage20_barrage_holdout_comparison_maps.py", repo_root),
                "sha256": maps.sha256_file(TOOLS / "render_stage20_barrage_holdout_comparison_maps.py"),
            },
            "mode": "offline_existing_float64_fields_only",
        },
        "safeguards": {
            "physicalSolverInvoked": False,
            "networkAccessAttempted": False,
            "additionalPhysicalRunPerformed": False,
            "automaticRetryPerformed": False,
            "publicSimulatorConnected": False,
            "mainMerged": False,
            "sourceFilesModified": False,
            "physicalValidationClaimAllowed": False,
            "forecastValidationClaimAllowed": False,
        },
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    prepare_output(manifest_path)
    manifest_path.write_bytes(manifest_payload)
    return {
        "status": STATUS,
        "modelHour": MODEL_HOUR,
        "overview": str(overview_path),
        "overviewSha256": maps.sha256_file(overview_path),
        "viewCount": len(view_outputs),
        "panelCount": len(view_outputs) * 6,
        "manifest": str(manifest_path),
        "manifestSha256": maps.sha256_file(manifest_path),
        "solverInvoked": False,
        "networkAccessAttempted": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = render(Path(args.repo_root).resolve())
    except CandidateError as error:
        print(
            json.dumps(
                {
                    "status": "not_rendered_invalid_or_incomplete_evidence",
                    "error": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "not_rendered_implementation_or_io_error",
                    "exceptionType": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
