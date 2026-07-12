export const STAGE16_BENCHMARK_REGISTRY_VERSION = 'stage16-benchmark-registry-v1';

const TRACKS = new Set(['scalar_skeleton', 'shallow_water_candidate']);
const OPERATORS = new Set(['lte', 'gte', 'eq', 'between']);

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-registry] ${message}`);
}

function finite(value, label) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite`);
  return numeric;
}

function nonempty(value, label) {
  const text = String(value ?? '').trim();
  if (!text) throw new TypeError(`${label} must be nonempty`);
  return text;
}

function freezeDeep(value) {
  if (Array.isArray(value)) return Object.freeze(value.map(freezeDeep));
  if (value && typeof value === 'object') {
    return Object.freeze(Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, freezeDeep(entry)]),
    ));
  }
  return value;
}

export const DEFAULT_STAGE16_BENCHMARK_REGISTRY = freezeDeep([
  {
    id: 'mesh_topology_integrity',
    category: 'geometry_verification',
    requiredFor: ['scalar_skeleton', 'shallow_water_candidate'],
    criteria: [
      { metric: 'failedChecks', operator: 'eq', target: 0 },
      { metric: 'connectedComponents', operator: 'eq', target: 1 },
    ],
  },
  {
    id: 'constant_field_preservation',
    category: 'algebraic_verification',
    requiredFor: ['scalar_skeleton', 'shallow_water_candidate'],
    criteria: [
      { metric: 'maxError', operator: 'lte', target: 1e-10 },
      { metric: 'residualInfinityNorm', operator: 'lte', target: 1e-10 },
    ],
  },
  {
    id: 'closed_domain_mass_conservation',
    category: 'algebraic_verification',
    requiredFor: ['scalar_skeleton', 'shallow_water_candidate'],
    criteria: [
      { metric: 'relativeMassError', operator: 'lte', target: 1e-10 },
    ],
  },
  {
    id: 'boundary_reversal_symmetry',
    category: 'boundary_verification',
    requiredFor: ['scalar_skeleton', 'shallow_water_candidate'],
    criteria: [
      { metric: 'fieldSymmetryError', operator: 'lte', target: 1e-10 },
      { metric: 'fluxAntisymmetryError', operator: 'lte', target: 1e-10 },
    ],
  },
  {
    id: 'interface_complete_closure',
    category: 'structure_verification',
    requiredFor: ['scalar_skeleton', 'shallow_water_candidate'],
    criteria: [
      { metric: 'closedInterfaceFlux', operator: 'lte', target: 1e-12 },
    ],
  },
  {
    id: 'lake_at_rest_variable_bed',
    category: 'pde_verification',
    requiredFor: ['shallow_water_candidate'],
    criteria: [
      { metric: 'maximumResidual', operator: 'lte', target: 1e-10 },
      { metric: 'minimumDepth', operator: 'gte', target: -1e-12 },
    ],
  },
  {
    id: 'dry_bed_dam_break',
    category: 'pde_verification',
    requiredFor: ['shallow_water_candidate'],
    criteria: [
      { metric: 'minimumDepth', operator: 'gte', target: -1e-12 },
      { metric: 'relativeMassError', operator: 'lte', target: 1e-6 },
      { metric: 'frontNormalizedError', operator: 'lte', target: 0.05 },
    ],
  },
  {
    id: 'linear_standing_wave',
    category: 'pde_verification',
    requiredFor: ['shallow_water_candidate'],
    criteria: [
      { metric: 'observedOrder', operator: 'gte', target: 1.8 },
      { metric: 'relativeMassError', operator: 'lte', target: 1e-8 },
      { metric: 'amplitudeRelativeError', operator: 'lte', target: 0.05 },
    ],
  },
  {
    id: 'manning_uniform_flow',
    category: 'source_term_verification',
    requiredFor: ['shallow_water_candidate'],
    criteria: [
      { metric: 'normalDepthRelativeError', operator: 'lte', target: 1e-6 },
      { metric: 'directionErrorRadians', operator: 'lte', target: 1e-10 },
    ],
  },
  {
    id: 'structure_head_reversal',
    category: 'structure_verification',
    requiredFor: ['shallow_water_candidate'],
    criteria: [
      { metric: 'antisymmetryError', operator: 'lte', target: 1e-10 },
      { metric: 'conservationError', operator: 'lte', target: 1e-12 },
    ],
  },
]);

function validateCriterion(criterion, benchmarkId, index) {
  assert(criterion && typeof criterion === 'object', `${benchmarkId} criterion ${index} is invalid`);
  const metric = nonempty(criterion.metric, `${benchmarkId} criterion ${index} metric`);
  const operator = nonempty(criterion.operator, `${benchmarkId} criterion ${index} operator`);
  assert(OPERATORS.has(operator), `${benchmarkId} criterion ${index} has unsupported operator ${operator}`);
  if (operator === 'between') {
    assert(Array.isArray(criterion.target) && criterion.target.length === 2,
      `${benchmarkId} criterion ${index} between target must have two values`);
    const low = finite(criterion.target[0], `${benchmarkId} criterion ${index} lower target`);
    const high = finite(criterion.target[1], `${benchmarkId} criterion ${index} upper target`);
    assert(low <= high, `${benchmarkId} criterion ${index} lower target exceeds upper target`);
    return Object.freeze({ metric, operator, target: Object.freeze([low, high]) });
  }
  return Object.freeze({
    metric,
    operator,
    target: finite(criterion.target, `${benchmarkId} criterion ${index} target`),
  });
}

export function validateBenchmarkRegistry(registry = DEFAULT_STAGE16_BENCHMARK_REGISTRY) {
  assert(Array.isArray(registry) && registry.length > 0, 'registry must be a nonempty array');
  const ids = new Set();
  const validated = registry.map((benchmark, index) => {
    assert(benchmark && typeof benchmark === 'object', `benchmark ${index} is invalid`);
    const id = nonempty(benchmark.id, `benchmark ${index} id`);
    assert(!ids.has(id), `duplicate benchmark id ${id}`);
    ids.add(id);
    const category = nonempty(benchmark.category, `${id} category`);
    assert(Array.isArray(benchmark.requiredFor) && benchmark.requiredFor.length > 0,
      `${id} requiredFor is missing`);
    const requiredFor = benchmark.requiredFor.map((track, trackIndex) => {
      const name = nonempty(track, `${id} requiredFor ${trackIndex}`);
      assert(TRACKS.has(name), `${id} references unsupported track ${name}`);
      return name;
    });
    assert(new Set(requiredFor).size === requiredFor.length, `${id} repeats a track`);
    assert(Array.isArray(benchmark.criteria) && benchmark.criteria.length > 0, `${id} criteria are missing`);
    const criteria = benchmark.criteria.map((criterion, criterionIndex) => (
      validateCriterion(criterion, id, criterionIndex)
    ));
    return Object.freeze({ id, category, requiredFor: Object.freeze(requiredFor), criteria: Object.freeze(criteria) });
  });
  return Object.freeze(validated);
}

function evaluateCriterion(criterion, metrics, benchmarkId) {
  assert(Object.hasOwn(metrics, criterion.metric), `${benchmarkId} result lacks metric ${criterion.metric}`);
  const value = finite(metrics[criterion.metric], `${benchmarkId}.${criterion.metric}`);
  let ok;
  if (criterion.operator === 'lte') ok = value <= criterion.target;
  else if (criterion.operator === 'gte') ok = value >= criterion.target;
  else if (criterion.operator === 'eq') ok = value === criterion.target;
  else ok = value >= criterion.target[0] && value <= criterion.target[1];
  return Object.freeze({
    metric: criterion.metric,
    value,
    operator: criterion.operator,
    target: criterion.target,
    ok,
  });
}

function validateResult(result, benchmarkId) {
  assert(result && typeof result === 'object', `${benchmarkId} result is invalid`);
  assert(result.purpose === 'synthetic_verification', `${benchmarkId} result is not synthetic Verification`);
  assert(result.resultsLabel !== 'physical_prediction', `${benchmarkId} synthetic result is labelled physical_prediction`);
  nonempty(result.scenarioHash, `${benchmarkId} scenarioHash`);
  nonempty(result.codeCommit, `${benchmarkId} codeCommit`);
  assert(result.metrics && typeof result.metrics === 'object', `${benchmarkId} metrics are missing`);
  return result;
}

export function evaluateBenchmarkRegistry({
  registry = DEFAULT_STAGE16_BENCHMARK_REGISTRY,
  results,
  track,
}) {
  const validatedRegistry = validateBenchmarkRegistry(registry);
  const selectedTrack = nonempty(track, 'track');
  assert(TRACKS.has(selectedTrack), `unsupported track ${selectedTrack}`);
  assert(results && typeof results === 'object' && !Array.isArray(results), 'results must be an object keyed by benchmark id');
  const required = validatedRegistry.filter(benchmark => benchmark.requiredFor.includes(selectedTrack));
  const evaluations = required.map(benchmark => {
    const result = results[benchmark.id];
    if (result === undefined) {
      return Object.freeze({
        id: benchmark.id,
        category: benchmark.category,
        status: 'missing',
        checks: Object.freeze([]),
      });
    }
    try {
      const validatedResult = validateResult(result, benchmark.id);
      const checks = benchmark.criteria.map(criterion => (
        evaluateCriterion(criterion, validatedResult.metrics, benchmark.id)
      ));
      return Object.freeze({
        id: benchmark.id,
        category: benchmark.category,
        status: checks.every(check => check.ok) ? 'passed' : 'failed',
        checks: Object.freeze(checks),
        scenarioHash: validatedResult.scenarioHash,
        codeCommit: validatedResult.codeCommit,
      });
    } catch (error) {
      return Object.freeze({
        id: benchmark.id,
        category: benchmark.category,
        status: 'invalid',
        checks: Object.freeze([]),
        error: String(error),
      });
    }
  });
  const passed = evaluations.filter(evaluation => evaluation.status === 'passed').length;
  const failed = evaluations.filter(evaluation => evaluation.status === 'failed').length;
  const missing = evaluations.filter(evaluation => evaluation.status === 'missing').length;
  const invalid = evaluations.filter(evaluation => evaluation.status === 'invalid').length;
  const syntheticTrackReady = passed === evaluations.length;
  return Object.freeze({
    schema: 'onga-stage16-benchmark-registry-evaluation-v1',
    registryVersion: STAGE16_BENCHMARK_REGISTRY_VERSION,
    track: selectedTrack,
    status: syntheticTrackReady ? 'passed' : 'incomplete_or_failed',
    syntheticTrackReady,
    physicalValidationReady: false,
    publicProductionReady: false,
    counts: Object.freeze({ required: evaluations.length, passed, failed, missing, invalid }),
    evaluations: Object.freeze(evaluations),
    note: 'Passing this registry establishes numerical synthetic Verification only．It does not approve physical Validation or public production．',
  });
}

export const Stage16BenchmarkRegistry = Object.freeze({
  version: STAGE16_BENCHMARK_REGISTRY_VERSION,
  tracks: Object.freeze([...TRACKS]),
  defaultRegistry: DEFAULT_STAGE16_BENCHMARK_REGISTRY,
  validateBenchmarkRegistry,
  evaluateBenchmarkRegistry,
});
