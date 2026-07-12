(() => {
  'use strict';

  if (window.__ONGA_STAGE13_FLUID_DOMAIN_PATCH__) return;
  window.__ONGA_STAGE13_FLUID_DOMAIN_PATCH__ = true;

  const VERSION = 'stage13-fluid-domain-patch-v1';

  function assert(condition, message) {
    if (!condition) throw new Error(`[onga-stage13-fluid-domain] ${message}`);
  }

  function setDataset(name, value) {
    if (typeof document === 'undefined' || !document.documentElement) return;
    document.documentElement.dataset[name] = String(value);
  }

  function legacyState() {
    try {
      if (typeof state !== 'undefined') return state;
    } catch (_) {
      // Fall through to the window property.
    }
    return window.state;
  }

  function legacyGsi() {
    try {
      if (typeof GSI !== 'undefined') return GSI;
    } catch (_) {
      // Fall through to the window property.
    }
    return window.GSI;
  }

  function legacyOnga() {
    try {
      if (typeof ONGA !== 'undefined') return ONGA;
    } catch (_) {
      // Fall through to the window property.
    }
    return window.ONGA;
  }

  function hydroAt(lat, lng) {
    try {
      if (typeof nearestHydroCorridor === 'function') return nearestHydroCorridor(lat, lng);
    } catch (_) {
      // Fall through to the window property.
    }
    return typeof window.nearestHydroCorridor === 'function'
      ? window.nearestHydroCorridor(lat, lng)
      : null;
  }

  function mainProgressAt(lat, lng) {
    try {
      if (typeof nearestRiverProgress === 'function') return nearestRiverProgress(lat, lng);
    } catch (_) {
      // Fall through to the window property.
    }
    return typeof window.nearestRiverProgress === 'function'
      ? window.nearestRiverProgress(lat, lng)
      : null;
  }

  function distanceMeters(lat1, lng1, lat2, lng2) {
    try {
      if (typeof haversine === 'function') return haversine(lat1, lng1, lat2, lng2);
    } catch (_) {
      // Fall through to the window property.
    }
    if (typeof window.haversine === 'function') return window.haversine(lat1, lng1, lat2, lng2);
    return Infinity;
  }

  function depthAndMobilityAt(lat, lng) {
    try {
      if (typeof fluidDepthAndMobility === 'function') return fluidDepthAndMobility(lat, lng);
    } catch (_) {
      // Fall through to the window property.
    }
    if (typeof window.fluidDepthAndMobility === 'function') {
      return window.fluidDepthAndMobility(lat, lng);
    }
    throw new Error('[onga-stage13-fluid-domain] fluidDepthAndMobility is unavailable');
  }

  function boundaryTypeForCell(lat, lng) {
    const hydro = hydroAt(lat, lng);
    const mainNear = mainProgressAt(lat, lng);
    const onga = legacyOnga();

    if (Number(mainNear?.s) > 0.90
      || (onga?.ashiya && distanceMeters(lat, lng, onga.ashiya.lat, onga.ashiya.lng) < 120)) {
      return 1;
    }
    if (hydro?.kind === 'onga_up' && Number(hydro.tributaryProgress ?? 1) < 0.16) return 2;
    if (hydro?.kind === 'nishi' && Number(hydro.tributaryProgress ?? 1) < 0.16) return 3;
    if (hydro?.kind === 'magari' && Number(hydro.tributaryProgress ?? 1) < 0.16) return 4;
    if (onga?.barrage && distanceMeters(lat, lng, onga.barrage.lat, onga.barrage.lng) < 95) return 5;
    return 0;
  }

  function reconcileBaseGrid(authority, base) {
    const bounds = legacyGsi()?.bounds;
    assert(bounds, 'GSI.bounds is unavailable');
    assert([bounds.north, bounds.south, bounds.west, bounds.east].every(Number.isFinite), 'GSI.bounds is invalid');
    assert(Number.isInteger(base?.nx) && Number.isInteger(base?.ny), 'base grid dimensions are invalid');
    assert(base.water?.length === base.nx * base.ny, 'base water array length is invalid');

    let beforeDifference = 0;
    let added = 0;
    let removed = 0;
    let waterCount = 0;

    for (let j = 0; j < base.ny; j += 1) {
      const lat = bounds.north - (bounds.north - bounds.south) * (j + 0.5) / base.ny;
      for (let i = 0; i < base.nx; i += 1) {
        const lng = bounds.west + (bounds.east - bounds.west) * (i + 0.5) / base.nx;
        const index = j * base.nx + i;
        const expected = authority.water.containsLatLng(lat, lng);
        const actual = base.water[index] === 1;

        if (expected !== actual) beforeDifference += 1;

        if (expected) {
          waterCount += 1;
          base.water[index] = 1;
          if (base.latArr) base.latArr[index] = lat;
          if (base.lngArr) base.lngArr[index] = lng;

          if (!actual) {
            added += 1;
            const properties = depthAndMobilityAt(lat, lng);
            if (base.depth) base.depth[index] = Number(properties?.depth) || 0;
            if (base.K) base.K[index] = Number(properties?.hydraulic) || 0;
            if (base.mainS) {
              const progress = Number(mainProgressAt(lat, lng)?.s);
              base.mainS[index] = Number.isFinite(progress) ? Math.min(1, Math.max(0, progress)) : 0;
            }
            if (base.boundaryType) base.boundaryType[index] = boundaryTypeForCell(lat, lng);
          }
        } else {
          if (actual) removed += 1;
          base.water[index] = 0;
          if (base.depth) base.depth[index] = 0;
          if (base.K) base.K[index] = 0;
          if (base.mainS) base.mainS[index] = 0;
          if (base.boundaryType) base.boundaryType[index] = 0;
        }
      }
    }

    base.waterCount = waterCount;
    setDataset('ongaStage13BaseDomainDifferenceBefore', beforeDifference);
    setDataset('ongaStage13BaseDomainDifferenceAfter', 0);
    setDataset('ongaStage13BaseDomainAdded', added);
    setDataset('ongaStage13BaseDomainRemoved', removed);

    return { beforeDifference, added, removed, waterCount };
  }

  class AuthorityFluidBaseCache extends Map {
    constructor(authority) {
      super();
      this.authority = authority;
      this.lastReconciliation = null;
    }

    set(key, base) {
      this.lastReconciliation = reconcileBaseGrid(this.authority, base);
      return super.set(key, base);
    }
  }

  function install(authority) {
    assert(authority?.water?.containsLatLng, 'authority is not ready');
    const currentState = legacyState();
    assert(currentState, 'legacy state is unavailable');

    const cache = new AuthorityFluidBaseCache(authority);
    currentState.fluidBaseCache = cache;
    currentState.fluidCache?.clear?.();
    currentState.validationCache?.clear?.();

    setDataset('ongaStage13FluidBasePatch', VERSION);
    window.OngaStage13FluidBaseCache = cache;

    return Object.freeze({ version: VERSION, installed: true, cache });
  }

  window.OngaStage13FluidDomainPatch = Object.freeze({ VERSION, install, reconcileBaseGrid });
})();
