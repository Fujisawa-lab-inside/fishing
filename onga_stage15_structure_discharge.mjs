export const STAGE15_STRUCTURE_VERSION = 'stage15-structure-discharge-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-structure] ${message}`);
}

function assertFinite(value, label) {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite`);
}

function scalar(specification, time, context, label) {
  const resolved = typeof specification === 'function'
    ? specification(time, context)
    : specification;
  const numeric = Number(resolved);
  assertFinite(numeric, label);
  return numeric;
}

function unitVector(direction, label = 'direction') {
  const x = Number(direction?.x ?? direction?.[0]);
  const y = Number(direction?.y ?? direction?.[1]);
  assertFinite(x, `${label}.x`);
  assertFinite(y, `${label}.y`);
  const magnitude = Math.hypot(x, y);
  assert(magnitude > 0, `${label} must have nonzero length`);
  return Object.freeze({ x: x / magnitude, y: y / magnitude });
}

export function gateOpeningArea({
  width,
  maximumOpening,
  openingFraction,
  time = 0,
  context = {},
}) {
  const gateWidth = scalar(width, time, context, 'width');
  const gateHeight = scalar(maximumOpening, time, context, 'maximumOpening');
  const fraction = scalar(openingFraction, time, context, 'openingFraction');
  assert(gateWidth >= 0, 'width must be nonnegative');
  assert(gateHeight >= 0, 'maximumOpening must be nonnegative');
  assert(fraction >= 0 && fraction <= 1, 'openingFraction must be in [0，1]');
  return gateWidth * gateHeight * fraction;
}

export function headOrificeDischarge({
  headA,
  headB,
  dischargeCoefficient,
  area,
  gravity = 9.80665,
  time = 0,
  context = {},
}) {
  const a = scalar(headA, time, context, 'headA');
  const b = scalar(headB, time, context, 'headB');
  const coefficient = scalar(dischargeCoefficient, time, context, 'dischargeCoefficient');
  const effectiveArea = scalar(area, time, context, 'area');
  const g = scalar(gravity, time, context, 'gravity');
  assert(coefficient >= 0, 'dischargeCoefficient must be nonnegative');
  assert(effectiveArea >= 0, 'area must be nonnegative');
  assert(g > 0, 'gravity must be positive');
  const headDifference = a - b;
  const speed = Math.sqrt(2 * g * Math.abs(headDifference));
  const discharge = headDifference === 0
    ? 0
    : Math.sign(headDifference) * coefficient * effectiveArea * speed;
  return Object.freeze({
    version: STAGE15_STRUCTURE_VERSION,
    mode: 'head_orifice',
    discharge,
    headA: a,
    headB: b,
    headDifference,
    dischargeCoefficient: coefficient,
    area: effectiveArea,
    gravity: g,
    speed,
  });
}

export function gateOrificeDischarge(options) {
  const area = gateOpeningArea(options);
  const result = headOrificeDischarge({ ...options, area });
  return Object.freeze({
    ...result,
    mode: 'gate_orifice',
    openingArea: area,
  });
}

export function evaluateStructureDischarge({
  mode,
  time = 0,
  context = {},
  ...parameters
}) {
  const selected = String(mode || 'disabled');
  if (selected === 'disabled') {
    return Object.freeze({
      version: STAGE15_STRUCTURE_VERSION,
      mode: selected,
      discharge: 0,
      speed: 0,
    });
  }
  if (selected === 'fixed_discharge') {
    return Object.freeze({
      version: STAGE15_STRUCTURE_VERSION,
      mode: selected,
      discharge: scalar(parameters.discharge, time, context, 'discharge'),
      speed: parameters.transportSpeed === undefined
        ? 0
        : Math.abs(scalar(parameters.transportSpeed, time, context, 'transportSpeed')),
    });
  }
  if (selected === 'head_orifice') {
    return headOrificeDischarge({ ...parameters, time, context });
  }
  if (selected === 'gate_orifice') {
    return gateOrificeDischarge({ ...parameters, time, context });
  }
  throw new TypeError(`unsupported structure mode: ${selected}`);
}

export function conservativeStructureTransfer({
  cellCount,
  cellA,
  cellB,
  discharge,
  direction = [1, 0],
  transportSpeed = 0,
  momentumMode = 'directional',
}) {
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount must be a positive integer');
  const a = Number(cellA);
  const b = Number(cellB);
  assert(Number.isInteger(a) && a >= 0 && a < cellCount, 'cellA is invalid');
  assert(Number.isInteger(b) && b >= 0 && b < cellCount && b !== a, 'cellB is invalid');
  const q = Number(discharge);
  const speed = Number(transportSpeed);
  assertFinite(q, 'discharge');
  assertFinite(speed, 'transportSpeed');
  assert(speed >= 0, 'transportSpeed must be nonnegative');
  const selectedMomentumMode = String(momentumMode);
  assert(selectedMomentumMode === 'directional' || selectedMomentumMode === 'none',
    'momentumMode must be directional or none');
  const unit = unitVector(direction);
  const sign = q === 0 ? 0 : Math.sign(q);
  const velocityX = selectedMomentumMode === 'directional' ? sign * speed * unit.x : 0;
  const velocityY = selectedMomentumMode === 'directional' ? sign * speed * unit.y : 0;
  const momentumFluxX = q * velocityX;
  const momentumFluxY = q * velocityY;
  const sources = {
    mass: new Float64Array(cellCount),
    momentumX: new Float64Array(cellCount),
    momentumY: new Float64Array(cellCount),
  };
  sources.mass[a] -= q;
  sources.mass[b] += q;
  sources.momentumX[a] -= momentumFluxX;
  sources.momentumX[b] += momentumFluxX;
  sources.momentumY[a] -= momentumFluxY;
  sources.momentumY[b] += momentumFluxY;
  return Object.freeze({
    version: STAGE15_STRUCTURE_VERSION,
    cellA: a,
    cellB: b,
    discharge: q,
    direction: unit,
    transportSpeed: speed,
    momentumMode: selectedMomentumMode,
    transportVelocity: Object.freeze({ x: velocityX, y: velocityY }),
    momentumFlux: Object.freeze({ x: momentumFluxX, y: momentumFluxY }),
    sources: Object.freeze(sources),
  });
}

export function accumulateStructureTransfers({ cellCount, transfers }) {
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount must be a positive integer');
  assert(Array.isArray(transfers), 'transfers must be an array');
  const total = {
    mass: new Float64Array(cellCount),
    momentumX: new Float64Array(cellCount),
    momentumY: new Float64Array(cellCount),
  };
  const evaluated = transfers.map((definition, index) => {
    const transfer = conservativeStructureTransfer({ cellCount, ...definition });
    for (let cell = 0; cell < cellCount; cell += 1) {
      total.mass[cell] += transfer.sources.mass[cell];
      total.momentumX[cell] += transfer.sources.momentumX[cell];
      total.momentumY[cell] += transfer.sources.momentumY[cell];
    }
    return Object.freeze({ id: definition.id ?? `structure-${index}`, ...transfer });
  });
  return Object.freeze({
    version: STAGE15_STRUCTURE_VERSION,
    transfers: Object.freeze(evaluated),
    sources: Object.freeze(total),
  });
}
