"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BadgeDollarSign, Building2, CheckCircle2, Hourglass, Inbox, PauseCircle, Wallet } from "lucide-react";
import { useRouter } from "next/navigation";

import { Indicador } from "@/components/admin/indicador";
import { linhaClicavel, TableCard, TableSkeleton } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { diasAte, useEstudios, useResumoAdmin } from "@/lib/admin";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda, numero } from "@/lib/format";
import { type ResumoCobranca, ROTULO_STATUS, type Solicitacao, TOM_STATUS } from "@/lib/tipos-admin";

/** Testes que acabam em até N dias aparecem como "vencendo". */
const JANELA_TESTE = 7;

function saudacao() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

/** Início do admin MayaCorp: a carteira de estúdios do MayaFit. */
export default function InicioAdminPage() {
  const router = useRouter();
  const { usuario } = useAuth();
  const resumo = useResumoAdmin();
  const estudios = useEstudios();
  const cobr = useQuery({ queryKey: ["admin", "cobrancas", "resumo"], queryFn: () => api.get<ResumoCobranca>("/admin/cobrancas/resumo") });
  const novas = useQuery({
    queryKey: ["admin", "solicitacoes", "nova"],
    queryFn: () => api.get<Solicitacao[]>("/admin/solicitacoes", { status: "nova" }),
  });
  const r = resumo.data;
  const c = cobr.data;
  const lista = estudios.data ?? [];
  const vencendo = lista.filter((e) => {
    const d = e.status === "teste" ? diasAte(e.teste_ate) : null;
    return d != null && d <= JANELA_TESTE;
  });
  // pedem atenção: teste acabando (ou já acabado), suspensos e sem plano
  const atencao = lista
    .filter((e) => vencendo.includes(e) || e.status === "suspenso" || (!e.plano && e.status !== "inativo"))
    .sort((a, b) => (a.teste_ate ?? "9999").localeCompare(b.teste_ate ?? "9999"));
  const ps = r?.por_status ?? {};

  return (
    <div>
      <PageHeader
        titulo={`${saudacao()}, ${usuario?.nome.split(" ")[0] ?? ""}.`}
        descricao="A carteira de estúdios do MayaFit."
        icone={Building2}
        migalhas={[{ label: "MayaCorp" }, { label: "Início" }]}
      />

      <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador titulo="Receita mensal (MRR)" icone={BadgeDollarSign} carregando={!r} valor={r ? moeda(r.mrr) : "—"} legenda="ativos e suspensos" />
        <Indicador
          titulo="Estúdios ativos"
          icone={CheckCircle2}
          tom="success"
          carregando={!r}
          valor={numero(ps.ativo ?? 0)}
          legenda={r ? `${numero(r.clientes)} no total` : undefined}
          href="/admin/estudios?status=ativo"
        />
        <Indicador
          titulo="Em teste"
          icone={Hourglass}
          carregando={!r}
          valor={numero(ps.teste ?? 0)}
          legenda={estudios.data ? `${vencendo.length} acabando em até ${JANELA_TESTE} dias` : undefined}
          tom={vencendo.length ? "warning" : undefined}
          href="/admin/estudios?status=teste"
        />
        <Indicador
          titulo="Suspensos / inativos"
          icone={PauseCircle}
          carregando={!r}
          valor={`${numero(ps.suspenso ?? 0)} / ${numero(ps.inativo ?? 0)}`}
          href="/admin/estudios?status=suspenso"
        />
      </div>
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador
          titulo="Cobranças vencidas"
          icone={AlertTriangle}
          tom={c && Number(c.vencido) > 0 ? "danger" : undefined}
          carregando={!c}
          valor={c ? moeda(c.vencido) : "—"}
          legenda={c ? `${numero(c.inadimplentes)} estúdio(s) em atraso` : undefined}
          href="/admin/cobrancas?status=vencida"
        />
        <Indicador
          titulo="Em aberto (a vencer)"
          icone={Wallet}
          carregando={!c}
          valor={c ? moeda(c.em_aberto) : "—"}
          href="/admin/cobrancas?status=pendente"
        />
        <Indicador titulo="Recebido no mês" icone={CheckCircle2} tom="success" carregando={!c} valor={c ? moeda(c.recebido_mes) : "—"} href="/admin/cobrancas?status=paga" />
        <Indicador
          titulo="Solicitações novas"
          icone={Inbox}
          tom={novas.data?.length ? "warning" : undefined}
          carregando={!novas.data}
          valor={numero(novas.data?.length ?? 0)}
          legenda="cadastros pelo site"
          href="/admin/solicitacoes"
        />
      </div>

      <h2 className="mb-2 font-medium">Pedem atenção</h2>
      <TableCard>
        {estudios.isPending ? (
          <TableSkeleton colunas={4} linhas={3} />
        ) : !atencao.length ? (
          <EmptyState icone={CheckCircle2} titulo="Tudo em dia" descricao="Nenhum teste acabando, nenhum estúdio suspenso ou sem plano." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Estúdio</th>
                  <th className="px-3 py-2.5 font-medium">Plano</th>
                  <th className="px-3 py-2.5 font-medium">Teste até</th>
                  <th className="px-3 py-2.5 font-medium">Situação</th>
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
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </TableCard>
    </div>
  );
}
