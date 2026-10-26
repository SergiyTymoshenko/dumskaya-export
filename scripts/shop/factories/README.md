# Данные фабрик с их сайтов (OLEV, Delta Light, Baxter, Flexform, Molteni&C, Maxalto, Minotti, Poliform, MisuraEmme, Rimadesio, Calligaris, Rugiano)

Откуда берутся `content/shop/sources/<фабрика>/` и каталоги `content/shop/catalog/<фабрика>.json`.
У IDL — свой путь: `scripts/shop/idl_factory/README.md`.

Только то, что фабрика открыто выкладывает на сайте без входа: тексты, характеристики, фото, техкарты PDF.
Файлы 2D/3D и BIM, которые у фабрики даются после регистрации, не качаем — в каталоге только ссылка
на страницу изделия. `robots.txt` соблюдаем: Delta Light — не чаще одного запроса в 20 секунд
(так у них для ClaudeBot), разделы `/asset/file/*` не трогаем; остальные сайты — 1–2 запроса в секунду.

## Шаги

1. **Сбор со страниц** (компьютер с Python 3, `pip install requests beautifulsoup4 lxml pdfplumber`), в этой папке:

   ```
   python3 olev.py && python3 olev_ds.py          # → olev.json, olev_ds.json (коды, мощность, люмены из техлистов)
   python3 baxter.py                              # → baxter.json
   python3 flexform.py                            # → flexform.json
   python3 molteni.py && python3 molteni_post.py  # → molteni.json → molteni2.json (только фото и техкарты этого изделия)
   python3 maxalto.py                             # → maxalto.json
   python3 delta_run.py                           # → delta.json, dl-delta.tsv и файлы в delta_files/ (долго: 20 с на запрос)
   python3 minotti.py                             # → minotti.json (≈ 20 минут: 1 запрос в секунду)
   python3 poliform.py                            # → poliform.json (EN + RU страницы, ≈ 25 минут)
   python3 misuraemme.py                          # → misuraemme.json (≈ 3 минуты)
   python3 rimadesio.py                           # → rimadesio.json (EN + RU страницы, ≈ 5 минут)
   python3 calligaris.py crawl && python3 calligaris.py build && python3 calligaris.py sizes && python3 calligaris.py sources
                                                  # → content/shop/sources/calligaris/ сразу (≈ 25 минут; шаги 2–5 не нужны)
   python3 rugiano.py crawl && python3 rugiano.py sizes && python3 rugiano.py sources
                                                  # → content/shop/sources/rugiano/ сразу (≈ 10 минут; шаги 2–5 не нужны)
   ```

   Страницы кешируются в `cache/` — повторный запуск не ходит на сайт заново. Ничего из этого не хранится в git.

2. **Списки файлов**: `python3 gen_dl.py olev baxter flexform molteni maxalto minotti poliform misuraemme rimadesio` → `dl-<фабрика>.tsv`
   («путь в выгрузке<TAB>адрес»): до 8 фото на изделие и техкарты PDF (у Minotti ещё чертежи элементов
   с сайта — `images/shop/minotti/<изделие>/drawings/`). Уже скачанным путь не меняется.

3. **Скачать на Mac** (Терминал Mac): списки и `dl.sh` положить в `~/Documents/dumskaya-export/_work/`, затем
   `cd ~/Documents/dumskaya-export/_work && bash dl.sh dl-baxter.tsv 600` — повторять, пока не напишет
   «не скачано: 0» (уже скачанное пропускает). Фото — в `images/shop/<фабрика>/<изделие>/`, техкарты —
   в `catalogs/<фабрика>/`. Файлы Delta Light скачиваются шагом 1 (`delta_files/`) — их перенести в выгрузку.
   Если каталог фабрики уже в репозитории, скачать её файлы на Mac проще так (из папки сайта, Терминал Mac):
   `python3 scripts/shop/factories/dl.py minotti` — по `content/shop/sources/<фабрика>/files.json`,
   в `~/Documents/dumskaya-export`, по 4 файла сразу; уже скачанное пропускает.

4. **Размеры фото и чертежи** (там же, нужны `pip install pillow pymupdf`):
   `python3 manifest.py <фабрика>` → `manifest-<фабрика>.json` (размеры фото, текст техкарт);
   `python3 drawings.py <фабрика>` → чертежи с размерами, вырезанные из техкарт
   (`images/shop/<фабрика>/drawings/`, сведения — `drawings-<фабрика>.json`). У Minotti этот шаг не нужен:
   чертежи элементов с размерами (см и дюймы) фабрика сама выкладывает на странице изделия.
   У Minotti `manifest.py` ещё берёт из техкарты английскую колонку описания (она там вторая из четырёх: IT, EN, DE, FR).

5. **Исходники в репозиторий**: собрать в одну папку `<фабрика>.json` из шага 1, `dl-*.tsv`, `manifest-*.json`,
   `drawings-*.json` и запустить `python3 scripts/shop/factories/make_sources.py <папка>` →
   `content/shop/sources/<фабрика>/site.json` (данные сайта) и `files.json` (адрес → файл в выгрузке,
   размеры; что прочитано из техкарт: коды исполнений, материалы, отделки, страницы чертежей).
   Тексты PDF целиком в git не попадают.

6. **Каталоги**: `python3 scripts/shop/factories_import.py` → `content/shop/catalog/<фабрика>.json`
   (артикулы, названия по-русски, тип, коллекции, тексты, исполнения, фото, чертежи, техкарты, ссылки).
   Выданные артикулы сохраняются. Потом `python3 scripts/build_shop.py` — список для бота.

## Что где у фабрик

| Фабрика | Что берём | Размеры |
|---|---|---|
| OLEV | страницы изделий (EN), техлисты PDF: коды, мощность, люмены, CCT, IP | чертёж из техлиста |
| Delta Light | подсемейства с исполнениями (EN): характеристики, отделки, фото изделия, чертёж SVG | в характеристиках и на чертеже |
| Baxter | EN и RU тексты, исполнения с кодами и размерами в см, материалы, техкарты | по исполнениям + чертёж |
| Flexform | EN и RU тексты и материалы, техкарты (коды исполнений), архив 2D (ссылка) | чертёж из техкарты |
| Molteni&C | EN тексты, техкарты (материалы, отделки) | чертёж из техкарты |
| Maxalto | EN тексты, техкарты (материалы) | чертёж из техкарты |
| Minotti | EN тексты, дизайнер, элементы из «Technical Features» с чертежом каждого (см и дюймы), техкарты (материалы), схемы композиций (ссылка) | в названии элемента + его чертёж |
| Poliform | EN и RU тексты, дизайнер и год, материалы (пары «Structure: …»), отделки с кодами, чертежи SVG из вкладки DIMENSIONS; техкарт PDF нет | на чертежах SVG (`manifest.py` берёт размер SVG по viewBox) |
| Rimadesio | EN и RU тексты, дизайнер («Design …»), раздел и тип, технические детали, фото, техническая документация PDF коллекции (одна на несколько изделий) | в PDF коллекции (размеры композиций «W … H … D …» в мм) |
| MisuraEmme | EN текст и техническое описание, дизайнер, тип, отделки с кодами, чертежи PNG из «Dimensions» (оригинал вместо миниатюры); техкарта — версия страницы для печати (ссылка) | в подписи чертежа в мм («W. 824 x D. 816 mm», «ø1550») → см |
| Calligaris | EN описание (en-RW — международная версия), раздел, размеры (высота, ширина, глубина, высота сиденья…), розничная цена в евро, фото на белом (cloudfront) и интерьерные (Contentful, до 2400 px), прямые ссылки OBJ / DWG / SKP | в данных страницы, в см |
| Rugiano | EN: тип изделия (подпись над названием), название, тексты блоков описания, фото, схемы «Measures» (PNG, имя файла — модель и размер); раздел indoor / outdoor; одна модель — в нескольких разделах (ключ — раздел + изделие); дизайнеров на сайте нет. «Technical specification» (материалы, отделки) — после входа в Area riservata (https://www.rugiano.com/en/reserved-area), не качаем: ссылка `links.spec_after_login`. Открытые каталоги PDF — https://www.rugiano.com/en/catalogues | на схемах «Measures» (картинка) |

Чертежи Delta Light — векторные SVG; `width`/`height` в каталоге — размеры из `viewBox` (у многих 128×128),
это не пиксели. На сайт их отдавать как SVG или растрировать с повышенной плотностью
(`sharp(svg, { density: 600 })`), иначе картинка получится крошечной.

Minotti: список изделий — сервис их страницы списка (`/WS/wsMinottiProducts.asmx/GetList`, разделы Indoor, Outdoor,
«2026 Collection» → новинки); тип товара — по разделу списка (Sofas, Coffee tables…), уточняется по названию
и элементам. Имена файлов у Minotti бывают с пробелами («AERON MOD A.jpg») — адреса кодируются при сборе.
Файлы 2D/3D, фото высокого разрешения и «архив» у Minotti — после входа; в каталоге только ссылка на страницу.

Poliform: файлы 2D/3D (DWG, 3DM, FBX, MAX, SKP) отдаются только после формы подписки — не качаем, но их адреса
видны на странице: `poliform.py` записывает список (формат, размер, адрес), в каталоге он — `files_after_login`.
Фото — галерея между заголовком и техническими вкладками (в ней бывают соседние изделия — берём те, где в имени
файла есть название модели).

**Не терять то, что за регистрацией.** Что фабрика даёт только после входа (2D/3D, BIM, фото высокого разрешения,
размеры у Rugiano), в каталоге отмечено ссылкой `links.files_2d3d`, а если адреса видны — списком `files_after_login`.
Сводка по фабрикам — в «Плане работы по фабрикам».

MisuraEmme: в карте сайта есть снятые изделия — их адреса ведут на главную, сборщик их пропускает (как и разделы-списки).
Фото высокого разрешения и 2D/3D (PDF, DWG, 3DS) — после входа: в каталоге ссылки `links.files_2d3d`, `links.photos_hr`
и список `files_after_login` (что есть; адрес — страница изделия).

Rimadesio: в карте сайта есть и готовые интерьеры («New interiors»: interior-…, night-…, living-…, dining, walk-in-closet) —
это не изделия, сборщик их пропускает. 2D/3D — в Reserved Area после входа: в каталоге ссылка на неё.

Calligaris (с 25.10.2026, закреплена за разработчиком): страница у фабрики — одно исполнение (код CS5156-C);
наш товар — семейство + тип («Twins coffee table» с исполнениями A, B, C), «MTO» — исполнения под заказ.
Всё открыто без входа; данные — из JSON страницы (`__NEXT_DATA__`), внутренний API сайта не используем.
Файлы OBJ / DWG / SKP — прямые ссылки (в каталоге `downloads`, в заявке — подсказка дизайнеру), сами файлы не качаем.

## Незавершённые фабрики (отложены 25.10.2026, вернуться после запуска dumskaya-home.com)

Все — за Александром Замлинским. Свободные номера артикулов: 4700–4999 и от 9000.

- **Lago** — начата. Карта сайта `https://www.lago.it/sitemap_it.xml`: около 200 адресов `/design/<изделие>/`, среди них
  около 45 разделов и подборок (tutti-i-prodotti, armadi, divani, letti, tavoli, cucine, soggiorno, camera-da-letto,
  lampade, mensole, idee-salvaspazio…) — их пропускать. Английская версия — на другом домене:
  `https://www.lagodesign.com/en/design/<изделие по-английски>/` (у страницы есть `hreflang` en/fr/es, русского нет).
  Сайт на Nuxt: данные страницы — `https://www.lago.it/_nuxt/static/1/design/<изделие>/payload.js` (тексты, отделки
  sections-finishings, материалы sections-technical-materials), так проще, чем разбирать страницу. «Scarica modelli 3D»
  и «Scarica catalogo» — через форму (forms-dynamic-forms): не качаем, ссылку — в `links.files_2d3d`. Конфигуратор:
  `https://configurator.lago.it/<раздел>/<изделие>`. robots.txt разрешает обход (закрыты /privacy, /cookies, /posizione/*,
  /feed/, `?store=`, `?s=`). Артикулы — DF-9500–9799 (9000–9499 с 25.10.2026 — у Calligaris).
- **Rugiano** — собрана 26.10.2026 (366 изделий, артикулы DF/DL-…9500–9999). Регистрация владельца в Area riservata одобрена
  26.10.2026; в тот же день после его входа во встроенном браузере собраны ссылки на техкарты (`rugiano_sheets.py <links.json>`):
  363 техкарты PDF — материалы у 348, размеры в см у 348, вес у 341 (`content/shop/sources/rugiano/sheets.json`), PDF — в
  `catalogs/rugiano/` (качает `dl.py rugiano`). Без техкарты: Atlanta Bar, Marina 180 (нет у фабрики), Club comò (CDN фабрики
  отвечает 400). Схемы с размерами открыты и без входа. Тексты на пяти языках и выкладка — 26.10.2026.
- **Giorgetti** — сайт не пускает автоматическое чтение страниц (защита от роботов). Варианты: через браузер или каталог
  от фабрики через Замлинского.
- **Il Paralume Marina** — свет; данные изделий после входа на сайте, нужна регистрация.
