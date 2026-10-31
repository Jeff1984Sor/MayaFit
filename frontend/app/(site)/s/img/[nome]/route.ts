import { API_INTERNA, cabecalhosApi } from "@/components/site/servidor";

/** Fotos do site (públicas). Repassa o host do estúdio à API; cache longo porque o nome muda quando a foto muda. */
export async function GET(_req: Request, ctx: { params: Promise<{ nome: string }> }) {
  const { nome } = await ctx.params;
  if (!/^[0-9a-f]{32}\.(png|jpe?g|webp)$/.test(nome)) return new Response(null, { status: 404 });
  try {
    const r = await fetch(`${API_INTERNA}/site-publico/imagens/${nome}`, { headers: await cabecalhosApi(), cache: "no-store" });
    if (!r.ok) return new Response(null, { status: r.status === 429 ? 429 : 404 });
    return new Response(r.body, {
      headers: {
        "content-type": r.headers.get("content-type") ?? "application/octet-stream",
        "cache-control": "public, max-age=31536000, immutable",
        "x-content-type-options": "nosniff",
      },
    });
  } catch {
    return new Response(null, { status: 502 });
  }
}
