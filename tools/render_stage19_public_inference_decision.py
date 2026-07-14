#!/usr/bin/env python3
"""Render the normalized Stage 19 inferred-depth shape decision image.

This renderer never assigns metre-valued depth to the solver and never starts a
numerical run.  It converts the approved water mask into a normalized
shore-to-centre weighting solely for visual review.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan",
        default="config/stage19_public_inference_input_plan_v1.json",
    )
    parser.add_argument(
        "--manifest",
        default="data/onga_unified_water_manifest_r3.json",
    )
    parser.add_argument(
        "--output",
        default="docs/visuals/stage19-public-inference-input-decision.png",
    )
    return parser.parse_args()


def load_water_mask(manifest_path: Path) -> tuple[dict, np.ndarray]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    height = int(manifest["height"])
    width = int(manifest["width"])
    mask = np.zeros((height, width), dtype=bool)
    for relative in manifest["chunks"]:
        chunk_path = (manifest_path.parent / Path(relative).name).resolve()
        chunk = json.loads(chunk_path.read_text(encoding="utf-8"))
        start_row = int(chunk["startRow"])
        for row_offset, runs in enumerate(chunk["rows"]):
            if len(runs) % 2:
                raise ValueError(f"odd run endpoint count in {chunk_path}:{row_offset}")
            row = start_row + row_offset
            for index in range(0, len(runs), 2):
                x0 = int(runs[index])
                x1 = int(runs[index + 1])
                mask[row, x0 : x1 + 1] = True
    if int(mask.sum()) != int(manifest["pixelCount"]):
        raise ValueError("decoded water pixel count does not match the approved manifest")
    return manifest, mask


def normalized_profile(x: np.ndarray, sigma: float) -> np.ndarray:
    edge = np.exp(-0.5 / sigma**2)
    return (np.exp(-0.5 * (x / sigma) ** 2) - edge) / (1.0 - edge)


def normalized_map(mask: np.ndarray, sigma: float) -> np.ndarray:
    # Extend the four open-boundary wet runs vertically so that the artificial
    # image edge is not mistaken for a shoreline.  Left/right remain dry.
    extension = 220
    padded = np.pad(mask, ((extension, extension), (1, 1)), mode="constant", constant_values=False)
    padded[:extension, 1:-1] = mask[0]
    padded[extension + mask.shape[0] :, 1:-1] = mask[-1]
    extended_distance = distance_transform_edt(padded)
    shore_distance = extended_distance[extension : extension + mask.shape[0], 1:-1]
    # Use a single robust distance scale for the preview.  This preserves a
    # smooth shore-to-centre gradient without inventing cross-section axes at
    # confluences.  Narrow tributaries can therefore remain relatively
    # shallower than the broad main channel in this shape-only map.
    distance_scale = float(np.percentile(shore_distance[mask], 95.0))
    centre_fraction = np.divide(
        shore_distance,
        max(distance_scale, 1.0),
        out=np.zeros_like(shore_distance),
        where=mask,
    )
    centre_fraction = np.clip(centre_fraction, 0.0, 1.0)
    # Convert shore=0 / centre=1 into the same inverse-normal family used by
    # the explicit cross-section panel.  This is still dimensionless.
    x_from_centre = 1.0 - centre_fraction
    relative_depth = normalized_profile(x_from_centre, sigma)
    smooth_weight = gaussian_filter(mask.astype(float), sigma=1.6, mode="nearest")
    relative_depth = np.divide(
        gaussian_filter(relative_depth * mask, sigma=1.6, mode="nearest"),
        np.maximum(smooth_weight, 1e-9),
        out=np.zeros_like(relative_depth),
        where=smooth_weight > 0,
    )
    relative_depth[~mask] = np.nan
    return relative_depth


def boundary_markers(manifest: dict) -> list[tuple[str, float, float]]:
    markers = []
    height = int(manifest["height"])
    for boundary in manifest["openBoundaries"]:
        x0, x1 = boundary["pixelRun"]
        x = (float(x0) + float(x1)) / 2.0
        y = 10.0 if boundary["edge"] == "top" else float(height - 11)
        markers.append((boundary["id"], x, y))
    return markers


def render(plan: dict, manifest: dict, mask: np.ndarray, output: Path) -> None:
    bathymetry = plan["inferenceScenario"]["bathymetry"]
    sigmas = [float(value) for value in bathymetry["sigmaCandidates"]]
    reference_sigma = float(bathymetry["referenceSigma"])
    relative_depth = normalized_map(mask, reference_sigma)

    fig = plt.figure(figsize=(14, 8.4), dpi=150, facecolor="#f7f9fa")
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=(1.62, 1.0),
        height_ratios=(1.0, 0.24),
        left=0.045,
        right=0.975,
        top=0.88,
        bottom=0.08,
        wspace=0.16,
        hspace=0.18,
    )
    map_ax = fig.add_subplot(grid[0, 0])
    section_ax = fig.add_subplot(grid[0, 1])
    note_ax = fig.add_subplot(grid[1, :])

    cmap = matplotlib.colormaps["Blues"].copy()
    cmap.set_bad("#f7f9fa")
    image = map_ax.imshow(relative_depth, origin="upper", cmap=cmap, vmin=0.0, vmax=1.0)
    map_ax.contour(mask.astype(float), levels=[0.5], colors=["#35566f"], linewidths=0.45)
    for boundary_id, x, y in boundary_markers(manifest):
        map_ax.scatter([x], [y], s=38, marker="o", color="#ef8a2f", edgecolor="#ffffff", linewidth=0.8)
        map_ax.text(x + 18, y, boundary_id, color="#263845", fontsize=9, va="center", weight="bold")
    map_ax.set_title("Approved water domain: relative shore-distance weighting", loc="left", fontsize=12, weight="bold")
    map_ax.set_axis_off()
    colorbar = fig.colorbar(image, ax=map_ax, fraction=0.028, pad=0.015)
    colorbar.set_label("relative depth fraction (0 shore / 1 broad-channel centre)", fontsize=9)
    colorbar.ax.tick_params(labelsize=8)

    x = np.linspace(-1.0, 1.0, 501)
    labels = {0.28: "narrow", 0.36: "reference", 0.46: "broad"}
    colours = {0.28: "#6b7f8f", 0.36: "#176ca4", 0.46: "#2f9f92"}
    for sigma in sigmas:
        depth = normalized_profile(x, sigma)
        line_width = 2.8 if sigma == reference_sigma else 1.5
        section_ax.plot(
            x,
            -depth,
            color=colours[sigma],
            linewidth=line_width,
            label=f"{labels[sigma]}  sigma={sigma:.2f}",
        )
    reference_depth = normalized_profile(x, reference_sigma)
    section_ax.fill_between(x, -reference_depth, 0.0, color="#5fb6d9", alpha=0.16)
    section_ax.axhline(0.0, color="#5d7280", linewidth=1.0)
    section_ax.text(-0.98, 0.03, "left shore", fontsize=8, color="#5d7280", va="bottom")
    section_ax.text(0.98, 0.03, "right shore", fontsize=8, color="#5d7280", va="bottom", ha="right")
    section_ax.annotate(
        "deepest at channel centre",
        xy=(0.0, -1.0),
        xytext=(0.42, -0.72),
        arrowprops={"arrowstyle": "->", "color": "#263845", "linewidth": 1.0},
        fontsize=9,
        color="#263845",
    )
    section_ax.set_title("Proposed smooth inverse-normal-like cross-section", loc="left", fontsize=12, weight="bold")
    section_ax.set_xlabel("normalized cross-channel position")
    section_ax.set_ylabel("relative bed depth (downward)")
    section_ax.set_xlim(-1.05, 1.05)
    section_ax.set_ylim(-1.08, 0.08)
    section_ax.set_xticks([-1.0, -0.5, 0.0, 0.5, 1.0])
    section_ax.set_yticks([-1.0, -0.5, 0.0], ["1.0", "0.5", "0.0"])
    section_ax.grid(color="#d7dfe4", linewidth=0.65)
    section_ax.legend(loc="lower left", fontsize=8, frameon=False)
    for spine in ("top", "right"):
        section_ax.spines[spine].set_visible(False)

    note_ax.set_axis_off()
    note_ax.axhline(0.96, color="#cfd9de", linewidth=1.0)
    note_ax.text(
        0.0,
        0.70,
        "PUBLIC METADATA FIXED",
        transform=note_ax.transAxes,
        fontsize=9,
        color="#46606e",
        weight="bold",
    )
    note_ax.text(
        0.0,
        0.42,
        "Gion Bridge / Nakama / Karakuma station metadata | JMA tide as secondary shape reference | published barrage gate inventory",
        transform=note_ax.transAxes,
        fontsize=9,
        color="#263845",
    )
    note_ax.text(
        0.0,
        0.10,
        "STILL INFERRED",
        transform=note_ax.transAxes,
        fontsize=9,
        color="#a05522",
        weight="bold",
    )
    note_ax.text(
        0.16,
        0.10,
        "absolute depth | Magarigawa inflow | gate operation | fishway coefficients | velocity validation",
        transform=note_ax.transAxes,
        fontsize=9,
        color="#263845",
    )

    fig.suptitle(
        "Stage 19 visual decision: provisional bathymetry shape only",
        x=0.045,
        y=0.955,
        ha="left",
        fontsize=17,
        color="#1f3440",
        weight="bold",
    )
    fig.text(
        0.045,
        0.915,
        "No metre-valued depth, boundary assignment, solver input, numerical run, or physical Validation is approved by this image.",
        fontsize=10,
        color="#5b707d",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output,
        dpi=150,
        facecolor=fig.get_facecolor(),
        metadata={"Software": "onga-stage19-public-inference-renderer-v1"},
    )
    plt.close(fig)


def main() -> None:
    args = parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    manifest, mask = load_water_mask(Path(args.manifest).resolve())
    render(plan, manifest, mask, Path(args.output))
    print(
        json.dumps(
            {
                "status": "rendered",
                "output": str(Path(args.output)),
                "waterPixelCount": int(mask.sum()),
                "normalizedOnly": True,
                "numericalRunEnabled": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
