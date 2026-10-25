// Проверка UI/UX каталога DUMSKAYA HOME по собранному сайту (home/dist) — правило: после любых изменений вёрстки
// каталога, до выкладки. Запуск:  node scripts/ux_home.cjs   (нужны Playwright с Chromium и axe-core:
// npm i --no-save playwright axe-core && npx playwright install chromium — на Маке не обязательно, проверяет Claude).
// Что проверяет:
//  • каждая страница — на компьютере (1440), телефоне (390) и iPhone Pro Max (440): ответ 200, нет прокрутки вбок,
//    доступность (axe: WCAG 2 A/AA и рекомендации) — 0 нарушений, нажимаемые зоны не меньше 24 px (кроме ссылок в тексте),
//    один H1, у всех фото есть alt, сдвиг вёрстки < 0,1;
//  • раздел: видно 24 товара и «Показать ещё», в первом ряду разные фабрики, число товаров меняется вместе с фильтром,
//    фильтры в адресе, «назад» с товара возвращает столько же показанных, пустой результат — сообщение и сброс;
//  • главная: одиночная последняя плитка — на всю ширину, у плиток разные фото, новинки разных фабрик;
//  • меню: на телефоне разделы свёрнуты (открыт раздел текущей страницы) и раскрываются, на компьютере — всё на первом экране;
//  • галерея товара: счётчик, листание пальцем; форма: необязательные поля подписаны.
// Скриншоты — в папку из --out (по умолчанию — временная папка), их тоже смотреть глазами.
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const DIST = path.resolve(arg('--dist', path.join(ROOT, 'home/dist')));
const IMG = path.join(ROOT, 'home/img');
const OUT = path.resolve(arg('--out', path.join(os.tmpdir(), 'dumskaya-ux-home')));
const PORT = Number(arg('--port', 8097));
const BASE = `http://127.0.0.1:${PORT}`;

let chromium;
try { ({ chromium } = require('playwright')); } catch {
  console.log('Нет Playwright. Установить: npm i --no-save playwright axe-core && npx playwright install chromium');
  process.exit(2);
}
let AXE = '';
try { AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'); } catch {
  try { AXE = fs.readFileSync(process.env.UX_AXE || '', 'utf8'); } catch { /* ниже — предупреждение */ }
}
if (!fs.existsSync(path.join(DIST, 'index.html'))) { console.log(`Нет сборки каталога: ${DIST}. Сначала: npx astro build --root home`); process.exit(2); }
fs.mkdirSync(OUT, { recursive: true });

// просмотр сборки как на сервере: /адрес → адрес.html, фото — из home/img, /api/* — заглушка
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.xml': 'application/xml', '.txt': 'text/plain', '.ico': 'image/x-icon' };
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split('?')[0]);
  if (u.startsWith('/api/')) { res.writeHead(200, { 'content-type': 'application/json' }); return res.end('{"ok":true}'); }
  let f = path.join(DIST, u === '/' ? 'index.html' : u);
  if (u.startsWith('/img/') && !fs.existsSync(f)) f = path.join(IMG, u.slice(5));
  if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) f += '.html';
  if (!f.startsWith(DIST) && !f.startsWith(IMG)) { res.writeHead(403); return res.end(); }
  if (!fs.existsSync(f)) { res.writeHead(404, { 'content-type': TYPES['.html'] }); return res.end(fs.readFileSync(path.join(DIST, '404.html'))); }
  res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});

const lines = [];
let fails = 0;
const ok = (c, what, extra = '') => { if (!c) fails++; lines.push(`${c ? '✓' : '✗'} ${what}${extra ? ' — ' + extra : ''}`); };
const SIZES = { d: { viewport: { width: 1440, height: 900 } }, m: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  pm: { viewport: { width: 440, height: 956 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true } };

(async () => {
  await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
  const b = await chromium.launch();
  try {
    // адреса страниц — из меню собранного сайта, а не вписаны руками (каталог меняется)
    let ctx = await b.newContext(SIZES.d), p = await ctx.newPage();
    await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    const nav = await p.evaluate(() => {
      const href = (s) => document.querySelector(s)?.getAttribute('href') || '';
      return { dept: href('.menu__sec h2 a'), cat: href('.menu__sec ul a'), brands: document.getElementById('m-brands') ? document.getElementById('m-brands').closest('.menu__sec').querySelector('h2 a').getAttribute('href') : '',
        brand: href('#m-brands a'), contact: href('.menu__sec--gap h2 a'), ru: href('.hdr__langs a[hreflang="ru"]') };
    });
    await p.goto(BASE + nav.ru, { waitUntil: 'domcontentloaded' });
    const ruContact = await p.evaluate(() => document.querySelector('.menu__sec--gap h2 a')?.getAttribute('href') || '');
    await p.goto(BASE + nav.cat, { waitUntil: 'domcontentloaded' });
    const catInfo = await p.evaluate(() => {
      const cards = [...document.querySelectorAll('[data-grid] .pc')];
      const withPhoto = cards.find((c) => c.querySelector('img'));
      return { brand: document.querySelectorAll('[data-brand]')[1]?.getAttribute('data-brand') || '', product: (withPhoto || cards[0])?.getAttribute('href') || '' };
    });
    await p.goto(BASE + catInfo.product, { waitUntil: 'domcontentloaded' });
    const ruProduct = await p.evaluate(() => document.querySelector('.hdr__langs a[hreflang="ru"]')?.getAttribute('href') || '');
    await ctx.close();
    const pages = [['home', '/'], ['ru-home', nav.ru], ['dept', nav.dept], ['cat', nav.cat], ['cat-brand', `${nav.cat}?brand=${catInfo.brand}`],
      ['brand', nav.brand], ['brands', nav.brands], ['product', catInfo.product], ['ru-product', ruProduct], ['contact', nav.contact], ['ru-contact', ruContact], ['404', '/no-such-page']];
    if (!AXE) lines.push('⚠ axe-core не найден — доступность не проверялась (npm i --no-save axe-core)');

    // 1. каждая страница на трёх экранах
    for (const [name, url] of pages) {
      if (!url) { ok(false, `${name}: не нашёлся адрес в меню`); continue; }
      for (const [sz, opt] of Object.entries(SIZES)) {
        ctx = await b.newContext(opt); p = await ctx.newPage();
        await p.addInitScript(() => {
          window.__cls = 0;
          new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: 'layout-shift', buffered: true });
        });
        const resp = await p.goto(BASE + url, { waitUntil: 'networkidle' });
        await p.waitForTimeout(250);
        const m = await p.evaluate(() => {
          const vw = document.documentElement.clientWidth;
          const small = [];
          for (const a of document.querySelectorAll('a[href], button, input, select, textarea, summary, [role=button]')) {
            const r = a.getBoundingClientRect(), cs = getComputedStyle(a);
            if (!r.width || !r.height || cs.visibility === 'hidden' || a.closest('[hidden], .lead__hp, .menu')) continue;
            if (a.closest('p, li > p, address') && !a.matches('.btn, button')) continue;      // ссылки в тексте — исключение WCAG 2.5.8
            const lab = a.closest('label'); if (lab && lab.getBoundingClientRect().height >= 24) continue;  // галочка с подписью — нажимается вся подпись
            if (r.width < 24 || r.height < 24) small.push(`${a.tagName.toLowerCase()}「${(a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 30)}」${Math.round(r.width)}×${Math.round(r.height)}`);
          }
          return { overflow: document.documentElement.scrollWidth > vw + 1, small, h1: document.querySelectorAll('h1').length,
            noAlt: [...document.images].filter((i) => !i.hasAttribute('alt')).length, cls: window.__cls };
        });
        let axe = [];
        if (AXE) {
          await p.addScriptTag({ content: AXE });
          axe = await p.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'], runOnly: ['wcag2a', 'wcag2aa', 'best-practice'] }))
            .violations.map((v) => `${v.id} ×${v.nodes.length}: ${v.nodes[0].target.join(' ')}`));
        }
        const bad = [];
        if (resp.status() !== (name === '404' ? 404 : 200)) bad.push(`ответ ${resp.status()}`);
        if (m.overflow) bad.push('прокрутка вбок');
        if (m.small.length) bad.push(`мелкие зоны: ${m.small.slice(0, 3).join('; ')}`);
        if (m.h1 !== 1) bad.push(`H1: ${m.h1}`);
        if (m.noAlt) bad.push(`фото без alt: ${m.noAlt}`);
        if (m.cls >= 0.1) bad.push(`сдвиг вёрстки ${m.cls.toFixed(2)}`);
        if (axe.length) bad.push(`доступность: ${axe.slice(0, 3).join(' | ')}`);
        ok(!bad.length, `${name} (${sz}) ${url}`, bad.join('; '));
        await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 800) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 40)); } window.scrollTo(0, 0); });
        await p.waitForTimeout(250);
        await p.screenshot({ path: path.join(OUT, `${name}-${sz}.png`), fullPage: true });
        await ctx.close();
      }
    }

    // 2. раздел
    ctx = await b.newContext(SIZES.d); p = await ctx.newPage();
    await p.goto(BASE + nav.cat, { waitUntil: 'networkidle' });
    const st = () => p.evaluate(() => {
      const vis = [...document.querySelectorAll('[data-grid] .pc')].filter((c) => !c.hidden);
      return { count: document.querySelector('[data-count]')?.textContent || '', vis: vis.length, total: document.querySelectorAll('[data-grid] .pc').length,
        more: !document.querySelector('[data-more-box]')?.hidden, empty: !document.querySelector('[data-empty]')?.hidden, url: location.search,
        brands: new Set([...document.querySelectorAll('[data-brand]')].map((c) => c.dataset.brand).filter(Boolean)).size,
        row: vis.slice(0, 4).map((c) => c.dataset.brand) };
    });
    let s = await st();
    const num = (t) => Number((t.match(/\d+/) || [0])[0]);
    ok(s.total <= 24 ? s.vis === s.total : s.vis === 24 && s.more, 'раздел: сначала 24 товара и «Показать ещё»', `${s.count}, видно ${s.vis}`);
    ok(num(s.count) === s.total, 'раздел: число в заголовке = товаров в разделе', `${s.count} / ${s.total}`);
    ok(new Set(s.row).size >= Math.min(4, s.brands), 'раздел: в первом ряду разные фабрики', s.row.join(', '));
    if (s.more) { await p.click('[data-more]'); s = await st(); ok(s.vis > 24, '«Показать ещё» добавляет товары', `видно ${s.vis}`); }
    if (catInfo.brand) {
      await p.click(`[data-brand="${catInfo.brand}"]`); s = await st();
      ok(num(s.count) === s.vis || (s.more && num(s.count) > s.vis), 'фильтр: число = видимым товарам', `${s.count}, видно ${s.vis}`);
      ok(s.url.includes(`brand=${catInfo.brand}`), 'фильтр по фабрике — в адресе', s.url);
    }
    const out = await p.$('[data-out]');
    if (out && !(await out.isDisabled())) { await out.check(); s = await st(); ok(s.url.includes('outdoor=1'), '«Для улицы» — в адресе', s.url); await out.uncheck(); }
    await p.click('[data-brand=""]').catch(() => {});
    // «назад» с карточки товара
    s = await st();
    if (s.more) {
      await p.click('[data-more]');
      const shown = (await st()).vis;
      const href = await p.evaluate(() => { const v = [...document.querySelectorAll('[data-grid] .pc')].filter((c) => !c.hidden); return v[v.length - 1].getAttribute('href'); });
      await p.click(`[data-grid] a[href="${href}"]`); await p.waitForLoadState('networkidle');
      await p.goBack({ waitUntil: 'networkidle' }); s = await st();
      ok(s.vis === shown, '«назад» с товара — показано столько же', `${s.vis} из ${shown}`);
    }
    // пустой результат: у карточек меняется фабрика — под фильтр не попадает ни одна
    if (catInfo.brand) {
      await p.evaluate((b) => { document.querySelectorAll('[data-grid] .pc').forEach((c) => (c.dataset.brand = '-')); document.querySelector(`[data-brand="${b}"]`).click(); }, catInfo.brand);
      s = await st();
      ok(s.empty && num(s.count) === 0, 'пустой результат — сообщение и «Сбросить фильтры»', s.count);
      await p.screenshot({ path: path.join(OUT, 'flow-empty-d.png') });
    }
    await ctx.close();
    ctx = await b.newContext(SIZES.d); p = await ctx.newPage();
    await p.goto(BASE + nav.ru, { waitUntil: 'domcontentloaded' });
    const ruCat = await p.evaluate(() => document.querySelector('.menu__sec ul a')?.getAttribute('href') || '');
    await p.goto(BASE + ruCat, { waitUntil: 'networkidle' });
    s = await st();
    ok(/товар/.test(s.count), 'RU: число товаров по-русски', s.count);
    await ctx.close();

    // 3. главная
    for (const sz of ['d', 'm']) {
      ctx = await b.newContext(SIZES[sz]); p = await ctx.newPage();
      await p.goto(BASE + '/', { waitUntil: 'networkidle' });
      const t = await p.evaluate(() => {
        const ts = [...document.querySelectorAll('.home-depts .tile')];
        const cols = getComputedStyle(document.querySelector('.home-depts')).gridTemplateColumns.split(' ').length;
        const r = (e) => e.getBoundingClientRect();
        const pics = ts.map((x) => (x.querySelector('img')?.getAttribute('src') || '').replace(/-\d+\.webp$/, '')).filter(Boolean);
        const fresh = [...document.querySelectorAll('.home-sec .grid .pc')].map((c) => c.dataset.brand);
        return { n: ts.length, cols, lastW: r(ts.at(-1)).width, gridW: r(document.querySelector('.home-depts')).width, pics: pics.length, uniq: new Set(pics).size, fresh };
      });
      const lone = t.n % t.cols === 1;
      ok(!lone || t.lastW > t.gridW * 0.95, `главная (${sz}): одиночная последняя плитка — на всю ширину`, `${t.n} плиток, колонок ${t.cols}`);
      ok(t.uniq === t.pics, `главная (${sz}): у плиток разные фото`, `${t.uniq} из ${t.pics}`);
      ok(new Set(t.fresh).size >= Math.min(3, t.fresh.length), `главная (${sz}): новинки разных фабрик`, t.fresh.join(', '));
      await ctx.close();
    }

    // 4. меню
    ctx = await b.newContext(SIZES.pm); p = await ctx.newPage();
    await p.goto(BASE + '/', { waitUntil: 'networkidle' });
    await p.click('[data-menu-open]'); await p.waitForTimeout(250);
    const openLists = () => p.evaluate(() => [...document.querySelectorAll('.menu__sec > ul')].filter((u) => u.offsetHeight > 0).length);
    ok((await openLists()) === 0, 'меню (телефон): разделы свёрнуты');
    await p.screenshot({ path: path.join(OUT, 'flow-menu-pm.png') });
    await p.click('.menu__tog'); await p.waitForTimeout(150);
    ok((await openLists()) === 1, 'меню (телефон): стрелка раскрывает раздел');
    await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    ok(await p.evaluate(() => document.getElementById('menu').hidden), 'меню закрывается клавишей Esc');
    await p.goto(BASE + nav.cat, { waitUntil: 'networkidle' });
    await p.click('[data-menu-open]'); await p.waitForTimeout(250);
    ok((await openLists()) === 1, 'меню (телефон): открыт раздел текущей страницы');
    await ctx.close();
    ctx = await b.newContext(SIZES.d); p = await ctx.newPage();
    await p.goto(BASE + '/', { waitUntil: 'networkidle' });
    await p.click('[data-menu-open]'); await p.waitForTimeout(250);
    const mb = await p.evaluate(() => Math.round(Math.max(...[...document.querySelectorAll('.menu__sec')].map((x) => x.getBoundingClientRect().bottom))));
    ok(mb <= 900, 'меню (компьютер): все разделы на первом экране', `низ ${mb} px`);
    await p.screenshot({ path: path.join(OUT, 'flow-menu-d.png') });
    await ctx.close();

    // 5. галерея и форма
    ctx = await b.newContext(SIZES.pm); p = await ctx.newPage();
    await p.goto(BASE + catInfo.product, { waitUntil: 'networkidle' });
    const many = await p.evaluate(() => [...document.querySelectorAll('[data-gallery] [data-full]')].filter((x) => x.dataset.full).length);
    if (many) {
      await p.click('[data-gallery] [data-full]:not([data-full=""])');
      const n0 = await p.evaluate(() => document.querySelector('[data-lb-n]').textContent);
      ok(n0.startsWith('1 /') && !!(await p.getAttribute('[data-lb-img]', 'src')), 'галерея: фото и счётчик сразу', n0);
      if (many > 1) {
        await p.evaluate(() => {
          const lb = document.querySelector('[data-lb]'), t = (x) => new Touch({ identifier: 1, target: lb, clientX: x, clientY: 400 });
          lb.dispatchEvent(new TouchEvent('touchstart', { touches: [t(320)], changedTouches: [t(320)], bubbles: true }));
          lb.dispatchEvent(new TouchEvent('touchend', { touches: [], changedTouches: [t(100)], bubbles: true }));
        });
        ok((await p.evaluate(() => document.querySelector('[data-lb-n]').textContent)).startsWith('2 /'), 'галерея: листается пальцем');
      }
    }
    await ctx.close();
    ctx = await b.newContext(SIZES.d); p = await ctx.newPage();
    await p.goto(BASE + nav.contact, { waitUntil: 'networkidle' });
    const f = await p.evaluate(() => [...document.querySelectorAll('form[data-lead] label.lead__f')].map((l) => ({ req: !!l.querySelector('[required]'), opt: !!l.querySelector('.lead__opt') })));
    ok(f.length > 0 && f.every((x) => x.req !== x.opt), 'форма: необязательные поля подписаны, обязательные — нет');
    await ctx.close();
  } finally {
    await b.close();
    server.close();
  }
  console.log(lines.join('\n'));
  console.log(`\n${fails ? `Ошибок: ${fails}` : 'UI/UX: всё в порядке'}. Скриншоты: ${OUT}`);
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); server.close(); process.exit(1); });
