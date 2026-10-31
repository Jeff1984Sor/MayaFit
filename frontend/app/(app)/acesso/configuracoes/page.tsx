"use client";

import { Settings2 } from "lucide-react";

import { ConfiguracoesAcesso } from "@/components/acesso/configuracoes";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

export default function RegrasAcessoPage() {
  const { pode } = useAuth();
  if (!pode("acesso.ver")) return <SemAcesso titulo="Regras de acesso" />;
  return (
    <div>
      <PageHeader
        titulo="Regras de acesso"
        descricao="Quando o aluno pode entrar: janela da aula, tolerância da mensalidade, planos livres e reconhecimento facial."
        icone={Settings2}
        migalhas={[{ label: "Início", href: "/" }, { label: "Controle de acesso", href: "/acesso" }, { label: "Regras" }]}
      />
      <ConfiguracoesAcesso />
    </div>
  );
}
