"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CheckCheck, ChevronLeft, ChevronRight, Inbox, Mail, MessageSquareText, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/mayacorp/empty-state";
import { Pill } from "@/components/mayacorp/status-badge";
import { IconeWhatsapp } from "@/components/site/icones";
import { linkWhatsapp } from "@/components/site/util";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { dataHora } from "@/lib/format";
import type { ContatoSite, ListaContatosSite } from "@/lib/tipos-site";
import { cn } from "@/lib/utils";

const POR_PAGINA = 20;

/** Histórico dos contatos que chegaram pelo formulário do site (o CRM recebe o lead; aqui fica o registro). */
export function ContatosSite({ publicado, podeEditar, onPublicar }: { publicado: boolean; podeEditar: boolean; onPublicar: () => void }) {
  const qc = useQueryClient();
  const [pagina, setPagina] = useState(1);
  const q = useQuery({
    queryKey: ["site", "contatos", pagina],
    queryFn: () => api.get<ListaContatosSite>("/site/contatos", { pagina, por_pagina: POR_PAGINA }),
    placeholderData: keepPreviousData,
  });
  const atualizar = () => {
    qc.invalidateQueries({ queryKey: ["site", "contatos"] });
    qc.invalidateQueries({ queryKey: ["site", "editor"] });
  };
  const lido = useMutation({ mutationFn: (id: number) => api.post(`/site/contatos/${id}/lido`), onSuccess: atualizar });
  const todos = useMutation({
    mutationFn: () => api.post("/site/contatos/lidos"),
    onSuccess: () => {
      toast.success("Tudo marcado como lido");
      atualizar();
    },
  });

  if (q.isPending) return <Skeleton className="h-64 rounded-2xl" />;
  const d = q.data;
  if (!d || d.total === 0)
    return (
      <div className="card-surface">
        <EmptyState
          icone={Inbox}
          titulo="Nenhum contato ainda"
          descricao={
            publicado
              ? "Quando alguém pedir uma aula experimental pelo site, o contato aparece aqui e vira lead no CRM. Divulgue o link no Instagram e no WhatsApp!"
              : "Publique o site para começar a receber pedidos de aula experimental."
          }
          acao={
            !publicado && podeEditar ? (
              <Button onClick={onPublicar}>
                <Send /> Publicar o site
              </Button>
            ) : undefined
          }
        />
      </div>
    );

  const paginas = Math.max(1, Math.ceil(d.total / POR_PAGINA));
  return (
    <div className="card-surface overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <p className="text-sm text-muted-foreground">
          <strong className="text-foreground">{d.total}</strong> contato(s) · {d.nao_lidos} não lido(s)
        </p>
        {podeEditar && d.nao_lidos > 0 && (
          <Button variant="outline" size="sm" onClick={() => todos.mutate()} disabled={todos.isPending}>
            <CheckCheck /> Marcar todos como lidos
          </Button>
        )}
      </div>
      <ul className="divide-y">
        {d.itens.map((c) => (
          <Item key={c.id} c={c} onLer={() => podeEditar && !c.lido && lido.mutate(c.id)} />
        ))}
      </ul>
      {paginas > 1 && (
        <div className="flex items-center justify-end gap-2 border-t px-4 py-2 text-sm">
          <Button variant="ghost" size="icon-sm" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)} aria-label="Página anterior">
            <ChevronLeft />
          </Button>
          <span className="tabular-nums">
            {pagina} / {paginas}
          </span>
          <Button variant="ghost" size="icon-sm" disabled={pagina >= paginas} onClick={() => setPagina((p) => p + 1)} aria-label="Próxima página">
            <ChevronRight />
          </Button>
        </div>
      )}
    </div>
  );
}

function Item({ c, onLer }: { c: ContatoSite; onLer: () => void }) {
  const whats = c.telefone ? linkWhatsapp(c.telefone, `Olá, ${c.nome.split(" ")[0]}! Recebemos seu contato pelo site.`) : null;
  return (
    <li className={cn("flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start", !c.lido && "bg-brand/5")} onClick={onLer}>
      <span className={cn("mt-2 hidden size-2 shrink-0 rounded-full sm:block", c.lido ? "bg-transparent" : "bg-brand")} aria-label={c.lido ? undefined : "Não lido"} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{c.nome}</span>
          {c.quer_aula_experimental && (
            <Pill tom="brand">
              <CalendarCheck className="size-3" /> Aula experimental
            </Pill>
          )}
          {c.interesse && <Pill>{c.interesse}</Pill>}
          <Pill tom={c.enviado_crm ? "success" : "neutral"}>{c.enviado_crm ? "No CRM" : "Só no site"}</Pill>
        </div>
        {c.mensagem && (
          <p className="mt-1 flex gap-1.5 text-sm text-muted-foreground">
            <MessageSquareText className="mt-0.5 size-3.5 shrink-0" />
            <span className="line-clamp-3 whitespace-pre-line">{c.mensagem}</span>
          </p>
        )}
        <p className="mt-1 text-xs text-muted-foreground">{dataHora(c.criado_em)}</p>
      </div>
      <div className="flex shrink-0 gap-2">
        {whats && (
          <Button size="sm" variant="outline" render={<a href={whats} target="_blank" rel="noopener noreferrer" />}>
            <IconeWhatsapp className="size-3.5 text-[#25D366]" /> {c.telefone}
          </Button>
        )}
        {c.email && (
          <Button size="sm" variant="ghost" render={<a href={`mailto:${c.email}`} />} aria-label={`E-mail para ${c.email}`}>
            <Mail />
          </Button>
        )}
      </div>
    </li>
  );
}
