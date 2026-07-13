#!/usr/bin/env python3
"""Render a provenance-bound visual judgment package for the Stage 18 full64 run."""

import argparse
import base64
import binascii
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from xml.sax.saxutils import escape
import zlib

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_bounds

from run_stage18_full64 import validate_authorization, validate_mesh_package


OUTPUT_NAMES = (
    'full64-depth-median.png',
    'full64-velocity-median.png',
    'full64-wet-probability.png',
    'full64-direction-agreement.png',
    'full64-direction-support.png',
    'full64-judgment.svg',
    'full64-visual-manifest.json',
)
CLASSIFICATION = 'provisional_step_matched_numerical_endpoint_statistics_not_physical_validation'
COMPARISON_BASIS = 'equal_step_count_not_equal_simulated_time'
CELL_COUNT = 50333
CASE_COUNT = 64
DIRECTION_AGREEMENT_MIN_SAMPLES = 2
PNG_WIDTH = 3840
PNG_HEIGHT = 2640
INTERPRETATION_LIMITS = {
    'commonPhysicalTime': False,
    'physicalValidationClaimAllowed': False,
    'sensitivityClaimAllowed': False,
    'publicSimulatorConnectionAllowed': False,
}
GRADIENT_STOP_OFFSETS = ('0%', '33.33%', '66.67%', '100%')
MAP_SPECS = (
    {
        'filename': 'full64-depth-median.png',
        'field': 'water_depth_median_m',
        'title': '水深中央値 / Median water depth',
        'unit': 'm',
        'palette': ((220, 247, 246), (107, 207, 211), (42, 130, 186), (8, 48, 107)),
        'fixedRange': None,
    },
    {
        'filename': 'full64-velocity-median.png',
        'field': 'velocity_median_ms',
        'title': '流速中央値 / Median velocity',
        'unit': 'm/s',
        'palette': ((255, 247, 188), (253, 174, 97), (221, 60, 87), (103, 24, 107)),
        'fixedRange': None,
    },
    {
        'filename': 'full64-wet-probability.png',
        'field': 'wet_probability',
        'title': '湿潤確率 / Wet probability',
        'unit': 'fraction',
        'palette': ((247, 242, 224), (143, 205, 181), (37, 139, 111), (6, 78, 59)),
        'fixedRange': (0.0, 1.0),
    },
    {
        'filename': 'full64-direction-agreement.png',
        'field': 'flow_direction_agreement_fraction',
        'title': '流向一致度 / Direction agreement',
        'unit': 'fraction',
        'palette': ((245, 235, 255), (196, 163, 230), (126, 82, 178), (76, 29, 149)),
        'fixedRange': (0.0, 1.0),
    },
    {
        'filename': 'full64-direction-support.png',
        'field': 'direction_sample_support_fraction',
        'title': '流向サンプル率 / Direction sample support',
        'unit': 'active cases / 64',
        'palette': ((244, 247, 246), (173, 216, 230), (55, 150, 162), (7, 78, 89)),
        'fixedRange': (0.0, 1.0),
    },
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def reject_json_constant(value):
    raise ValueError(f'nonstandard JSON constant: {value}')


def load_json(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=reject_json_constant)
    require(isinstance(value, dict), f'JSON object required: {path}')
    return value


def finite_number(value, label, nonnegative=False):
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f'{label} must be numeric')
    require(math.isfinite(value), f'{label} must be finite')
    if nonnegative:
        require(value >= 0, f'{label} must be nonnegative')
    return float(value)


def require_close(actual, expected, label):
    actual = finite_number(actual, label)
    expected = finite_number(expected, f'{label} expected')
    require(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15), f'{label} mismatch')


def scalar_text(archive, key):
    require(key in archive.files, f'missing statistics array: {key}')
    value = archive[key]
    require(value.shape == (), f'{key} must be scalar')
    require(value.dtype.kind in ('U', 'S'), f'{key} must be text')
    return str(value.item())


def scalar_float64(archive, key):
    require(key in archive.files, f'missing statistics array: {key}')
    value = archive[key]
    require(value.shape == () and value.dtype == np.dtype(np.float64), f'{key} must be scalar float64')
    result = float(value.item())
    require(math.isfinite(result), f'{key} must be finite')
    return result


def float64_vector(archive, key):
    require(key in archive.files, f'missing statistics array: {key}')
    value = np.array(archive[key], copy=True)
    require(value.shape == (CELL_COUNT,), f'{key} shape mismatch')
    require(value.dtype == np.dtype(np.float64), f'{key} dtype must be float64')
    require(np.isfinite(value).all(), f'{key} contains nonfinite values')
    return value


def bounds_match(summary_fields, key, values):
    entry = summary_fields.get(key)
    require(isinstance(entry, dict), f'summary field missing: {key}')
    require_close(entry.get('minimum'), float(np.min(values)), f'{key}.minimum')
    require_close(entry.get('maximum'), float(np.max(values)), f'{key}.maximum')


def validate_report(report, authorization, source_digests):
    require(report.get('schema') == 'onga-stage18-full64-run-report-v1', 'unsupported run report schema')
    require(report.get('classification') == 'provisional_full64_runtime_and_numerical_stability_evidence_only', 'run report classification changed')
    require(report.get('requestedCaseCount') == CASE_COUNT, 'run report must request 64 cases')
    require(report.get('completedCaseCount') == CASE_COUNT, 'run report must complete 64 cases')
    require(report.get('failedCaseCount') == 0, 'run report contains failed cases')
    expected_ids = [f'stage18-{index:04d}' for index in range(1, CASE_COUNT + 1)]
    require(report.get('attemptedCaseIds') == expected_ids, 'run report case IDs mismatch')
    require(report.get('failures') == [], 'run report failure list must be empty')
    require(report.get('geometry') == authorization.get('geometry'), 'run report geometry mismatch')
    require(report.get('ensembleSeed') == authorization.get('run', {}).get('ensembleSeed'), 'run report ensemble seed mismatch')
    require(report.get('comparisonBasis') == COMPARISON_BASIS, 'run report comparison basis mismatch')
    require(report.get('parameterCoverage') == authorization.get('parameterCoverage'), 'run report parameter coverage mismatch')
    require(report.get('safeguards') == authorization.get('safeguards'), 'run report safeguards mismatch')
    require(report.get('meshSummaryVerified') is True, 'mesh summary was not verified')
    require(report.get('protectedSurfaceHashesUnchanged') is True, 'protected surfaces changed')

    digests = report.get('inputDigests', {})
    require(digests.get('meshSha256') == source_digests['mesh'], 'run report mesh digest mismatch')
    require(digests.get('authorizationSha256') == source_digests['authorization'], 'run report authorization digest mismatch')
    require(digests.get('meshSummarySha256') == authorization['meshExpected']['summarySha256'], 'run report mesh-summary digest mismatch')
    require(digests.get('ensembleSha256') == authorization['ensembleExpected']['sha256'], 'run report ensemble digest mismatch')

    field = report.get('fieldArtifact', {})
    require(field.get('shape') == {'caseCount': CASE_COUNT, 'cellCount': CELL_COUNT}, 'run report field shape mismatch')
    require(field.get('dtype') == 'float64', 'run report field dtype mismatch')
    field_digest = field.get('sha256')
    require(
        isinstance(field_digest, str)
        and len(field_digest) == 64
        and all(character in '0123456789abcdef' for character in field_digest),
        'run report field digest missing',
    )

    acceptance = authorization['acceptance']
    nan_count = report.get('nanCount')
    negative_count = report.get('negativeDepthCount')
    require(isinstance(nan_count, int) and not isinstance(nan_count, bool), 'nanCount must be an integer')
    require(isinstance(negative_count, int) and not isinstance(negative_count, bool), 'negativeDepthCount must be an integer')
    require(0 <= nan_count <= acceptance['nanCountMax'], 'NaN count exceeds authorization')
    require(0 <= negative_count <= acceptance['negativeDepthCountMax'], 'negative-depth count exceeds authorization')
    metrics = {
        'maxCfl': 'maxCflMax',
        'maxAbsoluteMassBalanceError': 'maxAbsoluteMassBalanceErrorMax',
        'wallSeconds': 'maxWallSeconds',
        'peakResidentMemoryMiB': 'maxResidentMemoryMiB',
    }
    for report_key, acceptance_key in metrics.items():
        actual = finite_number(report.get(report_key), f'report {report_key}', nonnegative=True)
        limit = finite_number(acceptance.get(acceptance_key), f'acceptance {acceptance_key}', nonnegative=True)
        require(actual <= limit, f'{report_key} exceeds authorization')
    finite_number(report.get('minimumDepthM'), 'report minimumDepthM', nonnegative=True)


def validate_evaluation(evaluation, report, authorization, source_digests):
    require(evaluation.get('schema') == 'onga-stage18-full64-evaluation-v1', 'unsupported evaluation schema')
    require(evaluation.get('classification') == 'provisional_full64_runtime_and_numerical_stability_evidence_only', 'evaluation classification changed')
    require(evaluation.get('passed') is True, 'full64 evaluation did not pass')
    require(evaluation.get('offlineStepMatchedStatisticsAllowed') is True, 'offline statistics are not allowed')
    for key in ('sensitivityClaimAllowed', 'physicalValidationClaimAllowed', 'publicSimulatorConnectionAllowed', 'automaticAdditionalRunAuthorized'):
        require(evaluation.get(key) is False, f'evaluation safeguard changed: {key}')
    require_close(evaluation.get('completionFraction'), 1.0, 'evaluation completion fraction')
    checks = evaluation.get('checks')
    require(isinstance(checks, dict) and checks, 'evaluation checks missing')
    require(all(value is True for value in checks.values()), 'one or more evaluation checks failed')
    provenance = evaluation.get('provenance', {})
    require(provenance.get('authorizationSha256') == source_digests['authorization'], 'evaluation authorization digest mismatch')
    require(provenance.get('runReportSha256') == source_digests['runReport'], 'evaluation run-report digest mismatch')
    require(provenance.get('fieldArtifactSha256') == report['fieldArtifact']['sha256'], 'evaluation field digest mismatch')
    require(provenance.get('meshSha256') == source_digests['mesh'], 'evaluation mesh digest mismatch')
    require(provenance.get('meshSummarySha256') == authorization['meshExpected']['summarySha256'], 'evaluation mesh-summary digest mismatch')
    require(provenance.get('ensembleSha256') == authorization['ensembleExpected']['sha256'], 'evaluation ensemble digest mismatch')


def validate_statistics(path, report, source_digests):
    expected_arrays = {
        'schema', 'cell_id',
        'velocity_median_ms', 'velocity_q1_ms', 'velocity_q3_ms', 'velocity_iqr_width_ms',
        'velocity_p025_ms', 'velocity_p975_ms', 'velocity_p95_width_ms',
        'water_depth_median_m', 'water_depth_q1_m', 'water_depth_q3_m', 'water_depth_iqr_width_m',
        'water_depth_p025_m', 'water_depth_p975_m', 'water_depth_p95_width_m',
        'wet_probability', 'flow_direction_agreement_fraction', 'mean_flow_direction_rad',
        'active_direction_sample_count', 'dry_threshold_m', 'direction_speed_threshold_ms',
        'source_fields_sha256', 'source_run_report_sha256', 'source_evaluation_sha256',
        'source_authorization_sha256', 'comparison_basis',
    }
    with np.load(path, allow_pickle=False) as archive:
        require(set(archive.files) == expected_arrays, 'statistics arrays changed')
        require(scalar_text(archive, 'schema') == 'onga-stage18-full64-step-matched-statistics-v1', 'unsupported statistics schema')
        require(scalar_text(archive, 'comparison_basis') == COMPARISON_BASIS, 'statistics comparison basis mismatch')
        require(scalar_text(archive, 'source_fields_sha256') == report['fieldArtifact']['sha256'], 'statistics source-field digest mismatch')
        require(scalar_text(archive, 'source_run_report_sha256') == source_digests['runReport'], 'statistics run-report digest mismatch')
        require(scalar_text(archive, 'source_evaluation_sha256') == source_digests['evaluation'], 'statistics evaluation digest mismatch')
        require(scalar_text(archive, 'source_authorization_sha256') == source_digests['authorization'], 'statistics authorization digest mismatch')
        cell_id = archive['cell_id']
        require(cell_id.dtype == np.dtype(np.int32) and np.array_equal(cell_id, np.arange(CELL_COUNT, dtype=np.int32)), 'statistics cell IDs mismatch')

        names = (
            'velocity_median_ms', 'velocity_q1_ms', 'velocity_q3_ms', 'velocity_iqr_width_ms',
            'velocity_p025_ms', 'velocity_p975_ms', 'velocity_p95_width_ms',
            'water_depth_median_m', 'water_depth_q1_m', 'water_depth_q3_m', 'water_depth_iqr_width_m',
            'water_depth_p025_m', 'water_depth_p975_m', 'water_depth_p95_width_m',
            'wet_probability', 'flow_direction_agreement_fraction',
        )
        values = {name: float64_vector(archive, name) for name in names}
        direction = np.array(archive['mean_flow_direction_rad'], copy=True)
        active_count = np.array(archive['active_direction_sample_count'], copy=True)
        require(direction.shape == (CELL_COUNT,) and direction.dtype == np.dtype(np.float64), 'mean direction contract mismatch')
        require(active_count.shape == (CELL_COUNT,) and active_count.dtype == np.dtype(np.int16), 'active direction count contract mismatch')
        require(np.all((active_count >= 0) & (active_count <= CASE_COUNT)), 'active direction count outside 0..64')
        inactive = active_count == 0
        require(np.isnan(direction[inactive]).all(), 'inactive mean direction must be NaN')
        require(np.isfinite(direction[~inactive]).all(), 'active mean direction must be finite')
        require(np.all(np.abs(direction[~inactive]) <= math.pi + 1e-15), 'mean direction outside -pi..pi')

        dry_threshold = scalar_float64(archive, 'dry_threshold_m')
        speed_threshold = scalar_float64(archive, 'direction_speed_threshold_ms')
        require(dry_threshold >= 0 and speed_threshold >= 0, 'statistics thresholds must be nonnegative')

    for prefix in ('velocity', 'water_depth'):
        suffix = 'ms' if prefix == 'velocity' else 'm'
        p025 = values[f'{prefix}_p025_{suffix}']
        q1 = values[f'{prefix}_q1_{suffix}']
        median = values[f'{prefix}_median_{suffix}']
        q3 = values[f'{prefix}_q3_{suffix}']
        p975 = values[f'{prefix}_p975_{suffix}']
        require(np.all(p025 <= q1) and np.all(q1 <= median) and np.all(median <= q3) and np.all(q3 <= p975), f'{prefix} quantiles are unordered')
        require(np.allclose(values[f'{prefix}_iqr_width_{suffix}'], q3 - q1, rtol=1e-12, atol=1e-15), f'{prefix} IQR width mismatch')
        require(np.allclose(values[f'{prefix}_p95_width_{suffix}'], p975 - p025, rtol=1e-12, atol=1e-15), f'{prefix} P95 width mismatch')
        require(np.all(p025 >= 0), f'{prefix} contains negative values')
    for key in ('wet_probability', 'flow_direction_agreement_fraction'):
        require(np.all(values[key] >= -1e-15) and np.all(values[key] <= 1 + 1e-15), f'{key} outside 0..1')

    return values, dry_threshold, speed_threshold, active_count


def validate_summary(summary, statistics, report, authorization, source_digests, dry_threshold, speed_threshold):
    require(summary.get('schema') == 'onga-stage18-full64-step-matched-statistics-summary-v1', 'unsupported statistics summary schema')
    require(summary.get('classification') == CLASSIFICATION, 'statistics summary classification changed')
    require(summary.get('sourceCaseCount') == CASE_COUNT, 'statistics summary case count mismatch')
    require(summary.get('cellCount') == CELL_COUNT, 'statistics summary cell count mismatch')
    require(summary.get('geometry') == authorization['geometry'], 'statistics summary geometry mismatch')
    require(summary.get('comparisonBasis') == COMPARISON_BASIS, 'statistics summary comparison basis mismatch')
    require(summary.get('parameterCoverage') == authorization['parameterCoverage'], 'statistics summary parameter coverage mismatch')
    require_close(summary.get('dryThresholdM'), dry_threshold, 'statistics summary dry threshold')
    require_close(summary.get('directionSpeedThresholdMs'), speed_threshold, 'statistics summary direction threshold')
    limits = summary.get('interpretationLimits', {})
    for key, expected in INTERPRETATION_LIMITS.items():
        require(limits.get(key) is expected, f'statistics summary interpretation limit changed: {key}')
    require(limits.get('waterSurfaceElevationAvailable') is False, 'water-surface availability changed')

    artifacts = summary.get('artifacts', {})
    require(artifacts.get('sourceFieldsSha256') == report['fieldArtifact']['sha256'], 'summary field digest mismatch')
    require(artifacts.get('runReportSha256') == source_digests['runReport'], 'summary run-report digest mismatch')
    require(artifacts.get('evaluationSha256') == source_digests['evaluation'], 'summary evaluation digest mismatch')
    require(artifacts.get('authorizationSha256') == source_digests['authorization'], 'summary authorization digest mismatch')
    require(artifacts.get('statisticsSha256') == source_digests['statistics'], 'summary statistics digest mismatch')

    fields = summary.get('fields', {})
    mapping = {
        'velocityMedianMs': 'velocity_median_ms',
        'velocityIqrWidthMs': 'velocity_iqr_width_ms',
        'velocityP95WidthMs': 'velocity_p95_width_ms',
        'waterDepthMedianM': 'water_depth_median_m',
        'waterDepthIqrWidthM': 'water_depth_iqr_width_m',
        'waterDepthP95WidthM': 'water_depth_p95_width_m',
        'wetProbability': 'wet_probability',
        'flowDirectionAgreementFraction': 'flow_direction_agreement_fraction',
    }
    for summary_key, statistics_key in mapping.items():
        bounds_match(fields, summary_key, statistics[statistics_key])
    simulated = summary.get('simulatedTimeSeconds', {})
    require_close(simulated.get('minimum'), report.get('minimumSimulatedTimeSeconds'), 'summary minimum simulated time')
    require_close(simulated.get('maximum'), report.get('maximumSimulatedTimeSeconds'), 'summary maximum simulated time')
    diagnostics = summary.get('runDiagnostics', {})
    require_close(diagnostics.get('massBalanceAbsoluteMaximum'), report.get('maxAbsoluteMassBalanceError'), 'summary mass-balance maximum')
    require_close(diagnostics.get('maxCfl'), report.get('maxCfl'), 'summary max CFL')
    finite_number(diagnostics.get('massBalanceAbsoluteMedian'), 'summary median mass balance', nonnegative=True)


def prepare_outputs(input_paths, output_dir):
    directory = Path(output_dir)
    destinations = {name: directory / name for name in OUTPUT_NAMES}
    resolved_inputs = {Path(path).resolve() for path in input_paths}
    resolved_outputs = [path.resolve() for path in destinations.values()]
    require(len(set(resolved_outputs)) == len(resolved_outputs), 'visual output paths must be distinct')
    for name, path in destinations.items():
        require(path.resolve() not in resolved_inputs, f'visual output overlaps an input: {name}')
        require(not path.exists(), f'visual output already exists: {path}')
    return directory, destinations


def png_chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', binascii.crc32(kind + payload) & 0xffffffff)


def encode_png(rgb):
    require(rgb.dtype == np.dtype(np.uint8) and rgb.ndim == 3 and rgb.shape[2] == 3, 'RGB uint8 image required')
    height, width, _ = rgb.shape
    scanlines = b''.join(b'\x00' + np.ascontiguousarray(row).tobytes() for row in rgb)
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', header) + png_chunk(b'IDAT', zlib.compress(scanlines, 9)) + png_chunk(b'IEND', b'')


def interpolate_palette(values, low, high, colors):
    if high <= low:
        normalized = np.zeros(values.shape, dtype=np.float64)
    else:
        normalized = np.clip((values - low) / (high - low), 0, 1)
    scaled = normalized * (len(colors) - 1)
    lower = np.floor(scaled).astype(np.int16)
    upper = np.minimum(lower + 1, len(colors) - 1)
    fraction = (scaled - lower)[..., None]
    palette = np.asarray(colors, dtype=np.float64)
    return np.rint(palette[lower] * (1 - fraction) + palette[upper] * fraction).astype(np.uint8)


def build_cell_raster(vertices, triangles):
    x_min, y_min = np.min(vertices, axis=0).astype(np.float64)
    x_max, y_max = np.max(vertices, axis=0).astype(np.float64)
    margin_x = max(1.0, (x_max - x_min) * 0.025)
    margin_y = max(1.0, (y_max - y_min) * 0.025)
    bounds = (x_min - margin_x, y_min - margin_y, x_max + margin_x, y_max + margin_y)
    transform = from_bounds(*bounds, PNG_WIDTH, PNG_HEIGHT)

    def geometries():
        for index, triangle in enumerate(triangles):
            points = vertices[triangle]
            ring = [(int(point[0]), int(point[1])) for point in points]
            ring.append(ring[0])
            yield {'type': 'Polygon', 'coordinates': [ring]}, index

    grid = rasterize(
        geometries(), out_shape=(PNG_HEIGHT, PNG_WIDTH), fill=-1,
        transform=transform, dtype=np.int32, all_touched=False,
    )
    require(np.any(grid >= 0), 'mesh rasterization produced no visible cells')
    represented_cell_ids = np.unique(grid[grid >= 0])
    expected_cell_ids = np.arange(CELL_COUNT, dtype=np.int32)
    require(
        np.array_equal(represented_cell_ids, expected_cell_ids),
        f'mesh rasterization omitted {CELL_COUNT - represented_cell_ids.size} of {CELL_COUNT} cells',
    )
    coverage = {
        'representedCellCount': int(represented_cell_ids.size),
        'coverageFraction': float(represented_cell_ids.size / CELL_COUNT),
    }
    return grid, [float(value) for value in bounds], coverage


def render_map(cell_grid, values, palette, fixed_range=None, valid_cells=None):
    if valid_cells is None:
        valid_cells = np.ones(values.shape, dtype=bool)
    require(valid_cells.shape == values.shape and valid_cells.dtype == np.dtype(np.bool_), 'map validity mask contract mismatch')
    visible_values = values[valid_cells]
    if fixed_range is None:
        require(visible_values.size > 0, 'map has no eligible cells for an automatic color scale')
        low, high = (float(value) for value in np.quantile(visible_values, [0.02, 0.98]))
        if high <= low:
            low, high = float(np.min(visible_values)), float(np.max(visible_values))
    else:
        low, high = fixed_range
    image = np.empty((PNG_HEIGHT, PNG_WIDTH, 3), dtype=np.uint8)
    image[:] = np.array([236, 241, 239], dtype=np.uint8)
    geometry_mask = cell_grid >= 0
    image[geometry_mask] = np.array([174, 184, 180], dtype=np.uint8)
    eligible_mask = np.zeros(cell_grid.shape, dtype=bool)
    eligible_mask[geometry_mask] = valid_cells[cell_grid[geometry_mask]]
    image[eligible_mask] = interpolate_palette(values[cell_grid[eligible_mask]], low, high, palette)
    return encode_png(image), {
        'dataMinimum': float(np.min(visible_values)) if visible_values.size else None,
        'dataMaximum': float(np.max(visible_values)) if visible_values.size else None,
        'colorScaleMinimum': float(low),
        'colorScaleMaximum': float(high),
        'colorScaleClipping': 'p02_p98' if fixed_range is None else 'fixed_0_1',
        'excludedCellCount': int(np.count_nonzero(~valid_cells)),
    }


def format_metric(value, kind):
    value = float(value)
    if kind == 'seconds':
        return f'{value:,.1f} s'
    if kind == 'memory':
        return f'{value:,.1f} MiB'
    if kind == 'scientific':
        return f'{value:.3e}'
    return f'{value:.4g}'


def color_hex(color):
    require(len(color) == 3 and all(isinstance(channel, int) and 0 <= channel <= 255 for channel in color), 'invalid RGB color')
    return f'#{color[0]:02x}{color[1]:02x}{color[2]:02x}'


def build_svg(png_payloads, ranges, report, authorization, source_digests):
    def image_data(name):
        return base64.b64encode(png_payloads[name]).decode('ascii')

    acceptance = authorization['acceptance']
    cards = [
        ('完了ケース / Completed', f"{report['completedCaseCount']} / {report['requestedCaseCount']}", '全64ケース完了 / All cases completed'),
        ('NaN / 負の水深', f"{report['nanCount']} / {report['negativeDepthCount']}", '許容値 0 / 0'),
        ('CFL', f"{format_metric(report['maxCfl'], 'plain')} ≤ {format_metric(acceptance['maxCflMax'], 'plain')}", '最大値 ≤ 許容値 / Maximum ≤ limit'),
        ('質量収支 / Mass balance', f"{format_metric(report['maxAbsoluteMassBalanceError'], 'scientific')} ≤ {format_metric(acceptance['maxAbsoluteMassBalanceErrorMax'], 'scientific')}", '絶対誤差最大値 / Maximum absolute error'),
        ('実行時間 / Wall time', f"{format_metric(report['wallSeconds'], 'seconds')} ≤ {format_metric(acceptance['maxWallSeconds'], 'seconds')}", '実測 ≤ 許容値 / Actual ≤ limit'),
        ('メモリ / Memory', f"{format_metric(report['peakResidentMemoryMiB'], 'memory')} ≤ {format_metric(acceptance['maxResidentMemoryMiB'], 'memory')}", '最大常駐メモリ / Peak resident memory'),
    ]
    card_svg = []
    for index, (label, value, note) in enumerate(cards):
        column = index % 3
        row = index // 3
        x = 60 + column * 500
        y = 245 + row * 145
        card_svg.append(f'''<g transform="translate({x} {y})">
  <rect width="460" height="120" rx="20" fill="#ffffff" stroke="#cddbd4" stroke-width="2"/>
  <text x="24" y="31" class="card-label">{escape(label)}</text>
  <text x="24" y="69" class="card-value">{escape(value)}</text>
  <text x="24" y="99" class="card-note">{escape(note)}</text>
</g>''')

    panel_svg = []
    for index, spec in enumerate(MAP_SPECS):
        name = spec['filename']
        title = spec['title']
        unit = spec['unit']
        if index == 4:
            x = 440
            y = 1970
        else:
            column = index % 2
            row = index // 2
            x = 60 + column * 770
            y = 570 + row * 700
        value_range = ranges[name]
        minimum = value_range['colorScaleMinimum']
        maximum = value_range['colorScaleMaximum']
        clipping = 'P2–P98表示（端値は色を固定）' if value_range['colorScaleClipping'] == 'p02_p98' else '0–1 固定表示'
        if value_range['excludedCellCount']:
            clipping = '灰=比較不可（2例未満） / gray=<2 samples'
        if name == 'full64-direction-support.png':
            minimum_label = f'{minimum * CASE_COUNT:.0f} / {CASE_COUNT} active cases'
            maximum_label = f'{maximum * CASE_COUNT:.0f} / {CASE_COUNT} active cases'
        else:
            minimum_label = f"{format_metric(minimum, 'plain')} {unit}"
            maximum_label = f"{format_metric(maximum, 'plain')} {unit}"
        panel_svg.append(f'''<g transform="translate({x} {y})">
  <rect width="720" height="650" rx="24" fill="#ffffff" stroke="#cddbd4" stroke-width="2"/>
  <text x="26" y="43" class="panel-title">{escape(title)}</text>
  <image x="26" y="66" width="668" height="459" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{image_data(name)}"/>
  <line x1="26" y1="540" x2="694" y2="540" stroke="#e1ebe6" stroke-width="2"/>
  <rect x="42" y="555" width="390" height="14" rx="7" fill="url(#{'gradient-' + str(index)})"/>
  <text x="42" y="597" class="legend">{escape(minimum_label)}</text>
  <text x="432" y="597" text-anchor="end" class="legend">{escape(maximum_label)}</text>
  <text x="682" y="627" text-anchor="end" class="legend-note">{escape(clipping)}</text>
</g>''')

    gradients = ''.join(
        f'<linearGradient id="gradient-{index}" x1="0%" x2="100%">'
        + ''.join(
            f'<stop offset="{offset}" stop-color="{color_hex(color)}"/>'
            for offset, color in zip(GRADIENT_STOP_OFFSETS, spec['palette'])
        )
        + '</linearGradient>'
        for index, spec in enumerate(MAP_SPECS)
    )
    provenance = (
        f"Stage 18 full64 • mesh {source_digests['mesh'][:12]}… • "
        f"statistics {source_digests['statistics'][:12]}… • report {source_digests['runReport'][:12]}…"
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="3305" viewBox="0 0 1600 3305" role="img" aria-labelledby="title description">
<title id="title">Stage 18 full64 visual judgment: PASS</title>
<desc id="description">64-case numerical acceptance summary and five spatial endpoint-statistics maps. Not physical validation and not connected to the public simulator.</desc>
<defs>{gradients}</defs>
<style>
text {{ font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", Meiryo, system-ui, sans-serif; fill: #15352a; }}
.banner {{ font-size: 54px; font-weight: 800; fill: #ffffff; }}
.subtitle {{ font-size: 24px; fill: #d9fbe9; }}
.card-label {{ font-size: 20px; font-weight: 700; fill: #3f6255; }}
.card-value {{ font-size: 29px; font-weight: 800; fill: #123b2b; }}
.card-note {{ font-size: 16px; fill: #607c71; }}
.panel-title {{ font-size: 25px; font-weight: 800; }}
.legend {{ font-size: 16px; font-weight: 700; }}
.legend-note {{ font-size: 14px; fill: #607c71; }}
.limit-title {{ font-size: 28px; font-weight: 800; fill: #7f1d1d; }}
.limit {{ font-size: 22px; font-weight: 650; fill: #7f1d1d; }}
.decision-title {{ font-size: 29px; font-weight: 800; fill: #164e63; }}
.decision {{ font-size: 21px; font-weight: 650; fill: #164e63; }}
.provenance {{ font-size: 15px; fill: #607c71; }}
</style>
<rect width="1600" height="3305" fill="#edf3f0"/>
<rect x="40" y="35" width="1520" height="150" rx="28" fill="#08783f"/>
<circle cx="103" cy="110" r="35" fill="#ffffff" opacity="0.2"/>
<path d="M84 111l13 13 27-32" fill="none" stroke="#ffffff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
<text x="155" y="103" class="banner" fill="#ffffff" style="fill:#ffffff">判定: PASS / RESULT: PASS</text>
<text x="158" y="143" class="subtitle" fill="#d9fbe9" style="fill:#d9fbe9">承認済みの数値安定性・実行条件をすべて満たしました / All authorized numerical acceptance checks passed</text>
{''.join(card_svg)}
{''.join(panel_svg)}
<rect x="60" y="2670" width="1480" height="285" rx="24" fill="#ecfeff" stroke="#4aa3b6" stroke-width="3"/>
<text x="95" y="2722" class="decision-title">この画像で判断すること</text>
<text x="95" y="2768" class="decision">① 上部がPASSで、64/64完了、NaN / 負の水深が0 / 0、CFL・質量収支・時間・メモリがすべて許容値内か</text>
<text x="95" y="2813" class="decision">② 5枚の地図が河道内で欠落なく表示されているか（灰色は流向比較不可：有効ケース2未満）</text>
<text x="95" y="2858" class="decision">③ 地図は次に詳しく調べる場所を特定するためのもの。物理的な正しさを判定するものではない</text>
<text x="95" y="2903" class="decision">④ 流向一致度は流向サンプル率と併せて見る。高一致でもサンプル率が低い場所は確証が弱い</text>
<rect x="60" y="2985" width="1480" height="205" rx="24" fill="#fff4f2" stroke="#d97766" stroke-width="3"/>
<text x="95" y="3035" class="limit-title">判断するときの重要な制限 / Important interpretation limits</text>
<text x="95" y="3077" class="limit">暫定的な同一ステップ数の数値終端統計 / Provisional equal-step numerical endpoint statistics</text>
<text x="95" y="3117" class="limit">物理的妥当性の検証ではありません。公開シミュレータには接続していません。 / Not physical validation. Not connected to the public simulator.</text>
<text x="60" y="3255" class="provenance">{escape(provenance)}</text>
</svg>
'''.encode('utf-8')


def write_atomic(path, payload):
    path = Path(path)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh')
    parser.add_argument('statistics')
    parser.add_argument('statistics_summary')
    parser.add_argument('run_report')
    parser.add_argument('evaluation')
    parser.add_argument('authorization')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()

    input_paths = [args.mesh, args.statistics, args.statistics_summary, args.run_report, args.evaluation, args.authorization]
    for path in input_paths:
        require(Path(path).is_file(), f'visual input is not a file: {path}')
    output_dir, destinations = prepare_outputs(input_paths, args.output_dir)

    source_digests = {
        'mesh': sha256(args.mesh),
        'statistics': sha256(args.statistics),
        'statisticsSummary': sha256(args.statistics_summary),
        'runReport': sha256(args.run_report),
        'evaluation': sha256(args.evaluation),
        'authorization': sha256(args.authorization),
    }
    authorization = load_json(args.authorization)
    validate_authorization(authorization)
    report = load_json(args.run_report)
    evaluation = load_json(args.evaluation)
    summary = load_json(args.statistics_summary)
    validate_report(report, authorization, source_digests)
    validate_mesh_package(args.mesh, authorization)
    validate_evaluation(evaluation, report, authorization, source_digests)
    statistics, dry_threshold, speed_threshold, active_direction_count = validate_statistics(
        args.statistics, report, source_digests,
    )
    statistics['direction_sample_support_fraction'] = (
        active_direction_count.astype(np.float64) / CASE_COUNT
    )
    validate_summary(summary, statistics, report, authorization, source_digests, dry_threshold, speed_threshold)

    with np.load(args.mesh, allow_pickle=False) as package:
        vertices = np.array(package['vertex_local_mm'], copy=True)
        triangles = np.array(package['triangles'], copy=True)
    cell_grid, raster_bounds, raster_coverage = build_cell_raster(vertices, triangles)

    png_payloads = {}
    ranges = {}
    for spec in MAP_SPECS:
        name = spec['filename']
        value_name = spec['field']
        fixed_range = spec['fixedRange']
        valid_cells = (
            active_direction_count >= DIRECTION_AGREEMENT_MIN_SAMPLES
            if name == 'full64-direction-agreement.png' else None
        )
        png_payloads[name], ranges[name] = render_map(
            cell_grid, statistics[value_name], spec['palette'], fixed_range=fixed_range, valid_cells=valid_cells,
        )
    svg_payload = build_svg(png_payloads, ranges, report, authorization, source_digests)

    visual_payloads = {**png_payloads, 'full64-judgment.svg': svg_payload}
    manifest = {
        'schema': 'onga-stage18-full64-visual-manifest-v1',
        'status': 'generated',
        'judgment': 'pass',
        'classification': CLASSIFICATION,
        'sourceCaseCount': CASE_COUNT,
        'cellCount': CELL_COUNT,
        'comparisonBasis': COMPARISON_BASIS,
        'sources': source_digests,
        'outputs': {
            name: {
                'sha256': sha256_bytes(payload),
                'mediaType': 'image/png' if name.endswith('.png') else 'image/svg+xml',
            }
            for name, payload in visual_payloads.items()
        },
        'visualization': {
            'geometrySource': 'vertex_local_mm_and_triangles',
            'rasterization': 'deterministic_triangle_cell_index_raster',
            'pngWidth': PNG_WIDTH,
            'pngHeight': PNG_HEIGHT,
            'localBoundsMm': raster_bounds,
            **raster_coverage,
            'fields': ranges,
            'palettes': {
                spec['filename']: [color_hex(color) for color in spec['palette']]
                for spec in MAP_SPECS
            },
            'gradientStopOffsetsPercent': [0.0, 33.33, 66.67, 100.0],
            'directionAgreementMinimumActiveSamples': DIRECTION_AGREEMENT_MIN_SAMPLES,
            'directionSampleSupport': {
                'definition': 'active_direction_sample_count_divided_by_case_count',
                'denominatorCaseCount': CASE_COUNT,
            },
        },
        'interpretationLimits': INTERPRETATION_LIMITS,
    }
    manifest_payload = f'{json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)}\n'.encode('utf-8')

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in visual_payloads.items():
        write_atomic(destinations[name], payload)
    write_atomic(destinations['full64-visual-manifest.json'], manifest_payload)
    print(json.dumps({
        'status': 'generated',
        'judgment': 'pass',
        'outputDirectory': str(output_dir),
        'outputs': list(OUTPUT_NAMES),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
