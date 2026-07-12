import fs from 'node:fs/promises';
import {
  STAGE16_BENCHMARK_METRICS_VERSION,
  assessBenchmark,
  compareFrontPosition,
  detectWettingFront,
  observedConvergenceOrders,
  relativeConservationError,
  standingWaveProjection,
  weightedErrorNorms,
} from '../onga_stage16_benchmark_metrics.mjs';

const outputPath = process.argv[2] || 'stage16-benchmark-metrics-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const norms = weightedErrorNorms({
  numerical: [1.1, 1.8, 3.3],
  reference: [1, 2, 3],
  weights: [1, 2, 1],
});
const expectedL1 = (0.1 + 2 * 0.2 + 0.3) / 4;
const expectedL2 = Math.sqrt((0.01 + 2 * 0.04 + 0.09) / 4);
const conservation = relativeConservationError({
  initial: 10,
  final: 10.5,
  expectedChange: 0.5,
});
const orders = observedConvergenceOrders({
  cellSizes: [0.2, 0.1, 0.05, 0.025],
  errors: [0.04, 0.01, 0.0025, 0.000625],
});
const coordinates = [-1, -0.5, 0, 0.5, 1, 1.5];
const depths = [1, 0.8, 0.4, 1e-9, 0, 0];
const maximumFront = detectWettingFront({ coordinates, depths, threshold: 1e-8, direction: 'maximum' });
const minimumFront = detectWettingFront({ coordinates, depths, threshold: 1e-8, direction: 'minimum' });
const noFront = detectWettingFront({ coordinates, depths: depths.map(() => 0), threshold: 1e-8 });

const length = 10;
const sampleCount = 200;
const dx = length / sampleCount;
const x = Array.from({ length: sampleCount }, (_, index) => (index + 0.5) * dx);
const trueAmplitude = 0.35;
const perturbation = x.map(value => trueAmplitude * Math.cos(Math.PI * value / length));
const projection = standingWaveProjection({
  coordinates: x,
  surfacePerturbation: perturbation,
  length,
  mode: 1,
  weights: Array(sampleCount).fill(dx),
});
const front = compareFrontPosition({
  numericalFront: 10.25,
  referenceFront: 10,
  characteristicLength: 2,
});
const assessment = assessBenchmark([
  { name: 'mass', value: conservation.relativeError, criterion: '<1e-12', ok: conservation.relativeError < 1e-12 },
  { name: 'order', value: Math.min(...orders), criterion: '>=1.9', ok: Math.min(...orders) >= 1.9 },
]);
const failedAssessment = assessBenchmark([
  { name: 'pass', value: 0, criterion: '=0', ok: true },
  { name: 'fail', value: 1, criterion: '=0', ok: false },
]);

let invalidResolutionRejected = false;
try {
  observedConvergenceOrders({ cellSizes: [0.1, 0.2], errors: [0.01, 0.02] });
} catch (_) {
  invalidResolutionRejected = true;
}

const tolerance = 1e-12;
const checks = [
  check('weighted L1', Math.abs(norms.l1 - expectedL1), `<${tolerance}`,
    Math.abs(norms.l1 - expectedL1) < tolerance),
  check('weighted L2', Math.abs(norms.l2 - expectedL2), `<${tolerance}`,
    Math.abs(norms.l2 - expectedL2) < tolerance),
  check('Linf', norms.linf, 0.3, Math.abs(norms.linf - 0.3) < tolerance),
  check('conservation residual', conservation.residual, 0, Math.abs(conservation.residual) < tolerance),
  check('second-order estimates', Math.max(...orders.map(value => Math.abs(value - 2))), `<${tolerance}`,
    orders.every(value => Math.abs(value - 2) < tolerance)),
  check('maximum wetting front', maximumFront, 0, maximumFront === 0),
  check('minimum wetting front', minimumFront, -1, minimumFront === -1),
  check('fully dry front', noFront, null, noFront === null),
  check('standing-wave amplitude projection', Math.abs(projection.amplitude - trueAmplitude), '<1e-12',
    Math.abs(projection.amplitude - trueAmplitude) < 1e-12),
  check('standing-wave weighted mean', Math.abs(projection.weightedMean), '<1e-12',
    Math.abs(projection.weightedMean) < 1e-12),
  check('front absolute error', front.absoluteError, 0.25, Math.abs(front.absoluteError - 0.25) < tolerance),
  check('front normalized error', front.normalizedError, 0.125,
    Math.abs(front.normalizedError - 0.125) < tolerance),
  check('passing assessment', assessment.status, 'passed', assessment.status === 'passed'),
  check('failing assessment', failedAssessment.status, 'failed', failedAssessment.status === 'failed'),
  check('invalid resolution order rejected', invalidResolutionRejected, true, invalidResolutionRejected),
];

const report = {
  schema: 'onga-stage16-benchmark-metrics-validation-v1',
  moduleVersion: STAGE16_BENCHMARK_METRICS_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    connectedToPublicSimulator: false,
    usesRealOngaData: false,
    modifiesApprovedWaterGeometry: false,
    calibrationPerformed: false,
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
