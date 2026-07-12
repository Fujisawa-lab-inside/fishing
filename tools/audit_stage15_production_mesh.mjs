import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadStage15MeshManifest } from '../onga_stage15_mesh_manifest_loader.mjs';
import { auditLoadedProductionMesh } from '../onga_stage15_production_mesh_audit.mjs';

const manifestPath = path.resolve(process.argv[2] || 'data/stage15_mesh/manifest.json');
const outputPath = path.resolve(process.argv[3] || 'stage15-production-mesh-audit.json');
const directory = path.dirname(manifestPath);
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
const loaded = await loadStage15MeshManifest(manifest, {
  fetchJson: async url => JSON.parse(await fs.readFile(path.resolve(directory, url.replace(/^\.\//, '')), 'utf8')),
});
const report = auditLoadedProductionMesh(loaded);
await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
