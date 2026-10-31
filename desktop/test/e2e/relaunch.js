'use strict';
// A second start of an installed setup goes straight into the app; what is left (a step from an older run) is
// finished first through the setup screen. Uses the folders of a screens.js run:
//   node test/e2e/relaunch.js <out-dir of screens.js --install>
const path = require('node:path');
const { _electron: electron } = require('playwright');

async function start(out) {
  const app = await electron.launch({
    args: [path.join(__dirname, '..', '..')],
    env: { ...process.env, REMIQORA_VIDEO_USER_DATA: path.join(out, 'user-data'), REMIQORA_VIDEO_HOME: path.join(out, 'home'), REMIQORA_VIDEO_LANG: 'ru' },
  });
  const win = await app.firstWindow();
  await win.waitForFunction(() => location.protocol.startsWith('http') || document.querySelector('.pickbox, #comps, h1'), null, { timeout: 120000 });
  await win.waitForTimeout(3000);
  return { app, win };
}

(async () => {
  const out = process.argv[2];
  let { app, win } = await start(out);
  console.log('first start:', win.url().startsWith('http') ? 'the app' : 'the setup screen');
  if (!win.url().startsWith('http')) {
    console.log('left to do:', (await win.locator('.note').allInnerTexts()).join(' | '));
    await win.locator('#accept').check();
    await win.locator('#start').click();
    await win.waitForSelector('#open', { timeout: 600000 });
    await app.close();
    ({ app, win } = await start(out));
    console.log('next start:', win.url().startsWith('http') ? `the app (${win.url()})` : 'the setup screen again');
  }
  await win.waitForTimeout(2000);
  const add = win.locator('text=Добавить наборы моделей');
  await win.goto(new URL('#/models/h3', win.url()).toString());
  await win.waitForTimeout(3000);
  console.log('models page button:', await add.count());
  if (await add.count()) {
    await add.first().click();
    await win.waitForSelector('.pickbox', { timeout: 60000 });
    console.log('add mode:', await win.locator('h1').innerText(), '| back button:', await win.locator('#back').count());
    await win.screenshot({ path: path.join(out, '5-add.png'), fullPage: true });
    await win.locator('#back').click();
    await win.waitForURL(/127\.0\.0\.1/, { timeout: 30000 });
    console.log('back in the app:', win.url());
  }
  await app.close();
})().catch((err) => { console.error(err); process.exit(1); });
