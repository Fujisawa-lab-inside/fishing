import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const gui = await readFile(
  new URL('../onga_stage20_gui.mjs', import.meta.url),
  'utf8',
);

async function freshModule(relativePath, label) {
  const url = new URL(relativePath, import.meta.url);
  url.searchParams.set('m0-security-test', label);
  return import(url.href);
}

function securityFields(token) {
  return {
    csrfToken: token,
    csrfHeaderName: 'X-Stage20-CSRF-Token',
    requestSecurity: {
      loopbackHostRequired: true,
      sameOriginRequired: true,
      applicationJsonRequired: true,
      perProcessCsrfToken: true,
    },
  };
}


test('locks the submitted gate pattern while the local solver is running', () => {
  assert.match(gui, /localRequestedCapacity: null/);
  assert.match(
    gui,
    /const pattern = busy && state\.localRequestedCapacity[\s\S]*?\? state\.localRequestedCapacity[\s\S]*?: effectiveGatePattern\(\)/,
  );
  assert.match(gui, /state\.localRequestedCapacity = capacity;[\s\S]*?state\.localServiceState = 'running'/);
});

test('local solver POST is impossible before the same-origin security handshake', async () => {
  const local = await freshModule('../onga_stage20_local_simulation.mjs', 'missing-local-token');
  let fetchCalled = false;
  await assert.rejects(
    local.createStage20LocalSimulationJob([0, 0, 0, 0, 0, 0, 0, 0], 5, {
      fetchImpl: async () => {
        fetchCalled = true;
        throw new Error('fetch must not run');
      },
    }),
    /security handshake is required/,
  );
  assert.equal(fetchCalled, false);
});

test('local solver POST carries the per-process CSRF token after probing', async () => {
  const local = await freshModule('../onga_stage20_local_simulation.mjs', 'valid-local-token');
  const token = 'local_token_abcdefghijklmnopqrstuvwxyz0123456789';
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/stage20/local/capabilities') {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          schema: 'onga-stage20-local-simulator-capabilities-v1',
          status: 'READY_FOR_EXPLICIT_LOCAL_RUN',
          localOnly: true,
          meshId: 'candidate_C_R1C_exact_confluence_R20_patches',
          cellCount: 37724,
          fishwayMode: 'always_enabled_C2_1_storage_tau60',
          classification: {
            localRunnerAvailable: true,
            runtimeInputsVerified: true,
            solverExecutionPreflightPassed: false,
            physicalSolverConnected: false,
            physicalCalibration: false,
            fieldPrediction: false,
          },
          ...securityFields(token),
        }),
      };
    }
    return {
      ok: true,
      status: 202,
      json: async () => ({
        schema: 'onga-stage20-local-simulator-job-v1',
        jobId: 'local-20260826T120000-012345abcdef',
        completed: false,
      }),
    };
  };
  await local.probeStage20LocalSimulator({ fetchImpl });
  await local.createStage20LocalSimulationJob([0, 1, 0, 1, 0, 1, 0, 1], 5, { fetchImpl });
  const post = calls.at(-1);
  assert.equal(post.url, '/api/stage20/local/jobs');
  assert.equal(post.options.method, 'POST');
  assert.equal(post.options.mode, 'same-origin');
  assert.equal(post.options.headers['Content-Type'], 'application/json');
  assert.equal(post.options.headers['X-Stage20-CSRF-Token'], token);
});

test('offline forcing POST carries CSRF and refuses to build before probing', async () => {
  const missing = await freshModule('../onga_stage20_forcing_integration.mjs', 'missing-forcing-token');
  let missingFetchCalled = false;
  await assert.rejects(
    missing.buildStage20IntegratedForcing(
      { requestedDate: '2026-02-15', csvFile: new Blob(['fixture']) },
      {
        fetchImpl: async () => {
          missingFetchCalled = true;
          throw new Error('fetch must not run');
        },
      },
    ),
    /security handshake is required/,
  );
  assert.equal(missingFetchCalled, false);

  const forcing = await freshModule('../onga_stage20_forcing_integration.mjs', 'valid-forcing-token');
  const token = 'forcing_token_abcdefghijklmnopqrstuvwxyz0123456789';
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/stage20/forcing/capabilities') {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          schema: 'onga-stage20-parallel-forcing-capabilities-v1',
          status: 'READY_OFFLINE',
          localOnly: true,
          offlineOnly: true,
          networkFetchAllowed: false,
          availableTideSnapshotYears: [2026],
          availableRequestedDateRanges: [
            { start: '2026-01-02', end: '2026-12-30' },
          ],
          defaultRequestedDate: '2026-02-15',
          pointCount: 37,
          connection: {
            guiDisplay: true,
            automaticGateSelection: true,
            localR1CGateOnlyRun: true,
            riverAndTideBoundaryPhysics: false,
          },
          ...securityFields(token),
        }),
      };
    }
    return {
      ok: false,
      status: 409,
      json: async () => ({ message: 'stop after request inspection' }),
    };
  };
  await forcing.probeStage20ForcingIntegration({ fetchImpl });
  await assert.rejects(
    forcing.buildStage20IntegratedForcing(
      { requestedDate: '2026-02-15', csvFile: new Blob(['fixture']) },
      { fetchImpl },
    ),
    /stop after request inspection/,
  );
  const post = calls.at(-1);
  assert.equal(post.url, '/api/stage20/forcing/build');
  assert.equal(post.options.method, 'POST');
  assert.equal(post.options.mode, 'same-origin');
  assert.equal(post.options.headers['Content-Type'], 'application/json');
  assert.equal(post.options.headers['X-Stage20-CSRF-Token'], token);
});
