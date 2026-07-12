import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import zlib from 'node:zlib';

export const STAGE16_METRIC_MESH_VERSION = 'stage16-metric-fv-mesh-compact-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-mesh-loader] ${message}`);
}

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function product(values) {
  return values.reduce((result, value) => result * value, 1);
}

function decodeArray(raw, descriptor) {
  const count = product(descriptor.shape);
  const start = Number(descriptor.byteOffset);
  const byteLength = Number(descriptor.byteLength);
  const end = start + byteLength;
  assert(Number.isInteger(start) && start >= 0 && end <= raw.length, `${descriptor.name} byte range invalid`);
  const slice = raw.subarray(start, end);
  let values;
  if (descriptor.dtype === '<i4') {
    assert(byteLength === count * 4, `${descriptor.name} byte length mismatch`);
    values = new Int32Array(count);
    for (let index = 0; index < count; index += 1) values[index] = slice.readInt32LE(index * 4);
  } else if (descriptor.dtype === '|u1' || descriptor.dtype === 'u1') {
    assert(byteLength === count, `${descriptor.name} byte length mismatch`);
    values = Uint8Array.from(slice);
  } else {
    throw new Error(`[stage16-mesh-loader] unsupported dtype ${descriptor.dtype}`);
  }
  return Object.freeze({
    name: descriptor.name,
    dtype: descriptor.dtype,
    shape: Object.freeze([...descriptor.shape]),
    values,
  });
}

export async function loadMetricFvMesh({
  manifestPath = 'data/stage16/onga_fv_metric_mesh_compact_manifest_v1.json',
} = {}) {
  const resolvedManifest = path.resolve(manifestPath);
  const manifest = JSON.parse(await fs.readFile(resolvedManifest, 'utf8'));
  assert(manifest.schema === 'onga-metric-fv-mesh-compact-v1', 'manifest schema mismatch');
  assert(manifest.version === STAGE16_METRIC_MESH_VERSION, 'manifest version mismatch');
  assert(manifest.encoding === 'gzip+base64', 'manifest encoding mismatch');
  assert(Array.isArray(manifest.chunks) && manifest.chunks.length > 0, 'manifest chunks missing');
  const root = path.dirname(resolvedManifest);
  const encodedParts = [];
  for (const relative of manifest.chunks) {
    encodedParts.push((await fs.readFile(path.resolve(root, relative), 'ascii')).trim());
  }
  const encoded = encodedParts.join('');
  assert(encoded.length === manifest.base64Characters, 'base64 character count mismatch');
  const compressed = Buffer.from(encoded, 'base64');
  assert(compressed.length === manifest.compressedBytes, 'compressed byte count mismatch');
  assert(sha256(compressed) === manifest.sha256Compressed, 'compressed SHA-256 mismatch');
  const raw = zlib.gunzipSync(compressed);
  assert(raw.length === manifest.uncompressedBytes, 'uncompressed byte count mismatch');
  assert(sha256(raw) === manifest.sha256Uncompressed, 'uncompressed SHA-256 mismatch');
  const arrays = new Map();
  for (const descriptor of manifest.arrays) {
    assert(!arrays.has(descriptor.name), `duplicate array ${descriptor.name}`);
    arrays.set(descriptor.name, decodeArray(raw, descriptor));
  }
  const array = name => {
    const result = arrays.get(name);
    assert(result, `array ${name} missing`);
    return result;
  };
  return Object.freeze({
    version: STAGE16_METRIC_MESH_VERSION,
    manifestPath: resolvedManifest,
    manifest: Object.freeze(manifest),
    arrays,
    array,
    diagnostics: Object.freeze({
      compressedBytes: compressed.length,
      uncompressedBytes: raw.length,
      sha256Compressed: manifest.sha256Compressed,
      sha256Uncompressed: manifest.sha256Uncompressed,
    }),
  });
}
