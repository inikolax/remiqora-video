'use strict';
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const net = require('node:net');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { spawnTree, killTree, cleanEnv } = require('./proc');
const { ffmpegBin } = require('./bootstrap/components');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function listenOnce(port) {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(port, '127.0.0.1', () => { const bound = srv.address().port; srv.close(() => resolve(bound)); });
  });
}

/** A free port; the last one first, so the page's localStorage (its origin is the port) survives a restart. */
async function freePort(preferred) {
  if (preferred) {
    try { return await listenOnce(preferred); } catch { /* taken: pick another */ }
  }
  return listenOnce(0);
}

/**
 * app\.env: where this install keeps its models and tools. Written before every start, so a changed models folder or
 * an added folder of existing weights reaches the app; the Models page's own choices (data\settings.json) stay on top.
 */
function envLines({ L, manifest, selection }) {
  const find = selection.find || [];
  const ff = ffmpegBin(L, manifest);
  return [
    '# Written by the Remiqora Video installer before every start; the Models page saves its own choices in data\\settings.json',
    `H3_MODEL_ROOTS=${[L.models, ...find].join(';')}`,
    `H3_REF_DIR=${L.models}`,
    `LLM_DIRS=${[L.models, ...find].map((r) => path.join(r, 'llm')).join(';')}`,
    `FFMPEG=${path.join(ff, 'ffmpeg.exe')}`,
    `FFPROBE=${path.join(ff, 'ffprobe.exe')}`,
    `HF_HOME=${L.hfHome}`,
    `TORCH_HOME=${L.torchHome}`,
    '',
  ];
}

async function writeEnv(ctx) {
  await fsp.mkdir(ctx.L.app, { recursive: true });
  await fsp.writeFile(path.join(ctx.L.app, '.env'), envLines(ctx).join('\r\n'), 'utf8');
}

/** Owns the app's server: start on a free port, wait until it answers, stop it with the worker under it. */
class BackendServer extends EventEmitter {
  constructor(ctx) {
    super();
    this.ctx = ctx;
    this.child = null;
    this.url = null;
    this.port = null;
  }

  async start({ timeoutMs = 120000, preferredPort } = {}) {
    const { L } = this.ctx;
    await fsp.mkdir(L.logs, { recursive: true });
    await writeEnv(this.ctx);
    const port = await freePort(preferredPort);
    this.port = port;
    const log = fs.createWriteStream(path.join(L.logs, 'app-server.log'), { flags: 'a' });
    log.write(`\n--- start ${new Date().toISOString()} port ${port}\n`);
    const child = spawnTree(L.appPython, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)], {
      cwd: L.app, env: cleanEnv({ PYTHONUTF8: '1', HOST: '127.0.0.1', PORT: String(port) }), stdio: ['ignore', 'pipe', 'pipe'],
    });
    this.child = child;
    child.stdout.pipe(log, { end: false });
    child.stderr.pipe(log, { end: false });
    let exitCode = null;
    child.on('exit', (code) => { exitCode = code ?? -1; log.end(); this.emit('exit', exitCode); });
    const base = `http://127.0.0.1:${port}/`;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (exitCode !== null) throw new Error(`the app's server stopped with code ${exitCode} (${path.join(L.logs, 'app-server.log')})`);
      try {
        const res = await fetch(`${base}api/config`, { signal: AbortSignal.timeout(2000) });
        if (res.ok) { this.url = base; return base; }
      } catch { /* starting */ }
      await sleep(400);
    }
    await this.stop();
    throw new Error('the app did not answer in time');
  }

  /** The worker and llama-server live in Job Objects under the server: ending its tree ends them. */
  async stop() {
    const child = this.child;
    if (!child) return;
    await killTree(child);
    for (let i = 0; i < 25 && child.exitCode === null; i++) await sleep(200);
    this.child = null;
    this.url = null;
  }
}

module.exports = { BackendServer, freePort, writeEnv, envLines };
