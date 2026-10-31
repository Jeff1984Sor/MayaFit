"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, ListChecks, Loader2, RotateCw } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CabecalhoWellhub, PillResultado } from "@/components/wellhub/comum";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora } from "@/lib/format";
import type { EventoDetalhe, EventoWellhub, ListaEventos, ReprocessarOut, ResultadoEvento } from "@/lib/tipos-wellhub";

type Filtro = "todos" | ResultadoEvento | "ignorado";
const FILTROS: Filtro[] = ["todos", "erro", "processado", "cancelado", "rejeitado", "descartado", "ignorado"];
const TIPOS = [
  ["", "Todos os tipos"],
  ["booking-requested", "Reserva pedida"],
  ["booking-canceled", "Reserva cancelada"],
  ["booking-late-canceled", "Cancelamento tardio"],
  ["checkin", "Check-in"],
  ["checkin-booking-occurred", "Check-in em aula reservada"],
] as const;

function useAcoes() {
  const qc = useQueryClient();
  const atualizar = () => {
    qc.invalidateQueries({ queryKey: ["wellhub-eventos"] });
    qc.invalidateQueries({ queryKey: ["wellhub-evento"] });
    qc.invalidateQueries({ queryKey: ["wellhub-painel"] });
  };
  const reprocessar = useMutation({
    mutationFn: (id: number) => api.post<ReprocessarOut>(`/wellhub/eventos/${id}/reprocessar`),
    onSuccess: (r) => {
      if (r.resultado === "erro") toast.error("Ainda com erro", { description: r.mensagem ?? undefined });
      else toast.success("Evento reprocessado", { description: r.evento.tipo_rotulo });
      atualizar();
    },
  });
  const conferir = useMutation({
    mutationFn: ({ id, desfazer }: { id: number; desfazer: boolean }) => api.post<EventoWellhub>(`/wellhub/eventos/${id}/conferido`, undefined, { query: { desfazer } }),
    onSuccess: (e) => {
      toast.success(e.ignorado ? "Erro marcado como conferido (sai dos alertas)" : "Erro voltou para os alertas");
      atualizar();
    },
  });
  return { reprocessar, conferir };
}

function Detalhe({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { pode } = useAuth();
  const q = useQuery({ queryKey: ["wellhub-evento", id], queryFn: () => api.get<EventoDetalhe>(`/wellhub/eventos/${id}`), enabled: id != null });
  const { reprocessar, conferir } = useAcoes();
  const e = q.data;
  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{e ? `${e.tipo_rotulo} · #${e.id}` : "Evento"}</DialogTitle>
          <DialogDescription>Dados pessoais mascarados. O Gympass ID completo fica só no relatório exportado.</DialogDescription>
        </DialogHeader>
        {!e ? (
          <Loader2 className="mx-auto my-8 animate-spin text-muted-foreground" />
        ) : (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <PillResultado resultado={e.resultado} ignorado={e.ignorado} />
              <span className="text-xs text-muted-foreground">
                Recebido {dataHora(e.recebido_em)} · {e.tentativas} tentativa(s) · origem {e.origem}
              </span>
            </div>
            {e.erro && <p className="rounded-lg border border-danger/30 bg-danger/8 px-3 py-2 text-danger-ink">{e.erro}</p>}
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
              {[
                ["Aluno", e.aluno_nome ?? "—"],
                ["Gympass ID", e.gympass_mascarado ?? "—"],
                ["Unidade", e.unidade_nome ?? "—"],
                ["Reserva Wellhub", e.booking_number ?? "—"],
                ["Horário (slot)", e.slot_id ?? "—"],
                ["Reserva na agenda", e.reserva_id ? `#${e.reserva_id}` : "—"],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs text-muted-foreground">{k}</dt>
                  <dd className="font-medium break-all">{v}</dd>
                </div>
              ))}
            </dl>
            <details className="rounded-lg border">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">Conteúdo recebido (JSON)</summary>
              <pre className="max-h-72 overflow-auto border-t bg-muted/40 p-3 font-mono text-xs">{JSON.stringify(e.payload, null, 2)}</pre>
            </details>
            {pode("integracoes.editar") && (
              <div className="flex flex-wrap justify-end gap-2 border-t pt-3">
                {e.resultado === "erro" && (
                  <Button variant="outline" disabled={conferir.isPending} onClick={() => conferir.mutate({ id: e.id, desfazer: e.ignorado })}>
                    {e.ignorado ? <Eye /> : <EyeOff />} {e.ignorado ? "Voltar para os alertas" : "Marcar como conferido"}
                  </Button>
                )}
                {e.pode_reprocessar && (
                  <Button disabled={reprocessar.isPending} onClick={() => reprocessar.mutate(e.id)}>
                    {reprocessar.isPending ? <Loader2 className="animate-spin" /> : <RotateCw />} Reprocessar
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Eventos() {
  const { pode } = useAuth();
  const params = useSearchParams();
  const inicial = params.get("resultado") as Filtro | null;
  const [filtro, setFiltro] = useState<Filtro>(inicial && FILTROS.includes(inicial) ? inicial : "todos");
  const [tipo, setTipo] = useState("");
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(1);
  const [aberto, setAberto] = useState<number | null>(null);
  const { reprocessar } = useAcoes();
  const q = useQuery({
    queryKey: ["wellhub-eventos", filtro, tipo, busca, pagina],
    queryFn: () =>
      api.get<ListaEventos>("/wellhub/eventos", { resultado: filtro === "todos" ? undefined : filtro, tipo: tipo || undefined, q: busca.trim() || undefined, pagina, por_pagina: 20 }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
  const itens = q.data?.itens ?? [];
  const mudar = <T,>(fn: (v: T) => void) => (v: T) => {
    fn(v);
    setPagina(1);
  };
  return (
    <section className="space-y-3">
      <TableCard>
        <Toolbar>
          <Segmented<Filtro>
            value={filtro}
            onChange={mudar(setFiltro)}
            opcoes={[
              { value: "todos", label: "Todos" },
              { value: "erro", label: "Erros", tom: "danger" },
              { value: "processado", label: "Processados" },
              { value: "cancelado", label: "Cancelados" },
              { value: "rejeitado", label: "Recusados" },
              { value: "descartado", label: "Descartados" },
              { value: "ignorado", label: "Conferidos" },
            ]}
          />
          <div className="flex flex-wrap gap-2">
            <NativeSelect value={tipo} onChange={(e) => mudar(setTipo)(e.target.value)} aria-label="Tipo do evento" className="w-52">
              {TIPOS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </NativeSelect>
            <SearchInput value={busca} onChange={mudar(setBusca)} placeholder="Nº da reserva, Gympass ID ou slot" />
          </div>
        </Toolbar>
        {q.isPending ? (
          <TableSkeleton colunas={6} />
        ) : itens.length === 0 ? (
          <EmptyState icone={ListChecks} titulo="Nenhum evento" descricao="Reservas, cancelamentos e check-ins enviados pelo Wellhub aparecem aqui." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Recebido</th>
                  <th className="px-3 py-2.5 font-medium">Evento</th>
                  <th className="px-3 py-2.5 font-medium">Resultado</th>
                  <th className="hidden px-3 py-2.5 font-medium md:table-cell">Aluno</th>
                  <th className="px-3 py-2.5 font-medium">Motivo</th>
                  <th className="px-3 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {itens.map((e) => (
                  <tr key={e.id} className="cursor-pointer transition-colors hover:bg-accent/50" onClick={() => setAberto(e.id)}>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{dataHora(e.recebido_em)}</td>
                    <td className="px-3 py-3">
                      <p className="font-medium">{e.tipo_rotulo}</p>
                      <p className="font-mono text-xs text-muted-foreground">{e.booking_number ?? e.gympass_mascarado ?? ""}</p>
                    </td>
                    <td className="px-3 py-3">
                      <PillResultado resultado={e.resultado} ignorado={e.ignorado} />
                    </td>
                    <td className="hidden px-3 py-3 md:table-cell">{e.aluno_nome ?? "—"}</td>
                    <td className="max-w-80 px-3 py-3 text-xs text-muted-foreground" title={e.erro ?? undefined}>
                      <span className="line-clamp-2">{e.erro ?? ""}</span>
                    </td>
                    <td className="px-3 py-3 text-right" onClick={(ev) => ev.stopPropagation()}>
                      {e.pode_reprocessar && pode("integracoes.editar") && (
                        <Button size="sm" variant="outline" disabled={reprocessar.isPending} onClick={() => reprocessar.mutate(e.id)}>
                          {reprocessar.isPending && reprocessar.variables === e.id ? <Loader2 className="animate-spin" /> : <RotateCw />} Reprocessar
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {q.data && q.data.total > 0 && <Pagination pagina={pagina} porPagina={q.data.por_pagina} total={q.data.total} onChange={setPagina} />}
      </TableCard>
      <Detalhe id={aberto} onClose={() => setAberto(null)} />
    </section>
  );
}

export default function WellhubEventosPage() {
  return (
    <div className="space-y-6">
      <CabecalhoWellhub />
      <Suspense fallback={<TableSkeleton colunas={6} />}>
        <Eventos />
      </Suspense>
    </div>
  );
}
