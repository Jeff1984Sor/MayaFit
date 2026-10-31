"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, Inbox, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { copiarTexto, DIAS_TESTE_PADRAO, valorDoCiclo } from "@/lib/admin";
import { api } from "@/lib/api";
import { dataHora, documento, moeda, numero } from "@/lib/format";
import { type Estudio, ROTULO_SOLICITACAO, type Solicitacao, type StatusSolicitacao } from "@/lib/tipos-admin";

const POR_PAGINA = 20;
const linkCadastro = () => (typeof window === "undefined" ? "/cadastro" : `${window.location.origin}/cadastro`);

/** Cadastros feitos no formulário público "Quero o MayaFit", esperando aprovação. */
export default function SolicitacoesPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const [status, setStatus] = useState<StatusSolicitacao | "todas">("nova");
  const [q, setQ] = useState("");
  const [pagina, setPagina] = useState(1);
  const [aprovar, setAprovar] = useState<Solicitacao | null>(null);
  const [recusar, setRecusar] = useState<Solicitacao | null>(null);
  const [dias, setDias] = useState(String(DIAS_TESTE_PADRAO));
  const [slug, setSlug] = useState("");
  const lista = useQuery({
    queryKey: ["admin", "solicitacoes", status],
    queryFn: () => api.get<Solicitacao[]>("/admin/solicitacoes", { status: status === "todas" ? undefined : status }),
  });
  const termo = q.trim().toLowerCase();
  const filtradas = (lista.data ?? []).filter(
    (s) => !termo || [s.nome, s.responsavel, s.email, s.documento ?? ""].some((x) => x.toLowerCase().includes(termo)),
  );
  const itens = filtradas.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA);

  const ok = useMutation({
    mutationFn: () =>
      api.post<Estudio>(`/admin/solicitacoes/${aprovar!.id}/aprovar`, { dias_teste: Number(dias) || null, slug: slug.trim().toLowerCase() || null }),
    onSuccess: (c) => {
      toast.success(`Estúdio ${c.nome} criado. Enviamos o link de primeiro acesso.`, {
        action: c.convite ? { label: "Copiar link", onClick: () => copiarTexto(c.convite!) } : undefined,
        duration: 15000,
      });
      setAprovar(null);
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  const nao = useMutation({
    mutationFn: () => api.post(`/admin/solicitacoes/${recusar!.id}/recusar`),
    onSuccess: () => {
      toast.success("Solicitação recusada");
      setRecusar(null);
      qc.invalidateQueries({ queryKey: ["admin", "solicitacoes"] });
    },
  });

  return (
    <div>
      <PageHeader
        titulo="Solicitações"
        descricao="Pedidos feitos no formulário público. Aprovar cria o estúdio com teste grátis."
        icone={Inbox}
        migalhas={[{ label: "Admin MayaFit", href: "/admin" }, { label: "Solicitações" }]}
        acoes={
          <>
            <Button variant="outline" render={<a href="/cadastro" target="_blank" rel="noopener noreferrer" />}>
              <ExternalLink /> Ver formulário
            </Button>
            <Button variant="outline" onClick={() => copiarTexto(linkCadastro(), "Link do formulário copiado")}>
              <Copy /> Copiar link
            </Button>
          </>
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
            placeholder="Estúdio, responsável, e-mail ou CNPJ"
          />
          <Segmented
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPagina(1);
            }}
            opcoes={[
              { value: "nova", label: "Novas", tom: "warning" },
              { value: "aprovada", label: "Aprovadas", tom: "success" },
              { value: "recusada", label: "Recusadas" },
              { value: "todas", label: "Todas" },
            ]}
          />
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={5} />
        ) : !filtradas.length ? (
          <EmptyState
            icone={Inbox}
            titulo={termo ? "Nenhuma solicitação encontrada" : status === "nova" ? "Nenhuma solicitação nova" : "Nenhuma solicitação"}
            descricao="Os pedidos feitos no formulário “Quero o MayaFit” aparecem aqui para você aprovar ou recusar."
            acao={
              <Button variant="outline" onClick={() => copiarTexto(linkCadastro(), "Link do formulário copiado")}>
                <Copy /> Copiar link do formulário
              </Button>
            }
          />
        ) : (
          <>
            <div className="divide-y">
              {itens.map((s) => (
                <div key={s.id} className="flex flex-wrap items-start gap-4 px-4 py-4 text-sm">
                  <div className="min-w-60 flex-1 space-y-0.5">
                    <p className="font-medium">
                      {s.nome} {s.documento && <span className="num text-xs text-muted-foreground">{documento(s.documento)}</span>}
                    </p>
                    <p className="text-muted-foreground">
                      {s.responsavel} · {s.email}
                      {s.telefone && (
                        <>
                          {" "}
                          · <span className="num">{s.telefone}</span>
                        </>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {s.plano ? (
                        <>
                          {s.plano.nome} ({s.ciclo}) · <span className="num">{moeda(valorDoCiclo(s.plano, s.ciclo))}</span>
                        </>
                      ) : (
                        "Plano a definir"
                      )}
                      {s.alunos ? ` · ${numero(s.alunos)} aluno(s) ativo(s) hoje` : ""}
                      {s.indicacao ? ` · indicação: ${s.indicacao}` : ""}
                    </p>
                    {s.mensagem && <p className="mt-1 rounded-lg bg-muted/50 p-2 text-xs whitespace-pre-line">{s.mensagem}</p>}
                    <p className="num text-xs text-muted-foreground">{dataHora(s.criado_em)}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill tom={ROTULO_SOLICITACAO[s.status][1]}>{ROTULO_SOLICITACAO[s.status][0]}</Pill>
                    {s.status === "nova" && (
                      <>
                        <Button
                          size="sm"
                          onClick={() => {
                            setDias(String(DIAS_TESTE_PADRAO));
                            setSlug("");
                            setAprovar(s);
                          }}
                        >
                          <Check /> Aprovar
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setRecusar(s)}>
                          <X /> Recusar
                        </Button>
                      </>
                    )}
                    {s.cliente_id && (
                      <Button size="sm" variant="outline" onClick={() => router.push(`/admin/estudios/${s.cliente_id}`)}>
                        Abrir estúdio
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <Pagination pagina={pagina} porPagina={POR_PAGINA} total={filtradas.length} onChange={setPagina} />
          </>
        )}
      </TableCard>

      <FormDialog
        open={!!aprovar}
        onOpenChange={(o) => !o && setAprovar(null)}
        titulo={`Aprovar ${aprovar?.nome ?? ""}`}
        descricao="Cria o estúdio com o usuário Suporte e envia ao dono o link para criar o usuário master."
        rotuloSalvar="Aprovar e criar estúdio"
        salvando={ok.isPending}
        onSubmit={(e) => {
          e.preventDefault();
          ok.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Dias de teste grátis" htmlFor="apr-dias" dica="Padrão: 60 dias (2 meses). Vazio = já entra ativo.">
            <Input id="apr-dias" type="number" min={1} max={90} value={dias} onChange={(e) => setDias(e.target.value)} className="num" />
          </Field>
          <Field label="Identificador" htmlFor="apr-slug" dica="Opcional; gerado pelo nome.">
            <Input id="apr-slug" value={slug} onChange={(e) => setSlug(e.target.value.toLowerCase())} className="font-mono" placeholder="studio-ana" />
          </Field>
        </div>
      </FormDialog>
      <ConfirmDialog
        open={!!recusar}
        onOpenChange={(o) => !o && setRecusar(null)}
        titulo={`Recusar ${recusar?.nome ?? ""}?`}
        descricao="A solicitação sai da lista de novas. Nenhum e-mail é enviado."
        confirmar="Recusar"
        destrutivo
        carregando={nao.isPending}
        onConfirm={() => nao.mutate()}
      />
    </div>
  );
}
