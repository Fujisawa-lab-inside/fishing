export const STAGE20_BROWSER_MESH_SCHEMA = 'onga-stage20-browser-mesh-v1';
export const STAGE20_BROWSER_MESH_SCHEMAS = Object.freeze([
  STAGE20_BROWSER_MESH_SCHEMA,
  'onga-stage20-browser-mesh-v2',
]);

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-browser-mesh] ${message}`);
}

function hex(bytes) {
  return Array.from(new Uint8Array(bytes), value => value.toString(16).padStart(2, '0')).join('');
}

async function sha256(buffer) {
  assert(globalThis.crypto?.subtle, 'Web Crypto SHA-256 is unavailable');
  return hex(await globalThis.crypto.subtle.digest('SHA-256', buffer));
}

function product(values) {
  return values.reduce((result, value) => result * value, 1);
}

export function decodeStage20BrowserMesh(manifest, buffer) {
  assert(STAGE20_BROWSER_MESH_SCHEMAS.includes(manifest?.schema), 'manifest schema mismatch');
  assert(manifest.status === 'approved_canonical_geometry_only', 'mesh is not approved canonical geometry');
  assert(buffer instanceof ArrayBuffer, 'mesh payload must be an ArrayBuffer');
  assert(buffer.byteLength === manifest.binary.byteLength, 'mesh payload byte length mismatch');
  const arrays = {};
  for (const [name, descriptor] of Object.entries(manifest.arrays)) {
    assert(Array.isArray(descriptor.shape) && descriptor.shape.length > 0, `${name} shape is invalid`);
    const Type = descriptor.dtype === 'int32' ? Int32Array : descriptor.dtype === 'uint8' ? Uint8Array : null;
    assert(Type, `${name} dtype is unsupported`);
    const length = product(descriptor.shape);
    assert(length * Type.BYTES_PER_ELEMENT === descriptor.byteLength, `${name} byte length mismatch`);
    assert(descriptor.byteOffset % Type.BYTES_PER_ELEMENT === 0, `${name} byte offset is unaligned`);
    assert(descriptor.byteOffset + descriptor.byteLength <= buffer.byteLength, `${name} exceeds payload`);
    arrays[name] = new Type(buffer, descriptor.byteOffset, length);
  }
  assert(arrays.triangles.length / 3 === manifest.counts.cells, 'cell count mismatch');
  assert(arrays.vertex_local_mm.length / 2 === manifest.counts.vertices, 'vertex count mismatch');
  assert(arrays.internal_face_cells.length / 2 === manifest.counts.internalFaces, 'internal-face count mismatch');
  assert(arrays.boundary_face_cell.length === manifest.counts.boundaryFaces, 'boundary-face count mismatch');
  assert(arrays.barrage_face_ids.length === manifest.counts.barrageFaces, 'barrage-face count mismatch');
  return Object.freeze({ manifest: Object.freeze(manifest), buffer, arrays: Object.freeze(arrays) });
}

export async function loadStage20BrowserMesh(manifestUrl, options = {}) {
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
  assert(await sha256(buffer) === manifest.binary.sha256, 'mesh payload SHA-256 mismatch');
  return decodeStage20BrowserMesh(manifest, buffer);
}
