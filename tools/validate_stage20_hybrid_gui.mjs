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
const localSimulation = fs.readFileSync('onga_stage20_local_simulation.mjs', 'utf8');
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
  'data-layer="maximum-speed"',
  'data-view="estuary"',
  'data-view="barrage"',
  'data-view="confluence"',
  'data-view="fishway"',
  'ローカル実動版',
  '合成データ',
  '物理計算未実行・予測ではありません',
  '「ローカル物理計算を実行」で入力を流れ図へ反映',
  '46.5mはH2モデル開口幅の水理契約',
  '魚道は1〜8番に含めず',
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
  'data-browser-contract-version="m0.2-ui-20260826-01"',
  'data-runtime-freshness="checking"',
  'id="runtime-version-alert"',
  'id="runtime-version-message"',
  'id="runtime-reload-button"',
  'id="forcing-reprobe-button"',
  'id="local-reprobe-button"',
  'class="source-classification-banner"',
  'id="warning-hud-text"',
  '現在表示：',
  'id="local-calculation-banner"',
  'id="local-calculation-title"',
  'id="local-calculation-note"',
  'id="local-calculation-jump"',
  'aria-controls="local-simulator-card"',
  'ローカル計算：未実行',
  'class="map-source-credit"',
  '地理院タイル（国土地理院）',
  '流れ・メッシュ等を追記',
]) {
  requireCondition(html.includes(marker), 'GUI HTML marker is missing: ' + marker);
}
requireCondition(html.includes('stage20-hybrid-gui.css'), 'GUI stylesheet is not linked');
requireCondition(html.includes('onga_stage20_gui.mjs'), 'GUI module is not linked');
requireCondition(viewCount === 4, 'GUI must expose exactly four map views');
requireCondition(layerCount === 3, 'GUI must expose current speed, depth, and approved 36-hour maximum-speed layers');
requireCondition(gateCount === 8, 'GUI must expose exactly eight barrage gates');
requireCondition(/min="0"/.test(sliderTag) && /max="36"/.test(sliderTag) && /step="1"/.test(sliderTag), '37-step time slider contract changed');
requireCondition(css.includes('@media (max-width: 760px)'), 'mobile breakpoint is missing');
requireCondition(css.includes(':focus-visible'), 'keyboard focus treatment is missing');
requireCondition(!html.includes('user-scalable=no'), 'page zoom must not be disabled');
requireCondition(html.includes('id="retry-button"'), 'retry control is missing');
const viewTabsOffset = html.indexOf('class="view-tabs"');
const sourceBannerOffset = html.indexOf('id="warning-hud"');
const localCalculationBannerOffset = html.indexOf('id="local-calculation-banner"');
const mapFrameOffset = html.indexOf('id="map-frame"');
requireCondition(
  viewTabsOffset >= 0
    && viewTabsOffset < sourceBannerOffset
    && sourceBannerOffset < localCalculationBannerOffset
    && localCalculationBannerOffset < mapFrameOffset,
  'source and local-calculation banners must remain in normal flow between view tabs and map',
);
requireCondition(
  /id="warning-hud"[\s\S]{0,180}role="status"[\s\S]{0,180}aria-live="polite"[\s\S]{0,180}aria-atomic="true"/.test(html),
  'source classification banner accessibility contract changed',
);
requireCondition(
  html.includes('class="warning-dot" aria-hidden="true"'),
  'source classification marker must remain hidden from assistive technology',
);
requireCondition(
  css.includes('.source-classification-banner')
    && css.includes('min-height: 48px')
    && css.includes('background: #fff3c4'),
  'high-priority source classification banner style changed',
);
requireCondition(
  css.includes('.local-calculation-banner')
    && css.includes('.local-calculation-banner[data-status="stale"]')
    && css.includes('.local-calculation-banner[data-status="failed"]')
    && css.includes('grid-template-rows: auto auto auto minmax(420px, 1fr) auto;'),
  'always-visible local-calculation status style changed',
);
const mobileCssStart = css.indexOf('@media (max-width: 760px)');
const narrowCssStart = css.indexOf('@media (max-width: 430px)');
const mobileCss = css.slice(mobileCssStart, narrowCssStart);
requireCondition(
  mobileCssStart >= 0
    && narrowCssStart > mobileCssStart
    && mobileCss.includes('.source-badge { display: none; }'),
  'mobile UI must prioritize the full-width source banner over the compact source badge',
);

for (const marker of [
  'loadStage20GuiData,',
  'renderCells(',
  'renderArrows(',
  'renderMarkers(',
  'renderGateInputOverlay(',
  'setGateObservation(',
  'GATE_OPENING_ORDER',
  'gatePatternForStage(',
  'classifyGatePattern(',
  'lonLatToWorld(',
  'gateReferenceAnchors',
  'reference_anchor_not_exact_geometric_center',
  'gate-reference-anchor-authority-v2',
  'drawGateReferenceAnchor(',
  'selectCellAtCanvasPoint(',
  'togglePlayback(',
  'createStage20LocalSimulationJob(',
  'loadStage20LocalSimulationResult(',
  "const BROWSER_CONTRACT_VERSION = 'm0.2-ui-20260826-01'",
  'activeBrowserContractVersion = BROWSER_CONTRACT_VERSION',
  'activateBrowserContract();',
  "elements.workspace.removeAttribute('inert')",
  "localReprobeButton.addEventListener('click', probeLocalSimulator)",
  "forcingReprobeButton.addEventListener('click', probeForcingIntegrationService)",
  "localCalculationJump.addEventListener('click'",
  'syncLocalCalculationBanner(',
  'ローカル計算：入力変更済み・再計算が必要',
  "['unavailable', 'failed'].includes(state.localServiceState)",
  "['unavailable', 'error'].includes(state.forcingServiceState)",
  '合成データ（物理計算未実行・予測ではありません）',
  'ローカル物理計算（未較正・現地予測ではありません）',
]) {
  requireCondition(gui.includes(marker), 'GUI implementation marker is missing: ' + marker);
}

requireCondition(
  gui.includes('runnerと入力を検査済み。solver実行preflightは未実施です。明示操作後にローカル計算できます。'),
  'local runner readiness message must keep solver execution preflight explicitly pending',
);
requireCondition(
  !/物理solver(?:へ)?接続済/.test(gui),
  'GUI must not claim that the physical solver is already connected',
);
requireCondition(
  html.includes('id="workspace" inert aria-hidden="true" aria-disabled="true"')
    && html.includes("workspace?.setAttribute('inert', '')")
    && html.includes("workspace?.setAttribute('aria-disabled', 'true')")
    && html.includes("control.dataset.staleVersionDisabled = 'true'")
    && html.includes("target.setAttribute('tabindex', '-1')")
    && html.includes("workspace?.addEventListener('click', blockUnverifiedWorkspaceEvent, true)")
    && html.includes("workspace?.addEventListener('submit', blockUnverifiedWorkspaceEvent, true)"),
  'unverified browser code must keep the workspace fail-closed before offering reload',
);
const moduleLoadListenerOffset = html.indexOf("moduleScript.addEventListener('load'");
const moduleErrorListenerOffset = html.indexOf("moduleScript.addEventListener('error'");
const moduleAppendOffset = html.indexOf('document.body.append(moduleScript)');
requireCondition(
  html.includes("moduleScript.src = './onga_stage20_gui.mjs'")
    && moduleLoadListenerOffset >= 0
    && moduleErrorListenerOffset >= 0
    && moduleLoadListenerOffset < moduleAppendOffset
    && moduleErrorListenerOffset < moduleAppendOffset
    && html.includes("activeBrowserContractVersion === expected")
    && html.includes("runtimeFreshness === 'current'")
    && !html.includes('window.setTimeout(() =>'),
  'browser contract guard must use module load/error events instead of a fixed timeout',
);
const contractActivationOffset = gui.indexOf('function activateBrowserContract()');
const contractCurrentOffset = gui.indexOf("elements.app.dataset.runtimeFreshness = 'current'", contractActivationOffset);
const workspaceUnlockOffset = gui.indexOf("elements.workspace.removeAttribute('inert')", contractActivationOffset);
const controlRestoreOffset = gui.indexOf('control.disabled = false', contractActivationOffset);
requireCondition(
  contractActivationOffset >= 0
    && controlRestoreOffset > contractActivationOffset
    && workspaceUnlockOffset > controlRestoreOffset
    && contractCurrentOffset > workspaceUnlockOffset,
  'browser contract must publish current only after every workspace restoration succeeds',
);
const bindEventsCallOffset = gui.lastIndexOf('bindEvents();');
const activateContractCallOffset = gui.lastIndexOf('activateBrowserContract();');
const loadApplicationCallOffset = gui.lastIndexOf('loadApplication();');
requireCondition(
  (gui.match(/activateBrowserContract\(\);/g) || []).length === 1
    && bindEventsCallOffset >= 0
    && bindEventsCallOffset < activateContractCallOffset
    && activateContractCallOffset < loadApplicationCallOffset,
  'browser contract activation must occur exactly once after event binding and before application loading',
);
requireCondition(
  css.includes('.workspace {\n  grid-row: 3;'),
  'workspace must remain in the flexible third grid row when the alert is hidden',
);
requireCondition(
  css.includes('.app-shell:not([data-runtime-freshness="current"]) .workspace')
    && css.includes('pointer-events: none'),
  'unverified browser code must also block pointer interaction when inert is unsupported',
);
requireCondition(
  gui.includes('if (elements.warningHud.dataset.sourceMode !== sourceMode)')
    && gui.includes('elements.warningHudText.textContent = localMode'),
  'source live-region text must change only when the source mode changes',
);
requireCondition(
  !gui.includes('warningHud.lastChild.textContent'),
  'source classification updates must target the dedicated live-region text node',
);

for (const marker of [
  '/api/stage20/local/capabilities',
  '/api/stage20/local/jobs',
  'localRunnerAvailable === true',
  'runtimeInputsVerified === true',
  'solverExecutionPreflightPassed === false',
  'physicalSolverConnected === false',
  'physicalCalibration === false',
  'fieldPrediction === false',
  'fishwayAlwaysEnabled === true',
  'fieldGateInputDrivesDisplayedFlow: true',
  'automaticGateEstimatorDrivesDisplayedFlow: true',
]) {
  requireCondition(
    localSimulation.includes(marker),
    'local physical-solver browser contract marker is missing: ' + marker,
  );
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

const localResultInputChangedFunction = extractFunctionDeclaration(gui, 'localResultInputChanged');
const localResultSandbox = {};
vm.runInNewContext(`
  const state = {
    localData: {},
    localResultCapacity: [1, 0, 0, 1, 0, 0, 0, 1],
  };
  let currentPattern = [100, 0, 0, 100, 0, 0, 0, 100];
  function effectiveGatePattern() { return currentPattern; }
  ${localResultInputChangedFunction}
  globalThis.localResultGate = {
    changed: localResultInputChanged,
    setCurrent(value) { currentPattern = value; },
    clearData() { state.localData = null; },
  };
`, localResultSandbox, { timeout: 1_000 });
requireCondition(
  localResultSandbox.localResultGate.changed() === false,
  'local calculation result must remain current when all eight gate values match',
);
localResultSandbox.localResultGate.setCurrent([100, 0, 100, 100, 0, 0, 0, 100]);
requireCondition(
  localResultSandbox.localResultGate.changed() === true,
  'local calculation result must become stale when any gate value changes',
);
localResultSandbox.localResultGate.setCurrent(null);
requireCondition(
  localResultSandbox.localResultGate.changed() === true,
  'local calculation result must fail closed when the current gate pattern is unavailable',
);
localResultSandbox.localResultGate.clearData();
requireCondition(
  localResultSandbox.localResultGate.changed() === false,
  'no local result must not be reported as stale',
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
  'mainGateModelOpeningWidthM',
  'reference_anchor_not_exact_geometric_center',
  '8593f67c5157ed1d55b717ba6ed691674694cfa499f7f7d533fc9950acdfc536',
  '09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659',
  '2d92e67d2ececf8e3c9e540003cd5546e3f6a38b234de7b5122aa4448c3478a3',
  '146429c21fecc13359710bb5335885258b63cd1f5750b6816f01098659135417',
]) {
  requireCondition(adapter.includes(marker), 'GUI data-contract marker is missing: ' + marker);
}

const gsiAttributionUrl = 'https://maps.gsi.go.jp/development/ichiran.html';
requireCondition(
  html.split(gsiAttributionUrl).length === 2,
  'GUI must include exactly one visible GSI attribution link',
);
const combined = html + '\n' + css + '\n' + gui + '\n' + adapter + '\n' + localSimulation;
const combinedWithoutApprovedAttribution = combined.replace(gsiAttributionUrl, '');
requireCondition(
  !/https?:\/\//i.test(combinedWithoutApprovedAttribution),
  'GUI must not reference remote HTTP assets beyond the approved GSI attribution link',
);
for (const forbidden of [
  'stage20_barrage_holdout_activation',
  'run_stage20_barrage_holdout_segment',
  'github/workflows',
  'cyberjapandata.gsi.go.jp',
]) {
  requireCondition(!combined.includes(forbidden), 'GUI unexpectedly references an execution or remote boundary: ' + forbidden);
}

console.log(JSON.stringify({
  schema: 'onga-stage20-hybrid-gui-validation-v3',
  status: 'passed_static_gui_contract',
  files: [
    'stage20-hybrid-gui.html',
    'stage20-hybrid-gui.css',
    'onga_stage20_gui.mjs',
    'onga_stage20_gui_data.mjs',
    'onga_stage20_local_simulation.mjs',
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
    gateInputDisplayOnly: false,
    gateInputDrivesLocalPhysicsAfterExplicitRun:
      gui.includes('createStage20LocalSimulationJob(capacity, durationS')
      && localSimulation.includes('fieldGateInputDrivesDisplayedFlow: true'),
    gateInputModes: ['auto', 'field'],
    gateOpeningOrder,
    gateStageCount: gatePatterns.length,
    gateStageValuesPercent: [0, 100],
    fieldOverrideMetadata: ['source', 'observedAt'],
    fieldAutoDelta: html.includes('id="gate-delta"'),
    fieldReturnToAuto: html.includes('id="gate-return-auto"'),
    standardPatternClassification: true,
    nonstandardPatternWarning: html.includes('標準順序外'),
    providedGateReferenceCoordinates:
      gui.includes('data.gateReferenceAnchors')
      && adapter.includes("kind === 'gate_reference_anchor'"),
    approvedPhotoVisibleGateEndpoints:
      adapter.includes('all_16_photo_visible_gate_endpoints_user_approved_coordinate_authority')
      && adapter.includes('gatePhotoVisibleEndpointApprovedCount'),
    photoVisibleGateEndpointsUsedAsPhysicalMesh: false,
    providedFishwayCoordinate: adapter.includes("kind === 'fishway_center'")
      && gui.includes('fishwayCenter: fishwayCoordinateCenter'),
    publishedEqualGateWidthM: publishedGateFacts.publishedMainGateWidthM,
    fishwayExcludedFromGateDisplay: !gui.includes('mesh.arrays.barrage_face_ids') && gui.includes("marks: Object.freeze(['barrage', 'fishway'])"),
    mobileBreakpoint: true,
  },
  safeguards: {
    syntheticFixtureOnly: false,
    localUncalibratedPhysicsAvailable: true,
    remoteTilesUsed: false,
    publicSimulatorConnected: false,
    physicalRunnerReferenced: true,
    physicalCalibrationClaimed: false,
    fieldPredictionClaimed: false,
    productionPrecomputationConnected: false,
    gateInputSentToDataAdapter: false,
    gateInputSentToHybridWorker: false,
  },
}, null, 2));
