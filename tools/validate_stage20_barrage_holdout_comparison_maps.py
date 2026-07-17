#!/usr/bin/env python3
"""Validate the offline Stage 20 barrage holdout comparison-map renderer.

The validator creates deterministic synthetic map-ready fields for all 50,199
mesh cells in a temporary directory.  It never invokes a solver and does not
use network access.  The production rendering entry point is exercised twice
against the same inputs so that byte-for-byte determinism can be checked.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Mapping

sys.dont_write_bytecode = True

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools/render_stage20_barrage_holdout_comparison_maps.py"
MASK_MANIFEST = ROOT / "config/stage20_barrage_holdout_region_masks_v1.json"
MASK_BINARY = ROOT / "data/onga_stage20_barrage_holdout_region_masks_v1.bin"
MESH_MANIFEST = ROOT / "public/data/onga/stage20/mesh-v2.json"
MESH_BINARY = ROOT / "public/data/onga/stage20/mesh-v2.bin"
COORDINATE_MANIFEST = ROOT / "data/onga_unified_water_manifest_r3.json"
GSI_TILE_ROOT = ROOT / "data/external/gsi/seamlessphoto"

ANALYSIS_SCHEMA = "onga-stage20-barrage-holdout-recovery-postrun-analysis-v1"
MANIFEST_SCHEMA = "onga-stage20-barrage-holdout-comparison-map-manifest-v1"
MANIFEST_STATUS = "rendered_holdout_comparison_not_physical_validation"
REGION_IDS = ("estuary", "barrage", "confluence", "fishway")
MODEL_HOURS = (-12, -11, -10, -9, -8)
WORST_HOUR = -10
CELL_COUNT = 50199
PANEL_LABELS = (
    "直接計算（河口堰50%）",
    "端点50:50補間（全閉＋全開）",
    "速度差（補間−直接）",
)
DISCLAIMER = "補間整合性の比較／実測・予報精度の検証ではない"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_fields(path: Path, *, depth: np.ndarray, u: np.ndarray, v: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        waterDepthM=np.asarray(depth, dtype=np.float64),
        velocityUms=np.asarray(u, dtype=np.float64),
        velocityVms=np.asarray(v, dtype=np.float64),
    )


def write_depth_error(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, waterDepthErrorM=np.asarray(values, dtype=np.float64))


def file_record(kind: str, model_hour: int, path: Path) -> dict[str, Any]:
    return {
        "kind": kind,
        "modelHour": model_hour,
        "path": str(path),
        "byteLength": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def synthetic_fields() -> dict[str, dict[str, np.ndarray] | np.ndarray]:
    """Return smooth, finite, nontrivial deterministic fields."""

    manifest = json.loads(MESH_MANIFEST.read_text(encoding="utf-8"))
    payload = MESH_BINARY.read_bytes()
    vertex_descriptor = manifest["arrays"]["vertex_image_millipixel"]
    triangle_descriptor = manifest["arrays"]["triangles"]
    image_vertices = np.frombuffer(
        payload,
        dtype="<i4",
        count=math.prod(vertex_descriptor["shape"]),
        offset=vertex_descriptor["byteOffset"],
    ).reshape(vertex_descriptor["shape"]).astype(np.float64) * 0.001
    triangles = np.frombuffer(
        payload,
        dtype="<i4",
        count=math.prod(triangle_descriptor["shape"]),
        offset=triangle_descriptor["byteOffset"],
    ).reshape(triangle_descriptor["shape"]).astype(np.int64)
    centres = image_vertices[triangles].mean(axis=1)
    x = (centres[:, 0] - float(centres[:, 0].min())) / float(np.ptp(centres[:, 0]))
    y = (centres[:, 1] - float(centres[:, 1].min())) / float(np.ptp(centres[:, 1]))
    gaussian = np.exp(-(((x - 0.56) / 0.18) ** 2 + ((y - 0.56) / 0.24) ** 2))
    depth = 1.08 + 0.36 * (1.0 - y) + 0.07 * np.sin(2.0 * np.pi * x)
    direct_u = 0.070 + 0.046 * (1.0 - y) + 0.016 * np.sin(2.0 * np.pi * x)
    direct_v = 0.018 * np.cos(2.0 * np.pi * y) + 0.006 * np.sin(4.0 * np.pi * x)
    delta_depth = 0.004 * np.sin(3.0 * np.pi * x) + 0.014 * gaussian
    delta_u = 0.0018 + 0.0068 * gaussian + 0.0016 * np.sin(3.0 * np.pi * y)
    delta_v = -0.0012 + 0.0037 * gaussian * np.cos(2.0 * np.pi * x)
    interpolated_depth = depth + delta_depth
    interpolated_u = direct_u + delta_u
    interpolated_v = direct_v + delta_v
    direct = {
        "waterDepthM": depth.astype(np.float64),
        "velocityUms": direct_u.astype(np.float64),
        "velocityVms": direct_v.astype(np.float64),
    }
    interpolated = {
        "waterDepthM": interpolated_depth.astype(np.float64),
        "velocityUms": interpolated_u.astype(np.float64),
        "velocityVms": interpolated_v.astype(np.float64),
    }
    velocity_error = {
        "waterDepthM": direct["waterDepthM"].copy(),
        "velocityUms": (interpolated_u - direct_u).astype(np.float64),
        "velocityVms": (interpolated_v - direct_v).astype(np.float64),
    }
    return {
        "direct": direct,
        "interpolated": interpolated,
        "velocity_error": velocity_error,
        "depth_error": (interpolated_depth - depth).astype(np.float64),
    }


def metric_rows(mask_manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    counts = {view["id"]: int(view["cellCount"]) for view in mask_manifest["views"]}
    thresholds = {
        "velocityVectorRmseMPS": 0.01,
        "speedMaeMPS": 0.005,
        "p95DirectionErrorDeg": 5.0,
        "depthRmseM": 0.1,
        "maximumAbsoluteDepthErrorM": 0.25,
    }
    rows: list[dict[str, Any]] = []
    for hour_index, model_hour in enumerate(MODEL_HOURS):
        for region_index, region_id in enumerate(REGION_IDS):
            vector_rmse = 0.0040 + hour_index * 0.0003 + region_index * 0.0001
            if model_hour == WORST_HOUR and region_id == "barrage":
                vector_rmse = 0.0120
            values = {
                "velocityVectorRmseMPS": vector_rmse,
                "speedMaeMPS": 0.0030 + region_index * 0.0002,
                "p95DirectionErrorDeg": 2.1 + hour_index * 0.2 + region_index * 0.1,
                "depthRmseM": 0.018 + hour_index * 0.001,
                "maximumAbsoluteDepthErrorM": 0.045 + region_index * 0.002,
            }
            checks = {key: values[key] <= threshold for key, threshold in thresholds.items()}
            rows.append(
                {
                    "modelHour": model_hour,
                    "regionId": region_id,
                    "cellCount": counts[region_id],
                    **values,
                    "thresholdChecks": checks,
                    "passed": all(checks.values()),
                }
            )
    require(len(rows) == 20, "synthetic metric fixture does not contain 20 rows")
    return rows


def make_analysis(root: Path) -> tuple[Path, dict[str, Any], dict[str, Path], dict[str, dict[str, np.ndarray] | np.ndarray]]:
    fields = synthetic_fields()
    field_root = root / "fields/hour-m10h"
    direct_path = field_root / "direct-fields.npz"
    interpolated_path = field_root / "interpolated-fields.npz"
    velocity_error_path = field_root / "velocity-error-fields.npz"
    depth_error_path = field_root / "depth-error-fields.npz"
    direct = fields["direct"]
    interpolated = fields["interpolated"]
    velocity_error = fields["velocity_error"]
    require(isinstance(direct, dict), "internal direct fixture type error")
    require(isinstance(interpolated, dict), "internal interpolated fixture type error")
    require(isinstance(velocity_error, dict), "internal velocity-error fixture type error")
    write_fields(
        direct_path,
        depth=direct["waterDepthM"],
        u=direct["velocityUms"],
        v=direct["velocityVms"],
    )
    write_fields(
        interpolated_path,
        depth=interpolated["waterDepthM"],
        u=interpolated["velocityUms"],
        v=interpolated["velocityVms"],
    )
    write_fields(
        velocity_error_path,
        depth=velocity_error["waterDepthM"],
        u=velocity_error["velocityUms"],
        v=velocity_error["velocityVms"],
    )
    depth_error = fields["depth_error"]
    require(isinstance(depth_error, np.ndarray), "internal depth-error fixture type error")
    write_depth_error(depth_error_path, depth_error)

    mask_manifest = json.loads(MASK_MANIFEST.read_text(encoding="utf-8"))
    rows = metric_rows(mask_manifest)
    selection = {
        "metric": "velocityVectorRmseMPS",
        "modelHour": WORST_HOUR,
        "regionId": "barrage",
        "value": 0.012,
        "convention": "maximum_across_five_hours_and_four_regions",
    }
    records = [
        file_record("direct", WORST_HOUR, direct_path),
        file_record("interpolated", WORST_HOUR, interpolated_path),
        file_record("velocity_error", WORST_HOUR, velocity_error_path),
        file_record("depth_error", WORST_HOUR, depth_error_path),
    ]
    analysis: dict[str, Any] = {
        "schema": ANALYSIS_SCHEMA,
        "status": "evaluated_failed_thresholds",
        "fixture": {
            "synthetic": True,
            "purpose": "deterministic_renderer_validation_only",
        },
        "analysisMode": "offline_local_artifacts_only",
        "identity": {"expectedGithubRunId": 29511898671},
        "staticInputValidation": {
            "passed": True,
            "mesh": {
                "manifest": str(MESH_MANIFEST),
                "binary": str(MESH_BINARY),
                "cellCount": CELL_COUNT,
                "sha256": sha256_file(MESH_BINARY),
            },
            "regionalMasks": {
                "manifest": str(MASK_MANIFEST),
                "manifestSha256": sha256_file(MASK_MANIFEST),
                "binary": str(MASK_BINARY),
                "binarySha256": sha256_file(MASK_BINARY),
            },
        },
        "holdoutEvaluation": {
            "evaluable": True,
            "acceptanceResult": "failed",
            "expectedComparisonCount": 20,
            "evaluatedComparisonCount": 20,
            "passedComparisonCount": 19,
            "failedComparisonCount": 1,
            "thresholds": {
                "velocityVectorRmseMPS": 0.01,
                "speedMaeMPS": 0.005,
                "p95DirectionErrorDeg": 5.0,
                "depthRmseM": 0.1,
                "maximumAbsoluteDepthErrorM": 0.25,
            },
            "perHourRegion": rows,
            "worstMapSelection": selection,
        },
        "derivedArtifacts": {
            "createdThisInvocation": True,
            "selectionConvention": selection,
            "mapReadyWorstHourFields": records,
            "mapsRendered": False,
        },
        "diagnostics": [],
        "safeguards": {
            "solverInvoked": False,
            "networkAccessAttempted": False,
            "githubActionsMutationAttempted": False,
            "automaticRetryPerformed": False,
            "additionalPhysicalRunPerformed": False,
            "publicSimulatorConnected": False,
            "physicalValidationClaimAllowed": False,
            "dailyForecastClaimAllowed": False,
        },
    }
    analysis_path = root / "synthetic-analysis.json"
    write_json(analysis_path, analysis)
    paths = {
        "analysis": analysis_path,
        "direct": direct_path,
        "interpolated": interpolated_path,
        "velocity_error": velocity_error_path,
        "depth_error": depth_error_path,
    }
    return analysis_path, analysis, paths, fields


def renderer_command(
    analysis_path: Path,
    output_dir: Path,
    manifest_path: Path,
    html_path: Path,
) -> list[str]:
    return [
        sys.executable,
        str(RENDERER),
        "--repo-root",
        str(ROOT),
        "--analysis",
        str(analysis_path),
        "--output-dir",
        str(output_dir),
        "--manifest-output",
        str(manifest_path),
        "--html-output",
        str(html_path),
    ]


def run_renderer(
    analysis_path: Path,
    output_dir: Path,
    manifest_path: Path,
    html_path: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        renderer_command(analysis_path, output_dir, manifest_path, html_path),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def output_inventory(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def record_path(record: Mapping[str, Any], *, manifest_path: Path, output_root: Path) -> Path:
    raw = record.get("path")
    require(isinstance(raw, str) and raw, "output record is missing a path")
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    candidates = (
        ROOT / candidate,
        manifest_path.parent / candidate,
        output_root / candidate,
        output_root / "maps" / candidate,
    )
    for resolved in candidates:
        if resolved.is_file():
            return resolved
    return manifest_path.parent / candidate


def validate_file_record(record: Mapping[str, Any], path: Path, label: str) -> None:
    require(path.is_file(), f"{label} output is missing: {path}")
    require(path.stat().st_size == int(record["byteLength"]), f"{label} byte length mismatch")
    require(sha256_file(path) == record["sha256"], f"{label} digest mismatch")


def scale_record(scales: Mapping[str, Any], names: Iterable[str], label: str) -> Mapping[str, Any]:
    for name in names:
        record = scales.get(name)
        if isinstance(record, dict):
            return record
    raise RuntimeError(f"displayScales is missing {label}")


def scale_maximum(record: Mapping[str, Any], label: str) -> float:
    for key in ("maximumMPS", "maximum", "ceilingMPS", "maxMPS"):
        value = record.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    raise RuntimeError(f"{label} scale does not record its maximum in m/s")


def rounded_p95_ceiling(values: np.ndarray) -> float:
    nonzero = np.asarray(values, dtype=np.float64)[np.asarray(values, dtype=np.float64) > 0.0]
    require(nonzero.size > 0, "synthetic scale population is empty")
    return max(0.01, math.ceil(float(np.percentile(nonzero, 95.0)) * 100.0) / 100.0)


def require_scale_metadata(record: Mapping[str, Any], expected_terms: Iterable[str], label: str) -> None:
    require(record.get("unit", record.get("units")) == "m/s", f"{label} scale unit is not m/s")
    percentile = record.get("percentile", record.get("percentileBasis"))
    require(percentile in (95, 95.0, "p95", "95th_nonzero"), f"{label} scale p95 convention is missing")
    applies = json.dumps(record.get("appliesTo", ""), ensure_ascii=False).lower()
    for term in expected_terms:
        require(term.lower() in applies, f"{label} scale does not declare that it applies to {term}")


def reject_remote_or_script(text: str, label: str) -> None:
    require(re.search(r"https?://", text, flags=re.IGNORECASE) is None, f"{label} contains a remote URL")
    require(re.search(r"<\s*script\b", text, flags=re.IGNORECASE) is None, f"{label} contains script")
    require(
        re.search(r"(?:href|src)\s*=\s*['\"]//", text, flags=re.IGNORECASE) is None,
        f"{label} contains a protocol-relative external reference",
    )


def validate_rendered_outputs(
    output_root: Path,
    output_dir: Path,
    manifest_path: Path,
    html_path: Path,
    analysis_path: Path,
    fields: Mapping[str, dict[str, np.ndarray] | np.ndarray],
) -> dict[str, Any]:
    require(manifest_path.is_file(), "renderer did not write the comparison-map manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == MANIFEST_SCHEMA, "comparison-map manifest schema changed")
    require(manifest.get("status") == MANIFEST_STATUS, "comparison-map manifest status changed")
    require(manifest.get("modelHour") == WORST_HOUR, "manifest does not identify the selected worst hour")

    views = manifest.get("views")
    require(isinstance(views, list) and len(views) == 4, "manifest must contain exactly four regional views")
    require([view.get("id") for view in views] == list(REGION_IDS), "regional view order or identity changed")
    mask_manifest = json.loads(MASK_MANIFEST.read_text(encoding="utf-8"))
    expected_counts = {view["id"]: int(view["cellCount"]) for view in mask_manifest["views"]}
    svg_paths: list[Path] = []
    combined_svg = ""
    for view in views:
        path = record_path(view, manifest_path=manifest_path, output_root=output_root)
        validate_file_record(view, path, f"{view['id']} SVG")
        require(path.suffix.lower() == ".svg", f"{view['id']} output is not SVG")
        require(int(view["cellCount"]) == expected_counts[view["id"]], f"{view['id']} rendered cell count changed")
        text = path.read_text(encoding="utf-8")
        reject_remote_or_script(text, f"{view['id']} SVG")
        root = ET.fromstring(text)
        require(root.tag.endswith("svg"), f"{view['id']} XML root is not SVG")
        require(root.attrib.get("role") == "img", f"{view['id']} SVG is missing role=img")
        child_names = {child.tag.rsplit("}", 1)[-1] for child in root}
        require("title" in child_names and "desc" in child_names, f"{view['id']} SVG needs title and desc")
        for panel_label in PANEL_LABELS:
            require(text.count(panel_label) == 1, f"{view['id']} does not contain exactly one {panel_label} panel")
        require("河口堰位置" in text, f"{view['id']} does not use the generic barrage marker")
        require("河口堰（全開）" not in text, f"{view['id']} incorrectly labels the barrage as fully open")
        svg_paths.append(path)
        combined_svg += text
    require(len(svg_paths) == 4, "renderer did not create exactly four SVGs")
    actual_svgs = sorted(path.resolve() for path in output_dir.rglob("*.svg"))
    require(actual_svgs == sorted(path.resolve() for path in svg_paths), "SVG output inventory is not exactly the four declared views")
    require(sum(combined_svg.count(label) for label in PANEL_LABELS) == 12, "the four views do not contain exactly 12 panels")
    require(DISCLAIMER in combined_svg or DISCLAIMER in html_path.read_text(encoding="utf-8"), "comparison disclaimer is missing")

    overview_record = manifest.get("overview")
    require(isinstance(overview_record, dict), "manifest overview record is missing")
    overview_path = record_path(overview_record, manifest_path=manifest_path, output_root=output_root)
    validate_file_record(overview_record, overview_path, "comparison overview")
    require(overview_path.name == "comparison-overview.jpg", "overview filename changed")
    with Image.open(overview_path) as image:
        require(image.format == "JPEG", "comparison overview is not a JPEG")
        require(image.width > 0 and image.height > 0, "comparison overview has invalid dimensions")
        image.verify()

    require(html_path.is_file(), "renderer did not write the visualization fragment")
    html_record = manifest.get("html")
    require(isinstance(html_record, dict), "manifest HTML record is missing")
    validate_file_record(html_record, html_path, "visualization fragment")
    html = html_path.read_text(encoding="utf-8")
    reject_remote_or_script(html, "visualization fragment")
    require(re.search(r"<\s*(?:html|head|body)\b", html, flags=re.IGNORECASE) is None, "visualization output is not an HTML fragment")
    require("data:image/jpeg;base64," in html, "visualization fragment does not embed its overview image")
    require(DISCLAIMER in html, "visualization fragment is missing the comparison disclaimer")

    scales = manifest.get("displayScales")
    require(isinstance(scales, dict), "manifest displayScales record is missing")
    shared = scale_record(
        scales,
        ("sharedDirectInterpolatedSpeedMPS", "sharedDirectAndInterpolatedSpeedMPS"),
        "shared direct/interpolated speed scale",
    )
    error = scale_record(scales, ("velocityErrorMPS", "velocityErrorSpeedMPS"), "velocity-error scale")
    direct = fields["direct"]
    interpolated = fields["interpolated"]
    velocity_error = fields["velocity_error"]
    require(isinstance(direct, dict) and isinstance(interpolated, dict), "internal scale fixture type error")
    require(isinstance(velocity_error, dict), "internal error-scale fixture type error")
    direct_speed = np.hypot(direct["velocityUms"], direct["velocityVms"])
    interpolated_speed = np.hypot(interpolated["velocityUms"], interpolated["velocityVms"])
    expected_shared = max(rounded_p95_ceiling(direct_speed), rounded_p95_ceiling(interpolated_speed))
    error_speed = np.hypot(velocity_error["velocityUms"], velocity_error["velocityVms"])
    expected_error = rounded_p95_ceiling(error_speed)
    require(math.isclose(scale_maximum(shared, "shared speed"), expected_shared, abs_tol=1e-12), "shared speed scale ceiling changed")
    require(math.isclose(scale_maximum(error, "velocity error"), expected_error, abs_tol=1e-12), "velocity-error scale ceiling changed")
    require_scale_metadata(shared, ("direct", "interpolated"), "shared speed")
    require_scale_metadata(error, ("velocity_error",), "velocity error")

    safeguards = manifest.get("safeguards")
    require(isinstance(safeguards, dict), "manifest safeguards are missing")
    for key in ("solverInvoked", "networkAccessAttempted", "physicalValidationClaimAllowed"):
        require(safeguards.get(key) is False, f"manifest safeguard {key} must be false")

    source = manifest.get("sourceAnalysis", manifest.get("analysis"))
    require(isinstance(source, dict), "manifest source-analysis record is missing")
    require(source.get("schema", ANALYSIS_SCHEMA) == ANALYSIS_SCHEMA, "source analysis schema was not retained")
    require(source.get("status") == "evaluated_failed_thresholds", "threshold-failed but evaluable status was not retained")
    require(source.get("sha256") == sha256_file(analysis_path), "source analysis digest was not retained")
    declared_source_path = record_path(source, manifest_path=manifest_path, output_root=output_root)
    require(declared_source_path.resolve() == analysis_path.resolve(), "manifest identifies the wrong source analysis")
    return {
        "viewCount": len(views),
        "panelCount": 12,
        "sharedSpeedMaximumMPS": expected_shared,
        "velocityErrorMaximumMPS": expected_error,
        "overviewByteLength": overview_path.stat().st_size,
        "fragmentByteLength": html_path.stat().st_size,
    }


def assert_renderer_boundary() -> None:
    require(RENDERER.is_file(), f"renderer is missing: {RENDERER}")
    source = RENDERER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(RENDERER))
    forbidden_imports = {"aiohttp", "httpx", "requests", "socket", "subprocess", "urllib"}
    forbidden_module_terms = ("solver", "run_stage20", "hybrid_physical")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        for module in modules:
            root = module.split(".", 1)[0]
            require(root not in forbidden_imports, f"renderer imports forbidden network/process module {module}")
            require(not any(term in module.lower() for term in forbidden_module_terms), f"renderer imports solver-adjacent module {module}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                call_name = node.func.attr.lower()
            elif isinstance(node.func, ast.Name):
                call_name = node.func.id.lower()
            else:
                call_name = ""
            require(call_name not in {"system", "popen", "urlopen", "request", "geturl"}, f"renderer contains forbidden call {call_name}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            require("http://" not in node.value.lower() and "https://" not in node.value.lower(), "renderer embeds a remote URL")


def expect_rejected(
    root: Path,
    label: str,
    analysis: Mapping[str, Any],
) -> None:
    case_root = root / f"negative-{label}"
    analysis_path = case_root / "analysis.json"
    output_dir = case_root / "maps"
    manifest_path = case_root / "manifest.json"
    html_path = case_root / "preview.html"
    write_json(analysis_path, analysis)
    result = run_renderer(analysis_path, output_dir, manifest_path, html_path)
    require(result.returncode == 2, f"{label}: invalid analysis returned {result.returncode}, expected 2; stderr={result.stderr.strip()}")
    require(not manifest_path.exists(), f"{label}: invalid input produced a manifest")
    require(not html_path.exists(), f"{label}: invalid input produced an HTML fragment")
    require(not output_dir.exists() or not any(output_dir.rglob("*")), f"{label}: invalid input produced map outputs")


def test_negative_cases(root: Path, analysis: Mapping[str, Any], paths: Mapping[str, Path]) -> list[str]:
    not_evaluable = copy.deepcopy(analysis)
    not_evaluable["status"] = "not_evaluable_invalid_or_incomplete_evidence"
    not_evaluable["holdoutEvaluation"]["evaluable"] = False
    not_evaluable["holdoutEvaluation"]["acceptanceResult"] = "not_evaluable_not_failed"
    expect_rejected(root, "not-evaluable", not_evaluable)

    bad_digest = copy.deepcopy(analysis)
    bad_digest["derivedArtifacts"]["mapReadyWorstHourFields"][0]["sha256"] = "0" * 64
    expect_rejected(root, "source-digest", bad_digest)

    bad_error_path = root / "bad-error-fields.npz"
    with np.load(paths["velocity_error"], allow_pickle=False) as archive:
        write_fields(
            bad_error_path,
            depth=archive["waterDepthM"],
            u=archive["velocityUms"] + 0.02,
            v=archive["velocityVms"],
        )
    bad_algebra = copy.deepcopy(analysis)
    records = bad_algebra["derivedArtifacts"]["mapReadyWorstHourFields"]
    error_index = next(index for index, record in enumerate(records) if record["kind"] == "velocity_error")
    records[error_index] = file_record("velocity_error", WORST_HOUR, bad_error_path)
    expect_rejected(root, "error-algebra", bad_algebra)
    return ["not_evaluable", "source_digest_mismatch", "velocity_error_algebra_mismatch"]


def test_evaluated_pass_case(root: Path, analysis: Mapping[str, Any]) -> str:
    passed = copy.deepcopy(analysis)
    passed["status"] = "evaluated_passed_thresholds"
    evaluation = passed["holdoutEvaluation"]
    evaluation["acceptanceResult"] = "passed"
    evaluation["thresholds"]["velocityVectorRmseMPS"] = 0.02
    thresholds = evaluation["thresholds"]
    for row in evaluation["perHourRegion"]:
        checks = {
            key: float(row[key]) <= float(limit)
            for key, limit in thresholds.items()
        }
        row["thresholdChecks"] = checks
        row["passed"] = all(checks.values())
    evaluation["passedComparisonCount"] = 20
    evaluation["failedComparisonCount"] = 0
    case_root = root / "positive-evaluated-pass"
    analysis_path = case_root / "analysis.json"
    output_dir = case_root / "maps"
    manifest_path = case_root / "manifest.json"
    html_path = case_root / "preview.html"
    write_json(analysis_path, passed)
    result = run_renderer(analysis_path, output_dir, manifest_path, html_path)
    require(result.returncode == 0, f"evaluated-pass analysis was rejected: {result.stderr.strip()}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("analysisAcceptanceStatus") == "evaluated_passed_thresholds", "evaluated-pass status was not retained")
    require(manifest.get("sourceAnalysis", {}).get("status") == "evaluated_passed_thresholds", "evaluated-pass source status was not retained")
    require(len(manifest.get("views", [])) == 4 and html_path.is_file(), "evaluated-pass rendering is incomplete")
    return "evaluated_passed_thresholds"


def main() -> int:
    assert_renderer_boundary()
    static_sources = [
        MASK_MANIFEST,
        MASK_BINARY,
        MESH_MANIFEST,
        MESH_BINARY,
        COORDINATE_MANIFEST,
        RENDERER,
        *sorted(GSI_TILE_ROOT.rglob("*.jpg")),
    ]
    before_static = {str(path): sha256_file(path) for path in static_sources}
    with tempfile.TemporaryDirectory(prefix="stage20-barrage-comparison-map-validator-") as temporary:
        root = Path(temporary)
        analysis_path, analysis, source_paths, fields = make_analysis(root)
        source_hashes_before = {name: sha256_file(path) for name, path in source_paths.items()}
        output_root = root / "rendered"
        output_dir = output_root / "maps"
        manifest_path = output_root / "comparison-map-manifest.json"
        html_path = output_root / "comparison-preview.html"

        first = run_renderer(analysis_path, output_dir, manifest_path, html_path)
        require(first.returncode == 0, f"first renderer invocation failed ({first.returncode}): {first.stderr.strip()}")
        first_inventory = output_inventory(output_root)
        require(first_inventory, "first renderer invocation produced no files")
        checks = validate_rendered_outputs(output_root, output_dir, manifest_path, html_path, analysis_path, fields)

        second = run_renderer(analysis_path, output_dir, manifest_path, html_path)
        require(second.returncode == 0, f"second renderer invocation failed ({second.returncode}): {second.stderr.strip()}")
        second_inventory = output_inventory(output_root)
        require(first_inventory.keys() == second_inventory.keys(), "renderer output inventory changed on rerender")
        for relative_path in first_inventory:
            require(
                first_inventory[relative_path] == second_inventory[relative_path],
                f"renderer output is not byte deterministic: {relative_path}",
            )

        source_hashes_after = {name: sha256_file(path) for name, path in source_paths.items()}
        require(source_hashes_before == source_hashes_after, "renderer mutated a synthetic source input")
        positive_case = test_evaluated_pass_case(root, analysis)
        negative_cases = test_negative_cases(root, analysis, source_paths)

    after_static = {str(path): sha256_file(path) for path in static_sources}
    require(before_static == after_static, "validator or renderer mutated a repository source input")
    print(
        json.dumps(
            {
                "status": "passed",
                "renderer": str(RENDERER.relative_to(ROOT)),
                "cellCount": CELL_COUNT,
                **checks,
                "deterministicRerender": True,
                "sourceHashesPreserved": True,
                "positiveCase": positive_case,
                "negativeCases": negative_cases,
                "solverInvoked": False,
                "networkAccessAttempted": False,
                "physicalValidationClaimAllowed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
