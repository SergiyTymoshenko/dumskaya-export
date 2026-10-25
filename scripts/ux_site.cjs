// Проверка UI/UX сайта студии dumskaya-design.com — правило: после любых изменений вёрстки сайта, до выкладки.
// Запуск:  node scripts/ux_site.cjs                  — по собранному dist/ (без фото: на Маке их нет в git, будут заглушки)
//          node scripts/ux_site.cjs --base https://dumskaya-design.com   — живой сайт с фото (аналитика не включается:
//          в браузере проверки выбран отказ от cookie; браузер без окна — журнал сайта считает его роботом).
// Что проверяет (scripts/ux_lib.cjs): страницы всех шаблонов (главная на 5 языках, услуги, цены, пакет, проект, портфолио,
// кухня, статья, магазин и товар, контакты, о студии, 404) на компьютере, телефоне и iPhone Pro Max — прокрутка вбок,
// доступность (axe), зоны нажатия ≥ 24 px, один H1, alt, сдвиг вёрстки; меню, окно cookie, форма заявки, просмотр фото.
const path = require('path');
const L = require('./ux_lib.cjs');

const { chromium } = L.playwright();
const AXE = L.axeSource();
const OUT = L.outDir('dumskaya-ux-site');
const PORT = Number(L.arg('--port', 8096));
const LIVE = L.arg('--base', '');
const BASE = LIVE ? LIVE.replace(/\/$/, '') : `http://127.0.0.1:${PORT}`;
const R = L.report();
const ONLY = L.arg('--only', '');      // --only home,project — только эти страницы

// одна страница каждого шаблона; языковые версии — по hreflang самой страницы
const PAGES = [
  ['home', '/', ['ua', 'en', 'sk', 'de']], ['service', '/interior-design-apartments-bratislava', ['en', 'de']], ['region', '/dizajn-interera-vena', ['de']],
  ['price', '/price-interior-design-bratislava-wien-praha', ['sk']], ['package', '/premium-interior-design-package-bratislava-vienna', []],
  ['portfolio', '/proekty-interior-design', []], ['project', '/interior-design-apartment-bratislava-127m', ['en']],
  ['kitchens', '/kuhni-na-zakaz-bratislava', []], ['kitchen', '/kuhni-pod-zakaz-k-01-cena-bratislava-slovakia', []],
  ['article', '/kak-pravilno-organizovat-udobnuyu-i-funkcionalnuyu-kuhnyu', []], ['shop', '/shop', []], ['shop-item', '/shop/executive-desk-boss-l', []],
  ['contact', '/contact-studio-interior-design-bratislava-vienna', ['en', 'de']], ['about', '/about-studio', []], ['privacy', '/privacy', []], ['404', '/no-such-page-ux', []],
].filter(([n]) => !ONLY || ONLY.split(',').includes(n));

const newCtx = async (b, sz, consent = 'denied') => {
  const ctx = await b.newContext(L.SIZES[sz]);
  if (consent) await ctx.addInitScript((v) => { try { localStorage.setItem('dd-consent', v); } catch { /* приватный режим */ } }, consent);
  return ctx;
};

(async () => {
  const srv = LIVE ? null : await L.staticServer([path.join(L.ROOT, 'dist'), path.join(L.ROOT, 'public')], PORT);
  const b = await chromium.launch();
  if (!AXE) R.warn('axe-core не найден — доступность не проверялась (npm i --no-save axe-core)');
  try {
    // 1. страницы
    for (const [name, url, alts] of PAGES) {
      let urls = [[name, url]];
      if (alts.length) {
        const ctx = await newCtx(b, 'd'), p = await ctx.newPage();
        await p.goto(BASE + url, { waitUntil: 'domcontentloaded' });
        const map = await p.evaluate(() => Object.fromEntries([...document.querySelectorAll('link[rel=alternate][hreflang]')].map((l) => [l.hreflang, new URL(l.href).pathname])));
        const code = { ua: 'uk', en: 'en', sk: 'sk', de: 'de' };
        for (const a of alts) { const u = map[code[a]] || map[a]; if (u) urls.push([`${name}-${a}`, u]); else R.ok(false, `${name}: нет версии ${a}`); }
        await ctx.close();
      }
      for (const [n, u] of urls) {
        for (const sz of ['d', 'm', 'pm']) {
          const ctx = await newCtx(b, sz), p = await ctx.newPage();
          await L.watchCls(p);
          const resp = await p.goto(BASE + u, { waitUntil: 'networkidle', timeout: 60000 });
          const bad = await L.checkPage(p, AXE, { skip: '#menu', status: resp.status(), expect: n === '404' ? 404 : 200 });
          R.ok(!bad.length, `${n} (${sz}) ${u}`, bad.join('; '));
          await L.scrollThrough(p);
          await p.screenshot({ path: path.join(OUT, `${n}-${sz}.png`), fullPage: true });
          await ctx.close();
        }
      }
    }

    // 2. окно cookie — первый визит (выбор не сделан); на живом сайте нажимаем только «Отказаться»
    for (const sz of ['d', 'pm']) {
      const ctx = await newCtx(b, sz, null), p = await ctx.newPage();
      await p.goto(BASE + '/', { waitUntil: 'networkidle' });
      const c = await p.evaluate(() => {
        const box = document.querySelector('[data-cookie]');
        if (!box || box.hidden) return null;
        const r = box.getBoundingClientRect();
        const btns = [...box.querySelectorAll('button')].map((x) => Math.round(x.getBoundingClientRect().height));
        const cta = [...document.querySelectorAll('main .btn, .hero .btn')].find((x) => { const q = x.getBoundingClientRect(); return q.height && q.top < innerHeight; });
        const cr = cta?.getBoundingClientRect();
        const over = !!cr && cr.bottom > r.top && cr.top < r.bottom && cr.right > r.left && cr.left < r.right;
        return { share: r.height / innerHeight, btns, covers: over };
      });
      R.ok(!!c, `cookie (${sz}): окно показывается при первом визите`);
      if (c) {
        R.ok(c.share < (sz === 'd' ? 0.25 : 0.3), `cookie (${sz}): окно не закрывает больше ${sz === 'd' ? '25' : '30'} % экрана`, `${Math.round(c.share * 100)} %`);
        R.ok(c.btns.every((h) => h >= 44), `cookie (${sz}): кнопки не ниже 44 px`, c.btns.join(', '));
        R.ok(!c.covers, `cookie (${sz}): не закрывает главную кнопку на первом экране`);
        await p.screenshot({ path: path.join(OUT, `cookie-${sz}.png`) });
        await p.click('[data-cookie] [data-choice="denied"]');
        await p.reload({ waitUntil: 'networkidle' });
        R.ok(await p.evaluate(() => document.querySelector('[data-cookie]').hidden), `cookie (${sz}): после выбора больше не показывается`);
      }
      await ctx.close();
    }

    // 3. меню
    for (const sz of ['d', 'pm']) {
      const ctx = await newCtx(b, sz), p = await ctx.newPage();
      await p.goto(BASE + '/', { waitUntil: 'networkidle' });
      await p.click('header [data-menu-open]'); await p.waitForTimeout(300);
      const m = await p.evaluate(() => {
        const menu = document.getElementById('menu');
        const items = [...menu.querySelectorAll('a')].filter((a) => a.offsetHeight);
        const bottom = Math.max(...[...menu.querySelectorAll('.menu__main, .menu__groups')].map((x) => x.getBoundingClientRect().bottom));
        return { open: !menu.hidden, focus: menu.contains(document.activeElement), n: items.length, h: menu.scrollHeight, bottom: Math.round(bottom), vh: innerHeight };
      });
      R.ok(m.open && m.focus, `меню (${sz}): открывается, фокус внутри`);
      const bad = await L.checkPage(p, AXE, { oneH1: false });
      R.ok(!bad.length, `меню (${sz}): доступность и зоны нажатия`, bad.join('; '));
      if (sz === 'd') R.ok(m.bottom <= m.vh, 'меню (компьютер): все пункты на первом экране', `низ ${m.bottom} из ${m.vh}`);
      else {
        R.ok(m.h <= m.vh * 1.3, 'меню (телефон): разделы свёрнуты — меню на одном экране', `${m.h} px из ${m.vh}`);
        const lists = () => p.evaluate(() => [...document.querySelectorAll('#menu .menu__sec > ul')].filter((u) => u.offsetHeight > 0).length);
        const before = await lists();
        if (await p.$('#menu .menu__tog')) {
          await p.click('#menu .menu__tog'); await p.waitForTimeout(150);
          R.ok((await lists()) === before + 1, 'меню (телефон): нажатие раскрывает раздел');
          await p.screenshot({ path: path.join(OUT, `menu-${sz}-open.png`), fullPage: false });
          await p.click('#menu .menu__tog'); await p.waitForTimeout(150);
        } else R.ok(false, 'меню (телефон): разделы не сворачиваются');
      }
      await p.screenshot({ path: path.join(OUT, `menu-${sz}.png`), fullPage: false });
      await p.keyboard.press('Escape'); await p.waitForTimeout(150);
      R.ok(await p.evaluate(() => document.getElementById('menu').hidden && document.activeElement?.matches('[data-menu-open]')), `меню (${sz}): Esc закрывает, фокус — на кнопку меню`);
      await ctx.close();
    }

    // 4. форма заявки: пустая не отправляется, поля подписаны, ошибка видна
    {
      const ctx = await newCtx(b, 'pm'), p = await ctx.newPage();
      await p.goto(BASE + '/contact-studio-interior-design-bratislava-vienna', { waitUntil: 'networkidle' });
      const f = await p.evaluate(() => {
        const form = document.querySelector('form[data-lead]');
        if (!form) return null;
        const fields = [...form.querySelectorAll('input:not([type=hidden]), textarea, select')].filter((x) => !x.closest('[aria-hidden="true"]'));
        const named = fields.filter((x) => x.labels?.length || x.getAttribute('aria-label'));
        return { n: fields.length, named: named.length, req: fields.filter((x) => x.required).length, auto: fields.filter((x) => x.autocomplete && x.autocomplete !== 'off').length };
      });
      R.ok(!!f, 'форма: есть на странице «Контакты»');
      if (f) {
        R.ok(f.named === f.n, 'форма: у каждого поля есть подпись', `${f.named} из ${f.n}`);
        R.ok(f.auto >= Math.min(2, f.n), 'форма: автозаполнение имени и контакта', `${f.auto}`);
        let posted = false;
        p.on('request', (r) => { if (r.url().includes('/api/lead')) posted = true; });
        await p.click('form[data-lead] [data-send]'); await p.waitForTimeout(300);
        const inv = await p.evaluate(() => [...document.querySelectorAll('form[data-lead] :invalid')].length);
        R.ok(!posted && inv > 0, 'форма: пустая не отправляется, незаполненные поля отмечены', `пустых обязательных ${inv}`);
        await p.screenshot({ path: path.join(OUT, 'form-empty-pm.png') });
      }
      await ctx.close();
    }

    // 5. просмотр фото на странице проекта
    for (const sz of ['d', 'pm']) {
      const ctx = await newCtx(b, sz), p = await ctx.newPage();
      await p.goto(BASE + '/interior-design-apartment-bratislava-127m', { waitUntil: 'networkidle' });
      const z = await p.$('[data-zoom]:has(img)');
      if (!z) { R.warn(`фото (${sz}): на странице проекта нет фото для просмотра (сборка без фото)`); await ctx.close(); continue; }
      await z.scrollIntoViewIfNeeded(); await z.click(); await p.waitForTimeout(400);
      const s0 = await p.evaluate(() => { const lb = document.querySelector('[data-lb]'); return { open: !!lb && (lb.tagName === 'DIALOG' ? lb.open : !lb.hidden), n: lb?.querySelector('[data-lb-count]')?.textContent || '', focus: !!lb && lb.contains(document.activeElement) }; });
      R.ok(s0.open, `фото (${sz}): открывается крупно`, s0.n);
      R.ok(s0.focus, `фото (${sz}): фокус в окне просмотра`);
      const bad = await L.checkPage(p, AXE, { oneH1: false, skip: '#menu' });
      R.ok(!bad.length, `фото (${sz}): доступность и кнопки окна просмотра`, bad.join('; '));
      if (sz === 'pm') {
        await p.evaluate(() => {
          const lb = document.querySelector('[data-lb]'), t = (x) => new Touch({ identifier: 1, target: lb, clientX: x, clientY: 400 });
          lb.dispatchEvent(new TouchEvent('touchstart', { touches: [t(330)], changedTouches: [t(330)], bubbles: true }));
          lb.dispatchEvent(new TouchEvent('touchmove', { touches: [t(200)], changedTouches: [t(200)], bubbles: true }));
          lb.dispatchEvent(new TouchEvent('touchend', { touches: [], changedTouches: [t(100)], bubbles: true }));
        });
        await p.waitForTimeout(300);
        const n1 = await p.evaluate(() => document.querySelector('[data-lb] [data-lb-count]')?.textContent || '');
        R.ok(n1 !== s0.n, 'фото (телефон): листается пальцем', `${s0.n} → ${n1}`);
      }
      await p.screenshot({ path: path.join(OUT, `lightbox-${sz}.png`) });
      await p.keyboard.press('Escape'); await p.waitForTimeout(200);
      R.ok(await p.evaluate(() => { const lb = document.querySelector('[data-lb]'); return lb.tagName === 'DIALOG' ? !lb.open : lb.hidden; }), `фото (${sz}): Esc закрывает`);
      await ctx.close();
    }
  } finally {
    await b.close();
    srv?.close();
  }
  process.exit(R.done(OUT) ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
