// Характеристики товара для страницы: исполнения с размерами (мебель), технические данные (свет), отделки.
// Тексты фабрик дословно не показываем — только факты: размеры, цифры, названия отделок.
import type { Lang } from './i18n';
import type { Product } from './catalog';

const LBL: Record<string, Record<Lang, string>> = {
  version: { en: 'Version', ru: 'Исполнение', de: 'Ausführung', fr: 'Version', es: 'Versión' },
  size: { en: 'Size, cm', ru: 'Размер, см', de: 'Maße, cm', fr: 'Dimensions, cm', es: 'Medidas, cm' },
  light: { en: 'Light source', ru: 'Источник света', de: 'Leuchtmittel', fr: 'Source lumineuse', es: 'Fuente de luz' },
  power: { en: 'Power', ru: 'Мощность', de: 'Leistung', fr: 'Puissance', es: 'Potencia' },
  lumen: { en: 'Luminous flux', ru: 'Световой поток', de: 'Lichtstrom', fr: 'Flux lumineux', es: 'Flujo luminoso' },
  cct: { en: 'Color temperature', ru: 'Цветовая температура', de: 'Farbtemperatur', fr: 'Température de couleur', es: 'Temperatura de color' },
  cri: { en: 'Color rendering (CRI)', ru: 'Цветопередача (CRI)', de: 'Farbwiedergabe (CRI)', fr: 'Rendu des couleurs (IRC)', es: 'Reproducción cromática (IRC)' },
  ip: { en: 'Protection rating', ru: 'Степень защиты', de: 'Schutzart', fr: 'Indice de protection', es: 'Grado de protección' },
  ik: { en: 'Impact rating', ru: 'Ударопрочность', de: 'Stoßfestigkeit', fr: 'Résistance aux chocs', es: 'Resistencia a impactos' },
  dimming: { en: 'Dimming', ru: 'Диммирование', de: 'Dimmung', fr: 'Gradation', es: 'Regulación' },
  voltage: { en: 'Voltage', ru: 'Напряжение', de: 'Spannung', fr: 'Tension', es: 'Tensión' },
  beam: { en: 'Beam angle', ru: 'Угол луча', de: 'Abstrahlwinkel', fr: 'Angle du faisceau', es: 'Ángulo de haz' },
  colours: { en: 'Colors', ru: 'Цвета', de: 'Farben', fr: 'Couleurs', es: 'Colores' },
  distribution: { en: 'Light distribution', ru: 'Распределение света', de: 'Lichtverteilung', fr: 'Distribution de la lumière', es: 'Distribución de la luz' },
  length: { en: 'Length', ru: 'Длина', de: 'Länge', fr: 'Longueur', es: 'Longitud' },
  diameter: { en: 'Diameter', ru: 'Диаметр', de: 'Durchmesser', fr: 'Diamètre', es: 'Diámetro' },
  height: { en: 'Height', ru: 'Высота', de: 'Höhe', fr: 'Hauteur', es: 'Altura' },
  width: { en: 'Width', ru: 'Ширина', de: 'Breite', fr: 'Largeur', es: 'Anchura' },
  dimension: { en: 'Dimensions', ru: 'Размеры', de: 'Abmessungen', fr: 'Dimensions', es: 'Dimensiones' },
  cutout: { en: 'Cut-out', ru: 'Монтажное отверстие', de: 'Einbauausschnitt', fr: 'Découpe', es: 'Recorte' },
  depth: { en: 'Recess depth', ru: 'Глубина встраивания', de: 'Einbautiefe', fr: 'Profondeur d’encastrement', es: 'Profundidad de empotrado' },
  weight: { en: 'Weight', ru: 'Вес', de: 'Gewicht', fr: 'Poids', es: 'Peso' },
};
// ключ у фабрики → наш
const KEY: Record<string, string> = {
  'Luminaire power': 'power', 'Watt': 'power', power_w: 'power', max_power: 'power', 'Luminaire lm': 'lumen', lumen: 'lumen',
  CCT: 'cct', cct: 'cct', CRI: 'cri', cri: 'cri', IP: 'ip', ip: 'ip', IK: 'ik', 'Dimming type': 'dimming', dimming: 'dimming',
  'Dimming Method': 'dimming', Voltage: 'voltage', supply: 'voltage', 'Beam angle': 'beam', beam: 'beam',
  'Light distribution': 'distribution', Length: 'length', Diameter: 'diameter', Height: 'height', 'Height bollard': 'height',
  Width: 'width', Dimension: 'dimension', 'Cutout size': 'cutout', 'Min. recessed depth': 'depth', Weight: 'weight', net_kg: 'weight', light: 'light',
};
const ORDER = ['light', 'power', 'lumen', 'cct', 'cri', 'beam', 'distribution', 'dimming', 'voltage', 'ip', 'ik', 'length', 'width', 'height', 'diameter', 'dimension', 'cutout', 'depth', 'weight', 'colours'];
const DIM: Record<Lang, Record<string, string>> = {
  en: { l: 'W', w: 'D', h: 'H', d: 'Ø' }, ru: { l: 'Ш', w: 'Г', h: 'В', d: 'Ø' }, de: { l: 'B', w: 'T', h: 'H', d: 'Ø' },
  fr: { l: 'L', w: 'P', h: 'H', d: 'Ø' }, es: { l: 'An', w: 'F', h: 'Al', d: 'Ø' },
};
const num = (x: number, l: Lang) => { const s = String(Math.round(x * 10) / 10); return l === 'en' ? s : s.replace('.', ','); };
const unitize = (k: string, v: string) => {
  v = String(v).replace(/\.0\b/g, '');
  if (k === 'power' && /^[\d.,]+$/.test(v)) return `${v} W`;
  if (k === 'lumen' && /^[\d.,]+$/.test(v)) return `${v} lm`;
  if (k === 'cct' && /^\d{4}$/.test(v)) return `${v} K`;
  if (k === 'ip' && /^\d+$/.test(v)) return `IP${v}`;
  if (k === 'beam' && /^\d+$/.test(v)) return `${v}°`;
  if (k === 'weight' && /^[\d.,]+$/.test(v)) return `${v} kg`;
  return v;
};
function dims(d: any, l: Lang) {
  if (!d) return '';
  return ['l', 'w', 'h', 'd'].filter((k) => d[k]).map((k) => `${DIM[l][k]} ${num(d[k], l)}`).join(' × ');
}
const vname = (v: any, l: Lang) => (v.name && (v.name[l] || v.name.en)) || '';

/** Таблица исполнений мебели: название исполнения и размеры в см */
export function versionsTable(p: Product, l: Lang) {
  const vs = (p.facts.versions || []).filter((v) => !v.props);
  const rows: string[][] = [];
  const seen = new Set<string>();
  for (const v of vs) {
    const n = vname(v, l).replace(/\s+/g, ' ').trim(), s = dims(v.dims_cm, l);
    if (!n && !s) continue;
    const key = `${n}|${s}`.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push([n, s]);
  }
  if (!rows.length || rows.every((r) => !r[1])) return rows.length > 1 ? { head: [LBL.version[l]], rows: rows.map((r) => [r[0]]) } : null;
  return { head: [LBL.version[l], LBL.size[l]], rows };
}

/** Технические данные света: одно значение или список значений через запятую; цвета исполнений */
export function techRows(p: Product, l: Lang): [string, string][] {
  const acc = new Map<string, Set<string>>();
  const add = (k0: string, v: any) => {
    const k = KEY[k0];
    if (!k || v == null || v === '') return;
    for (const x of Array.isArray(v) ? v : [v]) {
      const s = unitize(k, String(x).trim());
      if (s && s !== 'None') (acc.get(k) || acc.set(k, new Set()).get(k)!).add(s);
    }
  };
  const t = p.facts.tech;
  if (t && typeof t === 'object' && !('en' in t)) {
    for (const [k, v] of Object.entries(t)) {
      if (k === 'common' && v && typeof v === 'object') for (const [k2, v2] of Object.entries(v as any)) add(k2, v2);
      else add(k, v);
    }
  }
  const cols = new Set<string>();
  for (const v of p.facts.versions || []) {
    if (v.props) for (const [k, x] of Object.entries(v.props)) add(k, x);
    if (v.colour) cols.add(v.colour);
  }
  if (cols.size) acc.set('colours', cols);
  const sortv = (xs: string[]) => xs.sort((a, b) => (parseFloat(a) || 0) - (parseFloat(b) || 0) || a.localeCompare(b));
  return ORDER.filter((k) => acc.has(k)).map((k) => {
    const xs = sortv([...acc.get(k)!]);
    return [LBL[k][l], xs.length > 6 ? `${xs[0]} … ${xs.at(-1)} (${xs.length})` : xs.join(', ')] as [string, string];
  });
}

/** Отделки: группы фабрики (названия групп — как у фабрики, по-английски) */
export function finishGroups(p: Product): [string, string[]][] {
  const f = p.facts.finishes || {};
  return Object.entries(f).filter(([, v]) => v?.length).map(([k, v]) => [k || '—', v]);
}
