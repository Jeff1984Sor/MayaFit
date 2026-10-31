"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, HandCoins, Loader2, Send } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Achado, StatusNotaBadge, hojeIso } from "@/components/nfse/comum";
import { PainelRaioX } from "@/components/nfse/raio-x";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda } from "@/lib/format";
import type { LoteNfse, RaioX, RecebimentoNfse } from "@/lib/tipos-nfse";
import { cn } from "@/lib/utils";

type Situacao = "sem_nota" | "com_nota" | "todos";

function inicioDoMes() {
  const h = hojeIso();
  return `${h.slice(0, 8)}01`;
}

export default function EmitirRecebimentosPage() {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const [de, setDe] = useState(inicioDoMes());
  const [ate, setAte] = useState(hojeIso());
  const [situacao, setSituacao] = useState<Situacao>("sem_nota");
  const [q, setQ] = useState("");
  const busca = useDebounce(q, 300);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [resultado, setResultado] = useState<LoteNfse | null>(null);

  const lista = useQuery({
    queryKey: ["nfse", "recebimentos", de, ate, situacao, busca],
    queryFn: () => api.get<RecebimentoNfse[]>("/nfse/recebimentos", { de, ate, situacao, q: busca }),
  });
  const itens = useMemo(() => lista.data ?? [], [lista.data]);
  const elegiveis = itens.filter((i) => !i.nota_id && !i.problema);
  const ids = useMemo(() => [...sel].sort((a, b) => a - b), [sel]);
  const idsDebounced = useDebounce(ids, 400);
  const total = itens.filter((i) => sel.has(i.id)).reduce((s, i) => s + Number(i.valor), 0);

  const raio = useQuery({
    queryKey: ["nfse", "raio-x", "recebimentos", idsDebounced],
    queryFn: () => api.post<RaioX>("/nfse/raio-x", { recebimentos: idsDebounced }),
    enabled: idsDebounced.length > 0,
  });

  const emitir = useMutation({
    mutationFn: () => api.post<LoteNfse>("/nfse/recebimentos/emitir", { ids }),
    onSuccess: (r) => {
      setResultado(r);
      setSel(new Set());
      qc.invalidateQueries({ queryKey: ["nfse"] });
      toast.success(`${r.criadas} nota(s) criadas${r.processadas_agora ? ` e ${r.processadas_agora} enviadas` : " (na fila)"}.`);
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Não foi possível emitir."),
  });

  if (!pode("nfse.emitir")) return <SemAcesso />;

  const alternar = (id: number) =>
    setSel((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const todosMarcados = elegiveis.length > 0 && elegiveis.every((i) => sel.has(i.id));

  return (
    <div>
      <PageHeader
        titulo="Emitir a partir dos recebimentos"
        descricao="Selecione recebimentos pagos e emita as notas em lote. Cada recebimento gera no máximo uma nota."
        icone={HandCoins}
        migalhas={[{ label: "Início", href: "/" }, { label: "Notas fiscais", href: "/nfse" }, { label: "Recebimentos" }]}
      />
      {resultado && (
        <div className="mb-4 grid gap-2">
          <Achado
            nivel={resultado.notas.some((n) => n.status === "rejeitada") ? "aviso" : "info"}
            titulo="Lote enviado"
            mensagem={`${resultado.criadas} nota(s) criada(s), ${resultado.ja_existiam} já existiam, ${resultado.ignoradas.length} ignorada(s).`}
            acao="Acompanhe na lista de notas"
            link="/nfse"
          />
          {resultado.ignoradas.slice(0, 5).map((i) => (
            <Achado key={i.id} nivel="aviso" mensagem={i.motivo} />
          ))}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <TableCard>
          <div className="border-b p-3">
            <Segmented<Situacao>
              value={situacao}
              onChange={(v) => {
                setSituacao(v);
                setSel(new Set());
              }}
              opcoes={[
                { value: "sem_nota", label: "Sem nota" },
                { value: "com_nota", label: "Com nota" },
                { value: "todos", label: "Todos os pagos" },
              ]}
            />
          </div>
          <Toolbar className="sm:flex-wrap sm:justify-start">
            <SearchInput value={q} onChange={setQ} placeholder="Nome do aluno" className="sm:w-60" />
            <Input type="date" aria-label="Pagos de" value={de} onChange={(e) => setDe(e.target.value)} className="h-9 w-40" />
            <Input type="date" aria-label="Pagos até" value={ate} onChange={(e) => setAte(e.target.value)} className="h-9 w-40" />
          </Toolbar>
          {lista.isPending ? (
            <TableSkeleton colunas={5} />
          ) : itens.length === 0 ? (
            <EmptyState
              icone={CircleCheck}
              titulo={situacao === "sem_nota" ? "Todos os recebimentos pagos já têm nota" : "Nenhum recebimento pago no período"}
              descricao="Ajuste o período ou a situação."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="w-10 px-4 py-2.5">
                      <Checkbox
                        checked={todosMarcados}
                        disabled={elegiveis.length === 0}
                        onCheckedChange={(v) => setSel(v ? new Set(elegiveis.map((i) => i.id)) : new Set())}
                        aria-label="Selecionar todos"
                      />
                    </th>
                    <th className="px-4 py-2.5 font-medium">Aluno</th>
                    <th className="px-4 py-2.5 font-medium">Descrição</th>
                    <th className="px-4 py-2.5 font-medium">Pago em</th>
                    <th className="px-4 py-2.5 text-right font-medium">Valor</th>
                    <th className="px-4 py-2.5 font-medium">Nota</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {itens.map((i) => {
                    const livre = !i.nota_id && !i.problema;
                    return (
                      <tr key={i.id} className={cn(sel.has(i.id) && "bg-brand/5", !livre && "opacity-80")}>
                        <td className="px-4 py-3">
                          <Checkbox checked={sel.has(i.id)} disabled={!livre} onCheckedChange={() => alternar(i.id)} aria-label={`Selecionar ${i.aluno_nome}`} />
                        </td>
                        <td className="px-4 py-3">
                          <p className="font-medium">{i.aluno_nome}</p>
                          <p className={cn("text-xs num", i.problema ? "text-danger-ink" : "text-muted-foreground")}>
                            {i.problema ?? i.aluno_cpf}
                          </p>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{i.descricao ?? "—"}</td>
                        <td className="px-4 py-3 num">{data(i.pagamento)}</td>
                        <td className="px-4 py-3 text-right font-medium num">{moeda(i.valor)}</td>
                        <td className="px-4 py-3">
                          {i.nota_id && i.nota_status ? (
                            <Link href={`/nfse/${i.nota_id}`} className="inline-flex items-center gap-2">
                              <StatusNotaBadge status={i.nota_status} />
                              {i.nota_numero && <span className="text-xs num">nº {i.nota_numero}</span>}
                            </Link>
                          ) : i.problema ? (
                            <Link href={`/alunos/${i.aluno_id}`} className="text-xs font-medium text-info-ink hover:underline">
                              Corrigir cadastro
                            </Link>
                          ) : (
                            <span className="text-xs text-muted-foreground">sem nota</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </TableCard>
        <div className="flex h-fit flex-col gap-4 lg:sticky lg:top-4">
          <div className="card-surface p-4">
            <p className="text-xs text-muted-foreground">Selecionados</p>
            <p className="text-2xl font-semibold num">
              {sel.size} <span className="text-base font-normal text-muted-foreground">· {moeda(total)}</span>
            </p>
            <Button className="mt-3 w-full" disabled={sel.size === 0 || emitir.isPending || (raio.data && !raio.data.pode_emitir)} onClick={() => emitir.mutate()}>
              {emitir.isPending ? <Loader2 className="animate-spin" /> : <Send />}
              Emitir {sel.size > 0 ? `${sel.size} nota(s)` : "notas"}
            </Button>
            {sel.size > 10 && <p className="mt-2 text-xs text-muted-foreground">Lotes com mais de 10 notas seguem pela fila automática (em instantes).</p>}
          </div>
          <PainelRaioX raio={sel.size ? raio.data : undefined} carregando={raio.isFetching} />
        </div>
      </div>
    </div>
  );
}
