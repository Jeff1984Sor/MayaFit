"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Plus, ScrollText } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { linhaClicavel, Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { data, dataHora } from "@/lib/format";
import { type ContratoEstudio, type ModeloContrato, ROTULO_CONTRATO, type Rotulo, type StatusContrato } from "@/lib/tipos-admin";

const POR_PAGINA = 20;

// Ponto de partida de um modelo novo. Os valores saem da ficha do estúdio pelas {{variáveis}}; nada de preço fixo aqui.
const EXEMPLO = `CONTRATO DE LICENÇA DE USO DO MAYAFIT

CONTRATANTE: {{cliente_nome}}, inscrito no CNPJ/CPF {{cliente_documento}}, neste ato representado por {{responsavel}}.

CONTRATADA: MayaCorp.

1. OBJETO. Licença de uso do sistema MayaFit no plano {{plano}}, com até {{alunos_ativos}} alunos ativos e {{usuarios}} usuários.

2. PREÇO. Cobrança {{ciclo}} de R$ {{valor}}. Aluno ativo acima do limite: R$ {{aluno_excedente}} por mês. Usuário adicional: R$ {{usuario_adicional}} por mês.

3. VIGÊNCIA. A partir de {{data_inicio}}, por prazo indeterminado.

São Paulo, {{data_hoje}}.`;

function ContratosConteudo() {
  const modelos = useQuery({ queryKey: ["admin", "modelos"], queryFn: () => api.get<ModeloContrato[]>("/admin/modelos-contrato") });
  const [edit, setEdit] = useState<{ m: ModeloContrato | null } | null>(null);
  const [aba, setAba] = useState(useSearchParams().get("aba") === "modelos" ? "modelos" : "contratos");
  return (
    <div>
      <PageHeader
        titulo="Contratos"
        descricao="Os contratos gerados para os estúdios e os modelos de onde eles saem."
        icone={ScrollText}
        migalhas={[{ label: "Admin MayaFit", href: "/admin" }, { label: "Contratos" }]}
        acoes={
          <Button onClick={() => setEdit({ m: null })}>
            <Plus /> Novo modelo
          </Button>
        }
      />
      <Tabs value={aba} onValueChange={(v) => setAba(String(v))}>
        <TabsList>
          <TabsTrigger value="contratos">Contratos dos estúdios</TabsTrigger>
          <TabsTrigger value="modelos">Modelos</TabsTrigger>
        </TabsList>
        <TabsContent value="contratos" className="mt-4">
          <ContratosGerados irParaModelos={() => setAba("modelos")} />
        </TabsContent>
        <TabsContent value="modelos" className="mt-4">
          <TableCard>
            {modelos.isPending ? (
              <TableSkeleton colunas={3} />
            ) : !modelos.data?.length ? (
              <EmptyState
                icone={ScrollText}
                titulo="Nenhum modelo de contrato"
                descricao="Escreva o contrato uma vez com {{variáveis}}; na ficha do estúdio ele sai preenchido, em PDF, pronto para enviar."
                acao={
                  <Button onClick={() => setEdit({ m: null })}>
                    <Plus /> Novo modelo
                  </Button>
                }
              />
            ) : (
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Modelo</th>
                    <th className="px-3 py-2.5 font-medium">Atualizado</th>
                    <th className="px-3 py-2.5 font-medium">Situação</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {modelos.data.map((m) => (
                    <tr key={m.id} className={linhaClicavel} onClick={() => setEdit({ m })}>
                      <td className="px-4 py-3 font-medium">
                        {m.nome}
                        {m.variaveis_desconhecidas.length > 0 && (
                          <span className="ml-2 inline-flex items-center gap-1 text-xs text-warning-ink">
                            <AlertTriangle className="size-3" /> variável desconhecida
                          </span>
                        )}
                      </td>
                      <td className="num px-3 py-3 text-xs">{dataHora(m.atualizado_em)}</td>
                      <td className="px-3 py-3">
                        <Pill tom={m.ativo ? "success" : "neutral"}>{m.ativo ? "Ativo" : "Inativo"}</Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </TableCard>
        </TabsContent>
      </Tabs>
      <ModeloDialog edit={edit} onClose={() => setEdit(null)} />
    </div>
  );
}

export default function ContratosPage() {
  return (
    <Suspense>
      <ContratosConteudo />
    </Suspense>
  );
}

function ContratosGerados({ irParaModelos }: { irParaModelos: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusContrato | "todos">("todos");
  const [pagina, setPagina] = useState(1);
  const lista = useQuery({ queryKey: ["admin", "contratos", "todos"], queryFn: () => api.get<ContratoEstudio[]>("/admin/contratos") });
  const termo = q.trim().toLowerCase();
  const filtrados = (lista.data ?? []).filter(
    (k) => (status === "todos" || k.status === status) && (!termo || `${k.cliente_nome ?? ""} ${k.titulo}`.toLowerCase().includes(termo)),
  );
  const itens = filtrados.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA);
  const conta = (s: StatusContrato) => (lista.data ?? []).filter((k) => k.status === s).length;
  return (
    <TableCard>
      <Toolbar>
        <SearchInput
          value={q}
          onChange={(v) => {
            setQ(v);
            setPagina(1);
          }}
          placeholder="Estúdio ou título"
        />
        <Segmented
          value={status}
          onChange={(v) => {
            setStatus(v);
            setPagina(1);
          }}
          opcoes={[
            { value: "todos", label: "Todos" },
            { value: "rascunho", label: "Rascunhos", contagem: lista.data ? conta("rascunho") : undefined },
            { value: "enviado", label: "Enviados", tom: "warning", contagem: lista.data ? conta("enviado") : undefined },
            { value: "assinado", label: "Assinados", tom: "success", contagem: lista.data ? conta("assinado") : undefined },
            { value: "cancelado", label: "Cancelados" },
          ]}
        />
      </Toolbar>
      {lista.isPending ? (
        <TableSkeleton colunas={5} />
      ) : !filtrados.length ? (
        <EmptyState
          icone={ScrollText}
          titulo={termo || status !== "todos" ? "Nenhum contrato encontrado" : "Nenhum contrato gerado"}
          descricao="Abra o estúdio, aba Contratos, e gere a partir de um modelo: os dados da ficha entram sozinhos."
          acao={
            <Button variant="outline" onClick={irParaModelos}>
              Ver modelos
            </Button>
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Estúdio</th>
                  <th className="px-3 py-2.5 font-medium">Contrato</th>
                  <th className="px-3 py-2.5 font-medium">Gerado</th>
                  <th className="px-3 py-2.5 font-medium">Enviado</th>
                  <th className="px-3 py-2.5 font-medium">Situação</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {itens.map((k) => (
                  <tr key={k.id} className={linhaClicavel} onClick={() => router.push(`/admin/estudios/${k.cliente_id}?aba=contratos`)}>
                    <td className="px-4 py-3 font-medium">{k.cliente_nome}</td>
                    <td className="px-3 py-3">{k.titulo}</td>
                    <td className="num px-3 py-3 text-xs">{data(k.criado_em)}</td>
                    <td className="px-3 py-3 text-xs">
                      {k.enviado_em ? (
                        <>
                          <span className="num">{dataHora(k.enviado_em)}</span>
                          <p className="truncate text-muted-foreground">{k.enviado_para.join(", ")}</p>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <Pill tom={ROTULO_CONTRATO[k.status][1]}>{ROTULO_CONTRATO[k.status][0]}</Pill>
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
  );
}

function ModeloDialog({ edit, onClose }: { edit: { m: ModeloContrato | null } | null; onClose: () => void }) {
  const qc = useQueryClient();
  const vars = useQuery({ queryKey: ["admin", "variaveis"], queryFn: () => api.get<Rotulo[]>("/admin/contratos/variaveis"), enabled: !!edit });
  const [f, setF] = useState({ nome: "", corpo: "", ativo: true });
  const texto = useRef<HTMLTextAreaElement>(null);
  /* eslint-disable react-hooks/set-state-in-effect -- carrega o formulário ao abrir */
  useEffect(() => {
    if (edit) setF(edit.m ? { nome: edit.m.nome, corpo: edit.m.corpo, ativo: edit.m.ativo } : { nome: "Contrato de licença MayaFit", corpo: EXEMPLO, ativo: true });
  }, [edit]);
  /* eslint-enable react-hooks/set-state-in-effect */
  const salvar = useMutation({
    mutationFn: () => (edit?.m ? api.put<ModeloContrato>(`/admin/modelos-contrato/${edit.m.id}`, f) : api.post<ModeloContrato>("/admin/modelos-contrato", f)),
    onSuccess: (m) => {
      if (m.variaveis_desconhecidas.length) toast.warning(`Variáveis que o sistema não conhece: ${m.variaveis_desconhecidas.join(", ")}`);
      else toast.success("Modelo salvo");
      qc.invalidateQueries({ queryKey: ["admin", "modelos"] });
      onClose();
    },
  });
  const inserir = (chave: string) => {
    const el = texto.current;
    const tag = `{{${chave}}}`;
    if (!el) return setF((o) => ({ ...o, corpo: o.corpo + tag }));
    const ini = el.selectionStart ?? f.corpo.length;
    const fim = el.selectionEnd ?? ini;
    setF((o) => ({ ...o, corpo: o.corpo.slice(0, ini) + tag + o.corpo.slice(fim) }));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(ini + tag.length, ini + tag.length);
    });
  };
  return (
    <FormDialog
      open={!!edit}
      onOpenChange={(o) => !o && onClose()}
      titulo={edit?.m ? edit.m.nome : "Novo modelo de contrato"}
      descricao="Clique numa variável para inserir no ponto do cursor. Ela é trocada pelos dados da ficha do estúdio."
      largura="xl"
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        if (f.nome.trim().length < 2) return toast.error("Informe o nome do modelo.");
        if (f.corpo.trim().length < 10) return toast.error("Escreva o texto do contrato.");
        salvar.mutate();
      }}
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
        <div className="grid gap-4">
          <Field label="Nome do modelo" obrigatorio htmlFor="mod-nome">
            <Input id="mod-nome" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} />
          </Field>
          <Field label="Texto" obrigatorio htmlFor="mod-corpo" dica="Deixe uma linha em branco entre os parágrafos.">
            <Textarea ref={texto} id="mod-corpo" rows={20} value={f.corpo} onChange={(e) => setF({ ...f, corpo: e.target.value })} className="font-mono text-xs" />
          </Field>
          <SwitchRow titulo="Modelo ativo" descricao="Só modelos ativos aparecem para gerar contratos.">
            <Switch checked={f.ativo} onCheckedChange={(v) => setF({ ...f, ativo: v })} aria-label="Modelo ativo" />
          </SwitchRow>
        </div>
        <div>
          <p className="mb-2 text-[13px] text-foreground/80">Variáveis</p>
          <div className="flex flex-wrap gap-1.5 lg:flex-col">
            {vars.data?.map((v) => (
              <button
                key={v.chave}
                type="button"
                onClick={() => inserir(v.chave)}
                className="rounded-md border px-2 py-1 text-left text-xs transition hover:border-brand/50 hover:bg-brand/5"
                title={`{{${v.chave}}}`}
              >
                {v.rotulo}
              </button>
            ))}
          </div>
        </div>
      </div>
    </FormDialog>
  );
}
