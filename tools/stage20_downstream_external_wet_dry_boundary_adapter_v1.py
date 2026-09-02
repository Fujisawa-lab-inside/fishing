#!/usr/bin/env python3
"""Mask individually dry tributary faces without hiding a dry section.

The depth-weighted river boundary distributes a prescribed discharge over a
multi-face section.  A bank-edge face may become numerically dry while the
rest of the section remains wet.  Such a face is treated as a reflective wall
for the current step.  A nonzero-discharge section still fails closed when no
wet face remains.
"""

from __future__ import annotations

from typing import Any

import numpy as np


ADAPTER_VERSION = "stage20-downstream-external-wet-dry-boundary-adapter-v1"
RIVER_BOUNDARY_DRY_DEPTH_M = 1.0e-8


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{ADAPTER_VERSION}] {message}")


def build_safe_boundary_tags(
    state: np.ndarray,
    boundary_cells: np.ndarray,
    boundary_lengths: np.ndarray,
    boundary_tags: np.ndarray,
    target_discharge_by_tag: np.ndarray,
    *,
    dry_depth_m: float = RIVER_BOUNDARY_DRY_DEPTH_M,
) -> dict[str, Any]:
    """Return per-step tags with dry river faces converted to walls."""

    values = np.asarray(state, dtype=np.float64)
    cells = np.asarray(boundary_cells, dtype=np.int64)
    lengths = np.asarray(boundary_lengths, dtype=np.float64)
    tags = np.asarray(boundary_tags)
    discharge = np.asarray(target_discharge_by_tag, dtype=np.float64)
    threshold = float(dry_depth_m)

    require(values.ndim == 2 and values.shape[1] == 3, "state must have h, hu, hv columns")
    require(cells.ndim == lengths.ndim == tags.ndim == 1, "boundary arrays must be one-dimensional")
    require(len(cells) == len(lengths) == len(tags), "boundary array lengths differ")
    require(discharge.ndim == 1 and len(discharge) >= 5, "discharge tag array is too short")
    require(np.isfinite(threshold) and threshold > 0.0, "dry-depth threshold is invalid")
    require(bool(np.all((0 <= cells) & (cells < len(values)))), "boundary cell is out of range")
    require(bool(np.isfinite(lengths).all()) and bool(np.all(lengths > 0.0)), "boundary length is invalid")
    require(bool(np.isfinite(discharge).all()), "boundary discharge is nonfinite")

    safe_tags = tags.copy()
    wet_face_count = np.zeros(len(discharge), dtype=np.int64)
    dry_face_count = np.zeros(len(discharge), dtype=np.int64)
    wet_depth_length = np.zeros(len(discharge), dtype=np.float64)
    original_face_count = np.zeros(len(discharge), dtype=np.int64)

    for face, tag_value in enumerate(tags):
        tag = int(tag_value)
        if tag < 2:
            continue
        require(tag < len(discharge), f"unknown river boundary tag: {tag}")
        depth = float(values[cells[face], 0])
        require(np.isfinite(depth) and depth >= 0.0, "river boundary depth is invalid")
        original_face_count[tag] += 1
        if depth < threshold:
            safe_tags[face] = 0
            dry_face_count[tag] += 1
        else:
            wet_face_count[tag] += 1
            wet_depth_length[tag] += depth * lengths[face]

    for tag in range(2, len(discharge)):
        requested = abs(float(discharge[tag]))
        if requested > 0.0:
            require(original_face_count[tag] > 0, f"river boundary section is missing: tag {tag}")
            require(
                wet_face_count[tag] > 0 and wet_depth_length[tag] > 1.0e-12,
                f"river boundary section is fully dry: tag {tag}",
            )

    return {
        "schema": "onga-stage20-downstream-external-wet-dry-boundary-step-v1",
        "boundaryTags": safe_tags,
        "wetFaceCountByTag": wet_face_count,
        "dryFaceCountByTag": dry_face_count,
        "wetDepthLengthM2ByTag": wet_depth_length,
        "dryDepthThresholdM": threshold,
        "policy": "INDIVIDUAL_DRY_FACE_AS_WALL_FAIL_IF_NONZERO_SECTION_FULLY_DRY",
    }
