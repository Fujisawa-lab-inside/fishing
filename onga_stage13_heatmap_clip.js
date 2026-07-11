(() => {
  'use strict';

  if (window.__ONGA_STAGE13_HEATMAP_CLIP_V1__) return;
  window.__ONGA_STAGE13_HEATMAP_CLIP_V1__ = true;

  const VERSION = 'stage13-heatmap-clip-v1';
  const diagnostics = {
    version: VERSION,
    installed: false,
    clipCalls: 0,
    maskBuilds: 0,
    triangleCount: 0,
    sourceWidth: 0,
    sourceHeight: 0,
    lastViewportWidth: 0,
    lastViewportHeight: 0,
  };

  let sourceMaskCanvas = null;
  let viewportMaskCanvas = null;
  let viewportMaskKey = '';
  let scratchCanvas = null;

  function assert(condition, message) {
    if (!condition) throw new Error(`[onga-stage13-heatmap-clip] ${message}`);
  }

  function setDataset(name, value) {
    if (typeof document === 'undefined' || !document.documentElement) return;
    document.documentElement.dataset[name] = String(value);
  }

  function getLegacyLatLngToCanvas() {
    try {
      if (typeof latLngToCanvas === 'function') return latLngToCanvas;
    } catch (_) {
      // Ignore missing lexical binding.
    }
    return typeof window.latLngToCanvas === 'function' ? window.latLngToCanvas : null;
  }

  function buildSourceMask(authority) {
    if (sourceMaskCanvas) return sourceMaskCanvas;
    const { width, height, mask } = authority.water;
    assert(Number.isInteger(width) && Number.isInteger(height), 'authority mask dimensions are invalid');
    assert(mask?.length === width * height, 'authority mask length is invalid');

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', { alpha: true });
    assert(context, 'source-mask 2D context is unavailable');
    const image = context.createImageData(width, height);
    const rgba = image.data;
    for (let index = 0; index < mask.length; index += 1) {
      if (mask[index] !== 1) continue;
      const offset = index * 4;
      rgba[offset] = 255;
      rgba[offset + 1] = 255;
      rgba[offset + 2] = 255;
      rgba[offset + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    sourceMaskCanvas = canvas;
    diagnostics.sourceWidth = width;
    diagnostics.sourceHeight = height;
    return canvas;
  }

  function affineFromTriangles(source, target) {
    const [s0, s1, s2] = source;
    const [t0, t1, t2] = target;
    const denominator = s0[0] * (s1[1] - s2[1])
      + s1[0] * (s2[1] - s0[1])
      + s2[0] * (s0[1] - s1[1]);
    assert(Math.abs(denominator) > 1e-12, 'control-mesh source triangle is degenerate');

    const coefficient = values => ({
      linearX: (
        values[0] * (s1[1] - s2[1])
        + values[1] * (s2[1] - s0[1])
        + values[2] * (s0[1] - s1[1])
      ) / denominator,
      linearY: (
        values[0] * (s2[0] - s1[0])
        + values[1] * (s0[0] - s2[0])
        + values[2] * (s1[0] - s0[0])
      ) / denominator,
      offset: (
        values[0] * (s1[0] * s2[1] - s2[0] * s1[1])
        + values[1] * (s2[0] * s0[1] - s0[0] * s2[1])
        + values[2] * (s0[0] * s1[1] - s1[0] * s0[1])
      ) / denominator,
    });

    const x = coefficient(target.map(point => point[0]));
    const y = coefficient(target.map(point => point[1]));
    return [x.linearX, y.linearX, x.linearY, y.linearY, x.offset, y.offset];
  }

  function controlMesh(authority) {
    const mesh = authority.spec?.coordinateSystem?.geographic?.controlMesh;
    assert(Array.isArray(mesh?.anchors) && mesh.anchors.length >= 3, 'control-mesh anchors are missing');
    assert(Array.isArray(mesh?.triangles) && mesh.triangles.length > 0, 'control-mesh triangles are missing');
    return mesh;
  }

  function projectControlMesh(authority) {
    const projector = getLegacyLatLngToCanvas();
    assert(projector, 'legacy latLngToCanvas is unavailable');
    const mesh = controlMesh(authority);
    return mesh.anchors.map(anchor => {
      const source = anchor.targetImagePixel;
      assert(Array.isArray(source) && source.length === 2, 'targetImagePixel anchor is invalid');
      const coordinate = authority.coordinates.imagePixelToLatLng(source[0], source[1]);
      const point = projector(coordinate.lat, coordinate.lng);
      assert(Number.isFinite(point?.x) && Number.isFinite(point?.y), 'control anchor did not project to canvas');
      return [point.x, point.y];
    });
  }

  function makeViewportKey(canvas, projected) {
    return [
      canvas.width,
      canvas.height,
      ...projected.flatMap(point => [point[0].toFixed(4), point[1].toFixed(4)]),
    ].join('|');
  }

  function buildViewportMask(authority, targetCanvas) {
    const projected = projectControlMesh(authority);
    const key = makeViewportKey(targetCanvas, projected);
    if (viewportMaskCanvas && viewportMaskKey === key) return viewportMaskCanvas;

    const source = buildSourceMask(authority);
    const mesh = controlMesh(authority);
    const output = document.createElement('canvas');
    output.width = targetCanvas.width;
    output.height = targetCanvas.height;
    const context = output.getContext('2d', { alpha: true });
    assert(context, 'viewport-mask 2D context is unavailable');
    context.clearRect(0, 0, output.width, output.height);
    context.imageSmoothingEnabled = false;
    context.globalCompositeOperation = 'lighter';

    for (const triangle of mesh.triangles) {
      assert(Array.isArray(triangle) && triangle.length === 3, 'control-mesh triangle is invalid');
      const sourceTriangle = triangle.map(index => mesh.anchors[index].targetImagePixel);
      const targetTriangle = triangle.map(index => projected[index]);
      const transform = affineFromTriangles(sourceTriangle, targetTriangle);

      context.save();
      context.beginPath();
      context.moveTo(targetTriangle[0][0], targetTriangle[0][1]);
      context.lineTo(targetTriangle[1][0], targetTriangle[1][1]);
      context.lineTo(targetTriangle[2][0], targetTriangle[2][1]);
      context.closePath();
      context.clip();
      context.setTransform(...transform);
      context.drawImage(source, 0, 0);
      context.restore();
    }
    context.globalCompositeOperation = 'source-over';

    viewportMaskCanvas = output;
    viewportMaskKey = key;
    diagnostics.maskBuilds += 1;
    diagnostics.triangleCount = mesh.triangles.length;
    diagnostics.lastViewportWidth = targetCanvas.width;
    diagnostics.lastViewportHeight = targetCanvas.height;
    setDataset('ongaStage13HeatmapMaskTriangles', diagnostics.triangleCount);
    setDataset('ongaStage13HeatmapMaskBuilds', diagnostics.maskBuilds);
    return output;
  }

  function getScratchCanvas(targetCanvas) {
    if (!scratchCanvas
      || scratchCanvas.width !== targetCanvas.width
      || scratchCanvas.height !== targetCanvas.height) {
      scratchCanvas = document.createElement('canvas');
      scratchCanvas.width = targetCanvas.width;
      scratchCanvas.height = targetCanvas.height;
    }
    return scratchCanvas;
  }

  function installExactClip(authority) {
    if (diagnostics.installed) return diagnostics;
    let originalDrawHeatmap = null;
    try {
      if (typeof drawHeatmap === 'function') originalDrawHeatmap = drawHeatmap;
    } catch (_) {
      // Ignore missing lexical binding.
    }
    if (!originalDrawHeatmap && typeof window.drawHeatmap === 'function') {
      originalDrawHeatmap = window.drawHeatmap;
    }
    assert(originalDrawHeatmap, 'drawHeatmap is unavailable after bridge installation');

    const replacement = function authoritativeClippedHeatmap(context, ...args) {
      assert(context?.canvas, 'drawHeatmap context is invalid');
      const scratch = getScratchCanvas(context.canvas);
      const scratchContext = scratch.getContext('2d', { alpha: true });
      assert(scratchContext, 'scratch 2D context is unavailable');
      scratchContext.setTransform(1, 0, 0, 1, 0, 0);
      scratchContext.globalCompositeOperation = 'source-over';
      scratchContext.clearRect(0, 0, scratch.width, scratch.height);
      originalDrawHeatmap.call(this, scratchContext, ...args);

      const exactMask = buildViewportMask(authority, context.canvas);
      scratchContext.setTransform(1, 0, 0, 1, 0, 0);
      scratchContext.globalCompositeOperation = 'destination-in';
      scratchContext.drawImage(exactMask, 0, 0);
      scratchContext.globalCompositeOperation = 'source-over';

      context.save();
      context.drawImage(scratch, 0, 0);
      context.restore();
      diagnostics.clipCalls += 1;
      setDataset('ongaStage13HeatmapClipCalls', diagnostics.clipCalls);
    };

    try {
      if (typeof drawHeatmap === 'function') drawHeatmap = replacement;
    } catch (_) {
      // A lexical binding is not mandatory when the window property is used by legacy rendering.
    }
    window.drawHeatmap = replacement;
    diagnostics.installed = true;
    setDataset('ongaStage13HeatmapClipModule', VERSION);
    setDataset('ongaStage13HeatmapClip', 'authority-mask');
    setDataset('ongaStage13HeatmapMaskTriangles', controlMesh(authority).triangles.length);
    window.OngaStage13HeatmapClip = Object.freeze({ version: VERSION, diagnostics });
    return diagnostics;
  }

  const bridgeApi = window.OngaStage13Bridge;
  assert(bridgeApi?.install, 'OngaStage13Bridge.install is unavailable');
  const originalInstall = bridgeApi.install;
  window.OngaStage13Bridge = Object.freeze({
    ...bridgeApi,
    install(...args) {
      const bridge = originalInstall.apply(this, args);
      installExactClip(bridge.authority);
      return bridge;
    },
  });
})();
