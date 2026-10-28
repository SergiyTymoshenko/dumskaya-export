// robots.txt студии (решено 28.10.2026): сайт открыт для поисковиков и ИИ-ассистентов (ChatGPT, Claude, Perplexity,
// Gemini, Copilot и др.) — как на usk.ua. Две группы: общая (*) и ИИ-боты (список — content/ai_bots.json, общий с
// dumskaya-home.com). У бота со своей группой общая не действует, поэтому запреты повторены в обеих; Disallow — первыми,
// Allow: / — последним. Закрыто: /api/ — «Студия», кабинеты заказчиков и подрядчиков, графики, приём заявок.
import bots from '../../content/ai_bots.json';

const SITE = 'https://dumskaya-design.com';
const CLOSED = ['/api/'];

function robotsTxt(): string {
  const rules = [...CLOSED.map((p) => `Disallow: ${p}`), 'Allow: /'];
  return [
    '# DUMSKAYA DESIGN — сайт открыт для поисковых систем и ИИ-ассистентов (ChatGPT, Claude, Perplexity, Gemini, Copilot и др.)',
    '# Закрыто для всех: /api/ — кабинеты, «Студия» и приём заявок',
    'User-agent: *',
    ...rules,
    '',
    '# ИИ-боты — явное разрешение (поиск и ответы пользователям); запреты те же, что для всех',
    ...(bots.agents as string[]).map((b) => `User-agent: ${b}`),
    ...rules,
    '',
    `Sitemap: ${SITE}/sitemap.xml`,
    `# Справка для нейросетей / LLM summary: ${SITE}/llms.txt · полный текст сайта / full text: ${SITE}/llms-full.txt`,
    '',
  ].join('\n');
}

export function GET() {
  return new Response(robotsTxt(), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
