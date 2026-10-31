"use client";

import { BarChart3 } from "lucide-react";

import { Historico } from "@/components/acesso/historico";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

export default function HistoricoAcessosPage() {
  const { pode } = useAuth();
  if (!pode("acesso.ver")) return <SemAcesso titulo="Histórico de acessos" />;
  return (
    <div>
      <PageHeader
        titulo="Histórico de acessos"
        descricao="Toda tentativa de entrada (liberada ou negada), com o motivo, o método e onde aconteceu."
        icone={BarChart3}
        migalhas={[{ label: "Início", href: "/" }, { label: "Controle de acesso", href: "/acesso" }, { label: "Histórico" }]}
      />
      <Historico />
    </div>
  );
}
