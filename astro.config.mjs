import { defineConfig } from 'astro/config';

// Адреса страниц без слэша на конце (/proekty-interior-design), как на старом сайте.
// build.format 'file' кладёт каждую страницу в <адрес>.html — nginx отдаёт её через try_files.
export default defineConfig({
  site: 'https://dumskaya-design.com',
  trailingSlash: 'never',
  build: { format: 'file', inlineStylesheets: 'auto' },
  compressHTML: true,
  devToolbar: { enabled: false },
});
