// End-to-end check in real Chromium: phone flow, TV display, admin, print card, text fit for every set.
// Usage: NODE_PATH=$(npm root -g) BASE=http://localhost:3100 OUT=./shots PIN=1234 node test/e2e.cjs
// WARNING: wipes all game data on the target server.
const { chromium, devices } = require('playwright');
const fs = require('fs');

const BASE = process.env.BASE || 'http://localhost:3100';
const OUT = process.env.OUT || './shots';
const PIN = process.env.PIN || '1234';
fs.mkdirSync(OUT, { recursive: true });

const problems = [];
const check = (cond, msg) => { if (!cond) problems.push(msg); };

async function api(path, body, headers = {}) {
  const res = await fetch(BASE + path, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, data: await res.json().catch(() => ({})), headers: res.headers };
}

const overflowing = (page, sel) => page.evaluate((s) => [...document.querySelectorAll(s)]
  .filter((b) => b.scrollHeight > b.clientHeight + 1 || b.scrollWidth > b.clientWidth + 1)
  .map((b) => b.textContent), sel);
const scrollsSideways = (page) => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);

(async () => {
  const browser = await chromium.launch();
  const watch = (page, name) => {
    page.on('console', (m) => {
      // The admin test types a wrong PIN on purpose; that 401 is expected.
      if (m.type() === 'error' && !(name === 'admin' && /status of 401/.test(m.text()))) problems.push(`${name} console error: ${m.text()}`);
    });
    page.on('pageerror', (e) => problems.push(`${name} page error: ${e.message}`));
  };

  const login = await api('/api/admin/login', { pin: PIN });
  const adminCookie = (login.headers.get('set-cookie') || '').split(';')[0];
  const admin = (path, body) => api(path, body, { Cookie: adminCookie });
  await admin('/api/admin/wipe', { confirm: 'RESET' });
  await admin('/api/admin/settings', { cooldownMin: 10, lineCap: 3, paused: false, ended: false });

  // TV first, so it sees everything happen.
  const tvCtx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, reducedMotion: 'no-preference' });
  const tv = await tvCtx.newPage();
  watch(tv, 'tv');
  await tv.goto(BASE + '/display');
  await tv.waitForSelector('#grid .sq');
  await tv.waitForTimeout(800);
  await tv.screenshot({ path: `${OUT}/tv-1-empty.png` });

  // Phone: sign up.
  const phoneCtx = await browser.newContext({ ...devices['iPhone 13'], reducedMotion: 'no-preference' });
  const phone = await phoneCtx.newPage();
  watch(phone, 'phone');
  await phone.goto(BASE + '/');
  await phone.waitForSelector('#screen-register:not([hidden])');
  await phone.screenshot({ path: `${OUT}/phone-1-register.png`, fullPage: true });
  check(!(await scrollsSideways(phone)), 'phone register scrolls sideways');
  check((await phone.locator('#contactTabs button').first().textContent()) === 'LinkedIn', 'LinkedIn is not the first contact option');
  await phone.fill('input[name=name]', 'Dana Rivera');
  await phone.fill('input[name=company]', 'Acme Analytics');
  await phone.fill('#contactValue', 'linkedin.com/in/dana-rivera');
  const t0 = Date.now();
  await phone.click('#regBtn');
  await phone.waitForSelector('#screen-board:not([hidden])');
  check(Date.now() - t0 < 3000, 'sign-up took over 3 seconds locally');
  await phone.waitForTimeout(500);
  await phone.screenshot({ path: `${OUT}/phone-2-board.png`, fullPage: true });

  // Claim N3: first tap opens the sheet, second confirms.
  await phone.click('.sq[data-idx="12"]');
  await phone.waitForSelector('#sheet:not([hidden])');
  check((await tv.evaluate(() => document.querySelectorAll('#grid .sq.claimed').length)) === 0, 'first tap claimed without confirming');
  await phone.waitForTimeout(400); // let the sheet's slide-up animation finish
  await phone.screenshot({ path: `${OUT}/phone-3-sheet.png` });
  await phone.click('#sheet .btn.primary');
  await phone.waitForSelector('#sheet .result-title');
  await phone.waitForTimeout(700);
  await phone.screenshot({ path: `${OUT}/phone-4-winner.png` });
  const title = await phone.textContent('#sheet .result-title');
  check(/claim #1/.test(title), `first claim title unexpected: ${title}`);
  check(await phone.isVisible('#sheet .code'), 'first-five winner has no code');
  await phone.click('#sheet .ratings button:first-child');
  await phone.waitForTimeout(400);
  await phone.click('#sheet .btn.dark');
  await phone.waitForTimeout(300);
  await phone.screenshot({ path: `${OUT}/phone-5-cooldown.png`, fullPage: true });
  check(/unlocks in/.test(await phone.textContent('#banner')), 'cooldown banner missing after claim');
  check(await phone.isVisible('#myKitBtn'), 'kit button should be visible after winning');

  await tv.waitForTimeout(500);
  check((await tv.evaluate(() => document.querySelectorAll('#grid .sq.claimed').length)) === 1, 'tv did not show the claim');

  // Bots fill Row 3 (cells 10..14); N3 (12) is already Dana's.
  const bots = [];
  for (let i = 0; i < 8; i++) {
    const r = await api('/api/register', { name: `Bot ${i}`, company: 'BotCo', contactType: 'email', contactValue: `bot${i}@botco.com` });
    bots.push(r.data.token);
  }
  const claimAs = (t, idx) => api('/api/claim', { idx }, { 'X-Player-Token': t });
  await claimAs(bots[0], 10);
  await claimAs(bots[1], 11);
  await claimAs(bots[2], 13);
  await tv.waitForTimeout(700);
  await tv.screenshot({ path: `${OUT}/tv-2-progress.png` });
  const done = await claimAs(bots[3], 14);
  check(done.data.result && done.data.result.lines.includes('Row 3'), 'bot did not complete Row 3');
  check(done.data.result && done.data.result.outcome === 'first_five_kit', `5th player outcome: ${done.data.result && done.data.result.outcome}`);
  await tv.waitForTimeout(900);
  await tv.screenshot({ path: `${OUT}/tv-3-celebrate.png` });
  check(await tv.isVisible('#celebrate'), 'tv did not celebrate the line');
  check(/Row 3 complete/.test(await tv.textContent('#celebrateText')), 'tv celebration text wrong');
  const tvText = await tv.evaluate(() => document.body.innerText);
  for (const leak of ['Dana', 'Acme', 'Bot 0', 'BotCo', 'Kit code', 'W1', 'W3']) check(!tvText.includes(leak), `tv shows "${leak}"`);

  // A line after the first five uses the cap: bots complete B column (0,5,10,15,20) — 10 is claimed.
  await claimAs(bots[4], 0);
  await claimAs(bots[5], 5);
  await claimAs(bots[6], 15);
  const lineWin = await claimAs(bots[7], 20);
  check(lineWin.data.result && lineWin.data.result.outcome === 'line_kit', `B column outcome: ${lineWin.data.result && lineWin.data.result.outcome}`);

  await phone.waitForTimeout(500);
  await phone.screenshot({ path: `${OUT}/phone-6-board-after.png`, fullPage: true });
  await phone.click('#myKitBtn');
  await phone.waitForSelector('#sheet .code');
  await phone.screenshot({ path: `${OUT}/phone-7-mykit.png` });
  await phone.click('#sheet .btn.dark');

  // Admin on a phone.
  const adCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const ad = await adCtx.newPage();
  watch(ad, 'admin');
  await ad.goto(BASE + '/admin');
  await ad.waitForSelector('#login:not([hidden])');
  await ad.fill('#pin', '0000');
  await ad.click('#loginForm button');
  await ad.waitForSelector('#loginError:not([hidden])');
  await ad.fill('#pin', PIN);
  await ad.click('#loginForm button');
  await ad.waitForSelector('.feed-item');
  await ad.waitForTimeout(500);
  await ad.screenshot({ path: `${OUT}/admin-1-phone.png`, fullPage: true });
  check(!(await scrollsSideways(ad)), 'admin scrolls sideways at 390px');
  const danaKit = ad.locator('.kit-row', { hasText: 'Dana Rivera' }).locator('.btn.primary');
  await danaKit.click();
  await phone.waitForTimeout(1500);
  check(!(await phone.isVisible('#myKitBtn')), 'phone kit button still visible after hand-over');

  const csvBytes = Buffer.from(await (await fetch(BASE + '/api/admin/export.csv', { headers: { Cookie: adminCookie } })).arrayBuffer());
  check(csvBytes[0] === 0xef && csvBytes[1] === 0xbb && csvBytes[2] === 0xbf, 'CSV has no BOM');
  const csv = csvBytes.toString('utf8');
  const csvLines = csv.trim().split(/\r\n/);
  check(csvLines.length === 1 + 9, `CSV rows: ${csvLines.length - 1} (expected 9)`);
  check(/Dana Rivera,Acme Analytics,linkedin,linkedin\.com\/in\/dana-rivera,Big one,first_five_kit/.test(csv), 'CSV missing Dana row with rating');

  // Text fit for every set, at the tightest sizes.
  for (let set = 1; set <= 4; set++) {
    for (const w of [390, 360, 320]) {
      await phone.setViewportSize({ width: w, height: 740 });
      await phone.waitForTimeout(150);
      const f = await overflowing(phone, '.sq');
      check(f.length === 0, `set ${set}: phone squares clipped at ${w}px: ${f.join(' | ')}`);
      check(!(await scrollsSideways(phone)), `set ${set}: phone scrolls sideways at ${w}px`);
    }
    for (const [w, h] of [[1920, 1080], [1366, 768], [1280, 720]]) {
      await tv.setViewportSize({ width: w, height: h });
      await tv.waitForTimeout(150);
      const f = await overflowing(tv, '#grid .sq');
      check(f.length === 0, `set ${set}: tv squares clipped at ${w}x${h}: ${f.join(' | ')}`);
      const scrolls = await tv.evaluate(() => document.documentElement.scrollHeight > document.documentElement.clientHeight + 1 || document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
      check(!scrolls, `set ${set}: tv page scrolls at ${w}x${h}`);
    }
    if (set === 1) {
      await phone.setViewportSize({ width: 320, height: 640 });
      await phone.screenshot({ path: `${OUT}/phone-w320.png`, fullPage: true });
      await tv.setViewportSize({ width: 1366, height: 768 });
      await tv.waitForTimeout(4000);
      await tv.screenshot({ path: `${OUT}/tv-4-1366.png` });
    }
    await admin('/api/admin/skip', {});
    await phone.waitForTimeout(600);
  }

  const pr = await (await browser.newContext({ viewport: { width: 900, height: 1200 } })).newPage();
  watch(pr, 'print');
  await pr.goto(BASE + '/print');
  await pr.waitForTimeout(500);
  await pr.screenshot({ path: `${OUT}/print.png`, fullPage: true });

  await browser.close();
  console.log(problems.length ? 'PROBLEMS:\n- ' + problems.join('\n- ') : 'ALL CHECKS PASSED');
  process.exit(problems.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
