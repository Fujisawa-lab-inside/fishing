#!/usr/bin/env python3
"""Aggregate accepted v2 fields and atomically create the five-map result bundle."""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import math
import os
import struct
import zlib
from pathlib import Path
from typing import Any

from evaluate_stage18_full64_v2 import (
    CASE_COUNT,
    CELL_COUNT,
    COMPARISON_BASIS,
    ENSEMBLE_SHA256,
    EVALUATION_SCHEMA,
    MESH_PACKAGE_SHA256,
    ValidationError,
    evaluate_evidence,
    inspect_fields,
    load_json_object,
    require,
    sha256_file,
    validate_contract,
)


STATISTICS_SCHEMA = 'onga-stage18-full64-step-matched-statistics-v2'
SUMMARY_SCHEMA = 'onga-stage18-full64-step-matched-statistics-summary-v2'
MANIFEST_SCHEMA = 'onga-stage18-full64-visual-manifest-v2'
CLASSIFICATION = 'provisional_step_matched_numerical_endpoint_statistics_not_physical_validation'

STATISTICS_NAME = 'full64-statistics.npz'
SUMMARY_NAME = 'full64-statistics-summary.json'
MANIFEST_NAME = 'full64-visual-manifest.json'
PNG_WIDTH = 3840
PNG_HEIGHT = 2640
DRY_THRESHOLD_M = 1e-6
DIRECTION_SPEED_THRESHOLD_MS = 1e-6
DIRECTION_AGREEMENT_MIN_SAMPLES = 2

MAP_SPECS = (
    {
        'filename': 'full64-depth-median.png',
        'field': 'water_depth_median_m',
        'title': '水深中央値 / Median water depth',
        'units': 'm',
        'palette': ((220, 247, 246), (107, 207, 211), (42, 130, 186), (8, 48, 107)),
        'fixedRange': None,
    },
    {
        'filename': 'full64-velocity-median.png',
        'field': 'velocity_median_ms',
        'title': '流速中央値 / Median velocity',
        'units': 'm/s',
        'palette': ((255, 247, 188), (253, 174, 97), (221, 60, 87), (103, 24, 107)),
        'fixedRange': None,
    },
    {
        'filename': 'full64-wet-probability.png',
        'field': 'wet_probability',
        'title': '湿潤確率 / Wet probability',
        'units': 'fraction',
        'palette': ((247, 242, 224), (143, 205, 181), (37, 139, 111), (6, 78, 59)),
        'fixedRange': (0.0, 1.0),
    },
    {
        'filename': 'full64-direction-agreement.png',
        'field': 'flow_direction_agreement_fraction',
        'title': '流向一致度 / Direction agreement',
        'units': 'fraction',
        'palette': ((245, 235, 255), (196, 163, 230), (126, 82, 178), (76, 29, 149)),
        'fixedRange': (0.0, 1.0),
    },
    {
        'filename': 'full64-direction-support.png',
        'field': 'direction_sample_support_fraction',
        'title': '流向サンプル率 / Direction sample support',
        'units': 'fraction',
        'palette': ((244, 247, 246), (173, 216, 230), (55, 150, 162), (7, 78, 89)),
        'fixedRange': (0.0, 1.0),
    },
)

BUNDLE_NAMES = {
    STATISTICS_NAME,
    SUMMARY_NAME,
    MANIFEST_NAME,
    *(spec['filename'] for spec in MAP_SPECS),
}


def array_sha256(values: Any) -> str:
    return hashlib.sha256(values.tobytes(order='C')).hexdigest()


def scalar_text(archive: Any, name: str) -> str:
    require(name in archive.files, f'statistics archive is missing {name}')
    value = archive[name]
    require(value.shape == () and value.dtype.kind in ('U', 'S'), f'{name} must be a string scalar')
    raw = value.item()
    return raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)


def require_close(actual: float, expected: float, label: str) -> None:
    require(math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-15),
            f'{label} mismatch')


def compute_statistics(
    depth: Any,
    velocity_u: Any,
    velocity_v: Any,
    *,
    dry_threshold_m: float = DRY_THRESHOLD_M,
    direction_speed_threshold_ms: float = DIRECTION_SPEED_THRESHOLD_MS,
) -> dict[str, Any]:
    """Compute step-matched endpoint statistics for any small or full fixture."""
    import numpy as np

    depth = np.asarray(depth, dtype=np.float64)
    velocity_u = np.asarray(velocity_u, dtype=np.float64)
    velocity_v = np.asarray(velocity_v, dtype=np.float64)
    require(depth.ndim == 2 and depth.shape == velocity_u.shape == velocity_v.shape,
            'depth and velocity fields must have one shared case-by-cell shape')
    require(depth.shape[0] > 0 and depth.shape[1] > 0, 'field fixture must not be empty')
    require(np.isfinite(depth).all() and np.isfinite(velocity_u).all() and np.isfinite(velocity_v).all(),
            'field fixture contains a non-finite value')
    require(np.all(depth >= 0), 'field fixture contains a negative depth')
    require(math.isfinite(dry_threshold_m) and dry_threshold_m >= 0, 'dry threshold must be nonnegative')
    require(math.isfinite(direction_speed_threshold_ms) and direction_speed_threshold_ms >= 0,
            'direction speed threshold must be nonnegative')

    speed = np.hypot(velocity_u, velocity_v)
    velocity_quantiles = np.quantile(speed, [0.025, 0.25, 0.5, 0.75, 0.975], axis=0)
    depth_quantiles = np.quantile(depth, [0.025, 0.25, 0.5, 0.75, 0.975], axis=0)
    wet_probability = np.mean(depth > dry_threshold_m, axis=0, dtype=np.float64)

    active = (depth > dry_threshold_m) & (speed > direction_speed_threshold_ms)
    unit_u = np.divide(velocity_u, speed, out=np.zeros_like(velocity_u), where=active)
    unit_v = np.divide(velocity_v, speed, out=np.zeros_like(velocity_v), where=active)
    active_count = np.sum(active, axis=0, dtype=np.int64)
    mean_unit_u = np.divide(
        np.sum(unit_u, axis=0), active_count,
        out=np.zeros(depth.shape[1], dtype=np.float64), where=active_count > 0,
    )
    mean_unit_v = np.divide(
        np.sum(unit_v, axis=0), active_count,
        out=np.zeros(depth.shape[1], dtype=np.float64), where=active_count > 0,
    )
    direction_agreement = np.clip(np.hypot(mean_unit_u, mean_unit_v), 0.0, 1.0)
    mean_direction = np.full(depth.shape[1], np.nan, dtype=np.float64)
    has_direction = active_count > 0
    mean_direction[has_direction] = np.arctan2(
        mean_unit_v[has_direction], mean_unit_u[has_direction],
    )

    velocity_p025, velocity_q1, velocity_median, velocity_q3, velocity_p975 = velocity_quantiles
    depth_p025, depth_q1, depth_median, depth_q3, depth_p975 = depth_quantiles
    return {
        'velocity_median_ms': velocity_median,
        'velocity_q1_ms': velocity_q1,
        'velocity_q3_ms': velocity_q3,
        'velocity_iqr_width_ms': velocity_q3 - velocity_q1,
        'velocity_p025_ms': velocity_p025,
        'velocity_p975_ms': velocity_p975,
        'velocity_p95_width_ms': velocity_p975 - velocity_p025,
        'water_depth_median_m': depth_median,
        'water_depth_q1_m': depth_q1,
        'water_depth_q3_m': depth_q3,
        'water_depth_iqr_width_m': depth_q3 - depth_q1,
        'water_depth_p025_m': depth_p025,
        'water_depth_p975_m': depth_p975,
        'water_depth_p95_width_m': depth_p975 - depth_p025,
        'wet_probability': wet_probability,
        'flow_direction_agreement_fraction': direction_agreement,
        'mean_flow_direction_rad': mean_direction,
        'active_direction_sample_count': active_count.astype(np.int16),
        'direction_sample_support_fraction': active_count.astype(np.float64) / depth.shape[0],
    }


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind + payload) & 0xffffffff
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', checksum)


def encode_png(rgb: Any) -> bytes:
    import numpy as np

    require(rgb.dtype == np.dtype(np.uint8) and rgb.ndim == 3 and rgb.shape[2] == 3,
            'RGB uint8 image required')
    height, width, _ = rgb.shape
    scanlines = b''.join(b'\x00' + np.ascontiguousarray(row).tobytes() for row in rgb)
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (
        b'\x89PNG\r\n\x1a\n'
        + png_chunk(b'IHDR', header)
        + png_chunk(b'IDAT', zlib.compress(scanlines, 9))
        + png_chunk(b'IEND', b'')
    )


def interpolate_palette(values: Any, low: float, high: float, colors: Any) -> Any:
    import numpy as np

    normalized = (
        np.zeros(values.shape, dtype=np.float64)
        if high <= low else np.clip((values - low) / (high - low), 0.0, 1.0)
    )
    scaled = normalized * (len(colors) - 1)
    lower = np.floor(scaled).astype(np.int16)
    upper = np.minimum(lower + 1, len(colors) - 1)
    fraction = (scaled - lower)[..., None]
    palette = np.asarray(colors, dtype=np.float64)
    return np.rint(palette[lower] * (1 - fraction) + palette[upper] * fraction).astype(np.uint8)


def build_cell_raster(
    vertices: Any,
    triangles: Any,
    *,
    width: int = PNG_WIDTH,
    height: int = PNG_HEIGHT,
) -> tuple[Any, list[float], dict[str, Any]]:
    import numpy as np
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds

    vertices = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.int32)
    require(vertices.ndim == 2 and vertices.shape[1] == 2, 'vertices must be N by 2')
    require(triangles.ndim == 2 and triangles.shape[1] == 3, 'triangles must be N by 3')
    require(width > 0 and height > 0, 'raster dimensions must be positive')
    require(np.isfinite(vertices).all(), 'vertices contain a non-finite value')
    require(np.all(triangles >= 0) and np.all(triangles < len(vertices)), 'triangle vertex index out of range')

    x_min, y_min = np.min(vertices, axis=0)
    x_max, y_max = np.max(vertices, axis=0)
    require(x_max > x_min and y_max > y_min, 'mesh bounds are degenerate')
    margin_x = max(1e-6, float(x_max - x_min) * 0.025)
    margin_y = max(1e-6, float(y_max - y_min) * 0.025)
    bounds = (x_min - margin_x, y_min - margin_y, x_max + margin_x, y_max + margin_y)
    transform = from_bounds(*bounds, width, height)

    def geometries():
        for cell_id, triangle in enumerate(triangles):
            points = vertices[triangle]
            ring = [(float(point[0]), float(point[1])) for point in points]
            ring.append(ring[0])
            yield {'type': 'Polygon', 'coordinates': [ring]}, cell_id

    grid = rasterize(
        geometries(), out_shape=(height, width), fill=-1,
        transform=transform, dtype=np.int32, all_touched=False,
    )
    require(np.any(grid >= 0), 'mesh rasterization produced no visible cells')
    represented = np.unique(grid[grid >= 0])
    expected = np.arange(len(triangles), dtype=np.int32)
    require(np.array_equal(represented, expected),
            f'mesh rasterization omitted {len(triangles) - represented.size} cells')
    return grid, [float(value) for value in bounds], {
        'representedCellCount': int(represented.size),
        'coverageFraction': float(represented.size / len(triangles)),
    }


def render_map(
    cell_grid: Any,
    values: Any,
    palette: Any,
    *,
    fixed_range: tuple[float, float] | None = None,
    valid_cells: Any | None = None,
) -> tuple[bytes, dict[str, Any]]:
    import numpy as np

    values = np.asarray(values, dtype=np.float64)
    require(values.ndim == 1 and np.isfinite(values).all(), 'map values must be a finite vector')
    if valid_cells is None:
        valid_cells = np.ones(values.shape, dtype=np.bool_)
    else:
        valid_cells = np.asarray(valid_cells, dtype=np.bool_)
    require(valid_cells.shape == values.shape, 'map validity mask shape changed')
    visible_values = values[valid_cells]
    if fixed_range is None:
        require(visible_values.size > 0, 'map has no eligible cells')
        low, high = (float(value) for value in np.quantile(visible_values, [0.02, 0.98]))
        if high <= low:
            low, high = float(np.min(visible_values)), float(np.max(visible_values))
    else:
        low, high = (float(value) for value in fixed_range)
    require(math.isfinite(low) and math.isfinite(high) and high >= low, 'map color range is invalid')

    image = np.empty((*cell_grid.shape, 3), dtype=np.uint8)
    image[:] = np.array([236, 241, 239], dtype=np.uint8)
    geometry_mask = cell_grid >= 0
    require(np.all(cell_grid[geometry_mask] < len(values)), 'raster cell ID exceeds value vector')
    image[geometry_mask] = np.array([174, 184, 180], dtype=np.uint8)
    eligible = np.zeros(cell_grid.shape, dtype=np.bool_)
    eligible[geometry_mask] = valid_cells[cell_grid[geometry_mask]]
    image[eligible] = interpolate_palette(values[cell_grid[eligible]], low, high, palette)
    return encode_png(image), {
        'dataMinimum': float(np.min(visible_values)) if visible_values.size else None,
        'dataMaximum': float(np.max(visible_values)) if visible_values.size else None,
        'colorScaleMinimum': low,
        'colorScaleMaximum': high,
        'colorScaleClipping': 'p02_p98' if fixed_range is None else 'fixed_0_1',
        'excludedCellCount': int(np.count_nonzero(~valid_cells)),
    }


def validate_evaluation_chain(
    contract_path: Path,
    authorization_path: Path,
    report_path: Path,
    fields_path: Path,
    evaluation_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_json_object(contract_path)
    authorization = load_json_object(authorization_path)
    report = load_json_object(report_path)
    evaluation = load_json_object(evaluation_path)
    validate_contract(contract)
    fields = inspect_fields(fields_path)
    require(Path(report.get('fieldArtifact', {}).get('path', '')).resolve() == fields_path.resolve(),
            'run report field path mismatch')
    expected = evaluate_evidence(
        contract,
        authorization,
        report,
        fields,
        contract_digest=sha256_file(contract_path),
        authorization_digest=sha256_file(authorization_path),
        report_digest=sha256_file(report_path),
    )
    require(evaluation == expected, 'evaluation is not the exact evaluation of the supplied sources')
    require(evaluation.get('schema') == EVALUATION_SCHEMA and evaluation.get('passed') is True,
            'statistics require a passing v2 evaluation')
    require(evaluation.get('offlineStepMatchedStatisticsAllowed') is True,
            'step-matched statistics are not authorized by evaluation')
    return contract, authorization, report, fields, evaluation


def load_mesh_geometry(mesh_path: Path, contract: dict[str, Any]) -> tuple[Any, Any]:
    import numpy as np

    require(sha256_file(mesh_path) == MESH_PACKAGE_SHA256, 'mesh package digest mismatch')
    expected = contract['meshExpected']['packageArrays']
    with np.load(mesh_path, allow_pickle=False) as package:
        require(package.files == list(expected), 'mesh package array order changed')
        for name, definition in expected.items():
            values = package[name]
            require(list(values.shape) == definition['shape'], f'mesh {name} shape changed')
            require(str(values.dtype) == definition['dtype'], f'mesh {name} dtype changed')
            require(array_sha256(values) == definition['sha256'], f'mesh {name} digest changed')
        vertices = package['vertex_local_mm'].astype(np.float64) * 1e-3
        triangles = package['triangles'].astype(np.int32, copy=True)
    require(triangles.shape == (CELL_COUNT, 3), 'mesh cell count changed')
    return vertices, triangles


def bounds(values: Any) -> dict[str, float]:
    import numpy as np

    return {'minimum': float(np.min(values)), 'maximum': float(np.max(values))}


def json_bytes(value: Any) -> bytes:
    return f'{json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)}\n'.encode('utf-8')


def write_bundle_atomic(output_dir: Path, files: dict[str, bytes]) -> None:
    require(set(files) == BUNDLE_NAMES, 'bundle output set changed')
    require(not output_dir.exists(), f'bundle output directory already exists: {output_dir}')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.with_name(f'.{output_dir.name}.{os.getpid()}.tmp')
    require(not staging.exists(), f'bundle staging directory already exists: {staging}')
    staging.mkdir()
    try:
        for name, payload in files.items():
            destination = staging / name
            with destination.open('xb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        os.rename(staging, output_dir)
    finally:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink()
            staging.rmdir()


def aggregate_and_render(
    mesh_path: str | Path,
    fields_path: str | Path,
    report_path: str | Path,
    evaluation_path: str | Path,
    authorization_path: str | Path,
    contract_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    import io
    import numpy as np

    paths = [
        Path(mesh_path), Path(fields_path), Path(report_path), Path(evaluation_path),
        Path(authorization_path), Path(contract_path),
    ]
    require(len({path.resolve() for path in paths}) == len(paths), 'aggregation input paths overlap')
    destination = Path(output_dir)
    require(not destination.exists(), f'bundle output directory already exists: {destination}')

    contract, authorization, report, field_evidence, evaluation = validate_evaluation_chain(
        Path(contract_path), Path(authorization_path), Path(report_path),
        Path(fields_path), Path(evaluation_path),
    )
    vertices, triangles = load_mesh_geometry(Path(mesh_path), contract)

    with np.load(fields_path, allow_pickle=False) as fields:
        depth = np.array(fields['water_depth_m'], dtype=np.float64, copy=True)
        velocity_u = np.array(fields['velocity_u_ms'], dtype=np.float64, copy=True)
        velocity_v = np.array(fields['velocity_v_ms'], dtype=np.float64, copy=True)
        mass_error = np.array(fields['mass_balance_error'], dtype=np.float64, copy=True)
        cfl_max = np.array(fields['cfl_max'], dtype=np.float64, copy=True)
        simulated_time = np.array(fields['simulated_time_seconds'], dtype=np.float64, copy=True)
    statistics = compute_statistics(depth, velocity_u, velocity_v)
    require(all(values.shape == (CELL_COUNT,) for values in statistics.values()),
            'full statistics vectors must contain 50,129 cells')

    source_digests = {
        'executionContractSha256': sha256_file(contract_path),
        'authorizationSha256': sha256_file(authorization_path),
        'runReportSha256': sha256_file(report_path),
        'fieldArtifactSha256': sha256_file(fields_path),
        'evaluationSha256': sha256_file(evaluation_path),
        'meshSha256': sha256_file(mesh_path),
        'meshSummarySha256': report['inputDigests']['meshSummarySha256'],
        'ensembleSha256': ENSEMBLE_SHA256,
    }
    statistics_arrays = {
        'schema': np.array(STATISTICS_SCHEMA),
        'cell_id': np.arange(CELL_COUNT, dtype=np.int32),
        **statistics,
        'dry_threshold_m': np.array(DRY_THRESHOLD_M, dtype=np.float64),
        'direction_speed_threshold_ms': np.array(DIRECTION_SPEED_THRESHOLD_MS, dtype=np.float64),
        'source_execution_contract_sha256': np.array(source_digests['executionContractSha256']),
        'source_authorization_sha256': np.array(source_digests['authorizationSha256']),
        'source_run_report_sha256': np.array(source_digests['runReportSha256']),
        'source_fields_sha256': np.array(source_digests['fieldArtifactSha256']),
        'source_evaluation_sha256': np.array(source_digests['evaluationSha256']),
        'source_mesh_sha256': np.array(source_digests['meshSha256']),
        'source_mesh_summary_sha256': np.array(source_digests['meshSummarySha256']),
        'source_ensemble_sha256': np.array(source_digests['ensembleSha256']),
        'comparison_basis': np.array(COMPARISON_BASIS),
    }
    statistics_buffer = io.BytesIO()
    np.savez_compressed(statistics_buffer, **statistics_arrays)
    statistics_payload = statistics_buffer.getvalue()
    statistics_digest = hashlib.sha256(statistics_payload).hexdigest()

    summary = {
        'schema': SUMMARY_SCHEMA,
        'classification': CLASSIFICATION,
        'sourceCaseCount': CASE_COUNT,
        'cellCount': CELL_COUNT,
        'geometry': contract['geometry'],
        'comparisonBasis': COMPARISON_BASIS,
        'simulatedTimeSeconds': bounds(simulated_time),
        'dryThresholdM': DRY_THRESHOLD_M,
        'directionSpeedThresholdMs': DIRECTION_SPEED_THRESHOLD_MS,
        'fields': {
            'velocityMedianMs': bounds(statistics['velocity_median_ms']),
            'velocityIqrWidthMs': bounds(statistics['velocity_iqr_width_ms']),
            'velocityP95WidthMs': bounds(statistics['velocity_p95_width_ms']),
            'waterDepthMedianM': bounds(statistics['water_depth_median_m']),
            'waterDepthIqrWidthM': bounds(statistics['water_depth_iqr_width_m']),
            'waterDepthP95WidthM': bounds(statistics['water_depth_p95_width_m']),
            'wetProbability': bounds(statistics['wet_probability']),
            'flowDirectionAgreementFraction': bounds(statistics['flow_direction_agreement_fraction']),
            'directionSampleSupportFraction': bounds(statistics['direction_sample_support_fraction']),
        },
        'runDiagnostics': {
            'massBalanceAbsoluteMedian': float(np.median(np.abs(mass_error))),
            'massBalanceAbsoluteMaximum': float(np.max(np.abs(mass_error))),
            'maxCfl': float(np.max(cfl_max)),
        },
        'parameterCoverage': contract['parameterCoverage'],
        'interpretationLimits': {
            'commonPhysicalTime': False,
            'waterSurfaceElevationAvailable': False,
            'sensitivityClaimAllowed': False,
            'physicalValidationClaimAllowed': False,
            'publicSimulatorConnectionAllowed': False,
        },
        'artifacts': {
            **source_digests,
            'statisticsSha256': statistics_digest,
        },
    }
    summary_payload = json_bytes(summary)
    summary_digest = hashlib.sha256(summary_payload).hexdigest()

    cell_grid, raster_bounds, coverage = build_cell_raster(vertices, triangles)
    map_payloads: dict[str, bytes] = {}
    map_metadata: dict[str, Any] = {}
    for spec in MAP_SPECS:
        values = statistics[spec['field']]
        valid_cells = (
            statistics['active_direction_sample_count'] >= DIRECTION_AGREEMENT_MIN_SAMPLES
            if spec['filename'] == 'full64-direction-agreement.png' else None
        )
        payload, metadata = render_map(
            cell_grid, values, spec['palette'],
            fixed_range=spec['fixedRange'], valid_cells=valid_cells,
        )
        map_payloads[spec['filename']] = payload
        map_metadata[spec['filename']] = {
            'title': spec['title'],
            'units': spec['units'],
            'paletteRgb': [list(color) for color in spec['palette']],
            **metadata,
            'sha256': hashlib.sha256(payload).hexdigest(),
            'mediaType': 'image/png',
            'width': PNG_WIDTH,
            'height': PNG_HEIGHT,
        }

    manifest = {
        'schema': MANIFEST_SCHEMA,
        'status': 'generated',
        'classification': CLASSIFICATION,
        'sourceCaseCount': CASE_COUNT,
        'cellCount': CELL_COUNT,
        'comparisonBasis': COMPARISON_BASIS,
        'sources': {
            **source_digests,
            'statisticsSha256': statistics_digest,
            'statisticsSummarySha256': summary_digest,
        },
        'outputs': map_metadata,
        'visualization': {
            'pngWidth': PNG_WIDTH,
            'pngHeight': PNG_HEIGHT,
            'boundsLocalM': raster_bounds,
            **coverage,
            'directionAgreementMinimumActiveSamples': DIRECTION_AGREEMENT_MIN_SAMPLES,
            'directionSampleSupport': {
                'definition': 'active_direction_sample_count_divided_by_case_count',
                'denominatorCaseCount': CASE_COUNT,
            },
        },
        'mapAvailability': {name: True for name in map_payloads},
        'interpretationLimits': summary['interpretationLimits'],
        'decisionSvgReady': True,
    }
    manifest_payload = json_bytes(manifest)
    files = {
        STATISTICS_NAME: statistics_payload,
        SUMMARY_NAME: summary_payload,
        MANIFEST_NAME: manifest_payload,
        **map_payloads,
    }
    write_bundle_atomic(destination, files)
    return {
        'outputDirectory': str(destination),
        'statisticsSha256': statistics_digest,
        'summarySha256': summary_digest,
        'manifestSha256': sha256_file(destination / MANIFEST_NAME),
        'mapCount': len(map_payloads),
        'representedCellCount': coverage['representedCellCount'],
        'evaluationPassed': evaluation['passed'],
        'executionAuthorized': authorization['authorized'],
        'fieldShape': field_evidence['shape'],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh')
    parser.add_argument('fields')
    parser.add_argument('report')
    parser.add_argument('evaluation')
    parser.add_argument('authorization')
    parser.add_argument('contract')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    result = aggregate_and_render(
        args.mesh, args.fields, args.report, args.evaluation,
        args.authorization, args.contract, args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ValidationError) as error:
        print(f'[stage18-full64-v2-aggregate] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
