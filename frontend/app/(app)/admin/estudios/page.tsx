"use client";

import { Building2, Plus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { EstudioDialog } from "@/components/admin/estudio-dialog";
import { Medidor } from "@/components/admin/medidor";
import { linhaClicavel, Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { useDebounce } from "@/hooks/use-debounce";
import { useEstudios, usePlanos, useResumoAdmin } from "@/lib/admin";
import { data, documento, moeda, toNum } from "@/lib/format";
import { ROTULO_STATUS, type StatusEstudio, TOM_STATUS } from "@/lib/tipos-admin";

const POR_PAGINA = 20;
const STATUS = ["teste", "ativo", "suspenso", "inativo"] as const;

function EstudiosConteudo() {
  const router = useRouter();
  const inicial = useSearchParams().get("status");
  const [q, setQ] = useState("");
  const busca = useDebounce(q, 300);
  const [status, setStatus] = useState<StatusEstudio | "todos">(STATUS.includes(inicial as StatusEstudio) ? (inicial as StatusEstudio) : "todos");
  const [plano, setPlano] = useState("");
  const [pagina, setPagina] = useState(1);
  const [novo, setNovo] = useState(false);
  const resumo = useResumoAdmin();
  const planos = usePlanos();
  const lista = useEstudios({ q: busca, status: status === "todos" ? undefined : status });
  // a API filtra por busca e situação; o plano e a paginação ficam aqui (a carteira é pequena)
  const filtrados = (lista.data ?? []).filter((e) => !plano || (plano === "sem" ? !e.plano_id : String(e.plano_id) === plano));
  const itens = filtrados.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA);
  const ps = resumo.data?.por_status ?? {};
  const filtrando = !!busca || status !== "todos" || !!plano;

  return (
    <div>
      <PageHeader
        titulo="Estúdios"
        descricao="Os clientes do MayaFit: ficha, plano, uso, domínios e acesso."
        icone={Building2}
        migalhas={[{ label: "MayaCorp", href: "/admin" }, { label: "Estúdios" }]}
        acoes={
          <Button onClick={() => setNovo(true)}>
            <Plus /> Novo estúdio
          </Button>
        }
      />

      <TableCard>
        <Toolbar>
          <SearchInput
            value={q}
            onChange={(v) => {
              setQ(v);
              setPagina(1);
            }}
            placeholder="Nome, identificador ou CNPJ"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Segmented
              value={status}
              onChange={(v) => {
                setStatus(v);
                setPagina(1);
              }}
              opcoes={[
                { value: "todos", label: "Todos" },
                { value: "teste", label: "Em teste", contagem: resumo.data ? (ps.teste ?? 0) : undefined },
                { value: "ativo", label: "Ativos", tom: "success", contagem: resumo.data ? (ps.ativo ?? 0) : undefined },
                { value: "suspenso", label: "Suspensos", tom: "warning", contagem: resumo.data ? (ps.suspenso ?? 0) : undefined },
                { value: "inativo", label: "Inativos", contagem: resumo.data ? (ps.inativo ?? 0) : undefined },
              ]}
            />
            <NativeSelect
              aria-label="Filtrar por plano"
              value={plano}
              onChange={(e) => {
                setPlano(e.target.value);
                setPagina(1);
              }}
              className="w-40"
            >
              <option value="">Todos os planos</option>
              {planos.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
              <option value="sem">Sem plano</option>
            </NativeSelect>
          </div>
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : filtrados.length === 0 ? (
          <EmptyState
            icone={Building2}
            titulo={filtrando ? "Nenhum estúdio encontrado" : "Nenhum estúdio ainda"}
            descricao={
              filtrando
                ? "Tente outra busca ou limpe os filtros."
                : "Cada estúdio ganha um banco próprio e o dono recebe o link para criar o usuário master."
            }
            acao={
              !filtrando && (
                <Button onClick={() => setNovo(true)}>
                  <Plus /> Novo estúdio
                </Button>
              )
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Estúdio</th>
                    <th className="px-3 py-2.5 font-medium">Plano</th>
                    <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                    <th className="px-3 py-2.5 font-medium">Alunos ativos</th>
                    <th className="px-3 py-2.5 font-medium">Endereço</th>
                    <th className="px-3 py-2.5 font-medium">Situação</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {itens.map((e) => (
                    <tr key={e.id} className={linhaClicavel} onClick={() => router.push(`/admin/estudios/${e.id}`)}>
                      <td className="max-w-72 px-4 py-3">
                        <p className="truncate font-medium">{e.nome}</p>
                        <p className="truncate font-mono text-[11px] text-muted-foreground">
                          {e.slug}
                          {e.documento && ` · ${documento(e.documento)}`}
                        </p>
                      </td>
                      <td className="px-3 py-3">
                        {e.plano ? (
                          <>
                            {e.plano.nome} <span className="text-xs text-muted-foreground">· {e.ciclo}</span>
                          </>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right">
                        <span className="num">{e.valor ? moeda(e.valor_com_desconto ?? e.valor) : "—"}</span>
                        {toNum(e.desconto_percentual) > 0 && (
                          <p className="text-[11px] text-success-ink">−{toNum(e.desconto_percentual)}% indicação</p>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <Medidor compacto usado={e.uso?.alunos_ativos} limite={e.plano?.alunos_ativos} />
                      </td>
                      <td className="max-w-48 truncate px-3 py-3 font-mono text-xs">{e.dominios[0]?.host ?? "—"}</td>
                      <td className="px-3 py-3">
                        <Pill tom={TOM_STATUS[e.status]}>{ROTULO_STATUS[e.status]}</Pill>
                        {e.status === "teste" && e.teste_ate && <p className="num mt-0.5 text-[11px] text-muted-foreground">até {data(e.teste_ate)}</p>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination pagina={pagina} porPagina={POR_PAGINA} total={filtrados.length} onChange={setPagina} />
          </>
        )}
      </TableCard>

      <EstudioDialog open={novo} onOpenChange={setNovo} onSalvo={(c) => router.push(`/admin/estudios/${c.id}`)} />
    </div>
  );
}

export default function EstudiosPage() {
  return (
    <Suspense>
      <EstudiosConteudo />
    </Suspense>
  );
}
