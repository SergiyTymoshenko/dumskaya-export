import { defineConfig } from 'astro/config';
import { fileURLToPath } from 'node:url';

// Сайт DUMSKAYA HOME (dumskaya-home.com) — каталог товаров фабрик в дизайне сайта студии.
// Собирается из корня репозитория: npx astro build --root home (scripts/deploy_home.sh).
// Данные — home/data/catalog.json (scripts/shop/catalog_index.py --write), фото — home/public/img (scripts/home_images.mjs).
// Адреса без слэша на конце, страница — <адрес>.html (как у сайта студии; Caddy отдаёт через try_files).
const DATA = fileURLToPath(new URL('./data/', import.meta.url));

export default defineConfig({
  site: 'https://dumskaya-home.com',
  trailingSlash: 'never',
  build: { format: 'file', inlineStylesheets: 'auto' },
  compressHTML: true,
  devToolbar: { enabled: false },
  vite: { define: { 'import.meta.env.HOME_DATA': JSON.stringify(DATA) } },
});
