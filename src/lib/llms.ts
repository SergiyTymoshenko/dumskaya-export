// Тексты для нейросетей (llms.txt, llms-full.txt): справка о студии и полный текст сайта в Markdown.
// Собираются из тех же данных, что и страницы, поэтому всегда совпадают с сайтом.
import { pages, pageByPath, projects, site, type Page } from './data';

export const SITE = 'https://dumskaya-design.com';
export const abs = (p: string) => SITE + (p === '/' ? '/' : p);

const ENT: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'", nbsp: ' ' };
export function plain(html: string): string {
  return String(html || '')
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>/gi, (_, h, t) => (h.startsWith('/') ? `[${t}](${abs(h)})` : t))
    .replace(/<\/?strong>/gi, '**')
    .replace(/<[^>]+>/g, '')
    .replace(/&(amp|lt|gt|quot|#39|nbsp);/g, (_, e) => ENT[e])
    .replace(/\*\*\s*\*\*/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Текст страницы в Markdown: заголовки, абзацы, списки, кнопки-ссылки. h — уровень заголовков внутри страницы. */
export function pageMarkdown(p: Page, h = '###'): string {
  const out: string[] = [];
  for (const s of p.sections || []) {
    for (const b of s.blocks as any[]) {
      if (b.type === 'heading') {
        if (b.level === 1) continue;
        out.push(`${h} ${plain(b.text)}`);
      } else if (b.type === 'text') {
        for (const part of b.parts) {
          if (part.t === 'p') { const t = plain(part.html); if (t) out.push(t); }
          else out.push(part.items.map((i: string) => `- ${plain(i)}`).join('\n'));
        }
      } else if (b.type === 'faq') {
        for (const f of b.items) out.push(`**${plain(f.q)}**\n\n${plain(f.a)}`);
      } else if (b.type === 'facts') {
        out.push(b.rows.map(([k, v]: [string, string]) => `- ${plain(k)}: ${plain(v)}`).join('\n'));
      } else if (b.type === 'cards') {
        const items = b.items.filter((i: any) => i.title && i.href && i.href.startsWith('/'));
        if (items.length) out.push(items.map((i: any) => `- [${plain(i.title)}](${abs(i.href)})`).join('\n'));
      }
    }
  }
  return out.join('\n\n');
}

const en = (path: string) => pageByPath.get(path);
const menu = site.menu.en as any[];
const group = (label: string) => menu.find((m) => m.label === label)?.children || [];

const SUMMARY = 'Interior design studio based in Bratislava, Slovakia, working in Bratislava and Vienna, Austria; ' +
  'design projects for clients in other countries are prepared remotely. ' +
  'Residential and commercial interior design, custom furniture and kitchens from the studio’s own workshop in Bratislava, ' +
  'turnkey renovation by the studio’s own crews, architecture and 3D visualization. ' +
  'Founded and led by interior designer Irina Dumskaya, more than 15 years of experience. ' +
  'Prices are the same in Bratislava and Vienna, furniture delivery is included. ' +
  'The website is available in English, Slovak, German, Ukrainian and Russian.';

/** Оператор сайта (ответственный за данные) — как написано в политике конфиденциальности: только факты с сайта. */
function controller(): string | null {
  const p = en('/en/privacy');
  for (const s of p?.sections || []) for (const b of s.blocks as any[]) for (const part of b.parts || []) {
    const m = String(part.html || '').match(/Data controller:\s*<strong>([^<]+)<\/strong>[^.]*?\b(USA|United States)\b/);
    if (m) return `${m[1].trim()} (${m[2]})`;
  }
  return null;
}

function contactLines(L: string[]) {
  const c = site.contacts;
  L.push(`- Studio address: ${c.address.street}, ${c.address.postal} ${c.address.city}, Slovakia`);
  L.push(`- Phone: ${c.phones.map((p: any) => `${p.text} (${p.city.en})`).join(', ')}`);
  L.push(`- Email: ${c.email}`);
  L.push(`- Messengers: WhatsApp and Telegram at ${c.phones[0].text}`);
  L.push(`- Instagram: ${c.social.map((s: any) => s.href).join(', ')}`);
  L.push('- First consultation is free.');
}

export function llmsTxt(): string {
  const c = site.contacts;
  const L: string[] = [];
  L.push('# DUMSKAYA DESIGN');
  L.push('');
  L.push(`> ${SUMMARY}`);
  L.push('');
  contactLines(L);
  L.push(`- Full text of the website for LLMs: ${abs('/llms-full.txt')}`);
  L.push('');
  const op = controller();
  L.push('## Company details', '');
  L.push(`- Brand: DUMSKAYA DESIGN, interior design studio; founder and lead designer Irina Dumskaya`);
  L.push(`- Studio: ${c.address.street}, ${c.address.postal} ${c.address.city} (${c.address.district}), Slovakia`);
  if (op) L.push(`- Website operator and data controller: ${op} — [privacy policy](${abs('/en/privacy')})`);
  L.push(`- Product catalog of partner factories: [DUMSKAYA HOME](https://dumskaya-home.com/) — the studio’s catalog site`);
  L.push('');
  const section = (title: string, items: { label: string; href: string }[]) => {
    L.push(`## ${title}`, '');
    for (const i of items) {
      const p = en(i.href);
      L.push(`- [${i.label}](${abs(i.href)})${p?.description ? `: ${p.description}` : ''}`);
    }
    L.push('');
  };
  L.push('## About', '', `- [About the studio](${abs('/en/about-studio')}): who we are, own furniture workshop and crews, where we work.`, '');
  section('Services', group('Services'));
  section('Where we work', group('Where we work'));
  section('Design packages and prices', [{ label: 'All prices', href: '/en/interior-design-pricing-bratislava-wien-praha' }, ...group('Prices')]
    .map((i: any) => ({ label: en(i.href)?.title?.replace(/\s*\|\s*DUMSKAYA.*$/, '') || i.label, href: i.href })));
  const kitchens = pages.filter((p) => p.lang === 'en' && p.type === 'kitchen');
  L.push('## Custom kitchens', '');
  L.push(`- [Kitchen catalog](${abs('/en/custom-kitchens-bratislava-vienna')}): ${kitchens.length} standard kitchen models made to order in Bratislava and Vienna, each with full specifications.`);
  L.push('');
  const labels: Record<string, string> = { residential: 'Residential interiors', commercial: 'Commercial interiors', architecture: 'Architecture' };
  L.push('## Portfolio', '', `- [All projects](${abs('/en/portfolio-interior-design-projects')})`);
  for (const g of ['residential', 'commercial', 'architecture']) {
    const list = projects.filter((p: any) => p.group === g && p.alternates.en);
    if (!list.length) continue;
    L.push('', `### ${labels[g]}`, '');
    for (const p of list as any[]) { const d = en(p.alternates.en)?.description; L.push(`- [${p.title.en}](${abs(p.alternates.en)})${d ? `: ${d}` : ''}`); }
  }
  L.push('');
  // магазин студии: коллекция мебели собственного дизайна (страницы магазина — те же данные, что и на сайте)
  const shop = pages.filter((p) => p.lang === 'en' && p.type === 'shop').sort((a, b) => a.path.length - b.path.length || a.path.localeCompare(b.path));
  if (shop.length) {
    L.push('## Furniture shop', '');
    for (const p of shop) L.push(`- [${plain(p.h1 || p.title)}](${abs(p.path)})${p.description ? `: ${p.description}` : ''}`);
    L.push('');
  }
  // остальные страницы услуг: по городам (кухни и мебель в Вене, ремонт в Варшаве…) и отдельные — чтобы были все
  const linked = new Set(L.join('\n').match(/\]\(https:\/\/dumskaya-design\.com[^)]*\)/g)?.map((x) => x.slice(2, -1).replace(SITE, '') || '/') || []);
  const more = pages.filter((p) => p.lang === 'en' && p.type === 'service' && !linked.has(p.path)).sort((a, b) => a.path.localeCompare(b.path));
  if (more.length) {
    L.push('## More service pages', '');
    for (const p of more) L.push(`- [${plain(p.h1 || p.title)}](${abs(p.path)})${p.description ? `: ${p.description}` : ''}`);
    L.push('');
  }
  section('Tips', group('Tips'));
  L.push('## Contact', '', `- [Contact page](${abs('/en/contact-studio-interior-design-bratislava-vienna')}): phones, messengers, address and a request form.`, '');
  L.push('## Language versions', '');
  L.push(`- [English](${abs('/en')}): the links in this file lead to the English pages`);
  L.push(`- [Russian](${abs('/')}): the default language of the site (addresses without a language prefix)`);
  L.push(`- [Ukrainian](${abs('/ua')}): Ukrainian version`);
  L.push(`- [Slovak](${abs('/sk')}): Slovak version, with the Slovak phone number of the studio`);
  L.push(`- [German](${abs('/de')}): German version for Austria, with the Vienna phone number of the studio`);
  L.push('');
  L.push('## Optional', '');
  L.push(`- [Full text of the website](${abs('/llms-full.txt')}): every page as Markdown, by section — English text with the addresses of all language versions`);
  L.push(`- [Sitemap](${abs('/sitemap.xml')}): all pages in all languages`);
  L.push(`- [Privacy policy](${abs('/en/privacy')}): how request data is processed`);
  L.push(`- [Use of photos and renderings](${abs('/en/image-license')}): rights to the photos and renderings on the site`);
  return L.join('\n') + '\n';
}

// Полный текст сайта (решено 28.10.2026, как на usk.ua): раздел → страница → адрес и адреса на других языках →
// описание → текст, факты, вопросы и ответы. Текст — английская версия страницы (те же данные, что на сайте; собирается
// при каждой сборке), у каждой страницы — ссылки на её русскую, украинскую, словацкую и немецкую версии.
const LANG_NAME: Record<string, string> = { ru: 'Russian', ua: 'Ukrainian', sk: 'Slovak', de: 'German' };
const GROUP_NAME: Record<string, string> = { residential: 'residential interiors', commercial: 'commercial interiors', architecture: 'architecture' };

function sectionOf(p: Page): string {
  if (['home', 'about', 'contact'].includes(p.type)) return 'Studio';
  if (p.type === 'service') return 'Services';
  if (p.type === 'price') return 'Design packages and prices';
  if (p.type === 'kitchen') return 'Custom kitchens';
  if (p.type === 'portfolio') return 'Portfolio';
  if (p.type === 'project') {
    const pr = projects.find((x: any) => x.alternates.en === p.path) as any;
    return 'Portfolio: ' + (GROUP_NAME[pr?.group || p.group || ''] || 'projects');
  }
  if (p.type === 'article') return 'Tips';
  if (p.type === 'shop') return 'Furniture shop';
  if (p.type === 'privacy') return 'Legal';
  return 'Other pages';
}
const SECTION_ORDER = ['Studio', 'Services', 'Design packages and prices', 'Custom kitchens', 'Portfolio', 'Portfolio: residential interiors',
  'Portfolio: commercial interiors', 'Portfolio: architecture', 'Portfolio: projects', 'Tips', 'Furniture shop', 'Legal', 'Other pages'];
const TYPE_ORDER = ['home', 'about', 'contact'];

export function llmsFullList(): Page[] {
  return pages.filter((p) => p.lang === 'en');
}

export function llmsFullTxt(): string {
  const list = llmsFullList();
  const menuOrder = [...group('Services'), ...group('Where we work'), ...group('Prices'), ...group('Tips')].map((i: any) => i.href);
  const rank = (p: Page) => (TYPE_ORDER.includes(p.type) ? TYPE_ORDER.indexOf(p.type) : menuOrder.includes(p.path) ? 10 + menuOrder.indexOf(p.path) : 1000);
  const bySection = new Map<string, Page[]>();
  for (const p of list) { const k = sectionOf(p); if (!bySection.has(k)) bySection.set(k, []); bySection.get(k)!.push(p); }
  const L: string[] = ['# DUMSKAYA DESIGN — full text of the website', '', `> ${SUMMARY}`, ''];
  L.push(`Pages: ${list.length} — the English version of every page of the site, each with the addresses of its Russian, Ukrainian, ` +
    `Slovak and German versions (the texts are the same). Updated: ${new Date().toISOString().slice(0, 10)}.`);
  L.push('');
  contactLines(L);
  const op = controller();
  if (op) L.push(`- Website operator and data controller: ${op}`);
  L.push(`- Summary with links: ${abs('/llms.txt')} · Sitemap: ${abs('/sitemap.xml')}`);
  L.push('');
  const keys = [...bySection.keys()].sort((a, b) => (SECTION_ORDER.indexOf(a) + 1 || 99) - (SECTION_ORDER.indexOf(b) + 1 || 99));
  for (const k of keys) {
    const ps = bySection.get(k)!.sort((a, b) => rank(a) - rank(b) || a.path.localeCompare(b.path));
    L.push(`## ${k}`, '');
    for (const p of ps) {
      L.push(`### ${plain(p.h1 || p.title)}`, '', `- Page: ${abs(p.path)}`);
      const alts = Object.entries(LANG_NAME).map(([l, n]) => [n, p.alternates[l as keyof typeof p.alternates]] as const)
        .filter(([, u]) => u && pageByPath.has(u)).map(([n, u]) => `${n}: ${abs(u!)}`);
      if (alts.length) L.push(`- Other languages: ${alts.join(' · ')}`);
      if (p.description) L.push(`- Description: ${plain(p.description)}`);
      const body = pageMarkdown(p, '####');
      if (body) L.push('', body);
      L.push('');
    }
  }
  return L.join('\n') + '\n';
}
