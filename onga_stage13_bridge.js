(() => {
  'use strict';

  if (window.__ONGA_STAGE13_BRIDGE_V3__) return;
  window.__ONGA_STAGE13_BRIDGE_V3__ = true;

  const VERSION = 'stage13-bridge-v3';
  const audit = {
    version: VERSION,
    currentContext: 'idle',
    calls: { image: 0, latLng: 0, heatmap: 0, fluid: 0, hotspot: 0 },
    patches: {},
    heatmapSourceRejected: 0,
    heatmapSampleCount: null,
    heatmapSampleMismatch: null,
    fluidCellsChecked: null,
    fluidDomainDifferenceCells: null,
    fluidFalseNegative: null,
    fluidFalsePositive: null,
    refreshAttempted: false,
    refreshCompleted: false,
    refreshError: null,
  };

  function setDataset(name, value) {
    if (typeof document === 'undefined' || !document.documentElement) return;
    document.documentElement.dataset[name] = String(value);
  }

  function assertReady() {
    const authority = window.OngaUnifiedAuthority;
    if (!authority?.water?.containsImagePixel || !authority?.water?.containsLatLng) {
      throw new Error('[onga-stage13-bridge] unified authority with geographic transform is not ready');
    }
    return authority;
  }

  function legacyState() {
    try {
      if (typeof state !== 'undefined') return state;
    } catch (_) {
      // Ignore a missing global lexical binding.
    }
    return window.state;
  }

  function legacyGsi() {
    try {
      if (typeof GSI !== 'undefined') return GSI;
    } catch (_) {
      // Ignore a missing global lexical binding.
    }
    return window.GSI;
  }

  function withContext(context, callback) {
    const previous = audit.currentContext;
    audit.currentContext = context;
    try {
      return callback();
    } finally {
      audit.currentContext = previous;
    }
  }

  function countPredicate(kind) {
    audit.calls[kind] += 1;
    if (audit.currentContext in audit.calls) audit.calls[audit.currentContext] += 1;
  }

  function clearLegacyCaches() {
    const currentState = legacyState();
    currentState?.waterSampleCache?.clear?.();
    currentState?.fluidCache?.clear?.();
    currentState?.fluidBaseCache?.clear?.();
    currentState?.validationCache?.clear?.();
  }

  function installWaterPredicate(authority) {
    window.ongaUnifiedWaterAtImagePixel = (x, y) => {
      countPredicate('image');
      return authority.water.containsImagePixel(x, y);
    };
    window.ongaUnifiedWaterAtCanvas = window.ongaUnifiedWaterAtImagePixel;
    window.ongaUnifiedWaterAtLatLng = (lat, lng) => {
      countPredicate('latLng');
      return authority.water.containsLatLng(lat, lng);
    };

    const calibratedReplacement = (lat, lng) => (
      window.ongaUnifiedWaterAtLatLng(lat, lng) ? 1 : 0
    );
    try {
      if (typeof calibratedWaterMaskValueAt === 'function') calibratedWaterMaskValueAt = calibratedReplacement;
    } catch (_) {
      // The window property below remains available to legacy callers.
    }
    window.calibratedWaterMaskValueAt = calibratedReplacement;
    audit.patches.calibratedWaterMaskValueAt = true;

    const knownReplacement = (lat, lng) => window.ongaUnifiedWaterAtLatLng(lat, lng);
    try {
      if (typeof isKnownWater === 'function') isKnownWater = knownReplacement;
    } catch (_) {
      // The window property below remains available to legacy callers.
    }
    window.isKnownWater = knownReplacement;
    audit.patches.isKnownWater = true;
  }

  function enforceHeatmapSamples(authority, samples) {
    const list = Array.isArray(samples) ? samples : [];
    const filtered = [];
    let rejected = 0;
    for (const point of list) {
      if (!Number.isFinite(point?.lat) || !Number.isFinite(point?.lng)) {
        rejected += 1;
        continue;
      }
      if (!authority.water.containsLatLng(point.lat, point.lng)) {
        rejected += 1;
        continue;
      }
      filtered.push(point);
    }

    const currentState = legacyState();
    if (currentState) {
      currentState.waterMaskSamples = filtered;
      currentState.waterMaskPoints = filtered.slice(0, 3600);
    }

    audit.heatmapSourceRejected += rejected;
    audit.heatmapSampleCount = filtered.length;
    audit.heatmapSampleMismatch = 0;
    setDataset('ongaStage13HeatmapSourceRejected', audit.heatmapSourceRejected);
    setDataset('ongaStage13HeatmapSamples', filtered.length);
    setDataset('ongaStage13HeatmapMismatch', 0);
    return filtered;
  }

  function installHeatmapRoute(authority) {
    let originalSampler = null;
    let originalDrawHeatmap = null;
    try {
      if (typeof samplePhotoWaterCandidates === 'function') originalSampler = samplePhotoWaterCandidates;
      if (typeof drawHeatmap === 'function') originalDrawHeatmap = drawHeatmap;
    } catch (_) {
      // Fall through to window properties.
    }
    originalSampler ||= window.samplePhotoWaterCandidates;
    originalDrawHeatmap ||= window.drawHeatmap;

    if (typeof originalSampler === 'function') {
      const samplerReplacement = function unifiedWaterSamples(...args) {
        const samples = withContext('heatmap', () => originalSampler.apply(this, args));
        return enforceHeatmapSamples(authority, samples);
      };
      try {
        if (typeof samplePhotoWaterCandidates === 'function') samplePhotoWaterCandidates = samplerReplacement;
      } catch (_) {
        // Window replacement remains available.
      }
      window.samplePhotoWaterCandidates = samplerReplacement;
      audit.patches.samplePhotoWaterCandidates = true;
    } else {
      audit.patches.samplePhotoWaterCandidates = false;
    }

    if (typeof originalDrawHeatmap === 'function') {
      const drawReplacement = function unifiedHeatmap(...args) {
        return withContext('heatmap', () => originalDrawHeatmap.apply(this, args));
      };
      try {
        if (typeof drawHeatmap === 'function') drawHeatmap = drawReplacement;
      } catch (_) {
        // Window replacement remains available.
      }
      window.drawHeatmap = drawReplacement;
      audit.patches.drawHeatmap = true;
    } else {
      audit.patches.drawHeatmap = false;
    }
  }

  function validateFluidGrid(authority, grid) {
    if (!grid?.water || !Number.isInteger(grid.nx) || !Number.isInteger(grid.ny)) {
      throw new Error('[onga-stage13-bridge] fluid grid is incomplete');
    }
    const bounds = legacyGsi()?.bounds;
    if (!bounds || ![bounds.north, bounds.south, bounds.west, bounds.east].every(Number.isFinite)) {
      throw new Error('[onga-stage13-bridge] GSI.bounds is unavailable');
    }

    let difference = 0;
    let falseNegative = 0;
    let falsePositive = 0;
    const mismatchDetails = [];
    for (let index = 0; index < grid.water.length; index += 1) {
      const i = index % grid.nx;
      const j = Math.floor(index / grid.nx);
      const lat = bounds.north - (bounds.north - bounds.south) * (j + 0.5) / grid.ny;
      const lng = bounds.west + (bounds.east - bounds.west) * (i + 0.5) / grid.nx;
      const expected = authority.water.containsLatLng(lat, lng);
      const actual = grid.water[index] === 1;
      if (expected === actual) continue;
      difference += 1;
      if (expected) falseNegative += 1;
      else falsePositive += 1;
      if (mismatchDetails.length < 20) {
        mismatchDetails.push({ index, i, j, lat, lng, expected, actual });
      }
    }

    audit.fluidCellsChecked = grid.water.length;
    audit.fluidDomainDifferenceCells = difference;
    audit.fluidFalseNegative = falseNegative;
    audit.fluidFalsePositive = falsePositive;
    audit.fluidMismatchDetails = mismatchDetails;
    setDataset('ongaStage13FluidCells', grid.water.length);
    setDataset('ongaStage13FluidDomainDifference', difference);
    setDataset('ongaStage13FluidFalseNegative', falseNegative);
    setDataset('ongaStage13FluidFalsePositive', falsePositive);
    setDataset('ongaStage13FluidExactCentres', true);
    setDataset(
      'ongaStage13FluidMismatchDetails',
      mismatchDetails.map(item => [
        item.index,
        item.i,
        item.j,
        item.expected ? 1 : 0,
        item.actual ? 1 : 0,
        item.lat.toFixed(8),
        item.lng.toFixed(8),
      ].join(':')).join(','),
    );
    if (difference !== 0) {
      throw new Error(`[onga-stage13-bridge] fluid domain difference: ${difference}`);
    }
  }

  function installFluidRoute(authority) {
    let originalBuildFluidGrid = null;
    try {
      if (typeof buildFluidGrid === 'function') originalBuildFluidGrid = buildFluidGrid;
    } catch (_) {
      // Fall through to the window property.
    }
    originalBuildFluidGrid ||= window.buildFluidGrid;
    if (typeof originalBuildFluidGrid !== 'function') {
      audit.patches.buildFluidGrid = false;
      return;
    }

    const replacement = function unifiedBuildFluidGrid(...args) {
      const grid = withContext('fluid', () => originalBuildFluidGrid.apply(this, args));
      validateFluidGrid(authority, grid);
      return grid;
    };
    try {
      if (typeof buildFluidGrid === 'function') buildFluidGrid = replacement;
    } catch (_) {
      // Window replacement remains available.
    }
    window.buildFluidGrid = replacement;
    audit.patches.buildFluidGrid = true;
  }

  function installCandidateFilters(authority) {
    window.ongaUnifiedFilterImagePoints = points => (points || []).filter(point => {
      const x = Number(point?.x ?? point?.canvasX);
      const y = Number(point?.y ?? point?.canvasY);
      return Number.isFinite(x) && Number.isFinite(y) && authority.water.containsImagePixel(x, y);
    });
    window.ongaUnifiedFilterCanvasPoints = window.ongaUnifiedFilterImagePoints;
    window.ongaUnifiedFilterLatLngPoints = points => (points || []).filter(point => (
      Number.isFinite(point?.lat)
      && Number.isFinite(point?.lng)
      && authority.water.containsLatLng(point.lat, point.lng)
    ));

    let originalHotspots = null;
    try {
      if (typeof makeShoreCastingHotspots === 'function') originalHotspots = makeShoreCastingHotspots;
    } catch (_) {
      // Fall through to window property.
    }
    originalHotspots ||= window.makeShoreCastingHotspots;
    if (typeof originalHotspots === 'function') {
      const replacement = function unifiedHotspots(candidates, count) {
        return withContext('hotspot', () => {
          const filtered = window.ongaUnifiedFilterLatLngPoints(candidates);
          return originalHotspots.call(this, filtered, count);
        });
      };
      try {
        if (typeof makeShoreCastingHotspots === 'function') makeShoreCastingHotspots = replacement;
      } catch (_) {
        // Window replacement remains available.
      }
      window.makeShoreCastingHotspots = replacement;
      audit.patches.makeShoreCastingHotspots = true;
    } else {
      audit.patches.makeShoreCastingHotspots = false;
    }
  }

  function publishAudit() {
    setDataset('ongaStage13Bridge', VERSION);
    setDataset('ongaStage13WaterPredicate', audit.patches.calibratedWaterMaskValueAt ? 'authority' : 'missing');
    setDataset('ongaStage13HeatmapRoute', audit.patches.samplePhotoWaterCandidates ? 'authority' : 'missing');
    setDataset('ongaStage13FluidRoute', audit.patches.buildFluidGrid ? 'authority' : 'missing');
    window.OngaStage13RuntimeAudit = audit;
    return audit;
  }

  async function settle() {
    await new Promise(resolve => setTimeout(resolve, 0));
    if (typeof requestAnimationFrame === 'function') {
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }
  }

  async function refresh() {
    audit.refreshAttempted = true;
    clearLegacyCaches();
    try {
      const currentState = legacyState();
      const sampler = window.samplePhotoWaterCandidates;
      let compute = null;
      let render = null;
      try {
        if (typeof computeAndRender === 'function') compute = computeAndRender;
        if (typeof renderAll === 'function') render = renderAll;
      } catch (_) {
        // Fall through to window properties.
      }
      compute ||= window.computeAndRender;
      render ||= window.renderAll;

      if (typeof sampler === 'function') sampler();
      if (typeof compute === 'function' && currentState?.timeline?.length) {
        await Promise.resolve(compute(true));
      } else if (typeof render === 'function') {
        render();
      }
      await settle();
      audit.refreshCompleted = true;
      setDataset('ongaStage13Refresh', 'complete');
    } catch (error) {
      audit.refreshError = String(error);
      setDataset('ongaStage13Refresh', 'error');
      throw error;
    } finally {
      publishAudit();
    }
    return audit;
  }

  function install() {
    const authority = assertReady();
    installWaterPredicate(authority);
    installHeatmapRoute(authority);
    installFluidRoute(authority);
    installCandidateFilters(authority);
    clearLegacyCaches();
    publishAudit();

    const bridge = Object.freeze({ version: VERSION, installed: true, authority, audit, refresh });
    window.OngaUnifiedDomainBridge = bridge;
    window.dispatchEvent(new CustomEvent('onga:unified-domain-installed', { detail: bridge }));
    console.info('[onga-stage13-bridge] installed', authority.water.pixelCount);
    return bridge;
  }

  window.OngaStage13Bridge = Object.freeze({ VERSION, install });
})();
