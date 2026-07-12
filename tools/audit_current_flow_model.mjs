import fs from 'node:fs/promises';

const outputPath = process.argv[2] || 'current-flow-model-audit.json';
const legacyFiles = ['pc_full.html', 'mobile_lite.html', 'closed_gate_patch.js'];
const stage13Files = [
  'onga_stage13_runtime.js',
  'onga_stage13_bridge.js',
  'onga_stage13_heatmap_clip.js',
  'onga_stage13_fluid_domain_patch.js',
  'onga_stage13_bootstrap.js',
];

const symbols = [
  'hydrodynamicBoundaryFluxes',
  'boundaryPhi',
  'classifyFluidBoundary',
  'buildFluidGrid',
  'solveFluid',
  'fluidCache',
  'waterMassContributionAt',
  'fishwayInfluenceAtPoint',
];

function lineNumber(text, index) {
  return text.slice(0, index).split('\n').length;
}

function occurrences(text, token) {
  const result = [];
  let offset = 0;
  while (offset < text.length) {
    const index = text.indexOf(token, offset);
    if (index < 0) break;
    result.push(lineNumber(text, index));
    offset = index + token.length;
  }
  return result;
}

async function inspect(path) {
  const text = await fs.readFile(path, 'utf8');
  const symbolLines = Object.fromEntries(
    symbols
      .map(symbol => [symbol, occurrences(text, symbol)])
      .filter(([, lines]) => lines.length > 0),
  );
  return {
    path,
    bytes: Buffer.byteLength(text),
    lines: text.split('\n').length,
    symbolLines,
  };
}

const legacy = await Promise.all(legacyFiles.map(inspect));
const stage13 = await Promise.all(stage13Files.map(inspect));

const forbiddenStage13Assignments = [
  /hydrodynamicBoundaryFluxes\s*=/,
  /boundaryPhi\s*=/,
  /classifyFluidBoundary\s*=/,
  /waterMassContributionAt\s*=/,
  /fishwayInfluenceAtPoint\s*=/,
];

const stage13PhysicsMutations = [];
for (const file of stage13Files) {
  const text = await fs.readFile(file, 'utf8');
  for (const pattern of forbiddenStage13Assignments) {
    if (pattern.test(text)) stage13PhysicsMutations.push({ file, pattern: String(pattern) });
  }
}

const closedGateText = await fs.readFile('closed_gate_patch.js', 'utf8');
const closedGateChecks = {
  mainRiverFluxForcedToZero: closedGateText.includes('riverDown:0') && closedGateText.includes('ongaUpQ:0'),
  boundaryPotentialOverridden: closedGateText.includes('boundaryPhi = function'),
  boundaryClassificationOverridden: closedGateText.includes('classifyFluidBoundary = function'),
  hotspotScoreModified: closedGateText.includes('scoreFishingSample = function'),
};

const report = {
  schema: 'onga-current-flow-model-audit-v1',
  generatedBy: 'tools/audit_current_flow_model.mjs',
  purpose: 'Record the existing flow calculation without changing geometry, boundary values, or solver behaviour.',
  conclusion: {
    authoritativeDomainIntegrated: true,
    newUnstructuredFiniteVolumeSolverIntegratedIntoPublicSimulator: false,
    currentPublicFlowCalculationRemainsLegacy: true,
    stage13ChangesFlowPhysics: stage13PhysicsMutations.length > 0,
    interpretation: 'Stage 13 currently changes the admissible water/heatmap/fluid domain only. The public flow field still uses the pre-existing browser model and closed-gate patch.',
  },
  legacyFiles: legacy,
  stage13Files: stage13,
  stage13PhysicsMutations,
  closedGateChecks,
  invariants: {
    approvedWaterPixelsFrozen: 679791,
    doNotModifyApprovedWaterFromFlowMismatch: true,
    observationDoesNotAuthorizeCorrection: true,
    requireSeparateDiagnosisOfDisplayInputBoundaryPhysicsAndNumerics: true,
  },
};

if (stage13PhysicsMutations.length > 0) {
  throw new Error(`Stage 13 unexpectedly mutates legacy flow physics: ${JSON.stringify(stage13PhysicsMutations)}`);
}
if (!Object.values(closedGateChecks).every(Boolean)) {
  throw new Error(`closed_gate_patch.js no longer satisfies the recorded legacy behaviour: ${JSON.stringify(closedGateChecks)}`);
}

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report.conclusion, null, 2));
