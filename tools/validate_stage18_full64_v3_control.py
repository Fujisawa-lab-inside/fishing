#!/usr/bin/env python3
"""Validate the fixed v3 pending, active, or consumed control plane without numerics."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import evaluate_stage18_full64_v2 as evaluator
import run_stage18_full64_v2 as core
from stage18_full64_v3_profile import (
    AUTHORIZATION_SCHEMA,
    AUTHORIZATION_PATH,
    CONTRACT_PATH,
    CONTRACT_SCHEMA,
    GATE_PATH,
    GATE_SCHEMA,
    configure_evaluator,
    configure_runner,
)


configure_runner(core)
configure_evaluator(evaluator)

SCHEMA = 'onga-stage18-full64-control-validation-v3'
BASE_GATE_KEYS = {
    'schema', 'state', 'enabled', 'replacementAuthorizationRequired',
    'activeAuthorization', 'consumedPreviousAuthorization', 'safeguards',
}
RESULT_RECORD_PATH = 'config/stage18_full64_v3_result_record.json'
RESULT_RECORD_SHA256 = '0e756f50d2a145a0603fb1f1342a06d12f72cbc84bc2165ee1297f56000cca46'
NUMERIC_EVIDENCE_MANIFEST_SHA256 = (
    'e60287e82d1837b978ecb1c939e9e4b5f2ac075bbaf5c4563df8972da8a350f8'
)
CONSUMED_V3_AUTHORIZATION = {
    'id': 'stage18-v3-20260714t044734z-one-time',
    'path': AUTHORIZATION_PATH,
    'sha256': '7151a7456f48a0fdb45b4eb77c3e157c0810534a211ed66373102e832afa7861',
    'authorizedGateSha256': '43d243938d44e51fa2f39f7e9fe04f2f277470e038ce64640e1821e0e0b3c12f',
    'workflowRunId': 29307047699,
    'executionCommit': 'c378fb3885484ea17b39143d294ca10e41cb59b6',
    'resultRecord': {
        'path': RESULT_RECORD_PATH,
        'sha256': RESULT_RECORD_SHA256,
    },
    'consumed': True,
    'reusable': False,
    'automaticRetryAllowed': False,
    'additionalRunAuthorized': False,
}
CONSUMED_PREVIOUS_AUTHORIZATION = {
    'id': 'stage18-v2-20260714t015121z-one-time',
    'path': 'config/stage18_full64_run_authorization_v2.json',
    'sha256': '0796a530bcfb8a1b9656be697b2bcef2c95ed4bfd8efb4882c6f65263b61f03c',
    'workflowRunId': 29300177716,
    'consumed': True,
    'reusable': False,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise core.PreflightError(message)


def fixed_repo_path(repo_root: Path, raw_path: str, label: str, *, must_exist: bool = True) -> Path:
    candidate = repo_root / raw_path
    require(not candidate.is_symlink(), f'{label} must not be a symbolic link')
    path = core.resolve_repo_relative_path(repo_root, raw_path, label)
    if must_exist:
        require(path.is_file() and not path.is_symlink(), f'{label} must be a regular file')
    return path


def validate_consumed_previous(gate: dict[str, Any], repo_root: Path) -> None:
    require(gate.get('consumedPreviousAuthorization') == CONSUMED_PREVIOUS_AUTHORIZATION,
            'consumed v2 authorization record changed')
    previous_path = fixed_repo_path(
        repo_root,
        CONSUMED_PREVIOUS_AUTHORIZATION['path'],
        'consumed v2 authorization',
    )
    require(core.sha256_file(previous_path) == CONSUMED_PREVIOUS_AUTHORIZATION['sha256'],
            'consumed v2 authorization digest mismatch')


def validate_consumed_v3(
    gate: dict[str, Any],
    repo_root: Path,
    authorization_path: Path,
    contract: dict[str, Any],
    contract_digest: str,
) -> tuple[str, str]:
    require(set(gate) == BASE_GATE_KEYS | {'consumedAuthorization'},
            'consumed v3 execution-gate keys changed')
    require(gate.get('state') == 'consumed', 'consumed v3 gate state changed')
    require(gate.get('enabled') is False, 'consumed v3 gate must be disabled')
    require(gate.get('replacementAuthorizationRequired') is True,
            'consumed v3 gate must require a new authorization path')
    require(gate.get('activeAuthorization') is None,
            'consumed v3 gate must not contain an active authorization')
    require(gate.get('consumedAuthorization') == CONSUMED_V3_AUTHORIZATION,
            'consumed v3 authorization evidence changed')
    require(gate.get('safeguards') == {
        'consumeOneTimeAuthorizationAllowed': False,
        'full64ExecutionAllowed': False,
        'automaticActivationAllowed': False,
    }, 'consumed v3 gate safeguards changed')

    require(authorization_path.is_file() and not authorization_path.is_symlink(),
            'consumed v3 authorization must remain a regular historical file')
    authorization, authorization_digest = core.load_json_strict(
        authorization_path, 'consumed v3 authorization',
    )
    require(authorization_digest == CONSUMED_V3_AUTHORIZATION['sha256'],
            'consumed v3 authorization digest mismatch')
    require(authorization.get('schema') == AUTHORIZATION_SCHEMA,
            'consumed v3 authorization schema changed')
    require(set(authorization) == core.EXPECTED_AUTHORIZATION_KEYS,
            'consumed v3 authorization keys changed')
    require(authorization.get('authorized') is True,
            'consumed v3 authorization must preserve the original explicit decision')
    require(authorization.get('authorizationId') == CONSUMED_V3_AUTHORIZATION['id'],
            'consumed v3 authorization ID changed')
    require(authorization.get('oneTime') is True,
            'consumed v3 authorization must remain one-time')
    core.validate_authorization_validity_window(
        authorization, enforce_current_time=False,
    )
    try:
        evaluator.validate_authorization(authorization, contract, contract_digest)
    except evaluator.ValidationError as error:
        raise core.PreflightError(
            f'consumed v3 authorization binding is invalid: {error}'
        ) from error
    decision = authorization['decisionImage']
    decision_path = fixed_repo_path(
        repo_root, decision['path'], 'consumed v3 authorization decision image',
    )
    require(core.sha256_file(decision_path) == decision['sha256'],
            'consumed v3 authorization decision-image digest mismatch')

    result_binding = CONSUMED_V3_AUTHORIZATION['resultRecord']
    result_path = fixed_repo_path(repo_root, result_binding['path'], 'v3 result record')
    result, result_digest = core.load_json_strict(result_path, 'v3 result record')
    require(result_digest == result_binding['sha256'], 'v3 result-record digest mismatch')
    require(result.get('schema') == 'onga-stage18-full64-v3-result-record-v1',
            'v3 result-record schema changed')
    require(result.get('status') == 'passed', 'v3 result record is not passed')
    workflow = result.get('workflow', {})
    require(workflow.get('runId') == CONSUMED_V3_AUTHORIZATION['workflowRunId'],
            'v3 consumed workflow run changed')
    require(workflow.get('executionCommit') == CONSUMED_V3_AUTHORIZATION['executionCommit'],
            'v3 execution commit changed')
    require(workflow.get('authorizationId') == CONSUMED_V3_AUTHORIZATION['id'],
            'v3 result authorization ID changed')
    require(workflow.get('authorizationConsumed') is True,
            'v3 result does not record authorization consumption')
    require(workflow.get('authorizationReusable') is False,
            'v3 result incorrectly permits authorization reuse')
    require(workflow.get('automaticRetryAllowed') is False,
            'v3 result incorrectly permits automatic retry')
    require(workflow.get('additionalRunAuthorized') is False,
            'v3 result incorrectly authorizes an additional run')
    numerical = result.get('numericalResult', {})
    require(numerical.get('requestedCaseCount') == 64
            and numerical.get('completedCaseCount') == 64
            and numerical.get('failedCaseCount') == 0
            and numerical.get('evaluationPassed') is True,
            'v3 result completion evidence changed')
    maps = result.get('mapPackage', {})
    require(maps.get('requiredMapCount') == 5
            and maps.get('completedMapCount') == 5
            and maps.get('completed') is True,
            'v3 map completion evidence changed')
    numeric_evidence = result.get('numericEvidence', {})
    require(numeric_evidence.get('sealed') is True
            and numeric_evidence.get('manifestSha256')
            == NUMERIC_EVIDENCE_MANIFEST_SHA256,
            'v3 sealed numeric-evidence binding changed')
    limits = result.get('interpretationLimits', {})
    require(limits.get('physicalValidationClaimAllowed') is False
            and limits.get('publicSimulatorConnectionEnabled') is False,
            'v3 result interpretation safeguards changed')
    return authorization_digest, result_digest


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    require(not os.path.lexists(path), f'control-validation output already exists: {path}')
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


def validate(repo_root: Path, expectation: str) -> dict[str, Any]:
    contract_path = fixed_repo_path(repo_root, CONTRACT_PATH, 'v3 execution contract')
    gate_path = fixed_repo_path(repo_root, GATE_PATH, 'v3 execution gate')
    authorization_path = fixed_repo_path(
        repo_root, AUTHORIZATION_PATH, 'v3 authorization', must_exist=False,
    )

    contract, contract_digest = core.load_json_strict(contract_path, 'v3 execution contract')
    require(contract.get('schema') == CONTRACT_SCHEMA, 'v3 execution-contract schema changed')
    core.validate_immutable_contract(contract)
    gate, gate_digest = core.load_json_strict(gate_path, 'v3 execution gate')
    require(gate.get('schema') == GATE_SCHEMA, 'v3 execution-gate schema changed')
    validate_consumed_previous(gate, repo_root)

    if core.validate_pending_gate(gate):
        require(set(gate) == BASE_GATE_KEYS, 'pending v3 execution-gate keys changed')
        actual_state = 'pending'
    elif gate.get('state') == 'authorized':
        require(set(gate) == BASE_GATE_KEYS, 'active v3 execution-gate keys changed')
        actual_state = 'active'
    elif gate.get('state') == 'consumed':
        actual_state = 'consumed'
    else:
        raise core.PreflightError(
            'v3 execution gate is neither exact pending, active, nor consumed state'
        )
    require(expectation == 'auto' or expectation == actual_state,
            f'expected v3 {expectation} control state, found {actual_state}')

    authorization_digest: str | None = None
    authorization_id: str | None = None
    result_record_digest: str | None = None
    if actual_state == 'pending':
        require(not os.path.lexists(authorization_path),
                'pending v3 control plane must not contain an authorization file')
        require(gate.get('state') == 'awaiting_new_explicit_authorization',
                'pending v3 gate state changed')
        require(gate.get('enabled') is False, 'pending v3 gate must be disabled')
        require(gate.get('replacementAuthorizationRequired') is True,
                'pending v3 gate must require a replacement authorization')
        require(gate.get('activeAuthorization') is None,
                'pending v3 gate must not contain an active authorization')
        require(gate.get('safeguards') == {
            'consumeOneTimeAuthorizationAllowed': False,
            'full64ExecutionAllowed': False,
            'automaticActivationAllowed': False,
        }, 'pending v3 gate safeguards changed')
    elif actual_state == 'active':
        require(authorization_path.is_file() and not authorization_path.is_symlink(),
                'active v3 control plane requires a regular authorization file')
        active = core.validate_active_gate(gate)
        authorization, authorization_digest = core.load_json_strict(
            authorization_path, 'v3 authorization',
        )
        core.validate_authorization(
            authorization,
            authorization_digest,
            active,
            contract,
            contract_path,
            contract_digest,
        )
        authorization_id = authorization['authorizationId']
        decision_path = fixed_repo_path(
            repo_root,
            authorization['decisionImage']['path'],
            'v3 authorization decision image',
        )
        require(core.sha256_file(decision_path) == authorization['decisionImage']['sha256'],
                'v3 authorization decision-image digest mismatch')
        require(gate.get('safeguards') == {
            'consumeOneTimeAuthorizationAllowed': True,
            'full64ExecutionAllowed': True,
            'automaticActivationAllowed': False,
        }, 'active v3 gate safeguards changed')
    else:
        authorization_digest, result_record_digest = validate_consumed_v3(
            gate, repo_root, authorization_path, contract, contract_digest,
        )
        authorization_id = CONSUMED_V3_AUTHORIZATION['id']

    return {
        'schema': SCHEMA,
        'status': 'passed',
        'controlState': actual_state,
        'executionAuthorized': actual_state == 'active',
        'authorizationPresent': actual_state in {'active', 'consumed'},
        'authorizationFilePresent': actual_state in {'active', 'consumed'},
        'authorizationActive': actual_state == 'active',
        'authorizationConsumed': actual_state == 'consumed',
        'authorizationId': authorization_id,
        'authorizationReusable': False if actual_state == 'consumed' else None,
        'consumedWorkflowRunId': (
            CONSUMED_V3_AUTHORIZATION['workflowRunId']
            if actual_state == 'consumed' else None
        ),
        'numericalCasesStarted': 0,
        'numericalOutputsCreated': 0,
        'digests': {
            'executionContractSha256': contract_digest,
            'executionGateSha256': gate_digest,
            'authorizedExecutionGateSha256': (
                CONSUMED_V3_AUTHORIZATION['authorizedGateSha256']
                if actual_state == 'consumed' else gate_digest if actual_state == 'active' else None
            ),
            'authorizationSha256': authorization_digest,
            'consumedPreviousAuthorizationSha256': CONSUMED_PREVIOUS_AUTHORIZATION['sha256'],
            'resultRecordSha256': result_record_digest,
            'numericEvidenceManifestSha256': (
                NUMERIC_EVIDENCE_MANIFEST_SHA256 if actual_state == 'consumed' else None
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', default='.')
    parser.add_argument(
        '--expect', choices=('auto', 'pending', 'active', 'consumed'), default='auto',
    )
    parser.add_argument('--output')
    args = parser.parse_args()

    result = validate(Path(args.repo_root).resolve(), args.expect)
    payload = f'{json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)}\n'
    if args.output:
        write_json_atomic(Path(args.output).absolute(), result)
    print(payload, end='')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, core.PreflightError) as error:
        print(f'[stage18-full64-v3-control] {error}', file=sys.stderr)
        raise SystemExit(2)
