export const STAGE15_UNSTRUCTURED_GEOMETRY_VERSION = 'stage15-unstructured-mesh-geometry-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-mesh] ${message}`);
}

function finite(value, label) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite`);
  return numeric;
}

function normaliseVertices(vertices) {
  assert(Array.isArray(vertices) && vertices.length >= 3, 'vertices must contain at least three points');
  return vertices.map((point, index) => {
    assert(Array.isArray(point) || ArrayBuffer.isView(point), `vertex ${index} must be a two-value vector`);
    assert(point.length === 2, `vertex ${index} must have length two`);
    return Object.freeze([
      finite(point[0], `vertex ${index} x`),
      finite(point[1], `vertex ${index} y`),
    ]);
  });
}

function orient2d(a, b, c) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function edgeKey(a, b) {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

function normaliseBoundaryMarkers(boundarySegments, vertexCount) {
  if (boundarySegments === null || boundarySegments === undefined) return new Map();
  assert(Array.isArray(boundarySegments), 'boundarySegments must be an array');
  const map = new Map();
  boundarySegments.forEach((entry, index) => {
    let a;
    let b;
    let marker;
    if (Array.isArray(entry)) {
      [a, b, marker = null] = entry;
    } else {
      a = entry?.a ?? entry?.vertices?.[0];
      b = entry?.b ?? entry?.vertices?.[1];
      marker = entry?.marker ?? entry?.id ?? null;
    }
    a = Number(a);
    b = Number(b);
    assert(Number.isInteger(a) && Number.isInteger(b), `boundary segment ${index} vertex ids must be integers`);
    assert(a >= 0 && a < vertexCount && b >= 0 && b < vertexCount && a !== b,
      `boundary segment ${index} vertex ids are invalid`);
    const key = edgeKey(a, b);
    assert(!map.has(key), `boundary segment ${index} duplicates ${key}`);
    map.set(key, marker);
  });
  return map;
}

function triangleGeometry(vertices, triangle, index, minimumDoubleArea) {
  assert(Array.isArray(triangle) || ArrayBuffer.isView(triangle), `triangle ${index} must be a vector`);
  assert(triangle.length === 3, `triangle ${index} must have three vertex ids`);
  let ids = Array.from(triangle, Number);
  assert(ids.every(Number.isInteger), `triangle ${index} vertex ids must be integers`);
  assert(new Set(ids).size === 3, `triangle ${index} repeats a vertex`);
  assert(ids.every(vertex => vertex >= 0 && vertex < vertices.length), `triangle ${index} has an invalid vertex id`);
  let doubleArea = orient2d(vertices[ids[0]], vertices[ids[1]], vertices[ids[2]]);
  assert(Math.abs(doubleArea) > minimumDoubleArea, `triangle ${index} is degenerate`);
  if (doubleArea < 0) {
    ids = [ids[0], ids[2], ids[1]];
    doubleArea = -doubleArea;
  }
  const area = 0.5 * doubleArea;
  const centroid = [
    (vertices[ids[0]][0] + vertices[ids[1]][0] + vertices[ids[2]][0]) / 3,
    (vertices[ids[0]][1] + vertices[ids[1]][1] + vertices[ids[2]][1]) / 3,
  ];
  return Object.freeze({
    id: index,
    vertices: Object.freeze(ids),
    area,
    centroid: Object.freeze(centroid),
  });
}

function directedFaceGeometry(vertices, a, b) {
  const pointA = vertices[a];
  const pointB = vertices[b];
  const dx = pointB[0] - pointA[0];
  const dy = pointB[1] - pointA[1];
  const length = Math.hypot(dx, dy);
  assert(length > 0, `edge ${a}:${b} has zero length`);
  return {
    length,
    midpoint: Object.freeze([(pointA[0] + pointB[0]) / 2, (pointA[1] + pointB[1]) / 2]),
    outwardNormal: Object.freeze([dy / length, -dx / length]),
  };
}

export function buildUnstructuredMeshGeometry({
  vertices,
  triangles,
  boundarySegments = null,
  minimumDoubleArea = 1e-14,
  requireAllMarkersMatched = true,
}) {
  const points = normaliseVertices(vertices);
  assert(Array.isArray(triangles) && triangles.length > 0, 'triangles must be a nonempty array');
  const minimumArea = finite(minimumDoubleArea, 'minimumDoubleArea');
  assert(minimumArea >= 0, 'minimumDoubleArea must be nonnegative');
  const cells = triangles.map((triangle, index) => triangleGeometry(points, triangle, index, minimumArea));
  const markerMap = normaliseBoundaryMarkers(boundarySegments, points.length);
  const incidences = new Map();

  for (const cell of cells) {
    const ids = cell.vertices;
    for (const [a, b] of [[ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[0]]]) {
      const key = edgeKey(a, b);
      const list = incidences.get(key) ?? [];
      list.push(Object.freeze({ cell: cell.id, a, b }));
      assert(list.length <= 2, `nonmanifold edge ${key} has more than two incident cells`);
      incidences.set(key, list);
    }
  }

  const interiorFaces = [];
  const boundaryFaces = [];
  const matchedMarkerKeys = new Set();

  for (const [key, list] of incidences) {
    if (list.length === 2) {
      let leftIncidence = list[0];
      let rightIncidence = list[1];
      let geometry = directedFaceGeometry(points, leftIncidence.a, leftIncidence.b);
      const leftCentroid = cells[leftIncidence.cell].centroid;
      const rightCentroid = cells[rightIncidence.cell].centroid;
      const displacement = [rightCentroid[0] - leftCentroid[0], rightCentroid[1] - leftCentroid[1]];
      let dot = geometry.outwardNormal[0] * displacement[0] + geometry.outwardNormal[1] * displacement[1];
      if (dot < 0) {
        [leftIncidence, rightIncidence] = [rightIncidence, leftIncidence];
        geometry = directedFaceGeometry(points, leftIncidence.a, leftIncidence.b);
        const newLeft = cells[leftIncidence.cell].centroid;
        const newRight = cells[rightIncidence.cell].centroid;
        dot = geometry.outwardNormal[0] * (newRight[0] - newLeft[0])
          + geometry.outwardNormal[1] * (newRight[1] - newLeft[1]);
      }
      assert(dot > 0, `interior face ${key} normal does not point from left to right`);
      interiorFaces.push(Object.freeze({
        id: interiorFaces.length,
        vertices: Object.freeze([leftIncidence.a, leftIncidence.b]),
        leftCell: leftIncidence.cell,
        rightCell: rightIncidence.cell,
        length: geometry.length,
        midpoint: geometry.midpoint,
        normal: geometry.outwardNormal,
        centreDistance: Math.hypot(
          cells[rightIncidence.cell].centroid[0] - cells[leftIncidence.cell].centroid[0],
          cells[rightIncidence.cell].centroid[1] - cells[leftIncidence.cell].centroid[1],
        ),
      }));
    } else {
      const incidence = list[0];
      const geometry = directedFaceGeometry(points, incidence.a, incidence.b);
      const marker = markerMap.has(key) ? markerMap.get(key) : null;
      if (markerMap.has(key)) matchedMarkerKeys.add(key);
      boundaryFaces.push(Object.freeze({
        id: boundaryFaces.length,
        vertices: Object.freeze([incidence.a, incidence.b]),
        cell: incidence.cell,
        length: geometry.length,
        midpoint: geometry.midpoint,
        normal: geometry.outwardNormal,
        marker,
      }));
    }
  }

  if (requireAllMarkersMatched) {
    for (const key of markerMap.keys()) assert(matchedMarkerKeys.has(key), `marked segment ${key} is not a mesh boundary`);
  }

  const neighbours = Array.from({ length: cells.length }, () => []);
  for (const face of interiorFaces) {
    neighbours[face.leftCell].push(face.rightCell);
    neighbours[face.rightCell].push(face.leftCell);
  }
  const totalArea = cells.reduce((sum, cell) => sum + cell.area, 0);
  const totalBoundaryLength = boundaryFaces.reduce((sum, face) => sum + face.length, 0);

  return Object.freeze({
    version: STAGE15_UNSTRUCTURED_GEOMETRY_VERSION,
    vertices: Object.freeze(points),
    cells: Object.freeze(cells),
    interiorFaces: Object.freeze(interiorFaces),
    boundaryFaces: Object.freeze(boundaryFaces),
    neighbours: Object.freeze(neighbours.map(list => Object.freeze([...list].sort((a, b) => a - b)))),
    totalArea,
    totalBoundaryLength,
    markerCount: markerMap.size,
  });
}

export function locatePointInMesh(mesh, x, y, tolerance = 1e-12) {
  const point = [finite(x, 'x'), finite(y, 'y')];
  const tol = finite(tolerance, 'tolerance');
  assert(tol >= 0, 'tolerance must be nonnegative');
  for (const cell of mesh.cells) {
    const [a, b, c] = cell.vertices.map(index => mesh.vertices[index]);
    const denominator = orient2d(a, b, c);
    const w0 = orient2d(b, c, point) / denominator;
    const w1 = orient2d(c, a, point) / denominator;
    const w2 = 1 - w0 - w1;
    if (w0 >= -tol && w1 >= -tol && w2 >= -tol) {
      return Object.freeze({
        cell: cell.id,
        barycentric: Object.freeze([w0, w1, w2]),
      });
    }
  }
  return null;
}

export function toShallowWaterMesh(mesh) {
  return Object.freeze({
    cellCount: mesh.cells.length,
    areas: Float64Array.from(mesh.cells, cell => cell.area),
    centroids: Object.freeze(mesh.cells.map(cell => cell.centroid)),
    faces: Object.freeze(mesh.interiorFaces.map(face => Object.freeze({
      left: face.leftCell,
      right: face.rightCell,
      length: face.length,
      nx: face.normal[0],
      ny: face.normal[1],
    }))),
    boundaryFaces: Object.freeze(mesh.boundaryFaces.map(face => Object.freeze({
      cell: face.cell,
      length: face.length,
      nx: face.normal[0],
      ny: face.normal[1],
      marker: face.marker,
    }))),
  });
}

export const Stage15UnstructuredMeshGeometry = Object.freeze({
  version: STAGE15_UNSTRUCTURED_GEOMETRY_VERSION,
  buildUnstructuredMeshGeometry,
  locatePointInMesh,
  toShallowWaterMesh,
});
