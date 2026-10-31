import {
  ArrowLeftRight,
  Ban,
  Briefcase,
  BarChart3,
  Building2,
  CalendarCheck,
  CircleUserRound,
  CalendarClock,
  CalendarDays,
  ClipboardList,
  Clock,
  FileSignature,
  FileText,
  FolderTree,
  HeartPulse,
  Home,
  Landmark,
  LayoutDashboard,
  Link2,
  Mail,
  Megaphone,
  MessageCircle,
  Palette,
  Percent,
  ReceiptText,
  Repeat,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Tags,
  Truck,
  Users,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import { NAV_ADMIN } from "./nav-admin";

export interface NavItem {
  label: string;
  href: string;
  icone: LucideIcon;
  /** Permissão do perfil de acesso exigida ("recurso.acao"); sem ela, basta estar logado. */
  permissao?: string;
  /** Área planejada: aparece no menu, mas ainda não tem tela (não clicável). */
  planejado?: boolean;
  /** Recurso do plano exigido (ex.: "crm", "nfse", "wellhub"); some se o estúdio não tiver. Sem estúdio, aparece. */
  recurso?: string;
  /** Selo "novo" ao lado do nome (módulo recém-lançado). */
  novo?: boolean;
  atalho?: string;
  exato?: boolean;
}

export interface NavGrupo {
  titulo: string;
  itens: NavItem[];
}

export const NAV: NavGrupo[] = [
  {
    titulo: "Geral",
    itens: [
      { label: "Início", href: "/", icone: Home, exato: true },
      { label: "Painel", href: "/dashboard", icone: LayoutDashboard, permissao: "painel.ver", atalho: "G D" },
    ],
  },
  {
    titulo: "Agenda",
    itens: [
      { label: "Grade semanal", href: "/agenda/semana", icone: CalendarDays, permissao: "agenda.ver", planejado: false },
      { label: "Aulas do dia", href: "/agenda/aulas", icone: CalendarCheck, permissao: "aulas.ver", planejado: false },
      { label: "Reposições", href: "/reposicoes", icone: Repeat, permissao: "reposicoes.ver", planejado: false },
    ],
  },
  {
    titulo: "Alunos",
    itens: [{ label: "Alunos", href: "/alunos", icone: UsersRound, permissao: "alunos.ver" }],
  },
  {
    titulo: "Contratos",
    itens: [
      { label: "Contratos", href: "/contratos", icone: FileSignature, permissao: "contratos.ver", planejado: false },
      { label: "Planos", href: "/cadastros/planos", icone: ClipboardList, permissao: "planos.ver" },
    ],
  },
  {
    titulo: "Financeiro",
    itens: [
      { label: "Contas a receber", href: "/financeiro/receber", icone: ReceiptText, permissao: "financeiro_receber.ver" },
      { label: "Contas a pagar", href: "/financeiro/pagar", icone: CalendarClock, permissao: "financeiro_pagar.ver" },
      { label: "Fluxo de caixa", href: "/financeiro/caixa", icone: ArrowLeftRight, permissao: "financeiro_caixa.ver" },
      { label: "DRE", href: "/financeiro/dre", icone: BarChart3, permissao: "financeiro_dre.ver" },
      { label: "Contas bancárias", href: "/financeiro/bancos", icone: Landmark, permissao: "financeiro_bancos.ver" },
      { label: "Receita Saúde", href: "/receita-saude", icone: HeartPulse, permissao: "receita_saude.ver" },
      { label: "Comissões", href: "/comissoes", icone: Percent, permissao: "comissoes.ver" },
    ],
  },
  {
    titulo: "Cadastros",
    itens: [
      { label: "Unidades", href: "/cadastros/unidades", icone: Building2, permissao: "cadastros_unidades.ver" },
      { label: "Tipos de serviço", href: "/cadastros/servicos", icone: Tags, permissao: "cadastros_servicos.ver" },
      { label: "Profissionais", href: "/cadastros/profissionais", icone: Stethoscope, permissao: "cadastros_profissionais.ver" },
      { label: "Profissões", href: "/cadastros/profissoes", icone: Briefcase, permissao: "cadastros_profissionais.ver" },
      { label: "Fornecedores", href: "/cadastros/fornecedores", icone: Truck, permissao: "cadastros_fornecedores.ver" },
      { label: "Categorias", href: "/cadastros/categorias", icone: FolderTree, permissao: "cadastros_categorias.ver" },
      { label: "Horários", href: "/cadastros/horarios", icone: Clock, permissao: "cadastros_horarios.ver" },
      { label: "Bloqueios", href: "/cadastros/bloqueios", icone: Ban, permissao: "cadastros_bloqueios.ver" },
      { label: "Termos", href: "/cadastros/termos", icone: ScrollText, permissao: "cadastros_termos.ver" },
      { label: "Modelos", href: "/cadastros/modelos", icone: FileText, permissao: "cadastros_modelos.ver" },
    ],
  },
  {
    titulo: "Comunicação",
    itens: [
      { label: "WhatsApp", href: "/comunicacao/whatsapp", icone: MessageCircle, permissao: "whatsapp.ver", planejado: false },
      { label: "Comunicados", href: "/comunicacao/comunicados", icone: Megaphone, permissao: "comunicacao.ver", planejado: false },
      { label: "Integrações", href: "/configuracoes/integracoes", icone: Link2, permissao: "integracoes.ver", planejado: false },
    ],
  },
  {
    titulo: "Configurações",
    itens: [
      { label: "Identidade", href: "/configuracoes/identidade", icone: Palette, permissao: "configuracoes.ver" },
      { label: "Usuários", href: "/configuracoes/usuarios", icone: Users, permissao: "usuarios.ver" },
      { label: "Perfis de acesso", href: "/configuracoes/perfis", icone: ShieldCheck, permissao: "perfis.ver" },
      { label: "E-mail", href: "/configuracoes/email", icone: Mail, permissao: "configuracoes.ver" },
      { label: "Inteligência Artificial", href: "/configuracoes/ia", icone: Sparkles, permissao: "configuracoes.ver" },
      { label: "Auditoria", href: "/auditoria", icone: ScrollText, permissao: "auditoria.ver" },
    ],
  },
];

/** Grupo "Conta" do admin MayaCorp (no estúdio, Minha conta fica no menu do usuário). */
const NAV_CONTA: NavGrupo = {
  titulo: "Conta",
  itens: [{ label: "Minha conta", href: "/minha-conta", icone: CircleUserRound }],
};

/**
 * O estúdio tem o recurso? `recursos` vem de /auth/me (estudio.recursos): lista de chaves ou mapa chave → ligado.
 * Sem informação (modo um banco só, ou backend antigo) tudo fica liberado.
 */
export function temRecurso(recursos: unknown, chave: string): boolean {
  if (recursos == null) return true;
  if (Array.isArray(recursos)) return recursos.includes(chave);
  if (typeof recursos === "object") {
    const v = (recursos as Record<string, unknown>)[chave];
    return v === undefined ? true : !!v;
  }
  return true;
}

export interface OpcoesNav {
  /** Admin MayaCorp (`usuario.estudio.mayacorp`): só a seção Admin MayaFit + Configurações + Auditoria + Minha conta. */
  mayacorp?: boolean;
  /** `usuario.estudio.recursos`: filtra os itens com `recurso`. */
  recursos?: unknown;
}

/** Grupos que a pessoa vê. Sem `opcoes` (modo um banco só) o menu é o de sempre. */
export function navPara(pode: ((permissao: string) => boolean) | undefined, opcoes: OpcoesNav = {}): NavGrupo[] {
  if (!pode) return [];
  const base = opcoes.mayacorp ? [NAV_ADMIN, ...NAV.filter((g) => g.titulo === "Configurações"), NAV_CONTA] : NAV;
  return base
    .map((g) => ({
      ...g,
      itens: g.itens.filter((i) => (!i.permissao || pode(i.permissao)) && (!i.recurso || temRecurso(opcoes.recursos, i.recurso))),
    }))
    .filter((g) => g.itens.length > 0);
}

/** Item do menu que cobre o endereço (o mais específico), para o bloqueio de página. */
export function itemDaRota(pathname: string): NavItem | undefined {
  let melhor: NavItem | undefined;
  for (const g of [...NAV, NAV_ADMIN])
    for (const i of g.itens)
      if (!i.planejado && i.href !== "/" && (pathname === i.href || pathname.startsWith(`${i.href}/`)))
        if (!melhor || i.href.length > melhor.href.length) melhor = i;
  return melhor;
}

/**
 * A rota pertence à outra "casa"? Módulos do estúdio somem no admin MayaCorp e a seção MayaCorp só existe lá.
 * Bloqueio leve de tela: o servidor já recusa os dados.
 */
export function rotaForaDaCasa(pathname: string, mayacorp: boolean): boolean {
  const rota = itemDaRota(pathname);
  if (!rota) return false;
  const doAdmin = NAV_ADMIN.itens.includes(rota);
  if (!mayacorp) return doAdmin;
  if (doAdmin) return false;
  const config = NAV.find((g) => g.titulo === "Configurações");
  return !config?.itens.includes(rota);
}

export function ativo(pathname: string, item: NavItem) {
  if (item.planejado) return false;
  return item.exato ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
}
