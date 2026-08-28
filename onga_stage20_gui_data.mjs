import { loadStage20BrowserMesh } from './onga_stage20_browser_mesh.mjs';

export const STAGE20_GUI_DATA_SCHEMA = 'onga-stage20-gui-data-v1';
const RUNTIME_CAPABILITIES_SCHEMA = 'onga-stage20-runtime-capabilities-v2';
const RUNTIME_CAPABILITY_MODE_IDS = Object.freeze([
  'synthetic',
  'r1c_saved_replay',
  'local_r1c_experiment',
  'f59_saved_replay',
  'fishing_decision_replay',
  'public_f59_viewer',
]);

const EXPECTED_MESH_SHA256 = '09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659';
const EXPECTED_RESPONSE_PACK_SHA256 = '2d92e67d2ececf8e3c9e540003cd5546e3f6a38b234de7b5122aa4448c3478a3';
const EXPECTED_OUTPUT_SHA256 = '146429c21fecc13359710bb5335885258b63cd1f5750b6816f01098659135417';
const EXPECTED_FISHWAY_GEOMETRY_SHA256 = '8593f67c5157ed1d55b717ba6ed691674694cfa499f7f7d533fc9950acdfc536';
const EXPECTED_GUI_INTEGRATION_MANIFEST_SHA256 = '34e88d3dfd3633a9ebb61b11cd6e8678e0aba3d55adc91bc5bf26300876056ff';
const EXPECTED_GUI_INTEGRATION_MANIFEST_BYTE_LENGTH = 12813;
const GUI_INTEGRATION_MANIFEST_SCHEMA = 'onga-stage20-gui-integration-status-manifest-v1';
const GUI_INTEGRATION_MANIFEST_STATUS = 'integrated_read_only_into_stage20_hybrid_GUI';
const EXPECTED_READINESS_GUI_INTEGRATION_SHA256 = 'ef41066d15beaed2531fcbe8d048b12cf50383b3fc0b788f443c5c4aaaf69811';
const EXPECTED_READINESS_GUI_INTEGRATION_BYTE_LENGTH = 4940;
const READINESS_GUI_INTEGRATION_SCHEMA = 'onga-stage20-parallel-readiness-gui-integration-v1';
const READINESS_GUI_INTEGRATION_STATUS = 'integrated_read_only_into_stage20_hybrid_GUI';
const EXPECTED_CONTRACT_RECOVERY_GUI_INTEGRATION_SHA256 = 'c31fe279a989f5b4f873e2f393dfdd44c3e1b70f2099830d5181e144b51da060';
const EXPECTED_CONTRACT_RECOVERY_GUI_INTEGRATION_BYTE_LENGTH = 5399;
const CONTRACT_RECOVERY_GUI_INTEGRATION_SCHEMA =
  'onga-stage20-contract-recovery-gui-integration-v1';
const CONTRACT_RECOVERY_GUI_INTEGRATION_STATUS =
  'integrated_read_only_into_stage20_hybrid_GUI';

const DEFAULT_URLS = Object.freeze({
  runtimeCapabilities: './config/stage20_runtime_capabilities_v2.json',
  guiIntegrationManifest: './config/stage20_gui_integration_status_manifest_v1.json',
  readinessGuiIntegration: './config/stage20_parallel_readiness_gui_integration_v1.json',
  contractRecoveryGuiIntegration:
    './config/stage20_contract_recovery_gui_integration_v1.json',
  meshManifest: './public/data/onga/stage20/mesh-v2.json',
  responseManifest: './public/data/onga/stage20/response-pack-synthetic-v2.json',
  hourlyInputs: './public/data/onga/stage20/hybrid-synthetic-input-v1.json',
  waterManifest: './data/onga_unified_water_manifest_r3.json',
  fishwayGeometry: './public/data/onga/onga_geometry.geojson',
  worker: './onga_stage20_hybrid_worker.mjs',
});

const RUNTIME_BINDING_PATHS = Object.freeze({
  gate_reference_anchor_authority_v2:
    'docs/results/stage20-barrage-pink-structure-alignment-candidate-v2/gate-reference-anchor-authority-v2.geojson',
  gate_photo_visible_endpoint_authority_v1:
    'config/stage20_barrage_gate_photo_visible_faces_authority_v1.geojson',
  current_synthetic_GUI_mesh_manifest:
    'public/data/onga/stage20/mesh-v2.json',
  current_synthetic_GUI_mesh_binary:
    'public/data/onga/stage20/mesh-v2.bin',
  current_synthetic_GUI_response_manifest:
    'public/data/onga/stage20/response-pack-synthetic-v2.json',
  current_synthetic_GUI_response_binary:
    'public/data/onga/stage20/response-pack-synthetic-v2.bin',
});

const READINESS_BINDING_PATHS = Object.freeze({
  parallel_readiness_package_v1:
    'config/stage20_parallel_readiness_package_v1.json',
  parallel_readiness_static_validation_v1:
    'docs/results/stage20-parallel-readiness-package-v1/static-validation.json',
  boundary_mesh_impact_report_v1:
    'docs/results/stage20-boundary-mesh-impact-v1/report.json',
  field_gate_observation_schema_v1:
    'config/stage20_field_gate_observation_schema_v1.json',
  result_provenance_schema_v1:
    'config/stage20_result_provenance_schema_v1.json',
});

const CONTRACT_RECOVERY_BINDING_PATHS = Object.freeze({
  contract_lint_scope_v1:
    'config/stage20_contract_lint_recovery_scope_v1.json',
  contract_lint_report_v1:
    'docs/results/stage20-contract-lint-and-recovery-v1/report.json',
  json_contract_recovery_bundle_v1:
    'docs/results/stage20-contract-lint-and-recovery-v1/stage20-json-contract-recovery-v1.zip',
  physical_validation_plan_v1:
    'docs/STAGE20_PHYSICAL_VALIDATION_PLAN_V1.md',
});

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-gui-data] ${message}`);
}

function validateRuntimeCapabilitiesV2(contract) {
  assert(
    contract?.schema === RUNTIME_CAPABILITIES_SCHEMA
      && contract?.version === 2
      && contract?.status === 'M0_CANDIDATE_NOT_PUBLIC_RUNTIME_AUTHORITY',
    'runtime capability contract identity changed',
  );
  assert(
    Array.isArray(contract.modes)
      && contract.modes.length === RUNTIME_CAPABILITY_MODE_IDS.length,
    'runtime capability mode count changed',
  );
  const modesById = {};
  for (const mode of contract.modes) {
    assert(
      RUNTIME_CAPABILITY_MODE_IDS.includes(mode?.id) && !modesById[mode.id],
      'runtime capability mode identity changed',
    );
    for (const field of [
      'calibrated',
      'fieldPrediction',
      'catchProbability',
      'operationalFishingAdvice',
      'safetyAuthority',
      'publicRuntime',
    ]) {
      assert(mode[field] === false, `${mode.id}.${field} must remain false`);
    }
    modesById[mode.id] = Object.freeze({ ...mode });
  }
  assert(
    RUNTIME_CAPABILITY_MODE_IDS.every(id => modesById[id]),
    'runtime capability mode set changed',
  );
  const local = modesById.local_r1c_experiment;
  assert(
    local.executionKind === 'local_bounded_solver_explicit_only'
      && local.gateEffect === 'explicit_run_updates_local_solver'
      && local.riverTideBoundaryPhysics === 'unconnected_fixed_local_conditions'
      && local.fishwayRepresentation === 'local_uncalibrated_lumped_C2_1',
    'local R1C capability boundary changed',
  );
  assert(
    contract.authorityBoundary
      && Object.values(contract.authorityBoundary).every(value => value === false),
    'runtime capability contract grants authority',
  );
  return Object.freeze({
    contract: Object.freeze(contract),
    modesById: Object.freeze(modesById),
  });
}

async function fetchJson(url, signal) {
  const response = await fetch(url, { cache: 'no-store', signal });
  assert(response.ok, `${url} returned HTTP ${response.status}`);
  return response.json();
}

function bytesToHex(bytes) {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

async function fetchPinnedJson(url, expectedSha256, signal, expectedByteLength = null) {
  const response = await fetch(url, { cache: 'no-store', signal });
  assert(response.ok, `${url} returned HTTP ${response.status}`);
  const payload = await response.arrayBuffer();
  if (expectedByteLength !== null) {
    assert(payload.byteLength === expectedByteLength, `${url} byte length changed`);
  }
  const digest = bytesToHex(new Uint8Array(await crypto.subtle.digest('SHA-256', payload)));
  assert(digest === expectedSha256, `${url} identity changed`);
  return JSON.parse(new TextDecoder().decode(payload));
}

function resolveUrl(value) {
  return new URL(value, import.meta.url).href;
}

function bindingMap(manifest) {
  assert(Array.isArray(manifest?.authorityBindings), 'GUI integration authority bindings are missing');
  const bindings = new Map();
  for (const binding of manifest.authorityBindings) {
    assert(binding && typeof binding.id === 'string', 'GUI integration binding id is invalid');
    assert(!bindings.has(binding.id), `duplicate GUI integration binding ${binding.id}`);
    bindings.set(binding.id, binding);
  }
  return bindings;
}

function requireRuntimeBinding(bindings, id) {
  const binding = bindings.get(id);
  assert(binding, `GUI integration binding ${id} is missing`);
  assert(binding.path === RUNTIME_BINDING_PATHS[id], `GUI integration binding ${id} path changed`);
  assert(/^[0-9a-f]{64}$/.test(binding.sha256), `GUI integration binding ${id} digest is invalid`);
  assert(Number.isInteger(binding.byteLength) && binding.byteLength > 0, `GUI integration binding ${id} byte length is invalid`);
  return binding;
}

function exactObjectKeys(value, expectedKeys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = Array.from(expectedKeys).sort();
  return actual.length === expected.length
    && actual.every((key, index) => key === expected[index]);
}

function readinessBindingMap(manifest) {
  assert(Array.isArray(manifest?.bindings), 'readiness GUI bindings are missing');
  const bindings = new Map();
  for (const binding of manifest.bindings) {
    assert(binding && typeof binding.id === 'string', 'readiness GUI binding id is invalid');
    assert(!bindings.has(binding.id), `duplicate readiness GUI binding ${binding.id}`);
    bindings.set(binding.id, binding);
  }
  return bindings;
}

function requireReadinessBinding(bindings, id) {
  const binding = bindings.get(id);
  assert(binding, `readiness GUI binding ${id} is missing`);
  assert(binding.path === READINESS_BINDING_PATHS[id], `readiness GUI binding ${id} path changed`);
  assert(/^[0-9a-f]{64}$/.test(binding.sha256), `readiness GUI binding ${id} digest is invalid`);
  assert(
    Number.isInteger(binding.byteLength) && binding.byteLength > 0,
    `readiness GUI binding ${id} byte length is invalid`,
  );
  return binding;
}

export function validateStage20ParallelReadinessGuiIntegration(manifest) {
  assert(manifest?.schema === READINESS_GUI_INTEGRATION_SCHEMA, 'readiness GUI integration schema changed');
  assert(manifest?.status === READINESS_GUI_INTEGRATION_STATUS, 'readiness GUI integration is not authorized');
  assert(manifest?.authorization?.authorizedBy === 'user_instruction', 'readiness GUI authorization is missing');
  const authorizedScope = new Set(manifest?.authorization?.scope || []);
  for (const permission of [
    'load_and_display_the_pinned_parallel_readiness_package',
    'display_boundary_mesh_and_precompute_decisions',
    'display_individual_gate_basis_and_cost_forecasts',
    'validate_and_import_local_field_gate_observation_JSON',
    'download_current_field_gate_observation_as_canonical_JSON',
    'display_result_provenance_classification',
  ]) {
    assert(authorizedScope.has(permission), `readiness GUI permission ${permission} is missing`);
  }
  assert(
    manifest?.integrationContract?.state === 'read_only_readiness_and_local_observation_IO_integrated'
      && manifest?.integrationContract?.failClosed === true
      && manifest?.integrationContract?.allBindingsPinnedBySha256AndByteLength === true,
    'readiness GUI fail-closed contract changed',
  );
  const display = manifest?.displayContract;
  assert(
    display?.completion?.taskCount === 11
      && display?.completion?.completedTaskCount === 11
      && display?.completion?.checkCount === 22
      && display?.completion?.passedCheckCount === 22
      && display?.completion?.recoveryBindingCount === 30
      && display?.completion?.binaryPatternCount === 256,
    'readiness completion display contract changed',
  );
  assert(
    display?.boundary?.classification === 'BOUNDARY_CHANGED_REBUILD_MESH_AND_PRECOMPUTE'
      && display?.boundary?.changedPixelCount === 116403
      && display?.boundary?.changedHistoricalMeshCentroidMembershipCount === 14859
      && display?.boundary?.existingHistoricalPackReusableAfterBoundaryAdoption === false,
    'boundary impact display contract changed',
  );
  assert(
    display?.formalR20?.precomputationExists === false
      && display?.formalR20?.recalculationRequiredNow === false
      && display?.formalR20?.firstPrecomputationRequiredAfterProductionMeshSelection === true,
    'formal R20 precompute display contract changed',
  );
  assert(
    display?.individualGates?.binaryTrainingBasisCount === 9
      && display?.individualGates?.binaryInteractionHoldoutCount === 5
      && display?.individualGates?.continuousAxisBasisCount === 17
      && display?.individualGates?.continuousInteractionHoldoutCount === 5
      && display?.individualGates?.globalFiftyPercentStatus === 'candidate_not_adopted'
      && display?.individualGates?.gateInputDrivesDisplayedFlow === false,
    'individual-gate readiness display contract changed',
  );
  assert(
    display?.provenance?.currentFlowClassification === 'synthetic_fixture'
      && display?.provenance?.physicalValidationPassed === false
      && display?.provenance?.forecastValidationPassed === false,
    'result provenance display contract changed',
  );
  assert(
    Object.values(manifest?.safeguards || {}).every(value => value === false),
    'readiness GUI safeguard changed',
  );
  const bindings = readinessBindingMap(manifest);
  const runtimeBindingIds = manifest.integrationContract.runtimeConsumedBindingIds || [];
  assert(
    runtimeBindingIds.length === Object.keys(READINESS_BINDING_PATHS).length
      && runtimeBindingIds.every(id => Object.hasOwn(READINESS_BINDING_PATHS, id)),
    'readiness runtime binding set changed',
  );
  const runtimeBindings = Object.freeze(Object.fromEntries(
    runtimeBindingIds.map(id => [
      id,
      Object.freeze({ ...requireReadinessBinding(bindings, id) }),
    ]),
  ));
  return Object.freeze({
    manifest: Object.freeze(manifest),
    runtimeBindings,
    display: Object.freeze(display),
  });
}

function contractRecoveryBindingMap(manifest) {
  assert(Array.isArray(manifest?.bindings), 'contract/recovery GUI bindings are missing');
  const bindings = new Map();
  for (const binding of manifest.bindings) {
    assert(
      binding && typeof binding.id === 'string',
      'contract/recovery GUI binding id is invalid',
    );
    assert(
      !bindings.has(binding.id),
      `duplicate contract/recovery GUI binding ${binding.id}`,
    );
    bindings.set(binding.id, binding);
  }
  return bindings;
}

function requireContractRecoveryBinding(bindings, id) {
  const binding = bindings.get(id);
  assert(binding, `contract/recovery GUI binding ${id} is missing`);
  assert(
    binding.path === CONTRACT_RECOVERY_BINDING_PATHS[id],
    `contract/recovery GUI binding ${id} path changed`,
  );
  assert(
    /^[0-9a-f]{64}$/.test(binding.sha256),
    `contract/recovery GUI binding ${id} digest is invalid`,
  );
  assert(
    Number.isInteger(binding.byteLength) && binding.byteLength > 0,
    `contract/recovery GUI binding ${id} byte length is invalid`,
  );
  assert(
    typeof binding.mediaType === 'string' && binding.mediaType.length > 0,
    `contract/recovery GUI binding ${id} media type is invalid`,
  );
  assert(
    typeof binding.downloadName === 'string' && binding.downloadName.length > 0,
    `contract/recovery GUI binding ${id} download name is invalid`,
  );
  return binding;
}

export function validateStage20ContractRecoveryGuiIntegration(manifest) {
  assert(
    manifest?.schema === CONTRACT_RECOVERY_GUI_INTEGRATION_SCHEMA,
    'contract/recovery GUI integration schema changed',
  );
  assert(
    manifest?.status === CONTRACT_RECOVERY_GUI_INTEGRATION_STATUS,
    'contract/recovery GUI integration is not authorized',
  );
  assert(
    manifest?.authorization?.authorizedBy === 'user_instruction'
      && manifest?.authorization?.instruction === '「GUI開発統合」へ統合せよ',
    'contract/recovery GUI authorization is missing',
  );
  const contract = manifest?.integrationContract;
  assert(
    contract?.state
      === 'read_only_contract_recovery_summary_and_verified_downloads_integrated'
      && contract?.failClosed === true
      && contract?.sidecarLoadedAtStartup === true
      && contract?.largeArtifactsLoadedAtStartup === false
      && contract?.allBindingsPinnedBySha256AndByteLength === true,
    'contract/recovery GUI fail-closed or lazy-load contract changed',
  );
  assert(
    Array.isArray(contract?.offlineValidatedBindingIds)
      && contract.offlineValidatedBindingIds.length
        === Object.keys(CONTRACT_RECOVERY_BINDING_PATHS).length
      && contract.offlineValidatedBindingIds.every(
        id => Object.hasOwn(CONTRACT_RECOVERY_BINDING_PATHS, id),
      ),
    'contract/recovery offline binding set changed',
  );
  assert(
    Array.isArray(contract?.lazyVerifiedDownloadBindingIds)
      && contract.lazyVerifiedDownloadBindingIds.join(',')
        === [
          'contract_lint_report_v1',
          'json_contract_recovery_bundle_v1',
          'physical_validation_plan_v1',
        ].join(','),
    'contract/recovery lazy download binding set changed',
  );

  const display = manifest?.displayContract;
  const audit = display?.audit;
  const warnings = audit?.warningBreakdown;
  assert(
    audit?.status === 'PASS_WITH_WARNINGS'
      && audit?.selectedJsonDocuments === 585
      && audit?.recoveryDocuments === 588
      && audit?.recognizableBindingsChecked === 3584
      && audit?.errorCount === 0
      && audit?.warningCount === 299,
    'contract audit display summary changed',
  );
  assert(
    warnings?.externalReferencesNotBundled === 86
      && warnings?.referencedFilesMissing === 175
      && warnings?.referencedSha256Mismatch === 21
      && warnings?.referencedByteLengthMismatch === 11
      && warnings?.rootSchemaIdentifierMissing === 5
      && warnings?.sha256ShapeInvalid === 1
      && Object.values(warnings).reduce((sum, value) => sum + value, 0)
        === audit.warningCount,
    'contract audit warning breakdown changed',
  );
  const recovery = display?.recovery;
  assert(
    recovery?.bundleVerificationStatus === 'PASS'
      && recovery?.documentEntriesChecked === 588
      && recovery?.zipEntryCount === 589
      && recovery?.bundleByteLength === 1564659
      && recovery?.restoreTargetMustBeNewOrEmpty === true
      && recovery?.overwriteCurrentWorktreeAllowed === false,
    'contract recovery display summary changed',
  );
  const physicalValidation = display?.physicalValidation;
  assert(
    physicalValidation?.status === 'plan_only_not_executed'
      && physicalValidation?.decisionRequiredNow === false
      && physicalValidation?.solverRunAuthorized === false
      && physicalValidation?.precomputationAuthorized === false
      && physicalValidation?.physicalValidationClaimAllowed === false,
    'physical validation display limit changed',
  );
  assert(
    manifest?.safeguards
      && Object.values(manifest.safeguards).every(value => value === false),
    'contract/recovery GUI safeguard changed',
  );

  const bindings = contractRecoveryBindingMap(manifest);
  assert(
    bindings.size === Object.keys(CONTRACT_RECOVERY_BINDING_PATHS).length,
    'contract/recovery binding count changed',
  );
  const artifactBindings = Object.freeze(Object.fromEntries(
    Object.keys(CONTRACT_RECOVERY_BINDING_PATHS).map(id => [
      id,
      Object.freeze({ ...requireContractRecoveryBinding(bindings, id) }),
    ]),
  ));
  return Object.freeze({
    manifest: Object.freeze(manifest),
    artifactBindings,
    display: Object.freeze({
      audit: Object.freeze({
        ...audit,
        warningBreakdown: Object.freeze({ ...warnings }),
      }),
      recovery: Object.freeze({ ...recovery }),
      physicalValidation: Object.freeze({ ...physicalValidation }),
    }),
  });
}

export async function fetchStage20ContractRecoveryArtifact(
  integration,
  bindingId,
  options = {},
) {
  assert(
    integration?.manifest?.schema === CONTRACT_RECOVERY_GUI_INTEGRATION_SCHEMA,
    'validated contract/recovery integration is required',
  );
  assert(
    integration.manifest.integrationContract.lazyVerifiedDownloadBindingIds
      .includes(bindingId),
    `contract/recovery artifact ${bindingId} is not authorized for lazy download`,
  );
  const binding = integration.artifactBindings?.[bindingId];
  assert(binding, `contract/recovery artifact ${bindingId} is not bound`);
  const response = await fetch(resolveUrl(`./${binding.path}`), {
    cache: 'no-store',
    signal: options.signal,
  });
  assert(response.ok, `${binding.path} returned HTTP ${response.status}`);
  const payload = await response.arrayBuffer();
  assert(
    payload.byteLength === binding.byteLength,
    `${binding.path} byte length changed`,
  );
  const digest = bytesToHex(
    new Uint8Array(await crypto.subtle.digest('SHA-256', payload)),
  );
  assert(digest === binding.sha256, `${binding.path} identity changed`);
  return Object.freeze({
    id: bindingId,
    binding,
    bytes: new Uint8Array(payload),
  });
}

function validateStage20ReadinessPayloads({
  integration,
  readinessPackage,
  staticValidation,
  boundaryReport,
  fieldObservationSchema,
  resultProvenanceSchema,
}) {
  const bindings = integration.runtimeBindings;
  assert(
    readinessPackage?.schema === 'onga-stage20-parallel-readiness-package-v1'
      && readinessPackage?.status === 'complete_static_readiness_package_no_physical_execution',
    'parallel readiness package identity changed',
  );
  assert(
    Array.isArray(readinessPackage.completionMatrix)
      && readinessPackage.completionMatrix.length === 11
      && readinessPackage.completionMatrix.every(item => item.status === 'complete'),
    'parallel readiness completion matrix changed',
  );
  for (const key of [
    'productionMeshSelected',
    'boundaryPhysicallyApplied',
    'individualGateLawPhysicallyAdopted',
    'solverRunAuthorized',
    'precomputationAuthorized',
    'paidComputeAuthorized',
    'responsePackChangeAuthorized',
    'publicRuntimeChangeAuthorized',
    'mainMergeAuthorized',
  ]) {
    assert(readinessPackage.authorization?.[key] === false, `readiness authorization ${key} changed`);
  }
  assert(
    staticValidation?.schema === 'onga-stage20-parallel-readiness-static-validation-v1'
      && staticValidation?.status === 'PASS'
      && staticValidation?.package?.sha256 === bindings.parallel_readiness_package_v1.sha256
      && staticValidation?.summary?.checkCount === 22
      && staticValidation?.summary?.passCount === 22
      && staticValidation?.summary?.failureCount === 0
      && staticValidation?.summary?.recoveryBindingCount === 30
      && staticValidation?.summary?.binaryPatternCount === 256,
    'parallel readiness static validation changed',
  );
  const pinnedBoundary = readinessPackage.boundaryImpactContract?.actualHistoricalComparison;
  assert(
    boundaryReport?.schema === 'onga-stage20-boundary-mesh-impact-report-v1'
      && boundaryReport?.status === 'PASS_READ_ONLY_AUDIT_COMPLETED'
      && boundaryReport?.classification === pinnedBoundary?.classification
      && boundaryReport?.waterMaskDifference?.changedPixelCount === pinnedBoundary?.changedPixelCount
      && boundaryReport?.historicalMeshCentroidImpact?.changedMembershipCount
        === pinnedBoundary?.changedHistoricalMeshCentroidMembershipCount
      && boundaryReport?.decision?.existingHistoricalPackReusableAfterBoundaryAdoption === false
      && boundaryReport?.decision?.meshRebuildRequiredBeforeBoundaryAdoption === true
      && boundaryReport?.decision?.precomputationRequiredAfterMeshRebuild === true
      && boundaryReport?.decision?.formalR20PrecomputationExists === false,
    'boundary impact report differs from the readiness package',
  );
  const binaryGateDefinition = fieldObservationSchema?.$defs?.binaryGateMap;
  assert(
    fieldObservationSchema?.$id === 'onga-stage20-field-gate-observation-batch-v1'
      && binaryGateDefinition?.required?.join(',') === '1,2,3,4,5,6,7,8'
      && binaryGateDefinition?.additionalProperties === false,
    'field gate observation schema changed',
  );
  const provenanceClasses = resultProvenanceSchema?.properties?.classification?.enum;
  assert(
    resultProvenanceSchema?.$id === 'onga-stage20-result-provenance-v1'
      && Array.isArray(provenanceClasses)
      && provenanceClasses.includes('synthetic_fixture')
      && resultProvenanceSchema?.['x-display-policy']?.historicalSyntheticPackLabelJa
        === '合成データ・物理計算未接続',
    'result provenance schema changed',
  );
  const basis = readinessPackage.individualGateBasisDesign;
  assert(
    basis?.binaryTrainingBasis?.basisCount === 9
      && basis?.binaryInteractionHoldouts?.length === 5
      && basis?.continuousAxisBasis?.basisCount === 17
      && basis?.globalFiftyPercentInterpolation?.currentStatus === 'candidate_not_adopted',
    'individual-gate basis contract changed',
  );
  const checkpoint = readinessPackage.checkpointRestartPlan;
  assert(
    checkpoint?.segmentDurationHours === 8
      && checkpoint?.segmentCountPerBasis === 6
      && checkpoint?.restartStateCountPerBasis === 7
      && checkpoint?.displaySnapshotHours?.count === 37,
    'checkpoint readiness contract changed',
  );
  const costMeshes = readinessPackage.precomputeCostForecast?.meshes;
  assert(
    Array.isArray(costMeshes)
      && costMeshes.length === 2
      && costMeshes[0]?.id === 'formal_R20_44880'
      && costMeshes[1]?.id === 'multizone_R20_37168',
    'precompute cost forecast mesh set changed',
  );
  return Object.freeze({
    package: Object.freeze(readinessPackage),
    staticValidation: Object.freeze(staticValidation),
    boundaryReport: Object.freeze(boundaryReport),
    fieldObservationSchema: Object.freeze(fieldObservationSchema),
    resultProvenanceSchema: Object.freeze(resultProvenanceSchema),
    completion: Object.freeze({ ...integration.display.completion }),
    boundary: Object.freeze({ ...integration.display.boundary }),
    formalR20: Object.freeze({ ...integration.display.formalR20 }),
    individualGates: Object.freeze({ ...integration.display.individualGates }),
    checkpoint: Object.freeze({ ...integration.display.checkpoint }),
    provenance: Object.freeze({ ...integration.display.provenance }),
    costMeshes: Object.freeze(costMeshes.map(mesh => Object.freeze(mesh))),
  });
}

function hasExplicitTimestampOffset(value) {
  return typeof value === 'string'
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function validateBinaryGateMap(value) {
  assert(exactObjectKeys(value, GATE_KEYS), 'gateStateById keys must be exactly strings 1 through 8');
  for (const key of GATE_KEYS) {
    assert(Number.isInteger(value[key]) && (value[key] === 0 || value[key] === 1), `gate ${key} must be integer 0 or 1`);
  }
}

const GATE_KEYS = Object.freeze(['1', '2', '3', '4', '5', '6', '7', '8']);

export function validateStage20FieldGateObservationBatch(batch, schema = null) {
  if (schema !== null) {
    assert(schema?.$id === 'onga-stage20-field-gate-observation-batch-v1', 'field observation schema identity changed');
  }
  assert(
    exactObjectKeys(batch, ['schema', 'version', 'timezone', 'exportedAt', 'records']),
    'field observation batch has missing or extra keys',
  );
  assert(batch.schema === 'onga-stage20-field-gate-observation-batch-v1', 'field observation batch schema changed');
  assert(batch.version === 1 && batch.timezone === 'Asia/Tokyo', 'field observation version or timezone changed');
  assert(hasExplicitTimestampOffset(batch.exportedAt), 'field observation exportedAt needs an explicit offset');
  assert(Array.isArray(batch.records), 'field observation records must be an array');
  const revisions = new Map();
  for (const record of batch.records) {
    const allowedKeys = [
      'observationId',
      'observedAt',
      'source',
      'gateStateById',
      'gateCapacityFractionById',
      'capacityFractionMeaning',
      'notes',
      'provenance',
      'revision',
    ];
    assert(
      record && typeof record === 'object'
        && ['observationId', 'observedAt', 'source', 'gateStateById', 'provenance', 'revision']
          .every(key => Object.hasOwn(record, key))
        && Object.keys(record).every(key => allowedKeys.includes(key)),
      'field observation record has missing or extra keys',
    );
    assert(
      typeof record.observationId === 'string'
        && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(record.observationId),
      'field observation id is invalid',
    );
    assert(hasExplicitTimestampOffset(record.observedAt), 'field observation observedAt needs an explicit offset');
    assert(
      ['field_visual', 'operator_record', 'imported_file', 'manual_test'].includes(record.source),
      'field observation source is invalid',
    );
    validateBinaryGateMap(record.gateStateById);
    const hasCapacity = Object.hasOwn(record, 'gateCapacityFractionById');
    const hasMeaning = Object.hasOwn(record, 'capacityFractionMeaning');
    assert(hasCapacity === hasMeaning, 'capacity map and meaning must occur together');
    if (hasCapacity) {
      assert(
        exactObjectKeys(record.gateCapacityFractionById, GATE_KEYS),
        'gateCapacityFractionById keys must be exactly strings 1 through 8',
      );
      for (const key of GATE_KEYS) {
        const value = record.gateCapacityFractionById[key];
        assert(
          typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1,
          `gate capacity ${key} must be finite numeric 0 through 1`,
        );
      }
      assert(
        record.capacityFractionMeaning === 'provisional_model_capacity_multiplier_not_measured_leaf_height',
        'capacity fraction meaning changed',
      );
    }
    assert(
      record.provenance && typeof record.provenance === 'object'
        && typeof record.provenance.recordedBy === 'string'
        && record.provenance.recordedBy.length > 0
        && hasExplicitTimestampOffset(record.provenance.recordedAt),
      'field observation provenance is invalid',
    );
    assert(Number.isInteger(record.revision) && record.revision >= 1, 'field observation revision is invalid');
    const priorRevision = revisions.get(record.observationId);
    assert(priorRevision === undefined || record.revision > priorRevision, 'field observation revision must increase');
    revisions.set(record.observationId, record.revision);
  }
  return Object.freeze(batch);
}

export function validateStage20GuiIntegrationManifest(manifest) {
  assert(manifest?.schema === GUI_INTEGRATION_MANIFEST_SCHEMA, 'GUI integration manifest schema changed');
  assert(manifest?.status === GUI_INTEGRATION_MANIFEST_STATUS, 'GUI integration manifest is not authorized for runtime display');
  assert(manifest?.integrationAuthorization?.authorizedBy === 'user_instruction', 'GUI integration authorization is missing');
  assert(
    manifest?.guiIntegrationContract?.integrationState === 'read_only_status_and_review_overlay_integrated',
    'GUI integration state changed',
  );
  assert(
    manifest?.guiIntegrationContract?.offlineValidationRequiredForAllBindings === true,
    'offline validation requirement is missing',
  );
  const allowedNow = new Set(manifest.guiIntegrationContract.allowedNow || []);
  for (const permission of [
    'load_this_manifest_as_read_only_status_data',
    'render_the_recommended_labels_and_adoption_stages',
    'use_authority_paths_for_number_markers_and_photo_endpoint_review_layers',
    'reject_mesh_and_response_pack_identity_mismatch',
  ]) {
    assert(allowedNow.has(permission), `GUI integration permission ${permission} is missing`);
  }
  const gates = manifest?.displayState?.mainGates;
  assert(gates?.gateCount === 8 && gates?.numbering === 'west_1_to_east_8', 'main-gate display contract changed');
  assert(gates?.referenceAnchors?.approvedCount === 8, 'gate reference-anchor approval count changed');
  assert(gates?.referenceAnchors?.exactGeometricCenters === false, 'gate anchors cannot be exact centres');
  assert(
    gates?.referenceAnchors?.physicalEndpointDerivationAuthorized === false,
    'gate anchors cannot authorize endpoint derivation',
  );
  assert(gates?.photoVisibleEndpoints?.approvedGateSpanCount === 8, 'photo-visible gate span count changed');
  assert(gates?.photoVisibleEndpoints?.approvedEndpointCount === 16, 'photo-visible endpoint approval count changed');
  assert(
    gates?.photoVisibleEndpoints?.guiRole === 'read_only_review_overlay_only'
      && gates?.photoVisibleEndpoints?.physicalMeshUseAuthorized === false,
    'photo-visible endpoint scope changed',
  );
  assert(
    gates?.hydraulicWidth?.effectiveWidthMPerGate === 46.5
      && gates?.hydraulicWidth?.mustNotBeRenderedAsGeographicSpanLength === true,
    'H2 model-width display contract changed',
  );
  assert(
    gates?.physicalAdoption?.productionMeshSelected === false
      && gates?.physicalAdoption?.solverConnected === false
      && gates?.physicalAdoption?.responsePackConnected === false
      && gates?.physicalAdoption?.precomputationAuthorized === false,
    'physical gate adoption must remain unapproved',
  );
  const fishway = manifest?.displayState?.fishway;
  assert(
    fishway?.operationalSemantics === 'always_enabled'
      && fishway?.userControllable === false
      && fishway?.guiControlAllowed === false,
    'fishway GUI semantics changed',
  );
  assert(
    fishway?.physicalRepresentationAdopted === false
      && fishway?.solverConnected === false
      && fishway?.responsePackConnected === false
      && fishway?.precomputationAuthorized === false,
    'fishway physical connection must remain unapproved',
  );
  const products = manifest?.displayState?.geometryAndDataProducts;
  assert(
    products?.formalR20ReviewMesh?.cellCount === 44880
      && products?.formalR20ReviewMesh?.precomputationAuthorized === false,
    'formal R20 review-mesh contract changed',
  );
  assert(
    products?.currentSyntheticGuiMesh?.cellCount === 50199
      && products?.currentSyntheticResponsePack?.cellCount === 50199
      && products?.currentSyntheticGuiMesh?.meshSha256
        === products?.currentSyntheticResponsePack?.meshSha256,
    'current synthetic mesh/response-pack contract changed',
  );
  assert(
    products?.compatibility?.formalR20ReviewMeshWithCurrentSyntheticResponsePack === false
      && products?.compatibility?.reason === 'different_mesh_identity_and_cell_count',
    'cross-mesh incompatibility guard changed',
  );
  const bindings = bindingMap(manifest);
  const runtimeBindingIds = manifest.guiIntegrationContract.runtimeConsumedBindingIds || [];
  assert(
    runtimeBindingIds.length === Object.keys(RUNTIME_BINDING_PATHS).length
      && runtimeBindingIds.every(id => Object.hasOwn(RUNTIME_BINDING_PATHS, id)),
    'runtime binding set changed',
  );
  const runtimeBindings = Object.freeze(Object.fromEntries(
    runtimeBindingIds.map(id => [id, Object.freeze({ ...requireRuntimeBinding(bindings, id) })]),
  ));
  assert(
    runtimeBindings.current_synthetic_GUI_mesh_binary.sha256 === EXPECTED_MESH_SHA256,
    'runtime mesh identity differs from the approved synthetic mesh',
  );
  assert(
    runtimeBindings.current_synthetic_GUI_response_binary.sha256 === EXPECTED_RESPONSE_PACK_SHA256,
    'runtime response-pack identity differs from the approved synthetic pack',
  );
  return Object.freeze({
    manifest: Object.freeze(manifest),
    runtimeBindings,
    gates: Object.freeze(gates),
    fishway: Object.freeze(fishway),
    products: Object.freeze(products),
  });
}

function runSynthesisWorker({ workerUrl, responseManifestUrl, inputs, signal }) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(workerUrl, { type: 'module' });
    let settled = false;
    let timeoutId = null;

    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      if (timeoutId !== null) globalThis.clearTimeout(timeoutId);
      signal?.removeEventListener('abort', onAbort);
      worker.terminate();
      callback(value);
    };
    const onAbort = () => finish(reject, new DOMException('GUI data loading was cancelled', 'AbortError'));

    worker.addEventListener('message', event => {
      const result = event.data;
      if (result?.type !== 'hybrid-synthesis-result') {
        finish(reject, new Error('hybrid synthesis worker returned an unexpected message'));
        return;
      }
      if (result.status !== 'passed') {
        finish(reject, new Error(result.error || 'hybrid synthesis failed'));
        return;
      }
      finish(resolve, result);
    });
    worker.addEventListener('error', event => {
      finish(reject, new Error(event.message || 'hybrid synthesis worker failed'));
    });
    worker.addEventListener('messageerror', () => {
      finish(reject, new Error('hybrid synthesis worker returned unreadable data'));
    });
    signal?.addEventListener('abort', onAbort, { once: true });
    if (signal?.aborted) {
      onAbort();
      return;
    }
    timeoutId = globalThis.setTimeout(() => {
      finish(reject, new Error('hybrid synthesis worker timed out'));
    }, 30_000);
    try {
      worker.postMessage({
        type: 'run-hybrid-synthesis',
        responseManifestUrl,
        inputs,
        includeOutput: true,
      });
    } catch (error) {
      finish(reject, error);
    }
  });
}

export async function loadStage20GuiData(options = {}) {
  assert(options.urls === undefined, 'GUI prototype data URLs are fixed');
  const urls = DEFAULT_URLS;
  const signal = options.signal;
  const runtimeCapabilitiesUrl = resolveUrl(urls.runtimeCapabilities);
  const guiIntegrationManifestUrl = resolveUrl(urls.guiIntegrationManifest);
  const readinessGuiIntegrationUrl = resolveUrl(urls.readinessGuiIntegration);
  const contractRecoveryGuiIntegrationUrl = resolveUrl(
    urls.contractRecoveryGuiIntegration,
  );
  const meshUrl = resolveUrl(urls.meshManifest);
  const responseManifestUrl = resolveUrl(urls.responseManifest);
  const inputsUrl = resolveUrl(urls.hourlyInputs);
  const waterManifestUrl = resolveUrl(urls.waterManifest);
  const fishwayGeometryUrl = resolveUrl(urls.fishwayGeometry);
  const workerUrl = resolveUrl(urls.worker);

  options.onProgress?.('runtime-capabilities');
  const runtimeCapabilities = validateRuntimeCapabilitiesV2(
    await fetchJson(runtimeCapabilitiesUrl, signal),
  );
  options.onProgress?.('integration-manifest');
  const guiIntegrationManifest = await fetchPinnedJson(
    guiIntegrationManifestUrl,
    EXPECTED_GUI_INTEGRATION_MANIFEST_SHA256,
    signal,
    EXPECTED_GUI_INTEGRATION_MANIFEST_BYTE_LENGTH,
  );
  const guiIntegration = validateStage20GuiIntegrationManifest(guiIntegrationManifest);
  const readinessGuiIntegrationManifest = await fetchPinnedJson(
    readinessGuiIntegrationUrl,
    EXPECTED_READINESS_GUI_INTEGRATION_SHA256,
    signal,
    EXPECTED_READINESS_GUI_INTEGRATION_BYTE_LENGTH,
  );
  const readinessGuiIntegration = validateStage20ParallelReadinessGuiIntegration(
    readinessGuiIntegrationManifest,
  );
  options.onProgress?.('contract-recovery-index');
  const contractRecoveryGuiIntegrationManifest = await fetchPinnedJson(
    contractRecoveryGuiIntegrationUrl,
    EXPECTED_CONTRACT_RECOVERY_GUI_INTEGRATION_SHA256,
    signal,
    EXPECTED_CONTRACT_RECOVERY_GUI_INTEGRATION_BYTE_LENGTH,
  );
  const contractRecovery = validateStage20ContractRecoveryGuiIntegration(
    contractRecoveryGuiIntegrationManifest,
  );
  const anchorBinding = guiIntegration.runtimeBindings.gate_reference_anchor_authority_v2;
  const photoEndpointBinding = guiIntegration.runtimeBindings.gate_photo_visible_endpoint_authority_v1;
  const meshManifestBinding = guiIntegration.runtimeBindings.current_synthetic_GUI_mesh_manifest;
  const meshBinaryBinding = guiIntegration.runtimeBindings.current_synthetic_GUI_mesh_binary;
  const responseManifestBinding = guiIntegration.runtimeBindings.current_synthetic_GUI_response_manifest;
  const responseBinaryBinding = guiIntegration.runtimeBindings.current_synthetic_GUI_response_binary;
  const gateReferenceAnchorAuthorityUrl = resolveUrl(`./${anchorBinding.path}`);
  const gatePhotoVisibleEndpointAuthorityUrl = resolveUrl(`./${photoEndpointBinding.path}`);
  const readinessPackageBinding =
    readinessGuiIntegration.runtimeBindings.parallel_readiness_package_v1;
  const readinessValidationBinding =
    readinessGuiIntegration.runtimeBindings.parallel_readiness_static_validation_v1;
  const boundaryImpactBinding =
    readinessGuiIntegration.runtimeBindings.boundary_mesh_impact_report_v1;
  const fieldObservationSchemaBinding =
    readinessGuiIntegration.runtimeBindings.field_gate_observation_schema_v1;
  const resultProvenanceSchemaBinding =
    readinessGuiIntegration.runtimeBindings.result_provenance_schema_v1;
  assert(meshUrl === resolveUrl(`./${meshManifestBinding.path}`), 'runtime mesh URL differs from the integration manifest');
  assert(
    responseManifestUrl === resolveUrl(`./${responseManifestBinding.path}`),
    'runtime response-pack URL differs from the integration manifest',
  );

  options.onProgress?.('readiness-contracts');
  const [
    readinessPackage,
    readinessStaticValidation,
    boundaryImpactReport,
    fieldGateObservationSchema,
    resultProvenanceSchema,
  ] = await Promise.all([
    fetchPinnedJson(
      resolveUrl(`./${readinessPackageBinding.path}`),
      readinessPackageBinding.sha256,
      signal,
      readinessPackageBinding.byteLength,
    ),
    fetchPinnedJson(
      resolveUrl(`./${readinessValidationBinding.path}`),
      readinessValidationBinding.sha256,
      signal,
      readinessValidationBinding.byteLength,
    ),
    fetchPinnedJson(
      resolveUrl(`./${boundaryImpactBinding.path}`),
      boundaryImpactBinding.sha256,
      signal,
      boundaryImpactBinding.byteLength,
    ),
    fetchPinnedJson(
      resolveUrl(`./${fieldObservationSchemaBinding.path}`),
      fieldObservationSchemaBinding.sha256,
      signal,
      fieldObservationSchemaBinding.byteLength,
    ),
    fetchPinnedJson(
      resolveUrl(`./${resultProvenanceSchemaBinding.path}`),
      resultProvenanceSchemaBinding.sha256,
      signal,
      resultProvenanceSchemaBinding.byteLength,
    ),
  ]);
  const parallelReadiness = validateStage20ReadinessPayloads({
    integration: readinessGuiIntegration,
    readinessPackage,
    staticValidation: readinessStaticValidation,
    boundaryReport: boundaryImpactReport,
    fieldObservationSchema: fieldGateObservationSchema,
    resultProvenanceSchema,
  });

  options.onProgress?.('mesh-and-contracts');
  const [
    meshManifestAuthority,
    mesh,
    responseManifest,
    inputs,
    waterManifest,
    fishwayGeometry,
    gateReferenceAnchorAuthority,
    gatePhotoVisibleEndpointAuthority,
  ] = await Promise.all([
    fetchPinnedJson(meshUrl, meshManifestBinding.sha256, signal, meshManifestBinding.byteLength),
    loadStage20BrowserMesh(meshUrl, { fetchImpl: (url, init = {}) => fetch(url, { ...init, signal }) }),
    fetchPinnedJson(
      responseManifestUrl,
      responseManifestBinding.sha256,
      signal,
      responseManifestBinding.byteLength,
    ),
    fetchJson(inputsUrl, signal),
    fetchJson(waterManifestUrl, signal),
    fetchPinnedJson(fishwayGeometryUrl, EXPECTED_FISHWAY_GEOMETRY_SHA256, signal),
    fetchPinnedJson(
      gateReferenceAnchorAuthorityUrl,
      anchorBinding.sha256,
      signal,
      anchorBinding.byteLength,
    ),
    fetchPinnedJson(
      gatePhotoVisibleEndpointAuthorityUrl,
      photoEndpointBinding.sha256,
      signal,
      photoEndpointBinding.byteLength,
    ),
  ]);

  assert(meshManifestAuthority.schema === mesh.manifest.schema, 'pinned mesh manifest schema differs from loaded mesh');
  assert(
    meshManifestAuthority.binary?.sha256 === mesh.manifest.binary?.sha256,
    'pinned mesh manifest differs from loaded mesh',
  );
  assert(mesh.manifest.schema === 'onga-stage20-browser-mesh-v2', 'mesh-v2 is required');
  assert(mesh.manifest.counts.cells === 50199, 'mesh-v2 cell count changed');
  assert(mesh.manifest.binary.sha256 === EXPECTED_MESH_SHA256, 'approved mesh-v2 identity changed');
  assert(mesh.manifest.binary.sha256 === meshBinaryBinding.sha256, 'mesh binary differs from the GUI integration binding');
  assert(mesh.manifest.binary.byteLength === meshBinaryBinding.byteLength, 'mesh binary length differs from the GUI integration binding');
  assert(mesh.arrays.barrage_gate_id?.length === mesh.arrays.barrage_face_ids.length, 'eight-gate barrage mapping is missing');
  assert(Array.from(mesh.arrays.barrage_gate_id).every(gate => gate >= 1 && gate <= 8), 'barrage gate id is outside 1 through 8');
  assert(new Set(mesh.arrays.barrage_gate_id).size === 8, 'barrage mapping does not contain all eight gates');
  assert(responseManifest.schema === 'onga-stage20-response-pack-v1', 'response manifest schema mismatch');
  assert(responseManifest.status === 'synthetic_browser_benchmark_only', 'GUI prototype accepts the synthetic fixture only');
  assert(responseManifest.version === 'stage20-synthetic-response-pack-v2-mesh-v2', 'response-pack v2 is required');
  assert(responseManifest.binary.sha256 === EXPECTED_RESPONSE_PACK_SHA256, 'synthetic response-pack identity changed');
  assert(
    responseManifest.binary.sha256 === responseBinaryBinding.sha256,
    'response-pack binary differs from the GUI integration binding',
  );
  assert(
    responseManifest.binary.byteLength === responseBinaryBinding.byteLength,
    'response-pack binary length differs from the GUI integration binding',
  );
  assert(responseManifest.mesh.sha256 === mesh.manifest.binary.sha256, 'response pack and mesh identities differ');
  assert(responseManifest.mesh.cellCount === mesh.manifest.counts.cells, 'response pack cell count differs from mesh');
  assert(responseManifest.componentOrder.join(',') === 'depthM,eastVelocityMPS,northVelocityMPS', 'component order changed');
  assert(inputs.schema === 'onga-stage20-hybrid-hourly-input-v1', 'hourly input schema mismatch');
  assert(inputs.status === 'synthetic_browser_benchmark_only', 'hourly inputs are not the synthetic fixture');
  assert(Array.isArray(inputs.hours) && inputs.hours.length === 37, '37 hourly inputs are required');
  assert(inputs.hours[0] === -12 && inputs.hours.at(-1) === 24, 'hour range must be -12 through +24');
  assert(inputs.hours.every((hour, index) => hour === index - 12), 'hourly inputs must use one-hour intervals');
  for (const key of ['tideRelativeM', 'barrageOpeningFraction', 'ongaDischargeM3S']) {
    assert(Array.isArray(inputs[key]) && inputs[key].length === inputs.hours.length, `${key} length mismatch`);
    assert(inputs[key].every(Number.isFinite), `${key} contains a non-finite value`);
  }
  assert(waterManifest?.coordinateSystem?.geographic, 'geographic display transform is missing');
  const gateReferenceAnchorFeatures = gateReferenceAnchorAuthority?.features
    ?.filter(feature => feature?.properties?.kind === 'gate_reference_anchor')
    .sort((left, right) => left.properties.gate_no - right.properties.gate_no);
  const gatePhotoVisibleEndpointFeatures = gatePhotoVisibleEndpointAuthority?.features
    ?.filter(feature => feature?.properties?.kind === 'approved_photo_visible_gate_face_pair')
    .sort((left, right) => left.properties.gate_no - right.properties.gate_no);
  const fishwayFeatures = fishwayGeometry?.features
    ?.filter(feature => feature?.properties?.kind === 'fishway_center');
  assert(gateReferenceAnchorAuthority?.type === 'FeatureCollection', 'gate reference-anchor authority must be GeoJSON');
  assert(
    gateReferenceAnchorAuthority?.properties?.status === 'approved_reference_semantics_only_unchanged_v2',
    'gate reference-anchor authority status changed',
  );
  assert(
    gateReferenceAnchorAuthority?.properties?.old_confirmed_gate_center_semantics_withdrawn === true,
    'withdrawal of the old exact-centre semantics is missing',
  );
  assert(gateReferenceAnchorFeatures?.length === 8, 'gate authority must contain eight reference anchors');
  assert(fishwayGeometry?.type === 'FeatureCollection', 'fishway geometry must be GeoJSON');
  assert(fishwayFeatures?.length === 1, 'fishway geometry must contain one provided fishway centre');
  assert(
    gateReferenceAnchorFeatures.every((feature, index) => feature.properties.gate_no === index + 1),
    'gate reference-anchor numbers must be 1 through 8',
  );
  assert(gateReferenceAnchorFeatures.every(feature => feature.geometry?.type === 'Point'
    && feature.geometry.coordinates.length === 2
    && feature.geometry.coordinates.every(Number.isFinite)), 'gate reference-anchor coordinate is invalid');
  assert(gateReferenceAnchorFeatures.every(feature => feature.properties.locked === true
    && feature.properties.user_confirmed === true
    && feature.properties.is_exact_geometric_center === false
    && feature.properties.physical_endpoint_derivation_authorized === false), 'gate reference-anchor semantics changed');
  assert(gateReferenceAnchorFeatures.every((feature, index) => index === 0
    || feature.geometry.coordinates[0] > gateReferenceAnchorFeatures[index - 1].geometry.coordinates[0]), 'gate reference anchors must run west to east');
  assert(
    gatePhotoVisibleEndpointAuthority?.type === 'FeatureCollection'
      && gatePhotoVisibleEndpointAuthority?.properties?.status
        === 'all_16_photo_visible_gate_endpoints_user_approved_coordinate_authority',
    'photo-visible endpoint authority status changed',
  );
  assert(
    gatePhotoVisibleEndpointAuthority?.properties?.physicalMeshUseAuthorized === false,
    'photo-visible endpoints cannot authorize physical mesh use',
  );
  assert(
    gatePhotoVisibleEndpointFeatures?.length === 8
      && gatePhotoVisibleEndpointFeatures.every((feature, index) => (
        feature.properties.gate_no === index + 1
        && feature.properties.status === 'user_approved_coordinate_authority_no_physical_mesh_use_yet'
        && feature.properties.endpointApproval === 'both_west_and_east_approved'
        && feature.geometry?.type === 'LineString'
        && feature.geometry.coordinates.length === 2
        && feature.geometry.coordinates.every(coordinate => (
          coordinate.length === 2 && coordinate.every(Number.isFinite)
        ))
      )),
    'photo-visible endpoint authority must contain eight approved two-endpoint spans',
  );
  const fishwayFeature = fishwayFeatures[0];
  assert(fishwayFeature.geometry?.type === 'Point'
    && fishwayFeature.geometry.coordinates.length === 2
    && fishwayFeature.geometry.coordinates.every(Number.isFinite), 'provided fishway coordinate is invalid');
  const gateReferenceAnchors = Object.freeze(gateReferenceAnchorFeatures.map(feature => Object.freeze({
    gate: feature.properties.gate_no,
    longitude: feature.geometry.coordinates[0],
    latitude: feature.geometry.coordinates[1],
    isExactGeometricCenter: false,
    physicalEndpointDerivationAuthorized: false,
  })));
  const gatePhotoVisibleSpans = Object.freeze(gatePhotoVisibleEndpointFeatures.map(feature => Object.freeze({
    gate: feature.properties.gate_no,
    classification: 'photo_visible_review_overlay_only',
    physicalMeshUseAuthorized: false,
    coordinates: Object.freeze(feature.geometry.coordinates.map(coordinate => Object.freeze({
      longitude: coordinate[0],
      latitude: coordinate[1],
    }))),
  })));
  const fishwayCenter = Object.freeze({
    longitude: fishwayFeature.geometry.coordinates[0],
    latitude: fishwayFeature.geometry.coordinates[1],
  });

  options.onProgress?.('synthesis');
  const workerResult = await runSynthesisWorker({
    workerUrl,
    responseManifestUrl,
    inputs,
    signal,
  });
  assert(workerResult.responsePackStatus === responseManifest.status, 'worker response-pack status mismatch');
  assert(workerResult.responsePackVersion === responseManifest.version, 'worker response-pack version mismatch');
  assert(workerResult.responsePackSha256 === responseManifest.binary.sha256, 'worker response-pack digest mismatch');
  assert(workerResult.meshSha256 === mesh.manifest.binary.sha256, 'worker mesh digest mismatch');
  assert(workerResult.snapshotCount === inputs.hours.length, 'worker snapshot count mismatch');
  assert(workerResult.hourRange?.[0] === -12 && workerResult.hourRange?.[1] === 24, 'worker hour range mismatch');
  assert(workerResult.intervalHours === 1, 'worker hour interval mismatch');
  assert(workerResult.cellCount === mesh.manifest.counts.cells, 'worker cell count mismatch');
  assert(workerResult.fields instanceof Float32Array, 'worker did not transfer Float32 fields');

  const componentCount = responseManifest.componentOrder.length;
  const expectedLength = inputs.hours.length * componentCount * mesh.manifest.counts.cells;
  assert(workerResult.fields.length === expectedLength, 'worker field length mismatch');
  assert(workerResult.outputBytes === expectedLength * Float32Array.BYTES_PER_ELEMENT, 'worker output byte length mismatch');
  assert(workerResult.outputSha256 === EXPECTED_OUTPUT_SHA256, 'synthetic output identity changed');
  assert(workerResult.diagnostics?.nonFiniteValueCount === 0, 'worker output contains a non-finite value');
  for (const key of ['minimumDepthM', 'maximumDepthM', 'maximumSpeedMPS']) {
    assert(Number.isFinite(workerResult.diagnostics?.[key]), `worker diagnostic ${key} is invalid`);
  }

  const cellCount = mesh.manifest.counts.cells;
  const snapshotStride = componentCount * cellCount;
  const fields = workerResult.fields;
  const displayInputs = Object.freeze(Object.fromEntries(
    ['hours', 'tideRelativeM', 'barrageOpeningFraction', 'ongaDischargeM3S'].map(key => [key, Object.freeze([...inputs[key]])]),
  ));
  const snapshot = index => {
    assert(Number.isInteger(index) && index >= 0 && index < inputs.hours.length, 'snapshot index is invalid');
    const start = index * snapshotStride;
    return Object.freeze({
      index,
      hour: inputs.hours[index],
      depthM: fields.subarray(start, start + cellCount),
      eastVelocityMPS: fields.subarray(start + cellCount, start + 2 * cellCount),
      northVelocityMPS: fields.subarray(start + 2 * cellCount, start + 3 * cellCount),
    });
  };

  return Object.freeze({
    schema: STAGE20_GUI_DATA_SCHEMA,
    metadata: Object.freeze({
      sourceStatus: responseManifest.status,
      sourceLabel: '合成データ',
      interpretation: '表示・操作確認用。観測値、物理予測、釣行判断ではありません。',
      runtimeCapabilityContractSchema: runtimeCapabilities.contract.schema,
      runtimeCapabilityContractStatus: runtimeCapabilities.contract.status,
      hours: Object.freeze([...inputs.hours]),
      componentOrder: Object.freeze([...responseManifest.componentOrder]),
      cellCount,
      snapshotCount: inputs.hours.length,
      meshSha256: mesh.manifest.binary.sha256,
      responsePackSha256: responseManifest.binary.sha256,
      responsePackVersion: responseManifest.version,
      guiIntegrationManifestSha256: EXPECTED_GUI_INTEGRATION_MANIFEST_SHA256,
      guiIntegrationStatus: guiIntegrationManifest.status,
      guiIntegrationState: guiIntegrationManifest.guiIntegrationContract.integrationState,
      runtimeBindingCount: guiIntegrationManifest.guiIntegrationContract.runtimeConsumedBindingIds.length,
      offlineValidationRequiredForAllBindings:
        guiIntegrationManifest.guiIntegrationContract.offlineValidationRequiredForAllBindings,
      readinessGuiIntegrationSha256: EXPECTED_READINESS_GUI_INTEGRATION_SHA256,
      readinessGuiIntegrationStatus: readinessGuiIntegrationManifest.status,
      readinessGuiIntegrationState: readinessGuiIntegrationManifest.integrationContract.state,
      readinessRuntimeBindingCount:
        readinessGuiIntegrationManifest.integrationContract.runtimeConsumedBindingIds.length,
      contractRecoveryGuiIntegrationSha256:
        EXPECTED_CONTRACT_RECOVERY_GUI_INTEGRATION_SHA256,
      contractRecoveryGuiIntegrationStatus:
        contractRecoveryGuiIntegrationManifest.status,
      contractRecoveryGuiIntegrationState:
        contractRecoveryGuiIntegrationManifest.integrationContract.state,
      contractRecoveryOfflineBindingCount:
        contractRecoveryGuiIntegrationManifest.integrationContract
          .offlineValidatedBindingIds.length,
      contractRecoveryLazyDownloadBindingCount:
        contractRecoveryGuiIntegrationManifest.integrationContract
          .lazyVerifiedDownloadBindingIds.length,
      contractAuditStatus: contractRecovery.display.audit.status,
      contractAuditSelectedJsonDocuments:
        contractRecovery.display.audit.selectedJsonDocuments,
      contractAuditRecoveryDocuments:
        contractRecovery.display.audit.recoveryDocuments,
      contractAuditRecognizableBindingsChecked:
        contractRecovery.display.audit.recognizableBindingsChecked,
      contractAuditErrorCount: contractRecovery.display.audit.errorCount,
      contractAuditWarningCount: contractRecovery.display.audit.warningCount,
      contractAuditWarningExternal:
        contractRecovery.display.audit.warningBreakdown.externalReferencesNotBundled,
      contractAuditWarningMissing:
        contractRecovery.display.audit.warningBreakdown.referencedFilesMissing,
      contractAuditWarningDigest:
        contractRecovery.display.audit.warningBreakdown.referencedSha256Mismatch,
      contractAuditWarningByteLength:
        contractRecovery.display.audit.warningBreakdown.referencedByteLengthMismatch,
      contractAuditWarningFormat:
        contractRecovery.display.audit.warningBreakdown.rootSchemaIdentifierMissing
        + contractRecovery.display.audit.warningBreakdown.sha256ShapeInvalid,
      recoveryBundleVerificationStatus:
        contractRecovery.display.recovery.bundleVerificationStatus,
      recoveryBundleDocumentEntriesChecked:
        contractRecovery.display.recovery.documentEntriesChecked,
      recoveryBundleZipEntryCount:
        contractRecovery.display.recovery.zipEntryCount,
      recoveryBundleByteLength:
        contractRecovery.display.recovery.bundleByteLength,
      physicalValidationPlanStatus:
        contractRecovery.display.physicalValidation.status,
      physicalValidationLabelJa:
        contractRecovery.display.physicalValidation.labelJa,
      physicalValidationDecisionRequiredNow:
        contractRecovery.display.physicalValidation.decisionRequiredNow,
      readinessPackageSha256: readinessPackageBinding.sha256,
      readinessTaskCount: parallelReadiness.completion.taskCount,
      readinessCompletedTaskCount: parallelReadiness.completion.completedTaskCount,
      readinessCheckCount: parallelReadiness.completion.checkCount,
      readinessPassedCheckCount: parallelReadiness.completion.passedCheckCount,
      readinessRecoveryBindingCount: parallelReadiness.completion.recoveryBindingCount,
      readinessBinaryPatternCount: parallelReadiness.completion.binaryPatternCount,
      boundaryImpactClassification: parallelReadiness.boundary.classification,
      boundaryChangedPixelCount: parallelReadiness.boundary.changedPixelCount,
      boundaryChangedMeshCentroidMembershipCount:
        parallelReadiness.boundary.changedHistoricalMeshCentroidMembershipCount,
      boundaryHistoricalPackReusable:
        parallelReadiness.boundary.existingHistoricalPackReusableAfterBoundaryAdoption,
      formalR20PrecomputationExists: parallelReadiness.formalR20.precomputationExists,
      formalR20RecalculationRequiredNow: parallelReadiness.formalR20.recalculationRequiredNow,
      formalR20FirstPrecomputationRequired:
        parallelReadiness.formalR20.firstPrecomputationRequiredAfterProductionMeshSelection,
      binaryGateTrainingBasisCount: parallelReadiness.individualGates.binaryTrainingBasisCount,
      binaryGateInteractionHoldoutCount:
        parallelReadiness.individualGates.binaryInteractionHoldoutCount,
      continuousGateAxisBasisCount: parallelReadiness.individualGates.continuousAxisBasisCount,
      continuousGateInteractionHoldoutCount:
        parallelReadiness.individualGates.continuousInteractionHoldoutCount,
      globalFiftyPercentStatus: parallelReadiness.individualGates.globalFiftyPercentStatus,
      gateInputDrivesDisplayedFlow: parallelReadiness.individualGates.gateInputDrivesDisplayedFlow,
      checkpointSegmentDurationHours: parallelReadiness.checkpoint.segmentDurationHours,
      checkpointSegmentCountPerBasis: parallelReadiness.checkpoint.segmentCountPerBasis,
      checkpointRestartStateCountPerBasis: parallelReadiness.checkpoint.restartStateCountPerBasis,
      checkpointDisplaySnapshotCountPerBasis:
        parallelReadiness.checkpoint.displaySnapshotCountPerBasis,
      currentFlowProvenanceClassification:
        parallelReadiness.provenance.currentFlowClassification,
      currentFlowProvenanceLabelJa: parallelReadiness.provenance.currentFlowLabelJa,
      fishwayGeometrySha256: EXPECTED_FISHWAY_GEOMETRY_SHA256,
      gateReferenceAnchorAuthoritySha256: anchorBinding.sha256,
      gateReferenceAnchorSemantics: 'reference_anchor_not_exact_geometric_center',
      gateReferenceAnchorApprovedCount: guiIntegration.gates.referenceAnchors.approvedCount,
      gatePhotoVisibleEndpointAuthoritySha256: photoEndpointBinding.sha256,
      gatePhotoVisibleSpanApprovedCount: guiIntegration.gates.photoVisibleEndpoints.approvedGateSpanCount,
      gatePhotoVisibleEndpointApprovedCount: guiIntegration.gates.photoVisibleEndpoints.approvedEndpointCount,
      gatePhotoVisibleEndpointGuiRole: guiIntegration.gates.photoVisibleEndpoints.guiRole,
      gatePhotoVisibleEndpointPhysicalMeshUseAuthorized:
        guiIntegration.gates.photoVisibleEndpoints.physicalMeshUseAuthorized,
      mainGateModelOpeningWidthM: guiIntegration.gates.hydraulicWidth.effectiveWidthMPerGate,
      mainGateModelWidthPolicyId: guiIntegration.gates.hydraulicWidth.policyId,
      mainGateModelWidthIsGeographicPositionLine: false,
      mainGatePhysicalMeshSelected: guiIntegration.gates.physicalAdoption.productionMeshSelected,
      mainGateSolverConnected: guiIntegration.gates.physicalAdoption.solverConnected,
      mainGateResponsePackConnected: guiIntegration.gates.physicalAdoption.responsePackConnected,
      mainGatePrecomputationAuthorized: guiIntegration.gates.physicalAdoption.precomputationAuthorized,
      fishwayOperationalSemantics: guiIntegration.fishway.operationalSemantics,
      fishwayUserControllable: guiIntegration.fishway.userControllable,
      fishwayPhysicalRepresentationAdopted: guiIntegration.fishway.physicalRepresentationAdopted,
      formalR20ReviewMeshCellCount: guiIntegration.products.formalR20ReviewMesh.cellCount,
      formalR20ReviewMeshWithCurrentSyntheticResponsePack:
        guiIntegration.products.compatibility.formalR20ReviewMeshWithCurrentSyntheticResponsePack,
      fishwayPositionSource: 'user_provided_coordinate',
    }),
    guiIntegrationManifest: Object.freeze(guiIntegrationManifest),
    runtimeCapabilities,
    readinessGuiIntegrationManifest: Object.freeze(readinessGuiIntegrationManifest),
    contractRecoveryGuiIntegrationManifest: Object.freeze(
      contractRecoveryGuiIntegrationManifest,
    ),
    contractRecovery,
    parallelReadiness,
    fieldGateObservationSchema: Object.freeze(fieldGateObservationSchema),
    resultProvenanceSchema: Object.freeze(resultProvenanceSchema),
    mesh,
    responseManifest: Object.freeze(responseManifest),
    inputs: displayInputs,
    waterManifest: Object.freeze(waterManifest),
    gateReferenceAnchors,
    gatePhotoVisibleSpans,
    fishwayCenter,
    diagnostics: Object.freeze(workerResult.diagnostics),
    timingsMs: Object.freeze(workerResult.timingsMs),
    snapshot,
  });
}
