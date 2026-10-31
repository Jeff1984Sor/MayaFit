/**
 * BFF do app do aluno: único caminho do navegador (PWA em /app) até `/api/aluno-app/*`.
 *
 * - Access/refresh do ALUNO vivem em cookies httpOnly com path `/app` (o JavaScript nunca os vê).
 * - Só repassa para `aluno-app/*` da API (lista fechada de rotas): o app do aluno não consegue falar com as rotas da equipe.
 * - Login: `auth/verificar` devolve tokens, que viram cookies e SAEM da resposta ao navegador.
 * - Renova o access sozinho (refresh curto) e repete a chamada uma vez.
 * - CSRF: SameSite=Lax + cabeçalho `X-Requested-With` + conferência de Origin nas escritas.
 */
import { NextRequest, NextResponse } from "next/server";

import { ACCESS, REFRESH, aplicarCookies, limparCookies, renovar, type Par } from "../_sessao";

const API = (process.env.INTERNAL_API_URL ?? "http://localhost:8000/api").replace(/\/$/, "");
const REPASSAR = ["content-type", "cache-control", "retry-after"];
// rotas aceitas (o resto é 404): nada de repassar caminho livre
const PERMITIDAS = /^(auth\/(codigo|verificar)|me|aulas|aulas\/\d+\/(confirmar|desmarcar)|reposicoes|reposicoes\/\d+\/pedir)$/;
const SEM_SESSAO = new Set(["auth/codigo", "auth/verificar"]);

function origemValida(req: NextRequest): boolean {
  if (["GET", "HEAD", "OPTIONS"].includes(req.method)) return true;
  const origin = req.headers.get("origin");
  if (!origin) return true;
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

function encaminhar(req: NextRequest, caminho: string, corpo: ArrayBuffer | undefined, access: string | undefined) {
  const h = new Headers();
  const ct = req.headers.get("content-type");
  if (ct) h.set("content-type", ct);
  if (access) h.set("authorization", `Bearer ${access}`);
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim();
  if (ip) h.set("x-forwarded-for", ip);
  return fetch(`${API}/aluno-app/${caminho}${req.nextUrl.search}`, {
    method: req.method,
    headers: h,
    body: corpo,
    redirect: "manual",
    cache: "no-store",
  });
}

function resposta(r: Response) {
  const h = new Headers();
  REPASSAR.forEach((k) => {
    const v = r.headers.get(k);
    if (v) h.set(k, v);
  });
  h.set("cache-control", "no-store");
  return new NextResponse(r.body, { status: r.status, headers: h });
}

async function tratar(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const caminho = (await ctx.params).path.join("/");
  if (caminho === "auth/sair") {
    if (!origemValida(req) || req.method !== "POST") return NextResponse.json({ detail: "Requisição recusada." }, { status: 403 });
    const out = NextResponse.json({ mensagem: "Sessão encerrada." });
    limparCookies(out);
    return out;
  }
  if (!PERMITIDAS.test(caminho)) return NextResponse.json({ detail: "Não encontrado." }, { status: 404 });
  if (!origemValida(req) || (req.method !== "GET" && req.headers.get("x-requested-with") !== "mayafit-aluno")) {
    return NextResponse.json({ detail: "Requisição recusada." }, { status: 403 });
  }

  const corpo = ["GET", "HEAD"].includes(req.method) ? undefined : await req.arrayBuffer();
  const publica = SEM_SESSAO.has(caminho);
  let access = req.cookies.get(ACCESS)?.value;
  const refresh = req.cookies.get(REFRESH)?.value;
  let novoPar: Par | null = null;

  if (!publica && !access && refresh) {
    novoPar = await renovar(refresh, API);
    access = novoPar?.access;
  }
  if (!publica && !access) {
    const out = NextResponse.json({ detail: "Entre com seu CPF para continuar." }, { status: 401 });
    if (refresh) limparCookies(out);
    return out;
  }

  let r: Response;
  try {
    r = await encaminhar(req, caminho, corpo, publica ? undefined : access);
    if (r.status === 401 && !publica && refresh && !novoPar) {
      novoPar = await renovar(refresh, API);
      if (novoPar) r = await encaminhar(req, caminho, corpo, novoPar.access);
    }
  } catch {
    return NextResponse.json({ detail: "Não foi possível falar com o servidor." }, { status: 502 });
  }

  let out: NextResponse;
  if (caminho === "auth/verificar" && r.ok) {
    const t = (await r.json()) as { access_token: string; refresh_token: string };
    novoPar = { access: t.access_token, refresh: t.refresh_token };
    out = NextResponse.json({ ok: true });
  } else {
    out = resposta(r);
  }
  if (novoPar) aplicarCookies(out, novoPar);
  else if (r.status === 401 && !publica) limparCookies(out);
  return out;
}

export const GET = tratar;
export const POST = tratar;
