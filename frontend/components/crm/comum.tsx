"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarCheck,
  Flame,
  Globe,
  Camera,
  Mail,
  MessageCircle,
  NotebookPen,
  Phone,
  Snowflake,
  Store,
  Sun,
  UserPlus,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ListaTarefas, OpcoesCrm, OrigemLead, Temperatura, TipoInteracao } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

export const ROTULO_ORIGEM: Record<OrigemLead, string> = {
  site: "Site",
  instagram: "Instagram",
  indicacao: "Indicação",
  wellhub: "Wellhub",
  totalpass: "TotalPass",
  passante: "Passante",
  whatsapp: "WhatsApp",
  outros: "Outros",
};

export const ICONE_ORIGEM: Record<OrigemLead, LucideIcon> = {
  site: Globe,
  instagram: Camera,
  indicacao: Users,
  wellhub: Zap,
  totalpass: Zap,
  passante: Store,
  whatsapp: MessageCircle,
  outros: UserPlus,
};

export const INTERACAO: Record<TipoInteracao, { rotulo: string; icone: LucideIcon; cor: string }> = {
  LIGACAO: { rotulo: "Ligação", icone: Phone, cor: "bg-info/12 text-info-ink" },
  WHATSAPP: { rotulo: "WhatsApp", icone: MessageCircle, cor: "bg-success/12 text-success-ink" },
  VISITA: { rotulo: "Visita", icone: Store, cor: "bg-warning/15 text-warning-ink" },
  EMAIL: { rotulo: "E-mail", icone: Mail, cor: "bg-brand/12 text-info-ink" },
  NOTA: { rotulo: "Nota", icone: NotebookPen, cor: "bg-muted text-muted-foreground" },
  SISTEMA: { rotulo: "Sistema", icone: CalendarCheck, cor: "bg-muted text-muted-foreground" },
};

const TEMP: Record<Temperatura, { rotulo: string; icone: LucideIcon; classe: string; dica: string }> = {
  quente: { rotulo: "Quente", icone: Flame, classe: "text-danger-ink bg-danger/10", dica: "Contato recente ou aula experimental marcada" },
  morno: { rotulo: "Morno", icone: Sun, classe: "text-warning-ink bg-warning/12", dica: "Sem contato há alguns dias" },
  frio: { rotulo: "Frio", icone: Snowflake, classe: "text-info-ink bg-info/10", dica: "Sem contato há mais de uma semana" },
  encerrado: { rotulo: "Encerrado", icone: CalendarCheck, classe: "text-muted-foreground bg-muted", dica: "Lead matriculado ou perdido" },
};

export function TemperaturaBadge({ t, compacto }: { t: Temperatura; compacto?: boolean }) {
  const c = TEMP[t];
  const Icone = c.icone;
  return (
    <span title={c.dica} className={cn("inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium", c.classe)}>
      <Icone className="size-3" />
      {!compacto && c.rotulo}
    </span>
  );
}

export function OrigemTag({ origem }: { origem: OrigemLead }) {
  const Icone = ICONE_ORIGEM[origem];
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Icone className="size-3" /> {ROTULO_ORIGEM[origem]}
    </span>
  );
}

export function useOpcoesCrm() {
  return useQuery({ queryKey: ["crm", "opcoes"], queryFn: () => api.get<OpcoesCrm>("/crm/opcoes"), staleTime: 60_000 });
}

/** "2026-10-31T14:00" (input datetime-local) a partir de um ISO, no fuso do navegador. */
export function paraInputLocal(iso: string | Date) {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Valor do input datetime-local -> ISO com fuso. */
export function deInputLocal(v: string) {
  return new Date(v).toISOString();
}

export function quandoCurto(iso: string) {
  const d = new Date(iso);
  const hoje = new Date();
  const amanha = new Date();
  amanha.setDate(hoje.getDate() + 1);
  const ontem = new Date();
  ontem.setDate(hoje.getDate() - 1);
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === hoje.toDateString()) return `hoje, ${hora}`;
  if (d.toDateString() === amanha.toDateString()) return `amanhã, ${hora}`;
  if (d.toDateString() === ontem.toDateString()) return `ontem, ${hora}`;
  return `${d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" })}, ${hora}`;
}

const ABAS = [
  { href: "/crm", rotulo: "Funil", exato: true },
  { href: "/crm/leads", rotulo: "Leads" },
  { href: "/crm/tarefas", rotulo: "Minhas tarefas", contador: true },
  { href: "/crm/relatorio", rotulo: "Relatório" },
  { href: "/crm/configuracoes", rotulo: "Configurações", permissao: "crm.editar" },
];

/** Abas do CRM (com o contador de tarefas de hoje/atrasadas). */
export function CrmNav() {
  const pathname = usePathname();
  const { pode } = useAuth();
  const tarefas = useQuery({
    queryKey: ["crm", "tarefas", "minhas", "hoje"],
    queryFn: () => api.get<ListaTarefas>("/crm/tarefas", { escopo: "minhas", situacao: "hoje" }),
    meta: { silencioso: true },
  });
  const pendentes = (tarefas.data?.contagens.atrasadas ?? 0) + (tarefas.data?.contagens.hoje ?? 0);
  const atrasadas = tarefas.data?.contagens.atrasadas ?? 0;
  return (
    <nav aria-label="Seções do CRM" className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1 pb-1">
      {ABAS.filter((a) => !a.permissao || pode(a.permissao)).map((a) => {
        const ativo = a.exato ? pathname === a.href : pathname === a.href || pathname.startsWith(`${a.href}/`);
        return (
          <Link
            key={a.href}
            href={a.href}
            aria-current={ativo ? "page" : undefined}
            className={cn(
              "inline-flex h-9 shrink-0 items-center gap-2 rounded-full border px-3.5 text-sm font-medium transition-colors",
              ativo ? "border-brand bg-brand/10 text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {a.rotulo}
            {a.contador && pendentes > 0 && (
              <span className={cn("rounded-full px-1.5 text-xs tabular-nums text-white", atrasadas ? "bg-danger" : "bg-brand")}>{pendentes}</span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
