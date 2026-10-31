"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Wand2 } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/mayacorp/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CabecalhoWellhub, SeletorUnidade, useTelaWellhub, useUnidadeWellhub } from "@/components/wellhub/comum";
import { PassoCredenciais, PassoGrade, PassoMapeamento, PassoRepasse, PassoWebhook } from "@/components/wellhub/passos";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Painel, Passo } from "@/lib/tipos-wellhub";
import { cn } from "@/lib/utils";

const DESCRICAO: Record<Passo["id"], string> = {
  credenciais: "Ambiente, gym id e chave de API. Teste a conexão antes de seguir.",
  webhook: "Endereço e segredo que o Wellhub usa para avisar reservas e check-ins.",
  mapeamento: "Quais serviços do estúdio são vendidos no Wellhub, e com qual produto.",
  grade: "Envie as aulas e as vagas ao Wellhub (prévia sem enviar nada).",
  repasse: "Valor por check-in, regras de aluno e validação, e ligar a integração.",
};
const ORDEM: Passo["id"][] = ["credenciais", "webhook", "mapeamento", "grade", "repasse"];

export default function WellhubAssistentePage() {
  const { pode } = useAuth();
  const editar = pode("integracoes.editar");
  const tela = useTelaWellhub();
  const configs = tela.data?.configuracoes ?? [];
  const { atual, escolher } = useUnidadeWellhub(configs);
  const painel = useQuery({
    queryKey: ["wellhub-painel", atual?.unidade_id],
    queryFn: () => api.get<Painel>(`/wellhub/unidades/${atual!.unidade_id}/painel`),
    enabled: !!atual,
  });
  const [passo, setPasso] = useState<Passo["id"]>("credenciais");
  const passos = painel.data?.passos ?? ORDEM.map((id) => ({ id, titulo: id, concluido: false, pendencia: null }));
  const i = ORDEM.indexOf(passo);

  return (
    <div className="space-y-6">
      <CabecalhoWellhub extra={<SeletorUnidade configs={configs} atual={atual} onChange={escolher} />} />
      {tela.isPending ? (
        <Skeleton className="h-96 rounded-2xl" />
      ) : !atual ? (
        <EmptyState icone={Wand2} titulo="Nenhuma unidade ativa" descricao="Cadastre uma unidade em Cadastros antes de configurar o Wellhub." />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <ol className="flex gap-2 overflow-x-auto lg:flex-col" aria-label="Passos da configuração">
            {passos.map((p, n) => {
              const on = p.id === passo;
              return (
                <li key={p.id} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => setPasso(p.id)}
                    aria-current={on ? "step" : undefined}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors",
                      on ? "border-brand/40 bg-brand/10" : "border-transparent hover:bg-accent",
                    )}
                  >
                    <span
                      className={cn(
                        "grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold",
                        p.concluido ? "bg-success text-white" : on ? "brand-gradient text-white" : "bg-muted text-muted-foreground",
                      )}
                    >
                      {p.concluido ? <Check className="size-4" /> : n + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{p.titulo}</span>
                      <span className="hidden text-xs text-muted-foreground lg:block">{p.concluido ? "Concluído" : (p.pendencia ?? "")}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          <section className="card-surface space-y-5 p-5">
            <div>
              <p className="text-xs font-medium text-muted-foreground">
                Passo {i + 1} de {ORDEM.length} · {atual.unidade_nome}
              </p>
              <h3 className="text-base font-semibold">{passos[i]?.titulo}</h3>
              <p className="text-sm text-muted-foreground">{DESCRICAO[passo]}</p>
            </div>
            {passo === "credenciais" && <PassoCredenciais key={`c${atual.unidade_id}`} cfg={atual} editar={editar} />}
            {passo === "webhook" && <PassoWebhook key={`w${atual.unidade_id}`} cfg={atual} editar={editar} caminho={tela.data!.webhook_caminho} />}
            {passo === "mapeamento" && <PassoMapeamento key={`m${atual.unidade_id}`} cfg={atual} editar={editar} servicos={tela.data!.servicos} />}
            {passo === "grade" && <PassoGrade key={`g${atual.unidade_id}`} cfg={atual} editar={editar} />}
            {passo === "repasse" && <PassoRepasse key={`r${atual.unidade_id}`} cfg={atual} editar={editar} servicos={tela.data!.servicos} />}
            <div className="flex justify-between border-t pt-4">
              <Button variant="ghost" disabled={i === 0} onClick={() => setPasso(ORDEM[i - 1])}>
                <ArrowLeft /> Anterior
              </Button>
              <Button variant="ghost" disabled={i === ORDEM.length - 1} onClick={() => setPasso(ORDEM[i + 1])}>
                Próximo <ArrowRight />
              </Button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
