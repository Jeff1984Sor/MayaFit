"use server";

import { API_INTERNA, cabecalhosApi } from "@/components/site/servidor";

export interface DadosContato {
  nome: string;
  telefone: string;
  email: string;
  interesse: string;
  mensagem: string;
  quer_aula_experimental: boolean;
  consentimento: boolean;
  website: string;
  tempo_ms: number;
}

export type ResultadoContato = { ok: true; mensagem: string } | { ok: false; erro: string };

/** Envia o formulário do site à API (o Next repassa o host do estúdio e o IP do visitante). */
export async function enviarContato(dados: DadosContato): Promise<ResultadoContato> {
  try {
    const r = await fetch(`${API_INTERNA}/site-publico/contato`, {
      method: "POST",
      headers: await cabecalhosApi({ "content-type": "application/json" }),
      body: JSON.stringify(dados),
      cache: "no-store",
    });
    const corpo = (await r.json().catch(() => ({}))) as { mensagem?: string; detail?: string };
    if (r.ok) return { ok: true, mensagem: corpo.mensagem ?? "Recebemos seu contato!" };
    if (r.status === 429) return { ok: false, erro: "Muitos envios seguidos. Aguarde alguns minutos e tente de novo." };
    return { ok: false, erro: typeof corpo.detail === "string" ? corpo.detail : "Não foi possível enviar agora. Tente de novo." };
  } catch {
    return { ok: false, erro: "Não foi possível enviar agora. Tente pelo WhatsApp ou mais tarde." };
  }
}
