// robots.txt каталога (решено 25.10.2026): пока владелец не подтвердил, что каталог готов, — закрыт для всех роботов.
// Открыть: content/home/site.json → "indexing": true и выкладка (npm run deploy:home) — тогда отдаётся LIVE.
// Пока закрыт, IndexNow (deploy/indexnow.py) каталог поисковикам не отправляет.
// Открытый (решено 28.10.2026) — и для ИИ-ассистентов (ChatGPT, Claude, Perplexity, Gemini, Copilot и др.), как на usk.ua:
// общая группа (*) и группа ИИ-ботов (content/ai_bots.json, общий со студией); у бота со своей группой общая не действует,
// поэтому запреты (/api/) повторены в обеих; Disallow — первыми, Allow: / — последним.
import fs from 'node:fs';
import path from 'node:path';

const SITE = 'https://dumskaya-home.com';
const DATA = import.meta.env.HOME_DATA as string;
const bots: string[] = JSON.parse(fs.readFileSync(path.join(DATA, '../../content/ai_bots.json'), 'utf8')).agents;
const RULES = ['Disallow: /api/', 'Allow: /'];

export const LIVE = [
  '# DUMSKAYA HOME — сайт открыт для поисковых систем и ИИ-ассистентов (ChatGPT, Claude, Perplexity, Gemini, Copilot и др.)',
  '# Закрыто для всех: /api/ — приём заявок',
  'User-agent: *',
  ...RULES,
  '',
  '# ИИ-боты — явное разрешение (поиск и ответы пользователям); запреты те же, что для всех',
  ...bots.map((b) => `User-agent: ${b}`),
  ...RULES,
  '',
  `Sitemap: ${SITE}/sitemap.xml`,
  `# LLM summary: ${SITE}/llms.txt · full text of the catalog: ${SITE}/llms-full.txt`,
  '',
].join('\n');
export const CLOSED = '# DUMSKAYA HOME is not open for search engines yet\nUser-agent: *\nDisallow: /\n';
