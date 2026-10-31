"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, HandCoins, ListTodo, Sparkles, Trophy, UsersRound } from "lucide-react";
import Link from "next/link";

import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { moedaCompacta, numero } from "@/lib/format";
import type { ResumoCrm } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

export function Indicador({
  titulo,
  valor,
  sub,
  icone: Icone,
  tom,
  href,
  carregando,
}: {
  titulo: string;
  valor: React.ReactNode;
  sub?: React.ReactNode;
  icone: React.ComponentType<{ className?: string }>;
  tom?: "danger" | "success" | "warning";
  href?: string;
  carregando?: boolean;
}) {
  const corpo = (
    <div
      className={cn(
        "card-surface relative h-full overflow-hidden p-4 transition-shadow",
        href && "hover:shadow-md",
        tom === "danger" && "ring-1 ring-danger/30",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-muted-foreground">{titulo}</p>
        <div
          className={cn(
            "grid size-8 place-items-center rounded-lg bg-brand/10 text-navy dark:text-brand",
            tom === "danger" && "bg-danger/10 text-danger-ink",
            tom === "success" && "bg-success/10 text-success-ink",
            tom === "warning" && "bg-warning/12 text-warning-ink",
          )}
        >
          <Icone className="size-4" />
        </div>
      </div>
      {carregando ? <Skeleton className="mt-3 h-8 w-24" /> : <p className="mt-1.5 text-2xl font-semibold tracking-tight num">{valor}</p>}
      {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
  return href ? (
    <Link href={href} className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-2xl">
      {corpo}
    </Link>
  ) : (
    corpo
  );
}

/** Indicadores do topo do funil + frase de destaque do dia. */
export function ResumoFunil() {
  const q = useQuery({ queryKey: ["crm", "resumo"], queryFn: () => api.get<ResumoCrm>("/crm/resumo") });
  const r = q.data;
  const c = q.isPending;
  return (
    <div className="mb-4 space-y-3">
      {r?.destaque && (
        <div className="flex items-center gap-3 rounded-2xl border border-brand/30 bg-linear-to-r from-brand/12 via-brand/5 to-transparent px-4 py-3 text-sm">
          <div className="grid size-8 shrink-0 place-items-center rounded-lg brand-gradient text-white shadow-sm">
            <Sparkles className="size-4" />
          </div>
          <p className="font-medium">{r.destaque}</p>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Indicador carregando={c} titulo="Leads em aberto" icone={UsersRound} valor={numero(r?.abertos)} sub={`${r?.novos_7_dias ?? 0} novos nos últimos 7 dias`} href="/crm/leads" />
        <Indicador carregando={c} titulo="Em negociação" icone={HandCoins} valor={moedaCompacta(r?.valor_em_negociacao)} sub="soma do valor mensal estimado" />
        <Indicador
          carregando={c}
          titulo="Conversão (30 dias)"
          icone={Trophy}
          tom="success"
          valor={`${(r?.taxa_conversao_30_dias ?? 0).toLocaleString("pt-BR")}%`}
          sub={`${r?.conversoes_30_dias ?? 0} matrícula(s) fechadas`}
          href="/crm/relatorio"
        />
        <Indicador
          carregando={c}
          titulo="Minhas tarefas hoje"
          icone={ListTodo}
          tom={r?.tarefas_atrasadas ? "danger" : undefined}
          valor={numero((r?.tarefas_hoje ?? 0) + (r?.tarefas_atrasadas ?? 0))}
          sub={r?.tarefas_atrasadas ? <span className="font-medium text-danger-ink">{r.tarefas_atrasadas} atrasada(s)</span> : "nenhuma atrasada"}
          href="/crm/tarefas"
        />
        <Indicador
          carregando={c}
          titulo="Aulas experimentais hoje"
          icone={CalendarClock}
          tom={r?.aulas_experimentais_hoje ? "warning" : undefined}
          valor={numero(r?.aulas_experimentais_hoje)}
          sub={`${r?.parados ?? 0} lead(s) parados na etapa`}
        />
      </div>
    </div>
  );
}
