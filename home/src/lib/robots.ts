// robots.txt каталога (решено 25.10.2026): пока владелец не подтвердил, что каталог готов, — закрыт для всех роботов.
// Открыть: content/home/site.json → "indexing": true и выкладка (npm run deploy:home) — тогда отдаётся LIVE.
// Пока закрыт, IndexNow (deploy/indexnow.py) каталог поисковикам не отправляет.
export const LIVE = 'User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: https://dumskaya-home.com/sitemap.xml\n\n# LLM summary: https://dumskaya-home.com/llms.txt\n';
export const CLOSED = '# DUMSKAYA HOME is not open for search engines yet\nUser-agent: *\nDisallow: /\n';
