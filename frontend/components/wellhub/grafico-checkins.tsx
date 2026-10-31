"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { PontoSerie } from "@/lib/tipos-wellhub";

const EIXO = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, axisLine: false, tickLine: false } as const;

/** Check-ins por dia: barra cheia = validados (entram no repasse); clara = pendentes de validação. */
export function GraficoCheckins({ serie }: { serie: PontoSerie[] }) {
  const dados = serie.map((p) => ({ ...p, rotulo: p.dia.slice(8, 10), pendentes: p.total - p.validados }));
  const resumo = dados.map((d) => `dia ${d.rotulo}: ${d.validados} validados, ${d.pendentes} pendentes`).join("; ");
  return (
    <div className="h-56" role="img" aria-label={`Check-ins por dia. ${resumo}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={dados} margin={{ top: 12, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="rotulo" {...EIXO} interval="preserveStartEnd" />
          <YAxis {...EIXO} allowDecimals={false} width={40} />
          <Tooltip
            cursor={{ fill: "var(--accent)", opacity: 0.5 }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as (typeof dados)[number] | undefined;
              if (!active || !p) return null;
              return (
                <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
                  <p className="font-medium">{p.dia.split("-").reverse().join("/")}</p>
                  <p className="text-muted-foreground">
                    <span className="font-medium text-foreground num">{p.validados}</span> validado(s) ·{" "}
                    <span className="font-medium text-foreground num">{p.pendentes}</span> pendente(s)
                  </p>
                </div>
              );
            }}
          />
          <Bar dataKey="validados" stackId="c" fill="var(--brand)" maxBarSize={22} />
          <Bar dataKey="pendentes" stackId="c" fill="var(--brand)" fillOpacity={0.3} radius={[5, 5, 0, 0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
