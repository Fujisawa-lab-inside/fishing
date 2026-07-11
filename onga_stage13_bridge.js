(() => {
  'use strict';

  if (window.__ONGA_STAGE13_BRIDGE__) return;
  window.__ONGA_STAGE13_BRIDGE__ = true;

  function assertReady() {
    const authority = window.OngaUnifiedAuthority;
    if (!authority?.water?.contains) {
      throw new Error('[onga-stage13-bridge] unified authority is not ready');
    }
    return authority;
  }

  function installWaterPredicate(authority) {
    const contains = authority.water.contains;
    const canvasPoint = (lat, lng) => {
      if (typeof latLngToCanvas !== 'function') return null;
      const point = latLngToCanvas(lat, lng);
      return point && Number.isFinite(point.x) && Number.isFinite(point.y) ? point : null;
    };

    window.ongaUnifiedWaterAtCanvas = (x, y) => contains(x, y);
    window.ongaUnifiedWaterAtLatLng = (lat, lng) => {
      const point = canvasPoint(lat, lng);
      return point ? contains(point.x, point.y) : false;
    };

    if (typeof calibratedWaterMaskValueAt === 'function') {
      calibratedWaterMaskValueAt = (lat, lng) => window.ongaUnifiedWaterAtLatLng(lat, lng) ? 1 : 0;
    }
    if (typeof isKnownWater === 'function') {
      isKnownWater = (lat, lng) => window.ongaUnifiedWaterAtLatLng(lat, lng);
    }
  }

  function installCandidateFilters(authority) {
    const contains = authority.water.contains;
    const originalHotspots = typeof makeShoreCastingHotspots === 'function'
      ? makeShoreCastingHotspots
      : null;

    window.ongaUnifiedFilterCanvasPoints = points => (points || []).filter(point => {
      const x = Number(point?.x ?? point?.canvasX);
      const y = Number(point?.y ?? point?.canvasY);
      return Number.isFinite(x) && Number.isFinite(y) && contains(x, y);
    });

    window.ongaUnifiedFilterLatLngPoints = points => (points || []).filter(point => {
      if (!Number.isFinite(point?.lat) || !Number.isFinite(point?.lng)) return false;
      return window.ongaUnifiedWaterAtLatLng(point.lat, point.lng);
    });

    if (originalHotspots) {
      makeShoreCastingHotspots = function unifiedHotspots(candidates, count) {
        const filtered = window.ongaUnifiedFilterLatLngPoints(candidates);
        return originalHotspots(filtered, count);
      };
    }
  }

  function clearLegacyCaches() {
    try {
      state?.waterSampleCache?.clear?.();
      state?.fluidCache?.clear?.();
      state?.fluidBaseCache?.clear?.();
      state?.validationCache?.clear?.();
    } catch (_) {
      // State may not exist yet during early bootstrap.
    }
  }

  function install() {
    const authority = assertReady();
    installWaterPredicate(authority);
    installCandidateFilters(authority);
    clearLegacyCaches();

    window.OngaUnifiedDomainBridge = Object.freeze({
      version: 'stage13-bridge-v1',
      installed: true,
      authority,
    });
    window.dispatchEvent(new CustomEvent('onga:unified-domain-installed', {
      detail: window.OngaUnifiedDomainBridge,
    }));
    console.info('[onga-stage13-bridge] installed', authority.water.pixelCount);
    return window.OngaUnifiedDomainBridge;
  }

  window.OngaStage13Bridge = Object.freeze({ install });
})();