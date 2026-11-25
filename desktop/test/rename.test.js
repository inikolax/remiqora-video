'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fsp = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { renameRetry } = require('../src/bootstrap/download');

test('renameRetry waits while the file is held, then moves it', async () => {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), 'rv-rename-'));
  const a = path.join(dir, 'a.part');
  const b = path.join(dir, 'a');
  await fsp.writeFile(a, 'x');
  const real = fsp.rename;
  let calls = 0;
  fsp.rename = async (...args) => {
    if (++calls <= 2) throw Object.assign(new Error('held'), { code: 'EPERM' });
    return real(...args);
  };
  try {
    await renameRetry(a, b, { firstMs: 1 });
  } finally {
    fsp.rename = real;
  }
  assert.strictEqual(calls, 3);
  assert.strictEqual(await fsp.readFile(b, 'utf8'), 'x');
});

test('renameRetry gives up with the last error, and does not retry other errors', async () => {
  const real = fsp.rename;
  let calls = 0;
  fsp.rename = async () => { calls++; throw Object.assign(new Error('nope'), { code: 'ENOENT' }); };
  try {
    await assert.rejects(renameRetry('x', 'y', { firstMs: 1 }), { code: 'ENOENT' });
    assert.strictEqual(calls, 1);
    calls = 0;
    fsp.rename = async () => { calls++; throw Object.assign(new Error('busy'), { code: 'EBUSY' }); };
    await assert.rejects(renameRetry('x', 'y', { firstMs: 1, totalMs: 5 }), { code: 'EBUSY' });
    assert.ok(calls > 1);
  } finally {
    fsp.rename = real;
  }
});
