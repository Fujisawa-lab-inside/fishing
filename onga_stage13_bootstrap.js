(() => {
  'use strict';

  if (window.__ONGA_STAGE13_BOOTSTRAP_V5__) return;
  window.__ONGA_STAGE13_BOOTSTRAP_V5__ = true;

  const params = new URLSearchParams(location.search);
  const enabled = params.get('stage13') === '1';
  const BADGE_ID = 'onga-stage13-status-badge';

  function setDataset(name, value) {
    document.documentElement.dataset[name] = String(value);
  }

  function ensureBadge() {
    let badge = document.getElementById(BADGE_ID);
    if (badge) return badge;
    badge = document.createElement('div');
    badge.id = BADGE_ID;
    badge.setAttribute('role', 'status');
    Object.assign(badge.style, {
      position: 'fixed',
      top: window.innerWidth <= 600 ? '64px' : '76px',
      right: window.innerWidth <= 600 ? '8px' : '16px',
      zIndex: '2147483647',
      pointerEvents: 'none',
      padding: window.innerWidth <= 600 ? '7px 10px' : '8px 12px',
      borderRadius: '999px',
      border: '1px solid rgba(0,0,0,.38)',
      boxShadow: '0 8px 24px rgba(0,0,0,.38)',
      backdropFilter: 'blur(8px)',
      fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Sans","Yu Gothic",sans-serif',
      fontSize: window.innerWidth <= 600 ? '11px' : '12px',
      fontWeight: '800',
      letterSpacing: '.02em',
      color: '#07111d',
      background: '#ffd36f',
    });
    document.body.appendChild(badge);
    return badge;
  }

  function updateBadge(status, detail = '') {
    if (!enabled || !document.body) return;
    const badge = ensureBadge();
    const state = status === 'ready' ? '稼働中' : status === 'error' ? 'エラー' : '準備中';
    badge.textContent = `Stage 13 正解水面統合：${state}`;
    badge.style.background = status === 'ready' ? '#8cff9b' : status === 'error' ? '#ff6868' : '#ffd36f';
    badge.title = detail;
    badge.dataset.status = status;
    setDataset('ongaStage13Badge', status);
  }

  async function start() {
    if (!enabled) {
      console.info('[onga-stage13] disabled; use ?stage13=1 for the opt-in integration path');
      return { enabled: false, installed: false };
    }

    updateBadge('pending', '承認済み680,633画素の正解水面authorityを読み込み中');
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
      updateBadge(
        'ready',
        `水面${authority.water.pixelCount}画素／ヒート差分0／流体差分0`,
      );
      return { enabled: true, installed: true, authority, fluidDomainPatch, bridge };
    } catch (error) {
      setDataset('ongaStage13', 'error');
      window.__ONGA_STAGE13_ERROR__ = error;
      updateBadge('error', String(error));
      console.error('[onga-stage13] opt-in bootstrap failed; legacy simulation remains active', error);
      return { enabled: true, installed: false, error };
    }
  }

  window.OngaStage13Bootstrap = Object.freeze({ enabled, start, updateBadge });
  window.addEventListener('load', () => {
    void start();
  }, { once: true });
})();
