"use client";

import { DoorOpen } from "lucide-react";

import { PainelAoVivo } from "@/components/acesso/painel-ao-vivo";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

export default function AcessoPage() {
  const { pode } = useAuth();
  if (!pode("acesso.ver")) return <SemAcesso titulo="Controle de acesso" />;
  return (
    <div>
      <PageHeader
        titulo="Quem está no estúdio"
        descricao="Check-ins do totem e liberações da recepção, em tempo real."
        icone={DoorOpen}
        migalhas={[{ label: "Início", href: "/" }, { label: "Controle de acesso" }]}
      />
      <PainelAoVivo />
    </div>
  );
}
