import fs from 'node:fs/promises';
import {
  STAGE15_STRUCTURE_FLUX_VERSION,
  conservativeInterfaceSources,
  evaluateConservativeStructureTransfer,
  evaluateGateSet,
  evaluateStructureInterface,
  gateEffectiveArea,
  limitDischargeByAvailableVolume,
  linearHeadLossDischarge,
  orificeDischarge,
} from '../onga_stage15_structure_flux_laws.mjs';

const outputPath = process.argv[2] || 'stage15-structure-flux-validation.json';
const tolerance = 1e-12;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function maximumAbsolute(values) {
  return Math.max(...Array.from(values, value => Math.abs(Number(value))));
}

const closed = evaluateStructureInterface({ mode: 'closed' });
const zeroHead = orificeDischarge({
  leftWaterLevel: 2,
  rightWaterLevel: 2,
  effectiveArea: 3,
  dischargeCoefficient: 0.7,
});
const forward = orificeDischarge({
  leftWaterLevel: 3.2,
  rightWaterLevel: 1.7,
  effectiveArea: 2.4,
  dischargeCoefficient: 0.68,
  openingFraction: 0.6,
});
const reverse = orificeDischarge({
  leftWaterLevel: 1.7,
  rightWaterLevel: 3.2,
  effectiveArea: 2.4,
  dischargeCoefficient: 0.68,
  openingFraction: 0.6,
});
const smallerHead = orificeDischarge({
  leftWaterLevel: 2.2,
  rightWaterLevel: 1.7,
  effectiveArea: 2.4,
  dischargeCoefficient: 0.68,
  openingFraction: 0.6,
});
const halfOpen = orificeDischarge({
  leftWaterLevel: 3.2,
  rightWaterLevel: 1.7,
  effectiveArea: 2.4,
  dischargeCoefficient: 0.68,
  openingFraction: 0.3,
});
const linearForward = linearHeadLossDischarge({
  leftWaterLevel: 2.5,
  rightWaterLevel: 1.5,
  conductance: 4,
  openingFraction: 0.5,
});
const linearReverse = linearHeadLossDischarge({
  leftWaterLevel: 1.5,
  rightWaterLevel: 2.5,
  conductance: 4,
  openingFraction: 0.5,
});

const gates = evaluateGateSet({
  leftWaterLevel: 3,
  rightWaterLevel: 1,
  gates: Array.from({ length: 8 }, (_, index) => ({
    id: `gate-${index + 1}`,
    mode: index === 3 ? 'closed' : 'orifice',
    fullOpenArea: 2 + index * 0.1,
    dischargeCoefficient: 0.65,
    openingFraction: index === 3 ? 0 : (index + 1) / 8,
  })),
});
const gateSum = gates.gates.reduce(
  (sum, gate) => sum + gate.signedDischargeLeftToRight,
  0,
);

const sources = conservativeInterfaceSources({
  cellCount: 5,
  leftCell: 1,
  rightCell: 4,
  signedDischargeLeftToRight: 2.75,
});
const sourceSum = Array.from(sources).reduce((sum, value) => sum + value, 0);

const limitedForward = limitDischargeByAvailableVolume({
  signedDischargeLeftToRight: 10,
  leftAvailableVolume: 3,
  rightAvailableVolume: 8,
  dt: 0.5,
});
const limitedReverse = limitDischargeByAvailableVolume({
  signedDischargeLeftToRight: -10,
  leftAvailableVolume: 3,
  rightAvailableVolume: 2,
  dt: 0.5,
});
const transfer = evaluateConservativeStructureTransfer({
  cellCount: 2,
  leftCell: 0,
  rightCell: 1,
  specification: {
    mode: 'orifice',
    leftWaterLevel: 4,
    rightWaterLevel: 1,
    effectiveArea: 10,
    dischargeCoefficient: 0.8,
    openingFraction: 1,
  },
  leftAvailableVolume: 1.2,
  rightAvailableVolume: 9,
  dt: 0.2,
});
const transferSum = Array.from(transfer.sources).reduce((sum, value) => sum + value, 0);

const area = gateEffectiveArea({
  gateWidth: 5,
  maximumOpeningHeight: 2,
  openingFraction: 0.4,
});

let invalidOpeningRejected = false;
try {
  orificeDischarge({
    leftWaterLevel: 1,
    rightWaterLevel: 0,
    effectiveArea: 1,
    dischargeCoefficient: 0.7,
    openingFraction: 1.2,
  });
} catch (_) {
  invalidOpeningRejected = true;
}

let invalidCoefficientRejected = false;
try {
  linearHeadLossDischarge({
    leftWaterLevel: 1,
    rightWaterLevel: 0,
    conductance: -1,
  });
} catch (_) {
  invalidCoefficientRejected = true;
}

const checks = [
  check('closed structure discharge', closed.signedDischargeLeftToRight, 0,
    closed.signedDischargeLeftToRight === 0),
  check('zero-head orifice discharge', zeroHead.signedDischargeLeftToRight, 0,
    zeroHead.signedDischargeLeftToRight === 0),
  check('orifice head reversal antisymmetry',
    Math.abs(forward.signedDischargeLeftToRight + reverse.signedDischargeLeftToRight),
    `<${tolerance}`,
    Math.abs(forward.signedDischargeLeftToRight + reverse.signedDischargeLeftToRight) < tolerance),
  check('orifice magnitude monotonic with head',
    Math.abs(forward.signedDischargeLeftToRight) - Math.abs(smallerHead.signedDischargeLeftToRight),
    '>0',
    Math.abs(forward.signedDischargeLeftToRight) > Math.abs(smallerHead.signedDischargeLeftToRight)),
  check('orifice linear opening scaling',
    Math.abs(halfOpen.signedDischargeLeftToRight / forward.signedDischargeLeftToRight - 0.5),
    `<${tolerance}`,
    Math.abs(halfOpen.signedDischargeLeftToRight / forward.signedDischargeLeftToRight - 0.5) < tolerance),
  check('linear relation head reversal',
    Math.abs(linearForward.signedDischargeLeftToRight + linearReverse.signedDischargeLeftToRight),
    `<${tolerance}`,
    Math.abs(linearForward.signedDischargeLeftToRight + linearReverse.signedDischargeLeftToRight) < tolerance),
  check('eight-gate aggregation',
    Math.abs(gates.totalSignedDischargeLeftToRight - gateSum),
    `<${tolerance}`,
    Math.abs(gates.totalSignedDischargeLeftToRight - gateSum) < tolerance),
  check('closed individual gate', gates.gates[3].signedDischargeLeftToRight, 0,
    gates.gates[3].signedDischargeLeftToRight === 0),
  check('conservative interface source sum', Math.abs(sourceSum), `<${tolerance}`,
    Math.abs(sourceSum) < tolerance),
  check('conservative interface source signs',
    maximumAbsolute([sources[1] + 2.75, sources[4] - 2.75]),
    `<${tolerance}`,
    maximumAbsolute([sources[1] + 2.75, sources[4] - 2.75]) < tolerance),
  check('forward available-volume limit', limitedForward, 6,
    Math.abs(limitedForward - 6) < tolerance),
  check('reverse available-volume limit', limitedReverse, -4,
    Math.abs(limitedReverse + 4) < tolerance),
  check('limited transfer conservation', Math.abs(transferSum), `<${tolerance}`,
    Math.abs(transferSum) < tolerance),
  check('limited transfer donor volume bound',
    transfer.limitedSignedDischargeLeftToRight * 0.2,
    '<=1.2',
    transfer.limitedSignedDischargeLeftToRight * 0.2 <= 1.2 + tolerance),
  check('gate effective area', area, 4, Math.abs(area - 4) < tolerance),
  check('invalid opening rejected', invalidOpeningRejected, true, invalidOpeningRejected),
  check('negative coefficient rejected', invalidCoefficientRejected, true, invalidCoefficientRejected),
];

const report = {
  schema: 'onga-stage15-structure-flux-validation-v1',
  moduleVersion: STAGE15_STRUCTURE_FLUX_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    connectedToPublicSimulator: false,
    modifiesApprovedWaterGeometry: false,
    usesPhysicalStructureParameters: false,
    calibrationPerformed: false,
    purpose: 'synthetic verification of conservative hydraulic-structure transfer laws only',
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
