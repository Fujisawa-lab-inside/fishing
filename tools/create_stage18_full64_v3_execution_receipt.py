#!/usr/bin/env python3
"""Create a provenance-bound receipt after the v3 one-time gate is consumed."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import run_stage18_full64_v2 as core
from stage18_full64_v3_profile import (
    AUTHORIZATION_PATH,
    CONTRACT_PATH,
    EXPECTED_WORKFLOW,
    GATE_PATH,
    configure_runner,
)


configure_runner(core)

REPOSITORY = 'Fujisawa-lab-inside/fishing'
ACTOR = 'RyusukeFujisawa'
REF = 'refs/heads/main'
RECEIPT_SCHEMA = 'onga-stage18-full64-execution-receipt-v3'
PREFLIGHT_SCHEMA = 'onga-stage18-full64-preflight-v3'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise core.PreflightError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('preflight')
    parser.add_argument('--contract', default=CONTRACT_PATH)
    parser.add_argument('--authorization', default=AUTHORIZATION_PATH)
    parser.add_argument('--gate', default=GATE_PATH)
    parser.add_argument('--repo-root', default='.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    for raw_path, label in (
        (args.contract, 'v3 execution contract'),
        (args.authorization, 'v3 authorization'),
        (args.gate, 'v3 execution gate'),
    ):
        candidate = repo_root / raw_path
        require(not candidate.is_symlink(), f'{label} must not be a symbolic link')
    contract_path = core.resolve_repo_relative_path(
        repo_root, args.contract, 'v3 execution contract',
    )
    authorization_path = core.resolve_repo_relative_path(
        repo_root, args.authorization, 'v3 authorization',
    )
    gate_path = core.resolve_repo_relative_path(repo_root, args.gate, 'v3 execution gate')
    require(contract_path == (repo_root / CONTRACT_PATH).resolve(),
            'receipt must use the fixed v3 execution contract')
    require(authorization_path == (repo_root / AUTHORIZATION_PATH).resolve(),
            'receipt must use the fixed v3 authorization')
    require(gate_path == (repo_root / GATE_PATH).resolve(),
            'receipt must use the fixed v3 execution gate')

    preflight_argument = Path(args.preflight)
    require(not preflight_argument.is_symlink(), 'v3 preflight report must not be a symbolic link')
    preflight_path = preflight_argument.resolve()
    output_path = Path(args.output).absolute()
    require(output_path != preflight_path, 'receipt output overlaps preflight report')
    require(preflight_path.is_file() and not preflight_path.is_symlink(),
            'v3 preflight report must be a regular file')

    contract, contract_digest = core.load_json_strict(contract_path, 'v3 execution contract')
    core.validate_immutable_contract(contract)
    gate, gate_digest = core.load_json_strict(gate_path, 'v3 execution gate')
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
    decision_path = core.resolve_repo_relative_path(
        repo_root,
        authorization['decisionImage']['path'],
        'v3 authorization decision image',
    )
    require(
        core.sha256_file(decision_path) == authorization['decisionImage']['sha256'],
        'v3 authorization decision-image digest mismatch',
    )
    execution_commit = core.validate_reviewed_code_commit(
        repo_root,
        authorization['reviewedCodeCommit'],
        authorization['decisionImage']['path'],
    )

    preflight, preflight_digest = core.load_json_strict(preflight_path, 'v3 preflight report')
    require(preflight.get('schema') == PREFLIGHT_SCHEMA, 'v3 preflight schema changed')
    require(preflight.get('status') == 'passed', 'v3 preflight did not pass')
    require(preflight.get('numericalCasesStarted') == 0, 'v3 preflight started numerical cases')
    require(preflight.get('outputsCreated') == 0, 'v3 preflight created numerical outputs')
    require(preflight.get('caseCount') == 64, 'v3 preflight case count changed')
    require(preflight.get('cellCount') == 50129, 'v3 preflight cell count changed')
    digests = preflight.get('inputDigests', {})
    require(isinstance(digests, dict), 'v3 preflight input digests are missing')
    require(digests.get('executionContractSha256') == contract_digest,
            'v3 preflight contract digest mismatch')
    require(digests.get('authorizationSha256') == authorization_digest,
            'v3 preflight authorization digest mismatch')
    require(digests.get('meshSha256') == contract['meshExpected']['packageSha256'],
            'v3 preflight mesh digest mismatch')
    require(digests.get('ensembleSha256') == contract['ensembleExpected']['sha256'],
            'v3 preflight ensemble digest mismatch')
    require(re.fullmatch(r'[a-f0-9]{64}', digests.get('meshSummarySha256', '')) is not None,
            'v3 preflight mesh-summary digest is missing')

    environment = {
        'repository': os.environ.get('GITHUB_REPOSITORY'),
        'actor': os.environ.get('GITHUB_ACTOR'),
        'ref': os.environ.get('GITHUB_REF'),
        'sha': os.environ.get('GITHUB_SHA'),
        'runId': os.environ.get('GITHUB_RUN_ID'),
        'runAttempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'workflow': os.environ.get('GITHUB_WORKFLOW'),
    }
    require(environment['repository'] == REPOSITORY, 'receipt repository mismatch')
    require(environment['actor'] == ACTOR, 'receipt actor mismatch')
    require(environment['ref'] == REF, 'receipt ref mismatch')
    require(environment['sha'] == execution_commit, 'receipt execution commit mismatch')
    require(environment['runAttempt'] == '1', 'receipt requires first run attempt')
    require(isinstance(environment['runId'], str) and environment['runId'].isdigit(),
            'receipt workflow run ID is invalid')
    require(environment['workflow'] == EXPECTED_WORKFLOW, 'receipt workflow name mismatch')

    receipt = {
        'schema': RECEIPT_SCHEMA,
        'status': 'one_time_authorization_consumed',
        'authorizationId': authorization['authorizationId'],
        'authorizationSha256': authorization_digest,
        'executionContractSha256': contract_digest,
        'executionGateSha256': gate_digest,
        'decisionImageSha256': authorization['decisionImage']['sha256'],
        'preflightSha256': preflight_digest,
        'reviewedCodeCommit': authorization['reviewedCodeCommit'],
        'executionCommit': execution_commit,
        'authorizationValidity': {
            'issuedAtUtc': authorization['issuedAtUtc'],
            'notAfterUtc': authorization['notAfterUtc'],
            'maxValiditySeconds': 86400,
        },
        'workflow': environment,
        'consumptionEvidence': {
            'stepName': 'Consume v3 one-time recovery authorization',
            'automaticRetryAllowed': False,
            'automaticAdditionalRunAllowed': False,
        },
        'createdAtUtc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }
    core.write_json_atomic(output_path, receipt)
    print(json.dumps({
        'output': str(output_path),
        'authorizationId': receipt['authorizationId'],
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, core.PreflightError) as error:
        print(f'[stage18-full64-v3-receipt] {error}', file=sys.stderr)
        raise SystemExit(2)
