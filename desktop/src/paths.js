'use strict';
const path = require('node:path');
const os = require('node:os');

const IS_WINDOWS = process.platform === 'win32';
const PLATFORM = `${process.platform}-${process.arch}`;

function repoRoot() {
  return path.resolve(__dirname, '..', '..');
}

/**
 * The app's sources (app/, engine/ with its lock file, the built page, tools/, install/manifest.json) and the RTX Video
 * folder: next to the executable when installed, the repository itself when running from source.
 */
function resourcePaths(isPackaged) {
  if (isPackaged) {
    const base = process.resourcesPath;
    return { project: path.join(base, 'project'), rtxvsr: path.join(base, 'rtxvsr') };
  }
  // from source: what `npm run prepare-resources` copied, as the installer would ship it (never the working tree itself)
  const root = repoRoot();
  return { project: path.join(root, 'desktop', 'resources', 'project'), rtxvsr: path.join(root, 'tools', 'rtxvsr') };
}

const manifestPath = (resources) => path.join(resources.project, 'install', 'manifest.json');

/** Default folder for everything: per user, never inside the install dir (the models are hundreds of GB). */
function defaultDataRoot() {
  if (process.env.REMIQORA_VIDEO_HOME) return path.resolve(process.env.REMIQORA_VIDEO_HOME);
  return path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'RemiqoraVideo');
}

/**
 * Every path the setup and the app use, under one root the user picks. The app runs from root\app with its usual
 * layout (data, outputs, projects, engine\ComfyUI, engine\.venv, .venv, tools\llama|rife|rtxvsr beside app\), so its
 * code finds everything where a source checkout has it; the models folder can be elsewhere (picked on the first screen).
 */
function layout(root, modelsDir) {
  const app = path.join(root, 'app');
  const uvDir = path.join(root, 'tools', 'uv');
  const pythonDir = path.join(root, 'tools', 'python');
  return {
    root,
    app,
    models: modelsDir || path.join(root, 'models'),
    uvDir,
    uvBin: path.join(uvDir, 'uv.exe'),
    pythonDir,
    python: path.join(pythonDir, 'tools', 'python.exe'),
    ffmpegDir: path.join(root, 'tools', 'ffmpeg'),
    uvCache: path.join(root, 'cache', 'uv'),
    hfHome: path.join(root, 'cache', 'huggingface'),
    torchHome: path.join(root, 'cache', 'torch'),
    downloads: path.join(root, 'cache', 'downloads'),
    engine: path.join(app, 'engine'),
    comfy: path.join(app, 'engine', 'ComfyUI'),
    enginePython: path.join(app, 'engine', '.venv', 'Scripts', 'python.exe'),
    appPython: path.join(app, '.venv', 'Scripts', 'python.exe'),
    llama: path.join(app, 'tools', 'llama'),
    rife: path.join(app, 'tools', 'rife'),
    rtxvsr: path.join(app, 'tools', 'rtxvsr'),
    logs: path.join(root, 'logs'),
    state: path.join(root, 'state.json'),
    hfToken: path.join(root, 'cache', 'huggingface', 'token'),
  };
}

module.exports = { IS_WINDOWS, PLATFORM, repoRoot, resourcePaths, manifestPath, defaultDataRoot, layout };
