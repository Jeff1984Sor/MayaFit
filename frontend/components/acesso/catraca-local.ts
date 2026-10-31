"use client";

/**
 * Executa na REDE LOCAL o plano de acionamento da catraca que a API devolve (modo "totem"): o servidor fica na nuvem e
 * não alcança a catraca; o navegador do totem (ou da recepção) alcança. Ex.: Control iD = login.fcgi -> execute_actions.
 *
 * Requisitos no equipamento real (ver docs/progresso-acesso.md): a página do sistema é HTTPS, então a catraca precisa
 * aceitar HTTPS (certificado aceito no tablet) e responder CORS; senão o navegador bloqueia e o caminho é o agente local.
 */
import type { PlanoCatraca } from "@/lib/tipos-acesso";

export interface ResultadoLocal {
  ok: boolean;
  detalhe: string;
}

const TEMPO_POR_PASSO_MS = 4000;

export async function executarPlano(plano: PlanoCatraca): Promise<ResultadoLocal> {
  if (!plano.passos.length) return { ok: true, detalhe: plano.descricao || "Nada a acionar." };
  let sessao = "";
  for (const [i, p] of plano.passos.entries()) {
    const url = p.url.replaceAll("{sessao}", encodeURIComponent(sessao));
    const ultimo = i === plano.passos.length - 1;
    let r: Response;
    try {
      r = await fetch(url, {
        method: p.metodo,
        headers: { "Content-Type": "application/json" },
        body: p.corpo ? JSON.stringify(p.corpo) : undefined,
        mode: "cors",
        cache: "no-store",
        credentials: "omit",
        signal: AbortSignal.timeout(TEMPO_POR_PASSO_MS),
      });
    } catch (e) {
      if (ultimo && i > 0) return { ok: true, detalhe: "Giro liberado (o encerramento da sessão não respondeu)." };
      const tempo = e instanceof DOMException && e.name === "TimeoutError";
      return {
        ok: false,
        detalhe: tempo
          ? "A catraca não respondeu a tempo. Confira o IP e se o tablet está na mesma rede."
          : "O navegador não conseguiu falar com a catraca (rede, HTTPS ou CORS do equipamento).",
      };
    }
    if (!r.ok && !ultimo) {
      return { ok: false, detalhe: r.status === 401 || r.status === 403 ? "Usuário ou senha da catraca recusados." : `A catraca respondeu com erro (HTTP ${r.status}).` };
    }
    if (p.extrair) {
      try {
        const j = (await r.json()) as Record<string, unknown>;
        sessao = String(j[p.extrair] ?? "");
      } catch {
        sessao = "";
      }
      if (!sessao) return { ok: false, detalhe: "A catraca não devolveu a sessão. Confira usuário e senha." };
    }
  }
  return { ok: true, detalhe: "Giro liberado." };
}
