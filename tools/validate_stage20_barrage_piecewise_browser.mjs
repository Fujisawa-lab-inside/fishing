import crypto from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { Worker } from 'node:worker_threads';

import {
  decodeStage20BarragePiecewisePack,
  interpolateStage20BarrageFiveHourFields,
  stage20BarragePiecewiseWeights,
} from '../onga_stage20_barrage_piecewise_interpolator.mjs';

const PACK_MANIFEST_PATH =
  'docs/results/stage20-barrage-piecewise-candidate-v1/barrage-piecewise-anchor-pack.json';
const PACK_BINARY_PATH =
  'docs/results/stage20-barrage-piecewise-candidate-v1/barrage-piecewise-anchor-pack.bin';
const DEFAULT_OUTPUT_PATH =
  'config/stage20_barrage_piecewise_validation_v1.json';
const EXPECTED_ANALYSIS_SHA256 =
  '82ce4ece4dda010b846204266e604c01d26eaffba041bd4b04329a353fc834c2';
const EXPECTED_RESULT_SHA256 =
  'fe4be9be3112eafff9965abc68bf254c78d560344c99cb2d5f31e1e75af519ab';
const EXPECTED_MESH_SHA256 =
  '09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659';
const EXPECTED_MESH_MANIFEST_SHA256 =
  '17850a07821f409f13bd3c38446982ae6124743ad9e6437d5d612da447f421c8';
const EXPECTED_PACK_SHA256 =
  'd3a0b315d7fb3bf17c04a4715b1595242b501a50dacc163ae8716013ed638047';
const EXPECTED_MANIFEST_SHA256 =
  'f5770256962268f2e6e4a1bec2a124fada55568d3e4ab0fe74269bbf3f0eecbc';
const OPENINGS = Object.freeze([0, 0.25, 0.5, 0.75, 1]);

function requireValue(condition, message) {
  if (!condition) throw new Error(`[stage20-barrage-piecewise-validation] ${message}`);
}

function sha256(payload) {
  return crypto.createHash('sha256').update(payload).digest('hex');
}

function arrayBuffer(buffer) {
  return buffer.buffer.slice(
    buffer.byteOffset,
    buffer.byteOffset + buffer.byteLength,
  );
}

function arraysEqual(first, second) {
  if (
    !(first instanceof Float32Array)
    || !(second instanceof Float32Array)
    || first.length !== second.length
  ) {
    return false;
  }
  return Buffer.from(
    first.buffer,
    first.byteOffset,
    first.byteLength,
  ).equals(
    Buffer.from(second.buffer, second.byteOffset, second.byteLength),
  );
}

function expectedAdjacentMidpoint(pack, lowerAnchorIndex, upperAnchorIndex) {
  const stride = pack.hourCount * pack.componentCount * pack.cellCount;
  const lowerOffset = lowerAnchorIndex * stride;
  const upperOffset = upperAnchorIndex * stride;
  const result = new Float32Array(stride);
  for (let index = 0; index < stride; index += 1) {
    result[index] =
      pack.anchors[lowerOffset + index] * 0.5
      + pack.anchors[upperOffset + index] * 0.5;
  }
  return result;
}

async function fileDigest(path) {
  return sha256(await readFile(path));
}

async function rejectCase(callback, label) {
  let rejected = false;
  try {
    await callback();
  } catch {
    rejected = true;
  }
  requireValue(rejected, `${label} was accepted`);
  return label;
}

async function validateSourceFiles(manifest) {
  requireValue(
    manifest.sourceAnalysis?.sha256 === EXPECTED_ANALYSIS_SHA256,
    'source analysis identity changed',
  );
  requireValue(
    manifest.sourceDecision?.sha256 === EXPECTED_RESULT_SHA256,
    'source decision identity changed',
  );
  requireValue(
    await fileDigest(manifest.sourceAnalysis.path) ===
      manifest.sourceAnalysis.sha256,
    'source analysis digest mismatch',
  );
  requireValue(
    await fileDigest(manifest.sourceDecision.path) ===
      manifest.sourceDecision.sha256,
    'source decision digest mismatch',
  );
  requireValue(
    await fileDigest(manifest.builder.path) === manifest.builder.sha256,
    'builder digest mismatch',
  );
  requireValue(
    manifest.mesh?.binarySha256 === EXPECTED_MESH_SHA256,
    'mesh identity changed',
  );
  requireValue(
    await fileDigest(manifest.mesh.binary) === manifest.mesh.binarySha256,
    'mesh binary digest mismatch',
  );
  requireValue(
    manifest.mesh?.manifestSha256 === EXPECTED_MESH_MANIFEST_SHA256,
    'mesh manifest identity changed',
  );
  requireValue(
    await fileDigest(manifest.mesh.manifest) ===
      manifest.mesh.manifestSha256,
    'mesh manifest digest mismatch',
  );
  const meshManifest = JSON.parse(
    await readFile(manifest.mesh.manifest, 'utf8'),
  );
  requireValue(
    meshManifest.schema === 'onga-stage20-browser-mesh-v2',
    'mesh manifest schema mismatch',
  );
  requireValue(
    meshManifest.counts?.cells === 50199,
    'mesh manifest cell count mismatch',
  );
  requireValue(
    meshManifest.binary?.sha256 === EXPECTED_MESH_SHA256,
    'mesh manifest binary identity mismatch',
  );
  requireValue(
    resolve(dirname(manifest.mesh.manifest), meshManifest.binary.url)
      === resolve(manifest.mesh.binary),
    'mesh manifest binary path mismatch',
  );
  requireValue(
    Array.isArray(manifest.sourceAnchors)
      && manifest.sourceAnchors.length === 15,
    'source anchor inventory mismatch',
  );
  const identities = [];
  for (const source of manifest.sourceAnchors) {
    requireValue(
      await fileDigest(source.path) === source.sha256,
      `source anchor digest mismatch: ${source.path}`,
    );
    requireValue(
      (await readFile(source.path)).byteLength === source.byteLength,
      `source anchor byte length mismatch: ${source.path}`,
    );
    identities.push(`${source.openingFraction}:${source.modelHour}`);
  }
  const expectedIdentities = [0, 0.5, 1]
    .flatMap(opening => [-12, -11, -10, -9, -8]
      .map(hour => `${opening}:${hour}`));
  requireValue(
    identities.join('|') === expectedIdentities.join('|'),
    'source anchor order mismatch',
  );

  const quantization = manifest.float32Quantization;
  requireValue(quantization?.passed === true, 'float32 quantization did not pass');
  for (const [valueKey, limitKey] of [
    ['maximumDepthAbsoluteErrorM', 'maximumDepthAbsoluteErrorM'],
    [
      'maximumVelocityComponentAbsoluteErrorMPS',
      'maximumVelocityComponentAbsoluteErrorMPS',
    ],
    [
      'maximumVelocityVectorAbsoluteErrorMPS',
      'maximumVelocityVectorAbsoluteErrorMPS',
    ],
    ['maximumVelocityVectorRmseMPS', 'maximumVelocityVectorRmseMPS'],
  ]) {
    requireValue(
      Number.isFinite(quantization[valueKey])
        && Number.isFinite(quantization.acceptanceLimits?.[limitKey])
        && quantization[valueKey] <= quantization.acceptanceLimits[limitKey],
      `float32 quantization limit failed: ${valueKey}`,
    );
  }

  requireValue(
    manifest.limitations?.valueContinuityAtMiddleAnchor ===
      'guaranteed_by_construction',
    'middle-anchor continuity contract changed',
  );
  requireValue(
    manifest.limitations?.slopeContinuityAtMiddleAnchor ===
      'not_guaranteed_and_known_to_have_a_kink',
    'middle-anchor slope limitation changed',
  );
  requireValue(
    manifest.limitations?.physicalInterpolationAccuracyValidated === false,
    'physical interpolation accuracy was claimed',
  );
  for (const key of [
    'physicalSolverInvoked',
    'additionalPhysicalRunPerformed',
    'automaticRetryPerformed',
    'referenceS03RunPerformed',
    'networkAccessAttempted',
    'publicSimulatorConnected',
    'mainMerged',
    'physicalValidationClaimAllowed',
    'forecastValidationClaimAllowed',
  ]) {
    requireValue(
      manifest.safeguards?.[key] === false,
      `pack safeguard ${key} is not false`,
    );
  }
}

async function validateWorker({
  manifestPath,
  binaryPath,
  expectedFields,
  expectedDigest,
}) {
  const workerPath = resolve('onga_stage20_barrage_piecewise_worker.mjs');
  const workerUrl = pathToFileURL(workerPath).href;
  const manifestAbsolute = resolve(manifestPath);
  const binaryAbsolute = resolve(binaryPath);
  const wrapper = `
    import { parentPort } from 'node:worker_threads';
    import { readFile } from 'node:fs/promises';
    const manifestText = await readFile(${JSON.stringify(manifestAbsolute)}, 'utf8');
    const manifest = JSON.parse(manifestText);
    const binary = await readFile(${JSON.stringify(binaryAbsolute)});
    const manifestUrl = 'http://stage20.local/barrage-piecewise-anchor-pack.json';
    const binaryUrl = 'http://stage20.local/barrage-piecewise-anchor-pack.bin';
    globalThis.fetch = async value => {
      const url = String(value);
      if (url === manifestUrl) {
        return {
          ok: true,
          status: 200,
          url: manifestUrl,
          text: async () => manifestText,
        };
      }
      if (url === binaryUrl) {
        return {
          ok: true,
          status: 200,
          url: binaryUrl,
          arrayBuffer: async () => binary.buffer.slice(
            binary.byteOffset,
            binary.byteOffset + binary.byteLength,
          ),
        };
      }
      return { ok: false, status: 404, url };
    };
    globalThis.self = {
      addEventListener(type, callback) {
        if (type === 'message') {
          parentPort.on('message', data => callback({ data }));
        }
      },
      postMessage(data, transfer) {
        parentPort.postMessage(data, transfer);
      },
    };
    await import(${JSON.stringify(workerUrl)});
    parentPort.postMessage({ type: 'ready' });
  `;
  const worker = new Worker(
    new URL(`data:text/javascript,${encodeURIComponent(wrapper)}`),
    { type: 'module' },
  );
  let result;
  try {
    result = await new Promise((resolveResult, reject) => {
      let settled = false;
      let timeout;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        callback(value);
      };
      timeout = setTimeout(
        () => finish(
          reject,
          new Error('piecewise worker validation timed out'),
        ),
        30000,
      );
      worker.on('error', error => finish(reject, error));
      worker.on('message', message => {
        if (message.type === 'ready') {
          worker.postMessage({
            type: 'run-barrage-piecewise-candidate',
            anchorManifestUrl:
              'http://stage20.local/barrage-piecewise-anchor-pack.json',
            openingFraction: 0.25,
            includeOutput: true,
          });
          return;
        }
        finish(resolveResult, message);
      });
    });
  } finally {
    await worker.terminate();
  }
  requireValue(result.status === 'passed', result.error || 'worker failed');
  requireValue(result.openingFraction === 0.25, 'worker opening mismatch');
  requireValue(result.segmentId === 'opening-0-to-50', 'worker segment mismatch');
  requireValue(result.snapshotCount === 5, 'worker snapshot count mismatch');
  requireValue(
    result.hourRange[0] === -12 && result.hourRange[1] === -8,
    'worker hour range mismatch',
  );
  requireValue(result.cellCount === 50199, 'worker cell count mismatch');
  requireValue(result.meshSha256 === EXPECTED_MESH_SHA256, 'worker mesh mismatch');
  requireValue(result.outputSha256 === expectedDigest, 'worker output digest mismatch');
  requireValue(result.fields instanceof Float32Array, 'worker output transfer failed');
  requireValue(arraysEqual(result.fields, expectedFields), 'worker output differs from direct module');
  requireValue(result.timingsMs.total < 10000, 'worker exceeded the development target');
  requireValue(result.safeguards?.solverInvoked === false, 'worker invoked a solver');
  requireValue(
    result.safeguards?.physicalRunPerformed === false,
    'worker performed a physical run',
  );
  requireValue(
    result.safeguards?.publicSimulatorConnected === false,
    'worker connected the public simulator',
  );
  delete result.fields;
  result.outputTransferValidated = true;
  return result;
}

const outputPath = process.argv[2] || DEFAULT_OUTPUT_PATH;
const manifestText = await readFile(PACK_MANIFEST_PATH, 'utf8');
const manifest = JSON.parse(manifestText);
const manifestDigest = sha256(manifestText);
requireValue(
  manifestDigest === EXPECTED_MANIFEST_SHA256,
  'approved anchor-pack manifest identity changed',
);
await validateSourceFiles(manifest);
requireValue(
  manifest.binary.url === './barrage-piecewise-anchor-pack.bin',
  'anchor-pack binary URL mismatch',
);
const binary = await readFile(PACK_BINARY_PATH);
requireValue(binary.byteLength === 9_035_820, 'anchor-pack byte length mismatch');
requireValue(sha256(binary) === manifest.binary.sha256, 'anchor-pack digest mismatch');
requireValue(
  manifest.binary.sha256 === EXPECTED_PACK_SHA256,
  'approved anchor-pack identity changed',
);
requireValue(
  manifest.arrays?.anchors?.sha256 === manifest.binary.sha256,
  'anchor descriptor digest mismatch',
);
const originalBinaryDigest = sha256(binary);
const pack = await decodeStage20BarragePiecewisePack(
  manifestText,
  arrayBuffer(binary),
);

const directStarted = performance.now();
const results = [];
for (const opening of OPENINGS) {
  const first = interpolateStage20BarrageFiveHourFields(pack, opening);
  const second = interpolateStage20BarrageFiveHourFields(pack, opening);
  const firstDigest = sha256(Buffer.from(first.fields.buffer));
  const secondDigest = sha256(Buffer.from(second.fields.buffer));
  requireValue(firstDigest === secondDigest, `opening ${opening} is not deterministic`);
  requireValue(arraysEqual(first.fields, second.fields), `opening ${opening} repeat differs`);
  requireValue(first.fields.byteLength === 3_011_940, `opening ${opening} output length mismatch`);
  requireValue(first.snapshotCount === 5 && first.cellCount === 50199, `opening ${opening} identity mismatch`);
  requireValue(first.diagnostics.nonFiniteValueCount === 0, `opening ${opening} is non-finite`);
  requireValue(first.diagnostics.negativeDepthCount === 0, `opening ${opening} has negative depth`);
  const weights = stage20BarragePiecewiseWeights(opening);
  requireValue(
    weights.lowerWeight >= 0
      && weights.upperWeight >= 0
      && Math.abs(weights.lowerWeight + weights.upperWeight - 1) <= Number.EPSILON,
    `opening ${opening} weights are not convex`,
  );
  results.push({
    openingFraction: opening,
    segmentId: first.segmentId,
    exactAnchor: first.exactAnchor,
    lowerAnchorFraction: first.lowerAnchorFraction,
    upperAnchorFraction: first.upperAnchorFraction,
    lowerWeight: first.lowerWeight,
    upperWeight: first.upperWeight,
    outputBytes: first.fields.byteLength,
    outputSha256: firstDigest,
    diagnostics: first.diagnostics,
  });
}
const directElapsedMs = performance.now() - directStarted;
requireValue(directElapsedMs < 1000, 'direct five-opening validation exceeded one second');

const anchorStride = pack.hourCount * pack.componentCount * pack.cellCount;
for (const [opening, anchorIndex] of [[0, 0], [0.5, 1], [1, 2]]) {
  const actual = interpolateStage20BarrageFiveHourFields(pack, opening).fields;
  const expected = pack.anchors.slice(
    anchorIndex * anchorStride,
    (anchorIndex + 1) * anchorStride,
  );
  requireValue(arraysEqual(actual, expected), `opening ${opening} anchor was not reproduced exactly`);
}
const quarter = interpolateStage20BarrageFiveHourFields(pack, 0.25);
const threeQuarter = interpolateStage20BarrageFiveHourFields(pack, 0.75);
requireValue(
  arraysEqual(quarter.fields, expectedAdjacentMidpoint(pack, 0, 1)),
  '25% adjacent midpoint mismatch',
);
requireValue(
  arraysEqual(threeQuarter.fields, expectedAdjacentMidpoint(pack, 1, 2)),
  '75% adjacent midpoint mismatch',
);

const rejectedCases = [];
for (const [label, value] of [
  ['opening_below_zero', -Number.EPSILON],
  ['opening_above_one', 1 + Number.EPSILON],
  ['opening_nan', Number.NaN],
  ['opening_positive_infinity', Number.POSITIVE_INFINITY],
  ['opening_array_schedule', [0, 0.5, 1]],
]) {
  rejectedCases.push(
    await rejectCase(
      () => interpolateStage20BarrageFiveHourFields(pack, value),
      label,
    ),
  );
}
rejectedCases.push(
  await rejectCase(() => {
    const invalid = structuredClone(manifest);
    invalid.timeContract.timeInterpolationAllowed = true;
    return decodeStage20BarragePiecewisePack(
      JSON.stringify(invalid),
      arrayBuffer(binary),
    );
  }, 'time_interpolation_enabled'),
);
rejectedCases.push(
  await rejectCase(() => {
    const invalid = structuredClone(manifest);
    invalid.openingContract.timeVaryingScheduleAllowed = true;
    return decodeStage20BarragePiecewisePack(
      JSON.stringify(invalid),
      arrayBuffer(binary),
    );
  }, 'time_varying_opening_enabled'),
);
rejectedCases.push(
  await rejectCase(() => {
    const invalid = structuredClone(manifest);
    invalid.arrays.anchors.sha256 = '0'.repeat(64);
    return decodeStage20BarragePiecewisePack(
      JSON.stringify(invalid),
      arrayBuffer(binary),
    );
  }, 'anchor_descriptor_digest_mismatch'),
);
rejectedCases.push(
  await rejectCase(() => {
    const invalid = structuredClone(manifest);
    invalid.binary.sha256 = '0'.repeat(64);
    invalid.arrays.anchors.sha256 = invalid.binary.sha256;
    return decodeStage20BarragePiecewisePack(
      JSON.stringify(invalid),
      arrayBuffer(binary),
    );
  }, 'unapproved_pack_identity'),
);
rejectedCases.push(
  await rejectCase(() => {
    const invalid = structuredClone(manifest);
    invalid.mesh.binarySha256 = '0'.repeat(64);
    return decodeStage20BarragePiecewisePack(
      JSON.stringify(invalid),
      arrayBuffer(binary),
    );
  }, 'unapproved_mesh_identity'),
);
rejectedCases.push(
  await rejectCase(() => {
    const invalid = structuredClone(manifest);
    invalid.scope.boundaryInputs.ODischargeM3S = 36;
    return decodeStage20BarragePiecewisePack(
      JSON.stringify(invalid),
      arrayBuffer(binary),
    );
  }, 'different_boundary_inputs'),
);
rejectedCases.push(
  await rejectCase(() => {
    const invalid = structuredClone(manifest);
    invalid.sourceAnalysis.sha256 = '0'.repeat(64);
    return decodeStage20BarragePiecewisePack(
      JSON.stringify(invalid),
      arrayBuffer(binary),
    );
  }, 'unapproved_source_analysis'),
);
rejectedCases.push(
  await rejectCase(() => {
    const invalid = structuredClone(manifest);
    invalid.timeContract.anchorHours = [-12, -11, -10, -9];
    return decodeStage20BarragePiecewisePack(
      JSON.stringify(invalid),
      arrayBuffer(binary),
    );
  }, 'missing_model_hour'),
);
rejectedCases.push(
  await rejectCase(() => {
    const truncated = binary.subarray(0, binary.length - 4);
    return decodeStage20BarragePiecewisePack(
      manifestText,
      arrayBuffer(truncated),
    );
  }, 'truncated_binary'),
);
rejectedCases.push(
  await rejectCase(() => {
    const modified = Buffer.from(binary);
    modified[modified.length - 1] ^= 1;
    return decodeStage20BarragePiecewisePack(
      manifestText,
      arrayBuffer(modified),
    );
  }, 'same_length_payload_digest_mismatch'),
);

requireValue(sha256(binary) === originalBinaryDigest, 'input anchor pack was mutated');
const resultByOpening = new Map(
  results.map(result => [result.openingFraction, result]),
);
const workerResult = await validateWorker({
  manifestPath: PACK_MANIFEST_PATH,
  binaryPath: PACK_BINARY_PATH,
  expectedFields: quarter.fields,
  expectedDigest: resultByOpening.get(0.25).outputSha256,
});

const modulePath = 'onga_stage20_barrage_piecewise_interpolator.mjs';
const workerPath = 'onga_stage20_barrage_piecewise_worker.mjs';
const validatorPath = 'tools/validate_stage20_barrage_piecewise_browser.mjs';
const report = {
  schema: 'onga-stage20-barrage-piecewise-validation-v1',
  status:
    'passed_code_only_piecewise_browser_candidate_validation_not_physical_validation',
  validatedDate: '2026-07-17',
  sourceDecision: {
    path: manifest.sourceDecision.path,
    sha256: manifest.sourceDecision.sha256,
    selectedOption: 'A',
  },
  anchorPack: {
    manifest: PACK_MANIFEST_PATH,
    manifestSha256: manifestDigest,
    binary: PACK_BINARY_PATH,
    binarySha256: manifest.binary.sha256,
    binaryBytes: binary.byteLength,
    sourceAnchorCount: manifest.sourceAnchors.length,
    openingFractions: manifest.openingContract.anchorFractions,
    modelHours: manifest.timeContract.anchorHours,
    componentOrder: manifest.componentOrder,
    cellCount: manifest.mesh.cellCount,
  },
  toolchain: {
    module: modulePath,
    moduleSha256: await fileDigest(modulePath),
    worker: workerPath,
    workerSha256: await fileDigest(workerPath),
    validator: validatorPath,
    validatorSha256: await fileDigest(validatorPath),
  },
  directModuleValidation: {
    status: 'passed',
    openingResults: results,
    elapsedMs: directElapsedMs,
    targetMs: 1000,
    deterministic: true,
    exactAnchorReproduction: true,
    adjacentMidpointsExactFloat32: true,
    convexWeights: true,
  },
  workerValidation: workerResult,
  negativeCases: {
    status: 'passed',
    rejected: rejectedCases,
  },
  float32Quantization: manifest.float32Quantization,
  resource: {
    anchorPackBytes: binary.byteLength,
    fiveHourOutputBytes: quarter.fields.byteLength,
    packPlusOneOutputBytes: binary.byteLength + quarter.fields.byteLength,
    packPlusOneOutputMiB:
      (binary.byteLength + quarter.fields.byteLength) / (1024 * 1024),
  },
  applicability: {
    supportedModelHours: [-12, -11, -10, -9, -8],
    oneOpeningScalarConstantAcrossFiveHours: true,
    timeInterpolationAllowed: false,
    timeExtrapolationAllowed: false,
    differentBoundaryInputsAllowed: false,
    physicalAccuracyAt25And75PercentValidated: false,
    thirtySixHourServiceReady: false,
  },
  safeguards: {
    physicalSolverInvoked: false,
    additionalPhysicalRunPerformed: false,
    automaticRetryPerformed: false,
    referenceS03RunPerformed: false,
    networkAccessAttempted: false,
    existingHybridModulesModified: false,
    publicSimulatorConnected: false,
    mainMerged: false,
    physicalValidationClaimAllowed: false,
    forecastValidationClaimAllowed: false,
  },
};
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
