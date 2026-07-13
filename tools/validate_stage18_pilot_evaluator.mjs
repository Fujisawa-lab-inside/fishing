import fs from 'node:fs/promises';
import { evaluatePilotResult } from '../onga_stage18_pilot_evaluator.mjs';

const config = JSON.parse(await fs.readFile('config/stage18_production_mesh_pilot_v1.json', 'utf8'));
const geometry = config.geometry;
const makeReport = overrides => ({
  schema: 'onga-stage18-pilot-run-report-v1', tierId: 'smoke', geometry,
  requestedCaseCount: 1, completedCaseCount: 1, failedCaseCount: 0,
  wallSeconds: 10, peakResidentMemoryMiB: 512, maxCfl: 0.5,
  maxAbsoluteMassBalanceError: 1e-10, minimumDepthM: 0,
  nanCount: 0, negativeDepthCount: 0, failures: [], ...overrides,
});
const pass = evaluatePilotResult(config, makeReport());
if (!pass.passed || pass.nextTierId !== 'screening' || pass.automaticPromotionPerformed) throw new Error('valid smoke report failed');
for (const bad of [
  {maxCfl: 1.1}, {nanCount: 1}, {negativeDepthCount: 1},
  {maxAbsoluteMassBalanceError: 1e-5}, {minimumDepthM: -0.01},
  {wallSeconds: 121}, {peakResidentMemoryMiB: 2049},
]) {
  if (evaluatePilotResult(config, makeReport(bad)).passed) throw new Error(`invalid report passed: ${JSON.stringify(bad)}`);
}
let rejected = 0;
for (const malformed of [
  {geometry: {...geometry, metricMeshCellCount: 50332}},
  {requestedCaseCount: 2},
  {completedCaseCount: 0, failedCaseCount: 1, failures: []},
]) {
  try { evaluatePilotResult(config, makeReport(malformed)); } catch { rejected += 1; }
}
if (rejected !== 3) throw new Error('malformed reports were not rejected');
await fs.writeFile('stage18-pilot-evaluator-validation.json', `${JSON.stringify({status:'pass', pass}, null, 2)}\n`);
console.log(JSON.stringify({status:'pass'}));
