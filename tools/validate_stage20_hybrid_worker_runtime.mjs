import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { Worker } from 'node:worker_threads';

const baseUrl = new URL(process.argv[2] || 'http://127.0.0.1:4173/');
const workerModule = pathToFileURL(resolve('onga_stage20_hybrid_worker.mjs')).href;
const inputs = JSON.parse(await readFile('public/data/onga/stage20/hybrid-synthetic-input-v1.json', 'utf8'));
const wrapper = `
  import { parentPort } from 'node:worker_threads';
  globalThis.self = {
    addEventListener(type, callback) {
      if (type === 'message') parentPort.on('message', data => callback({ data }));
    },
    postMessage(data, transfer) { parentPort.postMessage(data, transfer); },
  };
  await import(${JSON.stringify(workerModule)});
  parentPort.postMessage({ type: 'ready' });
`;
const worker = new Worker(new URL(`data:text/javascript,${encodeURIComponent(wrapper)}`), { type: 'module' });
const result = await new Promise((resolveResult, reject) => {
  const timeout = setTimeout(() => reject(new Error('hybrid worker validation timed out')), 30000);
  worker.on('error', reject);
  worker.on('message', message => {
    if (message.type === 'ready') {
      worker.postMessage({
        type: 'run-hybrid-synthesis',
        responseManifestUrl: new URL('public/data/onga/stage20/response-pack-synthetic-v2.json', baseUrl).href,
        inputs,
        includeOutput: true,
      });
      return;
    }
    clearTimeout(timeout);
    resolveResult(message);
  });
});
await worker.terminate();
if (result.status !== 'passed') throw new Error(result.error || 'hybrid worker benchmark failed');
if (result.responsePackStatus !== 'synthetic_browser_benchmark_only') throw new Error('physical pack unexpectedly used');
if (result.meshSchema !== 'onga-stage20-browser-mesh-v2') throw new Error('hybrid mesh schema mismatch');
if (result.meshSha256 !== '09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659') throw new Error('hybrid mesh digest mismatch');
if (result.snapshotCount !== 37 || result.cellCount !== 50199) throw new Error('hybrid output identity mismatch');
if (result.hourRange[0] !== -12 || result.hourRange[1] !== 24 || result.intervalHours !== 1) throw new Error('hybrid time contract mismatch');
if (result.diagnostics.nonFiniteValueCount !== 0) throw new Error('hybrid worker output is non-finite');
if (!(result.fields instanceof Float32Array) || result.fields.byteLength !== result.outputBytes) throw new Error('hybrid output transfer failed');
result.outputTransferValidated = true;
delete result.fields;
console.log(JSON.stringify(result, null, 2));
