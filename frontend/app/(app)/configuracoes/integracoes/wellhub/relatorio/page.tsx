"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Download, HandCoins, Loader2, TicketCheck, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { KpiCard } from "@/components/mayacorp/kpi-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CabecalhoWellhub, Indicador, useTelaWellhub } from "@/components/wellhub/comum";
import { GraficoCheckins } from "@/components/wellhub/grafico-checkins";
import { api, baixar } from "@/lib/api";
import { data, moeda, numero } from "@/lib/format";
import type { Relatorio } from "@/lib/tipos-wellhub";

function mesAtual() {
  const h = new Date();
  return { ano: h.getFullYear(), mes: h.getMonth() + 1 };
}

export default function WellhubRelatorioPage() {
  const [ref, setRef] = useState(mesAtual);
  const [unidade, setUnidade] = useState("");
  const [baixando, setBaixando] = useState(false);
  const tela = useTelaWellhub();
  const configuradas = (tela.data?.configuracoes ?? []).filter((c) => c.configurada);
  const query = { ano: ref.ano, mes: ref.mes, unidade_id: unidade || undefined };
  const q = useQuery({
    queryKey: ["wellhub-relatorio", ref.ano, ref.mes, unidade],
    queryFn: () => api.get<Relatorio>("/wellhub/relatorio", query),
    placeholderData: keepPreviousData,
  });
  const r = q.data;
  const andar = (d: number) =>
    setRef(({ ano, mes }) => {
      const t = ano * 12 + (mes - 1) + d;
      return { ano: Math.floor(t / 12), mes: (t % 12) + 1 };
    });
  const rotulo = new Date(ref.ano, ref.mes - 1, 1).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  const exportar = async () => {
    setBaixando(true);
    try {
      await baixar("/wellhub/relatorio.csv", { query }, `wellhub-checkins-${ref.ano}-${String(ref.mes).padStart(2, "0")}.csv`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Não foi possível exportar.");
    } finally {
      setBaixando(false);
    }
  };

  return (
    <div className="space-y-6">
      <CabecalhoWellhub />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" aria-label="Mês anterior" onClick={() => andar(-1)}>
            <ChevronLeft />
          </Button>
          <p className="min-w-44 text-center font-semibold capitalize">{rotulo}</p>
          <Button variant="outline" size="icon" aria-label="Próximo mês" onClick={() => andar(1)}>
            <ChevronRight />
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {configuradas.length > 1 && (
            <NativeSelect value={unidade} onChange={(e) => setUnidade(e.target.value)} aria-label="Unidade" className="w-48">
              <option value="">Todas as unidades</option>
              {configuradas.map((c) => (
                <option key={c.unidade_id} value={c.unidade_id}>
                  {c.unidade_nome}
                </option>
              ))}
            </NativeSelect>
          )}
          <Button variant="outline" onClick={exportar} disabled={baixando || !r || r.total === 0}>
            {baixando ? <Loader2 className="animate-spin" /> : <Download />} Exportar CSV
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        Confira com o extrato de repasse do Wellhub. Só check-in <strong>validado</strong> conta; o valor é uma estimativa (valor por check-in × validados).
        O CSV traz o Gympass ID completo de cada visita para a conferência.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard titulo="Check-ins validados" valor={numero(r?.validados)} icone={TicketCheck} variacao={r?.variacao} carregando={q.isPending} indice={0} />
        <Indicador titulo="Repasse estimado" valor={moeda(r?.valor_estimado)} icone={HandCoins} carregando={q.isPending}
          rodape={r ? `${r.por_unidade.length} unidade(s)` : undefined} />
        <Indicador titulo="Aguardando validação" valor={numero(r?.pendentes)} icone={TicketCheck} carregando={q.isPending}
          rodape="Não entram no repasse até serem validados" />
        <Indicador titulo="Alunos distintos" valor={numero(r?.alunos_distintos)} icone={Users} carregando={q.isPending}
          rodape={r ? `${numero(r.total)} visita(s) no mês` : undefined} />
      </div>

      {q.isPending ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : !r || r.total === 0 ? (
        <div className="card-surface">
          <EmptyState icone={TicketCheck} titulo="Nenhum check-in neste mês" descricao="Escolha outro mês ou confira se o webhook do Wellhub está configurado." />
        </div>
      ) : (
        <>
          <section className="card-surface p-5">
            <h3 className="mb-2 text-sm font-semibold">Check-ins por dia</h3>
            <GraficoCheckins serie={r.por_dia} />
          </section>
          {r.por_unidade.length > 1 && (
            <section className="card-surface overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Unidade</th>
                    <th className="px-3 py-2.5 text-right font-medium">Visitas</th>
                    <th className="px-3 py-2.5 text-right font-medium">Validadas</th>
                    <th className="px-3 py-2.5 text-right font-medium">Valor unitário</th>
                    <th className="px-4 py-2.5 text-right font-medium">Estimado</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {r.por_unidade.map((u) => (
                    <tr key={u.unidade_id}>
                      <td className="px-4 py-2.5 font-medium">{u.unidade_nome}</td>
                      <td className="px-3 py-2.5 text-right num">{u.total}</td>
                      <td className="px-3 py-2.5 text-right num">{u.validados}</td>
                      <td className="px-3 py-2.5 text-right num">{u.valor_unitario ? moeda(u.valor_unitario) : "—"}</td>
                      <td className="px-4 py-2.5 text-right font-medium num">{moeda(u.valor_estimado)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          <section className="card-surface overflow-x-auto">
            <div className="border-b px-4 py-3">
              <h3 className="text-sm font-semibold">Por aluno</h3>
            </div>
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Aluno</th>
                  <th className="hidden px-3 py-2.5 font-medium sm:table-cell">Gympass ID</th>
                  <th className="px-3 py-2.5 text-right font-medium">Visitas</th>
                  <th className="px-3 py-2.5 text-right font-medium">Validadas</th>
                  <th className="px-4 py-2.5 text-right font-medium">Última</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {r.por_aluno.map((a) => (
                  <tr key={`${a.aluno_id}-${a.gympass_id}`}>
                    <td className="px-4 py-2.5 font-medium">{a.aluno_nome}</td>
                    <td className="hidden px-3 py-2.5 font-mono text-xs text-muted-foreground sm:table-cell">{a.gympass_id}</td>
                    <td className="px-3 py-2.5 text-right num">{a.total}</td>
                    <td className="px-3 py-2.5 text-right num">{a.validados}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">{data(a.ultimo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
