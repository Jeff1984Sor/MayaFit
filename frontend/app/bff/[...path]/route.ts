/**
 * BFF (backend-for-frontend): único caminho do navegador até a API.
 *
 * - Access e refresh token vivem em cookies httpOnly (o JavaScript da página nunca os vê: XSS não rouba sessão).
 * - O BFF anexa `Authorization: Bearer` ao repassar a chamada e, se a API responder 401, renova o par de tokens
 *   (uma renovação por vez, mesmo com várias chamadas simultâneas) e repete a chamada uma vez.
 * - Login/troca de senha: os tokens que a API devolve viram cookies e são REMOVIDOS da resposta ao navegador.
 * - CSRF: cookies SameSite=Lax + exigência do cabeçalho `X-Requested-With` + conferência de Origin nas escritas.
 * - `/auth/refresh` não é exposto ao navegador.
 */
import { NextRequest, NextResponse } from "next/server";

import { ACCESS, REFRESH, aplicarCookies, limparCookies, renovar, type Par } from "@/lib/server/sessao";

const API = (process.env.INTERNAL_API_URL ?? "http://localhost:8000/api").replace(/\/$/, "");
const REPASSAR = ["content-type", "content-disposition", "cache-control", "retry-after", "content-length"];
// rotas que respondem com TokenOut: viram cookies
const ROTAS_DE_TOKEN = new Set(["auth/login", "auth/trocar-senha", "auth/primeiro-acesso"]);
// rotas que não exigem sessão
const ROTAS_PUBLICAS = /^(auth\/(login|forgot|reset|forgot-codigo|reset-codigo|primeiro-acesso)|public\/.*|arquivos-publicos\/.*|assinar\/(contrato|termo)\/.*|health)$/;

function origemValida(req: NextRequest): boolean {
  if (["GET", "HEAD", "OPTIONS"].includes(req.method)) return true;
  const origin = req.headers.get("origin");
  if (!origin) return true; // chamadas same-origin sem Origin (alguns navegadores) dependem do SameSite + X-Requested-With
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

async function encaminhar(req: NextRequest, caminho: string, corpo: ArrayBuffer | undefined, access: string | undefined) {
  const h = new Headers();
  const ct = req.headers.get("content-type");
  if (ct) h.set("content-type", ct);
  if (access) h.set("authorization", `Bearer ${access}`);
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim();
  if (ip) h.set("x-forwarded-for", ip);
  return fetch(`${API}/${caminho}${req.nextUrl.search}`, { method: req.method, headers: h, body: corpo, redirect: "manual", cache: "no-store" });
}

function resposta(r: Response, corpo?: BodyInit | null) {
  const h = new Headers();
  REPASSAR.forEach((k) => {
    const v = r.headers.get(k);
    if (v && !(corpo !== undefined && k === "content-length")) h.set(k, v);
  });
  return new NextResponse(corpo !== undefined ? corpo : r.body, { status: r.status, headers: h });
}

async function tratar(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const caminho = (await ctx.params).path.join("/");
  if (caminho.includes("..") || caminho === "auth/refresh") return NextResponse.json({ detail: "Não encontrado." }, { status: 404 });
  if (!origemValida(req) || (req.method !== "GET" && req.headers.get("x-requested-with") !== "mayafit")) {
    return NextResponse.json({ detail: "Requisição recusada." }, { status: 403 });
  }

  const corpo = ["GET", "HEAD"].includes(req.method) ? undefined : await req.arrayBuffer();

  if (caminho === "auth/logout") {
    const access = req.cookies.get(ACCESS)?.value;
    if (access) await encaminhar(req, caminho, corpo, access).catch(() => null);
    const out = NextResponse.json({ mensagem: "Sessão encerrada." });
    limparCookies(out);
    return out;
  }

  let access = req.cookies.get(ACCESS)?.value;
  const refresh = req.cookies.get(REFRESH)?.value;
  let novoPar: Par | null = null;
  const publica = ROTAS_PUBLICAS.test(caminho);

  if (!publica && !access && refresh) {
    novoPar = await renovar(refresh, API);
    access = novoPar?.access;
  }
  if (!publica && !access) {
    const out = NextResponse.json({ detail: "Faça login para continuar." }, { status: 401 });
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
  if (ROTAS_DE_TOKEN.has(caminho) && req.method === "POST" && r.ok) {
    const t = (await r.json()) as { access_token: string; refresh_token: string; usuario: unknown };
    novoPar = { access: t.access_token, refresh: t.refresh_token };
    out = NextResponse.json({ usuario: t.usuario });
  } else {
    out = resposta(r);
  }
  if (novoPar) aplicarCookies(out, novoPar);
  else if (r.status === 401 && !publica) limparCookies(out); // sessão não renovável: o navegador volta ao login
  return out;
}

export const GET = tratar;
export const POST = tratar;
export const PUT = tratar;
export const PATCH = tratar;
export const DELETE = tratar;
