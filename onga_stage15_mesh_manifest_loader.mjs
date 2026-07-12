export const STAGE15_MESH_MANIFEST_VERSION = 'stage15-mesh-manifest-loader-v1';
export const STAGE15_MESH_MANIFEST_SCHEMA = 'onga-stage15-unstructured-mesh-manifest-v1';
export const STAGE15_MESH_CHUNK_SCHEMA = 'onga-stage15-unstructured-mesh-chunk-v1';

const KINDS = Object.freeze(['vertices', 'triangles', 'interiorFaces', 'boundaryFaces']);

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-mesh-loader] ${message}`);
}

function finite(value, label) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite`);
  return numeric;
}

function integer(value, label, minimum = 0) {
  const numeric = Number(value);
  if (!Number.isInteger(numeric) || numeric < minimum) {
    throw new RangeError(`${label} must be an integer >= ${minimum}`);
  }
  return numeric;
}

export function fnv1a32(text) {
  let hash = 0x811c9dc5;
  const bytes = new TextEncoder().encode(String(text));
  for (const byte of bytes) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

function validateManifest(manifest) {
  assert(manifest?.schema === STAGE15_MESH_MANIFEST_SCHEMA, 'manifest schema mismatch');
  assert(typeof manifest.version === 'string' && manifest.version.length > 0, 'manifest version is missing');
  assert(manifest.counts && typeof manifest.counts === 'object', 'manifest counts are missing');
  const counts = Object.fromEntries(KINDS.map(kind => [kind, integer(manifest.counts[kind], `counts.${kind}`)]));
  assert(Array.isArray(manifest.chunks) && manifest.chunks.length > 0, 'manifest chunks are missing');
  const chunks = manifest.chunks.map((chunk, index) => {
    const kind = String(chunk?.kind ?? '');
    assert(KINDS.includes(kind), `chunk ${index} has unsupported kind ${kind}`);
    const start = integer(chunk.start, `chunk ${index} start`);
    const count = integer(chunk.count, `chunk ${index} count`, 1);
    assert(start + count <= counts[kind], `chunk ${index} exceeds ${kind} count`);
    assert(typeof chunk.url === 'string' && chunk.url.length > 0, `chunk ${index} url is missing`);
    assert(/^[0-9a-f]{8}$/i.test(String(chunk.checksum)), `chunk ${index} checksum is invalid`);
    return Object.freeze({ kind, start, count, url: chunk.url, checksum: String(chunk.checksum).toLowerCase() });
  });
  return Object.freeze({ counts: Object.freeze(counts), chunks: Object.freeze(chunks) });
}

function validateCoverage(kind, count, chunks) {
  const selected = chunks.filter(chunk => chunk.kind === kind).sort((a, b) => a.start - b.start);
  if (count === 0) {
    assert(selected.length === 0, `${kind} count is zero but chunks exist`);
    return;
  }
  assert(selected.length > 0, `${kind} chunks are missing`);
  let cursor = 0;
  for (const chunk of selected) {
    assert(chunk.start === cursor, `${kind} coverage gap or overlap at ${cursor}`);
    cursor += chunk.count;
  }
  assert(cursor === count, `${kind} coverage ends at ${cursor} instead of ${count}`);
}

function validateRow(kind, row, index, counts) {
  assert(Array.isArray(row), `${kind}[${index}] must be an array`);
  if (kind === 'vertices') {
    assert(row.length === 2, `vertices[${index}] must have length 2`);
    return Object.freeze([finite(row[0], `vertices[${index}][0]`), finite(row[1], `vertices[${index}][1]`)]);
  }
  if (kind === 'triangles') {
    assert(row.length === 3, `triangles[${index}] must have length 3`);
    const ids = row.map((value, component) => integer(value, `triangles[${index}][${component}]`));
    assert(ids.every(id => id < counts.vertices), `triangles[${index}] has out-of-range vertex`);
    assert(new Set(ids).size === 3, `triangles[${index}] repeats a vertex`);
    return Object.freeze(ids);
  }
  if (kind === 'interiorFaces') {
    assert(row.length >= 8, `interiorFaces[${index}] must contain at least 8 values`);
    const a = integer(row[0], `interiorFaces[${index}][0]`);
    const b = integer(row[1], `interiorFaces[${index}][1]`);
    const left = integer(row[2], `interiorFaces[${index}][2]`);
    const right = integer(row[3], `interiorFaces[${index}][3]`);
    assert(a < counts.vertices && b < counts.vertices && a !== b, `interiorFaces[${index}] vertex ids are invalid`);
    assert(left < counts.triangles && right < counts.triangles && left !== right,
      `interiorFaces[${index}] cell ids are invalid`);
    const tail = row.slice(4).map((value, component) => finite(value, `interiorFaces[${index}][${component + 4}]`));
    assert(tail[0] > 0 && tail[1] > 0, `interiorFaces[${index}] length and centre distance must be positive`);
    return Object.freeze([a, b, left, right, ...tail]);
  }
  assert(kind === 'boundaryFaces', `unknown kind ${kind}`);
  assert(row.length >= 6, `boundaryFaces[${index}] must contain at least 6 values`);
  const a = integer(row[0], `boundaryFaces[${index}][0]`);
  const b = integer(row[1], `boundaryFaces[${index}][1]`);
  const cell = integer(row[2], `boundaryFaces[${index}][2]`);
  assert(a < counts.vertices && b < counts.vertices && a !== b, `boundaryFaces[${index}] vertex ids are invalid`);
  assert(cell < counts.triangles, `boundaryFaces[${index}] cell id is invalid`);
  const length = finite(row[3], `boundaryFaces[${index}][3]`);
  assert(length > 0, `boundaryFaces[${index}] length must be positive`);
  const midpointX = finite(row[4], `boundaryFaces[${index}][4]`);
  const midpointY = finite(row[5], `boundaryFaces[${index}][5]`);
  const marker = row.length > 6 ? row[6] : null;
  return Object.freeze([a, b, cell, length, midpointX, midpointY, marker]);
}

async function defaultFetchJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  assert(response.ok, `${url} fetch failed with HTTP ${response.status}`);
  return response.json();
}

export async function loadStage15MeshManifest(manifestOrUrl, options = {}) {
  const fetchJson = options.fetchJson ?? defaultFetchJson;
  const manifest = typeof manifestOrUrl === 'string'
    ? await fetchJson(manifestOrUrl)
    : manifestOrUrl;
  const definition = validateManifest(manifest);
  for (const kind of KINDS) validateCoverage(kind, definition.counts[kind], definition.chunks);

  const arrays = Object.fromEntries(KINDS.map(kind => [kind, new Array(definition.counts[kind])]));
  const loadedChunks = await Promise.all(definition.chunks.map(async chunk => {
    const payload = await fetchJson(chunk.url);
    assert(payload?.schema === STAGE15_MESH_CHUNK_SCHEMA, `${chunk.url} chunk schema mismatch`);
    assert(payload.kind === chunk.kind, `${chunk.url} kind mismatch`);
    assert(integer(payload.start, `${chunk.url} start`) === chunk.start, `${chunk.url} start mismatch`);
    assert(Array.isArray(payload.values) && payload.values.length === chunk.count, `${chunk.url} value count mismatch`);
    const canonical = JSON.stringify(payload.values);
    assert(fnv1a32(canonical) === chunk.checksum, `${chunk.url} checksum mismatch`);
    return { chunk, values: payload.values };
  }));

  for (const { chunk, values } of loadedChunks) {
    values.forEach((row, offset) => {
      const index = chunk.start + offset;
      assert(arrays[chunk.kind][index] === undefined, `${chunk.kind}[${index}] is duplicated`);
      arrays[chunk.kind][index] = validateRow(chunk.kind, row, index, definition.counts);
    });
  }
  for (const kind of KINDS) assert(arrays[kind].every(value => value !== undefined), `${kind} contains an unloaded row`);

  return Object.freeze({
    loaderVersion: STAGE15_MESH_MANIFEST_VERSION,
    manifest,
    counts: definition.counts,
    vertices: Object.freeze(arrays.vertices),
    triangles: Object.freeze(arrays.triangles),
    interiorFaces: Object.freeze(arrays.interiorFaces),
    boundaryFaces: Object.freeze(arrays.boundaryFaces),
  });
}

export const Stage15MeshManifestLoader = Object.freeze({
  version: STAGE15_MESH_MANIFEST_VERSION,
  manifestSchema: STAGE15_MESH_MANIFEST_SCHEMA,
  chunkSchema: STAGE15_MESH_CHUNK_SCHEMA,
  fnv1a32,
  loadStage15MeshManifest,
});
