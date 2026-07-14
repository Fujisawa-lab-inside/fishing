#!/usr/bin/env python3
"""Render the Stage 19 M-boundary relative-tide selection decision."""

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
        "--candidate",
        default="config/stage19_m_boundary_tide_candidate_v1.json",
    )
    parser.add_argument(
        "--coverage",
        default="config/stage19_solver_parameter_coverage_audit_v1.json",
    )
    parser.add_argument(
        "--output",
        default="docs/visuals/stage19-m-boundary-tide-decision.png",
    )
    return parser.parse_args()


def render(candidate: dict, coverage: dict, output: Path) -> None:
    curve = candidate["candidateCurve"]
    anomaly = np.array(curve["relativeAnomalyM"] + [curve["nextDayZeroHourRelativeAnomalyM"]])
    hours = np.arange(25)
    low_multiplier = candidate["resultingCaseEnvelope"]["amplitudeMultiplier"]["min"]
    high_multiplier = candidate["resultingCaseEnvelope"]["amplitudeMultiplier"]["max"]
    low = np.minimum(anomaly * low_multiplier, anomaly * high_multiplier)
    high = np.maximum(anomaly * low_multiplier, anomaly * high_multiplier)

    fig = plt.figure(figsize=(14, 8.4), dpi=150, facecolor="#f7f9fa")
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=(1.78, 0.82),
        height_ratios=(1.0, 0.28),
        left=0.055,
        right=0.97,
        top=0.85,
        bottom=0.07,
        wspace=0.16,
        hspace=0.18,
    )
    plot_ax = fig.add_subplot(grid[0, 0])
    info_ax = fig.add_subplot(grid[0, 1])
    decision_ax = fig.add_subplot(grid[1, :])

    plot_ax.fill_between(hours, low, high, color="#6ab0cf", alpha=0.20, label="case envelope: x0.6 to x1.4")
    plot_ax.plot(hours, anomaly, color="#176ca4", linewidth=2.5, marker="o", markersize=3.3,
                 label="reference multiplier x1.0")
    plot_ax.axhline(0.0, color="#667984", linewidth=1.0)
    plot_ax.axvspan(0.0, 1.5, color="#d67825", alpha=0.08)
    plot_ax.axvspan(22.5, 24.0, color="#d67825", alpha=0.08)
    plot_ax.text(0.2, 0.92, "phase may shift by +/- 90 min", transform=plot_ax.transAxes,
                 fontsize=8.5, color="#8b572a")
    plot_ax.set_title("Proposed relative M-boundary curve", loc="left", fontsize=13, weight="bold")
    plot_ax.set_xlabel("hour from 2026-02-15 00:00 JST")
    plot_ax.set_ylabel("mean-removed tide anomaly (m)")
    plot_ax.set_xlim(0, 24)
    plot_ax.set_xticks(np.arange(0, 25, 3))
    plot_ax.set_ylim(-1.05, 1.05)
    plot_ax.grid(color="#d6dfe4", linewidth=0.65)
    plot_ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    for spine in ("top", "right"):
        plot_ax.spines[spine].set_visible(False)

    info_ax.set_axis_off()
    info_ax.text(0.0, 0.96, "SELECTION RULE", transform=info_ax.transAxes,
                 fontsize=9, color="#46606e", weight="bold")
    info_ax.text(0.0, 0.88, "2026 annual median daily range", transform=info_ax.transAxes,
                 fontsize=10.5, color="#263845", weight="bold")
    info_ax.text(0.0, 0.81, "earliest exact match: 2026-02-15", transform=info_ax.transAxes,
                 fontsize=9, color="#263845")
    info_ax.text(0.0, 0.72, "daily range", transform=info_ax.transAxes,
                 fontsize=8.5, color="#657782")
    info_ax.text(0.0, 0.65, "1.37 m", transform=info_ax.transAxes,
                 fontsize=18, color="#176ca4", weight="bold")
    info_ax.text(0.0, 0.55, "USE LIMIT", transform=info_ax.transAxes,
                 fontsize=9, color="#46606e", weight="bold")
    info_ax.text(0.0, 0.47, "mean removed", transform=info_ax.transAxes,
                 fontsize=10, color="#263845")
    info_ax.text(0.0, 0.40, "no absolute water-level offset", transform=info_ax.transAxes,
                 fontsize=10, color="#9a4e31", weight="bold")
    info_ax.text(0.0, 0.30, "OTHER BOUNDARIES", transform=info_ax.transAxes,
                 fontsize=9, color="#46606e", weight="bold")
    info_ax.text(0.0, 0.22, "N / O / G: constant inferred Q", transform=info_ax.transAxes,
                 fontsize=9.3, color="#263845")
    info_ax.text(0.0, 0.15, "during each 500-step case", transform=info_ax.transAxes,
                 fontsize=9.3, color="#263845")
    info_ax.text(0.0, 0.06, "LEGACY KERNEL", transform=info_ax.transAxes,
                 fontsize=9, color="#9a4e31", weight="bold")
    info_ax.text(0.36, 0.06,
                 f"{coverage['summary']['semanticallyApplied']} / {coverage['approvedCaseDimensions']} inputs correct; DO NOT RUN",
                 transform=info_ax.transAxes, fontsize=9, color="#263845", weight="bold")

    decision_ax.set_axis_off()
    decision_ax.axhline(0.98, color="#cbd6dc", linewidth=1.0)
    decision_ax.text(0.0, 0.73, "ONE DECISION", transform=decision_ax.transAxes,
                     fontsize=9, color="#46606e", weight="bold")
    decision_ax.text(
        0.12,
        0.73,
        "Use this mean-removed Hakata curve as the relative M-boundary reference for solver integration?",
        transform=decision_ax.transAxes,
        fontsize=10.5,
        color="#263845",
        weight="bold",
    )
    decision_ax.text(0.0, 0.39, "APPROVES", transform=decision_ax.transAxes,
                     fontsize=8.5, color="#33766f", weight="bold")
    decision_ax.text(0.12, 0.39,
                     "curve selection + phase/amplitude envelope + constant inferred N/O/G discharge",
                     transform=decision_ax.transAxes, fontsize=8.8, color="#263845")
    decision_ax.text(0.0, 0.10, "DOES NOT", transform=decision_ax.transAxes,
                     fontsize=8.5, color="#9a4e31", weight="bold")
    decision_ax.text(0.12, 0.10,
                     "authorize a numerical run, absolute mouth level, physical Validation, public connection, or main merge",
                     transform=decision_ax.transAxes, fontsize=8.8, color="#263845")

    fig.suptitle(
        "Stage 19 input decision: exact tide curve for boundary M",
        x=0.055,
        y=0.955,
        ha="left",
        fontsize=17,
        color="#1f3440",
        weight="bold",
    )
    fig.text(
        0.055,
        0.912,
        "JMA Hakata astronomical prediction is used only as a relative secondary reference; zero numerical cases have started.",
        fontsize=10,
        color="#5b707d",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, facecolor=fig.get_facecolor(),
                metadata={"Software": "onga-stage19-m-boundary-tide-renderer-v1"})
    plt.close(fig)


def main() -> None:
    args = parse_args()
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    coverage = json.loads(Path(args.coverage).read_text(encoding="utf-8"))
    output = Path(args.output)
    render(candidate, coverage, output)
    print(json.dumps({"status": "rendered", "output": str(output), "width": 2100, "height": 1260}))


if __name__ == "__main__":
    main()
