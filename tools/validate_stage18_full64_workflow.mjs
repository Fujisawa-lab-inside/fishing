import fs from 'node:fs/promises';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const workflowPath = '.github/workflows/stage18-full64-run.yml';
const workflow = (await fs.readFile(workflowPath, 'utf8')).replaceAll('\r\n', '\n');
const expected = `name: Stage 18 superseded full64 numerical run

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  reject-superseded-v1-full64:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Reject superseded v1 full64 run
        run: |
          echo 'The v1 full64 workflow is retired after the Ashiya bridge geometry correction.' >&2
          echo 'Create a separate v2 execution contract after visual approval; this workflow cannot run numerical cases.' >&2
          exit 1
`;

assert(workflow === expected, 'retired full64 workflow must remain the exact rejection-only definition');
assert(!workflow.includes('actions/checkout@'), 'retired full64 workflow must reject before checkout');
assert(!workflow.includes('run_stage18_full64.py'), 'retired full64 workflow must not invoke the numerical runner');
assert(!workflow.includes('generate_stage16_metric_mesh.py'), 'retired full64 workflow must not generate a mesh');
assert(!workflow.includes('upload-artifact'), 'retired full64 workflow must not publish numerical artifacts');

const report = {
  schema: 'onga-stage18-full64-workflow-validation-v1',
  status: 'passed',
  full64ExecutionAllowed: false,
  verified: [
    'workflow_dispatch is rejection-only',
    'repository permission is read-only',
    'the only job exits explicitly before checkout',
    'no mesh generation, numerical runner, or artifact upload is reachable',
    'a separate v2 execution contract is required after visual approval',
  ],
};
await fs.writeFile('stage18-full64-workflow-validation.json', `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
