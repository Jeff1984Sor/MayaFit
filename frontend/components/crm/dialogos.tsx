"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import confetti from "canvas-confetti";
import { CalendarPlus, Check, GraduationCap, Link2, Loader2, UserRoundCheck, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { LeadFicha, LeadIn, OrigemLead, PreparoConversao, Tarefa } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

import { deInputLocal, paraInputLocal, useOpcoesCrm } from "./comum";

/** Atualiza tudo que o CRM mostra (funil, listas, ficha, tarefas, resumo). */
export function useInvalidarCrm() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["crm"] });
}

// ------------------------------------------------------------------------------------------------ lead (novo/editar)
export function LeadDialog({
  aberto,
  onFechar,
  lead,
  etapaInicial,
}: {
  aberto: boolean;
  onFechar: () => void;
  lead?: LeadFicha | null;
  etapaInicial?: number;
}) {
  const opcoes = useOpcoesCrm();
  const invalidar = useInvalidarCrm();
  const router = useRouter();
  const { usuario } = useAuth();
  const [form, setForm] = useState<LeadIn>(() =>
    lead
      ? {
          nome: lead.nome,
          telefone: lead.telefone_formatado ?? lead.telefone ?? "",
          email: lead.email ?? "",
          origem: lead.origem,
          indicado_por: lead.indicado_por ?? "",
          interesse: lead.interesse ?? "",
          responsavel_id: lead.responsavel?.id ?? null,
          valor_estimado: lead.valor_estimado ?? "",
          observacoes: lead.observacoes ?? "",
          tags: lead.tags,
        }
      : { nome: "", telefone: "", email: "", origem: "instagram", interesse: "", responsavel_id: usuario?.id ?? null, tags: [], etapa_id: etapaInicial },
  );
  const [tagNova, setTagNova] = useState("");
  const set = <K extends keyof LeadIn>(k: K, v: LeadIn[K]) => setForm((f) => ({ ...f, [k]: v }));

  const salvar = useMutation({
    mutationFn: () => {
      const corpo = { ...form, valor_estimado: form.valor_estimado ? String(form.valor_estimado).replace(",", ".") : null };
      return lead ? api.put<LeadFicha>(`/crm/leads/${lead.id}`, corpo) : api.post<LeadFicha>("/crm/leads", corpo);
    },
    onSuccess: (r) => {
      toast.success(lead ? "Lead atualizado." : `${r.nome} entrou no funil.`, {
        action: lead ? undefined : { label: "Abrir ficha", onClick: () => router.push(`/crm/leads/${r.id}`) },
      });
      invalidar();
      onFechar();
    },
  });

  function addTag(t: string) {
    const limpa = t.trim();
    if (limpa && !(form.tags ?? []).some((x) => x.toLowerCase() === limpa.toLowerCase())) set("tags", [...(form.tags ?? []), limpa]);
    setTagNova("");
  }

  const sugestoesTag = (opcoes.data?.tags ?? []).filter((t) => !(form.tags ?? []).includes(t)).slice(0, 6);

  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onFechar()}
      titulo={lead ? `Editar ${lead.nome}` : "Novo lead"}
      descricao={lead ? undefined : "Basta nome e um contato. O resto você completa depois."}
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
      salvando={salvar.isPending}
      rotuloSalvar={lead ? "Salvar" : "Adicionar ao funil"}
      largura="lg"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome" obrigatorio className="sm:col-span-2">
          <Input autoFocus value={form.nome ?? ""} onChange={(e) => set("nome", e.target.value)} maxLength={150} required minLength={2} />
        </Field>
        <Field label="Telefone / WhatsApp" dica="Com DDD. Abre o WhatsApp com um clique.">
          <Input value={form.telefone ?? ""} onChange={(e) => set("telefone", e.target.value)} inputMode="tel" placeholder="(11) 99999-0000" />
        </Field>
        <Field label="E-mail">
          <Input type="email" value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label="Origem">
          <NativeSelect value={form.origem ?? "outros"} onChange={(e) => set("origem", e.target.value as OrigemLead)}>
            {(opcoes.data?.origens ?? []).map((o) => (
              <option key={o.valor} value={o.valor}>
                {o.rotulo}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {form.origem === "indicacao" ? (
          <Field label="Indicado por" dica="Agradeça quem indicou: indicação é o canal que mais converte.">
            <Input value={form.indicado_por ?? ""} onChange={(e) => set("indicado_por", e.target.value)} placeholder="Nome de quem indicou" />
          </Field>
        ) : (
          <Field label="Interesse / modalidade">
            <Input value={form.interesse ?? ""} onChange={(e) => set("interesse", e.target.value)} placeholder="Pilates, funcional..." list="crm-interesses" />
          </Field>
        )}
        {form.origem === "indicacao" && (
          <Field label="Interesse / modalidade">
            <Input value={form.interesse ?? ""} onChange={(e) => set("interesse", e.target.value)} placeholder="Pilates, funcional..." list="crm-interesses" />
          </Field>
        )}
        <datalist id="crm-interesses">
          {["Pilates", "Pilates solo", "Funcional", "Musculação", "Yoga", "Fisioterapia"].map((x) => (
            <option key={x} value={x} />
          ))}
        </datalist>
        <Field label="Responsável">
          <NativeSelect value={form.responsavel_id ?? ""} onChange={(e) => set("responsavel_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">Equipe (sem responsável)</option>
            {(opcoes.data?.usuarios ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Valor estimado (mensal)" dica="Ajuda a ver quanto está em negociação.">
          <Input inputMode="decimal" value={form.valor_estimado ?? ""} onChange={(e) => set("valor_estimado", e.target.value)} placeholder="R$ 0,00" />
        </Field>
        {!lead && (
          <Field label="Etapa">
            <NativeSelect value={form.etapa_id ?? ""} onChange={(e) => set("etapa_id", e.target.value ? Number(e.target.value) : null)}>
              {(opcoes.data?.etapas ?? [])
                .filter((e) => e.tipo === "ABERTA")
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.nome}
                  </option>
                ))}
            </NativeSelect>
          </Field>
        )}
        <Field label="Tags" className="sm:col-span-2">
          <div className="flex flex-wrap items-center gap-1.5 rounded-lg border px-2 py-1.5">
            {(form.tags ?? []).map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full bg-brand/12 px-2 py-0.5 text-xs">
                {t}
                <button type="button" aria-label={`Remover ${t}`} onClick={() => set("tags", (form.tags ?? []).filter((x) => x !== t))}>
                  <X className="size-3" />
                </button>
              </span>
            ))}
            <input
              value={tagNova}
              onChange={(e) => setTagNova(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addTag(tagNova);
                }
              }}
              onBlur={() => tagNova && addTag(tagNova)}
              placeholder="Digite e Enter"
              className="min-w-24 flex-1 bg-transparent text-sm outline-none"
              maxLength={30}
            />
          </div>
          {sugestoesTag.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {sugestoesTag.map((t) => (
                <button key={t} type="button" onClick={() => addTag(t)} className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted">
                  + {t}
                </button>
              ))}
            </div>
          )}
        </Field>
        <Field label="Observações" className="sm:col-span-2">
          <Textarea value={form.observacoes ?? ""} onChange={(e) => set("observacoes", e.target.value)} rows={3} maxLength={4000} />
        </Field>
      </div>
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------ perda
export function PerdaDialog({
  lead,
  etapaPerdidoId,
  onFechar,
  onConfirmar,
}: {
  lead: { id: number; nome: string } | null;
  etapaPerdidoId: number;
  onFechar: () => void;
  onConfirmar?: () => void;
}) {
  const opcoes = useOpcoesCrm();
  const invalidar = useInvalidarCrm();
  const [motivo, setMotivo] = useState<number | null>(null);
  const [detalhe, setDetalhe] = useState("");
  const perder = useMutation({
    mutationFn: () => api.post(`/crm/leads/${lead!.id}/mover`, { etapa_id: etapaPerdidoId, motivo_perda_id: motivo, motivo_perda_detalhe: detalhe || null }),
    onSuccess: () => {
      toast.success(`${lead!.nome} marcado como perdido.`, { description: "Dá para reabrir na ficha se a situação mudar." });
      invalidar();
      onConfirmar?.();
      onFechar();
    },
  });
  const ativos = (opcoes.data?.motivos ?? []).filter((m) => m.ativo);
  return (
    <FormDialog
      open={!!lead}
      onOpenChange={(o) => !o && onFechar()}
      titulo={`Por que perdemos ${lead?.nome ?? ""}?`}
      descricao="O motivo alimenta o relatório de perdas: é assim que se descobre o que ajustar."
      onSubmit={(e) => {
        e.preventDefault();
        if (motivo) perder.mutate();
      }}
      salvando={perder.isPending}
      rotuloSalvar="Marcar como perdido"
    >
      <div className="grid gap-2 sm:grid-cols-2">
        {ativos.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMotivo(m.id)}
            className={cn(
              "rounded-lg border px-3 py-2 text-left text-sm transition-colors hover:bg-muted",
              motivo === m.id && "border-danger bg-danger/8 ring-1 ring-danger",
            )}
          >
            {m.nome}
          </button>
        ))}
      </div>
      <Field label="Detalhe (opcional)" className="mt-4">
        <Input value={detalhe} onChange={(e) => setDetalhe(e.target.value)} maxLength={300} placeholder="Ex.: achou caro o plano de 3x por semana" />
      </Field>
      {!motivo && <p className="mt-2 text-xs text-muted-foreground">Escolha um motivo para continuar.</p>}
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------ aula experimental
export function AulaDialog({ lead, onFechar }: { lead: LeadFicha | null; onFechar: () => void }) {
  const opcoes = useOpcoesCrm();
  const invalidar = useInvalidarCrm();
  const padrao = () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
    return paraInputLocal(lead?.aula_experimental_em && lead.aula_experimental_status === "AGENDADA" ? lead.aula_experimental_em : d);
  };
  const [quando, setQuando] = useState(padrao);
  const [prof, setProf] = useState<number | "">(lead?.aula_experimental_profissional_id ?? "");
  const [unidade, setUnidade] = useState<number | "">(lead?.aula_experimental_unidade_id ?? "");
  const [obs, setObs] = useState(lead?.aula_experimental_obs ?? "");
  const [lembrete, setLembrete] = useState(true);
  const agendar = useMutation({
    mutationFn: () =>
      api.post<LeadFicha>(`/crm/leads/${lead!.id}/aula-experimental`, {
        data_hora: deInputLocal(quando),
        profissional_id: prof || null,
        unidade_id: unidade || null,
        observacao: obs || null,
        criar_lembrete: lembrete,
      }),
    onSuccess: () => {
      toast.success("Aula experimental agendada.", { description: lembrete ? "Criamos o lembrete para confirmar na véspera." : undefined });
      invalidar();
      onFechar();
    },
  });
  const atalhos = [
    { rotulo: "Amanhã 7h", dias: 1, h: 7 },
    { rotulo: "Amanhã 18h", dias: 1, h: 18 },
    { rotulo: "Depois de amanhã 9h", dias: 2, h: 9 },
  ];
  return (
    <FormDialog
      open={!!lead}
      onOpenChange={(o) => !o && onFechar()}
      titulo={`Aula experimental de ${lead?.nome ?? ""}`}
      descricao="O lead avança para “Aula experimental agendada” e você recebe a tarefa de confirmar na véspera."
      onSubmit={(e) => {
        e.preventDefault();
        agendar.mutate();
      }}
      salvando={agendar.isPending}
      rotuloSalvar="Agendar"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Data e hora" obrigatorio className="sm:col-span-2">
          <Input type="datetime-local" value={quando} onChange={(e) => setQuando(e.target.value)} required />
          <div className="mt-1.5 flex flex-wrap gap-1">
            {atalhos.map((a) => (
              <button
                key={a.rotulo}
                type="button"
                className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted"
                onClick={() => {
                  const d = new Date();
                  d.setDate(d.getDate() + a.dias);
                  d.setHours(a.h, 0, 0, 0);
                  setQuando(paraInputLocal(d));
                }}
              >
                {a.rotulo}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Professor(a)">
          <NativeSelect value={prof} onChange={(e) => setProf(e.target.value ? Number(e.target.value) : "")}>
            <option value="">A definir</option>
            {(opcoes.data?.profissionais ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Unidade">
          <NativeSelect value={unidade} onChange={(e) => setUnidade(e.target.value ? Number(e.target.value) : "")}>
            <option value="">A definir</option>
            {(opcoes.data?.unidades ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Observação" className="sm:col-span-2">
          <Input value={obs} onChange={(e) => setObs(e.target.value)} maxLength={300} placeholder="Ex.: tem dor lombar, prefere aparelho" />
        </Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" checked={lembrete} onChange={(e) => setLembrete(e.target.checked)} />
          Criar lembrete para confirmar a presença na véspera
        </label>
      </div>
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------ converter em aluno
export function ConverterDialog({ lead, onFechar }: { lead: { id: number; nome: string } | null; onFechar: () => void }) {
  const invalidar = useInvalidarCrm();
  const router = useRouter();
  const prep = useQuery({
    queryKey: ["crm", "conversao", lead?.id],
    queryFn: () => api.get<PreparoConversao>(`/crm/leads/${lead!.id}/conversao`),
    enabled: !!lead,
  });
  const [unidade, setUnidade] = useState<number | "">("");
  const [cpf, setCpf] = useState("");
  const [nascimento, setNascimento] = useState("");
  const [vincular, setVincular] = useState<number | null>(null);
  const unidadeEfetiva = unidade || prep.data?.unidades[0]?.id || "";

  const converter = useMutation({
    mutationFn: () =>
      api.post<{ aluno_id: number; aluno_nome: string; criado: boolean }>(
        `/crm/leads/${lead!.id}/converter`,
        vincular ? { aluno_id: vincular } : { unidade_id: unidadeEfetiva || null, cpf: cpf || null, data_nascimento: nascimento || null },
      ),
    onSuccess: (r) => {
      void confetti({ particleCount: 120, spread: 75, origin: { y: 0.6 }, colors: ["#7C8FFF", "#1A8F5E", "#F5A623"] });
      toast.success(r.criado ? `${r.aluno_nome} agora é aluno(a)!` : `Lead vinculado a ${r.aluno_nome}.`, {
        action: { label: "Abrir ficha do aluno", onClick: () => router.push(`/alunos/${r.aluno_id}`) },
      });
      invalidar();
      onFechar();
    },
  });

  const d = prep.data;
  return (
    <FormDialog
      open={!!lead}
      onOpenChange={(o) => !o && onFechar()}
      titulo={`Matricular ${lead?.nome ?? ""}`}
      descricao="Cria o cadastro do aluno com nome, telefone e e-mail do lead e marca o lead como Matriculado."
      onSubmit={(e) => {
        e.preventDefault();
        converter.mutate();
      }}
      salvando={converter.isPending}
      rotuloSalvar={vincular ? "Vincular e marcar como matriculado" : "Criar aluno"}
    >
      {prep.isPending ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Conferindo se já existe um aluno parecido...
        </p>
      ) : (
        <div className="space-y-4">
          {d && d.parecidos.length > 0 && (
            <div className="rounded-xl border border-warning/40 bg-warning/8 p-3">
              <p className="mb-2 text-sm font-medium">Encontramos aluno(s) parecido(s). Evite cadastro duplicado:</p>
              <div className="space-y-1.5">
                {d.parecidos.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setVincular(vincular === p.id ? null : p.id)}
                    className={cn(
                      "flex w-full items-center justify-between rounded-lg border bg-card px-3 py-2 text-left text-sm hover:bg-muted",
                      vincular === p.id && "border-brand ring-1 ring-brand",
                    )}
                  >
                    <span>
                      <strong>{p.nome}</strong> <span className="text-muted-foreground">· {p.motivo}</span>
                    </span>
                    {vincular === p.id ? <Check className="size-4 text-brand" /> : <Link2 className="size-4 text-muted-foreground" />}
                  </button>
                ))}
              </div>
            </div>
          )}
          {!vincular &&
            (d?.pode_criar_aluno ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Unidade" obrigatorio className="sm:col-span-2">
                  <NativeSelect value={unidadeEfetiva} onChange={(e) => setUnidade(e.target.value ? Number(e.target.value) : "")}>
                    {(d?.unidades ?? []).map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.nome}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="CPF" dica="Opcional agora; completa depois na ficha do aluno.">
                  <Input value={cpf} onChange={(e) => setCpf(e.target.value)} inputMode="numeric" placeholder="000.000.000-00" />
                </Field>
                <Field label="Nascimento">
                  <Input type="date" value={nascimento} onChange={(e) => setNascimento(e.target.value)} />
                </Field>
              </div>
            ) : (
              <p className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">
                Seu perfil não cadastra alunos. Vincule a um aluno existente acima ou peça a quem tem acesso a Alunos.
              </p>
            ))}
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <GraduationCap className="size-4" /> Depois é só criar o contrato na ficha do aluno.
          </p>
        </div>
      )}
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------ tarefa
export function TarefaDialog({
  aberto,
  onFechar,
  leadId,
  tarefa,
}: {
  aberto: boolean;
  onFechar: () => void;
  leadId?: number | null;
  tarefa?: Tarefa | null;
}) {
  const opcoes = useOpcoesCrm();
  const invalidar = useInvalidarCrm();
  const { usuario } = useAuth();
  const inicial = () => {
    const d = new Date(Date.now() + 60 * 60 * 1000);
    d.setMinutes(0, 0, 0);
    return paraInputLocal(tarefa?.vence_em ?? d);
  };
  const [titulo, setTitulo] = useState(tarefa?.titulo ?? "");
  const [descricao, setDescricao] = useState(tarefa?.descricao ?? "");
  const [vence, setVence] = useState(inicial);
  const [resp, setResp] = useState<number | "">(tarefa ? (tarefa.responsavel?.id ?? "") : (usuario?.id ?? ""));
  const salvar = useMutation({
    mutationFn: () => {
      const corpo = { titulo, descricao: descricao || null, vence_em: deInputLocal(vence), responsavel_id: resp || null, lead_id: tarefa?.lead_id ?? leadId ?? null };
      return tarefa ? api.put(`/crm/tarefas/${tarefa.id}`, corpo) : api.post("/crm/tarefas", corpo);
    },
    onSuccess: () => {
      toast.success(tarefa ? "Tarefa atualizada." : "Tarefa criada.");
      invalidar();
      onFechar();
    },
  });
  const rapidos = ["Ligar", "Mandar WhatsApp", "Enviar proposta", "Confirmar aula experimental", "Follow-up"];
  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onFechar()}
      titulo={tarefa ? "Editar tarefa" : "Nova tarefa"}
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
      salvando={salvar.isPending}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="O que fazer" obrigatorio className="sm:col-span-2">
          <Input autoFocus value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={150} required minLength={2} />
          {!tarefa && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {rapidos.map((r) => (
                <button key={r} type="button" onClick={() => setTitulo(r)} className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted">
                  {r}
                </button>
              ))}
            </div>
          )}
        </Field>
        <Field label="Quando" obrigatorio>
          <Input type="datetime-local" value={vence} onChange={(e) => setVence(e.target.value)} required />
        </Field>
        <Field label="Responsável">
          <NativeSelect value={resp} onChange={(e) => setResp(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Equipe (todos veem)</option>
            {(opcoes.data?.usuarios ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Detalhes" className="sm:col-span-2">
          <Textarea value={descricao} onChange={(e) => setDescricao(e.target.value)} rows={2} maxLength={2000} />
        </Field>
      </div>
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------ resultado da aula
export function ResultadoAulaBotoes({ leadId }: { leadId: number }) {
  const invalidar = useInvalidarCrm();
  const enviar = useMutation({
    mutationFn: (compareceu: boolean) => api.post(`/crm/leads/${leadId}/aula-experimental/resultado`, { compareceu }),
    onSuccess: (_r, compareceu) => {
      toast.success(compareceu ? "Ótimo! Criamos a tarefa de enviar a proposta." : "Anotado. Criamos a tarefa de remarcar.");
      invalidar();
    },
  });
  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" onClick={() => enviar.mutate(true)} disabled={enviar.isPending}>
        <UserRoundCheck /> Compareceu
      </Button>
      <Button size="sm" variant="outline" onClick={() => enviar.mutate(false)} disabled={enviar.isPending}>
        <CalendarPlus /> Faltou
      </Button>
    </div>
  );
}
