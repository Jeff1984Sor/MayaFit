"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardList, FilePlus2, FileText, HandCoins, Landmark, ReceiptText, Settings, Wallet } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { KpiCard } from "@/components/mayacorp/kpi-card";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar, linhaClicavel } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { BarraValidade, CertificadoResumo, ListaPendencias, ModoPill, StatusNotaBadge } from "@/components/nfse/comum";
import { GraficoNotas } from "@/components/nfse/grafico";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePaginado } from "@/hooks/use-paginado";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, documento, moeda, numero } from "@/lib/format";
import type { NotaResumo, PainelNfse, StatusNota } from "@/lib/tipos-nfse";

type Filtro = "" | "atencao" | StatusNota;

function Painel() {
  const { pode } = useAuth();
  const q = useQuery({ queryKey: ["nfse", "painel"], queryFn: () => api.get<PainelNfse>("/nfse/painel"), refetchInterval: 30_000 });
  const p = q.data;
  const mes = p ? new Date(`${p.mes}-01T00:00:00`).toLocaleDateString("pt-BR", { month: "long" }) : "";
  return (
    <div className="mb-6 grid gap-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard titulo={`Notas emitidas em ${mes}`} valor={numero(p?.notas_mes)} icone={FileText} carregando={q.isPending} indice={0} />
        <KpiCard titulo="Valor emitido no mês" valor={moeda(p?.valor_mes)} icone={Wallet} carregando={q.isPending} indice={1} />
        <KpiCard
          titulo={p?.iss_no_das ? "ISS estimado (dentro do DAS)" : "ISS estimado do mês"}
          valor={moeda(p?.iss_estimado_mes)}
          icone={Landmark}
          carregando={q.isPending}
          indice={2}
        />
        <KpiCard
          titulo="Pagos sem nota no mês"
          valor={
            <span>
              {numero(p?.recebimentos_sem_nota)}
              <span className="ml-2 text-sm font-normal text-muted-foreground">{moeda(p?.valor_sem_nota)}</span>
            </span>
          }
          icone={HandCoins}
          carregando={q.isPending}
          indice={3}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="card-surface p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Emitido nos últimos 6 meses</h3>
            {p && <ModoPill modo={p.modo} />}
          </div>
          {p ? <GraficoNotas serie={p.serie} /> : <Skeleton className="h-52 w-full" />}
        </div>
        <div className="card-surface flex flex-col gap-3 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Pendências</h3>
            {pode("nfse.configurar") && (
              <Button variant="ghost" size="sm" render={<Link href="/configuracoes/nfse" />}>
                <Settings /> Configuração fiscal
              </Button>
            )}
          </div>
          {p ? (
            <>
              <CertificadoResumo cert={p.certificado} compacto />
              <BarraValidade cert={p.certificado} />
              <div className="max-h-64 overflow-y-auto pr-1">
                <ListaPendencias itens={p.pendencias} />
              </div>
            </>
          ) : (
            <Skeleton className="h-40 w-full" />
          )}
        </div>
      </div>
    </div>
  );
}

function ListaComParametros() {
  const inicial = useSearchParams().get("status") ?? "";
  return <Lista key={inicial} inicial={inicial} />;
}

function Lista({ inicial }: { inicial: string }) {
  const router = useRouter();
  const lista = usePaginado<NotaResumo>("nfse", "/nfse/notas", { status: inicial }, 25);
  const contagens = (lista.data as unknown as { contagens?: Partial<Record<StatusNota, number>> } | undefined)?.contagens ?? {};
  const filtros = lista.filtros;
  const status = String(filtros.status ?? "") as Filtro;
  const atencao = (contagens.rejeitada ?? 0) + (contagens.falha ?? 0);
  return (
    <TableCard>
      <div className="border-b p-3">
        <Segmented<Filtro>
          value={status}
          onChange={(v) => lista.setFiltro("status", v)}
          opcoes={[
            { value: "", label: "Todas" },
            { value: "emitida", label: "Emitidas", contagem: contagens.emitida ?? 0, tom: "success" },
            { value: "atencao", label: "Precisam de atenção", contagem: atencao, tom: "danger" },
            { value: "pendente", label: "Na fila", contagem: contagens.pendente ?? 0, tom: "warning" },
            { value: "validada", label: "Validadas (teste)", contagem: contagens.validada ?? 0 },
            { value: "cancelada", label: "Canceladas", contagem: contagens.cancelada ?? 0 },
          ]}
        />
      </div>
      <Toolbar className="sm:flex-wrap sm:justify-start">
        <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Tomador, CPF/CNPJ ou nº da nota" />
        <NativeSelect value={String(filtros.origem ?? "")} onChange={(e) => lista.setFiltro("origem", e.target.value)} className="w-44" aria-label="Origem">
          <option value="">Todas as origens</option>
          <option value="recebimento">Recebimentos</option>
          <option value="automatica">Automáticas</option>
          <option value="avulsa">Avulsas</option>
        </NativeSelect>
        <Input type="date" aria-label="Competência de" value={String(filtros.de ?? "")} onChange={(e) => lista.setFiltro("de", e.target.value)} className="h-9 w-40" />
        <Input type="date" aria-label="Competência até" value={String(filtros.ate ?? "")} onChange={(e) => lista.setFiltro("ate", e.target.value)} className="h-9 w-40" />
      </Toolbar>
      {lista.isPending ? (
        <TableSkeleton colunas={6} />
      ) : lista.itens.length === 0 ? (
        <EmptyState
          icone={ReceiptText}
          titulo="Nenhuma nota por aqui"
          descricao="Emita a partir dos recebimentos pagos ou crie uma nota avulsa."
          acao={
            <Button render={<Link href="/nfse/recebimentos" />}>
              <HandCoins /> Emitir dos recebimentos
            </Button>
          }
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Nota</th>
                <th className="px-4 py-2.5 font-medium">Tomador</th>
                <th className="px-4 py-2.5 font-medium">Competência</th>
                <th className="px-4 py-2.5 text-right font-medium">Valor</th>
                <th className="px-4 py-2.5 text-right font-medium">ISS</th>
                <th className="px-4 py-2.5 font-medium">Situação</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {lista.itens.map((n) => (
                <tr key={n.id} className={linhaClicavel} onClick={() => router.push(`/nfse/${n.id}`)}>
                  <td className="px-4 py-3">
                    <p className="font-medium num">{n.numero_nfse ? `Nº ${n.numero_nfse}` : "—"}</p>
                    <p className="text-xs text-muted-foreground num">
                      DPS {n.serie}-{n.numero_dps}
                      {n.modo !== "producao" && " · teste"}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <p className="font-medium">{n.tomador_nome}</p>
                    <p className="text-xs text-muted-foreground num">{documento(n.tomador_documento)}</p>
                  </td>
                  <td className="px-4 py-3 num">{data(n.competencia).slice(3)}</td>
                  <td className="px-4 py-3 text-right font-medium num">{moeda(n.valor_servico)}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground num">{moeda(n.valor_iss)}</td>
                  <td className="px-4 py-3">
                    <StatusNotaBadge status={n.status} />
                    {n.erro_principal && (n.status === "rejeitada" || n.status === "falha" || n.status === "pendente") && (
                      <p className="mt-1 max-w-xs truncate text-xs text-muted-foreground" title={n.erro_principal}>
                        {n.erro_principal}
                      </p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination pagina={lista.pagina} porPagina={lista.porPagina} total={lista.total} onChange={lista.setPagina} />
    </TableCard>
  );
}

export default function NotasFiscaisPage() {
  const { pode } = useAuth();
  if (!pode("nfse.ver")) return <SemAcesso />;
  return (
    <div>
      <PageHeader
        titulo="Notas fiscais (NFS-e)"
        descricao="Painel do mês, fila de emissão e todas as notas de serviço do estúdio."
        icone={ClipboardList}
        migalhas={[{ label: "Início", href: "/" }, { label: "Financeiro" }, { label: "Notas fiscais" }]}
        acoes={
          pode("nfse.emitir") && (
            <>
              <Button variant="outline" render={<Link href="/nfse/recebimentos" />}>
                <HandCoins /> Emitir dos recebimentos
              </Button>
              <Button render={<Link href="/nfse/nova" />}>
                <FilePlus2 /> Nova nota
              </Button>
            </>
          )
        }
      />
      <Painel />
      <Suspense fallback={<TableSkeleton colunas={6} />}>
        <ListaComParametros />
      </Suspense>
    </div>
  );
}
