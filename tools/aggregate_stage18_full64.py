#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from run_stage18_full64 import validate_authorization


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def scalar_text(archive, key):
    value = archive[key]
    require(value.shape == (), f'{key} must be a scalar')
    return str(value.item())


def save_npz_atomic(path, **arrays):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.tmp')
    with temporary.open('wb') as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(temporary, destination)


def save_json_atomic(path, payload):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.tmp')
    temporary.write_text(f'{json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)}\n', encoding='utf-8')
    os.replace(temporary, destination)


def validate_output_paths(input_paths, output_paths):
    inputs = [Path(path).resolve() for path in input_paths]
    outputs = [Path(path).resolve() for path in output_paths]
    require(len(set(inputs + outputs)) == len(inputs) + len(outputs), 'aggregation input and output paths must be distinct')
    for raw in output_paths:
        require(not Path(raw).exists(), f'aggregation output already exists: {raw}')


def bounds(values):
    return {'minimum': float(np.min(values)), 'maximum': float(np.max(values))}


def finite_nonnegative(value, label):
    require(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0, f'{label} must be finite and nonnegative')


def require_close(actual, expected, label):
    require(math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-15), f'{label} mismatch')


def require_float64(arrays):
    for name, values in arrays.items():
        require(values.dtype == np.dtype(np.float64), f'{name} dtype must be float64')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('fields')
    parser.add_argument('run_report')
    parser.add_argument('evaluation')
    parser.add_argument('authorization')
    parser.add_argument('--statistics-output', required=True)
    parser.add_argument('--summary-output', required=True)
    parser.add_argument('--dry-threshold-m', type=float, default=1e-4)
    parser.add_argument('--direction-speed-threshold-ms', type=float, default=1e-9)
    args = parser.parse_args()

    validate_output_paths(
        [args.fields, args.run_report, args.evaluation, args.authorization],
        [args.statistics_output, args.summary_output],
    )

    report = json.loads(Path(args.run_report).read_text(encoding='utf-8'))
    evaluation = json.loads(Path(args.evaluation).read_text(encoding='utf-8'))
    authorization = json.loads(Path(args.authorization).read_text(encoding='utf-8'))
    validate_authorization(authorization)
    finite_nonnegative(args.dry_threshold_m, 'dry threshold')
    finite_nonnegative(args.direction_speed_threshold_ms, 'direction speed threshold')
    require(report.get('schema') == 'onga-stage18-full64-run-report-v1', 'unsupported run report')
    require(evaluation.get('schema') == 'onga-stage18-full64-evaluation-v1', 'unsupported evaluation')
    require(evaluation.get('passed') is True, 'full64 evaluation must pass before aggregation')
    require(evaluation.get('offlineStepMatchedStatisticsAllowed') is True, 'offline statistics not allowed')
    require(evaluation.get('sensitivityClaimAllowed') is False, 'sensitivity safeguard changed')
    provenance = evaluation.get('provenance', {})
    require(provenance.get('authorizationSha256') == sha256(args.authorization), 'evaluation authorization digest mismatch')
    require(provenance.get('runReportSha256') == sha256(args.run_report), 'evaluation run-report digest mismatch')
    require(provenance.get('fieldArtifactSha256') == sha256(args.fields), 'evaluation field digest mismatch')
    require(provenance.get('meshSha256') == report.get('inputDigests', {}).get('meshSha256'), 'evaluation mesh digest mismatch')
    require(provenance.get('meshSummarySha256') == report.get('inputDigests', {}).get('meshSummarySha256'), 'evaluation mesh-summary digest mismatch')
    require(provenance.get('ensembleSha256') == report.get('inputDigests', {}).get('ensembleSha256'), 'evaluation ensemble digest mismatch')
    require(report.get('completedCaseCount') == 64 and report.get('failedCaseCount') == 0, '64/64 completed cases required')
    require(report.get('comparisonBasis') == 'equal_step_count_not_equal_simulated_time', 'comparison basis mismatch')
    require(report.get('protectedSurfaceHashesUnchanged') is True, 'protected surfaces changed')
    require(report.get('fieldArtifact', {}).get('sha256') == sha256(args.fields), 'field artifact digest mismatch')
    require(report.get('inputDigests', {}).get('authorizationSha256') == sha256(args.authorization), 'authorization digest mismatch')
    require(report.get('geometry') == authorization.get('geometry'), 'report geometry mismatch')
    require(report.get('ensembleSeed') == authorization.get('run', {}).get('ensembleSeed'), 'report ensemble seed mismatch')
    acceptance = authorization.get('acceptance', {})
    finite_nonnegative(report.get('maxCfl'), 'report maxCfl')
    finite_nonnegative(report.get('maxAbsoluteMassBalanceError'), 'report mass balance')
    finite_nonnegative(report.get('wallSeconds'), 'report wall time')
    finite_nonnegative(report.get('peakResidentMemoryMiB'), 'report memory')
    finite_nonnegative(report.get('minimumDepthM'), 'report minimum depth')
    require(report.get('nanCount') == 0 and report.get('negativeDepthCount') == 0, 'invalid numerical state count')
    require(report['maxCfl'] <= acceptance.get('maxCflMax'), 'report CFL exceeds authorization')
    require(report['maxAbsoluteMassBalanceError'] <= acceptance.get('maxAbsoluteMassBalanceErrorMax'), 'report mass balance exceeds authorization')
    require(report['wallSeconds'] <= acceptance.get('maxWallSeconds'), 'report wall time exceeds authorization')
    require(report['peakResidentMemoryMiB'] <= acceptance.get('maxResidentMemoryMiB'), 'report memory exceeds authorization')

    with np.load(args.fields, allow_pickle=False) as fields:
        require(scalar_text(fields, 'schema') == 'onga-stage18-full64-fields-v1', 'unsupported field schema')
        require(scalar_text(fields, 'comparison_basis') == report['comparisonBasis'], 'field comparison basis mismatch')
        require(scalar_text(fields, 'mesh_sha256') == report['inputDigests']['meshSha256'], 'field mesh digest mismatch')
        require(scalar_text(fields, 'mesh_summary_sha256') == report['inputDigests']['meshSummarySha256'], 'field mesh-summary digest mismatch')
        require(scalar_text(fields, 'ensemble_sha256') == report['inputDigests']['ensembleSha256'], 'field ensemble digest mismatch')
        require(scalar_text(fields, 'authorization_sha256') == report['inputDigests']['authorizationSha256'], 'field authorization digest mismatch')
        case_ids = fields['case_ids']
        expected_ids = np.array([f'stage18-{index:04d}' for index in range(1, 65)])
        require(np.array_equal(case_ids, expected_ids), 'field case IDs mismatch')
        depth = fields['water_depth_m']
        velocity_u = fields['velocity_u_ms']
        velocity_v = fields['velocity_v_ms']
        mass_error = fields['mass_balance_error']
        cfl_max = fields['cfl_max']
        simulated_time = fields['simulated_time_seconds']
        minimum_time_step = fields['minimum_time_step_seconds']
        maximum_time_step = fields['maximum_time_step_seconds']

        require_float64({
            'water_depth_m': depth,
            'velocity_u_ms': velocity_u,
            'velocity_v_ms': velocity_v,
            'mass_balance_error': mass_error,
            'cfl_max': cfl_max,
            'simulated_time_seconds': simulated_time,
            'minimum_time_step_seconds': minimum_time_step,
            'maximum_time_step_seconds': maximum_time_step,
        })
        require(depth.shape == (64, 50333), f'unexpected depth shape {depth.shape}')
        require(velocity_u.shape == depth.shape and velocity_v.shape == depth.shape, 'velocity shape mismatch')
        require(mass_error.shape == (64,) and cfl_max.shape == (64,), 'diagnostic shape mismatch')
        require(simulated_time.shape == (64,), 'simulated-time shape mismatch')
        require(minimum_time_step.shape == (64,) and maximum_time_step.shape == (64,), 'time-step shape mismatch')
        require(np.isfinite(depth).all() and np.isfinite(velocity_u).all() and np.isfinite(velocity_v).all(), 'nonfinite cell field')
        require(np.isfinite(mass_error).all() and np.isfinite(cfl_max).all(), 'nonfinite case diagnostic')
        require(np.isfinite(simulated_time).all() and np.all(simulated_time > 0), 'invalid simulated time')
        require(np.isfinite(minimum_time_step).all() and np.all(minimum_time_step > 0), 'invalid minimum time step')
        require(np.isfinite(maximum_time_step).all() and np.all(maximum_time_step >= minimum_time_step), 'invalid maximum time step')
        require((depth >= 0).all(), 'negative water depth')
        require_close(np.max(cfl_max), report['maxCfl'], 'report maxCfl')
        require_close(np.max(np.abs(mass_error)), report['maxAbsoluteMassBalanceError'], 'report mass balance')
        require_close(np.min(depth), report['minimumDepthM'], 'report minimum depth')
        require_close(np.min(simulated_time), report['minimumSimulatedTimeSeconds'], 'report minimum simulated time')
        require_close(np.max(simulated_time), report['maximumSimulatedTimeSeconds'], 'report maximum simulated time')

        speed = np.hypot(velocity_u, velocity_v)
        velocity_quantiles = np.quantile(speed, [0.025, 0.25, 0.5, 0.75, 0.975], axis=0)
        depth_quantiles = np.quantile(depth, [0.025, 0.25, 0.5, 0.75, 0.975], axis=0)
        wet_probability = np.mean(depth > args.dry_threshold_m, axis=0)

        active = (depth > args.dry_threshold_m) & (speed > args.direction_speed_threshold_ms)
        unit_u = np.divide(velocity_u, speed, out=np.zeros_like(velocity_u), where=active)
        unit_v = np.divide(velocity_v, speed, out=np.zeros_like(velocity_v), where=active)
        active_count = np.sum(active, axis=0)
        mean_unit_u = np.divide(np.sum(unit_u, axis=0), active_count, out=np.zeros(depth.shape[1]), where=active_count > 0)
        mean_unit_v = np.divide(np.sum(unit_v, axis=0), active_count, out=np.zeros(depth.shape[1]), where=active_count > 0)
        direction_agreement = np.hypot(mean_unit_u, mean_unit_v)
        mean_direction = np.where(active_count > 0, np.arctan2(mean_unit_v, mean_unit_u), np.nan)

        velocity_p025, velocity_q1, velocity_median, velocity_q3, velocity_p975 = velocity_quantiles
        depth_p025, depth_q1, depth_median, depth_q3, depth_p975 = depth_quantiles
        arrays = {
            'schema': np.array('onga-stage18-full64-step-matched-statistics-v1'),
            'cell_id': np.arange(depth.shape[1], dtype=np.int32),
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
            'dry_threshold_m': np.array(args.dry_threshold_m),
            'direction_speed_threshold_ms': np.array(args.direction_speed_threshold_ms),
            'source_fields_sha256': np.array(sha256(args.fields)),
            'source_run_report_sha256': np.array(sha256(args.run_report)),
            'source_evaluation_sha256': np.array(sha256(args.evaluation)),
            'source_authorization_sha256': np.array(sha256(args.authorization)),
            'comparison_basis': np.array(report['comparisonBasis']),
        }
        save_npz_atomic(args.statistics_output, **arrays)

        summary = {
            'schema': 'onga-stage18-full64-step-matched-statistics-summary-v1',
            'classification': 'provisional_step_matched_numerical_endpoint_statistics_not_physical_validation',
            'sourceCaseCount': 64,
            'cellCount': 50333,
            'geometry': authorization['geometry'],
            'comparisonBasis': report['comparisonBasis'],
            'simulatedTimeSeconds': bounds(simulated_time),
            'dryThresholdM': args.dry_threshold_m,
            'directionSpeedThresholdMs': args.direction_speed_threshold_ms,
            'fields': {
                'velocityMedianMs': bounds(velocity_median),
                'velocityIqrWidthMs': bounds(velocity_q3 - velocity_q1),
                'velocityP95WidthMs': bounds(velocity_p975 - velocity_p025),
                'waterDepthMedianM': bounds(depth_median),
                'waterDepthIqrWidthM': bounds(depth_q3 - depth_q1),
                'waterDepthP95WidthM': bounds(depth_p975 - depth_p025),
                'wetProbability': bounds(wet_probability),
                'flowDirectionAgreementFraction': bounds(direction_agreement),
            },
            'runDiagnostics': {
                'massBalanceAbsoluteMedian': float(np.median(np.abs(mass_error))),
                'massBalanceAbsoluteMaximum': float(np.max(np.abs(mass_error))),
                'maxCfl': float(np.max(cfl_max)),
            },
            'parameterCoverage': report['parameterCoverage'],
            'interpretationLimits': {
                'commonPhysicalTime': False,
                'waterSurfaceElevationAvailable': False,
                'sensitivityClaimAllowed': False,
                'physicalValidationClaimAllowed': False,
                'publicSimulatorConnectionAllowed': False,
            },
            'artifacts': {
                'sourceFieldsSha256': sha256(args.fields),
                'runReportSha256': sha256(args.run_report),
                'evaluationSha256': sha256(args.evaluation),
                'authorizationSha256': sha256(args.authorization),
                'statisticsSha256': sha256(args.statistics_output),
            },
        }
        save_json_atomic(args.summary_output, summary)
        print(json.dumps({'statistics': args.statistics_output, 'summary': args.summary_output, 'status': 'generated'}))


if __name__ == '__main__':
    main()
