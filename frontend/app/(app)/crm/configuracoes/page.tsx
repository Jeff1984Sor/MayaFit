"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Lock, Pencil, Plus, Settings2, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CrmNav } from "@/components/crm/comum";
import { useInvalidarCrm } from "@/components/crm/dialogos";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Etapa, MarcoEtapa, Motivo } from "@/lib/tipos-crm";

const MARCOS: { valor: MarcoEtapa | ""; rotulo: string }[] = [
  { valor: "", rotulo: "Nenhum" },
  { valor: "AULA_AGENDADA", rotulo: "Aula experimental agendada" },
  { valor: "AULA_REALIZADA", rotulo: "Fez a aula experimental" },
  { valor: "PROPOSTA", rotulo: "Proposta enviada" },
];
const CORES = ["#7C8FFF", "#1E2D6B", "#F5A623", "#8B5CF6", "#0EA5E9", "#EC4899", "#1A8F5E", "#C94343"];

function EtapaDialog({ etapa, onFechar }: { etapa: Etapa | "nova"; onFechar: () => void }) {
  const invalidar = useInvalidarCrm();
  const e = etapa === "nova" ? null : etapa;
  const [nome, setNome] = useState(e?.nome ?? "");
  const [cor, setCor] = useState(e?.cor ?? CORES[0]);
  const [marco, setMarco] = useState<MarcoEtapa | "">(e?.marco ?? "");
  const [dias, setDias] = useState(e?.dias_alerta ?? 3);
  const salvar = useMutation({
    mutationFn: () => {
      const corpo = { nome, cor, marco: marco || null, dias_alerta: dias };
      return e ? api.put(`/crm/etapas/${e.id}`, corpo) : api.post("/crm/etapas", corpo);
    },
    onSuccess: () => {
      toast.success(e ? "Etapa atualizada." : "Etapa criada.");
      invalidar();
      onFechar();
    },
  });
  const aberta = !e || e.tipo === "ABERTA";
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onFechar()}
      titulo={e ? `Editar “${e.nome}”` : "Nova etapa"}
      onSubmit={(ev) => {
        ev.preventDefault();
        salvar.mutate();
      }}
      salvando={salvar.isPending}
    >
      <div className="grid gap-4">
        <Field label="Nome" obrigatorio>
          <Input autoFocus value={nome} onChange={(ev) => setNome(ev.target.value)} maxLength={60} required minLength={2} />
        </Field>
        <Field label="Cor">
          <div className="flex flex-wrap gap-2">
            {CORES.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setCor(c)}
                aria-label={`Cor ${c}`}
                className="size-8 rounded-full ring-offset-2 ring-offset-background transition"
                style={{ background: c, boxShadow: cor === c ? `0 0 0 2px var(--background), 0 0 0 4px ${c}` : undefined }}
              />
            ))}
          </div>
        </Field>
        {aberta && (
          <>
            <Field label="Marco automático" dica="O sistema move o lead para esta etapa sozinho quando o fato acontece.">
              <NativeSelect value={marco} onChange={(ev) => setMarco(ev.target.value as MarcoEtapa | "")}>
                {MARCOS.map((m) => (
                  <option key={m.valor} value={m.valor}>
                    {m.rotulo}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Alerta de lead parado (dias)" dica="Depois de quantos dias sem avançar o cartão fica em vermelho. 0 = nunca.">
              <Input type="number" min={0} max={90} value={dias} onChange={(ev) => setDias(Number(ev.target.value))} />
            </Field>
          </>
        )}
      </div>
    </FormDialog>
  );
}

function ExcluirEtapa({ etapa, abertas, onFechar }: { etapa: Etapa; abertas: Etapa[]; onFechar: () => void }) {
  const invalidar = useInvalidarCrm();
  const outras = abertas.filter((a) => a.id !== etapa.id);
  const [destino, setDestino] = useState<number>(outras[0]?.id ?? 0);
  const excluir = useMutation({
    mutationFn: () => api(`/crm/etapas/${etapa.id}`, { method: "DELETE", query: { mover_para_id: etapa.leads ? destino : undefined } }),
    onSuccess: () => {
      toast.success("Etapa excluída.");
      invalidar();
      onFechar();
    },
  });
  return (
    <ConfirmDialog
      open
      onOpenChange={(o) => !o && onFechar()}
      titulo={`Excluir a etapa “${etapa.nome}”?`}
      descricao={etapa.leads ? `Ela tem ${etapa.leads} lead(s). Escolha para onde eles vão:` : "Nenhum lead está nesta etapa."}
      confirmar="Excluir"
      destrutivo
      carregando={excluir.isPending}
      onConfirm={() => excluir.mutate()}
    >
      {etapa.leads > 0 && (
        <NativeSelect value={destino} onChange={(e) => setDestino(Number(e.target.value))}>
          {outras.map((o) => (
            <option key={o.id} value={o.id}>
              {o.nome}
            </option>
          ))}
        </NativeSelect>
      )}
    </ConfirmDialog>
  );
}

function Motivos({ motivos }: { motivos: Motivo[] }) {
  const invalidar = useInvalidarCrm();
  const podeExcluir = useAuth().pode("crm.excluir");
  const [novo, setNovo] = useState("");
  const [editando, setEditando] = useState<{ id: number; nome: string } | null>(null);
  const criar = useMutation({
    mutationFn: () => api.post("/crm/motivos", { nome: novo.trim() }),
    onSuccess: () => {
      setNovo("");
      toast.success("Motivo criado.");
      invalidar();
    },
  });
  const salvar = useMutation({
    mutationFn: (m: { id: number; nome: string; ativo: boolean }) => api.put(`/crm/motivos/${m.id}`, { nome: m.nome, ativo: m.ativo }),
    onSuccess: () => {
      setEditando(null);
      invalidar();
    },
  });
  const excluir = useMutation({
    mutationFn: (id: number) => api.del<{ mensagem: string }>(`/crm/motivos/${id}`),
    onSuccess: (r) => {
      toast.success(r.mensagem);
      invalidar();
    },
  });
  return (
    <section className="card-surface p-5">
      <h2 className="text-sm font-semibold">Motivos de perda</h2>
      <p className="mb-4 text-xs text-muted-foreground">Aparecem ao marcar um lead como perdido e alimentam o relatório. Motivo em uso é desativado, não apagado.</p>
      <form
        className="mb-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (novo.trim().length >= 2) criar.mutate();
        }}
      >
        <Input value={novo} onChange={(e) => setNovo(e.target.value)} placeholder="Novo motivo" maxLength={80} />
        <Button type="submit" disabled={novo.trim().length < 2 || criar.isPending}>
          <Plus /> Adicionar
        </Button>
      </form>
      <ul className="divide-y rounded-xl border">
        {motivos.map((m) => (
          <li key={m.id} className="flex items-center gap-3 px-3 py-2">
            {editando?.id === m.id ? (
              <form
                className="flex flex-1 gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  salvar.mutate({ id: m.id, nome: editando.nome, ativo: m.ativo });
                }}
              >
                <Input autoFocus value={editando.nome} onChange={(e) => setEditando({ id: m.id, nome: e.target.value })} maxLength={80} />
                <Button type="submit" size="sm">
                  Salvar
                </Button>
              </form>
            ) : (
              <span className={m.ativo ? "flex-1 text-sm" : "flex-1 text-sm text-muted-foreground line-through"}>
                {m.nome}
                {m.usos > 0 && <span className="ml-2 text-xs text-muted-foreground no-underline">{m.usos} uso(s)</span>}
              </span>
            )}
            <Switch checked={m.ativo} onCheckedChange={(v) => salvar.mutate({ id: m.id, nome: m.nome, ativo: v })} aria-label="Ativo" />
            <Button size="icon-sm" variant="ghost" aria-label="Renomear" onClick={() => setEditando({ id: m.id, nome: m.nome })}>
              <Pencil />
            </Button>
            {podeExcluir && (
              <Button size="icon-sm" variant="ghost" aria-label="Excluir" onClick={() => excluir.mutate(m.id)}>
                <Trash2 />
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ConfiguracoesCrmPage() {
  const { pode } = useAuth();
  const invalidar = useInvalidarCrm();
  const [editar, setEditar] = useState<Etapa | "nova" | null>(null);
  const [excluir, setExcluir] = useState<Etapa | null>(null);
  const etapas = useQuery({ queryKey: ["crm", "etapas"], queryFn: () => api.get<Etapa[]>("/crm/etapas"), enabled: pode("crm.editar") });
  const motivos = useQuery({ queryKey: ["crm", "motivos"], queryFn: () => api.get<Motivo[]>("/crm/motivos"), enabled: pode("crm.editar") });
  const ordenar = useMutation({
    mutationFn: (ids: number[]) => api.put("/crm/etapas/ordem", { ids }),
    onSuccess: () => invalidar(),
  });
  if (!pode("crm.editar")) return <SemAcesso titulo="Configurações do CRM" />;
  const lista = etapas.data ?? [];
  const abertas = lista.filter((e) => e.tipo === "ABERTA");

  function mover(i: number, delta: number) {
    const ids = abertas.map((e) => e.id);
    const j = i + delta;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    ordenar.mutate(ids);
  }

  return (
    <div>
      <PageHeader icone={Settings2} titulo="Configurações do funil" descricao="Etapas, cores, automações e motivos de perda. Vale para toda a equipe." />
      <CrmNav />
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card-surface p-5">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Etapas do funil</h2>
            <Button size="sm" onClick={() => setEditar("nova")}>
              <Plus /> Nova etapa
            </Button>
          </div>
          <p className="mb-4 text-xs text-muted-foreground">
            Use as setas para reordenar. “Matriculado” e “Perdido” ficam sempre no fim (dá para renomear).
          </p>
          {etapas.isPending ? (
            <Skeleton className="h-64 rounded-xl" />
          ) : (
            <ul className="space-y-2">
              {lista.map((e) => {
                const i = abertas.findIndex((a) => a.id === e.id);
                return (
                  <li key={e.id} className="flex items-center gap-3 rounded-xl border bg-card px-3 py-2.5">
                    <span className="size-3 shrink-0 rounded-full" style={{ background: e.cor }} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{e.nome}</p>
                      <p className="text-xs text-muted-foreground">
                        {e.leads} lead(s)
                        {e.marco && ` · automático: ${MARCOS.find((m) => m.valor === e.marco)?.rotulo.toLowerCase()}`}
                        {e.tipo === "ABERTA" && e.dias_alerta > 0 && ` · alerta em ${e.dias_alerta}d`}
                      </p>
                    </div>
                    {e.tipo === "ABERTA" ? (
                      <>
                        <Button size="icon-sm" variant="ghost" aria-label="Subir" disabled={i === 0 || ordenar.isPending} onClick={() => mover(i, -1)}>
                          <ArrowUp />
                        </Button>
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label="Descer"
                          disabled={i === abertas.length - 1 || ordenar.isPending}
                          onClick={() => mover(i, 1)}
                        >
                          <ArrowDown />
                        </Button>
                      </>
                    ) : (
                      <Pill tom={e.tipo === "GANHO" ? "success" : "danger"}>
                        <Lock className="mr-1 inline size-3" />
                        {e.tipo === "GANHO" ? "Ganho" : "Perda"}
                      </Pill>
                    )}
                    <Button size="icon-sm" variant="ghost" aria-label="Editar" onClick={() => setEditar(e)}>
                      <Pencil />
                    </Button>
                    {e.tipo === "ABERTA" && pode("crm.excluir") && (
                      <Button size="icon-sm" variant="ghost" aria-label="Excluir" disabled={abertas.length <= 1} onClick={() => setExcluir(e)}>
                        <Trash2 />
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        {motivos.data ? <Motivos motivos={motivos.data} /> : <Skeleton className="h-64 rounded-2xl" />}
      </div>
      {editar && <EtapaDialog etapa={editar} onFechar={() => setEditar(null)} />}
      {excluir && <ExcluirEtapa etapa={excluir} abertas={abertas} onFechar={() => setExcluir(null)} />}
    </div>
  );
}
