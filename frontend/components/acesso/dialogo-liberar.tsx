"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DoorOpen } from "lucide-react";
import { useState } from "react";

import { acionarNesteNavegador } from "@/components/acesso/comum";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { Catraca, Checkin, ListaAlunosAcesso } from "@/lib/tipos-acesso";

const MOTIVOS = ["Aluno esqueceu o celular", "Reconhecimento facial falhou", "Visitante / aula experimental", "Manutenção / entrega", "Saída de emergência"];

/** Liberação manual (motivo obrigatório, auditada). Sem catraca escolhida, só registra a entrada do aluno. */
export function DialogoLiberar({ open, onOpenChange, catracaInicial }: { open: boolean; onOpenChange: (o: boolean) => void; catracaInicial?: number | null }) {
  const qc = useQueryClient();
  const [catraca, setCatraca] = useState<string>(catracaInicial ? String(catracaInicial) : "");
  const [sentido, setSentido] = useState<"entrada" | "saida">("entrada");
  const [motivo, setMotivo] = useState("");
  const [busca, setBusca] = useState("");
  const [aluno, setAluno] = useState<{ id: number; nome: string } | null>(null);

  const catracas = useQuery({ queryKey: ["acesso", "catracas"], queryFn: () => api.get<Catraca[]>("/acesso/catracas"), enabled: open });
  const alunos = useQuery({
    queryKey: ["acesso", "alunos-busca", busca],
    queryFn: () => api.get<ListaAlunosAcesso>("/acesso/alunos", { q: busca, por_pagina: 6 }),
    enabled: open && busca.trim().length >= 2 && !aluno,
  });

  const liberar = useMutation({
    mutationFn: () =>
      api.post<Checkin>(catraca ? `/acesso/catracas/${catraca}/liberar` : "/acesso/liberar", { motivo, sentido, aluno_id: aluno?.id ?? null }),
    onSuccess: async (r) => {
      onOpenChange(false);
      setMotivo("");
      setAluno(null);
      setBusca("");
      if (r.acionamento) await acionarNesteNavegador(r.acionamento, r.registro_id ? `/acesso/registros/${r.registro_id}/catraca` : null);
      qc.invalidateQueries({ queryKey: ["acesso"] });
    },
  });

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      titulo="Liberar agora"
      descricao="Liberação manual: fica registrada no histórico e na auditoria com o seu nome e o motivo."
      rotuloSalvar="Liberar"
      salvando={liberar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        liberar.mutate();
      }}
    >
      <div className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Catraca">
            <NativeSelect value={catraca} onChange={(e) => setCatraca(e.target.value)}>
              <option value="">Sem catraca (só registrar)</option>
              {catracas.data?.filter((c) => c.ativo).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Sentido">
            <NativeSelect value={sentido} onChange={(e) => setSentido(e.target.value as "entrada" | "saida")}>
              <option value="entrada">Entrada</option>
              <option value="saida">Saída</option>
            </NativeSelect>
          </Field>
        </div>
        <Field label="Aluno (opcional)" dica={aluno ? "Clique no nome para trocar." : "Digite ao menos 2 letras, CPF ou código."}>
          {aluno ? (
            <button type="button" onClick={() => setAluno(null)} className="flex h-9 items-center gap-2 rounded-lg border bg-brand/5 px-3 text-left text-sm">
              <DoorOpen className="size-4 text-brand" /> {aluno.nome}
            </button>
          ) : (
            <div className="relative">
              <Input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nome, CPF ou código" />
              {!!alunos.data?.itens.length && (
                <div className="absolute inset-x-0 top-10 z-10 overflow-hidden rounded-lg border bg-popover shadow-lg">
                  {alunos.data.itens.map((a) => (
                    <button key={a.id} type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-accent" onClick={() => setAluno({ id: a.id, nome: a.nome })}>
                      {a.nome} {a.codigo ? <span className="text-xs text-muted-foreground">· {a.codigo}</span> : null}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </Field>
        <Field label="Motivo" obrigatorio>
          <Textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={2} required minLength={3} maxLength={300} placeholder="Por que está liberando?" />
        </Field>
        <div className="flex flex-wrap gap-1.5">
          {MOTIVOS.map((m) => (
            <button key={m} type="button" onClick={() => setMotivo(m)} className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground hover:border-brand hover:text-foreground">
              {m}
            </button>
          ))}
        </div>
      </div>
    </FormDialog>
  );
}
