"use client";

// Cliente do BFF do totem (/totem/api/*). O token do dispositivo fica em cookie httpOnly; aqui nunca aparece.

export class ErroTotem extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function mensagem(status: number, corpo: unknown): string {
  if (corpo && typeof corpo === "object" && "detail" in corpo && typeof (corpo as { detail: unknown }).detail === "string") {
    return (corpo as { detail: string }).detail;
  }
  if (status === 0 || status === 502) return "Sem conexão com o servidor. Verifique a internet do totem.";
  if (status === 429) return "Muitas tentativas. Aguarde um pouquinho.";
  if (status >= 500) return "O servidor teve um problema. Tente de novo em instantes.";
  return `Erro ${status}`;
}

export async function totemApi<T>(caminho: string, corpo?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`/totem/api/${caminho}`, {
      method: corpo === undefined ? "GET" : "POST",
      headers: corpo === undefined ? undefined : { "Content-Type": "application/json", "X-Requested-With": "mayafit-totem" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch {
    throw new ErroTotem(0, mensagem(0, null));
  }
  let j: unknown = null;
  try {
    j = await r.json();
  } catch {
    /* sem corpo */
  }
  if (!r.ok) throw new ErroTotem(r.status, mensagem(r.status, j));
  return j as T;
}

/** 401 = totem sem token válido (revogado ou nunca pareado). */
export const precisaParear = (e: unknown) => e instanceof ErroTotem && e.status === 401;
