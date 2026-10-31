"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChartColumn, Lightbulb, Target, Timer, Trophy, TriangleAlert, UsersRound } from "lucide-react";
import { useState } from "react";

import { CrmNav, ICONE_ORIGEM } from "@/components/crm/comum";
import { Indicador } from "@/components/crm/indicadores";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { moeda, numero } from "@/lib/format";
import type { RelatorioCrm } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function diasAtras(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return iso(d);
}
const PRESETS = [
  { id: "30", rotulo: "30 dias", de: () => diasAtras(29) },
  { id: "90", rotulo: "90 dias", de: () => diasAtras(89) },
  { id: "ano", rotulo: "Este ano", de: () => `${new Date().getFullYear()}-01-01` },
  { id: "12m", rotulo: "12 meses", de: () => diasAtras(364) },
];

export default function RelatorioCrmPage() {
  const { pode } = useAuth();
  const [de, setDe] = useState(() => diasAtras(89));
  const [ate, setAte] = useState(() => iso(new Date()));
  const q = useQuery({
    queryKey: ["crm", "relatorio", de, ate],
    queryFn: () => api.get<RelatorioCrm>("/crm/relatorio", { de, ate }),
    placeholderData: keepPreviousData,
    enabled: pode("crm.ver") && !!de && !!ate,
  });
  if (!pode("crm.ver")) return <SemAcesso titulo="Relatório de vendas" />;
  const r = q.data;
  const maxMotivo = Math.max(1, ...(r?.perdidos_por_motivo.map((m) => m.quantidade) ?? [1]));

  return (
    <div>
      <PageHeader
        icone={ChartColumn}
        titulo="Relatório de vendas"
        descricao="Conversão e origem dos leads que entraram no período. Perdas pelo período em que foram perdidos."
      />
      <CrmNav />

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                setDe(p.de());
                setAte(iso(new Date()));
              }}
              className={cn(
                "h-8 rounded-full border px-3 text-sm transition-colors",
                de === p.de() && ate === iso(new Date()) ? "border-brand bg-brand/10 font-medium" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {p.rotulo}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Input type="date" value={de} max={ate} onChange={(e) => setDe(e.target.value)} className="w-40" aria-label="De" />
          <span className="text-muted-foreground">até</span>
          <Input type="date" value={ate} min={de} onChange={(e) => setAte(e.target.value)} className="w-40" aria-label="Até" />
        </div>
      </div>

      {q.isPending || !r ? (
        <div className="grid gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
        </div>
      ) : r.total_leads === 0 && r.perdidos_por_motivo.length === 0 ? (
        <div className="card-surface">
          <EmptyState icone={Target} titulo="Nenhum lead neste período" descricao="Escolha um período maior ou cadastre leads no funil para ver a conversão." />
        </div>
      ) : (
        <div className={cn("space-y-4 transition-opacity", q.isFetching && "opacity-70")}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Indicador titulo="Leads no período" icone={UsersRound} valor={numero(r.total_leads)} sub={`${r.abertos} ainda em aberto`} />
            <Indicador titulo="Matrículas" icone={Trophy} tom="success" valor={numero(r.ganhos)} sub={`${moeda(r.valor_ganho)}/mês estimado`} />
            <Indicador titulo="Taxa de conversão" icone={Target} valor={`${r.taxa_conversao.toLocaleString("pt-BR")}%`} sub={`${r.perdidos} perdido(s)`} />
            <Indicador
              titulo="Tempo até matricular"
              icone={Timer}
              valor={r.tempo_medio_dias == null ? "—" : `${r.tempo_medio_dias.toLocaleString("pt-BR")} dias`}
              sub="média do 1º contato à matrícula"
            />
          </div>

          {(r.melhor_origem || r.gargalo) && (
            <div className="grid gap-3 md:grid-cols-2">
              {r.melhor_origem && (
                <div className="flex items-start gap-2 rounded-2xl border border-success/30 bg-success/8 p-3 text-sm">
                  <Lightbulb className="mt-0.5 size-4 shrink-0 text-success-ink" />
                  <span>
                    <strong>Seu melhor canal:</strong> {r.melhor_origem} Vale investir mais nele.
                  </span>
                </div>
              )}
              {r.gargalo && (
                <div className="flex items-start gap-2 rounded-2xl border border-warning/40 bg-warning/8 p-3 text-sm">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning-ink" />
                  <span>
                    <strong>Gargalo:</strong> {r.gargalo}
                  </span>
                </div>
              )}
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="card-surface p-5">
              <h2 className="mb-4 text-sm font-semibold">Conversão por etapa</h2>
              <ol className="space-y-2.5">
                {r.funil.map((e, i) => (
                  <li key={e.etapa_id}>
                    {i > 0 && (
                      <p className="mb-1 pl-1 text-[11px] text-muted-foreground">
                        ↓ {e.pct_anterior.toLocaleString("pt-BR")}% avançam
                      </p>
                    )}
                    <div className="flex items-center gap-3">
                      <div className="relative h-9 flex-1 overflow-hidden rounded-lg bg-muted">
                        <div
                          className="absolute inset-y-0 left-0 rounded-lg transition-all duration-700"
                          style={{ width: `${Math.max(e.pct_total, 2)}%`, background: e.cor, opacity: 0.85 }}
                        />
                        <span className="relative z-10 flex h-full items-center px-3 text-sm font-medium mix-blend-normal">{e.etapa}</span>
                      </div>
                      <span className="w-20 text-right text-sm num">
                        <strong>{e.quantidade}</strong> <span className="text-muted-foreground">({e.pct_total.toLocaleString("pt-BR")}%)</span>
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
            </section>

            <section className="card-surface p-5">
              <h2 className="mb-4 text-sm font-semibold">Leads perdidos por motivo</h2>
              {r.perdidos_por_motivo.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhuma perda no período.</p>
              ) : (
                <ul className="space-y-3">
                  {r.perdidos_por_motivo.map((m) => (
                    <li key={m.motivo_id ?? "sem"}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>{m.motivo}</span>
                        <span className="num text-muted-foreground">
                          {m.quantidade} · {m.pct.toLocaleString("pt-BR")}%
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-danger/70" style={{ width: `${(m.quantidade / maxMotivo) * 100}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <section className="card-surface overflow-hidden">
            <h2 className="px-5 pt-5 pb-3 text-sm font-semibold">Por origem</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-y bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-5 py-2 font-medium">Origem</th>
                    <th className="px-3 py-2 text-right font-medium">Leads</th>
                    <th className="px-3 py-2 text-right font-medium">Matrículas</th>
                    <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">Perdidos</th>
                    <th className="px-3 py-2 font-medium">Conversão</th>
                    <th className="hidden px-3 py-2 text-right font-medium md:table-cell">Tempo médio</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {r.por_origem.map((o) => {
                    const Icone = ICONE_ORIGEM[o.origem];
                    return (
                      <tr key={o.origem}>
                        <td className="px-5 py-2.5">
                          <span className="inline-flex items-center gap-2">
                            <Icone className="size-4 text-muted-foreground" /> {o.rotulo}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-right num">{o.total}</td>
                        <td className="px-3 py-2.5 text-right num">{o.ganhos}</td>
                        <td className="hidden px-3 py-2.5 text-right num sm:table-cell">{o.perdidos}</td>
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                              <div className="h-full rounded-full bg-success" style={{ width: `${o.taxa_conversao}%` }} />
                            </div>
                            <span className="num text-xs">{o.taxa_conversao.toLocaleString("pt-BR")}%</span>
                          </div>
                        </td>
                        <td className="hidden px-3 py-2.5 text-right text-muted-foreground md:table-cell">
                          {o.tempo_medio_dias == null ? "—" : `${o.tempo_medio_dias.toLocaleString("pt-BR")} d`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
