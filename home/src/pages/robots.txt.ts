export function GET() {
  return new Response('User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: https://dumskaya-home.com/sitemap.xml\n\n# LLM summary: https://dumskaya-home.com/llms.txt\n', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
