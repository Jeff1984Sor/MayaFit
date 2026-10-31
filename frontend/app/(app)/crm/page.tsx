"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Globe, Plus, Target } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { CrmNav, useOpcoesCrm } from "@/components/crm/comum";
import { LeadDialog } from "@/components/crm/dialogos";
import { ResumoFunil } from "@/components/crm/indicadores";
import { Kanban } from "@/components/crm/kanban";
import { SearchInput } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Funil, OrigemLead } from "@/lib/tipos-crm";

export default function FunilPage() {
  const { pode, usuario } = useAuth();
  const opcoes = useOpcoesCrm();
  const [q, setQ] = useState("");
  const [resp, setResp] = useState<string>("");
  const [origem, setOrigem] = useState<OrigemLead | "">("");
  const [novo, setNovo] = useState<{ etapa?: number } | null>(null);
  const busca = useDebounce(q, 250);
  const raiz = useRef<HTMLDivElement>(null);
  const podeEditar = pode("crm.editar");

  const chave = ["crm", "funil", busca, resp, origem] as const;
  const funil = useQuery({
    queryKey: chave,
    queryFn: () => api.get<Funil>("/crm/funil", { q: busca, responsavel_id: resp || undefined, origem: origem || undefined }),
    placeholderData: keepPreviousData,
    enabled: pode("crm.ver"),
  });

  // atalhos: N = novo lead · / = buscar
  useEffect(() => {
    function tecla(e: KeyboardEvent) {
      const alvo = e.target as HTMLElement;
      if (alvo.closest("input, textarea, select, [contenteditable], [role=dialog]")) return;
      if (e.key === "n" && podeEditar && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setNovo({});
      } else if (e.key === "/") {
        e.preventDefault();
        raiz.current?.querySelector<HTMLInputElement>("input[type=search], input")?.focus();
      }
    }
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [podeEditar]);

  if (!pode("crm.ver")) return <SemAcesso titulo="CRM de vendas" />;

  const total = funil.data?.colunas.reduce((s, c) => s + c.total, 0) ?? 0;
  const filtrando = !!(busca || resp || origem);

  return (
    <div>
      <PageHeader
        icone={Target}
        titulo="Funil de vendas"
        descricao="Acompanhe cada interessado do primeiro contato até a matrícula. Arraste os cartões entre as etapas."
        acoes={
          podeEditar && (
            <Button onClick={() => setNovo({})}>
              <Plus /> Novo lead <kbd className="ml-1 hidden rounded border border-white/30 px-1 text-[10px] sm:inline">N</kbd>
            </Button>
          )
        }
      />
      <CrmNav />
      <ResumoFunil />

      <div ref={raiz} className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <SearchInput value={q} onChange={setQ} placeholder="Buscar nome, telefone ou interesse  ( / )" className="sm:w-80" />
        <NativeSelect value={resp} onChange={(e) => setResp(e.target.value)} className="sm:w-52" aria-label="Responsável">
          <option value="">Todos os responsáveis</option>
          {usuario && <option value={usuario.id}>Só os meus</option>}
          {(opcoes.data?.usuarios ?? [])
            .filter((u) => u.id !== usuario?.id)
            .map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
        </NativeSelect>
        <NativeSelect value={origem} onChange={(e) => setOrigem(e.target.value as OrigemLead | "")} className="sm:w-44" aria-label="Origem">
          <option value="">Todas as origens</option>
          {(opcoes.data?.origens ?? []).map((o) => (
            <option key={o.valor} value={o.valor}>
              {o.rotulo}
            </option>
          ))}
        </NativeSelect>
      </div>

      {funil.isPending ? (
        <div className="flex gap-3 overflow-hidden">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-80 w-72 shrink-0 rounded-2xl" />
          ))}
        </div>
      ) : total === 0 && !filtrando ? (
        <div className="card-surface">
          <EmptyState
            icone={Target}
            titulo="Seu funil está pronto para receber interessados"
            descricao={
              <>
                Cadastre quem ligou, mandou mensagem no Instagram ou passou na porta. Os contatos do formulário do site entram aqui sozinhos,
                com a tarefa de primeiro contato já criada.
              </>
            }
            acao={
              podeEditar && (
                <div className="flex flex-wrap justify-center gap-2">
                  <Button onClick={() => setNovo({})}>
                    <Plus /> Cadastrar o primeiro lead
                  </Button>
                  <Button variant="outline" disabled title="O formulário do site é configurado no módulo do site do estúdio">
                    <Globe /> Formulário do site
                  </Button>
                </div>
              )
            }
          />
        </div>
      ) : (
        funil.data && <Kanban funil={funil.data} chave={chave} podeEditar={podeEditar} onNovo={(etapa) => setNovo({ etapa })} />
      )}

      {novo && <LeadDialog aberto onFechar={() => setNovo(null)} etapaInicial={novo.etapa ?? opcoes.data?.etapas.find((e) => e.tipo === "ABERTA")?.id} />}
    </div>
  );
}
