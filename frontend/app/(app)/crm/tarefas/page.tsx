"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CircleCheckBig, ListTodo, Plus, PartyPopper } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { CrmNav } from "@/components/crm/comum";
import { TarefaDialog } from "@/components/crm/dialogos";
import { ListaDeTarefas } from "@/components/crm/tarefas";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ListaTarefas } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

type Situacao = "hoje" | "pendentes" | "concluidas";
type Escopo = "minhas" | "todas";

function saudacao() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

export default function TarefasPage() {
  const { pode, usuario } = useAuth();
  const [situacao, setSituacao] = useState<Situacao>("hoje");
  const [escopo, setEscopo] = useState<Escopo>("minhas");
  const [nova, setNova] = useState(false);
  const q = useQuery({
    queryKey: ["crm", "tarefas", escopo, situacao],
    queryFn: () => api.get<ListaTarefas>("/crm/tarefas", { escopo, situacao }),
    placeholderData: keepPreviousData,
    enabled: pode("crm.ver"),
  });
  if (!pode("crm.ver")) return <SemAcesso titulo="Tarefas do CRM" />;
  const c = q.data?.contagens;
  const itens = q.data?.itens ?? [];
  const atrasadas = itens.filter((t) => t.situacao === "atrasada");
  const resto = itens.filter((t) => t.situacao !== "atrasada");
  const pendentesHoje = (c?.atrasadas ?? 0) + (c?.hoje ?? 0);
  const total = pendentesHoje + (c?.concluidas_hoje ?? 0);
  const progresso = total ? Math.round(((c?.concluidas_hoje ?? 0) / total) * 100) : 0;
  const podeEditar = pode("crm.editar");

  return (
    <div>
      <PageHeader
        icone={ListTodo}
        titulo="Minhas tarefas"
        descricao="Ligações, mensagens e lembretes do funil. As atrasadas ficam no topo, em vermelho."
        acoes={
          podeEditar && (
            <Button onClick={() => setNova(true)}>
              <Plus /> Nova tarefa
            </Button>
          )
        }
      />
      <CrmNav />

      <div className="card-surface mb-4 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-base font-semibold">
            {saudacao()}, {usuario?.nome.split(" ")[0]}!
          </p>
          <p className="text-sm text-muted-foreground">
            {pendentesHoje === 0
              ? "Nada pendente para hoje."
              : `Você tem ${pendentesHoje} tarefa(s) para hoje${c?.atrasadas ? `, ${c.atrasadas} atrasada(s)` : ""}.`}
          </p>
        </div>
        <div className="w-full sm:w-64">
          <div className="mb-1 flex justify-between text-xs text-muted-foreground">
            <span>Progresso do dia</span>
            <span className="num">
              {c?.concluidas_hoje ?? 0}/{total}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-success transition-all duration-500" style={{ width: `${progresso}%` }} />
          </div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2" role="tablist">
          {(
            [
              ["hoje", "Hoje", pendentesHoje],
              ["pendentes", "Todas pendentes", (c?.atrasadas ?? 0) + (c?.hoje ?? 0) + (c?.futuras ?? 0)],
              ["concluidas", "Concluídas", undefined],
            ] as const
          ).map(([v, r, n]) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={situacao === v}
              onClick={() => setSituacao(v)}
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded-full border px-3.5 text-sm font-medium transition-colors",
                situacao === v ? "border-brand bg-brand/10" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {r}
              {n !== undefined && <span className="rounded-full bg-muted px-1.5 text-xs tabular-nums">{n}</span>}
            </button>
          ))}
        </div>
        <div className="inline-flex rounded-lg border p-0.5 text-sm">
          {(["minhas", "todas"] as const).map((e) => (
            <button
              key={e}
              type="button"
              onClick={() => setEscopo(e)}
              className={cn("rounded-md px-3 py-1", escopo === e ? "bg-muted font-medium" : "text-muted-foreground")}
            >
              {e === "minhas" ? "Minhas e da equipe" : "De todos"}
            </button>
          ))}
        </div>
      </div>

      {q.isPending ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : itens.length === 0 ? (
        <div className="card-surface">
          <EmptyState
            icone={situacao === "concluidas" ? CircleCheckBig : PartyPopper}
            titulo={situacao === "concluidas" ? "Nenhuma tarefa concluída ainda" : "Tudo em dia!"}
            descricao={
              situacao === "concluidas"
                ? "Conclua tarefas e elas aparecem aqui."
                : "Sem pendências por aqui. Que tal abrir o funil e puxar conversa com quem está parado?"
            }
            acao={
              situacao !== "concluidas" && (
                <Button variant="outline" render={<Link href="/crm" />}>
                  Abrir o funil
                </Button>
              )
            }
          />
        </div>
      ) : (
        <div className="space-y-5">
          {atrasadas.length > 0 && situacao !== "concluidas" && (
            <section>
              <h2 className="mb-2 text-xs font-semibold tracking-wide text-danger-ink uppercase">Atrasadas ({atrasadas.length})</h2>
              <ListaDeTarefas tarefas={atrasadas} podeEditar={podeEditar} vazio="" />
            </section>
          )}
          {resto.length > 0 && (
            <section>
              {situacao !== "concluidas" && (
                <h2 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  {situacao === "hoje" ? "Para hoje" : "Próximas"} ({resto.length})
                </h2>
              )}
              <ListaDeTarefas tarefas={resto} podeEditar={podeEditar} vazio="" />
            </section>
          )}
        </div>
      )}
      {nova && <TarefaDialog aberto onFechar={() => setNova(false)} />}
    </div>
  );
}
