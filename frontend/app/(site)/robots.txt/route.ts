import { carregarPagina, origemPublica } from "@/components/site/servidor";

/** robots.txt: com o site no ar, indexa a raiz (o site) e a política; o sistema (login, telas internas) fica de fora. */
export async function GET() {
  const p = await carregarPagina().catch(() => null);
  const origem = await origemPublica();
  const corpo = p
    ? ["User-agent: *", "Allow: /$", "Allow: /s/", "Allow: /_next/", "Disallow: /", "", `Sitemap: ${origem}/sitemap.xml`, ""]
    : ["User-agent: *", "Disallow: /", ""];
  return new Response(corpo.join("\n"), { headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "public, max-age=3600" } });
}
