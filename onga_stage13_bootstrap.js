(() => {
  'use strict';

  if (window.__ONGA_STAGE13_BOOTSTRAP_V4__) return;
  window.__ONGA_STAGE13_BOOTSTRAP_V4__ = true;

  const params = new URLSearchParams(location.search);
  const enabled = params.get('stage13') === '1';

  function setDataset(name, value) {
    document.documentElement.dataset[name] = String(value);
  }

  async function start() {
    if (!enabled) {
      console.info('[onga-stage13] disabled; use ?stage13=1 for the opt-in integration path');
      return { enabled: false, installed: false };
    }

    try {
      if (!window.OngaStage13?.load) throw new Error('onga_stage13_runtime.js is not loaded');
      if (!window.OngaStage13FluidDomainPatch?.install) {
        throw new Error('onga_stage13_fluid_domain_patch.js is not loaded');
      }
      if (!window.OngaStage13Bridge?.install) throw new Error('onga_stage13_bridge.js is not loaded');

      const authority = await window.OngaStage13.load();
      const fluidDomainPatch = window.OngaStage13FluidDomainPatch.install(authority);
      const bridge = window.OngaStage13Bridge.install();
      setDataset('ongaStage13PixelCount', authority.water.pixelCount);
      setDataset('ongaStage13Georef', 'ready');
      setDataset(
        'ongaStage13GeorefMaxError',
        authority.diagnostics.controlPointValidation.maxPixelError.toExponential(3),
      );
      await bridge.refresh();
      setDataset('ongaStage13', 'ready');
      return { enabled: true, installed: true, authority, fluidDomainPatch, bridge };
    } catch (error) {
      setDataset('ongaStage13', 'error');
      window.__ONGA_STAGE13_ERROR__ = error;
      console.error('[onga-stage13] opt-in bootstrap failed; legacy simulation remains active', error);
      return { enabled: true, installed: false, error };
    }
  }

  window.OngaStage13Bootstrap = Object.freeze({ enabled, start });
  window.addEventListener('load', () => {
    void start();
  }, { once: true });
})();
