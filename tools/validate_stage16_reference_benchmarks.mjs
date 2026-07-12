import fs from 'node:fs/promises';
import {
  STAGE16_REFERENCE_BENCHMARK_VERSION,
  dryBedDamBreakExact,
  dryBedDamBreakFrontSpeed,
  integrateMidpoint,
  lakeAtRestState,
  linearStandingWaveExact,
  manningWideChannelDischargePerWidth,
  manningWideChannelNormalDepth,
  shallowWaterCharacteristicSpeeds,
} from '../onga_stage16_reference_benchmarks.mjs';

const outputPath = process.argv[2] || 'stage16-reference-benchmark-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const gravity = 9.80665;
const leftDepth = 2;
const c0 = Math.sqrt(gravity * leftDepth);
const time = 0.4;
const origin = 0;
const leftEdge = dryBedDamBreakExact({
  x: origin - c0 * time,
  time,
  leftDepth,
  damLocation: origin,
  gravity,
});
const rightEdge = dryBedDamBreakExact({
  x: origin + 2 * c0 * time,
  time,
  leftDepth,
  damLocation: origin,
  gravity,
});
const fanCentre = dryBedDamBreakExact({
  x: origin,
  time,
  leftDepth,
  damLocation: origin,
  gravity,
});
const frontSpeed = dryBedDamBreakFrontSpeed({ leftDepth, gravity });
const domainLeft = -12;
const domainRight = 12;
const mass = integrateMidpoint({
  start: domainLeft,
  end: domainRight,
  intervals: 200000,
  functionValue: x => dryBedDamBreakExact({ x, time, leftDepth, gravity }).depth,
});
const initialMass = leftDepth * (origin - domainLeft);
const massRelativeError = Math.abs(mass - initialMass) / initialMass;

const wave = {
  length: 100,
  meanDepth: 5,
  amplitude: 0.2,
  mode: 1,
  gravity,
};
const sample = linearStandingWaveExact({ ...wave, x: 37, time: 2.3 });
const leftWall = linearStandingWaveExact({ ...wave, x: 0, time: 2.3 });
const rightWall = linearStandingWaveExact({ ...wave, x: wave.length, time: 2.3 });
const initialWave = linearStandingWaveExact({ ...wave, x: 37, time: 0 });
const halfPeriod = linearStandingWaveExact({ ...wave, x: 37, time: initialWave.wavePeriod / 2 });
const meanPerturbation = integrateMidpoint({
  start: 0,
  end: wave.length,
  intervals: 10000,
  functionValue: x => linearStandingWaveExact({ ...wave, x, time: 1.7 }).surfacePerturbation,
}) / wave.length;

const dx = 1e-3;
const dt = 1e-4;
const x0 = 37;
const t0 = 2.3;
const etaPlusTime = linearStandingWaveExact({ ...wave, x: x0, time: t0 + dt }).surfacePerturbation;
const etaMinusTime = linearStandingWaveExact({ ...wave, x: x0, time: t0 - dt }).surfacePerturbation;
const uPlusSpace = linearStandingWaveExact({ ...wave, x: x0 + dx, time: t0 }).velocity;
const uMinusSpace = linearStandingWaveExact({ ...wave, x: x0 - dx, time: t0 }).velocity;
const etaTime = (etaPlusTime - etaMinusTime) / (2 * dt);
const uSpace = (uPlusSpace - uMinusSpace) / (2 * dx);
const continuityResidual = etaTime + wave.meanDepth * uSpace;
const uPlusTime = linearStandingWaveExact({ ...wave, x: x0, time: t0 + dt }).velocity;
const uMinusTime = linearStandingWaveExact({ ...wave, x: x0, time: t0 - dt }).velocity;
const etaPlusSpace = linearStandingWaveExact({ ...wave, x: x0 + dx, time: t0 }).surfacePerturbation;
const etaMinusSpace = linearStandingWaveExact({ ...wave, x: x0 - dx, time: t0 }).surfacePerturbation;
const momentumResidual = (uPlusTime - uMinusTime) / (2 * dt)
  + gravity * (etaPlusSpace - etaMinusSpace) / (2 * dx);

const normalDepth = 3.4;
const slope = 0.0008;
const roughness = 0.027;
const discharge = manningWideChannelDischargePerWidth({ depth: normalDepth, slope, roughness });
const recoveredDepth = manningWideChannelNormalDepth({ dischargePerWidth: discharge, slope, roughness });
const stillWet = lakeAtRestState({ bedElevation: 1.2, freeSurfaceElevation: 3.7 });
const stillDry = lakeAtRestState({ bedElevation: 4.2, freeSurfaceElevation: 3.7 });
const speeds = shallowWaterCharacteristicSpeeds({ depth: 4, normalVelocity: -1.2, gravity });

const checks = [
  check('dam-break left fan continuity depth', Math.abs(leftEdge.depth - leftDepth), '<1e-12',
    Math.abs(leftEdge.depth - leftDepth) < 1e-12),
  check('dam-break left fan continuity velocity', Math.abs(leftEdge.velocity), '<1e-12',
    Math.abs(leftEdge.velocity) < 1e-12),
  check('dam-break wetting-front depth', Math.abs(rightEdge.depth), '<1e-12',
    Math.abs(rightEdge.depth) < 1e-12),
  check('dam-break front speed', frontSpeed, 2 * c0,
    Math.abs(frontSpeed - 2 * c0) < 1e-12),
  check('dam-break fan centre positive', fanCentre.depth, '>0',
    fanCentre.depth > 0 && fanCentre.velocity > 0),
  check('dam-break integrated mass', massRelativeError, '<2e-6', massRelativeError < 2e-6),
  check('standing-wave left wall velocity', Math.abs(leftWall.velocity), '<1e-12',
    Math.abs(leftWall.velocity) < 1e-12),
  check('standing-wave right wall velocity', Math.abs(rightWall.velocity), '<1e-12',
    Math.abs(rightWall.velocity) < 1e-12),
  check('standing-wave half-period surface reversal',
    Math.abs(halfPeriod.surfacePerturbation + initialWave.surfacePerturbation),
    '<1e-12',
    Math.abs(halfPeriod.surfacePerturbation + initialWave.surfacePerturbation) < 1e-12),
  check('standing-wave half-period velocity', Math.abs(halfPeriod.velocity), '<1e-12',
    Math.abs(halfPeriod.velocity) < 1e-12),
  check('standing-wave mean perturbation', Math.abs(meanPerturbation), '<1e-12',
    Math.abs(meanPerturbation) < 1e-12),
  check('linear continuity residual', Math.abs(continuityResidual), '<1e-8',
    Math.abs(continuityResidual) < 1e-8),
  check('linear momentum residual', Math.abs(momentumResidual), '<1e-8',
    Math.abs(momentumResidual) < 1e-8),
  check('Manning normal-depth inverse', Math.abs(recoveredDepth - normalDepth), '<1e-12',
    Math.abs(recoveredDepth - normalDepth) < 1e-12),
  check('lake-at-rest wet depth', stillWet.depth, 2.5, Math.abs(stillWet.depth - 2.5) < 1e-12),
  check('lake-at-rest dry depth', stillDry.depth, 0, stillDry.depth === 0),
  check('characteristic speed ordering', `${speeds.minus},${speeds.plus}`, 'minus<plus',
    speeds.minus < speeds.plus && speeds.spectralRadius >= Math.abs(speeds.minus)
      && speeds.spectralRadius >= Math.abs(speeds.plus)),
  check('reference values finite', sample.depth, 'finite',
    [sample.depth, sample.velocity, sample.discharge].every(Number.isFinite)),
];

const report = {
  schema: 'onga-stage16-reference-benchmark-validation-v1',
  moduleVersion: STAGE16_REFERENCE_BENCHMARK_VERSION,
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
