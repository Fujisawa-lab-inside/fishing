#!/usr/bin/env python3
"""Apply the single reviewed Stage 18 v3 recovery profile to shared v2 cores.

The numerical and result schemas remain v2.  Only the one-time control plane,
map-raster preflight, and sealed-evidence packaging are versioned as v3.  This
module deliberately exposes no user-selectable profile or command-line switch.
"""

from __future__ import annotations

from types import ModuleType


CONTRACT_SCHEMA = 'onga-stage18-full64-execution-contract-v3'
AUTHORIZATION_SCHEMA = 'onga-stage18-full64-run-authorization-v3'
GATE_SCHEMA = 'onga-stage18-full64-execution-gate-v3'
CONTRACT_PATH = 'config/stage18_full64_execution_contract_v3.json'
GATE_PATH = 'config/stage18_full64_execution_gate_v3.json'
AUTHORIZATION_PATH = 'config/stage18_full64_run_authorization_v3.json'
AUTHORIZATION_SCOPE = (
    'exactly_one_recovery_run_of_64_corrected_geometry_v2_cases_for_'
    'sealed_numerical_evidence_and_five_maps'
)
AUTHORIZATION_SOURCE_STATEMENT = (
    '承認済み橋下補正v2と修正済み地図化経路v3上で、この判断資料に示された64条件×500ステップを、'
    '承認後24時間以内に一回限り、完全な数値証拠と5枚の地図を作成するため再実行してよい。'
)
EXPECTED_WORKFLOW = 'Stage 18 corrected v3 one-time full64 recovery run'
EXPECTED_WORKFLOW_PATH = '.github/workflows/stage18-full64-v3-run.yml'
EXPECTED_DECISION_IMAGE_PATH = 'docs/visuals/stage18-v3-execution-decision.svg'

EXPECTED_PREVIOUS_ATTEMPT = {
    'workflowRunId': 29300177716,
    'authorizationId': 'stage18-v2-20260714t015121z-one-time',
    'authorizationConsumed': True,
    'numericalCasesCompleted': 64,
    'numericalEvaluationPassed': True,
    'mapPackageCompleted': False,
    'failure': 'mesh_rasterization_omitted_cell_320',
    'fullFieldArtifactAvailable': False,
    'reusable': False,
    'automaticRetryAllowed': False,
}

EXPECTED_MAP_RASTER = {
    'preflightRequiredBeforeAuthorizationConsumption': True,
    'pngWidth': 3840,
    'pngHeight': 2640,
    'rasterization': 'deterministic_triangle_cell_index_center_sample_square_pixel',
    'squarePixels': True,
    'representedCellCountRequired': 50129,
    'coverageFractionRequired': 1.0,
    'minimumPixelsPerCellRequired': 1,
    'cell320MinimumPixelsRequired': 1,
    'pixelSizeLocalMRequired': 0.7147801171875,
    'yBoundsExpansionTotalLocalMRequired': 8.356359375,
}

NUMERIC_CHECKPOINT_REQUIRED = [
    'execution-receipt.json',
    'onga_stage16_metric_fv_mesh_v2.npz',
    'stage16_metric_mesh_summary.json',
    'ensemble-v2.json',
    'preflight.json',
    'preflight-recheck.json',
    'full64-map-raster-preflight.json',
    'full64-map-raster-preflight-recheck.json',
    'full64-progress.json',
    'full64-report.json',
    'full64-fields.npz',
    'full64-evaluation.json',
    'full64-numeric-evidence-manifest.json',
]

EXPECTED_OUTPUTS = {
    'successRequired': [
        *NUMERIC_CHECKPOINT_REQUIRED,
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
    'numericCheckpointRequired': NUMERIC_CHECKPOINT_REQUIRED,
    'diagnosticBestEffortIfStoppedAfterAuthorization': [
        'execution-receipt.json',
        'full64-progress.json',
        'full64-diagnostic-stop.svg',
    ],
    'partialFieldArtifactAllowed': False,
    'numericEvidenceArtifactPrefix': 'stage18-full64-v3-numeric-evidence-',
    'successArtifactPrefix': 'stage18-full64-v3-results-',
    'diagnosticArtifactPrefix': 'stage18-full64-v3-diagnostics-',
}

EXPECTED_CONTRACT_KEYS = {
    'schema', 'status', 'executionAuthorized', 'authorization', 'authorizationContract',
    'geometry', 'meshExpected', 'ensembleExpected', 'run', 'acceptance', 'safeguards',
    'protectedPaths', 'parameterCoverage', 'outputs', 'stopPolicy', 'claimLimits',
    'visualDecision', 'previousAttempt', 'mapRaster',
}

EXPECTED_REVIEWED_CODE_PATHS = [
    CONTRACT_PATH,
    'tools/stage18_full64_v3_profile.py',
    'tools/run_stage18_full64_v3.py',
    'tools/preflight_stage18_full64_v3.py',
    'tools/evaluate_stage18_full64_v3.py',
    'tools/aggregate_stage18_full64_v3.py',
    'tools/render_stage18_full64_decision_v3.py',
    'tools/validate_stage18_full64_v3_map_raster.py',
    'tools/create_stage18_full64_v3_execution_receipt.py',
    'tools/seal_stage18_full64_v3_numeric_evidence.py',
    'tools/validate_stage18_full64_v3_control.py',
    'tools/run_stage18_full64_v2.py',
    'tools/evaluate_stage18_full64_v2.py',
    'tools/aggregate_stage18_full64_v2.py',
    'tools/render_stage18_full64_decision_v2.py',
    'tools/validate_stage18_full64_v2_map_raster.py',
    'tools/stage18_shallow_water_kernel_v2.py',
    EXPECTED_WORKFLOW_PATH,
]


def configure_runner(module: ModuleType) -> ModuleType:
    """Mutate the imported shared runner to the one fixed v3 control profile."""
    module.CONTRACT_SCHEMA = CONTRACT_SCHEMA
    module.AUTHORIZATION_SCHEMA = AUTHORIZATION_SCHEMA
    module.GATE_SCHEMA = GATE_SCHEMA
    module.CONTRACT_PATH = CONTRACT_PATH
    module.GATE_PATH = GATE_PATH
    module.AUTHORIZATION_PATH = AUTHORIZATION_PATH
    module.AUTHORIZATION_SCOPE = AUTHORIZATION_SCOPE
    module.AUTHORIZATION_SOURCE_STATEMENT = AUTHORIZATION_SOURCE_STATEMENT
    module.EXPECTED_WORKFLOW = EXPECTED_WORKFLOW
    module.EXPECTED_WORKFLOW_PATH = EXPECTED_WORKFLOW_PATH
    module.EXPECTED_DECISION_IMAGE_PATH = EXPECTED_DECISION_IMAGE_PATH
    module.EXPECTED_OUTPUTS = EXPECTED_OUTPUTS
    module.EXPECTED_REVIEWED_CODE_PATHS = EXPECTED_REVIEWED_CODE_PATHS
    module.EXPECTED_PREVIOUS_ATTEMPT = EXPECTED_PREVIOUS_ATTEMPT
    module.EXPECTED_MAP_RASTER = EXPECTED_MAP_RASTER
    module.EXPECTED_CONTRACT_KEYS = EXPECTED_CONTRACT_KEYS
    return module


def configure_evaluator(module: ModuleType) -> ModuleType:
    """Mutate the imported shared evaluator to the matching fixed v3 control profile."""
    module.CONTRACT_SCHEMA = CONTRACT_SCHEMA
    module.AUTHORIZATION_SCHEMA = AUTHORIZATION_SCHEMA
    module.CONTRACT_PATH = CONTRACT_PATH
    module.AUTHORIZATION_PATH = AUTHORIZATION_PATH
    module.AUTHORIZATION_SCOPE = AUTHORIZATION_SCOPE
    module.AUTHORIZATION_SOURCE_STATEMENT = AUTHORIZATION_SOURCE_STATEMENT
    module.DECISION_IMAGE_PATH = EXPECTED_DECISION_IMAGE_PATH
    module.EXPECTED_CONTRACT_KEYS = EXPECTED_CONTRACT_KEYS
    module.EXPECTED_PREVIOUS_ATTEMPT = EXPECTED_PREVIOUS_ATTEMPT
    module.EXPECTED_MAP_RASTER = EXPECTED_MAP_RASTER
    return module
