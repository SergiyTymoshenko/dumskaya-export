// Дизайн-пакеты со страницы цен: название, цена за м², минимальная стоимость, описание и ссылки.
// Пакеты распознаются по заголовку/короткому абзацу с ценой в €/м²; всё, что идёт после, — их текст.
import { isServicesSection, plain, pageByPath, localize, type Page, type Part } from './data';
import type { Lang } from './i18n';

export type Pack = {
  title: string; name: string; price: string; note: string;
  parts: Part[]; buttons: { text: string; href: string | null }[];
  href: string | null; min: string;
};
export type Extra = { title: string; parts: Part[]; buttons: { text: string; href: string | null }[] };

const PRICE = /(€\s?\d[\d\s,.–-]*(?:€)?\s*\/\s*m²|\d[\d\s,.–-]*\s*€\s*\/\s*[мm]²)/i;
const isPack = (t: string) => PRICE.test(t) && t.length < 200;
const MIN = /(Минимальн|Мінімальн|Minimum|Minimáln|Mindestpreis)/i;
const COST = /^(Стоимость|Вартість|Price|Cost|Cena|Preis|Kosten)[^:]{0,30}:\s*/i; // без \b — в JS он не работает с кириллицей

export function parsePacks(page: Page) {
  const intro: Part[] = [];
  const packs: Pack[] = [];
  const extra: Extra[] = [];
  let cur: any = null;
  const start = (text: string) => {
    const m = text.match(PRICE)!;
    const before = text.slice(0, m.index).replace(/[\s—–-]+$/, '');
    const after = text.slice(m.index! + m[0].length).replace(/^[\s.—–-]+/, '');
    const q = before.match(/[«“„"]([^»”“"]+)[»”“"]/);
    const name = q ? q[1] : before.replace(/Interior Design Package|Design package|Дизайн-пакет (интерьера|інтер’єру)|Dizajnový balík( interiéru)?|Designpaket/i, '').trim();
    cur = { title: text, name, price: m[0].replace(/\s+/g, ' ').trim(), note: after, parts: [], buttons: [], href: null, min: '' };
    packs.push(cur);
  };
  for (const s of page.sections) {
    if (isServicesSection(s)) continue;
    for (const b of s.blocks) {
      if (b.type === 'heading') {
        if (b.level === 1) continue;
        if (isPack(b.text)) start(b.text);
        else { cur = { title: b.text, parts: [], buttons: [] }; extra.push(cur); }
      } else if (b.type === 'text') {
        for (const p of b.parts) {
          const t = p.t === 'p' ? plain(p.html) : '';
          if (t && isPack(t) && /[«“„"]/.test(t) && t.length < 120) { start(t); continue; }
          if (cur && 'price' in cur) {
            if (MIN.test(t) && t.length < 90) { cur.min = t.replace(/\.$/, ''); continue; }  // выводится отдельно
            if (COST.test(t) && PRICE.test(t) && t.length < 60) continue;                   // «Стоимость: 50 €/м²» — уже в шапке пакета
          }
          (cur ? cur.parts : intro).push(p);
        }
      } else if (b.type === 'buttons' && cur) {
        cur.buttons.push(...b.items.filter((x) => x.href));
      }
    }
  }
  // ссылка «Подробнее» — на страницу пакета (первая кнопка, ведущая на страницу с ценами того же типа)
  for (const p of packs) {
    p.href = p.buttons.find((x) => x.href && pageByPath.get(x.href)?.type === 'price')?.href || null;
  }
  return { intro, packs, extra };
}

/** Пакет, которому посвящена страница (для карточки с ценой на странице пакета). */
export function packFor(page: Page): Pack | null {
  if (page.type !== 'price') return null;
  const overview = localize('/price-interior-design-bratislava-wien-praha', page.lang as Lang);
  if (!overview || overview === page.path) return null;
  const o = pageByPath.get(overview);
  if (!o) return null;
  return parsePacks(o).packs.find((p) => p.href === page.path) || null;
}
