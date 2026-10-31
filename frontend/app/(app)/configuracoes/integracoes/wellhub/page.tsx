"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarCheck2, CheckCircle2, Circle, HandCoins, ListChecks, TicketCheck, Wand2 } from "lucide-react";
import Link from "next/link";

import { KpiCard } from "@/components/mayacorp/kpi-card";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CabecalhoWellhub, Indicador, ListaAlertas, PillResultado, RAIZ, SeletorUnidade, useTelaWellhub, useUnidadeWellhub } from "@/components/wellhub/comum";
import { GraficoCheckins } from "@/components/wellhub/grafico-checkins";
import { ValidarCheckin } from "@/components/wellhub/validar-checkin";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora, moeda, numero } from "@/lib/format";
import type { Painel } from "@/lib/tipos-wellhub";
import { cn } from "@/lib/utils";

function nomeDoMes(mes: string) {
  const [a, m] = mes.split("-").map(Number);
  return new Date(a, m - 1, 1).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
}

export default function WellhubPainelPage() {
  const { pode } = useAuth();
  const tela = useTelaWellhub();
  const configs = tela.data?.configuracoes ?? [];
  const { atual, escolher } = useUnidadeWellhub(configs);
  const painel = useQuery({
    queryKey: ["wellhub-painel", atual?.unidade_id],
    queryFn: () => api.get<Painel>(`/wellhub/unidades/${atual!.unidade_id}/painel`),
    enabled: !!atual,
    refetchInterval: 60_000,
  });
  const p = painel.data;
  const carregando = tela.isPending || painel.isPending;
  const feitos = p?.passos.filter((x) => x.concluido).length ?? 0;

  return (
    <div className="space-y-6">
      <CabecalhoWellhub extra={<SeletorUnidade configs={configs} atual={atual} onChange={escolher} />} />
      {tela.isSuccess && configs.length === 0 ? (
        <EmptyState icone={TicketCheck} titulo="Nenhuma unidade ativa" descricao="Cadastre uma unidade em Cadastros antes de configurar o Wellhub." />
      ) : (
        <>
          {p && !p.configurada && (
            <div className="card-surface flex flex-wrap items-center justify-between gap-4 p-5">
              <div>
                <h3 className="font-semibold">Comece pelo assistente</h3>
                <p className="text-sm text-muted-foreground">
                  Em 5 passos: credenciais, webhook, serviços, grade e repasse. Cada passo tem o seu botão de teste.
                </p>
              </div>
              <Button render={<Link href={`${RAIZ}/configurar`} />}>
                <Wand2 /> Configurar o Wellhub
              </Button>
            </div>
          )}
          {p && <ListaAlertas alertas={p.alertas} />}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard titulo={`Check-ins validados · ${p ? nomeDoMes(p.mes) : ""}`} valor={numero(p?.checkins_validados_mes)} icone={TicketCheck}
              variacao={p?.variacao_checkins} carregando={carregando} indice={0} />
            <Indicador titulo="Repasse estimado do mês" valor={moeda(p?.valor_estimado_mes)} icone={HandCoins} carregando={carregando}
              rodape={p?.valor_repasse_checkin ? `${moeda(p.valor_repasse_checkin)} por check-in validado` : "Informe o valor por check-in no assistente"} />
            <Indicador titulo="Reservas do mês" valor={numero(p?.reservas_mes)} icone={CalendarCheck2} carregando={carregando}
              rodape={p ? `${p.rejeitadas_mes} recusada(s) por lotação · ${p.cancelamentos_mes} cancelada(s)` : undefined} />
            <Indicador titulo="Eventos com erro" valor={numero(p?.eventos_com_erro)} icone={ListChecks} carregando={carregando}
              tom={p && p.eventos_com_erro > 0 ? "danger" : undefined}
              rodape={p ? `${p.checkins_pendentes_mes} check-in(s) aguardando validação` : undefined} />
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
            <section className="card-surface p-5">
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold">Check-ins por dia</h3>
                <p className="text-xs text-muted-foreground">
                  <span className="mr-1 inline-block size-2 rounded-sm bg-brand" /> validados
                  <span className="mr-1 ml-3 inline-block size-2 rounded-sm bg-brand/30" /> pendentes
                </p>
              </div>
              {carregando ? (
                <Skeleton className="h-56 w-full rounded-xl" />
              ) : (p?.serie.length ?? 0) === 0 || p!.checkins_mes === 0 ? (
                <EmptyState icone={TicketCheck} titulo="Nenhum check-in neste mês" descricao="Quando um aluno do Wellhub fizer check-in, ele aparece aqui." className="py-8" />
              ) : (
                <GraficoCheckins serie={p!.serie} />
              )}
            </section>

            <section className="card-surface space-y-3 p-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">Configuração</h3>
                <Pill tom={feitos === 5 ? "success" : "warning"}>{feitos} de 5</Pill>
              </div>
              <ol className="space-y-2">
                {(p?.passos ?? []).map((s) => (
                  <li key={s.id} className="flex items-start gap-2 text-sm">
                    {s.concluido ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success-ink" /> : <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
                    <div>
                      <p className={cn(s.concluido && "text-muted-foreground")}>{s.titulo}</p>
                      {s.pendencia && <p className="text-xs text-muted-foreground">{s.pendencia}</p>}
                    </div>
                  </li>
                ))}
              </ol>
              <div className="flex flex-wrap items-center gap-2 border-t pt-3 text-xs text-muted-foreground">
                {p && <Pill tom={p.ativo ? "success" : "neutral"}>{p.ativo ? "Ativa" : "Desligada"}</Pill>}
                {p && <Pill tom={p.ambiente === "producao" ? "info" : "warning"}>{p.ambiente === "producao" ? "Produção" : "Sandbox"}</Pill>}
                {p && <span>{p.slots_futuros} horário(s) publicados</span>}
              </div>
              <Button variant="outline" size="sm" render={<Link href={`${RAIZ}/configurar`} />}>
                <Wand2 /> Abrir assistente
              </Button>
            </section>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
            <section className="card-surface p-5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Últimos eventos</h3>
                <Link href={`${RAIZ}/eventos`} className="text-xs font-medium text-info-ink underline-offset-2 hover:underline">
                  Ver todos
                </Link>
              </div>
              {(p?.ultimos_eventos ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">Nada recebido ainda.</p>
              ) : (
                <ul className="divide-y">
                  {p!.ultimos_eventos.map((e) => (
                    <li key={e.id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {e.tipo_rotulo}
                          {e.aluno_nome ? ` · ${e.aluno_nome}` : ""}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">{e.erro ?? dataHora(e.recebido_em)}</p>
                      </div>
                      <PillResultado resultado={e.resultado} ignorado={e.ignorado} />
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <ValidarCheckin podeValidar={pode("integracoes.editar") && !!p?.ativo} />
          </div>
        </>
      )}
    </div>
  );
}
