import { loadMetricFvMesh } from './onga_stage16_metric_fv_mesh_loader.mjs';

export const STAGE16_ACTUAL_MESH_ADAPTER_VERSION = 'stage16-actual-mesh-adapter-v1';

const BOUNDARY_TAGS = Object.freeze(['shoreline', 'M', 'N', 'O', 'G']);

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-actual-mesh] ${message}`);
}

function finite(value, label) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite`);
  return numeric;
}

function pair(values, index) {
  return [Number(values[2 * index]), Number(values[2 * index + 1])];
}

function metricVertices(packageData) {
  const descriptor = packageData.array('vertexLocalMillimetreXY');
  const quantization = packageData.manifest.quantization?.vertexLocalMillimetreXY;
  const scale = finite(quantization?.scaleToMetre ?? 0.001, 'vertex scaleToMetre');
  assert(scale > 0, 'vertex scale must be positive');
  return Float64Array.from(descriptor.values, value => Number(value) * scale);
}

function cellGeometry(vertices, triangles, cellCount) {
  const areas = new Float64Array(cellCount);
  const centroids = new Float64Array(cellCount * 2);
  let totalArea = 0;
  let minimumArea = Infinity;
  let maximumArea = 0;
  for (let cell = 0; cell < cellCount; cell += 1) {
    const ids = [triangles[3 * cell], triangles[3 * cell + 1], triangles[3 * cell + 2]];
    for (const vertex of ids) {
      assert(Number.isInteger(vertex) && vertex >= 0 && 2 * vertex + 1 < vertices.length,
        `cell ${cell} vertex ${vertex} is invalid`);
    }
    const a = pair(vertices, ids[0]);
    const b = pair(vertices, ids[1]);
    const c = pair(vertices, ids[2]);
    const signedDoubleArea = (b[0] - a[0]) * (c[1] - a[1])
      - (b[1] - a[1]) * (c[0] - a[0]);
    const area = 0.5 * Math.abs(signedDoubleArea);
    assert(Number.isFinite(area) && area > 0, `cell ${cell} has nonpositive area`);
    areas[cell] = area;
    centroids[2 * cell] = (a[0] + b[0] + c[0]) / 3;
    centroids[2 * cell + 1] = (a[1] + b[1] + c[1]) / 3;
    totalArea += area;
    minimumArea = Math.min(minimumArea, area);
    maximumArea = Math.max(maximumArea, area);
  }
  return Object.freeze({ areas, centroids, totalArea, minimumArea, maximumArea });
}

function orientedInternalFace(vertices, centroids, vertex0, vertex1, left, right, id) {
  const a = pair(vertices, vertex0);
  const b = pair(vertices, vertex1);
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = Math.hypot(dx, dy);
  assert(Number.isFinite(length) && length > 0, `internal face ${id} has invalid length`);
  let nx = dy / length;
  let ny = -dx / length;
  const centreDx = centroids[2 * right] - centroids[2 * left];
  const centreDy = centroids[2 * right + 1] - centroids[2 * left + 1];
  if (nx * centreDx + ny * centreDy < 0) {
    nx = -nx;
    ny = -ny;
  }
  const orientation = nx * centreDx + ny * centreDy;
  assert(orientation > 0, `internal face ${id} normal is not left-to-right`);
  return Object.freeze({ id, left, right, length, nx, ny, vertex0, vertex1, orientation });
}

function orientedBoundaryFace(vertices, centroids, vertex0, vertex1, cell, tagCode, id) {
  const a = pair(vertices, vertex0);
  const b = pair(vertices, vertex1);
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = Math.hypot(dx, dy);
  assert(Number.isFinite(length) && length > 0, `boundary face ${id} has invalid length`);
  let nx = dy / length;
  let ny = -dx / length;
  const midpointX = 0.5 * (a[0] + b[0]);
  const midpointY = 0.5 * (a[1] + b[1]);
  const outwardDx = midpointX - centroids[2 * cell];
  const outwardDy = midpointY - centroids[2 * cell + 1];
  if (nx * outwardDx + ny * outwardDy < 0) {
    nx = -nx;
    ny = -ny;
  }
  const orientation = nx * outwardDx + ny * outwardDy;
  assert(orientation > 0, `boundary face ${id} normal is not outward`);
  assert(Number.isInteger(tagCode) && tagCode >= 0 && tagCode < BOUNDARY_TAGS.length,
    `boundary face ${id} tag ${tagCode} is invalid`);
  return Object.freeze({
    id,
    cell,
    length,
    nx,
    ny,
    vertex0,
    vertex1,
    tagCode,
    tag: BOUNDARY_TAGS[tagCode],
    orientation,
  });
}

function faceGeometry(packageData, vertices, centroids, cellCount) {
  const internalVertexIds = packageData.array('internalFaceVertexIds').values;
  const internalCells = packageData.array('internalFaceCells').values;
  const boundaryVertexIds = packageData.array('boundaryFaceVertexIds').values;
  const boundaryCells = packageData.array('boundaryFaceCell').values;
  const boundaryTags = packageData.array('boundaryFaceTag').values;
  assert(internalVertexIds.length === internalCells.length && internalCells.length % 2 === 0,
    'internal face arrays have inconsistent shapes');
  assert(boundaryVertexIds.length === 2 * boundaryCells.length
    && boundaryCells.length === boundaryTags.length,
  'boundary face arrays have inconsistent shapes');
  const internalFaces = new Array(internalCells.length / 2);
  for (let face = 0; face < internalFaces.length; face += 1) {
    const left = internalCells[2 * face];
    const right = internalCells[2 * face + 1];
    assert(left >= 0 && left < cellCount && right >= 0 && right < cellCount && left !== right,
      `internal face ${face} cell ids are invalid`);
    internalFaces[face] = orientedInternalFace(
      vertices,
      centroids,
      internalVertexIds[2 * face],
      internalVertexIds[2 * face + 1],
      left,
      right,
      face,
    );
  }
  const boundaryFaces = new Array(boundaryCells.length);
  for (let face = 0; face < boundaryFaces.length; face += 1) {
    const cell = boundaryCells[face];
    assert(cell >= 0 && cell < cellCount, `boundary face ${face} cell is invalid`);
    boundaryFaces[face] = orientedBoundaryFace(
      vertices,
      centroids,
      boundaryVertexIds[2 * face],
      boundaryVertexIds[2 * face + 1],
      cell,
      boundaryTags[face],
      face,
    );
  }
  return Object.freeze({
    internalFaces: Object.freeze(internalFaces),
    boundaryFaces: Object.freeze(boundaryFaces),
  });
}

function boundaryGroups(boundaryFaces) {
  const result = Object.fromEntries(BOUNDARY_TAGS.map(tag => [tag, []]));
  for (const face of boundaryFaces) result[face.tag].push(face);
  return Object.freeze(Object.fromEntries(
    Object.entries(result).map(([tag, faces]) => [tag, Object.freeze(faces)]),
  ));
}

function structureMetadata(packageData, internalFaceCount, cellCount) {
  const barrageFaceIds = packageData.array('barrageFaceIds').values;
  const barrageGateId = packageData.array('barrageGateId').values;
  const fishwayCells = packageData.array('fishwayCells').values;
  const fishwayComponents = packageData.array('fishwayComponents').values;
  assert(barrageFaceIds.length === barrageGateId.length, 'barrage arrays length mismatch');
  const barrageFaceMask = new Uint8Array(internalFaceCount);
  const gates = Object.fromEntries(Array.from({ length: 8 }, (_, index) => [String(index + 1), []]));
  for (let index = 0; index < barrageFaceIds.length; index += 1) {
    const face = barrageFaceIds[index];
    const gate = barrageGateId[index];
    assert(face >= 0 && face < internalFaceCount, `barrage face ${face} is invalid`);
    assert(gate >= 1 && gate <= 8, `barrage gate ${gate} is invalid`);
    assert(!barrageFaceMask[face], `duplicate barrage face ${face}`);
    barrageFaceMask[face] = 1;
    gates[String(gate)].push(face);
  }
  assert(fishwayCells.length === 2 && fishwayComponents.length === 2,
    'fishway mapping must contain two cells and two components');
  for (const cell of fishwayCells) assert(cell >= 0 && cell < cellCount, `fishway cell ${cell} is invalid`);
  return Object.freeze({
    barrageFaceIds: Int32Array.from(barrageFaceIds),
    barrageGateId: Uint8Array.from(barrageGateId),
    barrageFaceMask,
    gates: Object.freeze(Object.fromEntries(
      Object.entries(gates).map(([gate, faces]) => [gate, Object.freeze(faces)]),
    )),
    fishwayCells: Int32Array.from(fishwayCells),
    fishwayComponents: Int32Array.from(fishwayComponents),
  });
}

export function allWallBoundaries(mesh) {
  return Object.freeze(mesh.boundaryFaces.map(face => Object.freeze({ ...face, type: 'wall' })));
}

export function boundaryStateFaces(mesh, stateByTag, { defaultType = 'wall' } = {}) {
  assert(stateByTag && typeof stateByTag === 'object', 'stateByTag must be an object');
  return Object.freeze(mesh.boundaryFaces.map(face => {
    const specification = stateByTag[face.tag];
    if (specification === undefined || specification === null) {
      assert(defaultType === 'wall', `no state supplied for ${face.tag}`);
      return Object.freeze({ ...face, type: 'wall' });
    }
    return Object.freeze({ ...face, type: 'state', state: specification });
  }));
}

export function activeInternalFaces(mesh, { barrageOpening = 1, gateOpenings = null } = {}) {
  const uniform = finite(barrageOpening, 'barrageOpening');
  assert(uniform >= 0 && uniform <= 1, 'barrageOpening must be in [0, 1]');
  if (gateOpenings !== null) {
    assert(Array.isArray(gateOpenings) || ArrayBuffer.isView(gateOpenings),
      'gateOpenings must be an Array or typed array');
    assert(gateOpenings.length === 8, 'gateOpenings length must be 8');
  }
  return Object.freeze(mesh.internalFaces.filter(face => {
    if (!mesh.structures.barrageFaceMask[face.id]) return true;
    let opening = uniform;
    if (gateOpenings !== null) {
      const index = mesh.structures.barrageFaceIds.indexOf(face.id);
      assert(index >= 0, `barrage face ${face.id} metadata is missing`);
      opening = finite(gateOpenings[mesh.structures.barrageGateId[index] - 1],
        `gateOpenings[${mesh.structures.barrageGateId[index] - 1}]`);
      assert(opening >= 0 && opening <= 1, 'gate opening must be in [0, 1]');
    }
    return opening > 0;
  }));
}

export function connectedComponents(mesh, faces = mesh.internalFaces) {
  const adjacency = Array.from({ length: mesh.cellCount }, () => []);
  for (const face of faces) {
    adjacency[face.left].push(face.right);
    adjacency[face.right].push(face.left);
  }
  const labels = new Int32Array(mesh.cellCount);
  labels.fill(-1);
  let count = 0;
  for (let seed = 0; seed < mesh.cellCount; seed += 1) {
    if (labels[seed] >= 0) continue;
    labels[seed] = count;
    const queue = [seed];
    for (let head = 0; head < queue.length; head += 1) {
      for (const neighbour of adjacency[queue[head]]) {
        if (labels[neighbour] < 0) {
          labels[neighbour] = count;
          queue.push(neighbour);
        }
      }
    }
    count += 1;
  }
  return Object.freeze({ count, labels });
}

export async function loadStage16ActualMesh(options = {}) {
  const packageData = await loadMetricFvMesh(options);
  const counts = packageData.manifest.counts;
  const vertices = metricVertices(packageData);
  const triangles = Int32Array.from(packageData.array('triangles').values);
  assert(vertices.length === counts.vertices * 2, 'vertex count mismatch');
  assert(triangles.length === counts.cells * 3, 'triangle count mismatch');
  const geometry = cellGeometry(vertices, triangles, counts.cells);
  const faces = faceGeometry(packageData, vertices, geometry.centroids, counts.cells);
  assert(faces.internalFaces.length === counts.internalFaces, 'internal face count mismatch');
  assert(faces.boundaryFaces.length === counts.boundaryFaces, 'boundary face count mismatch');
  const structures = structureMetadata(
    packageData,
    faces.internalFaces.length,
    counts.cells,
  );
  const mesh = {
    version: STAGE16_ACTUAL_MESH_ADAPTER_VERSION,
    packageVersion: packageData.version,
    packageData,
    vertexCount: counts.vertices,
    cellCount: counts.cells,
    vertices,
    triangles,
    areas: geometry.areas,
    centroids: geometry.centroids,
    totalArea: geometry.totalArea,
    minimumArea: geometry.minimumArea,
    maximumArea: geometry.maximumArea,
    internalFaces: faces.internalFaces,
    boundaryFaces: faces.boundaryFaces,
    boundaryGroups: boundaryGroups(faces.boundaryFaces),
    structures,
    referenceSections: Object.freeze(packageData.manifest.referenceSections),
    safeguards: Object.freeze(packageData.manifest.safeguards),
  };
  return Object.freeze(mesh);
}
