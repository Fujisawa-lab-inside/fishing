#!/usr/bin/env python3
"""Validate the exact corrected-v2 mesh map raster without numerical cases."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from aggregate_stage18_full64_v2 import (
    CELL_COUNT,
    PNG_HEIGHT,
    PNG_WIDTH,
    build_cell_raster,
    load_mesh_geometry,
)
from evaluate_stage18_full64_v2 import (
    MESH_PACKAGE_SHA256,
    load_json_object,
    sha256_file,
    validate_contract,
)


SCHEMA = 'onga-stage18-full64-v2-map-raster-preflight-v1'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh')
    parser.add_argument(
        '--contract', default='config/stage18_full64_execution_contract_v2.json',
    )
    parser.add_argument('--output')
    args = parser.parse_args()

    mesh_path = Path(args.mesh).resolve()
    contract_path = Path(args.contract).resolve()
    contract = load_json_object(contract_path)
    validate_contract(contract)
    require(sha256_file(mesh_path) == MESH_PACKAGE_SHA256, 'exact corrected-v2 mesh digest changed')
    vertices, triangles = load_mesh_geometry(mesh_path, contract)
    grid, bounds, coverage = build_cell_raster(
        vertices, triangles, width=PNG_WIDTH, height=PNG_HEIGHT,
    )

    import numpy as np

    visible = grid[grid >= 0]
    pixel_counts = np.bincount(visible, minlength=CELL_COUNT)
    require(pixel_counts.shape == (CELL_COUNT,), 'raster cell count changed')
    require(int(np.count_nonzero(pixel_counts)) == CELL_COUNT, 'not every cell is represented')
    require(int(np.min(pixel_counts)) >= 1, 'one or more cells have no raster pixel')
    require(coverage['representedCellCount'] == CELL_COUNT, 'represented-cell count changed')
    require(coverage['coverageFraction'] == 1.0, 'raster coverage is incomplete')
    require(coverage['squarePixels'] is True, 'raster pixels are not square')
    require(
        math.isclose(
            float(coverage['boundsExpansionLocalM']['xTotal']), 0.0,
            rel_tol=0.0, abs_tol=1e-12,
        ),
        'corrected-v2 raster unexpectedly expanded the x bounds',
    )
    require(
        math.isclose(
            float(coverage['boundsExpansionLocalM']['yTotal']), 8.356359375,
            rel_tol=1e-12, abs_tol=1e-9,
        ),
        'corrected-v2 square-pixel y expansion changed',
    )
    require(int(pixel_counts[320]) == 1, 'boundary cell 320 must occupy exactly one raster pixel')

    result = {
        'schema': SCHEMA,
        'status': 'passed',
        'numericalCasesStarted': 0,
        'meshSha256': sha256_file(mesh_path),
        'cellCount': CELL_COUNT,
        'pngWidth': PNG_WIDTH,
        'pngHeight': PNG_HEIGHT,
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
        print(f'[stage18-full64-v2-map-raster] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
