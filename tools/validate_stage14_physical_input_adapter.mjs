import fs from 'node:fs/promises';
import {
  createLinearSeries,
  createStage14RuntimeForcing,
  normaliseSeries,
} from '../onga_stage14_physical_input_adapter.mjs';

const outputPath = process.argv[2] || 'stage14-input-adapter-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const t0 = Date.parse('2026-07-12T00:00:00+09:00') / 1000;
const t1 = Date.parse('2026-07-12T01:00:00+09:00') / 1000;
const t2 = Date.parse('2026-07-12T02:00:00+09:00') / 1000;
const waterLevel = createLinearSeries([
  { timestamp: '2026-07-12T00:00:00+09:00', water_level_m: 0 },
  { timestamp: '2026-07-12T01:00:00+09:00', water_level_m: 1 },
  { timestamp: '2026-07-12T02:00:00+09:00', water_level_m: 0 },
], 'water_level_m', { minimumSamples: 2 });
const interpolationError = Math.abs(waterLevel.at((t0 + t1) / 2) - 0.5);
const lowerHoldError = Math.abs(waterLevel.at(t0 - 100));
const upperHoldError = Math.abs(waterLevel.at(t2 + 100));

let nonMonotoneRejected = false;
try {
  normaliseSeries([
    { timestamp: '2026-07-12T01:00:00+09:00', discharge_m3_s: 1 },
    { timestamp: '2026-07-12T00:00:00+09:00', discharge_m3_s: 2 },
  ], 'discharge_m3_s');
} catch (error) {
  nonMonotoneRejected = /strictly increasing/.test(String(error));
}

let missingValueRejected = false;
try {
  normaliseSeries([{ timestamp: '2026-07-12T00:00:00+09:00' }], 'discharge_m3_s');
} catch (error) {
  missingValueRejected = /finite/.test(String(error));
}

const mapping = {
  cellCount: 6,
  edgeCount: 10,
  boundaryFaces: {
    M: [{ cell: 0, length: 2, conductance: 3 }, { cell: 1, length: 1, conductance: 2 }],
    N: [{ cell: 2, length: 1 }, { cell: 3, length: 3 }],
    O: [{ cell: 4, length: 2 }],
    G: [{ cell: 5, length: 1 }, { cell: 4, length: 1 }],
  },
  barrageEdgeIds: [3, 4, 7, 8],
  barrageGateIds: [1, 2, 7, 8],
  fishway: { upstreamCell: 2, downstreamCell: 1 },
};
const input = {
  M: [
    { timestamp: '2026-07-12T00:00:00+09:00', water_level_m: 0 },
    { timestamp: '2026-07-12T02:00:00+09:00', water_level_m: 1 },
  ],
  N: -4,
  O: [{ timestamp: '2026-07-12T00:00:00+09:00', discharge_m3_s: -2 }],
  G: 1,
  fishway: { discharge_m3_s: 0.25 },
  barrage: { opening_fraction: 0.4 },
};
const forcing = createStage14RuntimeForcing({ input, mapping });
const boundaries = forcing.boundariesAt(t1);
const sumFlux = id => boundaries
  .filter(boundary => boundary.id.startsWith(`${id}-`))
  .reduce((sum, boundary) => sum + boundary.value, 0);
const nFluxError = Math.abs(sumFlux('N') + 4);
const oFluxError = Math.abs(sumFlux('O') + 2);
const gFluxError = Math.abs(sumFlux('G') - 1);
const mLevelError = Math.max(...boundaries
  .filter(boundary => boundary.id.startsWith('M-'))
  .map(boundary => Math.abs(boundary.value - 0.5)));
const sources = forcing.sourcesAt(t1);
const sourceSum = sources.reduce((sum, value) => sum + value, 0);
const fishwayPairError = Math.max(Math.abs(sources[2] + 0.25), Math.abs(sources[1] - 0.25));
const multipliers = forcing.edgeMultipliersAt(t1);
const uniformOpeningError = Math.max(...mapping.barrageEdgeIds.map(edge => Math.abs(multipliers[edge] - 0.4)));
const untouchedEdges = Array.from({ length: mapping.edgeCount }, (_, edge) => edge)
  .filter(edge => !mapping.barrageEdgeIds.includes(edge));
const untouchedError = Math.max(...untouchedEdges.map(edge => Math.abs(multipliers[edge] - 1)));

const gatewise = createStage14RuntimeForcing({
  input: {
    ...input,
    barrage: { gate_opening_fraction: [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7] },
  },
  mapping,
});
const gatewiseMultipliers = gatewise.edgeMultipliersAt(t1);
const gatewiseError = Math.max(
  Math.abs(gatewiseMultipliers[3]),
  Math.abs(gatewiseMultipliers[4] - 0.1),
  Math.abs(gatewiseMultipliers[7] - 0.6),
  Math.abs(gatewiseMultipliers[8] - 0.7),
);

let unassignedRejected = false;
try {
  createStage14RuntimeForcing({
    input: { ...input, fishway: { discharge_m3_s: null } },
    mapping,
  });
} catch (error) {
  unassignedRejected = /required|finite/.test(String(error));
}

const detachedSummary = forcing.summaryAt;
const detachedSummaryError = Math.abs(detachedSummary(t1).MWaterLevel - 0.5);

const checks = [
  check('linear interpolation', interpolationError, '<1e-12', interpolationError < 1e-12),
  check('lower hold extrapolation', lowerHoldError, '<1e-12', lowerHoldError < 1e-12),
  check('upper hold extrapolation', upperHoldError, '<1e-12', upperHoldError < 1e-12),
  check('non-monotone series rejected', nonMonotoneRejected, true, nonMonotoneRejected),
  check('missing numeric value rejected', missingValueRejected, true, missingValueRejected),
  check('M water-level interpolation', mLevelError, '<1e-12', mLevelError < 1e-12),
  check('N outward-flux sum', nFluxError, '<1e-12', nFluxError < 1e-12),
  check('O outward-flux sum', oFluxError, '<1e-12', oFluxError < 1e-12),
  check('G outward-flux sum', gFluxError, '<1e-12', gFluxError < 1e-12),
  check('fishway net source', Math.abs(sourceSum), '<1e-12', Math.abs(sourceSum) < 1e-12),
  check('fishway source pair', fishwayPairError, '<1e-12', fishwayPairError < 1e-12),
  check('uniform barrage opening', uniformOpeningError, '<1e-12', uniformOpeningError < 1e-12),
  check('non-barrage edges unchanged', untouchedError, '<1e-12', untouchedError < 1e-12),
  check('gate-wise barrage opening', gatewiseError, '<1e-12', gatewiseError < 1e-12),
  check('unassigned physical value rejected', unassignedRejected, true, unassignedRejected),
  check('detached summary function', detachedSummaryError, '<1e-12', detachedSummaryError < 1e-12),
];

const report = {
  schema: 'onga-stage14-input-adapter-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    interpolationError,
    nFluxError,
    oFluxError,
    gFluxError,
    mLevelError,
    sourceSum,
    fishwayPairError,
    uniformOpeningError,
    gatewiseError,
    detachedSummaryError,
  },
  safeguards: {
    usesSyntheticValuesOnly: true,
    connectedToPublicSimulator: false,
    approvedWaterGeometryChanged: false,
    actualPhysicalValuesAssigned: false,
    calibrationPerformed: false,
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
