#!/usr/bin/env python3
"""Build a conservative raindrop-reduced visual aid from fixed-camera frames.

The raw observations remain authoritative.  This tool computes a per-pixel
temporal median and a temporal-dispersion mask from an odd-sized window of
camera frames.  The result is useful for inspection and as an auxiliary model
input, but it must never become a gate-state label by itself: a gate can move
inside the window and the median may then combine different physical states.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image


SCHEMA = "onga-stage20-gate-camera-temporal-derain-v1"
STATUS = "PASS_VISUAL_AID_NOT_GATE_STATE_EVIDENCE"
CAMERA_SOURCE_NAME = "barrageCamera"


class TemporalDerainError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TemporalDerainError(f"[stage20-gate-camera-temporal-derain-v1] {message}")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_window_size(count: int) -> None:
    require(3 <= count <= 15, "frame count must be between 3 and 15")
    require(count % 2 == 1, "frame count must be odd")


def load_rgb_frames(paths: Sequence[Path]) -> np.ndarray:
    validate_window_size(len(paths))
    arrays: list[np.ndarray] = []
    expected_size: tuple[int, int] | None = None
    for path in paths:
        require(path.is_file(), f"camera frame is absent: {path}")
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            if expected_size is None:
                expected_size = rgb.size
            require(rgb.size == expected_size, f"camera frame size changed: {path}")
            arrays.append(np.asarray(rgb, dtype=np.uint8))
    return np.stack(arrays, axis=0)


def temporal_median_and_dispersion(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    require(frames.ndim == 4 and frames.shape[-1] == 3, "frames must have shape [N,H,W,3]")
    validate_window_size(int(frames.shape[0]))
    median = np.median(frames.astype(np.float32), axis=0)
    absolute_deviation = np.abs(frames.astype(np.float32) - median[None, ...])
    dispersion = np.median(absolute_deviation, axis=(0, 3))
    return np.rint(median).clip(0, 255).astype(np.uint8), dispersion


def edge_energy(rgb: np.ndarray) -> float:
    luminance = (
        0.2126 * rgb[..., 0].astype(np.float32)
        + 0.7152 * rgb[..., 1].astype(np.float32)
        + 0.0722 * rgb[..., 2].astype(np.float32)
    )
    horizontal = np.abs(np.diff(luminance, axis=1)).mean()
    vertical = np.abs(np.diff(luminance, axis=0)).mean()
    return float((horizontal + vertical) / 2.0)


def dispersion_image(dispersion: np.ndarray) -> np.ndarray:
    require(dispersion.ndim == 2, "dispersion must have shape [H,W]")
    upper = float(np.percentile(dispersion, 99.0))
    if upper <= 0.0:
        return np.zeros(dispersion.shape, dtype=np.uint8)
    return np.rint(np.clip(dispersion / upper, 0.0, 1.0) * 255.0).astype(np.uint8)


def discover_recent_frames(collection_root: Path, count: int) -> list[Path]:
    validate_window_size(count)
    candidates: list[tuple[str, Path]] = []
    for observation_path in sorted(collection_root.glob("runs/*/*/*/*/observation.json")):
        try:
            observation = json.loads(observation_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        source = observation.get("sources", {}).get(CAMERA_SOURCE_NAME, {})
        if source.get("status") != "FETCHED":
            continue
        relative_path = source.get("relativePath")
        if not isinstance(relative_path, str):
            continue
        frame_path = observation_path.parent / relative_path
        if frame_path.is_file():
            candidates.append((str(observation.get("runId", observation_path.parent.name)), frame_path))
    require(len(candidates) >= count, f"only {len(candidates)} camera frames are available")
    return [path for _, path in candidates[-count:]]


def _atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(body)
    os.replace(temporary, path)


def generate_visual_aid(paths: Sequence[Path], output_root: Path) -> dict[str, Any]:
    resolved_paths = [path.resolve() for path in paths]
    frames = load_rgb_frames(resolved_paths)
    median, dispersion = temporal_median_and_dispersion(frames)
    output_root.mkdir(parents=True, exist_ok=True)
    image_path = output_root / "temporal-median.jpg"
    dispersion_path = output_root / "temporal-dispersion.png"
    report_path = output_root / "report.json"

    image_temp = output_root / f".temporal-median.{os.getpid()}.{uuid.uuid4().hex}.jpg"
    dispersion_temp = output_root / f".temporal-dispersion.{os.getpid()}.{uuid.uuid4().hex}.png"
    Image.fromarray(median, mode="RGB").save(image_temp, format="JPEG", quality=95, optimize=True)
    Image.fromarray(dispersion_image(dispersion), mode="L").save(dispersion_temp, format="PNG", optimize=True)
    os.replace(image_temp, image_path)
    os.replace(dispersion_temp, dispersion_path)

    input_records = [
        {
            "path": str(path),
            "byteLength": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in resolved_paths
    ]
    current_edge = edge_energy(frames[-1])
    median_edge = edge_energy(median)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "method": "per_pixel_temporal_median_fixed_camera",
        "frameCount": len(resolved_paths),
        "inputsOldestToNewest": input_records,
        "outputs": {
            "temporalMedian": {
                "path": str(image_path.resolve()),
                "byteLength": image_path.stat().st_size,
                "sha256": sha256_file(image_path),
            },
            "temporalDispersion": {
                "path": str(dispersion_path.resolve()),
                "byteLength": dispersion_path.stat().st_size,
                "sha256": sha256_file(dispersion_path),
            },
        },
        "metrics": {
            "newestFrameEdgeEnergy": current_edge,
            "temporalMedianEdgeEnergy": median_edge,
            "edgeEnergyRatioMedianToNewest": median_edge / current_edge if current_edge > 0.0 else None,
            "medianTemporalDispersionRgbLevels": float(np.median(dispersion)),
            "p99TemporalDispersionRgbLevels": float(np.percentile(dispersion, 99.0)),
        },
        "boundary": {
            "rawImagesModified": False,
            "gateStateInferred": False,
            "trainingLabelGenerated": False,
            "humanVisibilityAidOnly": True,
            "auxiliaryModelInputCandidate": True,
            "mustRejectAsStateEvidenceIfGateConfigurationChangedInsideWindow": True,
        },
    }
    _atomic_bytes(report_path, canonical_bytes(report))
    report["reportPath"] = str(report_path.resolve())
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--collection-root", type=Path)
    source.add_argument("--frame", type=Path, action="append", dest="frames")
    parser.add_argument("--count", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.collection_root is not None:
            paths = discover_recent_frames(args.collection_root, args.count)
        else:
            paths = list(args.frames or [])
            require(len(paths) == args.count, "--count must match the number of --frame arguments")
        result = generate_visual_aid(paths, args.output)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED_NO_GATE_INFERENCE", "errorType": type(error).__name__, "message": str(error)}, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
