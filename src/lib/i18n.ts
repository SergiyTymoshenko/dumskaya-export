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
    tips: 'Советы', otherTips: 'Другие советы', kitchens: 'Кухни', otherKitchens: 'Другие модели кухонь', allKitchens: 'Каталог кухонь',
    kitchenPrice: 'Рассчитать стоимость', more: 'Подробнее', prices2: 'Цены', shop: 'Магазин', askPrice: 'Узнать цену', article: 'Артикул',
    form: { title: 'Заявка на бесплатную консультацию', name: 'Имя', contact: 'Телефон или e-mail', message: 'Расскажите об объекте', send: 'Отправить заявку', sending: 'Отправляем…', ok: 'Заявка отправлена. Мы свяжемся с вами в течение рабочего дня.', fail: 'Не получилось отправить заявку. Позвоните нам или напишите на почту.', consent: 'Отправляя форму, вы соглашаетесь на обработку данных для ответа на заявку.', privacy: 'Политика конфиденциальности', model: 'Модель' },
    write: 'Написать', messengers: 'Мессенджеры', address: 'Адрес студии',
    cookie: { text: 'Мы используем файлы cookie Google Analytics, чтобы понимать, как посетители пользуются сайтом. Без вашего согласия они не загружаются.', accept: 'Принять', decline: 'Отклонить' },
    notFound: { title: 'Страница не найдена', text: 'Возможно, адрес изменился. Начните с главной или посмотрите проекты.' },
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
    tips: 'Поради', otherTips: 'Інші поради', kitchens: 'Кухні', otherKitchens: 'Інші моделі кухонь', allKitchens: 'Каталог кухонь',
    kitchenPrice: 'Розрахувати вартість', more: 'Детальніше', prices2: 'Ціни', shop: 'Магазин', askPrice: 'Дізнатися ціну', article: 'Артикул',
    form: { title: 'Заявка на безкоштовну консультацію', name: 'Ім’я', contact: 'Телефон або e-mail', message: 'Розкажіть про об’єкт', send: 'Надіслати заявку', sending: 'Надсилаємо…', ok: 'Заявку надіслано. Ми зв’яжемося з вами протягом робочого дня.', fail: 'Не вдалося надіслати заявку. Зателефонуйте нам або напишіть на пошту.', consent: 'Надсилаючи форму, ви погоджуєтеся на обробку даних для відповіді на заявку.', privacy: 'Політика конфіденційності', model: 'Модель' },
    write: 'Написати', messengers: 'Месенджери', address: 'Адреса студії',
    cookie: { text: 'Ми використовуємо файли cookie Google Analytics, щоб розуміти, як відвідувачі користуються сайтом. Без вашої згоди вони не завантажуються.', accept: 'Прийняти', decline: 'Відхилити' },
    notFound: { title: 'Сторінку не знайдено', text: 'Можливо, адреса змінилася. Почніть з головної або перегляньте проєкти.' },
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
    tips: 'Tips', otherTips: 'More tips', kitchens: 'Kitchens', otherKitchens: 'Other kitchen models', allKitchens: 'Kitchen catalog',
    kitchenPrice: 'Get a price', more: 'Details', prices2: 'Prices', shop: 'Shop', askPrice: 'Ask for a price', article: 'Item',
    form: { title: 'Request a free consultation', name: 'Name', contact: 'Phone or e-mail', message: 'Tell us about your property', send: 'Send request', sending: 'Sending…', ok: 'Request sent. We will get back to you within one working day.', fail: 'The request could not be sent. Please call us or send an e-mail.', consent: 'By sending the form you agree to the processing of your data to answer your request.', privacy: 'Privacy policy', model: 'Model' },
    write: 'Write', messengers: 'Messengers', address: 'Studio address',
    cookie: { text: 'We use Google Analytics cookies to understand how visitors use the site. They are not loaded without your consent.', accept: 'Accept', decline: 'Decline' },
    notFound: { title: 'Page not found', text: 'The address may have changed. Start from the home page or browse the projects.' },
  },
} as const;

export function ui(lang: Lang) {
  return t[lang];
}
