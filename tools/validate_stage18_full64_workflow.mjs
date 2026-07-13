import fs from 'node:fs/promises';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const workflowPath = '.github/workflows/stage18-full64-run.yml';
const workflow = (await fs.readFile(workflowPath, 'utf8')).replaceAll('\r\n', '\n');

function topLevelBlock(name) {
  const marker = `${name}:\n`;
  const start = workflow.indexOf(marker);
  assert(start >= 0, `missing top-level workflow block: ${name}`);
  const remainder = workflow.slice(start + marker.length);
  const next = remainder.search(/^\S/m);
  return next >= 0 ? workflow.slice(start, start + marker.length + next) : workflow.slice(start);
}

function assertUniqueOrdered(section, markers, label) {
  let previous = -1;
  for (const marker of markers) {
    const index = section.indexOf(marker);
    assert(index >= 0, `${label} step missing: ${marker}`);
    assert(section.lastIndexOf(marker) === index, `${label} step must be unique: ${marker}`);
    assert(index > previous, `${label} step order invalid at: ${marker}`);
    previous = index;
  }
}

const expectedOn = `on:
  workflow_dispatch:
    inputs:
      confirmation:
        description: 'Exact confirmation phrase for the one authorized 64-case run'
        required: true
        type: string

`;
assert(topLevelBlock('on') === expectedOn, 'full64 workflow trigger and input contract must match exactly');

const expectedPermissions = `permissions:
  actions: read
  contents: read

`;
assert(topLevelBlock('permissions') === expectedPermissions, 'workflow permissions must be exactly actions:read and contents:read');
assert((workflow.match(/^\s*permissions:/gm) || []).length === 1, 'job-level or duplicate permissions are forbidden');

const jobsBlock = topLevelBlock('jobs');
const jobNames = [...jobsBlock.matchAll(/^  ([A-Za-z0-9_-]+):$/gm)].map((match) => match[1]);
assert(JSON.stringify(jobNames) === JSON.stringify(['authorize', 'full64']), 'workflow must contain only authorize and full64 jobs');
const authorizeStart = jobsBlock.indexOf('  authorize:\n');
const full64Start = jobsBlock.indexOf('  full64:\n');
assert(authorizeStart >= 0 && full64Start > authorizeStart, 'authorize/full64 job ordering invalid');
const authorizeJob = jobsBlock.slice(authorizeStart, full64Start);
const full64Job = jobsBlock.slice(full64Start);

for (const required of [
  'actions: read',
  'contents: read',
  'group: stage18-full64-one-time-20260713',
  'cancel-in-progress: false',
  'Validate dispatch identity and scope',
  "test \"$CONFIRMATION\" = 'RUN_STAGE18_FULL64_20260713'",
  "test \"$REPOSITORY\" = 'Fujisawa-lab-inside/fishing'",
  "test \"$ACTOR\" = 'RyusukeFujisawa'",
  "test \"$REF\" = 'refs/heads/main'",
  "test \"$RUN_ATTEMPT\" = '1'",
  'Consume one-time authorization',
  'actions/workflows/stage18-full64-run.yml/runs?event=workflow_dispatch',
  'timeout-minutes: 90',
  'timeout --signal=TERM --kill-after=30s 65m',
  '--progress-output stage18-full64/full64-progress.json',
  'node tools/evaluate_stage18_full64.mjs',
  'stage18-full64/full64-report.json\n          stage18-full64/full64-fields.npz\n          stage18-full64/full64-evaluation.json',
  'Verify complete result set',
  'stage18-full64-results-${{ github.run_id }}',
  'stage18-full64-diagnostics-${{ github.run_id }}',
  'if-no-files-found: error',
  'retention-days: 90',
]) assert(workflow.includes(required), `required workflow safeguard missing: ${required}`);

assert(!/^\s+if:\s*\$\{\{\s*inputs\.confirmation/m.test(workflow), 'confirmation must fail explicitly, not skip the job');
assert(!workflow.includes('continue-on-error:'), 'authorization or full64 failures must never be ignored');
for (const required of [
  'Validate dispatch identity and scope',
  "test \"$CONFIRMATION\" = 'RUN_STAGE18_FULL64_20260713'",
  "test \"$REPOSITORY\" = 'Fujisawa-lab-inside/fishing'",
  "test \"$ACTOR\" = 'RyusukeFujisawa'",
  "test \"$REF\" = 'refs/heads/main'",
  "test \"$RUN_ATTEMPT\" = '1'",
  'Consume one-time authorization',
  'gh api --paginate',
  'select(.id != ${RUN_ID})',
  'select(.name == "Consume one-time authorization" and .conclusion == "success")',
  'exit 1',
]) assert(authorizeJob.includes(required), `authorize job safeguard missing: ${required}`);
assert(!/^\s+if:/m.test(authorizeJob), 'authorize steps must not be conditionally skipped');
assertUniqueOrdered(authorizeJob, [
  '- name: Validate dispatch identity and scope',
  '- name: Consume one-time authorization',
], 'authorize job');
assert(
  authorizeJob.indexOf('      - ') === authorizeJob.indexOf('      - name: Validate dispatch identity and scope'),
  'identity validation must be the first authorize step',
);

for (const required of [
  'needs: authorize',
  'Reject rerun attempts',
  'RUN_ATTEMPT: ${{ github.run_attempt }}',
  "test \"$RUN_ATTEMPT\" = '1'",
  'timeout-minutes: 90',
]) assert(full64Job.includes(required), `full64 job safeguard missing: ${required}`);
assertUniqueOrdered(full64Job, [
  '- name: Reject rerun attempts',
  '- uses: actions/checkout@v4',
  '- uses: actions/setup-node@v4',
  '- uses: actions/setup-python@v5',
  '- name: Install dependencies',
  '- name: Validate explicit authorization and canonical ensemble',
  '- name: Generate frozen production mesh',
  '- name: Generate deterministic 64-case ensemble',
  '- name: Run exactly 64 numerical cases',
  '- name: Evaluate full64 report and bind provenance',
  '- name: Aggregate offline step-matched statistics',
  '- name: Verify complete result set',
  'name: stage18-full64-results-${{ github.run_id }}',
  'name: stage18-full64-diagnostics-${{ github.run_id }}',
], 'full64 job');
assert(
  full64Job.indexOf('      - ') === full64Job.indexOf('      - name: Reject rerun attempts'),
  'rerun rejection must be the first full64 step',
);

assert((workflow.match(/uses: actions\/upload-artifact@v4/g) || []).length === 2, 'separate result and diagnostic uploads required');
assert(workflow.includes('persist-credentials: false'), 'checkout credentials must not persist');

const resultStepStart = full64Job.indexOf('      - uses: actions/upload-artifact@v4');
const resultPathStart = full64Job.indexOf('name: stage18-full64-results-${{ github.run_id }}');
const diagnosticStepStart = full64Job.lastIndexOf('      - uses: actions/upload-artifact@v4');
const diagnosticPathStart = full64Job.indexOf('name: stage18-full64-diagnostics-${{ github.run_id }}');
assert(resultStepStart >= 0 && resultPathStart > resultStepStart && diagnosticPathStart > resultPathStart, 'result/diagnostic upload order invalid');
assert(diagnosticStepStart > resultPathStart && diagnosticStepStart < diagnosticPathStart, 'diagnostic upload step boundary invalid');
const resultUpload = full64Job.slice(resultStepStart, diagnosticStepStart);
const diagnosticUpload = full64Job.slice(diagnosticStepStart);
assert(!/^\s+if:/m.test(resultUpload), 'success result upload must not be conditional');
assert(diagnosticUpload.includes('if: ${{ failure() || cancelled() }}'), 'diagnostic upload must run only after failure or cancellation');
assert((diagnosticUpload.match(/^\s+if:/gm) || []).length === 1, 'diagnostic upload must have exactly one condition');
assert(diagnosticUpload.includes('if-no-files-found: warn'), 'diagnostic upload must tolerate partial output');
for (const requiredArtifact of [
  'onga_stage16_metric_fv_mesh_v1.npz',
  'stage16_metric_mesh_summary.json',
  'ensemble.json',
  'full64-progress.json',
  'full64-report.json',
  'full64-fields.npz',
  'full64-evaluation.json',
  'full64-statistics.npz',
  'full64-statistics-summary.json',
]) assert(resultUpload.includes(requiredArtifact), `required result artifact missing: ${requiredArtifact}`);

const report = {
  schema: 'onga-stage18-full64-workflow-validation-v1',
  status: 'passed',
  verified: [
    'workflow_dispatch-only trigger',
    'read-only repository and Actions permissions',
    'authorized repository, actor, main ref, confirmation, and first attempt',
    'serialized one-time authorization consumption check',
    'full64 job depends on authorization and independently rejects reruns',
    'bounded runtime',
    'provenance-bound evaluation',
    'complete success artifacts separated from failure diagnostics',
  ],
};
await fs.writeFile('stage18-full64-workflow-validation.json', `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
