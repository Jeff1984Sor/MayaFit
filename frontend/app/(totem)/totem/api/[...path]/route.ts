/**
 * BFF do totem: único caminho do navegador do totem até `/api/totem/*`.
 *
 * - O token do DISPOSITIVO vive em cookie httpOnly `mf_totem` (path /totem): o JavaScript da página nunca o vê.
 * - Lista fechada de rotas: o totem não consegue falar com as rotas da equipe.
 * - `parear` valida o token na API (GET /totem/me) antes de gravar o cookie; `desparear` apaga o cookie.
 * - CSRF: SameSite=Lax + cabeçalho `X-Requested-With: mayafit-totem` + conferência de Origin nas escritas.
 */
import { NextRequest, NextResponse } from "next/server";

const API = (process.env.INTERNAL_API_URL ?? "http://localhost:8000/api").replace(/\/$/, "");
const COOKIE = "mf_totem";
const SEGURO = process.env.NODE_ENV === "production" && process.env.COOKIE_SECURE !== "false";
const BASE_COOKIE = { httpOnly: true, secure: SEGURO, sameSite: "lax" as const, path: "/totem" };
const MAX_IDADE = 400 * 86400;
const REPASSAR = ["content-type", "retry-after"];
const PERMITIDAS = /^(me|identificar\/(facial|documento|qr)|registros\/\d+\/catraca|cadastro\/(iniciar|concluir))$/;
const LEITURA = new Set(["me"]);

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

function cabecalhos(req: NextRequest, token: string, comCorpo: boolean) {
  const h = new Headers();
  if (comCorpo) h.set("content-type", "application/json");
  h.set("x-dispositivo-token", token);
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim();
  if (ip) h.set("x-forwarded-for", ip);
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  if (host) h.set("x-forwarded-host", host);
  return h;
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

const recusada = () => NextResponse.json({ detail: "Requisição recusada." }, { status: 403 });

async function parear(req: NextRequest) {
  let token = "";
  try {
    token = String(((await req.json()) as { token?: unknown }).token ?? "").trim();
  } catch {
    /* corpo inválido */
  }
  if (!/^mfdisp_[A-Za-z0-9_-]{20,}$/.test(token)) {
    return NextResponse.json({ detail: "Token inválido. Copie o token completo gerado em Catracas e totens." }, { status: 422 });
  }
  let r: Response;
  try {
    r = await fetch(`${API}/totem/me`, { headers: cabecalhos(req, token, false), cache: "no-store" });
  } catch {
    return NextResponse.json({ detail: "Não foi possível falar com o servidor." }, { status: 502 });
  }
  if (!r.ok) return resposta(r);
  const out = NextResponse.json(await r.json());
  out.cookies.set(COOKIE, token, { ...BASE_COOKIE, maxAge: MAX_IDADE });
  return out;
}

async function tratar(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const caminho = (await ctx.params).path.join("/");
  const escrita = req.method !== "GET";
  if (escrita && (!origemValida(req) || req.headers.get("x-requested-with") !== "mayafit-totem")) return recusada();

  if (caminho === "parear" && req.method === "POST") return parear(req);
  if (caminho === "desparear" && req.method === "POST") {
    const out = NextResponse.json({ mensagem: "Totem desconectado." });
    out.cookies.set(COOKIE, "", { ...BASE_COOKIE, maxAge: 0 });
    return out;
  }
  if (!PERMITIDAS.test(caminho) || (LEITURA.has(caminho) ? escrita : !escrita)) {
    return NextResponse.json({ detail: "Não encontrado." }, { status: 404 });
  }

  const token = req.cookies.get(COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Totem não pareado." }, { status: 401 });

  const corpo = escrita ? await req.arrayBuffer() : undefined;
  let r: Response;
  try {
    r = await fetch(`${API}/totem/${caminho}`, {
      method: req.method,
      headers: cabecalhos(req, token, escrita),
      body: corpo,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Não foi possível falar com o servidor." }, { status: 502 });
  }
  return resposta(r);
}

export const GET = tratar;
export const POST = tratar;
