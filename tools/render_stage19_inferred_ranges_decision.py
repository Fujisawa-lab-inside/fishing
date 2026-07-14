#!/usr/bin/env python3
"""Render the Stage 19 candidate-range and boundary-mapping decision image.

This is a review-only renderer. It does not generate solver cases, assign a
single parameter set, or start a numerical run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ranges",
        default="config/stage19_inferred_scenario_ranges_v1.json",
    )
    parser.add_argument(
        "--manifest",
        default="data/onga_unified_water_manifest_r3.json",
    )
    parser.add_argument(
        "--output",
        default="docs/visuals/stage19-inferred-scenario-ranges-decision.png",
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
        raise ValueError("decoded water pixel count does not match manifest")
    return manifest, mask


def boundary_markers(manifest: dict) -> dict[str, tuple[float, float]]:
    markers: dict[str, tuple[float, float]] = {}
    height = int(manifest["height"])
    for boundary in manifest["openBoundaries"]:
        x0, x1 = boundary["pixelRun"]
        x = (float(x0) + float(x1)) / 2.0
        y = 12.0 if boundary["edge"] == "top" else float(height - 13)
        markers[boundary["id"]] = (x, y)
    return markers


def draw_range(
    axis: plt.Axes,
    y: float,
    label: str,
    values: dict,
    unit: str,
    colour: str,
) -> None:
    minimum = float(values["min"])
    reference = float(values["reference"])
    maximum = float(values["max"])
    fraction = 0.5 if maximum == minimum else (reference - minimum) / (maximum - minimum)
    axis.plot([0.0, 1.0], [y, y], color="#c8d2d8", linewidth=5, solid_capstyle="round")
    axis.scatter([0.0, 1.0], [y, y], s=28, color="#71828d", zorder=3)
    axis.scatter([fraction], [y], s=70, color=colour, edgecolor="#ffffff", linewidth=1.0, zorder=4)
    axis.text(-0.04, y, label, ha="right", va="center", fontsize=8.2, color="#263845")
    axis.text(0.0, y - 0.24, f"{minimum:g}", ha="center", va="top", fontsize=7.2, color="#657782")
    axis.text(fraction, y + 0.22, f"ref {reference:g}", ha="center", va="bottom", fontsize=7.2, color="#263845")
    axis.text(1.0, y - 0.24, f"{maximum:g} {unit}", ha="center", va="top", fontsize=7.2, color="#657782")


def render(ranges: dict, manifest: dict, mask: np.ndarray, output: Path) -> None:
    boundaries = {item["boundaryId"]: item for item in ranges["boundaryCandidates"]}
    fig = plt.figure(figsize=(14, 10), dpi=150, facecolor="#f7f9fa")
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=(1.42, 1.0),
        height_ratios=(1.0, 0.29),
        left=0.045,
        right=0.975,
        top=0.88,
        bottom=0.06,
        wspace=0.12,
        hspace=0.16,
    )
    map_ax = fig.add_subplot(grid[0, 0])
    range_ax = fig.add_subplot(grid[0, 1])
    scope_ax = fig.add_subplot(grid[1, :])

    map_image = np.full(mask.shape, np.nan)
    map_image[mask] = 1.0
    cmap = matplotlib.colors.ListedColormap(["#cce9f4"])
    cmap.set_bad("#f7f9fa")
    map_ax.imshow(map_image, origin="upper", cmap=cmap, vmin=0.0, vmax=1.0)
    map_ax.contour(mask.astype(float), levels=[0.5], colors=["#35566f"], linewidths=0.55)
    marker_positions = boundary_markers(manifest)
    source_text = {
        "M": "JMA Hakata tide\nshape only",
        "N": "MLIT Gion Bridge\ncandidate",
        "O": "MLIT Nakama / Karakuma\ncandidates",
        "G": "No direct station\ninference only",
    }
    offsets = {
        "M": (120, 92),
        "N": (-270, -120),
        "O": (-60, -150),
        "G": (95, -110),
    }
    for boundary_id in ("M", "N", "O", "G"):
        x, y = marker_positions[boundary_id]
        dx, dy = offsets[boundary_id]
        colour = "#d67825" if boundary_id != "G" else "#9a4e31"
        map_ax.scatter([x], [y], s=85, marker="o", color=colour, edgecolor="#ffffff", linewidth=1.2, zorder=4)
        map_ax.annotate(
            f"{boundary_id}  {source_text[boundary_id]}",
            xy=(x, y),
            xytext=(x + dx, y + dy),
            fontsize=8.3,
            color="#263845",
            ha="left",
            va="center",
            arrowprops={"arrowstyle": "-", "color": "#7b8c96", "linewidth": 0.9},
        )
    map_ax.set_title("Candidate public-source mapping to open boundaries", loc="left", fontsize=12, weight="bold")
    map_ax.text(
        0.0,
        -0.035,
        "Map geometry is already approved and remains frozen. Mapping labels are candidates, not observations at the boundary.",
        transform=map_ax.transAxes,
        fontsize=8.1,
        color="#596d79",
        va="top",
    )
    map_ax.set_axis_off()

    range_ax.set_xlim(-0.55, 1.16)
    range_ax.set_ylim(-0.75, 10.75)
    range_ax.set_axis_off()
    range_ax.set_title("Proposed ensemble ranges", loc="left", fontsize=12, weight="bold")
    range_ax.text(
        0.0,
        10.34,
        "Endpoints = uncertainty limits   |   dot = reference only",
        fontsize=8.2,
        color="#596d79",
    )
    rows = [
        (9.62, "Main depth", ranges["bathymetryCandidates"]["mainstemMeanDepthM"], "m", "#176ca4"),
        (8.66, "Tributary depth", ranges["bathymetryCandidates"]["tributaryMeanDepthM"], "m", "#176ca4"),
        (7.70, "N discharge", boundaries["N"]["parameters"]["dischargeM3S"], "m3/s", "#2f8f83"),
        (6.74, "O discharge", boundaries["O"]["parameters"]["dischargeM3S"], "m3/s", "#2f8f83"),
        (5.78, "G discharge", boundaries["G"]["parameters"]["dischargeM3S"], "m3/s", "#9a4e31"),
        (4.82, "Manning n", ranges["roughnessCandidates"]["openChannel"], "", "#7a68a6"),
        (3.86, "M phase", boundaries["M"]["parameters"]["phaseShiftMinutes"], "min", "#d67825"),
        (2.90, "Barrage Cd", ranges["structureCandidates"]["barrage"]["effectiveDischargeCoefficient"], "", "#6b7f8f"),
        (1.94, "Fishway Cd", ranges["structureCandidates"]["fishway"]["effectiveDischargeCoefficient"], "", "#6b7f8f"),
        (0.98, "Fishway area", ranges["structureCandidates"]["fishway"]["effectiveAreaM2"], "m2", "#6b7f8f"),
    ]
    for row in rows:
        draw_range(range_ax, *row)
    amplitude = boundaries["M"]["parameters"]["amplitudeMultiplier"]
    range_ax.text(
        -0.02,
        0.28,
        f"M amplitude: {amplitude['min']:g} — ref {amplitude['reference']:g} — {amplitude['max']:g}",
        fontsize=7.8,
        color="#263845",
    )
    range_ax.text(
        -0.02,
        -0.02,
        "M absolute water-level offset: unassigned",
        fontsize=7.8,
        color="#9a4e31",
    )
    range_ax.text(
        -0.02,
        -0.36,
        "Barrage: closed / 25 / 50 / 100%   |   Fishway: disabled / head-relation ensemble",
        fontsize=7.1,
        color="#596d79",
    )

    scope_ax.set_axis_off()
    scope_ax.axhline(0.98, color="#cbd6dc", linewidth=1.0)
    scope_ax.text(0.0, 0.79, "ONE DECISION", transform=scope_ax.transAxes, fontsize=9, color="#46606e", weight="bold")
    scope_ax.text(
        0.12,
        0.79,
        "May these broad ranges + candidate boundary mappings be used to generate a provisional ensemble case package?",
        transform=scope_ax.transAxes,
        fontsize=10,
        color="#263845",
        weight="bold",
    )
    scope_ax.text(0.0, 0.47, "INCLUDED", transform=scope_ax.transAxes, fontsize=8.5, color="#33766f", weight="bold")
    scope_ax.text(
        0.12,
        0.47,
        "range endpoints | M/N/O source roles | G inference-only | barrage and fishway scenario ranges",
        transform=scope_ax.transAxes,
        fontsize=8.7,
        color="#263845",
    )
    scope_ax.text(0.0, 0.17, "NOT INCLUDED", transform=scope_ax.transAxes, fontsize=8.5, color="#9a4e31", weight="bold")
    scope_ax.text(
        0.12,
        0.17,
        "single true values | observed-status claim | solver assignment | numerical run | physical Validation | main merge",
        transform=scope_ax.transAxes,
        fontsize=8.7,
        color="#263845",
    )

    fig.suptitle(
        "Stage 19 input decision: ranges and boundary-source roles",
        x=0.045,
        y=0.952,
        ha="left",
        fontsize=17,
        color="#1f3440",
        weight="bold",
    )
    fig.text(
        0.045,
        0.912,
        "All numbers are provisional inference ranges. Approval creates cases only; it does not authorize a simulation.",
        fontsize=10,
        color="#5b707d",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output,
        dpi=150,
        facecolor=fig.get_facecolor(),
        metadata={"Software": "onga-stage19-inferred-ranges-renderer-v1"},
    )
    plt.close(fig)


def main() -> None:
    args = parse_args()
    ranges = json.loads(Path(args.ranges).read_text(encoding="utf-8"))
    manifest, mask = load_water_mask(Path(args.manifest).resolve())
    output = Path(args.output)
    render(ranges, manifest, mask, output)
    print(json.dumps({"status": "rendered", "output": str(output), "width": 2100, "height": 1500}))


if __name__ == "__main__":
    main()
