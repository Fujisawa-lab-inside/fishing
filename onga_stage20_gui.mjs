import {
  fetchStage20ContractRecoveryArtifact,
  loadStage20GuiData,
  validateStage20FieldGateObservationBatch,
} from './onga_stage20_gui_data.mjs';
import { loadStage20R1CDiagnosticReplay } from './onga_stage20_R1C_diagnostic_replay.mjs';
import {
  createStage20LocalSimulationJob,
  fetchStage20LocalSimulationJob,
  loadStage20LocalSimulationResult,
  probeStage20LocalSimulator,
} from './onga_stage20_local_simulation.mjs';
import {
  buildStage20IntegratedForcing,
  probeStage20ForcingIntegration,
} from './onga_stage20_forcing_integration.mjs';

const BROWSER_CONTRACT_VERSION = 'm0.2-ui-20260826-01';
const TILE_SIZE = 256;
const CIRCUMFERENCE_M = 40075016.68557849;
const PRESENT_INDEX = 12;
const SPEED_PALETTE = Object.freeze([
  [27, 107, 174],
  [37, 167, 184],
  [246, 188, 65],
  [218, 69, 55],
]);
const DEPTH_PALETTE = Object.freeze([
  [197, 245, 246],
  [85, 185, 209],
  [36, 111, 174],
  [9, 43, 98],
]);
const VIEW_SPECS = Object.freeze({
  estuary: Object.freeze({
    id: 'estuary',
    label: '河口全域',
    zoom: 16,
    tileBox: Object.freeze([56553, 26201, 56558, 26204]),
    cropSize: null,
    centerKind: null,
    marks: Object.freeze(['barrage', 'confluence']),
  }),
  barrage: Object.freeze({
    id: 'barrage',
    label: '河口堰',
    zoom: 18,
    tileBox: Object.freeze([226224, 104808, 226231, 104816]),
    cropSize: Object.freeze([1100, 580]),
    centerKind: 'barrage',
    marks: Object.freeze(['barrage', 'fishway']),
  }),
  confluence: Object.freeze({
    id: 'confluence',
    label: '曲川・遠賀川合流部',
    zoom: 18,
    tileBox: Object.freeze([226224, 104808, 226231, 104816]),
    cropSize: Object.freeze([1180, 625]),
    centerKind: 'confluence',
    marks: Object.freeze(['confluence']),
  }),
  fishway: Object.freeze({
    id: 'fishway',
    label: '魚道',
    zoom: 18,
    tileBox: Object.freeze([226224, 104808, 226231, 104816]),
    cropSize: Object.freeze([1040, 550]),
    centerKind: 'fishway',
    marks: Object.freeze(['fishway', 'barrage']),
  }),
});
const GATE_OPENING_ORDER = Object.freeze([5, 4, 6, 3, 7, 2, 8, 1]);

function gatePatternForStage(stage) {
  const normalizedStage = Math.max(0, Math.min(8, Math.round(Number(stage) || 0)));
  const openingGates = new Set(GATE_OPENING_ORDER.slice(0, normalizedStage));
  return Array.from({ length: 8 }, (_, index) => openingGates.has(index + 1) ? 100 : 0);
}

function classifyGatePattern(levels) {
  if (!levels || levels.length !== 8) return null;
  const normalized = Array.from(levels, level => Number(level));
  if (normalized.some(level => level !== 0 && level !== 100)) return null;
  for (let stage = 0; stage <= 8; stage += 1) {
    const candidate = gatePatternForStage(stage);
    if (candidate.every((level, index) => level === normalized[index])) return stage;
  }
  return null;
}

const GATE_PRESETS = Object.freeze({
  closed: Object.freeze(gatePatternForStage(0)),
  stage2: Object.freeze(gatePatternForStage(2)),
  stage4: Object.freeze(gatePatternForStage(4)),
  stage6: Object.freeze(gatePatternForStage(6)),
  all: Object.freeze(gatePatternForStage(8)),
});

const byId = id => document.getElementById(id);
const elements = Object.freeze({
  app: byId('app-shell'),
  runtimeVersionAlert: byId('runtime-version-alert'),
  workspace: byId('workspace'),
  controlPanel: byId('control-panel'),
  mapSection: byId('map-section'),
  canvas: byId('flow-map'),
  frame: byId('map-frame'),
  loadStatus: byId('load-status'),
  sourceBadge: byId('source-badge'),
  integrationStatusBadge: byId('integration-status-badge'),
  overlayTitle: byId('overlay-title'),
  overlayMessage: byId('overlay-message'),
  retry: byId('retry-button'),
  sideTime: byId('side-time'),
  frameCount: byId('frame-count'),
  dataModeSynthetic: byId('data-mode-synthetic'),
  dataModeR1C: byId('data-mode-r1c'),
  dataModeReferenceV2: byId('data-mode-reference-v2'),
  dataModeN4P8d: byId('data-mode-n4p8d'),
  dataModeLocal: byId('data-mode-local'),
  dataModeStatus: byId('data-mode-status'),
  dataModeNote: byId('data-mode-note'),
  forcingCard: byId('forcing-input-card'),
  forcingBadge: byId('forcing-badge'),
  forcingDate: byId('forcing-date'),
  forcingDateHelp: byId('forcing-date-help'),
  forcingJmaCsv: byId('forcing-jma-csv'),
  forcingBuildButton: byId('forcing-build-button'),
  forcingReprobeButton: byId('forcing-reprobe-button'),
  forcingStatus: byId('forcing-status'),
  forcingValues: byId('forcing-values'),
  forcingCurrentTime: byId('forcing-current-time'),
  forcingOnga: byId('forcing-onga'),
  forcingNishi: byId('forcing-nishi'),
  forcingMagari: byId('forcing-magari'),
  forcingTide: byId('forcing-tide'),
  forcingGates: byId('forcing-gates'),
  forcingSource: byId('forcing-source'),
  forcingConnectionNote: byId('forcing-connection-note'),
  metricTideLabel: byId('metric-tide-label'),
  metricTide: byId('metric-tide'),
  metricBarrageLabel: byId('metric-barrage-label'),
  metricBarrage: byId('metric-barrage'),
  metricOngaLabel: byId('metric-onga-label'),
  metricOnga: byId('metric-onga'),
  metricSpeedLabel: byId('metric-speed-label'),
  metricSpeed: byId('metric-speed'),
  R1CReplayCard: byId('r1c-replay-card'),
  R1CReplayTitle: byId('r1c-replay-title'),
  R1CWarningBadge: byId('r1c-warning-badge'),
  R1CContractTitle: byId('r1c-contract-title'),
  R1CContractNote: byId('r1c-contract-note'),
  R1CGateResultLabel: byId('r1c-gate-result-label'),
  R1CCurrentTime: byId('r1c-current-time'),
  R1CUpstreamHead: byId('r1c-upstream-head'),
  R1CDownstreamHead: byId('r1c-downstream-head'),
  R1CHeadDifference: byId('r1c-head-difference'),
  R1CFishwayFlow: byId('r1c-fishway-flow'),
  R1CFishwayDepth: byId('r1c-fishway-depth'),
  R1CGateFlux: byId('r1c-gate-flux'),
  R1CStoredVolume: byId('r1c-stored-volume'),
  R1CSavedGates: byId('r1c-saved-gates'),
  R1CGateDifference: byId('r1c-gate-difference'),
  gateSummaryBadge: byId('gate-summary-badge'),
  gateModeAuto: byId('gate-mode-auto'),
  gateModeField: byId('gate-mode-field'),
  gateAutoStage: byId('gate-auto-stage'),
  gateDelta: byId('gate-delta'),
  gateStandardStatus: byId('gate-standard-status'),
  gateFieldInputs: byId('gate-field-inputs'),
  gateSource: byId('gate-source'),
  gateObservedAt: byId('gate-observed-at'),
  gateObservationImportFile: byId('gate-observation-import-file'),
  gateObservationImportButton: byId('gate-observation-import-button'),
  gateObservationExportButton: byId('gate-observation-export-button'),
  gateObservationIoStatus: byId('gate-observation-io-status'),
  gateReturnAuto: byId('gate-return-auto'),
  gateDetail: byId('gate-detail'),
  gateMapButton: byId('gate-map-button'),
  localSimulatorCard: byId('local-simulator-card'),
  localSimulatorBadge: byId('local-simulator-badge'),
  localSimulationDuration: byId('local-simulation-duration'),
  localSimulationRun: byId('local-simulation-run'),
  localReprobeButton: byId('local-reprobe-button'),
  localSimulationGates: byId('local-simulation-gates'),
  localSimulationStatus: byId('local-simulation-status'),
  gateReferenceStatus: byId('gate-reference-status'),
  gateIntegrationTitle: byId('gate-integration-title'),
  gateIntegrationNote: byId('gate-integration-note'),
  gateAnchorStatus: byId('gate-anchor-status'),
  gatePhotoEndpointStatus: byId('gate-photo-endpoint-status'),
  gatePhysicalStatus: byId('gate-physical-status'),
  gateWidthStatus: byId('gate-width-status'),
  fishwayIntegrationNote: byId('fishway-integration-note'),
  syntheticPairStatus: byId('synthetic-pair-status'),
  r20CompatibilityStatus: byId('r20-compatibility-status'),
  readinessCard: byId('precompute-readiness-card'),
  readinessValidationBadge: byId('readiness-validation-badge'),
  readinessBoundaryStatus: byId('readiness-boundary-status'),
  readinessBoundaryNote: byId('readiness-boundary-note'),
  readinessR20Status: byId('readiness-r20-status'),
  readinessGateBasisStatus: byId('readiness-gate-basis-status'),
  readinessFiftyStatus: byId('readiness-fifty-status'),
  readinessCheckpointStatus: byId('readiness-checkpoint-status'),
  readinessFormalCost: byId('readiness-formal-cost'),
  readinessMultizoneCost: byId('readiness-multizone-cost'),
  readinessProvenanceStatus: byId('readiness-provenance-status'),
  readinessPackageStatus: byId('readiness-package-status'),
  contractRecoveryCard: byId('contract-recovery-card'),
  contractRecoveryValidationBadge: byId('contract-recovery-validation-badge'),
  contractAuditStatus: byId('contract-audit-status'),
  contractAuditCounts: byId('contract-audit-counts'),
  contractAuditErrorCount: byId('contract-audit-error-count'),
  contractAuditWarningCount: byId('contract-audit-warning-count'),
  contractWarningExternal: byId('contract-warning-external'),
  contractWarningMissing: byId('contract-warning-missing'),
  contractWarningDigest: byId('contract-warning-digest'),
  contractWarningFormat: byId('contract-warning-format'),
  recoveryBundleStatus: byId('recovery-bundle-status'),
  recoveryBundleCount: byId('recovery-bundle-count'),
  physicalValidationStatus: byId('physical-validation-status'),
  physicalValidationNext: byId('physical-validation-next'),
  contractReportDownloadButton: byId('contract-report-download-button'),
  recoveryBundleDownloadButton: byId('recovery-bundle-download-button'),
  physicalValidationPlanDownloadButton: byId('physical-validation-plan-download-button'),
  contractRecoveryDownloadStatus: byId('contract-recovery-download-status'),
  mapGateLabel: byId('map-gate-label'),
  layerMaximumSpeed: byId('layer-maximum-speed'),
  arrowToggle: byId('arrow-toggle'),
  arrowNote: byId('arrow-note'),
  markerToggle: byId('marker-toggle'),
  selectedCellId: byId('selected-cell-id'),
  emptySelection: byId('empty-selection'),
  selectedValues: byId('selected-values'),
  selectedSpeed: byId('selected-speed'),
  selectedDepth: byId('selected-depth'),
  selectedDirection: byId('selected-direction'),
  detailPack: byId('detail-pack'),
  detailTiming: byId('detail-timing'),
  detailIntegration: byId('detail-integration'),
  detailBindings: byId('detail-bindings'),
  detailMesh: byId('detail-mesh'),
  detailTime: byId('detail-time'),
  mapViewLabel: byId('map-view-label'),
  mapTimeLabel: byId('map-time-label'),
  legendTitle: byId('legend-title'),
  legendMax: byId('legend-max'),
  legendMin: byId('legend-min'),
  legendGradient: byId('legend-gradient'),
  legendNote: byId('legend-note'),
  warningHud: byId('warning-hud'),
  warningHudText: byId('warning-hud-text'),
  localCalculationBanner: byId('local-calculation-banner'),
  localCalculationTitle: byId('local-calculation-title'),
  localCalculationNote: byId('local-calculation-note'),
  localCalculationJump: byId('local-calculation-jump'),
  previous: byId('previous-button'),
  play: byId('play-button'),
  playLabel: byId('play-label'),
  next: byId('next-button'),
  now: byId('now-button'),
  slider: byId('time-slider'),
  timelineCurrent: byId('timeline-current'),
  timelineStart: byId('timeline-start'),
  timelineEnd: byId('timeline-end'),
  timelineTicks: Object.freeze(Array.from(
    { length: 7 },
    (_, index) => byId('timeline-tick-' + index),
  )),
});

if (elements.app?.dataset?.browserContractVersion !== BROWSER_CONTRACT_VERSION) {
  throw new Error('browser HTML and JavaScript contract versions differ');
}

function activateBrowserContract() {
  for (const control of elements.workspace.querySelectorAll('[data-stale-version-disabled="true"]')) {
    control.disabled = false;
    delete control.dataset.staleVersionDisabled;
  }
  for (const target of elements.workspace.querySelectorAll('[data-stale-version-tabindex]')) {
    const previous = target.dataset.staleVersionTabindex;
    if (previous === '') target.removeAttribute('tabindex');
    else target.setAttribute('tabindex', previous);
    delete target.dataset.staleVersionTabindex;
  }
  elements.workspace.removeAttribute('inert');
  elements.workspace.removeAttribute('aria-hidden');
  elements.workspace.removeAttribute('aria-disabled');
  elements.runtimeVersionAlert.hidden = true;
  elements.app.dataset.activeBrowserContractVersion = BROWSER_CONTRACT_VERSION;
  elements.app.dataset.runtimeFreshness = 'current';
}

const context = elements.canvas.getContext('2d', { alpha: false });
const mobileLayout = window.matchMedia('(max-width: 760px)');
const staticReviewMode =
  elements.app?.dataset?.releaseMode === 'static-review';
const GUI_MODE_CAPABILITY_IDS = Object.freeze({
  synthetic: 'synthetic',
  r1c: 'r1c_saved_replay',
  'reference-v2': 'r1c_saved_replay',
  n4p8d: 'r1c_saved_replay',
  local: 'local_r1c_experiment',
});
const state = {
  phase: 'loading',
  dataMode: 'synthetic',
  data: null,
  geometry: null,
  runtimeCapabilities: null,
  syntheticData: null,
  syntheticGeometry: null,
  R1CData: null,
  R1CGeometry: null,
  R1CLoadController: null,
  R1CLoadState: 'idle',
  R1CLoadMessage: '選択すると約75MiBの検証済みデータを読み込みます。',
  referenceV2Data: null,
  referenceV2Geometry: null,
  referenceV2LoadController: null,
  referenceV2LoadState: 'idle',
  referenceV2LoadMessage: '選択すると約17MiBの固定S4基準リプレイを検証して読み込みます。',
  N4P8dData: null,
  N4P8dGeometry: null,
  N4P8dLoadController: null,
  N4P8dLoadState: 'idle',
  N4P8dLoadMessage: '選択すると約17MiBの承認済み36時間リプレイを検証して読み込みます。',
  localCapabilities: null,
  localServiceState: 'checking',
  localServiceMessage: 'ローカル計算サービスを確認しています。',
  localJob: null,
  localRequestedCapacity: null,
  localResultCapacity: null,
  localData: null,
  localGeometry: null,
  localController: null,
  forcingCapabilities: null,
  forcingServiceState: 'checking',
  forcingServiceMessage: 'ローカル入力サービスを確認しています。',
  forcingData: null,
  forcingController: null,
  snapshotIndex: PRESENT_INDEX,
  viewId: 'estuary',
  layer: 'speed',
  arrows: true,
  markers: true,
  selectedCell: null,
  gateInputMode: 'auto',
  gateObservation: null,
  gateObservationSource: '現地目視',
  gateObservedAt: '',
  gateObservationIoState: 'loading',
  gateObservationIoMessage: '観測schemaを検証中です。',
  contractRecoveryDownloadState: 'loading',
  contractRecoveryDownloadMessage: 'sidecar manifestを検証中です。',
  playing: false,
  playTimer: null,
  loadController: null,
  snapshotMaximumSpeeds: null,
  tileCache: new Map(),
  renderQueued: false,
  lastRender: null,
};

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function formatHour(hour, compact = false) {
  if (hour === 0) return compact ? '0時間' : '現在相当・0時間';
  if (hour < 0) return compact ? '−' + Math.abs(hour) + '時間' : Math.abs(hour) + '時間前';
  return compact ? '+' + hour + '時間' : hour + '時間後';
}

function isLocalPhysicsMode() {
  return state.dataMode === 'local'
    && state.data?.metadata?.dataMode === 'r1c_local_physics';
}

function runtimeCapabilityForGuiMode(mode = state.dataMode) {
  const capabilityId = GUI_MODE_CAPABILITY_IDS[mode];
  return state.runtimeCapabilities?.modesById?.[capabilityId] || null;
}

function isR1CSavedReplayMode() {
  return state.dataMode === 'r1c'
    && state.data?.metadata?.dataMode === 'r1c_diagnostic_replay';
}

function isReferenceV2Mode() {
  return state.dataMode === 'reference-v2'
    && state.data?.metadata?.dataMode === 'reference_v2_fixed_S4_replay';
}

function isN4P8dMode() {
  return state.dataMode === 'n4p8d'
    && state.data?.metadata?.dataMode === 'n4p8d_36h_replay';
}

function isMaximumSpeedLayer() {
  return state.layer === 'maximum-speed' && isN4P8dMode();
}

function layerLabelJa() {
  if (isMaximumSpeedLayer()) return '36時間最大流速';
  return state.layer === 'depth' ? '水深' : '流速';
}

function isR1CMode() {
  return isR1CSavedReplayMode()
    || isReferenceV2Mode()
    || isN4P8dMode()
    || isLocalPhysicsMode();
}

function homeSnapshotIndex() {
  return isR1CMode() ? 0 : PRESENT_INDEX;
}

function formatReplayTime(absoluteTimeS, compact = false) {
  const totalSeconds = Math.round(Number(absoluteTimeS));
  if (!Number.isFinite(totalSeconds)) return '—';
  if (totalSeconds < 60) {
    return compact ? totalSeconds + '秒' : '開始から' + totalSeconds + '秒';
  }
  const totalMinutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  if (compact) {
    return remainingSeconds === 0
      ? totalMinutes + '分'
      : totalMinutes + '分' + remainingSeconds + '秒';
  }
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return '開始から' + (hours > 0 ? hours + '時間' : '') + minutes + '分'
    + (remainingSeconds > 0 ? remainingSeconds + '秒' : '');
}

function formatReferenceTimestamp(timestampJst, compact = false) {
  if (typeof timestampJst !== 'string' || !timestampJst.includes('T')) return '時刻なし';
  const normalized = timestampJst.replace('T', ' ').replace('+09:00', ' JST');
  return compact ? normalized.slice(5, 16) : normalized;
}

function formatDisplayTime(snapshot, compact = false) {
  return isReferenceV2Mode() || isN4P8dMode()
    ? formatReferenceTimestamp(snapshot.timestampJst, compact)
    : isR1CMode()
    ? formatReplayTime(snapshot.absoluteTimeS, compact)
    : formatHour(snapshot.hour, compact);
}

function replayGateCapacities() {
  return isR1CMode()
    ? state.data.replay.gateCapacities(state.snapshotIndex)
    : null;
}

function formatNumber(value, digits, suffix = '') {
  return Number.isFinite(value) ? value.toFixed(digits) + suffix : '—';
}

function formatBytes(value) {
  if (!Number.isFinite(value) || value < 0) return '—';
  if (value < 1024) return value.toLocaleString('ja-JP') + ' B';
  if (value < 1024 * 1024) return (value / 1024).toFixed(1) + ' KB';
  return (value / (1024 * 1024)).toFixed(2) + ' MB';
}

function forcingSnapshotIndex() {
  if (!state.forcingData) return PRESENT_INDEX;
  if (!isLocalPhysicsMode() && state.data?.metadata?.snapshotCount === 37) {
    return clamp(state.snapshotIndex, 0, 36);
  }
  return PRESENT_INDEX;
}

function forcingAutomaticStage() {
  if (!state.forcingData) return null;
  return state.forcingData.automaticGateOperation.stages[forcingSnapshotIndex()];
}

function forcingSourceLabel() {
  if (!state.forcingData) return '入力未作成';
  const tide = state.forcingData.sourceArtifacts?.tide;
  const tideLabel = tide?.status === 'official_prediction_transformed'
    ? '保存済み気象庁天文潮位表'
    : '指定日を表さない保存済み代表潮位';
  return '降水量：気象庁CSV／潮位：' + tideLabel
    + '／流量：未較正一次貯留モデル';
}

function forcingDateIsAvailable(value = elements.forcingDate.value) {
  const ranges = state.forcingCapabilities?.availableRequestedDateRanges;
  return Array.isArray(ranges) && ranges.some(
    range => range.start <= value && value <= range.end,
  );
}

function forcingDateRangeLabel(ranges) {
  return ranges.map(range => `${range.start}〜${range.end}`).join('、');
}

function applyForcingDateCapability(capability) {
  const ranges = capability.availableRequestedDateRanges;
  elements.forcingDate.min = ranges[0].start;
  elements.forcingDate.max = ranges.at(-1).end;
  if (!ranges.some(
    range => range.start <= elements.forcingDate.value
      && elements.forcingDate.value <= range.end,
  )) {
    elements.forcingDate.value = capability.defaultRequestedDate;
  }
  elements.forcingDateHelp.textContent =
    `現在の保存済み潮位表で作成できる日付は、${forcingDateRangeLabel(ranges)}です。`;
}

function syncForcingInterface() {
  const serviceReady = state.forcingServiceState === 'ready'
    || state.forcingServiceState === 'pass';
  const running = state.forcingServiceState === 'running';
  const hasCsv = Boolean(elements.forcingJmaCsv.files?.[0]);
  const hasAvailableDate = forcingDateIsAvailable();
  elements.forcingCard.dataset.integrationStatus = state.forcingServiceState;
  elements.forcingBuildButton.disabled =
    !serviceReady || running || !hasCsv || !hasAvailableDate;
  elements.forcingReprobeButton.hidden =
    staticReviewMode || !['unavailable', 'error'].includes(state.forcingServiceState);
  elements.forcingStatus.textContent = state.forcingServiceMessage;
  elements.forcingBadge.textContent =
    state.forcingServiceState === 'checking' ? '接続確認中'
      : state.forcingServiceState === 'running' ? '入力作成中'
        : state.forcingServiceState === 'pass' ? '37時間統合済み'
          : state.forcingServiceState === 'ready' ? '入力可能'
            : state.forcingServiceState === 'unavailable' ? '接続エラー'
              : state.forcingServiceState === 'error' ? '安全停止'
                : '待機中';
  elements.forcingValues.hidden = !state.forcingData;
  if (!state.forcingData) {
    elements.forcingSource.textContent =
      '入力未作成。気象庁CSVと保存済み潮位表は、このPC内のローカル処理だけに使用します。';
    return;
  }
  const index = forcingSnapshotIndex();
  const forcing = state.forcingData;
  const stage = forcing.automaticGateOperation.stages[index];
  const pattern = forcing.automaticGateOperation.capacityFractionByGateId[index];
  const open = pattern.flatMap((value, gateIndex) => value ? [gateIndex + 1] : []);
  elements.forcingCurrentTime.textContent = forcing.timestampsJst[index]
    .replace('T', ' ')
    .replace('+09:00', ' JST');
  elements.forcingOnga.textContent =
    formatNumber(forcing.series.ongaDischargeM3S[index], 1, ' m³/s');
  elements.forcingNishi.textContent =
    formatNumber(forcing.series.nishiDischargeM3S[index], 1, ' m³/s');
  elements.forcingMagari.textContent =
    formatNumber(forcing.series.magariDischargeM3S[index], 1, ' m³/s');
  elements.forcingTide.textContent =
    formatNumber(forcing.series.tideRelativeM[index], 2, ' m');
  elements.forcingGates.textContent = open.length === 0
    ? '段階' + stage + '・全閉'
    : '段階' + stage + '・' + open.join('・') + '番開';
  elements.forcingSource.textContent = forcingSourceLabel();
}

async function probeForcingIntegrationService() {
  state.forcingController?.abort();
  const controller = new AbortController();
  state.forcingController = controller;
  state.forcingServiceState = 'checking';
  state.forcingServiceMessage = 'ローカル入力サービスを確認しています。';
  syncForcingInterface();
  try {
    state.forcingCapabilities = await probeStage20ForcingIntegration({
      signal: controller.signal,
    });
    applyForcingDateCapability(state.forcingCapabilities);
    state.forcingServiceState = 'ready';
    state.forcingServiceMessage =
      `利用可能な日付（${forcingDateRangeLabel(state.forcingCapabilities.availableRequestedDateRanges)}）と気象庁CSVを選ぶと、37時間に統合できます。`;
  } catch (error) {
    if (error?.name === 'AbortError') return;
    console.error('[stage20-forcing-integration] capability probe failed', error);
    state.forcingCapabilities = null;
    state.forcingServiceState = 'unavailable';
    state.forcingServiceMessage =
      '専用serviceに接続できません。tools/serve_stage20_local_simulator_v1.pyから開いた後、'
      + '「ローカル入力サービスを再確認」を押してください。詳細：'
      + (error?.message || String(error));
  } finally {
    if (state.forcingController === controller) state.forcingController = null;
    syncForcingInterface();
  }
}

function invalidateForcingInput(message) {
  state.forcingData = null;
  if (state.forcingCapabilities) state.forcingServiceState = 'ready';
  state.forcingServiceMessage = message;
  syncForcingInterface();
  if (state.data) {
    syncGateInterface();
    scheduleRender();
  }
}

async function buildIntegratedForcingInput() {
  if (!state.forcingCapabilities || state.forcingServiceState === 'running') return;
  const csvFile = elements.forcingJmaCsv.files?.[0];
  if (!csvFile) return;
  state.forcingController?.abort();
  const controller = new AbortController();
  state.forcingController = controller;
  state.forcingServiceState = 'running';
  state.forcingServiceMessage =
    '気象庁CSVの品質と時刻を確認し、保存済み潮位表を読み込んでいます。';
  syncForcingInterface();
  try {
    const forcing = await buildStage20IntegratedForcing(
      {
        requestedDate: elements.forcingDate.value,
        csvFile,
        tideFailurePolicy: 'fail_closed',
      },
      { signal: controller.signal },
    );
    state.forcingData = forcing;
    state.forcingServiceState = 'pass';
    state.forcingServiceMessage =
      '37時間の統合が完了しました。自動開門段階を水門入力へ接続しました。';
    syncInterface();
    scheduleRender();
  } catch (error) {
    if (error?.name === 'AbortError') return;
    console.error(error);
    state.forcingData = null;
    state.forcingServiceState = 'error';
    state.forcingServiceMessage =
      '入力を安全停止しました：' + (error?.message || String(error));
    syncForcingInterface();
    syncGateInterface();
  } finally {
    if (state.forcingController === controller) state.forcingController = null;
  }
}

function automaticGateStage() {
  if (!state.data) return null;
  const integratedStage = forcingAutomaticStage();
  if (integratedStage !== null) return integratedStage;
  const fraction = state.data.inputs.barrageOpeningFraction[state.snapshotIndex];
  return clamp(Math.round(clamp(fraction, 0, 1) * 8), 0, 8);
}

function automaticGatePattern() {
  const stage = automaticGateStage();
  return stage === null ? null : gatePatternForStage(stage);
}

function effectiveGatePattern() {
  if (state.gateInputMode === 'field' && state.gateObservation) return state.gateObservation;
  return automaticGatePattern();
}

function openGateNumbers(levels = effectiveGatePattern()) {
  if (!levels) return [];
  return Array.from(levels).flatMap((level, index) => Number(level) > 0 ? [index + 1] : []);
}

function gatePatternLabel(levels, compact = false) {
  if (!levels) return '推定待ち';
  const open = openGateNumbers(levels);
  if (open.length === 0) return compact ? '全閉' : '全閉・0/8門';
  if (open.length === 8) return compact ? '全開' : '全開・8/8門';
  return compact ? open.join('・') + '番開' : open.length + '/8門開';
}

function gateObservationLabel(compact = false) {
  const automaticStage = automaticGateStage();
  if (state.gateInputMode === 'auto') {
    return automaticStage === null ? '自動推定待ち' : compact ? '自動・段階' + automaticStage : '自動推定・段階' + automaticStage + '/8';
  }
  const stage = classifyGatePattern(state.gateObservation);
  return stage === null ? '現地・標準順序外' : compact ? '現地・段階' + stage : '現地入力・段階' + stage + '/8';
}

function tokyoDateTimeParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Tokyo',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  return Object.fromEntries(parts.map(part => [part.type, part.value]));
}

function localDateTimeValue(date = new Date()) {
  const parts = tokyoDateTimeParts(date);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function observedAtLabel(value) {
  if (!value) return '時刻未入力';
  return value.replace('T', ' ');
}

function tokyoOffsetTimestamp(value) {
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2}))?$/.exec(value || '');
  if (!match) throw new Error('観測時刻を入力してください。');
  const timestamp = `${match[1]}:${match[2] || '00'}+09:00`;
  if (!Number.isFinite(Date.parse(timestamp))) throw new Error('観測時刻が正しくありません。');
  return timestamp;
}

function timestampToTokyoLocalValue(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) throw new Error('観測JSONの時刻が正しくありません。');
  return localDateTimeValue(date);
}

function gateSourceForSchema(value) {
  if (value === '現地目視') return 'field_visual';
  if (value === '現地連絡' || value === '点検記録') return 'operator_record';
  if (value === 'インポートJSON') return 'imported_file';
  return 'manual_test';
}

function gateSourceFromSchema(value) {
  if (value === 'field_visual') return '現地目視';
  if (value === 'operator_record') return '点検記録';
  return 'インポートJSON';
}

function canonicalJsonValue(value) {
  if (Array.isArray(value)) return value.map(canonicalJsonValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).sort().map(key => [key, canonicalJsonValue(value[key])]),
    );
  }
  return value;
}

function canonicalJsonText(value) {
  return JSON.stringify(canonicalJsonValue(value)) + '\n';
}

function formatRunnerHoursRange(forecast) {
  return forecast.runnerHoursLow.toFixed(1) + '–' + forecast.runnerHoursHigh.toFixed(1)
    + ' runner-h / ' + (forecast.planningBytesAt1_3x / 1e9).toFixed(3) + ' GB';
}

function differingGateNumbers(first, second) {
  if (!first || !second) return [];
  return Array.from({ length: 8 }, (_, index) => index + 1)
    .filter(gateNumber => Number(first[gateNumber - 1]) !== Number(second[gateNumber - 1]));
}

function syncMapAriaLabel() {
  if (!state.data) return;
  const snapshot = state.data.snapshot(state.snapshotIndex);
  const view = VIEW_SPECS[state.viewId];
  if (isR1CMode()) {
    const local = isLocalPhysicsMode();
    const referenceV2 = isReferenceV2Mode();
    const N4P8d = isN4P8dMode();
    elements.canvas.setAttribute(
      'aria-label',
      view.label + 'の' + layerLabelJa() + '地図、'
        + formatDisplayTime(snapshot)
        + (local
          ? '。GUI入力を反映したR1Cローカル未較正物理計算であり、現地較正済みの流量予測ではありません。'
          : N4P8d
            ? '。数値検査とヒートマップ目視を通過した保存済み36時間計算です。未較正・ゼロ降雨条件で、予測ではありません。'
              + (isMaximumSpeedLayer()
                ? '全37時点の各セル最大流速を表示し、赤紫と白枠は中心が承認済み水域外の19セルです。'
                : '')
          : referenceV2
            ? '。連続潮位を使用した固定S4の保存済み基準リプレイです。未較正・モデル参考値であり、予測ではありません。'
            : '。R1C未較正診断リプレイであり、現地流量の絶対再現や物理予測ではありません。')
        + '水門1〜8の能力倍率は実扉高ではありません。'
        + (local
          ? '表示中の流れ図には計算開始時の8門入力が反映されています。入力変更後は再計算が必要です。'
          : '現地入力と自動推定は比較表示だけで流れ図を変更しません。')
        + '青線は承認済み写真可視端点、白線はR1Cメッシュの水面陸地境界です。'
        + '魚道は常時有効・操作不可で、全主水門閉でも上流と下流を接続します。Enterキーで中央地点を選択できます。',
    );
    return;
  }
  elements.canvas.setAttribute(
    'aria-label',
    view.label + 'の' + layerLabelJa() + '地図、' + formatHour(snapshot.hour)
      + '。合成データで物理予測ではありません。開門入力は' + gateObservationLabel(true)
      + 'ですがStage 20物理solver・応答packへ未接続で、流れの図には未反映です。A1〜A8は水門番号の参照アンカーで、厳密な幾何中心ではありません。写真可視端点16点は承認済みのレビュー表示で、物理メッシュには未採用です。46.5mはH2モデル開口幅の静的契約であり、地理的な実位置線としては描画しません。魚道は主水門1〜8とは別の常時有効・操作不可の接続で、全主水門閉でも上流と下流を接続します。Enterキーで中央地点を選択できます。',
  );
}

function syncIntegrationInterface() {
  if (!state.data) return;
  const metadata = state.data.metadata;
  elements.integrationStatusBadge.textContent = '統合状態：検証済';
  elements.integrationStatusBadge.setAttribute(
    'aria-label',
    'GUI統合状態manifestをSHA-256で検証し、read-onlyで接続済み',
  );
  elements.gateIntegrationTitle.textContent = '状態manifest接続済';
  elements.gateIntegrationNote.textContent = '写真上の位置と承認済みR1C計算面を分離';
  elements.gateAnchorStatus.textContent = metadata.gateReferenceAnchorApprovedCount + '/8 承認';
  elements.gatePhotoEndpointStatus.textContent = metadata.gatePhotoVisibleEndpointApprovedCount + '/16 承認';
  elements.gatePhysicalStatus.textContent = metadata.mainGatePhysicalMeshSelected ? '採用済' : '未採用';
  elements.gateWidthStatus.textContent = metadata.mainGateModelOpeningWidthM + 'm・静的契約のみ';
  elements.gateReferenceStatus.dataset.photoVisibleEndpointsApproved =
    String(metadata.gatePhotoVisibleEndpointApprovedCount);
  elements.gateReferenceStatus.dataset.photoVisibleEndpointsRequired = '16';
  elements.gateReferenceStatus.dataset.physicalMeshUseAuthorized =
    String(metadata.gatePhotoVisibleEndpointPhysicalMeshUseAuthorized);
  elements.gateReferenceStatus.setAttribute(
    'aria-label',
    '番号参照アンカー' + metadata.gateReferenceAnchorApprovedCount + '点と写真可視端点'
      + metadata.gatePhotoVisibleEndpointApprovedCount
      + '点は承認済みです。写真可視端点はレビュー表示専用で、計算面には採用していません。'
      + 'ローカル物理計算は別の承認済みR1C内部インターフェースを使用します。'
      + metadata.mainGateModelOpeningWidthM
      + 'メートルはH2モデル開口幅の静的契約で、地理的な実位置線ではありません。',
  );
  elements.fishwayIntegrationNote.textContent = isLocalPhysicsMode()
    ? '常時有効・操作不可／今回のR1Cローカル計算結果'
    : isN4P8dMode()
      ? '魚道等の簡易集約流路／常時有効／保存済み36時間結果'
    : isReferenceV2Mode()
      ? '常時有効・操作不可／瞬時流量は保存されていないため「値なし」'
      : '常時有効・操作不可／保存済み診断またはローカル計算を選択可能';
  elements.syntheticPairStatus.textContent = '現行synthetic：'
    + metadata.cellCount.toLocaleString('ja-JP') + 'セル・mesh/pack一致';
  elements.r20CompatibilityStatus.textContent = 'R20レビュー：'
    + metadata.formalR20ReviewMeshCellCount.toLocaleString('ja-JP')
    + 'セル・現行packとは非互換';
  elements.detailIntegration.textContent = isLocalPhysicsMode()
    ? 'local solver / fail-closed'
    : isN4P8dMode()
      ? 'sealed N4P8d 36h / read-only'
    : isReferenceV2Mode()
      ? 'sealed reference-v2 / read-only'
      : 'read-only / fail-closed';
  elements.detailBindings.textContent = 'runtime '
    + metadata.runtimeBindingCount + '/6・readiness '
    + metadata.readinessRuntimeBindingCount + '/5・契約復旧 '
    + metadata.contractRecoveryOfflineBindingCount + '/4 検証';
  syncReadinessInterface();
  syncContractRecoveryInterface();
}

function syncReadinessInterface() {
  if (!state.data) return;
  const metadata = state.data.metadata;
  const readiness = state.data.parallelReadiness;
  const formalMesh = readiness.costMeshes.find(mesh => mesh.id === 'formal_R20_44880');
  const multizoneMesh = readiness.costMeshes.find(mesh => mesh.id === 'multizone_R20_37168');
  const formalForecast = formalMesh.scenarioForecasts.binary_training_plus_5_holdouts;
  const multizoneForecast = multizoneMesh.scenarioForecasts.binary_training_plus_5_holdouts;

  elements.readinessValidationBadge.textContent =
    metadata.readinessPassedCheckCount + '/' + metadata.readinessCheckCount + ' PASS';
  elements.readinessValidationBadge.classList.add('is-pass');
  elements.readinessBoundaryStatus.textContent = '境界採用時：mesh再生成＋事前計算';
  elements.readinessBoundaryNote.textContent =
    metadata.boundaryChangedPixelCount.toLocaleString('ja-JP') + '画素・旧mesh '
    + metadata.boundaryChangedMeshCentroidMembershipCount.toLocaleString('ja-JP')
    + 'セル重心の所属が変化。旧packは流用不可です。';
  elements.readinessR20Status.textContent =
    metadata.formalR20PrecomputationExists ? '既存計算を確認' : '初回事前計算・再計算ではない';
  elements.readinessGateBasisStatus.textContent =
    'binary ' + metadata.binaryGateTrainingBasisCount + '＋'
    + metadata.binaryGateInteractionHoldoutCount + ' holdout / continuous '
    + metadata.continuousGateAxisBasisCount + '＋'
    + metadata.continuousGateInteractionHoldoutCount;
  elements.readinessFiftyStatus.textContent =
    metadata.globalFiftyPercentStatus === 'candidate_not_adopted'
      ? '未採用・direct 50% holdout待ち'
      : metadata.globalFiftyPercentStatus;
  elements.readinessCheckpointStatus.textContent =
    metadata.checkpointSegmentDurationHours + 'h×'
    + metadata.checkpointSegmentCountPerBasis + ' / restart '
    + metadata.checkpointRestartStateCountPerBasis + ' / snapshot '
    + metadata.checkpointDisplaySnapshotCountPerBasis;
  elements.readinessFormalCost.textContent = formatRunnerHoursRange(formalForecast);
  elements.readinessMultizoneCost.textContent = formatRunnerHoursRange(multizoneForecast);
  elements.readinessProvenanceStatus.textContent = metadata.currentFlowProvenanceLabelJa;
  elements.readinessPackageStatus.textContent =
    metadata.readinessCompletedTaskCount + '/' + metadata.readinessTaskCount
    + '項目完了・復旧binding ' + metadata.readinessRecoveryBindingCount
    + '・8門 ' + metadata.readinessBinaryPatternCount + ' pattern検証';
  elements.readinessCard.dataset.status = 'pass';
  elements.readinessCard.dataset.packageSha256 = metadata.readinessPackageSha256;
  elements.readinessCard.dataset.boundaryClassification = metadata.boundaryImpactClassification;
  elements.readinessCard.dataset.historicalPackReusable =
    String(metadata.boundaryHistoricalPackReusable);
  elements.readinessCard.dataset.gateInputDrivesDisplayedFlow =
    String(metadata.gateInputDrivesDisplayedFlow);
  elements.readinessCard.dataset.provenanceClassification =
    metadata.currentFlowProvenanceClassification;
}

function syncContractRecoveryInterface() {
  const ready = Boolean(state.data);
  const busy = state.contractRecoveryDownloadState === 'loading' && ready;
  for (const button of [
    elements.contractReportDownloadButton,
    elements.recoveryBundleDownloadButton,
    elements.physicalValidationPlanDownloadButton,
  ]) {
    button.disabled = !ready || busy;
  }
  elements.contractRecoveryDownloadStatus.textContent =
    state.contractRecoveryDownloadMessage;
  elements.contractRecoveryDownloadStatus.classList.toggle(
    'is-pass',
    state.contractRecoveryDownloadState === 'ready'
      || state.contractRecoveryDownloadState === 'pass',
  );
  elements.contractRecoveryDownloadStatus.classList.toggle(
    'is-error',
    state.contractRecoveryDownloadState === 'error',
  );
  if (!ready) return;

  const metadata = state.data.metadata;
  elements.contractRecoveryValidationBadge.textContent =
    metadata.contractAuditErrorCount + ' error / '
    + metadata.contractAuditWarningCount + ' warning';
  elements.contractRecoveryValidationBadge.classList.add('is-pass-with-warnings');
  elements.contractAuditStatus.textContent = 'PASS_WITH_WARNINGS・復旧可能';
  elements.contractAuditCounts.textContent =
    metadata.contractAuditSelectedJsonDocuments.toLocaleString('ja-JP')
    + ' JSON・' + metadata.contractAuditRecognizableBindingsChecked.toLocaleString('ja-JP')
    + ' bindingを横断検査';
  elements.contractAuditErrorCount.textContent =
    metadata.contractAuditErrorCount.toLocaleString('ja-JP');
  elements.contractAuditWarningCount.textContent =
    metadata.contractAuditWarningCount.toLocaleString('ja-JP');
  elements.contractWarningExternal.textContent =
    metadata.contractAuditWarningExternal.toLocaleString('ja-JP');
  elements.contractWarningMissing.textContent =
    metadata.contractAuditWarningMissing.toLocaleString('ja-JP');
  elements.contractWarningDigest.textContent =
    (
      metadata.contractAuditWarningDigest
      + metadata.contractAuditWarningByteLength
    ).toLocaleString('ja-JP');
  elements.contractWarningFormat.textContent =
    metadata.contractAuditWarningFormat.toLocaleString('ja-JP');
  elements.recoveryBundleStatus.textContent =
    metadata.recoveryBundleVerificationStatus + '・全entry SHA一致';
  elements.recoveryBundleCount.textContent =
    metadata.recoveryBundleDocumentEntriesChecked.toLocaleString('ja-JP')
    + '文書 / ' + metadata.recoveryBundleZipEntryCount.toLocaleString('ja-JP')
    + ' ZIP entry・' + formatBytes(metadata.recoveryBundleByteLength);
  elements.physicalValidationStatus.textContent =
    metadata.physicalValidationLabelJa;
  elements.physicalValidationNext.textContent =
    metadata.physicalValidationDecisionRequiredNow
      ? '判断が必要です'
      : '現在の追加判断は不要・全域境界凍結後に再確認';

  elements.contractRecoveryCard.dataset.status = metadata.contractAuditStatus;
  elements.contractRecoveryCard.dataset.sidecarSha256 =
    metadata.contractRecoveryGuiIntegrationSha256;
  elements.contractRecoveryCard.dataset.errorCount =
    String(metadata.contractAuditErrorCount);
  elements.contractRecoveryCard.dataset.warningCount =
    String(metadata.contractAuditWarningCount);
  elements.contractRecoveryCard.dataset.bundleVerification =
    metadata.recoveryBundleVerificationStatus;
  elements.contractRecoveryCard.dataset.physicalValidation =
    metadata.physicalValidationPlanStatus;
  elements.contractRecoveryCard.dataset.decisionRequiredNow =
    String(metadata.physicalValidationDecisionRequiredNow);
}

function syncGateObservationIo() {
  const ready = Boolean(state.data);
  elements.gateObservationImportButton.disabled = !ready;
  elements.gateObservationExportButton.disabled =
    !ready || state.gateInputMode !== 'field' || !state.gateObservation;
  elements.gateObservationIoStatus.textContent = state.gateObservationIoMessage;
  elements.gateObservationIoStatus.classList.toggle(
    'is-pass',
    state.gateObservationIoState === 'pass' || state.gateObservationIoState === 'ready',
  );
  elements.gateObservationIoStatus.classList.toggle(
    'is-error',
    state.gateObservationIoState === 'error',
  );
}

function syncR1CReplayCard() {
  const active = isR1CMode();
  elements.R1CReplayCard.hidden = !active;
  if (!active) return;
  const local = isLocalPhysicsMode();
  const referenceV2 = isReferenceV2Mode();
  const N4P8d = isN4P8dMode();
  elements.R1CReplayTitle.textContent = local
    ? '今回の物理計算値'
    : N4P8d
      ? '承認済みN4P8d・36時間リプレイ'
    : referenceV2
      ? '固定S4・48時間基準リプレイ'
      : '保存済み診断値';
  elements.R1CWarningBadge.textContent = local
    ? '未較正物理・参考値'
    : N4P8d
      ? '未較正・保存済み参考値'
    : referenceV2
      ? '未較正・モデル参考値'
      : '未較正・参考値';
  elements.R1CContractTitle.textContent = local
    ? '8門入力を物理solverへ反映済み'
    : N4P8d
      ? '36時間計算・数値検査・ヒートマップ目視承認済み'
    : referenceV2
      ? '固定S4基準リプレイ・予測ではありません'
      : '現地流量の絶対再現・予測ではありません';
  elements.R1CContractNote.textContent = local
    ? '魚道固有の観測データは存在せず、魚道流量はモデル参考値です。入力変更後は再計算してください。'
    : N4P8d
      ? '魚道と微調整ゲートは設備上別ですが、計算上は「魚道等」の簡易集約流路です。保存済み37時点だけを表示します。'
    : referenceV2
      ? '現地入力・自動推定は比較専用です。魚道は常時有効ですが、瞬時流量は保存されていません。'
      : '保存済みの標準開閉cycleです。魚道流量は未較正のモデル参考値です。';
  elements.R1CGateResultLabel.textContent = local
    ? '計算に使用した8門能力倍率'
    : N4P8d
      ? '保存時点の8門開閉状態（入力非駆動）'
    : referenceV2
      ? '固定S4能力倍率（入力非駆動）'
      : '保存済み8門能力倍率';
  const replay = state.data.replay;
  const index = state.snapshotIndex;
  const capacities = replay.gateCapacities(index);
  const comparisonPattern = effectiveGatePattern();
  const differing = [];
  for (let gateIndex = 0; gateIndex < 8; gateIndex += 1) {
    const comparison = Number(comparisonPattern?.[gateIndex]) / 100;
    if (!Number.isFinite(comparison) || Math.abs(comparison - capacities[gateIndex]) > 1e-6) {
      differing.push(gateIndex + 1);
    }
  }
  elements.R1CCurrentTime.textContent =
    referenceV2 || N4P8d
      ? formatReferenceTimestamp(replay.timestampsJst[index], false)
      : formatReplayTime(replay.absoluteTimeS[index], false);
  if (referenceV2 || N4P8d) {
    elements.R1CUpstreamHead.textContent =
      state.data.displayValue('upstreamP2HeadM').displayTextJa;
    elements.R1CDownstreamHead.textContent =
      state.data.displayValue('downstreamP2HeadM').displayTextJa;
    elements.R1CHeadDifference.textContent =
      state.data.displayValue('headDifferenceM').displayTextJa;
    elements.R1CFishwayFlow.textContent =
      state.data.displayValue('fishwayOutflowM3S').displayTextJa;
    elements.R1CFishwayDepth.textContent =
      state.data.displayValue('fishwayStorageDepthM').displayTextJa;
    elements.R1CGateFlux.textContent =
      state.data.displayValue('gateFluxM3SByGateId').displayTextJa;
    elements.R1CStoredVolume.textContent = N4P8d
      ? formatNumber(replay.storedVolumeM3[index], 0, ' m³')
      : state.data.displayValue('storedVolumeM3').displayTextJa;
  } else {
    elements.R1CUpstreamHead.textContent =
      formatNumber(replay.upstreamP2HeadM[index], 3, ' m');
    elements.R1CDownstreamHead.textContent =
      formatNumber(replay.downstreamP2HeadM[index], 3, ' m');
    elements.R1CHeadDifference.textContent =
      formatNumber(replay.headDifferenceM[index], 3, ' m');
    elements.R1CFishwayFlow.textContent =
      formatNumber(replay.fishwayOutflowM3S[index], 3, ' m³/s');
    elements.R1CFishwayDepth.textContent =
      formatNumber(replay.fishwayStorageDepthM[index], 3, ' m');
    elements.R1CGateFlux.textContent = Array.from(
      replay.gateFluxes(index),
      (value, gateIndex) => (gateIndex + 1) + ':' + formatNumber(value, 2),
    ).join('　') + ' m³/s';
    elements.R1CStoredVolume.textContent =
      formatNumber(replay.storedVolumeM3[index], 0, ' m³');
  }
  elements.R1CSavedGates.textContent = Array.from(
    capacities,
    (value, gateIndex) => (gateIndex + 1) + ':' + Math.round(value * 100) + '%',
  ).join('　');
  elements.R1CGateDifference.textContent = differing.length === 0
    ? '現在の' + (state.gateInputMode === 'field' ? '現地入力' : '自動推定')
      + (local
        ? 'と一致。この8門状態が表示中の流れ図に反映されています。'
        : N4P8d
          ? 'と保存時点が一致。入力非駆動のため流れ図は変更しません。'
          : referenceV2
            ? 'と固定S4が一致。入力非駆動のため流れ図は変更しません。'
          : 'と一致。比較表示だけで流れ図は変更しません。')
    : '現在の' + (state.gateInputMode === 'field' ? '現地入力' : '自動推定')
      + 'との差：' + differing.join('・') + '番。'
      + (local
        ? '変更を反映するには再計算してください。'
        : N4P8d
          ? '承認済み36時間リプレイは入力非駆動のため変更しません。'
          : referenceV2
            ? '固定S4基準リプレイは入力非駆動のため変更しません。'
          : '保存済み流れ図は変更しません。');
}

function syncLocalSimulatorInterface() {
  const busy = state.localServiceState === 'running'
    || state.localServiceState === 'loading';
  const pattern = busy && state.localRequestedCapacity
    ? state.localRequestedCapacity
    : effectiveGatePattern();
  const available = state.localServiceState === 'ready'
    || state.localServiceState === 'pass';
  elements.localSimulatorCard.dataset.status = state.localServiceState;
  elements.localSimulationDuration.disabled = !available || busy;
  elements.localSimulationRun.disabled = !available || busy || !pattern;
  elements.localReprobeButton.hidden =
    staticReviewMode || !['unavailable', 'failed'].includes(state.localServiceState);
  elements.localSimulatorBadge.textContent =
    staticReviewMode ? '閲覧専用'
      : state.localServiceState === 'ready' ? '実行可能'
      : state.localServiceState === 'running' ? '計算中'
        : state.localServiceState === 'loading' ? '結果読込中'
          : state.localServiceState === 'pass' ? '計算完了'
            : state.localServiceState === 'unavailable' ? '接続エラー'
              : state.localServiceState === 'failed' ? '安全停止'
                : '接続確認中';
  elements.localSimulationStatus.textContent = state.localServiceMessage;
  elements.localSimulationStatus.classList.toggle(
    'is-error',
    state.localServiceState === 'unavailable' || state.localServiceState === 'failed',
  );
  elements.localSimulationStatus.classList.toggle(
    'is-pass',
    state.localServiceState === 'ready' || state.localServiceState === 'pass',
  );
  if (!pattern) {
    elements.localSimulationGates.textContent = '水門入力の準備中です。';
  } else {
    const capacities = Array.from(pattern, value => Number(value) > 0 ? 1 : 0);
    const open = capacities.flatMap((value, index) => value ? [index + 1] : []);
    elements.localSimulationGates.textContent = open.length === 0
      ? '計算入力：1〜8番すべて閉／魚道は常時有効'
      : open.length === 8
        ? '計算入力：1〜8番すべて開／魚道は常時有効'
        : '計算入力：' + open.join('・') + '番開／他は閉／魚道は常時有効';
  }
  elements.dataModeLocal.disabled = !state.localData;
  syncLocalCalculationBanner();
}

function localResultInputChanged() {
  if (!state.localData || !state.localResultCapacity) return false;
  const current = effectiveGatePattern();
  if (!current || current.length !== state.localResultCapacity.length) return true;
  return state.localResultCapacity.some(
    (value, index) => Number(value) !== (Number(current[index]) > 0 ? 1 : 0),
  );
}

function syncLocalCalculationBanner() {
  let status = 'not-run';
  let title = 'ローカル計算：未実行';
  let note = '現在の表示は計算開始を意味しません。計算は明示操作後に開始します。';
  let jumpLabel = '水門入力と計算へ';

  if (staticReviewMode) {
    status = 'review-only';
    title = 'ローカル計算：閲覧専用';
    note = 'この画面では計算を開始できません。保存済み・合成表示だけを確認できます。';
  } else if (state.localServiceState === 'failed') {
    status = 'failed';
    title = 'ローカル計算：安全停止';
    note = '合成または保存済み表示は継続中です。サービス再確認後も計算は自動再開しません。';
    jumpLabel = '復旧と入力を確認';
  } else if (state.localServiceState === 'unavailable') {
    status = 'unavailable';
    title = 'ローカル計算：サービス未接続';
    note = '合成または保存済み表示は継続中です。計算サービスだけが停止しています。';
    jumpLabel = '復旧と入力を確認';
  } else if (state.localServiceState === 'running') {
    status = 'running';
    title = 'ローカル計算：計算中';
    note = '実行ボタンを押した時点の8門入力を固定して計算しています。';
  } else if (state.localServiceState === 'loading') {
    status = 'verifying';
    title = 'ローカル計算：結果検証中';
    note = '結果のSHA-256と配列構造を確認しています。';
  } else if (state.localData && localResultInputChanged()) {
    status = 'stale';
    title = 'ローカル計算：入力変更済み・再計算が必要';
    note = '表示中または保存済みの結果は変更前の8門入力です。現在入力はまだ反映されていません。';
  } else if (state.localData && isLocalPhysicsMode()) {
    status = 'result';
    title = 'ローカル計算：結果表示中';
    note = '計算時の8門入力を反映した未較正結果です。現地予測ではありません。';
  } else if (state.localData) {
    status = 'result';
    title = 'ローカル計算：結果あり';
    note = '検証済みのローカル結果がありますが、現在の地図は別の表示データです。';
  } else if (state.localServiceState === 'checking') {
    status = 'checking';
    title = 'ローカル計算：接続確認中';
    note = 'サービスの能力だけを確認しています。計算は開始していません。';
  }

  elements.localCalculationBanner.dataset.status = status;
  elements.localCalculationTitle.textContent = title;
  elements.localCalculationNote.textContent = note;
  elements.localCalculationJump.textContent = jumpLabel;
  elements.localCalculationJump.hidden = staticReviewMode;
}

function syncGateInterface() {
  const isField = state.gateInputMode === 'field';
  const automaticStage = automaticGateStage();
  const automaticPattern = automaticGatePattern();
  const effectivePattern = effectiveGatePattern();
  const open = openGateNumbers(effectivePattern);
  const fieldStage = isField ? classifyGatePattern(state.gateObservation) : null;
  const differing = isField ? differingGateNumbers(state.gateObservation, automaticPattern) : [];
  const hasPattern = effectivePattern !== null;

  elements.gateSummaryBadge.textContent = gateObservationLabel(false);
  elements.gateSummaryBadge.classList.toggle('has-input', isField);
  elements.gateSummaryBadge.classList.toggle('is-auto', !isField);
  elements.gateSummaryBadge.classList.toggle('is-warning', isField && fieldStage === null);
  elements.gateFieldInputs.hidden = !isField;
  elements.gateReturnAuto.disabled = !isField;

  for (const button of document.querySelectorAll('[data-gate-mode]')) {
    const active = button.dataset.gateMode === state.gateInputMode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  }

  if (elements.gateSource.value !== state.gateObservationSource) {
    elements.gateSource.value = state.gateObservationSource;
  }
  if (elements.gateObservedAt.value !== state.gateObservedAt) {
    elements.gateObservedAt.value = state.gateObservedAt;
  }

  for (const button of document.querySelectorAll('[data-gate]')) {
    const gateIndex = Number(button.dataset.gate);
    const isOpen = hasPattern && Number(effectivePattern[gateIndex]) > 0;
    button.classList.toggle('is-unset', !hasPattern);
    button.classList.toggle('is-open', hasPattern && isField && isOpen);
    button.classList.toggle('is-auto-open', hasPattern && !isField && isOpen);
    button.classList.toggle('is-closed', hasPattern && !isOpen);
    button.setAttribute('aria-pressed', hasPattern ? String(isOpen) : 'mixed');
    button.setAttribute(
      'aria-label',
      (gateIndex + 1) + '番水門、' + (!hasPattern ? '推定待ち' : isOpen ? '開100%' : '閉0%')
        + (isField ? '、現地入力' : '、自動推定'),
    );
    button.querySelector('small').textContent = !hasPattern ? '—' : isOpen ? '開' : '閉';
  }

  if (automaticStage === null) {
    elements.gateAutoStage.textContent = '推定待ち';
  } else {
    const fraction = state.forcingData
      ? automaticStage / 8
      : state.data.inputs.barrageOpeningFraction[state.snapshotIndex];
    elements.gateAutoStage.textContent = '段階 ' + automaticStage + ' / 8（全体'
      + Math.round(fraction * 100) + '%）'
      + (state.forcingData ? '・気象／潮位入力' : '');
  }

  elements.gateDelta.textContent = !isField
    ? '—（自動推定を使用）'
    : differing.length === 0
      ? '差なし（0門）'
      : differing.join('・') + '番（' + differing.length + '門）';

  elements.gateStandardStatus.classList.toggle('is-standard', isField && fieldStage !== null);
  elements.gateStandardStatus.classList.toggle('is-warning', isField && fieldStage === null);
  elements.gateStandardStatus.textContent = !isField
    ? '自動推定を使用中'
    : fieldStage === null
      ? '標準順序外'
      : '固定順序の段階 ' + fieldStage + ' / 8';

  if (!hasPattern) {
    elements.gateDetail.textContent = '自動推定の準備中です。';
  } else if (!isField) {
    elements.gateDetail.textContent = '自動推定：段階' + automaticStage + '/8。'
      + (state.forcingData
        ? '気象庁降水量からの未較正流量と指定日の相対潮位を使用。'
        : '表示中データの合成開度を使用。')
      + '固定順序の先頭' + automaticStage + '門を100%、残りを0%として表示しています。';
  } else {
    const pattern = gatePatternLabel(state.gateObservation, false);
    const source = state.gateObservationSource || '入力元未指定';
    elements.gateDetail.textContent = '現地入力：' + pattern
      + (open.length > 0 && open.length < 8 ? '（' + open.join('・') + '番開）' : '')
      + '。入力元：' + source + '／観測：' + observedAtLabel(state.gateObservedAt) + '。';
  }

  const mapModeLabel = !hasPattern
    ? '自動推定：待機中'
    : state.gateInputMode === 'auto'
      ? '自動推定：段階' + automaticStage + '/8'
      : fieldStage === null
        ? '現地入力：標準順序外'
        : '現地入力：段階' + fieldStage + '/8';
  elements.mapGateLabel.textContent = isR1CMode()
    ? isLocalPhysicsMode()
      ? 'R1Cローカル物理計算／計算時の8門状態を反映／青：水門1〜8／魚道常時有効'
      : isN4P8dMode()
        ? '承認済み36時間リプレイ／保存時点の8門状態／青：水門1〜8／魚道等は常時有効'
      : isReferenceV2Mode()
        ? '固定S4基準リプレイ／入力非駆動・比較のみ／青：水門1〜8／魚道常時有効'
        : 'R1C保存済み能力倍率／現地・自動入力は比較のみ／青：水門1〜8／魚道常時有効'
    : mapModeLabel
      + (state.forcingData ? '・気象／潮位入力' : '')
      + '／A1–A8番号アンカー・写真端点16/16／実行ボタンで水門状態だけR1C物理計算へ反映';
  elements.fishwayIntegrationNote.textContent = isR1CMode()
    ? isLocalPhysicsMode()
      ? '魚道流量は未較正のモデル参考値。常時有効・操作不可。'
      : isN4P8dMode()
        ? '魚道等は簡易集約流路として常時有効。瞬時流量は保存されていないため「値なし」。'
      : isReferenceV2Mode()
        ? '魚道は常時有効・操作不可。瞬時流量は保存されていないため「値なし」。'
        : '保存済みの魚道流量は未較正のモデル参考値。常時有効・操作不可。'
    : '魚道はローカル物理計算でも常時有効。入力は実行ボタンで流れ図へ反映。';
  syncR1CReplayCard();
  syncLocalSimulatorInterface();
  syncGateObservationIo();
  syncMapAriaLabel();
}

function setGateMode(mode) {
  if (mode !== 'auto' && mode !== 'field') return;
  if (mode === 'field') {
    state.gateObservation = state.gateObservation
      ? Array.from(state.gateObservation)
      : Array.from(automaticGatePattern() || gatePatternForStage(0));
    if (!state.gateObservedAt) state.gateObservedAt = localDateTimeValue();
  } else {
    state.gateObservation = null;
    state.gateObservedAt = '';
  }
  state.gateInputMode = mode;
  syncGateInterface();
  scheduleRender();
}

function setGateObservation(levels) {
  state.gateInputMode = 'field';
  state.gateObservation = Array.from({ length: 8 }, (_, index) => Number(levels?.[index]) > 0 ? 100 : 0);
  if (!state.gateObservedAt) state.gateObservedAt = localDateTimeValue();
  syncGateInterface();
  scheduleRender();
}

function currentGateObservationBatch() {
  if (state.gateInputMode !== 'field' || !state.gateObservation) {
    throw new Error('現地目視入力を有効にして、1〜8番の状態を確認してください。');
  }
  if (!state.gateObservedAt) state.gateObservedAt = localDateTimeValue();
  const exportedAt = new Date().toISOString();
  const compactId = exportedAt.replace(/[^0-9]/g, '').slice(0, 17);
  const gateStateById = Object.fromEntries(
    Array.from({ length: 8 }, (_, index) => [
      String(index + 1),
      Number(state.gateObservation[index]) > 0 ? 1 : 0,
    ]),
  );
  const batch = {
    schema: 'onga-stage20-field-gate-observation-batch-v1',
    version: 1,
    timezone: 'Asia/Tokyo',
    exportedAt,
    records: [
      {
        observationId: 'stage20-gui-' + compactId,
        observedAt: tokyoOffsetTimestamp(state.gateObservedAt),
        source: gateSourceForSchema(state.gateObservationSource),
        gateStateById,
        provenance: {
          recordedBy: 'stage20-hybrid-gui-local',
          recordedAt: exportedAt,
        },
        revision: 1,
      },
    ],
  };
  validateStage20FieldGateObservationBatch(
    batch,
    state.data.fieldGateObservationSchema,
  );
  return batch;
}

function downloadCurrentGateObservation() {
  try {
    const batch = currentGateObservationBatch();
    const text = canonicalJsonText(batch);
    const blob = new Blob([text], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = batch.records[0].observationId + '.json';
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    state.gateObservationIoState = 'pass';
    state.gateObservationIoMessage =
      'PASS：現在の8門状態をcanonical JSONとして端末へ保存しました。外部送信はしていません。';
  } catch (error) {
    state.gateObservationIoState = 'error';
    state.gateObservationIoMessage = '出力できません：' + (error?.message || String(error));
  }
  syncGateObservationIo();
}

async function downloadContractRecoveryArtifact(bindingId) {
  if (!state.data) return;
  state.contractRecoveryDownloadState = 'loading';
  state.contractRecoveryDownloadMessage =
    '固定SHA-256とbyte lengthを照合してから保存します。';
  syncContractRecoveryInterface();
  try {
    const artifact = await fetchStage20ContractRecoveryArtifact(
      state.data.contractRecovery,
      bindingId,
    );
    const blob = new Blob([artifact.bytes], {
      type: artifact.binding.mediaType,
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = artifact.binding.downloadName;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    state.contractRecoveryDownloadState = 'pass';
    state.contractRecoveryDownloadMessage =
      'PASS：' + artifact.binding.downloadName + '（'
      + formatBytes(artifact.binding.byteLength)
      + '）をSHA検証後に保存しました。外部送信はしていません。';
  } catch (error) {
    state.contractRecoveryDownloadState = 'error';
    state.contractRecoveryDownloadMessage =
      '成果物を保存できません：' + (error?.message || String(error));
  }
  syncContractRecoveryInterface();
}

async function importGateObservationFile(file) {
  if (!file) return;
  state.gateObservationIoState = 'loading';
  state.gateObservationIoMessage = '観測JSONを検証しています。';
  syncGateObservationIo();
  try {
    if (file.size > 1024 * 1024) throw new Error('観測JSONは1MB以下にしてください。');
    const batch = JSON.parse(await file.text());
    validateStage20FieldGateObservationBatch(
      batch,
      state.data.fieldGateObservationSchema,
    );
    if (batch.records.length === 0) throw new Error('観測recordがありません。');
    const record = batch.records.at(-1);
    state.gateObservationSource = gateSourceFromSchema(record.source);
    state.gateObservedAt = timestampToTokyoLocalValue(record.observedAt);
    setGateObservation(
      Array.from({ length: 8 }, (_, index) => (
        record.gateStateById[String(index + 1)] === 1 ? 100 : 0
      )),
    );
    state.gateObservationIoState = 'pass';
    state.gateObservationIoMessage =
      'PASS：' + file.name + '（' + batch.records.length
      + ' record）を検証し、最終recordを画面内の8門入力へ反映しました。';
  } catch (error) {
    state.gateObservationIoState = 'error';
    state.gateObservationIoMessage =
      '観測JSONを拒否しました：' + (error?.message || String(error));
  } finally {
    elements.gateObservationImportFile.value = '';
    syncGateInterface();
  }
}

function syncResponsiveDocumentOrder() {
  const first = mobileLayout.matches ? elements.mapSection : elements.controlPanel;
  const second = mobileLayout.matches ? elements.controlPanel : elements.mapSection;
  if (elements.workspace.firstElementChild !== first) elements.workspace.insertBefore(first, second);
}

function setPhase(phase, title, message) {
  state.phase = phase;
  elements.app.dataset.phase = phase;
  elements.loadStatus.textContent = phase === 'ready' ? '表示準備完了' : phase === 'error' ? '読み込み失敗' : '読み込み中';
  if (phase === 'error') {
    elements.integrationStatusBadge.textContent = '統合状態：停止';
    elements.integrationStatusBadge.setAttribute('aria-label', 'GUI統合検証に失敗したため表示を停止');
  }
  elements.overlayTitle.textContent = title;
  elements.overlayMessage.textContent = message;
  elements.retry.hidden = phase !== 'error';
  const disabled = phase !== 'ready';
  for (const control of [elements.previous, elements.play, elements.next, elements.now, elements.slider]) {
    control.disabled = disabled;
  }
}

function syncDataModeButtons(activeMode = state.dataMode) {
  for (const button of document.querySelectorAll('[data-data-mode]')) {
    const active = button.dataset.dataMode === activeMode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  }
}

function activateDataMode(mode, data, geometry) {
  stopPlayback({ sync: false });
  if (mode !== 'n4p8d' && state.layer === 'maximum-speed') state.layer = 'speed';
  state.dataMode = mode;
  const runtimeCapability = runtimeCapabilityForGuiMode(mode);
  if (!runtimeCapability) throw new Error(`runtime capability is missing for GUI mode ${mode}`);
  state.data = data;
  state.geometry = geometry;
  state.selectedCell = null;
  state.snapshotMaximumSpeeds = new Float64Array(data.metadata.snapshotCount);
  state.snapshotMaximumSpeeds.fill(Number.NaN);
  state.snapshotIndex = mode === 'synthetic' ? PRESENT_INDEX : 0;
  elements.slider.max = String(data.metadata.snapshotCount - 1);
  elements.slider.value = String(state.snapshotIndex);
  elements.canvas.dataset.dataMode =
    mode === 'r1c' ? 'R1C-uncalibrated-diagnostic-replay'
      : mode === 'reference-v2' ? 'reference-v2-fixed-S4-replay'
      : mode === 'n4p8d' ? 'N4P8d-36h-uncalibrated-read-only-replay'
      : mode === 'local' ? 'R1C-local-uncalibrated-physics'
        : 'synthetic-prototype';
  elements.canvas.dataset.runtimeCapabilityMode = runtimeCapability.id;
  elements.canvas.dataset.runtimeExecutionKind = runtimeCapability.executionKind;
  elements.canvas.dataset.runtimeGateEffect = runtimeCapability.gateEffect;
  elements.canvas.dataset.runtimeRiverTideBoundaryPhysics =
    runtimeCapability.riverTideBoundaryPhysics;
  elements.canvas.dataset.runtimeFishwayRepresentation =
    runtimeCapability.fishwayRepresentation;
  elements.canvas.dataset.runtimeFieldPrediction = String(runtimeCapability.fieldPrediction);
  elements.canvas.dataset.runtimeOperationalFishingAdvice =
    String(runtimeCapability.operationalFishingAdvice);
  elements.canvas.dataset.runtimeSafetyAuthority = String(runtimeCapability.safetyAuthority);
  elements.canvas.dataset.runtimePublicRuntime = String(runtimeCapability.publicRuntime);
  elements.canvas.dataset.resultProvenanceClassification =
    data.metadata.currentFlowProvenanceClassification;
  elements.canvas.dataset.gateInputDrivesDisplayedFlow =
    String(data.metadata.fieldGateInputDrivesDisplayedFlow
      ?? data.metadata.gateInputDrivesDisplayedFlow);
  elements.canvas.dataset.R1CReplayReadOnly =
    String(mode === 'r1c' || mode === 'reference-v2' || mode === 'n4p8d');
  elements.canvas.dataset.R1CReplayUncalibrated =
    String(mode === 'r1c' || mode === 'reference-v2' || mode === 'n4p8d');
  elements.canvas.dataset.referenceV2FixedS4 = String(mode === 'reference-v2');
  elements.canvas.dataset.N4P8dApproved36h = String(mode === 'n4p8d');
  elements.canvas.dataset.N4P8dInputDriven = 'false';
  elements.canvas.dataset.N4P8dCalibrated = 'false';
  elements.canvas.dataset.referenceV2Prediction = 'false';
  elements.canvas.dataset.referenceV2InputDriven = 'false';
  elements.canvas.dataset.localPhysicsResult = String(mode === 'local');
  elements.canvas.dataset.localPhysicsCalibrated = 'false';
  syncDataModeButtons(mode);
  syncIntegrationInterface();
  setPhase('ready', '表示準備が完了しました', '地図を操作できます。');
  syncInterface();
  scheduleRender();
}

function R1CProgressLabel(stage) {
  state.R1CLoadState = 'loading';
  if (stage === 'R1C-approval') {
    state.R1CLoadMessage = '承認・manifest・静的検査の固定SHAを確認中です。';
    setPhase('loading', 'R1C診断の承認を検証しています', state.R1CLoadMessage);
  } else if (stage === 'R1C-binary') {
    state.R1CLoadMessage = '約75MiBの保存済み診断データを読み込み、SHA-256を確認中です。';
    setPhase('loading', 'R1C診断データを読み込んでいます', state.R1CLoadMessage);
  } else if (stage === 'R1C-index') {
    state.R1CLoadMessage = '171時点・37,724セルの座標と水面境界を構築中です。';
    setPhase('loading', 'R1C表示を組み立てています', state.R1CLoadMessage);
  }
  elements.dataModeStatus.textContent = state.R1CLoadMessage;
}

function referenceV2ProgressLabel(stage) {
  state.referenceV2LoadState = 'loading';
  if (stage === 'reference-v2-loader-import') {
    state.referenceV2LoadMessage = '検証済み読込器を準備しています。';
  } else if (stage.includes('manifest')) {
    state.referenceV2LoadMessage = '固定manifestのサイズ・SHA-256・URLを確認しています。';
  } else if (stage.includes('binary')) {
    state.referenceV2LoadMessage = '約17MiBの水深・流速データを取得し、SHA-256を確認しています。';
  } else if (stage === 'reference-v2-adapter') {
    state.referenceV2LoadMessage = '37時点・37,724セルの表示索引を構築しています。';
  } else {
    state.referenceV2LoadMessage = '固定S4基準リプレイを安全確認しています。';
  }
  setPhase(
    'loading',
    '48時間基準リプレイを検証しています',
    state.referenceV2LoadMessage,
  );
  elements.dataModeStatus.textContent = state.referenceV2LoadMessage;
}

function N4P8dProgressLabel(stage) {
  state.N4P8dLoadState = 'loading';
  if (stage === 'n4p8d-contract') {
    state.N4P8dLoadMessage = '目視承認・manifest・独立検査の固定SHAを確認しています。';
  } else if (stage === 'n4p8d-binary') {
    state.N4P8dLoadMessage = '約17MiBの36時間水深・流速データを検証して読み込んでいます。';
  } else {
    state.N4P8dLoadMessage = '37時点・37,724セルの表示索引を構築しています。';
  }
  setPhase('loading', '承認済み36時間リプレイを検証しています', state.N4P8dLoadMessage);
  elements.dataModeStatus.textContent = state.N4P8dLoadMessage;
}

async function switchDataMode(mode) {
  if (
    mode !== 'synthetic'
      && mode !== 'r1c'
      && mode !== 'reference-v2'
      && mode !== 'n4p8d'
      && mode !== 'local'
  ) return;
  if (!state.syntheticData || !state.syntheticGeometry) return;
  if (mode === 'local') {
    if (state.localData && state.localGeometry) {
      state.localServiceMessage =
        '今回のR1Cローカル未較正物理計算を表示しています。';
      activateDataMode('local', state.localData, state.localGeometry);
    }
    return;
  }
  if (mode === 'synthetic') {
    state.R1CLoadController?.abort();
    state.R1CLoadController = null;
    state.referenceV2LoadController?.abort();
    state.referenceV2LoadController = null;
    state.N4P8dLoadController?.abort();
    state.N4P8dLoadController = null;
    state.R1CLoadState = state.R1CData ? 'ready' : 'idle';
    state.R1CLoadMessage = state.R1CData
      ? 'R1C診断リプレイは検証済みです。選択すると再表示できます。'
      : '選択すると約75MiBの検証済みデータを読み込みます。';
    activateDataMode('synthetic', state.syntheticData, state.syntheticGeometry);
    return;
  }
  if (mode === 'n4p8d') {
    if (state.N4P8dData && state.N4P8dGeometry) {
      state.N4P8dLoadState = 'ready';
      state.N4P8dLoadMessage = '承認済み36時間リプレイを読み取り専用・入力非駆動で表示しています。';
      activateDataMode('n4p8d', state.N4P8dData, state.N4P8dGeometry);
      return;
    }
    const previous = Object.freeze({ mode: state.dataMode, data: state.data, geometry: state.geometry });
    stopPlayback({ sync: false });
    state.R1CLoadController?.abort();
    state.referenceV2LoadController?.abort();
    const controller = new AbortController();
    state.N4P8dLoadController?.abort();
    state.N4P8dLoadController = controller;
    syncDataModeButtons('n4p8d');
    elements.dataModeStatus.classList.remove('is-error');
    try {
      const replayModule = await import('./onga_stage20_n4p8d_replay.mjs');
      const data = await replayModule.loadStage20N4P8dReplay({
        baseData: state.syntheticData,
        signal: controller.signal,
        onProgress: N4P8dProgressLabel,
      });
      if (state.N4P8dLoadController !== controller) return;
      const geometry = prepareGeometry(data);
      state.N4P8dData = data;
      state.N4P8dGeometry = geometry;
      state.N4P8dLoadState = 'ready';
      state.N4P8dLoadMessage = '承認済み36時間リプレイを読み取り専用・入力非駆動で表示しています。';
      activateDataMode('n4p8d', data, geometry);
    } catch (error) {
      if (error?.name === 'AbortError') return;
      console.error(error);
      state.N4P8dLoadState = 'error';
      state.N4P8dLoadMessage = '承認済み36時間リプレイを拒否しました。直前の表示へ復帰しました：'
        + (error?.message || String(error));
      elements.dataModeStatus.classList.add('is-error');
      activateDataMode(previous.mode, previous.data, previous.geometry);
      elements.dataModeStatus.textContent = state.N4P8dLoadMessage;
      elements.dataModeStatus.classList.add('is-error');
    } finally {
      if (state.N4P8dLoadController === controller) state.N4P8dLoadController = null;
    }
    return;
  }
  if (mode === 'reference-v2') {
    if (state.referenceV2Data && state.referenceV2Geometry) {
      state.referenceV2LoadState = 'ready';
      state.referenceV2LoadMessage =
        '固定S4基準リプレイを読み取り専用・入力非駆動で表示しています。';
      activateDataMode(
        'reference-v2',
        state.referenceV2Data,
        state.referenceV2Geometry,
      );
      return;
    }
    const previous = Object.freeze({
      mode: state.dataMode,
      data: state.data,
      geometry: state.geometry,
    });
    stopPlayback({ sync: false });
    state.R1CLoadController?.abort();
    state.N4P8dLoadController?.abort();
    const controller = new AbortController();
    state.referenceV2LoadController?.abort();
    state.referenceV2LoadController = controller;
    syncDataModeButtons('reference-v2');
    elements.dataModeStatus.classList.remove('is-error');
    try {
      const replayModule = await import(
        './onga_stage20_reference_v2_display_adapter_20260730_g6t4.mjs'
      );
      const data = await replayModule.loadStage20ReferenceV2DisplayData({
        baseData: state.syntheticData,
        signal: controller.signal,
        onProgress: referenceV2ProgressLabel,
      });
      if (state.referenceV2LoadController !== controller) return;
      const geometry = prepareGeometry(data);
      state.referenceV2Data = data;
      state.referenceV2Geometry = geometry;
      state.referenceV2LoadState = 'ready';
      state.referenceV2LoadMessage =
        '固定S4基準リプレイを読み取り専用・入力非駆動で表示しています。';
      activateDataMode('reference-v2', data, geometry);
    } catch (error) {
      if (error?.name === 'AbortError') return;
      console.error(error);
      state.referenceV2LoadState = 'error';
      state.referenceV2LoadMessage =
        '48時間基準リプレイを拒否しました。直前の表示へ復帰しました：'
        + (error?.message || String(error));
      elements.dataModeStatus.classList.add('is-error');
      activateDataMode(previous.mode, previous.data, previous.geometry);
      elements.dataModeStatus.textContent = state.referenceV2LoadMessage;
      elements.dataModeStatus.classList.add('is-error');
    } finally {
      if (state.referenceV2LoadController === controller) {
        state.referenceV2LoadController = null;
      }
    }
    return;
  }
  state.referenceV2LoadController?.abort();
  state.referenceV2LoadController = null;
  state.N4P8dLoadController?.abort();
  state.N4P8dLoadController = null;
  if (state.R1CData && state.R1CGeometry) {
    state.R1CLoadState = 'ready';
    state.R1CLoadMessage = 'R1C未較正診断リプレイを読み取り専用で表示しています。';
    activateDataMode('r1c', state.R1CData, state.R1CGeometry);
    return;
  }
  stopPlayback({ sync: false });
  state.R1CLoadController?.abort();
  state.R1CLoadController = new AbortController();
  syncDataModeButtons('r1c');
  elements.dataModeStatus.classList.remove('is-error');
  try {
    const data = await loadStage20R1CDiagnosticReplay({
      baseData: state.syntheticData,
      signal: state.R1CLoadController.signal,
      onProgress: R1CProgressLabel,
    });
    const geometry = prepareGeometry(data);
    state.R1CData = data;
    state.R1CGeometry = geometry;
    state.R1CLoadState = 'ready';
    state.R1CLoadMessage = 'R1C未較正診断リプレイを読み取り専用で表示しています。';
    activateDataMode('r1c', data, geometry);
  } catch (error) {
    if (error?.name === 'AbortError') return;
    console.error(error);
    state.R1CLoadState = 'error';
    state.R1CLoadMessage =
      'R1Cデータを拒否しました。既存の合成表示へ復帰しました：'
      + (error?.message || String(error));
    elements.dataModeStatus.classList.add('is-error');
    activateDataMode('synthetic', state.syntheticData, state.syntheticGeometry);
    elements.dataModeStatus.textContent = state.R1CLoadMessage;
  } finally {
    state.R1CLoadController = null;
  }
}

async function probeLocalSimulator() {
  state.localController?.abort();
  const controller = new AbortController();
  state.localController = controller;
  state.localServiceState = 'checking';
  state.localServiceMessage = 'ローカル計算サービスを確認しています。';
  syncLocalSimulatorInterface();
  try {
    state.localCapabilities = await probeStage20LocalSimulator({
      signal: controller.signal,
    });
    state.localServiceState = 'ready';
    state.localServiceMessage =
      'runnerと入力を検査済み。solver実行preflightは未実施です。明示操作後にローカル計算できます。';
  } catch (error) {
    if (error?.name === 'AbortError') return;
    console.error('[stage20-local-simulator] capability probe failed', error);
    state.localCapabilities = null;
    state.localServiceState = 'unavailable';
    state.localServiceMessage =
      '専用serviceに接続できません。tools/serve_stage20_local_simulator_v1.pyから開いた後、'
      + '「ローカル計算サービスを再確認」を押してください。詳細：'
      + (error?.message || String(error));
  } finally {
    if (state.localController === controller) state.localController = null;
    syncLocalSimulatorInterface();
  }
}

function waitForLocalPoll(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

async function runLocalSimulation() {
  if (!state.localCapabilities || state.localServiceState === 'running') return;
  const pattern = effectiveGatePattern();
  if (!pattern) return;
  const capacity = Array.from(pattern, value => Number(value) > 0 ? 1 : 0);
  const durationS = Number(elements.localSimulationDuration.value);
  state.localController?.abort();
  const controller = new AbortController();
  state.localController = controller;
  state.localRequestedCapacity = capacity;
  state.localServiceState = 'running';
  state.localServiceMessage =
    'R1C 37,724セルの物理計算を準備しています。画面を閉じずにお待ちください。';
  syncLocalSimulatorInterface();
  try {
    if (!state.R1CData || !state.R1CGeometry) {
      await switchDataMode('r1c');
      if (!state.R1CData || !state.R1CGeometry) {
        throw new Error('検証済みR1C形状を読み込めませんでした。');
      }
    }
    const job = await createStage20LocalSimulationJob(capacity, durationS, {
      signal: controller.signal,
    });
    state.localJob = job;
    state.localServiceMessage =
      durationS + '秒の物理計算を実行中です。魚道は常時有効です。';
    syncLocalSimulatorInterface();
    const started = performance.now();
    let completedJob = job;
    while (!completedJob.completed) {
      if (performance.now() - started > 30 * 60 * 1000) {
        throw new Error('ローカル計算の待機上限を超えました。');
      }
      await waitForLocalPoll(650, controller.signal);
      completedJob = await fetchStage20LocalSimulationJob(job.jobId, {
        signal: controller.signal,
      });
    }
    if (completedJob.status !== 'PASS' || completedJob.resultUsable !== true) {
      throw new Error(completedJob.message || '物理計算が安全停止しました。');
    }
    state.localServiceState = 'loading';
    state.localServiceMessage = '計算結果のSHA-256と配列構造を検証しています。';
    syncLocalSimulatorInterface();
    const data = await loadStage20LocalSimulationResult(completedJob, {
      baseR1CData: state.R1CData,
      signal: controller.signal,
      onProgress: stage => {
        state.localServiceMessage =
          stage === 'local-manifest'
            ? '計算結果manifestを検証しています。'
            : stage === 'local-binary'
              ? '流速・水深配列のSHA-256を検証しています。'
              : '37,724セルの表示索引を構築しています。';
        syncLocalSimulatorInterface();
      },
    });
    state.localJob = completedJob;
    state.localData = data;
    state.localResultCapacity = Array.from(capacity);
    state.localGeometry = state.R1CGeometry;
    state.localServiceState = 'pass';
    state.localServiceMessage =
      durationS + '秒の未較正物理計算が完了し、8門入力を流れ図へ反映しました。';
    activateDataMode('local', data, state.localGeometry);
  } catch (error) {
    if (error?.name === 'AbortError') return;
    console.error(error);
    state.localServiceState = 'failed';
    state.localServiceMessage =
      '物理計算を安全停止しました：' + (error?.message || String(error));
    syncLocalSimulatorInterface();
  } finally {
    if (state.localController === controller) state.localController = null;
  }
}

function progressLabel(stage) {
  if (stage === 'integration-manifest') {
    setPhase('loading', 'GUI統合状態を検証しています', '状態manifestのidentity、表示区分、runtime bindingを確認中です。');
  } else if (stage === 'contract-recovery-index') {
    setPhase('loading', '契約監査・復旧を検証しています', '小さいsidecarだけを読み、監査JSON・復旧ZIP・Validation計画の固定SHAを確認中です。');
  } else if (stage === 'readiness-contracts') {
    setPhase('loading', '事前計算準備を検証しています', 'readiness package、境界影響、観測・出所schemaの固定SHAを確認中です。');
  } else if (stage === 'mesh-and-contracts') {
    setPhase('loading', '地図の形を読み込んでいます', 'メッシュv2とローカル背景、表示用データの組み合わせを確認中です。');
  } else if (stage === 'synthesis') {
    setPhase('loading', '37時点の表示データを作成中です', '合成応答パックをブラウザ内で展開しています。本計算は実行していません。');
  }
}

async function loadApplicationUnchecked() {
  stopPlayback();
  state.loadController?.abort();
  state.R1CLoadController?.abort();
  state.referenceV2LoadController?.abort();
  state.N4P8dLoadController?.abort();
  state.localController?.abort();
  state.forcingController?.abort();
  state.loadController = new AbortController();
  state.R1CLoadController = null;
  state.dataMode = 'synthetic';
  state.data = null;
  state.geometry = null;
  state.runtimeCapabilities = null;
  state.syntheticData = null;
  state.syntheticGeometry = null;
  state.R1CData = null;
  state.R1CGeometry = null;
  state.R1CLoadState = 'idle';
  state.R1CLoadMessage = '選択すると約75MiBの検証済みデータを読み込みます。';
  state.referenceV2Data = null;
  state.referenceV2Geometry = null;
  state.referenceV2LoadController = null;
  state.referenceV2LoadState = 'idle';
  state.referenceV2LoadMessage =
    '選択すると約17MiBの固定S4基準リプレイを検証して読み込みます。';
  state.N4P8dData = null;
  state.N4P8dGeometry = null;
  state.N4P8dLoadController = null;
  state.N4P8dLoadState = 'idle';
  state.N4P8dLoadMessage =
    '選択すると約17MiBの承認済み36時間リプレイを検証して読み込みます。';
  state.localCapabilities = null;
  state.localServiceState = 'checking';
  state.localServiceMessage = 'ローカル計算サービスを確認しています。';
  state.localJob = null;
  state.localRequestedCapacity = null;
  state.localResultCapacity = null;
  state.localData = null;
  state.localGeometry = null;
  state.localController = null;
  state.forcingCapabilities = null;
  state.forcingServiceState = 'checking';
  state.forcingServiceMessage = 'ローカル入力サービスを確認しています。';
  state.forcingData = null;
  state.forcingController = null;
  elements.dataModeLocal.disabled = true;
  state.snapshotMaximumSpeeds = null;
  state.selectedCell = null;
  state.gateObservationIoState = 'loading';
  state.gateObservationIoMessage = '観測schemaを検証中です。';
  state.contractRecoveryDownloadState = 'loading';
  state.contractRecoveryDownloadMessage = 'sidecar manifestを検証中です。';
  syncContractRecoveryInterface();
  setPhase('loading', '表示データを準備しています', 'メッシュと合成データを確認中です。');
  try {
    const data = await loadStage20GuiData({
      signal: state.loadController.signal,
      onProgress: progressLabel,
    });
    state.data = data;
    state.runtimeCapabilities = data.runtimeCapabilities;
    state.geometry = prepareGeometry(data);
    state.syntheticData = data;
    state.syntheticGeometry = state.geometry;
    elements.canvas.dataset.guiIntegrationStatus = data.metadata.guiIntegrationStatus;
    elements.canvas.dataset.runtimeCapabilityContract =
      data.metadata.runtimeCapabilityContractSchema;
    elements.canvas.dataset.runtimeCapabilityContractStatus =
      data.metadata.runtimeCapabilityContractStatus;
    const syntheticCapability = runtimeCapabilityForGuiMode('synthetic');
    if (!syntheticCapability) throw new Error('synthetic runtime capability is missing');
    elements.canvas.dataset.runtimeCapabilityMode = syntheticCapability.id;
    elements.canvas.dataset.runtimeExecutionKind = syntheticCapability.executionKind;
    elements.canvas.dataset.runtimeGateEffect = syntheticCapability.gateEffect;
    elements.canvas.dataset.runtimeRiverTideBoundaryPhysics =
      syntheticCapability.riverTideBoundaryPhysics;
    elements.canvas.dataset.runtimeFishwayRepresentation =
      syntheticCapability.fishwayRepresentation;
    elements.canvas.dataset.runtimeFieldPrediction = 'false';
    elements.canvas.dataset.runtimeOperationalFishingAdvice = 'false';
    elements.canvas.dataset.runtimeSafetyAuthority = 'false';
    elements.canvas.dataset.runtimePublicRuntime = 'false';
    elements.canvas.dataset.guiIntegrationState = data.metadata.guiIntegrationState;
    elements.canvas.dataset.guiIntegrationManifestSha256 = data.metadata.guiIntegrationManifestSha256;
    elements.canvas.dataset.readinessIntegrationStatus = data.metadata.readinessGuiIntegrationStatus;
    elements.canvas.dataset.readinessIntegrationState = data.metadata.readinessGuiIntegrationState;
    elements.canvas.dataset.readinessIntegrationManifestSha256 =
      data.metadata.readinessGuiIntegrationSha256;
    elements.canvas.dataset.contractRecoveryIntegrationStatus =
      data.metadata.contractRecoveryGuiIntegrationStatus;
    elements.canvas.dataset.contractRecoveryIntegrationState =
      data.metadata.contractRecoveryGuiIntegrationState;
    elements.canvas.dataset.contractRecoveryIntegrationManifestSha256 =
      data.metadata.contractRecoveryGuiIntegrationSha256;
    elements.canvas.dataset.contractAuditStatus = data.metadata.contractAuditStatus;
    elements.canvas.dataset.contractAuditErrors =
      String(data.metadata.contractAuditErrorCount);
    elements.canvas.dataset.contractAuditWarnings =
      String(data.metadata.contractAuditWarningCount);
    elements.canvas.dataset.recoveryBundleVerification =
      data.metadata.recoveryBundleVerificationStatus;
    elements.canvas.dataset.physicalValidation =
      data.metadata.physicalValidationPlanStatus;
    elements.canvas.dataset.readinessPackageSha256 = data.metadata.readinessPackageSha256;
    elements.canvas.dataset.boundaryImpactClassification =
      data.metadata.boundaryImpactClassification;
    elements.canvas.dataset.gateInputDrivesDisplayedFlow =
      String(data.metadata.gateInputDrivesDisplayedFlow);
    elements.canvas.dataset.resultProvenanceClassification =
      data.metadata.currentFlowProvenanceClassification;
    elements.canvas.dataset.gatePositionSource = 'gate-reference-anchor-authority-v2';
    elements.canvas.dataset.gateAnchorSemantics = data.metadata.gateReferenceAnchorSemantics;
    elements.canvas.dataset.gateReferenceAnchorsApproved = String(data.metadata.gateReferenceAnchorApprovedCount);
    elements.canvas.dataset.gatePhotoVisibleEndpointsApproved =
      String(data.metadata.gatePhotoVisibleEndpointApprovedCount);
    elements.canvas.dataset.gatePhotoVisibleOverlay = data.metadata.gatePhotoVisibleEndpointGuiRole;
    elements.canvas.dataset.gatePhotoVisiblePhysicalMeshUseAuthorized =
      String(data.metadata.gatePhotoVisibleEndpointPhysicalMeshUseAuthorized);
    elements.canvas.dataset.gateModelOpeningWidthMetres = String(data.metadata.mainGateModelOpeningWidthM);
    elements.canvas.dataset.gateGeographicWidthLine = 'not-rendered';
    elements.canvas.dataset.gatePhysicalMeshSelected = String(data.metadata.mainGatePhysicalMeshSelected);
    elements.canvas.dataset.gateSolverConnected = String(data.metadata.mainGateSolverConnected);
    elements.canvas.dataset.gateResponsePackConnected = String(data.metadata.mainGateResponsePackConnected);
    elements.canvas.dataset.fishwaySeparated = 'true';
    state.snapshotMaximumSpeeds = new Float64Array(data.metadata.snapshotCount);
    state.snapshotMaximumSpeeds.fill(Number.NaN);
    state.snapshotIndex = PRESENT_INDEX;
    elements.slider.max = String(data.metadata.snapshotCount - 1);
    elements.slider.value = String(PRESENT_INDEX);
    elements.canvas.dataset.dataMode = 'synthetic-prototype';
    elements.canvas.dataset.R1CReplayReadOnly = 'false';
    elements.canvas.dataset.R1CReplayUncalibrated = 'false';
    elements.canvas.dataset.referenceV2FixedS4 = 'false';
    elements.canvas.dataset.referenceV2Prediction = 'false';
    elements.canvas.dataset.referenceV2InputDriven = 'false';
    state.gateObservationIoState = 'ready';
    state.gateObservationIoMessage =
      '観測schema検証済み。JSONの読込・DLはこのブラウザ内だけで処理します。';
    state.contractRecoveryDownloadState = 'ready';
    state.contractRecoveryDownloadMessage =
      'summary検証済み。大容量成果物は未読込です。必要なものだけSHA検証してDLできます。';
    syncDataModeButtons('synthetic');
    syncIntegrationInterface();
    setPhase('ready', '表示準備が完了しました', '地図を操作できます。');
    syncInterface();
    scheduleRender();
    if (staticReviewMode) {
      state.localCapabilities = null;
      state.localServiceState = 'unavailable';
      state.localServiceMessage =
        '公開閲覧版では物理計算を実行しません。保存済み結果だけを表示します。';
      state.forcingCapabilities = null;
      state.forcingServiceState = 'unavailable';
      state.forcingServiceMessage =
        '公開閲覧版では気象庁CSVを処理しません。ローカル実動版を使用してください。';
      syncLocalSimulatorInterface();
      syncForcingInterface();
    } else {
      probeLocalSimulator();
      probeForcingIntegrationService();
    }
  } catch (error) {
    if (error?.name === 'AbortError') return;
    console.error(error);
    setPhase(
      'error',
      '表示データを読み込めませんでした',
      'ローカルHTTPサーバーから開いているか確認し、もう一度お試しください。' + (error?.message ? '（' + error.message + '）' : ''),
    );
  }
}

async function loadApplication() {
  try {
    await loadApplicationUnchecked();
  } catch (error) {
    if (error?.name === 'AbortError') return;
    console.error(error);
    setPhase(
      'error',
      '表示データを読み込めませんでした',
      '画面の初期化に失敗しました。ページを再読み込みしてください。' + (error?.message ? '（' + error.message + '）' : ''),
    );
  }
}

function barycentric(px, py, a, b, c) {
  const denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
  if (Math.abs(denominator) < 1e-15) return null;
  const u = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / denominator;
  const v = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / denominator;
  return [u, v, 1 - u - v];
}

function pointInTriangle(px, py, ax, ay, bx, by, cx, cy) {
  const denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
  if (Math.abs(denominator) < 1e-15) return false;
  const u = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denominator;
  const v = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denominator;
  const w = 1 - u - v;
  return u >= -1e-7 && v >= -1e-7 && w >= -1e-7;
}

function piecewiseMap(x, y, mesh, sourceKey, targetKey) {
  const anchors = mesh.anchors;
  for (const triangle of mesh.triangles) {
    const a = anchors[triangle[0]][sourceKey];
    const b = anchors[triangle[1]][sourceKey];
    const c = anchors[triangle[2]][sourceKey];
    const weights = barycentric(x, y, a, b, c);
    if (!weights || Math.min(...weights) < -1e-7 || Math.max(...weights) > 1 + 1e-7) continue;
    const targets = triangle.map(index => anchors[index][targetKey]);
    return [
      weights[0] * targets[0][0] + weights[1] * targets[1][0] + weights[2] * targets[2][0],
      weights[0] * targets[0][1] + weights[1] * targets[1][1] + weights[2] * targets[2][1],
    ];
  }
  return [x, y];
}

function imageToWorld(x, y, geographic, zoom) {
  const source = piecewiseMap(
    x,
    y,
    geographic.controlMesh,
    'targetImagePixel',
    'sourceBasePixel',
  );
  const transform = geographic.transform;
  const worldX = transform.tx + transform.a * source[0] - transform.b * source[1];
  const worldY = transform.ty + transform.b * source[0] + transform.a * source[1];
  const lon = worldX / CIRCUMFERENCE_M * 360 - 180;
  const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * worldY / CIRCUMFERENCE_M))) * 180 / Math.PI;
  return lonLatToWorld(lon, lat, zoom);
}

function lonLatToWorld(longitude, latitude, zoom) {
  const scale = TILE_SIZE * 2 ** zoom;
  return [
    (longitude + 180) / 360 * scale,
    (1 - Math.asinh(Math.tan(latitude * Math.PI / 180)) / Math.PI) / 2 * scale,
  ];
}

function projectMesh(mesh, geographic, zoom) {
  const imageVertices = mesh.arrays.vertex_image_millipixel;
  const geographicVertices = mesh.arrays.vertex_lonlat;
  const triangles = mesh.arrays.triangles;
  const sourceVertices = geographicVertices || imageVertices;
  if (!sourceVertices) throw new Error('メッシュ座標がありません。');
  const vertexCount = sourceVertices.length / 2;
  const cellCount = triangles.length / 3;
  const vertices = new Float64Array(vertexCount * 2);
  const centres = new Float64Array(cellCount * 2);
  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    const world = geographicVertices
      ? lonLatToWorld(
        geographicVertices[vertex * 2],
        geographicVertices[vertex * 2 + 1],
        zoom,
      )
      : imageToWorld(
        imageVertices[vertex * 2] / 1000,
        imageVertices[vertex * 2 + 1] / 1000,
        geographic,
        zoom,
      );
    vertices[vertex * 2] = world[0];
    vertices[vertex * 2 + 1] = world[1];
  }
  for (let cell = 0; cell < cellCount; cell += 1) {
    const a = triangles[cell * 3];
    const b = triangles[cell * 3 + 1];
    const c = triangles[cell * 3 + 2];
    centres[cell * 2] = (vertices[a * 2] + vertices[b * 2] + vertices[c * 2]) / 3;
    centres[cell * 2 + 1] = (vertices[a * 2 + 1] + vertices[b * 2 + 1] + vertices[c * 2 + 1]) / 3;
  }
  return { vertices, centres };
}

function calculateAreas(mesh) {
  const verticesM = mesh.arrays.vertices_m;
  const local = verticesM || mesh.arrays.vertex_local_mm;
  const divisor = verticesM ? 1 : 1000;
  const triangles = mesh.arrays.triangles;
  const areas = new Float32Array(triangles.length / 3);
  for (let cell = 0; cell < areas.length; cell += 1) {
    const a = triangles[cell * 3];
    const b = triangles[cell * 3 + 1];
    const c = triangles[cell * 3 + 2];
    const ax = local[a * 2] / divisor;
    const ay = local[a * 2 + 1] / divisor;
    const bx = local[b * 2] / divisor;
    const by = local[b * 2 + 1] / divisor;
    const cx = local[c * 2] / divisor;
    const cy = local[c * 2 + 1] / divisor;
    areas[cell] = Math.abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2;
  }
  return areas;
}

function averagePoints(points) {
  const total = points.reduce((sum, point) => [sum[0] + point[0], sum[1] + point[1]], [0, 0]);
  return [total[0] / points.length, total[1] / points.length];
}

function prepareGeometry(data) {
  const mesh = data.mesh;
  const geographic = data.waterManifest.coordinateSystem.geographic;
  const projections = new Map([
    [16, projectMesh(mesh, geographic, 16)],
    [18, projectMesh(mesh, geographic, 18)],
  ]);
  const areas = calculateAreas(mesh);
  const fishwayCells = mesh.arrays.fishway_cells;
  const special = {};

  for (const zoom of [16, 18]) {
    const projection = projections.get(zoom);
    const gateReferenceAnchors = data.gateReferenceAnchors
      .map(anchor => lonLatToWorld(anchor.longitude, anchor.latitude, zoom));
    if (!gateReferenceAnchors.every((point, index) => index === 0 || point[0] > gateReferenceAnchors[index - 1][0])) {
      throw new Error('水門参照アンカーが西から東へA1〜A8の順に並んでいません。');
    }
    if (data.metadata.gateReferenceAnchorSemantics !== 'reference_anchor_not_exact_geometric_center') {
      throw new Error('水門参照アンカーの意味論が変わっています。');
    }
    if (data.metadata.mainGateModelOpeningWidthM !== 46.5
      || data.metadata.mainGateModelWidthIsGeographicPositionLine !== false) {
      throw new Error('46.5mモデル開口幅を地理的な実位置線として扱わない契約が変わっています。');
    }
    if (data.metadata.gatePhotoVisibleSpanApprovedCount !== 8
      || data.metadata.gatePhotoVisibleEndpointApprovedCount !== 16
      || data.metadata.gatePhotoVisibleEndpointPhysicalMeshUseAuthorized !== false) {
      throw new Error('写真可視端点16/16を物理メッシュ採用と分離する表示契約が変わっています。');
    }
    if (data.metadata.mainGatePhysicalMeshSelected !== false
      || data.metadata.mainGateSolverConnected !== false
      || data.metadata.mainGateResponsePackConnected !== false
      || data.metadata.mainGatePrecomputationAuthorized !== false) {
      throw new Error('水門の物理採用または計算接続は承認されていません。');
    }
    const gatePhotoVisibleSpans = data.gatePhotoVisibleSpans.map(span => (
      span.coordinates.map(coordinate => lonLatToWorld(
        coordinate.longitude,
        coordinate.latitude,
        zoom,
      ))
    ));
    const fishwayCoordinateCenter = lonLatToWorld(
      data.fishwayCenter.longitude,
      data.fishwayCenter.latitude,
      zoom,
    );
    const fishwayPoints = Array.from(fishwayCells, cell => [
      projection.centres[cell * 2],
      projection.centres[cell * 2 + 1],
    ]);
    special[zoom] = {
      barrageCenter: averagePoints(gateReferenceAnchors),
      gateReferenceAnchors,
      gatePhotoVisibleSpans,
      fishwayPoints,
      fishwayCenter: fishwayCoordinateCenter,
      confluenceCenter: imageToWorld(1168, 441, geographic, zoom),
    };
  }

  const views = {};
  for (const spec of Object.values(VIEW_SPECS)) {
    const projection = projections.get(spec.zoom);
    let origin;
    let size;
    if (spec.cropSize) {
      const center = special[spec.zoom][spec.centerKind + 'Center'];
      size = [...spec.cropSize];
      origin = [center[0] - size[0] / 2, center[1] - size[1] / 2];
    } else {
      const box = spec.tileBox;
      origin = [box[0] * TILE_SIZE, box[1] * TILE_SIZE];
      size = [(box[2] - box[0] + 1) * TILE_SIZE, (box[3] - box[1] + 1) * TILE_SIZE];
    }
    const visible = [];
    for (let cell = 0; cell < data.metadata.cellCount; cell += 1) {
      const x = projection.centres[cell * 2];
      const y = projection.centres[cell * 2 + 1];
      if (x >= origin[0] && x <= origin[0] + size[0] && y >= origin[1] && y <= origin[1] + size[1]) {
        visible.push(cell);
      }
    }
    views[spec.id] = {
      ...spec,
      projection,
      origin,
      size,
      visible: Int32Array.from(visible),
      special: special[spec.zoom],
    };
  }
  return { areas, projections, special, views };
}

function resizeCanvas() {
  const rect = elements.canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const pixelWidth = Math.round(width * dpr);
  const pixelHeight = Math.round(height * dpr);
  if (elements.canvas.width !== pixelWidth || elements.canvas.height !== pixelHeight) {
    elements.canvas.width = pixelWidth;
    elements.canvas.height = pixelHeight;
  }
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { width, height, dpr };
}

function makeTransform(view, width, height) {
  const scale = Math.min(width / view.size[0], height / view.size[1]);
  const drawWidth = view.size[0] * scale;
  const drawHeight = view.size[1] * scale;
  const offsetX = (width - drawWidth) / 2;
  const offsetY = (height - drawHeight) / 2;
  return {
    scale,
    offsetX,
    offsetY,
    x: worldX => (worldX - view.origin[0]) * scale + offsetX,
    y: worldY => (worldY - view.origin[1]) * scale + offsetY,
  };
}

function drawPlaceholderGrid(width, height) {
  const gradient = context.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, '#112b35');
  gradient.addColorStop(1, '#07141c');
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);
  context.strokeStyle = 'rgba(130, 190, 204, .07)';
  context.lineWidth = 1;
  for (let x = 0; x < width; x += 48) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  for (let y = 0; y < height; y += 48) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }
}

function tileImage(zoom, x, y) {
  const key = zoom + '/' + x + '/' + y;
  if (state.tileCache.has(key)) return state.tileCache.get(key);
  const record = { image: new Image(), status: 'loading' };
  record.image.decoding = 'async';
  record.image.addEventListener('load', () => {
    record.status = 'ready';
    scheduleRender();
  });
  record.image.addEventListener('error', () => {
    record.status = 'failed';
  });
  record.image.src = './data/external/gsi/seamlessphoto/z' + zoom + '/' + x + '-' + y + '.jpg';
  state.tileCache.set(key, record);
  return record;
}

function drawBackground(view, transform, width, height) {
  drawPlaceholderGrid(width, height);
  const x0 = Math.max(view.tileBox[0], Math.floor(view.origin[0] / TILE_SIZE));
  const y0 = Math.max(view.tileBox[1], Math.floor(view.origin[1] / TILE_SIZE));
  const x1 = Math.min(view.tileBox[2], Math.floor((view.origin[0] + view.size[0]) / TILE_SIZE));
  const y1 = Math.min(view.tileBox[3], Math.floor((view.origin[1] + view.size[1]) / TILE_SIZE));
  context.save();
  context.filter = 'saturate(.72) brightness(.68) contrast(1.08)';
  for (let y = y0; y <= y1; y += 1) {
    for (let x = x0; x <= x1; x += 1) {
      const record = tileImage(view.zoom, x, y);
      if (record.status !== 'ready') continue;
      const left = transform.x(x * TILE_SIZE);
      const top = transform.y(y * TILE_SIZE);
      const size = TILE_SIZE * transform.scale + 0.7;
      context.drawImage(record.image, left, top, size, size);
    }
  }
  context.restore();
  context.fillStyle = 'rgba(3, 18, 25, .17)';
  context.fillRect(0, 0, width, height);
}

function interpolatePalette(palette, value) {
  const x = clamp(value, 0, 1) * (palette.length - 1);
  const index = Math.min(palette.length - 2, Math.floor(x));
  const amount = x - index;
  return palette[index].map((channel, channelIndex) =>
    Math.round(channel + (palette[index + 1][channelIndex] - channel) * amount),
  );
}

function colourCss(palette, value, alpha) {
  const colour = interpolatePalette(palette, value);
  return 'rgba(' + colour[0] + ',' + colour[1] + ',' + colour[2] + ',' + alpha + ')';
}

function renderCells(view, transform, snapshot) {
  const triangles = state.data.mesh.arrays.triangles;
  const vertices = view.projection.vertices;
  const binCount = 15;
  const paths = Array.from({ length: binCount }, () => new Path2D());
  const maximumSpeedLayer = isMaximumSpeedLayer();
  const speedLayer = state.layer === 'speed' || maximumSpeedLayer;
  const palette = speedLayer ? SPEED_PALETTE : DEPTH_PALETTE;
  const minimum = speedLayer ? 0 : state.data.diagnostics.minimumDepthM;
  const maximum = speedLayer
    ? Math.max(state.data.diagnostics.maximumSpeedMPS, 1e-6)
    : Math.max(state.data.diagnostics.maximumDepthM, minimum + 1e-6);

  for (const cell of view.visible) {
    const value = maximumSpeedLayer
      ? state.data.replay.maximumSpeedMPSByCell[cell]
      : state.layer === 'speed'
        ? Math.hypot(snapshot.eastVelocityMPS[cell], snapshot.northVelocityMPS[cell])
        : snapshot.depthM[cell];
    const normalized = clamp((value - minimum) / (maximum - minimum), 0, 1);
    const bin = Math.min(binCount - 1, Math.floor(normalized * binCount));
    const path = paths[bin];
    const a = triangles[cell * 3];
    const b = triangles[cell * 3 + 1];
    const c = triangles[cell * 3 + 2];
    path.moveTo(transform.x(vertices[a * 2]), transform.y(vertices[a * 2 + 1]));
    path.lineTo(transform.x(vertices[b * 2]), transform.y(vertices[b * 2 + 1]));
    path.lineTo(transform.x(vertices[c * 2]), transform.y(vertices[c * 2 + 1]));
    path.closePath();
  }
  context.save();
  context.globalCompositeOperation = 'source-over';
  for (let bin = 0; bin < binCount; bin += 1) {
    context.fillStyle = colourCss(palette, (bin + 0.5) / binCount, speedLayer ? 0.64 : 0.7);
    context.fill(paths[bin]);
  }
  context.restore();
}

function renderLandAuditOverlay(view, transform) {
  if (!isMaximumSpeedLayer()) return;
  const outsideCells = state.data.replay?.landAudit?.outsideWaterCentroidCellIds;
  if (!outsideCells?.length) return;
  const triangles = state.data.mesh.arrays.triangles;
  const vertices = view.projection.vertices;
  context.save();
  context.fillStyle = 'rgba(255, 0, 190, .78)';
  context.strokeStyle = 'rgba(255, 255, 255, .98)';
  context.lineWidth = 1.5;
  context.shadowColor = 'rgba(255, 0, 190, .9)';
  context.shadowBlur = 5;
  for (const cell of outsideCells) {
    const a = triangles[cell * 3];
    const b = triangles[cell * 3 + 1];
    const c = triangles[cell * 3 + 2];
    context.beginPath();
    context.moveTo(transform.x(vertices[a * 2]), transform.y(vertices[a * 2 + 1]));
    context.lineTo(transform.x(vertices[b * 2]), transform.y(vertices[b * 2 + 1]));
    context.lineTo(transform.x(vertices[c * 2]), transform.y(vertices[c * 2 + 1]));
    context.closePath();
    context.fill();
    context.stroke();
  }
  context.restore();
}

function renderR1CBoundary(view, transform) {
  const edges = state.data.mesh.arrays.boundary_edges;
  if (!isR1CMode() || !edges) return;
  const vertices = view.projection.vertices;
  context.save();
  context.beginPath();
  for (let index = 0; index < edges.length; index += 2) {
    const left = edges[index];
    const right = edges[index + 1];
    context.moveTo(
      transform.x(vertices[left * 2]),
      transform.y(vertices[left * 2 + 1]),
    );
    context.lineTo(
      transform.x(vertices[right * 2]),
      transform.y(vertices[right * 2 + 1]),
    );
  }
  context.strokeStyle = 'rgba(255, 255, 255, .94)';
  context.lineWidth = 1.5;
  context.shadowColor = 'rgba(3, 18, 25, .9)';
  context.shadowBlur = 4;
  context.stroke();
  context.restore();
}

function drawArrow(x, y, east, north, speed, maximum) {
  const magnitude = Math.hypot(east, north);
  if (magnitude <= 1e-12) return;
  const ux = east / magnitude;
  const uy = -north / magnitude;
  const length = 12 + 28 * Math.min(speed / Math.max(maximum, 1e-12), 1);
  const endX = x + ux * length;
  const endY = y + uy * length;
  const angle = Math.atan2(uy, ux);
  const wing = Math.max(5, length * 0.24);
  context.save();
  context.lineCap = 'round';
  context.lineJoin = 'round';
  for (const [colour, width] of [['rgba(4, 15, 21, .88)', 5], ['rgba(255, 255, 255, .94)', 2]]) {
    context.strokeStyle = colour;
    context.lineWidth = width;
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(endX, endY);
    context.moveTo(endX, endY);
    context.lineTo(endX + Math.cos(angle + 2.55) * wing, endY + Math.sin(angle + 2.55) * wing);
    context.moveTo(endX, endY);
    context.lineTo(endX + Math.cos(angle - 2.55) * wing, endY + Math.sin(angle - 2.55) * wing);
    context.stroke();
  }
  context.restore();
}

function renderArrows(view, transform, snapshot, width) {
  if (!state.arrows || isMaximumSpeedLayer()) return;
  const centres = view.projection.centres;
  const areas = state.geometry.areas;
  const binPixels = width < 650 ? 58 : 72;
  const bins = new Map();
  for (const cell of view.visible) {
    const x = transform.x(centres[cell * 2]);
    const y = transform.y(centres[cell * 2 + 1]);
    const key = Math.floor(x / binPixels) + ':' + Math.floor(y / binPixels);
    const depth = snapshot.depthM[cell];
    const weight = Math.max(depth * areas[cell], 1e-9);
    let item = bins.get(key);
    if (!item) {
      item = { x: 0, y: 0, east: 0, north: 0, weight: 0 };
      bins.set(key, item);
    }
    const east = snapshot.eastVelocityMPS[cell];
    const north = snapshot.northVelocityMPS[cell];
    item.x += x * weight;
    item.y += y * weight;
    item.east += east * weight;
    item.north += north * weight;
    item.weight += weight;
  }
  const maximum = Math.max(state.data.diagnostics.maximumSpeedMPS, 1e-6);
  for (const item of bins.values()) {
    const east = item.east / item.weight;
    const north = item.north / item.weight;
    const speed = Math.hypot(east, north);
    if (speed < Math.max(0.004, maximum * 0.012)) continue;
    drawArrow(
      item.x / item.weight,
      item.y / item.weight,
      east,
      north,
      speed,
      maximum,
    );
  }
}

function labelBox(text, x, y, align = 'left') {
  context.save();
  context.font = '700 12px \"Hiragino Sans\", \"Yu Gothic\", sans-serif';
  const paddingX = 9;
  const width = context.measureText(text).width + paddingX * 2;
  const height = 28;
  const left = align === 'right' ? x - width : align === 'center' ? x - width / 2 : x;
  context.fillStyle = 'rgba(5, 21, 29, .86)';
  context.strokeStyle = 'rgba(223, 245, 249, .32)';
  context.lineWidth = 1;
  context.beginPath();
  context.roundRect(left, y, width, height, 7);
  context.fill();
  context.stroke();
  context.fillStyle = '#f0fbfd';
  context.textBaseline = 'middle';
  context.fillText(text, left + paddingX, y + height / 2 + 0.5);
  context.restore();
}

function drawPointMarker(point, transform, colour, label, options = {}) {
  const x = transform.x(point[0]);
  const y = transform.y(point[1]);
  context.save();
  context.beginPath();
  context.arc(x, y, 7, 0, Math.PI * 2);
  context.fillStyle = colour;
  context.fill();
  context.lineWidth = 2.5;
  context.strokeStyle = '#fff';
  context.stroke();
  context.restore();
  labelBox(
    label,
    x + (options.labelOffsetX ?? 12),
    y + (options.labelOffsetY ?? -14),
    options.labelAlign ?? 'left',
  );
}

function drawGateInputBadge(
  point,
  transform,
  gateNumber,
  gateStatus,
  inputMode,
  capacity = null,
) {
  const x = transform.x(point[0]);
  const lineY = transform.y(point[1]);
  const top = lineY - 50;
  const replayMode = inputMode === 'replay';
  const fill = replayMode
    ? gateStatus === 'open' ? '#4faedb' : '#172a33'
    : gateStatus === 'open'
    ? inputMode === 'field' ? '#f4c65a' : '#57d8ed'
    : gateStatus === 'closed' ? '#172a33' : '#27424d';
  const text = replayMode ? '#f1fbff' : gateStatus === 'open' ? '#251900' : '#eef8fa';
  context.save();
  context.strokeStyle = replayMode
    ? gateStatus === 'open' ? 'rgba(90, 191, 239, .96)' : 'rgba(213, 235, 240, .5)'
    : gateStatus === 'open'
    ? inputMode === 'field' ? 'rgba(244, 198, 90, .88)' : 'rgba(87, 216, 237, .88)'
    : 'rgba(213, 235, 240, .5)';
  context.lineWidth = 1.5;
  context.beginPath();
  context.roundRect(x - 16, top, 32, 34, 8);
  context.fillStyle = fill;
  context.fill();
  context.stroke();
  context.fillStyle = text;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.font = '800 10px "Hiragino Sans", "Yu Gothic", sans-serif';
  context.fillText((replayMode ? '' : 'A') + gateNumber, x, top + 11);
  context.font = '800 8px "Hiragino Sans", "Yu Gothic", sans-serif';
  context.fillText(
    replayMode && Number.isFinite(capacity)
      ? Math.round(capacity * 100) + '%'
      : gateStatus === 'open' ? '開' : gateStatus === 'closed' ? '閉' : '未',
    x,
    top + 25,
  );
  context.beginPath();
  context.arc(x, lineY, 4.5, 0, Math.PI * 2);
  context.fillStyle = fill;
  context.fill();
  context.lineWidth = 1.5;
  context.strokeStyle = '#ffffff';
  context.stroke();
  context.restore();
}

function drawGateReferenceAnchor(point, transform, gateNumber) {
  const x = transform.x(point[0]);
  const y = transform.y(point[1]);
  context.save();
  context.beginPath();
  context.arc(x, y, 4.5, 0, Math.PI * 2);
  context.fillStyle = '#f4c65a';
  context.fill();
  context.lineWidth = 1.5;
  context.strokeStyle = '#ffffff';
  context.stroke();
  context.fillStyle = '#fff1bd';
  context.textAlign = 'center';
  context.textBaseline = 'top';
  context.font = '800 8px "Hiragino Sans", "Yu Gothic", sans-serif';
  context.fillText('A' + gateNumber, x, y + 7);
  context.restore();
}

function drawGatePhotoVisibleReviewSpans(spans, transform) {
  const replayMode = isR1CMode();
  context.save();
  context.lineCap = 'round';
  context.lineWidth = replayMode ? 3.5 : 2;
  context.strokeStyle = replayMode
    ? 'rgba(75, 177, 232, .98)'
    : 'rgba(126, 213, 151, .92)';
  context.fillStyle = replayMode ? '#68c5f2' : '#9ce8b1';
  if (replayMode) {
    context.setLineDash([]);
  } else {
    context.setLineDash([6, 4]);
  }
  for (const span of spans) {
    const [west, east] = span;
    context.beginPath();
    context.moveTo(transform.x(west[0]), transform.y(west[1]));
    context.lineTo(transform.x(east[0]), transform.y(east[1]));
    context.stroke();
    for (const endpoint of span) {
      context.beginPath();
      context.arc(transform.x(endpoint[0]), transform.y(endpoint[1]), 3.5, 0, Math.PI * 2);
      context.fill();
      context.lineWidth = 1;
      context.strokeStyle = '#ffffff';
      context.stroke();
      context.strokeStyle = replayMode
        ? 'rgba(75, 177, 232, .98)'
        : 'rgba(126, 213, 151, .92)';
    }
  }
  context.setLineDash([]);
  context.restore();
}

function renderGateInputOverlay(view, transform) {
  if (view.id !== 'barrage') return;
  const capacities = replayGateCapacities();
  const pattern = capacities || effectiveGatePattern();
  const hasPattern = pattern !== null;
  for (let gateIndex = 0; gateIndex < 8; gateIndex += 1) {
    const value = Number(pattern?.[gateIndex]);
    const status = !hasPattern ? 'unset' : value > 1e-6 ? 'open' : 'closed';
    drawGateInputBadge(
      view.special.gateReferenceAnchors[gateIndex],
      transform,
      gateIndex + 1,
      status,
      capacities ? 'replay' : state.gateInputMode,
      capacities ? value : null,
    );
  }
}

function renderMarkers(view, transform) {
  if (state.markers && view.marks.includes('barrage')) {
    drawGatePhotoVisibleReviewSpans(view.special.gatePhotoVisibleSpans, transform);
    if (view.id !== 'barrage') {
      for (let gateIndex = 0; gateIndex < 8; gateIndex += 1) {
        drawGateReferenceAnchor(view.special.gateReferenceAnchors[gateIndex], transform, gateIndex + 1);
      }
    }
    const center = view.special.barrageCenter;
    labelBox(
      isR1CMode()
        ? '青：実水門1〜8／白：R1C水面境界'
        : '写真端点16/16（レビュー用・物理未採用）',
      transform.x(center[0]),
      transform.y(center[1]) - (view.id === 'barrage' ? 88 : 35),
      'center',
    );
  }
  if (state.markers && view.marks.includes('confluence')) {
    drawPointMarker(view.special.confluenceCenter, transform, '#ed6f9f', '曲川・遠賀川合流部');
  }
  if (state.markers && view.marks.includes('fishway')) {
    drawPointMarker(view.special.fishwayCenter, transform, '#bd82d7', '魚道（提供座標）', {
      labelOffsetX: -10,
      labelOffsetY: 16,
      labelAlign: 'right',
    });
  }
  renderGateInputOverlay(view, transform);
}

function renderSelected(view, transform) {
  const cell = state.selectedCell;
  if (cell === null || !view.visible.includes(cell)) return;
  const triangles = state.data.mesh.arrays.triangles;
  const vertices = view.projection.vertices;
  const ids = [triangles[cell * 3], triangles[cell * 3 + 1], triangles[cell * 3 + 2]];
  context.save();
  context.beginPath();
  context.moveTo(transform.x(vertices[ids[0] * 2]), transform.y(vertices[ids[0] * 2 + 1]));
  context.lineTo(transform.x(vertices[ids[1] * 2]), transform.y(vertices[ids[1] * 2 + 1]));
  context.lineTo(transform.x(vertices[ids[2] * 2]), transform.y(vertices[ids[2] * 2 + 1]));
  context.closePath();
  context.strokeStyle = '#fff';
  context.lineWidth = 3;
  context.shadowColor = '#57d8ed';
  context.shadowBlur = 12;
  context.stroke();
  context.restore();
}

function renderMap() {
  state.renderQueued = false;
  try {
    const size = resizeCanvas();
    if (state.phase !== 'ready' || !state.data || !state.geometry) {
      drawPlaceholderGrid(size.width, size.height);
      return;
    }
    const view = state.geometry.views[state.viewId];
    const transform = makeTransform(view, size.width, size.height);
    const snapshot = state.data.snapshot(state.snapshotIndex);
    context.clearRect(0, 0, size.width, size.height);
    drawBackground(view, transform, size.width, size.height);
    renderCells(view, transform, snapshot);
    renderLandAuditOverlay(view, transform);
    renderR1CBoundary(view, transform);
    renderArrows(view, transform, snapshot, size.width);
    renderMarkers(view, transform);
    renderSelected(view, transform);
    state.lastRender = { view, transform, width: size.width, height: size.height };
  } catch (error) {
    state.lastRender = null;
    stopPlayback({ sync: false });
    console.error(error);
    setPhase(
      'error',
      '地図を描画できませんでした',
      'ブラウザの表示機能を確認し、もう一度お試しください。' + (error?.message ? '（' + error.message + '）' : ''),
    );
  }
}

function scheduleRender() {
  if (state.renderQueued) return;
  state.renderQueued = true;
  const flush = () => {
    if (state.renderQueued) renderMap();
  };
  requestAnimationFrame(flush);
  window.setTimeout(flush, 100);
}

function maximumSnapshotSpeed(snapshot, snapshotIndex) {
  const cached = state.snapshotMaximumSpeeds?.[snapshotIndex];
  if (Number.isFinite(cached)) return cached;
  let maximum = 0;
  for (let cell = 0; cell < state.data.metadata.cellCount; cell += 1) {
    maximum = Math.max(maximum, Math.hypot(snapshot.eastVelocityMPS[cell], snapshot.northVelocityMPS[cell]));
  }
  if (state.snapshotMaximumSpeeds) state.snapshotMaximumSpeeds[snapshotIndex] = maximum;
  return maximum;
}

function directionLabel(east, north) {
  const speed = Math.hypot(east, north);
  if (speed < 1e-6) return 'ほぼ静止';
  const bearing = (Math.atan2(east, north) * 180 / Math.PI + 360) % 360;
  const names = ['北', '北東', '東', '南東', '南', '南西', '西', '北西'];
  const name = names[Math.round(bearing / 45) % 8];
  return name + ' ' + Math.round(bearing) + '°';
}

function updateSelection(snapshot) {
  if (state.selectedCell === null) {
    elements.selectedCellId.textContent = '未選択';
    elements.emptySelection.hidden = false;
    elements.selectedValues.hidden = true;
    return;
  }
  const cell = state.selectedCell;
  const east = snapshot.eastVelocityMPS[cell];
  const north = snapshot.northVelocityMPS[cell];
  elements.selectedCellId.textContent = '#' + cell.toLocaleString('ja-JP');
  elements.emptySelection.hidden = true;
  elements.selectedValues.hidden = false;
  elements.selectedSpeed.textContent = formatNumber(
    isMaximumSpeedLayer()
      ? state.data.replay.maximumSpeedMPSByCell[cell]
      : Math.hypot(east, north),
    3,
    ' m/s',
  );
  elements.selectedDepth.textContent = formatNumber(snapshot.depthM[cell], 2, ' m');
  elements.selectedDirection.textContent = isMaximumSpeedLayer()
    ? '期間最大値のため方向なし'
    : directionLabel(east, north);
}

function syncInterface() {
  if (!state.data) return;
  const snapshot = state.data.snapshot(state.snapshotIndex);
  const inputs = state.data.inputs;
  const currentMaximum = maximumSnapshotSpeed(snapshot, state.snapshotIndex);
  const view = VIEW_SPECS[state.viewId];
  const R1CMode = isR1CMode();
  const localMode = isLocalPhysicsMode();
  const referenceV2Mode = isReferenceV2Mode();
  const N4P8dMode = isN4P8dMode();
  const maximumSpeedLayer = isMaximumSpeedLayer();
  elements.sideTime.textContent = formatDisplayTime(snapshot);
  elements.frameCount.textContent = (state.snapshotIndex + 1) + ' / ' + state.data.metadata.snapshotCount;
  elements.metricTideLabel.textContent = N4P8dMode
    ? 'M相対潮位'
    : R1CMode ? '上流P2水位' : '相対潮位';
  elements.metricBarrageLabel.textContent = N4P8dMode
    ? '保存時8門平均'
    : referenceV2Mode
    ? '固定S4能力倍率'
    : R1CMode
      ? '8門平均能力倍率'
      : '河口堰（合成開度）';
  elements.metricOngaLabel.textContent = R1CMode
    ? N4P8dMode
      ? 'O境界流量'
      : referenceV2Mode
      ? '魚道瞬時流量'
      : '魚道流量（モデル参考値）'
    : '遠賀川流量';
  elements.metricSpeedLabel.textContent = maximumSpeedLayer ? '36時間最大流速' : '最大流速';
  elements.metricTide.textContent = N4P8dMode
    ? formatNumber(inputs.tideRelativeM[state.snapshotIndex], 3, ' m')
    : referenceV2Mode
    ? state.data.displayValue('upstreamP2HeadM').displayTextJa
    : R1CMode
      ? formatNumber(state.data.replay.upstreamP2HeadM[state.snapshotIndex], 3, ' m')
    : formatNumber(inputs.tideRelativeM[state.snapshotIndex], 2, ' m');
  elements.metricBarrage.textContent =
    Math.round(inputs.barrageOpeningFraction[state.snapshotIndex] * 100)
      + (R1CMode ? '% 能力' : '% 開');
  elements.metricOnga.textContent = N4P8dMode
    ? formatNumber(inputs.ongaDischargeM3S[state.snapshotIndex], 1, ' m³/s')
    : referenceV2Mode
    ? state.data.displayValue('fishwayOutflowM3S').displayTextJa
    : R1CMode
      ? formatNumber(state.data.replay.fishwayOutflowM3S[state.snapshotIndex], 3, ' m³/s')
    : Math.round(inputs.ongaDischargeM3S[state.snapshotIndex]) + ' m³/s';
  elements.metricSpeed.textContent = formatNumber(
    maximumSpeedLayer ? state.data.diagnostics.maximumSpeedMPS : currentMaximum,
    2,
    ' m/s',
  );
  elements.sourceBadge.classList.toggle('is-r1c', R1CMode && !localMode);
  elements.sourceBadge.classList.toggle('is-local', localMode);
  elements.sourceBadge.innerHTML = localMode
    ? '<i></i> R1Cローカル物理／未較正'
    : N4P8dMode
      ? '<i></i> 承認済み36h／未較正・非予測'
    : referenceV2Mode
      ? '<i></i> 固定S4基準／未較正・非予測'
      : R1CMode
      ? '<i></i> R1C未較正診断／非予測'
      : '<i></i> 合成データ／非予測';
  elements.sourceBadge.setAttribute(
    'aria-label',
    localMode
      ? 'GUIの8門入力を反映したR1Cローカル物理計算。現地較正済みの流量予測ではありません'
      : N4P8dMode
        ? '数値検査とヒートマップ目視を通過した保存済み36時間計算。未較正で、予測や現地操作指示ではありません'
      : referenceV2Mode
        ? '固定S4基準リプレイ。未較正・モデル参考値で、予測ではなく、入力は表示流れを変更しません'
        : R1CMode
        ? 'R1C未較正診断リプレイ。現地流量の絶対再現や物理予測ではありません'
      : '合成データ。物理予測ではありません',
  );
  elements.dataModeStatus.classList.toggle(
    'is-error',
    state.R1CLoadState === 'error'
      || state.referenceV2LoadState === 'error'
      || state.N4P8dLoadState === 'error',
  );
  elements.dataModeStatus.textContent = localMode
    ? '今回の8門入力を反映したR1Cローカル物理計算を表示しています。'
    : N4P8dMode
      ? state.N4P8dLoadMessage
    : referenceV2Mode
      ? state.referenceV2LoadMessage
      : R1CMode
      ? 'R1C未較正診断リプレイを読み取り専用で表示しています。'
      : state.R1CLoadMessage;
  elements.dataModeNote.textContent = localMode
    ? '魚道流量は未較正のモデル参考値です。現地の絶対流量・将来予測としては使用できません。'
    : N4P8dMode
      ? '未較正・モデル参考値／ゼロ降雨条件／魚道等は簡易集約流路／保存済み37時点／予測・操作指示ではありません。'
    : referenceV2Mode
      ? '未較正・モデル参考値／固定S4基準リプレイ／予測ではありません／入力非駆動。瞬時値がない項目は「値なし」と表示します。'
      : R1CMode
      ? '保存済み診断値です。魚道流量は未較正のモデル参考値で、絶対再現・予測ではありません。'
      : '画面・操作の確認用に生成した値です。観測値や物理予測ではありません。';
  const sourceMode = localMode
    ? 'local'
    : N4P8dMode
      ? 'n4p8d'
      : referenceV2Mode
        ? 'reference-v2'
        : R1CMode
          ? 'r1c'
          : 'synthetic';
  if (elements.warningHud.dataset.sourceMode !== sourceMode) {
    elements.warningHud.dataset.sourceMode = sourceMode;
    elements.warningHudText.textContent = localMode
      ? 'ローカル物理計算（未較正・現地予測ではありません）'
      : N4P8dMode
        ? '保存済み36時間計算（未較正・予測ではありません）'
      : referenceV2Mode
        ? '固定S4基準リプレイ（未較正・予測ではありません）'
        : R1CMode
        ? '未較正の保存済み診断値（物理予測ではありません）'
        : '合成データ（物理計算未実行・予測ではありません）';
  }
  syncForcingInterface();
  syncGateInterface();
  elements.mapViewLabel.textContent = view.label;
  elements.mapTimeLabel.textContent = maximumSpeedLayer
    ? '36時間・全37時点の最大値'
    : formatDisplayTime(snapshot);
  elements.timelineCurrent.textContent = maximumSpeedLayer
    ? '全37時点'
    : formatDisplayTime(snapshot, true);
  elements.slider.value = String(state.snapshotIndex);
  elements.slider.setAttribute(
    'aria-valuetext',
    maximumSpeedLayer ? '全37時点の最大値' : formatDisplayTime(snapshot),
  );
  elements.previous.disabled = maximumSpeedLayer || state.snapshotIndex === 0;
  elements.next.disabled = maximumSpeedLayer
    || state.snapshotIndex === state.data.metadata.snapshotCount - 1;
  elements.now.disabled = maximumSpeedLayer || state.snapshotIndex === homeSnapshotIndex();
  elements.play.disabled = maximumSpeedLayer;
  elements.slider.disabled = maximumSpeedLayer;
  const replayIntervalS = referenceV2Mode || N4P8dMode
    ? Number(state.data.replay.absoluteTimeS[1] - state.data.replay.absoluteTimeS[0])
    : R1CMode
      ? Number(state.data.responseManifest.timeline.intervalS)
    : 3600;
  const replayEndS = referenceV2Mode || N4P8dMode
    ? Number(state.data.replay.absoluteTimeS[state.data.metadata.snapshotCount - 1])
    : R1CMode
      ? Number(state.data.responseManifest.timeline.absoluteEndS)
    : 0;
  const stepLabel = R1CMode ? formatReplayTime(replayIntervalS, true) : '1時間';
  elements.previous.textContent = R1CMode ? '−' + stepLabel : '−1h';
  elements.next.textContent = R1CMode ? '+' + stepLabel : '+1h';
  elements.previous.setAttribute('aria-label', R1CMode ? stepLabel + '戻る' : '1時間戻る');
  elements.next.setAttribute('aria-label', R1CMode ? stepLabel + '進む' : '1時間進む');
  elements.now.textContent = R1CMode ? '先頭へ' : '0時間へ';
  elements.timelineStart.textContent = referenceV2Mode || N4P8dMode
    ? formatReferenceTimestamp(state.data.replay.timestampsJst[0], true)
    : R1CMode
      ? '開始 0秒'
      : '12時間前';
  elements.timelineEnd.textContent = referenceV2Mode || N4P8dMode
    ? formatReferenceTimestamp(
      state.data.replay.timestampsJst[state.data.metadata.snapshotCount - 1],
      true,
    )
    : R1CMode
      ? '終了 ' + formatReplayTime(replayEndS, true)
    : '24時間後';
  const tickLabels = referenceV2Mode || N4P8dMode
    ? Array.from(
      { length: 7 },
      (_, index) => formatReferenceTimestamp(
        state.data.replay.timestampsJst[Math.round(
          (state.data.metadata.snapshotCount - 1) * index / 6,
        )],
        true,
      ),
    )
    : R1CMode
    ? Array.from(
      { length: 7 },
      (_, index) => formatReplayTime(replayEndS * index / 6, true),
    )
    : ['−12', '−6', '0', '+6', '+12', '+18', '+24'];
  elements.timelineTicks.forEach((element, index) => {
    element.textContent = tickLabels[index];
  });
  elements.play.classList.toggle('playing', state.playing);
  elements.playLabel.textContent = state.playing ? '停止' : '再生';
  elements.play.setAttribute('aria-label', state.playing ? '停止' : '再生');
  elements.legendTitle.textContent = maximumSpeedLayer ? '36時間最大流速' : state.layer === 'speed' ? '流速' : '水深';
  elements.legendMin.textContent = state.layer === 'speed' || maximumSpeedLayer
    ? '0'
    : formatNumber(state.data.diagnostics.minimumDepthM, 1, ' m');
  elements.legendMax.textContent = state.layer === 'speed' || maximumSpeedLayer
    ? formatNumber(state.data.diagnostics.maximumSpeedMPS, 2, ' m/s')
    : formatNumber(state.data.diagnostics.maximumDepthM, 1, ' m');
  elements.legendGradient.classList.toggle('speed-gradient', state.layer === 'speed' || maximumSpeedLayer);
  elements.legendGradient.classList.toggle('depth-gradient', state.layer === 'depth');
  elements.legendNote.textContent = maximumSpeedLayer
    ? '赤紫＋白枠：水域外中心19セル（最大離隔0.528m・目視許容済み）'
    : '白い矢印：流れの向き';
  elements.layerMaximumSpeed.disabled = !N4P8dMode;
  elements.layerMaximumSpeed.setAttribute('aria-disabled', String(!N4P8dMode));
  elements.arrowToggle.disabled = maximumSpeedLayer;
  elements.arrowNote.textContent = maximumSpeedLayer
    ? '期間最大値には一意な流向がないため非表示'
    : '水深×セル面積でまとめて表示';
  elements.detailPack.textContent = state.data.metadata.responsePackVersion;
  elements.detailTiming.textContent = formatNumber(state.data.timingsMs.synthesis, 1, ' ms');
  elements.detailMesh.textContent = R1CMode
    ? 'R1C / 37,724セル'
    : 'v2 / 50,199セル';
  elements.detailTime.textContent = referenceV2Mode || N4P8dMode
    ? formatReferenceTimestamp(state.data.replay.timestampsJst[0], false)
      + '〜'
      + formatReferenceTimestamp(
        state.data.replay.timestampsJst[state.data.metadata.snapshotCount - 1],
        false,
      )
      + ' / 1時間間隔'
    : R1CMode
      ? '0〜' + formatReplayTime(replayEndS, true) + ' / ' + stepLabel + '間隔'
    : '−12〜+24時間 / 1時間間隔';
  updateSelection(snapshot);
  for (const button of document.querySelectorAll('[data-layer]')) {
    const active = button.dataset.layer === state.layer;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  }
  for (const button of document.querySelectorAll('[data-view]')) {
    const active = button.dataset.view === state.viewId;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  }
}

function setSnapshotIndex(index, options = {}) {
  if (!state.data || isMaximumSpeedLayer()) return;
  state.snapshotIndex = clamp(Math.round(index), 0, state.data.metadata.snapshotCount - 1);
  if (options.fromPlayback !== true) stopPlayback({ sync: false });
  syncInterface();
  scheduleRender();
}

function stopPlayback(options = {}) {
  if (state.playTimer !== null) window.clearInterval(state.playTimer);
  state.playTimer = null;
  state.playing = false;
  if (state.data && options.sync !== false) syncInterface();
}

function togglePlayback() {
  if (!state.data || isMaximumSpeedLayer()) return;
  if (state.playing) {
    stopPlayback();
    return;
  }
  if (state.snapshotIndex >= state.data.metadata.snapshotCount - 1) return;
  state.playing = true;
  syncInterface();
  state.playTimer = window.setInterval(() => {
    if (state.snapshotIndex >= state.data.metadata.snapshotCount - 1) {
      stopPlayback();
      return;
    }
    const nextIndex = state.snapshotIndex + 1;
    setSnapshotIndex(nextIndex, { fromPlayback: true });
    if (nextIndex >= state.data.metadata.snapshotCount - 1) stopPlayback();
  }, 900);
}

function selectCellAtCanvasPoint(targetX, targetY) {
  if (!state.lastRender || !state.data) return;
  const { view, transform } = state.lastRender;
  const triangles = state.data.mesh.arrays.triangles;
  const vertices = view.projection.vertices;
  let bestCell = null;
  for (const cell of view.visible) {
    const a = triangles[cell * 3];
    const b = triangles[cell * 3 + 1];
    const c = triangles[cell * 3 + 2];
    if (pointInTriangle(
      targetX,
      targetY,
      transform.x(vertices[a * 2]),
      transform.y(vertices[a * 2 + 1]),
      transform.x(vertices[b * 2]),
      transform.y(vertices[b * 2 + 1]),
      transform.x(vertices[c * 2]),
      transform.y(vertices[c * 2 + 1]),
    )) {
      bestCell = cell;
      break;
    }
  }
  state.selectedCell = bestCell;
  syncInterface();
  scheduleRender();
}

function selectMapCell(event) {
  const rect = elements.canvas.getBoundingClientRect();
  selectCellAtCanvasPoint(event.clientX - rect.left, event.clientY - rect.top);
}

function bindEvents() {
  for (const button of document.querySelectorAll('[data-layer]')) {
    button.addEventListener('click', () => {
      if (button.dataset.layer === 'maximum-speed' && !isN4P8dMode()) return;
      if (button.dataset.layer === 'maximum-speed') stopPlayback({ sync: false });
      state.layer = button.dataset.layer;
      syncInterface();
      scheduleRender();
    });
  }
  for (const button of document.querySelectorAll('[data-view]')) {
    button.addEventListener('click', () => {
      state.viewId = button.dataset.view;
      state.selectedCell = null;
      syncInterface();
      scheduleRender();
    });
  }
  elements.arrowToggle.addEventListener('change', () => {
    state.arrows = elements.arrowToggle.checked;
    scheduleRender();
  });
  elements.markerToggle.addEventListener('change', () => {
    state.markers = elements.markerToggle.checked;
    scheduleRender();
  });
  elements.slider.addEventListener('input', event => setSnapshotIndex(Number(event.target.value)));
  elements.previous.addEventListener('click', () => setSnapshotIndex(state.snapshotIndex - 1));
  elements.next.addEventListener('click', () => setSnapshotIndex(state.snapshotIndex + 1));
  elements.now.addEventListener('click', () => setSnapshotIndex(homeSnapshotIndex()));
  elements.play.addEventListener('click', togglePlayback);
  elements.retry.addEventListener('click', loadApplication);
  elements.canvas.addEventListener('click', selectMapCell);
  elements.dataModeSynthetic.addEventListener('click', () => switchDataMode('synthetic'));
  elements.dataModeR1C.addEventListener('click', () => switchDataMode('r1c'));
  elements.dataModeReferenceV2.addEventListener(
    'click',
    () => switchDataMode('reference-v2'),
  );
  elements.dataModeN4P8d.addEventListener('click', () => switchDataMode('n4p8d'));
  elements.dataModeLocal.addEventListener('click', () => switchDataMode('local'));
  elements.localSimulationRun.addEventListener('click', runLocalSimulation);
  elements.localCalculationJump.addEventListener('click', () => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    elements.localSimulatorCard.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'center',
    });
    elements.localSimulatorCard.focus({ preventScroll: true });
  });
  elements.localReprobeButton.addEventListener('click', probeLocalSimulator);
  elements.forcingBuildButton.addEventListener('click', buildIntegratedForcingInput);
  elements.forcingReprobeButton.addEventListener('click', probeForcingIntegrationService);
  elements.forcingDate.addEventListener('input', () => {
    invalidateForcingInput(
      forcingDateIsAvailable()
        ? '日付が変更されました。対応する気象庁CSVを確認して、37時間入力を作り直してください。'
        : 'この日付に必要な保存済み潮位表がありません。表示された利用可能範囲を選んでください。',
    );
  });
  elements.forcingJmaCsv.addEventListener('change', () => {
    invalidateForcingInput(
      elements.forcingJmaCsv.files?.[0]
        ? 'CSVを選択しました。「37時間の入力を作る」を押してください。'
        : '気象庁CSVを選択してください。',
    );
  });
  elements.gateModeAuto.addEventListener('click', () => setGateMode('auto'));
  elements.gateModeField.addEventListener('click', () => setGateMode('field'));
  elements.gateSource.addEventListener('change', () => {
    state.gateObservationSource = elements.gateSource.value;
    syncGateInterface();
  });
  elements.gateObservedAt.addEventListener('input', () => {
    state.gateObservedAt = elements.gateObservedAt.value;
    syncGateInterface();
  });
  elements.gateObservationImportButton.addEventListener('click', () => {
    elements.gateObservationImportFile.click();
  });
  elements.gateObservationImportFile.addEventListener('change', event => {
    importGateObservationFile(event.target.files?.[0]);
  });
  elements.gateObservationExportButton.addEventListener(
    'click',
    downloadCurrentGateObservation,
  );
  elements.contractReportDownloadButton.addEventListener('click', () => {
    downloadContractRecoveryArtifact('contract_lint_report_v1');
  });
  elements.recoveryBundleDownloadButton.addEventListener('click', () => {
    downloadContractRecoveryArtifact('json_contract_recovery_bundle_v1');
  });
  elements.physicalValidationPlanDownloadButton.addEventListener('click', () => {
    downloadContractRecoveryArtifact('physical_validation_plan_v1');
  });
  elements.gateReturnAuto.addEventListener('click', () => setGateMode('auto'));
  for (const button of document.querySelectorAll('[data-gate]')) {
    button.addEventListener('click', () => {
      const levels = Array.from(effectiveGatePattern() || gatePatternForStage(0));
      const gateIndex = Number(button.dataset.gate);
      levels[gateIndex] = Number(levels[gateIndex]) > 0 ? 0 : 100;
      setGateObservation(levels);
    });
  }
  for (const button of document.querySelectorAll('[data-gate-preset]')) {
    button.addEventListener('click', () => {
      const preset = button.dataset.gatePreset;
      setGateObservation(GATE_PRESETS[preset]);
    });
  }
  elements.gateMapButton.addEventListener('click', () => {
    document.querySelector('[data-view="barrage"]').click();
    elements.mapSection.scrollIntoView({ block: 'start' });
  });
  window.addEventListener('keydown', event => {
    const target = event.target;
    if (target === elements.canvas && event.key === 'Enter') {
      event.preventDefault();
      const rect = elements.canvas.getBoundingClientRect();
      selectCellAtCanvasPoint(rect.width / 2, rect.height / 2);
      return;
    }
    if (target instanceof Element && target.closest('button, input, summary, a, select, textarea')) return;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setSnapshotIndex(state.snapshotIndex - 1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      setSnapshotIndex(state.snapshotIndex + 1);
    } else if (event.key === ' ') {
      event.preventDefault();
      togglePlayback();
    }
  });
  const observer = new ResizeObserver(scheduleRender);
  observer.observe(elements.frame);
  mobileLayout.addEventListener('change', syncResponsiveDocumentOrder);
}

syncGateInterface();
syncContractRecoveryInterface();
syncResponsiveDocumentOrder();
bindEvents();
activateBrowserContract();
loadApplication();
