#!/usr/bin/env python3
import copy
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
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


def main():
    authorization_path = Path('config/stage18_full64_run_authorization_v1.json')
    authorization = json.loads(authorization_path.read_text(encoding='utf-8'))
    authorization_digest = sha256(authorization_path)
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
            'mesh_sha256': np.array('a' * 64),
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
                'meshSha256': 'a' * 64,
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
        ],
    }
    Path('stage18-full64-artifact-validation.json').write_text(f'{json.dumps(output, indent=2)}\n', encoding='utf-8')
    print(json.dumps(output))


if __name__ == '__main__':
    main()
