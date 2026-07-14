import { loadStage20BrowserMesh } from './onga_stage20_browser_mesh.mjs';
import {
  buildStage20ReferenceGeometry,
  createUniformState,
  createWasmStateUpdater,
  flatWaterResidual,
  summariseState,
} from './onga_stage20_reference_solver.mjs';

const now = () => performance.now();

self.addEventListener('message', async event => {
  if (event.data?.type !== 'run-still-water-benchmark') return;
  try {
    const started = now();
    const mesh = await loadStage20BrowserMesh(event.data.meshManifestUrl);
    const loaded = now();
    const geometry = buildStage20ReferenceGeometry(mesh);
    const prepared = now();
    const depthM = 3;
    const state = createUniformState(geometry.cellCount, depthM, 0.03);
    const residual = flatWaterResidual(geometry, state, { cfl: 0.12 });
    const residualReady = now();
    const updater = await createWasmStateUpdater(event.data.wasmUrl, geometry.cellCount);
    const wasmReady = now();
    const clippedCells = updater.advance(state, residual, geometry.areas, state.manning, residual.dt);
    const advanced = now();
    const diagnostics = summariseState(state, depthM);
    const passed = clippedCells === 0
      && diagnostics.nonFinite === 0
      && diagnostics.maxDepthDrift <= 1e-10
      && diagnostics.maxVelocity <= 1e-10;
    self.postMessage({
      type: 'still-water-benchmark-result',
      status: passed ? 'passed' : 'failed',
      meshSha256: mesh.manifest.binary.sha256,
      counts: mesh.manifest.counts,
      wasmBytes: updater.wasmBytes,
      dtSeconds: residual.dt,
      clippedCells,
      ...diagnostics,
      timingsMs: {
        meshFetchAndDigest: loaded - started,
        geometryBuild: prepared - loaded,
        residual: residualReady - prepared,
        wasmLoad: wasmReady - residualReady,
        wasmAdvance: advanced - wasmReady,
        total: advanced - started,
      },
      interpretation: 'synthetic_uniform_still_water_reference_test_not_a_physical_flow_run',
    });
  } catch (error) {
    self.postMessage({ type: 'still-water-benchmark-result', status: 'failed', error: String(error?.stack || error) });
  }
});
