"use client";

import { useId } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { AulasMes } from "@/lib/tipos-painel";

const EIXO = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, axisLine: false, tickLine: false } as const;

/**
 * Barras de aulas (reservas não canceladas) por mês. O mês atual leva o degradê cheio da marca;
 * os anteriores ficam mais claros. A linha tracejada é a média do período.
 */
export function GraficoAulasPorMes({ meses }: { meses: AulasMes[] }) {
  const ultimo = meses.length - 1;
  const id = useId().replace(/:/g, "");
  const media = meses.length ? meses.reduce((s, m) => s + m.total, 0) / meses.length : 0;
  return (
    <div className="h-64" role="img" aria-label={`Aulas por mês: ${meses.map((m) => `${m.rotulo} ${m.total}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={meses} margin={{ top: 20, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id={`barra-${id}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--brand)" stopOpacity={1} />
              <stop offset="100%" stopColor="var(--navy)" stopOpacity={0.9} />
            </linearGradient>
            <linearGradient id={`barra-clara-${id}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.55} />
              <stop offset="100%" stopColor="var(--brand)" stopOpacity={0.2} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="rotulo" {...EIXO} />
          <YAxis {...EIXO} allowDecimals={false} width={44} />
          {media > 0 && (
            <ReferenceLine
              y={media}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              strokeOpacity={0.6}
              label={{ value: "média", position: "insideTopRight", fontSize: 10, fill: "var(--muted-foreground)" }}
            />
          )}
          <Tooltip
            cursor={{ fill: "var(--accent)", opacity: 0.5, radius: 8 }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as AulasMes | undefined;
              if (!active || !p) return null;
              return (
                <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
                  <p className="font-medium">{p.rotulo}</p>
                  <p className="text-muted-foreground">
                    <span className="font-medium text-foreground num">{p.total}</span> aula{p.total === 1 ? "" : "s"}
                  </p>
                </div>
              );
            }}
          />
          <Bar
            dataKey="total"
            radius={[8, 8, 0, 0]}
            maxBarSize={40}
            animationDuration={700}
            label={{ position: "top", fontSize: 11, fill: "var(--muted-foreground)" }}
            shape={(props: { x?: number; y?: number; width?: number; height?: number; index?: number }) => {
              const { x = 0, y = 0, width = 0, height = 0, index = 0 } = props;
              return (
                <rect
                  x={x}
                  y={y}
                  width={width}
                  height={Math.max(height, 0)}
                  rx={8}
                  fill={`url(#${index === ultimo ? "barra" : "barra-clara"}-${id})`}
                />
              );
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
