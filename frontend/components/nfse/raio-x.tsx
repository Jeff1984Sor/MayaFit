"use client";

import { Loader2, ScanSearch } from "lucide-react";
import { motion } from "motion/react";

import { moeda } from "@/lib/format";
import type { RaioX } from "@/lib/tipos-nfse";
import { cn } from "@/lib/utils";

import { Achado, ModoPill } from "./comum";

function Medidor({ score }: { score: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const cor = score >= 90 ? "var(--success)" : score >= 60 ? "var(--warning)" : "var(--danger)";
  return (
    <div className="relative grid size-24 shrink-0 place-items-center">
      <svg viewBox="0 0 80 80" className="absolute inset-0 -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" stroke="var(--muted)" strokeWidth="7" />
        <motion.circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          stroke={cor}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c - (c * score) / 100 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </svg>
      <div className="text-center">
        <p className="text-2xl font-semibold num">{score}</p>
        <p className="-mt-1 text-[10px] tracking-wide text-muted-foreground uppercase">saúde</p>
      </div>
    </div>
  );
}

/** Painel do raio-x antes de emitir: nota de saúde, totais, ISS estimado e cada achado com a ação sugerida. */
export function PainelRaioX({ raio, carregando, className }: { raio?: RaioX; carregando?: boolean; className?: string }) {
  return (
    <div className={cn("card-surface p-4", className)}>
      <div className="mb-3 flex items-center gap-2">
        <ScanSearch className="size-4 text-info-ink" />
        <h3 className="text-sm font-semibold">Raio-x antes de emitir</h3>
        {carregando && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
        {raio && (
          <span className="ml-auto">
            <ModoPill modo={raio.modo} />
          </span>
        )}
      </div>
      {!raio ? (
        <p className="text-sm text-muted-foreground">Preencha os dados para o MayaFit conferir tudo antes de enviar.</p>
      ) : (
        <>
          <div className="flex items-center gap-4">
            <Medidor score={raio.score} />
            <div className="grid flex-1 grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Notas</p>
                <p className="font-semibold num">{raio.quantidade}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Valor total</p>
                <p className="font-semibold num">{moeda(raio.valor_total)}</p>
              </div>
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground">
                  ISS estimado {raio.iss_no_das ? "(já incluso no DAS)" : `(${raio.aliquota.replace(".", ",")}%)`}
                </p>
                <p className="font-semibold num">{moeda(raio.iss_estimado)}</p>
              </div>
            </div>
          </div>
          <p
            className={cn(
              "mt-3 rounded-lg px-3 py-2 text-sm font-medium",
              raio.pode_emitir ? "bg-success/10 text-success-ink" : "bg-danger/10 text-danger-ink",
            )}
          >
            {raio.frase}
          </p>
          <div className="mt-3 flex flex-col gap-2">
            {raio.achados.map((a, i) => (
              <Achado key={i} nivel={a.nivel} titulo={a.titulo} mensagem={a.mensagem} acao={a.acao} link={a.link} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
