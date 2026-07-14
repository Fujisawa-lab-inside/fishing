#!/usr/bin/env python3
"""Seal or verify the complete v3 numerical-evidence checkpoint.

The checkpoint is written immediately after the numerical evaluator passes and
before map packaging starts.  It is deliberately fixed to the reviewed v3
filenames; there is no selectable execution profile.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import evaluate_stage18_full64_v2 as evaluator
import run_stage18_full64_v2 as runner
from stage18_full64_v3_profile import (
    AUTHORIZATION_PATH,
    CONTRACT_PATH,
    EXPECTED_DECISION_IMAGE_PATH,
    EXPECTED_WORKFLOW,
    GATE_PATH,
    NUMERIC_CHECKPOINT_REQUIRED,
    configure_evaluator,
    configure_runner,
)


configure_runner(runner)
configure_evaluator(evaluator)

SCHEMA = 'onga-stage18-full64-numeric-evidence-manifest-v3'
RECEIPT_SCHEMA = 'onga-stage18-full64-execution-receipt-v3'
EVALUATION_SCHEMA = 'onga-stage18-full64-evaluation-v2'
REPORT_SCHEMA = 'onga-stage18-full64-run-report-v2'
PROGRESS_SCHEMA = 'onga-stage18-full64-progress-v2'
MAP_RASTER_SCHEMA = 'onga-stage18-full64-v3-map-raster-preflight-v1'
DECISION_IMAGE_PATH = EXPECTED_DECISION_IMAGE_PATH
MANIFEST_NAME = 'full64-numeric-evidence-manifest.json'
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

# These are the complete, map-independent products needed to preserve the
# numerical PASS and regenerate maps without starting another numerical case.
EVIDENCE_FILES = tuple(NUMERIC_CHECKPOINT_REQUIRED[:-1])


class SealError(RuntimeError):
    """Raised when numerical evidence cannot be sealed or verified."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SealError(message)


def _reject_constant(value: str) -> None:
    raise ValueError(f'nonstandard JSON constant: {value}')


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def load_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    require(path.is_file() and not path.is_symlink(), f'{label} must be a regular file: {path}')
    try:
        payload = path.read_bytes()
        value = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SealError(f'{label} is not strict JSON: {error}') from error
    require(isinstance(value, dict), f'{label} must be a JSON object')
    return value, hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha256(value: Any, label: str) -> str:
    require(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
            f'{label} must be a lowercase SHA-256')
    return value


def repo_file(repo_root: Path, raw_path: str, label: str) -> Path:
    require(isinstance(raw_path, str) and raw_path, f'{label} path is required')
    relative = Path(raw_path)
    require(not relative.is_absolute(), f'{label} path must be repository-relative')
    candidate = repo_root / relative
    require(not candidate.is_symlink(), f'{label} must not be a symbolic link')
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as error:
        raise SealError(f'{label} path escapes the repository') from error
    require(resolved.is_file() and not resolved.is_symlink(), f'{label} must be a regular file')
    return resolved


def evidence_file(workdir: Path, name: str) -> Path:
    require(Path(name).name == name, f'invalid fixed evidence filename: {name}')
    path = workdir / name
    require(path.is_file() and not path.is_symlink(), f'numerical evidence is missing: {name}')
    require(path.stat().st_size > 0, f'numerical evidence is empty: {name}')
    return path


def validate_content_chain(
    workdir: Path,
    repo_root: Path,
    *,
    require_original_field_path: bool,
) -> dict[str, Any]:
    contract_path = repo_file(repo_root, CONTRACT_PATH, 'v3 execution contract')
    gate_path = repo_file(repo_root, GATE_PATH, 'v3 execution gate')
    authorization_path = repo_file(repo_root, AUTHORIZATION_PATH, 'v3 authorization')
    contract, contract_digest = load_json(contract_path, 'v3 execution contract')
    gate, gate_digest = load_json(gate_path, 'v3 execution gate')
    authorization, authorization_digest = load_json(authorization_path, 'v3 authorization')

    try:
        runner.validate_immutable_contract(contract)
        active = runner.validate_active_gate(gate)
        evaluator.validate_authorization(authorization, contract, contract_digest)
    except (runner.PreflightError, evaluator.ValidationError) as error:
        raise SealError(f'v3 reviewed control chain is invalid: {error}') from error
    require(active.get('path') == AUTHORIZATION_PATH, 'v3 active authorization path changed')
    require(active.get('sha256') == authorization_digest,
            'v3 active authorization digest does not match the authorization file')
    authorization_id = authorization.get('authorizationId')
    require(isinstance(authorization_id, str) and authorization_id,
            'v3 authorization ID is missing')
    require(active.get('id') == authorization_id, 'v3 gate and authorization IDs differ')
    binding = authorization.get('executionContract')
    require(isinstance(binding, dict), 'v3 authorization contract binding is missing')
    require(binding.get('path') == CONTRACT_PATH and binding.get('sha256') == contract_digest,
            'v3 authorization is not bound to the exact execution contract')
    decision = authorization.get('decisionImage')
    require(isinstance(decision, dict), 'v3 authorization decision-image binding is missing')
    require(decision.get('path') == DECISION_IMAGE_PATH, 'v3 decision-image path changed')
    decision_digest = require_sha256(decision.get('sha256'), 'v3 decision-image digest')
    decision_path = repo_file(repo_root, DECISION_IMAGE_PATH, 'v3 decision image')
    require(sha256_file(decision_path) == decision_digest, 'v3 decision-image digest mismatch')

    receipt, receipt_digest = load_json(
        evidence_file(workdir, 'execution-receipt.json'), 'v3 execution receipt',
    )
    require(set(receipt) == {
        'schema', 'status', 'authorizationId', 'authorizationSha256',
        'executionContractSha256', 'executionGateSha256', 'decisionImageSha256',
        'preflightSha256', 'reviewedCodeCommit', 'executionCommit',
        'authorizationValidity', 'workflow', 'consumptionEvidence', 'createdAtUtc',
    }, 'v3 execution-receipt keys changed')
    require(receipt.get('schema') == RECEIPT_SCHEMA, 'v3 execution-receipt schema changed')
    require(receipt.get('status') == 'one_time_authorization_consumed',
            'v3 execution receipt does not record authorization consumption')
    require(receipt.get('authorizationId') == authorization_id,
            'v3 execution receipt authorization ID changed')
    require(receipt.get('authorizationSha256') == authorization_digest,
            'v3 execution receipt authorization digest mismatch')
    require(receipt.get('executionContractSha256') == contract_digest,
            'v3 execution receipt contract digest mismatch')
    require(receipt.get('executionGateSha256') == gate_digest,
            'v3 execution receipt gate digest mismatch')
    require(receipt.get('decisionImageSha256') == decision_digest,
            'v3 execution receipt decision-image digest mismatch')
    workflow = receipt.get('workflow')
    require(isinstance(workflow, dict), 'v3 execution receipt workflow identity is missing')
    require(workflow.get('repository') == 'Fujisawa-lab-inside/fishing',
            'v3 execution receipt repository changed')
    require(workflow.get('actor') == 'RyusukeFujisawa',
            'v3 execution receipt actor changed')
    require(workflow.get('ref') == 'refs/heads/main', 'v3 execution receipt ref changed')
    require(workflow.get('runAttempt') == '1', 'v3 numerical evidence must come from run attempt 1')
    require(workflow.get('workflow') == EXPECTED_WORKFLOW,
            'v3 execution receipt workflow name changed')
    require(isinstance(workflow.get('runId'), str) and workflow['runId'].isdigit(),
            'v3 execution receipt run ID is invalid')
    current_run_id = os.environ.get('GITHUB_RUN_ID')
    if current_run_id is not None:
        require(current_run_id == workflow['runId'],
                'downloaded numerical evidence belongs to a different workflow run')
    require(set(workflow) == {
        'repository', 'actor', 'ref', 'sha', 'runId', 'runAttempt', 'workflow',
    }, 'v3 execution receipt workflow keys changed')
    require(isinstance(workflow.get('sha'), str)
            and re.fullmatch(r'[0-9a-f]{40}', workflow['sha']) is not None,
            'v3 execution receipt workflow commit is invalid')
    require(receipt.get('executionCommit') == workflow['sha'],
            'v3 execution receipt commit differs from workflow commit')
    require(isinstance(receipt.get('reviewedCodeCommit'), str)
            and re.fullmatch(r'[0-9a-f]{40}', receipt['reviewedCodeCommit']) is not None,
            'v3 execution receipt reviewed commit is invalid')
    require(receipt.get('consumptionEvidence') == {
        'stepName': 'Consume v3 one-time recovery authorization',
        'automaticRetryAllowed': False,
        'automaticAdditionalRunAllowed': False,
    }, 'v3 authorization-consumption evidence changed')

    preflight_path = evidence_file(workdir, 'preflight.json')
    preflight_recheck_path = evidence_file(workdir, 'preflight-recheck.json')
    require(preflight_path.read_bytes() == preflight_recheck_path.read_bytes(),
            'downloaded input preflight differs from its numerical-job recheck')
    preflight, preflight_digest = load_json(preflight_recheck_path, 'v3 input preflight recheck')
    require(preflight.get('schema') == 'onga-stage18-full64-preflight-v3',
            'v3 input preflight schema changed')
    require(preflight.get('status') == 'passed', 'v3 input preflight did not pass')
    require(preflight.get('numericalCasesStarted') == 0 and preflight.get('outputsCreated') == 0,
            'v3 input preflight started numerical work or created numerical outputs')
    require(preflight.get('caseCount') == 64 and preflight.get('cellCount') == 50129,
            'v3 input preflight dimensions changed')
    require(receipt.get('preflightSha256') == preflight_digest,
            'v3 execution receipt input-preflight digest mismatch')

    evaluation, evaluation_digest = load_json(
        evidence_file(workdir, 'full64-evaluation.json'), 'full64 evaluation',
    )
    require(evaluation.get('schema') == EVALUATION_SCHEMA, 'full64 evaluation schema changed')
    require(evaluation.get('status') == 'passed' and evaluation.get('passed') is True,
            'numerical evaluation did not pass')
    checks = evaluation.get('checks')
    require(isinstance(checks, dict) and checks and all(value is True for value in checks.values()),
            'one or more numerical evaluation checks did not pass')
    provenance = evaluation.get('provenance')
    require(isinstance(provenance, dict), 'numerical evaluation provenance is missing')
    require(provenance.get('executionContractSha256') == contract_digest,
            'evaluation contract digest mismatch')
    require(provenance.get('authorizationSha256') == authorization_digest,
            'evaluation authorization digest mismatch')

    report, report_digest = load_json(evidence_file(workdir, 'full64-report.json'), 'full64 report')
    require(report.get('schema') == REPORT_SCHEMA, 'full64 report schema changed')
    require(provenance.get('runReportSha256') == report_digest,
            'evaluation run-report digest mismatch')
    report_inputs = report.get('inputDigests')
    require(isinstance(report_inputs, dict), 'full64 report input digests are missing')
    require(report_inputs.get('executionContractSha256') == contract_digest,
            'full64 report contract digest mismatch')
    require(report_inputs.get('authorizationSha256') == authorization_digest,
            'full64 report authorization digest mismatch')
    require(preflight.get('inputDigests') == report_inputs,
            'input preflight and full64 report digests differ')

    fields_path = evidence_file(workdir, 'full64-fields.npz')
    fields_digest = sha256_file(fields_path)
    require(provenance.get('fieldArtifactSha256') == fields_digest,
            'evaluation field-artifact digest mismatch')
    field_metadata = report.get('fieldArtifact')
    require(isinstance(field_metadata, dict) and field_metadata.get('sha256') == fields_digest,
            'full64 report field-artifact digest mismatch')
    reported_field_path = Path(str(field_metadata.get('path', '')))
    require(reported_field_path.name == 'full64-fields.npz',
            'full64 report field-artifact filename changed')
    if require_original_field_path:
        require(reported_field_path.resolve() == fields_path.resolve(),
                'full64 report field-artifact path mismatch')

    progress, _ = load_json(evidence_file(workdir, 'full64-progress.json'), 'full64 progress')
    require(progress.get('schema') == PROGRESS_SCHEMA, 'full64 progress schema changed')
    require(progress.get('status') == 'completed', 'full64 progress is not complete')
    require(progress.get('completedCaseCount') == 64 and progress.get('failedCaseCount') == 0,
            'full64 progress case accounting changed')
    progress_inputs = progress.get('inputDigests')
    require(progress_inputs == report_inputs, 'progress and report input digests differ')

    raster, raster_digest = load_json(
        evidence_file(workdir, 'full64-map-raster-preflight.json'),
        'full64 map-raster preflight',
    )
    raster_recheck_path = evidence_file(workdir, 'full64-map-raster-preflight-recheck.json')
    require(
        evidence_file(workdir, 'full64-map-raster-preflight.json').read_bytes()
        == raster_recheck_path.read_bytes(),
        'downloaded map-raster preflight differs from its numerical-job recheck',
    )
    require(raster.get('schema') == MAP_RASTER_SCHEMA, 'map-raster preflight schema changed')
    require(raster.get('status') == 'passed' and raster.get('numericalCasesStarted') == 0,
            'map-raster preflight did not pass without numerical execution')
    require(raster.get('cellCount') == 50129, 'map-raster preflight cell count changed')
    require(raster.get('pngWidth') == 3840 and raster.get('pngHeight') == 2640,
            'map-raster preflight dimensions changed')
    require(raster.get('representedCellCount') == 50129,
            'map-raster preflight omitted one or more cells')
    require(raster.get('coverageFraction') == 1.0,
            'map-raster preflight coverage is incomplete')
    require(raster.get('minimumPixelsPerCell') == 1,
            'map-raster minimum pixels per cell changed')
    require(raster.get('cell320PixelCount') == 1,
            'boundary cell 320 is not represented exactly once')
    require(raster.get('squarePixels') is True, 'map-raster pixels are not square')
    require(raster.get('rasterization')
            == 'deterministic_triangle_cell_index_center_sample_square_pixel',
            'map-raster method changed')
    pixel_size = raster.get('pixelSizeLocalM')
    require(isinstance(pixel_size, (int, float)) and not isinstance(pixel_size, bool)
            and math.isclose(float(pixel_size), 0.7147801171875, rel_tol=1e-12, abs_tol=1e-12),
            'map-raster square-pixel size changed')
    bounds_expansion = raster.get('boundsExpansionLocalM')
    x_expansion = bounds_expansion.get('xTotal') if isinstance(bounds_expansion, dict) else None
    y_expansion = bounds_expansion.get('yTotal') if isinstance(bounds_expansion, dict) else None
    require(isinstance(bounds_expansion, dict)
            and isinstance(x_expansion, (int, float)) and not isinstance(x_expansion, bool)
            and isinstance(y_expansion, (int, float)) and not isinstance(y_expansion, bool)
            and math.isclose(float(x_expansion), 0.0, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(float(y_expansion), 8.356359375, rel_tol=1e-12, abs_tol=1e-9),
            'map-raster bounds expansion changed')

    mesh_digest = sha256_file(evidence_file(workdir, 'onga_stage16_metric_fv_mesh_v2.npz'))
    require(mesh_digest == contract.get('meshExpected', {}).get('packageSha256'),
            'sealed mesh differs from the v3 contract')
    require(mesh_digest == provenance.get('meshSha256'), 'sealed mesh digest mismatch')
    require(mesh_digest == raster.get('meshSha256'), 'map-raster preflight mesh digest mismatch')
    summary_digest = sha256_file(evidence_file(workdir, 'stage16_metric_mesh_summary.json'))
    require(summary_digest == provenance.get('meshSummarySha256'),
            'sealed mesh-summary digest mismatch')
    ensemble_digest = sha256_file(evidence_file(workdir, 'ensemble-v2.json'))
    require(ensemble_digest == contract.get('ensembleExpected', {}).get('sha256'),
            'sealed ensemble differs from the v3 contract')
    require(ensemble_digest == provenance.get('ensembleSha256'), 'sealed ensemble digest mismatch')

    return {
        'authorizationId': authorization_id,
        'executionContractSha256': contract_digest,
        'executionGateSha256': gate_digest,
        'authorizationSha256': authorization_digest,
        'decisionImageSha256': decision_digest,
        'executionReceiptSha256': receipt_digest,
        'evaluationSha256': evaluation_digest,
        'mapRasterPreflightSha256': raster_digest,
        'reviewedCodeCommit': receipt['reviewedCodeCommit'],
        'executionCommit': receipt['executionCommit'],
        'workflow': workflow,
    }


def fixed_file_records(workdir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in EVIDENCE_FILES:
        path = evidence_file(workdir, name)
        records.append({
            'path': name,
            'sizeBytes': path.stat().st_size,
            'sha256': sha256_file(path),
        })
    return records


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    require(not os.path.lexists(path), f'numeric-evidence manifest already exists: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.{time.time_ns()}.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def seal(workdir: Path, output: Path, repo_root: Path) -> dict[str, Any]:
    require(NUMERIC_CHECKPOINT_REQUIRED == [*EVIDENCE_FILES, MANIFEST_NAME],
            'v3 numeric-checkpoint contract must end with the manifest')
    require(workdir.is_dir() and not workdir.is_symlink(), 'seal work directory must be a real directory')
    require(output.name == MANIFEST_NAME and output.parent.resolve() == workdir,
            f'numeric-evidence manifest must be {MANIFEST_NAME} in the work directory')
    provenance = validate_content_chain(
        workdir, repo_root, require_original_field_path=True,
    )
    records = fixed_file_records(workdir)
    manifest = {
        'schema': SCHEMA,
        'status': 'sealed_after_numerical_pass_before_map_packaging',
        'authorizationId': provenance['authorizationId'],
        'createdAtUtc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        'workflow': provenance['workflow'],
        'provenance': {
            key: provenance[key]
            for key in (
                'executionContractSha256', 'executionGateSha256', 'authorizationSha256',
                'decisionImageSha256', 'executionReceiptSha256', 'evaluationSha256',
                'mapRasterPreflightSha256', 'reviewedCodeCommit', 'executionCommit',
            )
        },
        'evidenceFiles': records,
        'fileCount': len(records),
        'checkpointFileCountIncludingManifest': len(NUMERIC_CHECKPOINT_REQUIRED),
        'recoveryPolicy': {
            'mapsMayBeGeneratedFromThisSealedEvidence': True,
            'numericalRerunRequiredForMapPackaging': False,
            'automaticNumericalRetryAllowed': False,
        },
    }
    write_json_atomic(output, manifest)
    return manifest


def verify(manifest_path: Path, workdir: Path, repo_root: Path) -> dict[str, Any]:
    require(NUMERIC_CHECKPOINT_REQUIRED == [*EVIDENCE_FILES, MANIFEST_NAME],
            'v3 numeric-checkpoint contract must end with the manifest')
    require(workdir.is_dir() and not workdir.is_symlink(), 'verify work directory must be a real directory')
    require(manifest_path.name == MANIFEST_NAME and manifest_path.parent.resolve() == workdir,
            f'verified manifest must be {MANIFEST_NAME} in the work directory')
    manifest, manifest_digest = load_json(manifest_path, 'numeric-evidence manifest')
    require(set(manifest) == {
        'schema', 'status', 'authorizationId', 'createdAtUtc', 'workflow', 'provenance',
        'evidenceFiles', 'fileCount', 'checkpointFileCountIncludingManifest',
        'recoveryPolicy',
    }, 'numeric-evidence manifest keys changed')
    require(manifest.get('schema') == SCHEMA, 'numeric-evidence manifest schema changed')
    require(manifest.get('status') == 'sealed_after_numerical_pass_before_map_packaging',
            'numeric-evidence manifest is not sealed at the required checkpoint')
    records = manifest.get('evidenceFiles')
    require(isinstance(records, list), 'numeric-evidence file records are missing')
    require(manifest.get('fileCount') == len(EVIDENCE_FILES) == len(records),
            'numeric-evidence file count changed')
    require(manifest.get('checkpointFileCountIncludingManifest')
            == len(NUMERIC_CHECKPOINT_REQUIRED),
            'numeric-checkpoint total file count changed')
    require([record.get('path') for record in records if isinstance(record, dict)]
            == list(EVIDENCE_FILES), 'numeric-evidence filename set or order changed')
    for expected_name, record in zip(EVIDENCE_FILES, records):
        require(isinstance(record, dict) and set(record) == {'path', 'sizeBytes', 'sha256'},
                f'numeric-evidence record changed: {expected_name}')
        path = evidence_file(workdir, expected_name)
        require(record.get('sizeBytes') == path.stat().st_size,
                f'numeric-evidence size changed: {expected_name}')
        require_sha256(record.get('sha256'), f'numeric-evidence digest: {expected_name}')
        require(record['sha256'] == sha256_file(path),
                f'numeric-evidence digest mismatch: {expected_name}')

    provenance = validate_content_chain(
        workdir, repo_root, require_original_field_path=False,
    )
    require(manifest.get('authorizationId') == provenance['authorizationId'],
            'numeric-evidence manifest authorization ID mismatch')
    require(manifest.get('workflow') == provenance['workflow'],
            'numeric-evidence manifest workflow identity mismatch')
    require(manifest.get('provenance') == {
        key: provenance[key]
        for key in (
            'executionContractSha256', 'executionGateSha256', 'authorizationSha256',
            'decisionImageSha256', 'executionReceiptSha256', 'evaluationSha256',
            'mapRasterPreflightSha256', 'reviewedCodeCommit', 'executionCommit',
        )
    }, 'numeric-evidence manifest provenance changed')
    require(manifest.get('recoveryPolicy') == {
        'mapsMayBeGeneratedFromThisSealedEvidence': True,
        'numericalRerunRequiredForMapPackaging': False,
        'automaticNumericalRetryAllowed': False,
    }, 'numeric-evidence recovery policy changed')
    return {'manifestSha256': manifest_digest, 'authorizationId': provenance['authorizationId']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seal_workdir', nargs='?')
    parser.add_argument('--output')
    parser.add_argument('--verify', metavar='MANIFEST')
    parser.add_argument('--workdir', help='Downloaded evidence directory for --verify')
    parser.add_argument('--repo-root', default='.')
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if args.verify is not None:
        require(args.seal_workdir is None and args.output is None,
                '--verify cannot be combined with seal arguments')
        require(args.workdir is not None, '--verify requires --workdir')
        result = verify(Path(args.verify).absolute(), Path(args.workdir).resolve(), repo_root)
        print(json.dumps({'status': 'verified', **result}, ensure_ascii=False))
        return 0

    require(args.seal_workdir is not None, 'seal mode requires the work directory')
    require(args.output is not None, 'seal mode requires --output')
    require(args.workdir is None, '--workdir is only valid with --verify')
    result = seal(Path(args.seal_workdir).resolve(), Path(args.output).absolute(), repo_root)
    print(json.dumps({
        'status': 'sealed',
        'output': str(Path(args.output).absolute()),
        'authorizationId': result['authorizationId'],
        'fileCount': result['fileCount'],
        'checkpointFileCountIncludingManifest': result['checkpointFileCountIncludingManifest'],
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, SealError) as error:
        print(f'[stage18-full64-v3-numeric-evidence] {error}', file=sys.stderr)
        raise SystemExit(2)
