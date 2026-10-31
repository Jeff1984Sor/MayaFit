import { BadgeDollarSign, Building2, HandCoins, Inbox, LayoutDashboard, ScrollText } from "lucide-react";

import type { NavGrupo } from "./nav";

/**
 * Seção "Admin MayaFit" do menu: só aparece no admin MayaCorp (usuário cujo estúdio tem `mayacorp: true`).
 * As rotas /api/admin/* conferem de novo no servidor (estúdio mayacorp + administrador).
 */
export const NAV_ADMIN: NavGrupo = {
  titulo: "Admin MayaFit",
  itens: [
    { label: "Início", href: "/admin", icone: LayoutDashboard, exato: true },
    { label: "Estúdios", href: "/admin/estudios", icone: Building2 },
    { label: "Solicitações", href: "/admin/solicitacoes", icone: Inbox },
    { label: "Planos e indicação", href: "/admin/planos", icone: BadgeDollarSign },
    { label: "Contratos", href: "/admin/contratos", icone: ScrollText },
    { label: "Cobranças", href: "/admin/cobrancas", icone: HandCoins },
  ],
};
