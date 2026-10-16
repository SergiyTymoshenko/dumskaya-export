export type Lang = 'ru' | 'ua' | 'en';
export const LANGS: Lang[] = ['ru', 'ua', 'en'];
export const HREFLANG: Record<Lang, string> = { ru: 'ru', ua: 'uk', en: 'en' };
export const LANG_LABEL: Record<Lang, string> = { ru: 'RU', ua: 'UA', en: 'EN' };

const t = {
  ru: {
    menu: 'Меню', close: 'Закрыть', call: 'Позвонить', phone: 'Телефон', home: 'Главная',
    city: 'Братислава и Вена',
    projects: 'Проекты', allProjects: 'Все проекты',
    groups: { residential: 'Жилые интерьеры', commercial: 'Коммерческие интерьеры', architecture: 'Архитектура' },
    services: 'Услуги студии',
    about: 'О студии', readMore: 'Читать полностью',
    consult: 'Заказать бесплатную консультацию', freeConsult: 'Бесплатная консультация', prices: 'Цены на услуги',
    facts: { object: 'Объект', area: 'Площадь', city: 'Город', works: 'Работы', status: 'Статус', terrace: 'Терраса' },
    next: 'Следующий проект', prev: 'Предыдущий проект',
    contacts: 'Контакты', rights: 'Все права защищены',
    m2: 'м²', photo: 'Фото',
    tips: 'Советы', otherTips: 'Другие советы', kitchens: 'Кухни', otherKitchens: 'Другие модели кухонь', allKitchens: 'Каталог кухонь',
    photoPrev: 'Предыдущее фото', photoNext: 'Следующее фото', photoZoom: 'Увеличить фото', packModel: 'Пакет «{}»', orderPack: 'Заказать пакет', packDetails: 'Подробнее о пакете', examples: 'Примеры', allPacks: 'Все пакеты и цены', minPrice: 'Минимальная стоимость', heroCta: 'Бесплатная консультация', cookieSettings: 'Настройки cookie', made: 'Изготовление — на собственном производстве в Братиславе. Доставка и монтаж — в Братиславе, Вене и по Германии; цена одна для всех городов.', portrait: 'Ирина Думская — руководитель и главный дизайнер DUMSKAYA DESIGN', skip: 'Перейти к содержимому',
    kitchenPrice: 'Рассчитать стоимость', more: 'Подробнее', prices2: 'Цены', shop: 'Магазин', askPrice: 'Узнать цену', article: 'Артикул',
    form: { title: 'Заявка на бесплатную консультацию', name: 'Имя', contact: 'Телефон или e-mail', message: 'Расскажите об объекте', send: 'Отправить заявку', sending: 'Отправляем…', ok: 'Заявка отправлена. Мы свяжемся с вами в течение рабочего дня.', fail: 'Не получилось отправить заявку. Позвоните нам или напишите на почту.', consent: 'Отправляя форму, вы соглашаетесь на обработку данных для ответа на заявку.', privacy: 'Политика конфиденциальности', model: 'Интересует' },
    write: 'Написать', messengers: 'Мессенджеры', address: 'Адрес студии',
    cookie: { text: 'Мы используем файлы cookie Google Analytics, чтобы понимать, как посетители пользуются сайтом. Без вашего согласия они не загружаются.', accept: 'Принять', decline: 'Отклонить' },
    notFound: { title: 'Страница не найдена', text: 'Возможно, адрес изменился. Начните с главной или посмотрите проекты.' },
  },
  ua: {
    menu: 'Меню', close: 'Закрити', call: 'Зателефонувати', phone: 'Телефон', home: 'Головна',
    city: 'Братислава і Відень',
    projects: 'Проєкти', allProjects: 'Усі проєкти',
    groups: { residential: 'Житлові інтер’єри', commercial: 'Комерційні інтер’єри', architecture: 'Архітектура' },
    services: 'Послуги студії',
    about: 'Про студію', readMore: 'Читати повністю',
    consult: 'Замовити безкоштовну консультацію', freeConsult: 'Безкоштовна консультація', prices: 'Ціни на послуги',
    facts: { object: 'Об’єкт', area: 'Площа', city: 'Місто', works: 'Роботи', status: 'Статус', terrace: 'Тераса' },
    next: 'Наступний проєкт', prev: 'Попередній проєкт',
    contacts: 'Контакти', rights: 'Усі права захищені',
    m2: 'м²', photo: 'Фото',
    tips: 'Поради', otherTips: 'Інші поради', kitchens: 'Кухні', otherKitchens: 'Інші моделі кухонь', allKitchens: 'Каталог кухонь',
    photoPrev: 'Попереднє фото', photoNext: 'Наступне фото', photoZoom: 'Збільшити фото', packModel: 'Пакет «{}»', orderPack: 'Замовити пакет', packDetails: 'Детальніше про пакет', examples: 'Приклади', allPacks: 'Усі пакети та ціни', minPrice: 'Мінімальна вартість', heroCta: 'Безкоштовна консультація', cookieSettings: 'Налаштування cookie', made: 'Виготовлення — на власному виробництві в Братиславі. Доставка й монтаж — у Братиславі, Відні та по Німеччині; ціна однакова для всіх міст.', portrait: 'Ірина Думська — керівниця та головна дизайнерка DUMSKAYA DESIGN', skip: 'Перейти до вмісту',
    kitchenPrice: 'Розрахувати вартість', more: 'Детальніше', prices2: 'Ціни', shop: 'Магазин', askPrice: 'Дізнатися ціну', article: 'Артикул',
    form: { title: 'Заявка на безкоштовну консультацію', name: 'Ім’я', contact: 'Телефон або e-mail', message: 'Розкажіть про об’єкт', send: 'Надіслати заявку', sending: 'Надсилаємо…', ok: 'Заявку надіслано. Ми зв’яжемося з вами протягом робочого дня.', fail: 'Не вдалося надіслати заявку. Зателефонуйте нам або напишіть на пошту.', consent: 'Надсилаючи форму, ви погоджуєтеся на обробку даних для відповіді на заявку.', privacy: 'Політика конфіденційності', model: 'Цікавить' },
    write: 'Написати', messengers: 'Месенджери', address: 'Адреса студії',
    cookie: { text: 'Ми використовуємо файли cookie Google Analytics, щоб розуміти, як відвідувачі користуються сайтом. Без вашої згоди вони не завантажуються.', accept: 'Прийняти', decline: 'Відхилити' },
    notFound: { title: 'Сторінку не знайдено', text: 'Можливо, адреса змінилася. Почніть з головної або перегляньте проєкти.' },
  },
  en: {
    menu: 'Menu', close: 'Close', call: 'Call', phone: 'Phone', home: 'Home',
    city: 'Bratislava and Vienna',
    projects: 'Projects', allProjects: 'All projects',
    groups: { residential: 'Residential interiors', commercial: 'Commercial interiors', architecture: 'Architecture' },
    services: 'Studio services',
    about: 'About the studio', readMore: 'Read more',
    consult: 'Book a free consultation', freeConsult: 'Free consultation', prices: 'Prices',
    facts: { object: 'Property', area: 'Area', city: 'City', works: 'Scope', status: 'Status', terrace: 'Terrace' },
    next: 'Next project', prev: 'Previous project',
    contacts: 'Contact', rights: 'All rights reserved',
    m2: 'm²', photo: 'Photo',
    tips: 'Tips', otherTips: 'More tips', kitchens: 'Kitchens', otherKitchens: 'Other kitchen models', allKitchens: 'Kitchen catalog',
    photoPrev: 'Previous photo', photoNext: 'Next photo', photoZoom: 'Enlarge photo', packModel: '“{}” package', orderPack: 'Order this package', packDetails: 'Package details', examples: 'Examples', allPacks: 'All packages and prices', minPrice: 'Minimum price', heroCta: 'Free consultation', cookieSettings: 'Cookie settings', made: 'Made in our own workshop in Bratislava. Delivery and installation in Bratislava, Vienna and across Germany — one price for every city.', portrait: 'Irina Dumskaya, founder and lead designer of DUMSKAYA DESIGN', skip: 'Skip to content',
    kitchenPrice: 'Get a price', more: 'Details', prices2: 'Prices', shop: 'Shop', askPrice: 'Ask for a price', article: 'Item',
    form: { title: 'Request a free consultation', name: 'Name', contact: 'Phone or e-mail', message: 'Tell us about your property', send: 'Send request', sending: 'Sending…', ok: 'Request sent. We will get back to you within one working day.', fail: 'The request could not be sent. Please call us or send an e-mail.', consent: 'By sending the form you agree to the processing of your data to answer your request.', privacy: 'Privacy policy', model: 'Interested in' },
    write: 'Write', messengers: 'Messengers', address: 'Studio address',
    cookie: { text: 'We use Google Analytics cookies to understand how visitors use the site. They are not loaded without your consent.', accept: 'Accept', decline: 'Decline' },
    notFound: { title: 'Page not found', text: 'The address may have changed. Start from the home page or browse the projects.' },
  },
} as const;

export function ui(lang: Lang) {
  return t[lang];
}
