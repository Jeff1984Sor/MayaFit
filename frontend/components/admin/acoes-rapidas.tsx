"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Link2, Mail, PauseCircle, PlayCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Button } from "@/components/ui/button";
import { copiarTexto, fichaDe, somarDias } from "@/lib/admin";
import { api } from "@/lib/api";
import { data } from "@/lib/format";
import { type Estudio, ROTULO_STATUS, type StatusEstudio } from "@/lib/tipos-admin";

/** Ações de um clique sobre um estúdio (Início e ficha). Todas passam pelas rotas normais do admin. */
export function useAcoesEstudio(e: Estudio) {
  const qc = useQueryClient();
  const atualizar = () => qc.invalidateQueries({ queryKey: ["admin"] });
  const estender = useMutation({
    mutationFn: (dias: number) => api.put<Estudio>(`/admin/clientes/${e.id}`, { ...fichaDe(e), teste_ate: somarDias(e.teste_ate, dias) }),
    onSuccess: (r) => {
      toast.success(`Teste de ${r.nome} vai até ${data(r.teste_ate)}`);
      atualizar();
    },
  });
  const status = useMutation({
    mutationFn: (s: StatusEstudio) => api.post<Estudio>(`/admin/clientes/${e.id}/status`, { status: s }),
    onSuccess: (r) => {
      toast.success(`${r.nome}: ${ROTULO_STATUS[r.status]}`);
      atualizar();
    },
  });
  const acesso = useMutation({
    mutationFn: () => api.post<{ link: string; enviado_para: string }>(`/admin/clientes/${e.id}/boas-vindas`),
    onSuccess: (r) =>
      toast.success(`Link de primeiro acesso enviado para ${r.enviado_para}`, {
        duration: 15000,
        action: { label: "Copiar link", onClick: () => copiarTexto(r.link) },
      }),
  });
  const endereco = e.dominios[0]?.host;
  return { estender, status, acesso, endereco };
}

/** Barra de ações rápidas. `compacto` = só ícones (linhas de tabela). */
export function AcoesRapidas({ estudio: e, compacto, semAcesso }: { estudio: Estudio; compacto?: boolean; semAcesso?: boolean }) {
  const { estender, status, acesso, endereco } = useAcoesEstudio(e);
  const [suspender, setSuspender] = useState(false);
  const tam = compacto ? "icon-sm" : "sm";
  const parar = (ev: React.MouseEvent) => ev.stopPropagation();
  return (
    <div className="flex flex-wrap items-center gap-1.5" onClick={parar}>
      {e.status === "teste" && (
        <>
          <Button size="sm" variant="outline" disabled={estender.isPending} onClick={() => estender.mutate(15)} title="Estender o teste em 15 dias">
            <CalendarPlus /> +15 dias
          </Button>
          {!compacto && (
            <Button size="sm" variant="outline" disabled={estender.isPending} onClick={() => estender.mutate(30)} title="Estender o teste em 30 dias">
              +30 dias
            </Button>
          )}
        </>
      )}
      {(e.status === "ativo" || e.status === "teste") && (
        <Button size={tam} variant="outline" onClick={() => setSuspender(true)} title="Suspender (continua entrando, com aviso)" aria-label="Suspender">
          <PauseCircle /> {!compacto && "Suspender"}
        </Button>
      )}
      {(e.status === "suspenso" || e.status === "inativo") && (
        <Button size={tam} variant="outline" disabled={status.isPending} onClick={() => status.mutate("ativo")} title="Reativar" aria-label="Reativar">
          <PlayCircle /> {!compacto && "Reativar"}
        </Button>
      )}
      {!semAcesso && (
        <Button size={tam} variant="outline" disabled={acesso.isPending} onClick={() => acesso.mutate()} title="Reenviar o link de primeiro acesso ao dono" aria-label="Reenviar acesso">
          <Mail /> {!compacto && "Reenviar acesso"}
        </Button>
      )}
      <Button
        size={tam}
        variant="ghost"
        onClick={() => copiarTexto(endereco ? `https://${endereco}` : e.slug, endereco ? "Endereço copiado" : "Identificador copiado")}
        title={endereco ? `Copiar https://${endereco}` : "Copiar o identificador"}
        aria-label="Copiar endereço"
      >
        <Link2 /> {!compacto && "Copiar endereço"}
      </Button>
      <ConfirmDialog
        open={suspender}
        onOpenChange={setSuspender}
        titulo={`Suspender ${e.nome}?`}
        descricao="O estúdio continua entrando, mas vê um aviso de pagamento em atraso. Para bloquear o acesso, use “Inativo” na ficha."
        confirmar="Suspender"
        carregando={status.isPending}
        onConfirm={() => status.mutate("suspenso", { onSuccess: () => setSuspender(false) })}
      />
    </div>
  );
}
