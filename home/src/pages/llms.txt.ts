// llms.txt — справка о сайте для нейросетей (как у сайта студии): что это за каталог, фабрики, разделы, как заказать.
import { brandList, byBrand, departments, paths, catName, byCategory, homeEmail } from '../lib/catalog';

const SITE = 'https://dumskaya-home.com';
export function GET() {
  const lines = [
    '# DUMSKAYA HOME',
    '',
    '> Product catalog of DUMSKAYA DESIGN, an interior design studio in Bratislava (Slovakia) that also works in Vienna (Austria).',
    '> Furniture and lighting by European factories. Prices are not published: a price request goes to the studio, which replies within one working day.',
    '> Worldwide delivery: the studio ships across Europe and to other countries; delivery cost and time are quoted together with the price, export documents are prepared for destinations outside the EU.',
    '',
    'Languages: English (main), Russian (/ru), German (/de), French (/fr), Spanish (/es).',
    `Contact: the form at ${SITE}${paths.contact.en}${homeEmail ? `, e-mail ${homeEmail}` : ''}`,
    'Studio website: https://dumskaya-design.com/en',
    '',
    '## Brands',
    ...brandList.map((b) => `- [${b.name}](${SITE}${paths.brand(b.slug).en}): ${byBrand[b.slug].length} products`),
    '',
    '## Catalog',
    ...departments.flatMap((d: any) => [`### ${d.name.en}`, ...d.categories.map((c: string) => `- [${catName(c, 'en')}](${SITE}${paths.cat(c).en}): ${byCategory[c].length} products`)]),
    '',
  ];
  return new Response(lines.join('\n'), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
