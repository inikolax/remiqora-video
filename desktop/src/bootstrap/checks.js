'use strict';
const { execFile } = require('node:child_process');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');

/** Runs a command, never rejects: { ok, stdout, timedOut }. */
function run(cmd, args, timeout = 5000) {
  return new Promise((resolve) => {
    execFile(cmd, args, { timeout, windowsHide: true }, (err, stdout) =>
      resolve({ ok: !err, stdout: String(stdout || ''), timedOut: !!(err && err.killed) }));
  });
}

function nvidiaSmiCandidates() {
  const sys = process.env.SystemRoot || 'C:\\Windows';
  return ['nvidia-smi', path.join(sys, 'System32', 'nvidia-smi.exe'),
    path.join(process.env.ProgramFiles || 'C:\\Program Files', 'NVIDIA Corporation', 'NVSMI', 'nvidia-smi.exe')];
}

/** First NVIDIA GPU as { name, driver, vramMiB, computeCap } or null. */
async function detectNvidiaGpu() {
  for (const smi of nvidiaSmiCandidates()) {
    if (path.isAbsolute(smi) && !fs.existsSync(smi)) continue;
    for (const fields of ['name,driver_version,memory.total,compute_cap', 'name,driver_version,memory.total']) {
      const r = await run(smi, [`--query-gpu=${fields}`, '--format=csv,noheader,nounits']);
      if (r.timedOut) return null;   // a hung driver hangs the next candidate too
      const line = r.ok ? r.stdout.split(/\r?\n/).find((l) => l.trim()) : null;
      if (!line) continue;
      const [name, driver, vram, cap] = line.split(',').map((s) => s.trim());
      return { name, driver, vramMiB: Number(vram) || 0, computeCap: cap ? Number(cap) : null };
    }
  }
  return null;
}

/** Pure decision: does this GPU run the engine (torch for CUDA 13)? A small card is a warning, not a stop. */
function evaluateGpu(gpu, req) {
  if (!gpu) return { ok: false, code: 'no-gpu' };
  const major = parseInt(gpu.driver, 10);
  if (!Number.isNaN(major) && major < req.minDriver) return { ok: false, code: 'old-driver' };
  if (gpu.computeCap !== null && gpu.computeCap < req.minComputeCapability) return { ok: false, code: 'old-gpu' };
  return { ok: true, smallVram: gpu.vramMiB > 0 && gpu.vramMiB < req.minVramMiB };
}

/** Free bytes on the volume that holds `dir` (the nearest existing parent). */
async function freeBytes(dir) {
  let probe = path.resolve(dir);
  for (;;) {
    try {
      const s = await fsp.statfs(probe);
      return Number(s.bavail) * Number(s.bsize);
    } catch {
      const parent = path.dirname(probe);
      if (parent === probe) return 0;
      probe = parent;
    }
  }
}

async function isOnline(fetchImpl = fetch) {
  try {
    await fetchImpl('https://huggingface.co', { method: 'HEAD', signal: AbortSignal.timeout(6000) });
    return true;
  } catch {
    return false;
  }
}

/**
 * What the first screen shows before anything is downloaded: rows and the first problem that stops the setup.
 * `needs` = { [dir]: bytes }: the tools and environments go to the install folder, the models maybe to another drive.
 */
async function runChecks({ platform, manifest, needs, fetchImpl = fetch }) {
  const req = manifest.requirements;
  const items = [];
  let blocking = null;
  const fail = (code, extra = {}) => { blocking ||= { code, ...extra }; };
  if (platform !== 'win32-x64') {
    items.push({ id: 'platform', ok: false, platform });
    fail('unsupported-platform', { platform });
  }
  const dirs = Object.keys(needs);
  const [gpu, online, ...free] = await Promise.all([detectNvidiaGpu(), isOnline(fetchImpl), ...dirs.map(freeBytes)]);
  const verdict = evaluateGpu(gpu, req);
  items.push({ id: 'gpu', ok: verdict.code !== 'no-gpu' && verdict.code !== 'old-gpu', warn: !!verdict.smallVram,
    name: gpu ? gpu.name : '', vramMiB: gpu ? gpu.vramMiB : 0, minVramMiB: req.minVramMiB });
  items.push({ id: 'driver', ok: verdict.code !== 'old-driver' && !!gpu, driver: gpu ? gpu.driver : '', required: req.minDriver });
  if (!verdict.ok) fail(verdict.code, { gpu, required: req.minDriver });
  // two folders on one drive need their sum there
  const byVolume = new Map();
  dirs.forEach((d, i) => {
    const vol = path.parse(path.resolve(d)).root.toLowerCase();
    const v = byVolume.get(vol) || { free: free[i], need: 0, dirs: [] };
    v.need += needs[d];
    v.dirs.push(d);
    byVolume.set(vol, v);
  });
  for (const [vol, v] of byVolume) {
    const ok = v.free >= v.need;
    items.push({ id: 'disk', ok, volume: vol.toUpperCase(), freeBytes: v.free, requiredBytes: v.need });
  }
  items.push({ id: 'network', ok: online });
  if (!online) fail('offline');
  return { items, blocking };
}

module.exports = { detectNvidiaGpu, evaluateGpu, freeBytes, isOnline, runChecks };
