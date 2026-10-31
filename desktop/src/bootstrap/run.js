'use strict';
const fsp = require('node:fs/promises');
const { buildComponents } = require('./components');
const { loadState, saveState } = require('./state');

/** Components still to install (not in state.json, another version, or gone from disk). */
async function pendingComponents(ctx) {
  const state = await loadState(ctx.L.state);
  const all = ctx.components || buildComponents(ctx);   // ctx.components: a test hook
  const done = new Set();
  for (const c of all) {
    const rec = state.components[c.id];
    if (rec && rec.version === c.version && (await c.verify(ctx))) done.add(c.id);
  }
  return { all, done, state };
}

/** The plan for the screen: what will be installed and how much it weighs. */
async function describePlan(ctx) {
  const { all, done } = await pendingComponents(ctx);
  return all.map((c) => ({ id: c.id, weight: c.weight, done: done.has(c.id) }));
}

/**
 * Installs every missing component in order. `emit` gets
 *   { type: 'component', id, status: 'running'|'done'|'partial'|'skipped'|'error', done?, total?, note?, error?, result? }.
 * A component whose install returns but whose files are not all there (a model set that did not download) is
 * 'partial': not recorded, the run goes on, a second run tries it again. An abort keeps partial downloads; any other
 * failure stops the run and is rethrown.
 */
async function runSetup(ctx, emit = () => {}) {
  const skip = new Set(ctx.skip || []);
  await fsp.mkdir(ctx.L.logs, { recursive: true });
  await fsp.mkdir(ctx.L.downloads, { recursive: true });
  const { all, done, state } = await pendingComponents(ctx);
  const partial = {};
  for (const c of all) {
    ctx.signal?.throwIfAborted();
    if (done.has(c.id)) { emit({ type: 'component', id: c.id, status: 'done' }); continue; }
    if (skip.has(c.id)) { emit({ type: 'component', id: c.id, status: 'skipped' }); continue; }
    emit({ type: 'component', id: c.id, status: 'running' });
    let result;
    try {
      result = await c.install(ctx, (progress) => emit({ type: 'component', id: c.id, status: 'running', ...progress }));
    } catch (error) {
      if (ctx.signal?.aborted) throw error;
      emit({ type: 'component', id: c.id, status: 'error', error: error.message });
      error.componentId = c.id;
      throw error;
    }
    if (!(await c.verify(ctx))) {
      partial[c.id] = result || {};
      emit({ type: 'component', id: c.id, status: 'partial', result });
      continue;
    }
    state.components[c.id] = { version: c.version, at: new Date().toISOString() };
    await saveState(ctx.L.state, state);
    emit({ type: 'component', id: c.id, status: 'done', result });
  }
  return { skipped: [...skip], partial };
}

/**
 * Whether the app can start: every component installed, except the model sets (a missing set only greys its model
 * out in the app) and the test switch's skips.
 */
async function isReady(ctx) {
  const { all, done } = await pendingComponents(ctx);
  const skipped = new Set(ctx.skip || []);
  return all.every((c) => c.id === 'weights' || done.has(c.id) || skipped.has(c.id));
}

module.exports = { describePlan, runSetup, isReady, pendingComponents };
