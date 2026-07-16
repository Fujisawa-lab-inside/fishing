import { loadStage20BrowserMesh } from './onga_stage20_browser_mesh.mjs';

export const STAGE20_GUI_DATA_SCHEMA = 'onga-stage20-gui-data-v1';

const EXPECTED_MESH_SHA256 = '09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659';
const EXPECTED_RESPONSE_PACK_SHA256 = '2d92e67d2ececf8e3c9e540003cd5546e3f6a38b234de7b5122aa4448c3478a3';
const EXPECTED_OUTPUT_SHA256 = '146429c21fecc13359710bb5335885258b63cd1f5750b6816f01098659135417';

const DEFAULT_URLS = Object.freeze({
  meshManifest: './public/data/onga/stage20/mesh-v2.json',
  responseManifest: './public/data/onga/stage20/response-pack-synthetic-v2.json',
  hourlyInputs: './public/data/onga/stage20/hybrid-synthetic-input-v1.json',
  waterManifest: './data/onga_unified_water_manifest_r3.json',
  worker: './onga_stage20_hybrid_worker.mjs',
});

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-gui-data] ${message}`);
}

async function fetchJson(url, signal) {
  const response = await fetch(url, { cache: 'no-store', signal });
  assert(response.ok, `${url} returned HTTP ${response.status}`);
  return response.json();
}

function resolveUrl(value) {
  return new URL(value, import.meta.url).href;
}

function runSynthesisWorker({ workerUrl, responseManifestUrl, inputs, signal }) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(workerUrl, { type: 'module' });
    let settled = false;
    let timeoutId = null;

    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      if (timeoutId !== null) globalThis.clearTimeout(timeoutId);
      signal?.removeEventListener('abort', onAbort);
      worker.terminate();
      callback(value);
    };
    const onAbort = () => finish(reject, new DOMException('GUI data loading was cancelled', 'AbortError'));

    worker.addEventListener('message', event => {
      const result = event.data;
      if (result?.type !== 'hybrid-synthesis-result') {
        finish(reject, new Error('hybrid synthesis worker returned an unexpected message'));
        return;
      }
      if (result.status !== 'passed') {
        finish(reject, new Error(result.error || 'hybrid synthesis failed'));
        return;
      }
      finish(resolve, result);
    });
    worker.addEventListener('error', event => {
      finish(reject, new Error(event.message || 'hybrid synthesis worker failed'));
    });
    worker.addEventListener('messageerror', () => {
      finish(reject, new Error('hybrid synthesis worker returned unreadable data'));
    });
    signal?.addEventListener('abort', onAbort, { once: true });
    if (signal?.aborted) {
      onAbort();
      return;
    }
    timeoutId = globalThis.setTimeout(() => {
      finish(reject, new Error('hybrid synthesis worker timed out'));
    }, 30_000);
    try {
      worker.postMessage({
        type: 'run-hybrid-synthesis',
        responseManifestUrl,
        inputs,
        includeOutput: true,
      });
    } catch (error) {
      finish(reject, error);
    }
  });
}

export async function loadStage20GuiData(options = {}) {
  assert(options.urls === undefined, 'GUI prototype data URLs are fixed');
  const urls = DEFAULT_URLS;
  const signal = options.signal;
  const meshUrl = resolveUrl(urls.meshManifest);
  const responseManifestUrl = resolveUrl(urls.responseManifest);
  const inputsUrl = resolveUrl(urls.hourlyInputs);
  const waterManifestUrl = resolveUrl(urls.waterManifest);
  const workerUrl = resolveUrl(urls.worker);

  options.onProgress?.('mesh-and-contracts');
  const [mesh, responseManifest, inputs, waterManifest] = await Promise.all([
    loadStage20BrowserMesh(meshUrl, { fetchImpl: (url, init = {}) => fetch(url, { ...init, signal }) }),
    fetchJson(responseManifestUrl, signal),
    fetchJson(inputsUrl, signal),
    fetchJson(waterManifestUrl, signal),
  ]);

  assert(mesh.manifest.schema === 'onga-stage20-browser-mesh-v2', 'mesh-v2 is required');
  assert(mesh.manifest.counts.cells === 50199, 'mesh-v2 cell count changed');
  assert(mesh.manifest.binary.sha256 === EXPECTED_MESH_SHA256, 'approved mesh-v2 identity changed');
  assert(responseManifest.schema === 'onga-stage20-response-pack-v1', 'response manifest schema mismatch');
  assert(responseManifest.status === 'synthetic_browser_benchmark_only', 'GUI prototype accepts the synthetic fixture only');
  assert(responseManifest.version === 'stage20-synthetic-response-pack-v2-mesh-v2', 'response-pack v2 is required');
  assert(responseManifest.binary.sha256 === EXPECTED_RESPONSE_PACK_SHA256, 'synthetic response-pack identity changed');
  assert(responseManifest.mesh.sha256 === mesh.manifest.binary.sha256, 'response pack and mesh identities differ');
  assert(responseManifest.mesh.cellCount === mesh.manifest.counts.cells, 'response pack cell count differs from mesh');
  assert(responseManifest.componentOrder.join(',') === 'depthM,eastVelocityMPS,northVelocityMPS', 'component order changed');
  assert(inputs.schema === 'onga-stage20-hybrid-hourly-input-v1', 'hourly input schema mismatch');
  assert(inputs.status === 'synthetic_browser_benchmark_only', 'hourly inputs are not the synthetic fixture');
  assert(Array.isArray(inputs.hours) && inputs.hours.length === 37, '37 hourly inputs are required');
  assert(inputs.hours[0] === -12 && inputs.hours.at(-1) === 24, 'hour range must be -12 through +24');
  assert(inputs.hours.every((hour, index) => hour === index - 12), 'hourly inputs must use one-hour intervals');
  for (const key of ['tideRelativeM', 'barrageOpeningFraction', 'ongaDischargeM3S']) {
    assert(Array.isArray(inputs[key]) && inputs[key].length === inputs.hours.length, `${key} length mismatch`);
    assert(inputs[key].every(Number.isFinite), `${key} contains a non-finite value`);
  }
  assert(waterManifest?.coordinateSystem?.geographic, 'geographic display transform is missing');

  options.onProgress?.('synthesis');
  const workerResult = await runSynthesisWorker({
    workerUrl,
    responseManifestUrl,
    inputs,
    signal,
  });
  assert(workerResult.responsePackStatus === responseManifest.status, 'worker response-pack status mismatch');
  assert(workerResult.responsePackVersion === responseManifest.version, 'worker response-pack version mismatch');
  assert(workerResult.responsePackSha256 === responseManifest.binary.sha256, 'worker response-pack digest mismatch');
  assert(workerResult.meshSha256 === mesh.manifest.binary.sha256, 'worker mesh digest mismatch');
  assert(workerResult.snapshotCount === inputs.hours.length, 'worker snapshot count mismatch');
  assert(workerResult.hourRange?.[0] === -12 && workerResult.hourRange?.[1] === 24, 'worker hour range mismatch');
  assert(workerResult.intervalHours === 1, 'worker hour interval mismatch');
  assert(workerResult.cellCount === mesh.manifest.counts.cells, 'worker cell count mismatch');
  assert(workerResult.fields instanceof Float32Array, 'worker did not transfer Float32 fields');

  const componentCount = responseManifest.componentOrder.length;
  const expectedLength = inputs.hours.length * componentCount * mesh.manifest.counts.cells;
  assert(workerResult.fields.length === expectedLength, 'worker field length mismatch');
  assert(workerResult.outputBytes === expectedLength * Float32Array.BYTES_PER_ELEMENT, 'worker output byte length mismatch');
  assert(workerResult.outputSha256 === EXPECTED_OUTPUT_SHA256, 'synthetic output identity changed');
  assert(workerResult.diagnostics?.nonFiniteValueCount === 0, 'worker output contains a non-finite value');
  for (const key of ['minimumDepthM', 'maximumDepthM', 'maximumSpeedMPS']) {
    assert(Number.isFinite(workerResult.diagnostics?.[key]), `worker diagnostic ${key} is invalid`);
  }

  const cellCount = mesh.manifest.counts.cells;
  const snapshotStride = componentCount * cellCount;
  const fields = workerResult.fields;
  const displayInputs = Object.freeze(Object.fromEntries(
    ['hours', 'tideRelativeM', 'barrageOpeningFraction', 'ongaDischargeM3S'].map(key => [key, Object.freeze([...inputs[key]])]),
  ));
  const snapshot = index => {
    assert(Number.isInteger(index) && index >= 0 && index < inputs.hours.length, 'snapshot index is invalid');
    const start = index * snapshotStride;
    return Object.freeze({
      index,
      hour: inputs.hours[index],
      depthM: fields.subarray(start, start + cellCount),
      eastVelocityMPS: fields.subarray(start + cellCount, start + 2 * cellCount),
      northVelocityMPS: fields.subarray(start + 2 * cellCount, start + 3 * cellCount),
    });
  };

  return Object.freeze({
    schema: STAGE20_GUI_DATA_SCHEMA,
    metadata: Object.freeze({
      sourceStatus: responseManifest.status,
      sourceLabel: '合成データ',
      interpretation: '表示・操作確認用。観測値、物理予測、釣行判断ではありません。',
      hours: Object.freeze([...inputs.hours]),
      componentOrder: Object.freeze([...responseManifest.componentOrder]),
      cellCount,
      snapshotCount: inputs.hours.length,
      meshSha256: mesh.manifest.binary.sha256,
      responsePackSha256: responseManifest.binary.sha256,
      responsePackVersion: responseManifest.version,
    }),
    mesh,
    responseManifest: Object.freeze(responseManifest),
    inputs: displayInputs,
    waterManifest: Object.freeze(waterManifest),
    diagnostics: Object.freeze(workerResult.diagnostics),
    timingsMs: Object.freeze(workerResult.timingsMs),
    snapshot,
  });
}
