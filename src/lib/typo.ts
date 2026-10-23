// Типографика: неразрывные пробелы, чтобы строки не обрывались на коротком слове
// («в / Вене»), числа не отрывались от единиц («50 / €/м²»), а тысячи — друг от друга («2 / 500 €»).
const NB = ' ';
const SHORT_WORDS = new Set([
  // ru / ua
  'для', 'при', 'без', 'под', 'над', 'про', 'или', 'чем', 'как', 'від', 'для', 'або', 'під', 'над', 'без', 'про', 'між',
  // en
  'the', 'and', 'for', 'von', 'und',
  // sk / de
  'pre', 'pri', 'bez', 'nad', 'pod', 'pod', 'zo', 'vo', 'ako', 'ich', 'für', 'mit', 'bei', 'aus', 'zum', 'zur', 'die', 'der', 'das',
]);

function shortWords(s: string): string {
  // слово из 1–2 букв (или из списка) + пробел → неразрывный пробел
  return s.replace(/(^|[\s («"„—–])([A-Za-zÀ-žА-ЯЁа-яёІіЇїЄєҐґ’']{1,3})\s(?=\S)/g, (m, pre, w) =>
    w.length <= 2 || SHORT_WORDS.has(w.toLowerCase()) ? pre + w + NB : m,
  );
}

export function typo(text: string): string {
  let s = String(text ?? '');
  s = shortWords(shortWords(s)); // дважды — для цепочек «и в»
  s = s.replace(/(\d) ?- ?(?=\d)/g, '$1–'); // диапазоны: 35-45 → 35–45
  s = s.replace(/(\d)\s(?=\d{3}(?!\d))/g, `$1${NB}`); // 2 500, 12 000
  s = s.replace(/(\d)\s(?=(?:€|zł|Kč|\$|м²|m²|м2|m2|мм|см|mm|cm|м\b|m\b|пог\.|дн|днів|days|мес|міс|month))/g, `$1${NB}`);
  s = s.replace(/\s([—–])\s/g, `${NB}$1 `); // тире не начинает строку
  return s;
}

/** То же для HTML абзаца: меняется только текст, теги и атрибуты не трогаются. */
export function typoHtml(html: string): string {
  return String(html ?? '')
    .split(/(<[^>]+>)/)
    .map((x) => (x.startsWith('<') ? x : typo(x)))
    .join('');
}
