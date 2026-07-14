#!/usr/bin/env python3
"""Fail-closed evaluator for the corrected-geometry Stage 18 full64 run."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any


CONTRACT_SCHEMA = 'onga-stage18-full64-execution-contract-v2'
AUTHORIZATION_SCHEMA = 'onga-stage18-full64-run-authorization-v2'
REPORT_SCHEMA = 'onga-stage18-full64-run-report-v2'
FIELDS_SCHEMA = 'onga-stage18-full64-fields-v2'
EVALUATION_SCHEMA = 'onga-stage18-full64-evaluation-v2'
CLASSIFICATION = 'provisional_full64_runtime_and_numerical_stability_evidence_only'
AUTHORIZATION_SCOPE = 'exactly_64_corrected_geometry_v2_cases_for_runtime_and_numerical_stability_evidence'
AUTHORIZATION_SOURCE_STATEMENT = (
    '承認済み橋下補正v2上で、この判断資料に示された64条件×500ステップを、'
    '承認後24時間以内に一回限りの数値安定性確認として実行してよい。'
)
DECISION_IMAGE_PATH = 'docs/visuals/stage18-v2-execution-decision.svg'
CONTRACT_PATH = 'config/stage18_full64_execution_contract_v2.json'
AUTHORIZATION_PATH = 'config/stage18_full64_run_authorization_v2.json'

CASE_COUNT = 64
CELL_COUNT = 50129
MESH_VERSION = 'stage16-metric-fv-mesh-v2'
MESH_PACKAGE_SHA256 = 'f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2'
ENSEMBLE_SHA256 = 'ef0fc1cd8cba91ebbdcd0921260543f829c637b3c9508ea9c2dfeff5aa766684'
COMPARISON_BASIS = 'equal_step_count_not_equal_simulated_time'

EXPECTED_ACCEPTANCE = {
    'completionFractionMin': 1.0,
    'nanCountMax': 0,
    'negativeDepthCountMax': 0,
    'maxCflMax': 0.95,
    'maxAbsoluteMassBalanceErrorMax': 1e-8,
    'maxWallSeconds': 3600,
    'maxResidentMemoryMiB': 8192,
}

EXPECTED_STOP_POLICY = {
    'immediateStopOnAnyCaseFailure': True,
    'immediateStopOnNan': True,
    'immediateStopOnNegativeDepth': True,
    'immediateStopOnCflExceedance': True,
    'immediateStopOnMassBalanceExceedance': True,
    'immediateStopOnWallTimeExceedance': True,
    'immediateStopOnMemoryExceedance': True,
    'failedCasesMayBeImputed': False,
}

EXPECTED_PROTECTED_PATHS = [
    'index.html',
    'pc_full.html',
    'mobile_lite.html',
    'app.js',
    'assets/app.js',
    'OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
    'OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
]

REQUIRED_FIELD_ARRAYS = {
    'water_depth_m': (CASE_COUNT, CELL_COUNT),
    'velocity_u_ms': (CASE_COUNT, CELL_COUNT),
    'velocity_v_ms': (CASE_COUNT, CELL_COUNT),
    'mass_balance_error': (CASE_COUNT,),
    'cfl_max': (CASE_COUNT,),
    'simulated_time_seconds': (CASE_COUNT,),
    'minimum_time_step_seconds': (CASE_COUNT,),
    'maximum_time_step_seconds': (CASE_COUNT,),
}

FALSE_AUTHORIZATION_SAFEGUARDS = (
    'automaticAdditionalRunsAllowed',
    'automaticRetryAllowed',
    'inferredParametersAreObservations',
    'physicalValidationClaimAllowed',
    'sensitivityClaimAllowed',
    'publicSimulatorConnectionAllowed',
    'legacyFlowCalculationMayChange',
    'failedCasesMayBeImputed',
)

EXPECTED_AUTHORIZATION_KEYS = {
    'schema', 'authorizationId', 'authorized', 'oneTime', 'approvedBy',
    'approvedDate', 'issuedAtUtc', 'notAfterUtc', 'sourceStatement', 'scope', 'decisionImage',
    'executionContract', 'reviewedCodeCommit', 'geometry', 'meshExpected',
    'ensembleExpected', 'run', 'acceptance', 'safeguards',
}

EXPECTED_REPORT_KEYS = {
    'schema', 'classification', 'geometry', 'ensembleSeed', 'requestedCaseCount',
    'attemptedCaseIds', 'completedCaseCount', 'failedCaseCount', 'wallSeconds',
    'caseWallSecondsTotal', 'peakResidentMemoryMiB', 'maxCfl',
    'maxAbsoluteMassBalanceError', 'minimumDepthM', 'minimumSimulatedTimeSeconds',
    'maximumSimulatedTimeSeconds', 'nanCount', 'negativeDepthCount',
    'comparisonBasis', 'parameterCoverage', 'failures', 'caseDiagnostics',
    'inputDigests', 'fieldArtifact', 'protectedSurfaceHashesBefore',
    'protectedSurfaceHashesAfter', 'protectedSurfaceHashesUnchanged',
    'safeguards', 'stopPolicy',
}

EXPECTED_FIELD_NAMES = {
    'schema', 'case_ids', *REQUIRED_FIELD_ARRAYS,
    'execution_contract_sha256', 'authorization_sha256', 'mesh_sha256',
    'mesh_summary_sha256', 'ensemble_sha256', 'comparison_basis',
}

SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')

EXPECTED_CONTRACT_KEYS = {
    'schema', 'status', 'executionAuthorized', 'authorization', 'authorizationContract',
    'geometry', 'meshExpected', 'ensembleExpected', 'run', 'acceptance', 'safeguards',
    'protectedPaths', 'parameterCoverage', 'outputs', 'stopPolicy', 'claimLimits',
    'visualDecision',
}
EXPECTED_RUN = {
    'purpose': 'offline_runtime_and_numerical_stability_evidence_only',
    'resultsClassification': CLASSIFICATION,
    'caseCount': CASE_COUNT,
    'ensembleSeed': 20260713,
    'maxStepsPerCase': 500,
    'comparisonBasis': COMPARISON_BASIS,
    'checkpointCompletedCaseCounts': [1, 4, 16, 64],
}
EXPECTED_PREVIOUS_ATTEMPT = None
EXPECTED_MAP_RASTER = None


class ValidationError(RuntimeError):
    """Raised when an input is structurally invalid or provenance is broken."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def reject_json_constant(value: str) -> None:
    raise ValueError(f'nonstandard JSON constant: {value}')


def load_json_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(
        Path(path).read_text(encoding='utf-8'),
        parse_constant=reject_json_constant,
    )
    require(isinstance(value, dict), f'JSON object required: {path}')
    return value


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha256(value: Any, label: str) -> str:
    require(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
            f'{label} must be a lowercase SHA-256')
    return value


def finite_number(value: Any, label: str, *, nonnegative: bool = False) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f'{label} must be numeric')
    result = float(value)
    require(math.isfinite(result), f'{label} must be finite')
    if nonnegative:
        require(result >= 0, f'{label} must be nonnegative')
    return result


def nonnegative_integer(value: Any, label: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f'{label} must be a nonnegative integer')
    return value


def require_close(actual: float, expected: float, label: str) -> None:
    scale = max(1.0, abs(actual), abs(expected))
    require(abs(actual - expected) <= 16 * float.fromhex('0x1.0p-52') * scale,
            f'{label} does not match field artifact')


def validate_contract(contract: dict[str, Any]) -> None:
    require(set(contract) == EXPECTED_CONTRACT_KEYS, 'execution-contract top-level keys changed')
    require(contract.get('schema') == CONTRACT_SCHEMA, 'unsupported execution-contract schema')
    require(contract.get('status') == 'awaiting_explicit_authorization', 'execution-contract status changed')
    require(contract.get('executionAuthorized') is False,
            'immutable execution contract must not itself authorize execution')
    require(contract.get('authorization') is None,
            'immutable execution contract must not contain an active authorization')

    authorization_contract = contract.get('authorizationContract')
    require(authorization_contract == {
        'schema': AUTHORIZATION_SCHEMA,
        'path': AUTHORIZATION_PATH,
        'required': True,
        'bindingField': 'executionContract',
        'oneTime': True,
        'requiredSourceStatement': AUTHORIZATION_SOURCE_STATEMENT,
        'maxValiditySeconds': 86400,
        'scope': AUTHORIZATION_SCOPE,
    }, 'authorization-contract declaration changed')

    geometry = contract.get('geometry')
    require(geometry == {
        'waterAuthorityVersion': 'v4.8.0-candidate-r3',
        'approvedWaterPixelCount': 680633,
        'metricMeshCellCount': CELL_COUNT,
        'frozen': True,
    }, 'corrected geometry contract changed')

    mesh = contract.get('meshExpected', {})
    require(mesh.get('version') == MESH_VERSION, 'mesh version changed')
    require(mesh.get('candidateStatus') == 'approved_canonical', 'mesh is not approved canonical')
    require(mesh.get('packageSha256') == MESH_PACKAGE_SHA256, 'mesh package identity changed')
    require(mesh.get('counts', {}).get('cells') == CELL_COUNT, 'mesh cell count changed')
    require(mesh.get('visualApproval', {}).get('status') == 'approved', 'mesh visual approval is missing')
    require(mesh.get('visualApproval', {}).get('scope')
            == 'corrected_linux_mesh_geometry_only_no_numerical_execution_authorization',
            'mesh visual-approval scope changed')

    ensemble = contract.get('ensembleExpected', {})
    require(ensemble.get('schema') == 'onga-stage18-inference-ensemble-v2',
            'ensemble schema changed')
    require(ensemble.get('sha256') == ENSEMBLE_SHA256, 'ensemble identity changed')
    require(ensemble.get('caseCount') == CASE_COUNT, 'ensemble case count changed')
    require(ensemble.get('seed') == 20260713, 'ensemble seed changed')
    require(ensemble.get('geometry') == geometry, 'ensemble geometry does not match contract geometry')

    require(contract.get('run') == EXPECTED_RUN, 'run definition changed')
    require(contract.get('acceptance') == EXPECTED_ACCEPTANCE, 'acceptance thresholds changed')
    require(contract.get('stopPolicy') == EXPECTED_STOP_POLICY, 'immediate STOP policy changed')
    require(contract.get('protectedPaths') == EXPECTED_PROTECTED_PATHS, 'protected paths changed')

    outputs = contract.get('outputs', {})
    success_outputs = outputs.get('successRequired')
    require(isinstance(success_outputs, list), 'required success outputs are missing')
    for required in (
        'full64-report.json', 'full64-fields.npz', 'full64-evaluation.json',
        'full64-depth-median.png', 'full64-velocity-median.png',
        'full64-wet-probability.png', 'full64-direction-agreement.png',
        'full64-direction-support.png', 'full64-judgment.svg',
    ):
        require(required in success_outputs, f'required success output changed: {required}')
    require(outputs.get('partialFieldArtifactAllowed') is False,
            'partial field artifacts must remain forbidden')

    safeguards = contract.get('safeguards')
    require(isinstance(safeguards, dict), 'contract safeguards are missing')
    for key in FALSE_AUTHORIZATION_SAFEGUARDS:
        require(safeguards.get(key) is False, f'contract safeguard changed: {key}')

    claim_limits = contract.get('claimLimits')
    require(isinstance(claim_limits, dict) and claim_limits, 'claim limits are missing')
    require(all(value is False for value in claim_limits.values()), 'one or more claim limits were enabled')
    if EXPECTED_PREVIOUS_ATTEMPT is not None:
        require(contract.get('previousAttempt') == EXPECTED_PREVIOUS_ATTEMPT,
                'previous-attempt evidence changed')
    if EXPECTED_MAP_RASTER is not None:
        require(contract.get('mapRaster') == EXPECTED_MAP_RASTER,
                'map-raster recovery contract changed')


def validate_authorization_validity_window(authorization: dict[str, Any]) -> None:
    pattern = r'20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
    issued_text = authorization.get('issuedAtUtc')
    not_after_text = authorization.get('notAfterUtc')
    require(isinstance(issued_text, str) and re.fullmatch(pattern, issued_text) is not None,
            'authorization issuedAtUtc must be an exact UTC timestamp')
    require(isinstance(not_after_text, str) and re.fullmatch(pattern, not_after_text) is not None,
            'authorization notAfterUtc must be an exact UTC timestamp')
    try:
        issued = dt.datetime.strptime(issued_text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
        not_after = dt.datetime.strptime(not_after_text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
    except ValueError as error:
        raise ValidationError(f'authorization validity timestamp is invalid: {error}') from error
    validity_seconds = (not_after - issued).total_seconds()
    require(validity_seconds > 0, 'authorization validity window must be positive')
    require(validity_seconds <= 86400, 'authorization validity window exceeds 24 hours')


def validate_authorization(
    authorization: dict[str, Any],
    contract: dict[str, Any],
    contract_digest: str,
) -> None:
    require(set(authorization) == EXPECTED_AUTHORIZATION_KEYS,
            'authorization top-level keys changed')
    require(authorization.get('schema') == AUTHORIZATION_SCHEMA, 'unsupported authorization schema')
    require(authorization.get('authorized') is True, 'v2 numerical execution is not authorized')
    require(authorization.get('oneTime') is True, 'authorization must be one-time')
    require(isinstance(authorization.get('authorizationId'), str)
            and authorization['authorizationId'].strip(), 'authorizationId is required')
    require(authorization.get('approvedBy') == 'Ryusuke Fujisawa',
            'authorization approver changed')
    require(isinstance(authorization.get('approvedDate'), str)
            and DATE_RE.fullmatch(authorization['approvedDate']) is not None,
            'authorization date must use YYYY-MM-DD')
    validate_authorization_validity_window(authorization)
    require(authorization.get('sourceStatement') == AUTHORIZATION_SOURCE_STATEMENT,
            'authorization source statement does not match the visual execution decision')
    require(authorization.get('scope') == AUTHORIZATION_SCOPE, 'authorization scope changed')
    require(isinstance(authorization.get('reviewedCodeCommit'), str)
            and COMMIT_RE.fullmatch(authorization['reviewedCodeCommit']) is not None,
            'authorization reviewedCodeCommit must be a full lowercase Git commit')

    decision_image = authorization.get('decisionImage')
    require(isinstance(decision_image, dict), 'authorization decision image is required')
    require(set(decision_image) == {'path', 'sha256'}, 'authorization decision-image keys changed')
    require(decision_image.get('path') == DECISION_IMAGE_PATH,
            'authorization decision-image path changed')
    require_sha256(decision_image.get('sha256'), 'authorization decision-image digest')

    expected_binding = {
        'path': CONTRACT_PATH,
        'sha256': contract_digest,
    }
    require(authorization.get('executionContract') == expected_binding,
            'authorization is not bound to the exact execution contract')
    for key in ('geometry', 'meshExpected', 'ensembleExpected', 'run', 'acceptance'):
        require(authorization.get(key) == contract.get(key), f'authorization {key} differs from contract')

    safeguards = authorization.get('safeguards')
    require(safeguards == {key: False for key in FALSE_AUTHORIZATION_SAFEGUARDS},
            'authorization safeguards changed')


def validate_protected_surfaces(report: dict[str, Any], contract: dict[str, Any]) -> bool:
    before = report.get('protectedSurfaceHashesBefore')
    after = report.get('protectedSurfaceHashesAfter')
    require(isinstance(before, dict) and isinstance(after, dict), 'protected-surface hashes are required')
    paths = contract['protectedPaths']
    require(list(before) == paths, 'protected-surface paths before run changed')
    require(list(after) == paths, 'protected-surface paths after run changed')
    for path in paths:
        require_sha256(before.get(path), f'protected surface before: {path}')
        require_sha256(after.get(path), f'protected surface after: {path}')
    unchanged = before == after
    require(report.get('protectedSurfaceHashesUnchanged') is unchanged,
            'protected-surface unchanged flag does not match hashes')
    return unchanged


def validate_report_structure(
    report: dict[str, Any],
    contract: dict[str, Any],
    contract_digest: str,
    authorization_digest: str,
) -> dict[str, Any]:
    require(set(report) == EXPECTED_REPORT_KEYS, 'run-report top-level keys changed')
    require(report.get('schema') == REPORT_SCHEMA, 'unsupported run-report schema')
    require(report.get('classification') == CLASSIFICATION, 'run-report classification changed')
    require(report.get('geometry') == contract['geometry'], 'run-report geometry changed')
    require(report.get('requestedCaseCount') == CASE_COUNT, 'run-report case count changed')
    require(report.get('ensembleSeed') == contract['run']['ensembleSeed'], 'run-report seed changed')
    require(report.get('comparisonBasis') == COMPARISON_BASIS, 'run-report comparison basis changed')

    attempted = report.get('attemptedCaseIds')
    require(isinstance(attempted, list), 'attempted case IDs are required')
    require(all(isinstance(case_id, str) and case_id for case_id in attempted),
            'attempted case IDs must be nonempty strings')
    require(len(attempted) == len(set(attempted)), 'attempted case IDs must be unique')
    require(len(attempted) <= CASE_COUNT, 'too many attempted case IDs')
    completed = nonnegative_integer(report.get('completedCaseCount'), 'completedCaseCount')
    failed = nonnegative_integer(report.get('failedCaseCount'), 'failedCaseCount')
    require(completed + failed == len(attempted), 'case accounting does not match attempted cases')

    failures = report.get('failures')
    require(isinstance(failures, list) and len(failures) == failed, 'failure list does not match failed count')
    diagnostics = report.get('caseDiagnostics')
    require(isinstance(diagnostics, list) and len(diagnostics) == len(attempted),
            'case diagnostics do not match attempted cases')
    require([entry.get('caseId') for entry in diagnostics if isinstance(entry, dict)] == attempted,
            'case diagnostics are not in attempted-case order')

    diagnostic_completed = 0
    diagnostic_failed = 0
    diagnostic_wall_seconds = 0.0
    for entry in diagnostics:
        require(isinstance(entry, dict), 'case diagnostic must be an object')
        diagnostic_wall_seconds += finite_number(
            entry.get('wallSeconds'), f"{entry['caseId']}.wallSeconds", nonnegative=True,
        )
        if entry.get('status') == 'completed':
            diagnostic_completed += 1
            require(entry.get('stepsCompleted') == contract['run']['maxStepsPerCase'],
                    f"{entry['caseId']} step count changed")
            for key in (
                'simulatedTimeSeconds', 'minimumTimeStepSeconds', 'maximumTimeStepSeconds',
                'massBalanceError', 'maxCfl', 'minimumDepthM',
            ):
                finite_number(
                    entry.get(key),
                    f"{entry['caseId']}.{key}",
                    nonnegative=key != 'massBalanceError',
                )
            require(entry['simulatedTimeSeconds'] > 0, f"{entry['caseId']} simulated time must be positive")
            require(entry['minimumTimeStepSeconds'] > 0,
                    f"{entry['caseId']} minimum time step must be positive")
            require(entry['maximumTimeStepSeconds'] >= entry['minimumTimeStepSeconds'],
                    f"{entry['caseId']} time-step range is invalid")
        else:
            diagnostic_failed += 1
            require(entry.get('status') == 'failed', f"{entry['caseId']} diagnostic status changed")
            require(isinstance(entry.get('reason'), str) and entry['reason'],
                    f"{entry['caseId']} failure reason is required")
    require(diagnostic_completed == completed and diagnostic_failed == failed,
            'diagnostic status counts do not match report counts')
    case_wall_seconds = finite_number(
        report.get('caseWallSecondsTotal'), 'caseWallSecondsTotal', nonnegative=True,
    )
    require_close(case_wall_seconds, diagnostic_wall_seconds, 'caseWallSecondsTotal')
    total_wall_seconds = finite_number(report.get('wallSeconds'), 'wallSeconds', nonnegative=True)
    require(total_wall_seconds + 1e-12 >= case_wall_seconds,
            'wallSeconds must include total case runtime')

    input_digests = report.get('inputDigests')
    require(isinstance(input_digests, dict), 'run-report input digests are required')
    require(input_digests.get('executionContractSha256') == contract_digest,
            'run report execution-contract digest mismatch')
    require(input_digests.get('authorizationSha256') == authorization_digest,
            'run report authorization digest mismatch')
    require(input_digests.get('meshSha256') == MESH_PACKAGE_SHA256,
            'run report mesh digest mismatch')
    require(input_digests.get('ensembleSha256') == ENSEMBLE_SHA256,
            'run report ensemble digest mismatch')
    require_sha256(input_digests.get('meshSummarySha256'), 'run report mesh-summary digest')

    field = report.get('fieldArtifact')
    require(isinstance(field, dict), 'field artifact metadata is required')
    require_sha256(field.get('sha256'), 'field artifact digest')
    require(field.get('shape') == {'caseCount': CASE_COUNT, 'cellCount': CELL_COUNT},
            'field artifact shape metadata changed')
    require(field.get('dtype') == 'float64', 'field artifact dtype metadata changed')

    require(report.get('parameterCoverage') == contract.get('parameterCoverage'),
            'run-report parameter coverage changed')
    require(report.get('stopPolicy') == contract.get('stopPolicy'),
            'run-report STOP policy changed')

    protected_unchanged = validate_protected_surfaces(report, contract)
    return {
        'attempted': attempted,
        'completed': completed,
        'failed': failed,
        'protectedUnchanged': protected_unchanged,
        'inputDigests': input_digests,
        'fieldArtifact': field,
    }


def _scalar_text(archive: Any, name: str) -> str:
    require(name in archive.files, f'field artifact is missing {name}')
    value = archive[name]
    require(value.shape == (), f'{name} must be a scalar')
    require(value.dtype.kind in ('U', 'S'), f'{name} must be a plain string')
    raw = value.item()
    return raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)


def inspect_fields(path: str | Path) -> dict[str, Any]:
    """Validate the full v2 NPZ and return compact evidence for pure evaluation."""
    import numpy as np  # Lazy import keeps metadata-only negative tests lightweight.

    fields_path = Path(path)
    require(fields_path.is_file() and not fields_path.is_symlink(), 'field artifact must be a regular file')
    digest = sha256_file(fields_path)
    with np.load(fields_path, allow_pickle=False) as archive:
        require(set(archive.files) == EXPECTED_FIELD_NAMES, 'field artifact array set changed')
        require(_scalar_text(archive, 'schema') == FIELDS_SCHEMA, 'unsupported field-artifact schema')
        require('case_ids' in archive.files, 'field artifact is missing case_ids')
        case_ids_array = archive['case_ids']
        require(case_ids_array.shape == (CASE_COUNT,), 'case_ids shape changed')
        require(case_ids_array.dtype.kind in ('U', 'S'), 'case_ids must be plain strings')
        case_ids = [
            value.decode('utf-8') if isinstance(value, bytes) else str(value)
            for value in case_ids_array.tolist()
        ]
        require(len(set(case_ids)) == CASE_COUNT and all(case_ids), 'case_ids must be 64 unique strings')

        metrics: dict[str, float] = {}
        for name, shape in REQUIRED_FIELD_ARRAYS.items():
            require(name in archive.files, f'field artifact is missing {name}')
            values = archive[name]
            require(values.shape == shape, f'{name} shape changed')
            require(values.dtype == np.dtype(np.float64), f'{name} dtype must be float64')
            require(np.isfinite(values).all(), f'{name} contains a non-finite value')
            if name == 'water_depth_m':
                metrics['minimumDepthM'] = float(np.min(values))
                require(metrics['minimumDepthM'] >= 0, 'water_depth_m contains a negative value')
            elif name == 'velocity_u_ms' or name == 'velocity_v_ms':
                continue
            elif name == 'mass_balance_error':
                metrics['maxAbsoluteMassBalanceError'] = float(np.max(np.abs(values)))
            elif name == 'cfl_max':
                require(np.all(values >= 0), 'cfl_max contains a negative value')
                metrics['maxCfl'] = float(np.max(values))
            elif name == 'simulated_time_seconds':
                require(np.all(values > 0), 'simulated_time_seconds must be positive')
            elif name == 'minimum_time_step_seconds':
                require(np.all(values > 0), 'minimum_time_step_seconds must be positive')
            elif name == 'maximum_time_step_seconds':
                require(np.all(values > 0), 'maximum_time_step_seconds must be positive')

        require(np.all(archive['maximum_time_step_seconds'] >= archive['minimum_time_step_seconds']),
                'maximum time step is below minimum time step')
        metadata = {
            'executionContractSha256': _scalar_text(archive, 'execution_contract_sha256'),
            'authorizationSha256': _scalar_text(archive, 'authorization_sha256'),
            'meshSha256': _scalar_text(archive, 'mesh_sha256'),
            'meshSummarySha256': _scalar_text(archive, 'mesh_summary_sha256'),
            'ensembleSha256': _scalar_text(archive, 'ensemble_sha256'),
            'comparisonBasis': _scalar_text(archive, 'comparison_basis'),
        }
    return {
        'sha256': digest,
        'schema': FIELDS_SCHEMA,
        'shape': {'caseCount': CASE_COUNT, 'cellCount': CELL_COUNT},
        'dtype': 'float64',
        'caseIds': case_ids,
        'metrics': metrics,
        'metadata': metadata,
    }


def evaluate_evidence(
    contract: dict[str, Any],
    authorization: dict[str, Any],
    report: dict[str, Any],
    field_evidence: dict[str, Any],
    *,
    contract_digest: str,
    authorization_digest: str,
    report_digest: str,
) -> dict[str, Any]:
    """Pure evaluator used by the CLI and compact metadata-only tests."""
    validate_contract(contract)
    require_sha256(contract_digest, 'execution-contract digest')
    require_sha256(authorization_digest, 'authorization digest')
    require_sha256(report_digest, 'run-report digest')
    validate_authorization(authorization, contract, contract_digest)
    state = validate_report_structure(report, contract, contract_digest, authorization_digest)
    require(report.get('safeguards') == authorization.get('safeguards'),
            'run-report safeguards differ from authorization')

    require(field_evidence.get('schema') == FIELDS_SCHEMA, 'field-evidence schema changed')
    require(field_evidence.get('shape') == {'caseCount': CASE_COUNT, 'cellCount': CELL_COUNT},
            'field-evidence shape changed')
    require(field_evidence.get('dtype') == 'float64', 'field-evidence dtype changed')
    require_sha256(field_evidence.get('sha256'), 'field-evidence digest')
    require(field_evidence['sha256'] == state['fieldArtifact']['sha256'],
            'run report field-artifact digest mismatch')
    field_case_ids = field_evidence.get('caseIds')
    require(isinstance(field_case_ids, list) and len(field_case_ids) == CASE_COUNT
            and len(set(field_case_ids)) == CASE_COUNT and all(field_case_ids),
            'field-evidence case IDs must be 64 unique strings')
    require(field_case_ids == state['attempted'],
            'field case IDs do not match attempted cases')

    metadata = field_evidence.get('metadata')
    require(isinstance(metadata, dict), 'field metadata is missing')
    expected_metadata = {
        'executionContractSha256': contract_digest,
        'authorizationSha256': authorization_digest,
        'meshSha256': MESH_PACKAGE_SHA256,
        'meshSummarySha256': state['inputDigests']['meshSummarySha256'],
        'ensembleSha256': ENSEMBLE_SHA256,
        'comparisonBasis': COMPARISON_BASIS,
    }
    require(metadata == expected_metadata, 'field metadata digest chain changed')

    field_metrics = field_evidence.get('metrics')
    require(isinstance(field_metrics, dict), 'field metrics are missing')
    for key in ('maxCfl', 'maxAbsoluteMassBalanceError', 'minimumDepthM'):
        actual = finite_number(report.get(key), f'run report {key}', nonnegative=True)
        expected = finite_number(field_metrics.get(key), f'field metric {key}', nonnegative=True)
        require_close(actual, expected, key)

    completed = state['completed']
    failed = state['failed']
    completion_fraction = completed / CASE_COUNT
    nan_count = nonnegative_integer(report.get('nanCount'), 'nanCount')
    negative_count = nonnegative_integer(report.get('negativeDepthCount'), 'negativeDepthCount')
    max_cfl = finite_number(report.get('maxCfl'), 'maxCfl', nonnegative=True)
    max_mass = finite_number(
        report.get('maxAbsoluteMassBalanceError'), 'maxAbsoluteMassBalanceError', nonnegative=True,
    )
    minimum_depth = finite_number(report.get('minimumDepthM'), 'minimumDepthM')
    wall_seconds = finite_number(report.get('wallSeconds'), 'wallSeconds', nonnegative=True)
    memory_mib = finite_number(report.get('peakResidentMemoryMiB'), 'peakResidentMemoryMiB', nonnegative=True)
    acceptance = contract['acceptance']
    checks = {
        'allCasesAttempted': len(state['attempted']) == CASE_COUNT,
        'completionFraction': completion_fraction >= acceptance['completionFractionMin'],
        'failedCaseCount': failed == 0,
        'nanCount': nan_count <= acceptance['nanCountMax'],
        'negativeDepthCount': negative_count <= acceptance['negativeDepthCountMax'],
        'maxCfl': max_cfl <= acceptance['maxCflMax'],
        'massBalance': max_mass <= acceptance['maxAbsoluteMassBalanceErrorMax'],
        'wallTime': wall_seconds <= acceptance['maxWallSeconds'],
        'memory': memory_mib <= acceptance['maxResidentMemoryMiB'],
        'minimumDepth': minimum_depth >= 0,
        'protectedSurfaces': state['protectedUnchanged'],
    }
    passed = all(checks.values())
    return {
        'schema': EVALUATION_SCHEMA,
        'status': 'passed' if passed else 'failed',
        'passed': passed,
        'classification': CLASSIFICATION,
        'checks': checks,
        'metrics': {
            'completedCaseCount': completed,
            'requestedCaseCount': CASE_COUNT,
            'completionFraction': completion_fraction,
            'failedCaseCount': failed,
            'nanCount': nan_count,
            'negativeDepthCount': negative_count,
            'maxCfl': max_cfl,
            'maxAbsoluteMassBalanceError': max_mass,
            'minimumDepthM': minimum_depth,
            'wallSeconds': wall_seconds,
            'peakResidentMemoryMiB': memory_mib,
        },
        'limits': dict(acceptance),
        'provenance': {
            'executionContractSha256': contract_digest,
            'authorizationSha256': authorization_digest,
            'runReportSha256': report_digest,
            'fieldArtifactSha256': field_evidence['sha256'],
            'meshSha256': state['inputDigests']['meshSha256'],
            'meshSummarySha256': state['inputDigests']['meshSummarySha256'],
            'ensembleSha256': state['inputDigests']['ensembleSha256'],
        },
        'fieldArtifact': {
            'shape': field_evidence['shape'],
            'dtype': field_evidence['dtype'],
        },
        'offlineStepMatchedStatisticsAllowed': passed,
        'physicalValidationClaimAllowed': False,
        'sensitivityClaimAllowed': False,
        'publicSimulatorConnectionAllowed': False,
        'automaticAdditionalRunAuthorized': False,
        'commonPhysicalTimeComparisonAllowed': False,
    }


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    require(not destination.exists(), f'evaluation output already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.{os.getpid()}.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def distinct_paths(entries: list[tuple[str, str | Path]]) -> None:
    seen: dict[Path, str] = {}
    for label, raw_path in entries:
        path = Path(raw_path).resolve()
        previous = seen.get(path)
        require(previous is None, f'{label} path overlaps {previous}: {path}')
        seen[path] = label


def evaluate_files(
    contract_path: str | Path,
    authorization_path: str | Path,
    report_path: str | Path,
    fields_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    distinct_paths([
        ('execution contract', contract_path),
        ('authorization', authorization_path),
        ('run report', report_path),
        ('field artifact', fields_path),
        ('evaluation output', output_path),
    ])
    require(not Path(output_path).exists(), f'evaluation output already exists: {output_path}')
    contract = load_json_object(contract_path)
    authorization = load_json_object(authorization_path)
    report = load_json_object(report_path)
    fields = inspect_fields(fields_path)
    if isinstance(report.get('fieldArtifact'), dict) and report['fieldArtifact'].get('path') is not None:
        require(Path(report['fieldArtifact']['path']).resolve() == Path(fields_path).resolve(),
                'run report field-artifact path mismatch')
    evaluation = evaluate_evidence(
        contract,
        authorization,
        report,
        fields,
        contract_digest=sha256_file(contract_path),
        authorization_digest=sha256_file(authorization_path),
        report_digest=sha256_file(report_path),
    )
    write_json_atomic(output_path, evaluation)
    return evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract')
    parser.add_argument('authorization')
    parser.add_argument('report')
    parser.add_argument('fields')
    parser.add_argument('output')
    args = parser.parse_args()
    evaluation = evaluate_files(args.contract, args.authorization, args.report, args.fields, args.output)
    print(json.dumps({
        'output': args.output,
        'passed': evaluation['passed'],
        'provenance': evaluation['provenance'],
    }, ensure_ascii=False))
    return 0 if evaluation['passed'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ValidationError) as error:
        print(f'[stage18-full64-v2-evaluator] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
