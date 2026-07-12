export const STAGE14_INPUT_ADAPTER_VERSION = 'stage14-physical-input-adapter-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage14-input] ${message}`);
}

function assertFinite(value, label) {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite`);
}

function parseTimestamp(value, label) {
  assert(typeof value === 'string' && /(Z|[+-]\d\d:\d\d)$/.test(value), `${label} must include an ISO-8601 timezone`);
  const time = Date.parse(value);
  assertFinite(time, label);
  return time / 1000;
}

export function normaliseSeries(samples, valueField, options = {}) {
  const minimumSamples = Number(options.minimumSamples ?? 1);
  assert(Array.isArray(samples) && samples.length >= minimumSamples,
    `${options.label || valueField} requires at least ${minimumSamples} samples`);
  const output = samples.map((sample, index) => {
    const time = parseTimestamp(sample.timestamp, `${options.label || valueField}[${index}].timestamp`);
    const value = Number(sample[valueField]);
    assertFinite(value, `${options.label || valueField}[${index}].${valueField}`);
    return Object.freeze({ time, value, timestamp: sample.timestamp });
  });
  for (let index = 1; index < output.length; index += 1) {
    assert(output[index].time > output[index - 1].time, `${options.label || valueField} timestamps must be strictly increasing`);
  }
  return Object.freeze(output);
}

export function createLinearSeries(samples, valueField, options = {}) {
  const series = normaliseSeries(samples, valueField, options);
  const extrapolation = options.extrapolation ?? 'hold';
  assert(extrapolation === 'hold' || extrapolation === 'error', 'unsupported extrapolation policy');
  return Object.freeze({
    series,
    at(timeSeconds) {
      const time = Number(timeSeconds);
      assertFinite(time, 'series time');
      if (time <= series[0].time) {
        assert(extrapolation === 'hold' || time === series[0].time, 'time precedes series range');
        return series[0].value;
      }
      const last = series[series.length - 1];
      if (time >= last.time) {
        assert(extrapolation === 'hold' || time === last.time, 'time exceeds series range');
        return last.value;
      }
      let low = 0;
      let high = series.length - 1;
      while (high - low > 1) {
        const middle = Math.floor((low + high) / 2);
        if (series[middle].time <= time) low = middle;
        else high = middle;
      }
      const left = series[low];
      const right = series[high];
      const fraction = (time - left.time) / (right.time - left.time);
      return left.value + fraction * (right.value - left.value);
    },
  });
}

function normaliseFixedOrSeries(value, field, label, options = {}) {
  if (typeof value === 'number') {
    assertFinite(value, label);
    return Object.freeze({ mode: 'fixed', at: () => value });
  }
  const interpolation = createLinearSeries(value, field, { ...options, label });
  return Object.freeze({ mode: 'series', at: interpolation.at, series: interpolation.series });
}

function normaliseInput(input) {
  assert(input && typeof input === 'object', 'input object is required');
  const waterLevel = createLinearSeries(input.M, 'water_level_m', {
    minimumSamples: 2,
    label: 'M water level',
    extrapolation: 'hold',
  });
  const discharges = {};
  for (const id of ['N', 'O', 'G']) {
    discharges[id] = normaliseFixedOrSeries(input[id], 'discharge_m3_s', `${id} discharge`, {
      minimumSamples: 1,
      extrapolation: 'hold',
    });
  }
  assert(input.fishway?.discharge_m3_s !== null && input.fishway?.discharge_m3_s !== undefined,
    'fishway discharge is required');
  const fishway = Number(input.fishway.discharge_m3_s);
  assertFinite(fishway, 'fishway discharge');
  assert(fishway >= 0, 'fishway discharge must be nonnegative');

  let barrage;
  if (input.barrage?.opening_fraction !== null
    && input.barrage?.opening_fraction !== undefined
    && Number.isFinite(Number(input.barrage.opening_fraction))) {
    const opening = Number(input.barrage.opening_fraction);
    assert(opening >= 0 && opening <= 1, 'uniform barrage opening must be in [0, 1]');
    barrage = Object.freeze({ mode: 'uniform', at: () => Float64Array.from({ length: 8 }, () => opening) });
  } else if (Array.isArray(input.barrage?.gate_opening_fraction)) {
    const openings = Float64Array.from(input.barrage.gate_opening_fraction, (entry, index) => {
      const value = Number(entry);
      assertFinite(value, `gate ${index + 1} opening`);
      assert(value >= 0 && value <= 1, `gate ${index + 1} opening must be in [0, 1]`);
      return value;
    });
    assert(openings.length === 8, 'gate-wise barrage opening requires eight values');
    barrage = Object.freeze({ mode: 'gatewise', at: () => Float64Array.from(openings) });
  } else {
    throw new Error('[stage14-input] barrage opening is required');
  }

  return Object.freeze({ waterLevel, discharges, fishway, barrage });
}

function normaliseFaceList(list, label, cellCount, requireConductance = false) {
  assert(Array.isArray(list) && list.length > 0, `${label} faces are required`);
  return Object.freeze(list.map((face, index) => {
    const cell = Number(face.cell);
    const length = Number(face.length);
    assert(Number.isInteger(cell) && cell >= 0 && cell < cellCount, `${label} face ${index} cell is invalid`);
    assertFinite(length, `${label} face ${index} length`);
    assert(length > 0, `${label} face ${index} length must be positive`);
    let conductance = 0;
    if (requireConductance) {
      conductance = Number(face.conductance);
      assertFinite(conductance, `${label} face ${index} conductance`);
      assert(conductance > 0, `${label} face ${index} conductance must be positive`);
    }
    return Object.freeze({ cell, length, conductance });
  }));
}

function normaliseMapping(mapping) {
  assert(mapping && typeof mapping === 'object', 'mapping object is required');
  const cellCount = Number(mapping.cellCount);
  const edgeCount = Number(mapping.edgeCount);
  assert(Number.isInteger(cellCount) && cellCount > 0, 'mapping cellCount is invalid');
  assert(Number.isInteger(edgeCount) && edgeCount > 0, 'mapping edgeCount is invalid');
  const boundaryFaces = {
    M: normaliseFaceList(mapping.boundaryFaces?.M, 'M', cellCount, true),
    N: normaliseFaceList(mapping.boundaryFaces?.N, 'N', cellCount),
    O: normaliseFaceList(mapping.boundaryFaces?.O, 'O', cellCount),
    G: normaliseFaceList(mapping.boundaryFaces?.G, 'G', cellCount),
  };
  const barrageEdgeIds = Uint32Array.from(mapping.barrageEdgeIds || [], (entry, index) => {
    const edge = Number(entry);
    assert(Number.isInteger(edge) && edge >= 0 && edge < edgeCount, `barrage edge ${index} is invalid`);
    return edge;
  });
  const barrageGateIds = Uint8Array.from(mapping.barrageGateIds || [], (entry, index) => {
    const gate = Number(entry);
    assert(Number.isInteger(gate) && gate >= 1 && gate <= 8, `barrage gate ${index} is invalid`);
    return gate;
  });
  assert(barrageEdgeIds.length > 0 && barrageEdgeIds.length === barrageGateIds.length,
    'barrage edge and gate mappings are inconsistent');
  const upstream = Number(mapping.fishway?.upstreamCell);
  const downstream = Number(mapping.fishway?.downstreamCell);
  assert(Number.isInteger(upstream) && upstream >= 0 && upstream < cellCount, 'fishway upstream cell is invalid');
  assert(Number.isInteger(downstream) && downstream >= 0 && downstream < cellCount, 'fishway downstream cell is invalid');
  assert(upstream !== downstream, 'fishway cells must be distinct');
  return Object.freeze({ cellCount, edgeCount, boundaryFaces, barrageEdgeIds, barrageGateIds, upstream, downstream });
}

function distributeFlux(faces, totalOutwardFlux, id) {
  const totalLength = faces.reduce((sum, face) => sum + face.length, 0);
  return faces.map((face, index) => Object.freeze({
    id: `${id}-${index}`,
    cell: face.cell,
    type: 'flux',
    value: totalOutwardFlux * face.length / totalLength,
  }));
}

export function createStage14RuntimeForcing({ input, mapping }) {
  const values = normaliseInput(input);
  const geometry = normaliseMapping(mapping);

  function boundariesAt(timeSeconds) {
    const time = Number(timeSeconds);
    assertFinite(time, 'forcing time');
    const boundaries = geometry.boundaryFaces.M.map((face, index) => Object.freeze({
      id: `M-${index}`,
      cell: face.cell,
      type: 'dirichlet',
      conductance: face.conductance,
      value: values.waterLevel.at(time),
    }));
    for (const id of ['N', 'O', 'G']) {
      boundaries.push(...distributeFlux(geometry.boundaryFaces[id], values.discharges[id].at(time), id));
    }
    return Object.freeze(boundaries);
  }

  function sourcesAt() {
    const sources = new Float64Array(geometry.cellCount);
    sources[geometry.upstream] -= values.fishway;
    sources[geometry.downstream] += values.fishway;
    return sources;
  }

  function edgeMultipliersAt(timeSeconds) {
    const time = Number(timeSeconds);
    assertFinite(time, 'forcing time');
    const gateOpenings = values.barrage.at(time);
    const multipliers = new Float64Array(geometry.edgeCount);
    multipliers.fill(1);
    for (let index = 0; index < geometry.barrageEdgeIds.length; index += 1) {
      multipliers[geometry.barrageEdgeIds[index]] = gateOpenings[geometry.barrageGateIds[index] - 1];
    }
    return multipliers;
  }

  function summaryAt(timeSeconds) {
    const time = Number(timeSeconds);
    assertFinite(time, 'forcing time');
    const boundaries = boundariesAt(time);
    const flux = Object.fromEntries(['N', 'O', 'G'].map(id => [
      id,
      boundaries
        .filter(boundary => boundary.id.startsWith(`${id}-`))
        .reduce((sum, boundary) => sum + boundary.value, 0),
    ]));
    return Object.freeze({
      time,
      MWaterLevel: values.waterLevel.at(time),
      boundaryOutwardFlux: flux,
      fishwayDischarge: values.fishway,
      barrageGateOpening: Array.from(values.barrage.at(time)),
    });
  }

  return Object.freeze({
    version: STAGE14_INPUT_ADAPTER_VERSION,
    modes: Object.freeze({
      M: 'water_level_time_series',
      N: 'normal_discharge',
      O: 'normal_discharge',
      G: 'normal_discharge',
      fishway: 'fixed_discharge',
      barrage: values.barrage.mode,
    }),
    boundariesAt,
    sourcesAt,
    edgeMultipliersAt,
    summaryAt,
  });
}
