// Общее для проверок UI/UX (scripts/ux_home.cjs — каталог, ux_site.cjs — сайт студии, ux_apps.cjs — мини-приложения бота):
// браузер, экраны, проверка страницы (прокрутка вбок, доступность axe, зоны нажатия, H1, alt, сдвиг вёрстки), сервер сборки, итог.
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const has = (k) => process.argv.includes(k);

function playwright() {
  try { return require('playwright'); } catch {
    console.log('Нет Playwright. Установить: npm i --no-save playwright axe-core && npx playwright install chromium');
    process.exit(2);
  }
}
function axeSource() {
  for (const f of [() => require.resolve('axe-core/axe.min.js'), () => process.env.UX_AXE]) {
    try { const p = f(); if (p && fs.existsSync(p)) return fs.readFileSync(p, 'utf8'); } catch { /* дальше */ }
  }
  return '';
}

// экраны: компьютер, телефон, iPhone Pro Max (у разработчика и Ирины), окно мини-приложения в Telegram на компьютере
const SIZES = {
  d: { viewport: { width: 1440, height: 900 } },
  m: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  pm: { viewport: { width: 440, height: 956 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true },
  tg: { viewport: { width: 420, height: 760 } },
};

function report() {
  const lines = [];
  let fails = 0;
  const ok = (c, what, extra = '') => { if (!c) fails++; lines.push(`${c ? '✓' : '✗'} ${what}${extra ? ' — ' + extra : ''}`); };
  const warn = (what) => lines.push(`⚠ ${what}`);
  const done = (out, label = 'UI/UX') => {
    console.log(lines.join('\n'));
    console.log(`\n${fails ? `Ошибок: ${fails}` : `${label}: всё в порядке`}. Скриншоты: ${out}`);
    return fails;
  };
  return { ok, warn, done, get fails() { return fails; } };
}

// статическая сборка как на сервере: /адрес → адрес.html (или адрес/index.html), /api/* — заглушка
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.xml': 'application/xml', '.txt': 'text/plain', '.ico': 'image/x-icon', '.json': 'application/json' };
function staticServer(dirs, port) {
  const roots = dirs.map((d) => path.resolve(d));
  const srv = http.createServer((req, res) => {
    const u = decodeURIComponent(req.url.split('?')[0]);
    if (u.startsWith('/api/')) { res.writeHead(200, { 'content-type': 'application/json' }); return res.end('{"ok":true}'); }
    for (const r of roots) {
      for (const c of [u === '/' ? 'index.html' : u, u + '.html', path.join(u, 'index.html')]) {
        const f = path.join(r, c);
        if (f.startsWith(r) && fs.existsSync(f) && fs.statSync(f).isFile()) {
          res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' });
          return fs.createReadStream(f).pipe(res);
        }
      }
    }
    const nf = path.join(roots[0], '404.html');
    res.writeHead(404, { 'content-type': TYPES['.html'] });
    res.end(fs.existsSync(nf) ? fs.readFileSync(nf) : 'not found');
  });
  return new Promise((ok) => srv.listen(port, '127.0.0.1', () => ok(srv)));
}

// Проверка одной открытой страницы. skip — селектор областей, которые не проверяем (например, закрытое меню).
// axeOff — правила axe, которые здесь не проверяются (у мини-приложений бота — только для экранного диктора, он не нужен)
async function checkPage(p, AXE, { skip = '', status, expect = 200, oneH1 = true, minTarget = 24, axeOff = [] } = {}) {
  await p.waitForTimeout(250);
  const m = await p.evaluate(([skip, minTarget]) => {
    const vw = document.documentElement.clientWidth;
    const small = [];
    for (const a of document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab]')) {
      const r = a.getBoundingClientRect(), cs = getComputedStyle(a);
      if (!r.width || !r.height || cs.visibility === 'hidden' || a.closest('[hidden], [aria-hidden="true"], .lead__hp' + (skip ? ', ' + skip : ''))) continue;
      // ссылка внутри предложения (вокруг неё есть слова) — исключение WCAG 2.5.8; пункт списка из одной ссылки — нет
      const block = a.closest('p, li, dd, td, address, figcaption');
      if (block && !a.matches('.btn, button, [role=button]') && !block.closest('nav, .crumbs')) {
        let rest = block.textContent;
        block.querySelectorAll('a, button').forEach((x) => { rest = rest.replace(x.textContent, ' '); });
        if (/\p{L}/u.test(rest)) continue;
      }
      const lab = a.closest('label'); if (lab && lab.getBoundingClientRect().height >= minTarget) continue;   // галочка с подписью — нажимается вся подпись
      if (r.width < minTarget || r.height < minTarget) small.push(`${a.tagName.toLowerCase()}「${(a.innerText || a.getAttribute('aria-label') || a.title || a.name || '').trim().replace(/\s+/g, ' ').slice(0, 30)}」${Math.round(r.width)}×${Math.round(r.height)}`);
    }
    const wide = [...document.querySelectorAll('body *')].filter((e) => { const r = e.getBoundingClientRect(); return r.width && r.right > vw + 1 && getComputedStyle(e).position !== 'fixed' && !e.closest('[hidden]'); })
      .slice(0, 3).map((e) => e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : ''));
    return { overflow: document.documentElement.scrollWidth > vw + 1, wide, small, h1: document.querySelectorAll('h1').length,
      noAlt: [...document.images].filter((i) => !i.hasAttribute('alt')).length, cls: window.__cls || 0 };
  }, [skip, minTarget]);
  let axe = [];
  if (AXE) {
    if (!(await p.evaluate(() => !!window.axe))) await p.addScriptTag({ content: AXE });
    axe = await p.evaluate(async ([skip, off]) => {
      const ctx = skip ? { exclude: skip.split(',').map((s) => [s.trim()]) } : document;
      const rules = Object.fromEntries(off.map((id) => [id, { enabled: false }]));
      const r = await window.axe.run(ctx, { resultTypes: ['violations'], runOnly: ['wcag2a', 'wcag2aa', 'best-practice'], rules });
      return r.violations.map((v) => `${v.id} ×${v.nodes.length}: ${v.nodes[0].target.join(' ')}`);
    }, [skip, axeOff]);
  }
  const bad = [];
  if (status !== undefined && status !== expect) bad.push(`ответ ${status}`);
  if (m.overflow) bad.push(`прокрутка вбок (${m.wide.join(', ')})`);
  if (m.small.length) bad.push(`мелкие зоны ×${m.small.length}: ${m.small.slice(0, 4).join('; ')}`);
  if (oneH1 && m.h1 !== 1) bad.push(`H1: ${m.h1}`);
  if (m.noAlt) bad.push(`фото без alt: ${m.noAlt}`);
  if (m.cls >= 0.1) bad.push(`сдвиг вёрстки ${m.cls.toFixed(2)}`);
  if (axe.length) bad.push(`доступность: ${axe.slice(0, 4).join(' | ')}`);
  return bad;
}
const watchCls = (p) => p.addInitScript(() => {
  window.__cls = 0;
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: 'layout-shift', buffered: true }); } catch { /* нет API */ }
});
async function scrollThrough(p) {
  await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 800) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 40)); } window.scrollTo(0, 0); });
  await p.waitForTimeout(250);
}
const outDir = (name) => { const d = path.resolve(arg('--out', path.join(os.tmpdir(), name))); fs.mkdirSync(d, { recursive: true }); return d; };

module.exports = { ROOT, arg, has, playwright, axeSource, SIZES, report, staticServer, checkPage, watchCls, scrollThrough, outDir };
