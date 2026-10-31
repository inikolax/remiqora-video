'use strict';
const fsp = require('node:fs/promises');
const path = require('node:path');

/** Tiny per-user settings file in Electron's userData folder (the data root itself can live on another drive). */
async function loadConfig(dir) {
  try {
    const parsed = JSON.parse(await fsp.readFile(path.join(dir, 'config.json'), 'utf8'));
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

async function saveConfig(dir, config) {
  await fsp.mkdir(dir, { recursive: true });
  await fsp.writeFile(path.join(dir, 'config.json'), JSON.stringify(config, null, 2));
}

/** Merges `patch` into the saved settings (data root, remembered port, ...). */
async function updateConfig(dir, patch) {
  const next = { ...(await loadConfig(dir)), ...patch };
  await saveConfig(dir, next);
  return next;
}

/** The data root must be creatable and writable before anything is downloaded into it. */
async function ensureWritableDir(dir) {
  await fsp.mkdir(dir, { recursive: true });
  const probe = path.join(dir, '.write-test');
  await fsp.writeFile(probe, 'ok');
  await fsp.rm(probe, { force: true });
}

module.exports = { loadConfig, saveConfig, updateConfig, ensureWritableDir };
