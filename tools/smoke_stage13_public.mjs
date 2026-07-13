import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const baseUrl = (process.env.PUBLIC_BASE_URL || 'https://fujisawa-lab-inside.github.io/fishing').replace(/\/$/, '');
const outputDirectory = 'stage13-public-smoke';
const chrome = process.env.CHROME_BIN || process.env.CHROME_PATH || 'google-chrome';
const deploymentId = process.env.GITHUB_SHA || String(Date.now());
const expectedAssetVersion = process.env.STAGE13_ASSET_VERSION || 'stage13g';

const wrappers = {
  pc: 'OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
  mobile: 'OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
};

const cases = [
  { name: 'pc-legacy', file: wrappers.pc, size: '1440,1000', stage13: false },
  { name: 'pc-stage13', file: wrappers.pc, size: '1440,1000', stage13: true },
  { name: 'mobile-legacy', file: wrappers.mobile, size: '390,844', stage13: false },
  { name: 'mobile-stage13', file: wrappers.mobile, size: '390,844', stage13: true },
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sleep(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

function publicUrl(testCase, probe = false) {
  const params = new URLSearchParams();
  if (testCase.stage13) params.set('stage13', '1');
  params.set('deploy', deploymentId);
  if (probe) params.set('probe', String(Date.now()));
  return `${baseUrl}/${testCase.file}?${params}`;
}

async function fetchText(url) {
  const response = await fetch(url, {
    redirect: 'follow',
    headers: {
      'cache-control': 'no-cache, no-store, must-revalidate',
      pragma: 'no-cache',
    },
  });
  assert(response.ok, `${url}: HTTP ${response.status}`);
  return response.text();
}

async function waitForDeployment() {
  const expectedToken = `onga_stage13_bootstrap.js?v=${expectedAssetVersion}`;
  const deadline = Date.now() + 12 * 60 * 1000;
  let last = {};
  while (Date.now() < deadline) {
    try {
      const [pc, mobile, manifest, bootstrap] = await Promise.all([
        fetchText(publicUrl(cases[0], true)),
        fetchText(publicUrl(cases[2], true)),
        fetchText(`${baseUrl}/data/onga_unified_water_manifest_r3.json?deploy=${deploymentId}&probe=${Date.now()}`),
        fetchText(`${baseUrl}/onga_stage13_bootstrap.js?deploy=${deploymentId}&probe=${Date.now()}`),
      ]);
      const parsedManifest = JSON.parse(manifest);
      last = {
        pcExpected: pc.includes(expectedToken),
        mobileExpected: mobile.includes(expectedToken),
        manifestR3: parsedManifest.schema === 'onga-unified-water-runtime-v2'
          && parsedManifest.version === 'v4.8.0-candidate-r3'
          && parsedManifest.pixelCount === 680633,
        badgeCode: bootstrap.includes('Stage 13 正解水面統合'),
      };
      if (Object.values(last).every(Boolean)) return last;
    } catch (error) {
      last = { error: String(error) };
    }
    console.log(JSON.stringify({ waitingForPublicPages: true, last }, null, 2));
    await sleep(15000);
  }
  throw new Error(`GitHub Pages did not expose deployment ${deploymentId}: ${JSON.stringify(last)}`);
}

function chromeArguments(testCase, extra = []) {
  return [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    '--no-first-run',
    '--no-default-browser-check',
    '--hide-scrollbars',
    '--force-device-scale-factor=1',
    '--run-all-compositor-stages-before-draw',
    '--virtual-time-budget=60000',
    `--window-size=${testCase.size}`,
    ...extra,
    publicUrl(testCase),
  ];
}

function runChrome(testCase, extra = []) {
  const result = spawnSync(chrome, chromeArguments(testCase, extra), {
    encoding: 'utf8',
    timeout: 150000,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  assert(result.status === 0, `${testCase.name}: Chrome exited with ${result.status}\n${result.stderr}`);
  return result;
}

function validateDom(testCase, dom) {
  assert(dom.includes('<html'), `${testCase.name}: dumped DOM lacks html element`);
  assert(!dom.includes('読込に失敗しました'), `${testCase.name}: wrapper fatal-load message is present`);
  if (!testCase.stage13) {
    assert(!/data-onga-stage13(?:=|-)/.test(dom), `${testCase.name}: legacy URL unexpectedly activated Stage 13`);
    assert(!dom.includes('onga-stage13-status-badge'), `${testCase.name}: legacy URL shows the Stage 13 badge`);
    return;
  }

  const required = [
    'data-onga-stage13="ready"',
    'data-onga-stage13-badge="ready"',
    'data-onga-stage13-pixel-count="680633"',
    'data-onga-stage13-georef="ready"',
    'data-onga-stage13-water-predicate="authority"',
    'data-onga-stage13-heatmap-route="authority"',
    'data-onga-stage13-heatmap-mismatch="0"',
    'data-onga-stage13-heatmap-clip="authority-mask"',
    'data-onga-stage13-fluid-base-patch="stage13-fluid-domain-patch-v1"',
    'data-onga-stage13-base-domain-difference-after="0"',
    'data-onga-stage13-fluid-route="authority"',
    'data-onga-stage13-fluid-domain-difference="0"',
    'data-onga-stage13-fluid-false-negative="0"',
    'data-onga-stage13-fluid-false-positive="0"',
    'data-onga-stage13-refresh="complete"',
    'Stage 13 正解水面統合：稼働中',
  ];
  for (const token of required) {
    assert(dom.includes(token), `${testCase.name}: missing public runtime diagnostic ${token}`);
  }
  assert(!dom.includes('data-onga-stage13="error"'), `${testCase.name}: Stage 13 bootstrap reported error`);
  assert(!dom.includes('data-onga-stage13="asset-error"'), `${testCase.name}: Stage 13 optional asset load failed`);
}

await fs.rm(outputDirectory, { recursive: true, force: true });
await fs.mkdir(outputDirectory, { recursive: true });
const deploymentProbe = await waitForDeployment();
const summary = [];

for (const testCase of cases) {
  const domResult = runChrome(testCase, ['--dump-dom']);
  await fs.writeFile(`${outputDirectory}/${testCase.name}.html`, domResult.stdout, 'utf8');
  await fs.writeFile(`${outputDirectory}/${testCase.name}.stderr.log`, domResult.stderr, 'utf8');
  validateDom(testCase, domResult.stdout);

  const screenshotPath = path.resolve(outputDirectory, `${testCase.name}.png`);
  runChrome(testCase, [`--screenshot=${screenshotPath}`]);
  const screenshot = await fs.stat(screenshotPath);
  assert(screenshot.size > 10000, `${testCase.name}: screenshot is unexpectedly small (${screenshot.size} bytes)`);

  summary.push({
    name: testCase.name,
    url: publicUrl(testCase),
    ok: true,
    domBytes: domResult.stdout.length,
    screenshotBytes: screenshot.size,
  });
}

const result = {
  ok: true,
  baseUrl,
  deploymentId,
  expectedAssetVersion,
  deploymentProbe,
  chrome,
  cases: summary,
};
await fs.writeFile(`${outputDirectory}/summary.json`, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(result, null, 2));
