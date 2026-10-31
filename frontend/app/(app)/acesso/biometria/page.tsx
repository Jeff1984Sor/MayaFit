"use client";

import { ScanFace } from "lucide-react";
import { Suspense } from "react";

import { Biometria } from "@/components/acesso/biometria";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

export default function BiometriaPage() {
  const { pode } = useAuth();
  if (!pode("acesso.ver")) return <SemAcesso titulo="Biometria e PIN" />;
  return (
    <div>
      <PageHeader
        titulo="Biometria e PIN"
        descricao="Consentimento, cadastro do rosto e PIN de cada aluno. Clique no aluno para abrir a ficha de acesso."
        icone={ScanFace}
        migalhas={[{ label: "Início", href: "/" }, { label: "Controle de acesso", href: "/acesso" }, { label: "Biometria e PIN" }]}
      />
      <Suspense>
        <Biometria />
      </Suspense>
    </div>
  );
}
