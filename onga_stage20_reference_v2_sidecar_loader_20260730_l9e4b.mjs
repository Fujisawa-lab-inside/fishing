import {
  loadStage20ReferenceV2Sidecar as loadL9E4,
  validateStage20ReferenceV2SidecarManifest,
} from './onga_stage20_reference_v2_sidecar_loader_20260730_l9e4.mjs';

export const STAGE20_REFERENCE_V2_SIDECAR_LOADER_SUCCESSOR_SCHEMA =
  'onga-stage20-reference-v2-sidecar-loader-20260730-l9e4b-v1';

function fail(message) {
  throw new Error(`[stage20-reference-v2-sidecar-l9e4b] ${message}`);
}

function normalizeAbsoluteUrl(value, label) {
  if (typeof value !== 'string' || value.length === 0) {
    fail(`${label} is missing or invalid`);
  }
  try {
    return new URL(value).href;
  } catch {
    fail(`${label} is missing or invalid`);
  }
}

function strictFetch(fetchImpl) {
  return async (requestedUrl, options) => {
    const normalizedRequestedUrl = normalizeAbsoluteUrl(
      String(requestedUrl),
      'requested URL',
    );
    const response = await fetchImpl(normalizedRequestedUrl, options);
    if (response === null || typeof response !== 'object') {
      fail('fetch response is missing or invalid');
    }
    if (response.status !== 200) {
      fail(`HTTP status must be exactly 200; received ${String(response.status)}`);
    }
    if (response.redirected !== false) {
      fail('redirected response is forbidden');
    }
    const normalizedResponseUrl = normalizeAbsoluteUrl(
      response.url,
      'response URL',
    );
    if (normalizedResponseUrl !== normalizedRequestedUrl) {
      fail(
        `response URL differs from requested URL: ${normalizedResponseUrl}`,
      );
    }
    return response;
  };
}

export {
  validateStage20ReferenceV2SidecarManifest,
};

export async function loadStage20ReferenceV2Sidecar(options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== 'function') {
    fail('fetch implementation is unavailable');
  }
  const loaded = await loadL9E4({
    ...options,
    fetchImpl: strictFetch(fetchImpl),
  });
  return Object.freeze({
    ...loaded,
    metadata: Object.freeze({
      ...loaded.metadata,
      successorSchema: STAGE20_REFERENCE_V2_SIDECAR_LOADER_SUCCESSOR_SCHEMA,
      exactHttpStatusRequired: 200,
      redirectAllowed: false,
      responseUrlMustMatchRequest: true,
    }),
  });
}
