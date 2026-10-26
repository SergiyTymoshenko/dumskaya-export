// Данные сайта: товары (home/data/catalog.json), фото (home/data/image-manifest.json) и все страницы сайта
// с адресами на пяти языках. Файлы читаются при сборке, в браузер не попадают.
import fs from 'node:fs';
import path from 'node:path';
import { LANGS, DEFAULT, prefix, homePath, ui, type Lang } from './i18n';
import { SUFFIX, T_MAX, D_MAX, fit, fitTitle, cutMiddle, productTitle, productDesc, listTitle, listDesc, brandTitle, brandDesc, homeDesc } from './seo';

const DATA = import.meta.env.HOME_DATA as string;
const read = (f: string, d: any) => { try { return JSON.parse(fs.readFileSync(path.join(DATA, f), 'utf8')); } catch { return d; } };
const raw = read('catalog.json', { taxonomy: null, brands: {}, products: [] });

export type L = Record<Lang, string>;
export type Pic = { src: string; w: number; h: number; name: string; title?: string };
export type Product = {
  sku: string; factory: string; brand: string; brand_slug: string; type: string; category: string; department: string;
  place: 'indoor' | 'outdoor' | 'both'; model: string; full_model: string; collection: string; collection_name: string;
  designer: string; year: string; new: boolean; rooms: string[]; name: L; path: L; images: Pic[]; drawings: Pic[];
  text: Partial<L>; facts: { tech?: any; versions?: any[]; finishes?: Record<string, string[]> };
  /** фабрика выложена (content/home/publish.json) и товар не скрыт — только такие идут в карту сайта и llms.txt */
  published?: boolean;
};
export type ImageFile = { width: number; height: number; files: [number, string][]; cut?: boolean; bg?: string };

export const tax = raw.taxonomy;
export const brandsInfo: Record<string, { name: string; slug: string; country: string; site: string; legal?: string; ru?: string; published?: { since: string } | null }> = raw.brands;
export const products: Product[] = raw.products;
export const manifest: Record<string, ImageFile> = read('image-manifest.json', {});
export const site = JSON.parse(fs.readFileSync(path.join(DATA, '../../content/site.json'), 'utf8'));
/** настройки DUMSKAYA HOME: коды подтверждения Search Console, Яндекс.Вебмастера, Bing (content/home/site.json) */
export const homeSite = (() => { try { return JSON.parse(fs.readFileSync(path.join(DATA, '../../content/home/site.json'), 'utf8')); } catch { return {}; } })();

export const typeName = (t: string, l: Lang) => tax.types[t][l] as string;
export const catName = (c: string, l: Lang) => tax.categories[c].name[l] as string;
export const deptName = (d: string, l: Lang) => tax.departments.find((x: any) => x.id === d).name[l] as string;
export const roomName = (r: string, l: Lang) => tax.rooms[r][l] as string;
const by = <T,>(arr: T[], key: (x: T) => string) => arr.reduce((m, x) => ((m[key(x)] ||= []).push(x), m), {} as Record<string, T[]>);

export const byCategory = by(products, (p) => p.category);
export const byBrand = by(products, (p) => p.brand_slug);
export const byCollection = by(products, (p) => `${p.factory}/${p.collection}`);
export const outdoorProducts = products.filter((p) => p.place !== 'indoor');
export const departments = (tax?.departments || []).map((d: any) => ({ ...d, categories: d.categories.filter((c: string) => byCategory[c]?.length) }))
  .filter((d: any) => d.categories.length);
export const brandList = Object.keys(byBrand).map((slug) => ({ slug, name: byBrand[slug][0].brand, factory: byBrand[slug][0].factory }))
  .sort((a, b) => byBrand[b.slug].length - byBrand[a.slug].length);

/** Список названий фабрик для текста: «Minotti, Poliform и Baxter» */
export function brandNames(l: Lang, max = 6) {
  const names = brandList.slice(0, max).map((b) => b.name);
  if (names.length < 2) return names.join('');
  const and = { en: 'and', ru: 'и', de: 'und', fr: 'et', es: 'y' }[l];
  return `${names.slice(0, -1).join(', ')} ${and} ${names.at(-1)}`;
}
/** Продукты по порядку: новинки, потом по названию (фабрики перемешаны) */
export const sortProducts = (ps: Product[], l: Lang) => [...ps].sort((a, b) => Number(b.new) - Number(a.new) || a.name[l].localeCompare(b.name[l]));
/** Для списков нескольких фабрик (раздел, новинки на главной): фабрики вперемешку по одной — в первом ряду
 *  все фабрики раздела, а не одна (у Baxter новинок больше всех); у каждой фабрики сначала её новинки, потом по названию.
 *  Первыми идут фабрики с новинками. */
export function mixByBrand(ps: Product[], l: Lang) {
  const groups = new Map<string, Product[]>();
  for (const p of sortProducts(ps, l)) { if (!groups.has(p.brand_slug)) groups.set(p.brand_slug, []); groups.get(p.brand_slug)!.push(p); }
  const fresh = (x: Product[]) => x.filter((p) => p.new).length;
  const lists = [...groups.values()].sort((a, b) => fresh(b) - fresh(a) || b.length - a.length);
  const out: Product[] = [];
  for (let i = 0; lists.some((x) => i < x.length); i++) for (const x of lists) if (i < x.length) out.push(x[i]);
  return out;
}

// ---------- страницы ----------
export type Crumb = { label: string; href?: string };
export type HPage = {
  kind: 'home' | 'dept' | 'cat' | 'outdoor' | 'brands' | 'brand' | 'product' | 'contact' | 'privacy';
  lang: Lang; path: string; alt: Partial<L>; title: string; description: string; h1: string; crumbs: Crumb[];
  key?: string; product?: Product; image?: string;
};
const STATIC: Record<string, L> = {
  brands: { en: 'brands', ru: 'fabriki', de: 'marken', fr: 'marques', es: 'marcas' },
  contact: { en: 'contact', ru: 'kontakty', de: 'kontakt', fr: 'contact', es: 'contacto' },
  privacy: { en: 'privacy', ru: 'privacy', de: 'datenschutz', fr: 'confidentialite', es: 'privacidad' },
};
const mk = (f: (l: Lang) => string) => Object.fromEntries(LANGS.map((l) => [l, f(l)])) as L;
export const paths = {
  home: mk((l) => homePath(l)),
  dept: (d: any) => mk((l) => `${prefix(l)}/${d.slug[l]}`),
  cat: (c: string) => mk((l) => `${prefix(l)}/${tax.categories[c].slug[l]}`),
  outdoor: () => mk((l) => `${prefix(l)}/${tax.outdoor.slug[l]}`),
  brands: mk((l) => `${prefix(l)}/${STATIC.brands[l]}`),
  brand: (slug: string) => mk((l) => `${prefix(l)}/${slug}`),
  contact: mk((l) => `${prefix(l)}/${STATIC.contact[l]}`),
  privacy: mk((l) => `${prefix(l)}/${STATIC.privacy[l]}`),
};
/** Фото для списков: предметный снимок на белом фоне, если есть, иначе первое */
export const coverOf = (p: Product) => p.images.find((im) => manifest[im.name]?.cut) || p.images[0];
const firstImage = (ps: Product[]) => ps.find((p) => p.images[0] && manifest[p.images[0].name])?.images[0].name || ps[0]?.images[0]?.name;

function catBrands(ps: Product[]) {
  const n = by(ps, (p) => p.brand);
  return Object.keys(n).sort((a, b) => n[b].length - n[a].length);
}

const COUNTRY: Record<string, Record<Lang, string>> = {
  'Италия': { en: 'Italy', ru: 'Италия', de: 'Italien', fr: 'Italie', es: 'Italia' },
  'Бельгия': { en: 'Belgium', ru: 'Бельгия', de: 'Belgien', fr: 'Belgique', es: 'Bélgica' },
};
export const countryName = (factory: string, l: Lang) => { const c = brandsInfo[factory]?.country || ''; return COUNTRY[c]?.[l] || c; };
const allItalian = (ps: Product[]) => ps.every((p) => brandsInfo[p.factory]?.country === 'Италия');

export function allPages(): HPage[] {
  const out: HPage[] = [];
  for (const l of LANGS) {
    const T = ui(l);
    const home = { label: T.home, href: homePath(l) };
    out.push({ kind: 'home', lang: l, path: paths.home[l], alt: paths.home, title: T.homeTitle, h1: T.home_h1,
      description: homeDesc(brandNames(l, 4), l), crumbs: [], image: firstImage(products) });
    const list = (kind: HPage['kind'], key: string | undefined, name: string, ps: Product[], path: L, crumbs: Crumb[]) => out.push({
      kind, lang: l, key, path: path[l], alt: path, h1: name, title: listTitle(name, catBrands(ps), l),
      description: listDesc(name, ps.length, catBrands(ps), allItalian(ps), l), crumbs, image: firstImage(ps) });
    for (const d of departments) {
      const ps = products.filter((p) => p.department === d.id);
      list('dept', d.id, d.name[l], ps, paths.dept(d), [home, { label: d.name[l] }]);
      for (const c of d.categories)
        list('cat', c, catName(c, l), byCategory[c], paths.cat(c), [home, { label: d.name[l], href: paths.dept(d)[l] }, { label: catName(c, l) }]);
    }
    if (outdoorProducts.length) list('outdoor', undefined, tax.outdoor.name[l], outdoorProducts, paths.outdoor(), [home, { label: tax.outdoor.name[l] }]);
    out.push({ kind: 'brands', lang: l, path: paths.brands[l], alt: paths.brands, h1: T.brandsTitle, title: fitTitle([T.brandsTitle]),
      // фабрик всё больше — в описание (до 155 знаков) берём столько, сколько помещается
      description: fit([12, 10, 8, 6, 4, 3].map((k) => `${T.brandsLead} ${brandNames(l, k)}.`), D_MAX), crumbs: [home, { label: T.brandsTitle }] });
    for (const b of brandList) {
      const ps = byBrand[b.slug];
      const cats = [...new Set(ps.map((p) => p.category))].sort((x, y) => ps.filter((p) => p.category === y).length - ps.filter((p) => p.category === x).length).map((c) => catName(c, l));
      const lighting = ps.filter((p) => p.department === 'lighting').length > ps.length / 2;
      const ru = brandsInfo[b.factory]?.ru || '';
      out.push({ kind: 'brand', lang: l, key: b.slug, path: paths.brand(b.slug)[l], alt: paths.brand(b.slug), h1: b.name,
        title: brandTitle(b.name, ru, lighting, cats, l), description: brandDesc(b.name, ru, countryName(b.factory, l), ps.length, cats, l),
        crumbs: [home, { label: T.brands, href: paths.brands[l] }, { label: b.name }], image: firstImage(ps) });
    }
    for (const p of products) {
      out.push({ kind: 'product', lang: l, key: p.sku, product: p, path: p.path[l], alt: p.path, h1: p.name[l],
        title: productTitle(p.name[l], p.brand, l), description: productDesc(p.name[l], p.brand, p.designer, l),
        crumbs: [home, { label: catName(p.category, l), href: paths.cat(p.category)[l] }, { label: p.brand, href: paths.brand(p.brand_slug)[l] }, { label: p.name[l] }],
        image: p.images[0]?.name });
    }
    out.push({ kind: 'contact', lang: l, path: paths.contact[l], alt: paths.contact, h1: T.contact_h1, title: fitTitle([T.contactTitle]),
      description: T.contactDesc, crumbs: [home, { label: T.contact_h1 }] });
    out.push({ kind: 'privacy', lang: l, path: paths.privacy[l], alt: paths.privacy, h1: T.privacy, title: fitTitle([T.privacy]),
      description: T.privacyDesc, crumbs: [home, { label: T.privacy }] });
  }
  // заголовки не повторяются: если у двух товаров они всё же совпали (длинные названия одной серии),
  // к названию добавляется наш артикул — он в конце и остаётся после сокращения
  const seen = new Map<string, number>();
  for (const pg of out) seen.set(pg.title, (seen.get(pg.title) || 0) + 1);
  for (const pg of out) if (pg.kind === 'product' && (seen.get(pg.title) || 0) > 1 && pg.product)
    pg.title = cutMiddle(`${pg.product.name[pg.lang]} ${pg.product.sku}`, T_MAX);
  return out;
}

/** Телефоны — только на русской версии (Братислава и Вена); на остальных языках связь через форму (решено 25.10.2026) */
export function phones(l: Lang) {
  return l === 'ru' ? site.contacts.phones.filter((p: any) => p.key === 'sk' || p.key === 'at') : [];
}
/** e-mail каталога — content/home/site.json (пока пусто: адрес добавим позже) */
export const homeEmail: string = homeSite.email || '';
export const cityName = (p: any, l: Lang) => ({ sk: { en: 'Bratislava', ru: 'Братислава', de: 'Bratislava', fr: 'Bratislava', es: 'Bratislava' }, at: { en: 'Vienna', ru: 'Вена', de: 'Wien', fr: 'Vienne', es: 'Viena' } } as any)[p.key][l];
export const DEFAULT_LANG = DEFAULT;
