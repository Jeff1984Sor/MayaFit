"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { MessageCircle, Plus, Target, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { CrmNav, OrigemTag, TemperaturaBadge, useOpcoesCrm } from "@/components/crm/comum";
import { LeadDialog } from "@/components/crm/dialogos";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar, linhaClicavel } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { moeda, relativo, toNum } from "@/lib/format";
import type { ListaLeads, OrigemLead } from "@/lib/tipos-crm";
import { cn } from "@/lib/utils";

type Situacao = "abertos" | "ganhos" | "perdidos" | "todos";

export default function LeadsPage() {
  const { pode } = useAuth();
  const router = useRouter();
  const opcoes = useOpcoesCrm();
  const [q, setQ] = useState("");
  const [situacao, setSituacao] = useState<Situacao>("abertos");
  const [etapa, setEtapa] = useState("");
  const [origem, setOrigem] = useState<OrigemLead | "">("");
  const [resp, setResp] = useState("");
  const [tag, setTag] = useState("");
  const [ordem, setOrdem] = useState("recentes");
  const [pagina, setPagina] = useState(1);
  const [novo, setNovo] = useState(false);
  const busca = useDebounce(q, 300);

  const lista = useQuery({
    queryKey: ["crm", "leads", busca, situacao, etapa, origem, resp, tag, ordem, pagina],
    queryFn: () =>
      api.get<ListaLeads>("/crm/leads", {
        q: busca,
        situacao,
        etapa_id: etapa || undefined,
        origem: origem || undefined,
        responsavel_id: resp || undefined,
        tag: tag || undefined,
        ordem,
        pagina,
        por_pagina: 25,
      }),
    placeholderData: keepPreviousData,
    enabled: pode("crm.ver"),
  });

  if (!pode("crm.ver")) return <SemAcesso titulo="Leads" />;
  const d = lista.data;
  const etapas = new Map((opcoes.data?.etapas ?? []).map((e) => [e.id, e]));
  const filtrando = !!(busca || etapa || origem || resp || tag);
  const reset = (fn: () => void) => {
    fn();
    setPagina(1);
  };

  return (
    <div>
      <PageHeader
        icone={Target}
        titulo="Leads"
        descricao="Todos os interessados, com filtros por etapa, origem, responsável e tag."
        acoes={
          pode("crm.editar") && (
            <Button onClick={() => setNovo(true)}>
              <Plus /> Novo lead
            </Button>
          )
        }
      />
      <CrmNav />
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
            <SearchInput value={q} onChange={(v) => reset(() => setQ(v))} placeholder="Nome, telefone, e-mail ou interesse" />
            <Segmented<Situacao>
              value={situacao}
              onChange={(v) => reset(() => setSituacao(v))}
              opcoes={[
                { value: "abertos", label: "Abertos", contagem: d?.contagens.abertos },
                { value: "ganhos", label: "Matriculados", contagem: d?.contagens.ganhos, tom: "success" },
                { value: "perdidos", label: "Perdidos", contagem: d?.contagens.perdidos, tom: "danger" },
                { value: "todos", label: "Todos", contagem: d?.contagens.todos },
              ]}
            />
          </div>
        </Toolbar>
        <div className="grid grid-cols-2 gap-2 border-b px-4 pb-3 sm:grid-cols-3 lg:grid-cols-5">
          <NativeSelect value={etapa} onChange={(e) => reset(() => setEtapa(e.target.value))} aria-label="Etapa">
            <option value="">Todas as etapas</option>
            {(opcoes.data?.etapas ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.nome}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect value={origem} onChange={(e) => reset(() => setOrigem(e.target.value as OrigemLead | ""))} aria-label="Origem">
            <option value="">Todas as origens</option>
            {(opcoes.data?.origens ?? []).map((o) => (
              <option key={o.valor} value={o.valor}>
                {o.rotulo}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect value={resp} onChange={(e) => reset(() => setResp(e.target.value))} aria-label="Responsável">
            <option value="">Todos os responsáveis</option>
            {(opcoes.data?.usuarios ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect value={tag} onChange={(e) => reset(() => setTag(e.target.value))} aria-label="Tag">
            <option value="">Todas as tags</option>
            {(opcoes.data?.tags ?? []).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect value={ordem} onChange={(e) => reset(() => setOrdem(e.target.value))} aria-label="Ordenar">
            <option value="recentes">Mais recentes</option>
            <option value="antigos">Mais antigos</option>
            <option value="nome">Nome</option>
            <option value="valor">Maior valor</option>
            <option value="contato">Sem contato há mais tempo</option>
          </NativeSelect>
        </div>

        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : !d || d.itens.length === 0 ? (
          <EmptyState
            icone={Target}
            titulo={filtrando ? "Nenhum lead com esses filtros" : "Nenhum lead por aqui"}
            descricao={filtrando ? "Tente limpar algum filtro." : "Quando alguém demonstrar interesse, cadastre como lead e acompanhe até a matrícula."}
            acao={
              filtrando ? (
                <Button
                  variant="outline"
                  onClick={() =>
                    reset(() => {
                      setQ("");
                      setEtapa("");
                      setOrigem("");
                      setResp("");
                      setTag("");
                    })
                  }
                >
                  Limpar filtros
                </Button>
              ) : (
                pode("crm.editar") && (
                  <Button onClick={() => setNovo(true)}>
                    <Plus /> Novo lead
                  </Button>
                )
              )
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Lead</th>
                    <th className="px-3 py-2.5 font-medium">Etapa</th>
                    <th className="hidden px-3 py-2.5 font-medium md:table-cell">Origem</th>
                    <th className="hidden px-3 py-2.5 font-medium lg:table-cell">Responsável</th>
                    <th className="hidden px-3 py-2.5 font-medium sm:table-cell">Último contato</th>
                    <th className="hidden px-3 py-2.5 text-right font-medium md:table-cell">Valor</th>
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {d.itens.map((l) => {
                    const e = etapas.get(l.etapa_id);
                    return (
                      <tr
                        key={l.id}
                        tabIndex={0}
                        onClick={() => router.push(`/crm/leads/${l.id}`)}
                        onKeyDown={(ev) => ev.key === "Enter" && router.push(`/crm/leads/${l.id}`)}
                        className={cn(linhaClicavel, "focus-visible:bg-accent/40 focus-visible:outline-none")}
                      >
                        <td className="px-4 py-3">
                          <Link href={`/crm/leads/${l.id}`} onClick={(ev) => ev.stopPropagation()} className="block">
                            <span className="flex items-center gap-2 font-medium">
                              {l.nome}
                              {l.situacao === "ABERTO" && <TemperaturaBadge t={l.temperatura} compacto />}
                              {l.tarefa_atrasada && <TriangleAlert className="size-3.5 text-danger" aria-label="Tarefa atrasada" />}
                            </span>
                            <span className="text-xs text-muted-foreground">{l.telefone_formatado ?? l.email ?? "sem contato"}</span>
                          </Link>
                        </td>
                        <td className="px-3 py-3">
                          {l.situacao === "GANHO" ? (
                            <Pill tom="success">{e?.nome ?? "Matriculado"}</Pill>
                          ) : l.situacao === "PERDIDO" ? (
                            <Pill tom="danger">{e?.nome ?? "Perdido"}</Pill>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 text-xs">
                              <span className="size-2 rounded-full" style={{ background: e?.cor }} />
                              {e?.nome}
                              <span className={cn("text-muted-foreground", l.parado && "font-medium text-danger-ink")}>· {l.dias_na_etapa}d</span>
                            </span>
                          )}
                        </td>
                        <td className="hidden px-3 py-3 md:table-cell">
                          <OrigemTag origem={l.origem} />
                        </td>
                        <td className="hidden px-3 py-3 text-muted-foreground lg:table-cell">{l.responsavel?.nome ?? "Equipe"}</td>
                        <td className="hidden px-3 py-3 text-muted-foreground sm:table-cell">{relativo(l.ultima_interacao_em)}</td>
                        <td className="hidden px-3 py-3 text-right num md:table-cell">{l.valor_estimado && toNum(l.valor_estimado) > 0 ? moeda(l.valor_estimado) : "—"}</td>
                        <td className="px-2 py-3">
                          {l.whatsapp_url && (
                            <a
                              href={l.whatsapp_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(ev) => ev.stopPropagation()}
                              className="grid size-8 place-items-center rounded-full text-[#1A8F5E] hover:bg-[#1A8F5E]/10"
                              aria-label={`WhatsApp de ${l.nome}`}
                            >
                              <MessageCircle className="size-4" />
                            </a>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination pagina={d.pagina} porPagina={d.por_pagina} total={d.total} onChange={setPagina} />
          </>
        )}
      </TableCard>
      {novo && <LeadDialog aberto onFechar={() => setNovo(false)} etapaInicial={opcoes.data?.etapas.find((e) => e.tipo === "ABERTA")?.id} />}
    </div>
  );
}
