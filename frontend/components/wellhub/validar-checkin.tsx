"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { BadgeCheck, Loader2, ScanLine, Search, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { AlunoWellhub, ValidacaoOut } from "@/lib/tipos-wellhub";
import { cn } from "@/lib/utils";

/** Recepção: acha o aluno Wellhub (nome ou Gympass ID) e valida a entrada de hoje no Wellhub (Access Control). */
export function ValidarCheckin({ podeValidar }: { podeValidar: boolean }) {
  const [busca, setBusca] = useState("");
  const [termo, setTermo] = useState("");
  const [resultado, setResultado] = useState<(ValidacaoOut & { nome: string }) | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setTermo(busca.trim()), 300);
    return () => clearTimeout(t);
  }, [busca]);
  const alunos = useQuery({
    queryKey: ["wellhub-alunos", termo],
    queryFn: () => api.get<AlunoWellhub[]>("/wellhub/alunos", { q: termo }),
    enabled: termo.length >= 2,
  });
  const validar = useMutation({
    mutationFn: (a: AlunoWellhub) => api.post<ValidacaoOut>("/wellhub/validar-checkin", { aluno_id: a.aluno_id }).then((r) => ({ ...r, nome: a.nome })),
    onSuccess: (r) => setResultado(r),
  });

  return (
    <section className="card-surface space-y-3 p-5">
      <div>
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <ScanLine className="size-4 text-info-ink" /> Validar check-in na recepção
        </h3>
        <p className="text-xs text-muted-foreground">O aluno faz o check-in no app do Wellhub; aqui você confirma a entrada. Só check-in validado entra no repasse.</p>
      </div>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={busca}
          onChange={(e) => {
            setBusca(e.target.value);
            setResultado(null);
          }}
          placeholder="Nome do aluno ou Gympass ID"
          className="pl-9"
          aria-label="Buscar aluno do Wellhub"
          disabled={!podeValidar}
        />
      </div>
      {termo.length >= 2 && (
        <ul className="divide-y rounded-xl border">
          {alunos.isPending ? (
            <li className="px-3 py-2.5 text-sm text-muted-foreground">Buscando…</li>
          ) : (alunos.data ?? []).length === 0 ? (
            <li className="px-3 py-2.5 text-sm text-muted-foreground">Nenhum aluno do Wellhub com esse nome ou ID.</li>
          ) : (
            alunos.data!.map((a) => (
              <li key={a.aluno_id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{a.nome}</p>
                  <p className="font-mono text-xs text-muted-foreground">{a.gympass_id}</p>
                </div>
                <Button size="sm" variant="outline" disabled={!podeValidar || validar.isPending} onClick={() => validar.mutate(a)}>
                  {validar.isPending && validar.variables?.aluno_id === a.aluno_id ? <Loader2 className="animate-spin" /> : <BadgeCheck />}
                  Validar
                </Button>
              </li>
            ))
          )}
        </ul>
      )}
      {resultado && (
        <div
          role="status"
          className={cn(
            "flex items-start gap-2 rounded-xl border px-3 py-2.5 text-sm",
            resultado.ok ? "border-success/30 bg-success/10 text-success-ink" : "border-danger/30 bg-danger/8 text-danger-ink",
          )}
        >
          {resultado.ok ? <BadgeCheck className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
          <p>
            <span className="font-semibold">{resultado.nome}:</span> {resultado.mensagem}
          </p>
        </div>
      )}
    </section>
  );
}
