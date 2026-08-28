#!/usr/bin/env python3
"""Serve the Stage 20 GUI and bounded local R1C physics jobs on loopback."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from stage20_parallel_forcing_integration_v1 import (
    IntegrationError,
    build_from_client_request,
    capability_document as forcing_capability_document,
)


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable).resolve()
RUNNER = ROOT / "tools/run_stage20_local_R1C_simulation_v1.py"
JOBS_ROOT = ROOT / ".stage20-local-only/stage20-local-simulator-jobs"
LEGACY_JOBS_ROOT = ROOT / "docs/results/stage20-local-simulator-jobs"
RUNTIME_CAPABILITIES = ROOT / "config/stage20_runtime_capabilities_v2.json"
RUNTIME_BASELINE = ROOT / "config/stage20_runtime_baseline_v2.json"
RUNTIME_ASSET_REGISTRY = ROOT / "config/stage20_runtime_assets_v2.json"
CAPABILITY_SCHEMA = "onga-stage20-local-simulator-capabilities-v1"
JOB_SCHEMA = "onga-stage20-local-simulator-job-v1"
REQUEST_SCHEMA = "onga-stage20-local-R1C-simulation-request-v1"
ALLOWED_DURATIONS = {
    5: 1,
    30: 5,
    60: 5,
    120: 10,
    300: 10,
}
MAX_REQUEST_BYTES = 16 * 1024
MAX_FORCING_REQUEST_BYTES = 6 * 1024 * 1024
SAFE_JOB_ID = re.compile(r"^local-[0-9]{8}T[0-9]{6}-[0-9a-f]{12}$")
SAFE_JOB_ARTIFACTS = {
    "browser-manifest.json": "application/json; charset=utf-8",
    "replay-fields.bin": "application/octet-stream",
    "result.json": "application/json; charset=utf-8",
}
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
CSRF_HEADER_NAME = "X-Stage20-CSRF-Token"
CSRF_TOKEN = secrets.token_urlsafe(32)
EXPECTED_DYNAMIC_STATIC_PATH_COUNT = 31
LOCAL_RUNTIME_REQUIRED_ASSET_IDS = (
    "r1c_review_mesh",
    "r1c_initial_checkpoint",
    "r1c_diagnostic_replay_binary",
    "fishway_constant_weak_flow_coupling_candidate",
    "r1c_review_mesh_summary",
    "fishway_c2_storage_candidate",
    "physical_pilot_source_contract",
    "physical_pilot_source_mesh_manifest",
    "synthetic_mesh_binary",
    "onga_water_mask_manifest_r3",
    "onga_water_mask_rows_r3_0",
    "onga_water_mask_rows_r3_1",
    "onga_water_mask_rows_r3_2",
    "onga_water_mask_rows_r3_3",
    "physical_pilot_final_fields",
    "stage19_m_boundary_tide_candidate",
    "physical_pilot_report",
)
EXPECTED_BROWSER_ENTRYPOINTS = frozenset(
    {
        "onga_stage20_gui.mjs",
        "onga_stage20_hybrid_worker.mjs",
    }
)
STATIC_MEDIA_TYPES = {
    ".bin": "application/octet-stream",
    ".css": "text/css; charset=utf-8",
    ".geojson": "application/geo+json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".jpg": "image/jpeg",
    ".json": "application/json; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".npz": "application/octet-stream",
    ".zip": "application/zip",
}
FORBIDDEN_STATIC_PREFIXES = (
    ".agents/",
    ".build/",
    ".codex/",
    ".git/",
    ".github/",
    ".pnpm-store/",
    ".stage20-local-only/",
    ".venv-stage20/",
    "tests/",
    "tools/",
)
JS_IMPORT = re.compile(
    r"(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)['\"](\.[^'\"]+)['\"]",
    re.DOTALL,
)
ROOT_BROWSER_MODULE = re.compile(r"^onga_stage20_[A-Za-z0-9_]+\.mjs$")
GSI_TILE = re.compile(
    r"^data/external/gsi/seamlessphoto/z(0|[1-9][0-9]?)/"
    r"(0|[1-9][0-9]{0,7})-(0|[1-9][0-9]{0,7})\.jpg$"
)


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def loopback_authority(value: str | None, expected_port: int) -> tuple[str, int] | None:
    if not isinstance(value, str) or not value or value.strip() != value:
        return None
    if any(character in value for character in ("/", "\\", "@", "#", "?", ",")):
        return None
    try:
        parsed = urlparse(f"//{value}")
        hostname = parsed.hostname.lower() if parsed.hostname else None
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        return None
    if (
        parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or hostname not in LOOPBACK_HOSTS
        or port != expected_port
    ):
        return None
    return hostname, port


def same_origin(
    origin: str | None,
    authority: tuple[str, int],
) -> bool:
    if not isinstance(origin, str) or not origin or origin.strip() != origin:
        return False
    try:
        parsed = urlparse(origin)
        hostname = parsed.hostname.lower() if parsed.hostname else None
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and hostname == authority[0]
        and port == authority[1]
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
        and parsed.username is None
        and parsed.password is None
    )


def post_header_failure(
    headers: Any,
    server_port: int,
) -> tuple[HTTPStatus, str] | None:
    authority = loopback_authority(headers.get("Host"), server_port)
    if authority is None:
        return HTTPStatus.FORBIDDEN, "loopback Host is required"
    if not same_origin(headers.get("Origin"), authority):
        return HTTPStatus.FORBIDDEN, "same-origin Origin is required"
    media_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json"
    supplied_token = headers.get(CSRF_HEADER_NAME)
    if not isinstance(supplied_token, str) or not hmac.compare_digest(
        supplied_token,
        CSRF_TOKEN,
    ):
        return HTTPStatus.FORBIDDEN, "CSRF token is missing or invalid"
    return None


def csrf_capability_fields() -> dict[str, Any]:
    return {
        "csrfToken": CSRF_TOKEN,
        "csrfHeaderName": CSRF_HEADER_NAME,
        "requestSecurity": {
            "loopbackHostRequired": True,
            "sameOriginRequired": True,
            "applicationJsonRequired": True,
            "perProcessCsrfToken": True,
        },
    }


def canonical_request_path(target: str) -> str | None:
    """Return one unambiguous ASCII request path, or reject the target."""

    if not isinstance(target, str) or not target or "%" in target or "\\" in target:
        return None
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in target):
        return None
    parsed = urlparse(target)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.params
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
    ):
        return None
    if parsed.path == "/":
        return "/"
    components = parsed.path[1:].split("/")
    if any(
        not component
        or component in {".", ".."}
        or component.startswith(".")
        for component in components
    ):
        return None
    if "/" + "/".join(components) != parsed.path:
        return None
    return parsed.path


def canonical_policy_path(
    value: Any,
    *,
    active_source: bool = False,
    allow_checkpoint: bool = False,
) -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise RuntimeError(f"runtime static path is invalid: {value!r}")
    if "%" in value or "\\" in value:
        raise RuntimeError(f"runtime static path is ambiguous: {value}")
    pure = PurePosixPath(value)
    components = pure.parts
    if (
        not components
        or pure.as_posix() != value
        or any(
            component in {".", ".."}
            or component.startswith(".")
            or not component
            for component in components
        )
    ):
        raise RuntimeError(f"runtime static path is non-canonical: {value}")
    if value.startswith(FORBIDDEN_STATIC_PREFIXES):
        raise RuntimeError(f"forbidden runtime static prefix: {value}")
    if not allow_checkpoint and any(
        "checkpoint" in component.casefold() for component in components
    ):
        raise RuntimeError(f"checkpoint path cannot be browser-served: {value}")
    suffix = pure.suffix.casefold()
    if suffix not in STATIC_MEDIA_TYPES:
        raise RuntimeError(f"unsupported runtime static media type: {value}")
    if not active_source and suffix in {".html", ".js", ".mjs", ".py"}:
        raise RuntimeError(f"active runtime source requires import review: {value}")
    return value


def secure_regular_file(
    root: Path,
    relative_path: str,
    *,
    allow_checkpoint: bool = False,
) -> Path | None:
    """Resolve a regular file without following a symlink in any component."""

    try:
        normalized = canonical_policy_path(
            relative_path,
            active_source=Path(relative_path).suffix.casefold()
            in {".html", ".js", ".mjs"},
            allow_checkpoint=allow_checkpoint,
        )
        root_resolved = root.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    candidate = root_resolved
    components = PurePosixPath(normalized).parts
    try:
        for index, component in enumerate(components):
            candidate = candidate / component
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                return None
            if index < len(components) - 1:
                if not stat.S_ISDIR(metadata.st_mode):
                    return None
            elif not stat.S_ISREG(metadata.st_mode):
                return None
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if resolved == root_resolved or root_resolved not in resolved.parents:
        return None
    return resolved


def read_policy_json(root: Path, relative_path: str) -> dict[str, Any]:
    path = secure_regular_file(root, relative_path)
    if path is None:
        raise RuntimeError(f"runtime policy document is unavailable: {relative_path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"runtime policy document must be an object: {relative_path}")
    return value


def browser_import_closure(
    root: Path,
    entrypoints: list[Any],
) -> frozenset[str]:
    if frozenset(entrypoints) != EXPECTED_BROWSER_ENTRYPOINTS or len(entrypoints) != 2:
        raise RuntimeError("browser entrypoint authority changed")
    queue = list(EXPECTED_BROWSER_ENTRYPOINTS)
    seen: set[str] = set()
    while queue:
        relative = canonical_policy_path(queue.pop(), active_source=True)
        if not ROOT_BROWSER_MODULE.fullmatch(relative):
            raise RuntimeError(f"browser module left reviewed root namespace: {relative}")
        source = secure_regular_file(root, relative)
        if source is None:
            raise RuntimeError(f"browser module is unavailable: {relative}")
        if relative in seen:
            continue
        seen.add(relative)
        for specifier in JS_IMPORT.findall(source.read_text(encoding="utf-8")):
            if (
                not specifier.startswith("./")
                or "%" in specifier
                or "\\" in specifier
                or "?" in specifier
                or "#" in specifier
            ):
                raise RuntimeError(
                    f"browser import is not a reviewed relative path: {relative} -> {specifier}"
                )
            imported = PurePosixPath(specifier[2:]).as_posix()
            imported = canonical_policy_path(imported, active_source=True)
            if not ROOT_BROWSER_MODULE.fullmatch(imported):
                raise RuntimeError(
                    f"browser import left reviewed root namespace: {relative} -> {specifier}"
                )
            queue.append(imported)
    return frozenset(seen)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def optional_asset_identity_matches(path: Path, asset: dict[str, Any]) -> bool:
    byte_length = asset.get("byteLength")
    expected_sha256 = asset.get("sha256")
    return (
        isinstance(byte_length, int)
        and byte_length >= 0
        and isinstance(expected_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None
        and path.stat().st_size == byte_length
        and hmac.compare_digest(sha256(path), expected_sha256)
    )


def local_runtime_asset_readiness(root: Path = ROOT) -> dict[str, Any]:
    """Evaluate the server-side assets required before a local job may exist."""

    capabilities = read_policy_json(
        root,
        "config/stage20_runtime_capabilities_v2.json",
    )
    registry = read_policy_json(root, "config/stage20_runtime_assets_v2.json")
    if (
        capabilities.get("schema") != "onga-stage20-runtime-capabilities-v2"
        or registry.get("schema") != "onga-stage20-runtime-assets-v2"
    ):
        raise RuntimeError("local runtime asset authority changed")
    modes = capabilities.get("modes")
    assets = registry.get("assets")
    if not isinstance(modes, list) or not isinstance(assets, list):
        raise RuntimeError("local runtime asset authority is incomplete")
    local = next(
        (
            mode
            for mode in modes
            if isinstance(mode, dict) and mode.get("id") == "local_r1c_experiment"
        ),
        None,
    )
    if not isinstance(local, dict) or not isinstance(local.get("requiredAssets"), list):
        raise RuntimeError("local runtime required assets are missing")
    asset_by_id = {
        asset.get("id"): asset
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("id"), str)
    }
    if len(asset_by_id) != len(assets):
        raise RuntimeError("local runtime asset registry contains duplicate ids")
    missing: list[str] = []
    invalid: list[str] = []
    required_ids = local["requiredAssets"]
    if len(required_ids) != len(set(required_ids)):
        raise RuntimeError("local runtime required asset ids are duplicated")
    if required_ids != list(LOCAL_RUNTIME_REQUIRED_ASSET_IDS):
        raise RuntimeError("local runtime dependency closure changed")
    for asset_id in required_ids:
        asset = asset_by_id.get(asset_id)
        if (
            not isinstance(asset, dict)
            or "local_r1c_experiment" not in asset.get("requiredByModes", [])
        ):
            invalid.append(str(asset_id))
            continue
        try:
            relative = canonical_policy_path(
                asset.get("path"),
                allow_checkpoint=True,
            )
        except RuntimeError:
            invalid.append(str(asset_id))
            continue
        path = secure_regular_file(
            root,
            relative,
            allow_checkpoint=True,
        )
        if path is None:
            missing.append(str(asset_id))
        elif not optional_asset_identity_matches(path, asset):
            invalid.append(str(asset_id))
    return {
        "ready": not missing and not invalid,
        "requiredAssetIds": list(required_ids),
        "missingAssetIds": sorted(missing),
        "invalidAssetIds": sorted(invalid),
        "evaluatedAtProcessStart": True,
    }


def build_runtime_static_policy(
    root: Path = ROOT,
) -> tuple[frozenset[str], frozenset[str]]:
    baseline = read_policy_json(root, "config/stage20_runtime_baseline_v2.json")
    assets = read_policy_json(root, "config/stage20_runtime_assets_v2.json")
    if baseline.get("schema") != "onga-stage20-runtime-baseline-v2":
        raise RuntimeError("runtime baseline identity changed")
    if assets.get("schema") != "onga-stage20-runtime-assets-v2":
        raise RuntimeError("runtime asset registry identity changed")

    import_config = baseline.get("importClosure")
    if not isinstance(import_config, dict):
        raise RuntimeError("browser import closure policy is missing")
    entrypoints = import_config.get("javascriptEntrypoints")
    if not isinstance(entrypoints, list):
        raise RuntimeError("browser import entrypoints are missing")
    allowed: set[str] = {
        canonical_policy_path("stage20-hybrid-gui.html", active_source=True),
        canonical_policy_path("stage20-hybrid-gui.css", active_source=True),
    }
    allowed.update(browser_import_closure(root, entrypoints))

    dynamic = baseline.get("dynamicBrowserRuntime")
    if not isinstance(dynamic, dict):
        raise RuntimeError("dynamic browser runtime policy is missing")
    if dynamic.get("expectedRequiredTrackedPathCount") != EXPECTED_DYNAMIC_STATIC_PATH_COUNT:
        raise RuntimeError("dynamic browser runtime count authority changed")
    groups = dynamic.get("requiredTrackedGroups")
    if not isinstance(groups, list) or not groups:
        raise RuntimeError("dynamic browser runtime groups are missing")
    dynamic_paths: set[str] = set()
    for group in groups:
        paths = group.get("paths") if isinstance(group, dict) else None
        if not isinstance(paths, list) or not paths:
            raise RuntimeError("dynamic browser runtime group is invalid")
        for raw_path in paths:
            relative = canonical_policy_path(raw_path)
            if relative in dynamic_paths:
                raise RuntimeError(f"duplicate dynamic browser runtime path: {relative}")
            if secure_regular_file(root, relative) is None:
                raise RuntimeError(f"required browser runtime file is unavailable: {relative}")
            dynamic_paths.add(relative)
    if len(dynamic_paths) != EXPECTED_DYNAMIC_STATIC_PATH_COUNT:
        raise RuntimeError(
            "dynamic browser runtime path count is not the reviewed 31-file baseline"
        )
    allowed.update(dynamic_paths)

    registry_assets = assets.get("assets")
    if not isinstance(registry_assets, list):
        raise RuntimeError("runtime asset entries are missing")
    asset_by_id = {
        asset.get("id"): asset
        for asset in registry_assets
        if isinstance(asset, dict) and isinstance(asset.get("id"), str)
    }
    optional_asset_ids = dynamic.get("optionalExternalAssetIds")
    if not isinstance(optional_asset_ids, list) or len(optional_asset_ids) != len(
        set(optional_asset_ids)
    ):
        raise RuntimeError("optional browser asset authority is invalid")
    for asset_id in optional_asset_ids:
        asset = asset_by_id.get(asset_id)
        if not isinstance(asset, dict):
            raise RuntimeError(f"unknown optional browser asset: {asset_id}")
        if asset.get("trackingPolicy") != "must_not_be_added_to_normal_git":
            raise RuntimeError(f"optional browser asset policy changed: {asset_id}")
        relative = canonical_policy_path(asset.get("path"))
        path = secure_regular_file(root, relative)
        if path is not None and optional_asset_identity_matches(path, asset):
            allowed.add(relative)

    collections = assets.get("optionalRuntimeCollections")
    if not isinstance(collections, list):
        raise RuntimeError("optional runtime collections are missing")
    collection_by_id = {
        collection.get("id"): collection
        for collection in collections
        if isinstance(collection, dict) and isinstance(collection.get("id"), str)
    }
    collection_ids = dynamic.get("optionalRuntimeCollectionIds")
    if not isinstance(collection_ids, list) or len(collection_ids) != len(
        set(collection_ids)
    ):
        raise RuntimeError("optional runtime collection authority is invalid")
    gsi_prefixes: set[str] = set()
    for collection_id in collection_ids:
        collection = collection_by_id.get(collection_id)
        if not isinstance(collection, dict):
            raise RuntimeError(f"unknown optional runtime collection: {collection_id}")
        if (
            collection_id != "gsi_seamlessphoto_tile_cache"
            or collection.get("pathPrefix") != "data/external/gsi/seamlessphoto/"
            or collection.get("filePattern") != "z{zoom}/{x}-{y}.jpg"
            or collection.get("networkFetchAllowed") is not False
        ):
            raise RuntimeError("GSI tile collection authority changed")
        gsi_prefixes.add(collection["pathPrefix"])
    return frozenset(allowed), frozenset(gsi_prefixes)


def is_allowed_gsi_tile(relative_path: str, prefixes: frozenset[str]) -> bool:
    if "data/external/gsi/seamlessphoto/" not in prefixes:
        return False
    match = GSI_TILE.fullmatch(relative_path)
    if match is None:
        return False
    zoom, x, y = (int(value) for value in match.groups())
    return zoom <= 24 and x < 2**zoom and y < 2**zoom


def resolve_runtime_static_path(
    request_path: str,
    *,
    root: Path = ROOT,
    allowlist: frozenset[str] | None = None,
    gsi_prefixes: frozenset[str] | None = None,
) -> Path | None:
    canonical = canonical_request_path(request_path)
    if canonical is None or canonical == "/":
        return None
    relative = canonical[1:]
    exact = RUNTIME_STATIC_ALLOWLIST if allowlist is None else allowlist
    prefixes = GSI_TILE_PREFIXES if gsi_prefixes is None else gsi_prefixes
    if relative not in exact and not is_allowed_gsi_tile(relative, prefixes):
        return None
    return secure_regular_file(root, relative)


RUNTIME_STATIC_ALLOWLIST, GSI_TILE_PREFIXES = build_runtime_static_policy()
LOCAL_RUNTIME_ASSET_READINESS = local_runtime_asset_readiness()


def local_runtime_capability() -> dict[str, Any]:
    contract = read_json(RUNTIME_CAPABILITIES)
    if (
        contract.get("schema") != "onga-stage20-runtime-capabilities-v2"
        or contract.get("version") != 2
        or contract.get("status") != "M0_CANDIDATE_NOT_PUBLIC_RUNTIME_AUTHORITY"
    ):
        raise RuntimeError("runtime capability contract identity changed")
    modes = contract.get("modes")
    if not isinstance(modes, list):
        raise RuntimeError("runtime capability modes are missing")
    local = next(
        (mode for mode in modes if mode.get("id") == "local_r1c_experiment"),
        None,
    )
    if not isinstance(local, dict):
        raise RuntimeError("local R1C capability is missing")
    expected = {
        "executionKind": "local_bounded_solver_explicit_only",
        "gateEffect": "explicit_run_updates_local_solver",
        "riverTideBoundaryPhysics": "unconnected_fixed_local_conditions",
        "fishwayRepresentation": "local_uncalibrated_lumped_C2_1",
        "calibrated": False,
        "fieldPrediction": False,
        "catchProbability": False,
        "operationalFishingAdvice": False,
        "safetyAuthority": False,
        "publicRuntime": False,
    }
    if any(local.get(key) != value for key, value in expected.items()):
        raise RuntimeError("local R1C capability boundary changed")
    return local


def job_output_dir(job_id: str) -> Path:
    current = JOBS_ROOT / job_id
    if (current / "server-status.json").is_file():
        return current
    legacy = LEGACY_JOBS_ROOT / job_id
    if (legacy / "server-status.json").is_file():
        return legacy
    return current


def public_job_status(job_id: str) -> dict[str, Any]:
    output_dir = job_output_dir(job_id)
    server_status_path = output_dir / "server-status.json"
    if not server_status_path.is_file():
        raise FileNotFoundError(job_id)
    status = read_json(server_status_path)
    runner_status_path = output_dir / "status.json"
    if runner_status_path.is_file():
        runner_status = read_json(runner_status_path)
        if runner_status.get("status") == "PASS":
            status.update(
                {
                    "status": "PASS",
                    "completed": True,
                    "resultUsable": True,
                    "manifestUrl": f"/api/stage20/local/jobs/{job_id}/artifacts/browser-manifest.json",
                    "binaryUrl": f"/api/stage20/local/jobs/{job_id}/artifacts/replay-fields.bin",
                    "resultUrl": f"/api/stage20/local/jobs/{job_id}/artifacts/result.json",
                }
            )
        elif runner_status.get("status") == "FAILED":
            status.update(
                {
                    "status": "FAILED",
                    "completed": True,
                    "resultUsable": False,
                    "message": runner_status.get(
                        "message", "物理計算が安全停止しました。"
                    ),
                }
            )
        elif runner_status.get("status") == "RUNNING":
            status["status"] = "RUNNING"
    return status


def normalize_client_request(payload: dict[str, Any]) -> tuple[list[float], int]:
    capacities = payload.get("gateCapacityFractionById")
    if not isinstance(capacities, list) or len(capacities) != 8:
        raise ValueError("1〜8番の水門状態を8個指定してください。")
    normalized: list[float] = []
    for value in capacities:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("水門状態は0または1で指定してください。")
        numeric = float(value)
        if numeric not in (0.0, 1.0):
            raise ValueError("水門状態は0または1で指定してください。")
        normalized.append(numeric)
    duration = payload.get("durationS")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("計算時間を指定してください。")
    duration_int = int(duration)
    if float(duration) != float(duration_int) or duration_int not in ALLOWED_DURATIONS:
        raise ValueError("計算時間は5・30・60・120・300秒から選択してください。")
    return normalized, duration_int


class JobManager:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active_job_id: str | None = None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        capacities, duration = normalize_client_request(payload)
        with self.lock:
            if self.active_job_id is not None:
                try:
                    active = public_job_status(self.active_job_id)
                except FileNotFoundError:
                    active = {"completed": True}
                if not active.get("completed", False):
                    raise RuntimeError(
                        "別のローカル物理計算を実行中です。完了後に再実行してください。"
                    )
                self.active_job_id = None
            timestamp = time.strftime("%Y%m%dT%H%M%S", time.localtime())
            job_id = f"local-{timestamp}-{uuid.uuid4().hex[:12]}"
            output_dir = JOBS_ROOT / job_id
            output_dir.mkdir(parents=True, exist_ok=False)
            request = {
                "schema": REQUEST_SCHEMA,
                "version": 1,
                "requestId": job_id,
                "classification": (
                    "local_uncalibrated_physics_not_field_prediction"
                ),
                "gateCapacityFractionById": capacities,
                "durationS": float(duration),
                "checkpointIntervalS": float(ALLOWED_DURATIONS[duration]),
                "fishwayMode": "always_enabled_C2_1_storage_tau60",
            }
            request_path = output_dir / "request.json"
            write_json(request_path, request)
            server_status = {
                "schema": JOB_SCHEMA,
                "version": 1,
                "jobId": job_id,
                "status": "QUEUED",
                "completed": False,
                "resultUsable": False,
                "classification": {
                    "localPhysicsRun": True,
                    "physicalCalibration": False,
                    "fieldPrediction": False,
                },
                "gateCapacityFractionById": capacities,
                "durationS": duration,
                "checkpointIntervalS": ALLOWED_DURATIONS[duration],
                "createdUnixS": time.time(),
            }
            write_json(output_dir / "server-status.json", server_status)
            self.active_job_id = job_id
            worker = threading.Thread(
                target=self._run,
                args=(job_id, request_path, output_dir),
                name=f"stage20-{job_id}",
                daemon=True,
            )
            worker.start()
        return public_job_status(job_id)

    def _run(
        self,
        job_id: str,
        request_path: Path,
        output_dir: Path,
    ) -> None:
        status_path = output_dir / "server-status.json"
        status = read_json(status_path)
        status["status"] = "RUNNING"
        status["startedUnixS"] = time.time()
        write_json(status_path, status)
        command = [
            str(PYTHON),
            str(RUNNER),
            "--request",
            str(request_path),
            "--output-dir",
            str(output_dir / "result-package"),
        ]
        log_path = output_dir / "runner.log"
        try:
            with log_path.open("wb") as log:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=1800,
                )
            package = output_dir / "result-package"
            if completed.returncode == 0:
                for name in [
                    "status.json",
                    "preflight.json",
                    "result.json",
                    "browser-manifest.json",
                    "replay-fields.bin",
                    "checkpoint-archive.npz",
                ]:
                    source = package / name
                    if source.is_file():
                        source.replace(output_dir / name)
                package.rmdir()
                runner_status = read_json(output_dir / "status.json")
                if runner_status.get("status") != "PASS":
                    raise RuntimeError("runner returned without a usable PASS package")
                status.update(
                    {
                        "status": "PASS",
                        "completed": True,
                        "resultUsable": True,
                        "completedUnixS": time.time(),
                    }
                )
            else:
                message = "物理計算が安全停止しました。runner.logを確認してください。"
                failed = package / "status.json"
                if failed.is_file():
                    failed_status = read_json(failed)
                    message = failed_status.get("message", message)
                status.update(
                    {
                        "status": "FAILED",
                        "completed": True,
                        "resultUsable": False,
                        "completedUnixS": time.time(),
                        "message": message,
                        "runnerExitCode": completed.returncode,
                    }
                )
        except Exception as error:
            status.update(
                {
                    "status": "FAILED",
                    "completed": True,
                    "resultUsable": False,
                    "completedUnixS": time.time(),
                    "message": str(error),
                    "errorType": type(error).__name__,
                }
            )
        finally:
            write_json(status_path, status)
            with self.lock:
                if self.active_job_id == job_id:
                    self.active_job_id = None


MANAGER = JobManager()


class Stage20IPv6ThreadingHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6


class Stage20Handler(BaseHTTPRequestHandler):
    server_version = "Stage20LocalSimulator/1.0"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    @staticmethod
    def copy_stream(source: Any, destination: Any) -> None:
        shutil.copyfileobj(source, destination, length=1024 * 1024)

    def send_empty(self, status: HTTPStatus, *, allow: str | None = None) -> None:
        self.send_response(status)
        if allow is not None:
            self.send_header("Allow", allow)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
    ) -> None:
        encoded = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_job_artifact(self, job_id: str, name: str) -> None:
        if not SAFE_JOB_ID.fullmatch(job_id) or name not in SAFE_JOB_ARTIFACTS:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"status": "ERROR", "message": "job artifact path is invalid"},
            )
            return
        output_dir = job_output_dir(job_id)
        artifact_root = next(
            (
                candidate
                for candidate in (JOBS_ROOT, LEGACY_JOBS_ROOT)
                if output_dir.parent == candidate
            ),
            None,
        )
        artifact = (
            secure_regular_file(artifact_root, f"{job_id}/{name}")
            if artifact_root is not None
            else None
        )
        if artifact is None:
            self.send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "ERROR", "message": "job artifact not found"},
            )
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", SAFE_JOB_ARTIFACTS[name])
        self.send_header("Content-Length", str(artifact.stat().st_size))
        self.end_headers()
        with artifact.open("rb") as stream:
            self.copy_stream(stream, self.wfile)

    def send_runtime_static(self, request_path: str, *, head_only: bool) -> bool:
        artifact = resolve_runtime_static_path(request_path)
        if artifact is None:
            return False
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(artifact, flags)
            stream = os.fdopen(descriptor, "rb")
        except OSError:
            return False
        with stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                return False
            media_type = STATIC_MEDIA_TYPES.get(artifact.suffix.casefold())
            if media_type is None:
                return False
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(metadata.st_size))
            self.end_headers()
            if not head_only:
                self.copy_stream(stream, self.wfile)
        return True

    def request_authority(self) -> tuple[str, int] | None:
        return loopback_authority(
            self.headers.get("Host"),
            int(self.server.server_port),
        )

    def reject_unsafe_get_context(self, path: str) -> bool:
        authority = self.request_authority()
        if authority is None:
            self.send_json(
                HTTPStatus.FORBIDDEN,
                {"status": "ERROR", "message": "loopback Host is required"},
            )
            return True
        origin = self.headers.get("Origin")
        if path.startswith("/api/") and origin is not None and not same_origin(
            origin,
            authority,
        ):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                {"status": "ERROR", "message": "cross-origin API request refused"},
            )
            return True
        return False

    def do_GET(self) -> None:
        path = canonical_request_path(self.path)
        if path is None:
            self.send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "ERROR", "message": "path is not served"},
            )
            return
        if self.reject_unsafe_get_context(path):
            return
        if path == "/api/stage20/forcing/capabilities":
            self.send_json(
                HTTPStatus.OK,
                {**forcing_capability_document(), **csrf_capability_fields()},
            )
            return
        if path == "/api/stage20/local/capabilities":
            runtime_capability = local_runtime_capability()
            asset_readiness = LOCAL_RUNTIME_ASSET_READINESS
            runtime_ready = asset_readiness["ready"] is True
            self.send_json(
                HTTPStatus.OK,
                {
                    "schema": CAPABILITY_SCHEMA,
                    "version": 1,
                    "status": (
                        "READY_FOR_EXPLICIT_LOCAL_RUN"
                        if runtime_ready
                        else "BLOCKED_LOCAL_ASSETS_UNAVAILABLE"
                    ),
                    "localOnly": True,
                    "meshId": "candidate_C_R1C_exact_confluence_R20_patches",
                    "cellCount": 37724,
                    "allowedDurationsS": (
                        list(ALLOWED_DURATIONS) if runtime_ready else []
                    ),
                    "maximumConcurrentJobs": 1 if runtime_ready else 0,
                    "fishwayMode": "always_enabled_C2_1_storage_tau60",
                    "runtimeCapabilityContract": runtime_capability,
                    "assetReadiness": asset_readiness,
                    **csrf_capability_fields(),
                    "classification": {
                        "localRunnerAvailable": runtime_ready,
                        "runtimeInputsVerified": runtime_ready,
                        "solverExecutionPreflightPassed": False,
                        "physicalSolverConnected": False,
                        "physicalCalibration": False,
                        "fieldPrediction": False,
                        "productionPrecomputation": False,
                    },
                },
            )
            return
        artifact_match = re.fullmatch(
            r"/api/stage20/local/jobs/(local-[0-9]{8}T[0-9]{6}-[0-9a-f]{12})/artifacts/([^/]+)",
            path,
        )
        if artifact_match:
            self.send_job_artifact(artifact_match.group(1), artifact_match.group(2))
            return
        prefix = "/api/stage20/local/jobs/"
        if path.startswith(prefix):
            job_id = path[len(prefix) :]
            if not SAFE_JOB_ID.fullmatch(job_id):
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "ERROR", "message": "job id is invalid"},
                )
                return
            try:
                payload = public_job_status(job_id)
            except FileNotFoundError:
                self.send_json(
                    HTTPStatus.NOT_FOUND,
                    {"status": "ERROR", "message": "job not found"},
                )
                return
            self.send_json(HTTPStatus.OK, payload)
            return
        if self.send_runtime_static(path, head_only=False):
            return
        self.send_json(
            HTTPStatus.NOT_FOUND,
            {"status": "ERROR", "message": "path is not served"},
        )

    def do_HEAD(self) -> None:
        path = canonical_request_path(self.path)
        if path is None:
            self.send_empty(HTTPStatus.NOT_FOUND)
            return
        authority = self.request_authority()
        if authority is None:
            self.send_empty(HTTPStatus.FORBIDDEN)
            return
        origin = self.headers.get("Origin")
        if path.startswith("/api/"):
            if origin is not None and not same_origin(origin, authority):
                self.send_empty(HTTPStatus.FORBIDDEN)
                return
            self.send_empty(HTTPStatus.METHOD_NOT_ALLOWED, allow="GET, POST")
            return
        if self.send_runtime_static(path, head_only=True):
            return
        self.send_empty(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = canonical_request_path(self.path)
        if path not in {
            "/api/stage20/local/jobs",
            "/api/stage20/forcing/build",
        }:
            self.send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "ERROR", "message": "endpoint not found"},
            )
            return
        header_failure = post_header_failure(
            self.headers,
            int(self.server.server_port),
        )
        if header_failure is not None:
            status, message = header_failure
            self.send_json(status, {"status": "ERROR", "message": message})
            return
        if path == "/api/stage20/local/jobs":
            try:
                current_readiness = local_runtime_asset_readiness()
            except RuntimeError:
                current_readiness = {"ready": False}
            if current_readiness.get("ready") is not True:
                self.send_json(
                    HTTPStatus.CONFLICT,
                    {
                        "status": "BLOCKED_LOCAL_ASSETS_UNAVAILABLE",
                        "message": "local R1C assets are missing or invalid",
                    },
                )
                return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        maximum = (
            MAX_FORCING_REQUEST_BYTES
            if path == "/api/stage20/forcing/build"
            else MAX_REQUEST_BYTES
        )
        if length <= 0 or length > maximum:
            self.send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"status": "ERROR", "message": "request size is invalid"},
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON object is required")
            if path == "/api/stage20/forcing/build":
                integrated = build_from_client_request(payload)
                self.send_json(HTTPStatus.OK, integrated)
                return
            job = MANAGER.create(payload)
        except (ValueError, IntegrationError) as error:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"status": "ERROR", "message": str(error)},
            )
            return
        except RuntimeError as error:
            self.send_json(
                HTTPStatus.CONFLICT,
                {"status": "ERROR", "message": str(error)},
            )
            return
        self.send_json(HTTPStatus.ACCEPTED, job)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    if args.bind not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("local simulator refuses non-loopback binding")
    if not PYTHON.is_file() or not RUNNER.is_file():
        raise SystemExit("local runtime is incomplete")
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    server_type = (
        Stage20IPv6ThreadingHTTPServer
        if args.bind == "::1"
        else ThreadingHTTPServer
    )
    server = server_type((args.bind, args.port), Stage20Handler)
    display_host = f"[{args.bind}]" if ":" in args.bind else args.bind
    print(
        f"Stage 20 local simulator: "
        f"http://{display_host}:{args.port}/stage20-hybrid-gui.html",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
