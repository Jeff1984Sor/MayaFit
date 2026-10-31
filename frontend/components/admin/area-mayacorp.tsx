"use client";

import { Building2, ShieldOff } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/mayacorp/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAreaMayaCorp } from "@/lib/admin";

/**
 * Guarda das telas /admin/*: só fazem sentido no estúdio "mayacorp" e para administradores.
 * É só conforto visual; quem bloqueia de verdade é a API (404 fora do admin, 403 para não administradores).
 */
export function AreaMayaCorp({ children }: { children: React.ReactNode }) {
  const { mayacorp, administrador, carregando } = useAreaMayaCorp();
  if (carregando) return <Skeleton className="h-72 rounded-2xl" />;
  if (!mayacorp)
    return (
      <EmptyState
        icone={Building2}
        titulo="Área exclusiva da MayaCorp"
        descricao="Estas telas administram os estúdios clientes do MayaFit e só abrem no endereço do admin da MayaCorp."
        acao={<Button variant="outline" render={<Link href="/" />}>Voltar ao início</Button>}
        className="py-20"
      />
    );
  if (!administrador)
    return (
      <EmptyState
        icone={ShieldOff}
        titulo="Só administradores da MayaCorp"
        descricao="Peça a um administrador para liberar o seu acesso."
        acao={<Button variant="outline" render={<Link href="/" />}>Voltar ao início</Button>}
        className="py-20"
      />
    );
  return <>{children}</>;
}
