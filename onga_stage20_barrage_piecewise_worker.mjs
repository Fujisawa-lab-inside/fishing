import {
  interpolateStage20BarrageFiveHourFields,
  loadStage20BarragePiecewisePack,
} from './onga_stage20_barrage_piecewise_interpolator.mjs';

const now = () => performance.now();

function hex(bytes) {
  return Array.from(
    new Uint8Array(bytes),
    value => value.toString(16).padStart(2, '0'),
  ).join('');
}

self.addEventListener('message', async event => {
  if (event.data?.type !== 'run-barrage-piecewise-candidate') return;
  try {
    const started = now();
    const pack = await loadStage20BarragePiecewisePack(
      event.data.anchorManifestUrl,
    );
    const loaded = now();
    const result = interpolateStage20BarrageFiveHourFields(
      pack,
      event.data.openingFraction,
    );
    const interpolated = now();
    const digest = hex(
      await crypto.subtle.digest('SHA-256', result.fields.buffer),
    );
    const digested = now();
    const message = {
      type: 'barrage-piecewise-candidate-result',
      status: 'passed',
      packStatus: pack.manifest.status,
      packVersion: pack.manifest.version,
      packSha256: pack.manifest.binary.sha256,
      packBytes: pack.manifest.binary.byteLength,
      meshSha256: pack.manifest.mesh.binarySha256,
      openingFraction: result.openingFraction,
      segmentId: result.segmentId,
      exactAnchor: result.exactAnchor,
      weights: {
        lowerAnchorFraction: result.lowerAnchorFraction,
        upperAnchorFraction: result.upperAnchorFraction,
        lowerWeight: result.lowerWeight,
        upperWeight: result.upperWeight,
      },
      snapshotCount: result.snapshotCount,
      hourRange: [result.hours[0], result.hours.at(-1)],
      cellCount: result.cellCount,
      outputBytes: result.fields.byteLength,
      outputSha256: digest,
      diagnostics: result.diagnostics,
      timingsMs: {
        packFetchAndDigest: loaded - started,
        interpolation: interpolated - loaded,
        outputDigest: digested - interpolated,
        total: digested - started,
      },
      interpretation:
        'code_only_piecewise_candidate_not_physical_or_forecast_validation',
      safeguards: {
        solverInvoked: false,
        physicalRunPerformed: false,
        publicSimulatorConnected: false,
      },
    };
    if (event.data.includeOutput === true) {
      message.fields = result.fields;
      self.postMessage(message, [result.fields.buffer]);
    } else {
      self.postMessage(message);
    }
  } catch (error) {
    self.postMessage({
      type: 'barrage-piecewise-candidate-result',
      status: 'failed',
      error: String(error?.stack || error),
    });
  }
});
