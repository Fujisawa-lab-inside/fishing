import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { Worker } from 'node:worker_threads';

const baseUrl = new URL(process.argv[2] || 'http://127.0.0.1:4173/');
const workerModule = pathToFileURL(resolve('onga_stage20_reference_worker.mjs')).href;
const wrapper = `
  import { parentPort } from 'node:worker_threads';
  globalThis.self = {
    addEventListener(type, callback) {
      if (type === 'message') parentPort.on('message', data => callback({ data }));
    },
    postMessage(data) { parentPort.postMessage(data); },
  };
  await import(${JSON.stringify(workerModule)});
  parentPort.postMessage({ type: 'ready' });
`;
const worker = new Worker(new URL(`data:text/javascript,${encodeURIComponent(wrapper)}`), { type: 'module' });
const result = await new Promise((resolveResult, reject) => {
  const timeout = setTimeout(() => reject(new Error('worker validation timed out')), 30000);
  worker.on('error', reject);
  worker.on('message', message => {
    if (message.type === 'ready') {
      worker.postMessage({
        type: 'run-still-water-benchmark',
        meshManifestUrl: new URL('public/data/onga/stage20/mesh-v2.json', baseUrl).href,
        wasmUrl: new URL('public/wasm/stage20-reference-kernel-v1.wasm', baseUrl).href,
      });
      return;
    }
    clearTimeout(timeout);
    resolveResult(message);
  });
});
await worker.terminate();
if (result.status !== 'passed') throw new Error(result.error || 'worker benchmark failed');
if (result.meshSchema !== 'onga-stage20-browser-mesh-v2') throw new Error('worker mesh schema mismatch');
if (result.meshSha256 !== '09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659') throw new Error('worker mesh digest mismatch');
if (result.counts.cells !== 50199 || result.counts.barrageFaces !== 68) throw new Error('worker mesh identity mismatch');
if (Math.abs(result.dtSeconds - 0.0033593783763900234) > 1e-15) throw new Error('worker stable timestep mismatch');
if (result.maxVelocity > 1e-10 || result.maxDepthDrift > 1e-10 || result.nonFinite !== 0) {
  throw new Error('worker still-water invariant failed');
}
console.log(JSON.stringify(result, null, 2));
