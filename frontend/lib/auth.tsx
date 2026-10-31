"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useMemo } from "react";

import { ApiError, api } from "./api";
import type { UsuarioMe } from "./types";

interface AuthCtx {
  usuario: UsuarioMe | undefined;
  carregando: boolean;
  logado: boolean;
  login: (identificador: string, senha: string) => Promise<UsuarioMe>;
  sair: () => Promise<void>;
  /** Permissão do perfil de acesso ("recurso.acao"); o administrador pode tudo. O servidor confere de novo. */
  pode: (permissao: string) => boolean;
  /** Perfil de acesso com "Acesso total". */
  administrador: boolean;
  /** Perfil que só enxerga as próprias aulas (Professor). */
  somenteProprias: boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const router = useRouter();

  // A sessão mora em cookie httpOnly (BFF). Quem decide se há sessão é a API: /auth/me responde 401 sem ela.
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<UsuarioMe>("/auth/me"),
    staleTime: 5 * 60_000,
    retry: false,
    meta: { silencioso: true },
    // páginas públicas (e o site do estúdio, marcado com #site-publico, que pode estar na raiz "/") não têm sessão
    enabled:
      typeof window !== "undefined" &&
      !/^\/(login|esqueci-senha|redefinir-senha|assinar|app)(\/|$)/.test(window.location.pathname) &&
      !document.getElementById("site-publico"),
  });

  const login = useCallback(
    async (identificador: string, senha: string) => {
      const r = await api.post<{ usuario: UsuarioMe }>("/auth/login", { identificador, senha }, { auth: false });
      qc.setQueryData(["me"], r.usuario);
      return r.usuario;
    },
    [qc],
  );

  const sair = useCallback(async () => {
    try {
      await api.post("/auth/logout", undefined, { auth: false });
    } catch {
      /* sai mesmo assim: o cookie é limpo pelo BFF */
    }
    qc.clear();
    router.replace("/login");
  }, [qc, router]);

  const value = useMemo<AuthCtx>(() => {
    const usuario = me.data;
    const administrador = !!usuario?.administrador;
    const permissoes = new Set(usuario?.permissoes ?? []);
    const pode = (permissao: string) => !!usuario && (administrador || permissoes.has(permissao));
    return {
      usuario,
      carregando: me.isPending && !me.isError,
      logado: !!usuario,
      login,
      sair,
      pode,
      administrador,
      somenteProprias: !!usuario?.somente_proprias_aulas,
    };
  }, [me.data, me.isPending, me.isError, login, sair]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth fora do AuthProvider");
  return c;
}

export function sessaoExpirou(e: unknown) {
  return e instanceof ApiError && e.status === 401;
}
