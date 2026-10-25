// Данные сайта: товары (home/data/catalog.json), фото (home/data/image-manifest.json) и все страницы сайта
// с адресами на пяти языках. Файлы читаются при сборке, в браузер не попадают.
import fs from 'node:fs';
import path from 'node:path';
import { LANGS, DEFAULT, prefix, homePath, ui, type Lang } from './i18n';

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
};
export type ImageFile = { width: number; height: number; files: [number, string][]; cut?: boolean; bg?: string };

export const tax = raw.taxonomy;
export const brandsInfo: Record<string, { name: string; slug: string; country: string; site: string }> = raw.brands;
export const products: Product[] = raw.products;
export const manifest: Record<string, ImageFile> = read('image-manifest.json', {});
export const site = JSON.parse(fs.readFileSync(path.join(DATA, '../../content/site.json'), 'utf8'));

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
const SUFFIX = ' | DUMSKAYA HOME';
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
const listJoin = (xs: string[], l: Lang, max = 3) => {
  const s = xs.slice(0, max);
  const and = { en: 'and', ru: 'и', de: 'und', fr: 'et', es: 'y' }[l];
  return s.length < 2 ? s.join('') : `${s.slice(0, -1).join(', ')} ${and} ${s.at(-1)}`;
};

export function allPages(): HPage[] {
  const out: HPage[] = [];
  for (const l of LANGS) {
    const T = ui(l);
    const home = { label: T.home, href: homePath(l) };
    out.push({ kind: 'home', lang: l, path: paths.home[l], alt: paths.home, title: T.homeTitle, h1: T.home_h1,
      description: T.home_lead(brandNames(l, 4)).split('. ')[0] + '.', crumbs: [], image: firstImage(products) });
    for (const d of departments) {
      const ps = products.filter((p) => p.department === d.id);
      out.push({ kind: 'dept', lang: l, key: d.id, path: paths.dept(d)[l], alt: paths.dept(d), h1: d.name[l],
        title: T.catTitle(d.name[l], listJoin(catBrands(ps), l)) + SUFFIX,
        description: T.catDesc(d.name[l], ps.length, listJoin(catBrands(ps), l)), crumbs: [home, { label: d.name[l] }], image: firstImage(ps) });
      for (const c of d.categories) {
        const cps = byCategory[c];
        const nm = catName(c, l);
        out.push({ kind: 'cat', lang: l, key: c, path: paths.cat(c)[l], alt: paths.cat(c), h1: nm,
          title: T.catTitle(nm, listJoin(catBrands(cps), l)) + SUFFIX, description: T.catDesc(nm, cps.length, listJoin(catBrands(cps), l)),
          crumbs: [home, { label: d.name[l], href: paths.dept(d)[l] }, { label: nm }], image: firstImage(cps) });
      }
    }
    if (outdoorProducts.length) out.push({ kind: 'outdoor', lang: l, path: paths.outdoor()[l], alt: paths.outdoor(), h1: tax.outdoor.name[l],
      title: T.catTitle(tax.outdoor.name[l], listJoin(catBrands(outdoorProducts), l)) + SUFFIX,
      description: T.catDesc(tax.outdoor.name[l], outdoorProducts.length, listJoin(catBrands(outdoorProducts), l)),
      crumbs: [home, { label: tax.outdoor.name[l] }], image: firstImage(outdoorProducts) });
    out.push({ kind: 'brands', lang: l, path: paths.brands[l], alt: paths.brands, h1: T.brandsTitle, title: T.brandsTitle + SUFFIX,
      description: T.brandsLead + ' ' + brandNames(l, 12) + '.', crumbs: [home, { label: T.brandsTitle }] });
    for (const b of brandList) {
      const ps = byBrand[b.slug];
      const cats = [...new Set(ps.map((p) => p.category))].sort((x, y) => byCategory[y].length - byCategory[x].length).map((c) => catName(c, l).toLowerCase());
      out.push({ kind: 'brand', lang: l, key: b.slug, path: paths.brand(b.slug)[l], alt: paths.brand(b.slug), h1: b.name,
        title: T.brandTitle(b.name) + SUFFIX, description: T.brandDesc(b.name, ps.length, cats.slice(0, 4).join(', ')),
        crumbs: [home, { label: T.brands, href: paths.brands[l] }, { label: b.name }], image: firstImage(ps) });
    }
    for (const p of products) {
      const d = departments.find((x: any) => x.id === p.department);
      out.push({ kind: 'product', lang: l, key: p.sku, product: p, path: p.path[l], alt: p.path, h1: p.name[l],
        title: `${p.name[l]} — ${p.brand}${SUFFIX}`, description: T.prodDesc(p.name[l], p.brand, p.designer),
        crumbs: [home, { label: catName(p.category, l), href: paths.cat(p.category)[l] }, { label: p.brand, href: paths.brand(p.brand_slug)[l] }, { label: p.name[l] }],
        image: p.images[0]?.name });
    }
    out.push({ kind: 'contact', lang: l, path: paths.contact[l], alt: paths.contact, h1: T.contact_h1, title: T.contactTitle + SUFFIX,
      description: T.contact_lead, crumbs: [home, { label: T.contact_h1 }] });
    out.push({ kind: 'privacy', lang: l, path: paths.privacy[l], alt: paths.privacy, h1: T.privacy, title: T.privacy + SUFFIX,
      description: '', crumbs: [home, { label: T.privacy }] });
  }
  return out;
}

/** Телефоны: на немецком — только австрийский номер (как у сайта студии), на остальных — Братислава и Вена */
export function phones(l: Lang) {
  const all = site.contacts.phones.filter((p: any) => p.key === 'sk' || p.key === 'at');
  return l === 'de' ? all.filter((p: any) => p.key === 'at') : all;
}
export const cityName = (p: any, l: Lang) => ({ sk: { en: 'Bratislava', ru: 'Братислава', de: 'Bratislava', fr: 'Bratislava', es: 'Bratislava' }, at: { en: 'Vienna', ru: 'Вена', de: 'Wien', fr: 'Vienne', es: 'Viena' } } as any)[p.key][l];
export const DEFAULT_LANG = DEFAULT;
