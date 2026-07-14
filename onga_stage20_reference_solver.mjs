export const STAGE20_REFERENCE_SOLVER_VERSION = 'stage20-browser-reference-solver-v1';
export const GRAVITY_M_S2 = 9.80665;

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-reference-solver] ${message}`);
}

function f64(length, value = 0) {
  const result = new Float64Array(length);
  if (value !== 0) result.fill(value);
  return result;
}

export function buildStage20ReferenceGeometry(mesh) {
  const a = mesh.arrays;
  const vertexCount = a.vertex_local_mm.length / 2;
  const cellCount = a.triangles.length / 3;
  const verticesX = f64(vertexCount);
  const verticesY = f64(vertexCount);
  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    verticesX[vertex] = a.vertex_local_mm[2 * vertex] * 1e-3;
    verticesY[vertex] = a.vertex_local_mm[2 * vertex + 1] * 1e-3;
  }
  const centroidX = f64(cellCount);
  const centroidY = f64(cellCount);
  const areas = f64(cellCount);
  for (let cell = 0; cell < cellCount; cell += 1) {
    const i = 3 * cell;
    const p0 = a.triangles[i];
    const p1 = a.triangles[i + 1];
    const p2 = a.triangles[i + 2];
    centroidX[cell] = (verticesX[p0] + verticesX[p1] + verticesX[p2]) / 3;
    centroidY[cell] = (verticesY[p0] + verticesY[p1] + verticesY[p2]) / 3;
    areas[cell] = Math.abs(
      (verticesX[p1] - verticesX[p0]) * (verticesY[p2] - verticesY[p0])
      - (verticesY[p1] - verticesY[p0]) * (verticesX[p2] - verticesX[p0]),
    ) / 2;
    assert(Number.isFinite(areas[cell]) && areas[cell] > 0, `invalid area at cell ${cell}`);
  }

  function faceMetrics(faceVertices, faceCells, boundary = false) {
    const count = boundary ? faceCells.length : faceCells.length / 2;
    const lengths = f64(count);
    const nx = f64(count);
    const ny = f64(count);
    for (let face = 0; face < count; face += 1) {
      const p0 = faceVertices[2 * face];
      const p1 = faceVertices[2 * face + 1];
      const dx = verticesX[p1] - verticesX[p0];
      const dy = verticesY[p1] - verticesY[p0];
      const length = Math.hypot(dx, dy);
      assert(Number.isFinite(length) && length > 0, `invalid length at face ${face}`);
      let normalX = dy / length;
      let normalY = -dx / length;
      const left = boundary ? faceCells[face] : faceCells[2 * face];
      const directionX = boundary
        ? (verticesX[p0] + verticesX[p1]) / 2 - centroidX[left]
        : centroidX[faceCells[2 * face + 1]] - centroidX[left];
      const directionY = boundary
        ? (verticesY[p0] + verticesY[p1]) / 2 - centroidY[left]
        : centroidY[faceCells[2 * face + 1]] - centroidY[left];
      if (normalX * directionX + normalY * directionY < 0) {
        normalX *= -1;
        normalY *= -1;
      }
      lengths[face] = length;
      nx[face] = normalX;
      ny[face] = normalY;
    }
    return Object.freeze({ lengths, nx, ny });
  }

  const internal = faceMetrics(a.internal_face_vertices, a.internal_face_cells);
  const boundary = faceMetrics(a.boundary_face_vertices, a.boundary_face_cell, true);
  const barrageMask = new Uint8Array(internal.lengths.length);
  for (const face of a.barrage_face_ids) barrageMask[face] = 1;
  return Object.freeze({
    version: STAGE20_REFERENCE_SOLVER_VERSION,
    cellCount,
    vertexCount,
    verticesX,
    verticesY,
    centroidX,
    centroidY,
    areas,
    internal: Object.freeze({
      cells: a.internal_face_cells,
      ...internal,
      barrageMask,
    }),
    boundary: Object.freeze({ cells: a.boundary_face_cell, tags: a.boundary_face_tag, ...boundary }),
  });
}

export function createUniformState(cellCount, depthM = 3, manningN = 0.03) {
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount is invalid');
  assert(Number.isFinite(depthM) && depthM > 0, 'depthM is invalid');
  assert(Number.isFinite(manningN) && manningN > 0, 'manningN is invalid');
  return Object.freeze({
    h: f64(cellCount, depthM),
    hu: f64(cellCount),
    hv: f64(cellCount),
    manning: f64(cellCount, manningN),
  });
}

export function flatWaterResidual(geometry, state, options = {}) {
  const gravity = Number(options.gravity ?? GRAVITY_M_S2);
  const count = geometry.cellCount;
  const rh = f64(count);
  const rhu = f64(count);
  const rhv = f64(count);
  const denominator = f64(count);
  const { cells, lengths, nx, ny } = geometry.internal;
  for (let face = 0; face < lengths.length; face += 1) {
    const left = cells[2 * face];
    const right = cells[2 * face + 1];
    const hLeft = state.h[left];
    const hRight = state.h[right];
    const huLeft = state.hu[left];
    const huRight = state.hu[right];
    const hvLeft = state.hv[left];
    const hvRight = state.hv[right];
    const unLeft = (huLeft * nx[face] + hvLeft * ny[face]) / hLeft;
    const unRight = (huRight * nx[face] + hvRight * ny[face]) / hRight;
    const speed = Math.max(Math.abs(unLeft) + Math.sqrt(gravity * hLeft), Math.abs(unRight) + Math.sqrt(gravity * hRight));
    const mass = 0.5 * (hLeft * unLeft + hRight * unRight) - 0.5 * speed * (hRight - hLeft);
    const mx = 0.5 * (
      huLeft * unLeft + 0.5 * gravity * hLeft * hLeft * nx[face]
      + huRight * unRight + 0.5 * gravity * hRight * hRight * nx[face]
    ) - 0.5 * speed * (huRight - huLeft);
    const my = 0.5 * (
      hvLeft * unLeft + 0.5 * gravity * hLeft * hLeft * ny[face]
      + hvRight * unRight + 0.5 * gravity * hRight * hRight * ny[face]
    ) - 0.5 * speed * (hvRight - hvLeft);
    const scale = lengths[face];
    rh[left] += scale * mass; rhu[left] += scale * mx; rhv[left] += scale * my;
    rh[right] -= scale * mass; rhu[right] -= scale * mx; rhv[right] -= scale * my;
    denominator[left] += scale * speed;
    denominator[right] += scale * speed;
  }
  const boundary = geometry.boundary;
  for (let face = 0; face < boundary.lengths.length; face += 1) {
    const cell = boundary.cells[face];
    const depth = state.h[cell];
    const normalMomentum = state.hu[cell] * boundary.nx[face] + state.hv[cell] * boundary.ny[face];
    const ghostHu = state.hu[cell] - 2 * normalMomentum * boundary.nx[face];
    const ghostHv = state.hv[cell] - 2 * normalMomentum * boundary.ny[face];
    const unLeft = normalMomentum / depth;
    const unRight = (ghostHu * boundary.nx[face] + ghostHv * boundary.ny[face]) / depth;
    const speed = Math.max(Math.abs(unLeft), Math.abs(unRight)) + Math.sqrt(gravity * depth);
    const mass = 0.5 * depth * (unLeft + unRight);
    const mx = 0.5 * (
      state.hu[cell] * unLeft + ghostHu * unRight + gravity * depth * depth * boundary.nx[face]
    ) - 0.5 * speed * (ghostHu - state.hu[cell]);
    const my = 0.5 * (
      state.hv[cell] * unLeft + ghostHv * unRight + gravity * depth * depth * boundary.ny[face]
    ) - 0.5 * speed * (ghostHv - state.hv[cell]);
    const scale = boundary.lengths[face];
    rh[cell] += scale * mass; rhu[cell] += scale * mx; rhv[cell] += scale * my;
    denominator[cell] += scale * speed;
  }
  let dt = Infinity;
  const cfl = Number(options.cfl ?? 0.12);
  for (let cell = 0; cell < count; cell += 1) {
    if (denominator[cell] > 0) dt = Math.min(dt, cfl * geometry.areas[cell] / denominator[cell]);
  }
  return Object.freeze({ rh, rhu, rhv, denominator, dt });
}

export async function createWasmStateUpdater(wasmUrl, cellCount, options = {}) {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const response = await fetchImpl(wasmUrl, { cache: 'no-store' });
  assert(response.ok, `WASM fetch failed with HTTP ${response.status}`);
  const bytes = await response.arrayBuffer();
  const module = await WebAssembly.instantiate(bytes, { env: { pow: Math.pow } });
  const api = module.instance.exports;
  api.reset_allocator();
  const names = ['h', 'hu', 'hv', 'rh', 'rhu', 'rhv', 'area', 'manning'];
  const pointers = Object.fromEntries(names.map(name => [name, api.allocate(cellCount * 8)]));
  const arrays = Object.fromEntries(names.map(name => [name, new Float64Array(api.memory.buffer, pointers[name], cellCount)]));
  return Object.freeze({
    wasmBytes: bytes.byteLength,
    advance(state, residual, areas, manning, dt, gravity = GRAVITY_M_S2, minimumDepth = 1e-8) {
      arrays.h.set(state.h); arrays.hu.set(state.hu); arrays.hv.set(state.hv);
      arrays.rh.set(residual.rh); arrays.rhu.set(residual.rhu); arrays.rhv.set(residual.rhv);
      arrays.area.set(areas); arrays.manning.set(manning);
      const clippedCells = api.advance_state(
        cellCount, pointers.h, pointers.hu, pointers.hv, pointers.rh, pointers.rhu, pointers.rhv,
        pointers.area, pointers.manning, dt, gravity, minimumDepth,
      );
      state.h.set(arrays.h); state.hu.set(arrays.hu); state.hv.set(arrays.hv);
      return clippedCells;
    },
  });
}

export function summariseState(state, referenceDepth) {
  let maxVelocity = 0;
  let maxDepthDrift = 0;
  let nonFinite = 0;
  for (let cell = 0; cell < state.h.length; cell += 1) {
    const velocity = Math.hypot(state.hu[cell], state.hv[cell]) / state.h[cell];
    maxVelocity = Math.max(maxVelocity, velocity);
    maxDepthDrift = Math.max(maxDepthDrift, Math.abs(state.h[cell] - referenceDepth));
    if (!Number.isFinite(state.h[cell]) || !Number.isFinite(state.hu[cell]) || !Number.isFinite(state.hv[cell])) nonFinite += 1;
  }
  return Object.freeze({ maxVelocity, maxDepthDrift, nonFinite });
}
