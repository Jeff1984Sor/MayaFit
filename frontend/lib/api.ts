/**
 * Cliente da API. O navegador NUNCA fala direto com a API nem enxerga tokens: tudo passa pelo BFF do Next
 * (`/bff/*`, ver app/bff/[...path]/route.ts), que guarda access/refresh em cookies httpOnly, renova o access
 * sozinho e repassa a chamada à API com `Authorization`. Por isso não há `localStorage` de token aqui.
 */
export const API_URL = "/bff";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
  }
}

type PydanticErro = { loc?: (string | number)[]; msg?: string };

function mensagemDeErro(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return (detail as PydanticErro[])
        .map((d) => {
          const campo = d.loc?.filter((l) => l !== "body").join(".");
          return campo ? `${campo}: ${d.msg}` : d.msg;
        })
        .join(" · ");
    }
  }
  if (status === 0) return "Não foi possível falar com o servidor. Verifique sua conexão.";
  if (status >= 500) return "O servidor teve um problema. Tente novamente em instantes.";
  return `Erro ${status}`;
}

function irParaLogin() {
  if (typeof window !== "undefined" && !/^\/(login|esqueci-senha|redefinir-senha|assinar|app)(\/|$)/.test(window.location.pathname)) {
    const volta = encodeURIComponent(window.location.pathname + window.location.search);
    // navegação completa de propósito: zera o estado em memória (cache de dados do usuário anterior)
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?volta=${volta}`;
  }
}

export interface RequestOpts extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** arrays viram parâmetros repetidos (?a=1&a=2) */
  query?: Record<string, string | number | boolean | null | undefined | (string | number)[]>;
  auth?: boolean;
}

function montarUrl(path: string, query?: RequestOpts["query"]) {
  const url = new URL(API_URL + path, typeof window === "undefined" ? "http://localhost" : window.location.origin);
  Object.entries(query ?? {}).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, String(x)));
    else if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });
  return url.toString();
}

async function rawFetch(path: string, opts: RequestOpts = {}): Promise<Response> {
  const { body, query, auth = true, headers, ...rest } = opts;
  const h = new Headers(headers);
  let payload: BodyInit | undefined;
  if (body instanceof FormData || body instanceof Blob) payload = body;
  else if (body !== undefined) {
    h.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }
  h.set("X-Requested-With", "mayafit");

  let res: Response;
  try {
    res = await fetch(montarUrl(path, query), { ...rest, headers: h, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, mensagemDeErro(0, null));
  }

  // o BFF já tentou renovar a sessão; 401 aqui = sessão encerrada
  if (res.status === 401 && auth) irParaLogin();
  if (!res.ok) {
    let b: unknown = null;
    try {
      b = await res.json();
    } catch {
      /* corpo vazio */
    }
    throw new ApiError(res.status, mensagemDeErro(res.status, b), b);
  }
  return res;
}

export async function api<T = unknown>(path: string, opts: RequestOpts = {}): Promise<T> {
  const res = await rawFetch(path, opts);
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

api.get = <T>(path: string, query?: RequestOpts["query"]) => api<T>(path, { query });
api.post = <T>(path: string, body?: unknown, opts?: RequestOpts) => api<T>(path, { ...opts, method: "POST", body });
api.put = <T>(path: string, body?: unknown) => api<T>(path, { method: "PUT", body });
api.patch = <T>(path: string, body?: unknown) => api<T>(path, { method: "PATCH", body });
api.del = <T>(path: string) => api<T>(path, { method: "DELETE" });

function nomeDoCabecalho(res: Response, fallback: string) {
  const cd = res.headers.get("content-disposition") ?? "";
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
  return m ? decodeURIComponent(m[1] ?? m[2]) : fallback;
}

/** Busca um arquivo autenticado e devolve blob + nome. */
export async function baixarBlob(path: string, opts: RequestOpts = {}, fallback = "arquivo") {
  const res = await rawFetch(path, opts);
  return { blob: await res.blob(), nome: nomeDoCabecalho(res, fallback) };
}

/** Faz download autenticado (fetch com Bearer → blob → objectURL). */
export async function baixar(path: string, opts: RequestOpts = {}, fallback = "arquivo") {
  const { blob, nome } = await baixarBlob(path, opts, fallback);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Abre um arquivo autenticado (ex.: PDF) em nova aba. */
export async function abrirArquivo(path: string) {
  const janela = window.open("", "_blank");
  const { blob } = await baixarBlob(path);
  const url = URL.createObjectURL(blob);
  if (janela) janela.location.href = url;
  else window.open(url, "_blank");
}
