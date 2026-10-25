// sitemap-pages.xml, sitemap-categories.xml, sitemap-products-<фабрика>.xml — файлы индекса sitemap.xml
// (home/src/lib/sitemap.ts): только опубликованное, языковые версии (hreflang и x-default — английская), фото товаров.
import { sitemapFiles, urlsetXml } from '../lib/sitemap';

export function getStaticPaths() {
  return sitemapFiles().map((f) => ({ params: { name: f.name } }));
}

export function GET({ params }: { params: { name: string } }) {
  const f = sitemapFiles().find((x) => x.name === params.name)!;
  return new Response(urlsetXml(f), { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
}
