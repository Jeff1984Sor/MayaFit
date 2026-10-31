"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, CalendarPlus, Check, CheckCircle2, Copy, HandCoins, Link2, Plus, ReceiptText, Send, Settings2, Wallet } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";

import { AvulsaDialog } from "@/components/admin/cobranca";
import { Indicador } from "@/components/admin/indicador";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SenhaInput } from "@/components/mayacorp/senha-input";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { copiarTexto, mesAno, passoRegua } from "@/lib/admin";
import { api } from "@/lib/api";
import { data, moeda, numero, toNum } from "@/lib/format";
import {
  type Cobranca,
  type ConfigCobranca,
  type ResumoCobranca,
  type StatusCobranca,
  TIPO_COBRANCA,
  TOM_COBRANCA,
} from "@/lib/tipos-admin";

const POR_PAGINA = 25;
const STATUS: StatusCobranca[] = ["pendente", "vencida", "paga", "cancelada"];
const FORMAS = ["Pix", "Transferência", "Boleto", "Dinheiro", "Cartão", "Outra"];

function CobrancasConteudo() {
  const qc = useQueryClient();
  const inicial = useSearchParams().get("status");
  const [status, setStatus] = useState<StatusCobranca | "todas">(STATUS.includes(inicial as StatusCobranca) ? (inicial as StatusCobranca) : "todas");
  const [tipo, setTipo] = useState("");
  const [q, setQ] = useState("");
  const [pagina, setPagina] = useState(1);
  const [avulsa, setAvulsa] = useState(false);
  const [gerar, setGerar] = useState(false);
  const [mp, setMp] = useState(false);
  const [cancelar, setCancelar] = useState<Cobranca | null>(null);
  const [baixa, setBaixa] = useState<Cobranca | null>(null);
  const [forma, setForma] = useState(FORMAS[0]);
  const cfg = useQuery({ queryKey: ["admin", "cobranca-config"], queryFn: () => api.get<ConfigCobranca>("/admin/cobranca/config") });
  const resumo = useQuery({ queryKey: ["admin", "cobrancas", "resumo"], queryFn: () => api.get<ResumoCobranca>("/admin/cobrancas/resumo") });
  const lista = useQuery({
    queryKey: ["admin", "cobrancas", "lista", status],
    queryFn: () => api.get<Cobranca[]>("/admin/cobrancas", { status: status === "todas" ? undefined : status }),
  });
  const termo = q.trim().toLowerCase();
  const filtradas = (lista.data ?? []).filter(
    (k) => (!tipo || k.tipo === tipo) && (!termo || `${k.cliente_nome} ${k.descricao}`.toLowerCase().includes(termo)),
  );
  const itens = filtradas.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA);
  const total = filtradas.reduce((s, k) => s + toNum(k.valor), 0);
  const atualizar = () => qc.invalidateQueries({ queryKey: ["admin"] });

  const enviar = useMutation({
    mutationFn: (k: Cobranca) => api.post<Cobranca & { enviado_para: string[] }>(`/admin/cobrancas/${k.id}/enviar`),
    onSuccess: (r) => {
      toast.success(`Cobrança enviada para ${r.enviado_para.join(", ")}`);
      atualizar();
    },
  });
  const darBaixa = useMutation({
    mutationFn: () => api.post<Cobranca>(`/admin/cobrancas/${baixa!.id}/baixa`, { forma: forma.toLowerCase() }),
    onSuccess: () => {
      toast.success("Baixa registrada");
      setBaixa(null);
      atualizar();
    },
  });
  const cancelarCob = useMutation({
    mutationFn: () => api.post<Cobranca>(`/admin/cobrancas/${cancelar!.id}/cancelar`),
    onSuccess: () => {
      toast.success("Cobrança cancelada");
      setCancelar(null);
      atualizar();
    },
  });
  const r = resumo.data;
  const conectado = cfg.data?.conectado;

  return (
    <div>
      <PageHeader
        titulo="Cobranças"
        descricao="Mensalidades e cobranças avulsas dos estúdios, pagas pelo Mercado Pago."
        icone={HandCoins}
        migalhas={[{ label: "Admin MayaFit", href: "/admin" }, { label: "Cobranças" }]}
        acoes={
          <>
            <Button variant="outline" onClick={() => setMp(true)}>
              <Settings2 /> Mercado Pago
            </Button>
            <Button variant="outline" disabled={!conectado} onClick={() => setGerar(true)}>
              <CalendarPlus /> Gerar mensalidades
            </Button>
            <Button disabled={!conectado} onClick={() => setAvulsa(true)}>
              <Plus /> Cobrança avulsa
            </Button>
          </>
        }
      />

      {cfg.data && !conectado && (
        <div className="card-surface mb-5 flex flex-wrap items-center gap-3 border-warning/40 p-4 text-sm">
          <AlertTriangle className="size-5 text-warning-ink" />
          <span className="flex-1">Conecte a conta do Mercado Pago para gerar links de pagamento e assinaturas no cartão.</span>
          <Button size="sm" onClick={() => setMp(true)}>
            Conectar
          </Button>
        </div>
      )}
      {cfg.data && conectado && (
        <div className="mb-5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Pill tom="success" className="normal-case">
            <Check className="size-3" /> Mercado Pago conectado{cfg.data.conta ? ` · ${cfg.data.conta}` : ""}
          </Pill>
          <span>
            Vencimento dia <span className="num">{cfg.data.dia_vencimento}</span> · lembretes {cfg.data.regua.map(passoRegua).join(", ") || "desligados"} ·{" "}
            {cfg.data.gerar_automatico ? "mensalidades geradas sozinhas no dia 1" : "mensalidades geradas à mão"}
          </span>
        </div>
      )}

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador titulo="Recebido no mês" icone={CheckCircle2} tom="success" carregando={!r} valor={r ? moeda(r.recebido_mes) : "—"} />
        <Indicador titulo="Em aberto (a vencer)" icone={Wallet} carregando={!r} valor={r ? moeda(r.em_aberto) : "—"} />
        <Indicador titulo="Vencido" icone={AlertTriangle} tom={r && toNum(r.vencido) > 0 ? "danger" : undefined} carregando={!r} valor={r ? moeda(r.vencido) : "—"} />
        <Indicador titulo="Estúdios em atraso" icone={ReceiptText} carregando={!r} valor={r ? numero(r.inadimplentes) : "—"} />
      </div>

      <TableCard>
        <Toolbar>
          <SearchInput
            value={q}
            onChange={(v) => {
              setQ(v);
              setPagina(1);
            }}
            placeholder="Estúdio ou descrição"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Segmented
              value={status}
              onChange={(v) => {
                setStatus(v);
                setPagina(1);
              }}
              opcoes={[
                { value: "todas", label: "Todas" },
                { value: "pendente", label: "Em aberto" },
                { value: "vencida", label: "Vencidas", tom: "danger" },
                { value: "paga", label: "Pagas", tom: "success" },
                { value: "cancelada", label: "Canceladas" },
              ]}
            />
            <NativeSelect
              aria-label="Filtrar por tipo"
              value={tipo}
              onChange={(e) => {
                setTipo(e.target.value);
                setPagina(1);
              }}
              className="w-40"
            >
              <option value="">Todos os tipos</option>
              {Object.entries(TIPO_COBRANCA).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </div>
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : !filtradas.length ? (
          <EmptyState
            icone={HandCoins}
            titulo={termo || tipo || status !== "todas" ? "Nenhuma cobrança encontrada" : "Nenhuma cobrança ainda"}
            descricao="Com o Mercado Pago conectado, as mensalidades saem sozinhas todo dia 1. Você também pode gerar agora ou criar uma cobrança avulsa."
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[960px] text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Estúdio</th>
                    <th className="px-3 py-2.5 font-medium">Cobrança</th>
                    <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                    <th className="px-3 py-2.5 font-medium">Vencimento</th>
                    <th className="px-3 py-2.5 font-medium">Situação</th>
                    <th className="px-3 py-2.5 text-right font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {itens.map((k) => {
                    const aberta = k.status === "pendente" || k.status === "vencida";
                    return (
                      <tr key={k.id}>
                        <td className="px-4 py-3 font-medium">{k.cliente_nome}</td>
                        <td className="px-3 py-3">
                          {k.descricao}
                          <div className="text-xs text-muted-foreground">
                            {TIPO_COBRANCA[k.tipo]}
                            {k.competencia && ` · ${mesAno(k.competencia)}`}
                            {k.itens.length > 1 && ` · ${k.itens.map((i) => `${i.descricao} ${moeda(i.valor)}`).join(" · ")}`}
                          </div>
                        </td>
                        <td className="num px-3 py-3 text-right">{moeda(k.valor)}</td>
                        <td className="num px-3 py-3 text-xs">{data(k.vencimento)}</td>
                        <td className="px-3 py-3">
                          <Pill tom={TOM_COBRANCA[k.status]}>{k.status_rotulo}</Pill>
                          {k.status === "paga" && (
                            <div className="mt-0.5 text-xs text-muted-foreground">
                              <span className="num">{data(k.pago_em)}</span>
                              {k.forma_paga && ` · ${k.forma_paga}`}
                            </div>
                          )}
                          {aberta && k.avisos.length > 0 && <div className="mt-0.5 text-xs text-muted-foreground">{k.avisos.length} lembrete(s) enviado(s)</div>}
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex justify-end gap-1">
                            {k.link && aberta && (
                              <Button size="icon-sm" variant="ghost" title="Copiar link de pagamento" aria-label="Copiar link de pagamento" onClick={() => copiarTexto(k.link!)}>
                                <Copy />
                              </Button>
                            )}
                            {aberta && (
                              <>
                                <Button
                                  size="icon-sm"
                                  variant="ghost"
                                  title="Enviar por e-mail"
                                  aria-label="Enviar por e-mail"
                                  disabled={enviar.isPending}
                                  onClick={() => enviar.mutate(k)}
                                >
                                  <Send />
                                </Button>
                                <Button
                                  size="icon-sm"
                                  variant="ghost"
                                  title="Dar baixa (recebido fora do Mercado Pago)"
                                  aria-label="Dar baixa"
                                  onClick={() => {
                                    setForma(FORMAS[0]);
                                    setBaixa(k);
                                  }}
                                >
                                  <CheckCircle2 />
                                </Button>
                                <Button size="icon-sm" variant="ghost" title="Cancelar" aria-label="Cancelar cobrança" onClick={() => setCancelar(k)}>
                                  <Ban />
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="border-t bg-muted/30 text-xs">
                  <tr>
                    <td className="px-4 py-2.5 text-muted-foreground" colSpan={2}>
                      {numero(filtradas.length)} cobrança(s) no filtro
                    </td>
                    <td className="num px-3 py-2.5 text-right font-medium">{moeda(total)}</td>
                    <td colSpan={3} />
                  </tr>
                </tfoot>
              </table>
            </div>
            <Pagination pagina={pagina} porPagina={POR_PAGINA} total={filtradas.length} onChange={setPagina} />
          </>
        )}
      </TableCard>

      <AvulsaDialog open={avulsa} onClose={() => setAvulsa(false)} />
      <GerarDialog open={gerar} onClose={() => setGerar(false)} />
      <MercadoPagoDialog open={mp} onClose={() => setMp(false)} cfg={cfg.data} />
      <FormDialog
        open={!!baixa}
        onOpenChange={(o) => !o && setBaixa(null)}
        titulo="Dar baixa manual"
        descricao={baixa ? `${baixa.cliente_nome}: ${moeda(baixa.valor)} entra como paga (recebida fora do Mercado Pago).` : undefined}
        rotuloSalvar="Dar baixa"
        salvando={darBaixa.isPending}
        onSubmit={(e) => {
          e.preventDefault();
          darBaixa.mutate();
        }}
      >
        <Field label="Como foi pago" htmlFor="bx-forma">
          <NativeSelect id="bx-forma" value={forma} onChange={(e) => setForma(e.target.value)}>
            {FORMAS.map((f) => (
              <option key={f}>{f}</option>
            ))}
          </NativeSelect>
        </Field>
      </FormDialog>
      <ConfirmDialog
        open={!!cancelar}
        onOpenChange={(o) => !o && setCancelar(null)}
        titulo="Cancelar a cobrança?"
        descricao={cancelar ? `${cancelar.cliente_nome}: ${cancelar.descricao}. Os lembretes param e a cobrança sai dos valores em aberto.` : undefined}
        confirmar="Cancelar cobrança"
        destrutivo
        carregando={cancelarCob.isPending}
        onConfirm={() => cancelarCob.mutate()}
      />
    </div>
  );
}

export default function CobrancasPage() {
  return (
    <Suspense>
      <CobrancasConteudo />
    </Suspense>
  );
}

function GerarDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [comp, setComp] = useState(() => new Date().toLocaleDateString("sv-SE").slice(0, 7));
  const [enviar, setEnviar] = useState(true);
  const gerar = useMutation({
    mutationFn: () => api.post<{ criadas: string[]; erros: string[] }>("/admin/cobrancas/gerar", { competencia: comp, enviar }),
    onSuccess: (r) => {
      if (r.erros.length) toast.warning(`${r.criadas.length} gerada(s). Problemas: ${r.erros.join(" · ")}`, { duration: 12000 });
      else toast.success(r.criadas.length ? `${r.criadas.length} mensalidade(s) gerada(s)` : "Nada novo: as mensalidades do mês já existem");
      qc.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo="Gerar mensalidades"
      descricao="Uma por estúdio ativo: plano (com desconto por indicação) + alunos e usuários acima do limite no mês anterior. As que já existem não são duplicadas."
      salvando={gerar.isPending}
      rotuloSalvar="Gerar"
      onSubmit={(e) => {
        e.preventDefault();
        gerar.mutate();
      }}
    >
      <div className="space-y-4">
        <Field label="Mês" htmlFor="ger-mes">
          <Input id="ger-mes" type="month" required value={comp} onChange={(e) => setComp(e.target.value)} className="max-w-48" />
        </Field>
        <SwitchRow titulo="Enviar o link por e-mail agora" descricao="Vai para o e-mail do financeiro de cada estúdio.">
          <Switch checked={enviar} onCheckedChange={setEnviar} />
        </SwitchRow>
      </div>
    </FormDialog>
  );
}

function SegredoMp({ id, label, definido, valor, onChange, dica }: { id: string; label: string; definido: boolean; valor: string; onChange: (v: string) => void; dica: string }) {
  return (
    <Field label={label} htmlFor={id} dica={definido ? "Deixe em branco para manter o valor salvo." : dica}>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tom={definido ? "success" : "neutral"} className="normal-case">
          {definido ? (
            <>
              <Check className="size-3" /> configurado
            </>
          ) : (
            "não configurado"
          )}
        </Pill>
      </div>
      <SenhaInput id={id} value={valor} onChange={onChange} autoComplete="new-password" placeholder={definido ? "•••••••• (mantém o atual)" : ""} />
    </Field>
  );
}

function MercadoPagoDialog({ open, onClose, cfg }: { open: boolean; onClose: () => void; cfg?: ConfigCobranca }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ token: "", segredo: "", dia_vencimento: 10, gerar_automatico: true, regua: "-3, 0, 3, 10" });
  /* eslint-disable react-hooks/set-state-in-effect -- carrega ao abrir */
  useEffect(() => {
    if (open && cfg) setF({ token: "", segredo: "", dia_vencimento: cfg.dia_vencimento, gerar_automatico: cfg.gerar_automatico, regua: cfg.regua.join(", ") });
  }, [open, cfg]);
  /* eslint-enable react-hooks/set-state-in-effect */
  const regua = f.regua
    .split(/[,;\s]+/)
    .filter(Boolean)
    .map(Number)
    .filter((n) => Number.isInteger(n));
  const salvar = useMutation({
    mutationFn: () =>
      api.put<ConfigCobranca>("/admin/cobranca/config", {
        token: f.token.trim() || null,
        segredo: f.segredo.trim() || null,
        dia_vencimento: f.dia_vencimento,
        gerar_automatico: f.gerar_automatico,
        regua,
      }),
    onSuccess: (r) => {
      toast.success(r.conectado ? `Mercado Pago conectado${r.conta ? ` (${r.conta})` : ""}` : "Configuração salva");
      qc.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });
  const testar = useMutation({
    mutationFn: () => api.post<{ ok: boolean; conta: string | null }>("/admin/cobranca/config/testar"),
    onSuccess: (r) => toast.success(`Conexão funcionando${r.conta ? `: ${r.conta}` : ""}`),
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo="Mercado Pago"
      descricao="A conta que recebe as mensalidades dos estúdios. As chaves ficam cifradas e não podem ser lidas depois."
      largura="lg"
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        if (f.dia_vencimento < 1 || f.dia_vencimento > 28) return toast.error("O dia do vencimento vai de 1 a 28.");
        salvar.mutate();
      }}
      rodapeExtra={
        cfg?.conectado && (
          <Button type="button" variant="outline" disabled={testar.isPending} onClick={() => testar.mutate()}>
            <Link2 /> Testar conexão
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {cfg?.conectado && (
          <p className="rounded-lg bg-success/10 px-3 py-2 text-sm text-success-ink">
            Conectado{cfg.conta ? (
              <>
                {" "}
                à conta <b>{cfg.conta}</b>
              </>
            ) : null}
            . Para trocar, cole outro Access Token.
          </p>
        )}
        <SegredoMp
          id="mp-token"
          label="Access Token de produção"
          definido={!!cfg?.conectado}
          valor={f.token}
          onChange={(v) => setF({ ...f, token: v })}
          dica="Mercado Pago › Suas integrações › Credenciais de produção. Começa com APP_USR-."
        />
        <SegredoMp
          id="mp-seg"
          label="Assinatura secreta das notificações"
          definido={!!cfg?.segredo_definido}
          valor={f.segredo}
          onChange={(v) => setF({ ...f, segredo: v })}
          dica="Em Suas integrações › Webhooks, cadastre o endereço abaixo (Pagamentos e Planos e assinaturas) e cole aqui a assinatura secreta."
        />
        {cfg?.url_notificacao && (
          <div>
            <p className="mb-1 text-[13px] text-foreground/80">Endereço das notificações</p>
            <div className="flex items-center gap-2 rounded-lg border px-3 py-2 font-mono text-xs">
              <span className="flex-1 truncate">{cfg.url_notificacao}</span>
              <Button type="button" size="icon-sm" variant="ghost" aria-label="Copiar endereço" onClick={() => copiarTexto(cfg.url_notificacao!, "Endereço copiado")}>
                <Copy />
              </Button>
            </div>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Dia do vencimento" htmlFor="mp-dia" dica="Do 1 ao 28.">
            <Input
              id="mp-dia"
              type="number"
              min={1}
              max={28}
              value={f.dia_vencimento}
              onChange={(e) => setF({ ...f, dia_vencimento: Number(e.target.value) })}
              className="num"
            />
          </Field>
          <Field label="Régua de lembretes (dias)" htmlFor="mp-regua" dica={regua.map(passoRegua).join(" · ") || "Negativo = antes do vencimento."}>
            <Input id="mp-regua" value={f.regua} onChange={(e) => setF({ ...f, regua: e.target.value })} className="num" placeholder="-3, 0, 3, 10" />
          </Field>
        </div>
        <SwitchRow titulo="Gerar as mensalidades sozinho" descricao="Todo dia 1, para os estúdios ativos. Atraso só gera aviso; suspender é sempre manual.">
          <Switch checked={f.gerar_automatico} onCheckedChange={(v) => setF({ ...f, gerar_automatico: v })} />
        </SwitchRow>
      </div>
    </FormDialog>
  );
}
