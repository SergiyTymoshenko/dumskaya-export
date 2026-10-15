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

/** Текст страницы в Markdown: заголовки, абзацы, списки, кнопки-ссылки. */
export function pageMarkdown(p: Page): string {
  const out: string[] = [];
  for (const s of p.sections || []) {
    for (const b of s.blocks as any[]) {
      if (b.type === 'heading') {
        if (b.level === 1) continue;
        out.push(`### ${plain(b.text)}`);
      } else if (b.type === 'text') {
        for (const part of b.parts) {
          if (part.t === 'p') { const t = plain(part.html); if (t) out.push(t); }
          else out.push(part.items.map((i: string) => `- ${plain(i)}`).join('\n'));
        }
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

export function llmsTxt(): string {
  const c = site.contacts;
  const L: string[] = [];
  L.push('# DUMSKAYA DESIGN');
  L.push('');
  L.push('> Interior design studio based in Bratislava, Slovakia, working in Bratislava and Vienna, Austria. ' +
    'Residential and commercial interior design, custom furniture and kitchens made to order, turnkey renovation, ' +
    'architecture and 3D visualization. Founded and led by interior designer Irina Dumskaya. ' +
    'The website is available in English, Ukrainian and Russian.');
  L.push('');
  L.push(`- Studio address: ${c.address.street}, ${c.address.postal} ${c.address.city}, Slovakia`);
  L.push(`- Phone: ${c.phones.map((p: any) => `${p.text} (${p.city.en})`).join(', ')}`);
  L.push(`- Email: ${c.email}`);
  L.push(`- Messengers: WhatsApp and Telegram at ${c.phones[0].text}`);
  L.push(`- Instagram: ${c.social.map((s: any) => s.href).join(', ')}`);
  L.push('- First consultation is free.');
  L.push('');
  const section = (title: string, items: { label: string; href: string }[]) => {
    L.push(`## ${title}`, '');
    for (const i of items) {
      const p = en(i.href);
      L.push(`- [${i.label}](${abs(i.href)})${p?.description ? `: ${p.description}` : ''}`);
    }
    L.push('');
  };
  section('Services', group('Services'));
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
    for (const p of list as any[]) L.push(`- [${p.title.en}](${abs(p.alternates.en)})`);
  }
  L.push('');
  section('Tips', group('Tips'));
  L.push('## Contact', '', `- [Contact page](${abs('/en/contact-studio-interior-design-bratislava-vienna')}): phones, messengers, address and a request form.`, '');
  L.push('## Other languages', '');
  L.push(`- Russian: [${abs('/')}](${abs('/')})`);
  L.push(`- Ukrainian: [${abs('/ua')}](${abs('/ua')})`);
  L.push('');
  L.push('## Optional', '');
  L.push(`- [Full text of the English website](${abs('/llms-full.txt')})`);
  L.push(`- [Sitemap](${abs('/sitemap.xml')})`);
  L.push(`- [Privacy policy](${abs('/en/privacy')})`);
  return L.join('\n') + '\n';
}

export function llmsFullTxt(): string {
  const order = ['home', 'service', 'price', 'kitchen', 'project', 'article', 'portfolio', 'contact', 'shop'];
  const list = pages
    .filter((p) => p.lang === 'en' && order.includes(p.type))
    .sort((a, b) => order.indexOf(a.type) - order.indexOf(b.type) || a.path.localeCompare(b.path));
  const L: string[] = [llmsTxt().trim(), '', '---', '', '# Full text of the English website', ''];
  for (const p of list) {
    L.push(`## ${plain(p.h1 || p.title)}`, '', `URL: ${abs(p.path)}`);
    if (p.description) L.push('', `> ${p.description}`);
    const body = pageMarkdown(p);
    if (body) L.push('', body);
    L.push('', '---', '');
  }
  return L.join('\n') + '\n';
}
