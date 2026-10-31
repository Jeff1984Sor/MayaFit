"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Check, CreditCard, ExternalLink, Gem, HandCoins } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Medidor } from "@/components/admin/medidor";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { diasAte, mesAno } from "@/lib/admin";
import { ApiError, api } from "@/lib/api";
import { data, moeda, numero, toNum } from "@/lib/format";
import { type MeuPlano, type PlanoOut, ROTULO_ASSINATURA, TOM_COBRANCA } from "@/lib/tipos-admin";
import { cn } from "@/lib/utils";

function abrir(link: string) {
  window.open(link, "_blank", "noopener");
}

/** "Meu plano" do estúdio: plano atual, uso contra os limites, cobranças em aberto (pagar pelo link) e troca de plano. */
export default function MeuPlanoPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["meu-plano"], queryFn: () => api.get<MeuPlano>("/meu-plano"), retry: false, meta: { silencioso: true } });
  const [troca, setTroca] = useState<PlanoOut | null>(null);
  const trocar = useMutation({
    mutationFn: () =>
      api.put<MeuPlano>("/meu-plano", {
        plano_id: troca!.id,
        ciclo: q.data?.forma_pagamento === "cartao" ? "mensal" : (q.data?.ciclo ?? "mensal"),
      }),
    onSuccess: (r) => {
      toast.success(`Plano alterado para ${r.plano?.nome}`);
      qc.setQueryData(["meu-plano"], r);
      setTroca(null);
    },
  });
  const cartao = useMutation({
    mutationFn: () => api.post<{ link: string }>("/meu-plano/cartao"),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["meu-plano"] });
      abrir(r.link);
    },
  });
  const pagar = useMutation({
    mutationFn: (id: number) => api.post<{ link: string }>(`/meu-plano/cobrancas/${id}/link`),
    onSuccess: (r) => abrir(r.link),
  });

  const cabecalho = (
    <PageHeader
      titulo="Meu plano"
      descricao="O plano do estúdio, o uso do mês e os pagamentos."
      icone={Gem}
      migalhas={[{ label: "Minha conta", href: "/minha-conta" }, { label: "Meu plano" }]}
    />
  );

  if (q.isError) {
    const nao = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div>
        {cabecalho}
        <EmptyState
          icone={Gem}
          titulo={nao ? "Plano não disponível aqui" : "Não deu para carregar o plano"}
          descricao={nao ? "Este ambiente não tem um plano do MayaFit." : q.error.message}
          acao={
            !nao && (
              <Button variant="outline" onClick={() => q.refetch()}>
                Tentar de novo
              </Button>
            )
          }
        />
      </div>
    );
  }
  const m = q.data;
  const atual = m?.plano?.id;
  const ordem = m?.planos.findIndex((p) => p.id === atual) ?? -1;
  const rotRecurso = (k: string) => m?.recursos.find((x) => x.chave === k)?.rotulo ?? k;
  const diasTeste = m?.status === "teste" ? diasAte(m.teste_ate) : null;

  return (
    <div>
      {cabecalho}
      {!m ? (
        <Skeleton className="h-64 w-full rounded-2xl" />
      ) : (
        <div className="space-y-5">
          {m.status === "suspenso" && (
            <div className="card-surface flex flex-wrap items-center gap-3 border-warning/40 p-4 text-sm">
              <HandCoins className="size-5 text-warning-ink" />
              <span className="flex-1">Há pagamento em atraso. Regularize abaixo para evitar o bloqueio do acesso.</span>
            </div>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card-surface space-y-3 p-5">
              <p className="text-sm text-muted-foreground">Plano atual</p>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-2xl font-semibold">{m.plano?.nome ?? "Sem plano"}</p>
                {m.status === "teste" && (
                  <Pill tom="info">
                    teste grátis{m.teste_ate ? ` até ${data(m.teste_ate)}` : ""}
                    {diasTeste != null && diasTeste >= 0 ? ` · faltam ${diasTeste} dia(s)` : ""}
                  </Pill>
                )}
              </div>
              {m.valor && (
                <p className="num text-lg">
                  {moeda(m.valor)} <span className="font-sans text-sm text-muted-foreground">por {m.ciclo === "anual" ? "ano" : "mês"}</span>
                </p>
              )}
              <p className="text-sm text-muted-foreground">
                Pagamento:{" "}
                {m.forma_pagamento === "cartao"
                  ? `cartão, todo mês, automático (${ROTULO_ASSINATURA[m.assinatura_status ?? ""] ?? "cartão ainda não cadastrado"})`
                  : "link do Mercado Pago por e-mail (Pix, cartão ou boleto)"}
              </p>
              {m.pode_alterar && m.ciclo === "mensal" && m.plano && m.assinatura_status !== "authorized" && (
                <Button variant="outline" disabled={cartao.isPending} onClick={() => cartao.mutate()}>
                  <CreditCard /> Pagar no cartão todo mês, automático
                </Button>
              )}
            </div>
            <div className="card-surface space-y-4 p-5">
              <p className="text-sm text-muted-foreground">Uso em {mesAno(m.uso.mes)}</p>
              <Medidor rotulo="Alunos ativos" usado={m.uso.alunos_ativos} limite={m.uso.limite_alunos} />
              <Medidor rotulo="Usuários com acesso" usado={m.uso.usuarios} limite={m.uso.limite_usuarios} />
              {toNum(m.uso.valor_excedente) > 0 ? (
                <p className="text-sm text-warning-ink">
                  Além do plano: <span className="num">{moeda(m.uso.valor_excedente)}</span> (entra na próxima mensalidade).
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">Dentro dos limites do plano.</p>
              )}
            </div>
          </div>

          <div className="card-surface overflow-hidden">
            <p className="border-b px-5 py-3 font-medium">Em aberto</p>
            {m.em_aberto.length === 0 ? (
              <p className="flex items-center gap-2 px-5 py-4 text-sm text-muted-foreground">
                <Check className="size-4 text-success" /> Nenhuma cobrança em aberto.
              </p>
            ) : (
              <div className="divide-y">
                {m.em_aberto.map((k) => (
                  <div key={k.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                    <div className="min-w-40 flex-1">
                      <p className="font-medium">{k.descricao}</p>
                      <p className="text-xs text-muted-foreground">
                        vence <span className="num">{data(k.vencimento)}</span>
                      </p>
                    </div>
                    <span className="num">{moeda(k.valor)}</span>
                    <Pill tom={TOM_COBRANCA[k.status]}>{k.status_rotulo}</Pill>
                    <Button size="sm" disabled={pagar.isPending} onClick={() => pagar.mutate(k.id)}>
                      <ExternalLink /> Pagar
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <p className="mb-3 font-medium">Planos</p>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {m.planos.map((p, i) => {
                const eh = p.id === atual;
                return (
                  <div key={p.id} className={cn("card-surface flex flex-col gap-3 p-5", eh && "border-brand ring-1 ring-brand")}>
                    <p className="text-lg font-semibold">{p.nome}</p>
                    <p className="num text-xl">
                      {moeda(p.preco_mensal)}
                      <span className="font-sans text-sm text-muted-foreground">/mês</span>
                    </p>
                    <ul className="flex-1 space-y-1 text-sm">
                      <li>{p.alunos_ativos != null ? `Até ${numero(p.alunos_ativos)} alunos ativos` : "Alunos ilimitados"}</li>
                      <li>{p.usuarios != null ? `${numero(p.usuarios)} usuário(s)` : "Usuários ilimitados"}</li>
                      {p.recursos.map((r) => (
                        <li key={r} className="flex items-center gap-1.5">
                          <Check className="size-3.5 shrink-0 text-success" /> {rotRecurso(r)}
                        </li>
                      ))}
                    </ul>
                    {eh ? (
                      <Pill tom="brand">Seu plano</Pill>
                    ) : (
                      m.pode_alterar && (
                        <Button variant={ordem < 0 || i > ordem ? "default" : "outline"} onClick={() => setTroca(p)}>
                          <ArrowUpRight /> {ordem >= 0 && i < ordem ? "Mudar para este" : "Fazer upgrade"}
                        </Button>
                      )
                    )}
                  </div>
                );
              })}
            </div>
            {!m.pode_alterar && <p className="mt-2 text-xs text-muted-foreground">Só o administrador do estúdio pode mudar o plano.</p>}
          </div>

          {m.pagas.length > 0 && (
            <div className="card-surface overflow-hidden">
              <p className="border-b px-5 py-3 font-medium">Pagamentos</p>
              <div className="divide-y">
                {m.pagas.map((k) => (
                  <div key={k.id} className="flex flex-wrap items-center gap-3 px-5 py-2.5 text-sm">
                    <span className="flex-1">{k.descricao}</span>
                    <span className="text-xs text-muted-foreground">
                      <span className="num">{data(k.pago_em)}</span>
                      {k.forma_paga && ` · ${k.forma_paga}`}
                    </span>
                    <span className="num">{moeda(k.valor)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      <ConfirmDialog
        open={!!troca}
        onOpenChange={(o) => !o && setTroca(null)}
        titulo={`Mudar para o plano ${troca?.nome ?? ""}?`}
        descricao={troca ? `Os limites mudam agora. A próxima mensalidade já vem em ${moeda(troca.preco_mensal)}.` : undefined}
        confirmar="Mudar de plano"
        carregando={trocar.isPending}
        onConfirm={() => trocar.mutate()}
      />
    </div>
  );
}
