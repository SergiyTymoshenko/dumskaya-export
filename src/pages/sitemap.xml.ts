// sitemap.xml: все страницы, языковые версии (hreflang) и фото страниц.
import { pages, manifest, seoImages } from '../lib/data';
import { HREFLANG, LANGS } from '../lib/i18n';
import projects from '../../content/projects.json';

const SITE = 'https://dumskaya-design.com';
const abs = (p: string) => SITE + (p === '/' ? '/' : p);
const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function GET() {
  const byPath = new Map(pages.map((p) => [p.path, p]));
  const covers = new Map<string, string[]>();
  // обложки проектов — к страницам портфолио
  for (const pr of projects as any[]) if (pr.cover) for (const l of LANGS) {
    const portfolio = pages.find((p) => p.type === 'portfolio' && p.lang === l);
    if (portfolio) covers.set(portfolio.path, [...(covers.get(portfolio.path) || []), pr.cover]);
  }
  const urls = pages.map((p) => {
    const alts = LANGS.filter((l) => p.alternates[l] && byPath.has(p.alternates[l]!))
      .map((l) => `<xhtml:link rel="alternate" hreflang="${HREFLANG[l]}" href="${abs(p.alternates[l]!)}"/>`);
    const xd = p.alternates.en || p.alternates.ru;
    if (alts.length) alts.push(`<xhtml:link rel="alternate" hreflang="x-default" href="${abs(xd!)}"/>`);
    const ids = [...new Set([...seoImages(p).map((i) => i.id), ...(covers.get(p.path) || [])])].filter((id) => manifest[id]).slice(0, 200);
    const imgs = ids.map((id) => {
      const m = manifest[id];
      const f = (m.files.find(([w]) => w >= 1440) || m.files[m.files.length - 1])[1];
      return `<image:image><image:loc>${SITE}/img/${esc(f)}</image:loc></image:image>`;
    });
    return `<url><loc>${abs(p.path)}</loc>${alts.join('')}${imgs.join('')}</url>`;
  });
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n${urls.join('\n')}\n</urlset>\n`;
  return new Response(xml, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
}
