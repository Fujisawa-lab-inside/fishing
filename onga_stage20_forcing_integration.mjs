export const STAGE20_FORCING_REQUEST_SCHEMA =
  'onga-stage20-parallel-forcing-build-request-v1';
export const STAGE20_FORCING_RESULT_SCHEMA =
  'onga-stage20-parallel-forcing-result-v1';
export const STAGE20_FORCING_CAPABILITY_SCHEMA =
  'onga-stage20-parallel-forcing-capabilities-v1';
const CSRF_HEADER_NAME = 'X-Stage20-CSRF-Token';

let forcingCsrfToken = null;

const HOURS = Object.freeze(Array.from({ length: 37 }, (_, index) => index - 12));
const GATE_OPENING_ORDER = Object.freeze([5, 4, 6, 3, 7, 2, 8, 1]);

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-forcing-integration] ${message}`);
}

function exactHours(values) {
  return Array.isArray(values)
    && values.length === HOURS.length
    && values.every((value, index) => value === HOURS[index]);
}

function finiteSeries(values, label, { nonnegative = false } = {}) {
  assert(Array.isArray(values) && values.length === HOURS.length, `${label} must contain 37 values`);
  for (const value of values) {
    assert(Number.isFinite(value), `${label} contains a non-finite value`);
    if (nonnegative) assert(value >= 0, `${label} contains a negative value`);
  }
  return Object.freeze([...values]);
}

function validateGatePatterns(operation) {
  assert(
    Array.isArray(operation?.openingOrder)
      && operation.openingOrder.join(',') === GATE_OPENING_ORDER.join(','),
    'gate opening order changed',
  );
  assert(
    Array.isArray(operation?.stages) && operation.stages.length === HOURS.length,
    'automatic gate stages must contain 37 values',
  );
  assert(
    Array.isArray(operation?.capacityFractionByGateId)
      && operation.capacityFractionByGateId.length === HOURS.length,
    'automatic gate patterns must contain 37 values',
  );
  for (let index = 0; index < HOURS.length; index += 1) {
    const stage = operation.stages[index];
    const pattern = operation.capacityFractionByGateId[index];
    assert(Number.isInteger(stage) && stage >= 0 && stage <= 8, 'gate stage is outside 0..8');
    assert(
      Array.isArray(pattern)
        && pattern.length === 8
        && pattern.every(value => value === 0 || value === 1),
      'gate capacity pattern is not binary',
    );
    const expectedOpen = new Set(GATE_OPENING_ORDER.slice(0, stage));
    for (let gateId = 1; gateId <= 8; gateId += 1) {
      assert(
        pattern[gateId - 1] === (expectedOpen.has(gateId) ? 1 : 0),
        'gate pattern does not follow the fixed opening order',
      );
    }
  }
}

export function validateStage20IntegratedForcing(payload) {
  assert(payload?.schema === STAGE20_FORCING_RESULT_SCHEMA, 'forcing result schema changed');
  assert(
    payload?.status === 'reference_forcing_ready'
      || payload?.status === 'reference_forcing_with_nonrepresentative_tide_fallback',
    'forcing result is not usable',
  );
  assert(payload?.displayLabel === '未較正・モデル参考値', 'uncalibrated label is missing');
  assert(exactHours(payload?.hours), 'forcing hour grid changed');
  assert(
    Array.isArray(payload?.timestampsJst) && payload.timestampsJst.length === HOURS.length,
    'forcing timestamps must contain 37 values',
  );
  const series = Object.freeze({
    tideRelativeM: finiteSeries(payload?.series?.tideRelativeM, 'tideRelativeM'),
    ongaDischargeM3S: finiteSeries(
      payload?.series?.ongaDischargeM3S,
      'ongaDischargeM3S',
      { nonnegative: true },
    ),
    nishiDischargeM3S: finiteSeries(
      payload?.series?.nishiDischargeM3S,
      'nishiDischargeM3S',
      { nonnegative: true },
    ),
    magariDischargeM3S: finiteSeries(
      payload?.series?.magariDischargeM3S,
      'magariDischargeM3S',
      { nonnegative: true },
    ),
    barrageOpeningFraction: finiteSeries(
      payload?.series?.barrageOpeningFraction,
      'barrageOpeningFraction',
      { nonnegative: true },
    ),
  });
  validateGatePatterns(payload.automaticGateOperation);
  const connection = payload?.connection;
  assert(
    connection?.guiDisplayConnected === true
      && connection?.automaticGateSelectionConnected === true
      && connection?.localR1CGateOnlyRunConnected === true
      && connection?.riverAndTideBoundaryPhysicsConnected === false
      && connection?.productionPrecomputationConnected === false,
    'forcing connection boundary changed',
  );
  assert(
    payload?.runtimePolicy?.offlineOnly === true
      && payload?.runtimePolicy?.networkFetchAttempted === false
      && payload?.runtimePolicy?.tideSourcePolicy
        === 'preserved_local_snapshot_or_fail_closed',
    'forcing offline runtime policy changed',
  );
  return Object.freeze({
    ...payload,
    hours: HOURS,
    series,
    automaticGateOperation: Object.freeze({
      ...payload.automaticGateOperation,
      openingOrder: GATE_OPENING_ORDER,
      stages: Object.freeze([...payload.automaticGateOperation.stages]),
      capacityFractionByGateId: Object.freeze(
        payload.automaticGateOperation.capacityFractionByGateId.map(
          pattern => Object.freeze([...pattern]),
        ),
      ),
    }),
  });
}

async function responseJson(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`HTTP ${response.status} returned invalid JSON`);
  }
  if (!response.ok) {
    throw new Error(payload?.message || payload?.error?.message || `HTTP ${response.status}`);
  }
  return payload;
}

function validOfflineDateCapability(payload) {
  const years = payload?.availableTideSnapshotYears;
  const ranges = payload?.availableRequestedDateRanges;
  const defaultDate = payload?.defaultRequestedDate;
  if (!Array.isArray(years) || years.length === 0
      || !years.every((year, index) => Number.isInteger(year)
        && year >= 2001 && year <= 2098
        && (index === 0 || year > years[index - 1]))) return false;
  if (!Array.isArray(ranges) || ranges.length === 0) return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(defaultDate || '')) return false;
  let defaultCovered = false;
  for (const [index, range] of ranges.entries()) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(range?.start || '')
        || !/^\d{4}-\d{2}-\d{2}$/.test(range?.end || '')
        || range.start > range.end
        || (index > 0 && ranges[index - 1].end >= range.start)) return false;
    if (range.start <= defaultDate && defaultDate <= range.end) defaultCovered = true;
  }
  return defaultCovered;
}

export async function probeStage20ForcingIntegration({ signal, fetchImpl = fetch } = {}) {
  forcingCsrfToken = null;
  const response = await fetchImpl('/api/stage20/forcing/capabilities', {
    cache: 'no-store',
    credentials: 'same-origin',
    mode: 'same-origin',
    redirect: 'error',
    signal,
  });
  const payload = await responseJson(response);
  assert(
    payload?.schema === STAGE20_FORCING_CAPABILITY_SCHEMA
      && payload?.status === 'READY_OFFLINE'
      && payload?.localOnly === true
      && payload?.offlineOnly === true
      && payload?.networkFetchAllowed === false
      && validOfflineDateCapability(payload)
      && payload?.pointCount === 37
      && payload?.connection?.guiDisplay === true
      && payload?.connection?.automaticGateSelection === true
      && payload?.connection?.localR1CGateOnlyRun === true
      && payload?.connection?.riverAndTideBoundaryPhysics === false,
    'forcing capability response changed',
  );
  assert(
    payload?.csrfHeaderName === CSRF_HEADER_NAME
      && typeof payload?.csrfToken === 'string'
      && /^[A-Za-z0-9_-]{32,}$/.test(payload.csrfToken)
      && payload?.requestSecurity?.loopbackHostRequired === true
      && payload?.requestSecurity?.sameOriginRequired === true
      && payload?.requestSecurity?.applicationJsonRequired === true
      && payload?.requestSecurity?.perProcessCsrfToken === true,
    'forcing request security changed',
  );
  forcingCsrfToken = payload.csrfToken;
  return Object.freeze(payload);
}

function bytesToBase64(bytes) {
  let binary = '';
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

export async function buildStage20IntegratedForcing(
  { requestedDate, csvFile, tideFailurePolicy = 'fail_closed' },
  { signal, fetchImpl = fetch } = {},
) {
  assert(forcingCsrfToken !== null, 'forcing security handshake is required');
  assert(/^\d{4}-\d{2}-\d{2}$/.test(requestedDate || ''), '日付を選択してください');
  assert(csvFile instanceof Blob, '気象庁CSVを選択してください');
  const bytes = new Uint8Array(await csvFile.arrayBuffer());
  assert(bytes.byteLength > 0 && bytes.byteLength <= 4 * 1024 * 1024, 'CSVサイズは4MB以下にしてください');
  const response = await fetchImpl('/api/stage20/forcing/build', {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    mode: 'same-origin',
    redirect: 'error',
    signal,
    headers: {
      'Content-Type': 'application/json',
      [CSRF_HEADER_NAME]: forcingCsrfToken,
    },
    body: JSON.stringify({
      schema: STAGE20_FORCING_REQUEST_SCHEMA,
      requestedDate,
      jmaCsvBase64: bytesToBase64(bytes),
      tideFailurePolicy,
    }),
  });
  return validateStage20IntegratedForcing(await responseJson(response));
}
