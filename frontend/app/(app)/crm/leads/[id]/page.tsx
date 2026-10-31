"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  CalendarPlus,
  Check,
  GraduationCap,
  Lightbulb,
  ListTodo,
  Pencil,
  Phone,
  Plus,
  RotateCcw,
  Send,
  ThumbsDown,
  Trash2,
  UserX,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { CrmNav, INTERACAO, OrigemTag, ROTULO_ORIGEM, TemperaturaBadge, quandoCurto, useOpcoesCrm } from "@/components/crm/comum";
import { AulaDialog, ConverterDialog, LeadDialog, PerdaDialog, ResultadoAulaBotoes, TarefaDialog, useInvalidarCrm } from "@/components/crm/dialogos";
import { ListaDeTarefas } from "@/components/crm/tarefas";
import { BotaoWhatsapp } from "@/components/crm/whatsapp";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora, moeda, relativo, toNum } from "@/lib/format";
import type { LeadFicha, TipoInteracao } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

const TIPOS: TipoInteracao[] = ["NOTA", "LIGACAO", "WHATSAPP", "VISITA", "EMAIL"];

function Registrar({ lead }: { lead: LeadFicha }) {
  const invalidar = useInvalidarCrm();
  const [tipo, setTipo] = useState<TipoInteracao>("NOTA");
  const [texto, setTexto] = useState("");
  const salvar = useMutation({
    mutationFn: () => api.post(`/crm/leads/${lead.id}/interacoes`, { tipo, descricao: texto.trim() }),
    onSuccess: () => {
      setTexto("");
      toast.success(`${INTERACAO[tipo].rotulo} registrada.`);
      invalidar();
    },
  });
  return (
    <div className="card-surface p-4">
      <div className="mb-2 flex flex-wrap gap-1">
        {TIPOS.map((t) => {
          const I = INTERACAO[t].icone;
          return (
            <button
              key={t}
              type="button"
              onClick={() => setTipo(t)}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                tipo === t ? "border-brand bg-brand/10" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <I className="size-3.5" /> {INTERACAO[t].rotulo}
            </button>
          );
        })}
      </div>
      <Textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && texto.trim()) salvar.mutate();
        }}
        placeholder={tipo === "LIGACAO" ? "Como foi a ligação? O que ficou combinado?" : "Escreva o que aconteceu..."}
        rows={3}
        maxLength={4000}
      />
      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-muted-foreground">Ctrl + Enter para salvar</span>
        <Button size="sm" disabled={!texto.trim() || salvar.isPending} onClick={() => salvar.mutate()}>
          <Send /> Registrar
        </Button>
      </div>
    </div>
  );
}

function Linha({ lead, podeExcluir }: { lead: LeadFicha; podeExcluir: boolean }) {
  const invalidar = useInvalidarCrm();
  const excluir = useMutation({
    mutationFn: (id: number) => api.del(`/crm/leads/${lead.id}/interacoes/${id}`),
    onSuccess: () => {
      toast.success("Interação excluída.");
      invalidar();
    },
  });
  if (lead.interacoes.length === 0) return <p className="p-4 text-sm text-muted-foreground">Nenhuma interação ainda.</p>;
  return (
    <ol className="relative space-y-4 border-l pl-6">
      {lead.interacoes.map((i) => {
        const c = INTERACAO[i.tipo];
        const I = c.icone;
        return (
          <li key={i.id} className="group relative">
            <span className={cn("absolute top-0 -left-[37px] grid size-7 place-items-center rounded-full ring-4 ring-background", c.cor)}>
              <I className="size-3.5" />
            </span>
            <div className="flex items-baseline justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{i.tipo === "SISTEMA" ? "Registro automático" : c.rotulo}</span>
                {i.usuario && ` · ${i.usuario.nome}`} · <span title={dataHora(i.ocorrido_em)}>{relativo(i.ocorrido_em)}</span>
              </p>
              {podeExcluir && i.tipo !== "SISTEMA" && (
                <button
                  type="button"
                  onClick={() => excluir.mutate(i.id)}
                  className="opacity-0 transition group-hover:opacity-100 focus:opacity-100"
                  aria-label="Excluir interação"
                >
                  <Trash2 className="size-3.5 text-muted-foreground hover:text-danger" />
                </button>
              )}
            </div>
            <p className={cn("mt-0.5 text-sm whitespace-pre-line", i.tipo === "SISTEMA" && "text-muted-foreground")}>{i.descricao}</p>
          </li>
        );
      })}
    </ol>
  );
}

function Etapas({ lead, podeEditar, onPerder, onGanhar }: { lead: LeadFicha; podeEditar: boolean; onPerder: () => void; onGanhar: () => void }) {
  const opcoes = useOpcoesCrm();
  const invalidar = useInvalidarCrm();
  const mover = useMutation({
    mutationFn: (etapa_id: number) => api.post(`/crm/leads/${lead.id}/mover`, { etapa_id }),
    onSuccess: () => {
      toast.success("Etapa atualizada.");
      invalidar();
    },
  });
  const etapas = opcoes.data?.etapas ?? [];
  const abertas = etapas.filter((e) => e.tipo === "ABERTA");
  const atual = etapas.find((e) => e.id === lead.etapa_id);
  const idx = abertas.findIndex((e) => e.id === lead.etapa_id);
  return (
    <div className="flex flex-wrap items-center gap-1">
      {abertas.map((e, i) => {
        const feito = lead.situacao === "GANHO" || (idx >= 0 && i < idx);
        const corrente = e.id === lead.etapa_id;
        return (
          <button
            key={e.id}
            type="button"
            disabled={!podeEditar || corrente || mover.isPending}
            onClick={() => mover.mutate(e.id)}
            title={podeEditar && !corrente ? `Mover para ${e.nome}` : undefined}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:cursor-default",
              corrente && "text-white",
              !corrente && feito && "border-transparent bg-muted text-foreground",
              !corrente && !feito && "text-muted-foreground hover:bg-muted",
            )}
            style={corrente ? { background: e.cor, borderColor: e.cor } : undefined}
          >
            {feito && !corrente && <Check className="size-3" />}
            {e.nome}
          </button>
        );
      })}
      {atual && atual.tipo !== "ABERTA" && (
        <Pill tom={atual.tipo === "GANHO" ? "success" : "danger"} className="ml-1">
          {atual.nome}
        </Pill>
      )}
      {podeEditar && lead.situacao === "ABERTO" && (
        <span className="ml-auto flex gap-1">
          <Button size="sm" variant="outline" className="text-danger-ink" onClick={onPerder}>
            <ThumbsDown /> Perdido
          </Button>
          <Button size="sm" className="bg-[#1A8F5E] text-white hover:bg-[#1A8F5E]/85" onClick={onGanhar}>
            <GraduationCap /> Matricular
          </Button>
        </span>
      )}
    </div>
  );
}

export default function FichaLeadPage() {
  const { id } = useParams<{ id: string }>();
  const leadId = Number(id);
  const router = useRouter();
  const { pode } = useAuth();
  const opcoes = useOpcoesCrm();
  const invalidar = useInvalidarCrm();
  const [editar, setEditar] = useState(false);
  const [aula, setAula] = useState(false);
  const [perder, setPerder] = useState(false);
  const [ganhar, setGanhar] = useState(false);
  const [tarefa, setTarefa] = useState(false);
  const [excluir, setExcluir] = useState(false);
  const podeEditar = pode("crm.editar");

  const q = useQuery({
    queryKey: ["crm", "lead", leadId],
    queryFn: () => api.get<LeadFicha>(`/crm/leads/${leadId}`),
    enabled: pode("crm.ver") && Number.isInteger(leadId),
    retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2,
    meta: { silencioso: true },
  });
  const reabrir = useMutation({
    mutationFn: () => api.post(`/crm/leads/${leadId}/reabrir`),
    onSuccess: () => {
      toast.success("Lead reaberto. Bora retomar o contato!");
      invalidar();
    },
  });
  const apagar = useMutation({
    mutationFn: () => api.del(`/crm/leads/${leadId}`),
    onSuccess: () => {
      toast.success("Lead excluído.");
      invalidar();
      router.replace("/crm");
    },
  });
  const registrarZap = useMutation({
    mutationFn: (titulo: string) => api.post(`/crm/leads/${leadId}/interacoes`, { tipo: "WHATSAPP", descricao: `Mensagem enviada: ${titulo}.` }),
    onSuccess: () => invalidar(),
    meta: { silencioso: true },
  });

  if (!pode("crm.ver")) return <SemAcesso titulo="Lead" />;
  if (q.isError)
    return (
      <EmptyState
        icone={UserX}
        titulo="Lead não encontrado"
        descricao="Ele pode ter sido excluído."
        acao={
          <Button variant="outline" onClick={() => router.replace("/crm")}>
            Voltar ao funil
          </Button>
        }
        className="py-20"
      />
    );
  if (q.isPending || !q.data) return <Skeleton className="h-96 rounded-2xl" />;
  const l = q.data;
  const perdido = opcoes.data?.etapas.find((e) => e.tipo === "PERDIDO");
  const aulaAgendada = l.aula_experimental_status === "AGENDADA" && l.aula_experimental_em;
  const aulaPassou = aulaAgendada && new Date(l.aula_experimental_em!) < new Date();

  return (
    <div>
      <PageHeader
        titulo={
          <span className="flex flex-wrap items-center gap-2">
            {l.nome} <TemperaturaBadge t={l.temperatura} />
          </span>
        }
        descricao={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <OrigemTag origem={l.origem} />
            {l.indicado_por && <span>indicado(a) por {l.indicado_por}</span>}
            {l.telefone_formatado && <span>{l.telefone_formatado}</span>}
            {l.email && <span>{l.email}</span>}
            <span>entrou {relativo(l.criado_em)}</span>
          </span>
        }
        migalhas={[{ label: "CRM", href: "/crm" }, { label: "Leads", href: "/crm/leads" }, { label: l.nome }]}
        acoes={
          <div className="flex flex-wrap gap-2">
            <BotaoWhatsapp url={l.whatsapp_url} mensagens={l.mensagens} onEnviada={(m) => podeEditar && registrarZap.mutate(m.titulo)} />
            {l.telefone && (
              <Button variant="outline" render={<a href={`tel:+${l.telefone}`} />}>
                <Phone /> Ligar
              </Button>
            )}
            {podeEditar && (
              <Button variant="outline" onClick={() => setEditar(true)}>
                <Pencil /> Editar
              </Button>
            )}
            {pode("crm.excluir") && (
              <Button variant="ghost" size="icon" aria-label="Excluir lead" onClick={() => setExcluir(true)}>
                <Trash2 />
              </Button>
            )}
          </div>
        }
      />
      <CrmNav />

      <div className="card-surface mb-4 space-y-3 p-4">
        <Etapas lead={l} podeEditar={podeEditar} onPerder={() => setPerder(true)} onGanhar={() => setGanhar(true)} />
        {l.situacao === "PERDIDO" && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-danger/8 px-3 py-2 text-sm">
            <span>
              Perdido {relativo(l.perdido_em)}: <strong>{l.motivo_perda ?? "sem motivo"}</strong>
              {l.motivo_perda_detalhe && ` (${l.motivo_perda_detalhe})`}
            </span>
            {podeEditar && (
              <Button size="sm" variant="outline" onClick={() => reabrir.mutate()} disabled={reabrir.isPending}>
                <RotateCcw /> Reabrir
              </Button>
            )}
          </div>
        )}
        {l.situacao === "GANHO" && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-success/10 px-3 py-2 text-sm">
            <span>
              Matriculado {relativo(l.ganho_em)}
              {l.aluno_nome && (
                <>
                  {" "}
                  como <strong>{l.aluno_nome}</strong>
                </>
              )}
              .
            </span>
            {l.aluno_id ? (
              pode("alunos.ver") && (
                <Button size="sm" variant="outline" render={<Link href={`/alunos/${l.aluno_id}`} />}>
                  <GraduationCap /> Abrir ficha do aluno
                </Button>
              )
            ) : (
              podeEditar && (
                <Button size="sm" onClick={() => setGanhar(true)}>
                  <GraduationCap /> Criar cadastro de aluno
                </Button>
              )
            )}
          </div>
        )}
        {l.sugestao && (
          <div className="flex items-start gap-2 rounded-xl border border-brand/25 bg-brand/6 px-3 py-2 text-sm">
            <Lightbulb className="mt-0.5 size-4 shrink-0 text-brand" />
            <span>
              <strong>Próximo passo:</strong> {l.sugestao}
            </span>
          </div>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {podeEditar && <Registrar lead={l} />}
          <section className="card-surface p-5">
            <h2 className="mb-4 text-sm font-semibold">Histórico</h2>
            <Linha lead={l} podeExcluir={pode("crm.excluir")} />
          </section>
        </div>

        <aside className="space-y-4">
          <section className="card-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <CalendarClock className="size-4 text-brand" /> Aula experimental
              </h2>
              {podeEditar && l.situacao === "ABERTO" && (
                <Button size="sm" variant="ghost" onClick={() => setAula(true)}>
                  <CalendarPlus /> {aulaAgendada ? "Remarcar" : "Agendar"}
                </Button>
              )}
            </div>
            {l.aula_experimental_em ? (
              <div className="space-y-2 text-sm">
                <p>
                  <strong>{quandoCurto(l.aula_experimental_em)}</strong>
                  {l.aula_experimental_profissional && <> com {l.aula_experimental_profissional}</>}
                </p>
                <Pill
                  tom={
                    l.aula_experimental_status === "REALIZADA" ? "success" : l.aula_experimental_status === "FALTOU" ? "danger" : "warning"
                  }
                >
                  {{ AGENDADA: "Agendada", REALIZADA: "Compareceu", FALTOU: "Faltou", CANCELADA: "Cancelada" }[l.aula_experimental_status ?? "AGENDADA"]}
                </Pill>
                {l.aula_experimental_obs && <p className="text-muted-foreground">{l.aula_experimental_obs}</p>}
                {podeEditar && (l.aula_experimental_status === "AGENDADA" || l.aula_experimental_status === "FALTOU") && (
                  <div className="pt-1">
                    <p className="mb-1.5 text-xs text-muted-foreground">{aulaPassou ? "Já passou: como foi?" : "Depois da aula, registre:"}</p>
                    <ResultadoAulaBotoes leadId={l.id} />
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Nenhuma aula marcada. A aula experimental é o passo que mais converte em matrícula.
              </p>
            )}
          </section>

          <section className="card-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <ListTodo className="size-4 text-brand" /> Tarefas
              </h2>
              {podeEditar && (
                <Button size="sm" variant="ghost" onClick={() => setTarefa(true)}>
                  <Plus /> Nova
                </Button>
              )}
            </div>
            <ListaDeTarefas tarefas={l.tarefas} mostrarLead={false} podeEditar={podeEditar} vazio="Nenhuma tarefa para este lead." />
          </section>

          <section className="card-surface space-y-2 p-4 text-sm">
            <h2 className="mb-1 text-sm font-semibold">Dados</h2>
            <Dado rotulo="Etapa" valor={`${l.etapa_nome} · há ${l.dias_na_etapa} dia(s)`} />
            <Dado rotulo="Origem" valor={ROTULO_ORIGEM[l.origem]} />
            <Dado rotulo="Interesse" valor={l.interesse} />
            <Dado rotulo="Responsável" valor={l.responsavel?.nome ?? "Equipe"} />
            <Dado rotulo="Valor estimado" valor={l.valor_estimado && toNum(l.valor_estimado) > 0 ? `${moeda(l.valor_estimado)}/mês` : null} />
            <Dado rotulo="Último contato" valor={l.ultima_interacao_em ? relativo(l.ultima_interacao_em) : "nunca"} />
            {l.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {l.tags.map((t) => (
                  <span key={t} className="rounded-full bg-brand/12 px-2 py-0.5 text-xs">
                    {t}
                  </span>
                ))}
              </div>
            )}
            {l.observacoes && <p className="rounded-lg bg-muted p-2 whitespace-pre-line">{l.observacoes}</p>}
          </section>
        </aside>
      </div>

      {editar && <LeadDialog aberto lead={l} onFechar={() => setEditar(false)} />}
      {aula && <AulaDialog lead={l} onFechar={() => setAula(false)} />}
      {perder && perdido && <PerdaDialog lead={l} etapaPerdidoId={perdido.id} onFechar={() => setPerder(false)} />}
      {ganhar && <ConverterDialog lead={l} onFechar={() => setGanhar(false)} />}
      {tarefa && <TarefaDialog aberto leadId={l.id} onFechar={() => setTarefa(false)} />}
      <ConfirmDialog
        open={excluir}
        onOpenChange={setExcluir}
        titulo={`Excluir ${l.nome}?`}
        descricao="O histórico e as tarefas do lead somem junto. Para tirar do funil sem apagar, marque como perdido."
        confirmar="Excluir"
        destrutivo
        carregando={apagar.isPending}
        onConfirm={() => apagar.mutate()}
      />
    </div>
  );
}

function Dado({ rotulo, valor }: { rotulo: string; valor: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-muted-foreground">{rotulo}</span>
      <span className="text-right font-medium">{valor || "—"}</span>
    </div>
  );
}
