import fs from 'node:fs/promises';

const files = ['pc_full.html', 'mobile_lite.html'];
const entrypoints = [
  'calibratedWaterMaskValueAt',
  'isKnownWater',
  'drawHeatmap',
  'buildFluidGrid',
  'computeAndRender',
  'makeShoreCastingHotspots',
];
const waterTokens = [
  'calibratedWaterMaskValueAt',
  'isKnownWater',
  'nearestHydroCorridor',
  'waterMask',
  'grid.water',
];

function lineNumber(text, index) {
  return text.slice(0, index).split('\n').length;
}

function findOccurrences(text, token) {
  const positions = [];
  let from = 0;
  while (true) {
    const index = text.indexOf(token, from);
    if (index < 0) return positions;
    positions.push(index);
    from = index + token.length;
  }
}

function findFunctionStart(text, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const patterns = [
    new RegExp(`function\\s+${escaped}\\s*\\(`, 'g'),
    new RegExp(`${escaped}\\s*=\\s*function\\s*\\(`, 'g'),
    new RegExp(`${escaped}\\s*=\\s*(?:async\\s*)?\\([^)]*\\)\\s*=>\\s*\\{`, 'g'),
  ];
  for (const pattern of patterns) {
    const match = pattern.exec(text);
    if (match) return match.index;
  }
  return -1;
}

function extractBraceBlock(text, startIndex) {
  if (startIndex < 0) return null;
  const open = text.indexOf('{', startIndex);
  if (open < 0) return null;
  let depth = 0;
  let state = 'code';
  let quote = '';
  for (let index = open; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (state === 'line-comment') {
      if (char === '\n') state = 'code';
      continue;
    }
    if (state === 'block-comment') {
      if (char === '*' && next === '/') {
        state = 'code';
        index += 1;
      }
      continue;
    }
    if (state === 'string') {
      if (char === '\\') {
        index += 1;
        continue;
      }
      if (char === quote) state = 'code';
      continue;
    }
    if (char === '/' && next === '/') {
      state = 'line-comment';
      index += 1;
      continue;
    }
    if (char === '/' && next === '*') {
      state = 'block-comment';
      index += 1;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      state = 'string';
      quote = char;
      continue;
    }
    if (char === '{') depth += 1;
    if (char === '}') {
      depth -= 1;
      if (depth === 0) return text.slice(open, index + 1);
    }
  }
  return null;
}

const report = {};
for (const file of files) {
  const text = await fs.readFile(file, 'utf8');
  const fileReport = {};
  for (const name of entrypoints) {
    const occurrences = findOccurrences(text, name);
    const start = findFunctionStart(text, name);
    const body = extractBraceBlock(text, start);
    fileReport[name] = {
      occurrences: occurrences.length,
      lines: occurrences.slice(0, 8).map(index => lineNumber(text, index)),
      definitionLine: start >= 0 ? lineNumber(text, start) : null,
      bodyLength: body?.length ?? 0,
      bodyWaterTokenCounts: Object.fromEntries(
        waterTokens.map(token => [token, body ? findOccurrences(body, token).length : 0]),
      ),
    };
  }
  report[file] = fileReport;

  for (const required of ['calibratedWaterMaskValueAt', 'isKnownWater', 'drawHeatmap', 'buildFluidGrid']) {
    if (fileReport[required].occurrences === 0) {
      throw new Error(`${file}: required legacy entrypoint not found: ${required}`);
    }
  }
}

console.log(JSON.stringify(report, null, 2));
