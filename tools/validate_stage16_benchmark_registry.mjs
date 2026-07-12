import fs from 'node:fs/promises';
import {
  DEFAULT_STAGE16_BENCHMARK_REGISTRY,
  STAGE16_BENCHMARK_REGISTRY_VERSION,
  evaluateBenchmarkRegistry,
  validateBenchmarkRegistry,
} from '../onga_stage16_benchmark_registry.mjs';

const outputPath = process.argv[2] || 'stage16-benchmark-registry-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function result(metrics, id) {
  return {
    purpose: 'synthetic_verification',
    resultsLabel: 'synthetic_verification_only',
    scenarioHash: `fnv1a32:${id.padEnd(8, '0').slice(0, 8)}`,
    codeCommit: '0123456789abcdef0123456789abcdef01234567',
    metrics,
  };
}

const passingResults = {
  mesh_topology_integrity: result({ failedChecks: 0, connectedComponents: 1 }, 'mesh'),
  constant_field_preservation: result({ maxError: 1e-13, residualInfinityNorm: 2e-13 }, 'const'),
  closed_domain_mass_conservation: result({ relativeMassError: 3e-13 }, 'mass'),
  boundary_reversal_symmetry: result({ fieldSymmetryError: 5e-13, fluxAntisymmetryError: 4e-13 }, 'revr'),
  interface_complete_closure: result({ closedInterfaceFlux: 0 }, 'clos'),
  lake_at_rest_variable_bed: result({ maximumResidual: 4e-13, minimumDepth: 0 }, 'lake'),
  dry_bed_dam_break: result({ minimumDepth: 0, relativeMassError: 4e-8, frontNormalizedError: 0.012 }, 'damb'),
  linear_standing_wave: result({ observedOrder: 1.96, relativeMassError: 8e-10, amplitudeRelativeError: 0.018 }, 'wave'),
  manning_uniform_flow: result({ normalDepthRelativeError: 2e-8, directionErrorRadians: 1e-13 }, 'mann'),
  structure_head_reversal: result({ antisymmetryError: 3e-13, conservationError: 0 }, 'stru'),
};

const shallowEvaluation = evaluateBenchmarkRegistry({
  results: passingResults,
  track: 'shallow_water_candidate',
});
const scalarEvaluation = evaluateBenchmarkRegistry({
  results: passingResults,
  track: 'scalar_skeleton',
});
const missingResults = structuredClone(passingResults);
delete missingResults.linear_standing_wave;
const missingEvaluation = evaluateBenchmarkRegistry({
  results: missingResults,
  track: 'shallow_water_candidate',
});
const failedResults = structuredClone(passingResults);
failedResults.dry_bed_dam_break.metrics.frontNormalizedError = 0.2;
const failedEvaluation = evaluateBenchmarkRegistry({
  results: failedResults,
  track: 'shallow_water_candidate',
});
const invalidResults = structuredClone(passingResults);
invalidResults.manning_uniform_flow.purpose = 'physical_validation';
const invalidEvaluation = evaluateBenchmarkRegistry({
  results: invalidResults,
  track: 'shallow_water_candidate',
});

let duplicateRejected = false;
try {
  validateBenchmarkRegistry([
    ...DEFAULT_STAGE16_BENCHMARK_REGISTRY,
    structuredClone(DEFAULT_STAGE16_BENCHMARK_REGISTRY[0]),
  ]);
} catch (_) {
  duplicateRejected = true;
}

let operatorRejected = false;
try {
  const registry = structuredClone(DEFAULT_STAGE16_BENCHMARK_REGISTRY);
  registry[0].criteria[0].operator = 'approximately';
  validateBenchmarkRegistry(registry);
} catch (_) {
  operatorRejected = true;
}

let unsupportedTrackRejected = false;
try {
  evaluateBenchmarkRegistry({ results: passingResults, track: 'three_dimensional_navier_stokes' });
} catch (_) {
  unsupportedTrackRejected = true;
}

const failedFront = failedEvaluation.evaluations.find(entry => entry.id === 'dry_bed_dam_break');
const missingWave = missingEvaluation.evaluations.find(entry => entry.id === 'linear_standing_wave');
const invalidManning = invalidEvaluation.evaluations.find(entry => entry.id === 'manning_uniform_flow');

const checks = [
  check('registry validates', validateBenchmarkRegistry().length,
    DEFAULT_STAGE16_BENCHMARK_REGISTRY.length,
    validateBenchmarkRegistry().length === DEFAULT_STAGE16_BENCHMARK_REGISTRY.length),
  check('shallow-water track passes', shallowEvaluation.status, 'passed',
    shallowEvaluation.syntheticTrackReady && shallowEvaluation.status === 'passed'),
  check('shallow-water required count', shallowEvaluation.counts.required, 10,
    shallowEvaluation.counts.required === 10),
  check('scalar track passes', scalarEvaluation.status, 'passed',
    scalarEvaluation.syntheticTrackReady && scalarEvaluation.status === 'passed'),
  check('scalar required count', scalarEvaluation.counts.required, 5,
    scalarEvaluation.counts.required === 5),
  check('physical readiness remains false', shallowEvaluation.physicalValidationReady, false,
    shallowEvaluation.physicalValidationReady === false),
  check('public readiness remains false', shallowEvaluation.publicProductionReady, false,
    shallowEvaluation.publicProductionReady === false),
  check('missing result prevents readiness', missingEvaluation.status, 'incomplete_or_failed',
    !missingEvaluation.syntheticTrackReady && missingEvaluation.counts.missing === 1),
  check('missing wave identified', missingWave?.status, 'missing', missingWave?.status === 'missing'),
  check('threshold failure prevents readiness', failedEvaluation.status, 'incomplete_or_failed',
    !failedEvaluation.syntheticTrackReady && failedEvaluation.counts.failed === 1),
  check('front threshold failure identified', failedFront?.status, 'failed', failedFront?.status === 'failed'),
  check('invalid provenance prevents readiness', invalidEvaluation.status, 'incomplete_or_failed',
    !invalidEvaluation.syntheticTrackReady && invalidEvaluation.counts.invalid === 1),
  check('invalid Manning provenance identified', invalidManning?.status, 'invalid',
    invalidManning?.status === 'invalid'),
  check('duplicate registry id rejected', duplicateRejected, true, duplicateRejected),
  check('unsupported operator rejected', operatorRejected, true, operatorRejected),
  check('unsupported track rejected', unsupportedTrackRejected, true, unsupportedTrackRejected),
  check('registry version', shallowEvaluation.registryVersion, STAGE16_BENCHMARK_REGISTRY_VERSION,
    shallowEvaluation.registryVersion === STAGE16_BENCHMARK_REGISTRY_VERSION),
];

const report = {
  schema: 'onga-stage16-benchmark-registry-validation-v1',
  moduleVersion: STAGE16_BENCHMARK_REGISTRY_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    connectedToPublicSimulator: false,
    usesRealOngaData: false,
    modifiesApprovedWaterGeometry: false,
    grantsPhysicalApproval: false,
    grantsPublicApproval: false,
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
