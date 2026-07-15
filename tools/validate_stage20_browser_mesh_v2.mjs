import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
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

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

const manifestPath = process.argv[2] || 'public/data/onga/stage20/mesh-v2.json';
const outputPath = process.argv[3] || 'config/stage20_browser_mesh_v2_validation_v1.json';
const manifestBytes = await readFile(manifestPath);
const manifest = JSON.parse(manifestBytes);
const binaryPath = new URL(manifest.binary.url, new URL(`file://${process.cwd()}/${manifestPath}`));
const binary = await readFile(binaryPath);
const arrayBuffer = binary.buffer.slice(binary.byteOffset, binary.byteOffset + binary.byteLength);
const mesh = decodeStage20BrowserMesh(manifest, arrayBuffer);

requireValue(manifest.schema === 'onga-stage20-browser-mesh-v2', 'browser mesh schema mismatch');
requireValue(manifest.binary.sha256 === sha256(binary), 'browser binary digest mismatch');
requireValue(manifest.source.linuxPackageSha256 === '284f4ff7666ecfa5bf7c605e3a133f7abd92d9f3fa2538235c8ed3c2616373f7', 'Linux package mismatch');
requireValue(manifest.source.workflowRunId === 29392549671, 'Linux workflow run mismatch');
requireValue(manifest.counts.vertices === 28450, 'vertex count mismatch');
requireValue(manifest.counts.cells === 50199, 'cell count mismatch');
requireValue(manifest.counts.internalFaces === 71949, 'internal-face count mismatch');
requireValue(manifest.counts.boundaryFaces === 6699, 'boundary-face count mismatch');
requireValue(manifest.counts.barrageFaces === 68, 'barrage-face count mismatch');

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
requireValue(clippedCells === 0, 'WASM update clipped a cell');
requireValue(diagnostics.nonFinite === 0, 'non-finite state');
requireValue(diagnostics.maxDepthDrift <= 1e-10, 'still-water depth drift');
requireValue(diagnostics.maxVelocity <= 1e-10, 'still-water velocity drift');

const report = {
  schema: 'onga-stage20-browser-mesh-v2-validation-v1',
  status: 'passed_not_connected',
  approvedMesh: {
    linuxPackageSha256: manifest.source.linuxPackageSha256,
    browserBinarySha256: manifest.binary.sha256,
    manifestSha256: sha256(manifestBytes),
    ...manifest.counts,
  },
  browserPath: {
    schema: manifest.schema,
    manifest: manifestPath,
    wasmSha256: sha256(wasm),
    wasmBytes: updater.wasmBytes,
  },
  syntheticStillWaterValidation: {
    depthM: 3,
    manningN: 0.03,
    cfl: 0.12,
    adaptiveStepSeconds: residual.dt,
    clippedCells,
    nonFiniteValues: diagnostics.nonFinite,
    maximumVelocityMPerS: diagnostics.maxVelocity,
    maximumDepthDriftM: diagnostics.maxDepthDrift,
    localNodeElapsedMs: performance.now() - started,
  },
  safeguards: {
    syntheticStillWaterOnly: true,
    physicalFlowRun: false,
    publicSimulatorConnected: false,
    published: false,
    mainMerged: false,
  },
  nextDecision: 'connect_browser_reference_to_mesh_v2_or_revise',
};
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
