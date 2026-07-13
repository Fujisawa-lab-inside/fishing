(() => {
  'use strict';

  const VERSION = 'stage13-runtime-v3';
  const EARTH_CIRCUMFERENCE_M = 40075016.68557849;
  const DEFAULTS = Object.freeze({
    unifiedSpecUrl: './data/onga_unified_water_manifest_r3.json',
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

    assert(manifest.schema === 'onga-unified-water-runtime-v2', '統一水面manifest schemaが不一致である');
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
      coordinateSystem: manifest.coordinateSystem,
      fishway: manifest.fishway,
      openBoundaries: manifest.openBoundaries,
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

  function barycentric(point, point0, point1, point2) {
    const [x, y] = point;
    const [x0, y0] = point0;
    const [x1, y1] = point1;
    const [x2, y2] = point2;
    const denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2);
    if (Math.abs(denominator) < 1e-12) return null;
    const weight0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / denominator;
    const weight1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / denominator;
    return [weight0, weight1, 1 - weight0 - weight1];
  }

  function meshMap(point, mesh, sourceField, targetField) {
    for (const triangle of mesh.triangles) {
      const source = triangle.map(index => mesh.anchors[index][sourceField]);
      const weights = barycentric(point, source[0], source[1], source[2]);
      if (!weights) continue;
      if (weights.every(weight => weight >= -1e-7 && weight <= 1 + 1e-7)) {
        const target = triangle.map(index => mesh.anchors[index][targetField]);
        return [
          weights[0] * target[0][0] + weights[1] * target[1][0] + weights[2] * target[2][0],
          weights[0] * target[0][1] + weights[1] * target[1][1] + weights[2] * target[2][1],
        ];
      }
    }
    return [...point];
  }

  function webMercator(lat, lng) {
    const clamped = Math.max(-85.05112878, Math.min(85.05112878, Number(lat)));
    const sinLat = Math.sin(clamped * Math.PI / 180);
    return [
      (Number(lng) + 180) / 360 * EARTH_CIRCUMFERENCE_M,
      (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * EARTH_CIRCUMFERENCE_M,
    ];
  }

  function inverseWebMercator(x, y) {
    const lng = x / EARTH_CIRCUMFERENCE_M * 360 - 180;
    const n = Math.PI - 2 * Math.PI * y / EARTH_CIRCUMFERENCE_M;
    const lat = Math.atan(Math.sinh(n)) * 180 / Math.PI;
    return { lat, lng };
  }

  function createCoordinateTransform(coordinateSystem) {
    const geographic = coordinateSystem?.geographic;
    const transform = geographic?.transform;
    const mesh = geographic?.controlMesh;
    assert(geographic?.crs === 'EPSG:4326', 'coordinateSystem geographic CRSが不正である');
    assert(transform && [transform.a, transform.b, transform.tx, transform.ty].every(Number.isFinite), 'geographic transformが不正である');
    assert(Array.isArray(mesh?.anchors) && Array.isArray(mesh?.triangles), 'control meshが不正である');
    const determinant = transform.a * transform.a + transform.b * transform.b;
    assert(determinant > 0, 'geographic transformの行列式が0である');

    function worldToBasePixel(worldX, worldY) {
      const dx = worldX - transform.tx;
      const dy = worldY - transform.ty;
      return [
        (transform.a * dx + transform.b * dy) / determinant,
        (-transform.b * dx + transform.a * dy) / determinant,
      ];
    }

    function basePixelToWorld(baseX, baseY) {
      return [
        transform.tx + transform.a * baseX - transform.b * baseY,
        transform.ty + transform.b * baseX + transform.a * baseY,
      ];
    }

    function latLngToImagePixel(lat, lng) {
      const [worldX, worldY] = webMercator(lat, lng);
      const basePixel = worldToBasePixel(worldX, worldY);
      const [x, y] = meshMap(basePixel, mesh, 'sourceBasePixel', 'targetImagePixel');
      return { x, y };
    }

    function imagePixelToLatLng(x, y) {
      const basePixel = meshMap([Number(x), Number(y)], mesh, 'targetImagePixel', 'sourceBasePixel');
      const [worldX, worldY] = basePixelToWorld(basePixel[0], basePixel[1]);
      return inverseWebMercator(worldX, worldY);
    }

    return Object.freeze({ latLngToImagePixel, imagePixelToLatLng });
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

  function createImagePredicate(decoded) {
    return (x, y) => {
      const ix = Math.floor(x);
      const iy = Math.floor(y);
      if (ix < 0 || iy < 0 || ix >= decoded.width || iy >= decoded.height) return false;
      return decoded.mask[iy * decoded.width + ix] === 1;
    };
  }

  function validateControlPoints(spec, coordinates, containsImagePixel) {
    const points = spec.coordinateSystem?.geographic?.controlPoints ?? [];
    assert(points.length > 0, 'geographic control pointがない');
    let maxPixelError = 0;
    let semanticMismatchCount = 0;
    for (const point of points) {
      const mapped = coordinates.latLngToImagePixel(point.lat, point.lng);
      const error = Math.hypot(mapped.x - point.pixel[0], mapped.y - point.pixel[1]);
      maxPixelError = Math.max(maxPixelError, error);
      const actualWater = containsImagePixel(mapped.x, mapped.y);
      const expectedWater = point.semantic === 'water';
      if (actualWater !== expectedWater) semanticMismatchCount += 1;
    }
    assert(maxPixelError <= 0.05, `control point最大誤差${maxPixelError.toFixed(6)}pxが許容値を超える`);
    assert(semanticMismatchCount === 0, `control point意味不一致が${semanticMismatchCount}件ある`);
    return Object.freeze({ maxPixelError, semanticMismatchCount, count: points.length });
  }

  async function load(options = {}) {
    const urls = { ...DEFAULTS, ...options };
    const [spec, modelConfig, inputSchema] = await Promise.all([
      loadUnifiedSpec(urls.unifiedSpecUrl),
      fetchJson(urls.modelConfigUrl),
      fetchJson(urls.inputSchemaUrl),
    ]);

    assert(spec.version === 'v4.8.0-candidate-r3', '統一仕様versionが不一致である');
    const decoded = decodeRows(spec.waterDomain);
    assert(decoded.pixelCount === spec.waterDomain.pixelCount, '水面画素数が仕様値と一致しない');
    assert(decoded.pixelCount === 680633, '承認済み水面画素数680633と一致しない');
    assert(spec.acceptanceCriteria?.runtimeDomainDifferenceCells === 0, 'runtime水面差分条件が0ではない');
    validateModelConfig(modelConfig);
    validateInputSchema(inputSchema);

    const coordinates = createCoordinateTransform(spec.coordinateSystem);
    const containsImagePixel = createImagePredicate(decoded);
    const controlPointValidation = validateControlPoints(spec, coordinates, containsImagePixel);
    const fishwayPixel = coordinates.latLngToImagePixel(spec.fishway.lat, spec.fishway.lng);
    assert(containsImagePixel(fishwayPixel.x, fishwayPixel.y), '魚道が承認済み水面外にある');
    const containsLatLng = (lat, lng) => {
      const pixel = coordinates.latLngToImagePixel(lat, lng);
      return containsImagePixel(pixel.x, pixel.y);
    };

    const authority = Object.freeze({
      version: VERSION,
      spec,
      modelConfig,
      inputSchema,
      coordinates,
      diagnostics: Object.freeze({ controlPointValidation, fishwayPixel: Object.freeze(fishwayPixel) }),
      water: Object.freeze({
        width: decoded.width,
        height: decoded.height,
        pixelCount: decoded.pixelCount,
        mask: decoded.mask,
        contains: containsImagePixel,
        containsImagePixel,
        containsLatLng,
      }),
    });

    window.OngaUnifiedAuthority = authority;
    window.dispatchEvent(new CustomEvent('onga:unified-authority-ready', { detail: authority }));
    return authority;
  }

  window.OngaStage13 = Object.freeze({
    VERSION,
    load,
    loadUnifiedSpec,
    decodeRows,
    createCoordinateTransform,
    validateControlPoints,
    validateModelConfig,
    validateInputSchema,
  });
})();
