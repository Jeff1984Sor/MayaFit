"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { BarChart3, CheckCircle2, Download, ListChecks, ShieldX, Trophy, Users } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CatracaPill, Indicador, MetodoTag, ResultadoPill } from "@/components/acesso/comum";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, baixar } from "@/lib/api";
import { dataHora, numero } from "@/lib/format";
import type { ListaRegistros, Metodo, Relatorio } from "@/lib/tipos-acesso";
import { ROTULO_METODO } from "@/lib/tipos-acesso";
import { cn } from "@/lib/utils";

const EIXO = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, axisLine: false, tickLine: false } as const;

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function diasAtras(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return iso(d);
}

export function Historico() {
  const [de, setDe] = useState(diasAtras(29));
  const [ate, setAte] = useState(iso(new Date()));
  return (
    <Tabs defaultValue="registros">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <TabsList>
          <TabsTrigger value="registros">
            <ListChecks /> Registros
          </TabsTrigger>
          <TabsTrigger value="relatorio">
            <BarChart3 /> Relatório do período
          </TabsTrigger>
        </TabsList>
        <div className="flex items-center gap-2 text-sm">
          <Input type="date" value={de} max={ate} onChange={(e) => setDe(e.target.value)} className="h-9 w-40" aria-label="De" />
          <span className="text-muted-foreground">até</span>
          <Input type="date" value={ate} min={de} onChange={(e) => setAte(e.target.value)} className="h-9 w-40" aria-label="Até" />
        </div>
      </div>
      <TabsContent value="registros" className="mt-4">
        <Registros de={de} ate={ate} />
      </TabsContent>
      <TabsContent value="relatorio" className="mt-4">
        <RelatorioPeriodo de={de} ate={ate} />
      </TabsContent>
    </Tabs>
  );
}

function Registros({ de, ate }: { de: string; ate: string }) {
  const [q, setQ] = useState("");
  const [resultado, setResultado] = useState<"todos" | "permitidos" | "negados">("todos");
  const [metodo, setMetodo] = useState<"" | Metodo>("");
  const [pagina, setPagina] = useState(1);
  const filtros = { de, ate, q, metodo: metodo || undefined, permitido: resultado === "todos" ? undefined : resultado === "permitidos" };
  const lista = useQuery({
    queryKey: ["acesso", "registros", filtros, pagina],
    queryFn: () => api.get<ListaRegistros>("/acesso/registros", { ...filtros, pagina, por_pagina: 25 }),
    placeholderData: keepPreviousData,
  });
  const mudar = <T,>(fn: (v: T) => void) => (v: T) => {
    fn(v);
    setPagina(1);
  };
  return (
    <TableCard>
      <Toolbar>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <SearchInput value={q} onChange={mudar(setQ)} placeholder="Aluno ou motivo" className="sm:w-64" />
          <Segmented
            value={resultado}
            onChange={mudar(setResultado)}
            opcoes={[
              { value: "todos", label: "Todos" },
              { value: "permitidos", label: "Liberados", tom: "success" },
              { value: "negados", label: "Negados", tom: "danger" },
            ]}
          />
          <NativeSelect value={metodo} onChange={(e) => mudar(setMetodo)(e.target.value as Metodo | "")} className="w-48">
            <option value="">Todos os métodos</option>
            {(Object.keys(ROTULO_METODO) as Metodo[]).map((m) => (
              <option key={m} value={m}>
                {ROTULO_METODO[m]}
              </option>
            ))}
          </NativeSelect>
        </div>
        <Button variant="outline" onClick={() => baixar("/acesso/registros.csv", { query: filtros }, "acessos.csv")}>
          <Download /> Exportar CSV
        </Button>
      </Toolbar>
      {lista.isLoading ? (
        <TableSkeleton colunas={6} />
      ) : !lista.data?.itens.length ? (
        <EmptyState icone={ListChecks} titulo="Nenhum acesso no período" descricao="Mude as datas ou os filtros. Os check-ins do totem e as liberações da recepção aparecem aqui." />
      ) : (
        <>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data e hora</TableHead>
                  <TableHead>Aluno</TableHead>
                  <TableHead>Resultado</TableHead>
                  <TableHead className="min-w-64">Motivo</TableHead>
                  <TableHead>Método</TableHead>
                  <TableHead>Onde</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lista.data.itens.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="whitespace-nowrap num">{dataHora(r.em)}</TableCell>
                    <TableCell className="font-medium">{r.aluno_nome ?? <span className="text-muted-foreground">Não identificado</span>}</TableCell>
                    <TableCell>
                      <div className="flex flex-col items-start gap-1">
                        <ResultadoPill r={r} />
                        {r.presenca_registrada && <span className="text-[11px] text-success-ink">presença na aula</span>}
                      </div>
                    </TableCell>
                    <TableCell className={cn("text-sm", !r.permitido && "text-danger-ink")}>
                      {r.motivo}
                      {r.aula_descricao && <div className="text-xs text-muted-foreground">{r.aula_descricao}</div>}
                    </TableCell>
                    <TableCell>
                      <MetodoTag metodo={r.metodo} />
                      {r.similaridade != null && <div className="text-[11px] text-muted-foreground num">semelhança {(r.similaridade * 100).toFixed(0)}%</div>}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {r.usuario_nome ? `Recepção: ${r.usuario_nome}` : (r.dispositivo_nome ?? "—")}
                      <div className="mt-1">
                        <CatracaPill status={r.catraca_status} detalhe={r.catraca_detalhe} />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <Pagination pagina={pagina} porPagina={25} total={lista.data.total} onChange={setPagina} />
        </>
      )}
    </TableCard>
  );
}

function RelatorioPeriodo({ de, ate }: { de: string; ate: string }) {
  const rel = useQuery({ queryKey: ["acesso", "relatorio", de, ate], queryFn: () => api.get<Relatorio>("/acesso/relatorio", { de, ate }), placeholderData: keepPreviousData });
  const r = rel.data;
  const maxHora = Math.max(1, ...(r?.por_hora.map((h) => h.total) ?? [1]));
  const pico = r?.por_hora.reduce((a, b) => (b.total > a.total ? b : a), { hora: -1, total: 0 });
  const taxa = r && r.total ? Math.round((100 * r.permitidos) / r.total) : 0;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador titulo="Entradas liberadas" valor={numero(r?.permitidos ?? 0)} icone={CheckCircle2} tom="success" carregando={!r} legenda={r ? `${taxa}% das tentativas` : undefined} />
        <Indicador titulo="Negadas" valor={numero(r?.negados ?? 0)} icone={ShieldX} tom="danger" carregando={!r} />
        <Indicador titulo="Alunos diferentes" valor={numero(r?.alunos_unicos ?? 0)} icone={Users} carregando={!r} />
        <Indicador
          titulo="Horário de pico"
          valor={pico && pico.hora >= 0 && pico.total ? `${String(pico.hora).padStart(2, "0")}h` : "—"}
          icone={BarChart3}
          tom="warning"
          carregando={!r}
          legenda={pico?.total ? `${numero(pico.total)} entradas nessa hora` : "sem entradas"}
        />
      </div>

      <section className="card-surface p-4 sm:p-5">
        <h2 className="mb-1 text-base font-semibold">Entradas por dia</h2>
        <p className="mb-4 text-xs text-muted-foreground">Liberadas e negadas em cada dia do período.</p>
        <div className="h-64" role="img" aria-label="Entradas por dia">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={r?.por_dia ?? []} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="dia" {...EIXO} tickFormatter={(d: string) => d.slice(8, 10) + "/" + d.slice(5, 7)} minTickGap={12} />
              <YAxis {...EIXO} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: "var(--accent)", opacity: 0.5 }}
                labelFormatter={(d) => String(d).split("-").reverse().join("/")}
                formatter={(v, n) => [numero(Number(v)), n === "permitidos" ? "Liberadas" : "Negadas"]}
              />
              <Bar dataKey="permitidos" stackId="a" fill="var(--success)" radius={[0, 0, 0, 0]} />
              <Bar dataKey="negados" stackId="a" fill="var(--danger)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card-surface p-4 sm:p-5">
          <h2 className="mb-1 text-base font-semibold">Mapa de calor dos horários</h2>
          <p className="mb-4 text-xs text-muted-foreground">Quanto mais forte, mais gente chegando naquela hora. Bom para planejar a recepção.</p>
          <div className="grid grid-cols-10 gap-1.5 sm:grid-cols-[repeat(19,minmax(0,1fr))]">
            {r?.por_hora.map((h) => (
              <div key={h.hora} className="flex flex-col items-center gap-1" title={`${h.hora}h: ${h.total} entradas`}>
                <div
                  className="h-12 w-full rounded-md ring-1 ring-border transition-colors"
                  style={{ background: h.total ? `color-mix(in oklab, var(--brand) ${Math.round(15 + (85 * h.total) / maxHora)}%, transparent)` : "var(--muted)" }}
                />
                <span className="text-[10px] text-muted-foreground num">{h.hora}h</span>
              </div>
            ))}
          </div>
          <div className="mt-6 space-y-2">
            <h3 className="text-sm font-semibold">Como entraram</h3>
            {r?.por_metodo.length ? (
              r.por_metodo.map((m) => (
                <div key={m.metodo} className="flex items-center gap-3 text-sm">
                  <MetodoTag metodo={m.metodo} className="w-44 shrink-0" />
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${(100 * m.total) / Math.max(1, r.permitidos)}%` }} />
                  </div>
                  <span className="w-10 text-right num">{numero(m.total)}</span>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Sem entradas no período.</p>
            )}
          </div>
        </section>

        <section className="card-surface p-4 sm:p-5">
          <h2 className="mb-3 text-base font-semibold">Por que negamos</h2>
          {r?.motivos_negacao.length ? (
            <ul className="space-y-2">
              {r.motivos_negacao.map((m) => (
                <li key={m.codigo} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
                  <span>{m.rotulo}</span>
                  <span className="font-semibold text-danger-ink num">{numero(m.total)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Nenhuma entrada negada no período. 🎉</p>
          )}
          <h2 className="mt-6 mb-3 flex items-center gap-2 text-base font-semibold">
            <Trophy className="size-4 text-warning" /> Mais frequentes
          </h2>
          {r?.mais_frequentes.length ? (
            <ol className="space-y-1.5">
              {r.mais_frequentes.map((a, i) => (
                <li key={a.aluno_id} className="flex items-center gap-3 text-sm">
                  <span className={cn("grid size-6 place-items-center rounded-full text-[11px] font-bold num", i < 3 ? "bg-warning/20 text-warning-ink" : "bg-muted text-muted-foreground")}>{i + 1}</span>
                  <span className="flex-1 truncate">{a.nome}</span>
                  <span className="text-xs text-muted-foreground num">{a.dias} dia(s)</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">Sem dados no período.</p>
          )}
        </section>
      </div>
    </div>
  );
}
