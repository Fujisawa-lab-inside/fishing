export const STAGE16_GOVERNING_EQUATION_DECISION_VERSION = 'stage16-governing-equation-decision-v1';

const OBJECTIVES = Object.freeze([
  'mass_conservation',
  'bidirectional_tidal_flow',
  'two_dimensional_velocity_vector',
  'tributary_confluence_interaction',
  'barrage_and_fishway_transfer',
  'water_level_propagation',
  'wetting_and_drying',
]);

const CANDIDATES = Object.freeze([
  Object.freeze({
    id: 'scalar_conservative_skeleton',
    label: 'Scalar conservative potential or transport skeleton',
    capabilities: Object.freeze({
      mass_conservation: true,
      bidirectional_tidal_flow: true,
      two_dimensional_velocity_vector: false,
      tributary_confluence_interaction: 'indirect',
      barrage_and_fishway_transfer: true,
      water_level_propagation: 'diffusive_proxy',
      wetting_and_drying: false,
    }),
    physicalMeaning: 'A scalar potential or transported quantity with conservative face exchange．It is suitable for algebra，connectivity，and relative-flow diagnostics but does not solve horizontal momentum．',
    requiredData: Object.freeze([
      'mesh geometry',
      'scalar boundary values or fluxes',
      'interface transfer laws',
    ]),
    advantages: Object.freeze([
      'lower computational cost',
      'simpler boundary calibration',
      'robust diagnostic baseline',
      'useful as a regression and sanity-check model',
    ]),
    limitations: Object.freeze([
      'cannot produce a physically complete two-component velocity vector',
      'does not represent shallow-water momentum or gravity-wave propagation',
      'cannot independently predict wetting and drying',
      'directional current patterns may be imposed indirectly by boundary and conductance choices',
    ]),
  }),
  Object.freeze({
    id: 'depth_averaged_shallow_water',
    label: 'Two-dimensional depth-averaged shallow-water equations',
    capabilities: Object.freeze({
      mass_conservation: true,
      bidirectional_tidal_flow: true,
      two_dimensional_velocity_vector: true,
      tributary_confluence_interaction: true,
      barrage_and_fishway_transfer: true,
      water_level_propagation: true,
      wetting_and_drying: true,
    }),
    physicalMeaning: 'A conservative depth-averaged free-surface and horizontal-momentum model with state variables h，hu，and hv．',
    requiredData: Object.freeze([
      'audited unstructured mesh',
      'bathymetry or bed elevation',
      'Manning roughness or another friction law',
      'water-level and discharge boundary series',
      'barrage and fishway structure parameters',
      'initial water level and velocity state',
    ]),
    advantages: Object.freeze([
      'resolves two-component velocity and flow-direction reversal',
      'represents tributary momentum interaction and tidal propagation',
      'supports wetting and drying',
      'supports physically interpretable structure and friction terms',
    ]),
    limitations: Object.freeze([
      'requires bathymetry and roughness that are not yet approved',
      'requires more stringent stability and positivity treatment',
      'has higher computational cost and a larger physical Validation burden',
      'depth-averaging omits vertical stratification and three-dimensional circulation',
    ]),
  }),
]);

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-equation-decision] ${message}`);
}

function nonempty(value, label) {
  const text = String(value ?? '').trim();
  if (!text) throw new TypeError(`${label} must be nonempty`);
  return text;
}

function normaliseObjectiveWeights(objectiveWeights = {}) {
  const result = {};
  for (const objective of OBJECTIVES) {
    const value = objectiveWeights[objective] === undefined ? 1 : Number(objectiveWeights[objective]);
    assert(Number.isFinite(value) && value >= 0, `objective weight ${objective} must be finite and nonnegative`);
    result[objective] = value;
  }
  assert(Object.values(result).some(value => value > 0), 'at least one objective weight must be positive');
  return Object.freeze(result);
}

function capabilityScore(capability) {
  if (capability === true) return 1;
  if (capability === 'indirect' || capability === 'diffusive_proxy') return 0.35;
  return 0;
}

function evaluateCandidate(candidate, weights) {
  const objectiveRows = OBJECTIVES.map(objective => {
    const capability = candidate.capabilities[objective];
    const score = capabilityScore(capability);
    const weight = weights[objective];
    return Object.freeze({ objective, capability, weight, weightedScore: weight * score });
  });
  const weightedMaximum = objectiveRows.reduce((sum, row) => sum + row.weight, 0);
  const weightedScore = objectiveRows.reduce((sum, row) => sum + row.weightedScore, 0);
  const unmetObjectives = objectiveRows
    .filter(row => row.weight > 0 && row.weightedScore === 0)
    .map(row => row.objective);
  const partialObjectives = objectiveRows
    .filter(row => row.weight > 0 && row.weightedScore > 0 && row.weightedScore < row.weight)
    .map(row => row.objective);
  return Object.freeze({
    id: candidate.id,
    label: candidate.label,
    suitabilityFraction: weightedScore / weightedMaximum,
    objectiveRows: Object.freeze(objectiveRows),
    unmetObjectives: Object.freeze(unmetObjectives),
    partialObjectives: Object.freeze(partialObjectives),
    physicalMeaning: candidate.physicalMeaning,
    requiredData: candidate.requiredData,
    advantages: candidate.advantages,
    limitations: candidate.limitations,
  });
}

function validateEvidence(evidence = {}) {
  const names = [
    'approvedWaterAuthorityReady',
    'productionMeshAudited',
    'scalarSyntheticBenchmarksPassed',
    'shallowWaterSyntheticBenchmarksPassed',
    'bathymetryApproved',
    'roughnessApproved',
    'boundaryInputsApproved',
    'structureParametersApproved',
  ];
  return Object.freeze(Object.fromEntries(names.map(name => [name, evidence[name] === true])));
}

export function buildGoverningEquationDecisionPacket({
  objectiveWeights = {},
  evidence = {},
  currentSelection = null,
} = {}) {
  const weights = normaliseObjectiveWeights(objectiveWeights);
  const validatedEvidence = validateEvidence(evidence);
  const candidates = CANDIDATES.map(candidate => evaluateCandidate(candidate, weights));
  const ranked = [...candidates].sort((left, right) => right.suitabilityFraction - left.suitabilityFraction);
  const recommendation = ranked[0].id;
  const recommendationReason = recommendation === 'depth_averaged_shallow_water'
    ? 'The stated objectives include a two-component velocity field，tidal reversal，tributary momentum interaction，free-surface propagation，and wetting or drying．These capabilities require the depth-averaged shallow-water candidate rather than the scalar skeleton．'
    : 'The selected objectives do not require horizontal momentum or wetting and drying，so the scalar conservative skeleton is the lower-complexity candidate．';

  const dataGaps = [];
  if (!validatedEvidence.productionMeshAudited) dataGaps.push('audited production mesh');
  if (!validatedEvidence.bathymetryApproved) dataGaps.push('approved bathymetry');
  if (!validatedEvidence.roughnessApproved) dataGaps.push('approved roughness model');
  if (!validatedEvidence.boundaryInputsApproved) dataGaps.push('approved M，N，O，and G physical inputs');
  if (!validatedEvidence.structureParametersApproved) dataGaps.push('approved barrage and fishway parameters');

  const physicalValidationReady = recommendation === 'depth_averaged_shallow_water'
    ? validatedEvidence.approvedWaterAuthorityReady
      && validatedEvidence.productionMeshAudited
      && validatedEvidence.shallowWaterSyntheticBenchmarksPassed
      && validatedEvidence.bathymetryApproved
      && validatedEvidence.roughnessApproved
      && validatedEvidence.boundaryInputsApproved
      && validatedEvidence.structureParametersApproved
    : validatedEvidence.approvedWaterAuthorityReady
      && validatedEvidence.productionMeshAudited
      && validatedEvidence.scalarSyntheticBenchmarksPassed
      && validatedEvidence.boundaryInputsApproved
      && validatedEvidence.structureParametersApproved;

  if (currentSelection !== null) {
    const selection = nonempty(currentSelection, 'currentSelection');
    assert(CANDIDATES.some(candidate => candidate.id === selection), `unsupported current selection ${selection}`);
  }

  return Object.freeze({
    schema: 'onga-stage16-governing-equation-decision-packet-v1',
    version: STAGE16_GOVERNING_EQUATION_DECISION_VERSION,
    objectiveWeights: weights,
    evidence: validatedEvidence,
    candidates: Object.freeze(candidates),
    recommendation,
    recommendationReason,
    currentSelection,
    selectionApproved: false,
    physicalValidationReady,
    publicProductionReady: false,
    dataGaps: Object.freeze(dataGaps),
    decisionOptions: Object.freeze([
      Object.freeze({
        id: 'adopt_depth_averaged_shallow_water_for_validation',
        governingEquation: 'depth_averaged_shallow_water',
        consequence: 'Continue toward physical Validation after approved bathymetry，roughness，boundary data，and structure parameters are supplied．',
      }),
      Object.freeze({
        id: 'retain_scalar_skeleton_for_diagnostics',
        governingEquation: 'scalar_conservative_skeleton',
        consequence: 'Use the scalar model only for conservative diagnostics and relative patterns，without claiming a complete physical velocity field．',
      }),
      Object.freeze({
        id: 'continue_dual_track_without_selection',
        governingEquation: null,
        consequence: 'Continue synthetic Verification of both tracks and defer physical data acquisition and production integration．',
      }),
    ]),
    humanDecisionRequired: true,
    note: 'The recommendation is not an approval．No governing equation is selected until an explicit human decision is recorded．',
  });
}

export function recordGoverningEquationDecision(packet, decision) {
  assert(packet?.schema === 'onga-stage16-governing-equation-decision-packet-v1', 'packet schema mismatch');
  const optionId = nonempty(decision?.optionId, 'decision.optionId');
  const option = packet.decisionOptions.find(entry => entry.id === optionId);
  assert(option, `unknown decision option ${optionId}`);
  const approvedBy = nonempty(decision?.approvedBy, 'decision.approvedBy');
  const approvedAt = nonempty(decision?.approvedAt, 'decision.approvedAt');
  assert(Number.isFinite(Date.parse(approvedAt)), 'decision.approvedAt must be an ISO-8601 timestamp');
  return Object.freeze({
    ...packet,
    currentSelection: option.governingEquation,
    selectionApproved: true,
    humanDecisionRequired: false,
    recordedDecision: Object.freeze({ optionId, approvedBy, approvedAt, notes: decision.notes ?? null }),
  });
}

export const Stage16GoverningEquationDecision = Object.freeze({
  version: STAGE16_GOVERNING_EQUATION_DECISION_VERSION,
  objectives: OBJECTIVES,
  candidates: CANDIDATES,
  buildGoverningEquationDecisionPacket,
  recordGoverningEquationDecision,
});
