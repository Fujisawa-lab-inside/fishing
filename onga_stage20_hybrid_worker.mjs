import { loadStage20ResponsePack } from './onga_stage20_response_pack.mjs';
import { synthesiseStage20HourlyFields } from './onga_stage20_hybrid_solver.mjs';

const now = () => performance.now();

function hex(bytes) {
  return Array.from(new Uint8Array(bytes), value => value.toString(16).padStart(2, '0')).join('');
}

self.addEventListener('message', async event => {
  if (event.data?.type !== 'run-hybrid-synthesis') return;
  try {
    const started = now();
    const pack = await loadStage20ResponsePack(event.data.responseManifestUrl);
    const loaded = now();
    const result = synthesiseStage20HourlyFields(pack, event.data.inputs);
    const synthesised = now();
    const digest = hex(await crypto.subtle.digest('SHA-256', result.fields.buffer));
    const digested = now();
    const message = {
      type: 'hybrid-synthesis-result',
      status: 'passed',
      responsePackStatus: pack.manifest.status,
      responsePackSha256: pack.manifest.binary.sha256,
      responsePackBytes: pack.manifest.binary.byteLength,
      meshSha256: pack.manifest.mesh.sha256,
      snapshotCount: result.snapshotCount,
      hourRange: [result.hours[0], result.hours.at(-1)],
      intervalHours: result.hours[1] - result.hours[0],
      cellCount: result.cellCount,
      outputBytes: result.fields.byteLength,
      outputSha256: digest,
      diagnostics: result.diagnostics,
      timingsMs: {
        responsePackFetchAndDigest: loaded - started,
        synthesis: synthesised - loaded,
        outputDigest: digested - synthesised,
        total: digested - started,
      },
      interpretation: 'synthetic_response_pack_browser_synthesis_benchmark_not_a_physical_flow_run',
    };
    if (event.data.includeOutput === true) {
      message.fields = result.fields;
      self.postMessage(message, [result.fields.buffer]);
    } else {
      self.postMessage(message);
    }
  } catch (error) {
    self.postMessage({ type: 'hybrid-synthesis-result', status: 'failed', error: String(error?.stack || error) });
  }
});
