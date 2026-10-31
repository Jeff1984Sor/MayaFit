"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, DoorOpen, KeyRound, MonitorSmartphone, Pencil, Plug, Plus, RefreshCw, Router, ShieldOff, Trash2, TriangleAlert } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { acionarNesteNavegador, CatracaPill } from "@/components/acesso/comum";
import { DialogoLiberar } from "@/components/acesso/dialogo-liberar";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { SenhaInput } from "@/components/mayacorp/senha-input";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativo } from "@/lib/format";
import type { Catraca, Dispositivo, OpcoesAcesso, TesteCatraca } from "@/lib/tipos-acesso";
import { ROTULO_MODO } from "@/lib/tipos-acesso";

export function Equipamentos() {
  return (
    <Tabs defaultValue="catracas">
      <TabsList>
        <TabsTrigger value="catracas">
          <Router /> Catracas
        </TabsTrigger>
        <TabsTrigger value="totens">
          <MonitorSmartphone /> Totens e agentes
        </TabsTrigger>
      </TabsList>
      <TabsContent value="catracas" className="mt-4">
        <Catracas />
      </TabsContent>
      <TabsContent value="totens" className="mt-4">
        <Dispositivos />
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------------------------------- catracas
type FormCatraca = Omit<Catraca, "id" | "unidade_nome" | "senha_definida" | "senha_final" | "ultimo_teste_em" | "ultimo_teste_ok" | "ultimo_teste_detalhe"> & { senha: string };

const VAZIA: FormCatraca = {
  nome: "",
  unidade_id: null,
  driver: "controlid",
  modo: "totem",
  host: "",
  porta: 80,
  usar_https: false,
  usuario: "admin",
  senha: "",
  sentido_entrada: "clockwise",
  acao_liberacao: "catra",
  porta_rele: 1,
  ativo: true,
};

function Catracas() {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const configurar = pode("acesso.configurar");
  const lista = useQuery({ queryKey: ["acesso", "catracas"], queryFn: () => api.get<Catraca[]>("/acesso/catracas") });
  const opcoes = useQuery({ queryKey: ["acesso", "opcoes"], queryFn: () => api.get<OpcoesAcesso>("/acesso/opcoes") });
  const [edit, setEdit] = useState<{ id: number | null; f: FormCatraca } | null>(null);
  const [excluir, setExcluir] = useState<Catraca | null>(null);
  const [liberar, setLiberar] = useState<number | null>(null);
  const [testando, setTestando] = useState<number | null>(null);

  const salvar = useMutation({
    mutationFn: ({ id, f }: { id: number | null; f: FormCatraca }) => {
      const corpo = { ...f, host: f.host || null, usuario: f.usuario || null, senha: f.senha || null, porta: f.porta || null };
      return id ? api.put<Catraca>(`/acesso/catracas/${id}`, corpo) : api.post<Catraca>("/acesso/catracas", corpo);
    },
    onSuccess: () => {
      toast.success("Catraca salva.");
      setEdit(null);
      qc.invalidateQueries({ queryKey: ["acesso"] });
    },
  });
  const remover = useMutation({
    mutationFn: (id: number) => api.del(`/acesso/catracas/${id}`),
    onSuccess: () => {
      setExcluir(null);
      qc.invalidateQueries({ queryKey: ["acesso"] });
    },
  });

  const testar = async (c: Catraca) => {
    setTestando(c.id);
    try {
      const r = await api.post<TesteCatraca>(`/acesso/catracas/${c.id}/testar`);
      if (r.ok === null && r.acionamento?.plano) await acionarNesteNavegador({ ...r.acionamento, status: "pendente" }, `/acesso/catracas/${c.id}/teste-navegador`);
      else if (r.ok) toast.success(r.mensagem);
      else if (r.ok === false) toast.error(r.mensagem);
      else toast.info(r.mensagem);
    } finally {
      setTestando(null);
      qc.invalidateQueries({ queryKey: ["acesso", "catracas"] });
    }
  };

  const f = edit?.f;
  const set = (p: Partial<FormCatraca>) => setEdit((e) => (e ? { ...e, f: { ...e.f, ...p } } : e));
  const atual = edit?.id ? lista.data?.find((c) => c.id === edit.id) : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-sm text-muted-foreground">
          O sistema fica na nuvem e a catraca na rede do estúdio. Escolha quem a aciona: o <b>navegador do totem</b> (mais simples), o <b>agente local</b> (programa
          leve no computador da recepção) ou o <b>servidor</b> (se a catraca for alcançável pela internet/VPN).
        </p>
        {configurar && (
          <Button onClick={() => setEdit({ id: null, f: { ...VAZIA } })}>
            <Plus /> Nova catraca
          </Button>
        )}
      </div>
      {lista.data && lista.data.length === 0 ? (
        <div className="card-surface">
          <EmptyState
            icone={Router}
            titulo="Nenhuma catraca cadastrada"
            descricao="Sem catraca, o totem só registra a entrada e a presença. Para testar sem equipamento, cadastre uma catraca “Simulada”."
            acao={configurar ? <Button onClick={() => setEdit({ id: null, f: { ...VAZIA, nome: "Catraca de teste", driver: "simulado", host: "" } })}>Cadastrar catraca simulada</Button> : undefined}
          />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {lista.data?.map((c) => (
            <div key={c.id} className="card-surface flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{c.nome}</p>
                  <p className="text-xs text-muted-foreground">
                    {opcoes.data?.drivers.find((d) => d.nome === c.driver)?.rotulo ?? c.driver}
                    {c.unidade_nome ? ` · ${c.unidade_nome}` : ""}
                  </p>
                </div>
                {!c.ativo ? <Pill tom="neutral">inativa</Pill> : <CatracaPill status={c.ultimo_teste_ok == null ? null : c.ultimo_teste_ok ? "liberada" : "falhou"} detalhe={c.ultimo_teste_detalhe} />}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <dt className="text-muted-foreground">Endereço</dt>
                <dd className="truncate font-mono">{c.host ? `${c.usar_https ? "https" : "http"}://${c.host}${c.porta ? `:${c.porta}` : ""}` : "—"}</dd>
                <dt className="text-muted-foreground">Acionada</dt>
                <dd>{ROTULO_MODO[c.modo].split(" (")[0]}</dd>
                <dt className="text-muted-foreground">Senha</dt>
                <dd>{c.senha_definida ? `configurada${c.senha_final ? ` · …${c.senha_final}` : ""}` : "não configurada"}</dd>
                <dt className="text-muted-foreground">Último teste</dt>
                <dd title={c.ultimo_teste_detalhe ?? undefined}>{c.ultimo_teste_em ? relativo(c.ultimo_teste_em) : "nunca"}</dd>
              </dl>
              <div className="mt-4 flex flex-wrap gap-2 border-t pt-3">
                {configurar && (
                  <Button size="sm" variant="outline" onClick={() => testar(c)} disabled={testando === c.id}>
                    <Plug className={testando === c.id ? "animate-pulse" : undefined} /> Testar conexão
                  </Button>
                )}
                {pode("acesso.liberar_manual") && c.ativo && (
                  <Button size="sm" onClick={() => setLiberar(c.id)}>
                    <DoorOpen /> Liberar agora
                  </Button>
                )}
                {configurar && (
                  <>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label="Editar"
                      onClick={() =>
                        setEdit({
                          id: c.id,
                          f: { nome: c.nome, unidade_id: c.unidade_id, driver: c.driver, modo: c.modo, host: c.host ?? "", porta: c.porta, usar_https: c.usar_https, usuario: c.usuario ?? "", senha: "", sentido_entrada: c.sentido_entrada, acao_liberacao: c.acao_liberacao, porta_rele: c.porta_rele, ativo: c.ativo },
                        })
                      }
                    >
                      <Pencil />
                    </Button>
                    <Button size="icon-sm" variant="ghost" aria-label="Excluir" onClick={() => setExcluir(c)}>
                      <Trash2 />
                    </Button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {f && (
        <FormDialog
          open
          onOpenChange={(o) => !o && setEdit(null)}
          titulo={edit?.id ? "Editar catraca" : "Nova catraca"}
          descricao="Os dados de acesso ficam cifrados. A senha é somente escrita: deixe em branco para manter a atual."
          largura="lg"
          salvando={salvar.isPending}
          onSubmit={(e) => {
            e.preventDefault();
            salvar.mutate({ id: edit!.id, f });
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nome" obrigatorio>
              <Input value={f.nome} onChange={(e) => set({ nome: e.target.value })} required minLength={2} placeholder="Catraca da recepção" />
            </Field>
            <Field label="Unidade">
              <NativeSelect value={f.unidade_id ?? ""} onChange={(e) => set({ unidade_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Todas / única</option>
                {opcoes.data?.unidades.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nome}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Fabricante / driver">
              <NativeSelect value={f.driver} onChange={(e) => set({ driver: e.target.value as FormCatraca["driver"], modo: e.target.value === "henry" ? "agente" : f.modo })}>
                {opcoes.data?.drivers.map((d) => (
                  <option key={d.nome} value={d.nome}>
                    {d.rotulo}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Quem aciona a catraca" dica={f.modo === "totem" ? "O tablet do totem precisa estar na mesma rede da catraca." : f.modo === "agente" ? "Instale o agente (deploy/agente-catraca) num computador da recepção." : "A catraca precisa ser alcançável pelo servidor."}>
              <NativeSelect value={f.modo} onChange={(e) => set({ modo: e.target.value as FormCatraca["modo"] })}>
                {(Object.keys(ROTULO_MODO) as (keyof typeof ROTULO_MODO)[]).map((m) => (
                  <option key={m} value={m} disabled={f.driver === "henry" && m === "totem"}>
                    {ROTULO_MODO[m]}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {f.driver !== "simulado" && (
              <>
                <Field label="IP ou nome na rede local" obrigatorio>
                  <Input value={f.host ?? ""} onChange={(e) => set({ host: e.target.value.trim() })} placeholder="192.168.0.50" className="font-mono" />
                </Field>
                <Field label="Porta">
                  <Input type="number" min={1} max={65535} value={f.porta ?? ""} onChange={(e) => set({ porta: e.target.value ? Number(e.target.value) : null })} />
                </Field>
                <Field label="Usuário da catraca">
                  <Input value={f.usuario ?? ""} onChange={(e) => set({ usuario: e.target.value })} autoComplete="off" />
                </Field>
                <Field label="Senha da catraca" dica={atual?.senha_definida ? `Configurada${atual.senha_final ? ` (…${atual.senha_final})` : ""}. Em branco mantém.` : "Fica cifrada no banco."}>
                  <SenhaInput value={f.senha} onChange={(v) => set({ senha: v })} autoComplete="new-password" />
                </Field>
              </>
            )}
            <Field label="Para que lado gira para ENTRAR">
              <NativeSelect value={f.sentido_entrada} onChange={(e) => set({ sentido_entrada: e.target.value as FormCatraca["sentido_entrada"] })}>
                <option value="clockwise">Horário</option>
                <option value="anticlockwise">Anti-horário</option>
                <option value="both">Os dois (libera nos dois sentidos)</option>
              </NativeSelect>
            </Field>
            <Field label="Tipo de liberação">
              <NativeSelect value={f.acao_liberacao} onChange={(e) => set({ acao_liberacao: e.target.value as FormCatraca["acao_liberacao"] })}>
                <option value="catra">Catraca (giro, iDBlock)</option>
                <option value="door">Porta / relé (iDAccess, iDFlex, iDFace)</option>
              </NativeSelect>
            </Field>
            {f.acao_liberacao === "door" && (
              <Field label="Número do relé/porta">
                <Input type="number" min={1} max={8} value={f.porta_rele} onChange={(e) => set({ porta_rele: Number(e.target.value) || 1 })} />
              </Field>
            )}
            <div className="sm:col-span-2 grid gap-2">
              {f.driver !== "simulado" && (
                <SwitchRow titulo="Usar HTTPS" descricao="Necessário para o totem chamar a catraca a partir de uma página https (aceite o certificado no tablet).">
                  <Switch checked={f.usar_https} onCheckedChange={(v) => set({ usar_https: v })} />
                </SwitchRow>
              )}
              <SwitchRow titulo="Catraca ativa" descricao="Inativa: o totem só registra a entrada, sem acionar.">
                <Switch checked={f.ativo} onCheckedChange={(v) => set({ ativo: v })} />
              </SwitchRow>
            </div>
          </div>
        </FormDialog>
      )}
      <ConfirmDialog
        open={!!excluir}
        onOpenChange={(o) => !o && setExcluir(null)}
        titulo={`Excluir ${excluir?.nome}?`}
        descricao="Os totens ligados a ela passam a só registrar a entrada. O histórico continua."
        confirmar="Excluir"
        destrutivo
        carregando={remover.isPending}
        onConfirm={() => excluir && remover.mutate(excluir.id)}
      />
      <DialogoLiberar key={liberar ?? 0} open={liberar !== null} onOpenChange={(o) => !o && setLiberar(null)} catracaInicial={liberar} />
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- dispositivos
function Dispositivos() {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const configurar = pode("acesso.configurar");
  const lista = useQuery({ queryKey: ["acesso", "dispositivos"], queryFn: () => api.get<Dispositivo[]>("/acesso/dispositivos"), refetchInterval: 20000 });
  const opcoes = useQuery({ queryKey: ["acesso", "opcoes"], queryFn: () => api.get<OpcoesAcesso>("/acesso/opcoes") });
  const [novo, setNovo] = useState<{ nome: string; tipo: "totem" | "agente"; unidade_id: number | null; catraca_id: number | null } | null>(null);
  const [token, setToken] = useState<Dispositivo | null>(null);
  const [revogar, setRevogar] = useState<Dispositivo | null>(null);
  const invalidar = () => qc.invalidateQueries({ queryKey: ["acesso"] });

  const criar = useMutation({
    mutationFn: () => api.post<Dispositivo>("/acesso/dispositivos", novo),
    onSuccess: (d) => {
      setNovo(null);
      setToken(d);
      invalidar();
    },
  });
  const regenerar = useMutation({ mutationFn: (id: number) => api.post<Dispositivo>(`/acesso/dispositivos/${id}/regenerar`), onSuccess: (d) => { setToken(d); invalidar(); } });
  const revogarM = useMutation({ mutationFn: (id: number) => api.post(`/acesso/dispositivos/${id}/revogar`), onSuccess: () => { setRevogar(null); toast.success("Dispositivo revogado: o token deixou de valer."); invalidar(); } });
  const excluir = useMutation({ mutationFn: (id: number) => api.del(`/acesso/dispositivos/${id}`), onSuccess: invalidar });
  const vincular = useMutation({ mutationFn: ({ id, catraca_id }: { id: number; catraca_id: number | null }) => api.patch(`/acesso/dispositivos/${id}`, { catraca_id }), onSuccess: invalidar });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Cada totem (tablet ou notebook da recepção) é pareado com um <b>token próprio</b>, que pode ser revogado a qualquer momento. O token aparece uma única vez,
          como QR Code: aponte a câmera do tablet ou abra o link nele.
        </p>
        {configurar && (
          <Button onClick={() => setNovo({ nome: "Totem da recepção", tipo: "totem", unidade_id: null, catraca_id: opcoes.data?.catracas[0]?.id ?? null })}>
            <Plus /> Novo dispositivo
          </Button>
        )}
      </div>
      {lista.data && lista.data.length === 0 ? (
        <div className="card-surface">
          <EmptyState icone={MonitorSmartphone} titulo="Nenhum totem pareado" descricao="Cadastre o tablet da recepção para os alunos fazerem check-in pelo rosto, CPF ou QR do app." />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {lista.data?.map((d) => (
            <div key={d.id} className="card-surface p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="relative grid size-10 place-items-center rounded-xl bg-brand/10 text-navy dark:text-brand">
                    {d.tipo === "totem" ? <MonitorSmartphone className="size-5" /> : <Router className="size-5" />}
                    {d.online && <span className="absolute -top-0.5 -right-0.5 size-3 rounded-full bg-success ring-2 ring-card" />}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{d.nome}</p>
                    <p className="text-xs text-muted-foreground">{d.tipo === "totem" ? "Totem" : "Agente local"}{d.unidade_nome ? ` · ${d.unidade_nome}` : ""}</p>
                  </div>
                </div>
                {!d.ativo ? <Pill tom="danger">revogado</Pill> : d.online ? <Pill tom="success">online</Pill> : <Pill tom="neutral">offline</Pill>}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <dt className="text-muted-foreground">Último contato</dt>
                <dd>{d.ultimo_contato ? relativo(d.ultimo_contato) : "nunca"}</dd>
                <dt className="text-muted-foreground">Token</dt>
                <dd className="font-mono">{d.token_final ? `…${d.token_final}` : "não gerado"}</dd>
                {d.tipo === "totem" && (
                  <>
                    <dt className="self-center text-muted-foreground">Catraca</dt>
                    <dd>
                      {configurar ? (
                        <NativeSelect className="h-7 text-xs" value={d.catraca_id ?? ""} onChange={(e) => vincular.mutate({ id: d.id, catraca_id: e.target.value ? Number(e.target.value) : null })}>
                          <option value="">Nenhuma</option>
                          {opcoes.data?.catracas.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.nome}
                            </option>
                          ))}
                        </NativeSelect>
                      ) : (
                        (d.catraca_nome ?? "Nenhuma")
                      )}
                    </dd>
                  </>
                )}
              </dl>
              {configurar && (
                <div className="mt-4 flex flex-wrap gap-2 border-t pt-3">
                  <Button size="sm" variant="outline" onClick={() => regenerar.mutate(d.id)}>
                    {d.ativo ? <RefreshCw /> : <KeyRound />} {d.ativo ? "Gerar novo token" : "Reativar com novo token"}
                  </Button>
                  {d.ativo ? (
                    <Button size="sm" variant="ghost" className="text-danger-ink" onClick={() => setRevogar(d)}>
                      <ShieldOff /> Revogar
                    </Button>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => excluir.mutate(d.id)}>
                      <Trash2 /> Excluir
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {novo && (
        <FormDialog
          open
          onOpenChange={(o) => !o && setNovo(null)}
          titulo="Novo dispositivo"
          descricao="Ao salvar aparece o QR Code de pareamento (uma única vez)."
          rotuloSalvar="Criar e gerar token"
          salvando={criar.isPending}
          onSubmit={(e) => {
            e.preventDefault();
            criar.mutate();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nome" obrigatorio className="sm:col-span-2">
              <Input value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} required minLength={2} />
            </Field>
            <Field label="Tipo">
              <NativeSelect value={novo.tipo} onChange={(e) => setNovo({ ...novo, tipo: e.target.value as "totem" | "agente" })}>
                <option value="totem">Totem (tablet/notebook com câmera)</option>
                <option value="agente">Agente local (aciona catracas)</option>
              </NativeSelect>
            </Field>
            <Field label="Unidade">
              <NativeSelect value={novo.unidade_id ?? ""} onChange={(e) => setNovo({ ...novo, unidade_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Todas / única</option>
                {opcoes.data?.unidades.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nome}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Catraca" className="sm:col-span-2" dica={novo.tipo === "agente" ? "Vazio: o agente atende todas as catracas em modo agente da unidade." : "A catraca que este totem libera quando o acesso é permitido."}>
              <NativeSelect value={novo.catraca_id ?? ""} onChange={(e) => setNovo({ ...novo, catraca_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Nenhuma</option>
                {opcoes.data?.catracas.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nome}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </div>
        </FormDialog>
      )}
      <TokenPareamento dispositivo={token} onClose={() => setToken(null)} />
      <ConfirmDialog
        open={!!revogar}
        onOpenChange={(o) => !o && setRevogar(null)}
        titulo={`Revogar ${revogar?.nome}?`}
        descricao="O token deixa de valer na hora e o aparelho precisa ser pareado de novo. Use se o tablet foi perdido ou trocado."
        confirmar="Revogar"
        destrutivo
        carregando={revogarM.isPending}
        onConfirm={() => revogar && revogarM.mutate(revogar.id)}
      />
    </div>
  );
}

function TokenPareamento({ dispositivo, onClose }: { dispositivo: Dispositivo | null; onClose: () => void }) {
  const [qr, setQr] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);
  const totem = dispositivo?.tipo === "totem";
  const link = dispositivo?.token && typeof window !== "undefined" ? `${window.location.origin}/totem/parear#t=${dispositivo.token}` : "";
  useEffect(() => {
    if (!link || !totem) return;
    let vivo = true;
    QRCode.toDataURL(link, { margin: 1, width: 320, errorCorrectionLevel: "M" }).then((u) => vivo && setQr(u));
    return () => {
      vivo = false;
      setQr(null);
    };
  }, [link, totem]);
  const copiar = async (v: string) => {
    try {
      await navigator.clipboard.writeText(v);
      setCopiado(true);
      toast.success("Copiado");
    } catch {
      toast.error("Não foi possível copiar. Selecione e copie manualmente.");
    }
  };
  return (
    <Dialog open={!!dispositivo?.token} onOpenChange={(o) => { if (!o) { setCopiado(false); onClose(); } }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{totem ? "Parear o totem" : "Token do agente local"}</DialogTitle>
          <DialogDescription>
            {totem ? "No tablet, abra /totem/parear e aponte a câmera para o QR — ou abra o link abaixo direto no tablet." : "Coloque este token no arquivo de configuração do agente (deploy/agente-catraca)."}
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-sm text-warning-ink">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>Aparece só agora. Quem tiver este token abre o totem do estúdio: não envie por canais públicos.</span>
        </div>
        {totem && (
          <div className="grid place-items-center rounded-2xl bg-white p-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {qr ? <img src={qr} alt="QR Code de pareamento" className="size-64" /> : <div className="size-64 animate-pulse rounded-lg bg-muted" />}
          </div>
        )}
        <div className="flex items-center gap-2">
          <code className="min-w-0 flex-1 rounded-lg border bg-muted/50 px-3 py-2 font-mono text-xs break-all select-all">{totem ? link : dispositivo?.token}</code>
          <Button type="button" variant="outline" onClick={() => copiar(totem ? link : (dispositivo?.token ?? ""))}>
            {copiado ? <Check /> : <Copy />}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
