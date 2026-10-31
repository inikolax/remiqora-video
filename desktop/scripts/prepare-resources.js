'use strict';
// Copies what the installed app needs beside the executable: the app's code, the engine's lock files (not the engine),
// the built page, the downloaders, the manifest, and RTX Video (built by tools/rtxvsr/build.ps1). Run by `npm run dist`.
// Never ships local state: the build fails if a .env, a venv, data or outputs got in.
const fs = require('node:fs');
const path = require('node:path');

const desktop = path.resolve(__dirname, '..');
const root = path.resolve(desktop, '..');
const out = path.join(desktop, 'resources');
const project = path.join(out, 'project');
const KEEP = [
  'app', 'engine/pyproject.toml', 'engine/uv.lock', 'engine/core.txt', 'engine/.python-version', 'frontend/dist',
  'requirements.txt', '.env.example', 'install/manifest.json', 'tools/install_models.py', 'tools/lyrics', 'dev.bat', 'LICENSE',
];
const OPTIONAL = new Set(['engine/.python-version', 'LICENSE']);
const LOCAL = new Set(['__pycache__', '.venv', 'data', 'outputs', 'projects', 'node_modules', '.env']);

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(project, { recursive: true });
for (const rel of KEEP) {
  const from = path.join(root, rel);
  if (!fs.existsSync(from)) {
    if (OPTIONAL.has(rel)) continue;
    throw new Error(`Required installer resource is missing: ${rel}${rel === 'frontend/dist' ? ' (build the page first)' : ''}`);
  }
  fs.cpSync(from, path.join(project, rel), { recursive: true, filter: (src) => !LOCAL.has(path.basename(src)) && !src.endsWith('.pyc') });
}
(function check(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (LOCAL.has(e.name)) throw new Error(`Local state got into the installer: ${path.join(dir, e.name)}`);
    if (e.isDirectory()) check(path.join(dir, e.name));
  }
})(project);

// RTX Video: rtx_vsr.exe and NVIDIA's DLLs under the SDK license. Without them the installer is built anyway and the
// final stays at the shot's size (the app says so); with them the setup copies them into app\tools\rtxvsr.
const RTX = ['rtx_vsr.exe', 'nvngx_vsr.dll', 'nvngx_truehdr.dll', 'NVIDIA_RTX_Video_SDK_License.pdf', 'NOTICE.txt'];
const rtxSrc = path.join(root, 'tools', 'rtxvsr');
if (RTX.every((f) => fs.existsSync(path.join(rtxSrc, f)))) {
  fs.mkdirSync(path.join(out, 'rtxvsr'), { recursive: true });
  for (const f of RTX) fs.copyFileSync(path.join(rtxSrc, f), path.join(out, 'rtxvsr', f));
  console.log('RTX Video included.');
} else {
  fs.mkdirSync(path.join(out, 'rtxvsr'), { recursive: true });
  console.warn('RTX Video is not built (tools/rtxvsr/build.ps1): the installer goes without it.');
}
console.log(`Prepared ${KEEP.length} resources in ${path.relative(root, out)}.`);
