"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Clock, MessageCircle, Plus, TriangleAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { UserAvatar } from "@/components/mayacorp/user-avatar";
import { api } from "@/lib/api";
import { moeda, moedaCompacta, toNum } from "@/lib/format";
import type { ColunaFunil, Funil, LeadCartao } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

import { OrigemTag, TemperaturaBadge, quandoCurto } from "./comum";
import { ConverterDialog, PerdaDialog } from "./dialogos";

function Cartao({ lead, cor, onAbrir, arrastavel }: { lead: LeadCartao; cor: string; onAbrir: () => void; arrastavel: boolean }) {
  const aulaFutura = lead.aula_experimental_status === "AGENDADA" && lead.aula_experimental_em;
  return (
    <div
      role="button"
      tabIndex={0}
      draggable={arrastavel}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/lead", String(lead.id));
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={onAbrir}
      onKeyDown={(e) => e.key === "Enter" && onAbrir()}
      className={cn(
        "group relative cursor-pointer rounded-xl border bg-card p-3 text-left shadow-xs transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none",
        arrastavel && "active:cursor-grabbing",
        lead.situacao !== "ABERTO" && "opacity-75",
      )}
      style={{ borderLeft: `3px solid ${cor}` }}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 truncate text-sm font-semibold">{lead.nome}</p>
        {lead.situacao === "ABERTO" && <TemperaturaBadge t={lead.temperatura} compacto />}
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <OrigemTag origem={lead.origem} />
        {lead.interesse && <span className="truncate text-xs text-muted-foreground">· {lead.interesse}</span>}
      </div>
      {aulaFutura && (
        <p className="mt-2 inline-flex items-center gap-1 rounded-md bg-warning/12 px-1.5 py-0.5 text-[11px] font-medium text-warning-ink">
          <CalendarClock className="size-3" /> Aula {quandoCurto(lead.aula_experimental_em!)}
        </p>
      )}
      {lead.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {lead.tags.slice(0, 3).map((t) => (
            <span key={t} className="rounded-full bg-muted px-1.5 text-[10px] text-muted-foreground">
              {t}
            </span>
          ))}
        </div>
      )}
      <div className="mt-2.5 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-2">
          {lead.valor_estimado && toNum(lead.valor_estimado) > 0 && <span className="num font-medium text-foreground">{moeda(lead.valor_estimado)}</span>}
          {lead.situacao === "ABERTO" && (
            <span className={cn("inline-flex items-center gap-0.5", lead.parado && "font-medium text-danger-ink")} title="Dias nesta etapa">
              {lead.parado ? <TriangleAlert className="size-3" /> : <Clock className="size-3" />}
              {lead.dias_na_etapa}d
            </span>
          )}
          {lead.tarefa_atrasada && (
            <span className="inline-flex items-center gap-0.5 font-medium text-danger-ink" title="Tarefa atrasada">
              <TriangleAlert className="size-3" /> tarefa
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {lead.whatsapp_url && (
            <a
              href={lead.whatsapp_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="grid size-6 place-items-center rounded-full text-[#1A8F5E] opacity-70 transition hover:bg-[#1A8F5E]/10 hover:opacity-100"
              aria-label={`WhatsApp de ${lead.nome}`}
            >
              <MessageCircle className="size-3.5" />
            </a>
          )}
          {lead.responsavel && <UserAvatar nome={lead.responsavel.nome} className="size-5" textoClassName="text-[9px]" />}
        </div>
      </div>
    </div>
  );
}

export function Kanban({
  funil,
  chave,
  podeEditar,
  onNovo,
}: {
  funil: Funil;
  chave: readonly unknown[];
  podeEditar: boolean;
  onNovo: (etapaId: number) => void;
}) {
  const qc = useQueryClient();
  const router = useRouter();
  const [sobre, setSobre] = useState<number | null>(null);
  const [perder, setPerder] = useState<LeadCartao | null>(null);
  const [converter, setConverter] = useState<LeadCartao | null>(null);
  const perdido = funil.colunas.find((c) => c.etapa.tipo === "PERDIDO");

  const mover = useMutation({
    mutationFn: ({ lead, etapaId }: { lead: LeadCartao; etapaId: number }) => api.post(`/crm/leads/${lead.id}/mover`, { etapa_id: etapaId }),
    onMutate: async ({ lead, etapaId }) => {
      await qc.cancelQueries({ queryKey: chave });
      const anterior = qc.getQueryData<Funil>(chave);
      qc.setQueryData<Funil>(chave, (f) =>
        f
          ? {
              colunas: f.colunas.map((c) => {
                const leads = c.leads.filter((l) => l.id !== lead.id);
                if (c.etapa.id === etapaId) leads.unshift({ ...lead, etapa_id: etapaId, dias_na_etapa: 0, parado: false });
                return { ...c, leads, total: leads.length };
              }),
            }
          : f,
      );
      return { anterior };
    },
    onError: (_e, _v, ctx) => ctx?.anterior && qc.setQueryData(chave, ctx.anterior),
    onSuccess: (_r, { lead, etapaId }) => {
      const destino = funil.colunas.find((c) => c.etapa.id === etapaId)?.etapa.nome;
      toast.success(`${lead.nome} → ${destino}`);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["crm"] }),
  });

  function soltar(col: ColunaFunil, leadId: number) {
    setSobre(null);
    const lead = funil.colunas.flatMap((c) => c.leads).find((l) => l.id === leadId);
    if (!lead || lead.etapa_id === col.etapa.id) return;
    if (col.etapa.tipo === "PERDIDO") setPerder(lead);
    else if (col.etapa.tipo === "GANHO") setConverter(lead);
    else mover.mutate({ lead, etapaId: col.etapa.id });
  }

  return (
    <>
      <div className="-mx-4 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6">
        <div className="flex min-w-max gap-3">
          {funil.colunas.map((col) => {
            const encerrada = col.etapa.tipo !== "ABERTA";
            return (
              <section
                key={col.etapa.id}
                aria-label={col.etapa.nome}
                onDragOver={(e) => {
                  if (!podeEditar) return;
                  e.preventDefault();
                  setSobre(col.etapa.id);
                }}
                onDragLeave={() => setSobre((s) => (s === col.etapa.id ? null : s))}
                onDrop={(e) => {
                  e.preventDefault();
                  const id = Number(e.dataTransfer.getData("text/lead"));
                  if (id) soltar(col, id);
                }}
                className={cn(
                  "flex w-72 shrink-0 flex-col rounded-2xl border bg-muted/40 transition-colors",
                  encerrada && "w-64 bg-muted/20",
                  sobre === col.etapa.id && "border-brand bg-brand/8 ring-2 ring-brand/30",
                )}
              >
                <header className="flex items-center justify-between gap-2 px-3 pt-3 pb-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="size-2.5 shrink-0 rounded-full" style={{ background: col.etapa.cor }} />
                      <h3 className="truncate text-sm font-semibold">{col.etapa.nome}</h3>
                      <span className="rounded-full bg-background px-1.5 text-xs text-muted-foreground tabular-nums">{col.total}</span>
                    </div>
                    <p className="mt-0.5 pl-4.5 text-[11px] text-muted-foreground">
                      {encerrada ? "últimos 30 dias" : toNum(col.valor_total) > 0 ? `${moedaCompacta(col.valor_total)} em negociação` : " "}
                    </p>
                  </div>
                  {!encerrada && podeEditar && (
                    <button
                      type="button"
                      onClick={() => onNovo(col.etapa.id)}
                      className="grid size-7 place-items-center rounded-lg text-muted-foreground hover:bg-background hover:text-foreground"
                      aria-label={`Novo lead em ${col.etapa.nome}`}
                    >
                      <Plus className="size-4" />
                    </button>
                  )}
                </header>
                <div className="flex max-h-[calc(100dvh-22rem)] min-h-32 flex-col gap-2 overflow-y-auto px-2 pb-3">
                  {col.leads.map((l) => (
                    <Cartao key={l.id} lead={l} cor={col.etapa.cor} arrastavel={podeEditar} onAbrir={() => router.push(`/crm/leads/${l.id}`)} />
                  ))}
                  {col.leads.length === 0 && (
                    <div className="grid flex-1 place-items-center rounded-xl border border-dashed p-4 text-center text-xs text-muted-foreground">
                      {podeEditar ? (encerrada ? "Arraste um lead para cá" : "Nenhum lead aqui. Arraste ou clique em +") : "Vazio"}
                    </div>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      </div>
      {perder && perdido && <PerdaDialog lead={perder} etapaPerdidoId={perdido.etapa.id} onFechar={() => setPerder(null)} />}
      {converter && <ConverterDialog lead={converter} onFechar={() => setConverter(null)} />}
    </>
  );
}
