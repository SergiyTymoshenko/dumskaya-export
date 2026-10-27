// Проверка UI/UX мини-приложений бота — «Студия» (crm_app.html), «Графики» (stats_app.html), «Сервер и ИИ» (server_app.html)
// и кабинет «Мой проект» (portal_app.html) — правило: после любых изменений этих страниц, до выкладки.
// Запуск:  node scripts/ux_apps.cjs   (нужны Python 3, Playwright с Chromium и axe-core; данные — тестовые, scripts/tests/ux_stand.py:
// сервис на временных базах, Telegram подменён — ничего никуда не уходит).
// Каждый экран (вкладки, проект, заявка, формы, настройки) — на iPhone Pro Max (440), телефоне (390) и в окне Telegram
// на компьютере (420, мышь), с обычным, крупным и очень крупным текстом: прокрутка вбок, контраст и прочее из axe (без правил для экранного диктора), зоны нажатия
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
const GSC_FIXTURE = require('fs').readFileSync(require('path').join(__dirname, 'tests', 'gsc_fixture.json'), 'utf8');

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

// экранный диктор в мини-приложениях не нужен (решено 25.10.2026): правила axe только для него не проверяются;
// контраст, размер кнопок, прокрутка вбок, ошибки скриптов — проверяются, как раньше
const SR_ONLY = ['region', 'landmark-one-main', 'landmark-unique', 'aria-dialog-name', 'label', 'select-name', 'button-name',
  'link-name', 'image-alt', 'heading-order', 'empty-heading', 'page-has-heading-one', 'aria-allowed-role'];
const SIZES = QUICK ? ['pm'] : ['pm', 'm', 'tg'];
// роль → приложение, размеры текста (по умолчанию у всех «Обычный» — решено 25.10.2026; крупные проверяются тоже)
const RUNS = [
  { app: '/api/crm/app', role: 'irina', name: 'studio', text: QUICK ? ['m'] : ['m', 'l', 'xl'], save: '/api/crm/ui' },
  { app: '/api/crm/app', role: 'owner', name: 'studio-owner', text: ['m'], save: '/api/crm/ui' },
  // разработчик: проекты только для просмотра (решено 25.10.2026) — ни одной кнопки, которая что-то меняет
  { app: '/api/crm/app?tab=projects', role: 'owner', name: 'studio-owner-projects', text: ['m', 'xl'], save: '/api/crm/ui' },
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
          // карточка «Google: поиск и индекс» — на образце данных (на стенде нет ключа Search Console)
          await p.route('**/api/stats/gsc**', (r) => r.fulfill({ contentType: 'application/json', body: GSC_FIXTURE }));
          const tag = `${run.name} ${z} (${sz})`;
          let shot = 0;
          const look = async (screen) => {
            await p.waitForTimeout(450);
            const bad = await L.checkPage(p, AXE, { oneH1: false, minTarget: 24, axeOff: SR_ONLY });
            // кнопки (не ссылки в тексте) — не меньше 44 px по меньшей стороне: так задано для «Студии» и кабинетов
            const tiny = await p.evaluate(() => [...document.querySelectorAll('button, [role=button], select, input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file])')]
              .filter((x) => { const r = x.getBoundingClientRect(); const cs = getComputedStyle(x); return r.width && r.height && cs.visibility !== 'hidden' && !x.closest('[hidden]') && (r.height < 40 || r.width < 40); })
              .slice(0, 6).map((x) => `${(x.innerText || x.getAttribute('aria-label') || x.title || x.name || x.type || '').trim().replace(/\s+/g, ' ').slice(0, 24)} ${Math.round(x.getBoundingClientRect().width)}×${Math.round(x.getBoundingClientRect().height)}`));
            if (tiny.length) bad.push(`кнопки меньше 40 px: ${tiny.join('; ')}`);
            // «null» / «undefined» на экране — пустое значение попало в страницу текстом (так было у разработчика в проекте)
            const junk = await p.evaluate(() => (document.body.innerText.match(/(^|[\s·(«])(null|undefined|NaN)(?=$|[\s·)»,.])/m) || [])[2] || '');
            if (junk) bad.push(`на экране текст «${junk}»`);
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
          if (new URL(p.url()).pathname !== run.app.split('?')[0]) { await p.goto(BASE + run.app, { waitUntil: 'load' }); await p.waitForTimeout(1200); }
          // настройки (⚙︎) — форма поверх страницы
          if (await clickFirst('button.icon-btn[aria-label*="астро"], button.icon-btn:has-text("⚙")')) { await look('настройки'); await back(); }
          // форма нового проекта (у Ирины)
          if (run.role === 'irina' && run.app === '/api/crm/app' && await clickFirst('#nav .in > button[data-tab="projects"]') && await clickFirst('button.btn.primary.small')) { await look('новый проект'); await back(); }
          // просмотр фото (решено 25.10.2026): «Визуализации» проекта — счётчик «1 / N», стрелка ›, клавиша ←, на телефоне — свайп пальцем
          const studio = run.app.startsWith('/api/crm/app') && (run.role === 'irina' || run.app.includes('tab=projects'));
          if (studio || run.role === 'client') {
            let opened = false;
            await p.goto(BASE + run.app, { waitUntil: 'load' }); await p.waitForTimeout(1200);   // вкладка «Сайт» уводит в графики — начать заново
            if (studio) opened = await clickFirst('#nav .in > button[data-tab="projects"]') && await clickFirst('#app button.pcard');
            else { const d = p.locator('#nav button', { hasText: /Документы/ }); if (await d.count()) { await d.first().click(); await p.waitForTimeout(500); opened = true; } }
            const chip = p.locator('button.chip', { hasText: /^Визуализации/ });
            if (opened && await chip.count()) { await chip.first().click(); await p.waitForTimeout(500); }
            let tiles = opened ? await p.$$('.gallery .thumb') : [];
            // согласование — у каждого фото (решено 25.10.2026): у Ирины под фото галочка, отмеченное — с зелёной галочкой на фото
            if (run.role === 'irina' && tiles.length) {
              const boxes = await p.$$('.gallery .gcell .agree input[type=checkbox]');
              const before = (await p.$$('.gallery .okmark')).length;
              if (boxes.length < tiles.length) R.ok(false, `${tag}: галочки «согласовано» под фото`, `${boxes.length} из ${tiles.length}`);
              else {
                await boxes[0].click(); await p.waitForTimeout(700);
                const after = (await p.$$('.gallery .okmark')).length;
                await look('визуализации — фото согласовано');
                const again = await p.$$('.gallery .gcell .agree input[type=checkbox]');
                if (again[0]) { await again[0].click(); await p.waitForTimeout(700); }
                const back = (await p.$$('.gallery .okmark')).length;
                R.ok(after === before + 1 && back === before, `${tag}: галочка «согласовано» под фото`, `зелёных галочек: ${before} → ${after} → ${back}`);
              }
              tiles = await p.$$('.gallery .thumb');
              // порядок файлов (решено 27.10.2026): «⇅ Порядок» → под фото ‹ ›; › у первого — оно становится вторым; ‹ — обратно
              const ord = p.locator('#sec-files button.chip', { hasText: /Порядок/ });
              if (!(await ord.count())) R.ok(false, `${tag}: порядок файлов`, 'нет кнопки «⇅ Порядок»');
              else {
                const firstSrc = () => p.$eval('#sec-files .gallery .thumb img', (x) => x.getAttribute('src')).catch(() => '');
                await ord.first().click(); await p.waitForTimeout(400);
                const s0 = await firstSrc(), bars = (await p.$$('#sec-files .gallery .ordbar')).length;
                await look('визуализации — порядок');
                await clickFirst('#sec-files .gallery .ordbar .ordbtn[title="Позже"]:not([disabled])'); await p.waitForTimeout(900);
                const s1 = await firstSrc();
                const sec = await p.$eval('#sec-files .gallery .gcell:nth-child(2) .thumb img', (x) => x.getAttribute('src')).catch(() => '');
                await clickFirst('#sec-files .gallery .gcell:nth-child(2) .ordbar .ordbtn[title="Раньше"]'); await p.waitForTimeout(900);
                const s2 = await firstSrc();
                await p.locator('#sec-files button.chip', { hasText: /Готово/ }).first().click(); await p.waitForTimeout(400);
                R.ok(bars >= 2 && s1 !== s0 && sec === s0 && s2 === s0 && !(await p.$('#sec-files .ordbar')), `${tag}: порядок файлов (‹ › под фото)`,
                  `кнопок у фото: ${bars}; первое фото после ›: ${s1 === s0 ? 'не сдвинулось' : 'сдвинулось'}, после ‹: ${s2 === s0 ? 'вернулось' : 'нет'}`);
              }
              tiles = await p.$$('.gallery .thumb');     // после «Порядка» плитки нарисованы заново
            }
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
              // имя файла не показываем; у Ирины раздел, вариант и кто видит — в свёрнутой панели «Настроить», у разработчика её нет
              const names = await p.$$eval('.viewer .vtop, .viewer .vbar', (xs) => xs.map((x) => x.innerText).join(' '));
              steps.push(['без имени файла', !/\.(png|jpe?g|webp|heic|pdf)\b/i.test(names), names.slice(0, 80)]);
              const set = await p.$('.viewer .vbar button[aria-controls]');
              if (run.role === 'irina') {
                if (set) { await set.click(); await p.waitForTimeout(300); await look('просмотр фото — «Настроить»');
                  steps.push(['«Настроить»: раздел и кто видит', (await p.$$('.viewer .vpanel:not([hidden]) select')).length >= 2, String((await p.$$('.viewer .vpanel select')).length)]);
                  await set.click(); await p.waitForTimeout(200); }
                else steps.push(['кнопка «Настроить»', false, 'нет']);
              } else if (run.role === 'owner') steps.push(['разработчик: нечего менять в просмотре', !set && !(await p.$('.viewer .vpanel')), set ? 'есть «Настроить»' : 'есть панель']);
              const bad = steps.filter((x) => !x[1]);
              R.ok(!bad.length, `${tag}: листание фото`, bad.map((x) => `${x[0]}: ${x[2]}`).join('; '));
              await p.keyboard.press('Escape'); await p.waitForTimeout(300);
              if (run.role === 'owner') {                    // проект у разработчика: только просмотр — кнопок изменений нет
                const rw = await p.$$eval('#app button', (xs) => xs.map((x) => x.innerText.trim()).filter((t) => /＋|Изменить|Удалить|Ссылка в бот|Написать|Оплата|Бонус|Завершить|Убрать|Закрыть кабинет|Отметить|Порядок/.test(t)));
                R.ok(!rw.length, `${tag}: проект — только просмотр`, rw.slice(0, 6).join('; '));
              }
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
