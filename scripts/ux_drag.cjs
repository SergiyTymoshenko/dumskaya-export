#!/usr/bin/env node
// Порядок файлов в «Студии» пальцем (решено 27.10.2026, вечер): касания телефона через Chromium (CDP Input.dispatchTouchEvent).
//   • нажать и подержать фото в режиме «Порядок», вести пальцем — фото встаёт на новое место (и на сервере);
//   • быстро провести пальцем по фото — это прокрутка страницы, порядок не меняется;
//   • коснуться фото — открывается просмотр.
// Стенд — scripts/tests/ux_stand.py (как у ux_apps.cjs). Скриншоты — /tmp/dumskaya-ux-drag.
// Запуск: node scripts/ux_drag.cjs
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const L = require('./ux_lib.cjs');
const { chromium } = L.playwright();
const PORT = Number(L.arg('--port', 18772));
const OUT = '/tmp/dumskaya-ux-drag';
fs.mkdirSync(OUT, { recursive: true });

const tgMock = (init) => `window.Telegram = { WebApp: (function () {
  const btn = () => ({ text: '', isVisible: false, isActive: true, _cb: [], setText(t) { this.text = t; return this; }, show() { this.isVisible = true; return this; },
    hide() { this.isVisible = false; return this; }, enable() { return this; }, disable() { return this; }, showProgress() { return this; }, hideProgress() { return this; },
    onClick(f) { this._cb.push(f); return this; }, offClick(f) { this._cb = this._cb.filter((x) => x !== f); return this; }, setParams(p) { Object.assign(this, p); return this; } });
  return { initData: ${JSON.stringify(init)}, initDataUnsafe: { user: { id: 1, first_name: 'T', language_code: 'ru' } }, colorScheme: 'light', themeParams: {},
    platform: 'ios', version: '8.0', viewportHeight: innerHeight, isExpanded: true, isVersionAtLeast() { return true; }, ready() {}, expand() {}, close() {},
    onEvent() {}, offEvent() {}, setHeaderColor() {}, setBackgroundColor() {}, enableClosingConfirmation() {}, disableClosingConfirmation() {}, disableVerticalSwipes() {},
    showConfirm(t, cb) { cb && cb(true); }, showAlert(t, cb) { cb && cb(); }, showPopup(p, cb) { cb && cb(''); }, openLink() {}, openTelegramLink() {},
    HapticFeedback: { notificationOccurred() {}, impactOccurred() { window.__haptic = (window.__haptic || 0) + 1; }, selectionChanged() {} },
    MainButton: btn(), SecondaryButton: btn(),
    BackButton: { isVisible: false, _cb: [], show() { this.isVisible = true; }, hide() { this.isVisible = false; }, onClick(f) { this._cb.push(f); }, offClick(f) { this._cb = this._cb.filter((x) => x !== f); } } };
})() };`;

function startStand() {
  return new Promise((ok, fail) => {
    const ch = spawn('python3', [path.join(L.ROOT, 'scripts/tests/ux_stand.py'), String(PORT)], { stdio: ['ignore', 'pipe', 'pipe'] });
    let buf = '';
    const t = setTimeout(() => fail(new Error('стенд не запустился за 60 с')), 60000);
    ch.stdout.on('data', (d) => { buf += d; const l = buf.split('\n').find((x) => x.startsWith('{"port"')); if (l) { clearTimeout(t); ok({ ch, st: JSON.parse(l) }); } });
    ch.on('exit', (c) => fail(new Error('стенд остановился, код ' + c)));
  });
}

(async () => {
  const R = L.report();
  const { ch, st } = await startStand();
  const BASE = `http://127.0.0.1:${st.port}`;
  const b = await chromium.launch();
  try {
    const ctx = await b.newContext({ viewport: { width: 390, height: 760 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', (e) => errs.push(e.message.slice(0, 160)));
    await p.route('https://telegram.org/**', (r) => r.fulfill({ contentType: 'text/javascript', body: tgMock(st.init.irina) }));
    const cdp = await ctx.newCDPSession(p);
    const touch = (type, x, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y, id: 1 }] });
    const G = '#sec-files .gallery';
    const centre = async (sel) => { const r = await (await p.$(sel)).boundingBox(); return [r.x + r.width / 2, r.y + r.height / 2]; };
    const names = () => p.$$eval(G + ' > .gcell .doc .nm', (xs) => xs.map((x) => x.textContent.trim().split('.')[0]));
    const shot = (n) => p.screenshot({ path: path.join(OUT, n + '.png') });
    const H = { 'X-Telegram-Init-Data': st.init.irina };
    const openDocs = async () => {
      await p.goto(BASE + '/api/crm/app?tab=projects', { waitUntil: 'load' }); await p.waitForTimeout(1500);
      await p.click('#nav .in > button[data-tab="projects"]'); await p.waitForTimeout(400);
      await p.click('#app button.pcard'); await p.waitForTimeout(1200);
      await p.locator('#sec-files button.chip', { hasText: /^Документация/ }).first().click(); await p.waitForTimeout(500);
    };
    const ordOn = async () => {
      await p.locator('#sec-files button.chip', { hasText: /Порядок/ }).first().click(); await p.waitForTimeout(500);
      await p.$eval(G, (g) => g.scrollIntoView({ block: 'center' })); await p.waitForTimeout(300);
    };

    // документы с номерами — загружены вперемешку; по умолчанию стоят по номерам
    await p.goto(BASE + '/api/crm/app?tab=projects', { waitUntil: 'load' }); await p.waitForTimeout(1200);
    const first = (await p.$eval('#app button.pcard', (x) => x.innerText)).trim();
    const state = await (await fetch(BASE + '/api/crm/state', { headers: H })).json();
    const pid = (state.projects.find((x) => first.includes(x.title)) || state.projects[0]).id;
    for (const n of ['12. План кондиционирования.pdf', '08. План демонтажа.pdf', '10. План монтажа ГКЛ.pdf', '9. План монтажа блоков.pdf', '13-14. План дверей.pdf']) {
      const r = await fetch(`${BASE}/api/crm/upload?project=${pid}&cat=docs&name=${encodeURIComponent(n)}`,
        { method: 'POST', headers: { ...H, 'Content-Type': 'application/pdf' }, body: Buffer.from('%PDF-1.4 test ' + n) });
      if (!r.ok) throw new Error('загрузка ' + n + ': ' + r.status);
    }
    await openDocs();
    const start = await names();
    R.ok(start.slice(0, 5).join(' ') === '08 9 10 12 13-14', 'по умолчанию документы — по номерам в названиях', start.join(' '));
    await ordOn();
    R.ok(!(await p.$('#sec-files .ordbar')), 'кнопок ‹ › под файлами больше нет');
    await shot('1-poryadok');

    // 1) нажать, подержать, повести пальцем: «08» — на место третьего
    const [x0, y0] = await centre(G + ' > .gcell:nth-child(1)');
    const [x1, y1] = await centre(G + ' > .gcell:nth-child(3)');
    await touch('touchStart', x0, y0); await p.waitForTimeout(400);
    const lifted = await p.$('.ord-ghost');
    for (let k = 1; k <= 12; k++) { await touch('touchMove', x0 + (x1 - x0) * k / 12, y0 + (y1 - y0) * k / 12); await p.waitForTimeout(25); }
    await shot('2-tashchu');
    await touch('touchEnd'); await p.waitForTimeout(1200);
    const after = await names();
    R.ok(!!lifted && after.slice(0, 3).join(' ') === '9 10 08', 'подержал и повёл пальцем — «08» стал третьим', lifted ? after.join(' ') : 'файл не приподнялся');
    R.ok(!(await p.$('.viewer')) && !(await p.$('.ord-ghost, .ord-hole')), 'после перетаскивания файл не открылся, копия под пальцем убрана');
    R.ok((await p.evaluate(() => window.__haptic || 0)) > 0, 'файл приподнялся с лёгкой вибрацией');
    await shot('3-gotovo');

    // 2) сохранено на сервере
    await openDocs();
    R.ok((await names()).slice(0, 3).join(' ') === '9 10 08', 'новый порядок сохранён (после перезагрузки тот же)');

    // 3) быстро провести пальцем вверх по файлу — прокрутка, порядок не меняется
    await ordOn();
    const [sx, sy] = await centre(G + ' > .gcell:nth-child(2)');
    const y0s = await p.evaluate(() => scrollY), o0 = await names();
    await touch('touchStart', sx, sy);
    for (let k = 1; k <= 8; k++) { await touch('touchMove', sx, sy - k * 30); await p.waitForTimeout(16); }
    await touch('touchEnd'); await p.waitForTimeout(900);
    const y1s = await p.evaluate(() => scrollY), o1 = await names();
    R.ok(y1s > y0s + 50 && o0.join() === o1.join() && !(await p.$('.ord-ghost')), 'быстрое движение пальцем — прокрутка страницы, порядок прежний',
      `прокрутка ${Math.round(y1s - y0s)} px`);

    // 4) «По номерам» — раздел снова по номерам
    const reset = p.locator('#sec-files button.chip', { hasText: /По номерам/ });
    R.ok(await reset.count() > 0, 'в разделе, который расставляли, есть «1→9 По номерам»');
    if (await reset.count()) { await reset.first().click(); await p.waitForTimeout(900); }
    R.ok((await names()).slice(0, 5).join(' ') === '08 9 10 12 13-14', '«По номерам» — снова 08, 9, 10, 12, 13-14');

    // 5) коснуться — открыть файл
    const [tx, ty] = await centre(G + ' > .gcell:nth-child(2) .doc');
    await touch('touchStart', tx, ty); await p.waitForTimeout(60); await touch('touchEnd'); await p.waitForTimeout(800);
    R.ok(!!(await p.$('.viewer')), 'короткое касание открывает файл');
    await shot('4-prosmotr');
    R.ok(!errs.length, 'без ошибок скрипта', errs.join(' | '));
  } finally {
    await b.close(); ch.kill();
  }
  process.exit(R.done(OUT, 'Порядок пальцем') ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
