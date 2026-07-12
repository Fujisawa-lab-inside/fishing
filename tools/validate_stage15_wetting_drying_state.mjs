import fs from 'node:fs/promises';
import {
  regulariseWetDryState,
  updateWetDryFlags,
  wetCellMaskToIndices,
} from '../onga_stage15_wetting_drying_state.mjs';

const outputPath = process.argv[2] || 'stage15-wet-dry-validation.json';
const tolerance = 1e-12;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function maxAbs(values) {
  return Math.max(...values.map(value => Math.abs(Number(value))));
}

function arrayError(left, right) {
  return Math.max(...left.map((value, index) => Math.abs(Number(value) - Number(right[index]))));
}

const initial = updateWetDryFlags({
  depths: [0.0009, 0.001, 0.002],
  wetThreshold: 0.001,
  dryThreshold: 0.0005,
});
const initialError = arrayError([...initial.wet], [0, 1, 1]);

const hysteresis = updateWetDryFlags({
  depths: [0.0007, 0.0007],
  previousWet: [1, 0],
  wetThreshold: 0.001,
  dryThreshold: 0.0005,
});
const hysteresisError = arrayError([...hysteresis.wet], [1, 0]);

const deactivate = updateWetDryFlags({
  depths: [0.0005, 0.00049],
  previousWet: [1, 1],
  wetThreshold: 0.001,
  dryThreshold: 0.0005,
});
const deactivationError = arrayError([...deactivate.wet], [0, 0]);

let sequenceFlags = new Uint8Array([0]);
let sequenceTransitions = 0;
for (const depth of [0.0007, 0.0008, 0.0006, 0.0009]) {
  const result = updateWetDryFlags({
    depths: [depth],
    previousWet: sequenceFlags,
    wetThreshold: 0.001,
    dryThreshold: 0.0005,
  });
  sequenceTransitions += result.newlyWet[0] + result.newlyDry[0];
  sequenceFlags = result.wet;
}
const dryBandNoChatter = sequenceTransitions === 0 && sequenceFlags[0] === 0;
for (const depth of [0.0011, 0.0008, 0.0006, 0.0004]) {
  const result = updateWetDryFlags({
    depths: [depth],
    previousWet: sequenceFlags,
    wetThreshold: 0.001,
    dryThreshold: 0.0005,
  });
  sequenceTransitions += result.newlyWet[0] + result.newlyDry[0];
  sequenceFlags = result.wet;
}
const activationDeactivationCount = sequenceTransitions;

const regularised = regulariseWetDryState({
  state: {
    h: [0.0004, 1, 0.00075],
    hu: [9, 2, 0.075],
    hv: [-7, 1, 0.1],
  },
  previousWet: [0, 1, 1],
  areas: [2, 3, 4],
  wetThreshold: 0.001,
  dryThreshold: 0.0005,
  velocityDepth: 0.001,
  maxSpeed: 2,
});
const dryResetError = maxAbs([
  regularised.state.h[0],
  regularised.state.hu[0],
  regularised.state.hv[0],
]);
const safeWetError = maxAbs([
  regularised.state.h[1] - 1,
  regularised.state.hu[1] - (2 / Math.sqrt(5) * 2),
  regularised.state.hv[1] - (1 / Math.sqrt(5) * 2),
]);
const nearDrySpeed = Math.hypot(
  regularised.state.hu[2] / regularised.state.h[2],
  regularised.state.hv[2] / regularised.state.h[2],
);
const originalDirection = Math.atan2(0.1, 0.075);
const regularisedDirection = Math.atan2(regularised.state.hv[2], regularised.state.hu[2]);
const directionError = Math.abs(regularisedDirection - originalDirection);
const removedVolumeError = Math.abs(regularised.diagnostics.removedVolume - 0.0004 * 2);
const removalBoundSatisfied = regularised.diagnostics.removedVolume
  <= regularised.diagnostics.maximumPossibleThresholdRemoval + tolerance;

let invalidThresholdRejected = false;
try {
  updateWetDryFlags({ depths: [1], wetThreshold: 0.001, dryThreshold: 0.001 });
} catch (_) {
  invalidThresholdRejected = true;
}

let negativeDepthRejected = false;
try {
  updateWetDryFlags({ depths: [-1], wetThreshold: 0.001, dryThreshold: 0.0005 });
} catch (_) {
  negativeDepthRejected = true;
}

const wetIndices = wetCellMaskToIndices(regularised.classification.wet);
const wetIndexError = arrayError([...wetIndices], [1, 2]);

const checks = [
  check('initial activation threshold', initialError, `<${tolerance}`, initialError < tolerance),
  check('hysteresis band retains prior state', hysteresisError, `<${tolerance}`, hysteresisError < tolerance),
  check('dry threshold deactivates wet cells', deactivationError, `<${tolerance}`, deactivationError < tolerance),
  check('dry-band oscillation does not chatter', dryBandNoChatter, true, dryBandNoChatter),
  check('one activation and one deactivation', activationDeactivationCount, 2, activationDeactivationCount === 2),
  check('dry cell state reset', dryResetError, `<${tolerance}`, dryResetError < tolerance),
  check('safe wet velocity capped without direction change', safeWetError, `<${tolerance}`, safeWetError < tolerance),
  check('near-dry speed cap', nearDrySpeed, '<=2', nearDrySpeed <= 2 + tolerance),
  check('near-dry direction preserved', directionError, `<${tolerance}`, directionError < tolerance),
  check('removed threshold volume diagnostic', removedVolumeError, `<${tolerance}`, removedVolumeError < tolerance),
  check('threshold removal bound', removalBoundSatisfied, true, removalBoundSatisfied),
  check('invalid threshold rejected', invalidThresholdRejected, true, invalidThresholdRejected),
  check('negative depth rejected', negativeDepthRejected, true, negativeDepthRejected),
  check('wet cell index extraction', wetIndexError, `<${tolerance}`, wetIndexError < tolerance),
];

const report = {
  schema: 'onga-stage15-wet-dry-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    initialError,
    hysteresisError,
    deactivationError,
    sequenceTransitions,
    dryResetError,
    safeWetError,
    nearDrySpeed,
    directionError,
    removedVolumeError,
    removalBoundSatisfied,
    wetIndices,
  },
  safeguards: {
    connectedToPublicSimulator: false,
    approvedWaterGeometryChanged: false,
    physicalValuesAssigned: false,
    calibrationPerformed: false,
    purpose: 'wet-dry state management verification only',
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
