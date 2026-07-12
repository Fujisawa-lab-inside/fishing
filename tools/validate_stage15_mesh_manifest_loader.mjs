import fs from 'node:fs/promises';
import {
  STAGE15_MESH_CHUNK_SCHEMA,
  STAGE15_MESH_MANIFEST_SCHEMA,
  STAGE15_MESH_MANIFEST_VERSION,
  fnv1a32,
  loadStage15MeshManifest,
} from '../onga_stage15_mesh_manifest_loader.mjs';

const outputPath = process.argv[2] || 'stage15-mesh-manifest-loader-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const datasets = {
  vertices: [[0, 0], [1, 0], [1, 1], [0, 1]],
  triangles: [[0, 1, 2], [0, 2, 3]],
  interiorFaces: [[0, 2, 0, 1, Math.SQRT2, Math.SQRT1_2, 0.5, 0.5]],
  boundaryFaces: [
    [0, 1, 0, 1, 0.5, 0, 10],
    [1, 2, 0, 1, 1, 0.5, 20],
    [2, 3, 1, 1, 0.5, 1, 30],
    [3, 0, 1, 1, 0, 0.5, 40],
  ],
};

const payloads = new Map();
const chunks = [];
for (const [kind, values] of Object.entries(datasets)) {
  const split = kind === 'vertices' || kind === 'boundaryFaces' ? 2 : values.length;
  for (let start = 0, part = 0; start < values.length; start += split, part += 1) {
    const rows = values.slice(start, start + split);
    const url = `memory://${kind}-${part}`;
    payloads.set(url, {
      schema: STAGE15_MESH_CHUNK_SCHEMA,
      kind,
      start,
      values: rows,
    });
    chunks.push({
      kind,
      start,
      count: rows.length,
      url,
      checksum: fnv1a32(JSON.stringify(rows)),
    });
  }
}

const manifest = {
  schema: STAGE15_MESH_MANIFEST_SCHEMA,
  version: 'synthetic-square-v1',
  counts: Object.fromEntries(Object.entries(datasets).map(([kind, values]) => [kind, values.length])),
  chunks,
};
const fetchJson = async url => {
  if (!payloads.has(url)) throw new Error(`missing synthetic payload ${url}`);
  return structuredClone(payloads.get(url));
};
const mesh = await loadStage15MeshManifest(manifest, { fetchJson });

let checksumRejected = false;
try {
  const badManifest = structuredClone(manifest);
  badManifest.chunks[0].checksum = '00000000';
  await loadStage15MeshManifest(badManifest, { fetchJson });
} catch (_) {
  checksumRejected = true;
}

let gapRejected = false;
try {
  const badManifest = structuredClone(manifest);
  badManifest.chunks = badManifest.chunks.filter(chunk => !(chunk.kind === 'vertices' && chunk.start === 2));
  await loadStage15MeshManifest(badManifest, { fetchJson });
} catch (_) {
  gapRejected = true;
}

let badReferenceRejected = false;
try {
  const badPayloads = new Map(payloads);
  const triangleUrl = manifest.chunks.find(chunk => chunk.kind === 'triangles').url;
  const payload = structuredClone(badPayloads.get(triangleUrl));
  payload.values[0] = [0, 1, 99];
  badPayloads.set(triangleUrl, payload);
  const badManifest = structuredClone(manifest);
  const descriptor = badManifest.chunks.find(chunk => chunk.url === triangleUrl);
  descriptor.checksum = fnv1a32(JSON.stringify(payload.values));
  await loadStage15MeshManifest(badManifest, {
    fetchJson: async url => structuredClone(badPayloads.get(url)),
  });
} catch (_) {
  badReferenceRejected = true;
}

let overlapRejected = false;
try {
  const badManifest = structuredClone(manifest);
  const vertexChunk = structuredClone(badManifest.chunks.find(chunk => chunk.kind === 'vertices'));
  vertexChunk.url = 'memory://duplicate';
  payloads.set(vertexChunk.url, {
    schema: STAGE15_MESH_CHUNK_SCHEMA,
    kind: 'vertices',
    start: vertexChunk.start,
    values: datasets.vertices.slice(vertexChunk.start, vertexChunk.start + vertexChunk.count),
  });
  badManifest.chunks.push(vertexChunk);
  await loadStage15MeshManifest(badManifest, { fetchJson });
} catch (_) {
  overlapRejected = true;
}

const checks = [
  check('loader version', mesh.loaderVersion, STAGE15_MESH_MANIFEST_VERSION,
    mesh.loaderVersion === STAGE15_MESH_MANIFEST_VERSION),
  check('vertex count', mesh.vertices.length, 4, mesh.vertices.length === 4),
  check('triangle count', mesh.triangles.length, 2, mesh.triangles.length === 2),
  check('interior face count', mesh.interiorFaces.length, 1, mesh.interiorFaces.length === 1),
  check('boundary face count', mesh.boundaryFaces.length, 4, mesh.boundaryFaces.length === 4),
  check('chunk ordering restored', mesh.vertices[3].join(','), '0,1', mesh.vertices[3].join(',') === '0,1'),
  check('boundary marker retained', mesh.boundaryFaces[2][6], 30, mesh.boundaryFaces[2][6] === 30),
  check('checksum corruption rejected', checksumRejected, true, checksumRejected),
  check('coverage gap rejected', gapRejected, true, gapRejected),
  check('out-of-range reference rejected', badReferenceRejected, true, badReferenceRejected),
  check('overlapping coverage rejected', overlapRejected, true, overlapRejected),
];

const report = {
  schema: 'onga-stage15-mesh-manifest-loader-validation-v1',
  moduleVersion: STAGE15_MESH_MANIFEST_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    productionMeshIncluded: false,
    publicRuntimeConnected: false,
    modifiesApprovedWaterGeometry: false,
    physicalValuesAssigned: false,
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
