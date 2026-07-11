(() => {
  'use strict';

  const DEFAULTS = Object.freeze({
    unifiedSpecUrl: './data/onga_unified_spec_v480_candidate_r2.json',
    modelConfigUrl: './config/onga_recommended_model_v1.json',
    inputSchemaUrl: './config/onga_physical_input_schema_v1.json',
  });

  function assert(condition, message) {
    if (!condition) throw new Error(`[onga-stage13] ${message}`);
  }

  async function fetchJson(url) {
    const response = await fetch(url, { cache: 'no-store' });
    assert(response.ok, `${url} の取得に失敗した: HTTP ${response.status}`);
    return response.json();
  }

  function decodeRows(domain) {
    const { width, height, rows } = domain;
    assert(Number.isInteger(width) && width > 0, 'waterDomain.width が不正である');
    assert(Number.isInteger(height) && height > 0, 'waterDomain.height が不正である');
    assert(Array.isArray(rows) && rows.length === height, 'waterDomain.rows の行数が不正である');

    const mask = new Uint8Array(width * height);
    let count = 0;
    rows.forEach((runs, y) => {
      assert(Array.isArray(runs) && runs.length % 2 === 0, `rows[${y}] が不正である`);
      for (let i = 0; i < runs.length; i += 2) {
        const x0 = runs[i];
        const x1 = runs[i + 1];
        assert(Number.isInteger(x0) && Number.isInteger(x1), `rows[${y}] の座標が整数でない`);
        assert(0 <= x0 && x0 <= x1 && x1 < width, `rows[${y}] のrunが範囲外である`);
        for (let x = x0; x <= x1; x += 1) {
          mask[y * width + x] = 1;
          count += 1;
        }
      }
    });
    return { width, height, mask, pixelCount: count };
  }

  function validateModelConfig(config) {
    assert(config.schema === 'onga-recommended-physical-model-v1', '物理モデル設定schemaが不一致である');
    assert(config.physicalValuesAssigned === false, '未承認の物理値が割り当て済みになっている');
    assert(config.selectedModes?.barrage?.gateCount === 8, '河口堰の門数が8ではない');
    return true;
  }

  function validateInputSchema(schema) {
    assert(schema.schema === 'onga-physical-input-v1', '物理入力schemaが不一致である');
    assert(schema.solverConnection?.enabled === false, '実値未承認のsolver接続が有効である');
    assert(schema.signConventions?.boundaryDischarge === 'outward_positive', '境界流量の符号規約が不一致である');
    return true;
  }

  function createWaterPredicate(decoded) {
    return (x, y) => {
      const ix = Math.floor(x);
      const iy = Math.floor(y);
      if (ix < 0 || iy < 0 || ix >= decoded.width || iy >= decoded.height) return false;
      return decoded.mask[iy * decoded.width + ix] === 1;
    };
  }

  async function load(options = {}) {
    const urls = { ...DEFAULTS, ...options };
    const [spec, modelConfig, inputSchema] = await Promise.all([
      fetchJson(urls.unifiedSpecUrl),
      fetchJson(urls.modelConfigUrl),
      fetchJson(urls.inputSchemaUrl),
    ]);

    assert(spec.version === 'v4.8.0-candidate-r2', '統一仕様versionが不一致である');
    const decoded = decodeRows(spec.waterDomain);
    assert(decoded.pixelCount === spec.waterDomain.pixelCount, '水面画素数が仕様値と一致しない');
    validateModelConfig(modelConfig);
    validateInputSchema(inputSchema);

    const authority = Object.freeze({
      spec,
      modelConfig,
      inputSchema,
      water: Object.freeze({
        width: decoded.width,
        height: decoded.height,
        pixelCount: decoded.pixelCount,
        mask: decoded.mask,
        contains: createWaterPredicate(decoded),
      }),
    });

    window.OngaUnifiedAuthority = authority;
    window.dispatchEvent(new CustomEvent('onga:unified-authority-ready', { detail: authority }));
    return authority;
  }

  window.OngaStage13 = Object.freeze({ load, decodeRows, validateModelConfig, validateInputSchema });
})();
