export const STAGE15_STRUCTURE_FLUX_VERSION = 'stage15-structure-flux-laws-v1';

const DEFAULT_GRAVITY = 9.80665;

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-structure] ${message}`);
}

function finite(value, label) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite`);
  return numeric;
}

function nonnegative(value, label) {
  const numeric = finite(value, label);
  if (numeric < 0) throw new RangeError(`${label} must be nonnegative`);
  return numeric;
}

function unitInterval(value, label) {
  const numeric = finite(value, label);
  if (numeric < 0 || numeric > 1) throw new RangeError(`${label} must be in [0, 1]`);
  return numeric;
}

function signedRootHead(headDifference, gravity) {
  if (headDifference === 0) return 0;
  return Math.sign(headDifference) * Math.sqrt(2 * gravity * Math.abs(headDifference));
}

export function orificeDischarge({
  leftWaterLevel,
  rightWaterLevel,
  effectiveArea,
  dischargeCoefficient,
  openingFraction = 1,
  gravity = DEFAULT_GRAVITY,
}) {
  const left = finite(leftWaterLevel, 'leftWaterLevel');
  const right = finite(rightWaterLevel, 'rightWaterLevel');
  const area = nonnegative(effectiveArea, 'effectiveArea');
  const coefficient = nonnegative(dischargeCoefficient, 'dischargeCoefficient');
  const opening = unitInterval(openingFraction, 'openingFraction');
  const g = nonnegative(gravity, 'gravity');
  assert(g > 0, 'gravity must be positive');
  const headDifference = left - right;
  const discharge = coefficient * area * opening * signedRootHead(headDifference, g);
  return Object.freeze({
    model: 'orifice',
    headDifference,
    openingFraction: opening,
    signedDischargeLeftToRight: discharge,
  });
}

export function linearHeadLossDischarge({
  leftWaterLevel,
  rightWaterLevel,
  conductance,
  openingFraction = 1,
}) {
  const left = finite(leftWaterLevel, 'leftWaterLevel');
  const right = finite(rightWaterLevel, 'rightWaterLevel');
  const coefficient = nonnegative(conductance, 'conductance');
  const opening = unitInterval(openingFraction, 'openingFraction');
  const headDifference = left - right;
  return Object.freeze({
    model: 'linear_head_loss',
    headDifference,
    openingFraction: opening,
    signedDischargeLeftToRight: coefficient * opening * headDifference,
  });
}

export function fixedDischarge({ discharge }) {
  return Object.freeze({
    model: 'fixed_discharge',
    headDifference: null,
    openingFraction: null,
    signedDischargeLeftToRight: finite(discharge, 'discharge'),
  });
}

export function evaluateStructureInterface(specification) {
  const mode = String(specification?.mode ?? 'closed');
  if (mode === 'closed') {
    return Object.freeze({
      model: 'closed',
      headDifference: null,
      openingFraction: 0,
      signedDischargeLeftToRight: 0,
    });
  }
  if (mode === 'orifice') return orificeDischarge(specification);
  if (mode === 'linear_head_loss') return linearHeadLossDischarge(specification);
  if (mode === 'fixed_discharge') return fixedDischarge(specification);
  throw new TypeError(`unsupported structure mode: ${mode}`);
}

export function gateEffectiveArea({ gateWidth, maximumOpeningHeight, openingFraction }) {
  const width = nonnegative(gateWidth, 'gateWidth');
  const height = nonnegative(maximumOpeningHeight, 'maximumOpeningHeight');
  const opening = unitInterval(openingFraction, 'openingFraction');
  return width * height * opening;
}

export function evaluateGateSet({
  leftWaterLevel,
  rightWaterLevel,
  gates,
  gravity = DEFAULT_GRAVITY,
}) {
  assert(Array.isArray(gates) && gates.length > 0, 'gates must be a nonempty array');
  const results = gates.map((gate, index) => {
    const mode = String(gate.mode ?? 'orifice');
    let result;
    if (mode === 'closed') {
      result = evaluateStructureInterface({ mode: 'closed' });
    } else if (mode === 'orifice') {
      const openingFraction = unitInterval(gate.openingFraction ?? 0, `gates[${index}].openingFraction`);
      const fullArea = nonnegative(gate.fullOpenArea, `gates[${index}].fullOpenArea`);
      result = orificeDischarge({
        leftWaterLevel,
        rightWaterLevel,
        effectiveArea: fullArea,
        dischargeCoefficient: gate.dischargeCoefficient,
        openingFraction,
        gravity,
      });
    } else if (mode === 'linear_head_loss') {
      result = linearHeadLossDischarge({
        leftWaterLevel,
        rightWaterLevel,
        conductance: gate.conductance,
        openingFraction: gate.openingFraction ?? 0,
      });
    } else {
      throw new TypeError(`gates[${index}] has unsupported mode: ${mode}`);
    }
    return Object.freeze({
      id: gate.id ?? `gate-${index + 1}`,
      ...result,
    });
  });
  const totalSignedDischargeLeftToRight = results.reduce(
    (sum, result) => sum + result.signedDischargeLeftToRight,
    0,
  );
  return Object.freeze({
    gates: Object.freeze(results),
    totalSignedDischargeLeftToRight,
  });
}

export function conservativeInterfaceSources({
  cellCount,
  leftCell,
  rightCell,
  signedDischargeLeftToRight,
}) {
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount must be a positive integer');
  assert(Number.isInteger(leftCell) && leftCell >= 0 && leftCell < cellCount, 'leftCell is invalid');
  assert(Number.isInteger(rightCell) && rightCell >= 0 && rightCell < cellCount, 'rightCell is invalid');
  assert(leftCell !== rightCell, 'interface cells must be distinct');
  const discharge = finite(signedDischargeLeftToRight, 'signedDischargeLeftToRight');
  const sources = new Float64Array(cellCount);
  sources[leftCell] -= discharge;
  sources[rightCell] += discharge;
  return sources;
}

export function limitDischargeByAvailableVolume({
  signedDischargeLeftToRight,
  leftAvailableVolume,
  rightAvailableVolume,
  dt,
}) {
  const discharge = finite(signedDischargeLeftToRight, 'signedDischargeLeftToRight');
  const leftVolume = nonnegative(leftAvailableVolume, 'leftAvailableVolume');
  const rightVolume = nonnegative(rightAvailableVolume, 'rightAvailableVolume');
  const step = finite(dt, 'dt');
  assert(step > 0, 'dt must be positive');
  if (discharge > 0) return Math.min(discharge, leftVolume / step);
  if (discharge < 0) return -Math.min(-discharge, rightVolume / step);
  return 0;
}

export function evaluateConservativeStructureTransfer({
  cellCount,
  leftCell,
  rightCell,
  specification,
  leftAvailableVolume = Infinity,
  rightAvailableVolume = Infinity,
  dt = null,
}) {
  const raw = evaluateStructureInterface(specification);
  let limitedDischarge = raw.signedDischargeLeftToRight;
  if (dt !== null) {
    limitedDischarge = limitDischargeByAvailableVolume({
      signedDischargeLeftToRight: limitedDischarge,
      leftAvailableVolume,
      rightAvailableVolume,
      dt,
    });
  }
  const sources = conservativeInterfaceSources({
    cellCount,
    leftCell,
    rightCell,
    signedDischargeLeftToRight: limitedDischarge,
  });
  return Object.freeze({
    raw,
    limitedSignedDischargeLeftToRight: limitedDischarge,
    sources,
  });
}

export const Stage15StructureFluxLaws = Object.freeze({
  version: STAGE15_STRUCTURE_FLUX_VERSION,
  orificeDischarge,
  linearHeadLossDischarge,
  fixedDischarge,
  evaluateStructureInterface,
  gateEffectiveArea,
  evaluateGateSet,
  conservativeInterfaceSources,
  limitDischargeByAvailableVolume,
  evaluateConservativeStructureTransfer,
});
