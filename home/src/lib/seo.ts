// Title и description страниц DUMSKAYA HOME — как люди ищут на каждом языке, в пределах сайта студии:
// title ≤ 60 знаков, description ≤ 155 (scripts/check_home.py проверяет). Из вариантов берётся первый, что помещается.
//   товар: «Poliform Westside sofa — price on request», «Диван Westside Poliform — цена по запросу»,
//          «Poliform Westside Sofa – Preis auf Anfrage», «Canapé Westside Poliform – prix sur demande»,
//          «Sofá Westside de Poliform – precio a consultar» (фабрика + модель — так ищут конкретное изделие);
//   категория: «Sofas by Minotti, Flexform and Baxter», «Диваны Minotti, Flexform и Baxter»…;
//   фабрика: «Minotti furniture: sofas, armchairs…», по-русски — и русское написание («Мебель Minotti (Минотти)»).
// В описании — что на странице, «цена по запросу», доставка по всему миру (решено 25.10.2026: заявки ждём из разных стран)
// и, если помещается, заказ через студию в Братиславе и Вене (факты студии).
import type { Lang } from './i18n';

export const T_MAX = 60, D_MAX = 155;
export const SUFFIX = ' | DUMSKAYA HOME';
export const fit = (xs: string[], max: number) => xs.find((x) => x.length <= max) || xs[xs.length - 1].slice(0, max - 1).trimEnd() + '…';
export const fitTitle = (base: string[]) => fit([...base.map((b) => b + SUFFIX), ...base], T_MAX);

const AND: Record<Lang, string> = { en: 'and', ru: 'и', de: 'und', fr: 'et', es: 'y' };
export const join = (xs: string[], l: Lang, max = 3) => {
  const s = xs.slice(0, max);
  return s.length < 2 ? s.join('') : `${s.slice(0, -1).join(', ')} ${AND[l]} ${s.at(-1)}`;
};
const PRICE: Record<Lang, string> = { en: 'price on request', ru: 'цена по запросу', de: 'Preis auf Anfrage', fr: 'prix sur demande', es: 'precio a consultar' };
const DASH: Record<Lang, string> = { en: ' — ', ru: ' — ', de: ' – ', fr: ' – ', es: ' – ' };
// «заказ через студию в Братиславе и Вене» — студия работает в двух городах, на немецком первой — Вена
const VIA: Record<Lang, string> = {
  en: 'order through our studio in Bratislava and Vienna', ru: 'заказ через нашу студию в Братиславе и Вене',
  de: 'Bestellung über unser Studio in Wien und Bratislava', fr: 'commande via notre studio à Bratislava et Vienne',
  es: 'pedido a través de nuestro estudio en Bratislava y Viena',
};
const SHIP: Record<Lang, string> = {
  en: 'worldwide delivery', ru: 'доставка по всему миру', de: 'Lieferung weltweit', fr: 'livraison dans le monde entier',
  es: 'envío a todo el mundo',
};
const ORIGIN: Record<Lang, [string, string]> = {          // фабрики: все итальянские / не только
  en: ['Italian makers', 'European makers'], ru: ['итальянских фабрик', 'европейских фабрик'],
  de: ['italienischer Hersteller', 'europäischer Hersteller'], fr: ['de fabricants italiens', 'de fabricants européens'],
  es: ['de fábricas italianas', 'de fábricas europeas'],
};

/** Товар: фабрика + модель + тип в порядке, как ищут на языке */
export function productTitle(name: string, brand: string, l: Lang) {
  const base = l === 'en' || l === 'de' ? `${brand} ${name}` : l === 'es' ? `${name} de ${brand}` : `${name} ${brand}`;
  return fitTitle([`${base}${DASH[l]}${PRICE[l]}`, base, name]);
}
export function productDesc(name: string, brand: string, designer: string, l: Lang) {
  const who = l === 'en' || l === 'de' ? `${brand} ${name}` : l === 'es' ? `${name} de ${brand}` : `${name} ${brand}`;
  const des = designer ? { en: `, design by ${designer}`, ru: `, дизайн ${designer}`, de: `, Design: ${designer}`, fr: `, design ${designer}`, es: `, diseño de ${designer}` }[l] : '';
  const what = { en: 'Sizes, finishes and photos', ru: 'Размеры, отделки и фото', de: 'Maße, Ausführungen und Fotos', fr: 'Dimensions, finitions et photos', es: 'Medidas, acabados y fotos' }[l];
  const p = PRICE[l][0].toUpperCase() + PRICE[l].slice(1);
  const sh = `${p}, ${SHIP[l]}`;
  return fit([`${who}${des}. ${what}. ${sh}, ${VIA[l]}.`, `${who}. ${what}. ${sh}, ${VIA[l]}.`, `${who}${des}. ${what}. ${sh}.`,
    `${who}. ${what}. ${sh}.`, `${who}. ${sh}.`], D_MAX);
}

/** Категория, раздел, «Для улицы»: название + главные фабрики */
export function listTitle(cat: string, brands: string[], l: Lang) {
  const by = (n: number) => (l === 'en' ? `${cat} by ${join(brands, l, n)}` : l === 'de' ? `${cat} von ${join(brands, l, n)}` : l === 'es' ? `${cat} de ${join(brands, l, n)}` : `${cat} ${join(brands, l, n)}`);
  return fitTitle(brands.length ? [by(3), by(2), by(1), cat] : [cat]);
}
export function listDesc(cat: string, n: number, brands: string[], italian: boolean, l: Lang) {
  const o = ORIGIN[l][italian ? 0 : 1], c = cat.toLowerCase();
  const tail = { en: 'Photos, sizes, finishes; price on request', ru: 'Фото, размеры, отделки; цена по запросу', de: 'Fotos, Maße, Ausführungen; Preis auf Anfrage', fr: 'Photos, dimensions, finitions ; prix sur demande', es: 'Fotos, medidas y acabados; precio a consultar' }[l];
  const head = (k: number) => ({
    en: `${n} ${c} from ${o}: ${join(brands, l, k)}.`,
    ru: `${cat}: ${n} ${plural(n, 'модель', 'модели', 'моделей')} ${o} — ${join(brands, l, k)}.`,
    de: `${n} ${cat} ${o}: ${join(brands, l, k)}.`,
    fr: `${n} modèles — ${c} ${o} : ${join(brands, l, k)}.`,
    es: `${n} modelos de ${c} ${o}: ${join(brands, l, k)}.`,
  }[l]);
  return fit([`${head(4)} ${tail}, ${SHIP[l]}, ${VIA[l]}.`, `${head(3)} ${tail}, ${SHIP[l]}.`, `${head(2)} ${tail}, ${SHIP[l]}.`,
    `${head(1)} ${tail}, ${SHIP[l]}.`, `${head(1)} ${tail}.`], D_MAX);
}

/** Фабрика: «Minotti furniture: sofas, armchairs…»; по-русски — с русским написанием */
export function brandTitle(brand: string, ru: string, lighting: boolean, cats: string[], l: Lang) {
  const kind = lighting ? { en: 'lighting', ru: 'Светильники', de: 'Leuchten', fr: 'Luminaires', es: 'Iluminación' }[l] : { en: 'furniture', ru: 'Мебель', de: 'Möbel', fr: 'Mobilier', es: 'Muebles' }[l];
  const name = l === 'ru' && ru ? `${kind} ${brand} (${ru})` : l === 'en' || l === 'de' ? `${brand} ${kind}` : `${kind} ${brand}`;
  const list = (k: number) => cats.slice(0, k).map((c) => c.toLowerCase()).join(', ');
  const sep = l === 'fr' ? ' : ' : ': ';
  return fitTitle([`${name}${sep}${list(3)}`, `${name}${sep}${list(2)}`, name]);
}
export function brandDesc(brand: string, ru: string, country: string, n: number, cats: string[], l: Lang) {
  const who = l === 'ru' && ru ? `${brand} (${ru})` : brand;
  const list = (k: number) => cats.slice(0, k).map((c) => c.toLowerCase()).join(', ');
  const head = (k: number) => ({
    en: `${who}, ${country}: ${n} models — ${list(k)}.`, ru: `${who}, ${country}: ${n} ${plural(n, 'модель', 'модели', 'моделей')} — ${list(k)}.`,
    de: `${who}, ${country}: ${n} Modelle – ${list(k)}.`, fr: `${who}, ${country} : ${n} modèles – ${list(k)}.`, es: `${who}, ${country}: ${n} modelos – ${list(k)}.`,
  }[l]);
  const tail = { en: 'Price on request', ru: 'Цена по запросу', de: 'Preis auf Anfrage', fr: 'Prix sur demande', es: 'Precio a consultar' }[l];
  return fit([`${head(5)} ${tail}, ${SHIP[l]}, ${VIA[l]}.`, `${head(4)} ${tail}, ${SHIP[l]}.`, `${head(3)} ${tail}, ${SHIP[l]}.`,
    `${head(2)} ${tail}, ${SHIP[l]}.`, `${head(2)} ${tail}.`], D_MAX);
}
export const homeDesc = (brands: string, l: Lang) => fit([
  { en: `Furniture and lighting by ${brands}. Price on request, ${SHIP.en}, ${VIA.en}.`, ru: `Мебель и свет ${brands}. Цена по запросу, ${SHIP.ru}, ${VIA.ru}.`,
    de: `Möbel und Leuchten von ${brands}. Preis auf Anfrage, ${SHIP.de}, ${VIA.de}.`, fr: `Mobilier et luminaires ${brands}. Prix sur demande, ${SHIP.fr}, ${VIA.fr}.`,
    es: `Muebles e iluminación de ${brands}. Precio a consultar, ${SHIP.es}, ${VIA.es}.` }[l],
  { en: `Furniture and lighting by ${brands}. Price on request, ${SHIP.en}.`, ru: `Мебель и свет ${brands}. Цена по запросу, ${SHIP.ru}.`,
    de: `Möbel und Leuchten von ${brands}. Preis auf Anfrage, ${SHIP.de}.`, fr: `Mobilier et luminaires ${brands}. Prix sur demande, ${SHIP.fr}.`,
    es: `Muebles e iluminación de ${brands}. Precio a consultar, ${SHIP.es}.` }[l],
  { en: `Furniture and lighting by ${brands}. Price on request.`, ru: `Мебель и свет ${brands}. Цена по запросу.`, de: `Möbel und Leuchten von ${brands}. Preis auf Anfrage.`,
    fr: `Mobilier et luminaires ${brands}. Prix sur demande.`, es: `Muebles e iluminación de ${brands}. Precio a consultar.` }[l],
], D_MAX);

function plural(n: number, one: string, few: string, many: string) {
  const a = n % 10, b = n % 100;
  return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many;
}
