"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, FileCheck2, KeyRound, ScanFace, ShieldAlert, ShieldCheck, Smartphone, Trash2, Wand2, XCircle } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { CapturaRosto } from "@/components/acesso/captura-rosto";
import { hora, MetodoTag, ResultadoPill } from "@/components/acesso/comum";
import type { Captura } from "@/components/acesso/motor-facial";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { linhaClicavel, Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field } from "@/components/mayacorp/form";
import { Pill } from "@/components/mayacorp/status-badge";
import { UserAvatar } from "@/components/mayacorp/user-avatar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora, numero } from "@/lib/format";
import type { AlunoAcessoDetalhe, ConfigAcesso, Decisao, ListaAlunosAcesso } from "@/lib/tipos-acesso";
import { cn } from "@/lib/utils";

type Filtro = "todos" | "com_biometria" | "sem_biometria";

export function Biometria() {
  const params = useSearchParams();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [pagina, setPagina] = useState(1);
  const [aberto, setAberto] = useState<number | null>(() => Number(params.get("aluno")) || null);

  const lista = useQuery({
    queryKey: ["acesso", "alunos", q, filtro, pagina],
    queryFn: () => api.get<ListaAlunosAcesso>("/acesso/alunos", { q, situacao: filtro, pagina, por_pagina: 20 }),
    placeholderData: keepPreviousData,
  });
  const d = lista.data;

  const abrir = (id: number | null) => {
    setAberto(id);
    router.replace(id ? `/acesso/biometria?aluno=${id}` : "/acesso/biometria", { scroll: false });
  };

  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="card-surface flex items-center gap-3 p-4">
          <ShieldCheck className="size-8 text-success" />
          <div>
            <p className="text-2xl font-semibold num">{numero(d?.com_biometria ?? 0)}</p>
            <p className="text-xs text-muted-foreground">alunos ativos com rosto cadastrado</p>
          </div>
        </div>
        <div className="card-surface flex items-center gap-3 p-4">
          <KeyRound className="size-8 text-muted-foreground" />
          <div>
            <p className="text-2xl font-semibold num">{numero(d?.sem_biometria ?? 0)}</p>
            <p className="text-xs text-muted-foreground">entram por CPF/código + PIN ou QR do app</p>
          </div>
        </div>
        <div className="card-surface flex items-start gap-3 p-4 text-xs text-muted-foreground">
          <ShieldAlert className="size-8 shrink-0 text-warning" />
          <p>
            Biometria é dado <b>sensível</b> (LGPD, art. 11): só com consentimento do aluno. Nenhuma foto é guardada; apenas números cifrados, que podem ser
            apagados a qualquer momento.
          </p>
        </div>
      </div>
      <TableCard>
        <Toolbar>
          <SearchInput
            value={q}
            onChange={(v) => {
              setQ(v);
              setPagina(1);
            }}
            placeholder="Nome, CPF ou código"
          />
          <Segmented
            value={filtro}
            onChange={(v) => {
              setFiltro(v);
              setPagina(1);
            }}
            opcoes={[
              { value: "todos", label: "Todos" },
              { value: "com_biometria", label: "Com rosto", tom: "success" },
              { value: "sem_biometria", label: "Sem rosto", tom: "warning" },
            ]}
          />
        </Toolbar>
        {lista.isLoading ? (
          <TableSkeleton colunas={4} />
        ) : !d?.itens.length ? (
          <EmptyState icone={ScanFace} titulo="Nenhum aluno encontrado" descricao="Só alunos ativos aparecem aqui. Confira a busca ou o filtro." />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Aluno</TableHead>
                  <TableHead>Rosto</TableHead>
                  <TableHead>Consentimento</TableHead>
                  <TableHead>PIN</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d.itens.map((a) => (
                  <TableRow key={a.id} className={linhaClicavel} onClick={() => abrir(a.id)}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <UserAvatar nome={a.nome} fotoUrl={a.foto_url} className="size-8" />
                        <div>
                          <p className="font-medium">{a.nome}</p>
                          <p className="text-xs text-muted-foreground">
                            {a.cpf ?? "sem CPF"} {a.codigo ? `· código ${a.codigo}` : ""}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>{a.descritores ? <Pill tom="success">{a.descritores} leitura(s)</Pill> : <Pill tom="neutral">não cadastrado</Pill>}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {a.consentimento ? `${dataHora(a.consentimento.coletado_em)} · ${a.consentimento.coletado_por_nome.split(" (")[0]}` : "—"}
                    </TableCell>
                    <TableCell>{a.pin_definido ? <Pill tom="brand">definido</Pill> : <span className="text-xs text-muted-foreground">—</span>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pagination pagina={pagina} porPagina={20} total={d.total} onChange={setPagina} />
          </>
        )}
      </TableCard>
      <FichaAcesso key={aberto ?? 0} alunoId={aberto} onClose={() => abrir(null)} />
    </>
  );
}

function FichaAcesso({ alunoId, onClose }: { alunoId: number | null; onClose: () => void }) {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const podeEditar = pode("acesso.configurar");
  const ficha = useQuery({
    queryKey: ["acesso", "aluno", alunoId],
    queryFn: () => api.get<AlunoAcessoDetalhe>(`/acesso/alunos/${alunoId}`),
    enabled: !!alunoId,
  });
  const decisao = useQuery({
    queryKey: ["acesso", "aluno", alunoId, "decisao"],
    queryFn: () => api.get<Decisao>(`/acesso/alunos/${alunoId}/decisao`),
    enabled: !!alunoId,
    refetchInterval: 30000,
  });
  const config = useQuery({ queryKey: ["acesso", "config"], queryFn: () => api.get<ConfigAcesso>("/acesso/config"), enabled: !!alunoId });

  const [leuTermo, setLeuTermo] = useState(false);
  const [camera, setCamera] = useState(false);
  const [apagar, setApagar] = useState(false);
  const [motivoApagar, setMotivoApagar] = useState("");
  const [pin, setPin] = useState("");
  const [codigo, setCodigo] = useState<{ codigo: string; expira_em: string } | null>(null);

  const recarregar = () => qc.invalidateQueries({ queryKey: ["acesso"] });
  const consentir = useMutation({ mutationFn: () => api.post(`/acesso/alunos/${alunoId}/consentimento`, { aceite: true }), onSuccess: () => { toast.success("Consentimento registrado."); recarregar(); } });
  const salvarRosto = async (c: Captura) => {
    await api.post(`/acesso/alunos/${alunoId}/descritores`, { descritores: c.descritores, qualidade: Math.round(c.qualidade * 100) / 100, prova_vida: c.prova_vida });
    toast.success("Rosto cadastrado. Já pode entrar pelo totem!");
    recarregar();
  };
  const apagarBio = useMutation({
    mutationFn: () => api.post<{ mensagem: string }>(`/acesso/alunos/${alunoId}/biometria/apagar`, { motivo: motivoApagar }),
    onSuccess: (r) => {
      toast.success(r.mensagem);
      setApagar(false);
      setMotivoApagar("");
      recarregar();
    },
  });
  const apagarUm = useMutation({ mutationFn: (id: number) => api.del(`/acesso/alunos/${alunoId}/descritores/${id}`), onSuccess: recarregar });
  const salvarPin = useMutation({ mutationFn: () => api.put(`/acesso/alunos/${alunoId}/pin`, { pin }), onSuccess: () => { toast.success("PIN definido. Entregue ao aluno."); setPin(""); recarregar(); } });
  const removerPin = useMutation({ mutationFn: () => api.del(`/acesso/alunos/${alunoId}/pin`), onSuccess: () => { toast.success("PIN removido."); recarregar(); } });
  const gerarCodigo = useMutation({ mutationFn: () => api.post<{ codigo: string; expira_em: string }>(`/acesso/alunos/${alunoId}/codigo-totem`), onSuccess: setCodigo });

  const f = ficha.data;
  const dec = decisao.data;
  return (
    <Sheet open={!!alunoId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl!">
        <SheetHeader className="border-b">
          <SheetTitle className="flex items-center gap-3">
            {f && <UserAvatar nome={f.nome} fotoUrl={f.foto_url} className="size-10" />}
            {f?.nome ?? "Carregando…"}
          </SheetTitle>
          <SheetDescription>{f ? `${f.cpf ?? "sem CPF"}${f.codigo ? ` · código ${f.codigo}` : ""}` : ""}</SheetDescription>
        </SheetHeader>
        {f && (
          <div className="space-y-6 px-4 pb-8">
            {/* o que o totem diria agora */}
            {dec && (
              <div className={cn("rounded-2xl p-4 text-white shadow-md", dec.permitido ? "bg-linear-to-br from-success to-teal-700" : "bg-linear-to-br from-danger to-rose-800")}>
                <p className="text-xs tracking-wide uppercase opacity-80">Se chegasse agora no totem</p>
                <p className="mt-1 flex items-center gap-2 text-lg font-semibold">
                  {dec.permitido ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
                  {dec.permitido ? "Entrada liberada" : "Entrada negada"}
                </p>
                <p className="text-sm opacity-90">{dec.motivo}</p>
                {dec.aula && <p className="mt-1 text-xs opacity-80">{dec.aula}</p>}
                {dec.avisos.map((a) => (
                  <p key={a} className="mt-1 text-xs opacity-90">⚠ {a}</p>
                ))}
              </div>
            )}

            <section>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <FileCheck2 className="size-4" /> Consentimento (LGPD)
              </h3>
              {f.consentimento ? (
                <div className="rounded-xl border border-success/30 bg-success/5 p-3 text-sm">
                  <p>
                    Aceito em <b>{dataHora(f.consentimento.coletado_em)}</b>, coletado por <b>{f.consentimento.coletado_por_nome}</b> ({f.consentimento.canal === "totem" ? "no totem" : "na recepção"}).
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">Versão do termo: {f.consentimento.hash_termo.slice(0, 12)}</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="max-h-44 overflow-y-auto rounded-xl border bg-muted/40 p-3 text-xs whitespace-pre-line">{f.termo_atual}</div>
                  {podeEditar && (
                    <>
                      <label className="flex items-start gap-2 text-sm">
                        <Checkbox checked={leuTermo} onCheckedChange={(v) => setLeuTermo(!!v)} />
                        <span>O aluno leu o termo acima e concorda com o uso da biometria facial.</span>
                      </label>
                      <Button disabled={!leuTermo || consentir.isPending} onClick={() => consentir.mutate()}>
                        <FileCheck2 /> Registrar consentimento
                      </Button>
                    </>
                  )}
                </div>
              )}
            </section>

            <section>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <ScanFace className="size-4" /> Rosto
              </h3>
              {f.lista_descritores.length ? (
                <ul className="mb-3 divide-y rounded-xl border">
                  {f.lista_descritores.map((d, i) => (
                    <li key={d.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                      <span>
                        Leitura {i + 1} · {d.origem === "totem" ? "no totem" : "na recepção"} · {dataHora(d.criado_em)}
                        {d.qualidade != null && <span className="text-xs text-muted-foreground"> · qualidade {Math.round(d.qualidade * 100)}%</span>}
                      </span>
                      {podeEditar && (
                        <button type="button" onClick={() => apagarUm.mutate(d.id)} className="text-muted-foreground hover:text-danger" aria-label="Apagar leitura">
                          <Trash2 className="size-4" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mb-3 text-sm text-muted-foreground">Nenhum rosto cadastrado.</p>
              )}
              {podeEditar && (
                <div className="flex flex-wrap gap-2">
                  <Button disabled={!f.consentimento} onClick={() => setCamera(true)} title={!f.consentimento ? "Registre o consentimento antes" : undefined}>
                    <ScanFace /> {f.descritores ? "Adicionar leitura" : "Cadastrar rosto"}
                  </Button>
                  {(f.descritores > 0 || f.consentimento) && (
                    <Button variant="outline" className="text-danger-ink" onClick={() => setApagar(true)}>
                      <Trash2 /> Apagar biometria
                    </Button>
                  )}
                </div>
              )}
            </section>

            {podeEditar && (
              <section className="rounded-xl border p-4">
                <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold">
                  <Smartphone className="size-4" /> Cadastrar no próprio totem
                </h3>
                <p className="mb-3 text-xs text-muted-foreground">
                  Gere um código de uso único (vale 15 minutos). No totem, o aluno toca em “Cadastrar meu rosto”, digita CPF/código e este código, lê o termo e aceita.
                </p>
                {codigo ? (
                  <div className="flex items-center justify-between rounded-xl bg-brand/10 px-4 py-3">
                    <span className="font-mono text-3xl font-bold tracking-[0.3em]">{codigo.codigo}</span>
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="size-3" /> até {hora(codigo.expira_em)}
                    </span>
                  </div>
                ) : (
                  <Button variant="outline" onClick={() => gerarCodigo.mutate()} disabled={gerarCodigo.isPending}>
                    <Wand2 /> Gerar código para o totem
                  </Button>
                )}
              </section>
            )}

            <section>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <KeyRound className="size-4" /> PIN (entrada por CPF/código)
              </h3>
              <p className="mb-2 text-xs text-muted-foreground">
                Para quem não quer biometria. {f.pin_definido ? "Este aluno já tem PIN." : "Ainda sem PIN."} De 4 a 6 números, sem sequência (1234) nem repetição (1111).
              </p>
              {podeEditar && (
                <form
                  className="flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    salvarPin.mutate();
                  }}
                >
                  <Input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="Novo PIN" className="w-36 font-mono tracking-widest" autoComplete="off" />
                  <Button type="submit" variant="outline" disabled={pin.length < 4 || salvarPin.isPending}>
                    {f.pin_definido ? "Trocar PIN" : "Definir PIN"}
                  </Button>
                  {f.pin_definido && (
                    <Button type="button" variant="ghost" onClick={() => removerPin.mutate()}>
                      Remover
                    </Button>
                  )}
                </form>
              )}
            </section>

            <section>
              <h3 className="mb-2 text-sm font-semibold">Últimos acessos</h3>
              {f.ultimos_acessos.length ? (
                <ul className="divide-y rounded-xl border">
                  {f.ultimos_acessos.map((r) => (
                    <li key={r.id} className="px-3 py-2 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <span className="num">{dataHora(r.em)}</span>
                        <ResultadoPill r={r} />
                      </div>
                      <div className="mt-0.5 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                        <span className="truncate">{r.motivo}</span>
                        <MetodoTag metodo={r.metodo} />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Ainda não entrou pelo controle de acesso.</p>
              )}
            </section>

            {f.historico_consentimentos.some((c) => c.revogado_em) && (
              <section>
                <h3 className="mb-2 text-sm font-semibold">Histórico de consentimentos</h3>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {f.historico_consentimentos.map((c) => (
                    <li key={c.id}>
                      {dataHora(c.coletado_em)} — aceito ({c.coletado_por_nome})
                      {c.revogado_em && ` · revogado em ${dataHora(c.revogado_em)} por ${c.revogado_por_nome}: ${c.motivo_revogacao}`}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
        <CapturaRosto open={camera} onOpenChange={setCamera} nome={f?.nome ?? ""} exigirProvaVida={config.data?.exigir_prova_vida ?? true} onCapturado={salvarRosto} />
        <ConfirmDialog
          open={apagar}
          onOpenChange={setApagar}
          titulo="Apagar a biometria?"
          descricao="Todas as leituras do rosto serão apagadas na hora e o consentimento fica revogado. O aluno continua entrando por CPF/código + PIN ou QR do app."
          confirmar="Apagar biometria"
          destrutivo
          carregando={apagarBio.isPending}
          desabilitado={motivoApagar.trim().length < 3}
          onConfirm={() => apagarBio.mutate()}
        >
          <Field label="Motivo" obrigatorio>
            <Textarea value={motivoApagar} onChange={(e) => setMotivoApagar(e.target.value)} placeholder="Ex.: pedido do aluno" rows={2} />
          </Field>
        </ConfirmDialog>
      </SheetContent>
    </Sheet>
  );
}
