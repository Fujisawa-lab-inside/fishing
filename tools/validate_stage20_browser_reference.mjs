import { readFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { decodeStage20BrowserMesh } from '../onga_stage20_browser_mesh.mjs';
import {
  buildStage20ReferenceGeometry,
  createUniformState,
  createWasmStateUpdater,
  flatWaterResidual,
  summariseState,
} from '../onga_stage20_reference_solver.mjs';

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

const manifest = JSON.parse(await readFile('public/data/onga/stage20/mesh-v1.json', 'utf8'));
const binary = await readFile('public/data/onga/stage20/mesh-v1.bin');
const arrayBuffer = binary.buffer.slice(binary.byteOffset, binary.byteOffset + binary.byteLength);
const mesh = decodeStage20BrowserMesh(manifest, arrayBuffer);
const started = performance.now();
const geometry = buildStage20ReferenceGeometry(mesh);
const state = createUniformState(geometry.cellCount, 3, 0.03);
const residual = flatWaterResidual(geometry, state, { cfl: 0.12 });
const wasm = await readFile('public/wasm/stage20-reference-kernel-v1.wasm');
const fetchImpl = async () => ({
  ok: true,
  status: 200,
  arrayBuffer: async () => wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength),
});
const updater = await createWasmStateUpdater('memory:stage20-reference', geometry.cellCount, { fetchImpl });
const clippedCells = updater.advance(state, residual, geometry.areas, state.manning, residual.dt);
const diagnostics = summariseState(state, 3);
requireValue(manifest.binary.sha256 === '717a076b901c29763b3b565250e68e15ad72fe2b87306ebd41f35b9dd37f4347', 'browser mesh digest changed');
requireValue(geometry.cellCount === 50339, 'cell count changed');
requireValue(manifest.counts.barrageFaces === 79, 'barrage-face count changed');
requireValue(clippedCells === 0, 'WASM update clipped a cell');
requireValue(diagnostics.nonFinite === 0, 'non-finite state');
requireValue(diagnostics.maxDepthDrift <= 1e-10, 'still-water depth drift');
requireValue(diagnostics.maxVelocity <= 1e-10, 'still-water velocity drift');
console.log(JSON.stringify({
  schema: 'onga-stage20-browser-reference-validation-v1',
  status: 'passed',
  meshSha256: manifest.binary.sha256,
  counts: manifest.counts,
  wasmBytes: updater.wasmBytes,
  dtSeconds: residual.dt,
  clippedCells,
  ...diagnostics,
  elapsedMs: performance.now() - started,
  safeguards: { syntheticStillWaterOnly: true, physicalFlowRun: false, publicSimulatorConnected: false },
}, null, 2));
