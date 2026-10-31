"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { moeda, moedaCompacta, toNum } from "@/lib/format";
import type { PainelNfse } from "@/lib/tipos-nfse";

import { mesExtenso } from "./comum";

const EIXO = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, axisLine: false, tickLine: false } as const;

/** Valor emitido por mês (últimos 6 meses), com ISS no tooltip. */
export function GraficoNotas({ serie }: { serie: PainelNfse["serie"] }) {
  const pontos = serie.map((s) => ({ rotulo: mesExtenso(s.mes), valor: toNum(s.valor), iss: toNum(s.iss), qtd: s.quantidade }));
  return (
    <div className="h-52" role="img" aria-label="Valor das notas emitidas nos últimos seis meses">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={pontos} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="rotulo" {...EIXO} />
          <YAxis {...EIXO} width={56} tickFormatter={(v) => moedaCompacta(v)} />
          <Tooltip
            cursor={{ fill: "var(--accent)", opacity: 0.5 }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as (typeof pontos)[number] | undefined;
              if (!active || !p) return null;
              return (
                <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
                  <p className="mb-1 font-medium capitalize">{p.rotulo}</p>
                  <p>
                    <span className="text-muted-foreground">Emitido </span>
                    <span className="font-medium num">{moeda(p.valor)}</span>
                  </p>
                  <p>
                    <span className="text-muted-foreground">ISS estimado </span>
                    <span className="font-medium num">{moeda(p.iss)}</span>
                  </p>
                  <p className="text-muted-foreground">
                    <span className="num">{p.qtd}</span> nota(s)
                  </p>
                </div>
              );
            }}
          />
          <Bar dataKey="valor" fill="var(--brand)" maxBarSize={34} radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
