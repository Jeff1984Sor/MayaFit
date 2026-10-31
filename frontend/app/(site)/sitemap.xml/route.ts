import { carregarPagina, origemPublica } from "@/components/site/servidor";

/** sitemap.xml do host do estúdio: a página do site e a política de privacidade (vazio se o site não está no ar). */
export async function GET() {
  const p = await carregarPagina().catch(() => null);
  const origem = await origemPublica();
  const lastmod = p?.publicado_em ? `<lastmod>${p.publicado_em.slice(0, 10)}</lastmod>` : "";
  const urls = p
    ? [`<url><loc>${origem}/</loc>${lastmod}<changefreq>weekly</changefreq><priority>1.0</priority></url>`,
       `<url><loc>${origem}/s/privacidade</loc>${lastmod}<priority>0.2</priority></url>`]
    : [];
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.join("")}</urlset>\n`;
  return new Response(xml, { headers: { "content-type": "application/xml; charset=utf-8", "cache-control": "public, max-age=3600" } });
}
