(() => {
  'use strict';

  if (window.__ONGA_STAGE13_BRIDGE_V2__) return;
  window.__ONGA_STAGE13_BRIDGE_V2__ = true;

  const VERSION = 'stage13-bridge-v2';
  const audit = {
    version: VERSION,
    currentContext: 'idle',
    calls: { image: 0, latLng: 0, heatmap: 0, fluid: 0, hotspot: 0 },
    patches: {},
    heatmapSampleCount: null,
    heatmapSampleMismatch: null,
    fluidCellsChecked: null,
    fluidDomainDifferenceCells: null,
    refreshAttempted: false,
    refreshCompleted: false,
    refreshError: null,
  };

  function assertReady() {
    const authority = window.OngaUnifiedAuthority;
    if (!authority?.water?.containsImagePixel || !authority?.water?.containsLatLng) {
      throw new Error('[onga-stage13-bridge] unified authority with geographic transform is not ready');
    }
    return authority;
  }

  function setDataset(name, value) {
    if (typeof document === 'undefined' || !document.documentElement) return;
    document.documentElement.dataset[name] = String(value);
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

  function installWaterPredicate(authority) {
    const containsImagePixel = authority.water.containsImagePixel;
    const containsLatLng = authority.water.containsLatLng;

    window.ongaUnifiedWaterAtImagePixel = (x, y) => {
      countPredicate('image');
      return containsImagePixel(x, y);
    };
    window.ongaUnifiedWaterAtCanvas = window.ongaUnifiedWaterAtImagePixel;
    window.ongaUnifiedWaterAtLatLng = (lat, lng) => {
      countPredicate('latLng');
      return containsLatLng(lat, lng);
    };

    if (typeof window.calibratedWaterMaskValueAt === 'function') {
      window.calibratedWaterMaskValueAt = (lat, lng) => (
        window.ongaUnifiedWaterAtLatLng(lat, lng) ? 1 : 0
      );
      audit.patches.calibratedWaterMaskValueAt = true;
    } else {
      audit.patches.calibratedWaterMaskValueAt = false;
    }

    if (typeof window.isKnownWater === 'function') {
      window.isKnownWater = (lat, lng) => window.ongaUnifiedWaterAtLatLng(lat, lng);
      audit.patches.isKnownWater = true;
    } else {
      audit.patches.isKnownWater = false;
    }
  }

  function validateHeatmapSamples(authority, samples) {
    const list = Array.isArray(samples) ? samples : [];
    let mismatch = 0;
    for (const point of list) {
      if (!Number.isFinite(point?.lat) || !Number.isFinite(point?.lng)) {
        mismatch += 1;
      } else if (!authority.water.containsLatLng(point.lat, point.lng)) {
        mismatch += 1;
      }
    }
    audit.heatmapSampleCount = list.length;
    audit.heatmapSampleMismatch = mismatch;
    setDataset('ongaStage13HeatmapSamples', list.length);
    setDataset('ongaStage13HeatmapMismatch', mismatch);
    if (mismatch !== 0) {
      throw new Error(`[onga-stage13-bridge] heatmap water sample mismatch: ${mismatch}`);
    }
  }

  function installHeatmapRoute(authority) {
    const originalSampler = typeof window.samplePhotoWaterCandidates === 'function'
      ? window.samplePhotoWaterCandidates
      : null;
    const originalDrawHeatmap = typeof window.drawHeatmap === 'function'
      ? window.drawHeatmap
      : null;

    if (originalSampler) {
      window.samplePhotoWaterCandidates = function unifiedWaterSamples(...args) {
        const samples = withContext('heatmap', () => originalSampler.apply(this, args));
        validateHeatmapSamples(authority, samples);
        return samples;
      };
    }
    if (originalDrawHeatmap) {
      window.drawHeatmap = function unifiedHeatmap(...args) {
        return withContext('heatmap', () => originalDrawHeatmap.apply(this, args));
      };
    }

    audit.patches.samplePhotoWaterCandidates = Boolean(originalSampler);
    audit.patches.drawHeatmap = Boolean(originalDrawHeatmap);
  }

  function createHydroFallback(originalHydro, authority) {
    return function unifiedHydroCorridor(lat, lng) {
      const hydro = typeof originalHydro === 'function'
        ? originalHydro(lat, lng)
        : null;
      if (!authority.water.containsLatLng(lat, lng)) return hydro;
      if (hydro && Number(hydro.corridor) > 0.01) return hydro;
      return {
        ...(hydro || {}),
        kind: hydro?.kind || 'unified_water',
        label: hydro?.label || '承認済み正解水面',
        corridor: 1,
        seed: Math.max(Number(hydro?.seed) || 0, 1),
      };
    };
  }

  function validateFluidGrid(authority, grid) {
    if (!grid?.water || !grid?.latArr || !grid?.lngArr) {
      throw new Error('[onga-stage13-bridge] fluid grid lacks water/lat/lng arrays');
    }
    const bounds = window.GSI?.bounds;
    const canReconstructCentres = bounds
      && [bounds.north, bounds.south, bounds.west, bounds.east].every(Number.isFinite)
      && Number.isInteger(grid.nx)
      && Number.isInteger(grid.ny);
    let difference = 0;
    let float32Difference = 0;
    for (let index = 0; index < grid.water.length; index += 1) {
      const i = index % grid.nx;
      const j = Math.floor(index / grid.nx);
      const lat = canReconstructCentres
        ? bounds.north - (bounds.north - bounds.south) * (j + 0.5) / grid.ny
        : grid.latArr[index];
      const lng = canReconstructCentres
        ? bounds.west + (bounds.east - bounds.west) * (i + 0.5) / grid.nx
        : grid.lngArr[index];
      const expected = authority.water.containsLatLng(lat, lng);
      const actual = grid.water[index] === 1;
      if (expected !== actual) difference += 1;
      const floatExpected = authority.water.containsLatLng(grid.latArr[index], grid.lngArr[index]);
      if (floatExpected !== actual) float32Difference += 1;
    }
    audit.fluidCellsChecked = grid.water.length;
    audit.fluidDomainDifferenceCells = difference;
    audit.fluidFloat32DiagnosticDifference = float32Difference;
    setDataset('ongaStage13FluidCells', grid.water.length);
    setDataset('ongaStage13FluidDomainDifference', difference);
    setDataset('ongaStage13FluidFloat32Difference', float32Difference);
    if (difference !== 0) {
      throw new Error(`[onga-stage13-bridge] fluid domain difference: ${difference}`);
    }
  }

  function installFluidRoute(authority) {
    const originalBuildFluidGrid = typeof window.buildFluidGrid === 'function'
      ? window.buildFluidGrid
      : null;
    if (!originalBuildFluidGrid) {
      audit.patches.buildFluidGrid = false;
      return;
    }

    window.buildFluidGrid = function unifiedBuildFluidGrid(...args) {
      const previousHydro = window.nearestHydroCorridor;
      window.nearestHydroCorridor = createHydroFallback(previousHydro, authority);
      try {
        const grid = withContext('fluid', () => originalBuildFluidGrid.apply(this, args));
        validateFluidGrid(authority, grid);
        return grid;
      } finally {
        window.nearestHydroCorridor = previousHydro;
      }
    };
    audit.patches.buildFluidGrid = true;
  }

  function installCandidateFilters(authority) {
    const containsLatLng = authority.water.containsLatLng;
    const originalHotspots = typeof window.makeShoreCastingHotspots === 'function'
      ? window.makeShoreCastingHotspots
      : null;

    window.ongaUnifiedFilterImagePoints = points => (points || []).filter(point => {
      const x = Number(point?.x ?? point?.canvasX);
      const y = Number(point?.y ?? point?.canvasY);
      return Number.isFinite(x) && Number.isFinite(y) && authority.water.containsImagePixel(x, y);
    });
    window.ongaUnifiedFilterCanvasPoints = window.ongaUnifiedFilterImagePoints;
    window.ongaUnifiedFilterLatLngPoints = points => (points || []).filter(point => (
      Number.isFinite(point?.lat)
      && Number.isFinite(point?.lng)
      && containsLatLng(point.lat, point.lng)
    ));

    if (originalHotspots) {
      window.makeShoreCastingHotspots = function unifiedHotspots(candidates, count) {
        return withContext('hotspot', () => {
          const filtered = window.ongaUnifiedFilterLatLngPoints(candidates);
          return originalHotspots.call(this, filtered, count);
        });
      };
    }
    audit.patches.makeShoreCastingHotspots = Boolean(originalHotspots);
  }

  function clearLegacyCaches() {
    try {
      window.state?.waterSampleCache?.clear?.();
      window.state?.fluidCache?.clear?.();
      window.state?.fluidBaseCache?.clear?.();
      window.state?.validationCache?.clear?.();
    } catch (_) {
      // State may not exist yet during early bootstrap.
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
      if (typeof window.samplePhotoWaterCandidates === 'function') {
        window.samplePhotoWaterCandidates();
      }
      if (typeof window.computeAndRender === 'function' && window.state?.timeline?.length) {
        await Promise.resolve(window.computeAndRender(true));
      } else if (typeof window.renderAll === 'function') {
        window.renderAll();
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

    const bridge = Object.freeze({
      version: VERSION,
      installed: true,
      authority,
      audit,
      refresh,
    });
    window.OngaUnifiedDomainBridge = bridge;
    window.dispatchEvent(new CustomEvent('onga:unified-domain-installed', { detail: bridge }));
    console.info('[onga-stage13-bridge] installed', authority.water.pixelCount);
    return bridge;
  }

  window.OngaStage13Bridge = Object.freeze({ VERSION, install });
})();
