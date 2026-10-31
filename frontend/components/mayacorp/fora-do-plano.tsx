"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Lock, Sparkles } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { moeda } from "@/lib/format";
import type { PlanoOut, Rotulo } from "@/lib/tipos-admin";

type PlanoPublico = PlanoOut & { recursos_rotulos?: Rotulo[] };

/**
 * Regra P8 (docs/ESPECIFICACAO.md): recurso fora do plano não some. A tela mostra o cadeado, o que o recurso faz e o
 * plano mais barato que o libera, com o caminho para o "Meu plano". O servidor recusa os dados de qualquer jeito.
 */
export function ForaDoPlano({ recurso, nome }: { recurso: string; nome: string }) {
  const { data: planos } = useQuery({
    queryKey: ["public", "planos"],
    queryFn: () => api.get<PlanoPublico[]>("/public/planos"),
    staleTime: 10 * 60_000,
  });
  const plano = planos?.find((p) => p.recursos.includes(recurso));
  const rotulo = plano?.recursos_rotulos?.find((r) => r.chave === recurso)?.rotulo ?? nome;

  return (
    <div className="mx-auto flex max-w-xl flex-col items-center py-16 text-center">
      <div className="relative mb-6">
        <div className="absolute inset-0 animate-pulse rounded-full bg-brand/20 blur-2xl" aria-hidden />
        <div className="relative flex size-20 items-center justify-center rounded-2xl bg-linear-to-br from-navy to-brand text-white shadow-lg">
          <Lock className="size-9" />
        </div>
      </div>
      <h1 className="text-2xl font-semibold tracking-tight">{rotulo}</h1>
      <p className="mt-2 text-muted-foreground">
        Este recurso não está no plano do seu estúdio
        {plano ? (
          <>
            . Ele vem a partir do plano <strong className="font-semibold text-foreground">{plano.nome}</strong>, por{" "}
            <span className="num font-semibold text-foreground">{moeda(plano.preco_mensal)}</span> por mês.
          </>
        ) : (
          ". Fale com a equipe MayaFit para liberar."
        )}
      </p>

      {plano?.recursos_rotulos && plano.recursos_rotulos.length > 0 && (
        <div className="mt-8 w-full rounded-xl border bg-card p-5 text-left shadow-sm">
          <p className="mb-3 flex items-center gap-2 text-sm font-medium">
            <Sparkles className="size-4 text-brand" /> No plano {plano.nome} você tem
          </p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {plano.recursos_rotulos.map((r) => (
              <li key={r.chave} className="flex items-start gap-2 text-sm">
                <Check className={r.chave === recurso ? "mt-0.5 size-4 text-teal-maya" : "mt-0.5 size-4 text-muted-foreground"} />
                <span className={r.chave === recurso ? "font-medium" : "text-muted-foreground"}>{r.rotulo}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Button render={<Link href={`/minha-conta/plano?recurso=${encodeURIComponent(recurso)}`} />}>Ver meu plano</Button>
        <Button variant="outline" render={<Link href="/" />}>Voltar ao início</Button>
      </div>
    </div>
  );
}
