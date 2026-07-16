import { loadStage20GuiData } from './onga_stage20_gui_data.mjs';

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
    marks: Object.freeze(['barrage']),
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

const byId = id => document.getElementById(id);
const elements = Object.freeze({
  app: byId('app-shell'),
  workspace: byId('workspace'),
  controlPanel: byId('control-panel'),
  mapSection: byId('map-section'),
  canvas: byId('flow-map'),
  frame: byId('map-frame'),
  loadStatus: byId('load-status'),
  overlayTitle: byId('overlay-title'),
  overlayMessage: byId('overlay-message'),
  retry: byId('retry-button'),
  sideTime: byId('side-time'),
  frameCount: byId('frame-count'),
  metricTide: byId('metric-tide'),
  metricBarrage: byId('metric-barrage'),
  metricOnga: byId('metric-onga'),
  metricSpeed: byId('metric-speed'),
  arrowToggle: byId('arrow-toggle'),
  markerToggle: byId('marker-toggle'),
  selectedCellId: byId('selected-cell-id'),
  emptySelection: byId('empty-selection'),
  selectedValues: byId('selected-values'),
  selectedSpeed: byId('selected-speed'),
  selectedDepth: byId('selected-depth'),
  selectedDirection: byId('selected-direction'),
  detailPack: byId('detail-pack'),
  detailTiming: byId('detail-timing'),
  mapViewLabel: byId('map-view-label'),
  mapTimeLabel: byId('map-time-label'),
  legendTitle: byId('legend-title'),
  legendMax: byId('legend-max'),
  legendMin: byId('legend-min'),
  legendGradient: byId('legend-gradient'),
  previous: byId('previous-button'),
  play: byId('play-button'),
  playLabel: byId('play-label'),
  next: byId('next-button'),
  now: byId('now-button'),
  slider: byId('time-slider'),
  timelineCurrent: byId('timeline-current'),
});

const context = elements.canvas.getContext('2d', { alpha: false });
const mobileLayout = window.matchMedia('(max-width: 760px)');
const state = {
  phase: 'loading',
  data: null,
  geometry: null,
  snapshotIndex: PRESENT_INDEX,
  viewId: 'estuary',
  layer: 'speed',
  arrows: true,
  markers: true,
  selectedCell: null,
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

function formatNumber(value, digits, suffix = '') {
  return Number.isFinite(value) ? value.toFixed(digits) + suffix : '—';
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
  elements.overlayTitle.textContent = title;
  elements.overlayMessage.textContent = message;
  elements.retry.hidden = phase !== 'error';
  const disabled = phase !== 'ready';
  for (const control of [elements.previous, elements.play, elements.next, elements.now, elements.slider]) {
    control.disabled = disabled;
  }
}

function progressLabel(stage) {
  if (stage === 'mesh-and-contracts') {
    setPhase('loading', '地図の形を読み込んでいます', 'メッシュv2とローカル背景、表示用データの組み合わせを確認中です。');
  } else if (stage === 'synthesis') {
    setPhase('loading', '37時点の表示データを作成中です', '合成応答パックをブラウザ内で展開しています。本計算は実行していません。');
  }
}

async function loadApplication() {
  stopPlayback();
  state.loadController?.abort();
  state.loadController = new AbortController();
  state.data = null;
  state.geometry = null;
  state.snapshotMaximumSpeeds = null;
  state.selectedCell = null;
  setPhase('loading', '表示データを準備しています', 'メッシュと合成データを確認中です。');
  try {
    const data = await loadStage20GuiData({
      signal: state.loadController.signal,
      onProgress: progressLabel,
    });
    state.data = data;
    state.geometry = prepareGeometry(data);
    state.snapshotMaximumSpeeds = new Float64Array(data.metadata.snapshotCount);
    state.snapshotMaximumSpeeds.fill(Number.NaN);
    state.snapshotIndex = PRESENT_INDEX;
    setPhase('ready', '表示準備が完了しました', '地図を操作できます。');
    syncInterface();
    scheduleRender();
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
  const scale = TILE_SIZE * 2 ** zoom;
  return [
    (lon + 180) / 360 * scale,
    (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * scale,
  ];
}

function projectMesh(mesh, geographic, zoom) {
  const imageVertices = mesh.arrays.vertex_image_millipixel;
  const triangles = mesh.arrays.triangles;
  const vertexCount = imageVertices.length / 2;
  const cellCount = triangles.length / 3;
  const vertices = new Float64Array(vertexCount * 2);
  const centres = new Float64Array(cellCount * 2);
  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    const world = imageToWorld(
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
  const local = mesh.arrays.vertex_local_mm;
  const triangles = mesh.arrays.triangles;
  const areas = new Float32Array(triangles.length / 3);
  for (let cell = 0; cell < areas.length; cell += 1) {
    const a = triangles[cell * 3];
    const b = triangles[cell * 3 + 1];
    const c = triangles[cell * 3 + 2];
    const ax = local[a * 2] / 1000;
    const ay = local[a * 2 + 1] / 1000;
    const bx = local[b * 2] / 1000;
    const by = local[b * 2 + 1] / 1000;
    const cx = local[c * 2] / 1000;
    const cy = local[c * 2 + 1] / 1000;
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
  const barrageFaces = mesh.arrays.barrage_face_ids;
  const internalFaceVertices = mesh.arrays.internal_face_vertices;
  const fishwayCells = mesh.arrays.fishway_cells;
  const special = {};

  for (const zoom of [16, 18]) {
    const projection = projections.get(zoom);
    const barrageSegments = [];
    const barragePoints = [];
    for (const faceId of barrageFaces) {
      const a = internalFaceVertices[faceId * 2];
      const b = internalFaceVertices[faceId * 2 + 1];
      const segment = [
        [projection.vertices[a * 2], projection.vertices[a * 2 + 1]],
        [projection.vertices[b * 2], projection.vertices[b * 2 + 1]],
      ];
      barrageSegments.push(segment);
      barragePoints.push(segment[0], segment[1]);
    }
    const fishwayPoints = Array.from(fishwayCells, cell => [
      projection.centres[cell * 2],
      projection.centres[cell * 2 + 1],
    ]);
    special[zoom] = {
      barrageSegments,
      barrageCenter: averagePoints(barragePoints),
      fishwayPoints,
      fishwayCenter: averagePoints(fishwayPoints),
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
  const palette = state.layer === 'speed' ? SPEED_PALETTE : DEPTH_PALETTE;
  const minimum = state.layer === 'speed' ? 0 : state.data.diagnostics.minimumDepthM;
  const maximum = state.layer === 'speed'
    ? Math.max(state.data.diagnostics.maximumSpeedMPS, 1e-6)
    : Math.max(state.data.diagnostics.maximumDepthM, minimum + 1e-6);

  for (const cell of view.visible) {
    const value = state.layer === 'speed'
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
    context.fillStyle = colourCss(palette, (bin + 0.5) / binCount, state.layer === 'speed' ? 0.64 : 0.7);
    context.fill(paths[bin]);
  }
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
  if (!state.arrows) return;
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
  const left = align === 'right' ? x - width : x;
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

function drawPointMarker(point, transform, colour, label) {
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
  labelBox(label, x + 12, y - 14);
}

function renderMarkers(view, transform) {
  if (!state.markers) return;
  if (view.marks.includes('barrage')) {
    context.save();
    context.strokeStyle = '#57d8ed';
    context.lineWidth = view.zoom === 18 ? 4 : 3;
    context.lineCap = 'round';
    context.beginPath();
    for (const segment of view.special.barrageSegments) {
      context.moveTo(transform.x(segment[0][0]), transform.y(segment[0][1]));
      context.lineTo(transform.x(segment[1][0]), transform.y(segment[1][1]));
    }
    context.stroke();
    context.restore();
    const center = view.special.barrageCenter;
    labelBox('河口堰', transform.x(center[0]) + 10, transform.y(center[1]) - 35);
  }
  if (view.marks.includes('confluence')) {
    drawPointMarker(view.special.confluenceCenter, transform, '#ed6f9f', '曲川・遠賀川合流部');
  }
  if (view.marks.includes('fishway')) {
    for (let index = 0; index < view.special.fishwayPoints.length; index += 1) {
      drawPointMarker(
        view.special.fishwayPoints[index],
        transform,
        '#f4c65a',
        index === 0 ? '魚道・上流側' : '魚道・河口側',
      );
    }
  }
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
  elements.selectedSpeed.textContent = formatNumber(Math.hypot(east, north), 3, ' m/s');
  elements.selectedDepth.textContent = formatNumber(snapshot.depthM[cell], 2, ' m');
  elements.selectedDirection.textContent = directionLabel(east, north);
}

function syncInterface() {
  if (!state.data) return;
  const snapshot = state.data.snapshot(state.snapshotIndex);
  const hour = snapshot.hour;
  const inputs = state.data.inputs;
  const currentMaximum = maximumSnapshotSpeed(snapshot, state.snapshotIndex);
  const view = VIEW_SPECS[state.viewId];
  elements.sideTime.textContent = formatHour(hour);
  elements.frameCount.textContent = (state.snapshotIndex + 1) + ' / ' + state.data.metadata.snapshotCount;
  elements.metricTide.textContent = formatNumber(inputs.tideRelativeM[state.snapshotIndex], 2, ' m');
  elements.metricBarrage.textContent = Math.round(inputs.barrageOpeningFraction[state.snapshotIndex] * 100) + '% 開';
  elements.metricOnga.textContent = Math.round(inputs.ongaDischargeM3S[state.snapshotIndex]) + ' m³/s';
  elements.metricSpeed.textContent = formatNumber(currentMaximum, 2, ' m/s');
  elements.mapViewLabel.textContent = view.label;
  elements.mapTimeLabel.textContent = formatHour(hour);
  elements.timelineCurrent.textContent = formatHour(hour, true);
  elements.slider.value = String(state.snapshotIndex);
  elements.slider.setAttribute('aria-valuetext', formatHour(hour));
  elements.previous.disabled = state.snapshotIndex === 0;
  elements.next.disabled = state.snapshotIndex === state.data.metadata.snapshotCount - 1;
  elements.now.disabled = state.snapshotIndex === PRESENT_INDEX;
  elements.play.classList.toggle('playing', state.playing);
  elements.playLabel.textContent = state.playing ? '停止' : '再生';
  elements.play.setAttribute('aria-label', state.playing ? '停止' : '再生');
  elements.legendTitle.textContent = state.layer === 'speed' ? '流速' : '水深';
  elements.legendMin.textContent = state.layer === 'speed'
    ? '0'
    : formatNumber(state.data.diagnostics.minimumDepthM, 1, ' m');
  elements.legendMax.textContent = state.layer === 'speed'
    ? formatNumber(state.data.diagnostics.maximumSpeedMPS, 2, ' m/s')
    : formatNumber(state.data.diagnostics.maximumDepthM, 1, ' m');
  elements.legendGradient.classList.toggle('speed-gradient', state.layer === 'speed');
  elements.legendGradient.classList.toggle('depth-gradient', state.layer === 'depth');
  elements.detailPack.textContent = state.data.metadata.responsePackVersion;
  elements.detailTiming.textContent = formatNumber(state.data.timingsMs.synthesis, 1, ' ms');
  updateSelection(snapshot);
  elements.canvas.setAttribute(
    'aria-label',
    view.label + 'の' + (state.layer === 'speed' ? '流速' : '水深') + '地図、' + formatHour(hour)
      + '。合成データで物理予測ではありません。Enterキーで中央地点を選択できます。',
  );
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
  if (!state.data) return;
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
  if (!state.data) return;
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
  elements.now.addEventListener('click', () => setSnapshotIndex(PRESENT_INDEX));
  elements.play.addEventListener('click', togglePlayback);
  elements.retry.addEventListener('click', loadApplication);
  elements.canvas.addEventListener('click', selectMapCell);
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

syncResponsiveDocumentOrder();
bindEvents();
loadApplication();
