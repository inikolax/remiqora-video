'use strict';
const { spawn, execFile } = require('node:child_process');
const readline = require('node:readline');
const fs = require('node:fs');
const path = require('node:path');
const { IS_WINDOWS } = require('./paths');

/** spawn() that puts the child in its own process group on POSIX, so killTree() can reach everything it starts. */
function spawnTree(cmd, args, options = {}) {
  return spawn(cmd, args, { windowsHide: true, detached: !IS_WINDOWS, ...options });
}

/** Kills a process and its descendants (the backend starts uv, which starts Python, which starts the model server). */
function killTree(child) {
  if (!child || child.pid === undefined || child.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    if (IS_WINDOWS) {
      execFile('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true }, () => resolve());
      return;
    }
    try { process.kill(-child.pid, 'SIGTERM'); } catch { try { child.kill('SIGTERM'); } catch { /* already gone */ } }
    resolve();
  });
}

/** Environment for child processes: the app's own, minus the switch that would turn Electron binaries into plain Node. */
function cleanEnv(extra = {}) {
  const env = { ...process.env, ...extra };
  delete env.ELECTRON_RUN_AS_NODE;
  return env;
}

/**
 * Runs a command to completion, streaming output lines to `onLine` and an optional log file.
 * Rejects with the last lines of output on a non-zero exit; an abort kills the whole tree.
 */
function runCommand(cmd, args, { cwd, env, onLine = () => {}, signal, logFile } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawnTree(cmd, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] });
    const tail = [];
    const log = logFile ? fs.createWriteStream(logFile, { flags: 'a' }) : null;
    log?.write(`\n$ ${cmd} ${args.join(' ')}\n`);

    const handle = (line) => {
      tail.push(line);
      if (tail.length > 30) tail.shift();
      log?.write(line + '\n');
      onLine(line);
    };
    readline.createInterface({ input: child.stdout }).on('line', handle);
    readline.createInterface({ input: child.stderr }).on('line', handle);

    const onAbort = () => { killTree(child); };
    signal?.addEventListener('abort', onAbort, { once: true });
    const cleanup = () => { signal?.removeEventListener('abort', onAbort); log?.end(); };

    child.on('error', (err) => { cleanup(); reject(err); });
    child.on('close', (code) => {
      cleanup();
      if (signal?.aborted) return reject(signal.reason);
      if (code === 0) return resolve();
      reject(new Error(`${path.basename(cmd)} ${args[0] ?? ''} exited with code ${code}\n${tail.slice(-12).join('\n')}`));
    });
  });
}

module.exports = { spawnTree, killTree, cleanEnv, runCommand };
