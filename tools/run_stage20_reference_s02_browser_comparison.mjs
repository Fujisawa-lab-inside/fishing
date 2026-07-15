#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { resolve } from 'node:path';

import {
  decodeStage20ReferenceTimePack,
  interpolateStage20ReferenceHour,
  interpolateStage20ReferencePair,
} from '../onga_stage20_reference_time_interpolator.mjs';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-reference-s02-browser-comparison] ${message}`);
}

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

function percentile(values, fraction) {
  const ordered = [...values].sort((a, b) => a - b);
  const index = Math.min(ordered.length - 1, Math.max(0, Math.ceil(fraction * ordered.length) - 1));
  return ordered[index];
}

function compareFields(predicted, truth, cellCount) {
  let depthSquared = 0;
  let maximumDepth = 0;
  let vectorSquared = 0;
  let maximumVector = 0;
  let speedAbsolute = 0;
  const vectorErrors = [];
  const speedErrors = [];
  const directionErrors = [];
  for (let cell = 0; cell < cellCount; cell += 1) {
    const depthError = predicted[cell] - truth[cell];
    depthSquared += depthError * depthError;
    maximumDepth = Math.max(maximumDepth, Math.abs(depthError));
    const pu = predicted[cellCount + cell];
    const pv = predicted[2 * cellCount + cell];
    const tu = truth[cellCount + cell];
    const tv = truth[2 * cellCount + cell];
    const du = pu - tu;
    const dv = pv - tv;
    const vectorError = Math.hypot(du, dv);
    vectorErrors.push(vectorError);
    vectorSquared += vectorError * vectorError;
    maximumVector = Math.max(maximumVector, vectorError);
    const predictedSpeed = Math.hypot(pu, pv);
    const truthSpeed = Math.hypot(tu, tv);
    const speedError = Math.abs(predictedSpeed - truthSpeed);
    speedErrors.push(speedError);
    speedAbsolute += speedError;
    if (predictedSpeed >= 0.02 && truthSpeed >= 0.02) {
      const cosine = Math.max(-1, Math.min(1, (pu * tu + pv * tv) / (predictedSpeed * truthSpeed)));
      directionErrors.push(Math.acos(cosine) * 180 / Math.PI);
    }
  }
  return {
    depthRmseM: Math.sqrt(depthSquared / cellCount),
    maximumAbsoluteDepthErrorM: maximumDepth,
    velocityVectorRmseMPS: Math.sqrt(vectorSquared / cellCount),
    p95VelocityVectorErrorMPS: percentile(vectorErrors, 0.95),
    maximumVelocityVectorErrorMPS: maximumVector,
    speedMaeMPS: speedAbsolute / cellCount,
    p95SpeedAbsoluteErrorMPS: percentile(speedErrors, 0.95),
    directionActiveThresholdMPS: 0.02,
    directionComparedCellCount: directionErrors.length,
    medianDirectionErrorDeg: percentile(directionErrors, 0.5),
    p95DirectionErrorDeg: percentile(directionErrors, 0.95),
  };
}

async function main() {
  const root = resolve(process.argv[2] || '.');
  const comparisonDir = resolve(root, 'docs/results/stage20-reference-s02-29434250546/browser-comparison');
  const manifestPath = resolve(comparisonDir, 'reference-s02-time-pack.json');
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const payload = await readFile(resolve(comparisonDir, 'reference-s02-time-pack.bin'));
  assert(sha256(payload) === manifest.binary.sha256, 'time-pack digest mismatch');
  const arrayBuffer = payload.buffer.slice(payload.byteOffset, payload.byteOffset + payload.byteLength);
  const pack = decodeStage20ReferenceTimePack(manifest, arrayBuffer);
  const stride = pack.componentCount * pack.cellCount;
  const anchors = [];
  for (let index = 0; index < pack.snapshotCount; index += 1) {
    const result = interpolateStage20ReferenceHour(pack, pack.hours[index]);
    const truth = pack.snapshots.subarray(index * stride, (index + 1) * stride);
    anchors.push({
      modelHour: pack.hours[index],
      ...compareFields(result.fields, truth, pack.cellCount),
    });
  }

  const leaveOneOut = [];
  await mkdir(comparisonDir, { recursive: true });
  for (let index = 1; index < pack.snapshotCount - 1; index += 1) {
    const modelHour = pack.hours[index];
    const prediction = interpolateStage20ReferencePair(pack, index - 1, index + 1, modelHour);
    const truth = pack.snapshots.subarray(index * stride, (index + 1) * stride);
    const predictionBytes = Buffer.from(prediction.fields.buffer, prediction.fields.byteOffset, prediction.fields.byteLength);
    const filename = `leave-one-out-m${Math.abs(modelHour)}h.bin`;
    await writeFile(resolve(comparisonDir, filename), predictionBytes);
    leaveOneOut.push({
      modelHour,
      lowerHour: prediction.lowerHour,
      upperHour: prediction.upperHour,
      weight: prediction.weight,
      prediction: filename,
      predictionByteLength: predictionBytes.byteLength,
      predictionSha256: sha256(predictionBytes),
      ...compareFields(prediction.fields, truth, pack.cellCount),
    });
  }

  const timings = [];
  for (let index = 0; index < 51; index += 1) {
    const started = performance.now();
    interpolateStage20ReferencePair(pack, 0, 1, -11.5);
    const elapsed = performance.now() - started;
    if (index > 0) timings.push(elapsed);
  }
  timings.sort((a, b) => a - b);
  const worst = leaveOneOut.reduce((current, item) => (
    !current || item.velocityVectorRmseMPS > current.velocityVectorRmseMPS ? item : current
  ), null);
  const report = {
    schema: 'onga-stage20-reference-s02-browser-comparison-v1',
    status: 'passed_reference_time_interpolation_comparison_not_physical_validation',
    pack: {
      manifest: 'docs/results/stage20-reference-s02-29434250546/browser-comparison/reference-s02-time-pack.json',
      manifestSha256: sha256(await readFile(manifestPath)),
      binary: 'docs/results/stage20-reference-s02-29434250546/browser-comparison/reference-s02-time-pack.bin',
      binarySha256: manifest.binary.sha256,
      binaryBytes: manifest.binary.byteLength,
      anchorHours: pack.hours,
      cellCount: pack.cellCount,
    },
    exactAnchorReconstruction: anchors,
    leaveOneHourOut: leaveOneOut,
    worstLeaveOneOutModelHourByVelocityVectorRmse: worst.modelHour,
    timing: {
      operation: 'one_50199_cell_three_component_linear_interpolation',
      repetitions: timings.length,
      medianMs: timings[Math.floor(timings.length / 2)],
      p95Ms: timings[Math.ceil(timings.length * 0.95) - 1],
      runtime: `${process.platform}-${process.arch}-node-${process.version}`,
      browserTimingClaimAllowed: false,
    },
    interpretation: {
      exactAnchorTest: 'tests_pack_float32_reconstruction_at_the_five_direct_solver_hours',
      leaveOneHourOutTest: 'tests_temporal_linear_interpolation_against_three_held_out_direct_solver_hours',
      crossConditionInterpolationTested: false,
      observedFlowTested: false,
      dailyForecastTested: false,
    },
    safeguards: {
      additionalPhysicalRunPerformed: false,
      publicSimulatorConnected: false,
      mainMergeAuthorized: false,
      physicalValidationClaimAllowed: false,
    },
  };
  const reportPath = resolve(comparisonDir, 'comparison-report.json');
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({ ...report, reportSha256: sha256(await readFile(reportPath)) }, null, 2)}\n`);
}

await main();
