'use strict';
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { downloadFile, withRetries } = require('./download');
const { extract, extractAtomic } = require('./extract');
const { runCommand, cleanEnv } = require('../proc');
const { setStatus, withNeeds } = require('./sets');

const exists = (p) => fsp.access(p).then(() => true, () => false);
const sum = (list) => list.reduce((a, b) => a + b, 0);
const sha1 = (text) => crypto.createHash('sha1').update(text).digest('hex').slice(0, 12);
const readOr = (file, fallback = '') => { try { return fs.readFileSync(file, 'utf8'); } catch { return fallback; } };

/** Environment of every tool the setup runs: caches, Python and models stay under the chosen folder. */
function toolEnv(L, extra = {}) {
  return cleanEnv({
    UV_CACHE_DIR: L.uvCache, UV_PYTHON: L.python, UV_PYTHON_DOWNLOADS: 'never', UV_NO_PROGRESS: '1',
    HF_HOME: L.hfHome, TORCH_HOME: L.torchHome, HF_HUB_DISABLE_SYMLINKS_WARNING: '1', PYTHONUTF8: '1', NO_COLOR: '1', ...extra,
  });
}

async function dirSize(dir) {
  let total = 0;
  let entries;
  try { entries = await fsp.readdir(dir, { withFileTypes: true }); } catch { return 0; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    total += e.isDirectory() ? await dirSize(p) : (await fsp.stat(p).catch(() => ({ size: 0 }))).size;
  }
  return total;
}

/** uv and the model fetchers print no byte counts; the growth of the folder they fill is an honest progress signal. */
async function withGrowth(dir, total, report, task) {
  const baseline = await dirSize(dir);
  const timer = setInterval(async () => report({ done: Math.min(Math.max(0, (await dirSize(dir)) - baseline), total * 0.98), total }), 3000);
  try { return await task(); } finally { clearInterval(timer); }
}

/** A short hash of every file under `dir` (paths and contents), skipping local state. */
function treeHash(dir, skip = new Set(['__pycache__', '.venv', 'ComfyUI', 'node_modules', 'data'])) {
  if (!fs.existsSync(dir)) return 'none';
  const hash = crypto.createHash('sha1');
  (function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (skip.has(e.name)) continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else hash.update(path.relative(dir, p).split(path.sep).join('/')).update('\0').update(fs.readFileSync(p));
    }
  })(dir);
  return hash.digest('hex').slice(0, 12);
}

/** Moves what is inside `from` (one level) into `to`, replacing what is there. */
async function moveContents(from, to) {
  await fsp.mkdir(to, { recursive: true });
  for (const name of await fsp.readdir(from)) {
    await fsp.rm(path.join(to, name), { recursive: true, force: true });
    await fsp.rename(path.join(from, name), path.join(to, name));
  }
}

const ffmpegBin = (L, manifest) => path.join(L.ffmpegDir, manifest.tools.ffmpeg.binDir);
const coreCommit = (resources) => readOr(path.join(resources.project, 'engine', 'core.txt')).split(/\r?\n/).map((s) => s.trim()).filter(Boolean);

/**
 * The ordered list of what the setup installs. Each component: id, weight (bytes, for the overall bar), version (a
 * change runs it again), verify() (is it on disk), install(ctx, report). report({ done, total, note }).
 * `selection.sets` - the model sets picked; `selection.find` - folders with weights already downloaded.
 */
function buildComponents({ L, manifest, resources, selection }) {
  const T = manifest.tools;
  const logFile = path.join(L.logs, 'setup.log');
  const sets = withNeeds(manifest, selection.sets || []);
  const needLlama = sets.some((id) => (manifest.sets[id].tools || []).includes('llama'));
  const fetchTo = (ctx, file, base, total, report) => downloadFile({
    url: file.url,
    dest: path.join(L.downloads, file.name || path.basename(new URL(file.url).pathname)),
    sha256: file.sha256,
    signal: ctx.signal,
    onProgress: (done) => report({ done: base + done, total }),
  });
  const run = (ctx, report, cmd, args, opts = {}) => runCommand(cmd, args, {
    env: toolEnv(L, opts.env), cwd: opts.cwd, signal: ctx.signal, logFile, onLine: (line) => report({ note: line }),
  });
  const retrying = (ctx, report, task) =>
    withRetries(task, { signal: ctx.signal, onRetry: (n, of) => report({ note: `connection lost, trying again (${n}/${of})` }) });

  const uv = {
    id: 'uv', weight: T.uv.bytes, version: T.uv.version,
    verify: () => exists(L.uvBin),
    async install(ctx, report) {
      const archive = await fetchTo(ctx, T.uv, 0, T.uv.bytes, report);
      await extractAtomic(archive, L.uvDir);
      await fsp.rm(archive, { force: true });
    },
  };

  // python.org's own build (signed: Smart App Control runs it), from its NuGet package: a zip with tools\python.exe
  const python = {
    id: 'python', weight: T.python.bytes, version: T.python.version,
    verify: () => exists(L.python),
    async install(ctx, report) {
      const archive = await fetchTo(ctx, { ...T.python, name: `python-${T.python.version}.nupkg.zip` }, 0, T.python.bytes, report);
      await extractAtomic(archive, L.pythonDir);
      await fsp.rm(archive, { force: true });
    },
  };

  const ffmpeg = {
    id: 'ffmpeg', weight: T.ffmpeg.bytes, version: T.ffmpeg.version,
    verify: () => exists(path.join(ffmpegBin(L, manifest), 'ffmpeg.exe')),
    async install(ctx, report) {
      const archive = await fetchTo(ctx, T.ffmpeg, 0, T.ffmpeg.bytes, report);
      await extractAtomic(archive, L.ffmpegDir);
      await fsp.rm(archive, { force: true });
    },
  };

  // The app's own code, copied from the installer's resources: its old code goes, its data, environments and tools stay
  const appCode = {
    id: 'app', weight: 40e6, version: treeHash(resources.project),
    verify: () => exists(path.join(L.app, 'app', 'main.py')),
    async install() {
      await fsp.mkdir(L.app, { recursive: true });
      for (const old of ['app', path.join('frontend', 'dist'), path.join('tools', 'lyrics')]) await fsp.rm(path.join(L.app, old), { recursive: true, force: true });
      await fsp.cp(resources.project, L.app, {
        recursive: true, force: true,
        filter: (src) => !['__pycache__', '.venv', 'data', 'outputs', 'projects', 'node_modules', '.env'].includes(path.basename(src)),
      });
    },
  };

  // ComfyUI's core at the pinned commit: GitHub's source archive, so no git is needed
  const [coreRepo, coreSha] = coreCommit(resources);
  const engineCore = {
    id: 'engine-core', weight: T.comfyCore.approxBytes, version: (coreSha || '').slice(0, 12),
    verify: () => exists(path.join(L.comfy, 'comfy', 'model_management.py')),
    async install(ctx, report) {
      if (!coreSha) throw new Error('engine/core.txt has no commit');
      const url = `${coreRepo.replace(/\.git$/, '')}/archive/${coreSha}.tar.gz`;
      const archive = await retrying(ctx, report, () => fetchTo(ctx, { url, name: `ComfyUI-${coreSha}.tar.gz` }, 0, T.comfyCore.approxBytes, report));
      await extractAtomic(archive, L.comfy, { stripComponents: 1 });
      await fsp.rm(archive, { force: true });
    },
  };

  // The engine's environment exactly as engine/uv.lock says: torch for CUDA 13, comfy-kitchen, Demucs, Whisper
  const engineEnv = {
    id: 'engine-env', weight: 5.2e9, version: `${T.python.version}-${sha1(readOr(path.join(resources.project, 'engine', 'uv.lock')))}`,
    verify: () => exists(L.enginePython),
    async install(ctx, report) {
      await withGrowth(L.uvCache, 5.2e9, report, () => retrying(ctx, report, () =>
        run(ctx, report, L.uvBin, ['sync', '--project', L.engine, '--frozen'])));
      report({ note: 'torch: checking the GPU' });
      await run(ctx, report, L.enginePython, ['-c', "import torch; assert torch.cuda.is_available(), 'CUDA is not available: update the NVIDIA driver'; print('torch', torch.__version__, '-', torch.cuda.get_device_name(0))"]);
    },
  };

  const appEnv = {
    id: 'app-env', weight: 4e8, version: `${T.python.version}-${sha1(readOr(path.join(resources.project, 'requirements.txt')))}`,
    verify: () => exists(L.appPython),
    async install(ctx, report) {
      await run(ctx, report, L.uvBin, ['venv', '--allow-existing', '--python', L.python, path.join(L.app, '.venv')]);
      await retrying(ctx, report, () => run(ctx, report, L.uvBin, ['pip', 'install', '--python', L.appPython, '-r', path.join(L.app, 'requirements.txt')]));
    },
  };

  // The writer's llama-server: llama.cpp's CUDA build and its CUDA runtime, unpacked side by side
  const llama = {
    id: 'llama', weight: sum(T.llama.files.map((f) => f.bytes)), version: T.llama.version,
    verify: () => exists(path.join(L.llama, 'llama-server.exe')),
    async install(ctx, report) {
      const total = sum(T.llama.files.map((f) => f.bytes));
      const tmp = `${L.llama}.tmp`;
      await fsp.rm(tmp, { recursive: true, force: true });
      let base = 0;
      for (const f of T.llama.files) {
        const archive = await fetchTo(ctx, f, base, total, report);
        base += f.bytes;
        await extract(archive, tmp);
        await fsp.rm(archive, { force: true });
      }
      await fsp.rm(L.llama, { recursive: true, force: true });
      await fsp.rename(tmp, L.llama);
    },
  };

  const rife = {
    id: 'rife', weight: T.rife.bytes, version: T.rife.version,
    verify: () => exists(path.join(L.rife, 'rife-ncnn-vulkan.exe')),
    async install(ctx, report) {
      const archive = await fetchTo(ctx, T.rife, 0, T.rife.bytes, report);
      const tmp = `${L.rife}.tmp`;
      await fsp.rm(tmp, { recursive: true, force: true });
      await extract(archive, tmp);
      await fsp.rm(L.rife, { recursive: true, force: true });
      await moveContents(path.join(tmp, T.rife.dir), L.rife);
      await fsp.rm(tmp, { recursive: true, force: true });
      await fsp.rm(archive, { force: true });
    },
  };

  // RTX Video ships inside the installer (built from NVIDIA's SDK by tools/rtxvsr/build.ps1): just copied into place
  const rtxFiles = ['rtx_vsr.exe', 'nvngx_vsr.dll', 'nvngx_truehdr.dll', 'NVIDIA_RTX_Video_SDK_License.pdf', 'NOTICE.txt'];
  const haveRtx = rtxFiles.every((f) => fs.existsSync(path.join(resources.rtxvsr, f)));
  const rtxvsr = {
    id: 'rtxvsr', weight: T.rtxvsr.approxBytes, version: haveRtx ? sha1(rtxFiles.map((f) => String(fs.statSync(path.join(resources.rtxvsr, f)).size)).join()) : 'none',
    verify: () => exists(path.join(L.rtxvsr, 'rtx_vsr.exe')),
    async install() {
      await fsp.mkdir(L.rtxvsr, { recursive: true });
      for (const f of rtxFiles) await fsp.copyFile(path.join(resources.rtxvsr, f), path.join(L.rtxvsr, f));
    },
  };

  // Whisper and Demucs fetched by the engine's own libraries, so recognizing a song never downloads mid-job
  const music = {
    id: 'music', weight: T.music.approxBytes, version: `${T.music.whisper}-${T.music.demucs}`,
    verify: async () => (await exists(path.join(L.hfHome, 'hub', `models--Systran--faster-whisper-${T.music.whisper}`))) &&
      (await exists(path.join(L.hfHome, 'hub', 'models--adefossez--HTDemucs'))),   // demucs 4.1 keeps htdemucs on Hugging Face
    async install(ctx, report) {
      const code = `from faster_whisper.utils import download_model; download_model('${T.music.whisper}'); `
        + `from demucs.pretrained import get_model; get_model('${T.music.demucs}'); print('ok')`;
      await withGrowth(path.dirname(L.hfHome), T.music.approxBytes, report, () => retrying(ctx, report, () =>
        run(ctx, report, L.enginePython, ['-c', code], { cwd: L.app })));
    },
  };

  // The clip checks' small models (faces, voices), fetched by the app's own code into app\data\models
  const checks = {
    id: 'checks', weight: T.checks.approxBytes, version: 'yunet-sface-wespeaker-1',
    verify: async () => (await exists(path.join(L.app, 'data', 'models', 'face', 'sface.onnx'))) &&
      (await exists(path.join(L.app, 'data', 'models', 'voice', 'voxceleb_resnet34_LM.onnx'))),
    async install(ctx, report) {
      await retrying(ctx, report, () => run(ctx, report, L.appPython,
        ['-c', 'from app import checks, voice; checks._yunet(); checks._sface(); voice._model(); print("ok")'], { cwd: L.app }));
    },
  };

  // The model sets picked: tools/install_models.py, the same downloader setup_models.ps1 runs. A set that fails (no
  // network, no access) does not stop the others: the step ends "partial" and a second run continues from the .part files.
  const roots = [L.models, ...(selection.find || [])];
  const status = () => setStatus(manifest, roots);
  const missingBytes = () => { const s = status(); return sum(sets.map((id) => s[id].bytes - s[id].have)); };
  const weights = {
    id: 'weights', weight: missingBytes(), version: sets.join('+'),
    verify: () => { const s = status(); return sets.every((id) => s[id].complete); },
    async install(ctx, report) {
      const total = missingBytes();
      const args = [path.join(L.app, 'tools', 'install_models.py'), '--json', '--lang', ctx.lang || 'ru',
        '--manifest', path.join(L.app, 'install', 'manifest.json'), '--models-dir', L.models, '--sets', sets.join(','),
        '--find', (selection.find || []).join(';'), '--token-file', L.hfToken];
      const result = {};
      let summary = null;
      await runCommand(L.appPython, args, {
        env: toolEnv(L, ctx.hfToken ? { HF_TOKEN: ctx.hfToken } : {}), cwd: L.app, signal: ctx.signal, logFile,
        onLine: (line) => {
          let ev;
          try { ev = JSON.parse(line); } catch { return; }
          if (ev.event === 'progress') report({ done: Math.min(ev.overall, total), total, note: `${ev.name}: ${Math.round((ev.done / ev.total) * 100)}%` });
          if (ev.event === 'file' && ev.status === 'download') report({ note: ev.name });
          if (ev.event === 'set' && ev.status !== 'running') result[ev.id] = { status: ev.status, code: ev.code, error: ev.error };
          if (ev.event === 'summary') summary = ev.sets;
        },
      }).catch((err) => { if (ctx.signal?.aborted || !summary) throw err; });   // exit code 2: some set did not finish
      return { sets: summary || result };
    },
  };

  const list = [uv, python, ffmpeg, appCode, engineCore, engineEnv, appEnv];
  if (needLlama) list.push(llama);
  list.push(rife);
  if (haveRtx) list.push(rtxvsr);
  list.push(music, checks);
  if (sets.length) list.push(weights);
  return list;
}

module.exports = { buildComponents, toolEnv, ffmpegBin, treeHash, dirSize };
