#!/usr/bin/env python3
"""Validate the exact fixed v3 map raster without starting numerical cases."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import evaluate_stage18_full64_v2 as evaluator
from stage18_full64_v3_profile import (
    CONTRACT_PATH,
    EXPECTED_MAP_RASTER,
    configure_evaluator,
)


configure_evaluator(evaluator)

import aggregate_stage18_full64_v2 as aggregate  # noqa: E402


SCHEMA = 'onga-stage18-full64-v3-map-raster-preflight-v1'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh')
    parser.add_argument('--contract', default=CONTRACT_PATH)
    parser.add_argument('--output')
    args = parser.parse_args()

    mesh_path = Path(args.mesh).resolve()
    contract_path = Path(args.contract).resolve()
    contract = evaluator.load_json_object(contract_path)
    evaluator.validate_contract(contract)
    require(
        aggregate.PNG_WIDTH == EXPECTED_MAP_RASTER['pngWidth']
        and aggregate.PNG_HEIGHT == EXPECTED_MAP_RASTER['pngHeight'],
        'fixed v3 PNG dimensions changed',
    )
    require(
        evaluator.CELL_COUNT == EXPECTED_MAP_RASTER['representedCellCountRequired'],
        'fixed v3 mesh cell count changed',
    )
    require(
        evaluator.sha256_file(mesh_path) == evaluator.MESH_PACKAGE_SHA256,
        'exact corrected-v2 mesh digest changed',
    )
    vertices, triangles = aggregate.load_mesh_geometry(mesh_path, contract)
    grid, bounds, coverage = aggregate.build_cell_raster(
        vertices,
        triangles,
        width=aggregate.PNG_WIDTH,
        height=aggregate.PNG_HEIGHT,
    )

    import numpy as np

    visible = grid[grid >= 0]
    pixel_counts = np.bincount(visible, minlength=evaluator.CELL_COUNT)
    require(pixel_counts.shape == (evaluator.CELL_COUNT,), 'raster cell count changed')
    require(
        int(np.count_nonzero(pixel_counts))
        == EXPECTED_MAP_RASTER['representedCellCountRequired'],
        'not every cell is represented',
    )
    require(
        int(np.min(pixel_counts)) >= EXPECTED_MAP_RASTER['minimumPixelsPerCellRequired'],
        'one or more cells have no raster pixel',
    )
    require(
        coverage['representedCellCount']
        == EXPECTED_MAP_RASTER['representedCellCountRequired'],
        'represented-cell count changed',
    )
    require(
        coverage['coverageFraction'] == EXPECTED_MAP_RASTER['coverageFractionRequired'],
        'raster coverage is incomplete',
    )
    require(coverage['squarePixels'] is EXPECTED_MAP_RASTER['squarePixels'],
            'raster pixels are not square')
    require(
        coverage['rasterization'] == EXPECTED_MAP_RASTER['rasterization'],
        'rasterization method changed',
    )
    require(
        math.isclose(
            float(coverage['pixelSizeLocalM']),
            EXPECTED_MAP_RASTER['pixelSizeLocalMRequired'],
            rel_tol=1e-12,
            abs_tol=1e-12,
        ),
        'square-pixel size changed',
    )
    require(
        math.isclose(
            float(coverage['boundsExpansionLocalM']['xTotal']),
            0.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        'v3 raster unexpectedly expanded the x bounds',
    )
    require(
        math.isclose(
            float(coverage['boundsExpansionLocalM']['yTotal']),
            EXPECTED_MAP_RASTER['yBoundsExpansionTotalLocalMRequired'],
            rel_tol=1e-12,
            abs_tol=1e-9,
        ),
        'v3 square-pixel y expansion changed',
    )
    require(
        int(pixel_counts[320]) == EXPECTED_MAP_RASTER['cell320MinimumPixelsRequired'],
        'boundary cell 320 must occupy exactly one raster pixel',
    )

    result = {
        'schema': SCHEMA,
        'status': 'passed',
        'numericalCasesStarted': 0,
        'meshSha256': evaluator.sha256_file(mesh_path),
        'cellCount': evaluator.CELL_COUNT,
        'pngWidth': aggregate.PNG_WIDTH,
        'pngHeight': aggregate.PNG_HEIGHT,
        'boundsLocalM': bounds,
        **coverage,
        'minimumPixelsPerCell': int(np.min(pixel_counts)),
        'maximumPixelsPerCell': int(np.max(pixel_counts)),
        'cell320PixelCount': int(pixel_counts[320]),
    }
    payload = f'{json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)}\n'
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8') as handle:
            handle.write(payload)
    print(payload, end='')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f'[stage18-full64-v3-map-raster] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
