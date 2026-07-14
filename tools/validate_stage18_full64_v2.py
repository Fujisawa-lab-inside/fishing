#!/usr/bin/env python3
"""Fixture-based negative tests for the fail-closed Stage 18 v2 runner."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import types
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_stage18_full64_v2 import (
    ExecutionStop,
    PreflightError,
    execute_cases,
    validate_authorization_validity_window,
    validate_case_thresholds,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / 'tools' / 'run_stage18_full64_v2.py'
PREFLIGHT = REPO_ROOT / 'tools' / 'preflight_stage18_full64_v2.py'
CONTRACT_SOURCE = REPO_ROOT / 'config' / 'stage18_full64_execution_contract_v2.json'
GATE_SOURCE = REPO_ROOT / 'config' / 'stage18_full64_execution_gate_v1.json'
FIXTURE_REPOSITORY = 'Fujisawa-lab-inside/fishing'
FIXTURE_WORKFLOW_PATH = '.github/workflows/stage18-full64-v2-run.yml'
FIXTURE_WORKFLOW_NAME = 'Stage 18 corrected v2 one-time full64 numerical run'
FIXTURE_SOURCE_STATEMENT = (
    '承認済み橋下補正v2上で、この判断資料に示された64条件×500ステップを、'
    '承認後24時間以内に一回限りの数値安定性確認として実行してよい。'
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def strict_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(f'{json.dumps(value, ensure_ascii=False, indent=2)}\n', encoding='utf-8')


def command(script, root, extra=()):
    return [
        sys.executable,
        str(script),
        'missing-v2-mesh.npz',
        'missing-v2-ensemble.json',
        'config/stage18_full64_run_authorization_v2.json',
        '--execution-contract',
        'config/stage18_full64_execution_contract_v2.json',
        '--execution-gate',
        'config/stage18_full64_execution_gate_v1.json',
        '--mesh-summary',
        'missing-v2-summary.json',
        '--fields-output',
        'should-not-exist-fields.npz',
        '--report-output',
        'should-not-exist-report.json',
        '--progress-output',
        'should-not-exist-progress.json',
        '--repo-root',
        str(root),
        *extra,
    ]


def run_blocked(script, root, blocker, extra=(), extra_environment=None):
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(blocker)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    if extra_environment is not None:
        environment.update(extra_environment)
    return subprocess.run(
        command(script, root, extra),
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def github_environment(head_commit):
    return {
        'GITHUB_ACTIONS': 'true',
        'GITHUB_ACTOR': 'RyusukeFujisawa',
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_REF': 'refs/heads/main',
        'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_RUN_ID': '123456789',
        'GITHUB_SHA': head_commit,
        'GITHUB_REPOSITORY': FIXTURE_REPOSITORY,
        'GITHUB_WORKFLOW': FIXTURE_WORKFLOW_NAME,
        'GITHUB_WORKFLOW_REF': (
            f'{FIXTURE_REPOSITORY}/{FIXTURE_WORKFLOW_PATH}@refs/heads/main'
        ),
    }


def require_no_outputs(root):
    for name in (
        'should-not-exist-fields.npz',
        'should-not-exist-report.json',
        'should-not-exist-progress.json',
        'numpy-imported.marker',
    ):
        require(not (Path(root) / name).exists(), f'unauthorized path created {name}')


def pending_gate_fixture():
    """Return the disabled gate shape even after the repository gate becomes active."""
    gate = strict_json(GATE_SOURCE)
    gate['state'] = 'awaiting_new_explicit_authorization'
    gate['enabled'] = False
    gate['replacementAuthorizationRequired'] = True
    gate['activeAuthorization'] = None
    gate['safeguards']['consumeOneTimeAuthorizationAllowed'] = False
    gate['safeguards']['full64ExecutionAllowed'] = False
    gate['safeguards']['automaticActivationAllowed'] = False
    return gate


def make_root(base, contract=None, gate=None, authorization=None):
    root = Path(base)
    write_json(
        root / 'config' / 'stage18_full64_execution_contract_v2.json',
        strict_json(CONTRACT_SOURCE) if contract is None else contract,
    )
    write_json(
        root / 'config' / 'stage18_full64_execution_gate_v1.json',
        pending_gate_fixture() if gate is None else gate,
    )
    if authorization is not None:
        write_json(root / 'config' / 'stage18_full64_run_authorization_v2.json', authorization)
    return root


def make_authorization(
    contract_path,
    contract,
    decision_image_path,
    reviewed_commit,
    decision_image_relative='docs/visuals/stage18-v2-execution-decision.svg',
):
    issued = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(minutes=1)
    not_after = issued + dt.timedelta(hours=24)
    return {
        'schema': 'onga-stage18-full64-run-authorization-v2',
        'authorizationId': 'fixture-v2-authorization',
        'authorized': True,
        'oneTime': True,
        'approvedBy': 'Ryusuke Fujisawa',
        'approvedDate': '2026-07-14',
        'issuedAtUtc': issued.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'notAfterUtc': not_after.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'sourceStatement': FIXTURE_SOURCE_STATEMENT,
        'scope': 'exactly_64_corrected_geometry_v2_cases_for_runtime_and_numerical_stability_evidence',
        'decisionImage': {
            'path': decision_image_relative,
            'sha256': digest(decision_image_path),
        },
        'executionContract': {
            'path': 'config/stage18_full64_execution_contract_v2.json',
            'sha256': digest(contract_path),
        },
        'reviewedCodeCommit': reviewed_commit,
        'geometry': contract['geometry'],
        'meshExpected': contract['meshExpected'],
        'ensembleExpected': contract['ensembleExpected'],
        'run': contract['run'],
        'acceptance': contract['acceptance'],
        'safeguards': {
            'automaticAdditionalRunsAllowed': False,
            'automaticRetryAllowed': False,
            'inferredParametersAreObservations': False,
            'physicalValidationClaimAllowed': False,
            'sensitivityClaimAllowed': False,
            'publicSimulatorConnectionAllowed': False,
            'legacyFlowCalculationMayChange': False,
            'failedCasesMayBeImputed': False,
        },
    }


def activate_gate(gate, authorization_path, authorization_id='fixture-v2-authorization'):
    active = json.loads(json.dumps(gate))
    active['state'] = 'authorized'
    active['enabled'] = True
    active['replacementAuthorizationRequired'] = False
    active['activeAuthorization'] = {
        'id': authorization_id,
        'path': 'config/stage18_full64_run_authorization_v2.json',
        'sha256': digest(authorization_path),
    }
    active['safeguards']['consumeOneTimeAuthorizationAllowed'] = True
    active['safeguards']['full64ExecutionAllowed'] = True
    active['safeguards']['automaticActivationAllowed'] = False
    return active


def run_git(root, *arguments):
    environment = os.environ.copy()
    environment.update({'GIT_TERMINAL_PROMPT': '0', 'LC_ALL': 'C'})
    result = subprocess.run(
        ['git', '-C', str(root), *arguments],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    require(
        result.returncode == 0,
        f'fixture git command failed ({" ".join(arguments)}): {result.stderr}',
    )
    return result.stdout.strip()


def prepare_authorized_git_root(
    root,
    *,
    reviewed_commit_override=None,
    decision_image_relative='docs/visuals/stage18-v2-execution-decision.svg',
    extra_activation_file=None,
    omit_reviewed_file=None,
):
    root = Path(root)
    contract_path = root / 'config' / 'stage18_full64_execution_contract_v2.json'
    contract = strict_json(contract_path)
    decision_image_path = root / 'docs' / 'visuals' / 'stage18-v2-execution-decision.svg'
    decision_image_path.parent.mkdir(parents=True, exist_ok=True)
    decision_image_path.write_bytes(b'fixture decision image')
    for reviewed_file in (
        'tools/run_stage18_full64_v2.py',
        'tools/stage18_shallow_water_kernel_v2.py',
        FIXTURE_WORKFLOW_PATH,
    ):
        if reviewed_file == omit_reviewed_file:
            continue
        reviewed_path = root / reviewed_file
        reviewed_path.parent.mkdir(parents=True, exist_ok=True)
        reviewed_path.write_text(f'reviewed fixture: {reviewed_file}\n', encoding='utf-8')
    (root / '.gitignore').write_text(
        '\n'.join((
            'should-not-exist-fields.npz',
            'should-not-exist-report.json',
            'should-not-exist-progress.json',
            'numpy-imported.marker',
            '',
        )),
        encoding='utf-8',
    )
    run_git(root, 'init', '--quiet')
    run_git(root, 'config', 'user.name', 'Stage18 Fixture')
    run_git(root, 'config', 'user.email', 'stage18-fixture@example.invalid')
    run_git(root, 'add', '--all')
    run_git(root, 'commit', '--quiet', '-m', 'reviewed base')
    base_commit = run_git(root, 'rev-parse', 'HEAD')

    authorization = make_authorization(
        contract_path,
        contract,
        decision_image_path,
        reviewed_commit_override or base_commit,
        decision_image_relative,
    )
    authorization_path = root / 'config' / 'stage18_full64_run_authorization_v2.json'
    write_json(authorization_path, authorization)
    active_gate = activate_gate(pending_gate_fixture(), authorization_path)
    write_json(root / 'config' / 'stage18_full64_execution_gate_v1.json', active_gate)
    if extra_activation_file is not None:
        extra_path = root / extra_activation_file
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_text('unexpected post-review change\n', encoding='utf-8')
    run_git(root, 'add', '--all')
    run_git(root, 'commit', '--quiet', '-m', 'activate authorization fixture')
    head_commit = run_git(root, 'rev-parse', 'HEAD')
    return {
        'baseCommit': base_commit,
        'headCommit': head_commit,
        'authorizationPath': authorization_path,
    }


def verify_interrupt_progress(root, mode):
    root = Path(root)
    progress_path = root / f'{mode}-progress.json'
    fake_numpy = types.ModuleType('numpy')
    fake_kernel = types.ModuleType('stage18_shallow_water_kernel_v2')

    class FixtureNumericalStop(RuntimeError):
        pass

    def interrupted_build_geometry(_package):
        if mode == 'sigterm':
            os.kill(os.getpid(), signal.SIGTERM)
            raise AssertionError('SIGTERM handler did not interrupt execution')
        raise KeyboardInterrupt('fixture keyboard interrupt')

    fake_kernel.NumericalStop = FixtureNumericalStop
    fake_kernel.build_geometry = interrupted_build_geometry
    fake_kernel.run_case = lambda *_args, **_kwargs: None
    prior_numpy = sys.modules.get('numpy')
    prior_kernel = sys.modules.get('stage18_shallow_water_kernel_v2')
    sys.modules['numpy'] = fake_numpy
    sys.modules['stage18_shallow_water_kernel_v2'] = fake_kernel
    context = {
        'package': object(),
        'progressPath': progress_path,
        'contractSha256': '1' * 64,
        'authorizationSha256': '2' * 64,
        'meshSha256': '3' * 64,
        'meshSummarySha256': '4' * 64,
        'ensembleSha256': '5' * 64,
    }
    caught = None
    try:
        execute_cases(None, context)
    except BaseException as error:
        caught = error
    finally:
        if prior_numpy is None:
            sys.modules.pop('numpy', None)
        else:
            sys.modules['numpy'] = prior_numpy
        if prior_kernel is None:
            sys.modules.pop('stage18_shallow_water_kernel_v2', None)
        else:
            sys.modules['stage18_shallow_water_kernel_v2'] = prior_kernel
    expected_type = ExecutionStop if mode == 'sigterm' else KeyboardInterrupt
    require(isinstance(caught, expected_type), f'{mode} did not propagate its interruption')
    progress = strict_json(progress_path)
    require(progress.get('status') == 'stopped', f'{mode} did not write STOP progress')
    require(progress.get('completedCaseCount') == 0, f'{mode} progress claims completed cases')
    require(progress.get('attemptedCaseIds') == [], f'{mode} progress claims attempted cases')
    require(mode.upper().replace('TERM', 'TERM') in progress['stop']['reason'].upper()
            if mode == 'sigterm' else 'KEYBOARDINTERRUPT' in progress['stop']['reason'].upper(),
            f'{mode} STOP reason is missing')


def main():
    source = RUNNER.read_text(encoding='utf-8')
    require('from run_stage18_full64 import' not in source, 'v2 runner imports retired v1 runner')
    require('from run_stage18_production_mesh_pilot import' not in source, 'v2 runner imports retired pilot')
    require('\nimport numpy' not in source.split('def validate_mesh_package', 1)[0], 'v2 runner imports NumPy before data preflight')
    require('signal.SIGINT' in source and 'signal.SIGTERM' in source,
            'authorized runner does not install both interruption handlers')
    require("publication_state=fields_publication" in source
            and "publication_state=report_publication" in source,
            'field/report publication ownership tracking is missing')

    verified = []
    issued = dt.datetime(2026, 7, 14, 0, 0, 0, tzinfo=dt.timezone.utc)
    valid_window = {
        'issuedAtUtc': '2026-07-14T00:00:00Z',
        'notAfterUtc': '2026-07-15T00:00:00Z',
    }
    validate_authorization_validity_window(
        valid_window,
        now=issued + dt.timedelta(hours=12),
    )
    invalid_windows = (
        ({**valid_window, 'notAfterUtc': '2026-07-15T00:00:01Z'}, issued, 'overlong'),
        (valid_window, issued - dt.timedelta(seconds=1), 'not-yet-valid'),
        (valid_window, issued + dt.timedelta(days=1, seconds=1), 'expired'),
    )
    rejected_windows = 0
    for authorization_window, current, _label in invalid_windows:
        try:
            validate_authorization_validity_window(authorization_window, now=current)
        except PreflightError:
            rejected_windows += 1
    require(rejected_windows == len(invalid_windows), 'authorization validity windows did not fail closed')
    verified.append('authorization must be current and its validity window cannot exceed 24 hours')

    valid_metrics = {
        'stepsCompleted': 500,
        'nanCount': 0,
        'negativeDepthCount': 0,
        'maxCfl': 0.12,
        'massBalanceError': 1e-12,
        'minimumDepthM': 0.5,
        'simulatedTimeSeconds': 10.0,
        'minimumTimeStepSeconds': 0.01,
        'maximumTimeStepSeconds': 0.02,
    }
    validate_case_thresholds(valid_metrics, 'fixture-valid')
    threshold_mutations = (
        ('failed step count', 'stepsCompleted', 499),
        ('NaN count', 'nanCount', 1),
        ('negative depth count', 'negativeDepthCount', 1),
        ('CFL threshold', 'maxCfl', 0.9500001),
        ('negative CFL', 'maxCfl', -0.01),
        ('mass-balance threshold', 'massBalanceError', 1.000001e-8),
        ('nonfinite metric', 'minimumDepthM', float('nan')),
    )
    rejected_thresholds = 0
    for _, key, value in threshold_mutations:
        candidate = dict(valid_metrics)
        candidate[key] = value
        try:
            validate_case_thresholds(candidate, 'fixture-invalid')
        except ExecutionStop:
            rejected_thresholds += 1
    require(
        rejected_thresholds == len(threshold_mutations),
        'one or more numerical STOP thresholds did not fail closed',
    )
    verified.append('case-level 500-step, NaN, negative-depth, CFL, mass-balance, and finite-value stops')

    with tempfile.TemporaryDirectory(prefix='stage18-v2-negative-') as temporary:
        fixture_base = Path(temporary)
        blocker = fixture_base / 'blocker'
        blocker.mkdir()
        (blocker / 'numpy.py').write_text(
            "from pathlib import Path\nPath('numpy-imported.marker').write_text('imported')\nraise RuntimeError('NumPy imported before authorization')\n",
            encoding='utf-8',
        )

        pending_root = make_root(fixture_base / 'pending')
        for script in (RUNNER, PREFLIGHT):
            result = run_blocked(script, pending_root, blocker)
            require(result.returncode == 2, f'pending gate exit code changed: {result.stderr}')
            require('awaiting a new explicit authorization' in result.stderr, 'pending gate reason missing')
            require('NumPy and numerical inputs were not loaded' in result.stderr, 'pre-import stop promise missing')
            require_no_outputs(pending_root)
        verified.append('pending contract and gate stop both CLIs before NumPy, numerical inputs, or outputs')

        mutated_contract = strict_json(CONTRACT_SOURCE)
        mutated_contract['run']['maxStepsPerCase'] = 499
        contract_root = make_root(fixture_base / 'mutated-contract', contract=mutated_contract)
        result = run_blocked(RUNNER, contract_root, blocker)
        require(result.returncode == 2, 'mutated 64x500 contract was not rejected')
        require('run contract changed' in result.stderr, 'mutated contract rejection reason missing')
        require_no_outputs(contract_root)
        verified.append('changed step count is rejected in the standard-library control plane')

        mutated_stop = strict_json(CONTRACT_SOURCE)
        mutated_stop['stopPolicy']['immediateStopOnNan'] = False
        stop_root = make_root(fixture_base / 'mutated-stop', contract=mutated_stop)
        result = run_blocked(RUNNER, stop_root, blocker)
        require(result.returncode == 2, 'weakened immediate STOP policy was not rejected')
        require('STOP policy changed' in result.stderr, 'STOP policy rejection reason missing')
        require_no_outputs(stop_root)
        verified.append('weakened immediate STOP policy is rejected before authorization')

        active_root = make_root(fixture_base / 'active-invalid-auth', authorization={})
        invalid_auth_path = active_root / 'config' / 'stage18_full64_run_authorization_v2.json'
        active_gate = activate_gate(pending_gate_fixture(), invalid_auth_path)
        write_json(active_root / 'config' / 'stage18_full64_execution_gate_v1.json', active_gate)
        result = run_blocked(RUNNER, active_root, blocker)
        require(result.returncode == 2, 'malformed active authorization was not rejected')
        require('authorization keys changed' in result.stderr, 'malformed authorization reason missing')
        require_no_outputs(active_root)
        verified.append('active gate with malformed authorization is rejected before NumPy')

        valid_root = make_root(fixture_base / 'active-valid-control')
        valid_git = prepare_authorized_git_root(valid_root)
        valid_environment = github_environment(valid_git['headCommit'])

        result = run_blocked(
            PREFLIGHT,
            valid_root,
            blocker,
            extra_environment=github_environment('f' * 40),
        )
        require(result.returncode == 2, 'GITHUB_SHA mismatch was not rejected')
        require('executing HEAD does not match GITHUB_SHA' in result.stderr,
                'GITHUB_SHA mismatch reason missing')
        require_no_outputs(valid_root)
        verified.append('executing HEAD must exactly equal GITHUB_SHA')

        environment_mutations = (
            ('actor', 'GITHUB_ACTOR', 'another-user', 'actor changed'),
            ('event', 'GITHUB_EVENT_NAME', 'push', 'requires workflow_dispatch'),
            ('attempt', 'GITHUB_RUN_ATTEMPT', '2', 'requires the first attempt'),
            (
                'workflow path',
                'GITHUB_WORKFLOW_REF',
                f'{FIXTURE_REPOSITORY}/.github/workflows/other.yml@refs/heads/main',
                'workflow path changed',
            ),
        )
        for label, key, value, reason in environment_mutations:
            changed_environment = dict(valid_environment)
            changed_environment[key] = value
            result = run_blocked(
                PREFLIGHT,
                valid_root,
                blocker,
                extra_environment=changed_environment,
            )
            require(result.returncode == 2, f'wrong execution {label} was not rejected')
            require(reason in result.stderr, f'wrong execution {label} reason missing')
            require_no_outputs(valid_root)
        verified.append('actor, workflow_dispatch, first attempt, and exact workflow path are mandatory')

        result = run_blocked(PREFLIGHT, valid_root, blocker, extra_environment=valid_environment)
        require(result.returncode == 3, f'valid control plane did not reach input preflight: {result.stderr}')
        require('v2 mesh constraints' in result.stderr, 'missing numerical-input rejection reason')
        require('numpy-imported.marker' not in result.stderr, 'NumPy blocker ran before JSON/digest preflight')
        require_no_outputs(valid_root)
        verified.append('reviewed ancestor plus auth/gate-only activation advances to input preflight')

        dirty_path = valid_root / 'unexpected-untracked.txt'
        dirty_path.write_text('dirty fixture\n', encoding='utf-8')
        result = run_blocked(PREFLIGHT, valid_root, blocker, extra_environment=valid_environment)
        require(result.returncode == 2, 'dirty authorized worktree was not rejected')
        require('worktree must be clean' in result.stderr, 'dirty-worktree rejection reason missing')
        dirty_path.unlink()
        require_no_outputs(valid_root)
        verified.append('authorized execution requires a clean worktree')

        invalid_ancestor_root = make_root(fixture_base / 'invalid-reviewed-ancestor')
        invalid_ancestor_git = prepare_authorized_git_root(
            invalid_ancestor_root,
            reviewed_commit_override='0' * 40,
        )
        result = run_blocked(
            PREFLIGHT,
            invalid_ancestor_root,
            blocker,
            extra_environment=github_environment(invalid_ancestor_git['headCommit']),
        )
        require(result.returncode == 2, 'non-ancestor reviewed commit was not rejected')
        require('not an ancestor' in result.stderr, 'non-ancestor rejection reason missing')
        require_no_outputs(invalid_ancestor_root)
        verified.append('reviewedCodeCommit must be an ancestor of the execution commit')

        extra_diff_root = make_root(fixture_base / 'extra-post-review-diff')
        extra_diff_git = prepare_authorized_git_root(
            extra_diff_root,
            extra_activation_file='unexpected-reviewed-change.txt',
        )
        result = run_blocked(
            PREFLIGHT,
            extra_diff_root,
            blocker,
            extra_environment=github_environment(extra_diff_git['headCommit']),
        )
        require(result.returncode == 2, 'extra post-review change was not rejected')
        require('exactly the v2 authorization and execution gate' in result.stderr,
                'post-review diff rejection reason missing')
        require_no_outputs(extra_diff_root)
        verified.append('post-review diff is limited to the authorization and gate files')

        missing_reviewed_path_root = make_root(fixture_base / 'missing-reviewed-kernel')
        missing_reviewed_path_git = prepare_authorized_git_root(
            missing_reviewed_path_root,
            omit_reviewed_file='tools/stage18_shallow_water_kernel_v2.py',
        )
        result = run_blocked(
            PREFLIGHT,
            missing_reviewed_path_root,
            blocker,
            extra_environment=github_environment(missing_reviewed_path_git['headCommit']),
        )
        require(result.returncode == 2, 'unreviewed numerical kernel was not rejected')
        require('is absent from reviewedCodeCommit' in result.stderr,
                'missing reviewed-kernel rejection reason absent')
        require_no_outputs(missing_reviewed_path_root)
        verified.append('contract, runner, kernel, workflow, and decision image must exist in reviewed base')

        escaped_image_root = make_root(fixture_base / 'escaped-decision-image')
        escaped_image_git = prepare_authorized_git_root(
            escaped_image_root,
            decision_image_relative='../outside-decision.png',
        )
        result = run_blocked(
            PREFLIGHT,
            escaped_image_root,
            blocker,
            extra_environment=github_environment(escaped_image_git['headCommit']),
        )
        require(result.returncode == 2, 'noncanonical decision image was not rejected')
        require('decision-image path changed' in result.stderr,
                'decision-image exact-path rejection reason missing')
        require_no_outputs(escaped_image_root)
        verified.append('decisionImage must use the exact reviewed repository path')

        protected_output = valid_root / 'should-not-exist-fields.npz'
        protected_output.write_bytes(b'do-not-overwrite')
        protected_digest = digest(protected_output)
        result = run_blocked(PREFLIGHT, valid_root, blocker, extra_environment=valid_environment)
        require(result.returncode == 3, 'existing output was not rejected')
        require('output already exists' in result.stderr, 'existing-output rejection reason missing')
        require(digest(protected_output) == protected_digest, 'existing output was modified')
        require(not (valid_root / 'should-not-exist-report.json').exists(), 'output collision created a report')
        require(not (valid_root / 'should-not-exist-progress.json').exists(), 'output collision created progress')
        require(not (valid_root / 'numpy-imported.marker').exists(), 'output collision imported NumPy')
        verified.append('pre-existing output is preserved and rejected before numerical input loading')

        interrupt_root = fixture_base / 'interrupt-progress'
        interrupt_root.mkdir()
        verify_interrupt_progress(interrupt_root, 'sigterm')
        verify_interrupt_progress(interrupt_root, 'keyboardinterrupt')
        require(not (interrupt_root / 'should-not-exist-fields.npz').exists(),
                'interrupt fixture created field output')
        require(not (interrupt_root / 'should-not-exist-report.json').exists(),
                'interrupt fixture created report output')
        verified.append('SIGTERM and KeyboardInterrupt both leave atomic STOP progress before any case starts')

    report = {
        'schema': 'onga-stage18-full64-v2-negative-validation-v1',
        'status': 'passed',
        'full64Executed': False,
        'numericalCasesStarted': 0,
        'verified': verified,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
