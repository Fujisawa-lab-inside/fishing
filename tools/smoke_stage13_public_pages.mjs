import fs from 'node:fs/promises';
import { spawnSync } from 'node:child_process';

const baseUrl = 'https://fujisawa-lab-inside.github.io/fishing';
const outputDirectory = 'stage13-pages-smoke';
const chrome = process.env.CHROME_BIN || process.env.CHROME_PATH || 'google-chrome';
const stamp = Date.now();

const cases = [
  {
    name: 'pc-legacy',
    path: '/OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
    size: '1440,1000',
    stage13: false,
  },
  {
    name: 'pc-stage13',
    path: `/OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html?stage13=1&pagesSmoke=${stamp}`,
    size: '1440,1000',
    stage13: true,
  },
  {
    name: 'mobile-legacy',
    path: '/OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
    size: '390,844',
    stage13: false,
  },
  {
    name: 'mobile-stage13',
    path: `/OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html?stage13=1&pagesSmoke=${stamp}`,
    size: '390,844',
    stage13: true,
  },
];

const requiredStage13Tokens = [
  'data-onga-stage13="ready"',
  'data-onga-stage13-pixel-count="679791"',
  'data-onga-stage13-georef="ready"',
  'data-onga-stage13-water-predicate="authority"',
  'data-onga-stage13-heatmap-route="authority"',
  'data-onga-stage13-fluid-route="authority"',
  'data-onga-stage13-heatmap-mismatch="0"',
  'data-onga-stage13-fluid-domain-difference="0"',
  'data-onga-stage13-refresh="complete"',
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function chromeArgs(testCase, mode, outputPath = null) {
  const url = `${baseUrl}${testCase.path}`;
  const args = [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    '--no-first-run',
    '--no-default-browser-check',
    '--hide-scrollbars',
    '--run-all-compositor-stages-before-draw',
    '--virtual-time-budget=90000',
    `--window-size=${testCase.size}`,
  ];
  if (mode === 'dom') args.push('--dump-dom');
  if (mode === 'screenshot') args.push(`--screenshot=${outputPath}`);
  args.push(url);
  return { url, args };
}

function runChrome(testCase, mode, outputPath = null) {
  const { url, args } = chromeArgs(testCase, mode, outputPath);
  const result = spawnSync(chrome, args, {
    encoding: 'utf8',
    timeout: 180000,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  assert(result.status === 0, `${testCase.name}: Chrome exited with ${result.status}\n${result.stderr}`);
  return { url, dom: result.stdout, stderr: result.stderr };
}

function validateDom(testCase, dom) {
  const missing = [];
  if (!dom.includes('<html')) missing.push('html element');
  if (dom.includes('読込に失敗しました')) missing.push('wrapper fatal-load message absent');
  if (testCase.stage13) {
    for (const token of requiredStage13Tokens) {
      if (!dom.includes(token)) missing.push(token);
    }
    if (dom.includes('data-onga-stage13="error"')) missing.push('no Stage 13 bootstrap error');
    if (dom.includes('data-onga-stage13="asset-error"')) missing.push('no Stage 13 asset error');
  } else if (/data-onga-stage13(?:=|-)/.test(dom)) {
    missing.push('legacy URL must not activate Stage 13');
  }
  return missing;
}

async function sleep(ms) {
  await new Promise(resolve => setTimeout(resolve, ms));
}

await fs.mkdir(outputDirectory, { recursive: true });
const summary = [];

for (const testCase of cases) {
  let finalResult = null;
  let missing = [];
  const attempts = testCase.stage13 ? 8 : 2;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const result = runChrome(testCase, 'dom');
    missing = validateDom(testCase, result.dom);
    await fs.writeFile(`${outputDirectory}/${testCase.name}-attempt-${attempt}.html`, result.dom, 'utf8');
    await fs.writeFile(`${outputDirectory}/${testCase.name}-attempt-${attempt}.stderr.log`, result.stderr, 'utf8');
    finalResult = result;
    if (missing.length === 0) break;
    if (attempt < attempts) await sleep(20000);
  }

  const screenshotPath = `${outputDirectory}/${testCase.name}.png`;
  try {
    runChrome(testCase, 'screenshot', screenshotPath);
  } catch (error) {
    await fs.writeFile(`${outputDirectory}/${testCase.name}-screenshot-error.txt`, String(error), 'utf8');
  }

  summary.push({
    name: testCase.name,
    url: finalResult?.url ?? `${baseUrl}${testCase.path}`,
    stage13: testCase.stage13,
    ok: missing.length === 0,
    missing,
    domBytes: finalResult?.dom.length ?? 0,
  });
}

const report = {
  ok: summary.every(item => item.ok),
  testedAt: new Date().toISOString(),
  chrome,
  baseUrl,
  cases: summary,
};
await fs.writeFile(`${outputDirectory}/summary.json`, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
assert(report.ok, `public Pages smoke failed: ${JSON.stringify(summary.filter(item => !item.ok))}`);
