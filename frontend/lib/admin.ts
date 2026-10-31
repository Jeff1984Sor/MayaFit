// Admin MayaCorp: consultas compartilhadas entre as telas (/api/admin/* via BFF). Tipos em ./tipos-admin.
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "./api";
import { useAuth } from "./auth";
import type { Estudio, PlanoOut, ResumoAdmin, Rotulo, UsuarioComEstudio } from "./tipos-admin";

/** Teste grátis padrão de um estúdio novo (decisão do Jefferson: 2 meses). */
export const DIAS_TESTE_PADRAO = 60;

/** O usuário está no admin da MayaCorp (estúdio "mayacorp") e é administrador. */
export function useAreaMayaCorp() {
  const { usuario, administrador, carregando } = useAuth();
  const u = usuario as UsuarioComEstudio | undefined;
  return { mayacorp: !!u?.estudio?.mayacorp, administrador, carregando };
}

export const chaves = {
  tudo: ["admin"] as const,
  resumo: ["admin", "resumo"] as const,
  estudios: (filtros: Record<string, unknown> = {}) => ["admin", "estudios", filtros] as const,
  estudio: (id: number | string) => ["admin", "estudio", String(id)] as const,
  planos: ["admin", "planos"] as const,
};

export function useEstudios(filtros: { q?: string; status?: string } = {}, enabled = true) {
  return useQuery({
    queryKey: chaves.estudios(filtros),
    queryFn: () => api.get<Estudio[]>("/admin/clientes", { q: filtros.q || undefined, status: filtros.status || undefined }),
    enabled,
  });
}

export function useResumoAdmin() {
  return useQuery({ queryKey: chaves.resumo, queryFn: () => api.get<ResumoAdmin>("/admin/resumo") });
}

export function usePlanos(enabled = true) {
  return useQuery({ queryKey: chaves.planos, queryFn: () => api.get<PlanoOut[]>("/admin/planos"), enabled });
}

export function useRecursos() {
  return useQuery({ queryKey: ["admin", "recursos"], queryFn: () => api.get<Rotulo[]>("/admin/recursos"), staleTime: 10 * 60_000 });
}

export function useExtras(enabled = true) {
  return useQuery({ queryKey: ["admin", "extras"], queryFn: () => api.get<Rotulo[]>("/admin/extras"), staleTime: 10 * 60_000, enabled });
}

export function copiarTexto(texto: string, ok = "Link copiado") {
  navigator.clipboard.writeText(texto).then(
    () => toast.success(ok),
    () => toast.error("Não deu para copiar. Selecione o texto e copie."),
  );
}

/** Passo da régua em palavras: -3 → "3 dias antes", 0 → "no dia", 5 → "5 dias depois". */
export const passoRegua = (d: number) => (d === 0 ? "no dia" : d < 0 ? `${-d} dia(s) antes` : `${d} dia(s) depois`);

/** "2026-10" → "10/2026". */
export const mesAno = (comp: string | null | undefined) => (comp ? comp.split("-").reverse().join("/") : "—");

/** Dias entre hoje e a data (negativo = passou). */
export function diasAte(iso: string | null | undefined) {
  if (!iso) return null;
  const alvo = new Date(`${iso.slice(0, 10)}T00:00:00`);
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  return Math.round((alvo.getTime() - hoje.getTime()) / 86_400_000);
}

export const valorDoCiclo = (p: PlanoOut, ciclo: "mensal" | "anual") => (ciclo === "anual" ? p.preco_anual : p.preco_mensal);

export const soDigitos = (v: string | null | undefined) => (v ?? "").replace(/\D/g, "");
