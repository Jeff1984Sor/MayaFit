"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BarChart3, CircleAlert, Info, LayoutDashboard, ListChecks, Wand2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { Pill } from "@/components/mayacorp/status-badge";
import { api } from "@/lib/api";
import type { Alerta, ResultadoEvento, WellhubConfig, WellhubTela } from "@/lib/tipos-wellhub";
import { cn } from "@/lib/utils";

export const RAIZ = "/configuracoes/integracoes/wellhub";

type Tom = "success" | "warning" | "danger" | "info" | "neutral";

export const ROTULO_RESULTADO: Record<ResultadoEvento, [string, Tom]> = {
  processado: ["Processado", "success"],
  cancelado: ["Cancelado", "info"],
  rejeitado: ["Recusado (lotada)", "warning"],
  descartado: ["Descartado", "neutral"],
  erro: ["Erro", "danger"],
  pendente: ["Pendente", "warning"],
};

export function PillResultado({ resultado, ignorado }: { resultado: ResultadoEvento; ignorado?: boolean }) {
  const [rot, tom] = ROTULO_RESULTADO[resultado] ?? [resultado, "neutral"];
  return <Pill tom={ignorado ? "neutral" : tom}>{ignorado ? "Erro conferido" : rot}</Pill>;
}

const ABAS = [
  { href: RAIZ, label: "Painel", icone: LayoutDashboard },
  { href: `${RAIZ}/configurar`, label: "Assistente", icone: Wand2 },
  { href: `${RAIZ}/eventos`, label: "Eventos", icone: ListChecks },
  { href: `${RAIZ}/relatorio`, label: "Relatório de repasse", icone: BarChart3 },
];

export function useTelaWellhub() {
  return useQuery({ queryKey: ["wellhub-tela"], queryFn: () => api.get<WellhubTela>("/wellhub") });
}

const CHAVE_UNIDADE = "wellhub-unidade";

/** Unidade escolhida (lembrada entre as telas do Wellhub). */
export function useUnidadeWellhub(configs: WellhubConfig[]) {
  const [escolhida, setEscolhida] = useState<number | null>(null);
  useEffect(() => {
    try {
      const salvo = Number(window.localStorage.getItem(CHAVE_UNIDADE));
      // eslint-disable-next-line react-hooks/set-state-in-effect -- lê a preferência salva só no cliente
      if (salvo) setEscolhida(salvo);
    } catch {
      /* sem armazenamento local */
    }
  }, []);
  const atual = configs.find((c) => c.unidade_id === escolhida) ?? configs[0];
  const escolher = (id: number) => {
    setEscolhida(id);
    try {
      window.localStorage.setItem(CHAVE_UNIDADE, String(id));
    } catch {
      /* sem armazenamento local */
    }
  };
  return { atual, escolher };
}

export function SeletorUnidade({ configs, atual, onChange }: { configs: WellhubConfig[]; atual?: WellhubConfig; onChange: (id: number) => void }) {
  if (configs.length < 2 || !atual) return null;
  return (
    <Field label="Unidade" className="w-full max-w-xs">
      <NativeSelect value={atual.unidade_id} onChange={(e) => onChange(Number(e.target.value))}>
        {configs.map((c) => (
          <option key={c.unidade_id} value={c.unidade_id}>
            {c.unidade_nome}
            {c.configurada ? (c.ativo ? "" : " (desligada)") : " (não configurada)"}
          </option>
        ))}
      </NativeSelect>
    </Field>
  );
}

export function CabecalhoWellhub({ extra }: { extra?: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <span className="grid size-7 place-items-center rounded-lg bg-[#D8FF3D] text-xs font-black text-[#0F1729]" aria-hidden>
              W
            </span>
            Wellhub
          </h2>
          <p className="text-sm text-muted-foreground">
            Reservas e check-ins dos alunos do Wellhub (antigo Gympass), grade publicada e conferência do repasse.
          </p>
        </div>
        {extra}
      </div>
      <nav className="-mx-1 flex gap-1 overflow-x-auto px-1" aria-label="Seções do Wellhub">
        {ABAS.map((a) => {
          const on = a.href === RAIZ ? pathname === RAIZ : pathname.startsWith(a.href);
          return (
            <Link
              key={a.href}
              href={a.href}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                on ? "bg-brand/12 text-foreground ring-1 ring-brand/25" : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <a.icone className="size-4" />
              {a.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

/** Cartão de indicador com rodapé livre (o KpiCard do core só mostra variação contra o mês anterior). */
export function Indicador({
  titulo,
  valor,
  icone: Icone,
  rodape,
  tom,
  carregando,
}: {
  titulo: string;
  valor: React.ReactNode;
  icone: React.ComponentType<{ className?: string }>;
  rodape?: React.ReactNode;
  tom?: "danger";
  carregando?: boolean;
}) {
  return (
    <div className="group card-surface relative overflow-hidden p-4">
      <div className="pointer-events-none absolute -top-10 -right-10 size-28 rounded-full bg-brand/10 blur-2xl md:opacity-60" />
      <div className="relative flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-muted-foreground">{titulo}</p>
        <div className={cn("grid size-8 place-items-center rounded-lg", tom === "danger" ? "bg-danger/10 text-danger-ink" : "bg-brand/10 text-navy dark:text-brand")}>
          <Icone className="size-4" />
        </div>
      </div>
      {carregando ? (
        <div className="mt-3 h-8 w-28 animate-pulse rounded-md bg-muted" />
      ) : (
        <p className={cn("relative mt-2 truncate text-[22px] leading-tight font-semibold tracking-tight num sm:text-[26px]", tom === "danger" && "text-danger-ink")}>{valor}</p>
      )}
      {rodape && <p className="relative mt-2 text-xs text-muted-foreground">{rodape}</p>}
    </div>
  );
}

const ESTILO_ALERTA = {
  danger: { icone: CircleAlert, classe: "border-danger/30 bg-danger/8 text-danger-ink" },
  warning: { icone: AlertTriangle, classe: "border-warning/30 bg-warning/10 text-warning-ink" },
  info: { icone: Info, classe: "border-info/30 bg-info/8 text-info-ink" },
} as const;

const DESTINO: Record<string, { href: string; rotulo: string }> = {
  eventos: { href: `${RAIZ}/eventos?resultado=erro`, rotulo: "Ver eventos" },
  assistente: { href: `${RAIZ}/configurar`, rotulo: "Abrir assistente" },
  relatorio: { href: `${RAIZ}/relatorio`, rotulo: "Ver relatório" },
};

export function ListaAlertas({ alertas }: { alertas: Alerta[] }) {
  if (alertas.length === 0) return null;
  return (
    <div className="space-y-2" role="status" aria-live="polite">
      {alertas.map((a, i) => {
        const e = ESTILO_ALERTA[a.nivel];
        const destino = a.acao ? DESTINO[a.acao] : null;
        return (
          <div key={i} className={cn("flex flex-wrap items-start gap-3 rounded-xl border px-3.5 py-3", e.classe)}>
            <e.icone className="mt-0.5 size-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{a.titulo}</p>
              <p className="text-xs opacity-90">{a.descricao}</p>
            </div>
            {destino && (
              <Link href={destino.href} className="shrink-0 text-xs font-medium underline underline-offset-2">
                {destino.rotulo}
              </Link>
            )}
          </div>
        );
      })}
    </div>
  );
}
