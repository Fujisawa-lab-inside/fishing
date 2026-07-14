#!/usr/bin/env python3
"""Statically validate the corrected-v2 one-time workflow without executing it."""

import json
import re
from pathlib import Path


WORKFLOW = Path('.github/workflows/stage18-full64-v2-run.yml')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def block(text, start_marker, end_marker=None):
    start = text.index(start_marker)
    if end_marker is None:
        return text[start:]
    end = text.index(end_marker, start + len(start_marker))
    return text[start:end]


def ordered(text, markers, label):
    cursor = -1
    for marker in markers:
        index = text.find(marker)
        require(index >= 0, f'{label} is missing: {marker}')
        require(text.find(marker, index + 1) < 0, f'{label} must contain exactly one: {marker}')
        require(index > cursor, f'{label} order changed at: {marker}')
        cursor = index


def main():
    workflow = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')
    require(workflow.startswith(
        'name: Stage 18 corrected v2 one-time full64 numerical run\n'
        'run-name: Stage 18 corrected v2 one-time run ${{ github.run_id }}\n'
    ), 'workflow identity changed')
    expected_trigger = (
        'on:\n'
        '  workflow_dispatch:\n'
        '    inputs:\n'
        '      confirmation:\n'
        "        description: 'Exact confirmation phrase for the one authorized corrected-v2 64-case run'\n"
        '        required: true\n'
        '        type: string\n\n'
    )
    trigger_start = workflow.index('on:\n')
    trigger_end = workflow.index('permissions:\n')
    require(workflow[trigger_start:trigger_end] == expected_trigger,
            'workflow_dispatch must be the exact and only trigger')
    require('\npull_request:' not in workflow, 'execution workflow must not run on pull requests')
    require('\npush:' not in workflow, 'execution workflow must not run on push')
    require('\nschedule:' not in workflow, 'execution workflow must not be scheduled')
    require(workflow.count('  workflow_dispatch:\n') == 1, 'workflow_dispatch must be the only trigger')
    require("test \"$CONFIRMATION\" = 'RUN_STAGE18_FULL64_V2_ONCE'" in workflow,
            'exact confirmation phrase is missing')
    require(workflow.count("test \"$CONFIRMATION\" = 'RUN_STAGE18_FULL64_V2_ONCE'") == 2,
            'confirmation must be checked before preflight and consumption')
    require(workflow.count("test \"$REPOSITORY\" = 'Fujisawa-lab-inside/fishing'") == 2,
            'repository must be checked before preflight and consumption')
    require(workflow.count("test \"$ACTOR\" = 'RyusukeFujisawa'") == 2,
            'actor must be checked before preflight and consumption')
    require(workflow.count("test \"$REF\" = 'refs/heads/main'") == 2,
            'main ref must be checked before preflight and consumption')
    require(workflow.count('test "$RUN_ATTEMPT" = \'1\'') == 3,
            'first-attempt guard must cover every job')
    require('\npermissions:\n  actions: read\n  contents: read\n' in workflow,
            'workflow permissions must remain read-only')
    require(workflow.count('permissions:') == 1, 'job-level or duplicate permissions are forbidden')
    require("\nenv:\n  PYTHONDONTWRITEBYTECODE: '1'\n" in workflow,
            'authorized jobs must not dirty the reviewed worktree with Python bytecode')
    require(workflow.count('fetch-depth: 0') == 2,
            'both reviewed-code checkouts require complete Git history')
    require('cancel-in-progress: false' in workflow, 'one-time concurrency must not cancel an active run')
    require('continue-on-error:' not in workflow, 'failures must never be ignored')

    jobs = block(workflow, 'jobs:\n')
    job_names = re.findall(r'^  ([a-zA-Z0-9_-]+):$', jobs, flags=re.MULTILINE)
    require(job_names == ['preflight', 'authorize', 'full64'], 'workflow job set or order changed')
    preflight = block(jobs, '  preflight:\n', '  authorize:\n')
    authorize = block(jobs, '  authorize:\n', '  full64:\n')
    full64 = block(jobs, '  full64:\n')

    require('run_stage18_full64_v2.py' not in preflight,
            'preflight job must never invoke the numerical runner')
    require('needs: preflight' in authorize, 'authorization must depend on successful preflight')
    require('actions/checkout@' not in authorize, 'authorization-consumption job must not execute repository code')
    require('needs: [preflight, authorize]' in full64,
            'numerical job must depend on both preflight and authorization consumption')
    require('timeout-minutes: 90' in full64, 'numerical job ceiling changed')

    ordered(preflight, [
        '- name: Validate dispatch identity and scope',
        '- uses: actions/checkout@v4',
        '- uses: actions/setup-node@v4',
        '- name: Validate active v2 authorization and immutable contract',
        '- name: Record authorization identity',
        '- uses: actions/setup-python@v5',
        '- name: Install pinned dependencies',
        '- name: Validate result packaging with non-run fixtures',
        '- name: Generate exact corrected-v2 mesh and ensemble',
        '- name: Validate all inputs without starting a numerical case',
        '- uses: actions/upload-artifact@v4',
    ], 'preflight job')
    require(preflight.index('Validate active v2 authorization and immutable contract')
            < preflight.index('Install pinned dependencies'),
            'authorization must be checked before numerical dependencies are installed')
    require('node tools/validate_stage18_full64_gate.mjs --require-active' in preflight,
            'active gate validation is missing')
    require('--output "$RUNNER_TEMP/stage18-full64-gate-validation.json"' in preflight,
            'active gate validator must write outside the reviewed worktree')
    require('node tools/validate_stage18_full64_execution_contract_v2.mjs' in preflight,
            'immutable v2 contract validation is missing')
    require('"$RUNNER_TEMP/stage18-full64-execution-contract-v2-validation.json"' in preflight,
            'contract validator must write outside the reviewed worktree')
    require('python tools/preflight_stage18_full64_v2.py' in preflight,
            'zero-case input preflight is missing')
    require('python tools/validate_stage18_full64_v2_evaluator.py --require-numeric-fixture' in preflight,
            'result packaging must pass its non-run numerical/raster fixture before consumption')
    require('.numericalCasesStarted == 0 and .outputsCreated == 0' in preflight,
            'preflight zero-case proof is missing')

    ordered(authorize, [
        '- name: Revalidate dispatch before consumption',
        '- name: Consume v2 one-time authorization',
    ], 'authorization job')
    require('gh api --paginate' in authorize, 'one-time prior-run search is missing')
    require('select(.name == "Consume v2 one-time authorization" and .conclusion == "success")' in authorize,
            'successful prior consumption check is missing')
    require('A new reviewed execution path and new explicit authorization are required.' in authorize,
            'post-consumption retry must require a newly reviewed path')

    ordered(full64, [
        '- name: Reject rerun attempts',
        '- uses: actions/checkout@v4',
        '- uses: actions/setup-python@v5',
        '- name: Install pinned dependencies',
        '- uses: actions/download-artifact@v4',
        '- name: Revalidate downloaded preflight inputs',
        '- name: Create consumed-authorization receipt',
        '- name: Run exactly 64 corrected-v2 numerical cases',
        '- name: Evaluate provenance and numerical acceptance',
        '- name: Aggregate statistics and render five bound maps',
        '- name: Render user judgment image',
        '- name: Verify complete success package',
        'name: stage18-full64-v2-results-${{ github.run_id }}',
        '- name: Attempt fail-closed STOP image',
        'name: stage18-full64-v2-diagnostics-${{ github.run_id }}',
    ], 'full64 job')
    require('timeout --signal=TERM --kill-after=30s 65m' in full64,
            '65-minute numerical watchdog changed')
    require(full64.index('Create consumed-authorization receipt')
            < full64.index('run_stage18_full64_v2.py'),
            'receipt must be written after consumption and before numerical execution')
    require(full64.count('python tools/run_stage18_full64_v2.py') == 1,
            'numerical runner must have exactly one reachable invocation')
    runner_invocations = re.findall(
        r'^\s*python(?:3(?:\.\d+)?)?\s+tools/run_stage18_full64_v2\.py(?:\s|$)',
        workflow,
        flags=re.MULTILINE,
    )
    require(len(runner_invocations) == 1,
            'python/python3 numerical runner invocation count must be exactly one')
    require('--manifest "$WORK_DIR/visual/full64-visual-manifest.json"' in full64,
            'decision image must validate the map manifest')
    require("grep -F '判定: PASS / RESULT: PASS'" in full64,
            'success artifact must require an explicit PASS judgment image')
    require(full64.count('uses: actions/upload-artifact@v4') == 2,
            'success and diagnostic artifacts must be separate')
    require(full64.count('if: ${{ failure() || cancelled() }}') == 2,
            'STOP rendering and diagnostic upload must both cover failure or cancellation')
    require('if-no-files-found: error' in full64, 'success artifact must fail on missing files')
    require('if-no-files-found: warn' in full64, 'diagnostic artifact must tolerate partial files')
    require('persist-credentials: false' in preflight and 'persist-credentials: false' in full64,
            'checkout credentials must not persist')
    require('${{ runner.temp }}/stage18-full64-v2' in preflight
            and '${{ runner.temp }}/stage18-full64-v2' in full64,
            'generated inputs and outputs must stay outside the reviewed worktree')

    report = {
        'schema': 'onga-stage18-full64-v2-workflow-validation-v1',
        'status': 'passed',
        'full64Executed': False,
        'numericalCasesStarted': 0,
        'verified': [
            'workflow_dispatch only and read-only permissions',
            'actor, repository, main ref, confirmation, and first attempt',
            'active authorization validation before dependency installation',
            'validator reports and all generated data remain outside the reviewed worktree',
            'complete zero-case preflight before one-time consumption',
            'serialized one-time consumption with prior-success rejection',
            'runner reachable once and only after receipt creation',
            '60-minute acceptance, 65-minute watchdog, and 90-minute job ceiling',
            'provenance evaluation, five-map manifest, and explicit PASS image',
            'separate success artifact and best-effort fail-closed diagnostics',
        ],
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
