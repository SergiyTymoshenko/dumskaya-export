// /llms-full.txt — полный текст сайта в Markdown для нейросетей: раздел → страница → адреса на всех языках → текст (src/lib/llms.ts).
import { llmsFullTxt } from '../lib/llms';
export function GET() {
  return new Response(llmsFullTxt(), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
