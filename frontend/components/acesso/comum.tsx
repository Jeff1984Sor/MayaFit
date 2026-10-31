"use client";

import { CheckCircle2, Hand, KeyRound, QrCode, ScanFace, XCircle } from "lucide-react";
import { toast } from "sonner";

import { executarPlano } from "@/components/acesso/catraca-local";
import { Pill } from "@/components/mayacorp/status-badge";
import { api } from "@/lib/api";
import type { Acionamento, Metodo, Registro } from "@/lib/tipos-acesso";
import { ROTULO_METODO } from "@/lib/tipos-acesso";
import { cn } from "@/lib/utils";

export const ICONE_METODO: Record<Metodo, React.ComponentType<{ className?: string }>> = {
  facial: ScanFace,
  cpf: KeyRound,
  codigo: KeyRound,
  qr: QrCode,
  manual: Hand,
};

export function MetodoTag({ metodo, className }: { metodo: Metodo; className?: string }) {
  const Icone = ICONE_METODO[metodo] ?? Hand;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs text-muted-foreground", className)} title={ROTULO_METODO[metodo]}>
      <Icone className="size-3.5" />
      {ROTULO_METODO[metodo] ?? metodo}
    </span>
  );
}

export function ResultadoPill({ r }: { r: Pick<Registro, "permitido" | "sentido"> }) {
  if (r.sentido === "saida") return <Pill tom="neutral">Saída</Pill>;
  return r.permitido ? (
    <Pill tom="success">
      <CheckCircle2 className="size-3" /> Liberado
    </Pill>
  ) : (
    <Pill tom="danger">
      <XCircle className="size-3" /> Negado
    </Pill>
  );
}

const CATRACA: Record<string, [string, "success" | "danger" | "warning" | "neutral"]> = {
  liberada: ["Catraca liberada", "success"],
  falhou: ["Catraca falhou", "danger"],
  pendente: ["Catraca aguardando", "warning"],
  sem_catraca: ["Sem catraca", "neutral"],
};

export function CatracaPill({ status, detalhe }: { status: string | null; detalhe?: string | null }) {
  if (!status) return null;
  const [rotulo, tom] = CATRACA[status] ?? [status, "neutral"];
  return (
    <span title={detalhe ?? undefined}>
      <Pill tom={tom}>{rotulo}</Pill>
    </span>
  );
}

/** Indicador simples (número grande + legenda), no visual dos cards MayaCorp. */
export function Indicador({
  titulo,
  valor,
  legenda,
  icone: Icone,
  tom = "brand",
  carregando,
}: {
  titulo: string;
  valor: React.ReactNode;
  legenda?: React.ReactNode;
  icone: React.ComponentType<{ className?: string }>;
  tom?: "brand" | "success" | "danger" | "warning";
  carregando?: boolean;
}) {
  return (
    <div className="card-surface relative overflow-hidden p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-muted-foreground">{titulo}</p>
        <div
          className={cn(
            "grid size-8 place-items-center rounded-lg",
            tom === "brand" && "bg-brand/10 text-navy dark:text-brand",
            tom === "success" && "bg-success/10 text-success-ink",
            tom === "danger" && "bg-danger/10 text-danger-ink",
            tom === "warning" && "bg-warning/12 text-warning-ink",
          )}
        >
          <Icone className="size-4" />
        </div>
      </div>
      {carregando ? (
        <div className="mt-3 h-8 w-20 animate-pulse rounded bg-muted" />
      ) : (
        <p className="mt-2 text-[26px] leading-tight font-semibold tracking-tight num">{valor}</p>
      )}
      {legenda && <p className="mt-1 text-xs text-muted-foreground">{legenda}</p>}
    </div>
  );
}

export function hora(v: string) {
  return new Date(v).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Depois de uma liberação (manual ou teste), se a API devolveu um plano para a rede local, ESTE navegador executa e
 * informa o resultado em `urlResultado`. Mostra toasts claros. Devolve ok/falha.
 */
export async function acionarNesteNavegador(ac: Acionamento | null, urlResultado: string | null): Promise<boolean | null> {
  if (!ac) return null;
  if (ac.status === "liberada" || ac.status === "ok") {
    toast.success(ac.mensagem || "Catraca liberada.");
    return true;
  }
  if (ac.status === "falhou") {
    toast.error(ac.mensagem || "A catraca não respondeu.");
    return false;
  }
  if (ac.status === "sem_catraca") return null;
  if (!ac.plano) {
    toast.info(ac.mensagem || "Comando enviado ao agente local.");
    return null;
  }
  const id = toast.loading("Falando com a catraca pela rede local…");
  const r = await executarPlano(ac.plano);
  toast.dismiss(id);
  if (r.ok) toast.success(r.detalhe);
  else toast.error(r.detalhe, { description: "Este computador precisa estar na mesma rede da catraca." });
  if (urlResultado) await api.post(urlResultado, { ok: r.ok, detalhe: r.detalhe }).catch(() => undefined);
  return r.ok;
}
