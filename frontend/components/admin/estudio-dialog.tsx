"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { copiarTexto, DIAS_TESTE_PADRAO, soDigitos, useEstudios, useExtras, usePlanos, valorDoCiclo } from "@/lib/admin";
import { api } from "@/lib/api";
import { moeda, numero } from "@/lib/format";
import type { Estudio, EstudioNovoIn, FichaIn } from "@/lib/tipos-admin";

const hoje = () => new Date().toLocaleDateString("sv-SE");

const vazio = (): EstudioNovoIn => ({
  nome: "",
  documento: null,
  responsavel: null,
  email_financeiro: null,
  telefone: null,
  plano_id: null,
  ciclo: "mensal",
  inicio_contrato: hoje(),
  teste_ate: null,
  observacao: null,
  indicado_por_id: null,
  extras: [],
  slug: null,
  admin_nome: "",
  admin_email: "",
  dias_teste: DIAS_TESTE_PADRAO,
  dominios: [],
});

const fichaDe = (c: Estudio): FichaIn => ({
  nome: c.nome,
  documento: c.documento,
  responsavel: c.responsavel,
  email_financeiro: c.email_financeiro,
  telefone: c.telefone,
  plano_id: c.plano_id,
  ciclo: c.ciclo,
  inicio_contrato: c.inicio_contrato,
  teste_ate: c.teste_ate,
  observacao: c.observacao,
  indicado_por_id: c.indicado_por_id,
  extras: c.extras ?? [],
});

const nulo = (v: string | null) => (v && v.trim() ? v.trim() : null);

/** Novo estúdio (cria o banco, o usuário Suporte e envia o link de primeiro acesso) ou edição da ficha comercial. */
export function EstudioDialog({
  open,
  onOpenChange,
  estudio,
  onSalvo,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  estudio?: Estudio | null;
  onSalvo?: (c: Estudio) => void;
}) {
  const qc = useQueryClient();
  const planos = usePlanos(open);
  const extras = useExtras(open);
  const todos = useEstudios({}, open);
  const [f, setF] = useState<EstudioNovoIn>(vazio);
  const [dominio, setDominio] = useState("");

  /* eslint-disable react-hooks/set-state-in-effect -- carrega o formulário ao abrir */
  useEffect(() => {
    if (!open) return;
    setF(estudio ? { ...vazio(), ...fichaDe(estudio), dias_teste: null } : vazio());
    setDominio("");
  }, [open, estudio]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const set = <K extends keyof EstudioNovoIn>(k: K, v: EstudioNovoIn[K]) => setF((o) => ({ ...o, [k]: v }));
  const plano = planos.data?.find((p) => p.id === f.plano_id);
  const outros = (todos.data ?? []).filter((c) => c.id !== estudio?.id);

  const salvar = useMutation({
    mutationFn: () => {
      const ficha: FichaIn = {
        nome: f.nome.trim(),
        documento: soDigitos(f.documento) || null,
        responsavel: nulo(f.responsavel),
        email_financeiro: nulo(f.email_financeiro),
        telefone: nulo(f.telefone),
        plano_id: f.plano_id,
        ciclo: f.ciclo,
        inicio_contrato: f.inicio_contrato,
        teste_ate: f.teste_ate,
        observacao: nulo(f.observacao),
        indicado_por_id: f.indicado_por_id,
        extras: f.extras ?? [],
      };
      return estudio
        ? api.put<Estudio>(`/admin/clientes/${estudio.id}`, ficha)
        : api.post<Estudio>("/admin/clientes", {
            ...ficha,
            slug: nulo(f.slug),
            admin_nome: f.admin_nome.trim(),
            admin_email: f.admin_email.trim(),
            dias_teste: f.dias_teste || null,
            dominios: dominio.trim() ? [dominio.trim().toLowerCase()] : [],
          });
    },
    onSuccess: (c) => {
      if (estudio) toast.success("Ficha atualizada");
      else
        toast.success(`Estúdio ${c.nome} criado. Enviamos o link de primeiro acesso.`, {
          duration: 20000,
          description: "O link vale por 7 dias. Copie se quiser mandar também pelo WhatsApp.",
          action: c.convite ? { label: "Copiar link", onClick: () => copiarTexto(c.convite!) } : undefined,
        });
      qc.invalidateQueries({ queryKey: ["admin"] });
      onSalvo?.(c);
      onOpenChange(false);
    },
  });

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      titulo={estudio ? `Ficha de ${estudio.nome}` : "Novo estúdio"}
      descricao={
        estudio
          ? "Dados comerciais, plano, teste grátis e extras liberados."
          : "Cria o ambiente do estúdio (com o usuário Suporte) e envia ao dono o link para criar o usuário master."
      }
      largura="lg"
      salvando={salvar.isPending}
      rotuloSalvar={estudio ? "Salvar" : "Criar estúdio"}
      onSubmit={(e) => {
        e.preventDefault();
        if (f.nome.trim().length < 2) return toast.error("Informe o nome do estúdio.");
        const doc = soDigitos(f.documento);
        if (doc && doc.length !== 11 && doc.length !== 14) return toast.error("CNPJ ou CPF incompleto.");
        if (!estudio && !f.admin_email.trim()) return toast.error("Informe o e-mail de quem recebe o primeiro acesso.");
        salvar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome do estúdio" obrigatorio htmlFor="est-nome" className="sm:col-span-2">
          <Input id="est-nome" value={f.nome} onChange={(e) => set("nome", e.target.value)} autoFocus placeholder="Ex.: Studio Ana Pilates" />
        </Field>
        <Field label="CNPJ ou CPF" htmlFor="est-doc">
          <Input id="est-doc" inputMode="numeric" value={f.documento ?? ""} onChange={(e) => set("documento", e.target.value)} className="num" />
        </Field>
        <Field label="Responsável" htmlFor="est-resp" dica="Quem assina o contrato.">
          <Input id="est-resp" value={f.responsavel ?? ""} onChange={(e) => set("responsavel", e.target.value)} />
        </Field>
        <Field label="E-mail do financeiro" htmlFor="est-email" dica="Recebe contratos e cobranças.">
          <Input id="est-email" type="email" value={f.email_financeiro ?? ""} onChange={(e) => set("email_financeiro", e.target.value)} />
        </Field>
        <Field label="Telefone / WhatsApp" htmlFor="est-tel">
          <Input id="est-tel" type="tel" value={f.telefone ?? ""} onChange={(e) => set("telefone", e.target.value)} />
        </Field>

        <Field
          label="Plano"
          htmlFor="est-plano"
          dica={
            plano
              ? `${moeda(valorDoCiclo(plano, f.ciclo))} por ${f.ciclo === "anual" ? "ano" : "mês"} · ${
                  plano.alunos_ativos ? `até ${numero(plano.alunos_ativos)} alunos ativos` : "alunos ilimitados"
                }`
              : undefined
          }
        >
          <NativeSelect id="est-plano" value={f.plano_id ?? ""} onChange={(e) => set("plano_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">Sem plano ainda</option>
            {planos.data
              ?.filter((p) => p.ativo || p.id === f.plano_id)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
          </NativeSelect>
        </Field>
        <Field label="Ciclo de cobrança" htmlFor="est-ciclo">
          <NativeSelect id="est-ciclo" value={f.ciclo} onChange={(e) => set("ciclo", e.target.value as FichaIn["ciclo"])}>
            <option value="mensal">Mensal</option>
            <option value="anual">Anual</option>
          </NativeSelect>
        </Field>
        <Field label="Início do contrato" htmlFor="est-inicio">
          <Input id="est-inicio" type="date" value={f.inicio_contrato ?? ""} onChange={(e) => set("inicio_contrato", e.target.value || null)} />
        </Field>
        {estudio ? (
          <Field label="Teste grátis até" htmlFor="est-teste" dica="Vale enquanto a situação for “Em teste”.">
            <Input id="est-teste" type="date" value={f.teste_ate ?? ""} onChange={(e) => set("teste_ate", e.target.value || null)} />
          </Field>
        ) : (
          <Field label="Dias de teste grátis" htmlFor="est-dias" dica="Padrão: 60 dias (2 meses). Vazio = já começa ativo.">
            <Input
              id="est-dias"
              type="number"
              min={1}
              max={90}
              value={f.dias_teste ?? ""}
              onChange={(e) => set("dias_teste", e.target.value ? Number(e.target.value) : null)}
              className="num"
            />
          </Field>
        )}
        <Field label="Indicado por" htmlFor="est-indicacao" dica="Quem indicou ganha desconto enquanto este estúdio estiver pagando.">
          <NativeSelect
            id="est-indicacao"
            value={f.indicado_por_id ?? ""}
            onChange={(e) => set("indicado_por_id", e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Ninguém</option>
            {outros.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>

        {!!extras.data?.length && (
          <div className="sm:col-span-2">
            <p className="mb-2 text-[13px] text-foreground/80">Extras liberados</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {extras.data.map((r) => (
                <label key={r.chave} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                  <Checkbox
                    checked={(f.extras ?? []).includes(r.chave)}
                    onCheckedChange={(v) =>
                      set("extras", v ? [...(f.extras ?? []), r.chave] : (f.extras ?? []).filter((x) => x !== r.chave))
                    }
                  />
                  {r.rotulo}
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">Módulos liberados só para este estúdio, além dos recursos do plano.</p>
          </div>
        )}

        {!estudio && (
          <>
            <p className="pt-2 text-[13px] font-semibold sm:col-span-2">Primeiro acesso do dono</p>
            <Field label="Nome de quem recebe" htmlFor="est-adm-nome">
              <Input id="est-adm-nome" value={f.admin_nome} onChange={(e) => set("admin_nome", e.target.value)} />
            </Field>
            <Field label="E-mail do primeiro acesso" obrigatorio htmlFor="est-adm-email" dica="Recebe o link para criar o usuário master.">
              <Input id="est-adm-email" type="email" value={f.admin_email} onChange={(e) => set("admin_email", e.target.value)} />
            </Field>
            <Field label="Identificador" htmlFor="est-slug" dica="Opcional; gerado pelo nome. Vira o endereço <identificador>.mayafit…">
              <Input
                id="est-slug"
                value={f.slug ?? ""}
                onChange={(e) => set("slug", e.target.value.toLowerCase())}
                className="font-mono"
                placeholder="studio-ana"
              />
            </Field>
            <Field label="Domínio próprio" htmlFor="est-dominio" dica="Opcional. Ex.: app.studioana.com.br">
              <Input id="est-dominio" value={dominio} onChange={(e) => setDominio(e.target.value)} className="font-mono" />
            </Field>
          </>
        )}
        <Field label="Observação" htmlFor="est-obs" className="sm:col-span-2">
          <Textarea id="est-obs" rows={2} value={f.observacao ?? ""} onChange={(e) => set("observacao", e.target.value)} />
        </Field>
      </div>
    </FormDialog>
  );
}
