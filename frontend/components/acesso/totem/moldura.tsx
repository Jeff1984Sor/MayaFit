"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/utils";

export type EstadoMoldura = "ocioso" | "rosto" | "lendo" | "sucesso" | "negado";

const COR: Record<EstadoMoldura, string> = {
  ocioso: "rgba(255,255,255,0.35)",
  rosto: "rgba(124,143,255,0.9)",
  lendo: "rgba(124,143,255,1)",
  sucesso: "rgba(16,185,129,1)",
  negado: "rgba(245,166,35,1)",
};

/**
 * Câmera dentro de uma moldura oval com animações: anel pulsando no ocioso, linha de varredura enquanto lê,
 * anel verde/âmbar no resultado. O vídeo é espelhado (como selfie).
 */
export function MolduraCamera({
  videoRef,
  estado,
  progresso = 0,
  children,
  className,
}: {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  estado: EstadoMoldura;
  progresso?: number;
  children?: React.ReactNode;
  className?: string;
}) {
  const cor = COR[estado];
  return (
    <div className={cn("relative aspect-[3/4] w-[min(78vw,52vh)]", className)}>
      {/* halo */}
      <motion.div
        className="absolute -inset-6 rounded-[50%] blur-2xl"
        style={{ background: cor }}
        animate={{ opacity: estado === "ocioso" ? [0.08, 0.18, 0.08] : estado === "lendo" ? [0.25, 0.45, 0.25] : 0.3 }}
        transition={{ duration: estado === "lendo" ? 1 : 3, repeat: Infinity }}
      />
      <div className="absolute inset-0 overflow-hidden rounded-[50%] bg-black ring-1 ring-white/10">
        <video ref={videoRef} className="size-full -scale-x-100 object-cover" playsInline muted autoPlay />
        {estado === "lendo" && (
          <motion.div
            className="absolute inset-x-0 h-24 bg-gradient-to-b from-transparent via-indigo-400/45 to-transparent"
            initial={{ top: "-20%" }}
            animate={{ top: ["-20%", "100%"] }}
            transition={{ duration: 1.3, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
        {(estado === "sucesso" || estado === "negado") && (
          <motion.div
            className="absolute inset-0"
            style={{ background: estado === "sucesso" ? "rgba(16,185,129,0.25)" : "rgba(245,166,35,0.22)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          />
        )}
      </div>
      {/* anel com progresso */}
      <svg className="pointer-events-none absolute -inset-3 size-[calc(100%+1.5rem)]" viewBox="0 0 100 100" preserveAspectRatio="none">
        <ellipse cx="50" cy="50" rx="48.5" ry="48.5" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
        <motion.ellipse
          cx="50"
          cy="50"
          rx="48.5"
          ry="48.5"
          fill="none"
          stroke={cor}
          strokeWidth="4"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          style={{ rotate: -90, transformOrigin: "50% 50%" }}
          animate={{ pathLength: estado === "ocioso" ? 0.12 : estado === "sucesso" || estado === "negado" ? 1 : Math.max(0.12, progresso) }}
          transition={{ duration: 0.4 }}
        />
      </svg>
      {estado === "ocioso" && (
        <motion.div
          className="pointer-events-none absolute -inset-3 rounded-[50%] border-2 border-white/20"
          animate={{ scale: [1, 1.06, 1], opacity: [0.6, 0, 0.6] }}
          transition={{ duration: 2.4, repeat: Infinity }}
        />
      )}
      {children}
    </div>
  );
}
