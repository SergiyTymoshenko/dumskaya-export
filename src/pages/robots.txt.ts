export function GET() {
  return new Response(`User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: https://dumskaya-design.com/sitemap.xml\n\n# Справка для нейросетей / LLM summary: https://dumskaya-design.com/llms.txt\n`, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
