// Ícones PNG do app (192, 512 e 512-maskable) com a marca do estúdio: cor de destaque + iniciais do nome (ou o logo).
import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";

const API = (process.env.INTERNAL_API_URL ?? "http://localhost:8000/api").replace(/\/$/, "");

export const dynamic = "force-dynamic";

function iniciais(nome: string) {
  const p = nome.trim().split(/\s+/).filter(Boolean);
  if (p.length === 0) return "P";
  return (p.length === 1 ? p[0].slice(0, 2) : p[0][0] + p[p.length - 1][0]).toUpperCase();
}

async function marca() {
  let nome = "MayaFit";
  let cor = "#b0486b";
  let logo: string | null = null;
  try {
    const r = await fetch(`${API}/public/identidade`, { cache: "no-store", signal: AbortSignal.timeout(4000) });
    if (r.ok) {
      const j = (await r.json()) as { nome_exibicao?: string; cor_destaque?: string | null; logo_url?: string | null };
      if (j.nome_exibicao) nome = j.nome_exibicao;
      if (j.cor_destaque && /^#[0-9a-f]{6}$/i.test(j.cor_destaque)) cor = j.cor_destaque;
      if (j.logo_url) {
        const l = await fetch(`${API}${j.logo_url.replace(/^\/api/, "")}`, { cache: "no-store", signal: AbortSignal.timeout(4000) });
        const tipo = l.headers.get("content-type") ?? "";
        if (l.ok && /^image\/(png|jpeg|webp)$/.test(tipo)) {
          logo = `data:${tipo};base64,${Buffer.from(await l.arrayBuffer()).toString("base64")}`;
        }
      }
    }
  } catch {
    /* padrão neutro */
  }
  return { nome, cor, logo };
}

export async function GET(_req: NextRequest, ctx: { params: Promise<{ tamanho: string }> }) {
  const { tamanho } = await ctx.params;
  const m = /^(192|512)(-maskable)?$/.exec(tamanho);
  if (!m) return new Response("Não encontrado", { status: 404 });
  const lado = Number(m[1]);
  const maskable = !!m[2];
  const { nome, cor, logo } = await marca();
  // maskable: o conteúdo fica na "zona segura" central (80%); o fundo ocupa tudo
  const conteudo = Math.round(lado * (maskable ? 0.5 : 0.62));
  return new ImageResponse(
    (
      <div
        style={{
          width: lado,
          height: lado,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: cor,
          borderRadius: maskable ? 0 : Math.round(lado * 0.22),
          color: "#ffffff",
        }}
      >
        {logo ? (
          <div style={{ display: "flex", width: conteudo, height: conteudo, background: "#ffffff", borderRadius: Math.round(conteudo * 0.2), alignItems: "center", justifyContent: "center" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logo} alt="" width={Math.round(conteudo * 0.86)} height={Math.round(conteudo * 0.86)} style={{ objectFit: "contain" }} />
          </div>
        ) : (
          <div style={{ display: "flex", fontSize: Math.round(conteudo * 0.9), fontWeight: 700, letterSpacing: -2 }}>{iniciais(nome)}</div>
        )}
      </div>
    ),
    { width: lado, height: lado, headers: { "cache-control": "public, max-age=300" } },
  );
}
