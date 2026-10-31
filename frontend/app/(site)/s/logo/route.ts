import { API_INTERNA, cabecalhosApi } from "@/components/site/servidor";

/** Logo da Identidade do estúdio para o site (e para o ícone/OpenGraph). */
export async function GET() {
  try {
    const r = await fetch(`${API_INTERNA}/public/logo`, { headers: await cabecalhosApi(), cache: "no-store" });
    if (!r.ok) return new Response(null, { status: 404 });
    return new Response(r.body, {
      headers: {
        "content-type": r.headers.get("content-type") ?? "image/png",
        "cache-control": "public, max-age=3600",
        "x-content-type-options": "nosniff",
      },
    });
  } catch {
    return new Response(null, { status: 502 });
  }
}
