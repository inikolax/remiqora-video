'use strict';
// Drives the setup screen from source with Playwright's Electron support, in throwaway folders, and saves screenshots.
//   cd desktop && npm i --no-save playwright && node test/e2e/screens.js <out-dir> [config.json] [--install]
// config.json (optional) is copied as the user-data config.json: dataRoot, modelsDir, find, sets.
// --install presses «Установить» and waits for the end (downloads the engine: about 10 GB, 10-20 minutes).
const fs = require('node:fs');
const path = require('node:path');
const { _electron: electron } = require('playwright');

(async () => {
  const [out, config] = process.argv.slice(2).filter((a) => !a.startsWith('--'));
  const install = process.argv.includes('--install');
  const userData = path.join(out, 'user-data');
  fs.mkdirSync(userData, { recursive: true });
  if (config) fs.copyFileSync(config, path.join(userData, 'config.json'));
  const app = await electron.launch({
    args: [path.join(__dirname, '..', '..')],
    env: { ...process.env, REMIQORA_VIDEO_USER_DATA: userData, REMIQORA_VIDEO_HOME: path.join(out, 'home'), REMIQORA_VIDEO_LANG: process.env.LANG_UI || 'ru' },
  });
  const win = await app.firstWindow();
  win.on('console', (m) => { if (m.type() === 'error') console.log('console:', m.text()); });
  await win.setViewportSize({ width: 1320, height: 860 }).catch(() => {});
  await win.waitForSelector('.pickbox, h1:has-text("NVIDIA"), .steplist', { timeout: 60000 });
  await win.screenshot({ path: path.join(out, '1-pick.png'), fullPage: true });
  console.log('screen 1:', (await win.locator('h1').innerText()));
  console.log('rows:', (await win.locator('.rows > li').allInnerTexts()).join(' | '));
  console.log('sets:', (await win.locator('.pick').allInnerTexts()).map((s) => s.replace(/\s+/g, ' ')).join(' | '));
  if (install) {
    await win.locator('#accept').check();
    await win.locator('#start').click();
    await win.waitForSelector('#comps', { timeout: 10000 });
    await win.waitForTimeout(4000);
    await win.screenshot({ path: path.join(out, '2-progress.png'), fullPage: true });
    const t0 = Date.now();
    let last = '';
    while (true) {
      const h1 = await win.locator('h1').innerText().catch(() => '');
      if (/Готово|Done|остановилась|stopped/.test(h1)) break;
      const now = (await win.locator('#comps').innerText().catch(() => '')).replace(/\s+/g, ' ');
      if (now !== last && Date.now() % 1 === 0) { last = now; }
      if ((Date.now() - t0) % 60000 < 2000) console.log(`${Math.round((Date.now() - t0) / 1000)}s`, (await win.locator('#meta').innerText().catch(() => '')));
      await win.waitForTimeout(2000);
      if (Date.now() - t0 > 60 * 60 * 1000) throw new Error('the install took over an hour');
    }
    await win.screenshot({ path: path.join(out, '3-done.png'), fullPage: true });
    console.log('end:', await win.locator('h1').innerText(), '|', (await win.locator('.rows').allInnerTexts().catch(() => [])).join(' '));
    const details = await win.locator('pre').allInnerTexts().catch(() => []);
    if (details.length) console.log('details:', details.join('\n'));
    if (await win.locator('#open').count()) {
      await win.locator('#open').click();
      await win.waitForURL(/127\.0\.0\.1/, { timeout: 180000 });
      await win.waitForTimeout(5000);
      await win.screenshot({ path: path.join(out, '4-app.png') });
      console.log('app opened at', win.url());
    }
  }
  await app.close();
})().catch((err) => { console.error(err); process.exit(1); });
