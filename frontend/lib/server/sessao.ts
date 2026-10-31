// Cookies de sessão (httpOnly) e renovação de tokens. Só roda no servidor do Next (BFF e proxy).
import type { NextResponse } from "next/server";

export const ACCESS = "mayafit_access";
export const REFRESH = "mayafit_refresh";
export interface Par {
  access: string;
  refresh: string;
}

const SEGURO = process.env.NODE_ENV === "production" && process.env.COOKIE_SECURE !== "false";
const base = { httpOnly: true, secure: SEGURO, sameSite: "lax" as const, path: "/" };

// minutos/dias iguais aos do backend (JWT_ACCESS_MINUTES / JWT_REFRESH_DAYS); o servidor é quem manda na validade real
const ACCESS_SEGUNDOS = Number(process.env.SESSAO_ACCESS_MINUTOS ?? 30) * 60;
const REFRESH_SEGUNDOS = Number(process.env.SESSAO_REFRESH_DIAS ?? 14) * 86400;

export function aplicarCookies(res: NextResponse, par: Par) {
  res.cookies.set(ACCESS, par.access, { ...base, maxAge: ACCESS_SEGUNDOS });
  res.cookies.set(REFRESH, par.refresh, { ...base, maxAge: REFRESH_SEGUNDOS });
}

export function limparCookies(res: NextResponse) {
  res.cookies.set(ACCESS, "", { ...base, maxAge: 0 });
  res.cookies.set(REFRESH, "", { ...base, maxAge: 0 });
}

// Uma renovação por refresh token por vez: várias chamadas simultâneas com o access vencido compartilham o resultado
// (o backend rotaciona o refresh a cada uso; renovar em paralelo derrubaria a sessão).
const emAndamento = new Map<string, Promise<Par | null>>();

export function renovar(refresh: string, api: string): Promise<Par | null> {
  let p = emAndamento.get(refresh);
  if (!p) {
    p = fetch(`${api}/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    })
      .then(async (r) => {
        if (!r.ok) return null;
        const t = (await r.json()) as { access_token: string; refresh_token: string };
        return { access: t.access_token, refresh: t.refresh_token };
      })
      .catch(() => null)
      .finally(() => setTimeout(() => emAndamento.delete(refresh), 20_000));
    emAndamento.set(refresh, p);
  }
  return p;
}
