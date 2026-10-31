"use client";

import { Router } from "lucide-react";

import { Equipamentos } from "@/components/acesso/equipamentos";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

export default function EquipamentosPage() {
  const { pode } = useAuth();
  if (!pode("acesso.ver")) return <SemAcesso titulo="Catracas e totens" />;
  return (
    <div>
      <PageHeader
        titulo="Catracas e totens"
        descricao="Cadastre as catracas, teste a conexão, libere manualmente e pareie os totens da recepção."
        icone={Router}
        migalhas={[{ label: "Início", href: "/" }, { label: "Controle de acesso", href: "/acesso" }, { label: "Catracas e totens" }]}
      />
      <Equipamentos />
    </div>
  );
}
