import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';

const port = 4173;
const baseUrl = `http://127.0.0.1:${port}`;
const outputDirectory = 'stage13-browser-smoke';
const chrome = process.env.CHROME_BIN || process.env.CHROME_PATH || 'google-chrome';

const cases = [
  { name: 'pc-legacy', path: '/OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html', size: '1440,1000', stage13: false },
  { name: 'pc-stage13', path: '/OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html?stage13=1', size: '1440,1000', stage13: true },
  { name: 'mobile-legacy', path: '/OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html', size: '390,844', stage13: false },
  { name: 'mobile-stage13', path: '/OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html?stage13=1', size: '390,844', stage13: true },
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForPort(host, targetPort, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await new Promise(resolve => {
      const socket = net.createConnection({ host, port: targetPort });
      socket.once('connect', () => {
        socket.destroy();
        resolve(true);
      });
      socket.once('error', () => resolve(false));
      socket.setTimeout(500, () => {
        socket.destroy();
        resolve(false);
      });
    });
    if (ready) return;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error(`static server did not start on ${host}:${targetPort}`);
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
    '--virtual-time-budget=45000',
    `--window-size=${testCase.size}`,
    ...extra,
    `${baseUrl}${testCase.path}`,
  ];
}

function runChrome(testCase, extra = []) {
  const result = spawnSync(chrome, chromeArguments(testCase, extra), {
    encoding: 'utf8',
    timeout: 120000,
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
    return;
  }

  const required = [
    'data-onga-stage13="ready"',
    'data-onga-stage13-pixel-count="679791"',
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
  ];
  for (const token of required) {
    assert(dom.includes(token), `${testCase.name}: missing runtime diagnostic ${token}`);
  }
  assert(!dom.includes('data-onga-stage13="error"'), `${testCase.name}: Stage 13 bootstrap reported error`);
  assert(!dom.includes('data-onga-stage13="asset-error"'), `${testCase.name}: Stage 13 optional asset load failed`);
}

await fs.rm(outputDirectory, { recursive: true, force: true });
await fs.mkdir(outputDirectory, { recursive: true });
const serverLog = await fs.open(`${outputDirectory}/server.log`, 'w');
const server = spawn(
  'python3',
  ['-m', 'http.server', String(port), '--bind', '127.0.0.1'],
  { stdio: ['ignore', serverLog.fd, serverLog.fd] },
);

try {
  await waitForPort('127.0.0.1', port);
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
      url: `${baseUrl}${testCase.path}`,
      ok: true,
      domBytes: domResult.stdout.length,
      screenshotBytes: screenshot.size,
    });
  }

  await fs.writeFile(
    `${outputDirectory}/summary.json`,
    `${JSON.stringify({ ok: true, chrome, cases: summary }, null, 2)}\n`,
    'utf8',
  );
  console.log(JSON.stringify({ ok: true, chrome, cases: summary }, null, 2));
} finally {
  server.kill('SIGTERM');
  await serverLog.close();
}
