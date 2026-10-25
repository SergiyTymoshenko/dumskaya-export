// Типографика DUMSKAYA HOME — та же, что у сайта студии (src/lib/typo.ts: неразрывные пробелы после коротких слов,
// между числом и единицей, перед тире), плюс французская: неразрывный пробел перед « : ; ? ! » и внутри « … ».
import { typo as base, typoHtml as baseHtml } from '../../../src/lib/typo';
import type { Lang } from './i18n';

const NB = ' ', NNB = ' ';
const SHORT = /(^|[\s(«"„—–])(les|des|une|par|sur|aux|los|las|del|con|por|sin|una|que)\s(?=\S)/gi;
function fr(s: string) {
  return s.replace(/\s+([;!?])/g, `${NNB}$1`).replace(/\s+:/g, `${NB}:`).replace(/«\s*/g, `«${NB}`).replace(/\s*»/g, `${NB}»`);
}
export function typo(s: string, l: Lang) {
  let t = base(s).replace(SHORT, (m, pre, w) => pre + w + NB);
  return l === 'fr' ? fr(t) : t;
}
export function typoHtml(s: string, l: Lang) {
  return String(s ?? '').split(/(<[^>]+>)/).map((x) => (x.startsWith('<') ? x : typo(x, l))).join('');
}
export { baseHtml };
