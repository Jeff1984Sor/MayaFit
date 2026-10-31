"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, KeyRound, Loader2, PlugZap, Save, Send, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SegredoCampo } from "@/components/integracoes/segredo-campo";
import { ValorUnicoDialog } from "@/components/integracoes/valor-unico-dialog";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Segmented } from "@/components/mayacorp/data-table";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ApiError, api } from "@/lib/api";
import { dataHora } from "@/lib/format";
import type {
  Ambiente,
  MapeamentoIn,
  Produto,
  ResumoGrade,
  SegredoGerado,
  TesteOut,
  WellhubConfig,
  WellhubConfigIn,
  WellhubTela,
} from "@/lib/tipos-wellhub";
import { cn } from "@/lib/utils";

type Props = { cfg: WellhubConfig; editar: boolean };

function rota(cfg: WellhubConfig) {
  return `/wellhub/unidades/${cfg.unidade_id}`;
}

/** Salva parte da configuração (PUT parcial) e atualiza as telas do Wellhub. */
function useSalvar(cfg: WellhubConfig, aoSalvar?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (corpo: WellhubConfigIn) => api.put<WellhubConfig>(rota(cfg), corpo),
    onSuccess: () => {
      toast.success("Configuração do Wellhub salva");
      aoSalvar?.();
      qc.invalidateQueries({ queryKey: ["wellhub-tela"] });
      qc.invalidateQueries({ queryKey: ["wellhub-painel"] });
    },
  });
}

type Teste = { ok: boolean; mensagem: string } | null;

/** Botão de teste com o resultado ao lado (sucesso ou erro, sem toast: o resultado fica visível no passo). */
function BotaoTeste({ rotulo, caminho, desabilitado, icone: Icone = PlugZap, onResultado }: {
  rotulo: string;
  caminho: string;
  desabilitado?: boolean;
  icone?: React.ComponentType<{ className?: string }>;
  onResultado?: (ok: boolean) => void;
}) {
  const qc = useQueryClient();
  const [res, setRes] = useState<Teste>(null);
  const m = useMutation({
    mutationFn: () => api.post<TesteOut>(caminho),
    meta: { silencioso: true },
    onSuccess: (r) => {
      setRes({ ok: r.ok, mensagem: r.mensagem });
      onResultado?.(r.ok);
    },
    onError: (e) => {
      setRes({ ok: false, mensagem: e instanceof ApiError ? e.message : "Falha no teste." });
      onResultado?.(false);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["wellhub-tela"] });
      qc.invalidateQueries({ queryKey: ["wellhub-painel"] });
    },
  });
  return (
    <div className="space-y-2">
      <Button type="button" variant="outline" disabled={desabilitado || m.isPending} onClick={() => m.mutate()}>
        {m.isPending ? <Loader2 className="animate-spin" /> : <Icone />} {rotulo}
      </Button>
      {res && <ResultadoTeste ok={res.ok} mensagem={res.mensagem} />}
    </div>
  );
}

export function ResultadoTeste({ ok, mensagem }: { ok: boolean; mensagem: string }) {
  return (
    <p
      role="status"
      className={cn(
        "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
        ok ? "border-success/30 bg-success/10 text-success-ink" : "border-danger/30 bg-danger/8 text-danger-ink",
      )}
    >
      {ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
      {mensagem}
    </p>
  );
}

function Rodape({ editar, salvando, children }: { editar: boolean; salvando: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-t pt-4">
      <div className="min-w-0 flex-1">{children}</div>
      {editar && (
        <Button type="submit" disabled={salvando}>
          {salvando ? <Loader2 className="animate-spin" /> : <Save />} Salvar
        </Button>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ 1. credenciais
export function PassoCredenciais({ cfg, editar }: Props) {
  const [ambiente, setAmbiente] = useState<Ambiente>(cfg.ambiente);
  const [gym, setGym] = useState(cfg.gym_id ?? "");
  const [chave, setChave] = useState("");
  const [remover, setRemover] = useState(false);
  const salvar = useSalvar(cfg, () => {
    setChave("");
    setRemover(false);
  });
  const pronto = cfg.configurada && !!cfg.gym_id && cfg.api_key.definido;
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        const corpo: WellhubConfigIn = { ambiente, gym_id: gym.trim() || null, limpar: remover ? ["api_key"] : [] };
        if (chave.trim() && !remover) corpo.api_key = chave.trim();
        salvar.mutate(corpo);
      }}
    >
      <fieldset disabled={!editar} className="space-y-5">
        <Field label="Ambiente" dica="Comece pelo sandbox (testes do Wellhub). Troque para produção quando o Wellhub liberar a credencial real.">
          <Segmented<Ambiente> value={ambiente} onChange={setAmbiente} opcoes={[{ value: "sandbox", label: "Sandbox (testes)" }, { value: "producao", label: "Produção" }]} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Gym ID" dica="Identificador da sua unidade no Wellhub (vai no cabeçalho X-Gym-Id)." obrigatorio>
            <Input value={gym} onChange={(e) => setGym(e.target.value.replace(/\s/g, ""))} maxLength={40} inputMode="numeric" placeholder="ex.: 123456" />
          </Field>
          <SegredoCampo id="wh-api-key" label="Chave de API (token de parceiro)" atual={cfg.api_key} valor={chave} onChange={setChave}
            remover={remover} onRemover={setRemover} dica={cfg.api_key.definido ? undefined : "Fornecida pelo Wellhub. Fica cifrada e ninguém consegue ler depois."} />
        </div>
      </fieldset>
      <Rodape editar={editar} salvando={salvar.isPending}>
        <BotaoTeste rotulo="Testar conexão" caminho={`${rota(cfg)}/testar-conexao`} desabilitado={!editar || !pronto} />
        {!pronto && <p className="mt-2 text-xs text-muted-foreground">Salve o gym id e a chave antes de testar.</p>}
        {cfg.teste_ultimo_em && (
          <p className="mt-2 text-xs text-muted-foreground">
            Último teste: {dataHora(cfg.teste_ultimo_em)} · {cfg.teste_ultimo_ok ? "OK" : "falhou"}
          </p>
        )}
      </Rodape>
    </form>
  );
}

// ------------------------------------------------------------------------------------------------ 2. webhook
export function PassoWebhook({ cfg, editar, caminho }: Props & { caminho: string }) {
  const qc = useQueryClient();
  const [segredo, setSegredo] = useState("");
  const [remover, setRemover] = useState(false);
  const [confirmar, setConfirmar] = useState(false);
  const [gerado, setGerado] = useState<string | null>(null);
  const salvar = useSalvar(cfg, () => {
    setSegredo("");
    setRemover(false);
  });
  const gerar = useMutation({
    mutationFn: () => api.post<SegredoGerado>(`${rota(cfg)}/segredo-webhook`),
    onSuccess: (r) => {
      setConfirmar(false);
      setGerado(r.valor);
      qc.invalidateQueries({ queryKey: ["wellhub-tela"] });
    },
  });
  const url = `${typeof window === "undefined" ? "" : window.location.origin}${caminho}`;
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Endereço copiado");
    } catch {
      toast.error("Não foi possível copiar.");
    }
  };
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        const corpo: WellhubConfigIn = { limpar: remover ? ["webhook_secret"] : [] };
        if (segredo.trim() && !remover) corpo.webhook_secret = segredo.trim();
        salvar.mutate(corpo);
      }}
    >
      <fieldset disabled={!editar} className="space-y-5">
        <Field label="Endereço do webhook (cadastre no Wellhub para check-in, reserva e cancelamento)" dica="Método POST. Toda chamada precisa vir assinada no cabeçalho X-Gympass-Signature.">
          <div className="flex items-center gap-2">
            <Input readOnly value={url} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
            <Button type="button" variant="outline" size="icon" aria-label="Copiar endereço" onClick={copiar}>
              <Copy />
            </Button>
          </div>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <SegredoCampo id="wh-secret" label="Segredo da assinatura" atual={cfg.webhook_secret} valor={segredo} onChange={setSegredo}
            remover={remover} onRemover={setRemover}
            dica={cfg.webhook_secret.definido ? "Deixe em branco para manter, ou gere um novo ao lado." : "Cole o segredo informado pelo Wellhub (mín. 16 caracteres) ou gere um e cadastre-o lá."} />
          <div className="flex items-end">
            <Button type="button" variant="outline" disabled={!editar || gerar.isPending} onClick={() => (cfg.webhook_secret.definido ? setConfirmar(true) : gerar.mutate())}>
              {gerar.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Gerar segredo
            </Button>
          </div>
        </div>
        {!cfg.webhook_secret.definido && (
          <p className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning-ink">
            Sem segredo, o sistema recusa todas as chamadas do Wellhub (nenhum evento é gravado).
          </p>
        )}
      </fieldset>
      <Rodape editar={editar} salvando={salvar.isPending}>
        <BotaoTeste rotulo="Testar assinatura" icone={ShieldCheck} caminho={`${rota(cfg)}/testar-webhook`} desabilitado={!editar || !cfg.webhook_secret.definido} />
      </Rodape>
      <ConfirmDialog
        open={confirmar}
        onOpenChange={setConfirmar}
        titulo="Gerar um novo segredo do webhook?"
        descricao="O segredo atual deixa de valer na hora. Cadastre o novo no Wellhub, senão as chamadas serão recusadas."
        confirmar="Gerar novo segredo"
        carregando={gerar.isPending}
        onConfirm={() => gerar.mutate()}
      />
      <ValorUnicoDialog valor={gerado} titulo="Novo segredo do webhook" descricao="Cadastre este valor no Wellhub como segredo (secret) do webhook. Ele não será mostrado de novo." onClose={() => setGerado(null)} />
    </form>
  );
}

// ------------------------------------------------------------------------------------------------ 3. mapeamento
type Linha = { ativo: boolean; product_id: string; nome_classe: string };

export function PassoMapeamento({ cfg, editar, servicos }: Props & { servicos: WellhubTela["servicos"] }) {
  const qc = useQueryClient();
  const inicial = () =>
    Object.fromEntries(
      servicos.map((s) => {
        const m = cfg.mapeamentos.find((x) => x.tipo_servico_id === s.id);
        return [s.id, { ativo: !!m?.ativo, product_id: m?.product_id ?? "", nome_classe: m?.nome_classe ?? "" }];
      }),
    ) as Record<number, Linha>;
  const [linhas, setLinhas] = useState<Record<number, Linha>>(inicial);
  const [produtos, setProdutos] = useState<Produto[] | null>(null);
  const [erroProdutos, setErroProdutos] = useState<string | null>(null);
  const set = (id: number, campo: Partial<Linha>) => setLinhas((l) => ({ ...l, [id]: { ...l[id], ...campo } }));
  const buscar = useMutation({
    mutationFn: () => api.post<Produto[]>(`${rota(cfg)}/produtos`),
    meta: { silencioso: true },
    onSuccess: (r) => {
      setProdutos(r);
      setErroProdutos(null);
    },
    onError: (e) => setErroProdutos(e.message),
  });
  const salvar = useMutation({
    mutationFn: () => {
      // serviço fora da lista = desativado no servidor (o histórico de horários publicados fica)
      const itens: MapeamentoIn[] = servicos
        .filter((s) => linhas[s.id]?.ativo)
        .map((s) => ({ tipo_servico_id: s.id, product_id: linhas[s.id].product_id.trim() || null, nome_classe: linhas[s.id].nome_classe.trim() || null, ativo: true }));
      return api.put<WellhubConfig>(`${rota(cfg)}/mapeamentos`, { itens });
    },
    onSuccess: () => {
      toast.success("Mapeamento salvo");
      qc.invalidateQueries({ queryKey: ["wellhub-tela"] });
      qc.invalidateQueries({ queryKey: ["wellhub-painel"] });
    },
  });
  const publicados = Object.fromEntries(cfg.mapeamentos.map((m) => [m.tipo_servico_id, m]));
  const podeBuscar = editar && cfg.configurada && !!cfg.gym_id && cfg.api_key.definido;
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
    >
      <p className="text-sm text-muted-foreground">
        Marque os serviços vendidos pelo Wellhub e ligue cada um ao produto (plano) correspondente. Cada serviço vira uma classe no Wellhub.
      </p>
      <fieldset disabled={!editar} className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 font-medium">Serviço do estúdio</th>
              <th className="px-3 py-2.5 font-medium">Produto Wellhub</th>
              <th className="hidden px-3 py-2.5 font-medium md:table-cell">Nome da classe no Wellhub</th>
              <th className="px-3 py-2.5 font-medium">Situação</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {servicos.map((s) => {
              const l = linhas[s.id] ?? { ativo: false, product_id: "", nome_classe: "" };
              const pub = publicados[s.id];
              return (
                <tr key={s.id} className={cn(!l.ativo && "text-muted-foreground")}>
                  <td className="px-3 py-2.5">
                    <label className="flex items-center gap-2">
                      <Switch checked={l.ativo} onCheckedChange={(v) => set(s.id, { ativo: v })} aria-label={`Vender ${s.nome} pelo Wellhub`} />
                      <span className="font-medium text-foreground">{s.nome}</span>
                    </label>
                  </td>
                  <td className="px-3 py-2.5">
                    {produtos && produtos.length > 0 ? (
                      <NativeSelect value={l.product_id} disabled={!l.ativo} onChange={(e) => set(s.id, { product_id: e.target.value })} aria-label={`Produto de ${s.nome}`}>
                        <option value="">Escolha…</option>
                        {produtos.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.nome} ({p.id})
                          </option>
                        ))}
                      </NativeSelect>
                    ) : (
                      <Input value={l.product_id} disabled={!l.ativo} onChange={(e) => set(s.id, { product_id: e.target.value.replace(/\s/g, "") })}
                        placeholder="id do produto" maxLength={40} className="w-36 font-mono" aria-label={`Produto de ${s.nome}`} />
                    )}
                  </td>
                  <td className="hidden px-3 py-2.5 md:table-cell">
                    <Input value={l.nome_classe} disabled={!l.ativo} onChange={(e) => set(s.id, { nome_classe: e.target.value })} placeholder={s.nome} maxLength={150} />
                  </td>
                  <td className="px-3 py-2.5">
                    {pub?.class_id ? (
                      <Pill tom="success">Publicada · {pub.slots_publicados} horário(s)</Pill>
                    ) : l.ativo && !l.product_id ? (
                      <Pill tom="warning">Falta o produto</Pill>
                    ) : l.ativo ? (
                      <Pill tom="info">A publicar</Pill>
                    ) : (
                      <Pill tom="neutral">Fora do Wellhub</Pill>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </fieldset>
      <Rodape editar={editar} salvando={salvar.isPending}>
        <div className="space-y-2">
          <Button type="button" variant="outline" disabled={!podeBuscar || buscar.isPending} onClick={() => buscar.mutate()}>
            {buscar.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Buscar produtos no Wellhub
          </Button>
          {produtos && <ResultadoTeste ok mensagem={`${produtos.length} produto(s) encontrado(s): escolha na lista de cada serviço.`} />}
          {erroProdutos && <ResultadoTeste ok={false} mensagem={erroProdutos} />}
          {!podeBuscar && <p className="text-xs text-muted-foreground">Sem as credenciais salvas, digite o id do produto informado pelo Wellhub.</p>}
        </div>
      </Rodape>
    </form>
  );
}

// ------------------------------------------------------------------------------------------------ 4. grade
export function PassoGrade({ cfg, editar }: Props) {
  const qc = useQueryClient();
  const [dias, setDias] = useState(String(cfg.sync_dias));
  const [auto, setAuto] = useState(cfg.sync_ativo);
  const [resumo, setResumo] = useState<ResumoGrade | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useSalvar(cfg);
  const rodar = useMutation({
    mutationFn: (previa: boolean) => api.post<ResumoGrade>(`${rota(cfg)}/grade/${previa ? "previa" : "publicar"}`),
    meta: { silencioso: true },
    onSuccess: (r) => {
      setResumo(r);
      setErro(null);
    },
    onError: (e) => {
      setErro(e.message);
      setResumo(null);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["wellhub-tela"] });
      qc.invalidateQueries({ queryKey: ["wellhub-painel"] });
    },
  });
  const credenciais = cfg.configurada && !!cfg.gym_id && cfg.api_key.definido;
  const mapeado = cfg.mapeamentos.some((m) => m.ativo && m.product_id);
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate({ sync_dias: Number(dias) || 7, sync_ativo: auto });
      }}
    >
      <p className="text-sm text-muted-foreground">
        As aulas dos serviços ligados ao Wellhub viram horários (slots) com as vagas livres. As vagas contam TODAS as reservas (do estúdio e do Wellhub), então o
        Wellhub nunca vende vaga que já está ocupada.
      </p>
      <fieldset disabled={!editar} className="grid gap-4 sm:grid-cols-2">
        <Field label="Publicar os próximos (dias)" dica="Janela de aulas enviada ao Wellhub (1 a 60 dias).">
          <Input type="number" min={1} max={60} value={dias} onChange={(e) => setDias(e.target.value)} className="w-32" />
        </Field>
        <SwitchRow titulo="Publicar automaticamente" descricao={credenciais ? "A cada 30 minutos, com a integração ativa." : "Salve as credenciais para ligar."}>
          <Switch checked={auto} disabled={!credenciais && !auto} onCheckedChange={setAuto} />
        </SwitchRow>
      </fieldset>
      {cfg.sync_ultimo_em && (
        <p className="text-xs text-muted-foreground">
          Última publicação: {dataHora(cfg.sync_ultimo_em)} · <span className={cn(cfg.sync_ultimo_ok === false && "text-danger-ink")}>{cfg.sync_ultimo_resumo}</span>
        </p>
      )}
      <Rodape editar={editar} salvando={salvar.isPending}>
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={!editar || !mapeado || rodar.isPending} onClick={() => rodar.mutate(true)}>
              {rodar.isPending && rodar.variables ? <Loader2 className="animate-spin" /> : <PlugZap />} Testar (prévia)
            </Button>
            <Button type="button" disabled={!editar || !mapeado || !credenciais || rodar.isPending} onClick={() => rodar.mutate(false)}>
              {rodar.isPending && !rodar.variables ? <Loader2 className="animate-spin" /> : <Send />} Publicar agora
            </Button>
          </div>
          {!mapeado && <p className="text-xs text-muted-foreground">Ligue ao menos um serviço a um produto (passo 3).</p>}
          {resumo && (
            <div className="space-y-1">
              <ResultadoTeste ok={resumo.erros === 0} mensagem={resumo.resumo} />
              {resumo.mensagens.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-5 text-xs text-danger-ink">
                  {resumo.mensagens.map((m, i) => (
                    <li key={i}>{m}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {erro && <ResultadoTeste ok={false} mensagem={erro} />}
        </div>
      </Rodape>
    </form>
  );
}

// ------------------------------------------------------------------------------------------------ 5. repasse e ativação
export function PassoRepasse({ cfg, editar, servicos }: Props & { servicos: WellhubTela["servicos"] }) {
  const [f, setF] = useState({
    valor: cfg.valor_repasse_checkin ?? "",
    criar: cfg.criar_aluno_automatico,
    validar: cfg.validar_checkin_automatico,
    ativo: cfg.ativo,
    padrao: cfg.servico_padrao_id ? String(cfg.servico_padrao_id) : "",
  });
  const salvar = useSalvar(cfg);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  const valorOk = f.valor === "" || /^\d{1,6}([.,]\d{1,2})?$/.test(f.valor.trim());
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valorOk) return;
        salvar.mutate({
          valor_repasse_checkin: f.valor.trim() ? f.valor.trim().replace(",", ".") : null,
          criar_aluno_automatico: f.criar,
          validar_checkin_automatico: f.validar,
          servico_padrao_id: f.padrao ? Number(f.padrao) : null,
          ativo: f.ativo,
        });
      }}
    >
      <fieldset disabled={!editar} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Repasse por check-in validado (R$)" erro={valorOk ? undefined : "Use um valor como 12,50."}
            dica="Valor que o Wellhub paga por visita no seu contrato. Usado só para estimar o repasse do mês.">
            <Input value={f.valor} onChange={(e) => set("valor", e.target.value)} inputMode="decimal" placeholder="12,50" className="w-40 num" />
          </Field>
          <Field label="Serviço padrão (opcional)" dica="Reservado para eventos sem classe identificada.">
            <NativeSelect value={f.padrao} onChange={(e) => set("padrao", e.target.value)}>
              <option value="">Nenhum</option>
              {servicos.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
        </div>
        <SwitchRow titulo="Criar o aluno automaticamente" descricao="Se o Gympass ID (ou o CPF, quando vier) não for de nenhum aluno, cria o cadastro com os dados do Wellhub.">
          <Switch checked={f.criar} onCheckedChange={(v) => set("criar", v)} />
        </SwitchRow>
        <SwitchRow titulo="Validar o check-in assim que o aviso chegar" descricao="Para estúdios sem catraca: o check-in feito no app já é validado no Wellhub. Desligado, a recepção valida no painel.">
          <Switch checked={f.validar} onCheckedChange={(v) => set("validar", v)} />
        </SwitchRow>
        <SwitchRow titulo="Integração ativa" descricao={cfg.webhook_secret.definido ? "Desligada, o webhook responde que está desativado e nada é gravado." : "Cadastre o segredo do webhook (passo 2) para ativar."}>
          <Switch checked={f.ativo} disabled={!cfg.webhook_secret.definido && !f.ativo} onCheckedChange={(v) => set("ativo", v)} />
        </SwitchRow>
      </fieldset>
      <Rodape editar={editar} salvando={salvar.isPending}>
        {cfg.ativo ? <Pill tom="success">Integração ativa</Pill> : <Pill tom="neutral">Integração desligada</Pill>}
      </Rodape>
    </form>
  );
}
