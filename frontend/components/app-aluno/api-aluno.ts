/**
 * Cliente do app do aluno. Fala só com o BFF do app (`/app/api/*`), que guarda a sessão do aluno em cookie httpOnly.
 * Erros viram `ApiError` (mesma classe do resto do sistema), com a mensagem em português vinda da API.
 */
import { ApiError } from "@/lib/api";

const BASE = "/app/api";

function mensagem(status: number, corpo: unknown): string {
  if (corpo && typeof corpo === "object" && "detail" in corpo && typeof (corpo as { detail: unknown }).detail === "string") {
    return (corpo as { detail: string }).detail;
  }
  if (status === 0) return "Sem conexão com a internet. Confira o sinal e tente de novo.";
  if (status === 429) return "Muitas tentativas. Aguarde um pouco e tente de novo.";
  if (status >= 500) return "O servidor teve um problema. Tente novamente em instantes.";
  return `Erro ${status}`;
}

export async function apiAluno<T>(caminho: string, opts: { method?: "GET" | "POST"; body?: unknown } = {}): Promise<T> {
  const method = opts.method ?? "GET";
  let res: Response;
  try {
    res = await fetch(BASE + caminho, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "X-Requested-With": "mayafit-aluno",
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, mensagem(0, null));
  }
  if (!res.ok) {
    let corpo: unknown = null;
    try {
      corpo = await res.json();
    } catch {
      /* sem corpo */
    }
    throw new ApiError(res.status, mensagem(res.status, corpo), corpo);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const semSessao = (e: unknown) => e instanceof ApiError && e.status === 401;
