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
    "fetchText('onga_stage13_runtime.js?v=stage13d')",
    "fetchText('onga_stage13_fluid_domain_patch.js?v=stage13d')",
    "fetchText('onga_stage13_bridge.js?v=stage13d')",
    "fetchText('onga_stage13_bootstrap.js?v=stage13d')",
    'script(runtime)+script(fluidDomainPatch)+script(bridge)+script(bootstrap)',
  ];
  for (const token of required) {
    if (!html.includes(token)) {
      throw new Error(`${file}: missing required token: ${token}`);
    }
  }

  const legacyEnd = html.indexOf(']);', html.indexOf('const [html,closedPatch'));
  const legacyBlock = html.slice(html.indexOf('const [html,closedPatch'), legacyEnd);
  if (legacyBlock.includes('onga_stage13_')) {
    throw new Error(`${file}: Stage 13 assets are still mandatory in the legacy Promise.all block`);
  }

  if (!html.includes('if(!response.ok) throw new Error')) {
    throw new Error(`${file}: HTTP response status is not validated`);
  }
}

console.log(`Validated ${files.length} wrappers: legacy path is independent and Stage 13 is opt-in.`);
