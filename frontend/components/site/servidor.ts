/**
 * Acesso à API pelo SERVIDOR do Next para o site público. O estúdio é definido pelo host: repassamos o host original
 * (`X-Forwarded-Host`) e o IP do visitante (`X-Forwarded-For`, usado no rate limit da API).
 * Não importar em componentes de cliente.
 */
import { headers } from "next/headers";
import { cache } from "react";

import type { PaginaPublica } from "@/lib/tipos-site";

export const API_INTERNA = (process.env.INTERNAL_API_URL ?? "http://localhost:8000/api").replace(/\/$/, "");

export async function hostDaRequisicao(): Promise<string> {
  const h = await headers();
  return (h.get("x-forwarded-host") ?? h.get("host") ?? "localhost").split(",")[0].trim();
}

export async function origemPublica(): Promise<string> {
  const h = await headers();
  const host = await hostDaRequisicao();
  const local = /^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host);
  const proto = h.get("x-forwarded-proto")?.split(",")[0].trim() ?? (local ? "http" : "https");
  return `${proto}://${host}`;
}

export async function cabecalhosApi(extra?: Record<string, string>): Promise<Headers> {
  const h = await headers();
  const out = new Headers(extra);
  out.set("x-forwarded-host", await hostDaRequisicao());
  const ip = h.get("x-forwarded-for")?.split(",")[0].trim() ?? h.get("x-real-ip");
  if (ip) out.set("x-forwarded-for", ip);
  return out;
}

/** Página publicada do estúdio do host atual; `null` quando o site não está no ar. Uma ida à API por requisição
 * (metadata e página compartilham o resultado). */
export const carregarPagina = cache(async (): Promise<PaginaPublica | null> => {
  const r = await fetch(`${API_INTERNA}/site-publico/pagina`, { headers: await cabecalhosApi(), cache: "no-store" });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`site: API respondeu ${r.status}`);
  return (await r.json()) as PaginaPublica;
});
