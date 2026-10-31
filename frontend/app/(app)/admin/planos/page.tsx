"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeDollarSign, Gift, LifeBuoy, Plus, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { linhaClicavel, TableCard, TableSkeleton } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SenhaInput } from "@/components/mayacorp/senha-input";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { usePlanos, useRecursos } from "@/lib/admin";
import { api } from "@/lib/api";
import { moeda, numero, toNum } from "@/lib/format";
import type { PlanoIn, PlanoOut, PoliticaIndicacao, Rotulo } from "@/lib/tipos-admin";

const novoPlano = (ordem: number): PlanoIn => ({
  nome: "",
  preco_mensal: "",
  preco_anual: "",
  usuarios: null,
  alunos_ativos: null,
  preco_aluno_excedente: "0.00",
  preco_usuario_adicional: "0.00",
  recursos: ["gestao"],
  ativo: true,
  ordem,
});

const paraForm = (p: PlanoOut): PlanoIn => ({
  nome: p.nome,
  preco_mensal: p.preco_mensal,
  preco_anual: p.preco_anual,
  usuarios: p.usuarios,
  alunos_ativos: p.alunos_ativos,
  preco_aluno_excedente: p.preco_aluno_excedente,
  preco_usuario_adicional: p.preco_usuario_adicional,
  recursos: p.recursos,
  ativo: p.ativo,
  ordem: p.ordem,
});

export default function PlanosPage() {
  const planos = usePlanos();
  const recursos = useRecursos();
  const [edit, setEdit] = useState<{ p: PlanoOut | null } | null>(null);
  const rot = (k: string) => recursos.data?.find((r) => r.chave === k)?.rotulo ?? k;

  return (
    <div className="space-y-5">
      <PageHeader
        className="mb-0"
        titulo="Planos e indicação"
        descricao="O que cada plano custa e libera, o desconto por indicação e a senha do usuário Suporte."
        icone={BadgeDollarSign}
        migalhas={[{ label: "Admin MayaFit", href: "/admin" }, { label: "Planos" }]}
        acoes={
          <Button onClick={() => setEdit({ p: null })}>
            <Plus /> Novo plano
          </Button>
        }
      />
      <TableCard>
        {planos.isPending ? (
          <TableSkeleton colunas={6} />
        ) : !planos.data?.length ? (
          <EmptyState
            icone={BadgeDollarSign}
            titulo="Nenhum plano cadastrado"
            descricao="Crie os planos que aparecem no cadastro público e no “Meu plano” dos estúdios."
            acao={
              <Button onClick={() => setEdit({ p: null })}>
                <Plus /> Novo plano
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Plano</th>
                  <th className="px-3 py-2.5 text-right font-medium">Mensal</th>
                  <th className="px-3 py-2.5 text-right font-medium">Anual</th>
                  <th className="px-3 py-2.5 text-right font-medium">Alunos ativos</th>
                  <th className="px-3 py-2.5 text-right font-medium">Usuários</th>
                  <th className="px-3 py-2.5 font-medium">Acima do limite</th>
                  <th className="px-3 py-2.5 font-medium">Recursos</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {planos.data.map((p) => (
                  <tr key={p.id} className={linhaClicavel + (p.ativo ? "" : " opacity-60")} onClick={() => setEdit({ p })}>
                    <td className="px-4 py-3 font-medium">
                      {p.nome} {!p.ativo && <Pill>inativo</Pill>}
                    </td>
                    <td className="num px-3 py-3 text-right">{moeda(p.preco_mensal)}</td>
                    <td className="num px-3 py-3 text-right">{moeda(p.preco_anual)}</td>
                    <td className="num px-3 py-3 text-right">{p.alunos_ativos != null ? numero(p.alunos_ativos) : "∞"}</td>
                    <td className="num px-3 py-3 text-right">{p.usuarios != null ? numero(p.usuarios) : "∞"}</td>
                    <td className="px-3 py-3 text-xs">
                      aluno <span className="num">{moeda(p.preco_aluno_excedente)}</span> · usuário <span className="num">{moeda(p.preco_usuario_adicional)}</span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex max-w-80 flex-wrap gap-1">
                        {p.recursos.map((r) => (
                          <Pill key={r} tom="brand">
                            {rot(r)}
                          </Pill>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </TableCard>

      <div className="grid gap-5 lg:grid-cols-2">
        <Indicacao />
        <SenhaSuporte />
      </div>
      <PlanoDialog edit={edit} onClose={() => setEdit(null)} recursos={recursos.data ?? []} proximaOrdem={(planos.data?.length ?? 0) + 1} />
    </div>
  );
}

function PlanoDialog({
  edit,
  onClose,
  recursos,
  proximaOrdem,
}: {
  edit: { p: PlanoOut | null } | null;
  onClose: () => void;
  recursos: Rotulo[];
  proximaOrdem: number;
}) {
  const qc = useQueryClient();
  const [f, setF] = useState<PlanoIn>(() => novoPlano(proximaOrdem));
  /* eslint-disable react-hooks/set-state-in-effect -- carrega o formulário ao abrir */
  useEffect(() => {
    if (edit) setF(edit.p ? paraForm(edit.p) : novoPlano(proximaOrdem));
  }, [edit, proximaOrdem]);
  /* eslint-enable react-hooks/set-state-in-effect */
  const set = <K extends keyof PlanoIn>(k: K, v: PlanoIn[K]) => setF((o) => ({ ...o, [k]: v }));
  const salvar = useMutation({
    mutationFn: () => (edit?.p ? api.put(`/admin/planos/${edit.p.id}`, f) : api.post("/admin/planos", f)),
    onSuccess: () => {
      toast.success(edit?.p ? "Plano atualizado" : "Plano criado");
      qc.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <FormDialog
      open={!!edit}
      onOpenChange={(o) => !o && onClose()}
      titulo={edit?.p ? `Plano ${edit.p.nome}` : "Novo plano"}
      descricao="Limite vazio = ilimitado. Mudanças valem para quem já está no plano a partir da próxima mensalidade."
      largura="lg"
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        if (f.nome.trim().length < 2) return toast.error("Informe o nome do plano.");
        if (f.preco_mensal === "" || f.preco_anual === "") return toast.error("Informe os preços mensal e anual.");
        salvar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome" obrigatorio htmlFor="pl-nome">
          <Input id="pl-nome" value={f.nome} onChange={(e) => set("nome", e.target.value)} autoFocus placeholder="Ex.: Essencial" />
        </Field>
        <Field label="Ordem de exibição" htmlFor="pl-ordem" dica="Menor aparece primeiro.">
          <Input id="pl-ordem" type="number" min={0} value={f.ordem} onChange={(e) => set("ordem", Number(e.target.value) || 0)} className="num" />
        </Field>
        <Field label="Preço mensal (R$)" obrigatorio htmlFor="pl-mensal">
          <Input id="pl-mensal" type="number" step="0.01" min={0} value={f.preco_mensal} onChange={(e) => set("preco_mensal", e.target.value)} className="num" />
        </Field>
        <Field
          label="Preço anual (R$)"
          obrigatorio
          htmlFor="pl-anual"
          dica={toNum(f.preco_mensal) > 0 ? `Referência: 10× o mensal = ${moeda(toNum(f.preco_mensal) * 10)}` : undefined}
        >
          <Input id="pl-anual" type="number" step="0.01" min={0} value={f.preco_anual} onChange={(e) => set("preco_anual", e.target.value)} className="num" />
        </Field>
        <Field label="Alunos ativos incluídos" htmlFor="pl-alunos">
          <Input
            id="pl-alunos"
            type="number"
            min={0}
            value={f.alunos_ativos ?? ""}
            onChange={(e) => set("alunos_ativos", num(e.target.value))}
            placeholder="ilimitado"
            className="num"
          />
        </Field>
        <Field label="Usuários incluídos" htmlFor="pl-usu">
          <Input id="pl-usu" type="number" min={1} value={f.usuarios ?? ""} onChange={(e) => set("usuarios", num(e.target.value))} placeholder="ilimitado" className="num" />
        </Field>
        <Field label="Por aluno acima do limite (R$)" htmlFor="pl-exc" dica="Cobrado por aluno ativo além do incluído, no mês seguinte.">
          <Input
            id="pl-exc"
            type="number"
            step="0.01"
            min={0}
            value={f.preco_aluno_excedente}
            onChange={(e) => set("preco_aluno_excedente", e.target.value)}
            className="num"
          />
        </Field>
        <Field label="Por usuário adicional (R$)" htmlFor="pl-usuad">
          <Input
            id="pl-usuad"
            type="number"
            step="0.01"
            min={0}
            value={f.preco_usuario_adicional}
            onChange={(e) => set("preco_usuario_adicional", e.target.value)}
            className="num"
          />
        </Field>
        <div className="sm:col-span-2">
          <p className="mb-2 text-[13px] text-foreground/80">Recursos liberados</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {recursos.map((r) => (
              <label key={r.chave} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                <Checkbox
                  checked={f.recursos.includes(r.chave)}
                  onCheckedChange={(v) => set("recursos", v ? [...f.recursos, r.chave] : f.recursos.filter((x) => x !== r.chave))}
                />
                {r.rotulo}
              </label>
            ))}
          </div>
        </div>
        <div className="sm:col-span-2">
          <SwitchRow titulo="Plano ativo" descricao="Inativo some do cadastro público e do “Meu plano”; quem já está nele continua.">
            <Switch checked={f.ativo} onCheckedChange={(v) => set("ativo", v)} aria-label="Plano ativo" />
          </SwitchRow>
        </div>
      </div>
    </FormDialog>
  );
}

function Indicacao() {
  const qc = useQueryClient();
  const pol = useQuery({ queryKey: ["admin", "politica"], queryFn: () => api.get<PoliticaIndicacao>("/admin/politica-indicacao") });
  const [f, setF] = useState({ desconto_por_indicacao: "", desconto_maximo: "" });
  /* eslint-disable react-hooks/set-state-in-effect -- carrega a política */
  useEffect(() => {
    if (pol.data) setF({ desconto_por_indicacao: pol.data.desconto_por_indicacao, desconto_maximo: pol.data.desconto_maximo });
  }, [pol.data]);
  /* eslint-enable react-hooks/set-state-in-effect */
  const salvar = useMutation({
    mutationFn: () => api.put("/admin/politica-indicacao", f),
    onSuccess: () => {
      toast.success("Política de indicação salva");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  const teto = pol.data ? toNum(pol.data.teto) : 10;
  const por = toNum(f.desconto_por_indicacao);
  const max = Math.min(toNum(f.desconto_maximo), teto);
  const fmt = (n: number) => n.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  return (
    <form
      className="card-surface space-y-4 p-5"
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
    >
      <div className="flex items-center gap-2">
        <Gift className="size-5 text-brand" />
        <h2 className="font-medium">Desconto por indicação</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Cada estúdio indicado que está pagando dá desconto na mensalidade de quem indicou. O desconto soma por indicação e nunca passa de{" "}
        {fmt(teto)}% da mensalidade.
      </p>
      <div className="grid max-w-md grid-cols-2 gap-4">
        <Field label="% por indicação" htmlFor="ind-por">
          <Input
            id="ind-por"
            type="number"
            step="0.5"
            min={0.5}
            max={teto}
            value={f.desconto_por_indicacao}
            onChange={(e) => setF({ ...f, desconto_por_indicacao: e.target.value })}
            className="num"
          />
        </Field>
        <Field label="Máximo (%)" htmlFor="ind-max" dica={`Até ${fmt(teto)}%.`}>
          <Input
            id="ind-max"
            type="number"
            step="0.5"
            min={0.5}
            max={teto}
            value={f.desconto_maximo}
            onChange={(e) => setF({ ...f, desconto_maximo: e.target.value })}
            className="num"
          />
        </Field>
      </div>
      {por > 0 && (
        <p className="text-xs text-muted-foreground">
          Exemplo: 1 indicação = {fmt(Math.min(por, max))}% · 2 = {fmt(Math.min(por * 2, max))}% · 3 = {fmt(Math.min(por * 3, max))}%
        </p>
      )}
      <Button type="submit" disabled={salvar.isPending || !pol.data}>
        <Save /> Salvar política
      </Button>
    </form>
  );
}

function SenhaSuporte() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "suporte"], queryFn: () => api.get<{ senha_definida: boolean }>("/admin/suporte") });
  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const salvar = useMutation({
    mutationFn: () => api.put("/admin/suporte", { senha }),
    onSuccess: () => {
      toast.success("Senha do Suporte salva");
      setSenha("");
      setConfirma("");
      qc.invalidateQueries({ queryKey: ["admin", "suporte"] });
    },
  });
  const diferente = confirma.length > 0 && confirma !== senha;
  return (
    <form
      id="suporte"
      className="card-surface scroll-mt-20 space-y-4 p-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (senha.length < 8) return toast.error("A senha precisa de pelo menos 8 caracteres.");
        if (senha !== confirma) return toast.error("As senhas não conferem.");
        salvar.mutate();
      }}
    >
      <div className="flex items-center gap-2">
        <LifeBuoy className="size-5 text-brand" />
        <h2 className="font-medium">Usuário Suporte</h2>
        {q.data && <Pill tom={q.data.senha_definida ? "success" : "warning"}>{q.data.senha_definida ? "senha definida" : "sem senha"}</Pill>}
      </div>
      <p className="text-sm text-muted-foreground">
        Todo estúdio novo ganha o usuário <b>Suporte</b> (login <span className="font-mono">suporte.identificador</span>) com esta senha. Ele não conta no
        limite de usuários do plano. A senha fica guardada cifrada e não pode ser lida; trocar aqui vale para os próximos estúdios.
      </p>
      <div className="grid max-w-md gap-4 sm:grid-cols-2">
        <Field label={q.data?.senha_definida ? "Nova senha" : "Senha"} htmlFor="sup-senha" dica="8+ caracteres, letras e números.">
          <SenhaInput id="sup-senha" autoComplete="new-password" value={senha} onChange={setSenha} forca />
        </Field>
        <Field label="Confirme" htmlFor="sup-conf" erro={diferente ? "As senhas não conferem" : undefined}>
          <SenhaInput id="sup-conf" autoComplete="new-password" value={confirma} onChange={setConfirma} />
        </Field>
      </div>
      <Button type="submit" disabled={salvar.isPending || !senha}>
        <Save /> Salvar senha
      </Button>
    </form>
  );
}
