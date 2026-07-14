import crypto from 'node:crypto';
import fs from 'node:fs/promises';

const candidatePath = process.argv[2] || 'config/stage19_m_boundary_tide_candidate_v1.json';
const outputPath = process.argv[3] || 'stage19-m-boundary-tide-candidate-validation.json';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage19-m-tide-candidate] ${message}`);
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

const candidate = JSON.parse(await fs.readFile(candidatePath, 'utf8'));
const sourceText = await fs.readFile(candidate.source.localSnapshot, 'utf8');
assert(candidate.schema === 'onga-stage19-m-boundary-tide-candidate-v1', 'schema mismatch');
assert(candidate.status === 'visual_review_required_before_solver_assignment', 'status mismatch');
assert(sha256(sourceText) === candidate.source.retrievedTextSha256, 'JMA snapshot digest changed');
assert(candidate.source.provider === '気象庁' && candidate.source.stationCode === 'QF',
  'JMA Hakata identity changed');

const rows = sourceText.trimEnd().split('\n').map(line => {
  assert(line.length === 136, 'JMA source row width changed');
  const hourly = Array.from({length: 24}, (_, index) => Number(line.slice(index * 3, index * 3 + 3)));
  const year = 2000 + Number(line.slice(72, 74));
  const month = Number(line.slice(74, 76));
  const day = Number(line.slice(76, 78));
  const station = line.slice(78, 80);
  const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  return {date, station, hourly, range: Math.max(...hourly) - Math.min(...hourly)};
});
assert(rows.length === 365, 'expected 365 JMA daily rows for 2026');
assert(rows.every(row => row.station === 'QF'), 'source contains a non-Hakata row');
const medianRange = median(rows.map(row => row.range));
assert(medianRange === candidate.selectionRule.annualMedianDailyRangeCm,
  'annual median daily range changed');
const selected = [...rows].sort((a, b) =>
  Math.abs(a.range - medianRange) - Math.abs(b.range - medianRange)
    || a.date.localeCompare(b.date))[0];
assert(selected.date === candidate.selectionRule.candidateDate, 'representative date changed');
assert(selected.range === candidate.selectionRule.candidateDailyRangeCm, 'candidate daily range changed');
assert(JSON.stringify(selected.hourly) === JSON.stringify(candidate.candidateCurve.hourlyHeightAboveTideTableDatumCm),
  'candidate hourly curve changed');

const mean = selected.hourly.reduce((sum, value) => sum + value, 0) / selected.hourly.length;
assert(Math.abs(mean - candidate.candidateCurve.dailyMeanCm) < 1e-9, 'daily mean changed');
const anomalies = selected.hourly.map(value => Number(((value - mean) / 100).toFixed(6)));
assert(JSON.stringify(anomalies) === JSON.stringify(candidate.candidateCurve.relativeAnomalyM),
  'mean-removed anomaly curve changed');
assert(candidate.candidateCurve.meanRemoved === true
  && candidate.candidateCurve.absoluteOffsetAssigned === false,
'candidate must remain a relative anomaly with no absolute offset');
assert(candidate.selectionRule.selectionApproved === false, 'candidate was selected without visual approval');

for (const key of [
  'externalContactPerformed',
  'candidateAssignedToSolver',
  'numericalCaseStarted',
  'numericalRunEnabled',
  'publicSimulatorConnected',
  'physicalValidationClaimAllowed',
]) {
  assert(candidate.safeguards?.[key] === false, `safeguard ${key} changed`);
}

const report = {
  schema: 'onga-stage19-m-boundary-tide-candidate-validation-v1',
  status: 'passed',
  sourceRows: rows.length,
  annualMedianDailyRangeCm: medianRange,
  candidateDate: selected.date,
  candidateDailyRangeCm: selected.range,
  absoluteOffsetAssigned: false,
  candidateAssignedToSolver: false,
  numericalRunEnabled: false,
};
await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
