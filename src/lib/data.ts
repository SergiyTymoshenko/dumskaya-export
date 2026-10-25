import type { Lang } from './i18n';

export type Part = { t: 'p'; html: string } | { t: 'ul' | 'ol'; items: string[] };
export type Img = { id: string; alt: string };
export type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'text'; parts: Part[] }
  /** docs: на странице проекта — листы технической документации: отдельный блок после фото, с заголовком секции */
  | { type: 'gallery'; images: Img[]; docs?: boolean }
  | { type: 'cards'; items: { title: string; href: string | null; image: Img | null }[] }
  | { type: 'buttons'; items: { text: string; href: string | null }[] }
  | { type: 'faq'; items: { q: string; a: string }[] }
  | { type: 'facts'; title?: string; rows: [string, string][] }
  | { type: 'form'; title?: string; text?: string }
  | { type: 'figure'; image: Img; caption?: string }
  /** видео с YouTube: превью — фото проекта (poster — id картинки), плеер грузится только по нажатию */
  | { type: 'video'; youtube: string; poster?: string }
  /** карточки товаров магазина (русские адреса; на других языках — те же товары на языке страницы) */
  | { type: 'products'; items: string[] }
  /** контакты студии: адрес, телефоны языка страницы (на SK — словацкий, на DE — австрийский), e-mail */
  | { type: 'contacts' };
export type Section = { id: string; blocks: Block[] };
export type Page = {
  path: string; lang: Lang; type: string; group: string | null;
  title: string; description: string; h1: string; og_image: string | null;
  alternates: Partial<Record<Lang, string>>;
  sections: Section[];
  /** посадочная страница региона: ключ телефона из site.json (sk, at, ua, us) — он стоит в шапке и под заголовком */
  phone?: string;
  /** телефон другого региона (например, украинский на странице Праги): подпись «Телефон» без города */
  phone_plain?: boolean;
};
export type Project = {
  path: string; group: 'residential' | 'commercial' | 'architecture';
  alternates: Partial<Record<Lang, string>>; cover: string | null;
  title: Partial<Record<Lang, string>>; area: number | null;
  facts?: Partial<Record<Lang, Record<string, string>>>;
};
export type ImageFile = { name: string; width: number; height: number; files: [number, string][] };

const pageModules = import.meta.glob<Page>('/content/pages/**/*.json', { eager: true, import: 'default' });
export const pages: Page[] = Object.values(pageModules);
export const pageByPath = new Map(pages.map((p) => [p.path, p]));

import projectsJson from '../../content/projects.json';
import manifestJson from '../../content/image-manifest.json';
import imagesJson from '../../content/images.json';
import siteJson from '../../content/site.json';

export const projects = projectsJson as Project[];
export const manifest = manifestJson as Record<string, ImageFile>;
export const imageMeta = imagesJson as Record<string, { width: number; height: number; alt: Record<Lang, string> }>;
export const site = siteJson as any;

export type Phone = { tel: string; text: string; key: string; city: Record<Lang, string>; label: Record<Lang, string> };
/** Телефоны языка: словацкая версия — только словацкий номер, немецкая — только австрийский, остальные — все номера студии. */
export const LANG_PHONES: Partial<Record<Lang, string[]>> = { sk: ['sk'], de: ['at'] };

/** Телефон страницы: телефон региона у посадочных страниц, иначе основной (Братислава).
 *  На SK и DE — всегда номер своего языка; если регион страницы другой — подпись без города. */
export function phoneFor(page: Page): { phone: Phone; regional: boolean; plain: boolean } {
  const all = site.contacts.phones as Phone[];
  const only = LANG_PHONES[page.lang];
  if (only) {
    const phone = all.find((p) => p.key === only[0]) || all[0];
    return { phone, regional: !!page.phone, plain: !!page.phone && page.phone !== phone.key };
  }
  const own = page.phone ? all.find((p) => p.key === page.phone) : undefined;
  return { phone: own || all[0], regional: !!own, plain: !!own && !!page.phone_plain };
}

/** Телефоны в подвале, меню, на главной и в «Контактах»: все номера студии (на SK и DE — только номер своего языка). */
export function langPhones(lang: Lang): Phone[] {
  const all = site.contacts.phones as Phone[];
  const keys = LANG_PHONES[lang] || ['sk', 'ua', 'at'];
  return all.filter((p) => keys.includes(p.key));
}

/** Телефоны в подвале, меню и на главной для страницы. */
export function pagePhones(page: Page): Phone[] {
  return langPhones(page.lang);
}

/** Адрес той же страницы на другом языке (или главная этого языка, если перевода нет). */
export function altPath(page: Page, lang: Lang): string {
  return page.alternates[lang] || (lang === 'ru' ? '/' : `/${lang}`);
}

/** Перевод русского адреса на язык lang по языковым парам страниц. */
export function localize(ruPath: string | null | undefined, lang: Lang): string | null {
  if (!ruPath) return null;
  if (lang === 'ru') return ruPath;
  const p = pageByPath.get(ruPath);
  return p?.alternates[lang] || null;
}

export function projectsFor(lang: Lang) {
  return projects
    .filter((p) => p.alternates[lang] && pageByPath.has(p.alternates[lang]!))
    .map((p) => ({ ...p, href: p.alternates[lang]!, label: p.title[lang] || p.title.ru || '' }));
}

/** Разбивает подпись карточки на название и строку с площадью: «Квартира в Вене 58 м²» → [«Квартира в Вене», «58 м²»]. */
export function splitCaption(text: string): [string, string] {
  const re = /,?\s*\(?\s*(?:тераса|терраса|terrace|terasa|Terrasse)?\s*\d{1,4}\s*(?:м²|м2|m²|m2)\s*(?:terrace|тераса|терраса|terasa|Terrasse)?\)?/gi;
  const areas = (text.match(re) || []).map((s) => s.replace(/^[,\s(]+|[)\s]+$/g, '').trim());
  const name = text.replace(re, '').replace(/\s{2,}/g, ' ').replace(/[,\s]+$/, '').trim();
  return [name, areas.join(', ')];
}

export function firstGallery(page: Page): Img[] {
  for (const s of page.sections) for (const b of s.blocks) if (b.type === 'gallery') return b.images;
  return [];
}

/** Все фото страницы для поисковиков: галереи и рисунки (планировки). */
export function seoImages(page: Page): Img[] {
  const out: Img[] = [];
  for (const s of page.sections) for (const b of s.blocks) {
    if (b.type === 'gallery') out.push(...b.images);
    else if (b.type === 'figure' && b.image) out.push(b.image);
  }
  return out;
}

export function allGalleryImages(page: Page): Img[] {
  const out: Img[] = [];
  for (const s of page.sections) for (const b of s.blocks) if (b.type === 'gallery') out.push(...b.images);
  return out;
}

export function isServicesSection(s: Section) {
  const h = s.blocks.find((b) => b.type === 'heading') as any;
  return !!h && /^(Услуги студии|Послуги студії|Interior design studio services|Our (interior design )?services|Services|Služby štúdia|Leistungen des Studios)/i.test(h.text);
}

/** Все страницы данного типа на языке lang (порядок — по русскому адресу). */
export function pagesOfType(type: string, lang: Lang) {
  return pages.filter((p) => p.type === type && p.lang === lang).sort((a, b) => (a.alternates.ru || a.path).localeCompare(b.alternates.ru || b.path));
}

/** Текст страницы без блока «Услуги студии». */
export function mainParts(page: Page): Part[] {
  return page.sections.filter((s) => !isServicesSection(s)).flatMap((s) => s.blocks)
    .filter((b) => b.type === 'text').flatMap((b: any) => b.parts as Part[]);
}

export function servicesCards(page: Page) {
  const s = page.sections.find(isServicesSection);
  return ((s?.blocks.find((b) => b.type === 'cards') as any)?.items || []) as { title: string; href: string | null; image: Img | null }[];
}

// выкладка (scripts/deploy.sh) ставит HOME_CATALOG_LINKS=off, пока каталог не открыт на домене — ссылок тогда нет
const homeLinksOn = () => !!site.home_catalog?.enabled && process.env.HOME_CATALOG_LINKS !== 'off';
/** Каталог фабрик DUMSKAYA HOME на языке страницы или null — ссылки выключены (content/site.json → home_catalog). */
export function homeCatalog(lang: Lang): string | null {
  const c = site.home_catalog;
  return homeLinksOn() && c.url?.[lang] ? c.url[lang] : null;
}
/** Страница студии, на которой стоит фраза со ссылкой на каталог (страницы дизайна квартир и дизайн-пакетов). */
export function catalogNoteOn(page: Page): boolean {
  const c = site.home_catalog;
  return homeLinksOn() && (c.pages || []).includes(page.alternates?.ru || page.path);
}

export function homePath(lang: Lang) {
  return lang === 'ru' ? '/' : `/${lang}`;
}

export const plain = (h: string) => h.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim();

/** Хлебные крошки страницы (видимые и для разметки BreadcrumbList). */
/** Название товара или раздела магазина — как в заголовке страницы (без «| DUMSKAYA DESIGN» и артикула в скобках). */
export function shopName(page: Page): string {
  return page.title.replace(/\s*\|\s*DUMSKAYA DESIGN\s*$/, '').replace(/\s*\([^)]*\)\s*$/, '');
}

export function crumbsFor(page: Page): { label: string; href: string | null }[] {
  const lang = page.lang;
  const t: any = {
    ru: { home: 'Главная', projects: 'Проекты', kitchens: 'Кухни', tips: 'Советы', shop: 'Магазин', prices: 'Цены', contacts: 'Контакты' },
    ua: { home: 'Головна', projects: 'Проєкти', kitchens: 'Кухні', tips: 'Поради', shop: 'Магазин', prices: 'Ціни', contacts: 'Контакти' },
    en: { home: 'Home', projects: 'Projects', kitchens: 'Kitchens', tips: 'Tips', shop: 'Shop', prices: 'Prices', contacts: 'Contact' },
    sk: { home: 'Domov', projects: 'Projekty', kitchens: 'Kuchyne', tips: 'Tipy', shop: 'Obchod', prices: 'Ceny', contacts: 'Kontakt' },
    de: { home: 'Startseite', projects: 'Projekte', kitchens: 'Küchen', tips: 'Tipps', shop: 'Shop', prices: 'Preise', contacts: 'Kontakt' },
  }[lang];
  const home = { label: t.home, href: homePath(lang) };
  const last = (label: string) => ({ label, href: page.path });
  const L = (ru: string) => localize(ru, lang);
  switch (page.type) {
    case 'home': return [home];
    case 'portfolio': return [home, last(t.projects)];
    case 'project': {
      const pr = projects.find((p) => p.alternates[lang] === page.path);
      return [home, { label: t.projects, href: L('/proekty-interior-design') }, last(pr?.title[lang] || page.h1)];
    }
    case 'kitchen': {
      const code = (page.alternates.ru || page.path).match(/k-?(\d{2})/i)?.[1];
      return [home, { label: t.kitchens, href: L('/kupkuhni-na-zakaz-vienna-bratislava') }, last(code ? `K-${code}` : page.h1)];
    }
    case 'article': return [home, { label: t.tips, href: null }, last(page.h1)];
    case 'contact': return [home, last(t.contacts)];
    case 'shop': {
      const ru = page.alternates.ru || page.path;
      if (ru === '/shop') return [home, last(t.shop)];
      return [home, { label: t.shop, href: L('/shop') }, last(shopName(page))];
    }
    default: {
      const ru = page.alternates.ru || page.path;
      if (ru === '/price-interior-design-bratislava-wien-praha') return [home, last(t.prices)];
      const menu = (site.menu[lang] || []) as any[];
      const group = menu.find((m) => m.children?.some((c: any) => c.href === page.path));
      const prices = group && /Цен|Ціни|Prices|Ceny|Preise/.test(group.label);
      return [home, ...(group ? [{ label: group.label, href: prices ? L('/price-interior-design-bratislava-wien-praha') : null }] : []), last(page.h1)];
    }
  }
}

/** Карточки товаров магазина для блока products: страница товара на языке lang, название, артикул, первое фото. */
export function productCards(ruPaths: string[], lang: Lang) {
  return ruPaths.flatMap((ru) => {
    const href = localize(ru, lang);
    const p = href ? pageByPath.get(href) : undefined;
    if (!p) return [];
    const code = p.title.match(/\((TDD-[^)]+)\)/)?.[1] || '';
    return [{ href: p.path, title: shopName(p), sub: code, image: firstGallery(p)[0]?.id || null }];
  });
}
