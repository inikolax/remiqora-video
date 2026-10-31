'use strict';
const { execFile } = require('node:child_process');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { IS_WINDOWS } = require('../paths');

/**
 * The system bsdtar reads both .zip and .tar.gz: tar.exe ships with Windows 10 1803+ and macOS.
 * Not "tar" from PATH on Windows: Git Bash puts GNU tar first, and that one cannot read zip.
 */
function tarBinary() {
  return IS_WINDOWS ? path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe') : 'tar';
}

/** Extracts `archive` into `destDir` (created if missing). */
async function extract(archive, destDir, { stripComponents = 0 } = {}) {
  await fsp.mkdir(destDir, { recursive: true });
  const args = ['-xf', archive, '-C', destDir];
  if (stripComponents) args.push(`--strip-components=${stripComponents}`);
  await new Promise((resolve, reject) => {
    execFile(tarBinary(), args, { windowsHide: true, maxBuffer: 4 << 20 }, (err, _out, stderr) => {
      if (err) reject(new Error(`could not extract ${path.basename(archive)}: ${String(stderr || err.message).trim()}`));
      else resolve();
    });
  });
}

/**
 * Extracts into a sibling temp directory and renames it into place, so an interrupted
 * extraction never leaves a half-populated `destDir` that looks installed.
 */
async function extractAtomic(archive, destDir, options) {
  const tmp = `${destDir}.tmp`;
  await fsp.rm(tmp, { recursive: true, force: true });
  await extract(archive, tmp, options);
  await fsp.rm(destDir, { recursive: true, force: true });
  await fsp.mkdir(path.dirname(destDir), { recursive: true });
  await fsp.rename(tmp, destDir);
}

module.exports = { extract, extractAtomic, tarBinary };
