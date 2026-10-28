// llms.txt каталога (стандарт llmstxt.org, по-английски; решено 25.10.2026): собирается при каждой сборке из тех же
// данных, что сайт и карта сайта, — в нём только опубликованное: выложенные фабрики (content/home/publish.json)
// и категории, где есть их товары. Новая фабрика появляется в файле сама, когда её выложат.
// Тексты — с самого сайта (home/src/lib/i18n.ts, английская версия): описание, доставка, как заказать.
import { brandList, byBrand, departments, outdoorProducts, products, paths, catName, tax, homeEmail, countryName, phones, CONTROLLER, STUDIO_ADDRESS } from './catalog';
import { publishedFactory } from './sitemap';
import { ui, LANGS } from './i18n';

const SITE = 'https://dumskaya-home.com';
const STUDIO = 'https://dumskaya-design.com/en';

export function llmsTxt(): string {
  const T = ui('en');
  const pub = products.filter((p) => p.published === true);
  const count = (ps: typeof products) => ps.filter((p) => p.published === true).length;
  const L: string[] = [];
  L.push('# DUMSKAYA HOME', '');
  L.push(`> ${T.home_studio} ${T.priceNote}`, '');
  L.push(`${T.home_h1}. Each product page shows photos, sizes and versions, finishes and dimension drawings; the price is sent on request.`, '');
  L.push(`- Full text of the catalog for LLMs: ${SITE}/llms-full.txt — every published page by section (English text, addresses of all language versions)`, '');
  // контакты и реквизиты (решено 28.10.2026) — только то, что написано на сайте: e-mail и форма на всех языках,
  // телефоны — на русской версии; оператор — из политики конфиденциальности
  const ruPh = phones('ru');
  L.push('## Contacts and company details', '');
  L.push(`- Catalog of DUMSKAYA DESIGN, interior design studio: ${STUDIO_ADDRESS}, Slovakia (also works in Vienna) — ${STUDIO}`);
  if (homeEmail) L.push(`- E-mail: ${homeEmail}`);
  L.push(`- Price requests: the form on every product page and on the [contact page](${SITE}${paths.contact.en})`);
  if (ruPh.length) L.push(`- Phone (listed on the Russian version of the site): ${ruPh.map((p: any) => p.text).join(', ')}`);
  L.push(`- Website operator and data controller: ${CONTROLLER.name} (${CONTROLLER.country}) — [privacy policy](${SITE}${paths.privacy.en})`);
  L.push('');
  L.push('## Worldwide delivery', '');
  for (const s of T.ship) L.push(`- ${s}`);
  L.push('');
  L.push('## How to request a price', '');
  T.how.forEach((s: string, i: number) => L.push(`${i + 1}. ${s}`));
  L.push('');
  L.push(`- [Contact page](${SITE}${paths.contact.en}): the request form${homeEmail ? ` and e-mail ${homeEmail}` : ''}; the same form is on every product page.`);
  const ru = phones('ru');
  if (ru.length) L.push(`- [Russian contact page](${SITE}${paths.contact.ru}): phone numbers are listed only on the Russian version of the site (${ru.map((p: any) => p.text).join(', ')}); in the other languages contact is by the form${homeEmail ? ' or e-mail' : ''}.`);
  L.push('');
  L.push('## Language versions', '');
  const names: Record<string, string> = { en: 'English', ru: 'Russian', de: 'German', fr: 'French', es: 'Spanish' };
  for (const l of LANGS) L.push(`- [${names[l]}](${SITE}${paths.home[l]}): ${l === 'en' ? 'main version, addresses without a language prefix' : `${names[l]} version (/${l})`}`);
  L.push('');
  const brands = brandList.filter((b) => publishedFactory(b.factory));
  L.push('## Brands', '');
  if (brands.length) {
    L.push(`- [All brands](${SITE}${paths.brands.en}): ${brands.length} ${brands.length === 1 ? 'factory' : 'factories'} in the catalog`);
    for (const b of brands) L.push(`- [${b.name}](${SITE}${paths.brand(b.slug).en}): ${T.products(count(byBrand[b.slug]))}, ${countryName(b.factory, 'en')}`);
  } else L.push('Brands are added to the catalog in batches; none is published yet.');
  L.push('');
  if (pub.length) {
    L.push('## Catalog', '');
    for (const d of departments as any[]) {
      const cats = d.categories.filter((c: string) => pub.some((p) => p.category === c));
      if (!cats.length) continue;
      L.push(`### ${d.name.en}`, '', `- [All ${d.name.en.toLowerCase()}](${SITE}${paths.dept(d).en}): ${T.products(pub.filter((p) => p.department === d.id).length)}`);
      for (const c of cats) L.push(`- [${catName(c, 'en')}](${SITE}${paths.cat(c).en}): ${T.products(pub.filter((p) => p.category === c).length)}`);
      L.push('');
    }
    const out = count(outdoorProducts);
    if (out) L.push(`- [${tax.outdoor.name.en}](${SITE}${paths.outdoor().en}): ${T.products(out)} for terraces, gardens and pool areas`, '');
  }
  L.push('## Optional', '');
  L.push(`- [DUMSKAYA DESIGN](${STUDIO}): the interior design studio behind the catalog, Bratislava and Vienna`);
  L.push(`- [Full text of the catalog](${SITE}/llms-full.txt): every published page as Markdown — products with sizes and versions, categories, brands`);
  L.push(`- [Sitemap](${SITE}/sitemap.xml): all published pages in all languages`);
  L.push(`- [Privacy policy](${SITE}${paths.privacy.en}): how data from price requests is processed`);
  return L.join('\n') + '\n';
}
