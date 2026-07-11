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

  function legacyState() {
    try {
      if (typeof state !== 'undefined') return state;
    } catch (_) {
      // Ignore missing global lexical binding.
    }
    return window.state;
  }

  function legacyGsi() {
    try {
      if (typeof GSI !== 'undefined') return GSI;
    } catch (_) {
      // Ignore missing global lexical binding.
    }
    return window.GSI;
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

    const calibratedReplacement = (lat, lng) => (
      window.ongaUnifiedWaterAtLatLng(lat, lng) ? 1 : 0
    );
    if (typeof calibratedWaterMaskValueAt === 'function') {
      calibratedWaterMaskValueAt = calibratedReplacement;
      window.calibratedWaterMaskValueAt = calibratedReplacement;
      audit.patches.calibratedWaterMaskValueAt = true;
    } else if (typeof window.calibratedWaterMaskValueAt === 'function') {
      window.calibratedWaterMaskValueAt = calibratedReplacement;
      audit.patches.calibratedWaterMaskValueAt = true;
    } else {
      audit.patches.calibratedWaterMaskValueAt = false;
    }

    const knownReplacement = (lat, lng) => window.ongaUnifiedWaterAtLatLng(lat, lng);
    if (typeof isKnownWater === 'function') {
      isKnownWater = knownReplacement;
      window.isKnownWater = knownReplacement;
      audit.patches.isKnownWater = true;
    } else if (typeof window.isKnownWater === 'function') {
      window.isKnownWater = knownReplacement;
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
    const originalSampler = typeof samplePhotoWaterCandidates === 'function'
      ? samplePhotoWaterCandidates
      : (typeof window.samplePhotoWaterCandidates === 'function' ? window.samplePhotoWaterCandidates : null);
    const originalDrawHeatmap = typeof drawHeatmap === 'function'
      ? drawHeatmap
      : (typeof window.drawHeatmap === 'function' ? window.drawHeatmap : null);

    if (originalSampler) {
      const replacement = function unifiedWaterSamples(...args) {
        const samples = withContext('heatmap', () => originalSampler.apply(this, args));
        validateHeatmapSamples(authority, samples);
        return samples;
      };
      if (typeof samplePhotoWaterCandidates === 'function') samplePhotoWaterCandidates = replacement;
      window.samplePhotoWaterCandidates = replacement;
    }
    if (originalDrawHeatmap) {
      const replacement = function unifiedHeatmap(...args) {
        return withContext('heatmap', () => originalDrawHeatmap.apply(this, args));
      };
      if (typeof drawHeatmap === 'function') drawHeatmap = replacement;
      window.drawHeatmap = replacement;
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
    const bounds = legacyGsi()?.bounds;
    const canReconstructCentres = bounds
      && [bounds.north, bounds.south, bounds.west, bounds.east].every(Number.isFinite)
      && Number.isInteger(grid.nx)
      && Number.isInteger(grid.ny);
    let difference = 0;
    let float32Difference = 0;
    const mismatchDetails = [];
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
      if (expected !== actual) {
        difference += 1;
        if (mismatchDetails.length < 20) {
          mismatchDetails.push({ index, i, j, lat, lng, expected, actual });
        }
      }
      const floatExpected = authority.water.containsLatLng(grid.latArr[index], grid.lngArr[index]);
      if (floatExpected !== actual) float32Difference += 1;
    }
    audit.fluidCellsChecked = grid.water.length;
    audit.fluidDomainDifferenceCells = difference;
    audit.fluidFloat32DiagnosticDifference = float32Difference;
    audit.fluidMismatchDetails = mismatchDetails;
    setDataset('ongaStage13FluidCells', grid.water.length);
    setDataset('ongaStage13FluidDomainDifference', difference);
    setDataset('ongaStage13FluidFloat32Difference', float32Difference);
    if (difference !== 0) {
      throw new Error(`[onga-stage13-bridge] fluid domain difference: ${difference}`);
    }
  }

  function installFluidRoute(authority) {
    const originalBuildFluidGrid = typeof buildFluidGrid === 'function'
      ? buildFluidGrid
      : (typeof window.buildFluidGrid === 'function' ? window.buildFluidGrid : null);
    if (!originalBuildFluidGrid) {
      audit.patches.buildFluidGrid = false;
      return;
    }

    const replacement = function unifiedBuildFluidGrid(...args) {
      const previousHydro = typeof nearestHydroCorridor === 'function'
        ? nearestHydroCorridor
        : window.nearestHydroCorridor;
      const hydroReplacement = createHydroFallback(previousHydro, authority);
      if (typeof nearestHydroCorridor === 'function') nearestHydroCorridor = hydroReplacement;
      window.nearestHydroCorridor = hydroReplacement;
      try {
        const grid = withContext('fluid', () => originalBuildFluidGrid.apply(this, args));
        validateFluidGrid(authority, grid);
        return grid;
      } finally {
        if (typeof nearestHydroCorridor === 'function') nearestHydroCorridor = previousHydro;
        window.nearestHydroCorridor = previousHydro;
      }
    };
    if (typeof buildFluidGrid === 'function') buildFluidGrid = replacement;
    window.buildFluidGrid = replacement;
    audit.patches.buildFluidGrid = true;
  }

  function installCandidateFilters(authority) {
    const containsLatLng = authority.water.containsLatLng;
    const originalHotspots = typeof makeShoreCastingHotspots === 'function'
      ? makeShoreCastingHotspots
      : (typeof window.makeShoreCastingHotspots === 'function' ? window.makeShoreCastingHotspots : null);

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
      const replacement = function unifiedHotspots(candidates, count) {
        return withContext('hotspot', () => {
          const filtered = window.ongaUnifiedFilterLatLngPoints(candidates);
          return originalHotspots.call(this, filtered, count);
        });
      };
      if (typeof makeShoreCastingHotspots === 'function') makeShoreCastingHotspots = replacement;
      window.makeShoreCastingHotspots = replacement;
    }
    audit.patches.makeShoreCastingHotspots = Boolean(originalHotspots);
  }

  function clearLegacyCaches() {
    try {
      const currentState = legacyState();
      currentState?.waterSampleCache?.clear?.();
      currentState?.fluidCache?.clear?.();
      currentState?.fluidBaseCache?.clear?.();
      currentState?.validationCache?.clear?.();
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
      const sampler = typeof samplePhotoWaterCandidates === 'function'
        ? samplePhotoWaterCandidates
        : window.samplePhotoWaterCandidates;
      const compute = typeof computeAndRender === 'function' ? computeAndRender : window.computeAndRender;
      const render = typeof renderAll === 'function' ? renderAll : window.renderAll;
      if (typeof sampler === 'function') sampler();
      if (typeof compute === 'function' && legacyState()?.timeline?.length) {
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
