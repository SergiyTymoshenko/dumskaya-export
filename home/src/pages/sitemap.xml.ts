// sitemap.xml — индекс карт сайта (home/src/lib/sitemap.ts): страницы, категории, товары по фабрикам.
import { indexXml } from '../lib/sitemap';

export function GET() {
  return new Response(indexXml(), { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
}
