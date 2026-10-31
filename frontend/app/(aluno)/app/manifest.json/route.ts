// Manifest do app do aluno, com a marca do estúdio vinda do banco (nome e cor de destaque via /api/public/identidade).
import { NextResponse } from "next/server";

const API = (process.env.INTERNAL_API_URL ?? "http://localhost:8000/api").replace(/\/$/, "");

export const dynamic = "force-dynamic";

export async function GET() {
  let nome = "MayaFit";
  let cor = "#7c8fff";
  try {
    const r = await fetch(`${API}/public/identidade`, { cache: "no-store", signal: AbortSignal.timeout(4000) });
    if (r.ok) {
      const j = (await r.json()) as { nome_exibicao?: string; cor_destaque?: string | null };
      if (j.nome_exibicao) nome = j.nome_exibicao;
      if (j.cor_destaque && /^#[0-9a-f]{6}$/i.test(j.cor_destaque)) cor = j.cor_destaque;
    }
  } catch {
    /* sem a API, vale o padrão neutro */
  }
  const curto = nome.length > 12 ? nome.split(" ")[0].slice(0, 12) : nome;
  const corpo = {
    name: nome,
    short_name: curto,
    description: `Suas aulas no ${nome}: confirme, desmarque e agende reposições.`,
    lang: "pt-BR",
    id: "/app/",
    start_url: "/app/",
    scope: "/app/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#ffffff",
    theme_color: cor,
    icons: [
      { src: "/app/icone/192", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/app/icone/512", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/app/icone/512-maskable", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
  return new NextResponse(JSON.stringify(corpo), {
    headers: { "content-type": "application/manifest+json; charset=utf-8", "cache-control": "public, max-age=300" },
  });
}
