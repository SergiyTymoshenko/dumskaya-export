// llms.txt — справка о каталоге для нейросетей (home/src/lib/llms.ts): только опубликованное.
import { llmsTxt } from '../lib/llms';

export function GET() {
  return new Response(llmsTxt(), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
