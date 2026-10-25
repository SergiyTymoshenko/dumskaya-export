// sitemap.xml: все страницы с языковыми версиями (hreflang) и фото товаров.
import { allPages, manifest } from '../lib/catalog';
import { HREFLANG, LANGS, DEFAULT } from '../lib/i18n';

const SITE = 'https://dumskaya-home.com';
const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function GET() {
  const urls = allPages().map((p) => {
    const alts = LANGS.filter((l) => p.alt[l]).map((l) => `<xhtml:link rel="alternate" hreflang="${HREFLANG[l]}" href="${SITE}${p.alt[l]}"/>`);
    if (alts.length && p.alt[DEFAULT]) alts.push(`<xhtml:link rel="alternate" hreflang="x-default" href="${SITE}${p.alt[DEFAULT]}"/>`);
    const imgs = (p.product?.images || []).filter((im) => manifest[im.name]).slice(0, 8).map((im) => {
      const m = manifest[im.name];
      return `<image:image><image:loc>${SITE}/img/${esc(m.files[m.files.length - 1][1])}</image:loc></image:image>`;
    });
    return `<url><loc>${SITE}${p.path}</loc>${alts.join('')}${imgs.join('')}</url>`;
  });
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n${urls.join('\n')}\n</urlset>\n`;
  return new Response(xml, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
}
