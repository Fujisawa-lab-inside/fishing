import fs from 'node:fs';

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const html = fs.readFileSync('stage20-hybrid-gui.html', 'utf8');
const css = fs.readFileSync('stage20-hybrid-gui.css', 'utf8');
const gui = fs.readFileSync('onga_stage20_gui.mjs', 'utf8');
const adapter = fs.readFileSync('onga_stage20_gui_data.mjs', 'utf8');
const viewCount = (html.match(/data-view="/g) || []).length;
const layerCount = (html.match(/data-layer="/g) || []).length;
const gateCount = (html.match(/data-gate="/g) || []).length;
const sliderTag = html.match(/<input[^>]+id="time-slider"[^>]*>/)?.[0] || '';

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
  'const gateIndex = 8 - barrageGateIds[barrageIndex]',
  'selectCellAtCanvasPoint(',
  'togglePlayback(',
]) {
  requireCondition(gui.includes(marker), 'GUI implementation marker is missing: ' + marker);
}
for (const marker of [
  'mesh-v2.json',
  'response-pack-synthetic-v2.json',
  'hybrid-synthetic-input-v1.json',
  'includeOutput: true',
  'const snapshot = index =>',
  'synthetic_browser_benchmark_only',
  'barrage_gate_id',
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
  schema: 'onga-stage20-hybrid-gui-validation-v1',
  status: 'passed_static_gui_contract',
  files: [
    'stage20-hybrid-gui.html',
    'stage20-hybrid-gui.css',
    'onga_stage20_gui.mjs',
    'onga_stage20_gui_data.mjs',
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
    legacyWestToEastGateOrder: gui.includes('const gateIndex = 8 - barrageGateIds[barrageIndex]'),
    mobileBreakpoint: true,
  },
  safeguards: {
    syntheticFixtureOnly: true,
    remoteTilesUsed: false,
    publicSimulatorConnected: false,
    physicalRunnerReferenced: false,
  },
}, null, 2));
