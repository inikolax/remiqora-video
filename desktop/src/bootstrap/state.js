'use strict';
const fsp = require('node:fs/promises');
const path = require('node:path');

const empty = () => ({ schema: 1, components: {} });

async function loadState(file) {
  try {
    const parsed = JSON.parse(await fsp.readFile(file, 'utf8'));
    return parsed && parsed.schema === 1 && parsed.components ? parsed : empty();
  } catch {
    return empty();
  }
}

/** Written through a temp file so a crash cannot leave a half-written state.json. */
async function saveState(file, state) {
  await fsp.mkdir(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp`;
  await fsp.writeFile(tmp, JSON.stringify(state, null, 2));
  await fsp.rename(tmp, file);
}

module.exports = { loadState, saveState };
