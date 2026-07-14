#!/usr/bin/env python3
"""Create a provenance-bound receipt after the v2 one-time gate is consumed."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path

from run_stage18_full64_v2 import (
    AUTHORIZATION_PATH,
    CONTRACT_PATH,
    GATE_PATH,
    PreflightError,
    load_json_strict,
    resolve_repo_relative_path,
    sha256_file,
    validate_authorization,
    validate_immutable_contract,
    validate_reviewed_code_commit,
    validate_active_gate,
    write_json_atomic,
)


REPOSITORY = 'Fujisawa-lab-inside/fishing'
ACTOR = 'RyusukeFujisawa'
REF = 'refs/heads/main'
RECEIPT_SCHEMA = 'onga-stage18-full64-execution-receipt-v2'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightError(message)


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
    contract_path = resolve_repo_relative_path(repo_root, args.contract, 'execution contract')
    authorization_path = resolve_repo_relative_path(repo_root, args.authorization, 'authorization')
    gate_path = resolve_repo_relative_path(repo_root, args.gate, 'execution gate')
    preflight_path = Path(args.preflight).resolve()
    output_path = Path(args.output).resolve()
    require(output_path != preflight_path, 'receipt output overlaps preflight report')

    contract, contract_digest = load_json_strict(contract_path, 'v2 execution contract')
    validate_immutable_contract(contract)
    gate, gate_digest = load_json_strict(gate_path, 'v2 execution gate')
    active = validate_active_gate(gate)
    authorization, authorization_digest = load_json_strict(authorization_path, 'v2 authorization')
    validate_authorization(
        authorization,
        authorization_digest,
        active,
        contract,
        contract_path,
        contract_digest,
    )
    decision_path = resolve_repo_relative_path(
        repo_root,
        authorization['decisionImage']['path'],
        'authorization decision image',
    )
    require(
        sha256_file(decision_path) == authorization['decisionImage']['sha256'],
        'authorization decision-image digest mismatch',
    )
    execution_commit = validate_reviewed_code_commit(
        repo_root,
        authorization['reviewedCodeCommit'],
    )

    preflight, preflight_digest = load_json_strict(preflight_path, 'v2 preflight report')
    require(preflight.get('schema') == 'onga-stage18-full64-preflight-v2', 'preflight schema changed')
    require(preflight.get('status') == 'passed', 'preflight did not pass')
    require(preflight.get('numericalCasesStarted') == 0, 'preflight started numerical cases')
    require(preflight.get('outputsCreated') == 0, 'preflight created numerical outputs')
    require(preflight.get('caseCount') == 64, 'preflight case count changed')
    require(preflight.get('cellCount') == 50129, 'preflight cell count changed')
    digests = preflight.get('inputDigests', {})
    require(digests.get('executionContractSha256') == contract_digest, 'preflight contract digest mismatch')
    require(digests.get('authorizationSha256') == authorization_digest, 'preflight authorization digest mismatch')
    require(digests.get('meshSha256') == contract['meshExpected']['packageSha256'], 'preflight mesh digest mismatch')
    require(digests.get('ensembleSha256') == contract['ensembleExpected']['sha256'], 'preflight ensemble digest mismatch')
    require(re.fullmatch(r'[a-f0-9]{64}', digests.get('meshSummarySha256', '')) is not None,
            'preflight mesh-summary digest missing')

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
    require(environment['workflow'] == 'Stage 18 corrected v2 one-time full64 numerical run',
            'receipt workflow name mismatch')

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
            'stepName': 'Consume v2 one-time authorization',
            'automaticRetryAllowed': False,
            'automaticAdditionalRunAllowed': False,
        },
        'createdAtUtc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }
    write_json_atomic(output_path, receipt)
    print(json.dumps({'output': str(output_path), 'authorizationId': receipt['authorizationId']}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, PreflightError) as error:
        print(f'[stage18-full64-v2-receipt] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
