// /llms.txt — краткая справка о студии для нейросетей (стандарт llmstxt.org).
import { llmsTxt } from '../lib/llms';
export function GET() {
  return new Response(llmsTxt(), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
