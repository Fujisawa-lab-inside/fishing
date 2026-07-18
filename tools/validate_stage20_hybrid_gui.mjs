import fs from 'node:fs';
import vm from 'node:vm';

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

function extractFunctionDeclaration(source, name) {
  const match = new RegExp(`function\\s+${name}\\s*\\(`).exec(source);
  requireCondition(match, `GUI function declaration is missing: ${name}`);
  const openBrace = source.indexOf('{', match.index);
  requireCondition(openBrace >= 0, `GUI function body is missing: ${name}`);
  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let index = openBrace; index < source.length; index += 1) {
    const character = source[index];
    const next = source[index + 1];
    if (lineComment) {
      if (character === '\n') lineComment = false;
      continue;
    }
    if (blockComment) {
      if (character === '*' && next === '/') {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote !== null) {
      if (escaped) {
        escaped = false;
      } else if (character === '\\') {
        escaped = true;
      } else if (character === quote) {
        quote = null;
      }
      continue;
    }
    if (character === '/' && next === '/') {
      lineComment = true;
      index += 1;
      continue;
    }
    if (character === '/' && next === '*') {
      blockComment = true;
      index += 1;
      continue;
    }
    if (character === "'" || character === '"' || character === '`') {
      quote = character;
      continue;
    }
    if (character === '{') depth += 1;
    if (character === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(match.index, index + 1);
    }
  }
  throw new Error(`GUI function body is incomplete: ${name}`);
}

function boundElementKey(source, id) {
  const match = new RegExp(`([A-Za-z_$][\\w$]*)\\s*:\\s*byId\\(['"]${id}['"]\\)`).exec(source);
  requireCondition(match, `GUI element binding is missing: ${id}`);
  return match[1];
}

const html = fs.readFileSync('stage20-hybrid-gui.html', 'utf8');
const css = fs.readFileSync('stage20-hybrid-gui.css', 'utf8');
const gui = fs.readFileSync('onga_stage20_gui.mjs', 'utf8');
const adapter = fs.readFileSync('onga_stage20_gui_data.mjs', 'utf8');
const worker = fs.readFileSync('onga_stage20_hybrid_worker.mjs', 'utf8');
const gateContractDoc = fs.readFileSync('docs/STAGE20_GATE_INPUT_UI_CANDIDATE.md', 'utf8');
const publicPlan = JSON.parse(fs.readFileSync('config/stage19_public_inference_input_plan_v1.json', 'utf8'));
const publishedGateFacts = publicPlan.publicEvidence.find(item => item.id === 'mlit_onga_barrage_gate_public_facts')?.facts;
const viewCount = (html.match(/data-view="/g) || []).length;
const layerCount = (html.match(/data-layer="/g) || []).length;
const gateCount = (html.match(/data-gate="/g) || []).length;
const sliderTag = html.match(/<input[^>]+id="time-slider"[^>]*>/)?.[0] || '';

for (const marker of [
  '自動推定',
  '現地目視入力',
  '5 → 4 → 6 → 3 → 7 → 2 → 8 → 1',
  '0%（閉）',
  '100%（開）',
  '入力元',
  '観測時刻',
  '自動との差',
  '自動推定へ戻す',
  '標準順序外',
  '流れの図には未反映',
  '物理solver',
  '応答pack',
  '合成Worker',
  '事前計算',
  '公開シミュレーター',
]) {
  requireCondition(gateContractDoc.includes(marker), 'gate-input UI contract marker is missing: ' + marker);
}

for (const marker of [
  'id="flow-map"',
  'id="time-slider"',
  'data-layer="speed"',
  'data-layer="depth"',
  'data-view="estuary"',
  'data-view="barrage"',
  'data-view="confluence"',
  'data-view="fishway"',
  'GUI試作',
  '合成データ',
  '物理予測ではありません',
  '流れの図には未反映',
  '各46.5mの主水門',
  '魚道は1〜8番に含めません',
  'id="gate-mode-auto"',
  'id="gate-mode-field"',
  'id="gate-source"',
  'id="gate-observed-at"',
  'id="gate-return-auto"',
  'id="gate-auto-stage"',
  'id="gate-delta"',
  'id="gate-standard-status"',
  '自動推定',
  '現地目視入力',
  '入力元',
  '観測時刻',
  '自動との差',
  '自動推定へ戻す',
  '標準順序外',
]) {
  requireCondition(html.includes(marker), 'GUI HTML marker is missing: ' + marker);
}
requireCondition(html.includes('stage20-hybrid-gui.css'), 'GUI stylesheet is not linked');
requireCondition(html.includes('onga_stage20_gui.mjs'), 'GUI module is not linked');
requireCondition(viewCount === 4, 'GUI must expose exactly four map views');
requireCondition(layerCount === 2, 'GUI must expose exactly two field layers');
requireCondition(gateCount === 8, 'GUI must expose exactly eight barrage gates');
requireCondition(/min="0"/.test(sliderTag) && /max="36"/.test(sliderTag) && /step="1"/.test(sliderTag), '37-step time slider contract changed');
requireCondition(css.includes('@media (max-width: 760px)'), 'mobile breakpoint is missing');
requireCondition(css.includes(':focus-visible'), 'keyboard focus treatment is missing');
requireCondition(!html.includes('user-scalable=no'), 'page zoom must not be disabled');
requireCondition(html.includes('id="retry-button"'), 'retry control is missing');

for (const marker of [
  "import { loadStage20GuiData } from './onga_stage20_gui_data.mjs'",
  'renderCells(',
  'renderArrows(',
  'renderMarkers(',
  'renderGateInputOverlay(',
  'setGateObservation(',
  'GATE_OPENING_ORDER',
  'gatePatternForStage(',
  'classifyGatePattern(',
  'lonLatToWorld(',
  'fitGateAxisUnit(',
  'metresPerWorldPixel(',
  'data.gateCenters.map(',
  'data.metadata.mainGateWidthM',
  'selectCellAtCanvasPoint(',
  'togglePlayback(',
]) {
  requireCondition(gui.includes(marker), 'GUI implementation marker is missing: ' + marker);
}

const openingOrderMatch = /const\s+GATE_OPENING_ORDER\s*=\s*Object\.freeze\(\s*\[([^\]]+)]\s*\)\s*;/.exec(gui);
requireCondition(openingOrderMatch, 'fixed gate-opening order declaration is missing');
const gateOpeningOrder = openingOrderMatch[1].split(',').map(value => Number(value.trim()));
requireCondition(gateOpeningOrder.join(',') === '5,4,6,3,7,2,8,1', 'gate-opening order must be 5,4,6,3,7,2,8,1');
requireCondition(
  /Math\.round\(clamp\(fraction,\s*0,\s*1\)\s*\*\s*8\)/.test(gui),
  'automatic gate stage must round the clamped overall opening fraction to stage 0 through 8',
);
requireCondition(!/Array\(8\)\.fill\(50\)/.test(gui), 'automatic gate estimate must not assign 50% to all gates');

const gatePatternFunction = extractFunctionDeclaration(gui, 'gatePatternForStage');
const classifyGateFunction = extractFunctionDeclaration(gui, 'classifyGatePattern');
const contractSandbox = {};
vm.runInNewContext(`
  const GATE_OPENING_ORDER = Object.freeze([${gateOpeningOrder.join(',')}]);
  ${gatePatternFunction}
  ${classifyGateFunction}
  globalThis.gateContract = { gatePatternForStage, classifyGatePattern };
`, contractSandbox, { timeout: 1_000 });
const gatePatterns = [];
for (let stage = 0; stage <= 8; stage += 1) {
  const expected = Array(8).fill(0);
  for (const gateNumber of gateOpeningOrder.slice(0, stage)) expected[gateNumber - 1] = 100;
  const actual = Array.from(contractSandbox.gateContract.gatePatternForStage(stage));
  requireCondition(actual.length === 8, `gate stage ${stage} must contain eight values`);
  requireCondition(actual.every(value => value === 0 || value === 100), `gate stage ${stage} must use only 0/100 values`);
  requireCondition(JSON.stringify(actual) === JSON.stringify(expected), `gate stage ${stage} does not match the fixed order`);
  requireCondition(contractSandbox.gateContract.classifyGatePattern(actual) === stage, `gate stage ${stage} is not classified correctly`);
  gatePatterns.push(actual);
}
requireCondition(new Set(gatePatterns.map(pattern => pattern.join(','))).size === 9, 'gate stages 0 through 8 must be unique');
requireCondition(
  contractSandbox.gateContract.classifyGatePattern([100, 0, 0, 0, 0, 0, 0, 0]) === null,
  'nonstandard gate pattern must be classified as null',
);

for (const id of ['gate-mode-auto', 'gate-mode-field', 'gate-source', 'gate-observed-at', 'gate-return-auto']) {
  const key = boundElementKey(gui, id);
  requireCondition(gui.includes(`elements.${key}.addEventListener(`), `GUI control is not wired: ${id}`);
}
for (const id of ['gate-auto-stage', 'gate-delta', 'gate-standard-status']) boundElementKey(gui, id);

for (const [sourceName, source] of [['GUI data adapter', adapter], ['hybrid Worker', worker]]) {
  for (const marker of [
    'GATE_OPENING_ORDER',
    'gatePatternForStage',
    'classifyGatePattern',
    'gateObservation',
    'gateMode',
    'gateSource',
    'gateObservedAt',
  ]) {
    requireCondition(!source.includes(marker), `${sourceName} must not receive display-only gate input: ${marker}`);
  }
}
requireCondition(!gui.includes('8 - barrageGateIds'), 'GUI must not place field gate numbers from equal mesh divisions');
requireCondition(!gui.includes('nearestPointIndex('), 'GUI must not assign the fishway-side wet span to the nearest main gate');
requireCondition(!gui.includes('mesh.arrays.barrage_face_ids'), 'GUI gate display must not use the full numerical barrage span');
requireCondition(
  gui.includes('data.fishwayCenter.longitude')
    && gui.includes('fishwayCenter: fishwayCoordinateCenter'),
  'GUI fishway marker must use the pinned provided coordinate',
);
requireCondition(
  !gui.includes('fishwayCenter: averagePoints(fishwayPoints)'),
  'GUI must not replace the provided fishway position with mesh-cell averaging',
);
requireCondition(publishedGateFacts?.mainGateCount === 8, 'published main-gate count must remain eight');
requireCondition(publishedGateFacts?.publishedMainGateWidthM === 46.5, 'published main-gate width must remain 46.5m');
for (const marker of [
  'mesh-v2.json',
  'response-pack-synthetic-v2.json',
  'hybrid-synthetic-input-v1.json',
  'includeOutput: true',
  'const snapshot = index =>',
  'synthetic_browser_benchmark_only',
  'barrage_gate_id',
  'onga_geometry.geojson',
  'gate_center',
  'fishway_center',
  'PUBLISHED_MAIN_GATE_WIDTH_M = 46.5',
  'mlit_onga_barrage_gate_public_facts',
  '8593f67c5157ed1d55b717ba6ed691674694cfa499f7f7d533fc9950acdfc536',
  '09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659',
  '2d92e67d2ececf8e3c9e540003cd5546e3f6a38b234de7b5122aa4448c3478a3',
  '146429c21fecc13359710bb5335885258b63cd1f5750b6816f01098659135417',
]) {
  requireCondition(adapter.includes(marker), 'GUI data-contract marker is missing: ' + marker);
}

const combined = html + '\n' + css + '\n' + gui + '\n' + adapter;
requireCondition(!/https?:\/\//i.test(combined), 'GUI must not reference remote HTTP assets');
for (const forbidden of [
  'stage20_barrage_holdout_activation',
  'run_stage20_barrage_holdout_segment',
  'github/workflows',
  'cyberjapandata.gsi.go.jp',
]) {
  requireCondition(!combined.includes(forbidden), 'GUI unexpectedly references an execution or remote boundary: ' + forbidden);
}

console.log(JSON.stringify({
  schema: 'onga-stage20-hybrid-gui-validation-v2',
  status: 'passed_static_gui_contract',
  files: [
    'stage20-hybrid-gui.html',
    'stage20-hybrid-gui.css',
    'onga_stage20_gui.mjs',
    'onga_stage20_gui_data.mjs',
    'docs/STAGE20_GATE_INPUT_UI_CANDIDATE.md',
  ],
  controls: {
    views: viewCount,
    layers: layerCount,
    barrageGates: gateCount,
    snapshotCount: Number(sliderTag.match(/max="(\d+)"/)?.[1]) + 1,
    hourRange: [-12, 24],
    pointSelection: true,
    playback: true,
    retryState: html.includes('id="retry-button"') && gui.includes('elements.retry.addEventListener'),
    gateInputDisplayOnly: html.includes('流れの図には未反映') && gui.includes('renderGateInputOverlay('),
    gateInputModes: ['auto', 'field'],
    gateOpeningOrder,
    gateStageCount: gatePatterns.length,
    gateStageValuesPercent: [0, 100],
    fieldOverrideMetadata: ['source', 'observedAt'],
    fieldAutoDelta: html.includes('id="gate-delta"'),
    fieldReturnToAuto: html.includes('id="gate-return-auto"'),
    standardPatternClassification: true,
    nonstandardPatternWarning: html.includes('標準順序外'),
    providedGateCoordinates: gui.includes('data.gateCenters.map(') && adapter.includes('EXPECTED_GATE_GEOMETRY_SHA256'),
    providedFishwayCoordinate: adapter.includes("kind === 'fishway_center'")
      && gui.includes('fishwayCenter: fishwayCoordinateCenter'),
    publishedEqualGateWidthM: publishedGateFacts.publishedMainGateWidthM,
    fishwayExcludedFromGateDisplay: !gui.includes('mesh.arrays.barrage_face_ids') && gui.includes("marks: Object.freeze(['barrage', 'fishway'])"),
    mobileBreakpoint: true,
  },
  safeguards: {
    syntheticFixtureOnly: true,
    remoteTilesUsed: false,
    publicSimulatorConnected: false,
    physicalRunnerReferenced: false,
    gateInputSentToDataAdapter: false,
    gateInputSentToHybridWorker: false,
  },
}, null, 2));
