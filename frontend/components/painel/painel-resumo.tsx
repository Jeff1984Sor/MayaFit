"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BarChart3,
  BellRing,
  Cake,
  CalendarCheck,
  CalendarClock,
  CalendarDays,
  CircleCheckBig,
  FileClock,
  Hourglass,
  Medal,
  RefreshCw,
  Rocket,
  Sparkles,
  UsersRound,
  Wallet,
  WalletCards,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { useEffect } from "react";

import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { moeda, numero, toNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ResumoPainel } from "@/lib/tipos-painel";

import { GraficoAulasPorMes } from "./graficos-painel";
import {
  ItemAlerta,
  KpiPainel,
  LinhaAniversariante,
  LinhasEsqueleto,
  ListaPassos,
  Secao,
  SeloStatusAula,
  Vazio,
  VariacaoRecebido,
} from "./blocos";

const ATUALIZA_A_CADA_MS = 60_000;

function saudacao(hora: number) {
  return hora < 12 ? "Bom dia" : hora < 18 ? "Boa tarde" : "Boa noite";
}

function dataPorExtenso(iso: string | undefined) {
  const d = iso ? new Date(`${iso}T00:00:00`) : new Date();
  const t = d.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function PainelResumo() {
  const { usuario, pode, somenteProprias, carregando: carregandoAuth } = useAuth();
  const { nome_exibicao } = useBrand();
  const router = useRouter();

  // Professor não usa o painel: vai direto para as aulas dele (como no sistema antigo)
  useEffect(() => {
    if (somenteProprias) router.replace("/agenda/aulas");
  }, [somenteProprias, router]);

  const liberado = pode("painel.ver") && !somenteProprias;
  const q = useQuery({
    queryKey: ["painel", "resumo"],
    queryFn: () => api.get<ResumoPainel>("/painel/resumo"),
    enabled: liberado,
    refetchInterval: ATUALIZA_A_CADA_MS,
    refetchOnWindowFocus: true,
    placeholderData: (anterior) => anterior,
  });

  if (carregandoAuth || somenteProprias) return <Skeleton className="h-40 w-full" />;
  if (!pode("painel.ver")) return <SemAcesso />;

  const r = q.data;
  const carregando = q.isPending;
  const primeiroNome = usuario?.nome.split(" ")[0] ?? "";
  const hora = new Date().getHours();
  const atualizadoEm = q.dataUpdatedAt
    ? new Date(q.dataUpdatedAt).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div>
      <HeroPainel
        titulo={`${saudacao(hora)}, ${primeiroNome}`}
        data={dataPorExtenso(r?.hoje)}
        estudio={nome_exibicao}
        r={r}
        atualizadoEm={atualizadoEm}
        atualizando={q.isFetching}
        onAtualizar={() => q.refetch()}
      />

      {q.isError && !r && (
        <div className="card-surface mb-6 flex flex-wrap items-center justify-between gap-3 p-5">
          <p className="text-sm">Não foi possível carregar o painel agora.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}

      {r?.primeiros_passos.visivel && !r.primeiros_passos.completo && (
        <Secao
          titulo="Primeiros passos"
          descricao="Deixe o estúdio pronto para o primeiro aluno. Esta lista some quando o básico estiver cadastrado."
          icone={Rocket}
          className="mb-6"
        >
          <ListaPassos passos={r.primeiros_passos.passos} />
        </Secao>
      )}

      <Kpis r={r} carregando={carregando} />

      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        {(carregando || r?.aulas_por_mes.visivel) && (
          <Secao
            titulo="Aulas por mês"
            descricao="Últimos 6 meses, sem as aulas canceladas"
            icone={BarChart3}
            className="xl:col-span-2"
            acao={r && <span className="text-xs text-muted-foreground num">{numero(r.aulas_por_mes.total)} no período</span>}
          >
            {carregando || !r ? (
              <Skeleton className="h-64 w-full" />
            ) : r.aulas_por_mes.total === 0 ? (
              <Vazio icone={CalendarDays} texto="Ainda não há aulas no período" dica="Quando as aulas forem agendadas, o gráfico aparece aqui." />
            ) : (
              <GraficoAulasPorMes meses={r.aulas_por_mes.meses} />
            )}
          </Secao>
        )}
        {(carregando || r?.alertas.visivel) && (
          <Secao
            titulo="Alertas"
            descricao="O que precisa da sua atenção"
            icone={BellRing}
            acao={
              r && r.alertas.itens.length > 0 && (
                <span className="rounded-full bg-danger/10 px-2 py-0.5 text-xs font-semibold text-danger-ink num">{r.alertas.itens.length}</span>
              )
            }
          >
            {carregando || !r ? (
              <LinhasEsqueleto n={3} />
            ) : r.alertas.itens.length === 0 ? (
              <Vazio icone={CircleCheckBig} texto="Tudo em dia" dica="Nenhuma pendência no momento." />
            ) : (
              <div className="space-y-2">
                {r.alertas.itens.map((a) => (
                  <ItemAlerta key={a.chave} a={a} />
                ))}
              </div>
            )}
          </Secao>
        )}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {(carregando || r?.proximas_aulas.visivel) && (
          <Secao
            titulo="Próximas aulas de hoje"
            icone={CalendarClock}
            acao={
              r?.proximas_aulas.href && (
                <Link href={r.proximas_aulas.href} className="text-xs font-medium text-navy hover:underline dark:text-brand">
                  Ver todas
                </Link>
              )
            }
          >
            {carregando || !r ? (
              <LinhasEsqueleto />
            ) : r.proximas_aulas.itens.length === 0 ? (
              <Vazio icone={CalendarClock} texto="Sem mais aulas hoje" dica="As aulas que ainda vão acontecer hoje aparecem aqui." />
            ) : (
              <ol className="relative space-y-1 before:absolute before:top-2 before:bottom-2 before:left-[65px] before:w-px before:bg-border">
                {r.proximas_aulas.itens.map((a, i) => (
                  <motion.li
                    key={a.reserva_id}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.15 + i * 0.04 }}
                    className="relative flex items-center gap-3 rounded-lg py-1.5 pr-1 transition-colors hover:bg-muted/60"
                  >
                    <span className="w-12 shrink-0 text-right text-xs font-semibold text-muted-foreground num">{a.hora}</span>
                    <span
                      className={cn(
                        "relative z-10 size-2.5 shrink-0 rounded-full ring-4 ring-card",
                        i === 0 ? "bg-brand shadow-[0_0_10px_var(--brand)]" : "bg-brand/40",
                      )}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{a.aluno ?? "Aluno reservado"}</span>
                      <span className="block truncate text-xs text-muted-foreground">{a.professor ?? "Sem profissional"}</span>
                    </span>
                    <SeloStatusAula status={a.status} />
                  </motion.li>
                ))}
                {r.proximas_aulas.restantes > 0 && (
                  <li className="pt-2 pl-[82px] text-xs text-muted-foreground">+ {r.proximas_aulas.restantes} aulas depois destas</li>
                )}
              </ol>
            )}
          </Secao>
        )}
        {(carregando || r?.ranking_professores.visivel) && (
          <Secao titulo="Professores no mês" descricao="Aulas do mês por profissional" icone={Medal}>
            {carregando || !r ? (
              <LinhasEsqueleto />
            ) : r.ranking_professores.itens.length === 0 ? (
              <Vazio icone={Medal} texto="Sem aulas neste mês" dica="O ranking aparece quando houver aulas no mês." />
            ) : (
              <RankingProfessores itens={r.ranking_professores.itens} />
            )}
          </Secao>
        )}
        {(carregando || r?.aniversariantes.visivel) && (
          <Secao titulo="Aniversariantes" descricao="Hoje e nos próximos 7 dias" icone={Cake}>
            {carregando || !r ? (
              <LinhasEsqueleto />
            ) : r.aniversariantes.itens.length === 0 ? (
              <Vazio icone={Cake} texto="Nenhum aniversário por perto" dica="Os próximos aniversários dos alunos ativos aparecem aqui." />
            ) : (
              <ul className="divide-y">
                {r.aniversariantes.itens.map((a) => (
                  <LinhaAniversariante key={a.aluno_id} a={a} />
                ))}
              </ul>
            )}
          </Secao>
        )}
      </div>
    </div>
  );
}

function RankingProfessores({ itens }: { itens: { profissional_id: number; nome: string; total: number }[] }) {
  const maximo = Math.max(...itens.map((i) => i.total), 1);
  return (
    <ol className="space-y-3">
      {itens.map((p, i) => (
        <li key={p.profissional_id}>
          <div className="mb-1 flex items-center justify-between gap-2 text-sm">
            <span className="min-w-0 truncate">
              <span
                className={cn(
                  "mr-2 inline-grid size-5 place-items-center rounded-full text-[10px] num",
                  i === 0 ? "bg-amber-maya/20 font-bold text-warning-ink" : "bg-muted text-muted-foreground",
                )}
              >
                {i + 1}º
              </span>
              <span className="font-medium">{p.nome}</span>
            </span>
            <span className="shrink-0 text-xs text-muted-foreground num">{numero(p.total)} aulas</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted" role="presentation">
            <motion.div
              className={cn("h-full rounded-full", i === 0 ? "brand-gradient" : "bg-brand/70")}
              initial={{ width: 0 }}
              animate={{ width: `${Math.round((p.total / maximo) * 100)}%` }}
              transition={{ duration: 0.7, delay: 0.1 + i * 0.05, ease: "easeOut" }}
            />
          </div>
        </li>
      ))}
    </ol>
  );
}

function Kpis({ r, carregando }: { r: ResumoPainel | undefined; carregando: boolean }) {
  const k = r?.kpis;
  const rm = r?.recebido_mes;
  // enquanto carrega ainda não sabemos o que o perfil enxerga: mostra os esqueletos de sempre
  const mostrar = (visivel: boolean | undefined) => carregando || !!visivel;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {mostrar(k?.alunos_ativos.visivel) && (
        <KpiPainel
          titulo="Alunos ativos"
          valor={numero(k?.alunos_ativos.valor)}
          animar={{ valor: k?.alunos_ativos.valor ?? 0, formato: numero }}
          indice={0}
          rodape={k?.alunos_ativos.valor === 0 ? "Cadastre o primeiro aluno para começar" : "Ver alunos ativos"}
          icone={UsersRound}
          href={k?.alunos_ativos.href}
          carregando={carregando}
        />
      )}
      {mostrar(k?.aulas.visivel) && (
        <KpiPainel
          titulo="Aulas hoje"
          valor={numero(k?.aulas.hoje)}
          animar={{ valor: k?.aulas.hoje ?? 0, formato: numero }}
          serie={r?.aulas_por_mes.visivel ? r.aulas_por_mes.meses.map((m) => m.total) : undefined}
          indice={1}
          rodape={`${numero(k?.aulas.amanha)} amanhã`}
          icone={CalendarCheck}
          href={k?.aulas.href}
          carregando={carregando}
        />
      )}
      {mostrar(k?.contratos_vencendo.visivel) && (
        <KpiPainel
          titulo="Contratos vencendo"
          valor={numero(k?.contratos_vencendo.valor)}
          animar={{ valor: k?.contratos_vencendo.valor ?? 0, formato: numero }}
          indice={2}
          rodape="nos próximos 30 dias"
          icone={FileClock}
          href={k?.contratos_vencendo.href}
          carregando={carregando}
        />
      )}
      {mostrar(k?.a_receber.visivel) && (
        <KpiPainel
          titulo="A receber (em aberto)"
          valor={moeda(k?.a_receber.valor)}
          animar={{ valor: toNum(k?.a_receber.valor), formato: moeda }}
          indice={3}
          rodape={`${numero(k?.a_receber.quantidade)} cobranças a vencer`}
          icone={Wallet}
          href={k?.a_receber.href}
          carregando={carregando}
        />
      )}
      {mostrar(k?.atrasado.visivel) && (
        <KpiPainel
          titulo="Atrasado"
          valor={moeda(k?.atrasado.valor)}
          animar={{ valor: toNum(k?.atrasado.valor), formato: moeda }}
          indice={4}
          rodape={`${numero(k?.atrasado.quantidade)} cobranças vencidas`}
          icone={Hourglass}
          tom={(k?.atrasado.quantidade ?? 0) > 0 ? "perigo" : "neutro"}
          href={k?.atrasado.href}
          carregando={carregando}
        />
      )}
      {mostrar(rm?.visivel) && (
        <KpiPainel
          titulo="Recebido no mês"
          valor={moeda(rm?.valor)}
          animar={{ valor: toNum(rm?.valor), formato: moeda }}
          indice={5}
          rodape={rm && <VariacaoRecebido pct={rm.variacao_pct} base={rm.anterior_ate_mesmo_dia} />}
          icone={WalletCards}
          href={rm?.href}
          carregando={carregando}
        />
      )}
    </div>
  );
}

/** Faixa de boas-vindas do painel: saudação, resumo do dia e atalhos (só o que o perfil pode abrir). */
function HeroPainel({
  titulo,
  data,
  estudio,
  r,
  atualizadoEm,
  atualizando,
  onAtualizar,
}: {
  titulo: string;
  data: string;
  estudio: string;
  r: ResumoPainel | undefined;
  atualizadoEm: string | null;
  atualizando: boolean;
  onAtualizar: () => void;
}) {
  const { pode } = useAuth();
  const atalhos = [
    { label: "Aulas do dia", href: "/agenda/aulas", icone: CalendarCheck, ok: pode("aulas.ver") },
    { label: "Grade semanal", href: "/agenda/semana", icone: CalendarDays, ok: pode("agenda.ver") },
    { label: "Alunos", href: "/alunos", icone: UsersRound, ok: pode("alunos.ver") },
    { label: "A receber", href: "/financeiro/receber", icone: Wallet, ok: pode("financeiro_receber.ver") },
  ].filter((a) => a.ok);
  const aulasHoje = r?.kpis.aulas.visivel ? (r.kpis.aulas.hoje ?? 0) : null;
  const aniversariosHoje = r?.aniversariantes.visivel ? r.aniversariantes.itens.filter((a) => a.hoje).length : 0;
  const alertas = r?.alertas.visivel ? r.alertas.itens.filter((a) => a.gravidade !== "info").length : 0;
  const resumo = [
    aulasHoje != null && `${numero(aulasHoje)} aula${aulasHoje === 1 ? "" : "s"} hoje`,
    aniversariosHoje > 0 && `${aniversariosHoje} aniversariante${aniversariosHoje === 1 ? "" : "s"} hoje`,
    alertas > 0 && `${alertas} alerta${alertas === 1 ? "" : "s"} para ver`,
  ].filter(Boolean) as string[];

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="relative mb-6 overflow-hidden rounded-3xl bg-dark-maya p-6 text-white shadow-xl shadow-dark-maya/20 sm:p-8"
      aria-labelledby="painel-titulo"
    >
      <div className="grid-bg absolute inset-0 opacity-50" />
      <div className="pointer-events-none absolute -top-24 -left-16 size-72 rounded-full bg-brand/40 blur-[90px]" />
      <div className="pointer-events-none absolute -right-20 -bottom-24 size-72 rounded-full bg-navy/90 blur-[80px]" />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-white/80 backdrop-blur">
            <Sparkles className="size-3.5 text-brand" />
            {data}
          </p>
          <h1 id="painel-titulo" className="truncate text-2xl font-semibold tracking-tight sm:text-3xl">
            {titulo}
          </h1>
          <p className="mt-1 text-sm text-white/60">{estudio}</p>
          {resumo.length > 0 && (
            <ul className="mt-4 flex flex-wrap gap-2">
              {resumo.map((t) => (
                <li key={t} className="rounded-lg bg-white/8 px-2.5 py-1 text-xs font-medium text-white/90 ring-1 ring-white/10">
                  {t}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="flex flex-col gap-3 lg:items-end">
          {atalhos.length > 0 && (
            <nav aria-label="Atalhos" className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
              {atalhos.map((a) => (
                <Link
                  key={a.href}
                  href={a.href}
                  className="group flex items-center gap-2 rounded-xl bg-white/8 px-3 py-2 text-sm font-medium ring-1 ring-white/12 backdrop-blur transition hover:bg-white/14 hover:ring-brand/50"
                >
                  <a.icone className="size-4 shrink-0 text-brand" />
                  <span className="truncate">{a.label}</span>
                  <ArrowUpRight className="ml-auto size-3.5 shrink-0 opacity-0 transition group-hover:opacity-70" />
                </Link>
              ))}
            </nav>
          )}
          <div className="flex items-center gap-2 text-xs text-white/55">
            {atualizadoEm && <span>Atualizado às {atualizadoEm}</span>}
            <Button
              variant="ghost"
              size="sm"
              onClick={onAtualizar}
              disabled={atualizando}
              className="h-7 text-white/80 hover:bg-white/10 hover:text-white"
            >
              <RefreshCw className={atualizando ? "animate-spin" : ""} />
              Atualizar
            </Button>
          </div>
        </div>
      </div>
    </motion.section>
  );
}
