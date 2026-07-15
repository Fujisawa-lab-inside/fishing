#!/usr/bin/env python3
"""Build a deterministic synthetic response pack for browser-path validation.

The generated fields exercise the selected browser mesh data path. They are
not shallow-water results and must never be published as physical flow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_mesh(path: Path) -> tuple[dict, dict[str, np.ndarray]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    payload = (path.parent / manifest["binary"]["url"]).read_bytes()
    require(sha256(payload) == manifest["binary"]["sha256"], "mesh digest mismatch")
    arrays = {}
    for name, descriptor in manifest["arrays"].items():
        dtype = np.dtype("<i4") if descriptor["dtype"] == "int32" else np.dtype("u1")
        arrays[name] = np.frombuffer(
            payload,
            dtype=dtype,
            count=math.prod(descriptor["shape"]),
            offset=descriptor["byteOffset"],
        ).reshape(descriptor["shape"])
    return manifest, arrays


def unit_to_target(points: np.ndarray, target: np.ndarray) -> np.ndarray:
    vector = target[None, :] - points
    norm = np.linalg.norm(vector, axis=1)
    return vector / np.maximum(norm[:, None], 1e-12)


def gaussian(points: np.ndarray, centre: np.ndarray, scale: float) -> np.ndarray:
    distance = np.linalg.norm(points - centre[None, :], axis=1)
    return np.exp(-0.5 * (distance / scale) ** 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", default="public/data/onga/stage20/mesh-v2.json")
    parser.add_argument("--manifest", default="public/data/onga/stage20/response-pack-synthetic-v2.json")
    parser.add_argument("--binary", default="public/data/onga/stage20/response-pack-synthetic-v2.bin")
    parser.add_argument("--inputs", default="public/data/onga/stage20/hybrid-synthetic-input-v1.json")
    args = parser.parse_args()

    mesh_manifest, arrays = load_mesh(Path(args.mesh))
    vertices = arrays["vertex_local_mm"].astype(np.float64) * 1e-3
    triangles = arrays["triangles"].astype(np.int64)
    centres = vertices[triangles].mean(axis=1)
    boundary_cells = arrays["boundary_face_cell"].astype(np.int64)
    boundary_tags = arrays["boundary_face_tag"].astype(np.uint8)
    mouth = centres[np.unique(boundary_cells[boundary_tags == 1])].mean(axis=0)
    n_centre = centres[np.unique(boundary_cells[boundary_tags == 2])].mean(axis=0)
    o_centre = centres[np.unique(boundary_cells[boundary_tags == 3])].mean(axis=0)
    g_centre = centres[np.unique(boundary_cells[boundary_tags == 4])].mean(axis=0)
    face_vertices = arrays["internal_face_vertices"].astype(np.int64)
    barrage_ids = arrays["barrage_face_ids"].astype(np.int64)
    barrage = vertices[face_vertices[barrage_ids]].mean(axis=(0, 1))

    span = np.maximum(centres.max(axis=0) - centres.min(axis=0), 1.0)
    normalised = (centres - centres.min(axis=0)) / span
    direction = unit_to_target(centres, mouth)
    cell_count = len(centres)
    component_count = 3
    mode_ids = ["constant", "tide", "onga_discharge", "nishi_discharge", "magari_discharge", "barrage_opening"]
    basis = np.zeros((len(mode_ids), component_count, cell_count), dtype="<f4")

    # Constant mode: positive synthetic depth only.
    basis[0, 0] = 2.6 + 0.9 * (0.25 + 0.75 * np.sin(np.pi * normalised[:, 0]) ** 2)
    # Tide mode: coherent level response and weak mouth-directed velocity.
    basis[1, 0] = 0.32
    basis[1, 1] = 0.10 * direction[:, 0]
    basis[1, 2] = 0.10 * direction[:, 1]
    # River modes: deterministic localised vectors used only to benchmark synthesis.
    for mode, centre, magnitude, scale in (
        (2, o_centre, 0.42, 900.0),
        (3, n_centre, 0.20, 520.0),
        (4, g_centre, 0.24, 520.0),
    ):
        weight = 0.25 + 0.75 * gaussian(centres, centre, scale)
        basis[mode, 0] = 0.025 * weight
        basis[mode, 1] = magnitude * weight * direction[:, 0]
        basis[mode, 2] = magnitude * weight * direction[:, 1]
    gate_weight = gaussian(centres, barrage, 260.0)
    basis[5, 0] = 0.015 * gate_weight
    basis[5, 1] = 0.28 * gate_weight * direction[:, 0]
    basis[5, 2] = 0.28 * gate_weight * direction[:, 1]

    payload = basis.tobytes(order="C")
    binary_path = Path(args.binary)
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_bytes(payload)
    manifest = {
        "schema": "onga-stage20-response-pack-v1",
        "version": "stage20-synthetic-response-pack-v2-mesh-v2",
        "status": "synthetic_browser_benchmark_only",
        "mesh": {
            "manifest": args.mesh,
            "schema": mesh_manifest["schema"],
            "version": mesh_manifest["version"],
            "sha256": mesh_manifest["binary"]["sha256"],
            "cellCount": mesh_manifest["counts"]["cells"],
        },
        "binary": {
            "url": f"./{binary_path.name}",
            "byteLength": len(payload),
            "sha256": sha256(payload),
        },
        "componentOrder": ["depthM", "eastVelocityMPS", "northVelocityMPS"],
        "arrays": {
            "basis": {
                "dtype": "float32",
                "shape": list(basis.shape),
                "byteOffset": 0,
                "byteLength": len(payload),
                "sha256": sha256(payload),
            }
        },
        "modes": [
            {"id": "constant", "kind": "constant"},
            {"id": "tide", "kind": "affine_input", "input": "tideRelativeM", "offset": 0.0, "scale": 1.0},
            {"id": "onga_discharge", "kind": "affine_input", "input": "ongaDischargeM3S", "offset": 35.0, "scale": 145.0},
            {"id": "nishi_discharge", "kind": "affine_input", "input": "nishiDischargeM3S", "offset": 2.0, "scale": 10.0},
            {"id": "magari_discharge", "kind": "affine_input", "input": "magariDischargeM3S", "offset": 1.0, "scale": 7.0},
            {"id": "barrage_opening", "kind": "affine_input", "input": "barrageOpeningFraction", "offset": 0.5, "scale": 0.5},
        ],
        "inputContract": {
            "startHour": -12,
            "endHour": 24,
            "intervalHours": 1,
            "snapshotCount": 37,
            "series": [
                {"name": "tideRelativeM", "unit": "m", "minimum": -1.0, "maximum": 1.0},
                {"name": "ongaDischargeM3S", "unit": "m3/s", "minimum": 5.0, "maximum": 180.0},
                {"name": "nishiDischargeM3S", "unit": "m3/s", "minimum": 0.2, "maximum": 12.0},
                {"name": "magariDischargeM3S", "unit": "m3/s", "minimum": 0.1, "maximum": 8.0},
                {"name": "barrageOpeningFraction", "unit": "1", "minimum": 0.0, "maximum": 1.0},
            ],
        },
        "outputContract": {
            "snapshotCount": 37,
            "cellCount": cell_count,
            "minimumDepthM": 0.2,
            "displayViews": ["estuary", "barrage", "confluence", "fishway"],
            "meshReferencedAdaptiveArrows": True,
        },
        "safeguards": {
            "physicalSolverExecuted": False,
            "observedDataUsed": False,
            "physicalValidationClaimAllowed": False,
            "publicSimulatorConnected": False,
        },
    }
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    hours = list(range(-12, 25))
    tide = [round(0.82 * math.sin(2.0 * math.pi * (hour + 1.8) / 12.42), 8) for hour in hours]
    fixture = {
        "schema": "onga-stage20-hybrid-hourly-input-v1",
        "status": "synthetic_browser_benchmark_only",
        "hours": hours,
        "tideRelativeM": tide,
        "ongaDischargeM3S": [180.0] * len(hours),
        "nishiDischargeM3S": [12.0] * len(hours),
        "magariDischargeM3S": [8.0] * len(hours),
        "barrageOpeningFraction": [1.0] * len(hours),
        "safeguards": {"physicalBoundarySeries": False, "physicalRunAuthorization": False},
    }
    Path(args.inputs).write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "built_synthetic_browser_benchmark_pack",
        "cellCount": cell_count,
        "modeCount": len(mode_ids),
        "byteLength": len(payload),
        "sha256": manifest["binary"]["sha256"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
