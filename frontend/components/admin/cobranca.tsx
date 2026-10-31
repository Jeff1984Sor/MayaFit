"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, CreditCard, HandCoins, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { copiarTexto, useEstudios } from "@/lib/admin";
import { api } from "@/lib/api";
import { data, moeda } from "@/lib/format";
import { type Cobranca, type Estudio, type PagamentoEstudio, ROTULO_ASSINATURA, TIPO_COBRANCA, TOM_COBRANCA } from "@/lib/tipos-admin";

function hojeMais(dias: number) {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return d.toLocaleDateString("sv-SE");
}

/** Linha de cobrança (ficha do estúdio). */
export function LinhaCobranca({ k }: { k: Cobranca }) {
  const aberta = k.status === "pendente" || k.status === "vencida";
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
      <div className="min-w-48 flex-1">
        <p className="font-medium">{k.descricao}</p>
        <p className="text-xs text-muted-foreground">
          {TIPO_COBRANCA[k.tipo]} · vence <span className="num">{data(k.vencimento)}</span>
          {k.status === "paga" && ` · paga em ${data(k.pago_em)}${k.forma_paga ? ` (${k.forma_paga})` : ""}`}
        </p>
      </div>
      <span className="num">{moeda(k.valor)}</span>
      <Pill tom={TOM_COBRANCA[k.status]}>{k.status_rotulo}</Pill>
      {k.link && aberta && (
        <Button size="icon-sm" variant="ghost" title="Copiar link de pagamento" aria-label="Copiar link de pagamento" onClick={() => copiarTexto(k.link!)}>
          <Copy />
        </Button>
      )}
    </div>
  );
}

export function AvulsaDialog({ open, onClose, estudioId }: { open: boolean; onClose: () => void; estudioId?: number }) {
  const qc = useQueryClient();
  const estudios = useEstudios({}, open && !estudioId);
  const vazio = () => ({ cliente_id: estudioId ? String(estudioId) : "", descricao: "", valor: "", vencimento: hojeMais(5), enviar: true });
  const [f, setF] = useState(vazio);
  /* eslint-disable react-hooks/set-state-in-effect -- limpa ao abrir */
  useEffect(() => {
    if (open) setF(vazio());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  /* eslint-enable react-hooks/set-state-in-effect */
  const salvar = useMutation({
    mutationFn: () =>
      api.post<Cobranca>("/admin/cobrancas/avulsa", {
        cliente_id: Number(f.cliente_id),
        descricao: f.descricao.trim(),
        valor: f.valor.replace(",", "."),
        vencimento: f.vencimento,
        enviar: f.enviar,
      }),
    onSuccess: (k) => {
      toast.success(f.enviar ? "Cobrança criada e enviada por e-mail" : "Cobrança criada", {
        action: k.link ? { label: "Copiar link", onClick: () => copiarTexto(k.link!) } : undefined,
      });
      qc.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo="Cobrança avulsa"
      descricao="Descreva e informe o valor. Sai um link do Mercado Pago (Pix, cartão ou boleto)."
      salvando={salvar.isPending}
      rotuloSalvar="Criar cobrança"
      onSubmit={(e) => {
        e.preventDefault();
        if (!f.cliente_id) return toast.error("Escolha o estúdio.");
        if (f.descricao.trim().length < 3) return toast.error("Descreva a cobrança (mínimo 3 letras).");
        if (!(Number(f.valor.replace(",", ".")) > 0)) return toast.error("Informe um valor maior que zero.");
        salvar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {!estudioId && (
          <Field label="Estúdio" obrigatorio htmlFor="av-est" className="sm:col-span-2">
            <NativeSelect id="av-est" value={f.cliente_id} onChange={(e) => setF({ ...f, cliente_id: e.target.value })}>
              <option value="">Escolha…</option>
              {estudios.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
        )}
        <Field label="Descrição" obrigatorio htmlFor="av-desc" className="sm:col-span-2">
          <Input id="av-desc" value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} placeholder="Ex.: Implantação e treinamento" autoFocus />
        </Field>
        <Field label="Valor (R$)" obrigatorio htmlFor="av-valor">
          <Input id="av-valor" inputMode="decimal" type="number" step="0.01" min={0.01} value={f.valor} onChange={(e) => setF({ ...f, valor: e.target.value })} className="num" />
        </Field>
        <Field label="Vencimento" obrigatorio htmlFor="av-venc">
          <Input id="av-venc" type="date" value={f.vencimento} onChange={(e) => setF({ ...f, vencimento: e.target.value })} />
        </Field>
        <div className="sm:col-span-2">
          <SwitchRow titulo="Enviar por e-mail" descricao="O link vai para o e-mail do financeiro do estúdio.">
            <Switch checked={f.enviar} onCheckedChange={(v) => setF({ ...f, enviar: v })} />
          </SwitchRow>
        </div>
      </div>
    </FormDialog>
  );
}

/** Aba da ficha do estúdio: como ele paga (link mensal ou cartão recorrente) e as cobranças dele. */
export function AbaCobrancas({ estudio }: { estudio: Estudio }) {
  const qc = useQueryClient();
  const [avulsa, setAvulsa] = useState(false);
  const chavePag = ["admin", "pagamento", estudio.id];
  const pag = useQuery({ queryKey: chavePag, queryFn: () => api.get<PagamentoEstudio>(`/admin/clientes/${estudio.id}/pagamento`) });
  const lista = useQuery({
    queryKey: ["admin", "cobrancas", "estudio", estudio.id],
    queryFn: () => api.get<Cobranca[]>("/admin/cobrancas", { cliente_id: estudio.id }),
  });
  const forma = useMutation({
    mutationFn: (v: "link" | "cartao") => api.put<PagamentoEstudio>(`/admin/clientes/${estudio.id}/pagamento`, { forma_pagamento: v }),
    onSuccess: () => {
      toast.success("Forma de pagamento alterada");
      qc.invalidateQueries({ queryKey: chavePag });
    },
  });
  const assinar = useMutation({
    mutationFn: () => api.post<PagamentoEstudio>(`/admin/clientes/${estudio.id}/assinatura`),
    onSuccess: (r) => {
      toast.success("Link do cartão enviado ao financeiro do estúdio", {
        action: r.link ? { label: "Copiar link", onClick: () => copiarTexto(r.link!) } : undefined,
      });
      qc.invalidateQueries({ queryKey: chavePag });
    },
  });
  const p = pag.data;
  return (
    <div className="space-y-4">
      <div className="card-surface space-y-3 p-5">
        <p className="font-medium">Forma de pagamento</p>
        <div className="flex flex-wrap items-center gap-3">
          <NativeSelect
            value={p?.forma_pagamento ?? "link"}
            onChange={(e) => forma.mutate(e.target.value as "link" | "cartao")}
            className="max-w-80"
            aria-label="Forma de pagamento"
            disabled={!p || forma.isPending}
          >
            <option value="link">Link do Mercado Pago todo mês (Pix, cartão ou boleto)</option>
            <option value="cartao">Cartão recorrente (assinatura)</option>
          </NativeSelect>
          {p?.forma_pagamento === "cartao" && (
            <>
              <span className="text-sm text-muted-foreground">
                Assinatura: {p.assinatura_status ? (ROTULO_ASSINATURA[p.assinatura_status] ?? p.assinatura_status) : "não criada"}
              </span>
              <Button size="sm" variant="outline" disabled={assinar.isPending} onClick={() => assinar.mutate()}>
                <CreditCard /> {p.assinatura_id ? "Reenviar link do cartão" : "Enviar link do cartão"}
              </Button>
            </>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          No cartão, o Mercado Pago debita a mensalidade sozinho; alunos e usuários acima do plano saem como link à parte.
        </p>
      </div>
      <div className="card-surface overflow-hidden">
        <div className="flex items-center justify-between border-b p-3">
          <p className="text-sm font-medium">Cobranças</p>
          <Button size="sm" onClick={() => setAvulsa(true)}>
            <Plus /> Cobrança avulsa
          </Button>
        </div>
        {!lista.data?.length ? (
          <EmptyState icone={HandCoins} titulo="Nenhuma cobrança" descricao="As mensalidades aparecem aqui assim que forem geradas." />
        ) : (
          <div className="divide-y">
            {lista.data.map((k) => (
              <LinhaCobranca key={k.id} k={k} />
            ))}
          </div>
        )}
      </div>
      <AvulsaDialog open={avulsa} onClose={() => setAvulsa(false)} estudioId={estudio.id} />
    </div>
  );
}
