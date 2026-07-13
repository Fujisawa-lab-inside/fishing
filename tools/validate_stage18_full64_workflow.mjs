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

const visualArtifacts = [
  'full64-depth-median.png',
  'full64-velocity-median.png',
  'full64-wet-probability.png',
  'full64-direction-agreement.png',
  'full64-direction-support.png',
  'full64-judgment.svg',
  'full64-visual-manifest.json',
];
assert(visualArtifacts.length === 7, 'visual package must contain exactly five PNG maps, one judgment SVG, and one manifest');
assert(visualArtifacts.filter((name) => name.endsWith('.png')).length === 5, 'visual package must contain exactly five PNG maps');

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
  'Validate active authorization gate',
  'node tools/validate_stage18_full64_gate.mjs --require-active',
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
  'python tools/render_stage18_full64_visuals.py',
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
  'actions/checkout@v4',
  'persist-credentials: false',
  'actions/setup-node@v4',
  "node-version: '22'",
  'Validate active authorization gate',
  'node tools/validate_stage18_full64_gate.mjs --require-active',
  'Consume one-time authorization',
  'gh api --paginate',
  'select(.id != ${RUN_ID})',
  'select(.name == "Consume one-time authorization" and .conclusion == "success")',
  'exit 1',
]) assert(authorizeJob.includes(required), `authorize job safeguard missing: ${required}`);
assert(!/^\s+if:/m.test(authorizeJob), 'authorize steps must not be conditionally skipped');
assertUniqueOrdered(authorizeJob, [
  '- name: Validate dispatch identity and scope',
  '- uses: actions/checkout@v4',
  '- uses: actions/setup-node@v4',
  '- name: Validate active authorization gate',
  '- name: Consume one-time authorization',
], 'authorize job');
assert(
  authorizeJob.indexOf('      - ') === authorizeJob.indexOf('      - name: Validate dispatch identity and scope'),
  'identity validation must be the first authorize step',
);
const gateStepStart = authorizeJob.indexOf('      - name: Validate active authorization gate');
const consumeStepStart = authorizeJob.indexOf('      - name: Consume one-time authorization');
const expectedGateStep = `      - name: Validate active authorization gate
        run: node tools/validate_stage18_full64_gate.mjs --require-active
`;
assert(gateStepStart >= 0 && consumeStepStart > gateStepStart, 'active gate must precede authorization consumption');
assert(
  authorizeJob.slice(gateStepStart, consumeStepStart) === expectedGateStep,
  'active-gate validation must immediately precede authorization consumption',
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
  '- name: Render visual judgment package',
  '- name: Verify complete result set',
  'name: stage18-full64-results-${{ github.run_id }}',
  '- name: Render STOP diagnostic image',
  'name: stage18-full64-diagnostics-${{ github.run_id }}',
], 'full64 job');
assert(
  full64Job.indexOf('      - ') === full64Job.indexOf('      - name: Reject rerun attempts'),
  'rerun rejection must be the first full64 step',
);

const expectedVisualStep = `      - name: Render visual judgment package
        run: >-
          python tools/render_stage18_full64_visuals.py
          stage18-full64/onga_stage16_metric_fv_mesh_v1.npz
          stage18-full64/full64-statistics.npz
          stage18-full64/full64-statistics-summary.json
          stage18-full64/full64-report.json
          stage18-full64/full64-evaluation.json
          config/stage18_full64_run_authorization_v1.json
          --output-dir stage18-full64
`;
assert(full64Job.includes(expectedVisualStep), 'visual renderer interface must match the provenance-bound contract exactly');
assert(
  full64Job.lastIndexOf(expectedVisualStep) === full64Job.indexOf(expectedVisualStep),
  'visual renderer interface must be unique',
);
const visualStepStart = full64Job.indexOf('      - name: Render visual judgment package');
const verifyStepStart = full64Job.indexOf('      - name: Verify complete result set');
assert(visualStepStart >= 0 && verifyStepStart > visualStepStart, 'visual renderer must precede complete-result verification');
const visualStep = full64Job.slice(visualStepStart, verifyStepStart);
assert(!/^\s+if:/m.test(visualStep), 'visual rendering must be an unconditional success-path step');

assert((workflow.match(/uses: actions\/upload-artifact@v4/g) || []).length === 2, 'separate result and diagnostic uploads required');
assert(workflow.includes('persist-credentials: false'), 'checkout credentials must not persist');

const resultStepStart = full64Job.indexOf('      - uses: actions/upload-artifact@v4');
const resultPathStart = full64Job.indexOf('name: stage18-full64-results-${{ github.run_id }}');
const diagnosticRenderStepStart = full64Job.indexOf('      - name: Render STOP diagnostic image');
const diagnosticStepStart = full64Job.lastIndexOf('      - uses: actions/upload-artifact@v4');
const diagnosticPathStart = full64Job.indexOf('name: stage18-full64-diagnostics-${{ github.run_id }}');
assert(resultStepStart >= 0 && resultPathStart > resultStepStart && diagnosticPathStart > resultPathStart, 'result/diagnostic upload order invalid');
assert(diagnosticRenderStepStart > resultPathStart, 'diagnostic renderer must follow the success upload');
assert(diagnosticStepStart > diagnosticRenderStepStart && diagnosticStepStart < diagnosticPathStart, 'diagnostic upload step boundary invalid');
const resultUpload = full64Job.slice(resultStepStart, diagnosticRenderStepStart);
const diagnosticRenderStep = full64Job.slice(diagnosticRenderStepStart, diagnosticStepStart);
const diagnosticUpload = full64Job.slice(diagnosticStepStart);
assert(!/^\s+if:/m.test(resultUpload), 'success result upload must not be conditional');

const expectedDiagnosticRenderStep = `      - name: Render STOP diagnostic image
        if: \${{ failure() || cancelled() }}
        env:
          RUN_ID: \${{ github.run_id }}
          REPOSITORY: \${{ github.repository }}
        run: >-
          python tools/render_stage18_full64_diagnostic.py
          --work-dir stage18-full64
          --output stage18-full64/full64-diagnostic-stop.svg
          --workflow-run-id "$RUN_ID"
          --repository "$REPOSITORY"
`;
assert(diagnosticRenderStep === expectedDiagnosticRenderStep, 'STOP diagnostic renderer step and command must match exactly and immediately precede diagnostic upload');
assert((full64Job.match(/python tools\/render_stage18_full64_diagnostic\.py/g) || []).length === 1, 'STOP diagnostic renderer command must be unique');
assert(diagnosticUpload.includes('if: ${{ failure() || cancelled() }}'), 'diagnostic upload must run only after failure or cancellation');
assert((diagnosticUpload.match(/^\s+if:/gm) || []).length === 1, 'diagnostic upload must have exactly one condition');
assert(diagnosticUpload.includes('if-no-files-found: warn'), 'diagnostic upload must tolerate partial output');
assert(diagnosticUpload.includes('stage18-full64/full64-diagnostic-stop.svg'), 'STOP diagnostic image must be included in failure diagnostics');
assert(!resultUpload.includes('full64-diagnostic-stop.svg'), 'STOP diagnostic image must be excluded from success results');
const verifyStep = full64Job.slice(verifyStepStart, resultStepStart);
assertUniqueOrdered(
  verifyStep,
  visualArtifacts.map((artifact) => `test -s stage18-full64/${artifact}`),
  'visual result verification',
);
assertUniqueOrdered(
  resultUpload,
  visualArtifacts.map((artifact) => `stage18-full64/${artifact}`),
  'visual result upload',
);
for (const visualArtifact of visualArtifacts) {
  assert(
    verifyStep.includes(`test -s stage18-full64/${visualArtifact}`),
    `visual result verification missing: ${visualArtifact}`,
  );
  assert(resultUpload.includes(`stage18-full64/${visualArtifact}`), `required visual result artifact missing: ${visualArtifact}`);
  assert(!diagnosticUpload.includes(visualArtifact), `visual success artifact must not be included in failure diagnostics: ${visualArtifact}`);
}
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
    'disabled or retired authorization is rejected before one-time consumption',
    'serialized one-time authorization consumption check',
    'full64 job depends on authorization and independently rejects reruns',
    'bounded runtime',
    'provenance-bound evaluation',
    'success-only visual judgment package with five PNG maps and seven verified artifacts',
    'failure/cancel-only STOP diagnostic image immediately before diagnostic upload',
    'complete success artifacts separated from failure diagnostics',
  ],
};
await fs.writeFile('stage18-full64-workflow-validation.json', `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
