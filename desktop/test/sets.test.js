'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { setStatus, withNeeds, profileOf, findFile } = require('../src/bootstrap/sets');

const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'install', 'manifest.json'), 'utf8'));

test('the manifest has only official repositories', () => {
  for (const [id, s] of Object.entries(manifest.sets)) {
    for (const f of s.files) {
      assert.doesNotMatch(`${f.repo}/${f.path}`.toLowerCase(), /uncensored|eros|abliterated|heretic|nsfw/, `${id}: ${f.repo}/${f.path}`);
      assert.ok(f.bytes > 0, `${id}: ${f.path} has no size`);
    }
  }
});

test('a set brings what it needs, in the manifest order', () => {
  assert.deepStrictEqual(withNeeds(manifest, ['ref2va']), ['h3', 'ref2va']);
  assert.deepStrictEqual(withNeeds(manifest, ['wan', 'h3', 'nope']), ['h3', 'wan']);
});

test('a profile is recognized whatever the order', () => {
  assert.strictEqual(profileOf(manifest, ['writer', 'h3']), 'minimum');
  assert.strictEqual(profileOf(manifest, ['h3']), '');
});

test('a file counts only with the official size, in its kind folder or under llm', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rv-sets-'));
  const f = { path: 'vae/x.safetensors', kind: 'vae', bytes: 5 };
  fs.mkdirSync(path.join(dir, 'vae'));
  fs.writeFileSync(path.join(dir, 'vae', 'x.safetensors'), '1234');
  assert.strictEqual(findFile(f, [dir]), null);
  fs.writeFileSync(path.join(dir, 'vae', 'x.safetensors'), '12345');
  assert.ok(findFile(f, [dir]));
  const g = { path: 'm.gguf', kind: 'llm', bytes: 3 };
  fs.mkdirSync(path.join(dir, 'llm', 'author', 'repo'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'llm', 'author', 'repo', 'm.gguf'), 'abc');
  assert.ok(findFile(g, [dir]));
  const status = setStatus({ sets: { t: { files: [f, g] } } }, [dir]);
  assert.deepStrictEqual(status.t, { bytes: 8, have: 8, complete: true });
});
