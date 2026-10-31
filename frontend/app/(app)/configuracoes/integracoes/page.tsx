"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Dumbbell, KeyRound, Link2, Mail, MessageCircle, Sparkles, Ticket } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { StatusWhatsapp } from "@/lib/tipos-comunicacao";
import { cn } from "@/lib/utils";

// Sub-páginas que pertencem a outros agentes. Troque para `true` quando a tela existir (ou o coordenador ligar na integração).
const DISPONIVEL = { totalpass: true, tokens: true };

interface Cartao {
  titulo: string;
  descricao: string;
  href: string;
  icone: React.ComponentType<{ className?: string }>;
  disponivel: boolean;
  permissao?: string;
  extra?: React.ReactNode;
}

export default function IntegracoesPage() {
  const { pode } = useAuth();
  const zap = useQuery({
    queryKey: ["whatsapp", "status"],
    queryFn: () => api.get<StatusWhatsapp>("/whatsapp/status"),
    enabled: pode("whatsapp.ver"),
    meta: { silencioso: true },
  });

  const cartoes: Cartao[] = [
    {
      titulo: "WhatsApp",
      descricao: "WasenderAPI ou Evolution API: token da sessão, testar conexão, horários e textos dos avisos automáticos.",
      href: "/configuracoes/integracoes/whatsapp",
      icone: MessageCircle,
      disponivel: true,
      permissao: "whatsapp.configurar",
      extra: zap.data ? (
        <div className="flex flex-wrap gap-1.5">
          <Pill tom={zap.data.unidades_configuradas > 0 ? "success" : "warning"}>
            {zap.data.unidades_configuradas > 0 ? `${zap.data.unidades_configuradas} unidade(s) configurada(s)` : "Não configurado"}
          </Pill>
          <Pill tom={zap.data.envio_automatico_ativo ? "success" : "neutral"}>Envio automático {zap.data.envio_automatico_ativo ? "ligado" : "desligado"}</Pill>
        </div>
      ) : null,
    },
    {
      titulo: "TotalPass",
      descricao: "Chaves da parceria e token do webhook para receber os check-ins e criar as reservas.",
      href: "/configuracoes/integracoes/totalpass",
      icone: Ticket,
      disponivel: DISPONIVEL.totalpass,
      permissao: "integracoes.ver",
    },
    {
      titulo: "Wellhub",
      descricao: "Antigo Gympass: reservas e check-ins dos alunos, grade publicada com as vagas e conferência do repasse mensal.",
      href: "/configuracoes/integracoes/wellhub",
      icone: Dumbbell,
      disponivel: true,
      permissao: "integracoes.ver",
    },
    {
      titulo: "Tokens de API",
      descricao: "Chaves para empresas parceiras consultarem e cadastrarem alunos pela API de integração.",
      href: "/configuracoes/integracoes/tokens",
      icone: KeyRound,
      disponivel: DISPONIVEL.tokens,
      permissao: "integracoes.ver",
    },
    {
      titulo: "Inteligência Artificial",
      descricao: "Chave do provedor de IA usada para melhorar textos de evolução e preencher cadastros.",
      href: "/configuracoes/ia",
      icone: Sparkles,
      disponivel: true,
      permissao: "configuracoes.ver",
    },
    {
      titulo: "E-mail",
      descricao: "Servidor SMTP para recuperação de senha, convites e envios a alunos.",
      href: "/configuracoes/email",
      icone: Mail,
      disponivel: true,
      permissao: "configuracoes.ver",
    },
  ];
  const visiveis = cartoes.filter((c) => !c.permissao || pode(c.permissao));
  if (visiveis.length === 0) return <SemAcesso titulo="Integrações" />;

  return (
    <div>
      <PageHeader
        titulo="Integrações"
        descricao="Todas as credenciais são cadastradas aqui, ficam cifradas e nunca são exibidas de novo. Só o perfil Full altera."
        icone={Link2}
        migalhas={[{ label: "Início", href: "/" }, { label: "Configurações" }, { label: "Integrações" }]}
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {visiveis.map((c) => {
          const conteudo = (
            <>
              <div className="flex items-start justify-between gap-3">
                <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand/12 text-navy ring-1 ring-brand/25 dark:text-brand">
                  <c.icone className="size-5" />
                </div>
                {c.disponivel ? <ArrowRight className="size-4 text-muted-foreground" /> : <Pill tom="info">Em breve</Pill>}
              </div>
              <h2 className="mt-3 font-semibold">{c.titulo}</h2>
              <p className="mt-1 flex-1 text-sm text-muted-foreground">{c.descricao}</p>
              {c.extra && <div className="mt-3">{c.extra}</div>}
            </>
          );
          const base = "card-surface flex flex-col p-5";
          return c.disponivel ? (
            <Link key={c.href} href={c.href} className={cn(base, "transition-shadow hover:shadow-md")}>
              {conteudo}
            </Link>
          ) : (
            <div key={c.href} className={cn(base, "opacity-70")} aria-disabled>
              {conteudo}
            </div>
          );
        })}
      </div>
    </div>
  );
}
