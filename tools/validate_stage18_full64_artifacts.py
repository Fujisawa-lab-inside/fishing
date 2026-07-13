#!/usr/bin/env python3
import base64
import copy
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

import numpy as np

from run_stage18_full64 import validate_fresh_outputs, validate_mesh_package


PROTECTED_PATHS = [
    'index.html',
    'pc_full.html',
    'mobile_lite.html',
    'app.js',
    'assets/app.js',
    'OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
    'OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
]
VISUAL_PNG_NAMES = (
    'full64-depth-median.png',
    'full64-velocity-median.png',
    'full64-wet-probability.png',
    'full64-direction-agreement.png',
    'full64-direction-support.png',
)
VISUAL_SVG_NAME = 'full64-judgment.svg'
VISUAL_MANIFEST_NAME = 'full64-visual-manifest.json'
VISUAL_OUTPUT_NAMES = (*VISUAL_PNG_NAMES, VISUAL_SVG_NAME, VISUAL_MANIFEST_NAME)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, expect_success=True):
    completed = subprocess.run(command, text=True, capture_output=True)
    if expect_success and completed.returncode != 0:
        raise RuntimeError(f'command failed: {command}\n{completed.stdout}\n{completed.stderr}')
    if not expect_success and completed.returncode == 0:
        raise RuntimeError(f'command unexpectedly passed: {command}')
    return completed


def save_fields(path, arrays):
    np.savez_compressed(path, **arrays)


def repack_npz(source, destination):
    shutil.copyfile(source, destination)
    with zipfile.ZipFile(destination, mode='a') as archive:
        archive.comment = b'stage18-validation-stale-file-digest'
    require(sha256(destination) != sha256(source), f'repacked NPZ digest did not change: {source}')


def write_report(path, template, fields_path):
    report = copy.deepcopy(template)
    report['fieldArtifact']['path'] = str(fields_path)
    report['fieldArtifact']['sha256'] = sha256(fields_path)
    Path(path).write_text(json.dumps(report), encoding='utf-8')
    return report


def evaluate(authorization_path, report_path, fields_path, evaluation_path):
    run([
        'node',
        'tools/evaluate_stage18_full64.mjs',
        str(authorization_path),
        str(report_path),
        str(fields_path),
        str(evaluation_path),
    ])


def aggregate(fields_path, report_path, evaluation_path, authorization_path, statistics_path, summary_path, extra=None, expect_success=True):
    command = [
        sys.executable,
        'tools/aggregate_stage18_full64.py',
        str(fields_path),
        str(report_path),
        str(evaluation_path),
        str(authorization_path),
        '--statistics-output', str(statistics_path),
        '--summary-output', str(summary_path),
    ]
    if extra:
        command.extend(extra)
    return run(command, expect_success=expect_success)


def render_visuals(mesh_path, statistics_path, summary_path, report_path, evaluation_path, authorization_path, output_dir, expect_success=True):
    return run([
        sys.executable,
        'tools/render_stage18_full64_visuals.py',
        str(mesh_path),
        str(statistics_path),
        str(summary_path),
        str(report_path),
        str(evaluation_path),
        str(authorization_path),
        '--output-dir', str(output_dir),
    ], expect_success=expect_success)


def render_diagnostic(work_dir, output_path, expect_success=True):
    return run([
        sys.executable,
        'tools/render_stage18_full64_diagnostic.py',
        '--work-dir', str(work_dir),
        '--output', str(output_path),
        '--workflow-run-id', '987654321',
        '--repository', 'Fujisawa-lab-inside/fishing',
    ], expect_success=expect_success)


def require_no_visual_outputs(output_dir, label):
    output_dir = Path(output_dir)
    require(
        not output_dir.exists() or (output_dir.is_dir() and not any(output_dir.iterdir())),
        f'{label} rejection created partial visual outputs',
    )


def require_failure_reason(completed, expected):
    require(expected in completed.stderr, f'expected rejection reason not found: {expected}')


def read_png(path):
    payload = Path(path).read_bytes()
    require(payload[:8] == b'\x89PNG\r\n\x1a\n', f'invalid PNG signature: {path}')
    offset = 8
    chunks = []
    while offset < len(payload):
        require(offset + 12 <= len(payload), f'truncated PNG chunk: {path}')
        length = struct.unpack('>I', payload[offset:offset + 4])[0]
        chunk_end = offset + 12 + length
        require(chunk_end <= len(payload), f'truncated PNG payload: {path}')
        chunk_type = payload[offset + 4:offset + 8]
        chunk_data = payload[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack('>I', payload[offset + 8 + length:chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xffffffff
        require(actual_crc == expected_crc, f'PNG CRC mismatch: {path}')
        chunks.append((chunk_type, chunk_data))
        offset = chunk_end
        if chunk_type == b'IEND':
            break
    require(offset == len(payload), f'bytes found after PNG IEND: {path}')
    require(chunks and chunks[0][0] == b'IHDR' and len(chunks[0][1]) == 13, f'missing PNG IHDR: {path}')
    require(chunks[-1] == (b'IEND', b''), f'missing PNG IEND: {path}')
    width, height = struct.unpack('>II', chunks[0][1][:8])
    require(width > 0 and height > 0, f'invalid PNG dimensions: {path}')
    return width, height, chunks


def png_dimensions(path):
    width, height, _ = read_png(path)
    return width, height


def decode_png_rgb(path):
    width, height, chunks = read_png(path)
    bit_depth, color_type, compression, filter_method, interlace = struct.unpack('>BBBBB', chunks[0][1][8:13])
    require((bit_depth, color_type, compression, filter_method, interlace) == (8, 2, 0, 0, 0), f'unsupported PNG encoding: {path}')
    raw = zlib.decompress(b''.join(data for kind, data in chunks if kind == b'IDAT'))
    stride = width * 3
    require(len(raw) == height * (stride + 1), f'PNG scanline size mismatch: {path}')
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, stride + 1)
    require(np.all(rows[:, 0] == 0), f'unsupported PNG scanline filter: {path}')
    return rows[:, 1:].reshape(height, width, 3)


def validate_visual_outputs(output_dir, source_paths):
    output_dir = Path(output_dir)
    for name in VISUAL_OUTPUT_NAMES:
        path = output_dir / name
        require(path.is_file() and path.stat().st_size > 0, f'missing or empty visual output: {name}')
    require({path.name for path in output_dir.iterdir()} == set(VISUAL_OUTPUT_NAMES), 'unexpected visual output file set')

    image_dimensions = [png_dimensions(output_dir / name) for name in VISUAL_PNG_NAMES]
    require(all(dimension == (3840, 2640) for dimension in image_dimensions), 'visual PNG dimensions must be 3840 by 2640')

    svg = (output_dir / VISUAL_SVG_NAME).read_text(encoding='utf-8')
    svg_root = ET.fromstring(svg)
    for expected_text in (
        '判定: PASS / RESULT: PASS',
        '64 / 64',
        'NaN / 負の水深',
        'CFL',
        '質量収支 / Mass balance',
        '実行時間 / Wall time',
        'メモリ / Memory',
        '灰=比較不可（2例未満） / gray=&lt;2 samples',
        '灰色は流向比較不可：有効ケース2未満',
        '流向サンプル率 / Direction sample support',
        '0 / 64 active cases',
        '64 / 64 active cases',
        '② 5枚の地図が河道内で欠落なく表示されているか',
        '流向一致度は流向サンプル率と併せて見る',
        'この画像で判断すること',
        '物理的な正しさを判定するものではない',
        '暫定的な同一ステップ数の数値終端統計 / Provisional equal-step numerical endpoint statistics',
        '物理的妥当性の検証ではありません。公開シミュレータには接続していません。 / Not physical validation. Not connected to the public simulator.',
    ):
        require(expected_text in svg, f'judgment SVG missing required text: {expected_text}')
    require('gray=&amp;lt;2 samples' not in svg, 'direction legend is double-escaped')
    embedded_pngs = [
        base64.b64decode(payload, validate=True)
        for payload in re.findall(r'data:image/png;base64,([A-Za-z0-9+/=]+)', svg)
    ]
    require(len(embedded_pngs) == 5, 'judgment SVG must embed all five PNG maps')
    embedded_digests = {hashlib.sha256(payload).hexdigest() for payload in embedded_pngs}
    standalone_digests = {sha256(output_dir / name) for name in VISUAL_PNG_NAMES}
    require(embedded_digests == standalone_digests, 'judgment SVG embedded PNGs do not match standalone maps')

    manifest = json.loads((output_dir / VISUAL_MANIFEST_NAME).read_text(encoding='utf-8'))
    require(manifest.get('schema') == 'onga-stage18-full64-visual-manifest-v1', 'visual manifest schema mismatch')
    require(manifest.get('status') == 'generated', 'visual manifest status mismatch')
    require(
        manifest.get('classification') == 'provisional_step_matched_numerical_endpoint_statistics_not_physical_validation',
        'visual manifest classification mismatch',
    )
    require(manifest.get('sourceCaseCount') == 64, 'visual manifest case count mismatch')
    require(manifest.get('cellCount') == 50333, 'visual manifest cell count mismatch')
    require(
        manifest.get('comparisonBasis') == 'equal_step_count_not_equal_simulated_time',
        'visual manifest comparison basis mismatch',
    )
    expected_sources = {
        name: sha256(path)
        for name, path in source_paths.items()
    }
    require(manifest.get('sources') == expected_sources, 'visual manifest source digest mismatch')
    expected_media_types = {
        **{name: 'image/png' for name in VISUAL_PNG_NAMES},
        VISUAL_SVG_NAME: 'image/svg+xml',
    }
    require(set(manifest.get('outputs', {})) == set(expected_media_types), 'visual manifest output set mismatch')
    for name, media_type in expected_media_types.items():
        entry = manifest['outputs'][name]
        require(entry.get('sha256') == sha256(output_dir / name), f'visual manifest output digest mismatch: {name}')
        require(entry.get('mediaType') == media_type, f'visual manifest media type mismatch: {name}')
    visualization = manifest.get('visualization', {})
    require(visualization.get('pngWidth') == 3840, 'visual manifest PNG width mismatch')
    require(visualization.get('pngHeight') == 2640, 'visual manifest PNG height mismatch')
    require(visualization.get('representedCellCount') == 50333, 'visual manifest represented-cell count mismatch')
    require(visualization.get('coverageFraction') == 1.0, 'visual manifest cell coverage mismatch')
    require(visualization.get('directionAgreementMinimumActiveSamples') == 2, 'direction agreement sample threshold mismatch')
    require(
        visualization.get('gradientStopOffsetsPercent') == [0.0, 33.33, 66.67, 100.0],
        'visual manifest gradient offsets mismatch',
    )
    palettes = visualization.get('palettes', {})
    require(set(palettes) == set(VISUAL_PNG_NAMES), 'visual manifest palette set mismatch')
    for name in VISUAL_PNG_NAMES:
        require(
            isinstance(palettes[name], list)
            and len(palettes[name]) == 4
            and all(re.fullmatch(r'#[0-9a-f]{6}', color) for color in palettes[name]),
            f'visual manifest palette contract mismatch: {name}',
        )
    gradient_tag = '{http://www.w3.org/2000/svg}linearGradient'
    stop_tag = '{http://www.w3.org/2000/svg}stop'
    gradients = {gradient.get('id'): gradient for gradient in svg_root.iter(gradient_tag)}
    require(set(gradients) == {f'gradient-{index}' for index in range(5)}, 'SVG gradient set mismatch')
    expected_offsets = ['0%', '33.33%', '66.67%', '100%']
    for index, name in enumerate(VISUAL_PNG_NAMES):
        stops = list(gradients[f'gradient-{index}'].findall(stop_tag))
        require([stop.get('offset') for stop in stops] == expected_offsets, f'SVG gradient offsets mismatch: {name}')
        require([stop.get('stop-color') for stop in stops] == palettes[name], f'SVG gradient palette mismatch: {name}')
    direction_field = visualization.get('fields', {}).get('full64-direction-agreement.png', {})
    require(direction_field.get('excludedCellCount') == 2, 'direction comparison exclusion count mismatch')
    support_field = visualization.get('fields', {}).get('full64-direction-support.png', {})
    require(support_field == {
        'dataMinimum': 0.0,
        'dataMaximum': 1.0,
        'colorScaleMinimum': 0.0,
        'colorScaleMaximum': 1.0,
        'colorScaleClipping': 'fixed_0_1',
        'excludedCellCount': 0,
    }, 'direction sample support field metadata mismatch')
    require(visualization.get('directionSampleSupport') == {
        'definition': 'active_direction_sample_count_divided_by_case_count',
        'denominatorCaseCount': 64,
    }, 'direction sample support definition mismatch')
    direction_rgb = decode_png_rgb(output_dir / 'full64-direction-agreement.png')
    inactive_gray = np.array([174, 184, 180], dtype=np.uint8)
    require(np.any(np.all(direction_rgb == inactive_gray, axis=2)), 'direction comparison exclusion mask is not visible')
    require(manifest.get('interpretationLimits') == {
        'commonPhysicalTime': False,
        'physicalValidationClaimAllowed': False,
        'sensitivityClaimAllowed': False,
        'publicSimulatorConnectionAllowed': False,
    }, 'visual manifest interpretation limits mismatch')


def main():
    authorization_path = Path('config/stage18_full64_run_authorization_v1.json')
    authorization = json.loads(authorization_path.read_text(encoding='utf-8'))
    authorization_digest = sha256(authorization_path)
    mesh_path = Path('stage18-contract-mesh/onga_stage16_metric_fv_mesh_v1.npz')
    require(mesh_path.is_file(), f'canonical metric mesh is missing: {mesh_path}')
    mesh_digest = sha256(mesh_path)
    with tempfile.TemporaryDirectory(prefix='stage18-full64-validation-') as temporary:
        root = Path(temporary)
        fields_path = root / 'fields.npz'
        report_path = root / 'report.json'
        evaluation_path = root / 'evaluation.json'
        statistics_path = root / 'statistics.npz'
        summary_path = root / 'summary.json'

        protected_overlap_rejected = False
        try:
            validate_fresh_outputs([], ['index.html'], '.')
        except RuntimeError:
            protected_overlap_rejected = True
        require(protected_overlap_rejected, 'protected output overlap was not rejected')

        malformed_mesh = root / 'malformed-mesh.npz'
        np.savez_compressed(malformed_mesh, **{
            name: np.empty((0,), dtype=contract['dtype'])
            for name, contract in authorization['meshExpected']['packageArrays'].items()
        })
        malformed_mesh_rejected = False
        try:
            validate_mesh_package(malformed_mesh, authorization)
        except RuntimeError:
            malformed_mesh_rejected = True
        require(malformed_mesh_rejected, 'malformed metric mesh package was not rejected')

        case_axis = np.arange(64, dtype=np.float64)[:, None]
        cell_axis = (np.arange(50333, dtype=np.float64) % 10)[None, :]
        depth = 1.0 + 0.01 * case_axis + 1e-6 * cell_axis
        velocity_u = np.broadcast_to(0.1 + 0.001 * case_axis, depth.shape).copy()
        velocity_v = np.zeros_like(depth)
        wrap_angles = np.concatenate((np.full(32, math.pi - 0.01), np.full(32, -math.pi + 0.01)))
        velocity_u[:, 0] = np.cos(wrap_angles)
        velocity_v[:, 0] = np.sin(wrap_angles)
        velocity_u[:, 2] = 0
        velocity_v[:, 2] = 0
        velocity_u[:, 3] = 0
        velocity_v[:, 3] = 0
        velocity_u[0, 3] = 0.1
        mass_error = np.linspace(0, 1e-12, 64)
        cfl_max = np.full(64, 0.12)
        simulated_time = np.linspace(10.0, 20.0, 64)
        minimum_time_step = np.full(64, 0.01)
        maximum_time_step = np.full(64, 0.02)
        case_ids = np.array([f'stage18-{index:04d}' for index in range(1, 65)])
        arrays = {
            'schema': np.array('onga-stage18-full64-fields-v1'),
            'case_ids': case_ids,
            'water_depth_m': depth,
            'velocity_u_ms': velocity_u,
            'velocity_v_ms': velocity_v,
            'mass_balance_error': mass_error,
            'cfl_max': cfl_max,
            'simulated_time_seconds': simulated_time,
            'minimum_time_step_seconds': minimum_time_step,
            'maximum_time_step_seconds': maximum_time_step,
            'mesh_sha256': np.array(mesh_digest),
            'mesh_summary_sha256': np.array(authorization['meshExpected']['summarySha256']),
            'ensemble_sha256': np.array(authorization['ensembleExpected']['sha256']),
            'authorization_sha256': np.array(authorization_digest),
            'comparison_basis': np.array(authorization['run']['comparisonBasis']),
        }
        save_fields(fields_path, arrays)

        attempted_case_ids = [f'stage18-{index:04d}' for index in range(1, 65)]
        diagnostics = [{
            'caseId': case_id,
            'status': 'completed',
            'wallSeconds': 1.0,
            'stepsCompleted': 500,
            'simulatedTimeSeconds': float(simulated_time[index]),
            'minimumTimeStepSeconds': 0.01,
            'maximumTimeStepSeconds': 0.02,
            'massBalanceError': float(mass_error[index]),
            'maxCfl': 0.12,
            'minimumDepthM': float(np.min(depth[index])),
        } for index, case_id in enumerate(attempted_case_ids)]
        protected_hashes = {path: hashlib.sha256(path.encode('utf-8')).hexdigest() for path in PROTECTED_PATHS}
        report_template = {
            'schema': 'onga-stage18-full64-run-report-v1',
            'classification': 'provisional_full64_runtime_and_numerical_stability_evidence_only',
            'geometry': authorization['geometry'],
            'ensembleSeed': 20260713,
            'requestedCaseCount': 64,
            'attemptedCaseIds': attempted_case_ids,
            'completedCaseCount': 64,
            'failedCaseCount': 0,
            'wallSeconds': 600,
            'caseWallSecondsTotal': 64,
            'peakResidentMemoryMiB': 512,
            'maxCfl': float(np.max(cfl_max)),
            'maxAbsoluteMassBalanceError': float(np.max(np.abs(mass_error))),
            'minimumDepthM': float(np.min(depth)),
            'minimumSimulatedTimeSeconds': float(np.min(simulated_time)),
            'maximumSimulatedTimeSeconds': float(np.max(simulated_time)),
            'nanCount': 0,
            'negativeDepthCount': 0,
            'comparisonBasis': authorization['run']['comparisonBasis'],
            'parameterCoverage': authorization['parameterCoverage'],
            'failures': [],
            'caseDiagnostics': diagnostics,
            'inputDigests': {
                'meshSha256': mesh_digest,
                'meshSummarySha256': authorization['meshExpected']['summarySha256'],
                'ensembleSha256': authorization['ensembleExpected']['sha256'],
                'authorizationSha256': authorization_digest,
            },
            'meshSummaryVerified': True,
            'fieldArtifact': {
                'path': str(fields_path),
                'sha256': sha256(fields_path),
                'shape': {'caseCount': 64, 'cellCount': 50333},
                'dtype': 'float64',
            },
            'protectedSurfaceHashesBefore': protected_hashes,
            'protectedSurfaceHashesAfter': protected_hashes,
            'protectedSurfaceHashesUnchanged': True,
            'safeguards': authorization['safeguards'],
        }
        write_report(report_path, report_template, fields_path)
        evaluate(authorization_path, report_path, fields_path, evaluation_path)

        evaluator_overlap_report = root / 'evaluator-overlap-report.json'
        write_report(evaluator_overlap_report, report_template, fields_path)
        evaluator_overlap_digest = sha256(evaluator_overlap_report)
        run([
            'node',
            'tools/evaluate_stage18_full64.mjs',
            str(authorization_path),
            str(evaluator_overlap_report),
            str(fields_path),
            str(evaluator_overlap_report),
        ], expect_success=False)
        require(sha256(evaluator_overlap_report) == evaluator_overlap_digest, 'evaluator overlap changed its input')

        existing_evaluation = root / 'existing-evaluation.json'
        existing_evaluation.write_text('{"sentinel":true}\n', encoding='utf-8')
        existing_evaluation_digest = sha256(existing_evaluation)
        run([
            'node',
            'tools/evaluate_stage18_full64.mjs',
            str(authorization_path),
            str(report_path),
            str(fields_path),
            str(existing_evaluation),
        ], expect_success=False)
        require(sha256(existing_evaluation) == existing_evaluation_digest, 'evaluator replaced an existing output')

        run([
            'node',
            'tools/evaluate_stage18_full64.mjs',
            str(authorization_path),
            str(report_path),
            str(root / 'missing-fields.npz'),
            str(root / 'missing-fields-evaluation.json'),
        ], expect_success=False)
        aggregate(fields_path, report_path, evaluation_path, authorization_path, statistics_path, summary_path)

        visual_output_dir = root / 'visuals'
        render_visuals(
            mesh_path, statistics_path, summary_path, report_path, evaluation_path,
            authorization_path, visual_output_dir,
        )
        validate_visual_outputs(visual_output_dir, {
            'mesh': mesh_path,
            'statistics': statistics_path,
            'statisticsSummary': summary_path,
            'runReport': report_path,
            'evaluation': evaluation_path,
            'authorization': authorization_path,
        })

        stale_mesh_path = root / 'stale-visual-mesh.npz'
        repack_npz(mesh_path, stale_mesh_path)
        stale_mesh_output = root / 'stale-mesh-visuals'
        stale_mesh_result = render_visuals(
            stale_mesh_path, statistics_path, summary_path, report_path, evaluation_path,
            authorization_path, stale_mesh_output, expect_success=False,
        )
        require_failure_reason(stale_mesh_result, 'run report mesh digest mismatch')
        require_no_visual_outputs(stale_mesh_output, 'stale mesh')

        stale_statistics_path = root / 'stale-visual-statistics.npz'
        repack_npz(statistics_path, stale_statistics_path)
        stale_statistics_output = root / 'stale-statistics-visuals'
        stale_statistics_result = render_visuals(
            mesh_path, stale_statistics_path, summary_path, report_path, evaluation_path,
            authorization_path, stale_statistics_output, expect_success=False,
        )
        require_failure_reason(stale_statistics_result, 'summary statistics digest mismatch')
        require_no_visual_outputs(stale_statistics_output, 'stale statistics')

        stale_summary = json.loads(summary_path.read_text(encoding='utf-8'))
        stale_summary['artifacts']['statisticsSha256'] = 'f' * 64
        stale_summary_path = root / 'stale-visual-summary.json'
        stale_summary_path.write_text(json.dumps(stale_summary), encoding='utf-8')
        stale_summary_output = root / 'stale-summary-visuals'
        stale_summary_result = render_visuals(
            mesh_path, statistics_path, stale_summary_path, report_path, evaluation_path,
            authorization_path, stale_summary_output, expect_success=False,
        )
        require_failure_reason(stale_summary_result, 'summary statistics digest mismatch')
        require_no_visual_outputs(stale_summary_output, 'stale statistics summary')

        stale_report = json.loads(report_path.read_text(encoding='utf-8'))
        stale_report['validationOnlyStaleMarker'] = True
        stale_report_path = root / 'stale-visual-report.json'
        stale_report_path.write_text(json.dumps(stale_report), encoding='utf-8')
        stale_report_output = root / 'stale-report-visuals'
        stale_report_result = render_visuals(
            mesh_path, statistics_path, summary_path, stale_report_path, evaluation_path,
            authorization_path, stale_report_output, expect_success=False,
        )
        require_failure_reason(stale_report_result, 'evaluation run-report digest mismatch')
        require_no_visual_outputs(stale_report_output, 'stale run report')

        stale_visual_evaluation = json.loads(evaluation_path.read_text(encoding='utf-8'))
        stale_visual_evaluation['validationOnlyStaleMarker'] = True
        stale_visual_evaluation_path = root / 'stale-visual-evaluation.json'
        stale_visual_evaluation_path.write_text(json.dumps(stale_visual_evaluation), encoding='utf-8')
        stale_evaluation_output = root / 'stale-evaluation-visuals'
        stale_evaluation_result = render_visuals(
            mesh_path, statistics_path, summary_path, report_path, stale_visual_evaluation_path,
            authorization_path, stale_evaluation_output, expect_success=False,
        )
        require_failure_reason(stale_evaluation_result, 'statistics evaluation digest mismatch')
        require_no_visual_outputs(stale_evaluation_output, 'stale evaluation')

        stale_authorization_path = root / 'stale-visual-authorization.json'
        stale_authorization_path.write_bytes(authorization_path.read_bytes() + b'\n')
        require(sha256(stale_authorization_path) != authorization_digest, 'stale authorization digest did not change')
        stale_authorization_output = root / 'stale-authorization-visuals'
        stale_authorization_result = render_visuals(
            mesh_path, statistics_path, summary_path, report_path, evaluation_path,
            stale_authorization_path, stale_authorization_output, expect_success=False,
        )
        require_failure_reason(stale_authorization_result, 'run report authorization digest mismatch')
        require_no_visual_outputs(stale_authorization_output, 'stale authorization')

        for index, output_name in enumerate(VISUAL_OUTPUT_NAMES):
            existing_visual_dir = root / f'existing-visuals-{index}'
            existing_visual_dir.mkdir()
            existing_visual = existing_visual_dir / output_name
            existing_visual.write_bytes(f'do-not-replace:{output_name}'.encode('utf-8'))
            existing_visual_digest = sha256(existing_visual)
            existing_output_result = render_visuals(
                mesh_path, statistics_path, summary_path, report_path, evaluation_path,
                authorization_path, existing_visual_dir, expect_success=False,
            )
            require_failure_reason(existing_output_result, f'visual output already exists: {existing_visual}')
            require(sha256(existing_visual) == existing_visual_digest, f'visual renderer replaced existing output: {output_name}')
            require(
                {path.name for path in existing_visual_dir.iterdir()} == {output_name},
                f'existing-output rejection created partial outputs: {output_name}',
            )

        diagnostic_work_dir = root / 'diagnostic-partial'
        diagnostic_work_dir.mkdir()
        diagnostic_progress = {
            'schema': 'onga-stage18-full64-progress-v1',
            'status': 'failed',
            'completedCaseCount': 17,
            'failedCaseCount': 2,
            'wallSeconds': 10 ** 4000,
            'terminalFailure': '<script>diagnostic</script> token=stage18-test-secret-value',
            'caseDiagnostics': [{'maxCfl': 0.42, 'massBalanceError': -2.5e-9}],
            'failures': [{'caseId': 'stage18-0018', 'reason': 'solver stopped'}],
        }
        (diagnostic_work_dir / 'full64-progress.json').write_text(
            json.dumps(diagnostic_progress), encoding='utf-8',
        )
        (diagnostic_work_dir / 'full64-report.json').write_text('{malformed', encoding='utf-8')
        (diagnostic_work_dir / 'full64-evaluation.json').write_text(json.dumps({
            'checks': {
                'completionFraction': False,
                'maxCfl': False,
                'massBalance': False,
                'wallTime': False,
            },
        }), encoding='utf-8')
        (diagnostic_work_dir / 'full64-statistics-summary.json').write_text(json.dumps({
            'runDiagnostics': {
                'maxCfl': 0.5,
                'massBalanceAbsoluteMaximum': 3e-9,
            },
        }), encoding='utf-8')
        diagnostic_output = root / 'full64-diagnostic-stop.svg'
        render_diagnostic(diagnostic_work_dir, diagnostic_output)
        diagnostic_payload = diagnostic_output.read_bytes()
        diagnostic_svg = diagnostic_payload.decode('utf-8')
        ET.fromstring(diagnostic_svg)
        for expected_text in (
            'STOP — 結果として使用不可',
            'fill="#ffffff" style="fill:#ffffff">STOP — 結果として使用不可',
            'fill="#fee2e2" style="fill:#fee2e2">NOT USABLE AS A RESULT',
            '一回限りの承認は消費済み / ONE-TIME AUTHORIZATION CONSUMED',
            '自動で再実行しない / DO NOT RERUN AUTOMATICALLY',
            '<text x="80" y="452" class="link">https://github.com/Fujisawa-lab-inside/fishing/actions/runs/987654321</text>',
            '17 / 64',
            'Failed / 失敗</text><text x="24" y="82" class="value">2</text>',
            'Authorized limit: CFL ≤ 0.95',
            'Authorized limit: mass ≤ 1e-8',
            'Authorized limit: wall ≤ 3,600 s',
            'Authorized limit: memory ≤ 8,192 MiB',
            '新しい明示承認に値するか判断する / Decide whether a NEW explicit authorization is warranted.',
            '物理的妥当性の検証ではありません。公開シミュレータには接続していません。',
            'Not physical validation. Not connected to the public simulator.',
            '&lt;script&gt;diagnostic&lt;/script&gt;',
            '[redacted]',
        ):
            require(expected_text in diagnostic_svg, f'diagnostic STOP SVG missing required text: {expected_text}')
        require('RESULT: PASS' not in diagnostic_svg.upper(), 'diagnostic STOP SVG must never show PASS')
        require('<a href=' not in diagnostic_svg, 'diagnostic run URL must be plain visible text')
        require('fill="#b91c1c"' in diagnostic_svg, 'diagnostic STOP SVG must use a red stop treatment')
        require('stage18-test-secret-value' not in diagnostic_svg, 'diagnostic STOP SVG leaked a secret')
        require('<script>diagnostic</script>' not in diagnostic_svg, 'diagnostic STOP SVG did not escape untrusted XML')
        require(
            len(re.findall(r'<circle cx="96" cy="[0-9]+" r="8" fill="#b91c1c"/>', diagnostic_svg)) == 3,
            'diagnostic STOP SVG must cap the fixture at three failure reasons',
        )

        deterministic_diagnostic = root / 'full64-diagnostic-stop-copy.svg'
        render_diagnostic(diagnostic_work_dir, deterministic_diagnostic)
        require(deterministic_diagnostic.read_bytes() == diagnostic_payload, 'diagnostic STOP SVG is not deterministic')

        diagnostic_digest = sha256(diagnostic_output)
        render_diagnostic(diagnostic_work_dir, diagnostic_output, expect_success=False)
        require(sha256(diagnostic_output) == diagnostic_digest, 'diagnostic renderer replaced an existing output')

        diagnostic_overlap = diagnostic_work_dir / 'full64-progress.json'
        diagnostic_overlap_digest = sha256(diagnostic_overlap)
        render_diagnostic(diagnostic_work_dir, diagnostic_overlap, expect_success=False)
        require(sha256(diagnostic_overlap) == diagnostic_overlap_digest, 'diagnostic renderer changed an inspected input')

        aggregate_overlap_fields = root / 'aggregate-overlap-fields.npz'
        shutil.copyfile(fields_path, aggregate_overlap_fields)
        aggregate_overlap_digest = sha256(aggregate_overlap_fields)
        aggregate(
            aggregate_overlap_fields, report_path, evaluation_path, authorization_path,
            aggregate_overlap_fields, root / 'aggregate-overlap-summary.json', expect_success=False,
        )
        require(sha256(aggregate_overlap_fields) == aggregate_overlap_digest, 'aggregator overlap changed its input')
        shared_output = root / 'shared-aggregate-output'
        aggregate(
            fields_path, report_path, evaluation_path, authorization_path,
            shared_output, shared_output, expect_success=False,
        )

        with np.load(statistics_path, allow_pickle=False) as statistics:
            require(statistics['velocity_median_ms'].shape == (50333,), 'velocity statistic shape mismatch')
            require(statistics['water_depth_median_m'].shape == (50333,), 'depth statistic shape mismatch')
            require(abs(float(statistics['velocity_median_ms'][1]) - 0.1315) < 1e-12, 'velocity median mismatch')
            require(abs(float(statistics['water_depth_median_m'][0]) - 1.315) < 1e-12, 'depth median mismatch')
            require(float(statistics['flow_direction_agreement_fraction'][0]) > 0.999, 'wrapped direction agreement mismatch')
            require(abs(abs(float(statistics['mean_flow_direction_rad'][0])) - math.pi) < 1e-12, 'wrapped mean direction mismatch')
            require(int(statistics['active_direction_sample_count'][2]) == 0, 'zero-speed direction sample must be inactive')
            require(float(statistics['flow_direction_agreement_fraction'][2]) == 0, 'inactive direction agreement must be zero')
            require(int(statistics['active_direction_sample_count'][3]) == 1, 'single-sample direction fixture mismatch')
            require(float(statistics['flow_direction_agreement_fraction'][3]) == 1, 'single-sample direction agreement mismatch')
            require(np.allclose(statistics['wet_probability'], 1), 'wet probability mismatch')
            require(str(statistics['source_run_report_sha256'].item()) == sha256(report_path), 'statistics report digest mismatch')
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        require(summary['interpretationLimits']['commonPhysicalTime'] is False, 'time-comparison safeguard changed')
        require(summary['interpretationLimits']['sensitivityClaimAllowed'] is False, 'sensitivity safeguard changed')
        require(summary['interpretationLimits']['physicalValidationClaimAllowed'] is False, 'validation safeguard changed')

        stale_evaluation = json.loads(evaluation_path.read_text(encoding='utf-8'))
        stale_evaluation['provenance']['runReportSha256'] = 'f' * 64
        stale_path = root / 'stale-evaluation.json'
        stale_path.write_text(json.dumps(stale_evaluation), encoding='utf-8')
        aggregate(
            fields_path, report_path, stale_path, authorization_path,
            root / 'stale-statistics.npz', root / 'stale-summary.json', expect_success=False,
        )

        nan_arrays = dict(arrays)
        nan_time = simulated_time.copy()
        nan_time[0] = np.nan
        nan_arrays['simulated_time_seconds'] = nan_time
        nan_fields = root / 'nan-time-fields.npz'
        nan_report = root / 'nan-time-report.json'
        nan_evaluation = root / 'nan-time-evaluation.json'
        save_fields(nan_fields, nan_arrays)
        write_report(nan_report, report_template, nan_fields)
        evaluate(authorization_path, nan_report, nan_fields, nan_evaluation)
        aggregate(
            nan_fields, nan_report, nan_evaluation, authorization_path,
            root / 'nan-time-statistics.npz', root / 'nan-time-summary.json', expect_success=False,
        )

        short_arrays = dict(arrays)
        short_arrays['simulated_time_seconds'] = simulated_time[:-1]
        short_fields = root / 'short-time-fields.npz'
        short_report = root / 'short-time-report.json'
        short_evaluation = root / 'short-time-evaluation.json'
        save_fields(short_fields, short_arrays)
        write_report(short_report, report_template, short_fields)
        evaluate(authorization_path, short_report, short_fields, short_evaluation)
        aggregate(
            short_fields, short_report, short_evaluation, authorization_path,
            root / 'short-time-statistics.npz', root / 'short-time-summary.json', expect_success=False,
        )

        float32_arrays = dict(arrays)
        for name in (
            'water_depth_m', 'velocity_u_ms', 'velocity_v_ms', 'mass_balance_error',
            'cfl_max', 'simulated_time_seconds', 'minimum_time_step_seconds', 'maximum_time_step_seconds',
        ):
            float32_arrays[name] = arrays[name].astype(np.float32)
        float32_fields = root / 'float32-fields.npz'
        float32_report = root / 'float32-report.json'
        float32_evaluation = root / 'float32-evaluation.json'
        save_fields(float32_fields, float32_arrays)
        write_report(float32_report, report_template, float32_fields)
        evaluate(authorization_path, float32_report, float32_fields, float32_evaluation)
        float32_result = aggregate(
            float32_fields, float32_report, float32_evaluation, authorization_path,
            root / 'float32-statistics.npz', root / 'float32-summary.json', expect_success=False,
        )
        require('water_depth_m dtype must be float64' in float32_result.stderr, 'float32 rejection reason mismatch')

        aggregate(
            fields_path, report_path, evaluation_path, authorization_path,
            root / 'negative-threshold-statistics.npz', root / 'negative-threshold-summary.json',
            extra=['--dry-threshold-m', '-1'], expect_success=False,
        )

    output = {
        'schema': 'onga-stage18-full64-artifact-validation-v1',
        'status': 'passed',
        'caseCount': 64,
        'cellCount': 50333,
        'verified': [
            'compressed 64-by-50333 field artifact',
            'protected output collision and malformed metric mesh rejection',
            'evaluation-to-report and authorization digest binding',
            'missing field artifact rejection',
            'resolved evaluator and aggregator input-output path separation with fresh outputs',
            'field metadata and report diagnostic binding',
            'float64 field and diagnostic array enforcement',
            'simulated-time shape and finiteness rejection',
            'finite nonnegative aggregation thresholds',
            'velocity and depth quantiles',
            'wet probability and inactive direction handling',
            'circular direction agreement across the plus/minus-pi boundary',
            'step-matched and no-sensitivity interpretation safeguards',
            'seven fixed visual judgment outputs with five PNGs and embedded-SVG integrity',
            'visual manifest source and output digest binding',
            '3840-by-2640 maps with complete 50333-cell raster coverage',
            'four-stop SVG gradients bound to manifest palettes',
            'direction agreement excludes zero- and one-sample cells as visible gray',
            'direction sample support is active case count divided by 64',
            'all visual source digest mismatch and seven-output no-overwrite rejection',
            'deterministic red STOP diagnostic for partial or malformed failed-run evidence',
            'diagnostic secret redaction, fresh-output, and inspected-input safeguards',
        ],
    }
    Path('stage18-full64-artifact-validation.json').write_text(f'{json.dumps(output, indent=2)}\n', encoding='utf-8')
    print(json.dumps(output))


if __name__ == '__main__':
    main()
