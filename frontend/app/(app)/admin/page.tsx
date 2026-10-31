"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BadgeDollarSign,
  Building2,
  CheckCircle2,
  Hourglass,
  Inbox,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AcoesRapidas } from "@/components/admin/acoes-rapidas";
import { BarrasNovos, FunilSolicitacoes, GraficoReceita, novosPorMes, receitaPorMes } from "@/components/admin/graficos";
import { Indicador } from "@/components/admin/indicador";
import { linhaClicavel, TableCard, TableSkeleton } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { diasAte, useEstudios, useResumoAdmin } from "@/lib/admin";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda, numero, toNum } from "@/lib/format";
import { type Cobranca, type ResumoCobranca, ROTULO_STATUS, type Solicitacao, TOM_STATUS } from "@/lib/tipos-admin";

/** Testes que acabam em até N dias aparecem como "vencendo". */
const JANELA_TESTE = 7;

function saudacao() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

const pct = (n: number, d: number) => (d ? `${((n / d) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%` : "—");

function Bloco({ titulo, acao, children, className }: { titulo: string; acao?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`card-surface p-5 ${className ?? ""}`}>
      <div className="mb-4 flex items-center justify-between gap-2">
        <h2 className="font-medium">{titulo}</h2>
        {acao}
      </div>
      {children}
    </section>
  );
}

/** Início do admin MayaCorp: a carteira de estúdios do MayaFit. */
export default function InicioAdminPage() {
  const router = useRouter();
  const { usuario } = useAuth();
  const resumo = useResumoAdmin();
  const estudios = useEstudios();
  const cobr = useQuery({ queryKey: ["admin", "cobrancas", "resumo"], queryFn: () => api.get<ResumoCobranca>("/admin/cobrancas/resumo") });
  const cobrancas = useQuery({ queryKey: ["admin", "cobrancas", "todas"], queryFn: () => api.get<Cobranca[]>("/admin/cobrancas") });
  const solicitacoes = useQuery({ queryKey: ["admin", "solicitacoes", "todas"], queryFn: () => api.get<Solicitacao[]>("/admin/solicitacoes") });
  const r = resumo.data;
  const c = cobr.data;
  const lista = estudios.data ?? [];
  const ps = r?.por_status ?? {};

  // crescimento: estúdios criados neste mês x mês passado
  const novos = novosPorMes(lista, 6);
  const novosMes = novos[novos.length - 1]?.novos ?? 0;
  const novosAntes = novos[novos.length - 2]?.novos ?? 0;
  // churn acumulado: inativos sobre todos os que já existiram (o controle não guarda a data da mudança de situação)
  const inativos = ps.inativo ?? lista.filter((e) => e.status === "inativo").length;
  const total = r?.clientes ?? lista.length;

  const vencendo = lista.filter((e) => {
    const d = e.status === "teste" ? diasAte(e.teste_ate) : null;
    return d != null && d <= JANELA_TESTE;
  });
  const novasSol = (solicitacoes.data ?? []).filter((s) => s.status === "nova").length;
  // pedem atenção: teste acabando (ou já acabado), suspensos e sem plano
  const atencao = lista
    .filter((e) => vencendo.includes(e) || e.status === "suspenso" || (!e.plano && e.status !== "inativo"))
    .sort((a, b) => (a.teste_ate ?? "9999").localeCompare(b.teste_ate ?? "9999"));

  return (
    <div className="space-y-5">
      <PageHeader
        className="mb-0"
        titulo={`${saudacao()}, ${usuario?.nome.split(" ")[0] ?? ""}.`}
        descricao="A carteira de estúdios do MayaFit num relance."
        icone={Building2}
        migalhas={[{ label: "Admin MayaFit" }, { label: "Início" }]}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador
          titulo="Receita mensal (MRR)"
          icone={BadgeDollarSign}
          carregando={!r}
          valor={r ? moeda(r.mrr) : "—"}
          legenda={r ? `${numero(ps.ativo ?? 0)} ativos · ${numero(ps.suspenso ?? 0)} suspensos` : undefined}
          href="/admin/estudios?status=ativo"
        />
        <Indicador
          titulo="Crescimento"
          icone={TrendingUp}
          tom={novosMes > 0 ? "success" : undefined}
          carregando={estudios.isPending}
          valor={`+${numero(novosMes)}`}
          legenda={`estúdios novos no mês · ${numero(novosAntes)} no anterior`}
          href="/admin/estudios"
        />
        <Indicador
          titulo="Churn (acumulado)"
          icone={TrendingDown}
          tom={inativos > 0 ? "danger" : undefined}
          carregando={!r}
          valor={pct(inativos, total)}
          legenda={`${numero(inativos)} inativo(s) de ${numero(total)}`}
          href="/admin/estudios?status=inativo"
        />
        <Indicador
          titulo="Em teste grátis"
          icone={Hourglass}
          tom={vencendo.length ? "warning" : undefined}
          carregando={!r}
          valor={numero(ps.teste ?? 0)}
          legenda={estudios.data ? `${vencendo.length} acabando em até ${JANELA_TESTE} dias` : undefined}
          href="/admin/estudios?status=teste"
        />
        <Indicador
          titulo="Cobranças vencidas"
          icone={AlertTriangle}
          tom={c && toNum(c.vencido) > 0 ? "danger" : undefined}
          carregando={!c}
          valor={c ? moeda(c.vencido) : "—"}
          legenda={c ? `${numero(c.inadimplentes)} estúdio(s) em atraso` : undefined}
          href="/admin/cobrancas?status=vencida"
        />
        <Indicador titulo="Em aberto (a vencer)" icone={Wallet} carregando={!c} valor={c ? moeda(c.em_aberto) : "—"} href="/admin/cobrancas?status=pendente" />
        <Indicador
          titulo="Recebido no mês"
          icone={CheckCircle2}
          tom="success"
          carregando={!c}
          valor={c ? moeda(c.recebido_mes) : "—"}
          href="/admin/cobrancas?status=paga"
        />
        <Indicador
          titulo="Solicitações novas"
          icone={Inbox}
          tom={novasSol ? "warning" : undefined}
          carregando={solicitacoes.isPending}
          valor={numero(novasSol)}
          legenda="cadastros pelo site esperando você"
          href="/admin/solicitacoes"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Bloco
          titulo="Receita por mês"
          className="lg:col-span-2"
          acao={
            <Link href="/admin/cobrancas" className="text-xs text-muted-foreground hover:underline">
              Ver cobranças
            </Link>
          }
        >
          {cobrancas.isPending ? <Skeleton className="h-64" /> : <GraficoReceita pontos={receitaPorMes(cobrancas.data ?? [])} />}
        </Bloco>
        <div className="grid gap-5">
          <Bloco titulo="Funil do cadastro pelo site">
            {solicitacoes.isPending || estudios.isPending ? (
              <Skeleton className="h-32" />
            ) : (
              <FunilSolicitacoes solicitacoes={solicitacoes.data ?? []} estudios={lista} />
            )}
          </Bloco>
          <Bloco titulo="Estúdios novos por mês">{estudios.isPending ? <Skeleton className="h-24" /> : <BarrasNovos pontos={novos} />}</Bloco>
        </div>
      </div>

      <div>
        <h2 className="mb-2 font-medium">Pedem atenção</h2>
        <TableCard>
          {estudios.isPending ? (
            <TableSkeleton colunas={4} linhas={3} />
          ) : !atencao.length ? (
            <EmptyState icone={CheckCircle2} titulo="Tudo em dia" descricao="Nenhum teste acabando, nenhum estúdio suspenso ou sem plano." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Estúdio</th>
                    <th className="px-3 py-2.5 font-medium">Plano</th>
                    <th className="px-3 py-2.5 font-medium">Teste até</th>
                    <th className="px-3 py-2.5 font-medium">Situação</th>
                    <th className="px-3 py-2.5 text-right font-medium">Ações rápidas</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {atencao.map((e) => {
                    const d = e.status === "teste" ? diasAte(e.teste_ate) : null;
                    return (
                      <tr key={e.id} className={linhaClicavel} onClick={() => router.push(`/admin/estudios/${e.id}`)}>
                        <td className="px-4 py-3 font-medium">{e.nome}</td>
                        <td className="px-3 py-3">{e.plano?.nome ?? <span className="text-warning-ink">sem plano</span>}</td>
                        <td className="px-3 py-3 text-xs">
                          <span className="num">{e.teste_ate ? data(e.teste_ate) : "—"}</span>
                          {d != null && (
                            <span className={d < 0 ? "ml-1.5 text-danger-ink" : "ml-1.5 text-warning-ink"}>
                              {d < 0 ? `acabou há ${-d} dia(s)` : d === 0 ? "acaba hoje" : `faltam ${d} dia(s)`}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <Pill tom={TOM_STATUS[e.status]}>{ROTULO_STATUS[e.status]}</Pill>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex justify-end">
                            <AcoesRapidas estudio={e} compacto semAcesso />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </TableCard>
      </div>
    </div>
  );
}
