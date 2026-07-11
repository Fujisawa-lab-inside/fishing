(() => {
  'use strict';

  if (window.__ONGA_STAGE13_BOOTSTRAP__) return;
  window.__ONGA_STAGE13_BOOTSTRAP__ = true;

  const params = new URLSearchParams(location.search);
  const enabled = params.get('stage13') === '1';

  async function start() {
    if (!enabled) {
      console.info('[onga-stage13] disabled; use ?stage13=1 for the opt-in integration path');
      return { enabled: false, installed: false };
    }

    try {
      if (!window.OngaStage13?.load) {
        throw new Error('onga_stage13_runtime.js is not loaded');
      }
      if (!window.OngaStage13Bridge?.install) {
        throw new Error('onga_stage13_bridge.js is not loaded');
      }

      const authority = await window.OngaStage13.load();
      const bridge = window.OngaStage13Bridge.install();
      document.documentElement.dataset.ongaStage13 = 'ready';
      return { enabled: true, installed: true, authority, bridge };
    } catch (error) {
      document.documentElement.dataset.ongaStage13 = 'error';
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