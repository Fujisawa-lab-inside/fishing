#!/usr/bin/env python3
"""Statically validate the inactive corrected-v3 recovery workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path


WORKFLOW = Path('.github/workflows/stage18-full64-v3-run.yml')
CHECKOUT_ACTION = 'actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5'
SETUP_NODE_ACTION = 'actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020'
SETUP_PYTHON_ACTION = 'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065'
UPLOAD_ARTIFACT_ACTION = 'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'
DOWNLOAD_ARTIFACT_ACTION = 'actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def block(text: str, start_marker: str, end_marker: str | None = None) -> str:
    start = text.index(start_marker)
    if end_marker is None:
        return text[start:]
    end = text.index(end_marker, start + len(start_marker))
    return text[start:end]


def ordered(text: str, markers: list[str], label: str) -> None:
    cursor = -1
    for marker in markers:
        index = text.find(marker)
        require(index >= 0, f'{label} is missing: {marker}')
        require(text.find(marker, index + 1) < 0,
                f'{label} must contain exactly one: {marker}')
        require(index > cursor, f'{label} order changed at: {marker}')
        cursor = index


def main() -> int:
    workflow = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')
    require(workflow.startswith(
        'name: Stage 18 corrected v3 one-time full64 recovery run\n'
        'run-name: Stage 18 corrected v3 recovery run ${{ github.run_id }}\n'
    ), 'workflow identity changed')
    expected_trigger = (
        'on:\n'
        '  workflow_dispatch:\n'
        '    inputs:\n'
        '      confirmation:\n'
        "        description: 'Exact confirmation phrase for the one authorized corrected-v3 64-case recovery run'\n"
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
    require(workflow.count('  workflow_dispatch:\n') == 1,
            'workflow_dispatch must be the only trigger')
    phrase = "test \"$CONFIRMATION\" = 'RUN_STAGE18_FULL64_V3_RECOVERY_ONCE'"
    require(workflow.count(phrase) == 2,
            'confirmation must be checked before preflight and consumption')
    require(workflow.count("test \"$REPOSITORY\" = 'Fujisawa-lab-inside/fishing'") == 2,
            'repository must be checked before preflight and consumption')
    require(workflow.count("test \"$ACTOR\" = 'RyusukeFujisawa'") == 2,
            'actor must be checked before preflight and consumption')
    require(workflow.count("test \"$REF\" = 'refs/heads/main'") == 2,
            'main ref must be checked before preflight and consumption')
    require(workflow.count('test "$RUN_ATTEMPT" = \'1\'') == 3,
            'first-attempt guard must cover preflight, consumption, and numerical jobs')
    require('\npermissions:\n  actions: read\n  contents: read\n' in workflow,
            'workflow permissions must remain read-only')
    require(workflow.count('permissions:') == 1,
            'job-level or duplicate permissions are forbidden')
    require("\nenv:\n  PYTHONDONTWRITEBYTECODE: '1'\n" in workflow,
            'Python bytecode must not dirty the reviewed worktree')
    require(workflow.count('fetch-depth: 0') == 3,
            'all reviewed-code checkouts require complete Git history')
    require(workflow.count('persist-credentials: false') == 3,
            'checkout credentials must never persist')
    require(workflow.count(f'uses: {SETUP_NODE_ACTION}') == 1
            and workflow.count("node-version: '22'") == 1,
            'the ensemble generator requires exactly one pinned Node 22 setup')
    expected_actions = {
        CHECKOUT_ACTION: 3,
        SETUP_NODE_ACTION: 1,
        SETUP_PYTHON_ACTION: 3,
        UPLOAD_ARTIFACT_ACTION: 5,
        DOWNLOAD_ARTIFACT_ACTION: 2,
    }
    for action, expected_count in expected_actions.items():
        require(workflow.count(f'uses: {action}') == expected_count,
                f'action digest or invocation count changed: {action}')
    action_uses = re.findall(r'uses: (actions/[a-z-]+)@([^\s]+)', workflow)
    require(len(action_uses) == sum(expected_actions.values()),
            'unexpected first-party action invocation found')
    require(all(re.fullmatch(r'[0-9a-f]{40}', revision) for _, revision in action_uses),
            'every execution action must be pinned to a full commit SHA')
    require('cancel-in-progress: false' in workflow,
            'one-time concurrency must not cancel an active run')
    require('continue-on-error:' not in workflow, 'failures must never be ignored')

    jobs = block(workflow, 'jobs:\n')
    job_names = re.findall(r'^  ([a-zA-Z0-9_-]+):$', jobs, flags=re.MULTILINE)
    require(job_names == ['preflight', 'authorize', 'numerical', 'maps'],
            'workflow job set or order changed')
    preflight = block(jobs, '  preflight:\n', '  authorize:\n')
    authorize = block(jobs, '  authorize:\n', '  numerical:\n')
    numerical = block(jobs, '  numerical:\n', '  maps:\n')
    maps = block(jobs, '  maps:\n')

    require('run_stage18_full64_v3.py' not in preflight,
            'preflight must never invoke the numerical runner')
    require('needs: preflight' in authorize,
            'authorization must depend on successful complete preflight')
    require('actions/checkout@' not in authorize,
            'authorization-consumption job must not execute repository code')
    require('needs: [preflight, authorize]' in numerical,
            'numerical job must depend on preflight and authorization consumption')
    require('needs: numerical' in maps,
            'map job must depend on sealed numerical evidence')
    require('timeout-minutes: 90' in numerical, 'numerical job ceiling changed')

    ordered(preflight, [
        '- name: Validate dispatch identity and recovery scope',
        f'- uses: {CHECKOUT_ACTION}',
        '- name: Validate active v3 authorization and immutable recovery contract',
        '- name: Record authorization identity',
        f'- uses: {SETUP_NODE_ACTION}',
        f'- uses: {SETUP_PYTHON_ACTION}',
        '- name: Install pinned dependencies',
        '- name: Validate result packaging with non-run fixtures',
        '- name: Generate exact corrected-v2 mesh and ensemble',
        '- name: Prove exact map raster coverage without numerical cases',
        '- name: Validate all inputs without starting a numerical case',
        f'- uses: {UPLOAD_ARTIFACT_ACTION}',
    ], 'preflight job')
    require(preflight.index('Validate active v3 authorization and immutable recovery contract')
            < preflight.index('Install pinned dependencies'),
            'authorization must be checked before numerical dependencies are installed')
    require('tools/validate_stage18_full64_v3_control.py' in preflight
            and '--expect active' in preflight,
            'active v3 control validation is missing')
    require('python tools/validate_stage18_full64_v2_evaluator.py --require-numeric-fixture'
            in preflight,
            'result packaging must pass its non-run numerical/raster fixture before consumption')
    require(preflight.index('Generate exact corrected-v2 mesh and ensemble')
            < preflight.index('validate_stage18_full64_v3_map_raster.py')
            < preflight.index('preflight_stage18_full64_v3.py'),
            'exact mesh raster proof must precede zero-case input preflight')
    require(preflight.count('python tools/validate_stage18_full64_v3_map_raster.py') == 1,
            'pre-consumption raster proof must run exactly once')
    require('.representedCellCount == 50129' in preflight,
            'complete raster cell coverage proof is missing')
    require('.cell320PixelCount >= 1' in preflight,
            'previously omitted boundary cell proof is missing')
    require('.squarePixels == true' in preflight,
            'square-pixel raster proof is missing')
    require('.numericalCasesStarted == 0' in preflight,
            'preflight zero-case proof is missing')
    require('full64-map-raster-preflight.json' in preflight,
            'raster proof must be retained in the preflight artifact')

    ordered(authorize, [
        '- name: Revalidate dispatch before v3 consumption',
        '- name: Consume v3 one-time recovery authorization',
    ], 'authorization job')
    require(authorize.count('gh api --paginate') == 2,
            'both prior-run and prior-job searches must paginate')
    require('gh api --paginate --slurp' in authorize,
            'prior-job pages must be slurped before the all-page success search')
    require('[.[].jobs[].steps[]?' in authorize,
            'prior authorization consumption must be searched across every job page')
    require(
        'select(.name == "Consume v3 one-time recovery authorization" and .conclusion == "success")'
        in authorize,
        'successful prior consumption check is missing',
    )
    require('A new reviewed execution path and new explicit authorization are required.' in authorize,
            'post-consumption retry must require a newly reviewed path')

    ordered(numerical, [
        '- name: Reject numerical rerun attempts',
        f'- uses: {CHECKOUT_ACTION}',
        f'- uses: {SETUP_PYTHON_ACTION}',
        '- name: Install pinned dependencies',
        f'- uses: {DOWNLOAD_ARTIFACT_ACTION}',
        '- name: Revalidate downloaded raster and input preflights',
        '- name: Create consumed-authorization receipt',
        '- name: Run exactly 64 corrected-v2 numerical cases once',
        '- name: Evaluate provenance and numerical acceptance',
        '- name: Seal complete numerical evidence before any map rendering',
        'name: stage18-full64-v3-numeric-evidence-${{ github.run_id }}',
        '- name: Attempt fail-closed STOP image',
        'name: stage18-full64-v3-diagnostics-${{ github.run_id }}',
    ], 'numerical job')
    require('timeout --signal=TERM --kill-after=30s 65m' in numerical,
            '65-minute numerical watchdog changed')
    require(numerical.index('Create consumed-authorization receipt')
            < numerical.index('run_stage18_full64_v3.py'),
            'receipt must be written after consumption and before numerical execution')
    require(numerical.count('python tools/run_stage18_full64_v3.py') == 1,
            'numerical runner must have exactly one reachable invocation')
    require(workflow.count('run_stage18_full64_v3.py') == 1,
            'v3 runner filename must occur exactly once in the entire workflow')
    require('run_stage18_full64_v2.py' not in workflow,
            'the historical v2 numerical runner must not be reachable from v3')
    runner_invocations = re.findall(
        r'^\s*python(?:3(?:\.\d+)?)?\s+tools/run_stage18_full64_v3\.py(?:\s|$)',
        workflow,
        flags=re.MULTILINE,
    )
    require(len(runner_invocations) == 1,
            'python/python3 numerical runner invocation count must be exactly one')
    require('aggregate_stage18_full64_v3.py' not in numerical,
            'map aggregation must not occur in the numerical job')
    require('Render user judgment image' not in numerical,
            'the normal judgment image must not be rendered before map packaging')
    immediate_upload = re.compile(
        r'- name: Seal complete numerical evidence before any map rendering\n'
        r'(?:.*\n)*?'
        rf'      - uses: {re.escape(UPLOAD_ARTIFACT_ACTION)}\n'
        r'        with:\n'
        r'          name: stage18-full64-v3-numeric-evidence-\$\{\{ github\.run_id \}\}\n'
    )
    require(immediate_upload.search(numerical) is not None,
            'sealed numerical evidence must be the next uploaded artifact')
    numeric_evidence_artifact = block(
        numerical,
        'name: stage18-full64-v3-numeric-evidence-${{ github.run_id }}',
        '- name: Attempt fail-closed STOP image',
    )
    for filename in [
        'execution-receipt.json',
        'onga_stage16_metric_fv_mesh_v2.npz',
        'stage16_metric_mesh_summary.json',
        'ensemble-v2.json',
        'full64-map-raster-preflight.json',
        'full64-map-raster-preflight-recheck.json',
        'preflight.json',
        'preflight-recheck.json',
        'full64-progress.json',
        'full64-report.json',
        'full64-fields.npz',
        'full64-evaluation.json',
        'full64-numeric-evidence-manifest.json',
    ]:
        require(filename in numeric_evidence_artifact,
                f'numerical evidence artifact is missing: {filename}')
    require(numerical.count(f'uses: {UPLOAD_ARTIFACT_ACTION}') == 2,
            'numeric evidence and diagnostic artifacts must be separate')
    require(numerical.count('if: ${{ failure() || cancelled() }}') == 2,
            'numerical STOP rendering and diagnostics must cover failure or cancellation')
    require('if-no-files-found: error' in numerical,
            'numerical evidence upload must fail on missing files')
    require('if-no-files-found: warn' in numerical,
            'numerical diagnostics must tolerate partial files')
    numerical_diagnostics = block(
        numerical,
        'name: stage18-full64-v3-diagnostics-${{ github.run_id }}',
    )
    for recoverable_filename in [
        'onga_stage16_metric_fv_mesh_v2.npz',
        'stage16_metric_mesh_summary.json',
        'ensemble-v2.json',
        'full64-report.json',
        'full64-fields.npz',
        'full64-evaluation.json',
        'full64-diagnostic-stop.svg',
    ]:
        require(recoverable_filename in numerical_diagnostics,
                f'numerical diagnostics are missing recoverable evidence: {recoverable_filename}')

    ordered(maps, [
        f'- uses: {CHECKOUT_ACTION}',
        f'- uses: {SETUP_PYTHON_ACTION}',
        '- name: Install pinned dependencies',
        f'- uses: {DOWNLOAD_ARTIFACT_ACTION}',
        '- name: Verify downloaded sealed numerical evidence',
        '- name: Aggregate statistics and render five bound maps',
        '- name: Render user judgment image',
        '- name: Verify complete map package',
        'name: stage18-full64-v3-results-${{ github.run_id }}',
        '- name: Attempt fail-closed STOP image',
        'name: stage18-full64-v3-diagnostics-${{ github.run_id }}',
    ], 'map job')
    require('run_stage18_full64_' not in maps,
            'map job must not contain any numerical runner')
    require('RUN_ATTEMPT' not in maps,
            'sealed-evidence map packaging must allow a manual map-only retry')
    require('stage18-full64-v3-numeric-evidence-${{ github.run_id }}' in maps,
            'map job must download the sealed numerical artifact')
    require('seal_stage18_full64_v3_numeric_evidence.py' in maps
            and '--verify "$WORK_DIR/full64-numeric-evidence-manifest.json"' in maps,
            'map job must verify the sealed numerical manifest before use')
    require(maps.index('Verify downloaded sealed numerical evidence')
            < maps.index('aggregate_stage18_full64_v3.py'),
            'numeric evidence verification must precede map aggregation')
    require('--manifest "$WORK_DIR/visual/full64-visual-manifest.json"' in maps,
            'decision image must validate the map manifest')
    require(workflow.count('--manifest "$WORK_DIR/visual/full64-visual-manifest.json"') == 1,
            'diagnostic renderers must omit the manifest so they are forced to STOP')
    require("grep -F '判定: PASS / RESULT: PASS'" in maps,
            'success artifact must require an explicit PASS judgment image')
    require(maps.count(f'uses: {UPLOAD_ARTIFACT_ACTION}') == 2,
            'map results and map diagnostics must be separate')
    require(workflow.count('name: stage18-full64-v3-diagnostics-${{ github.run_id }}') == 2,
            'both mutually exclusive failure jobs must use the fixed diagnostic prefix')
    require(maps.count('if: ${{ failure() || cancelled() }}') == 2,
            'STOP rendering and diagnostics must cover failure or cancellation')
    require('if-no-files-found: error' in maps,
            'map success artifact must fail on missing files')
    require('if-no-files-found: warn' in maps,
            'map diagnostics must tolerate partial files')
    require('${{ runner.temp }}/stage18-full64-v3' in preflight
            and '${{ runner.temp }}/stage18-full64-v3' in numerical
            and '${{ runner.temp }}/stage18-full64-v3' in maps,
            'generated inputs and outputs must stay outside the reviewed worktree')

    report = {
        'schema': 'onga-stage18-full64-v3-workflow-validation-v1',
        'status': 'passed',
        'workflowExecuted': False,
        'numericalCasesStarted': 0,
        'verified': [
            'workflow_dispatch only with exact actor, repository, main ref, and confirmation',
            'first-attempt-only numerical path with manual map-only recovery and read-only permissions',
            'all first-party execution actions pinned to full commit SHAs',
            'active v3 control required before dependency installation',
            'exact mesh raster coverage proof before authorization consumption',
            'complete zero-case input preflight before authorization consumption',
            'serialized one-time consumption with prior-success rejection',
            'one numerical runner invocation after consumed-authorization receipt',
            'sealed complete numerical evidence uploaded immediately after evaluation',
            'separate map job downloads and verifies the sealed evidence without a runner',
            'separate success artifacts and best-effort partial diagnostics',
        ],
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f'[stage18-full64-v3-workflow] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
