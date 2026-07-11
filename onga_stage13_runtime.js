(() => {
  'use strict';

  const DEFAULTS = Object.freeze({
    unifiedSpecUrl: './data/onga_unified_water_manifest_r2.json',
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

  async function loadUnifiedSpec(url) {
    const manifest = await fetchJson(url);
    if (manifest.waterDomain?.rows) return manifest;

    assert(manifest.schema === 'onga-unified-water-runtime-v1', '統一水面manifest schemaが不一致である');
    assert(Array.isArray(manifest.chunks) && manifest.chunks.length > 0, '水面row chunkがない');

    const chunks = await Promise.all(manifest.chunks.map(fetchJson));
    const rows = Array.from({ length: manifest.height }, () => null);
    for (const chunk of chunks) {
      assert(Number.isInteger(chunk.startRow), 'chunk.startRowが不正である');
      assert(Array.isArray(chunk.rows), 'chunk.rowsが不正である');
      chunk.rows.forEach((runs, offset) => {
        const y = chunk.startRow + offset;
        assert(y >= 0 && y < rows.length, `chunk row ${y}が範囲外である`);
        assert(rows[y] === null, `chunk row ${y}が重複している`);
        rows[y] = runs;
      });
    }
    assert(rows.every(Array.isArray), '水面row chunkに欠落がある');

    return {
      schema: 'onga-unified-spec-v1',
      version: manifest.version,
      acceptanceCriteria: manifest.acceptanceCriteria,
      waterDomain: {
        width: manifest.width,
        height: manifest.height,
        pixelCount: manifest.pixelCount,
        rows,
      },
    };
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
      let previousEnd = -1;
      for (let i = 0; i < runs.length; i += 2) {
        const x0 = runs[i];
        const x1 = runs[i + 1];
        assert(Number.isInteger(x0) && Number.isInteger(x1), `rows[${y}] の座標が整数でない`);
        assert(0 <= x0 && x0 <= x1 && x1 < width, `rows[${y}] のrunが範囲外である`);
        assert(x0 > previousEnd, `rows[${y}] のrunが重複または未整列である`);
        mask.fill(1, y * width + x0, y * width + x1 + 1);
        count += x1 - x0 + 1;
        previousEnd = x1;
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
      loadUnifiedSpec(urls.unifiedSpecUrl),
      fetchJson(urls.modelConfigUrl),
      fetchJson(urls.inputSchemaUrl),
    ]);

    assert(spec.version === 'v4.8.0-candidate-r2', '統一仕様versionが不一致である');
    const decoded = decodeRows(spec.waterDomain);
    assert(decoded.pixelCount === spec.waterDomain.pixelCount, '水面画素数が仕様値と一致しない');
    assert(decoded.pixelCount === 679791, '承認済み水面画素数679791と一致しない');
    assert(spec.acceptanceCriteria?.runtimeDomainDifferenceCells === 0, 'runtime水面差分条件が0ではない');
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

  window.OngaStage13 = Object.freeze({
    load,
    loadUnifiedSpec,
    decodeRows,
    validateModelConfig,
    validateInputSchema,
  });
})();