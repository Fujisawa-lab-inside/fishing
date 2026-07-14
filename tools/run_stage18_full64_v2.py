#!/usr/bin/env python3
"""Fail-closed runner for the corrected Stage 18 64-case v2 ensemble.

The control-plane preflight uses only the Python standard library.  NumPy and
all numerical inputs are touched only after the immutable execution contract,
the one-time gate, and a separately signed v2 authorization agree exactly.
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path


CONTRACT_SCHEMA = 'onga-stage18-full64-execution-contract-v2'
AUTHORIZATION_SCHEMA = 'onga-stage18-full64-run-authorization-v2'
GATE_SCHEMA = 'onga-stage18-full64-execution-gate-v1'
ENSEMBLE_SCHEMA = 'onga-stage18-inference-ensemble-v2'
CONTRACT_PATH = 'config/stage18_full64_execution_contract_v2.json'
GATE_PATH = 'config/stage18_full64_execution_gate_v1.json'
AUTHORIZATION_PATH = 'config/stage18_full64_run_authorization_v2.json'
AUTHORIZATION_SCOPE = (
    'exactly_64_corrected_geometry_v2_cases_for_runtime_and_numerical_stability_evidence'
)
AUTHORIZATION_SOURCE_STATEMENT = (
    '承認済み橋下補正v2上で、この判断資料に示された64条件×500ステップを、'
    '承認後24時間以内に一回限りの数値安定性確認として実行してよい。'
)
EXPECTED_REPOSITORY = 'Fujisawa-lab-inside/fishing'
EXPECTED_ACTOR = 'RyusukeFujisawa'
EXPECTED_REF = 'refs/heads/main'
EXPECTED_WORKFLOW = 'Stage 18 corrected v2 one-time full64 numerical run'
EXPECTED_WORKFLOW_PATH = '.github/workflows/stage18-full64-v2-run.yml'
EXPECTED_DECISION_IMAGE_PATH = 'docs/visuals/stage18-v2-execution-decision.svg'
EXPECTED_GEOMETRY = {
    'waterAuthorityVersion': 'v4.8.0-candidate-r3',
    'approvedWaterPixelCount': 680633,
    'metricMeshCellCount': 50129,
    'frozen': True,
}
EXPECTED_RUN = {
    'purpose': 'offline_runtime_and_numerical_stability_evidence_only',
    'resultsClassification': 'provisional_full64_runtime_and_numerical_stability_evidence_only',
    'caseCount': 64,
    'ensembleSeed': 20260713,
    'maxStepsPerCase': 500,
    'comparisonBasis': 'equal_step_count_not_equal_simulated_time',
    'checkpointCompletedCaseCounts': [1, 4, 16, 64],
}
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
EXPECTED_MESH_COUNTS = {
    'vertices': 28411,
    'cells': 50129,
    'internalFaces': 71848,
    'boundaryFaces': 6691,
    'barrageFaces': 67,
}
EXPECTED_MESH_ARRAY_HASHES = {
    'vertices': '8a43ab92f776809ba7216d27b7da60584937b698bb4b4f534edd8ce30e4886ec',
    'triangles': 'b0c3310a71707c8756acc176a5d5f5b0b580a7fc8edefbe1948992b2b4593100',
    'segments': '263cec21c51c01edc44f9fb84093275070ab89f73c1a54c8b61234ccb946c993',
    'segment_markers': '860b9d8f24a3159a9f552e8b980886007a9c9e7248434e149dc7752b2620b01e',
}
EXPECTED_PACKAGE_ARRAYS = {
    'vertex_local_mm': {
        'shape': [28411, 2], 'dtype': 'int32',
        'sha256': '1a86b9d8837a1529fd4fd525e335153f2a22456538803b87cff68a93a1d82a93',
    },
    'vertex_image_millipixel': {
        'shape': [28411, 2], 'dtype': 'int32',
        'sha256': '2a789541a06c663fd7c23c6ce5020c5c74d6196352f934e3d931deb7dba99319',
    },
    'triangles': {
        'shape': [50129, 3], 'dtype': 'int32',
        'sha256': 'b0c3310a71707c8756acc176a5d5f5b0b580a7fc8edefbe1948992b2b4593100',
    },
    'internal_face_vertices': {
        'shape': [71848, 2], 'dtype': 'int32',
        'sha256': 'ff9716f5468658710f98298ba6bd2b44628cabfffcd08d94d22d8f7e346505c5',
    },
    'internal_face_cells': {
        'shape': [71848, 2], 'dtype': 'int32',
        'sha256': 'c8c6a65dc8f04ff2c86b164a68e021040223f613d8fafce4a3fe0f2eb0882801',
    },
    'boundary_face_vertices': {
        'shape': [6691, 2], 'dtype': 'int32',
        'sha256': '8dd2bfea336b80671950c341728e5b25bfaab9e7e72d3e0e71272f05057434b7',
    },
    'boundary_face_cell': {
        'shape': [6691], 'dtype': 'int32',
        'sha256': '1bf0b02ef7f665adcde5fa3656e53255baa8087b077438372ac86730dc71ef4c',
    },
    'boundary_face_tag': {
        'shape': [6691], 'dtype': 'uint8',
        'sha256': '5b0d27c341c57448f5cccea5cc08afcfa4c49d8b7d27e150a72e94cc550f8f83',
    },
    'barrage_face_ids': {
        'shape': [67], 'dtype': 'int32',
        'sha256': 'c707afbc5126ae95925cb1e4428c4fd9811394cb8831b9e27337f19afac44afd',
    },
    'barrage_gate_id': {
        'shape': [67], 'dtype': 'uint8',
        'sha256': 'c8cfdfc7432ffa7d6b8e47dc2353c9950bb0a29354a5d4536a13b3378a82ecaf',
    },
    'fishway_cells': {
        'shape': [2], 'dtype': 'int32',
        'sha256': 'd6924334ca4940004ffbf91450222d1a69b416942c057c6dbebf7a12f06ab259',
    },
    'fishway_components': {
        'shape': [2], 'dtype': 'int32',
        'sha256': '7c9fa136d4413fa6173637e883b6998d32e1d675f88cddff9dcbcf331820f4b8',
    },
}
EXPECTED_PACKAGE_SHA256 = 'f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2'
EXPECTED_ENSEMBLE_SHA256 = 'ef0fc1cd8cba91ebbdcd0921260543f829c637b3c9508ea9c2dfeff5aa766684'
EXPECTED_CASES_SHA256 = 'f139f094c154e2c62c258bbe537b438b076bd47b2ae174242c968a6f7c2db317'
EXPECTED_SOURCE_PROBE = {
    'platform': 'Linux x86_64',
    'workflowRunId': 29282420163,
    'sourceCommit': 'c9b3cf11a8a0ea0f1684af6ca3ef2bb794c84046',
    'artifactName': 'stage16-ashiya-bridge-linux-probe-29282420163',
    'summarySha256': '0a874c0de615194630bd994629e1107d03f8f7ee3b504446dda5255c94aa51c8',
    'packageSha256': EXPECTED_PACKAGE_SHA256,
}
EXPECTED_VISUAL_APPROVAL = {
    'status': 'approved',
    'approvedBy': 'Ryusuke Fujisawa',
    'approvedDate': '2026-07-14',
    'sourceStatement': 'この形でよい',
    'scope': 'corrected_linux_mesh_geometry_only_no_numerical_execution_authorization',
    'reviewedMeshVersion': 'stage16-metric-fv-mesh-v2',
    'reviewedPackageSha256': EXPECTED_PACKAGE_SHA256,
    'comparisonImageSha256': '5d71c84aca13e264aa643b64161f17caa7fb36c31e0a3a987117bebe073aafda',
}
EXPECTED_PARAMETER_COVERAGE = {
    'active': [
        'bathymetry.mainstemMeanDepthM',
        'roughness.manningOpenChannel',
        'boundaries.M.phaseShiftMinutes',
        'fishway.mode',
        'fishway.effectiveDischargeCoefficient',
        'fishway.effectiveAreaM2',
        'barrage.scenario.closedVersusOpen',
    ],
    'inactive': [
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
    ],
}
EXPECTED_OUTPUTS = {
    'successRequired': [
        'execution-receipt.json',
        'onga_stage16_metric_fv_mesh_v2.npz',
        'stage16_metric_mesh_summary.json',
        'ensemble-v2.json',
        'full64-progress.json',
        'full64-report.json',
        'full64-fields.npz',
        'full64-evaluation.json',
        'full64-statistics.npz',
        'full64-statistics-summary.json',
        'full64-depth-median.png',
        'full64-velocity-median.png',
        'full64-wet-probability.png',
        'full64-direction-agreement.png',
        'full64-direction-support.png',
        'full64-judgment.svg',
        'full64-visual-manifest.json',
    ],
    'diagnosticBestEffortIfStoppedAfterAuthorization': [
        'execution-receipt.json', 'full64-progress.json', 'full64-diagnostic-stop.svg',
    ],
    'partialFieldArtifactAllowed': False,
    'successArtifactPrefix': 'stage18-full64-v2-results-',
    'diagnosticArtifactPrefix': 'stage18-full64-v2-diagnostics-',
}
EXPECTED_CLAIM_LIMITS = {
    'physicalValidationClaimAllowed': False,
    'sensitivityClaimAllowed': False,
    'inferredParametersMayBeCalledObservations': False,
    'publicSimulatorConnectionAllowed': False,
    'commonPhysicalTimeComparisonAllowed': False,
    'absoluteWaterSurfaceElevationClaimAllowed': False,
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
EXPECTED_REVIEWED_CODE_PATHS = [
    CONTRACT_PATH,
    'tools/run_stage18_full64_v2.py',
    'tools/stage18_shallow_water_kernel_v2.py',
    EXPECTED_WORKFLOW_PATH,
]
EXPECTED_PREVIOUS_ATTEMPT = None
EXPECTED_MAP_RASTER = None
EXPECTED_CONTRACT_KEYS = {
    'schema', 'status', 'executionAuthorized', 'authorization', 'authorizationContract',
    'geometry', 'meshExpected', 'ensembleExpected', 'run', 'acceptance', 'safeguards',
    'protectedPaths', 'parameterCoverage', 'outputs', 'stopPolicy', 'claimLimits',
    'visualDecision',
}
EXPECTED_AUTHORIZATION_KEYS = {
    'schema', 'authorizationId', 'authorized', 'oneTime', 'approvedBy',
    'approvedDate', 'issuedAtUtc', 'notAfterUtc', 'sourceStatement', 'scope', 'decisionImage',
    'executionContract', 'reviewedCodeCommit', 'geometry', 'meshExpected',
    'ensembleExpected', 'run', 'acceptance', 'safeguards',
}
EXPECTED_FALSE_AUTHORIZATION_SAFEGUARDS = {
    'automaticAdditionalRunsAllowed': False,
    'automaticRetryAllowed': False,
    'inferredParametersAreObservations': False,
    'physicalValidationClaimAllowed': False,
    'sensitivityClaimAllowed': False,
    'publicSimulatorConnectionAllowed': False,
    'legacyFlowCalculationMayChange': False,
    'failedCasesMayBeImputed': False,
}


class PreflightError(RuntimeError):
    pass


class ExecutionNotAuthorized(PreflightError):
    pass


class ExecutionStop(RuntimeError):
    pass


def require(condition, message, error_type=PreflightError):
    if not condition:
        raise error_type(message)


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require_file_digest(path, expected, label):
    try:
        actual = sha256_file(path)
    except OSError as error:
        raise PreflightError(f'{label} cannot be read: {error}') from error
    require(actual == expected, f'{label} digest mismatch')


def array_sha256(values):
    return hashlib.sha256(values.tobytes(order='C')).hexdigest()


def resolve_path(repo_root, raw_path):
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (Path(repo_root) / path).resolve()


def resolve_repo_relative_path(repo_root, raw_path, label):
    require(isinstance(raw_path, str) and len(raw_path.strip()) > 0, f'{label} path is required')
    candidate = Path(raw_path)
    require(not candidate.is_absolute(), f'{label} must be repo-relative')
    root = Path(repo_root).resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PreflightError(f'{label} escapes the repository root') from error
    return resolved


def run_git(repo_root, arguments, label, *, expect_success=True):
    environment = os.environ.copy()
    environment.update({'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0', 'LC_ALL': 'C'})
    result = subprocess.run(
        ['git', '-C', str(Path(repo_root).resolve()), *arguments],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    if expect_success:
        require(result.returncode == 0, f'{label} failed: {result.stderr.strip()}')
    return result


def _reviewed_workflow_path():
    repository = os.environ.get('GITHUB_REPOSITORY')
    workflow_ref = os.environ.get('GITHUB_WORKFLOW_REF')
    require(
        repository == EXPECTED_REPOSITORY,
        'authorized v2 run requires the reviewed repository',
    )
    prefix = f'{repository}/'
    require(
        isinstance(workflow_ref, str) and workflow_ref.startswith(prefix),
        'GITHUB_WORKFLOW_REF does not match GITHUB_REPOSITORY',
    )
    workflow_and_ref = workflow_ref[len(prefix):]
    workflow_path, separator, workflow_revision = workflow_and_ref.rpartition('@')
    require(separator == '@' and workflow_revision, 'GITHUB_WORKFLOW_REF is malformed')
    require(
        re.fullmatch(r'\.github/workflows/[A-Za-z0-9._/-]+\.ya?ml', workflow_path) is not None,
        'GITHUB_WORKFLOW_REF does not identify a workflow YAML file',
    )
    require(workflow_path == EXPECTED_WORKFLOW_PATH, 'authorized v2 workflow path changed')
    require(workflow_revision == EXPECTED_REF, 'authorized v2 workflow revision must be main')
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'authorized v2 run requires GitHub Actions')
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'authorized v2 run requires workflow_dispatch')
    require(os.environ.get('GITHUB_ACTOR') == EXPECTED_ACTOR, 'authorized v2 actor changed')
    require(os.environ.get('GITHUB_REF') == EXPECTED_REF, 'authorized v2 ref must be main')
    require(os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'authorized v2 run requires the first attempt')
    require(os.environ.get('GITHUB_WORKFLOW') == EXPECTED_WORKFLOW, 'authorized v2 workflow name changed')
    run_id = os.environ.get('GITHUB_RUN_ID')
    require(isinstance(run_id, str) and run_id.isdigit(), 'authorized v2 workflow run ID is invalid')
    return EXPECTED_WORKFLOW_PATH


def validate_reviewed_code_commit(repo_root, reviewed_commit, decision_image_path=None):
    reviewed_workflow_path = _reviewed_workflow_path()
    require(
        reviewed_workflow_path in EXPECTED_REVIEWED_CODE_PATHS,
        'reviewed workflow is missing from the fixed reviewed-code paths',
    )
    require(
        re.fullmatch(r'[a-f0-9]{40}', reviewed_commit or '') is not None,
        'reviewedCodeCommit must be a full lowercase Git commit',
    )
    head = run_git(repo_root, ['rev-parse', '--verify', 'HEAD'], 'resolve executing HEAD').stdout.strip()
    require(re.fullmatch(r'[a-f0-9]{40}', head) is not None, 'executing HEAD is not a full Git commit')
    github_sha = os.environ.get('GITHUB_SHA')
    require(
        isinstance(github_sha, str)
        and re.fullmatch(r'[a-f0-9]{40}', github_sha) is not None,
        'GITHUB_SHA is required for an authorized v2 run',
    )
    require(head == github_sha, 'executing HEAD does not match GITHUB_SHA')
    ancestor = run_git(
        repo_root,
        ['merge-base', '--is-ancestor', reviewed_commit, head],
        'verify reviewed code ancestry',
        expect_success=False,
    )
    require(ancestor.returncode == 0, 'reviewedCodeCommit is not an ancestor of executing HEAD')
    changed = run_git(
        repo_root,
        ['diff', '--name-only', f'{reviewed_commit}..{head}'],
        'inspect post-review changes',
    ).stdout.splitlines()
    expected_changes = [GATE_PATH, AUTHORIZATION_PATH]
    require(
        sorted(changed) == expected_changes,
        'post-review changes must be exactly the v2 authorization and execution gate',
    )
    reviewed_paths = list(EXPECTED_REVIEWED_CODE_PATHS)
    if decision_image_path is not None:
        resolved_decision = resolve_repo_relative_path(
            repo_root,
            decision_image_path,
            'authorization decision image',
        )
        reviewed_paths.append(
            resolved_decision.relative_to(Path(repo_root).resolve()).as_posix()
        )
    for reviewed_path in reviewed_paths:
        tree = run_git(
            repo_root,
            ['ls-tree', '-z', reviewed_commit, '--', reviewed_path],
            f'inspect reviewed path {reviewed_path}',
        ).stdout
        entries = [entry for entry in tree.split('\0') if entry]
        require(len(entries) == 1, f'{reviewed_path} is absent from reviewedCodeCommit')
        metadata, separator, tree_path = entries[0].partition('\t')
        metadata_parts = metadata.split()
        require(
            separator == '\t'
            and tree_path == reviewed_path
            and len(metadata_parts) == 3
            and metadata_parts[0] in {'100644', '100755'}
            and metadata_parts[1] == 'blob',
            f'{reviewed_path} is not a regular reviewed file',
        )
        working_path = Path(repo_root).resolve() / reviewed_path
        require(
            working_path.is_file() and not working_path.is_symlink(),
            f'{reviewed_path} is not a regular working-tree file',
        )
        working_blob = run_git(
            repo_root,
            ['hash-object', '--no-filters', '--', reviewed_path],
            f'hash working path {reviewed_path}',
        ).stdout.strip()
        require(
            working_blob == metadata_parts[2],
            f'{reviewed_path} differs from reviewedCodeCommit',
        )
    status = run_git(
        repo_root,
        ['status', '--porcelain=v1', '--untracked-files=all'],
        'inspect authorized worktree',
    ).stdout
    require(status == '', 'authorized v2 worktree must be clean')
    return head


def load_json_strict(path, label):
    try:
        payload = Path(path).read_bytes()
    except OSError as error:
        raise PreflightError(f'{label} cannot be read: {error}') from error

    def reject_constant(value):
        raise ValueError(f'nonstandard JSON constant: {value}')

    try:
        value = json.loads(payload, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PreflightError(f'{label} is not strict JSON: {error}') from error
    require(isinstance(value, dict), f'{label} must be a JSON object')
    return value, sha256_bytes(payload)


def validate_immutable_contract(contract):
    require(set(contract) == EXPECTED_CONTRACT_KEYS, 'v2 execution contract keys changed')
    require(contract.get('schema') == CONTRACT_SCHEMA, 'unsupported v2 execution contract schema')
    require(
        contract.get('status') == 'awaiting_explicit_authorization',
        'immutable v2 contract status changed',
    )
    require(contract.get('executionAuthorized') is False, 'immutable contract must not self-authorize')
    require(contract.get('authorization') is None, 'immutable contract must not embed authorization')
    require(contract.get('geometry') == EXPECTED_GEOMETRY, 'corrected v2 geometry contract changed')
    require(contract.get('run') == EXPECTED_RUN, 'v2 64x500 run contract changed')
    require(contract.get('acceptance') == EXPECTED_ACCEPTANCE, 'v2 acceptance thresholds changed')
    require(contract.get('stopPolicy') == EXPECTED_STOP_POLICY, 'v2 immediate STOP policy changed')
    require(contract.get('protectedPaths') == EXPECTED_PROTECTED_PATHS, 'protected path contract changed')

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
    }, 'v2 authorization contract changed')

    mesh = contract.get('meshExpected', {})
    require(mesh.get('version') == 'stage16-metric-fv-mesh-v2', 'v2 mesh version changed')
    require(mesh.get('candidateStatus') == 'approved_canonical', 'v2 mesh is not approved canonical')
    require(mesh.get('artifactFile') == 'onga_stage16_metric_fv_mesh_v2.npz', 'v2 mesh filename changed')
    require(mesh.get('constraints') == {
        'path': 'data/onga_stage16_mesh_constraints_v2.json',
        'sha256': '44c629ba6b7eb7bf0c43a1863de0c4835d8d331c0d230e50d891a0b23043fb33',
    }, 'v2 mesh constraints identity changed')
    require(mesh.get('waterAuthority') == {
        'version': 'v4.8.0-candidate-r3',
        'pixelCount': 680633,
        'manifest': 'data/onga_unified_water_manifest_r3.json',
        'manifestSha256': '964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7',
    }, 'v2 water authority identity changed')
    require(mesh.get('counts') == EXPECTED_MESH_COUNTS, 'v2 mesh counts changed')
    require(mesh.get('meshArrayHashes') == EXPECTED_MESH_ARRAY_HASHES, 'v2 mesh source hashes changed')
    require(mesh.get('packageArrays') == EXPECTED_PACKAGE_ARRAYS, 'v2 mesh package arrays changed')
    require(mesh.get('packageSha256') == EXPECTED_PACKAGE_SHA256, 'v2 mesh package identity changed')
    require(
        mesh.get('sourceProbe') == EXPECTED_SOURCE_PROBE,
        'v2 source probe identity changed',
    )
    require(
        mesh.get('visualApproval') == EXPECTED_VISUAL_APPROVAL,
        'v2 visual approval identity changed',
    )

    ensemble = contract.get('ensembleExpected', {})
    require(ensemble.get('schema') == ENSEMBLE_SCHEMA, 'v2 ensemble schema changed')
    require(ensemble.get('seed') == 20260713, 'v2 ensemble seed changed')
    require(ensemble.get('caseCount') == 64, 'v2 ensemble must contain 64 cases')
    require(ensemble.get('geometry') == EXPECTED_GEOMETRY, 'v2 ensemble geometry binding changed')
    require(ensemble.get('sha256') == EXPECTED_ENSEMBLE_SHA256, 'v2 ensemble identity changed')
    require(
        ensemble.get('parameterCaseInheritance', {}).get('casesSha256') == EXPECTED_CASES_SHA256,
        'v2 inherited case identity changed',
    )
    require(ensemble.get('sourcePrior') == {
        'path': 'config/stage17_inferred_physical_prior_v1.json',
        'sha256': 'bc801566ff93f6d73ed01926fa9da195faf91d55dc5bd122905d0d5dd5e40a84',
    }, 'v2 source-prior identity changed')
    require(ensemble.get('parameterCaseInheritance') == {
        'sourceEnsembleSchema': 'onga-stage18-inference-ensemble-v1',
        'sourceEnsembleSerializedSha256': '0a926fa20d6260a6cdb113b2a7d5be6807ca87f33350ce82be32ef9e13023ef2',
        'casesSha256': EXPECTED_CASES_SHA256,
        'policy': 'parameter_cases_identical_geometry_rebound_only',
    }, 'v2 parameter-case inheritance changed')
    require(
        ensemble.get('samplingMethod') == 'deterministic_stratified_marginals_with_categorical_rotation'
        and ensemble.get('governingEquation') == 'depth_averaged_shallow_water'
        and ensemble.get('serialization') == 'JSON.stringify(value,null,2)+LF',
        'v2 ensemble method contract changed',
    )
    require(contract.get('parameterCoverage') == EXPECTED_PARAMETER_COVERAGE, 'parameter coverage changed')
    require(contract.get('outputs') == EXPECTED_OUTPUTS, 'v2 output contract changed')
    require(contract.get('claimLimits') == EXPECTED_CLAIM_LIMITS, 'v2 claim limits changed')
    if EXPECTED_PREVIOUS_ATTEMPT is not None:
        require(contract.get('previousAttempt') == EXPECTED_PREVIOUS_ATTEMPT,
                'previous-attempt evidence changed')
    if EXPECTED_MAP_RASTER is not None:
        require(contract.get('mapRaster') == EXPECTED_MAP_RASTER,
                'map-raster recovery contract changed')

    safeguards = contract.get('safeguards', {})
    for key in (
        'geometryApprovalIsExecutionAuthorization', 'physicalExecutionAuthorized',
        'full64ExecutionAllowed', 'automaticActivationAllowed',
        'automaticAdditionalRunsAllowed', 'automaticRetryAllowed',
        'previousV1AuthorizationReusable', 'inferredParametersAreObservations',
        'physicalValidationClaimAllowed', 'sensitivityClaimAllowed',
        'publicSimulatorConnectionAllowed', 'publicRuntimeEnabled',
        'legacyFlowCalculationMayChange', 'failedCasesMayBeImputed',
    ):
        require(safeguards.get(key) is False, f'contract safeguard {key} must remain false')
    visual = contract.get('visualDecision', {})
    require(visual == {
        'geometryDecisionRecorded': True,
        'geometrySourceStatement': 'この形でよい',
        'geometryDecisionScope': 'corrected_linux_mesh_geometry_only_no_numerical_execution_authorization',
        'executionDecisionRequired': True,
        'executionDecisionRecorded': False,
        'executionDecisionImageRequired': True,
        'executionDecisionImageSha256': None,
    }, 'v2 visual-decision contract changed')
    return True


def validate_pending_gate(gate):
    require(gate.get('schema') == GATE_SCHEMA, 'unsupported execution gate schema')
    pending = (
        gate.get('state') == 'awaiting_new_explicit_authorization'
        and gate.get('enabled') is False
        and gate.get('replacementAuthorizationRequired') is True
        and gate.get('activeAuthorization') is None
        and gate.get('safeguards', {}).get('consumeOneTimeAuthorizationAllowed') is False
        and gate.get('safeguards', {}).get('full64ExecutionAllowed') is False
        and gate.get('safeguards', {}).get('automaticActivationAllowed') is False
    )
    return pending


def validate_active_gate(gate):
    require(gate.get('schema') == GATE_SCHEMA, 'unsupported execution gate schema')
    require(gate.get('state') == 'authorized', 'execution gate is not authorized', ExecutionNotAuthorized)
    require(gate.get('enabled') is True, 'execution gate is disabled', ExecutionNotAuthorized)
    require(
        gate.get('replacementAuthorizationRequired') is False,
        'replacement authorization is still required',
        ExecutionNotAuthorized,
    )
    active = gate.get('activeAuthorization')
    require(isinstance(active, dict), 'active authorization record is missing', ExecutionNotAuthorized)
    require(set(active) == {'id', 'path', 'sha256'}, 'active authorization keys changed')
    require(
        re.fullmatch(r'[a-z0-9][a-z0-9._-]{7,127}', active.get('id', '')) is not None,
        'active authorization ID is invalid',
    )
    require(active.get('path') == AUTHORIZATION_PATH, 'active authorization path changed')
    require(re.fullmatch(r'[a-f0-9]{64}', active.get('sha256', '')) is not None, 'authorization SHA-256 required')
    safeguards = gate.get('safeguards', {})
    require(safeguards.get('consumeOneTimeAuthorizationAllowed') is True, 'one-time authorization is not consumable')
    require(safeguards.get('full64ExecutionAllowed') is True, 'full64 execution is forbidden')
    require(safeguards.get('automaticActivationAllowed') is False, 'automatic gate activation is forbidden')
    return active


def validate_authorization_validity_window(authorization, *, now=None, enforce_current_time=True):
    pattern = r'20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
    issued_text = authorization.get('issuedAtUtc')
    not_after_text = authorization.get('notAfterUtc')
    require(
        isinstance(issued_text, str) and re.fullmatch(pattern, issued_text) is not None,
        'v2 authorization issuedAtUtc must be an exact UTC timestamp',
    )
    require(
        isinstance(not_after_text, str) and re.fullmatch(pattern, not_after_text) is not None,
        'v2 authorization notAfterUtc must be an exact UTC timestamp',
    )
    try:
        issued = dt.datetime.strptime(issued_text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
        not_after = dt.datetime.strptime(not_after_text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
    except ValueError as error:
        raise PreflightError(f'v2 authorization validity timestamp is invalid: {error}') from error
    validity_seconds = (not_after - issued).total_seconds()
    require(validity_seconds > 0, 'v2 authorization validity window must be positive')
    require(validity_seconds <= 86400, 'v2 authorization validity window exceeds 24 hours')
    if enforce_current_time:
        current = dt.datetime.now(dt.timezone.utc) if now is None else now
        require(
            isinstance(current, dt.datetime) and current.tzinfo is not None,
            'current authorization-validation time must be timezone-aware',
        )
        current = current.astimezone(dt.timezone.utc)
        require(current >= issued, 'v2 authorization is not valid yet', ExecutionNotAuthorized)
        require(current <= not_after, 'v2 authorization has expired', ExecutionNotAuthorized)
    return issued, not_after


def validate_authorization(authorization, authorization_digest, active, contract, contract_path, contract_digest):
    require(authorization_digest == active['sha256'], 'active authorization digest mismatch')
    require(set(authorization) == EXPECTED_AUTHORIZATION_KEYS, 'v2 authorization keys changed')
    require(authorization.get('schema') == AUTHORIZATION_SCHEMA, 'v2 authorization schema required')
    require(authorization.get('authorized') is True, 'v2 authorization is not explicit', ExecutionNotAuthorized)
    require(authorization.get('oneTime') is True, 'v2 authorization must be one-time')
    require(authorization.get('authorizationId') == active['id'], 'authorization ID differs from active gate')
    require(authorization.get('approvedBy') == 'Ryusuke Fujisawa', 'v2 authorization approver changed')
    require(
        re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}', authorization.get('approvedDate', '')) is not None,
        'v2 authorization date is required',
    )
    validate_authorization_validity_window(authorization)
    require(
        authorization.get('sourceStatement') == AUTHORIZATION_SOURCE_STATEMENT,
        'v2 authorization source statement does not match the visual execution decision',
    )
    require(authorization.get('scope') == AUTHORIZATION_SCOPE, 'v2 authorization scope changed')
    require(
        re.fullmatch(r'[a-f0-9]{40}', authorization.get('reviewedCodeCommit', '')) is not None,
        'v2 authorization reviewedCodeCommit must be a full lowercase Git commit',
    )
    decision_image = authorization.get('decisionImage')
    require(isinstance(decision_image, dict), 'authorization decision image is required')
    require(set(decision_image) == {'path', 'sha256'}, 'authorization decision-image keys changed')
    require(
        decision_image.get('path') == EXPECTED_DECISION_IMAGE_PATH,
        'authorization decision-image path changed',
    )
    require(
        re.fullmatch(r'[a-f0-9]{64}', decision_image.get('sha256', '')) is not None,
        'authorization decision-image digest is required',
    )
    binding = authorization.get('executionContract')
    require(isinstance(binding, dict), 'authorization execution-contract binding is missing')
    require(binding.get('path') == CONTRACT_PATH, 'authorization contract path changed')
    require(binding.get('sha256') == contract_digest, 'authorization contract digest mismatch')
    require(resolve_path(Path(contract_path).parents[1], binding['path']) == Path(contract_path).resolve(), 'authorization contract path does not resolve to the inspected contract')
    require(authorization.get('geometry') == contract['geometry'], 'authorization geometry changed')
    require(authorization.get('meshExpected') == contract['meshExpected'], 'authorization mesh identity changed')
    require(authorization.get('ensembleExpected') == contract['ensembleExpected'], 'authorization ensemble changed')
    require(authorization.get('run') == EXPECTED_RUN, 'authorization run contract changed')
    require(authorization.get('acceptance') == EXPECTED_ACCEPTANCE, 'authorization thresholds changed')
    require(
        authorization.get('safeguards') == EXPECTED_FALSE_AUTHORIZATION_SAFEGUARDS,
        'authorization safeguards changed',
    )
    return True


def control_plane_preflight(args):
    repo_root = Path(args.repo_root).resolve()
    contract_path = resolve_path(repo_root, args.execution_contract)
    require(
        contract_path == resolve_path(repo_root, CONTRACT_PATH),
        'CLI execution contract must use the reviewed v2 contract path',
    )
    contract, contract_digest = load_json_strict(contract_path, 'v2 execution contract')
    validate_immutable_contract(contract)

    gate_path = resolve_path(repo_root, args.execution_gate)
    require(
        gate_path == resolve_path(repo_root, GATE_PATH),
        'CLI execution gate must use the repository v2 gate path',
    )
    gate, _ = load_json_strict(gate_path, 'v2 execution gate')
    if validate_pending_gate(gate):
        raise ExecutionNotAuthorized(
            'v2 execution gate is awaiting a new explicit authorization; no numerical cases were started'
        )
    active = validate_active_gate(gate)

    authorization_path = resolve_path(repo_root, args.authorization)
    require(
        authorization_path == resolve_path(repo_root, active['path']),
        'CLI authorization does not match the active gate',
    )
    authorization, authorization_digest = load_json_strict(authorization_path, 'v2 authorization')
    validate_authorization(
        authorization,
        authorization_digest,
        active,
        contract,
        contract_path,
        contract_digest,
    )
    decision_image = authorization['decisionImage']
    decision_image_path = resolve_repo_relative_path(
        repo_root,
        decision_image['path'],
        'authorization decision image',
    )
    require_file_digest(
        decision_image_path,
        decision_image['sha256'],
        'authorization decision image',
    )
    repository_head = validate_reviewed_code_commit(
        repo_root,
        authorization['reviewedCodeCommit'],
        decision_image['path'],
    )
    return {
        'repoRoot': repo_root,
        'contractPath': contract_path,
        'contract': contract,
        'contractSha256': contract_digest,
        'gatePath': gate_path,
        'gate': gate,
        'authorizationPath': authorization_path,
        'authorization': authorization,
        'authorizationSha256': authorization_digest,
        'decisionImagePath': decision_image_path,
        'codeCommit': repository_head,
    }


def validate_output_paths(inputs, outputs, protected_paths, repo_root):
    resolved_inputs = {Path(path).resolve() for path in inputs}
    resolved_protected = {resolve_path(repo_root, path) for path in protected_paths}
    resolved_outputs = [Path(path).resolve() for path in outputs]
    require(len(set(resolved_outputs)) == len(resolved_outputs), 'v2 output paths must be distinct')
    for raw, resolved in zip(outputs, resolved_outputs):
        require(resolved not in resolved_inputs, f'v2 output overlaps an input: {raw}')
        require(resolved not in resolved_protected, f'v2 output overlaps a protected surface: {raw}')
        require(not Path(raw).exists(), f'v2 output already exists: {raw}')


def validate_mesh_summary(summary, contract):
    mesh = contract['meshExpected']
    require(summary.get('schema') == 'onga-stage16-metric-mesh-summary-v2', 'unsupported mesh summary')
    require(summary.get('version') == mesh['version'], 'mesh summary version mismatch')
    require(summary.get('candidateStatus') == 'approved_canonical', 'mesh summary is not approved canonical')
    require(summary.get('status') == 'passed', 'mesh summary did not pass')
    require(summary.get('identityPinned') is True, 'mesh summary identity is not pinned')
    require(summary.get('approvedIdentityReproduced') is True, 'approved mesh identity was not reproduced')
    require(summary.get('canonical') is True, 'mesh summary is not canonical')
    require(summary.get('artifactFile') == mesh['artifactFile'], 'mesh artifact filename mismatch')
    require(summary.get('artifactSha256') == mesh['packageSha256'], 'mesh artifact digest mismatch')
    counts = summary.get('counts', {})
    require(
        {key: counts.get(key) for key in EXPECTED_MESH_COUNTS} == EXPECTED_MESH_COUNTS,
        'mesh summary counts mismatch',
    )
    require(summary.get('meshArrayHashes') == EXPECTED_MESH_ARRAY_HASHES, 'mesh summary source hashes mismatch')
    require(
        summary.get('packageArrayHashes')
        == {name: item['sha256'] for name, item in EXPECTED_PACKAGE_ARRAYS.items()},
        'mesh summary package hashes mismatch',
    )
    require(
        summary.get('platform', {}).get('system') == 'Linux'
        and summary.get('platform', {}).get('machine') == 'x86_64',
        'canonical mesh summary must come from Linux x86_64',
    )
    require(summary.get('inputs') == {
        'waterManifest': contract['meshExpected']['waterAuthority']['manifest'],
        'waterAuthorityVersion': 'v4.8.0-candidate-r3',
        'waterPixelCount': 680633,
        'constraints': contract['meshExpected']['constraints']['path'],
    }, 'mesh summary input identity mismatch')
    require(summary.get('visualApproval') == mesh.get('visualApproval'), 'mesh visual approval mismatch')
    require(summary.get('safeguards') == {
        'waterAuthorityModifiedDuringGeneration': False,
        'physicalValuesAssigned': False,
        'physicalExecutionAuthorized': False,
        'connectedToPublicSimulator': False,
        'calibrationPerformed': False,
        'previousMeshAuthorizationReusable': False,
    }, 'mesh summary safeguards changed')
def validate_ensemble(ensemble, ensemble_digest, contract):
    expected = contract['ensembleExpected']
    require(ensemble_digest == expected['sha256'], 'v2 ensemble file digest mismatch')
    require(ensemble.get('schema') == ENSEMBLE_SCHEMA, 'unsupported v2 ensemble schema')
    require(ensemble.get('generatedFrom') == expected['generatedFrom'], 'v2 ensemble source changed')
    require(ensemble.get('seed') == 20260713, 'v2 ensemble seed changed')
    require(ensemble.get('count') == 64, 'v2 ensemble count must be 64')
    require(ensemble.get('geometry') == EXPECTED_GEOMETRY, 'v2 ensemble geometry mismatch')
    require(ensemble.get('sourcePrior') == expected['sourcePrior'], 'v2 ensemble source-prior binding changed')
    require(
        ensemble.get('parameterCaseInheritance') == expected['parameterCaseInheritance'],
        'v2 ensemble parameter-case inheritance changed',
    )
    require(
        ensemble.get('samplingMethod') == 'deterministic_stratified_marginals_with_categorical_rotation',
        'v2 ensemble sampling method changed',
    )
    require(ensemble.get('governingEquation') == 'depth_averaged_shallow_water', 'governing equation changed')
    cases = ensemble.get('cases')
    require(isinstance(cases, list) and len(cases) == 64, 'exactly 64 v2 cases are required')
    expected_ids = [f'stage18-{index:04d}' for index in range(1, 65)]
    require([case.get('caseId') for case in cases] == expected_ids, 'v2 case IDs or order changed')
    require(
        all(case.get('classification') == 'provisional_inference_case_not_observation' for case in cases),
        'a v2 case classification changed',
    )
    return cases


def validate_mesh_package(mesh_path, contract):
    require(sha256_file(mesh_path) == contract['meshExpected']['packageSha256'], 'v2 mesh package SHA-256 mismatch')
    import numpy as np

    package = np.load(mesh_path, allow_pickle=False)
    require(package.files == list(EXPECTED_PACKAGE_ARRAYS), 'v2 mesh package array order changed')
    for name, definition in EXPECTED_PACKAGE_ARRAYS.items():
        values = package[name]
        require(list(values.shape) == definition['shape'], f'{name} shape mismatch')
        require(str(values.dtype) == definition['dtype'], f'{name} dtype mismatch')
        require(array_sha256(values) == definition['sha256'], f'{name} array digest mismatch')
    return package


def data_plane_preflight(args, control):
    contract = control['contract']
    repo_root = control['repoRoot']
    mesh_path = resolve_path(repo_root, args.mesh)
    summary_path = resolve_path(repo_root, args.mesh_summary)
    ensemble_path = resolve_path(repo_root, args.ensemble)
    fields_path = resolve_path(repo_root, args.fields_output)
    report_path = resolve_path(repo_root, args.report_output)
    progress_path = resolve_path(repo_root, args.progress_output)
    source_definitions = (
        (contract['meshExpected']['constraints'], 'v2 mesh constraints', 'path', 'sha256'),
        (
            contract['meshExpected']['waterAuthority'],
            'v2 water authority manifest',
            'manifest',
            'manifestSha256',
        ),
        (contract['ensembleExpected']['sourcePrior'], 'v2 source prior', 'path', 'sha256'),
    )
    source_paths = [
        resolve_path(repo_root, definition[path_key])
        for definition, _, path_key, _ in source_definitions
    ]
    input_paths = [
        control['contractPath'], control['gatePath'], control['authorizationPath'],
        control['decisionImagePath'], mesh_path, summary_path, ensemble_path, *source_paths,
    ]
    output_paths = [fields_path, report_path, progress_path]
    validate_output_paths(input_paths, output_paths, contract['protectedPaths'], repo_root)

    for definition, label, path_key, digest_key in source_definitions:
        source_path = resolve_path(repo_root, definition[path_key])
        require_file_digest(
            source_path,
            definition[digest_key],
            label,
        )

    summary, summary_digest = load_json_strict(summary_path, 'v2 mesh summary')
    validate_mesh_summary(summary, contract)
    ensemble, ensemble_digest = load_json_strict(ensemble_path, 'v2 ensemble')
    cases = validate_ensemble(ensemble, ensemble_digest, contract)
    package = validate_mesh_package(mesh_path, contract)
    return {
        **control,
        'meshPath': mesh_path,
        'meshSha256': sha256_file(mesh_path),
        'meshSummaryPath': summary_path,
        'meshSummary': summary,
        'meshSummarySha256': summary_digest,
        'ensemblePath': ensemble_path,
        'ensemble': ensemble,
        'ensembleSha256': ensemble_digest,
        'cases': cases,
        'package': package,
        'fieldsPath': fields_path,
        'reportPath': report_path,
        'progressPath': progress_path,
    }


def peak_rss_mib():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == 'darwin' else rss / 1024


def _remove_owned_publication(destination, temporary, published):
    owned = published
    if not owned and destination.exists() and temporary.exists():
        try:
            owned = os.path.samefile(destination, temporary)
        except OSError:
            owned = False
    if owned:
        destination.unlink(missing_ok=True)
    return owned


def write_json_atomic(path, payload, *, replace_existing=False, publication_state=None):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f'.{destination.name}.{os.getpid()}.{time.time_ns()}.tmp'
    )
    require(not temporary.exists(), f'temporary output already exists: {temporary}', ExecutionStop)
    published = False
    try:
        temporary.write_text(
            f'{json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)}\n',
            encoding='utf-8',
        )
        if replace_existing:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
            published = True
            if publication_state is not None:
                publication_state['published'] = True
            temporary.unlink()
    except BaseException:
        removed = _remove_owned_publication(destination, temporary, published)
        temporary.unlink(missing_ok=True)
        if removed and publication_state is not None:
            publication_state['published'] = False
        raise


def save_npz_atomic(path, *, publication_state=None, **arrays):
    import numpy as np

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f'.{destination.name}.{os.getpid()}.{time.time_ns()}.tmp'
    )
    require(not temporary.exists(), f'temporary output already exists: {temporary}', ExecutionStop)
    published = False
    try:
        with temporary.open('xb') as handle:
            np.savez_compressed(handle, **arrays)
        os.link(temporary, destination)
        published = True
        if publication_state is not None:
            publication_state['published'] = True
        temporary.unlink()
    except BaseException:
        removed = _remove_owned_publication(destination, temporary, published)
        temporary.unlink(missing_ok=True)
        if removed and publication_state is not None:
            publication_state['published'] = False
        raise


def protected_hashes(repo_root, protected_paths):
    return {path: sha256_file(resolve_path(repo_root, path)) for path in protected_paths}


def progress_payload(context, started, diagnostics, attempted_ids, status, stop=None):
    completed = sum(item.get('status') == 'completed' for item in diagnostics)
    payload = {
        'schema': 'onga-stage18-full64-progress-v2',
        'classification': 'provisional_full64_runtime_and_numerical_stability_evidence_only',
        'status': status,
        'geometry': EXPECTED_GEOMETRY,
        'ensembleSeed': 20260713,
        'requestedCaseCount': 64,
        'attemptedCaseIds': attempted_ids,
        'completedCaseCount': completed,
        'failedCaseCount': sum(item.get('status') == 'failed' for item in diagnostics),
        'wallSeconds': time.perf_counter() - started,
        'peakResidentMemoryMiB': peak_rss_mib(),
        'caseDiagnostics': diagnostics,
        'comparisonBasis': EXPECTED_RUN['comparisonBasis'],
        'inputDigests': {
            'executionContractSha256': context['contractSha256'],
            'authorizationSha256': context['authorizationSha256'],
            'meshSha256': context['meshSha256'],
            'meshSummarySha256': context['meshSummarySha256'],
            'ensembleSha256': context['ensembleSha256'],
        },
    }
    if stop is not None:
        payload['stop'] = stop
    return payload


def validate_case_thresholds(result, case_id):
    require(isinstance(result, dict), f'{case_id} result must be an object', ExecutionStop)
    require(result.get('stepsCompleted') == 500, f'{case_id} did not complete exactly 500 steps', ExecutionStop)
    require(result.get('nanCount') == 0, f'{case_id} returned NaN state', ExecutionStop)
    require(result.get('negativeDepthCount') == 0, f'{case_id} returned negative depth', ExecutionStop)
    for key in (
        'maxCfl', 'massBalanceError', 'minimumDepthM', 'simulatedTimeSeconds',
        'minimumTimeStepSeconds', 'maximumTimeStepSeconds',
    ):
        value = result.get(key)
        require(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value),
            f'{case_id} {key} must be finite',
            ExecutionStop,
        )
    require(0 <= result['maxCfl'] <= 0.95, f'{case_id} CFL is negative or exceeds threshold', ExecutionStop)
    require(
        abs(result['massBalanceError']) <= 1e-8,
        f'{case_id} mass balance threshold exceeded',
        ExecutionStop,
    )
    require(result['minimumDepthM'] >= 0, f'{case_id} minimum depth is negative', ExecutionStop)
    require(result['simulatedTimeSeconds'] > 0, f'{case_id} simulated time is not positive', ExecutionStop)
    require(result['minimumTimeStepSeconds'] > 0, f'{case_id} minimum time step is not positive', ExecutionStop)
    require(
        result['maximumTimeStepSeconds'] >= result['minimumTimeStepSeconds'],
        f'{case_id} time-step range is invalid',
        ExecutionStop,
    )


def _execute_cases_impl(args, context, started, diagnostics, attempted_ids, progress_state):
    import numpy as np
    from stage18_shallow_water_kernel_v2 import NumericalStop, build_geometry, run_case

    geometry = build_geometry(context['package'])
    require(len(geometry['areas']) == 50129, 'v2 geometry must contain 50,129 cells', ExecutionStop)
    case_count = 64
    cell_count = 50129
    water_depth = np.full((case_count, cell_count), np.nan, dtype=np.float64)
    velocity_u = np.full_like(water_depth, np.nan)
    velocity_v = np.full_like(water_depth, np.nan)
    mass_error = np.full(case_count, np.nan, dtype=np.float64)
    cfl_max = np.full(case_count, np.nan, dtype=np.float64)
    simulated_time = np.full(case_count, np.nan, dtype=np.float64)
    minimum_time_step = np.full(case_count, np.nan, dtype=np.float64)
    maximum_time_step = np.full(case_count, np.nan, dtype=np.float64)
    protected_before = protected_hashes(context['repoRoot'], context['contract']['protectedPaths'])

    def immediate_resource_stop(step):
        wall_seconds = time.perf_counter() - started
        resident_mib = peak_rss_mib()
        if wall_seconds > EXPECTED_ACCEPTANCE['maxWallSeconds']:
            raise ExecutionStop(
                f'wall time {wall_seconds} exceeds {EXPECTED_ACCEPTANCE["maxWallSeconds"]} seconds at step {step}'
            )
        if resident_mib > EXPECTED_ACCEPTANCE['maxResidentMemoryMiB']:
            raise ExecutionStop(
                f'peak RSS {resident_mib} exceeds {EXPECTED_ACCEPTANCE["maxResidentMemoryMiB"]} MiB at step {step}'
            )

    for index, case in enumerate(context['cases']):
        case_id = case['caseId']
        attempted_ids.append(case_id)
        case_started = time.perf_counter()
        try:
            immediate_resource_stop(0)
            result = run_case(
                case,
                500,
                geometry,
                max_cfl_allowed=0.95,
                max_mass_balance_error_allowed=1e-8,
                stop_check=immediate_resource_stop,
                include_fields=True,
            )
            immediate_resource_stop(500)
            validate_case_thresholds(result, case_id)
            for name in ('waterDepthM', 'velocityUms', 'velocityVms'):
                values = np.asarray(result[name])
                require(values.shape == (cell_count,), f'{case_id} {name} shape mismatch', ExecutionStop)
                require(np.isfinite(values).all(), f'{case_id} {name} is nonfinite', ExecutionStop)
            require(np.all(result['waterDepthM'] >= 0), f'{case_id} has negative depth', ExecutionStop)

            water_depth[index] = result['waterDepthM']
            velocity_u[index] = result['velocityUms']
            velocity_v[index] = result['velocityVms']
            mass_error[index] = result['massBalanceError']
            cfl_max[index] = result['maxCfl']
            simulated_time[index] = result['simulatedTimeSeconds']
            minimum_time_step[index] = result['minimumTimeStepSeconds']
            maximum_time_step[index] = result['maximumTimeStepSeconds']
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
            write_json_atomic(
                context['progressPath'],
                progress_payload(context, started, diagnostics, attempted_ids, 'running'),
                replace_existing=progress_state['written'],
            )
            progress_state['written'] = True
        except BaseException as error:
            if (
                diagnostics
                and diagnostics[-1].get('caseId') == case_id
                and diagnostics[-1].get('status') == 'completed'
            ):
                diagnostics.pop()
            reason = f'{type(error).__name__}: {error}'
            diagnostic = {
                'caseId': case_id,
                'status': 'failed',
                'wallSeconds': time.perf_counter() - case_started,
                'reason': reason,
            }
            if isinstance(error, NumericalStop):
                diagnostic.update({
                    'step': error.step,
                    'nanCount': error.nan_count,
                    'negativeDepthCount': error.negative_depth_count,
                    'maxCfl': error.max_cfl,
                    'massBalanceError': error.mass_balance_error,
                })
            diagnostics.append(diagnostic)
            stop = {
                'caseId': case_id,
                'reason': reason,
                'automaticRetryAllowed': False,
                'partialFieldArtifactWritten': False,
            }
            write_json_atomic(
                context['progressPath'],
                progress_payload(context, started, diagnostics, attempted_ids, 'stopped', stop),
                replace_existing=progress_state['written'],
            )
            progress_state['written'] = True
            progress_state['stopWritten'] = True
            raise ExecutionStop(f'immediate STOP at {case_id}: {reason}') from error

    try:
        immediate_resource_stop(500)
        require(len(diagnostics) == 64, 'v2 run did not complete all 64 cases', ExecutionStop)
        require(np.isfinite(water_depth).all(), 'v2 depth fields are incomplete', ExecutionStop)
        require(
            np.isfinite(velocity_u).all() and np.isfinite(velocity_v).all(),
            'v2 velocity fields are incomplete',
            ExecutionStop,
        )
        require(np.all(water_depth >= 0), 'v2 depth fields contain negative values', ExecutionStop)
        protected_after = protected_hashes(context['repoRoot'], context['contract']['protectedPaths'])
        require(
            protected_after == protected_before,
            'a protected public or legacy surface changed',
            ExecutionStop,
        )
    except BaseException as error:
        reason = f'{type(error).__name__}: {error}'
        stop = {
            'caseId': None,
            'reason': reason,
            'automaticRetryAllowed': False,
            'partialFieldArtifactWritten': False,
        }
        write_json_atomic(
            context['progressPath'],
            progress_payload(context, started, diagnostics, attempted_ids, 'stopped', stop),
            replace_existing=progress_state['written'],
        )
        progress_state['written'] = True
        progress_state['stopWritten'] = True
        raise ExecutionStop(f'immediate STOP during final checks: {reason}') from error
    wall_seconds = time.perf_counter() - started
    input_digests = {
        'executionContractSha256': context['contractSha256'],
        'authorizationSha256': context['authorizationSha256'],
        'meshSha256': context['meshSha256'],
        'meshSummarySha256': context['meshSummarySha256'],
        'ensembleSha256': context['ensembleSha256'],
    }
    fields_publication = {'published': False}
    report_publication = {'published': False}
    try:
        save_npz_atomic(
            context['fieldsPath'],
            publication_state=fields_publication,
            schema=np.array('onga-stage18-full64-fields-v2'),
            case_ids=np.array(attempted_ids),
            water_depth_m=water_depth,
            velocity_u_ms=velocity_u,
            velocity_v_ms=velocity_v,
            mass_balance_error=mass_error,
            cfl_max=cfl_max,
            simulated_time_seconds=simulated_time,
            minimum_time_step_seconds=minimum_time_step,
            maximum_time_step_seconds=maximum_time_step,
            execution_contract_sha256=np.array(context['contractSha256']),
            authorization_sha256=np.array(context['authorizationSha256']),
            mesh_sha256=np.array(context['meshSha256']),
            mesh_summary_sha256=np.array(context['meshSummarySha256']),
            ensemble_sha256=np.array(context['ensembleSha256']),
            comparison_basis=np.array(EXPECTED_RUN['comparisonBasis']),
        )
        field_digest = sha256_file(context['fieldsPath'])
        case_wall_total = sum(item['wallSeconds'] for item in diagnostics)
        report = {
            'schema': 'onga-stage18-full64-run-report-v2',
            'classification': 'provisional_full64_runtime_and_numerical_stability_evidence_only',
            'geometry': EXPECTED_GEOMETRY,
            'ensembleSeed': 20260713,
            'requestedCaseCount': 64,
            'attemptedCaseIds': attempted_ids,
            'completedCaseCount': 64,
            'failedCaseCount': 0,
            'wallSeconds': wall_seconds,
            'caseWallSecondsTotal': case_wall_total,
            'peakResidentMemoryMiB': peak_rss_mib(),
            'maxCfl': float(np.max(cfl_max)),
            'maxAbsoluteMassBalanceError': float(np.max(np.abs(mass_error))),
            'minimumDepthM': float(np.min(water_depth)),
            'minimumSimulatedTimeSeconds': float(np.min(simulated_time)),
            'maximumSimulatedTimeSeconds': float(np.max(simulated_time)),
            'nanCount': 0,
            'negativeDepthCount': 0,
            'comparisonBasis': EXPECTED_RUN['comparisonBasis'],
            'parameterCoverage': context['contract']['parameterCoverage'],
            'failures': [],
            'caseDiagnostics': diagnostics,
            'inputDigests': input_digests,
            'fieldArtifact': {
                'path': str(context['fieldsPath']),
                'sha256': field_digest,
                'shape': {'caseCount': 64, 'cellCount': 50129},
                'dtype': 'float64',
            },
            'protectedSurfaceHashesBefore': protected_before,
            'protectedSurfaceHashesAfter': protected_after,
            'protectedSurfaceHashesUnchanged': True,
            'safeguards': context['authorization']['safeguards'],
            'stopPolicy': EXPECTED_STOP_POLICY,
        }
        write_json_atomic(
            context['reportPath'],
            report,
            publication_state=report_publication,
        )
        write_json_atomic(
            context['progressPath'],
            progress_payload(context, started, diagnostics, attempted_ids, 'completed'),
            replace_existing=True,
        )
        progress_state['completed'] = True
        return report
    except BaseException as error:
        if fields_publication['published']:
            context['fieldsPath'].unlink(missing_ok=True)
            fields_publication['published'] = False
        if report_publication['published']:
            context['reportPath'].unlink(missing_ok=True)
            report_publication['published'] = False
        reason = f'{type(error).__name__}: {error}'
        stop = {
            'caseId': None,
            'reason': reason,
            'automaticRetryAllowed': False,
            'partialFieldArtifactWritten': False,
        }
        try:
            write_json_atomic(
                context['progressPath'],
                progress_payload(context, started, diagnostics, attempted_ids, 'stopped', stop),
                replace_existing=True,
            )
            progress_state['written'] = True
            progress_state['stopWritten'] = True
        except BaseException:
            pass
        raise ExecutionStop(f'immediate STOP while publishing success outputs: {reason}') from error
    raise AssertionError('success publication exited without returning its report')


def execute_cases(args, context):
    """Run the authorized ensemble and always leave a STOP record on interruption."""
    started = time.perf_counter()
    diagnostics = []
    attempted_ids = []
    progress_state = {'written': False, 'stopWritten': False, 'completed': False}

    def interrupt_handler(signum, _frame):
        if progress_state['completed']:
            return
        try:
            signal_name = signal.Signals(signum).name
        except ValueError:
            signal_name = str(signum)
        raise ExecutionStop(f'received {signal_name}')

    previous_handlers = {}
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signal_number] = signal.getsignal(signal_number)
        signal.signal(signal_number, interrupt_handler)

    try:
        return _execute_cases_impl(
            args,
            context,
            started,
            diagnostics,
            attempted_ids,
            progress_state,
        )
    except BaseException as error:
        if not progress_state['stopWritten']:
            reason = f'{type(error).__name__}: {error}'
            stop = {
                'caseId': attempted_ids[-1] if attempted_ids else None,
                'reason': reason,
                'automaticRetryAllowed': False,
                'partialFieldArtifactWritten': False,
            }
            try:
                write_json_atomic(
                    context['progressPath'],
                    progress_payload(
                        context,
                        started,
                        diagnostics,
                        attempted_ids,
                        'stopped',
                        stop,
                    ),
                    replace_existing=progress_state['written'],
                )
                progress_state['written'] = True
                progress_state['stopWritten'] = True
            except BaseException:
                pass
        raise
    finally:
        for signal_number, previous_handler in previous_handlers.items():
            signal.signal(signal_number, previous_handler)


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('mesh')
    parser.add_argument('ensemble')
    parser.add_argument('authorization', nargs='?', default=AUTHORIZATION_PATH)
    parser.add_argument('--execution-contract', default=CONTRACT_PATH)
    parser.add_argument('--execution-gate', default=GATE_PATH)
    parser.add_argument('--mesh-summary', required=True)
    parser.add_argument('--fields-output', required=True)
    parser.add_argument('--report-output', required=True)
    parser.add_argument('--progress-output', required=True)
    parser.add_argument('--repo-root', default='.')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        control = control_plane_preflight(args)
    except (ExecutionNotAuthorized, PreflightError) as error:
        print(f'V2 CONTROL-PLANE STOP: {error}', file=sys.stderr)
        print('No numerical cases were started; NumPy and numerical inputs were not loaded.', file=sys.stderr)
        return 2

    try:
        context = data_plane_preflight(args, control)
    except (PreflightError, OSError, ValueError) as error:
        print(f'V2 PREFLIGHT STOP: {error}', file=sys.stderr)
        print('No numerical cases were started and no outputs were created.', file=sys.stderr)
        return 3

    try:
        report = execute_cases(args, context)
    except BaseException as error:
        print(f'V2 NUMERICAL STOP: {error}', file=sys.stderr)
        return 4
    print(json.dumps({
        'report': str(context['reportPath']),
        'completedCaseCount': report['completedCaseCount'],
        'failedCaseCount': report['failedCaseCount'],
        'wallSeconds': report['wallSeconds'],
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
