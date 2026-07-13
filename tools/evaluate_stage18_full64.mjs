import crypto from 'node:crypto';
import { createReadStream } from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

import { evaluateFull64Result } from '../onga_stage18_full64_evaluator.mjs';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(text) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

async function sha256File(filePath) {
  const hash = crypto.createHash('sha256');
  for await (const chunk of createReadStream(filePath)) hash.update(chunk);
  return hash.digest('hex');
}

async function writeJsonAtomic(outputPath, value) {
  const temporaryPath = path.join(path.dirname(outputPath), `.${path.basename(outputPath)}.${process.pid}.tmp`);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await fs.rename(temporaryPath, outputPath);
}

function assertDistinctPaths(entries) {
  const seen = new Map();
  for (const [label, filePath] of entries) {
    const resolved = path.resolve(filePath);
    const previous = seen.get(resolved);
    assert(previous === undefined, `${label} path overlaps ${previous}: ${resolved}`);
    seen.set(resolved, label);
  }
}

async function assertFreshOutput(outputPath) {
  try {
    await fs.access(outputPath);
  } catch (error) {
    if (error?.code === 'ENOENT') return;
    throw error;
  }
  throw new Error(`evaluation output already exists: ${outputPath}`);
}

export async function evaluateFull64Files(authorizationPath, reportPath, fieldsPath, outputPath) {
  assertDistinctPaths([
    ['authorization', authorizationPath],
    ['run report', reportPath],
    ['field artifact', fieldsPath],
    ['evaluation output', outputPath],
  ]);
  await assertFreshOutput(outputPath);
  const authorizationText = await fs.readFile(authorizationPath, 'utf8');
  const reportText = await fs.readFile(reportPath, 'utf8');
  const authorization = JSON.parse(authorizationText);
  const report = JSON.parse(reportText);
  const fieldsDigest = await sha256File(fieldsPath);
  assert(path.resolve(report.fieldArtifact?.path || '') === path.resolve(fieldsPath), 'field artifact path mismatch');
  assert(report.fieldArtifact?.sha256 === fieldsDigest, 'field artifact file digest mismatch');
  const evaluation = evaluateFull64Result(authorization, report);
  evaluation.provenance = {
    authorizationSha256: sha256(authorizationText),
    runReportSha256: sha256(reportText),
    fieldArtifactSha256: fieldsDigest,
    meshSha256: report.inputDigests?.meshSha256 ?? null,
    meshSummarySha256: report.inputDigests?.meshSummarySha256 ?? null,
    ensembleSha256: report.inputDigests?.ensembleSha256 ?? null,
  };
  assert(evaluation.provenance.authorizationSha256 === report.inputDigests.authorizationSha256, 'authorization digest mismatch');
  evaluation.offlineStepMatchedStatisticsAllowed = evaluation.passed;
  await writeJsonAtomic(outputPath, evaluation);
  if (!evaluation.passed) throw new Error('full64 evaluation failed');
  return evaluation;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const authorizationPath = process.argv[2];
  const reportPath = process.argv[3];
  const fieldsPath = process.argv[4];
  const outputPath = process.argv[5];
  assert(authorizationPath && reportPath && fieldsPath && outputPath, 'usage: evaluate_stage18_full64.mjs AUTHORIZATION REPORT FIELDS OUTPUT');
  const evaluation = await evaluateFull64Files(authorizationPath, reportPath, fieldsPath, outputPath);
  console.log(JSON.stringify({ outputPath, passed: evaluation.passed, provenance: evaluation.provenance }));
}
