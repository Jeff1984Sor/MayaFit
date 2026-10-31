"use client";

import { AlertTriangle, ArrowRight, CircleCheck, CircleX, Info, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Pill, StatusBadge } from "@/components/mayacorp/status-badge";
import { data } from "@/lib/format";
import type { CertificadoInfo, ErroNota, ModoNfse, Nivel, Pendencia, StatusNota } from "@/lib/tipos-nfse";
import { cn } from "@/lib/utils";

type Tom = "success" | "warning" | "danger" | "info" | "neutral" | "brand";

export const STATUS: Record<StatusNota, { label: string; tom: Tom; pulse?: boolean }> = {
  pendente: { label: "Na fila", tom: "brand", pulse: true },
  processando: { label: "Enviando", tom: "info", pulse: true },
  emitida: { label: "Emitida", tom: "success" },
  validada: { label: "Validada (teste)", tom: "info" },
  rejeitada: { label: "Rejeitada", tom: "danger" },
  falha: { label: "Falha de comunicação", tom: "warning" },
  cancelada: { label: "Cancelada", tom: "neutral" },
};

export function StatusNotaBadge({ status }: { status: StatusNota }) {
  const s = STATUS[status] ?? { label: status, tom: "neutral" as Tom };
  return <StatusBadge label={s.label} tom={s.tom} pulse={s.pulse} />;
}

export function ModoPill({ modo }: { modo: ModoNfse }) {
  if (modo === "producao") return <Pill tom="success">Produção</Pill>;
  if (modo === "homologacao") return <Pill tom="warning">Teste</Pill>;
  return <Pill tom="info">Simulado</Pill>;
}

const ICONE_NIVEL: Record<Nivel, typeof CircleX> = { erro: CircleX, aviso: AlertTriangle, info: Info };
const COR_NIVEL: Record<Nivel, string> = {
  erro: "border-danger/30 bg-danger/6 text-danger-ink",
  aviso: "border-warning/35 bg-warning/8 text-warning-ink",
  info: "border-info/30 bg-info/6 text-info-ink",
};

/** Um achado/erro em português claro: o que aconteceu + o que fazer (padrão do raio-x do MayaJus). */
export function Achado({
  nivel,
  titulo,
  mensagem,
  acao,
  link,
  tecnico,
  className,
}: {
  nivel: Nivel;
  titulo?: string;
  mensagem: string;
  acao?: string;
  link?: string | null;
  tecnico?: string | null;
  className?: string;
}) {
  const Icone = ICONE_NIVEL[nivel] ?? Info;
  return (
    <div className={cn("flex gap-3 rounded-xl border p-3", COR_NIVEL[nivel], className)}>
      <Icone className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1 text-sm">
        {titulo && <p className="text-xs font-semibold tracking-wide uppercase opacity-80">{titulo}</p>}
        <p className="font-medium text-foreground">{mensagem}</p>
        {acao && (
          <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[13px] text-muted-foreground">
            <ArrowRight className="size-3.5" />
            {link ? (
              <Link href={link} className="font-medium text-info-ink underline-offset-2 hover:underline">
                {acao}
              </Link>
            ) : (
              acao
            )}
          </p>
        )}
        {tecnico && (
          <details className="mt-1.5 text-xs text-muted-foreground">
            <summary className="cursor-pointer select-none">Detalhe técnico</summary>
            <code className="mt-1 block font-mono break-all whitespace-pre-wrap">{tecnico}</code>
          </details>
        )}
      </div>
    </div>
  );
}

export function ListaErros({ erros }: { erros: ErroNota[] }) {
  return (
    <div className="flex flex-col gap-2">
      {erros.map((e, i) => (
        <Achado
          key={i}
          nivel={e.nivel === "aviso" ? "aviso" : "erro"}
          titulo={e.codigo ? `Código ${e.codigo}` : undefined}
          mensagem={e.mensagem}
          acao={e.acao}
          tecnico={e.tecnico}
        />
      ))}
    </div>
  );
}

export function ListaPendencias({ itens }: { itens: Pendencia[] }) {
  if (!itens.length)
    return (
      <p className="flex items-center gap-2 rounded-xl border border-success/30 bg-success/6 p-3 text-sm text-success-ink">
        <CircleCheck className="size-4" /> Nenhuma pendência. Tudo pronto para emitir.
      </p>
    );
  return (
    <div className="flex flex-col gap-2">
      {itens.map((p, i) => (
        <Achado key={i} nivel={p.nivel} mensagem={p.mensagem} acao={p.acao} link={p.link} />
      ))}
    </div>
  );
}

export function CertificadoResumo({ cert, compacto }: { cert: CertificadoInfo; compacto?: boolean }) {
  const ok = cert.situacao === "valido";
  const Icone = ok ? ShieldCheck : ShieldAlert;
  const cor =
    cert.situacao === "valido"
      ? "text-success-ink bg-success/10"
      : cert.situacao === "vencendo"
        ? "text-warning-ink bg-warning/12"
        : cert.situacao === "vencido"
          ? "text-danger-ink bg-danger/10"
          : "text-muted-foreground bg-muted";
  return (
    <div className="flex items-start gap-3">
      <div className={cn("grid size-10 shrink-0 place-items-center rounded-xl", cor)}>
        <Icone className="size-5" />
      </div>
      <div className="min-w-0 text-sm">
        <p className="font-medium">{cert.configurado ? cert.titular || "Certificado A1" : "Nenhum certificado"}</p>
        <p className="text-muted-foreground">{cert.mensagem}</p>
        {!compacto && cert.configurado && (
          <p className="mt-1 text-xs text-muted-foreground">
            Emitido por {cert.emissor ?? "—"} · válido de {data(cert.valido_de)} a {data(cert.valido_ate)}
            {cert.dias != null && cert.dias >= 0 && <> · faltam <span className="num">{cert.dias}</span> dias</>}
          </p>
        )}
      </div>
    </div>
  );
}

/** Barra de validade do certificado (verde → âmbar → vermelho). */
export function BarraValidade({ cert }: { cert: CertificadoInfo }) {
  if (!cert.configurado || !cert.valido_de || !cert.valido_ate) return null;
  const ini = new Date(`${cert.valido_de}T00:00:00`).getTime();
  const fim = new Date(`${cert.valido_ate}T00:00:00`).getTime();
  // "dias" (restantes) vem do servidor: a barra não depende do relógio do navegador
  const totalDias = Math.max(1, (fim - ini) / 86_400_000);
  const pct = Math.min(100, Math.max(0, ((totalDias - (cert.dias ?? 0)) / totalDias) * 100));
  const cor = cert.situacao === "valido" ? "bg-success" : cert.situacao === "vencendo" ? "bg-warning" : "bg-danger";
  return (
    <div className="mt-3">
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", cor)} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>{data(cert.valido_de)}</span>
        <span>{data(cert.valido_ate)}</span>
      </div>
    </div>
  );
}

export function mesExtenso(ym: string) {
  const [a, m] = ym.split("-").map(Number);
  return new Date(a, m - 1, 1).toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(".", "");
}

export function hojeIso() {
  return new Date().toLocaleDateString("sv-SE");
}
