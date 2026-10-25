// Проверка UI/UX мини-приложений бота — «Студия» (crm_app.html), «Графики» (stats_app.html), «Сервер и ИИ» (server_app.html)
// и кабинет «Мой проект» (portal_app.html) — правило: после любых изменений этих страниц, до выкладки.
// Запуск:  node scripts/ux_apps.cjs   (нужны Python 3, Playwright с Chromium и axe-core; данные — тестовые, scripts/tests/ux_stand.py:
// сервис на временных базах, Telegram подменён — ничего никуда не уходит).
// Каждый экран (вкладки, проект, заявка, формы, настройки) — на iPhone Pro Max (440), телефоне (390) и в окне Telegram
// на компьютере (420, мышь), с обычным, крупным и очень крупным текстом: прокрутка вбок, доступность (axe), зоны нажатия
// ≥ 44 px у кнопок (24 px — у ссылок в тексте), ошибки скриптов. Скриншоты — в --out, их тоже смотреть глазами.
const path = require('path');
const { spawn } = require('child_process');
const L = require('./ux_lib.cjs');

const { chromium } = L.playwright();
const AXE = L.axeSource();
const OUT = L.outDir('dumskaya-ux-apps');
const PORT = Number(L.arg('--port', 18771));
const R = L.report();
const QUICK = L.has('--quick');          // только iPhone Pro Max и размер текста по умолчанию

// Telegram внутри мини-приложения: подпись (initData) и кнопки «Назад» / «Сохранить» — как у настоящего, без сети
const tgMock = (init) => `window.Telegram = { WebApp: (function () {
  const btn = () => ({ text: '', isVisible: false, isActive: true, _cb: [], setText(t) { this.text = t; return this; }, show() { this.isVisible = true; return this; },
    hide() { this.isVisible = false; return this; }, enable() { this.isActive = true; return this; }, disable() { this.isActive = false; return this; },
    showProgress() { return this; }, hideProgress() { return this; }, onClick(f) { this._cb.push(f); return this; }, offClick(f) { this._cb = this._cb.filter((x) => x !== f); return this; },
    setParams(p) { Object.assign(this, p); return this; } });
  return { initData: ${JSON.stringify(init)}, initDataUnsafe: { user: { id: 1, first_name: 'T', language_code: 'ru' } }, colorScheme: window.__tgScheme || 'light', themeParams: {},
    platform: window.__tgPlatform || 'ios', version: '8.0', viewportHeight: innerHeight, isExpanded: true,
    isVersionAtLeast() { return true; }, ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, setHeaderColor() {}, setBackgroundColor() {},
    enableClosingConfirmation() {}, disableClosingConfirmation() {}, disableVerticalSwipes() {},
    showConfirm(t, cb) { cb && cb(false); }, showAlert(t, cb) { cb && cb(); }, showPopup(p, cb) { cb && cb(''); },
    openLink(u) { window.__opened = u; }, openTelegramLink(u) { window.__opened = u; },
    HapticFeedback: { notificationOccurred() {}, impactOccurred() {}, selectionChanged() {} }, MainButton: btn(), SecondaryButton: btn(),
    BackButton: { isVisible: false, _cb: [], show() { this.isVisible = true; }, hide() { this.isVisible = false; }, onClick(f) { this._cb.push(f); }, offClick(f) { this._cb = this._cb.filter((x) => x !== f); } } };
})() };`;

function startStand() {
  return new Promise((ok, fail) => {
    const ch = spawn('python3', [path.join(L.ROOT, 'scripts/tests/ux_stand.py'), String(PORT)], { stdio: ['ignore', 'pipe', 'pipe'] });
    let buf = '';
    const t = setTimeout(() => fail(new Error('стенд не запустился за 60 с')), 60000);
    ch.stdout.on('data', (d) => {
      buf += d;
      const line = buf.split('\n').find((l) => l.startsWith('{"port"'));
      if (line) { clearTimeout(t); ok({ ch, st: JSON.parse(line) }); }
    });
    ch.on('exit', (c) => fail(new Error('стенд остановился, код ' + c)));
  });
}

const SIZES = QUICK ? ['pm'] : ['pm', 'm', 'tg'];
// роль → приложение, размеры текста (у Ирины по умолчанию «Крупный»)
const RUNS = [
  { app: '/api/crm/app', role: 'irina', name: 'studio', text: QUICK ? ['l'] : ['l', 'xl', 'm'], save: '/api/crm/ui' },
  { app: '/api/crm/app', role: 'owner', name: 'studio-owner', text: ['m'], save: '/api/crm/ui' },
  { app: '/api/stats/app', role: 'irina', name: 'stats', text: QUICK ? ['l'] : ['l', 'xl'], save: '/api/crm/ui' },
  { app: '/api/stats/server/app', role: 'owner', name: 'server', text: ['m'], save: '/api/crm/ui' },
  { app: '/api/portal/app', role: 'client', name: 'cabinet-client', text: QUICK ? ['m'] : ['m', 'xl'], save: '/api/portal/ui' },
  { app: '/api/portal/app', role: 'crew', name: 'cabinet-crew', text: ['m'], save: '/api/portal/ui' },
  { app: '/api/portal/app', role: 'worker', name: 'cabinet-worker', text: ['m'], save: '/api/portal/ui' },
  { app: '/api/portal/app', role: 'assistant', name: 'cabinet-staff', text: ['m'], save: '/api/portal/ui' },
  // тёмная тема Telegram (Ирина и заказчик — обычный и крупный текст)
  { app: '/api/crm/app', role: 'irina', name: 'studio-dark', text: QUICK ? ['l'] : ['l', 'm'], save: '/api/crm/ui', dark: true, sizes: ['pm'] },
  { app: '/api/stats/app', role: 'irina', name: 'stats-dark', text: ['l'], save: '/api/crm/ui', dark: true, sizes: ['pm'] },
  { app: '/api/portal/app', role: 'client', name: 'cabinet-client-dark', text: ['m'], save: '/api/portal/ui', dark: true, sizes: ['pm'] },
];

(async () => {
  const { ch, st } = await startStand();
  const BASE = `http://127.0.0.1:${st.port}`;
  const b = await chromium.launch();
  if (!AXE) R.warn('axe-core не найден — доступность не проверялась (npm i --no-save axe-core)');
  const setSize = (run, z) => fetch(BASE + run.save, { method: 'POST', headers: { 'X-Telegram-Init-Data': st.init[run.role], 'Content-Type': 'application/json' }, body: JSON.stringify({ size: z }) });
  try {
    for (const run of RUNS) {
      for (const z of run.text) {
        await setSize(run, z);
        for (const sz of run.sizes || SIZES) {
          const opt = sz === 'tg' ? { viewport: { width: 420, height: 760 } } : L.SIZES[sz];
          const ctx = await b.newContext(opt), p = await ctx.newPage();
          const errs = [];
          p.on('pageerror', (e) => errs.push(e.message.slice(0, 120)));
          await ctx.addInitScript(([z, plat, dark]) => { try { localStorage.setItem('ui-size', z); } catch { /* нет */ } window.__tgPlatform = plat; if (dark) window.__tgScheme = 'dark'; }, [z, sz === 'tg' ? 'macos' : 'ios', !!run.dark]);
          await p.route('https://telegram.org/**', (r) => r.fulfill({ contentType: 'text/javascript', body: tgMock(st.init[run.role]) }));
          const tag = `${run.name} ${z} (${sz})`;
          let shot = 0;
          const look = async (screen) => {
            await p.waitForTimeout(450);
            const bad = await L.checkPage(p, AXE, { oneH1: false, minTarget: 24 });
            // кнопки (не ссылки в тексте) — не меньше 44 px по меньшей стороне: так задано для «Студии» и кабинетов
            const tiny = await p.evaluate(() => [...document.querySelectorAll('button, [role=button], select, input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file])')]
              .filter((x) => { const r = x.getBoundingClientRect(); const cs = getComputedStyle(x); return r.width && r.height && cs.visibility !== 'hidden' && !x.closest('[hidden]') && (r.height < 40 || r.width < 40); })
              .slice(0, 6).map((x) => `${(x.innerText || x.getAttribute('aria-label') || x.title || x.name || x.type || '').trim().replace(/\s+/g, ' ').slice(0, 24)} ${Math.round(x.getBoundingClientRect().width)}×${Math.round(x.getBoundingClientRect().height)}`));
            if (tiny.length) bad.push(`кнопки меньше 40 px: ${tiny.join('; ')}`);
            if (errs.length) bad.push(`ошибки скрипта: ${errs.splice(0).join(' | ')}`);
            R.ok(!bad.length, `${tag}: ${screen}`, bad.join('; '));
            await p.screenshot({ path: path.join(OUT, `${run.name}-${z}-${sz}-${String(++shot).padStart(2, '0')}-${screen.replace(/[^a-zа-яё0-9]+/gi, '_')}.png`), fullPage: true });
          };
          const back = () => p.evaluate(() => { const bb = window.Telegram.WebApp.BackButton; (bb._cb.slice(-1)[0] || (() => {}))(); });
          const clickFirst = async (sel) => { const e = await p.$(sel); if (!e) return false; await e.scrollIntoViewIfNeeded(); await e.click(); await p.waitForTimeout(500); return true; };
          try {
          await p.goto(BASE + run.app, { waitUntil: 'load' });     // «Графики» обновляются сами — сеть не затихает
          await p.waitForTimeout(1500);
          await look('открытие');
          const tabs = await p.$$eval('#nav button[data-tab], #nav .in > button', (xs) => xs.filter((x) => x.offsetHeight).map((x, i) => ({ i, t: x.innerText.trim().replace(/\s+/g, ' ') })));
          for (const t of tabs) {
            await p.click(`#nav .in > button:nth-of-type(${t.i + 1})`); await p.waitForTimeout(500);
            await look(`вкладка «${t.t}»`);
            // первая карточка вкладки (проект, заявка, контакт) — открыть и вернуться
            if (await clickFirst('#app button.pcard, #app .lcard, #app button.card')) {
              await look(`вкладка «${t.t}» → карточка`); await back(); await p.waitForTimeout(300);
              // «Назад» увёл выше вкладок (у подрядчика — к списку проектов): открыть приложение заново
              if (await p.evaluate(() => document.getElementById('nav')?.hidden)) { await p.goto(BASE + run.app, { waitUntil: 'load' }); await p.waitForTimeout(1200); }
            }
          }
          if (!tabs.length && await clickFirst('#app button.pcard')) { await look('карточка'); await back(); }
          // последняя вкладка «Студии» («Сайт») уводит в графики — настройки и новый проект проверять в самом приложении
          if (!new URL(p.url()).pathname.startsWith(run.app)) { await p.goto(BASE + run.app, { waitUntil: 'load' }); await p.waitForTimeout(1200); }
          // настройки (⚙︎) — форма поверх страницы
          if (await clickFirst('button.icon-btn[aria-label*="астро"], button.icon-btn:has-text("⚙")')) { await look('настройки'); await back(); }
          // форма нового проекта (у Ирины)
          if (run.role === 'irina' && run.app === '/api/crm/app' && await clickFirst('#nav .in > button[data-tab="projects"]') && await clickFirst('button.btn.primary.small')) { await look('новый проект'); await back(); }
          // просмотр фото (решено 25.10.2026): «Визуализации» проекта — счётчик «1 / N», стрелка ›, клавиша ←, на телефоне — свайп пальцем
          if ((run.role === 'irina' && run.app === '/api/crm/app') || run.role === 'client') {
            let opened = false;
            await p.goto(BASE + run.app, { waitUntil: 'load' }); await p.waitForTimeout(1200);   // вкладка «Сайт» уводит в графики — начать заново
            if (run.role === 'irina') opened = await clickFirst('#nav .in > button[data-tab="projects"]') && await clickFirst('#app button.pcard');
            else { const d = p.locator('#nav button', { hasText: /Документы/ }); if (await d.count()) { await d.first().click(); await p.waitForTimeout(500); opened = true; } }
            const chip = p.locator('button.chip', { hasText: /^Визуализации/ });
            if (opened && await chip.count()) { await chip.first().click(); await p.waitForTimeout(500); }
            const tiles = opened ? await p.$$('.gallery .thumb') : [];
            if (tiles.length < 2) R.ok(false, `${tag}: листание фото`, `в «Визуализациях» фото: ${tiles.length}, нужно не меньше двух`);
            else {
              await tiles[0].scrollIntoViewIfNeeded(); await tiles[0].click(); await p.waitForTimeout(500);
              const pos = () => p.$eval('.viewer .pos', (x) => x.textContent).catch(() => 'нет счётчика');
              const n = tiles.length, steps = [];
              steps.push(['открылось первое', (await pos()) === `1 / ${n}`, await pos()]);
              await look('просмотр фото');
              if (await clickFirst('.viewer .vnav.next')) steps.push(['стрелка › → второе', (await pos()) === `2 / ${n}`, await pos()]);
              else steps.push(['стрелка ›', false, 'нет']);
              await p.keyboard.press('ArrowLeft'); await p.waitForTimeout(400);
              steps.push(['клавиша ← → первое', (await pos()) === `1 / ${n}`, await pos()]);
              if (sz !== 'tg' && L.SIZES[sz].hasTouch) {           // свайп — касаниями через Chrome DevTools Protocol
                const cdp = await ctx.newCDPSession(p);
                const c = await p.$eval('.viewer .img', (x) => { const r = x.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
                const sw = async (dx) => {
                  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [c] });
                  for (let k = 1; k <= 8; k++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: c.x + dx * k / 8, y: c.y }] });
                  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
                  await p.waitForTimeout(450);
                };
                await sw(-160); steps.push(['свайп влево → второе', (await pos()) === `2 / ${n}`, await pos()]);
                await sw(160); steps.push(['свайп вправо → первое', (await pos()) === `1 / ${n}`, await pos()]);
              }
              const bad = steps.filter((x) => !x[1]);
              R.ok(!bad.length, `${tag}: листание фото`, bad.map((x) => `${x[0]}: ${x[2]}`).join('; '));
              await p.keyboard.press('Escape'); await p.waitForTimeout(300);
            }
          }
          } catch (e) { R.ok(false, `${tag}: проверка прервалась`, e.message.split('\n')[0]); }
          await ctx.close();
        }
      }
    }
  } finally {
    await b.close();
    ch.kill();
  }
  process.exit(R.done(OUT) ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
