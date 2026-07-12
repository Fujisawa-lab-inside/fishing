import fs from 'node:fs/promises';

const files = [
  'OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
  'OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
];

for (const file of files) {
  const html = await fs.readFile(file, 'utf8');
  const required = [
    "params.get('stage13')==='1'",
    'if(stage13Enabled)',
    'optional assets failed; continuing legacy simulation',
    "fetchText('onga_stage13_runtime.js?v=stage13f')",
    "fetchText('onga_stage13_bridge.js?v=stage13f')",
    "fetchText('onga_stage13_heatmap_clip.js?v=stage13f')",
    "fetchText('onga_stage13_fluid_domain_patch.js?v=stage13f')",
    "fetchText('onga_stage13_bootstrap.js?v=stage13f')",
    'script(runtime)+script(bridge)+script(heatmapClip)+script(fluidDomainPatch)+script(bootstrap)',
  ];
  for (const token of required) {
    if (!html.includes(token)) {
      throw new Error(`${file}: missing required token: ${token}`);
    }
  }

  const legacyStart = html.indexOf('const [html,closedPatch');
  const legacyEnd = html.indexOf(']);', legacyStart);
  const legacyBlock = html.slice(legacyStart, legacyEnd);
  if (legacyBlock.includes('onga_stage13_')) {
    throw new Error(`${file}: Stage 13 assets are still mandatory in the legacy Promise.all block`);
  }

  const runtimeIndex = html.indexOf("fetchText('onga_stage13_runtime.js?v=stage13f')");
  const bridgeIndex = html.indexOf("fetchText('onga_stage13_bridge.js?v=stage13f')");
  const clipIndex = html.indexOf("fetchText('onga_stage13_heatmap_clip.js?v=stage13f')");
  const fluidIndex = html.indexOf("fetchText('onga_stage13_fluid_domain_patch.js?v=stage13f')");
  const bootstrapIndex = html.indexOf("fetchText('onga_stage13_bootstrap.js?v=stage13f')");
  if (!(runtimeIndex < bridgeIndex && bridgeIndex < clipIndex && clipIndex < fluidIndex && fluidIndex < bootstrapIndex)) {
    throw new Error(`${file}: Stage 13 scripts are not ordered runtime -> bridge -> heatmap clip -> fluid domain -> bootstrap`);
  }

  if (!html.includes('if(!response.ok) throw new Error')) {
    throw new Error(`${file}: HTTP response status is not validated`);
  }
}

console.log(`Validated ${files.length} wrappers: legacy path is independent and Stage 13 authority modules are opt-in.`);
