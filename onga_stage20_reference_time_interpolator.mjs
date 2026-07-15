export const STAGE20_REFERENCE_TIME_PACK_SCHEMA = 'onga-stage20-reference-time-pack-candidate-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-reference-time-interpolator] ${message}`);
}

function product(values) {
  return values.reduce((result, value) => result * value, 1);
}

export function decodeStage20ReferenceTimePack(manifest, buffer) {
  assert(manifest?.schema === STAGE20_REFERENCE_TIME_PACK_SCHEMA, 'manifest schema mismatch');
  assert(manifest.status === 'direct_solver_reference_candidate_not_public_simulator', 'pack status mismatch');
  assert(buffer instanceof ArrayBuffer, 'payload must be an ArrayBuffer');
  assert(buffer.byteLength === manifest.binary.byteLength, 'payload byte length mismatch');
  const descriptor = manifest.arrays?.snapshots;
  assert(descriptor?.dtype === 'float32', 'snapshot dtype mismatch');
  assert(Array.isArray(descriptor.shape) && descriptor.shape.length === 3, 'snapshot shape mismatch');
  assert(product(descriptor.shape) * Float32Array.BYTES_PER_ELEMENT === descriptor.byteLength, 'snapshot byte length mismatch');
  const [snapshotCount, componentCount, cellCount] = descriptor.shape;
  assert(snapshotCount === manifest.timeContract.anchorHours.length, 'anchor count mismatch');
  assert(componentCount === 3 && cellCount === manifest.mesh.cellCount, 'field identity mismatch');
  assert(manifest.componentOrder.join(',') === 'depthM,eastVelocityMPS,northVelocityMPS', 'component order mismatch');
  const hours = manifest.timeContract.anchorHours;
  for (let index = 1; index < hours.length; index += 1) {
    assert(hours[index] > hours[index - 1], 'anchor hours must increase');
  }
  return Object.freeze({
    manifest: Object.freeze(manifest),
    buffer,
    snapshots: new Float32Array(buffer, descriptor.byteOffset, product(descriptor.shape)),
    snapshotCount,
    componentCount,
    cellCount,
    hours: Object.freeze([...hours]),
  });
}

export function interpolateStage20ReferencePair(pack, lowerIndex, upperIndex, hour) {
  assert(Number.isInteger(lowerIndex) && Number.isInteger(upperIndex), 'pair indices must be integers');
  assert(lowerIndex >= 0 && upperIndex < pack.snapshotCount && lowerIndex < upperIndex, 'pair indices are invalid');
  const lowerHour = pack.hours[lowerIndex];
  const upperHour = pack.hours[upperIndex];
  assert(Number.isFinite(hour) && hour >= lowerHour && hour <= upperHour, 'hour is outside the selected pair');
  const weight = (hour - lowerHour) / (upperHour - lowerHour);
  const stride = pack.componentCount * pack.cellCount;
  const lowerOffset = lowerIndex * stride;
  const upperOffset = upperIndex * stride;
  const output = new Float32Array(stride);
  for (let index = 0; index < stride; index += 1) {
    output[index] = pack.snapshots[lowerOffset + index] * (1 - weight) + pack.snapshots[upperOffset + index] * weight;
  }
  return Object.freeze({ hour, lowerHour, upperHour, weight, fields: output });
}

export function interpolateStage20ReferenceHour(pack, hour) {
  assert(Number.isFinite(hour), 'hour must be finite');
  assert(hour >= pack.hours[0] && hour <= pack.hours.at(-1), 'extrapolation is forbidden');
  const exactIndex = pack.hours.indexOf(hour);
  if (exactIndex >= 0) {
    const stride = pack.componentCount * pack.cellCount;
    const start = exactIndex * stride;
    return Object.freeze({
      hour,
      lowerHour: hour,
      upperHour: hour,
      weight: 0,
      fields: pack.snapshots.slice(start, start + stride),
    });
  }
  let upperIndex = 1;
  while (pack.hours[upperIndex] < hour) upperIndex += 1;
  return interpolateStage20ReferencePair(pack, upperIndex - 1, upperIndex, hour);
}
