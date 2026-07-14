#!/usr/bin/env python3
"""Render the five Stage 19 maps from accepted step-matched statistics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from aggregate_stage18_full64_v2 import build_cell_raster, render_map


SPECS = (
    ("full64-depth-median.png", "water_depth_median_m", "water depth median", "m",
     ((220, 247, 246), (107, 207, 211), (42, 130, 186), (8, 48, 107)), None),
    ("full64-velocity-median.png", "velocity_median_ms", "velocity magnitude median", "m/s",
     ((255, 247, 188), (253, 174, 97), (221, 60, 87), (103, 24, 107)), None),
    ("full64-wet-probability.png", "wet_probability", "wet probability", "fraction",
     ((247, 242, 224), (143, 205, 181), (37, 139, 111), (6, 78, 59)), (0.0, 1.0)),
    ("full64-direction-agreement.png", "flow_direction_agreement_fraction", "direction agreement", "fraction",
     ((245, 235, 255), (196, 163, 230), (126, 82, 178), (76, 29, 149)), (0.0, 1.0)),
    ("full64-direction-support.png", "direction_sample_support_fraction", "direction sample support", "fraction",
     ((244, 247, 246), (173, 216, 230), (55, 150, 162), (7, 78, 89)), (0.0, 1.0)),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage19-maps] {message}")


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh")
    parser.add_argument("statistics")
    parser.add_argument("summary")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    require(sha256(args.mesh) == "f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2", "mesh digest")
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    require(summary["schema"] == "onga-stage19-full64-step-matched-statistics-summary-v1", "summary schema")
    require(summary["source"]["statisticsSha256"] == sha256(args.statistics), "statistics digest")
    with np.load(args.mesh, allow_pickle=False) as mesh:
        vertices = mesh["vertex_local_mm"].astype(np.float64) * 1e-3
        triangles = mesh["triangles"].astype(np.int32)
    require(triangles.shape == (50129, 3), "cell count")
    grid, bounds, coverage = build_cell_raster(vertices, triangles, width=3840, height=2640)
    require(coverage["representedCellCount"] == 50129 and coverage["coverageFraction"] == 1.0,
            "map does not represent every cell")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with np.load(args.statistics, allow_pickle=False) as statistics:
        require(str(statistics["schema"].item()) == "onga-stage19-full64-step-matched-statistics-v1", "statistics schema")
        rendered = []
        for filename, field, title, units, palette, fixed_range in SPECS:
            values = np.asarray(statistics[field], dtype=np.float64)
            png, scale = render_map(grid, values, palette, fixed_range=fixed_range)
            destination = output_dir / filename
            require(not destination.exists(), f"output exists: {destination}")
            destination.write_bytes(png)
            rendered.append({
                "filename": filename,
                "field": field,
                "title": title,
                "units": units,
                "sha256": sha256(destination),
                **scale,
            })
    manifest = {
        "schema": "onga-stage19-full64-map-manifest-v1",
        "status": "passed",
        "classification": "provisional_step_matched_outputs_not_physical_validation",
        "mapCount": 5,
        "cellCount": 50129,
        "representedCellCount": coverage["representedCellCount"],
        "coverageFraction": coverage["coverageFraction"],
        "pngWidth": 3840,
        "pngHeight": 2640,
        "boundsLocalM": bounds,
        "raster": coverage,
        "source": {
            "meshSha256": sha256(args.mesh),
            "statisticsSha256": sha256(args.statistics),
            "summarySha256": sha256(args.summary),
        },
        "maps": rendered,
        "interpretationLimits": summary["interpretationLimits"],
    }
    manifest_path = output_dir / "full64-map-manifest.json"
    require(not manifest_path.exists(), "map manifest exists")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "mapCount": 5, "coverageFraction": 1.0}))


if __name__ == "__main__":
    main()
