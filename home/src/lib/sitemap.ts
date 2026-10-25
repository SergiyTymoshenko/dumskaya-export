// Карта сайта каталога (решено 25.10.2026): только опубликованное — товары и страницы выложенных фабрик
// (content/home/publish.json), разделы и категории, где есть их товары, и общие страницы. В режиме просмотра (все фабрики)
// невыложенное в карту не попадает. sitemap.xml — индекс: sitemap-pages.xml (главная, фабрики, контакты, политика),
// sitemap-categories.xml (разделы, категории, «Для улицы», страницы фабрик), sitemap-products-<фабрика>.xml — товары
// по фабрикам; в файле не больше MAX адресов (у большой фабрики — несколько файлов: …-2.xml, …-3.xml).
// Даты <lastmod> вписывает после сборки scripts/lastmod.py (по содержимому страниц и истории git).
import { allPages, products, outdoorProducts, brandsInfo, manifest, type HPage, type Product } from './catalog';
import { HREFLANG, LANGS, DEFAULT } from './i18n';

export const SITE = 'https://dumskaya-home.com';
const MAX = 45000;                         // протокол — до 50 000 адресов в файле
const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const pub = (p: Product) => p.published === true;
export const publishedFactory = (f: string) => !!brandsInfo[f]?.published;
const factoryOfSlug = Object.fromEntries(products.map((p) => [p.brand_slug, p.factory]));
const hasPub = (ps: Product[]) => ps.some(pub);

/** Страница опубликована (её можно показывать поисковикам и в llms.txt) */
export function isPublished(pg: HPage): boolean {
  switch (pg.kind) {
    case 'product': return !!pg.product && pub(pg.product);
    case 'brand': return publishedFactory(factoryOfSlug[pg.key!] || '');
    case 'dept': return hasPub(products.filter((p) => p.department === pg.key));
    case 'cat': return hasPub(products.filter((p) => p.category === pg.key));
    case 'outdoor': return hasPub(outdoorProducts);
    default: return true;                  // главная, список фабрик, контакты, политика
  }
}

export type SitemapFile = { name: string; pages: HPage[] };
let cache: SitemapFile[] | null = null;
export function sitemapFiles(): SitemapFile[] {
  if (cache) return cache;
  const pages: HPage[] = [], cats: HPage[] = [], byFactory: Record<string, HPage[]> = {};
  for (const pg of allPages()) {
    if (!isPublished(pg)) continue;
    if (pg.kind === 'product') (byFactory[pg.product!.factory] ||= []).push(pg);
    else if (['dept', 'cat', 'outdoor', 'brand'].includes(pg.kind)) cats.push(pg);
    else pages.push(pg);
  }
  const out: SitemapFile[] = [{ name: 'pages', pages }];
  if (cats.length) out.push({ name: 'categories', pages: cats });
  for (const f of Object.keys(byFactory).sort()) {
    const all = byFactory[f];
    for (let i = 0; i < all.length; i += MAX) out.push({ name: `products-${f}${i ? `-${i / MAX + 1}` : ''}`, pages: all.slice(i, i + MAX) });
  }
  return (cache = out);
}

function urlXml(p: HPage) {
  const alts = LANGS.filter((l) => p.alt[l]).map((l) => `<xhtml:link rel="alternate" hreflang="${HREFLANG[l]}" href="${SITE}${p.alt[l]}"/>`);
  if (alts.length && p.alt[DEFAULT]) alts.push(`<xhtml:link rel="alternate" hreflang="x-default" href="${SITE}${p.alt[DEFAULT]}"/>`);
  const imgs = (p.product?.images || []).filter((im) => manifest[im.name]).slice(0, 8).map((im) => {
    const m = manifest[im.name];
    return `<image:image><image:loc>${SITE}/img/${esc(m.files[m.files.length - 1][1])}</image:loc></image:image>`;
  });
  return `<url><loc>${SITE}${p.path}</loc>${alts.join('')}${imgs.join('')}</url>`;
}

export function urlsetXml(f: SitemapFile) {
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n${f.pages.map(urlXml).join('\n')}\n</urlset>\n`;
}

export function indexXml() {
  const rows = sitemapFiles().map((f) => `<sitemap><loc>${SITE}/sitemap-${f.name}.xml</loc></sitemap>`);
  return `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${rows.join('\n')}\n</sitemapindex>\n`;
}
