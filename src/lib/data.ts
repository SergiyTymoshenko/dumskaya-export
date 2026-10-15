import type { Lang } from './i18n';

export type Part = { t: 'p'; html: string } | { t: 'ul' | 'ol'; items: string[] };
export type Img = { id: string; alt: string };
export type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'text'; parts: Part[] }
  | { type: 'gallery'; images: Img[] }
  | { type: 'cards'; items: { title: string; href: string | null; image: Img | null }[] }
  | { type: 'buttons'; items: { text: string; href: string | null }[] }
  | { type: 'form' };
export type Section = { id: string; blocks: Block[] };
export type Page = {
  path: string; lang: Lang; type: string; group: string | null;
  title: string; description: string; h1: string; og_image: string | null;
  alternates: Partial<Record<Lang, string>>;
  sections: Section[];
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
  const re = /,?\s*\(?\s*(?:тераса|терраса|terrace)?\s*\d{1,4}\s*(?:м²|м2|m²|m2)\s*(?:terrace|тераса|терраса)?\)?/gi;
  const areas = (text.match(re) || []).map((s) => s.replace(/^[,\s(]+|[)\s]+$/g, '').trim());
  const name = text.replace(re, '').replace(/\s{2,}/g, ' ').replace(/[,\s]+$/, '').trim();
  return [name, areas.join(', ')];
}

export function firstGallery(page: Page): Img[] {
  for (const s of page.sections) for (const b of s.blocks) if (b.type === 'gallery') return b.images;
  return [];
}

export function allGalleryImages(page: Page): Img[] {
  const out: Img[] = [];
  for (const s of page.sections) for (const b of s.blocks) if (b.type === 'gallery') out.push(...b.images);
  return out;
}

export function isServicesSection(s: Section) {
  const h = s.blocks.find((b) => b.type === 'heading') as any;
  return !!h && /^(Услуги студии|Послуги студії|Interior design studio services|Our services|Services)/i.test(h.text);
}
