'use strict';
// The setup screen: checks and the choice of model sets, the install's progress, problems, hand-over to the app.
// Opened from the app with ?state=add it adds sets left out (the app's server keeps running meanwhile).
(() => {
  const api = window.remiqoraVideo;
  const view = document.getElementById('view');
  const live = document.getElementById('live');
  const stepsEl = document.getElementById('steps');
  const params = new URLSearchParams(location.search);
  const adding = params.get('state') === 'add';

  let locale = 'ru';
  let ctx = null;
  let checkResult = null;
  let rows = {};          // component id -> { status, done, total, note, weight }
  let paused = false;
  let samples = [];       // [time, bytes] for the speed and the time left
  let accepted = adding;  // the licenses: ticked once per run of the screen
  let hf = null;          // the last token check
  let hfDraft = '';
  let hfBusy = false;
  let setResults = {};    // from the weights step: set id -> { status, error }

  const fill = (s, vars) => s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ''));
  const t = (key, vars = {}) => {
    const v = window.STRINGS[locale][key] ?? window.STRINGS.en[key] ?? key;
    return Array.isArray(v) ? v.map((s) => fill(s, vars)) : fill(v, vars);
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const $ = (sel) => view.querySelector(sel);
  const ICON = {
    ok: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M7.5 12.5l3 3 6-6.5"/></svg>',
    err: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 7v6M12 16.5v.5"/></svg>',
    warn: '<svg viewBox="0 0 24 24"><path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/></svg>',
    run: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 7v5l3 2"/></svg>',
    wait: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>',
  };
  const icon = (kind) => `<span class="ico ${kind === 'wait' ? '' : kind}">${ICON[kind]}</span>`;
  const nf = (digits) => new Intl.NumberFormat(locale, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  const fmtBytes = (n) => (n >= 1e9 ? `${nf(1).format(n / 1e9)} ${t('unit.gb')}` : `${nf(0).format(n / 1e6)} ${t('unit.mb')}`);
  const setTitle = (id) => (window.STRINGS[locale]['title.' + id] || (ctx.sets[id] ? ctx.sets[id].title : id));
  const fmtEta = (sec) => (sec >= 90 ? `${Math.ceil(sec / 60)} ${t('unit.min')}` : `${Math.max(5, Math.round(sec / 5) * 5)} ${t('unit.sec')}`);

  function setSteps(current, state) {
    stepsEl.innerHTML = ['check', 'download', 'done'].map((name, i) => {
      const n = i + 1;
      const cls = n < current ? 'done' : n === current && state === 'bad' ? 'bad' : '';
      return `<li class="${cls}"${n === current ? ' aria-current="step"' : ''}>${esc(t('steps.' + name))}</li>`;
    }).join('');
  }
  function render(html, title) {
    view.innerHTML = html;
    live.textContent = title;
    const h1 = view.querySelector('h1');
    if (h1) { h1.tabIndex = -1; h1.focus({ preventScroll: true }); }
  }
  const bind = (sel, fn) => { const el = $(sel); if (el) el.addEventListener('click', fn); };

  // ---------- 1. checks and the pick ----------
  async function runChecksAndShow() {
    setSteps(1);
    render(`<h1>${esc(t(adding ? 'add.title' : 'check.title'))}</h1><p class="lead">${esc(t(adding ? 'add.lead' : 'check.lead'))}</p><div class="spinner" role="presentation"></div>`, t('check.title'));
    const result = await api.checks();
    if (result.blocking) return showProblem(result);
    checkResult = result;
    showPick();
  }

  const pending = () => ctx.plan.filter((c) => !c.done);
  const diskOk = () => !checkResult || checkResult.items.filter((i) => i.id === 'disk').every((i) => i.ok);
  const gatedToFetch = () => ctx.picked.filter((id) => ctx.sets[id].gated && !ctx.sets[id].complete);
  const hfReady = () => gatedToFetch().length === 0 || !!(hf && hf.ok && gatedToFetch().every((id) => hf.checked.includes(id)));

  function checkRow(item) {
    let detail = '';
    let kind = item.ok ? 'ok' : 'err';
    if (item.id === 'gpu') {
      const gb = Math.round(item.vramMiB / 1024);
      detail = item.warn ? t('row.gpu.small', { name: item.name, gb, need: Math.round(item.minVramMiB / 1000) }) : item.vramMiB ? `${item.name}, ${gb} ${t('unit.gb')}` : item.name;
      if (item.ok && item.warn) kind = 'warn';
    }
    if (item.id === 'driver') detail = t('row.driver.detail', { v: item.driver, r: item.required });
    if (item.id === 'disk') detail = t('row.disk.detail', { free: fmtBytes(item.freeBytes), req: fmtBytes(item.requiredBytes) });
    if (item.id === 'network') detail = item.ok ? t('row.network.ok') : t('row.network.bad');
    if (item.id === 'platform') detail = item.platform;
    return `<li>${icon(kind)}<span class="name">${esc(t('row.' + item.id, { v: item.volume || '' }))}</span><span class="state long">${esc(detail)}</span></li>`;
  }

  function profileBlock() {
    const cur = ctx.profile || 'own';
    const opts = [...Object.keys(ctx.profiles), 'own'].map((p) => {
      const bytes = p === 'own' ? 0 : ctx.profiles[p].reduce((a, id) => a + ctx.sets[id].bytes, 0);
      return `<label class="profile${cur === p ? ' on' : ''}"><input type="radio" name="profile" value="${p}"${cur === p ? ' checked' : ''}>
        <span class="what"><span class="name">${esc(t('profile.' + p))}${bytes ? ` <span class="size">~${esc(fmtBytes(bytes))}</span>` : ''}</span><span class="text">${esc(t('profile.' + p + '.text'))}</span></span></label>`;
    }).join('');
    return `<div class="profiles" role="radiogroup" aria-label="${esc(t('pick.title'))}">${opts}</div>`;
  }

  function setRow(id) {
    const s = ctx.sets[id];
    const on = ctx.picked.includes(id);
    const needed = ctx.picked.some((p) => ctx.sets[p].needs.includes(id));
    const box = s.complete
      ? `<span class="box fixed" aria-hidden="true">${ICON.ok}</span>`
      : `<input type="checkbox" class="box" id="pick-${id}" data-set="${id}"${on ? ' checked' : ''}${needed ? ' disabled' : ''}>`;
    const state = s.complete ? t('pick.installed') : s.have ? t('pick.partial', { have: fmtBytes(s.have), size: fmtBytes(s.bytes) }) : fmtBytes(s.bytes);
    return `<li class="pick${on || s.complete ? ' on' : ''}">
      ${box}
      <label class="what"${s.complete ? '' : ` for="pick-${id}"`}><span class="name">${esc(setTitle(id))}</span><span class="text">${esc(t('set.' + id))}</span>
        <span class="text"><button type="button" class="btn link" data-open="license-${id}">${esc(t('pick.license', { name: s.license }))}</button></span></label>
      <span class="size">${esc(state)}</span>
      ${id === 'ltx25' && on && !s.complete ? hfBlock() : ''}
    </li>`;
  }

  function hfBlock() {
    let status = '';
    if (hfBusy) status = t('hf.checking');
    else if (hf) {
      status = hf.code ? t('hf.' + hf.code) + (hf.detail ? ` (${hf.detail})` : '')
        : hf.denied.length ? t('hf.denied', { user: hf.user, sets: hf.denied.map(setTitle).join(', ') })
        : t('hf.ok', { user: hf.user });
    }
    const tone = hfBusy || !hf ? '' : hfReady() ? ' ok' : ' bad';
    return `<div class="hf">
      <p class="text">${esc(t('hf.lead'))}</p>
      <ol class="hfsteps"><li>${esc(t('hf.step1'))} <button type="button" class="btn link" data-open="license-ltx25">huggingface.co/Lightricks/LTX-2.5</button></li><li>${esc(t('hf.step2'))}</li></ol>
      <div class="hfrow">
        <label for="hf-token" class="lbl">${esc(t('hf.token'))} <button type="button" class="btn link" data-open="hf-token">${esc(t('hf.newToken'))}</button></label>
        <input type="password" id="hf-token" autocomplete="off" spellcheck="false" placeholder="${esc(ctx.hfTokenSaved ? t('hf.savedPh') : 'hf_…')}" value="${esc(hfDraft)}">
        <button type="button" class="btn" id="hf-check"${hfBusy ? ' disabled' : ''}>${esc(t('hf.check'))}</button>
      </div>
      <p class="hfstatus${tone}" role="status">${esc(status)}</p>
      <p class="text">${esc(t('hf.where'))}</p>
    </div>`;
  }

  function findBlock() {
    const picked = ctx.picked.filter((id) => !ctx.sets[id].complete);
    const list = ctx.find.map((d) => `<li><span class="path">${esc(d)}</span><button type="button" class="btn link" data-drop="${esc(d)}">${esc(t('find.drop'))}</button></li>`).join('');
    const have = ctx.picked.reduce((a, id) => a + ctx.sets[id].have, 0);
    return `<section class="findbox"><h2>${esc(t('find.title'))}</h2><p class="text">${esc(t('find.lead'))}</p>
      ${list ? `<ul class="finds">${list}</ul>` : ''}
      ${ctx.find.length && picked.length >= 0 ? `<p class="text">${esc(t('find.found', { have: fmtBytes(have) }))}</p>` : ''}
      <button type="button" class="btn" id="find-add">${esc(t('find.add'))}</button></section>`;
  }

  function folderBlock() {
    return `<div class="folder"><span class="lbl">${esc(t('folder.root'))}</span><span class="path">${esc(ctx.dataRoot)}</span><button type="button" class="btn quiet" data-folder="root">${esc(t('folder.change'))}</button></div>
      <div class="folder"><span class="lbl">${esc(t('folder.models'))}</span><span class="path">${esc(ctx.modelsDir)}</span><button type="button" class="btn quiet" data-folder="models">${esc(t('folder.change'))}</button></div>`;
  }

  function showPick() {
    const toFetch = pending().reduce((a, c) => a + c.weight, 0);
    const nothing = pending().length === 0;
    const canStart = diskOk() && hfReady() && accepted && !nothing;
    const title = t(adding ? 'add.title' : 'check.title');
    render(`
      <h1>${esc(title)}</h1>
      <p class="lead">${esc(t(adding ? 'add.lead' : 'check.lead'))}</p>
      <ul class="rows">${checkResult.items.map(checkRow).join('')}</ul>
      <section class="pickbox" aria-labelledby="pick-title">
        <h2 id="pick-title">${esc(t('pick.title'))}</h2>
        <p class="text">${esc(t('pick.lead'))}</p>
        ${profileBlock()}
        <ul class="picks">${Object.keys(ctx.sets).map(setRow).join('')}</ul>
        <p class="note">${esc(t('pick.music'))}</p>
      </section>
      ${adding ? '' : findBlock()}
      ${adding ? '' : folderBlock()}
      ${adding ? '' : `<label class="accept"><input type="checkbox" id="accept"${accepted ? ' checked' : ''}> <span>${esc(t('license.accept'))}</span></label>`}
      <p class="note">${esc(t('license.region'))}</p>
      <p class="note">${esc(nothing ? t('pick.nothing') : t(adding ? 'add.note' : 'check.note', { size: fmtBytes(toFetch) }))}</p>
      ${diskOk() ? '' : `<p class="note bad" role="alert">${esc(t('pick.noDisk'))}</p>`}
      ${hfReady() ? '' : `<p class="note bad">${esc(t('hf.needed'))}</p>`}
      <div class="actions">
        <button type="button" class="btn primary" id="start"${canStart ? '' : ' disabled'}>${esc(t(adding ? 'btn.add' : 'btn.start'))}</button>
        ${adding ? `<button type="button" class="btn" id="back">${esc(t('btn.back'))}</button>` : ''}
      </div>`, title);
    bind('#start', startDownload);
    bind('#back', () => api.launch());
    bind('#hf-check', onHf);
    bind('#find-add', () => chooseFolder('find'));
    for (const b of view.querySelectorAll('[data-open]')) b.addEventListener('click', (e) => { e.preventDefault(); api.openExternal(b.dataset.open); });
    for (const b of view.querySelectorAll('[data-folder]')) b.addEventListener('click', () => chooseFolder(b.dataset.folder));
    for (const b of view.querySelectorAll('[data-drop]')) b.addEventListener('click', async () => { await api.dropFind(b.dataset.drop); await refresh(); });
    const token = $('#hf-token');
    if (token) {
      token.addEventListener('input', () => { hfDraft = token.value; });
      token.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); onHf(); } });
    }
    const accept = $('#accept');
    if (accept) accept.addEventListener('change', () => { accepted = accept.checked; $('#start').disabled = !(diskOk() && hfReady() && accepted && pending().length); });
    $('.pickbox').addEventListener('change', onPick);
  }

  /** Re-reads the plan and the disk check after a change, keeping the focus where it was. */
  async function refresh(focusSel) {
    ctx = await api.context();
    checkResult = await api.checks();
    showPick();
    const again = focusSel && $(focusSel);
    if (again) again.focus();
  }

  async function onPick(ev) {
    const el = ev.target;
    if (!(el instanceof HTMLInputElement)) return;
    let sets = [...ctx.picked];
    let focus;
    if (el.name === 'profile') {
      if (el.value === 'own') return;
      sets = [...ctx.profiles[el.value]];
      focus = `input[name="profile"][value="${el.value}"]`;
    } else if (el.dataset.set) {
      sets = el.checked ? [...sets, el.dataset.set] : sets.filter((id) => id !== el.dataset.set);
      focus = `[data-set="${el.dataset.set}"]`;
    } else return;
    // what is on disk stays picked: the installer never removes a set
    for (const [id, s] of Object.entries(ctx.sets)) if (s.complete && !sets.includes(id)) sets.push(id);
    await api.setSets(sets);
    await refresh(focus);
  }

  async function onHf() {
    if (hfBusy) return;
    hfBusy = true;
    showPick();
    try { hf = await api.checkHfToken(hfDraft); } finally { hfBusy = false; }
    if (hf.user) { hfDraft = ''; ctx = await api.context(); }
    showPick();
    const again = $('#hf-check');
    if (again) again.focus();
  }

  async function chooseFolder(kind) {
    const dir = await api.chooseFolder(kind);
    if (!dir) return;
    const res = await api.setFolder(kind, dir);
    if (!res.ok) { live.textContent = res.message; return; }
    await refresh();
  }

  function showProblem(result) {
    const b = result.blocking;
    const vars = { v: b.gpu ? b.gpu.driver : '', r: b.required ?? '', gpu: b.gpu ? b.gpu.name : '' };
    const steps = t(`p.${b.code}.steps`, vars);
    const primary = {
      'no-gpu': ['btn.drivers', () => api.openExternal('nvidia-drivers')],
      'old-driver': ['btn.drivers', () => api.openExternal('nvidia-drivers')],
      'old-gpu': ['btn.report', () => api.openExternal('issues')],
      'unsupported-platform': ['btn.report', () => api.openExternal('issues')],
      offline: ['btn.recheck', runChecksAndShow],
    }[b.code];
    setSteps(1, 'bad');
    render(`
      <h1>${esc(t(`p.${b.code}.title`, vars))}</h1>
      <p class="lead">${esc(t(`p.${b.code}.lead`, vars))}</p>
      ${steps.length ? `<ol class="steplist">${steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>` : ''}
      <details><summary>${esc(t('error.details'))}</summary><pre>${esc(JSON.stringify(result, null, 2))}</pre></details>
      <div class="actions">
        <button type="button" class="btn primary" id="primary">${esc(t(primary[0]))}</button>
        ${b.code !== 'offline' ? `<button type="button" class="btn" id="recheck">${esc(t('btn.recheck'))}</button>` : ''}
      </div>`, t(`p.${b.code}.title`, vars));
    bind('#primary', primary[1]);
    bind('#recheck', runChecksAndShow);
  }

  // ---------- 2. the install ----------
  function startDownload() {
    rows = {};
    for (const c of ctx.plan) rows[c.id] = { status: c.done ? 'done' : 'queued', done: 0, total: 0, note: '', weight: c.weight };
    samples = [];
    paused = false;
    setResults = {};
    setSteps(2);
    render(`
      <h1>${esc(t('download.title'))}</h1>
      <p class="lead">${esc(t('download.lead'))}</p>
      <div class="bigbar">
        <div class="top"><span class="pct" id="pct">0%</span><span class="meta" id="meta"></span></div>
        <div class="track" role="progressbar" aria-label="${esc(t('download.title'))}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" id="bigtrack"><i id="bigfill"></i></div>
      </div>
      <ul class="rows" id="comps">${ctx.plan.map((c) => `<li id="row-${c.id}"><span class="ico-slot"></span><span class="name">${esc(t('comp.' + c.id))}</span><span class="state"></span><div class="track thin" role="progressbar" aria-label="${esc(t('comp.' + c.id))}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" hidden><i></i></div><div class="note-line" hidden></div></li>`).join('')}</ul>
      <div class="actions"><button type="button" class="btn" id="pause">${esc(t('btn.pause'))}</button><button type="button" class="btn quiet" id="logs">${esc(t('btn.logs'))}</button></div>`, t('download.title'));
    for (const c of ctx.plan) renderRow(c.id);
    renderOverall();
    bind('#pause', togglePause);
    bind('#logs', () => api.openLogs());
    api.start();
  }

  function togglePause() {
    const btn = $('#pause');
    if (!paused) { btn.disabled = true; api.pause(); return; }   // the «paused» event finishes the switch
    paused = false;
    btn.textContent = t('btn.pause');
    api.start();
    renderOverall();
  }

  const fraction = (r) => (r.status === 'done' ? 1 : r.total > 0 ? Math.min(1, r.done / r.total) : 0);

  function renderRow(id) {
    const r = rows[id];
    const li = document.getElementById(`row-${id}`);
    if (!li) return;
    const slot = li.querySelector('.ico, .ico-slot');
    const state = li.querySelector('.state');
    const bar = li.querySelector('.track');
    const noteLine = li.querySelector('.note-line');
    const size = fmtBytes(r.weight);
    slot.outerHTML = icon({ done: 'ok', running: 'run', error: 'err', partial: 'warn' }[r.status] || 'wait');
    state.textContent = r.status === 'done' ? `${t('status.done')}, ${size}`
      : r.status === 'skipped' ? t('status.skipped') : r.status === 'error' ? t('status.error') : r.status === 'partial' ? t('status.partial')
      : r.status === 'running' ? (r.total > 0 ? `${Math.round(fraction(r) * 100)}%, ${size}` : `${t('status.working')}, ${size}`)
      : `${t('status.queued')}, ${size}`;
    const running = r.status === 'running';
    bar.hidden = !(running && r.total > 0);
    if (!bar.hidden) { bar.firstElementChild.style.width = `${fraction(r) * 100}%`; bar.setAttribute('aria-valuenow', String(Math.round(fraction(r) * 100))); }
    noteLine.hidden = !(running && r.note);
    if (!noteLine.hidden) noteLine.textContent = r.note;
  }

  function renderOverall() {
    const totalWeight = Object.values(rows).reduce((a, r) => a + r.weight, 0) || 1;
    const bytes = Object.values(rows).reduce((a, r) => a + r.weight * fraction(r), 0);
    const pct = Math.min(100, Math.round((bytes / totalWeight) * 100));
    const now = Date.now();
    samples.push([now, bytes]);
    samples = samples.filter(([time]) => now - time < 8000);
    let speed = 0;
    if (samples.length > 1) { const [t0, b0] = samples[0]; if (now - t0 > 1500) speed = ((bytes - b0) / (now - t0)) * 1000; }
    const parts = [t('meta.progress', { done: fmtBytes(bytes), total: fmtBytes(totalWeight) })];
    if (paused) parts.push(t('meta.paused'));
    else if (speed > 1e5) parts.push(t('meta.speed', { speed: fmtBytes(speed) }), t('meta.eta', { eta: fmtEta((totalWeight - bytes) / speed) }));
    const pctEl = $('#pct');
    if (!pctEl) return;
    pctEl.textContent = `${pct}%`;
    $('#bigfill').style.width = `${pct}%`;
    $('#bigtrack').setAttribute('aria-valuenow', String(pct));
    $('#meta').textContent = parts.join(' · ');
  }

  // ---------- 3. done, failure, start ----------
  function showDone(partial) {
    setSteps(3);
    const sets = Object.entries(setResults);
    const anyMissing = Object.keys(partial || {}).length > 0;
    render(`
      <h1>${esc(t('done.title'))}</h1>
      <p class="lead">${esc(t('done.lead'))}</p>
      ${sets.length ? `<ul class="rows">${sets.map(([id, r]) => `<li>${icon(r.status === 'done' ? 'ok' : 'warn')}<span class="name">${esc(setTitle(id))}</span><span class="state long">${esc(t('done.set.' + r.status) + (r.error ? `: ${r.error}` : ''))}</span></li>`).join('')}</ul>` : ''}
      ${anyMissing ? `<p class="note">${esc(t('done.partial'))}</p>` : ''}
      <p class="note">${esc(t('done.note'))}</p>
      <div class="actions">
        <button type="button" class="btn primary" id="open">${esc(t(adding ? 'btn.back' : 'btn.open'))}</button>
        ${anyMissing ? `<button type="button" class="btn" id="retry">${esc(t('btn.retry'))}</button>` : ''}
        <button type="button" class="btn quiet" id="data">${esc(t('btn.showdata'))}</button>
      </div>`, t('done.title'));
    bind('#open', () => api.launch());
    bind('#retry', async () => { ctx = await api.context(); startDownload(); });
    bind('#data', () => api.showData());
  }

  function showFailure(message, componentId) {
    setSteps(2, 'bad');
    render(`
      <h1>${esc(t('error.title'))}</h1>
      <p class="lead">${esc(t('error.lead', { comp: componentId ? t('comp.' + componentId) : '' }))}</p>
      <details open><summary>${esc(t('error.details'))}</summary><pre>${esc(message)}</pre></details>
      <div class="actions"><button type="button" class="btn primary" id="retry">${esc(t('btn.retry'))}</button><button type="button" class="btn" id="logs">${esc(t('btn.logs'))}</button><button type="button" class="btn quiet" id="report">${esc(t('btn.report'))}</button></div>`, t('error.title'));
    bind('#retry', async () => { ctx = await api.context(); startDownload(); });
    bind('#logs', () => api.openLogs());
    bind('#report', () => api.openExternal('issues'));
  }

  function showStarting() {
    setSteps(3);
    render(`<h1>${esc(t('starting.title'))}</h1><p class="lead">${esc(t('starting.lead'))}</p><div class="spinner" role="presentation"></div>`, t('starting.title'));
  }

  function showCrashed(message) {
    setSteps(3, 'bad');
    render(`
      <h1>${esc(t('crashed.title'))}</h1>
      <p class="lead">${esc(t('crashed.lead'))}</p>
      <details open><summary>${esc(t('error.details'))}</summary><pre>${esc(message)}</pre></details>
      <div class="actions"><button type="button" class="btn primary" id="retry">${esc(t('btn.retry'))}</button><button type="button" class="btn" id="logs">${esc(t('btn.logs'))}</button><button type="button" class="btn quiet" id="report">${esc(t('btn.report'))}</button></div>`, t('crashed.title'));
    bind('#retry', () => api.launch());
    bind('#logs', () => api.openLogs());
    bind('#report', () => api.openExternal('issues'));
  }

  function onEvent(ev) {
    if (ev.type === 'component' && rows[ev.id]) {
      const r = rows[ev.id];
      r.status = ev.status;
      if (ev.done !== undefined) { r.done = ev.done; r.total = ev.total; }
      if (ev.note) r.note = ev.note;
      if (ev.status === 'done') { r.done = r.total = 1; r.note = ''; }
      if (ev.result && ev.result.sets) setResults = ev.result.sets;
      renderRow(ev.id);
      renderOverall();
    } else if (ev.type === 'finished') showDone(ev.partial);
    else if (ev.type === 'paused') {
      paused = true;
      const btn = $('#pause');
      if (btn) { btn.disabled = false; btn.textContent = t('btn.resume'); }
      renderOverall();
    } else if (ev.type === 'failed') showFailure(ev.message, ev.componentId);
    else if (ev.type === 'starting') showStarting();
  }

  (async function init() {
    ctx = await api.context();
    locale = ctx.languages.some((lang) => String(lang).toLowerCase().startsWith('ru')) ? 'ru' : 'en';
    document.documentElement.lang = locale;
    api.setLang(locale);   // the downloader's messages in the same language
    api.onEvent(onEvent);
    if (params.get('state') === 'crashed') return showCrashed(params.get('message') || '');
    runChecksAndShow();
  })();
})();
