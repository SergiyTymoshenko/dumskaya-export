export type Lang = 'ru' | 'ua' | 'en';
export const LANGS: Lang[] = ['ru', 'ua', 'en'];
export const HREFLANG: Record<Lang, string> = { ru: 'ru', ua: 'uk', en: 'en' };
export const LANG_LABEL: Record<Lang, string> = { ru: 'RU', ua: 'UA', en: 'EN' };

const t = {
  ru: {
    menu: 'Меню', close: 'Закрыть', call: 'Позвонить', home: 'Главная',
    city: 'Братислава и Вена',
    projects: 'Проекты', allProjects: 'Все проекты',
    groups: { residential: 'Жилые интерьеры', commercial: 'Коммерческие интерьеры', architecture: 'Архитектура' },
    services: 'Услуги студии',
    about: 'О студии', readMore: 'Читать полностью',
    consult: 'Заказать бесплатную консультацию', freeConsult: 'Бесплатная консультация', prices: 'Цены на услуги',
    facts: { object: 'Объект', area: 'Площадь', city: 'Город', works: 'Работы', terrace: 'Терраса' },
    next: 'Следующий проект', prev: 'Предыдущий проект',
    contacts: 'Контакты', rights: 'Все права защищены',
    m2: 'м²', photo: 'Фото',
  },
  ua: {
    menu: 'Меню', close: 'Закрити', call: 'Зателефонувати', home: 'Головна',
    city: 'Братислава і Відень',
    projects: 'Проєкти', allProjects: 'Усі проєкти',
    groups: { residential: 'Житлові інтер’єри', commercial: 'Комерційні інтер’єри', architecture: 'Архітектура' },
    services: 'Послуги студії',
    about: 'Про студію', readMore: 'Читати повністю',
    consult: 'Замовити безкоштовну консультацію', freeConsult: 'Безкоштовна консультація', prices: 'Ціни на послуги',
    facts: { object: 'Об’єкт', area: 'Площа', city: 'Місто', works: 'Роботи', terrace: 'Тераса' },
    next: 'Наступний проєкт', prev: 'Попередній проєкт',
    contacts: 'Контакти', rights: 'Усі права захищені',
    m2: 'м²', photo: 'Фото',
  },
  en: {
    menu: 'Menu', close: 'Close', call: 'Call', home: 'Home',
    city: 'Bratislava and Vienna',
    projects: 'Projects', allProjects: 'All projects',
    groups: { residential: 'Residential interiors', commercial: 'Commercial interiors', architecture: 'Architecture' },
    services: 'Studio services',
    about: 'About the studio', readMore: 'Read more',
    consult: 'Book a free consultation', freeConsult: 'Free consultation', prices: 'Prices',
    facts: { object: 'Property', area: 'Area', city: 'City', works: 'Scope', terrace: 'Terrace' },
    next: 'Next project', prev: 'Previous project',
    contacts: 'Contact', rights: 'All rights reserved',
    m2: 'm²', photo: 'Photo',
  },
} as const;

export function ui(lang: Lang) {
  return t[lang];
}
