'use strict';
const fs = require('node:fs');
const path = require('node:path');

// The worker's folders for each kind (app/engine/worker.py KINDS), as tools/install_models.py looks in them
const KINDS = {
  diffusion_models: ['diffusion_models', 'unet'], text_encoders: ['text_encoders', 'clip'], vae: ['vae'], loras: ['loras'],
  checkpoints: ['checkpoints'], latent_upscale_models: ['latent_upscale_models'], llm: ['llm'],
};

const fileName = (f) => f.path.split('/').pop();

function sizeOf(p) {
  try { return fs.statSync(p).size; } catch { return -1; }
}

/** Where the file lies with the official size: the models folder or a folder the user pointed to; else null. */
function findFile(f, roots) {
  const name = fileName(f);
  for (const root of roots) {
    for (const sub of KINDS[f.kind] || [f.kind]) {
      const dir = path.join(root, sub);
      if (f.kind === 'llm') {
        const hit = findDeep(dir, name, f.bytes, 3);
        if (hit) return hit;
      } else if (sizeOf(path.join(dir, name)) === f.bytes) return path.join(dir, name);
    }
  }
  return null;
}

function findDeep(dir, name, bytes, depth) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return null; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isFile() && e.name === name && sizeOf(p) === bytes) return p;
  }
  if (depth > 0) for (const e of entries) if (e.isDirectory()) { const hit = findDeep(path.join(dir, e.name), name, bytes, depth - 1); if (hit) return hit; }
  return null;
}

/** Each set: its size, how much of it is already on disk, whether it is whole. */
function setStatus(manifest, roots) {
  const out = {};
  for (const [id, s] of Object.entries(manifest.sets)) {
    let have = 0;
    for (const f of s.files) if (findFile(f, roots)) have += f.bytes;
    const bytes = s.files.reduce((a, f) => a + f.bytes, 0);
    out[id] = { bytes, have, complete: have === bytes };
  }
  return out;
}

/** The picked sets with what they need (Ref2VA takes H3's encoder and VAE), in the manifest's order. */
function withNeeds(manifest, picked) {
  const all = new Set(picked.filter((id) => manifest.sets[id]));
  for (const id of [...all]) for (const need of manifest.sets[id].needs || []) all.add(need);
  return Object.keys(manifest.sets).filter((id) => all.has(id));
}

/** What a profile picks, or the profile a pick matches ('' for a pick of one's own). */
const profileSets = (manifest, profile) => manifest.profiles[profile] || [];
function profileOf(manifest, picked) {
  const key = [...picked].sort().join();
  return Object.keys(manifest.profiles).find((p) => [...manifest.profiles[p]].sort().join() === key) || '';
}

module.exports = { KINDS, fileName, findFile, setStatus, withNeeds, profileSets, profileOf };
