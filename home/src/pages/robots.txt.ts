// robots.txt: закрыт, пока в content/home/site.json нет "indexing": true (home/src/lib/robots.ts).
import { homeSite } from '../lib/catalog';
import { LIVE, CLOSED } from '../lib/robots';

export function GET() {
  return new Response(homeSite.indexing === true ? LIVE : CLOSED, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
