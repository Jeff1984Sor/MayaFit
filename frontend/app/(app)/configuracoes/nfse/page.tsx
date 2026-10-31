"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  Building2,
  Check,
  ChevronLeft,
  ChevronRight,
  FileKey2,
  FlaskConical,
  Landmark,
  Loader2,
  MapPin,
  PlugZap,
  Rocket,
  Save,
  ScrollText,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Achado, BarraValidade, CertificadoResumo, ListaPendencias } from "@/components/nfse/comum";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { documento } from "@/lib/format";
import type { ConfigNfse, ConfigNfseIn, ModoNfse, MunicipioInfo, OpcoesNfse, RegimeNfse } from "@/lib/tipos-nfse";
import { cn } from "@/lib/utils";

const PASSOS = [
  { titulo: "Estúdio e município", icone: Building2 },
  { titulo: "Serviço e tributos", icone: Landmark },
  { titulo: "Certificado A1", icone: FileKey2 },
  { titulo: "Nota e automações", icone: ScrollText },
  { titulo: "Ambiente e revisão", icone: Rocket },
];

const CAMPOS_IN: (keyof ConfigNfseIn)[] = [
  "ativo", "provedor", "modo", "cnpj", "razao_social", "inscricao_municipal", "codigo_municipio", "municipio_nome", "uf",
  "email", "telefone", "regime", "item_lista_servico", "codigo_servico_municipal", "nbs", "aliquota_iss", "iss_retido",
  "informar_aliquota", "percentual_tributos_sn", "discriminacao_modelo", "serie", "proximo_numero", "parametros_extras",
  "emissao_automatica", "automatica_desde", "enviar_email_aluno",
];

function paraForm(c: ConfigNfse): ConfigNfseIn {
  return Object.fromEntries(CAMPOS_IN.map((k) => [k, c[k]])) as unknown as ConfigNfseIn;
}

function limpar(f: ConfigNfseIn): ConfigNfseIn {
  const vazio = (v: unknown) => (typeof v === "string" && v.trim() === "" ? null : v);
  const r = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, vazio(v)])) as unknown as ConfigNfseIn;
  r.aliquota_iss = String(f.aliquota_iss || "0").replace(",", ".");
  r.percentual_tributos_sn = f.percentual_tributos_sn ? String(f.percentual_tributos_sn).replace(",", ".") : null;
  r.serie = f.serie || "1";
  return r;
}

const VARIAVEIS_EXEMPLO: Record<string, string> = {
  "{aluno}": "Maria Souza",
  "{cpf}": "529.982.247-25",
  "{descricao}": "Pilates 2x por semana",
  "{competencia}": "10/2026",
  "{vencimento}": "10/10/2026",
  "{pagamento}": "08/10/2026",
  "{valor}": "R$ 320,00",
  "{estudio}": "Seu Estúdio",
};

function Stepper({ atual, onIr, feitos }: { atual: number; onIr: (i: number) => void; feitos: boolean[] }) {
  return (
    <ol className="mb-6 grid grid-cols-5 gap-2">
      {PASSOS.map((p, i) => {
        const on = i === atual;
        const ok = feitos[i];
        return (
          <li key={p.titulo}>
            <button type="button" onClick={() => onIr(i)} className="group flex w-full flex-col items-center gap-2 text-center">
              <span
                className={cn(
                  "grid size-10 place-items-center rounded-xl ring-1 transition-all",
                  on ? "bg-navy text-white ring-navy dark:bg-brand dark:text-navy" : ok ? "bg-success/12 text-success-ink ring-success/30" : "bg-muted text-muted-foreground ring-border",
                )}
              >
                {ok && !on ? <Check className="size-5" /> : <p.icone className="size-5" />}
              </span>
              <span className={cn("hidden text-xs font-medium sm:block", on ? "text-foreground" : "text-muted-foreground")}>{p.titulo}</span>
              <span className={cn("h-1 w-full rounded-full", i <= atual ? "bg-brand" : "bg-muted")} />
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function CartaoOpcao({ ativo, onClick, titulo, descricao, icone: Icone, desabilitado, selo }: {
  ativo: boolean; onClick: () => void; titulo: string; descricao: string; icone?: React.ComponentType<{ className?: string }>; desabilitado?: boolean; selo?: string;
}) {
  return (
    <button
      type="button"
      disabled={desabilitado}
      onClick={onClick}
      className={cn(
        "relative flex flex-col items-start gap-1 rounded-xl border p-3.5 text-left transition-all disabled:cursor-not-allowed disabled:opacity-50",
        ativo ? "border-brand bg-brand/8 ring-2 ring-brand/30" : "hover:border-brand/40 hover:bg-accent/40",
      )}
    >
      {selo && <span className="absolute top-2 right-2 rounded-md bg-success/12 px-1.5 text-[10px] font-semibold text-success-ink uppercase">{selo}</span>}
      <span className="flex items-center gap-2 text-sm font-semibold">
        {Icone && <Icone className="size-4 text-info-ink" />}
        {titulo}
      </span>
      <span className="text-xs text-muted-foreground">{descricao}</span>
    </button>
  );
}

export default function ConfiguracaoNfsePage() {
  const { pode } = useAuth();
  const q = useQuery({ queryKey: ["nfse", "configuracao"], queryFn: () => api.get<ConfigNfse>("/nfse/configuracao") });
  if (!pode("nfse.configurar")) return <SemAcesso />;
  if (q.isPending || !q.data)
    return (
      <div className="grid gap-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  return <Assistente cfg={q.data} />;
}

function Assistente({ cfg }: { cfg: ConfigNfse }) {
  const qc = useQueryClient();
  const [passo, setPasso] = useState(0);
  const [f, setF] = useState<ConfigNfseIn>(() => paraForm(cfg));
  const [atual, setAtual] = useState(cfg);
  const [cep, setCep] = useState("");
  const [municipio, setMunicipio] = useState<MunicipioInfo | null>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [senha, setSenha] = useState("");
  const [remover, setRemover] = useState(false);
  const opcoes = useQuery({ queryKey: ["nfse", "opcoes"], queryFn: () => api.get<OpcoesNfse>("/nfse/configuracao/opcoes") });
  const set = <K extends keyof ConfigNfseIn>(k: K, v: ConfigNfseIn[K]) => setF((x) => ({ ...x, [k]: v }));
  const extras = f.parametros_extras ?? {};
  const setExtra = (k: string, v: string) => set("parametros_extras", { ...extras, [k]: v });

  const aplicar = (c: ConfigNfse) => {
    setAtual(c);
    setF(paraForm(c));
    qc.setQueryData(["nfse", "configuracao"], c);
    qc.invalidateQueries({ queryKey: ["nfse", "painel"] });
  };
  const salvar = useMutation({
    mutationFn: (corpo: ConfigNfseIn) => api.put<ConfigNfse>("/nfse/configuracao", limpar(corpo)),
    onSuccess: (c) => {
      aplicar(c);
      toast.success("Configuração salva.");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Não foi possível salvar."),
  });
  const buscar = useMutation({
    mutationFn: (p: { cep?: string; codigo?: string }) => api.get<MunicipioInfo>("/nfse/configuracao/municipio", p),
    onSuccess: (m) => {
      setMunicipio(m);
      setF((x) => ({ ...x, codigo_municipio: m.codigo_municipio, municipio_nome: m.municipio_nome, uf: m.uf, provedor: m.provedor }));
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Não encontrado."),
  });
  const enviarCert = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("arquivo", arquivo!);
      fd.append("senha", senha);
      return api.post<ConfigNfse>("/nfse/configuracao/certificado", fd);
    },
    onSuccess: (c) => {
      aplicar(c);
      setArquivo(null);
      setSenha("");
      toast.success("Certificado validado e guardado cifrado.");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Certificado recusado."),
  });
  const removerCert = useMutation({
    mutationFn: () => api.del<ConfigNfse>("/nfse/configuracao/certificado"),
    onSuccess: (c) => {
      aplicar(c);
      setRemover(false);
      toast.success("Certificado removido.");
    },
  });
  const testar = useMutation({
    mutationFn: () => api.post<{ mensagem: string }>("/nfse/configuracao/testar"),
    onSuccess: (r) => toast.success(r.mensagem, { duration: 8000 }),
    onError: (e) => toast.error(e instanceof Error ? e.message : "Falhou."),
  });

  const pend = atual.pendencias;
  const campos = (cs: string[]) => pend.some((p) => p.nivel === "erro" && cs.includes(p.campo ?? ""));
  const feitos = [
    !campos(["cnpj", "razao_social", "codigo_municipio", "inscricao_municipal"]),
    !campos(["aliquota_iss", "codigo_servico_municipal", "parametros_extras"]),
    atual.certificado.configurado && atual.certificado.situacao !== "vencido",
    !!atual.discriminacao_modelo,
    !pend.some((p) => p.nivel === "erro"),
  ];
  const sp = f.provedor === "sao_paulo";
  const previa = Object.entries(VARIAVEIS_EXEMPLO).reduce(
    (t, [k, v]) => t.replaceAll(k, v),
    f.discriminacao_modelo || opcoes.data?.discriminacao_padrao || "",
  );
  const salvarEAvancar = () => {
    salvar.mutate(f, { onSuccess: () => setPasso((p) => Math.min(p + 1, PASSOS.length - 1)) });
  };

  return (
    <div>
      <div className="mb-5 flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <ShieldCheck className="size-5 text-info-ink" /> Configuração fiscal (NFS-e)
        </h2>
        <p className="text-sm text-muted-foreground">
          Em 5 passos: o MayaFit descobre o provedor pelo município, valida o certificado e confere tudo antes da primeira nota.
        </p>
      </div>
      <Stepper atual={passo} onIr={setPasso} feitos={feitos} />

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="card-surface p-5">
          {passo === 0 && (
            <div className="grid gap-5">
              <div className="rounded-xl border bg-background/50 p-4">
                <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
                  <MapPin className="size-4 text-info-ink" /> Onde o estúdio fica?
                </p>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input placeholder="CEP do estúdio" value={cep} onChange={(e) => setCep(e.target.value)} inputMode="numeric" className="sm:w-48" />
                  <Button type="button" variant="outline" onClick={() => buscar.mutate({ cep })} disabled={buscar.isPending || cep.replace(/\D/g, "").length !== 8}>
                    {buscar.isPending ? <Loader2 className="animate-spin" /> : <Search />} Descobrir provedor
                  </Button>
                </div>
                {(municipio || f.codigo_municipio) && (
                  <div className="mt-3 grid gap-2">
                    <p className="text-sm">
                      <span className="font-medium">{f.municipio_nome ?? "Município"}</span> {f.uf && `/ ${f.uf}`} · IBGE <span className="num">{f.codigo_municipio}</span>
                    </p>
                    {municipio && <Achado nivel={municipio.suportado ? "info" : "aviso"} mensagem={municipio.mensagem} />}
                  </div>
                )}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Provedor" dica="Escolhido pelo município; troque só se a prefeitura orientar.">
                  <NativeSelect value={f.provedor} onChange={(e) => set("provedor", e.target.value as ConfigNfseIn["provedor"])}>
                    <option value="nacional">NFS-e Padrão Nacional (Emissor Nacional)</option>
                    <option value="sao_paulo">Prefeitura de São Paulo (layout 2)</option>
                  </NativeSelect>
                </Field>
                <Field label="Código IBGE do município" obrigatorio>
                  <div className="flex gap-2">
                    <Input value={f.codigo_municipio ?? ""} onChange={(e) => set("codigo_municipio", e.target.value)} maxLength={7} className="num" />
                    <Button type="button" variant="outline" size="icon" aria-label="Buscar pelo código" onClick={() => buscar.mutate({ codigo: f.codigo_municipio ?? "" })}>
                      <Search />
                    </Button>
                  </div>
                </Field>
                <Field label="CNPJ do estúdio" obrigatorio dica={f.cnpj ? documento(f.cnpj) : undefined}>
                  <Input value={f.cnpj ?? ""} onChange={(e) => set("cnpj", e.target.value)} inputMode="numeric" />
                </Field>
                <Field label="Razão social" obrigatorio>
                  <Input value={f.razao_social ?? ""} onChange={(e) => set("razao_social", e.target.value)} maxLength={150} />
                </Field>
                <Field label={sp ? "CCM (inscrição municipal)" : "Inscrição municipal"} obrigatorio={sp} dica={sp ? "8 dígitos" : "Se o município exigir"}>
                  <Input value={f.inscricao_municipal ?? ""} onChange={(e) => set("inscricao_municipal", e.target.value)} maxLength={15} />
                </Field>
                <Field label="E-mail fiscal">
                  <Input type="email" value={f.email ?? ""} onChange={(e) => set("email", e.target.value)} />
                </Field>
              </div>
            </div>
          )}

          {passo === 1 && (
            <div className="grid gap-5">
              <div>
                <p className="mb-2 text-sm font-semibold">Regime tributário</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {(Object.entries(opcoes.data?.regimes ?? {}) as [RegimeNfse, string][]).map(([k, v]) => (
                    <CartaoOpcao
                      key={k}
                      ativo={f.regime === k}
                      onClick={() => set("regime", k)}
                      titulo={v}
                      descricao={
                        k === "mei" ? "ISS fixo no DAS-MEI: a nota sai sem ISS." : k === "simples" ? "ISS dentro do DAS; a nota mostra a alíquota." : "ISS calculado e recolhido à parte."
                      }
                    />
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-2 text-sm font-semibold">Serviço (lista da LC 116/2003)</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {(opcoes.data?.servicos ?? []).map((s, i) => (
                    <CartaoOpcao
                      key={s.item}
                      ativo={f.item_lista_servico === s.item}
                      onClick={() => set("item_lista_servico", s.item)}
                      titulo={`${s.item} · ${s.descricao.split(",")[0]}`}
                      descricao={s.indicado_para}
                      selo={i === 0 ? "Sugerido" : undefined}
                    />
                  ))}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">Confirme o item com o contador. Código nacional gerado: <span className="num">{atual.codigo_tributacao_nacional}</span>.</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Alíquota do ISS (%)" obrigatorio={f.regime !== "mei"} dica="Entre 2% e 5%">
                  <Input value={f.aliquota_iss} onChange={(e) => set("aliquota_iss", e.target.value)} inputMode="decimal" className="num" disabled={f.regime === "mei"} />
                </Field>
                {f.regime === "simples" && (
                  <Field label="Tributos aproximados (%)" dica="Alíquota efetiva do DAS (Lei 12.741)">
                    <Input value={f.percentual_tributos_sn ?? ""} onChange={(e) => set("percentual_tributos_sn", e.target.value)} inputMode="decimal" className="num" />
                  </Field>
                )}
                <Field label={sp ? "Código de serviço SP" : "Código municipal (opcional)"} obrigatorio={sp} dica={sp ? "5 dígitos, informado pelo contador" : "3 dígitos, se o município usar"}>
                  <Input value={f.codigo_servico_municipal ?? ""} onChange={(e) => set("codigo_servico_municipal", e.target.value)} className="num" />
                </Field>
              </div>
              {sp && (
                <div className="grid gap-4 rounded-xl border border-warning/30 bg-warning/5 p-4 sm:grid-cols-3">
                  <p className="text-xs text-warning-ink sm:col-span-3">
                    São Paulo exige os campos de IBS/CBS no layout 2. Não há padrão seguro para estúdios: defina com o contador.
                  </p>
                  <Field label="NBS">
                    <Input value={f.nbs ?? ""} onChange={(e) => set("nbs", e.target.value)} className="num" placeholder="9 dígitos" />
                  </Field>
                  <Field label="cClassTrib">
                    <Input value={extras.class_trib ?? ""} onChange={(e) => setExtra("class_trib", e.target.value)} className="num" />
                  </Field>
                  <Field label="cIndOp">
                    <Input value={extras.ind_operacao ?? ""} onChange={(e) => setExtra("ind_operacao", e.target.value)} className="num" />
                  </Field>
                </div>
              )}
              <div className="grid gap-2">
                <SwitchRow titulo="ISS retido pelo tomador" descricao="Raro em estúdios: só quando a empresa tomadora é obrigada a reter.">
                  <Switch checked={f.iss_retido} onCheckedChange={(v) => set("iss_retido", v)} />
                </SwitchRow>
                {!sp && f.regime !== "mei" && (
                  <SwitchRow titulo="Informar a alíquota na DPS" descricao="Deixe desligado se o município já parametrizou a alíquota no Sistema Nacional.">
                    <Switch checked={f.informar_aliquota} onCheckedChange={(v) => set("informar_aliquota", v)} />
                  </SwitchRow>
                )}
              </div>
            </div>
          )}

          {passo === 2 && (
            <div className="grid gap-5">
              <div className="rounded-xl border bg-background/50 p-4">
                <CertificadoResumo cert={atual.certificado} />
                <BarraValidade cert={atual.certificado} />
                {atual.certificado.cnpj_confere === false && (
                  <Achado className="mt-3" nivel="erro" mensagem="Este certificado é de outro CNPJ." acao="Envie o e-CNPJ A1 do estúdio." />
                )}
                {atual.certificado.configurado && (
                  <Button type="button" variant="ghost" size="sm" className="mt-2 text-danger-ink" onClick={() => setRemover(true)}>
                    <Trash2 /> Remover certificado
                  </Button>
                )}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Arquivo .pfx (A1)" obrigatorio>
                  <label className="flex h-9 cursor-pointer items-center gap-2 rounded-lg border border-dashed px-3 text-sm text-muted-foreground hover:bg-accent/40">
                    <Upload className="size-4" />
                    <span className="truncate">{arquivo ? arquivo.name : "Escolher arquivo"}</span>
                    <input type="file" accept=".pfx,.p12" className="hidden" onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
                  </label>
                </Field>
                <Field label="Senha do certificado" obrigatorio>
                  <Input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="new-password" />
                </Field>
              </div>
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-muted-foreground">O arquivo e a senha são guardados cifrados e nunca voltam para a tela. Só a validade e o titular aparecem.</p>
                <Button type="button" onClick={() => enviarCert.mutate()} disabled={!arquivo || !senha || enviarCert.isPending}>
                  {enviarCert.isPending ? <Loader2 className="animate-spin" /> : <BadgeCheck />} Validar e guardar
                </Button>
              </div>
              {f.modo === "simulado" && !atual.certificado.configurado && (
                <Achado nivel="info" mensagem="No modo simulado o MayaFit assina com um certificado de teste próprio." acao="Envie o seu antes de passar para Teste ou Produção." />
              )}
            </div>
          )}

          {passo === 3 && (
            <div className="grid gap-5">
              <Field label="Modelo da discriminação" dica="Clique numa variável para inserir.">
                <Textarea rows={4} maxLength={2000} value={f.discriminacao_modelo ?? ""} onChange={(e) => set("discriminacao_modelo", e.target.value)} />
              </Field>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(opcoes.data?.variaveis ?? {}).map(([k, v]) => (
                  <button
                    key={k}
                    type="button"
                    title={v}
                    onClick={() => set("discriminacao_modelo", `${f.discriminacao_modelo ?? ""}${k}`)}
                    className="rounded-md bg-brand/10 px-2 py-1 font-mono text-xs text-info-ink hover:bg-brand/20"
                  >
                    {k}
                  </button>
                ))}
              </div>
              <div className="rounded-xl border bg-background/50 p-3">
                <p className="mb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Prévia</p>
                <p className="text-sm">{previa}</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Série da DPS/RPS" dica="Numérica (ex.: 1)">
                  <Input value={f.serie} onChange={(e) => set("serie", e.target.value)} className="num" />
                </Field>
                <Field label="Próximo número" dica="Nunca reaproveita número já usado">
                  <Input type="number" min={1} value={f.proximo_numero} onChange={(e) => set("proximo_numero", Number(e.target.value))} className="num" />
                </Field>
              </div>
              <div className="grid gap-2">
                <SwitchRow titulo="Enviar a nota por e-mail ao aluno" descricao="Com o PDF anexado e o link da nota oficial.">
                  <Switch checked={f.enviar_email_aluno} onCheckedChange={(v) => set("enviar_email_aluno", v)} />
                </SwitchRow>
                <SwitchRow titulo="Emissão automática" descricao="Todo recebimento pago (a partir de hoje) vira nota sozinho. Alunos sem CPF ficam nas pendências.">
                  <Switch checked={f.emissao_automatica} onCheckedChange={(v) => set("emissao_automatica", v)} />
                </SwitchRow>
              </div>
            </div>
          )}

          {passo === 4 && (
            <div className="grid gap-5">
              <div>
                <p className="mb-2 text-sm font-semibold">Ambiente</p>
                <div className="grid gap-2 sm:grid-cols-3">
                  {([
                    ["simulado", "Simulado", "Nada sai do servidor. Ideal para treinar a equipe.", FlaskConical],
                    ["homologacao", "Teste", sp ? "A Prefeitura valida tudo, sem gerar nota." : "Produção restrita da Sefin: nota de teste, sem valor fiscal.", PlugZap],
                    ["producao", "Produção", atual.ambiente_servidor === "prod" ? "Notas reais, com valor fiscal." : "Só no servidor de produção.", Rocket],
                  ] as [ModoNfse, string, string, typeof Rocket][]).map(([k, t, d, I]) => (
                    <CartaoOpcao key={k} ativo={f.modo === k} onClick={() => set("modo", k)} titulo={t} descricao={d} icone={I} desabilitado={k === "producao" && atual.ambiente_servidor !== "prod"} />
                  ))}
                </div>
              </div>
              <SwitchRow titulo="Emissão de NFS-e ligada" descricao="Desligada, ninguém emite (nem a automática).">
                <Switch checked={f.ativo} onCheckedChange={(v) => set("ativo", v)} />
              </SwitchRow>
              <div>
                <p className="mb-2 text-sm font-semibold">Checklist</p>
                <ListaPendencias itens={pend} />
              </div>
            </div>
          )}

          <div className="mt-6 flex items-center justify-between border-t pt-4">
            <Button type="button" variant="ghost" onClick={() => setPasso((p) => Math.max(0, p - 1))} disabled={passo === 0}>
              <ChevronLeft /> Voltar
            </Button>
            <div className="flex gap-2">
              {passo === 4 && (
                <Button type="button" variant="outline" onClick={() => testar.mutate()} disabled={testar.isPending}>
                  {testar.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Testar conexão
                </Button>
              )}
              {passo < 4 ? (
                <Button type="button" onClick={salvarEAvancar} disabled={salvar.isPending}>
                  {salvar.isPending && <Loader2 className="animate-spin" />} Salvar e continuar <ChevronRight />
                </Button>
              ) : (
                <Button type="button" onClick={() => salvar.mutate(f)} disabled={salvar.isPending}>
                  {salvar.isPending ? <Loader2 className="animate-spin" /> : <Save />} Salvar
                </Button>
              )}
            </div>
          </div>
        </div>

        <aside className="flex h-fit flex-col gap-4 lg:sticky lg:top-4">
          <div className="card-surface p-4">
            <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Resumo</p>
            <dl className="mt-2 grid gap-1.5 text-sm">
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Provedor</dt><dd className="text-right font-medium">{atual.provedor_rotulo}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Município</dt><dd className="font-medium">{atual.municipio_nome ?? "—"} {atual.uf ?? ""}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">CNPJ</dt><dd className="font-medium num">{documento(atual.cnpj)}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Serviço</dt><dd className="font-medium num">{atual.item_lista_servico} ({atual.codigo_tributacao_nacional})</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">ISS</dt><dd className="font-medium num">{atual.regime === "mei" ? "no DAS-MEI" : `${String(atual.aliquota_iss).replace(".", ",")}%`}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Ambiente</dt><dd className="font-medium">{{ simulado: "Simulado", homologacao: "Teste", producao: "Produção" }[atual.modo]}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Próxima DPS</dt><dd className="font-medium num">{atual.serie}-{atual.proximo_numero}</dd></div>
            </dl>
          </div>
          <div className="card-surface p-4">
            <p className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Pendências</p>
            <ListaPendencias itens={pend.slice(0, 4)} />
          </div>
        </aside>
      </div>

      <ConfirmDialog
        open={remover}
        onOpenChange={setRemover}
        titulo="Remover o certificado?"
        descricao="Fora do modo simulado a emissão para até você enviar outro certificado."
        confirmar="Remover"
        destrutivo
        carregando={removerCert.isPending}
        onConfirm={() => removerCert.mutate()}
      />
    </div>
  );
}
