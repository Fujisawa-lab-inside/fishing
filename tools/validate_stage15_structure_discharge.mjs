import fs from 'node:fs/promises';
import {
  accumulateStructureTransfers,
  conservativeStructureTransfer,
  evaluateStructureDischarge,
  gateOpeningArea,
  gateOrificeDischarge,
  headOrificeDischarge,
} from '../onga_stage15_structure_discharge.mjs';

const outputPath = process.argv[2] || 'stage15-structure-discharge-validation.json';
const tolerance = 1e-12;
const gravity = 9.80665;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function sum(values) {
  return [...values].reduce((total, value) => total + Number(value), 0);
}

const forward = headOrificeDischarge({
  headA: 3,
  headB: 1,
  dischargeCoefficient: 0.6,
  area: 2,
  gravity,
});
const expectedForward = 0.6 * 2 * Math.sqrt(2 * gravity * 2);
const forwardError = Math.abs(forward.discharge - expectedForward);

const reverse = headOrificeDischarge({
  headA: 1,
  headB: 3,
  dischargeCoefficient: 0.6,
  area: 2,
  gravity,
});
const reversalError = Math.abs(reverse.discharge + forward.discharge);

const equal = headOrificeDischarge({
  headA: 2,
  headB: 2,
  dischargeCoefficient: 0.8,
  area: 4,
});

const halfArea = gateOpeningArea({ width: 4, maximumOpening: 2, openingFraction: 0.5 });
const fullGate = gateOrificeDischarge({
  headA: 3,
  headB: 1,
  dischargeCoefficient: 0.7,
  width: 4,
  maximumOpening: 2,
  openingFraction: 1,
});
const halfGate = gateOrificeDischarge({
  headA: 3,
  headB: 1,
  dischargeCoefficient: 0.7,
  width: 4,
  maximumOpening: 2,
  openingFraction: 0.5,
});
const halfGateRatioError = Math.abs(halfGate.discharge / fullGate.discharge - 0.5);
const closedGate = gateOrificeDischarge({
  headA: 3,
  headB: 1,
  dischargeCoefficient: 0.7,
  width: 4,
  maximumOpening: 2,
  openingFraction: 0,
});

const timeDependentFixed = evaluateStructureDischarge({
  mode: 'fixed_discharge',
  discharge: time => 3 * time,
  transportSpeed: time => 1 + time,
  time: 2,
});
const timeDependentGate = evaluateStructureDischarge({
  mode: 'gate_orifice',
  headA: 2,
  headB: 1,
  dischargeCoefficient: 0.5,
  width: 4,
  maximumOpening: 2,
  openingFraction: time => time / 10,
  time: 5,
});
const disabled = evaluateStructureDischarge({ mode: 'disabled' });

const positiveTransfer = conservativeStructureTransfer({
  cellCount: 3,
  cellA: 0,
  cellB: 2,
  discharge: 5,
  direction: [3, 4],
  transportSpeed: 2,
});
const positiveMassBalance = Math.abs(sum(positiveTransfer.sources.mass));
const positiveMomentumBalance = Math.max(
  Math.abs(sum(positiveTransfer.sources.momentumX)),
  Math.abs(sum(positiveTransfer.sources.momentumY)),
);
const positiveComponentError = Math.max(
  Math.abs(positiveTransfer.sources.mass[0] + 5),
  Math.abs(positiveTransfer.sources.mass[2] - 5),
  Math.abs(positiveTransfer.sources.momentumX[0] + 6),
  Math.abs(positiveTransfer.sources.momentumX[2] - 6),
  Math.abs(positiveTransfer.sources.momentumY[0] + 8),
  Math.abs(positiveTransfer.sources.momentumY[2] - 8),
);

const reverseTransfer = conservativeStructureTransfer({
  cellCount: 2,
  cellA: 0,
  cellB: 1,
  discharge: -5,
  direction: [3, 4],
  transportSpeed: 2,
});
const reverseMassBalance = Math.abs(sum(reverseTransfer.sources.mass));
const reverseMomentumBalance = Math.max(
  Math.abs(sum(reverseTransfer.sources.momentumX)),
  Math.abs(sum(reverseTransfer.sources.momentumY)),
);
const reverseDirectionError = Math.max(
  Math.abs(reverseTransfer.sources.mass[0] - 5),
  Math.abs(reverseTransfer.sources.mass[1] + 5),
  Math.abs(reverseTransfer.transportVelocity.x + 1.2),
  Math.abs(reverseTransfer.transportVelocity.y + 1.6),
);

const accumulated = accumulateStructureTransfers({
  cellCount: 4,
  transfers: [
    { id: 'gate-1', cellA: 0, cellB: 1, discharge: 2, direction: [1, 0], transportSpeed: 3 },
    { id: 'fishway', cellA: 1, cellB: 2, discharge: 0.5, direction: [1, 1], transportSpeed: 1 },
    { id: 'reverse', cellA: 3, cellB: 2, discharge: -1, direction: [0, 1], transportSpeed: 2 },
  ],
});
const accumulatedBalance = Math.max(
  Math.abs(sum(accumulated.sources.mass)),
  Math.abs(sum(accumulated.sources.momentumX)),
  Math.abs(sum(accumulated.sources.momentumY)),
);

let invalidOpeningRejected = false;
try {
  gateOpeningArea({ width: 1, maximumOpening: 1, openingFraction: 1.1 });
} catch (_) {
  invalidOpeningRejected = true;
}

let negativeCoefficientRejected = false;
try {
  headOrificeDischarge({ headA: 2, headB: 1, dischargeCoefficient: -0.1, area: 1 });
} catch (_) {
  negativeCoefficientRejected = true;
}

let unsupportedModeRejected = false;
try {
  evaluateStructureDischarge({ mode: 'visual_fit' });
} catch (_) {
  unsupportedModeRejected = true;
}

const checks = [
  check('orifice analytical discharge', forwardError, `<${tolerance}`, forwardError < tolerance),
  check('head reversal odd symmetry', reversalError, `<${tolerance}`, reversalError < tolerance),
  check('equal head zero discharge', Math.abs(equal.discharge), `<${tolerance}`, Math.abs(equal.discharge) < tolerance),
  check('gate opening area', Math.abs(halfArea - 4), `<${tolerance}`, Math.abs(halfArea - 4) < tolerance),
  check('half opening gives half discharge', halfGateRatioError, `<${tolerance}`, halfGateRatioError < tolerance),
  check('closed gate zero discharge', Math.abs(closedGate.discharge), `<${tolerance}`, Math.abs(closedGate.discharge) < tolerance),
  check('time-dependent fixed discharge', Math.abs(timeDependentFixed.discharge - 6), `<${tolerance}`, Math.abs(timeDependentFixed.discharge - 6) < tolerance),
  check('time-dependent fixed transport speed', Math.abs(timeDependentFixed.speed - 3), `<${tolerance}`, Math.abs(timeDependentFixed.speed - 3) < tolerance),
  check('time-dependent gate opening', Math.abs(timeDependentGate.openingArea - 4), `<${tolerance}`, Math.abs(timeDependentGate.openingArea - 4) < tolerance),
  check('disabled structure zero discharge', Math.abs(disabled.discharge), `<${tolerance}`, Math.abs(disabled.discharge) < tolerance),
  check('positive transfer mass conservation', positiveMassBalance, `<${tolerance}`, positiveMassBalance < tolerance),
  check('positive transfer momentum conservation', positiveMomentumBalance, `<${tolerance}`, positiveMomentumBalance < tolerance),
  check('positive transfer components', positiveComponentError, `<${tolerance}`, positiveComponentError < tolerance),
  check('reverse transfer mass conservation', reverseMassBalance, `<${tolerance}`, reverseMassBalance < tolerance),
  check('reverse transfer momentum conservation', reverseMomentumBalance, `<${tolerance}`, reverseMomentumBalance < tolerance),
  check('reverse transfer direction', reverseDirectionError, `<${tolerance}`, reverseDirectionError < tolerance),
  check('multiple transfer global conservation', accumulatedBalance, `<${tolerance}`, accumulatedBalance < tolerance),
  check('invalid opening rejected', invalidOpeningRejected, true, invalidOpeningRejected),
  check('negative coefficient rejected', negativeCoefficientRejected, true, negativeCoefficientRejected),
  check('unsupported mode rejected', unsupportedModeRejected, true, unsupportedModeRejected),
];

const report = {
  schema: 'onga-stage15-structure-discharge-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    forwardDischarge: forward.discharge,
    reverseDischarge: reverse.discharge,
    halfArea,
    halfGateRatioError,
    positiveMassBalance,
    positiveMomentumBalance,
    reverseMassBalance,
    reverseMomentumBalance,
    accumulatedBalance,
  },
  safeguards: {
    connectedToPublicSimulator: false,
    approvedWaterGeometryChanged: false,
    physicalCoefficientsAssigned: false,
    calibrationPerformed: false,
    purpose: 'generic structure discharge verification only',
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
