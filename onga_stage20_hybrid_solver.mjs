export const STAGE20_HYBRID_SOLVER_VERSION = 'stage20-hybrid-browser-solver-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-hybrid-solver] ${message}`);
}

function coefficient(mode, inputs, index) {
  if (mode.kind === 'constant') return 1;
  return (inputs[mode.input][index] - mode.offset) / mode.scale;
}

export function validateStage20HourlyInputs(pack, inputs) {
  assert(inputs && typeof inputs === 'object', 'inputs are required');
  const contract = pack.manifest.inputContract;
  const hours = inputs.hours;
  assert(Array.isArray(hours), 'hours must be an array');
  assert(hours.length === contract.snapshotCount, 'snapshot count mismatch');
  assert(hours[0] === contract.startHour && hours.at(-1) === contract.endHour, 'hour range mismatch');
  for (let index = 1; index < hours.length; index += 1) {
    assert(hours[index] - hours[index - 1] === contract.intervalHours, 'hours are not uniformly spaced');
  }
  for (const series of contract.series) {
    const values = inputs[series.name];
    assert(Array.isArray(values) && values.length === hours.length, `${series.name} length mismatch`);
    for (const value of values) {
      assert(Number.isFinite(value), `${series.name} contains a non-finite value`);
      assert(value >= series.minimum && value <= series.maximum, `${series.name} is outside the response-pack envelope`);
    }
  }
  return Object.freeze({ snapshotCount: hours.length, hours: Object.freeze([...hours]) });
}

export function synthesiseStage20HourlyFields(pack, inputs) {
  const timeline = validateStage20HourlyInputs(pack, inputs);
  const { cellCount, componentCount, modeCount, basis } = pack;
  const snapshotStride = componentCount * cellCount;
  const modeStride = snapshotStride;
  const output = new Float32Array(timeline.snapshotCount * snapshotStride);
  let minimumDepthM = Infinity;
  let maximumDepthM = -Infinity;
  let maximumSpeedMPS = 0;
  let nonFiniteValueCount = 0;
  for (let snapshot = 0; snapshot < timeline.snapshotCount; snapshot += 1) {
    const targetOffset = snapshot * snapshotStride;
    for (let modeIndex = 0; modeIndex < modeCount; modeIndex += 1) {
      const factor = coefficient(pack.manifest.modes[modeIndex], inputs, snapshot);
      if (factor === 0) continue;
      const basisOffset = modeIndex * modeStride;
      for (let value = 0; value < snapshotStride; value += 1) {
        output[targetOffset + value] += factor * basis[basisOffset + value];
      }
    }
    const depthOffset = targetOffset;
    const eastOffset = targetOffset + cellCount;
    const northOffset = targetOffset + 2 * cellCount;
    for (let cell = 0; cell < cellCount; cell += 1) {
      const depth = output[depthOffset + cell];
      const east = output[eastOffset + cell];
      const north = output[northOffset + cell];
      minimumDepthM = Math.min(minimumDepthM, depth);
      maximumDepthM = Math.max(maximumDepthM, depth);
      maximumSpeedMPS = Math.max(maximumSpeedMPS, Math.hypot(east, north));
      if (!Number.isFinite(depth) || !Number.isFinite(east) || !Number.isFinite(north)) nonFiniteValueCount += 1;
    }
  }
  assert(nonFiniteValueCount === 0, 'synthesis produced non-finite values');
  assert(minimumDepthM >= pack.manifest.outputContract.minimumDepthM, 'synthesis produced a depth below the response-pack floor');
  return Object.freeze({
    version: STAGE20_HYBRID_SOLVER_VERSION,
    hours: timeline.hours,
    snapshotCount: timeline.snapshotCount,
    cellCount,
    componentCount,
    componentOrder: Object.freeze([...pack.manifest.componentOrder]),
    fields: output,
    diagnostics: Object.freeze({ minimumDepthM, maximumDepthM, maximumSpeedMPS, nonFiniteValueCount }),
  });
}

export function stage20SnapshotViews(result, snapshotIndex) {
  assert(Number.isInteger(snapshotIndex) && snapshotIndex >= 0 && snapshotIndex < result.snapshotCount, 'snapshot index is invalid');
  const stride = result.componentCount * result.cellCount;
  const start = snapshotIndex * stride;
  return Object.freeze({
    hour: result.hours[snapshotIndex],
    depthM: result.fields.subarray(start, start + result.cellCount),
    eastVelocityMPS: result.fields.subarray(start + result.cellCount, start + 2 * result.cellCount),
    northVelocityMPS: result.fields.subarray(start + 2 * result.cellCount, start + 3 * result.cellCount),
  });
}
