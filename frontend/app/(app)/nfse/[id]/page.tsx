"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Download,
  ExternalLink,
  FileCode2,
  FileText,
  Loader2,
  Mail,
  PencilLine,
  RefreshCw,
  Search,
  ShieldX,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Achado, ListaErros, ModoPill, StatusNotaBadge } from "@/components/nfse/comum";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, abrirArquivo, api, baixar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, dataHora, documento, moeda } from "@/lib/format";
import type { NotaDetalhe } from "@/lib/tipos-nfse";

function Linha({ rotulo, valor, mono }: { rotulo: string; valor: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{rotulo}</span>
      <span className={mono ? "text-right font-mono text-xs break-all" : "text-right font-medium"}>{valor ?? "—"}</span>
    </div>
  );
}

function erroDaApi(e: unknown) {
  if (e instanceof ApiError && e.body && typeof e.body === "object" && "detail" in e.body) {
    const d = (e.body as { detail: unknown }).detail;
    if (d && typeof d === "object" && "mensagem" in d) return String((d as { mensagem: string }).mensagem);
  }
  return e instanceof Error ? e.message : "Não foi possível concluir.";
}

const ICONE_EVENTO: Record<string, string> = {
  emitida: "bg-success",
  validada: "bg-info",
  rejeitada: "bg-danger",
  cancelada: "bg-muted-foreground",
  descartada: "bg-muted-foreground",
  falha_comunicacao: "bg-warning",
  falha: "bg-danger",
  email: "bg-brand",
};

export default function NotaDetalhePage() {
  const { id } = useParams<{ id: string }>();
  const { pode } = useAuth();
  const qc = useQueryClient();
  const chave = ["nfse", "nota", id];
  const q = useQuery({
    queryKey: chave,
    queryFn: () => api.get<NotaDetalhe>(`/nfse/notas/${id}`),
    refetchInterval: (query) => (["pendente", "processando"].includes(query.state.data?.status ?? "") ? 5000 : false),
  });
  const n = q.data;
  const [cancelar, setCancelar] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [codigo, setCodigo] = useState("1");
  const [corrigir, setCorrigir] = useState(false);
  const [corr, setCorr] = useState({ tomador_documento: "", tomador_nome: "", tomador_email: "", discriminacao: "" });

  const atualizar = (d: NotaDetalhe) => {
    qc.setQueryData(chave, d);
    qc.invalidateQueries({ queryKey: ["nfse"] });
  };
  const acao = useMutation({
    mutationFn: (caminho: string) => api.post<NotaDetalhe>(`/nfse/notas/${id}/${caminho}`),
    onSuccess: (d) => {
      atualizar(d);
      toast.success(d.status === "emitida" ? "Nota emitida." : "Atualizado.");
    },
    onError: (e) => toast.error(erroDaApi(e)),
  });
  const email = useMutation({
    mutationFn: () => api.post<{ mensagem: string }>(`/nfse/notas/${id}/email`),
    onSuccess: (d) => {
      toast.success(d.mensagem);
      qc.invalidateQueries({ queryKey: chave });
    },
    onError: (e) => toast.error(erroDaApi(e)),
  });
  const mCancelar = useMutation({
    mutationFn: () => api.post<NotaDetalhe>(`/nfse/notas/${id}/cancelar`, { codigo, motivo }),
    onSuccess: (d) => {
      atualizar(d);
      setCancelar(false);
      toast.success("Nota cancelada.");
    },
    onError: (e) => {
      toast.error(erroDaApi(e));
      qc.invalidateQueries({ queryKey: chave });
    },
  });
  const mCorrigir = useMutation({
    mutationFn: async () => {
      const corpo = Object.fromEntries(Object.entries(corr).filter(([, v]) => v.trim() !== ""));
      await api.patch<NotaDetalhe>(`/nfse/notas/${id}`, corpo);
      return api.post<NotaDetalhe>(`/nfse/notas/${id}/reprocessar`);
    },
    onSuccess: (d) => {
      atualizar(d);
      setCorrigir(false);
      toast[d.status === "emitida" ? "success" : "warning"](d.status === "emitida" ? "Corrigida e emitida." : "Reenviada: confira o resultado.");
    },
    onError: (e) => toast.error(erroDaApi(e)),
  });

  if (!pode("nfse.ver")) return <SemAcesso />;
  if (q.isPending)
    return (
      <div className="grid gap-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    );
  if (!n) return <EmptyState icone={FileText} titulo="Nota não encontrada" />;

  const emitir = pode("nfse.emitir");
  const titulo = n.numero_nfse ? `NFS-e nº ${n.numero_nfse}` : `DPS/RPS ${n.serie}-${n.numero_dps}`;
  return (
    <div>
      <PageHeader
        titulo={
          <span className="flex flex-wrap items-center gap-3">
            {titulo} <StatusNotaBadge status={n.status} /> <ModoPill modo={n.modo} />
          </span>
        }
        descricao={`${n.tomador_nome} · ${moeda(n.valor_servico)} · competência ${data(n.competencia).slice(3)}`}
        icone={FileText}
        migalhas={[{ label: "Início", href: "/" }, { label: "Notas fiscais", href: "/nfse" }, { label: titulo }]}
        acoes={
          <>
            {n.tem_pdf && (
              <Button variant="outline" onClick={() => abrirArquivo(`/nfse/notas/${n.id}/pdf`)}>
                <Download /> PDF
              </Button>
            )}
            {n.link_oficial && (
              <Button variant="outline" render={<a href={n.link_oficial} target="_blank" rel="noreferrer" />}>
                <ExternalLink /> Nota oficial
              </Button>
            )}
            {emitir && n.status === "emitida" && n.tomador_email && (
              <Button variant="outline" onClick={() => email.mutate()} disabled={email.isPending}>
                {email.isPending ? <Loader2 className="animate-spin" /> : <Mail />} Enviar por e-mail
              </Button>
            )}
            {emitir && n.pode_reprocessar && (
              <>
                <Button variant="outline" onClick={() => acao.mutate("consultar")} disabled={acao.isPending}>
                  <Search /> Consultar no provedor
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setCorr({ tomador_documento: n.tomador_documento ?? "", tomador_nome: n.tomador_nome, tomador_email: n.tomador_email ?? "", discriminacao: n.discriminacao });
                    setCorrigir(true);
                  }}
                >
                  <PencilLine /> Corrigir
                </Button>
                <Button onClick={() => acao.mutate("reprocessar")} disabled={acao.isPending}>
                  {acao.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Tentar de novo
                </Button>
              </>
            )}
            {pode("nfse.cancelar") && n.pode_cancelar && (
              <Button variant="outline" className="text-danger-ink" onClick={() => setCancelar(true)}>
                <Ban /> {n.status === "emitida" ? "Cancelar nota" : "Descartar"}
              </Button>
            )}
          </>
        }
      />

      {(n.erros.length > 0 || n.alertas.length > 0) && (
        <div className="mb-5 card-surface p-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <ShieldX className="size-4 text-danger-ink" /> Raio-x do retorno
          </h3>
          <ListaErros erros={[...n.erros, ...n.alertas]} />
          {n.proxima_tentativa_em && n.status === "pendente" && (
            <p className="mt-2 text-xs text-muted-foreground">Próxima tentativa automática: {dataHora(n.proxima_tentativa_em)}.</p>
          )}
        </div>
      )}
      {n.status === "cancelada" && (
        <Achado
          className="mb-5"
          nivel="info"
          titulo="Cancelada"
          mensagem={`Em ${dataHora(n.cancelada_em)}: ${n.motivo_cancelamento ?? ""}`}
          acao="O recebimento ficou livre para uma nova emissão."
        />
      )}

      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <div className="grid gap-4">
          <div className="card-surface p-4">
            <h3 className="mb-1 text-sm font-semibold">Discriminação do serviço</h3>
            <p className="text-sm whitespace-pre-wrap">{n.discriminacao}</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="card-surface divide-y px-4 py-2">
              <h3 className="py-2 text-sm font-semibold">Tomador</h3>
              <Linha rotulo="Nome" valor={n.tomador_nome} />
              <Linha rotulo="CPF/CNPJ" valor={<span className="num">{documento(n.tomador_documento)}</span>} />
              <Linha rotulo="E-mail" valor={n.tomador_email} />
              <Linha rotulo="E-mail enviado" valor={n.email_enviado_em ? dataHora(n.email_enviado_em) : "não"} />
              {n.aluno_id && <Linha rotulo="Aluno" valor={<Link className="text-info-ink hover:underline" href={`/alunos/${n.aluno_id}`}>abrir ficha</Link>} />}
            </div>
            <div className="card-surface divide-y px-4 py-2">
              <h3 className="py-2 text-sm font-semibold">Valores</h3>
              <Linha rotulo="Serviço" valor={<span className="num">{moeda(n.valor_servico)}</span>} />
              <Linha rotulo="Deduções" valor={<span className="num">{moeda(n.deducoes)}</span>} />
              <Linha rotulo="Alíquota ISS" valor={<span className="num">{n.aliquota.replace(".", ",")}%</span>} />
              <Linha rotulo={n.iss_retido ? "ISS (retido)" : "ISS"} valor={<span className="num">{moeda(n.valor_iss)}</span>} />
              <Linha rotulo="Regime" valor={{ mei: "MEI", simples: "Simples Nacional", presumido: "Lucro Presumido", real: "Lucro Real" }[n.regime]} />
            </div>
          </div>
          <div className="card-surface divide-y px-4 py-2">
            <h3 className="flex items-center justify-between py-2 text-sm font-semibold">
              Identificação e protocolo
              <span className="flex gap-1">
                {n.tem_xml_enviado && (
                  <Button variant="ghost" size="sm" onClick={() => baixar(`/nfse/notas/${n.id}/xml`, { query: { tipo: "enviado" } }, "nfse.xml")}>
                    <FileCode2 /> XML enviado
                  </Button>
                )}
                {n.tem_xml_retorno && (
                  <Button variant="ghost" size="sm" onClick={() => baixar(`/nfse/notas/${n.id}/xml`, { query: { tipo: "retorno" } }, "nfse.xml")}>
                    <FileCode2 /> XML de retorno
                  </Button>
                )}
              </span>
            </h3>
            <Linha rotulo="Provedor" valor={n.provedor === "nacional" ? "Padrão Nacional (Sefin)" : "Prefeitura de São Paulo"} />
            <Linha rotulo="Série / número DPS-RPS" valor={<span className="num">{n.serie} / {n.numero_dps}</span>} />
            <Linha rotulo="Número da NFS-e" valor={n.numero_nfse} />
            <Linha rotulo="Chave de acesso" valor={n.chave_acesso} mono />
            <Linha rotulo="Id da DPS" valor={n.id_dps} mono />
            <Linha rotulo="Código de verificação" valor={n.codigo_verificacao} mono />
            <Linha rotulo="Serviço (LC 116)" valor={`${n.item_lista_servico} · ${n.codigo_tributacao_nacional}${n.codigo_servico_municipal ? ` · mun. ${n.codigo_servico_municipal}` : ""}`} />
            <Linha rotulo="Chave de idempotência" valor={n.chave_emissao} mono />
            <Linha rotulo="Emitida em" valor={dataHora(n.emitida_em)} />
            <Linha rotulo="Tentativas de envio" valor={n.tentativas} />
          </div>
        </div>
        <div className="card-surface p-4">
          <h3 className="mb-3 text-sm font-semibold">Linha do tempo</h3>
          <ol className="relative ml-1.5 border-l pl-5">
            {n.eventos.map((e) => (
              <li key={e.id} className="mb-4 last:mb-0">
                <span className={`absolute -left-[5px] mt-1.5 size-2.5 rounded-full ring-4 ring-card ${ICONE_EVENTO[e.tipo] ?? "bg-muted-foreground/60"}`} />
                <p className="text-sm">{e.descricao}</p>
                <p className="text-xs text-muted-foreground">{dataHora(e.criado_em)}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>

      <ConfirmDialog
        open={cancelar}
        onOpenChange={setCancelar}
        titulo={n.status === "emitida" ? "Cancelar esta nota fiscal?" : "Descartar esta nota?"}
        descricao={
          n.status === "emitida"
            ? "O cancelamento é enviado ao provedor e não pode ser desfeito. Depois, o recebimento fica livre para uma nova emissão."
            : "A nota ainda não foi gerada no provedor: ela será só descartada."
        }
        confirmar={n.status === "emitida" ? "Cancelar nota" : "Descartar"}
        destrutivo
        carregando={mCancelar.isPending}
        desabilitado={motivo.trim().length < 15}
        onConfirm={() => mCancelar.mutate()}
      >
        <div className="grid gap-3">
          {n.status === "emitida" && (
            <Field label="Motivo (código)">
              <NativeSelect value={codigo} onChange={(e) => setCodigo(e.target.value)}>
                <option value="1">Erro na emissão</option>
                <option value="2">Serviço não prestado</option>
                <option value="9">Outros</option>
              </NativeSelect>
            </Field>
          )}
          <Field label="Justificativa" obrigatorio dica={`${motivo.trim().length}/15 caracteres no mínimo`}>
            <Textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={3} maxLength={255} placeholder="Ex.: valor lançado errado no recebimento" />
          </Field>
        </div>
      </ConfirmDialog>

      <FormDialog
        open={corrigir}
        onOpenChange={setCorrigir}
        titulo="Corrigir e reenviar"
        descricao="Ajuste o que o raio-x apontou. O reenvio usa o mesmo número de DPS/RPS (sem buraco na numeração)."
        onSubmit={(e) => {
          e.preventDefault();
          mCorrigir.mutate();
        }}
        salvando={mCorrigir.isPending}
        rotuloSalvar="Salvar e reenviar"
        largura="lg"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="CPF/CNPJ do tomador">
            <Input value={corr.tomador_documento} onChange={(e) => setCorr({ ...corr, tomador_documento: e.target.value })} />
          </Field>
          <Field label="Nome do tomador">
            <Input value={corr.tomador_nome} onChange={(e) => setCorr({ ...corr, tomador_nome: e.target.value })} />
          </Field>
          <Field label="E-mail" className="sm:col-span-2">
            <Input type="email" value={corr.tomador_email} onChange={(e) => setCorr({ ...corr, tomador_email: e.target.value })} />
          </Field>
          <Field label="Discriminação" className="sm:col-span-2">
            <Textarea rows={4} maxLength={2000} value={corr.discriminacao} onChange={(e) => setCorr({ ...corr, discriminacao: e.target.value })} />
          </Field>
        </div>
      </FormDialog>
    </div>
  );
}
