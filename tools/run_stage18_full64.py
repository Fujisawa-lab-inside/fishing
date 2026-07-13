#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import resource
import sys
import time
from pathlib import Path

RETIRED_CLI_MESSAGE = (
    'The v1 full64 runner is retired after the Ashiya bridge geometry correction; '
    'no numerical cases were started.'
)

if __name__ == '__main__':
    print(RETIRED_CLI_MESSAGE, file=sys.stderr)
    raise SystemExit(2)

import numpy as np

from run_stage18_production_mesh_pilot import geom, run_case_result


PROTECTED_PATHS = [
    'index.html',
    'pc_full.html',
    'mobile_lite.html',
    'app.js',
    'assets/app.js',
    'OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
    'OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
]

EXPECTED_SOURCE_PILOT = {
    'mergeCommit': 'e22bc2e81ebfb968fc535915e817f268229513a3',
    'headCommit': '958964f41bc3eed3a5e739a693173f1ca4b2197f',
    'workflowRunId': 29229011438,
    'tier': 'pilot',
    'completedCaseCount': 16,
    'passed': True,
}

EXPECTED_MESH_ARRAY_HASHES = {
    'vertices': '719e1206939dee4fdf45fa8bedba13c6608fdff46b885811ba8deb886b9b33c0',
    'triangles': '104b03f5174b5a14a91aca51ee2fbb3cfa32b64679486781413dea930f57141d',
    'segments': '07689a5cbe85a23248ca49f68983570249967de390e31cacb5b310731a371101',
    'segment_markers': '9b5be414b15f71a19825d5f4a50e255e491d9de4f9ceae6d7020b0c9318701e4',
}

EXPECTED_PACKAGE_ARRAYS = {
    'vertex_local_mm': {'shape': [28560, 2], 'dtype': 'int32', 'sha256': '7b65e2a63a65da840b7318b27741412271a37eabc865ca1ee885ff20e41e2e4b'},
    'vertex_image_millipixel': {'shape': [28560, 2], 'dtype': 'int32', 'sha256': '514175658451ec82d8eb3449184d90ad446e24938dbc411811502674edbde779'},
    'triangles': {'shape': [50333, 3], 'dtype': 'int32', 'sha256': '104b03f5174b5a14a91aca51ee2fbb3cfa32b64679486781413dea930f57141d'},
    'internal_face_vertices': {'shape': [72107, 2], 'dtype': 'int32', 'sha256': '123eda613dc6eed147d48238634cdc72b41527bc5b0a2b81db6e779cec044449'},
    'internal_face_cells': {'shape': [72107, 2], 'dtype': 'int32', 'sha256': '8b7ad394cff17129536af5e836f08c2564de3ae8dfa6136f094f0589850700b5'},
    'boundary_face_vertices': {'shape': [6785, 2], 'dtype': 'int32', 'sha256': 'a6b5f9c550a3117d2ada3ce99856fc6823378207a4328c6f7305712470436e15'},
    'boundary_face_cell': {'shape': [6785], 'dtype': 'int32', 'sha256': 'fc4687f57c34e029ddb82d8162702de1ef5f18320f61f61eaa5b68dc13a84f66'},
    'boundary_face_tag': {'shape': [6785], 'dtype': 'uint8', 'sha256': 'c0047c37c44d7abb4f562a4963bcf1e49417e512827bf6c80e71f1c1ccc50698'},
    'barrage_face_ids': {'shape': [68], 'dtype': 'int32', 'sha256': 'e4431bc01ec36c5b272e0a074e385c3638e401dfcc808d52c3eabbe4be0a9c86'},
    'barrage_gate_id': {'shape': [68], 'dtype': 'uint8', 'sha256': '2e4f9937653b020f6326cab02f0c7321676686f16793d391f2674e19ca7b5d1b'},
    'fishway_cells': {'shape': [2], 'dtype': 'int32', 'sha256': '1e1aa278d790d6d33bb4e708879b8fec5bf3f4661141f5366bc2b83e18a7bd6d'},
    'fishway_components': {'shape': [2], 'dtype': 'int32', 'sha256': '01acecb507abfe1a354aa8064f4af5d3f1acd019e37db3c11c97523b71c76e9d'},
}

EXPECTED_MESH_SUMMARY_SHA256 = 'f44b1317f469e34227e83cb0910db75d75404098f0927d93a8e3316ae92060f8'
EXPECTED_ENSEMBLE_SHA256 = '0a926fa20d6260a6cdb113b2a7d5be6807ca87f33350ce82be32ef9e13023ef2'

EXPECTED_ACCEPTANCE = {
    'completionFractionMin': 1.0,
    'nanCountMax': 0,
    'negativeDepthCountMax': 0,
    'maxCflMax': 0.95,
    'maxAbsoluteMassBalanceErrorMax': 1e-8,
    'maxWallSeconds': 3600,
    'maxResidentMemoryMiB': 8192,
}

EXPECTED_ACTIVE_PARAMETERS = [
    'bathymetry.mainstemMeanDepthM',
    'roughness.manningOpenChannel',
    'boundaries.M.phaseShiftMinutes',
    'fishway.mode',
    'fishway.effectiveDischargeCoefficient',
    'fishway.effectiveAreaM2',
    'barrage.scenario.closedVersusOpen',
]

EXPECTED_INACTIVE_PARAMETERS = [
    'bathymetry.crossSectionShape',
    'bathymetry.tributaryMeanDepthM',
    'bathymetry.thalwegOffsetFractionOfLocalWidth',
    'bathymetry.longitudinalSmoothingLengthM',
    'roughness.shallowMarginMultiplier',
    'roughness.structureVicinityMultiplier',
    'boundaries.M.amplitudeMultiplier',
    'boundaries.N.dischargeM3S',
    'boundaries.O.dischargeM3S',
    'boundaries.G.dischargeM3S',
    'barrage.effectiveDischargeCoefficient',
    'barrage.gateOpeningUncertaintyFraction',
    'barrage.scenario.openingMagnitude',
]

EXPECTED_SAFEGUARDS = {
    'inferredParametersAreObservations': False,
    'physicalValidationClaimAllowed': False,
    'publicSimulatorConnectionAllowed': False,
    'legacyFlowCalculationMayChange': False,
    'failedCasesMayBeImputed': False,
    'sensitivityClaimAllowed': False,
    'automaticAdditionalRunsAllowed': False,
}

def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def reject_retired_cli():
    raise RuntimeError(RETIRED_CLI_MESSAGE)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def protected_hashes(repo_root):
    root = Path(repo_root)
    return {path: sha256(root / path) for path in PROTECTED_PATHS}


def peak_rss_mib():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == 'darwin' else rss / 1024


def write_json_atomic(path, payload):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.tmp')
    temporary.write_text(
        f'{json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)}\n',
        encoding='utf-8',
    )
    os.replace(temporary, destination)


def save_npz_atomic(path, **arrays):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.tmp')
    with temporary.open('wb') as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(temporary, destination)


def validate_fresh_outputs(input_paths, output_paths, repo_root):
    resolved_inputs = {Path(path).resolve() for path in input_paths}
    resolved_protected = {(Path(repo_root) / path).resolve() for path in PROTECTED_PATHS}
    resolved_outputs = [Path(path).resolve() for path in output_paths]
    require(len(set(resolved_outputs)) == len(resolved_outputs), 'output paths must be distinct')
    for raw, resolved in zip(output_paths, resolved_outputs):
        require(resolved not in resolved_inputs, f'output path overlaps an input: {raw}')
        require(resolved not in resolved_protected, f'output path overlaps a protected surface: {raw}')
        require(not Path(raw).exists(), f'output already exists: {raw}')


def validate_authorization(config):
    require(config.get('schema') == 'onga-stage18-full64-run-authorization-v1', 'unsupported authorization schema')
    require(config.get('authorized') is True, 'full64 run is not authorized')
    require(config.get('approvedBy') == 'Ryusuke Fujisawa', 'authorization approver changed')
    require(config.get('approvedDate') == '2026-07-13', 'authorization date changed')
    require(config.get('sourceStatement') == '作業を開始してください．', 'authorization source statement changed')
    require(config.get('scope') == 'exactly_64_provisional_inference_cases_for_runtime_and_numerical_stability_evidence', 'authorization scope changed')
    require(config.get('sourcePilot') == EXPECTED_SOURCE_PILOT, 'pilot authorization provenance changed')
    require(config.get('geometry') == {'approvedWaterPixelCount': 679791, 'metricMeshCellCount': 50333, 'frozen': True}, 'geometry authorization mismatch')
    mesh_expected = config.get('meshExpected', {})
    require(mesh_expected.get('sourceWorkflowRunId') == 29191537971, 'mesh workflow provenance changed')
    require(mesh_expected.get('sourceCommit') == '43d94c8e26c0cb86ec33166fa28628f8cff664fd', 'mesh source commit changed')
    require(mesh_expected.get('sourceArtifactName') == 'stage16-metric-fv-mesh', 'mesh artifact provenance changed')
    for key, expected in (('vertices', 28560), ('cells', 50333), ('internalFaces', 72107), ('boundaryFaces', 6785), ('barrageFaces', 68)):
        require(mesh_expected.get(key) == expected, f'authorized mesh {key} mismatch')
    require(mesh_expected.get('summarySha256') == EXPECTED_MESH_SUMMARY_SHA256, 'authorized mesh summary digest changed')
    require(mesh_expected.get('meshArrayHashes') == EXPECTED_MESH_ARRAY_HASHES, 'authorized mesh array digests changed')
    require(mesh_expected.get('packageArrays') == EXPECTED_PACKAGE_ARRAYS, 'authorized metric mesh package changed')
    ensemble_expected = config.get('ensembleExpected')
    require(ensemble_expected == {
        'schema': 'onga-stage18-inference-ensemble-v1',
        'generatedFrom': 'onga-stage17-inferred-physical-prior-v1',
        'seed': 20260713,
        'caseCount': 64,
        'sha256': EXPECTED_ENSEMBLE_SHA256,
    }, 'authorized ensemble identity changed')
    require(config.get('run') == {
        'caseCount': 64,
        'ensembleSeed': 20260713,
        'maxStepsPerCase': 500,
        'comparisonBasis': 'equal_step_count_not_equal_simulated_time',
    }, 'run contract changed')
    require(config.get('acceptance') == EXPECTED_ACCEPTANCE, 'acceptance thresholds changed')
    require(config.get('parameterCoverage') == {
        'active': EXPECTED_ACTIVE_PARAMETERS,
        'inactive': EXPECTED_INACTIVE_PARAMETERS,
    }, 'parameter coverage changed')
    require(config.get('safeguards') == EXPECTED_SAFEGUARDS, 'authorization safeguards changed')


def validate_ensemble(ensemble, config, ensemble_path):
    require(sha256(ensemble_path) == config['ensembleExpected']['sha256'], 'ensemble file digest mismatch')
    require(ensemble.get('schema') == config['ensembleExpected']['schema'], 'unsupported ensemble schema')
    require(ensemble.get('generatedFrom') == config['ensembleExpected']['generatedFrom'], 'ensemble source changed')
    require(ensemble.get('count') == 64, 'ensemble count must be 64')
    require(ensemble.get('seed') == config['run']['ensembleSeed'], 'ensemble seed mismatch')
    require(ensemble.get('samplingMethod') == 'deterministic_stratified_marginals_with_categorical_rotation', 'sampling method changed')
    require(ensemble.get('governingEquation') == 'depth_averaged_shallow_water', 'governing equation changed')
    require(ensemble.get('geometry') == config['geometry'], 'ensemble geometry mismatch')
    require(ensemble.get('safeguards') == {
        'singleBestGuessForbidden': True,
        'physicalValidationClaimAllowed': False,
        'publicSimulatorConnectionAllowed': False,
        'visualFittingForbidden': True,
        'physicalRunEnabled': False,
    }, 'ensemble safeguards changed')
    cases = ensemble.get('cases')
    require(isinstance(cases, list) and len(cases) == 64, 'exactly 64 ensemble cases required')
    expected = [f'stage18-{index:04d}' for index in range(1, 65)]
    require([case.get('caseId') for case in cases] == expected, 'case IDs must be the canonical ordered 64-case set')
    require(all(case.get('classification') == 'provisional_inference_case_not_observation' for case in cases), 'case classification changed')
    return cases


def validate_mesh_summary(summary, config, summary_path):
    require(sha256(summary_path) == config['meshExpected']['summarySha256'], 'mesh summary file digest mismatch')
    require(summary.get('status') == 'passed', 'mesh generation summary must pass')
    expected = config['meshExpected']
    counts = summary.get('counts', {})
    for key in ('vertices', 'cells', 'internalFaces', 'boundaryFaces', 'barrageFaces'):
        require(counts.get(key) == expected[key], f'mesh summary {key} mismatch')
    require(summary.get('meshArrayHashes') == expected['meshArrayHashes'], 'mesh array digest mismatch')
    safeguards = summary.get('safeguards', {})
    require(safeguards == {
        'approvedWaterGeometryChanged': False,
        'physicalValuesAssigned': False,
        'connectedToPublicSimulator': False,
        'calibrationPerformed': False,
    }, 'mesh-generation safeguards changed')


def validate_mesh_package(mesh_path, config):
    expected = config['meshExpected']['packageArrays']
    with np.load(mesh_path, allow_pickle=False) as package:
        require(package.files == list(expected), 'metric mesh package arrays changed')
        for name, contract in expected.items():
            values = package[name]
            require(list(values.shape) == contract['shape'], f'{name} shape mismatch')
            require(str(values.dtype) == contract['dtype'], f'{name} dtype mismatch')
            digest = hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
            require(digest == contract['sha256'], f'{name} digest mismatch')


def validate_case_result(result, expected_steps, cell_count):
    require(result.get('stepsCompleted') == expected_steps, 'case step count mismatch')
    for key in (
        'massBalanceError', 'maxCfl', 'minimumDepthM', 'simulatedTimeSeconds',
        'minimumTimeStepSeconds', 'maximumTimeStepSeconds',
    ):
        require(math.isfinite(result.get(key, math.nan)) and result[key] >= 0, f'{key} must be finite and nonnegative')
    require(result['simulatedTimeSeconds'] > 0, 'simulated time must be positive')
    require(result['minimumTimeStepSeconds'] > 0, 'minimum time step must be positive')
    require(result['maximumTimeStepSeconds'] >= result['minimumTimeStepSeconds'], 'time-step range invalid')
    require(result.get('nanCount') == 0, 'case returned NaN state')
    require(result.get('negativeDepthCount') == 0, 'case returned negative depth')
    for key in ('waterDepthM', 'velocityUms', 'velocityVms'):
        values = np.asarray(result.get(key))
        require(values.shape == (cell_count,), f'{key} shape mismatch')
        require(np.isfinite(values).all(), f'{key} contains nonfinite values')
    require((np.asarray(result['waterDepthM']) >= 0).all(), 'waterDepthM contains negative values')


def progress_payload(authorization, attempted_ids, diagnostics, failures, started, status, terminal_failure=None):
    completed = sum(item['status'] == 'completed' for item in diagnostics)
    payload = {
        'schema': 'onga-stage18-full64-progress-v1',
        'classification': 'provisional_full64_runtime_and_numerical_stability_evidence_only',
        'status': status,
        'geometry': authorization['geometry'],
        'ensembleSeed': authorization['run']['ensembleSeed'],
        'requestedCaseCount': 64,
        'attemptedCaseIds': attempted_ids,
        'completedCaseCount': completed,
        'failedCaseCount': len(failures),
        'wallSeconds': time.perf_counter() - started,
        'caseDiagnostics': diagnostics,
        'failures': failures,
        'comparisonBasis': authorization['run']['comparisonBasis'],
    }
    if terminal_failure is not None:
        payload['terminalFailure'] = terminal_failure
    return payload


def finite_aggregate(values, operation):
    finite = values[np.isfinite(values)]
    return float(operation(finite)) if finite.size else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mesh')
    parser.add_argument('ensemble')
    parser.add_argument('authorization')
    parser.add_argument('--mesh-summary', required=True)
    parser.add_argument('--fields-output', required=True)
    parser.add_argument('--report-output', required=True)
    parser.add_argument('--progress-output', required=True)
    parser.add_argument('--repo-root', default='.')
    args = parser.parse_args()

    reject_retired_cli()

    validate_fresh_outputs(
        [args.mesh, args.ensemble, args.authorization, args.mesh_summary],
        [args.fields_output, args.report_output, args.progress_output],
        args.repo_root,
    )
    authorization = json.loads(Path(args.authorization).read_text(encoding='utf-8'))
    ensemble = json.loads(Path(args.ensemble).read_text(encoding='utf-8'))
    mesh_summary = json.loads(Path(args.mesh_summary).read_text(encoding='utf-8'))
    validate_authorization(authorization)
    cases = validate_ensemble(ensemble, authorization, args.ensemble)
    validate_mesh_summary(mesh_summary, authorization, args.mesh_summary)
    validate_mesh_package(args.mesh, authorization)
    geometry = geom(args.mesh)
    cell_count = len(geometry[2])
    require(cell_count == 50333, f'production mesh must contain 50333 cells, got {cell_count}')

    protected_before = protected_hashes(args.repo_root)
    case_count = 64
    water_depth = np.full((case_count, cell_count), np.nan, dtype=np.float64)
    velocity_u = np.full_like(water_depth, np.nan)
    velocity_v = np.full_like(water_depth, np.nan)
    mass_error = np.full(case_count, np.nan, dtype=np.float64)
    cfl_max = np.full(case_count, np.nan, dtype=np.float64)
    simulated_time = np.full(case_count, np.nan, dtype=np.float64)
    minimum_time_step = np.full(case_count, np.nan, dtype=np.float64)
    maximum_time_step = np.full(case_count, np.nan, dtype=np.float64)
    failures = []
    diagnostics = []
    attempted_ids = []
    nan_count = 0
    negative_depth_count = 0
    started = time.perf_counter()

    for index, case in enumerate(cases):
        case_id = case['caseId']
        attempted_ids.append(case_id)
        case_started = time.perf_counter()
        try:
            result = run_case_result(case, authorization['run']['maxStepsPerCase'], geometry, include_fields=True)
            validate_case_result(result, authorization['run']['maxStepsPerCase'], cell_count)
            water_depth[index] = result['waterDepthM']
            velocity_u[index] = result['velocityUms']
            velocity_v[index] = result['velocityVms']
            mass_error[index] = result['massBalanceError']
            cfl_max[index] = result['maxCfl']
            simulated_time[index] = result['simulatedTimeSeconds']
            minimum_time_step[index] = result['minimumTimeStepSeconds']
            maximum_time_step[index] = result['maximumTimeStepSeconds']
            nan_count += result['nanCount']
            negative_depth_count += result['negativeDepthCount']
            diagnostics.append({
                'caseId': case_id,
                'status': 'completed',
                'wallSeconds': time.perf_counter() - case_started,
                'stepsCompleted': result['stepsCompleted'],
                'simulatedTimeSeconds': result['simulatedTimeSeconds'],
                'minimumTimeStepSeconds': result['minimumTimeStepSeconds'],
                'maximumTimeStepSeconds': result['maximumTimeStepSeconds'],
                'massBalanceError': result['massBalanceError'],
                'maxCfl': result['maxCfl'],
                'minimumDepthM': result['minimumDepthM'],
            })
        except Exception as error:
            nan_count += int(getattr(error, 'nan_count', 0))
            negative_depth_count += int(getattr(error, 'negative_depth_count', 0))
            reason = f'{type(error).__name__}: {error}'
            failures.append({'caseId': case_id, 'reason': reason})
            diagnostics.append({
                'caseId': case_id,
                'status': 'failed',
                'wallSeconds': time.perf_counter() - case_started,
                'reason': reason,
            })
        write_json_atomic(
            args.progress_output,
            progress_payload(authorization, attempted_ids, diagnostics, failures, started, 'running'),
        )
        print(json.dumps({'caseId': case_id, 'status': diagnostics[-1]['status'], 'completed': index + 1, 'total': case_count}), flush=True)

    wall_seconds = time.perf_counter() - started
    completed_count = sum(item['status'] == 'completed' for item in diagnostics)
    case_wall_seconds_total = 0.0
    for diagnostic in diagnostics:
        case_wall_seconds_total += diagnostic['wallSeconds']
    protected_after = protected_hashes(args.repo_root)
    protected_unchanged = protected_before == protected_after
    field_artifact = None

    if completed_count == case_count:
        require(np.isfinite(water_depth).all(), 'nonfinite water depth field')
        require(np.isfinite(velocity_u).all() and np.isfinite(velocity_v).all(), 'nonfinite velocity field')
        require((water_depth >= 0).all(), 'negative water depth field')
        save_npz_atomic(
            args.fields_output,
            schema=np.array('onga-stage18-full64-fields-v1'),
            case_ids=np.array(attempted_ids),
            water_depth_m=water_depth,
            velocity_u_ms=velocity_u,
            velocity_v_ms=velocity_v,
            mass_balance_error=mass_error,
            cfl_max=cfl_max,
            simulated_time_seconds=simulated_time,
            minimum_time_step_seconds=minimum_time_step,
            maximum_time_step_seconds=maximum_time_step,
            mesh_sha256=np.array(sha256(args.mesh)),
            mesh_summary_sha256=np.array(sha256(args.mesh_summary)),
            ensemble_sha256=np.array(sha256(args.ensemble)),
            authorization_sha256=np.array(sha256(args.authorization)),
            comparison_basis=np.array(authorization['run']['comparisonBasis']),
        )
        field_artifact = {
            'path': str(Path(args.fields_output)),
            'sha256': sha256(args.fields_output),
            'shape': {'caseCount': case_count, 'cellCount': cell_count},
            'dtype': 'float64',
        }

    report = {
        'schema': 'onga-stage18-full64-run-report-v1',
        'classification': 'provisional_full64_runtime_and_numerical_stability_evidence_only',
        'geometry': authorization['geometry'],
        'ensembleSeed': ensemble['seed'],
        'requestedCaseCount': case_count,
        'attemptedCaseIds': attempted_ids,
        'completedCaseCount': completed_count,
        'failedCaseCount': len(failures),
        'wallSeconds': wall_seconds,
        'caseWallSecondsTotal': case_wall_seconds_total,
        'peakResidentMemoryMiB': peak_rss_mib(),
        'maxCfl': finite_aggregate(cfl_max, np.max),
        'maxAbsoluteMassBalanceError': finite_aggregate(np.abs(mass_error), np.max),
        'minimumDepthM': finite_aggregate(water_depth, np.min),
        'minimumSimulatedTimeSeconds': finite_aggregate(simulated_time, np.min),
        'maximumSimulatedTimeSeconds': finite_aggregate(simulated_time, np.max),
        'nanCount': nan_count,
        'negativeDepthCount': negative_depth_count,
        'comparisonBasis': authorization['run']['comparisonBasis'],
        'parameterCoverage': authorization['parameterCoverage'],
        'failures': failures,
        'caseDiagnostics': diagnostics,
        'inputDigests': {
            'meshSha256': sha256(args.mesh),
            'meshSummarySha256': sha256(args.mesh_summary),
            'ensembleSha256': sha256(args.ensemble),
            'authorizationSha256': sha256(args.authorization),
        },
        'meshSummaryVerified': True,
        'fieldArtifact': field_artifact,
        'protectedSurfaceHashesBefore': protected_before,
        'protectedSurfaceHashesAfter': protected_after,
        'protectedSurfaceHashesUnchanged': protected_unchanged,
        'safeguards': authorization['safeguards'],
    }
    write_json_atomic(args.report_output, report)

    terminal_failure = None
    if failures:
        terminal_failure = f'{len(failures)} full64 cases failed'
    elif not protected_unchanged:
        terminal_failure = 'public or legacy surface changed during full64 run'
    write_json_atomic(
        args.progress_output,
        progress_payload(
            authorization,
            attempted_ids,
            diagnostics,
            failures,
            started,
            'failed' if terminal_failure else 'completed',
            terminal_failure,
        ),
    )
    print(json.dumps({'report': args.report_output, 'completedCaseCount': completed_count, 'failedCaseCount': len(failures), 'wallSeconds': wall_seconds}), flush=True)
    if terminal_failure:
        raise RuntimeError(terminal_failure)


if __name__ == '__main__':
    main()
