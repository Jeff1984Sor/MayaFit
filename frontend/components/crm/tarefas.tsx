"use client";

import { useMutation } from "@tanstack/react-query";
import { Bot, Check, MessageCircle, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Tarefa } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

import { quandoCurto } from "./comum";
import { TarefaDialog, useInvalidarCrm } from "./dialogos";

function Item({ t, mostrarLead, podeEditar }: { t: Tarefa; mostrarLead: boolean; podeEditar: boolean }) {
  const invalidar = useInvalidarCrm();
  const { pode } = useAuth();
  const [feita, setFeita] = useState(t.concluida);
  const [editar, setEditar] = useState(false);
  const alternar = useMutation({
    mutationFn: (concluir: boolean) => api.post(`/crm/tarefas/${t.id}/${concluir ? "concluir" : "reabrir"}`),
    onMutate: (concluir) => setFeita(concluir),
    onError: () => setFeita(t.concluida),
    onSuccess: (_r, concluir) => {
      if (concluir)
        toast.success("Tarefa concluída.", { action: { label: "Desfazer", onClick: () => alternar.mutate(false) } });
      invalidar();
    },
  });
  const excluir = useMutation({
    mutationFn: () => api.del(`/crm/tarefas/${t.id}`),
    onSuccess: () => {
      toast.success("Tarefa excluída.");
      invalidar();
    },
  });
  const atrasada = !feita && t.situacao === "atrasada";
  return (
    <li
      className={cn(
        "group flex items-start gap-3 rounded-xl border bg-card px-3 py-2.5 transition-colors",
        atrasada && "border-danger/40 bg-danger/5",
        feita && "opacity-60",
      )}
    >
      <button
        type="button"
        disabled={!podeEditar || alternar.isPending}
        onClick={() => alternar.mutate(!feita)}
        aria-label={feita ? "Reabrir tarefa" : "Concluir tarefa"}
        className={cn(
          "mt-0.5 grid size-5 shrink-0 place-items-center rounded-md border-2 transition-colors",
          feita ? "border-success bg-success text-white" : atrasada ? "border-danger hover:bg-danger/10" : "border-muted-foreground/40 hover:border-brand",
        )}
      >
        {feita && <Check className="size-3.5" />}
      </button>
      <div className="min-w-0 flex-1">
        <p className={cn("text-sm font-medium", feita && "line-through")}>
          {t.titulo}
          {t.automatica && <Bot className="ml-1 inline size-3.5 text-muted-foreground" aria-label="Criada automaticamente" />}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          <span className={cn(atrasada && "font-semibold text-danger-ink")}>
            {atrasada ? "Atrasada · " : ""}
            {quandoCurto(t.vence_em)}
          </span>
          {mostrarLead && t.lead_id && (
            <Link href={`/crm/leads/${t.lead_id}`} className="font-medium text-foreground hover:underline">
              {t.lead_nome}
            </Link>
          )}
          {t.responsavel ? <span>· {t.responsavel.nome}</span> : <span>· Equipe</span>}
        </p>
        {t.descricao && <p className="mt-1 text-xs text-muted-foreground">{t.descricao}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        {t.whatsapp_url && !feita && (
          <a
            href={t.whatsapp_url}
            target="_blank"
            rel="noopener noreferrer"
            className="grid size-7 place-items-center rounded-full text-[#1A8F5E] hover:bg-[#1A8F5E]/10"
            aria-label={`WhatsApp de ${t.lead_nome}`}
          >
            <MessageCircle className="size-4" />
          </a>
        )}
        {podeEditar && (
          <button
            type="button"
            onClick={() => setEditar(true)}
            className="grid size-7 place-items-center rounded-full text-muted-foreground opacity-0 transition group-hover:opacity-100 hover:bg-muted focus:opacity-100"
            aria-label="Editar tarefa"
          >
            <Pencil className="size-3.5" />
          </button>
        )}
        {pode("crm.excluir") && (
          <button
            type="button"
            onClick={() => excluir.mutate()}
            className="grid size-7 place-items-center rounded-full text-muted-foreground opacity-0 transition group-hover:opacity-100 hover:bg-muted hover:text-danger focus:opacity-100"
            aria-label="Excluir tarefa"
          >
            <Trash2 className="size-3.5" />
          </button>
        )}
      </div>
      {editar && <TarefaDialog aberto tarefa={t} onFechar={() => setEditar(false)} />}
    </li>
  );
}

export function ListaDeTarefas({
  tarefas,
  mostrarLead = true,
  podeEditar,
  vazio,
}: {
  tarefas: Tarefa[];
  mostrarLead?: boolean;
  podeEditar: boolean;
  vazio: string;
}) {
  if (tarefas.length === 0) return <p className="text-sm text-muted-foreground">{vazio}</p>;
  return (
    <ul className="space-y-2">
      {tarefas.map((t) => (
        <Item key={`${t.id}-${t.concluida}`} t={t} mostrarLead={mostrarLead} podeEditar={podeEditar} />
      ))}
    </ul>
  );
}
