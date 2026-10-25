// Фото для dumskaya-home.com: из оригиналов выгрузки фабрик — WebP нескольких ширин с описательными именами.
//
//   node scripts/home_images.mjs           # фото товаров из home/data/catalog.json (сначала catalog_index.py --write)
//
// Оригиналы — в папке выгрузки на Маке: ~/Documents/dumskaya-export/images/shop/<фабрика>/… (другая — EXPORT_DIR=…).
// Имя файла на сайте — из каталога: minotti-torii-sofa-01-960.webp, чертёж — …-dimensions-01-960.webp.
// Фото товаров — 480, 960 и 1600 px по ширине, чертежи — 960 и 1600 px на белом фоне. Метаданные снимков фабрик
// не переносим. Уже готовые файлы пропускает: повторный запуск делает только новое. Сводка — home/data/image-manifest.json.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import sharp from 'sharp';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EXPORT = (process.env.EXPORT_DIR || path.join(os.homedir(), 'Documents/dumskaya-export')).replace(/^~/, os.homedir());
const OUT = path.join(ROOT, 'home/public/img');
const CAT = path.join(ROOT, 'home/data/catalog.json');
const MAN = path.join(ROOT, 'home/data/image-manifest.json');
const PHOTO = [480, 960, 1600], DRAW = [960, 1600];
sharp.concurrency(2);

const cat = JSON.parse(fs.readFileSync(CAT, 'utf8'));
const jobs = new Map();                       // имя → задание (одно фото у двух товаров — один файл)
for (const p of cat.products) {
  for (const im of p.images) jobs.set(im.name, { ...im, widths: PHOTO, drawing: false });
  for (const im of p.drawings) jobs.set(im.name, { ...im, widths: DRAW, drawing: true });
}
fs.mkdirSync(OUT, { recursive: true });
const manifest = {};
let made = 0, done = 0, missing = [], failed = [];
const queue = [...jobs.values()];
const t0 = Date.now();

async function one(j) {
  const src = path.join(EXPORT, j.src);
  const w0 = j.w || 1600, h0 = j.h || 1200;
  const widths = [...new Set(j.widths.filter((w) => w < w0).concat(w0 <= j.widths.at(-1) ? [w0] : []).map((w) => Math.min(w, j.widths.at(-1))))].sort((a, b) => a - b);
  if (!widths.length) widths.push(Math.min(w0, j.widths.at(-1)));
  const files = widths.map((w) => [w, `${j.name}-${w}.webp`]);
  const todo = files.filter(([, f]) => !fs.existsSync(path.join(OUT, f)));
  if (todo.length) {
    if (!fs.existsSync(src)) { missing.push(j.src); return; }
    let input = sharp(src, { limitInputPixels: false, density: /\.svg$/i.test(src) ? 150 : undefined }).rotate();
    if (j.drawing) input = input.flatten({ background: '#ffffff' });
    for (const [w, f] of todo) {
      await input.clone().resize({ width: w, withoutEnlargement: !/\.svg$/i.test(src) })
        .webp({ quality: j.drawing ? 88 : 78, effort: 4 }).toFile(path.join(OUT, f));
      made++;
    }
  }
  manifest[j.name] = { width: w0, height: h0, files };
  if (!j.drawing) Object.assign(manifest[j.name], await edges(path.join(OUT, files[0][1])));
}

// предметный снимок на светлом фоне (а не интерьер): светлые ровные края — в списках такой показываем целиком,
// а плитку закрашиваем цветом фона снимка (bg), чтобы не было видно границы фото
const cutCache = fs.existsSync(MAN) ? JSON.parse(fs.readFileSync(MAN, 'utf8')) : {};
async function edges(file) {
  const name = path.basename(file).replace(/-\d+\.webp$/, '');
  const c = cutCache[name];
  if (c && typeof c.cut === 'boolean' && (c.bg || !c.cut)) return { cut: c.cut, ...(c.bg ? { bg: c.bg } : {}) };
  const n = 24;
  const px = await sharp(file).flatten({ background: '#ffffff' }).resize(n, n, { fit: 'fill' }).removeAlpha().raw().toBuffer();
  const edge = [];
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    if (x > 1 && x < n - 2 && y > 1 && y < n - 2) continue;
    const i = (y * n + x) * 3;
    edge.push([px[i], px[i + 1], px[i + 2]]);
  }
  const light = edge.filter(([r, g, b]) => (r + g + b) / 3 > 222 && Math.max(r, g, b) - Math.min(r, g, b) < 14);
  if (light.length / edge.length < 0.85) return { cut: false };
  const avg = (k) => Math.round(light.reduce((s, p) => s + p[k], 0) / light.length);
  return { cut: true, bg: '#' + [0, 1, 2].map((k) => avg(k).toString(16).padStart(2, '0')).join('') };
}

async function worker() {
  while (queue.length) {
    const j = queue.shift();
    try { await one(j); } catch (e) { failed.push(`${j.src}: ${e.message}`); }
    if (++done % 500 === 0) console.log(`  ${done} из ${jobs.size} (${Math.round((Date.now() - t0) / 1000)} с)`);
  }
}
await Promise.all(Array.from({ length: Math.max(2, Math.min(6, os.cpus().length - 1)) }, worker));
fs.writeFileSync(MAN, JSON.stringify(manifest));
console.log(`фото DUMSKAYA HOME: ${Object.keys(manifest).length} из ${jobs.size}, сделано файлов ${made}` +
  (missing.length ? `, нет оригинала: ${missing.length} (например, ${missing.slice(0, 3).join(', ')})` : '') +
  (failed.length ? `, ошибок: ${failed.length} (${failed.slice(0, 2).join('; ')})` : ''));
if (missing.length) console.log(`  оригиналы ищутся в ${EXPORT} — докачать: python3 scripts/shop/factories/dl.py <фабрика>`);
