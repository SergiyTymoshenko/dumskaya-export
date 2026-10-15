// Готовит фото для сайта из оригиналов выгрузки.
//
//   IMAGES_DIR=~/Documents/dumskaya-export/images npm run images
//
// Для каждой картинки, которая используется на страницах, делает WebP нескольких
// ширин с понятным именем файла (dizajn-...-01-1600.webp) и записывает авторство
// (XMP: автор, правообладатель, описание). Уже готовые файлы пропускает,
// поэтому повторный запуск обрабатывает только новое.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import sharp from 'sharp';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = (process.env.IMAGES_DIR || path.join(os.homedir(), 'Documents/dumskaya-export/images')).replace(/^~/, os.homedir());
const OUT = path.join(ROOT, 'public', 'img');
const WIDTHS = [480, 960, 1440, 1920];
const QUALITY = 78;

const images = JSON.parse(fs.readFileSync(path.join(ROOT, 'content/images.json'), 'utf8'));
const names = JSON.parse(fs.readFileSync(path.join(ROOT, 'content/image-names.json'), 'utf8'));

fs.mkdirSync(OUT, { recursive: true });

const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
function xmp({ alt }) {
  return `<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/" xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/">
<dc:creator><rdf:Seq><rdf:li>DUMSKAYA DESIGN</rdf:li></rdf:Seq></dc:creator>
<dc:rights><rdf:Alt><rdf:li xml:lang="x-default">© DUMSKAYA DESIGN, dumskaya-design.com</rdf:li></rdf:Alt></dc:rights>
<dc:description><rdf:Alt><rdf:li xml:lang="x-default">${esc(alt)}</rdf:li></rdf:Alt></dc:description>
<photoshop:Credit>DUMSKAYA DESIGN</photoshop:Credit>
<xmpRights:WebStatement>https://dumskaya-design.com/</xmpRights:WebStatement>
</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>`;
}

const manifest = {};
const manifestPath = path.join(ROOT, 'content/image-manifest.json');
let done = 0, made = 0, missing = [];
const ids = Object.keys(names);
const queue = [...ids];

async function work() {
  while (queue.length) {
    const id = queue.shift();
    const meta = images[id];
    const name = names[id];
    if (!meta) continue;
    // фото из выгрузки старого сайта — из IMAGES_DIR, новые фото — из папки assets/ в репозитории
    const src = meta.file.startsWith('assets/') ? path.join(ROOT, meta.file) : path.join(SRC, meta.file.replace(/^images\//, ''));
    const widths = WIDTHS.filter((w) => w < meta.width).concat(meta.width > 1920 ? [] : [meta.width]);
    const uniq = [...new Set(widths.map((w) => Math.min(w, 1920)))].sort((a, b) => a - b);
    const files = uniq.map((w) => ({ w, file: `${name}-${w}.webp` }));
    manifest[id] = { name, width: meta.width, height: meta.height, files: files.map((f) => [f.w, f.file]) };
    const todo = files.filter((f) => !fs.existsSync(path.join(OUT, f.file)));
    if (todo.length) {
      if (!fs.existsSync(src)) { missing.push(id); delete manifest[id]; continue; }
      const input = sharp(src, { limitInputPixels: false }).rotate();
      for (const f of todo) {
        await input.clone().resize({ width: f.w, withoutEnlargement: true })
          .webp({ quality: QUALITY, effort: 5 })
          .withXmp(xmp({ alt: meta.alt?.ru || '' }))
          .toFile(path.join(OUT, f.file));
        made++;
      }
    }
    done++;
    if (done % 50 === 0) console.log(`фото: ${done}/${ids.length}`);
  }
}
await Promise.all(Array.from({ length: Math.max(1, os.cpus().length - 1) }, work));
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 0));
// убрать файлы фото, которые больше нигде не используются (фото удалено или заменено на новое)
const valid = new Set(Object.values(names));
let removed = 0;
for (const f of fs.readdirSync(OUT)) {
  const m = f.match(/^(.+)-\d+\.webp$/);
  if (m && !valid.has(m[1])) { fs.unlinkSync(path.join(OUT, f)); removed++; }
}
if (removed) console.log(`удалено старых файлов: ${removed}`);
console.log(`готово: ${done} фото, новых файлов ${made}` + (missing.length ? `, нет оригиналов: ${missing.length}` : ''));
