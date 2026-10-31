'use strict';
const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { PLATFORM, resourcePaths, manifestPath, defaultDataRoot, layout } = require('./paths');
const { runChecks } = require('./bootstrap/checks');
const { describePlan, runSetup, isReady } = require('./bootstrap/run');
const { setStatus, withNeeds, profileOf } = require('./bootstrap/sets');
const { BackendServer } = require('./server');
const { loadConfig, updateConfig, ensureWritableDir } = require('./config');

if (process.env.REMIQORA_VIDEO_USER_DATA) app.setPath('userData', process.env.REMIQORA_VIDEO_USER_DATA);

const resources = resourcePaths(app.isPackaged);
const manifest = JSON.parse(fs.readFileSync(manifestPath(resources), 'utf8'));
const SETUP_PAGE = path.join(__dirname, '..', 'renderer', 'index.html');
// Only these links open from the setup screen: the drivers, the token page, each set's license page
const EXTERNAL = {
  'nvidia-drivers': 'https://www.nvidia.com/drivers',
  issues: 'https://github.com/inikolax/remiqora-video/issues/new',
  'hf-token': 'https://huggingface.co/settings/tokens/new?tokenType=read',
  'smart-app-control': 'https://support.microsoft.com/topic/smart-app-control-faq-285ea03d-fa88-4d56-882e-6698afdb7003',
  ...Object.fromEntries(Object.entries(manifest.sets).map(([id, s]) => [`license-${id}`, s.license.url])),
};

let win = null;
let ctx = null;
let server = null;
let setupAbort = null;
let quitting = false;
let saved = {};
let pendingHfToken = null;   // a token the screen checked; saved into the chosen folder at the start

/** The context every call works with: the folders and what is picked. */
function buildContext(cfg) {
  const L = layout(cfg.dataRoot || defaultDataRoot(), cfg.modelsDir);
  const find = (cfg.find || []).filter((d) => fs.existsSync(d));
  // what is on disk already counts as picked: a later run only adds (a set is never removed by the installer)
  const status = setStatus(manifest, [L.models, ...find]);
  const picked = cfg.sets || manifest.profiles.minimum;
  const sets = withNeeds(manifest, [...picked, ...Object.keys(status).filter((id) => status[id].complete && cfg.sets)]);
  return {
    L, manifest, resources, platform: PLATFORM, selection: { sets, find },
    skip: (process.env.REMIQORA_VIDEO_SKIP_COMPONENTS || '').split(',').map((s) => s.trim()).filter(Boolean),
    lang: cfg.lang || 'ru',
  };
}

const rebuild = () => { ctx = buildContext(saved); };
const save = async (patch) => { saved = await updateConfig(app.getPath('userData'), patch); rebuild(); };

/** Free space each folder needs for what is still to do: tools and environments a third more for unpacking and caches. */
function neededBytes(plan) {
  const left = plan.filter((c) => !c.done);
  const models = left.filter((c) => c.id === 'weights').reduce((a, c) => a + c.weight, 0);
  const tools = left.filter((c) => c.id !== 'weights').reduce((a, c) => a + c.weight, 0);
  const needs = { [ctx.L.root]: Math.ceil(tools * 1.3) };
  needs[ctx.L.models] = (needs[ctx.L.models] || 0) + Math.ceil(models * 1.02);
  return needs;
}

const savedHfToken = () => { try { return fs.readFileSync(ctx.L.hfToken, 'utf8').trim(); } catch { return ''; } };

/** A Hugging Face token against the gated sets picked: whose it is, and which licenses it has not accepted yet. */
async function checkHfToken(token) {
  const use = String(token || '').trim() || pendingHfToken || savedHfToken();
  if (!use) return { ok: false, code: 'empty' };
  const get = (url, method = 'GET') => fetch(url, { method, headers: { Authorization: `Bearer ${use}` }, redirect: 'manual', signal: AbortSignal.timeout(20000) });
  try {
    const who = await get('https://huggingface.co/api/whoami-v2');
    if (who.status === 401) return { ok: false, code: 'login' };
    if (!who.ok) return { ok: false, code: 'network', detail: `whoami: HTTP ${who.status}` };
    const user = (await who.json()).name || '';
    const gated = ctx.selection.sets.filter((id) => manifest.sets[id].gated);
    const denied = [];
    for (const id of gated) {
      const f = manifest.sets[id].files[0];
      const res = await get(`https://huggingface.co/${f.repo}/resolve/main/${f.path}`, 'HEAD');
      if (res.status === 401 || res.status === 403) denied.push(id);
      else if (res.status >= 400) return { ok: false, code: 'network', detail: `${f.repo}: HTTP ${res.status}` };
    }
    if (String(token || '').trim()) pendingHfToken = use;
    return { ok: denied.length === 0, user, denied, checked: gated };
  } catch (err) {
    return { ok: false, code: 'network', detail: err.message };
  }
}

const send = (payload) => { if (win && !win.isDestroyed()) win.webContents.send('setup:event', payload); };

function createWindow() {
  win = new BrowserWindow({
    width: 1320, height: 860, minWidth: 960, minHeight: 640, show: false, title: 'Remiqora Video', backgroundColor: '#0f0f14',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  win.once('ready-to-show', () => win.show());
  win.on('closed', () => { win = null; });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (server && server.url && url.startsWith(server.url)) return { action: 'allow' };   // the app's own pages (a project in a new tab)
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    const own = url.startsWith('file:') || (server && server.url && url.startsWith(server.url));
    if (!own) { event.preventDefault(); if (/^https?:\/\//.test(url)) shell.openExternal(url); }
  });
  if (!app.isPackaged && process.env.REMIQORA_VIDEO_DEVTOOLS) win.webContents.openDevTools({ mode: 'detach' });
}

const showSetup = (query = {}) => win.loadFile(SETUP_PAGE, { query });

/** Starts the app's server and shows it in the window; back from adding sets, just shows it again. */
async function launch() {
  if (server && server.url) { await win.loadURL(server.url); return; }
  send({ type: 'starting' });
  server = new BackendServer(ctx);
  server.on('exit', (code) => { if (!quitting) showSetup({ state: 'crashed', message: `The app's server stopped (exit code ${code}).` }); });
  try {
    const url = await server.start({ preferredPort: saved.port });
    if (server.port !== saved.port) await save({ port: server.port });
    await win.loadURL(url);
  } catch (err) {
    server = null;
    showSetup({ state: 'crashed', message: err.message });
  }
}

async function startSetup() {
  if (setupAbort) return;
  setupAbort = new AbortController();
  try {
    const out = await runSetup({ ...ctx, signal: setupAbort.signal }, send);
    send({ type: 'finished', partial: out.partial });
  } catch (err) {
    if (setupAbort.signal.aborted) send({ type: 'paused' });
    else send({ type: 'failed', componentId: err.componentId || null, message: err.message });
  } finally {
    setupAbort = null;
  }
}

function registerIpc() {
  ipcMain.handle('setup:context', async () => {
    const plan = await describePlan(ctx);
    const status = setStatus(manifest, [ctx.L.models, ...ctx.selection.find]);
    return {
      version: app.getVersion(),
      languages: process.env.REMIQORA_VIDEO_LANG ? [process.env.REMIQORA_VIDEO_LANG] : [app.getLocale(), ...app.getPreferredSystemLanguages()],
      dataRoot: ctx.L.root,
      modelsDir: ctx.L.models,
      find: ctx.selection.find,
      sets: Object.fromEntries(Object.entries(manifest.sets).map(([id, s]) => [id, {
        title: s.title, license: s.license.name, gated: !!s.gated, needs: s.needs || [], ...status[id],
      }])),
      profiles: manifest.profiles,
      picked: ctx.selection.sets,
      profile: profileOf(manifest, ctx.selection.sets),
      plan,
      needs: neededBytes(plan),
      hfTokenSaved: !!pendingHfToken || !!savedHfToken(),
      adding: !!(server && server.url),
      minVramMiB: manifest.requirements.minVramMiB,
    };
  });
  ipcMain.handle('setup:checks', async () => runChecks({ platform: PLATFORM, manifest, needs: neededBytes(await describePlan(ctx)) }));
  ipcMain.handle('setup:set-sets', async (_e, sets) => {
    await save({ sets: withNeeds(manifest, Array.isArray(sets) ? sets : []) });
  });
  ipcMain.handle('setup:set-lang', async (_e, lang) => { if (lang !== saved.lang) await save({ lang }); });
  ipcMain.handle('setup:choose-folder', async (_e, kind) => {
    const r = await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'], defaultPath: kind === 'models' ? ctx.L.models : ctx.L.root });
    if (r.canceled || !r.filePaths[0]) return null;
    const picked = r.filePaths[0];
    if (kind === 'root') return path.basename(picked).toLowerCase() === 'remiqoravideo' ? picked : path.join(picked, 'RemiqoraVideo');
    return picked;
  });
  ipcMain.handle('setup:set-folder', async (_e, kind, dir) => {
    if (setupAbort) return { ok: false, message: 'busy' };
    try {
      if (kind !== 'find') await ensureWritableDir(dir);
      else if (!fs.existsSync(dir)) throw new Error(`${dir}: no such folder`);
    } catch (err) {
      return { ok: false, message: err.message };
    }
    if (kind === 'root') await save({ dataRoot: dir });
    else if (kind === 'models') await save({ modelsDir: dir });
    else await save({ find: [...new Set([...(saved.find || []), dir])] });
    return { ok: true };
  });
  ipcMain.handle('setup:drop-find', async (_e, dir) => { await save({ find: (saved.find || []).filter((d) => d !== dir) }); });
  ipcMain.handle('setup:hf-check', (_e, token) => checkHfToken(token));
  ipcMain.handle('setup:start', async () => {
    await ensureWritableDir(ctx.L.root);
    await ensureWritableDir(ctx.L.models);
    // remembered at once: an interrupted setup continues in the same folders on the next start
    await save({ dataRoot: ctx.L.root, modelsDir: ctx.L.models, sets: ctx.selection.sets });
    if (pendingHfToken) {
      await fs.promises.mkdir(path.dirname(ctx.L.hfToken), { recursive: true });
      await fs.promises.writeFile(ctx.L.hfToken, pendingHfToken);
      pendingHfToken = null;
    }
    startSetup();
  });
  ipcMain.handle('setup:pause', () => { if (setupAbort) setupAbort.abort(new Error('paused')); });
  ipcMain.handle('setup:launch', () => launch());
  ipcMain.handle('setup:open-external', (_e, key) => { if (EXTERNAL[key]) shell.openExternal(EXTERNAL[key]); });
  ipcMain.handle('setup:open-logs', () => shell.openPath(ctx.L.logs));
  ipcMain.handle('setup:show-data', () => shell.openPath(ctx.L.root));
  // From the app's Models page: the setup screen in «add» mode, the app's server keeps running meanwhile
  ipcMain.handle('app:add-sets', async () => { if (!setupAbort) await showSetup({ state: 'add' }); });
  ipcMain.handle('app:installed', () => {
    const status = setStatus(manifest, [ctx.L.models, ...ctx.selection.find]);
    return Object.fromEntries(Object.entries(status).map(([id, s]) => [id, s.complete]));
  });
}

async function boot() {
  saved = await loadConfig(app.getPath('userData'));
  rebuild();
  registerIpc();
  Menu.setApplicationMenu(null);
  createWindow();
  // a saved folder means the first run happened: straight into the app when nothing but model sets is missing
  if (saved.dataRoot && (await isReady(ctx))) await launch();
  else await showSetup();
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.whenReady().then(boot).catch((err) => { dialog.showErrorBox('Remiqora Video', err.stack || String(err)); app.exit(1); });
  app.on('window-all-closed', () => app.quit());
  // the worker holds the GPU: the server's process tree goes before the app does
  app.on('before-quit', (event) => {
    if (quitting) return;
    quitting = true;
    if (setupAbort) setupAbort.abort(new Error('quit'));
    if (server) { event.preventDefault(); server.stop().finally(() => app.quit()); }
  });
}
