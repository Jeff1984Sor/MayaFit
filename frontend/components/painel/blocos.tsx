"use client";

import { AlertTriangle, ArrowDownRight, ArrowUpRight, Cake, Check, ChevronRight, Circle, Info, Minus, PartyPopper } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useId } from "react";

import { AnimatedNumber } from "@/components/mayacorp/animated-number";
import { UserAvatar } from "@/components/mayacorp/user-avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { data, moeda, percentual } from "@/lib/format";
import type { AlertaPainel, Aniversariante, PassoInicial } from "@/lib/tipos-painel";
import { cn } from "@/lib/utils";

type Icone = React.ComponentType<{ className?: string }>;

/** Minigráfico de tendência (área + linha) na cor da marca. Puramente decorativo: o número ao lado é o dado. */
export function Sparkline({ valores, className, perigo }: { valores: number[]; className?: string; perigo?: boolean }) {
  const id = useId();
  if (valores.length < 2) return null;
  const w = 120;
  const h = 36;
  const max = Math.max(...valores, 1);
  const min = Math.min(...valores, 0);
  const passo = w / (valores.length - 1);
  const y = (v: number) => h - 3 - ((v - min) / (max - min || 1)) * (h - 6);
  const pontos = valores.map((v, i) => `${(i * passo).toFixed(1)},${y(v).toFixed(1)}`);
  const linha = `M${pontos.join(" L")}`;
  const area = `${linha} L${w},${h} L0,${h} Z`;
  const cor = perigo ? "var(--danger)" : "var(--brand)";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={cn("h-9 w-full", className)} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={cor} stopOpacity={0.35} />
          <stop offset="100%" stopColor={cor} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={linha} fill="none" stroke={cor} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      <circle cx={w} cy={y(valores.at(-1) ?? 0)} r={2.6} fill={cor} />
    </svg>
  );
}

/** KPI clicável: o cartão inteiro leva à tela filtrada. Número animado, tendência opcional e entrada escalonada. */
export function KpiPainel({
  titulo,
  valor,
  rodape,
  icone: Icone,
  href,
  tom = "neutro",
  carregando,
  indice = 0,
  animar,
  serie,
}: {
  titulo: string;
  valor: React.ReactNode;
  rodape?: React.ReactNode;
  icone: Icone;
  href?: string | null;
  tom?: "neutro" | "perigo";
  carregando?: boolean;
  /** Posição na grade (escalona a animação de entrada). */
  indice?: number;
  /** Quando informado, o número "conta" até o valor (usa `formato` para exibir). */
  animar?: { valor: number; formato: (n: number) => string };
  /** Série para o minigráfico de tendência (mais antiga → mais recente). */
  serie?: number[];
}) {
  const perigo = tom === "perigo";
  const corpo = (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: indice * 0.05, duration: 0.35, ease: "easeOut" }}
      className={cn("group card-surface relative h-full overflow-hidden p-4", href && !carregando && "card-hover")}
    >
      {/* filete de cor no topo */}
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-0.5 bg-linear-to-r opacity-70 transition-opacity group-hover:opacity-100",
          perigo ? "from-danger via-danger/60 to-transparent" : "from-brand via-brand/50 to-transparent",
        )}
      />
      <div className="pointer-events-none absolute -top-10 -right-10 size-28 rounded-full bg-brand/10 blur-2xl transition-opacity group-hover:opacity-100 md:opacity-60" />
      <div className="relative flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-muted-foreground">{titulo}</p>
        <div
          className={cn(
            "grid size-9 place-items-center rounded-xl transition-transform duration-200 group-hover:scale-105",
            perigo ? "bg-danger/10 text-danger-ink" : "bg-brand/12 text-navy ring-1 ring-brand/20 dark:text-brand",
          )}
        >
          <Icone className="size-4" />
        </div>
      </div>
      {carregando ? (
        <>
          <Skeleton className="mt-3 h-8 w-24" />
          <Skeleton className="mt-3 h-4 w-32" />
        </>
      ) : (
        <>
          <div className="relative mt-1.5 flex items-end justify-between gap-3">
            <p className={cn("min-w-0 truncate text-[22px] leading-tight font-semibold tracking-tight num sm:text-[26px]", perigo && "text-danger-ink")}>
              {animar ? <AnimatedNumber value={animar.valor} format={animar.formato} /> : valor}
            </p>
            {serie && <Sparkline valores={serie} perigo={perigo} className="mb-1 w-24 shrink-0" />}
          </div>
          {rodape && (
            <div className="relative mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
              <span className="min-w-0">{rodape}</span>
              {href && <ChevronRight className="size-3.5 shrink-0 -translate-x-1 opacity-0 transition group-hover:translate-x-0 group-hover:opacity-100" />}
            </div>
          )}
        </>
      )}
    </motion.div>
  );
  return href && !carregando ? (
    <Link href={href} className="block rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`${titulo}: ver detalhes`}>
      {corpo}
    </Link>
  ) : (
    corpo
  );
}

/** Cartão de seção com título e (opcional) ação à direita. */
export function Secao({
  titulo,
  descricao,
  acao,
  icone: IconeSecao,
  children,
  className,
}: {
  titulo: string;
  descricao?: string;
  acao?: React.ReactNode;
  /** Ícone ao lado do título. */
  icone?: Icone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut", delay: 0.1 }}
      className={cn("card-surface p-5", className)}
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          {IconeSecao && (
            <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand/10 text-navy dark:text-brand">
              <IconeSecao className="size-4" />
            </div>
          )}
          <div className="min-w-0">
            <h2 className="text-sm font-semibold">{titulo}</h2>
            {descricao && <p className="mt-0.5 text-xs text-muted-foreground">{descricao}</p>}
          </div>
        </div>
        {acao}
      </div>
      {children}
    </motion.section>
  );
}

/** Vazio ilustrado compacto (para dentro de cartões). */
export function Vazio({ icone: Icone, texto, dica }: { icone: Icone; texto: string; dica?: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-4 py-8 text-center">
      <div className="relative mb-2 h-14 w-20">
        <div className="absolute inset-0 rounded-full bg-brand/15 blur-xl" />
        <div className="absolute top-2 left-1 h-10 w-12 -rotate-8 rounded-lg border bg-card/80" />
        <div className="absolute top-1 right-1 h-10 w-12 rotate-6 rounded-lg border bg-card/80" />
        <div className="absolute inset-x-3 top-0 grid h-12 place-items-center rounded-xl border bg-card shadow-sm">
          <Icone className="size-5 text-navy dark:text-brand" />
        </div>
      </div>
      <p className="text-sm font-medium">{texto}</p>
      {dica && <p className="max-w-xs text-xs text-muted-foreground">{dica}</p>}
    </div>
  );
}

export function LinhasEsqueleto({ n = 4 }: { n?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="size-8 shrink-0 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5" style={{ width: `${70 - ((i * 13) % 30)}%` }} />
            <Skeleton className="h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

const ROTULO_STATUS: Record<string, { rotulo: string; classe: string }> = {
  RESERVADA: { rotulo: "Reservada", classe: "bg-brand/10 text-navy ring-brand/25 dark:text-brand" },
  PENDENTE: { rotulo: "Pendente", classe: "bg-warning/15 text-warning-ink ring-warning/30" },
};

export function SeloStatusAula({ status }: { status: string }) {
  const s = ROTULO_STATUS[status] ?? { rotulo: status, classe: "bg-muted text-muted-foreground ring-border" };
  return <span className={cn("rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset", s.classe)}>{s.rotulo}</span>;
}

export function VariacaoRecebido({ pct, base }: { pct: number | null; base: string | null }) {
  if (pct == null) return <span>sem base de comparação no mês anterior</span>;
  const Seta = pct === 0 ? Minus : pct > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span
        className={cn(
          "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 font-medium",
          pct === 0 && "bg-muted text-muted-foreground",
          pct > 0 && "bg-success/10 text-success-ink",
          pct < 0 && "bg-danger/10 text-danger-ink",
        )}
      >
        <Seta className="size-3" />
        {percentual(pct)}
      </span>
      <span>vs. mesmo período do mês anterior ({moeda(base)})</span>
    </span>
  );
}

const ESTILO_ALERTA = {
  critico: { Icone: AlertTriangle, classe: "bg-danger/10 text-danger-ink", barra: "bg-danger" },
  aviso: { Icone: AlertTriangle, classe: "bg-warning/15 text-warning-ink", barra: "bg-warning" },
  info: { Icone: Info, classe: "bg-muted text-muted-foreground", barra: "bg-brand/50" },
} as const;

export function ItemAlerta({ a }: { a: AlertaPainel }) {
  const { Icone, classe, barra } = ESTILO_ALERTA[a.gravidade] ?? ESTILO_ALERTA.info;
  const conteudo = (
    <div className="group relative flex items-start gap-3 overflow-hidden rounded-xl border p-3 pl-4 transition-colors hover:bg-accent/40">
      <span className={cn("absolute inset-y-0 left-0 w-1", barra)} aria-hidden />
      <div className={cn("grid size-8 shrink-0 place-items-center rounded-lg", classe)}>
        <Icone className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {a.titulo}
          {a.chave !== "whatsapp_automatico_desligado" && (
            <span className="ml-1.5 rounded-md bg-muted px-1.5 py-0.5 text-xs num">
              {a.quantidade}
              {a.valor ? ` · ${moeda(a.valor)}` : ""}
            </span>
          )}
        </p>
        {a.detalhe && <p className="mt-0.5 text-xs text-muted-foreground">{a.detalhe}</p>}
      </div>
      {a.href && (
        <ChevronRight className="mt-1.5 size-4 shrink-0 text-muted-foreground opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
      )}
    </div>
  );
  return a.href ? (
    <Link href={a.href} className="block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {conteudo}
    </Link>
  ) : (
    conteudo
  );
}

function comemorar() {
  import("canvas-confetti")
    .then((m) =>
      m.default({
        particleCount: 90,
        spread: 70,
        origin: { y: 0.7 },
        colors: ["#1E2D6B", "#7C8FFF", "#1A8F5E", "#F5A623"],
        disableForReducedMotion: true,
      }),
    )
    .catch(() => {});
}

export function LinhaAniversariante({ a }: { a: Aniversariante }) {
  const dia = data(a.dia).slice(0, 5);
  return (
    <li
      className={cn(
        "flex items-center gap-3 py-2",
        a.hoje && "-mx-2 rounded-xl bg-linear-to-r from-amber-maya/15 via-brand/8 to-transparent px-2",
      )}
    >
      <UserAvatar nome={a.nome} className={cn("size-8", a.hoje && "ring-2 ring-amber-maya/60")} textoClassName="text-[11px]" />
      <div className="min-w-0 flex-1">
        <Link href={`/alunos/${a.aluno_id}`} className="block truncate text-sm font-medium hover:underline">
          {a.nome}
        </Link>
        <span className="block text-xs text-muted-foreground">
          {a.hoje ? <strong className="text-navy dark:text-brand">Hoje</strong> : dia} · {a.idade} anos
        </span>
      </div>
      {a.hoje && (
        <button
          type="button"
          onClick={comemorar}
          className="grid size-8 shrink-0 place-items-center rounded-lg text-warning-ink transition hover:scale-110 hover:bg-amber-maya/15"
          aria-label={`Comemorar o aniversário de ${a.nome}`}
          title="Comemorar"
        >
          <PartyPopper className="size-4" />
        </button>
      )}
      {!a.hoje && <Cake className="size-3.5 shrink-0 text-muted-foreground/60" aria-hidden />}
    </li>
  );
}

export function ListaPassos({ passos }: { passos: PassoInicial[] }) {
  const feitos = passos.filter((p) => p.feito).length;
  const pct = passos.length ? Math.round((feitos / passos.length) * 100) : 0;
  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Progresso dos primeiros passos">
          <motion.div className="h-full rounded-full brand-gradient" initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8, ease: "easeOut" }} />
        </div>
        <span className="shrink-0 text-xs font-medium text-muted-foreground num">
          {feitos}/{passos.length}
        </span>
      </div>
      <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {passos.map((p, i) => (
          <li key={p.chave}>
            <Link
              href={p.href}
              className={cn("card-hover flex h-full items-start gap-3 rounded-xl border bg-card p-3 hover:bg-accent/40", p.feito && "opacity-70")}
            >
              <span
                className={cn(
                  "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold",
                  p.feito ? "bg-success/15 text-success-ink" : "bg-brand/10 text-navy dark:text-brand",
                )}
                aria-label={p.feito ? "feito" : "pendente"}
              >
                {p.feito ? <Check className="size-3.5" /> : p.conta ? i + 1 : <Circle className="size-3" />}
              </span>
              <span className="min-w-0">
                <span className={cn("block text-sm font-medium", p.feito && "line-through")}>{p.titulo}</span>
                <span className="block text-xs text-muted-foreground">{p.descricao}</span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
