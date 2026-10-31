"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { moeda, moedaCompacta, numero, toNum } from "@/lib/format";
import type { Cobranca, Estudio, Solicitacao } from "@/lib/tipos-admin";
import { cn } from "@/lib/utils";

const EIXO = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, axisLine: false, tickLine: false } as const;
const GRADE = { stroke: "var(--border)", strokeDasharray: "3 3" } as const;
const COR_FATURADO = "var(--brand)";
const COR_RECEBIDO = "var(--success)";
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** Últimos `n` meses como "AAAA-MM" (do mais antigo ao atual). */
export function ultimosMeses(n: number) {
  const hoje = new Date();
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(hoje.getFullYear(), hoje.getMonth() - (n - 1 - i), 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
}

const rotuloMes = (comp: string) => `${MESES[Number(comp.slice(5, 7)) - 1]}/${comp.slice(2, 4)}`;

export interface PontoReceita {
  mes: string;
  rotulo: string;
  faturado: number;
  recebido: number;
}

/** Faturado (pela competência ou vencimento) e recebido (pela data do pagamento) por mês. Canceladas ficam fora. */
export function receitaPorMes(cobrancas: Cobranca[], n = 12): PontoReceita[] {
  const meses = ultimosMeses(n);
  const pontos = new Map(meses.map((m) => [m, { mes: m, rotulo: rotuloMes(m), faturado: 0, recebido: 0 }]));
  for (const k of cobrancas) {
    if (k.status === "cancelada") continue;
    const comp = (k.competencia ?? k.vencimento).slice(0, 7);
    const pf = pontos.get(comp);
    if (pf) pf.faturado += toNum(k.valor);
    if (k.status === "paga" && k.pago_em) {
      const pr = pontos.get(k.pago_em.slice(0, 7));
      if (pr) pr.recebido += toNum(k.valor);
    }
  }
  return [...pontos.values()];
}

/** Estúdios novos por mês (pela data de criação). */
export function novosPorMes(estudios: Estudio[], n = 6) {
  const meses = ultimosMeses(n);
  const cont = new Map(meses.map((m) => [m, 0]));
  for (const e of estudios) {
    const m = e.criado_em?.slice(0, 7);
    if (m && cont.has(m)) cont.set(m, (cont.get(m) ?? 0) + 1);
  }
  return meses.map((m) => ({ mes: m, rotulo: rotuloMes(m), novos: cont.get(m) ?? 0 }));
}

export function Legenda({ itens }: { itens: { cor: string; rotulo: string }[] }) {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
      {itens.map((i) => (
        <span key={i.rotulo} className="flex items-center gap-1.5">
          <span className="size-2 rounded-full" style={{ background: i.cor }} />
          {i.rotulo}
        </span>
      ))}
    </div>
  );
}

export function GraficoReceita({ pontos }: { pontos: PontoReceita[] }) {
  return (
    <div>
      <Legenda
        itens={[
          { cor: COR_FATURADO, rotulo: "Faturado" },
          { cor: COR_RECEBIDO, rotulo: "Recebido" },
        ]}
      />
      <div className="mt-3 h-64" role="img" aria-label="Receita faturada e recebida por mês">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={pontos} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
            <CartesianGrid vertical={false} {...GRADE} />
            <XAxis dataKey="rotulo" {...EIXO} minTickGap={8} />
            <YAxis {...EIXO} width={60} tickFormatter={(v) => moedaCompacta(v)} />
            <Tooltip
              cursor={{ fill: "var(--accent)", opacity: 0.5 }}
              content={({ active, payload }) => {
                const p = payload?.[0]?.payload as PontoReceita | undefined;
                if (!active || !p) return null;
                return (
                  <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
                    <p className="mb-1 font-medium">{p.rotulo}</p>
                    <p className="flex justify-between gap-4">
                      <span className="text-muted-foreground">Faturado</span> <span className="num">{moeda(p.faturado)}</span>
                    </p>
                    <p className="flex justify-between gap-4">
                      <span className="text-muted-foreground">Recebido</span> <span className="num">{moeda(p.recebido)}</span>
                    </p>
                  </div>
                );
              }}
            />
            <Bar dataKey="faturado" fill={COR_FATURADO} maxBarSize={18} radius={[4, 4, 0, 0]} />
            <Bar dataKey="recebido" fill={COR_RECEBIDO} maxBarSize={18} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Mini barras de estúdios novos por mês. */
export function BarrasNovos({ pontos }: { pontos: { mes: string; rotulo: string; novos: number }[] }) {
  const max = Math.max(1, ...pontos.map((p) => p.novos));
  return (
    <div className="flex h-24 items-end gap-2" role="img" aria-label="Estúdios novos por mês">
      {pontos.map((p, i) => (
        <div key={p.mes} className="flex flex-1 flex-col items-center gap-1">
          <span className="num text-[11px] text-muted-foreground">{p.novos}</span>
          <div
            className={cn("w-full rounded-t-md", i === pontos.length - 1 ? "bg-brand" : "bg-brand/35")}
            style={{ height: `${Math.max(4, (p.novos / max) * 64)}px` }}
          />
          <span className="text-[10px] text-muted-foreground">{p.rotulo}</span>
        </div>
      ))}
    </div>
  );
}

/** Funil do cadastro pelo site: pedidos → aprovados → em teste ou ativos → pagando. */
export function FunilSolicitacoes({ solicitacoes, estudios }: { solicitacoes: Solicitacao[]; estudios: Estudio[] }) {
  const porId = new Map(estudios.map((e) => [e.id, e]));
  const aprovadas = solicitacoes.filter((s) => s.status === "aprovada");
  const vivos = aprovadas.filter((s) => {
    const e = s.cliente_id ? porId.get(s.cliente_id) : undefined;
    return e && e.status !== "inativo";
  });
  const pagando = aprovadas.filter((s) => (s.cliente_id ? porId.get(s.cliente_id)?.status === "ativo" : false));
  const etapas = [
    { rotulo: "Pedidos pelo site", n: solicitacoes.length },
    { rotulo: "Aprovados", n: aprovadas.length },
    { rotulo: "Usando (teste ou ativo)", n: vivos.length },
    { rotulo: "Pagando", n: pagando.length },
  ];
  const topo = Math.max(1, etapas[0].n);
  return (
    <div className="space-y-2.5">
      {etapas.map((et, i) => {
        const pct = (et.n / topo) * 100;
        const conv = i > 0 && etapas[i - 1].n ? Math.round((et.n / etapas[i - 1].n) * 100) : null;
        return (
          <div key={et.rotulo}>
            <div className="mb-1 flex justify-between text-xs">
              <span>{et.rotulo}</span>
              <span className="text-muted-foreground">
                <span className="num font-medium text-foreground">{numero(et.n)}</span>
                {conv != null && <span className="num"> · {conv}%</span>}
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-brand" style={{ width: `${Math.max(et.n ? 3 : 0, pct)}%`, opacity: 1 - i * 0.18 }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
