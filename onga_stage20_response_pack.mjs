export const STAGE20_RESPONSE_PACK_SCHEMA = 'onga-stage20-response-pack-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-response-pack] ${message}`);
}

function product(values) {
  return values.reduce((result, value) => result * value, 1);
}

function hex(bytes) {
  return Array.from(new Uint8Array(bytes), value => value.toString(16).padStart(2, '0')).join('');
}

async function sha256(buffer) {
  assert(globalThis.crypto?.subtle, 'Web Crypto SHA-256 is unavailable');
  return hex(await globalThis.crypto.subtle.digest('SHA-256', buffer));
}

export function decodeStage20ResponsePack(manifest, buffer) {
  assert(manifest?.schema === STAGE20_RESPONSE_PACK_SCHEMA, 'manifest schema mismatch');
  assert(
    manifest.status === 'synthetic_browser_benchmark_only'
      || manifest.status === 'approved_physical_response_pack',
    'response-pack status is unsupported',
  );
  assert(buffer instanceof ArrayBuffer, 'payload must be an ArrayBuffer');
  assert(buffer.byteLength === manifest.binary.byteLength, 'payload byte length mismatch');
  const descriptor = manifest.arrays?.basis;
  assert(descriptor?.dtype === 'float32', 'basis dtype must be float32');
  assert(Array.isArray(descriptor.shape) && descriptor.shape.length === 3, 'basis shape must be rank 3');
  assert(descriptor.byteOffset % Float32Array.BYTES_PER_ELEMENT === 0, 'basis offset is unaligned');
  const length = product(descriptor.shape);
  assert(length * Float32Array.BYTES_PER_ELEMENT === descriptor.byteLength, 'basis byte length mismatch');
  assert(descriptor.byteOffset + descriptor.byteLength <= buffer.byteLength, 'basis exceeds payload');
  const [modeCount, componentCount, cellCount] = descriptor.shape;
  assert(modeCount === manifest.modes.length, 'mode count mismatch');
  assert(componentCount === manifest.componentOrder.length, 'component count mismatch');
  assert(cellCount === manifest.mesh.cellCount, 'cell count mismatch');
  assert(manifest.componentOrder.join(',') === 'depthM,eastVelocityMPS,northVelocityMPS', 'component order mismatch');
  const inputNames = new Set(manifest.inputContract.series.map(item => item.name));
  for (const mode of manifest.modes) {
    assert(mode.kind === 'constant' || mode.kind === 'affine_input', `unsupported mode ${mode.id}`);
    if (mode.kind === 'affine_input') {
      assert(inputNames.has(mode.input), `mode ${mode.id} references an unknown input`);
      assert(Number.isFinite(mode.offset) && Number.isFinite(mode.scale) && mode.scale !== 0, `mode ${mode.id} scaling is invalid`);
    }
  }
  return Object.freeze({
    manifest: Object.freeze(manifest),
    buffer,
    basis: new Float32Array(buffer, descriptor.byteOffset, length),
    modeCount,
    componentCount,
    cellCount,
  });
}

export async function loadStage20ResponsePack(manifestUrl, options = {}) {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  assert(typeof fetchImpl === 'function', 'fetch is unavailable');
  const manifestResponse = await fetchImpl(manifestUrl, { cache: 'no-store' });
  assert(manifestResponse.ok, `manifest fetch failed with HTTP ${manifestResponse.status}`);
  const manifest = await manifestResponse.json();
  const base = manifestResponse.url || String(manifestUrl);
  const binaryUrl = new URL(manifest.binary.url, base).href;
  const binaryResponse = await fetchImpl(binaryUrl, { cache: 'no-store' });
  assert(binaryResponse.ok, `binary fetch failed with HTTP ${binaryResponse.status}`);
  const buffer = await binaryResponse.arrayBuffer();
  assert(await sha256(buffer) === manifest.binary.sha256, 'payload SHA-256 mismatch');
  return decodeStage20ResponsePack(manifest, buffer);
}
