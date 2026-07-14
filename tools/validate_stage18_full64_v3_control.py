#!/usr/bin/env python3
"""Validate the fixed v3 pending or active control plane without numerics."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import run_stage18_full64_v2 as core
from stage18_full64_v3_profile import (
    AUTHORIZATION_PATH,
    CONTRACT_PATH,
    CONTRACT_SCHEMA,
    GATE_PATH,
    GATE_SCHEMA,
    configure_runner,
)


configure_runner(core)

SCHEMA = 'onga-stage18-full64-control-validation-v3'
GATE_KEYS = {
    'schema', 'state', 'enabled', 'replacementAuthorizationRequired',
    'activeAuthorization', 'consumedPreviousAuthorization', 'safeguards',
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
    require(set(gate) == GATE_KEYS, 'v3 execution-gate keys changed')
    require(gate.get('schema') == GATE_SCHEMA, 'v3 execution-gate schema changed')
    validate_consumed_previous(gate, repo_root)

    if core.validate_pending_gate(gate):
        actual_state = 'pending'
    elif gate.get('state') == 'authorized':
        actual_state = 'active'
    else:
        raise core.PreflightError('v3 execution gate is neither exact pending nor active state')
    require(expectation == 'auto' or expectation == actual_state,
            f'expected v3 {expectation} control state, found {actual_state}')

    authorization_digest: str | None = None
    authorization_id: str | None = None
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
    else:
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

    return {
        'schema': SCHEMA,
        'status': 'passed',
        'controlState': actual_state,
        'executionAuthorized': actual_state == 'active',
        'authorizationPresent': actual_state == 'active',
        'authorizationId': authorization_id,
        'numericalCasesStarted': 0,
        'numericalOutputsCreated': 0,
        'digests': {
            'executionContractSha256': contract_digest,
            'executionGateSha256': gate_digest,
            'authorizationSha256': authorization_digest,
            'consumedPreviousAuthorizationSha256': CONSUMED_PREVIOUS_AUTHORIZATION['sha256'],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', default='.')
    parser.add_argument('--expect', choices=('auto', 'pending', 'active'), default='auto')
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
