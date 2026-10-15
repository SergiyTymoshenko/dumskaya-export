# dumskaya-design.com

Новый сайт студии DUMSKAYA DESIGN: статический сайт на [Astro](https://astro.build),
три языка (ru / ua / en), адреса страниц совпадают со старым сайтом на Weblium.

## Где что лежит

| Папка | Что внутри |
|---|---|
| `content/pages/{ru,ua,en}/` | Тексты страниц: мета-теги, языковые пары, блоки. **Правки текстов — здесь.** |
| `content/projects.json` | Карточки проектов портфолио (собирается скриптом) |
| `content/projects-overrides.json` | Ручные данные проектов: город, площадь, состав работ |
| `content/home.json` | Главная: первое фото, фото Ирины, избранные проекты |
| `content/site.json` | Меню, телефоны, соцсети, счётчики |
| `content/images.json`, `image-names.json` | Сведения о фото и их понятные имена файлов |
| `src/` | Шаблоны и стили |
| `scripts/` | Импорт со старого сайта и обработка фото |

Оригиналы фото в репозиторий не кладутся (2,5 ГБ): они лежат на Mac в
`~/Documents/dumskaya-export/images`, а готовые WebP создаются в `public/img/`.

## Сборка на Mac

```bash
npm install
npm run images     # фото → public/img (первый раз долго, потом только новые)
npm run build      # сайт → dist/
npm run preview    # посмотреть на http://localhost:4321
```
