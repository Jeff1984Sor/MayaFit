"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Globe, KeyRound, LifeBuoy, Mail, Pencil, Plus, Send, Trash2, UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Medidor } from "@/components/admin/medidor";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { TableSkeleton } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { copiarTexto, mesAno } from "@/lib/admin";
import { abrirArquivo, api } from "@/lib/api";
import { data, dataHora, moeda, numero, relativo } from "@/lib/format";
import {
  type ContratoEstudio,
  type Estudio,
  type ModeloContrato,
  PERFIS_PADRAO,
  ROTULO_CONTRATO,
  type UsoEstudio,
  type UsuarioEstudio,
} from "@/lib/tipos-admin";

function Info({ rotulo, valor, mono }: { rotulo: string; valor: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{rotulo}</p>
      <p className={mono ? "num truncate text-sm" : "truncate text-sm"}>{valor || "—"}</p>
    </div>
  );
}

// ================================================================ uso e dados
export function AbaUso({ estudio }: { estudio: Estudio }) {
  const uso = useQuery({
    queryKey: ["admin", "uso", estudio.id],
    queryFn: () => api.get<UsoEstudio>(`/admin/clientes/${estudio.id}/uso`),
  });
  const u = uso.data;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="card-surface space-y-4 p-5">
        <p className="font-medium">Uso do mês {u ? `(${mesAno(u.mes)})` : ""}</p>
        {u ? (
          <>
            <Medidor rotulo="Alunos ativos" usado={u.alunos_ativos} limite={u.limite_alunos} />
            <Medidor rotulo="Usuários com acesso" usado={u.usuarios} limite={u.limite_usuarios} />
            {u.aulas_mes != null && (
              <p className="text-sm text-muted-foreground">
                Aulas no mês: <span className="num text-foreground">{numero(u.aulas_mes)}</span>
              </p>
            )}
            <p className="text-sm text-muted-foreground">
              Além do plano: <b className="num text-foreground">{moeda(u.valor_excedente)}</b>
              {(u.alunos_excedentes > 0 || u.usuarios_excedentes > 0) &&
                ` (${u.alunos_excedentes} aluno(s) e ${u.usuarios_excedentes} usuário(s) acima do limite)`}
            </p>
          </>
        ) : uso.isError ? (
          <p className="text-sm text-muted-foreground">Não foi possível ler o uso agora.</p>
        ) : (
          <Skeleton className="h-24" />
        )}
        {estudio.uso?.em && <p className="text-xs text-muted-foreground">Última foto do uso: {relativo(estudio.uso.em)}.</p>}
      </div>
      <div className="card-surface grid grid-cols-2 gap-4 p-5">
        <Info rotulo="Responsável" valor={estudio.responsavel} />
        <Info rotulo="E-mail do financeiro" valor={estudio.email_financeiro} />
        <Info rotulo="Telefone" valor={estudio.telefone} mono />
        <Info rotulo="Cliente desde" valor={data(estudio.criado_em)} mono />
        <Info rotulo="Início do contrato" valor={estudio.inicio_contrato ? data(estudio.inicio_contrato) : null} mono />
        <Info rotulo="Teste grátis até" valor={estudio.teste_ate ? data(estudio.teste_ate) : null} mono />
        <div className="col-span-2">
          <p className="text-xs text-muted-foreground">Observação</p>
          <p className="text-sm whitespace-pre-line">{estudio.observacao || "—"}</p>
        </div>
      </div>
    </div>
  );
}

// ================================================================ usuários do estúdio
const novoUsuario = () => ({ nome: "", email: "", login: "", perfil: PERFIS_PADRAO[0] as string });

export function AbaUsuarios({ estudio }: { estudio: Estudio }) {
  const qc = useQueryClient();
  const [novo, setNovo] = useState(false);
  const [zerar, setZerar] = useState<UsuarioEstudio | null>(null);
  const [f, setF] = useState(novoUsuario);
  const chave = ["admin", "usuarios", estudio.id];
  const lista = useQuery({ queryKey: chave, queryFn: () => api.get<UsuarioEstudio[]>(`/admin/clientes/${estudio.id}/usuarios`) });
  const criar = useMutation({
    mutationFn: () =>
      api.post<UsuarioEstudio & { convite?: string }>(`/admin/clientes/${estudio.id}/usuarios`, {
        nome: f.nome.trim(),
        email: f.email.trim(),
        login: f.login.trim().toLowerCase() || null,
        perfil: f.perfil,
      }),
    onSuccess: (u) => {
      toast.success(`Convite enviado para ${u.email}`, {
        action: u.convite ? { label: "Copiar link", onClick: () => copiarTexto(u.convite!) } : undefined,
      });
      setNovo(false);
      setF(novoUsuario());
      qc.invalidateQueries({ queryKey: chave });
    },
  });
  const zerarSenha = useMutation({
    mutationFn: (u: UsuarioEstudio) => api.post<{ mensagem: string; link?: string }>(`/admin/clientes/${estudio.id}/usuarios/${u.id}/zerar-senha`),
    onSuccess: (r) => {
      toast.success(r.mensagem, { action: r.link ? { label: "Copiar link", onClick: () => copiarTexto(r.link!) } : undefined });
      setZerar(null);
      qc.invalidateQueries({ queryKey: chave });
    },
  });
  const boasVindas = useMutation({
    mutationFn: () => api.post<{ link: string; enviado_para: string }>(`/admin/clientes/${estudio.id}/boas-vindas`),
    onSuccess: (r) =>
      toast.success(`Link de primeiro acesso reenviado para ${r.enviado_para}`, {
        action: { label: "Copiar link", onClick: () => copiarTexto(r.link) },
      }),
  });
  const ativo = useMutation({
    mutationFn: ({ u, v }: { u: UsuarioEstudio; v: boolean }) => api.post(`/admin/clientes/${estudio.id}/usuarios/${u.id}/ativo`, { ativo: v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: chave }),
  });
  const temMaster = (lista.data ?? []).some((u) => !u.equipe_mayacorp && !u.convite_pendente);

  return (
    <div className="space-y-4">
      <div className="card-surface flex flex-wrap items-start gap-3 p-4">
        <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-brand/10 text-navy dark:text-brand">
          <LifeBuoy className="size-4" />
        </div>
        <div className="min-w-0 flex-1 text-sm">
          <p className="font-medium">Usuário Suporte</p>
          <p className="text-muted-foreground">
            Login <span className="font-mono text-foreground">suporte.{estudio.slug}</span>. A senha é a definida em{" "}
            <Link href="/admin/planos#suporte" className="underline underline-offset-2 hover:text-foreground">
              Planos › Usuário Suporte
            </Link>{" "}
            quando o estúdio foi criado. Ele não conta no limite de usuários do plano.
          </p>
        </div>
      </div>

      <div className="card-surface overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b p-3">
          <p className="text-sm text-muted-foreground">Usuários do estúdio</p>
          <div className="flex flex-wrap gap-2">
            {!temMaster && (
              <Button size="sm" variant="outline" disabled={boasVindas.isPending} onClick={() => boasVindas.mutate()}>
                <Mail /> Reenviar primeiro acesso
              </Button>
            )}
            <Button size="sm" onClick={() => setNovo(true)}>
              <UserPlus /> Novo usuário
            </Button>
          </div>
        </div>
        {lista.isPending ? (
          <TableSkeleton colunas={4} linhas={3} />
        ) : !lista.data?.length ? (
          <EmptyState icone={Users} titulo="Nenhum usuário" descricao="O dono cria o usuário master pelo link de primeiro acesso." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Nome</th>
                  <th className="px-3 py-2.5 font-medium">Login</th>
                  <th className="px-3 py-2.5 font-medium">Perfil</th>
                  <th className="px-3 py-2.5 font-medium">Último acesso</th>
                  <th className="px-3 py-2.5 font-medium">Ativo</th>
                  <th className="px-3 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {lista.data.map((u) => (
                  <tr key={u.id} className={u.ativo ? "" : "opacity-60"}>
                    <td className="px-4 py-3">
                      <p className="font-medium">
                        {u.nome} {u.equipe_mayacorp && <Pill tom="brand">Suporte</Pill>}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {u.email ?? "sem e-mail"}
                        {u.convite_pendente && <Pill className="ml-1.5">convite pendente</Pill>}
                      </p>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">{u.login ?? "—"}</td>
                    <td className="px-3 py-3">{u.perfil}</td>
                    <td className="px-3 py-3 text-xs">{u.ultimo_acesso ? dataHora(u.ultimo_acesso) : "nunca"}</td>
                    <td className="px-3 py-3">
                      <Switch checked={u.ativo} onCheckedChange={(v) => ativo.mutate({ u, v })} aria-label={`Ativo: ${u.nome}`} />
                    </td>
                    <td className="px-3 py-3 text-right">
                      <Button variant="ghost" size="sm" onClick={() => setZerar(u)} disabled={!u.email}>
                        <KeyRound /> Zerar senha
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <FormDialog
        open={novo}
        onOpenChange={setNovo}
        titulo="Novo usuário do estúdio"
        descricao="A pessoa recebe um convite por e-mail para criar a senha."
        salvando={criar.isPending}
        rotuloSalvar="Enviar convite"
        onSubmit={(e) => {
          e.preventDefault();
          if (f.nome.trim().length < 2) return toast.error("Informe o nome.");
          if (!f.email.trim()) return toast.error("Informe o e-mail para o convite.");
          criar.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nome" obrigatorio htmlFor="usu-nome" className="sm:col-span-2">
            <Input id="usu-nome" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} autoFocus />
          </Field>
          <Field label="E-mail" obrigatorio htmlFor="usu-email" dica="Recebe o convite; não é usado para entrar.">
            <Input id="usu-email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          </Field>
          <Field label="Login" htmlFor="usu-login" dica="Curto, para entrar. Ex.: ana. Vazio = gerado pelo nome.">
            <Input id="usu-login" value={f.login} onChange={(e) => setF({ ...f, login: e.target.value.toLowerCase() })} className="font-mono" />
          </Field>
          <Field label="Perfil" htmlFor="usu-perfil" className="sm:col-span-2">
            <NativeSelect id="usu-perfil" value={f.perfil} onChange={(e) => setF({ ...f, perfil: e.target.value })}>
              {PERFIS_PADRAO.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </NativeSelect>
          </Field>
        </div>
      </FormDialog>
      <ConfirmDialog
        open={!!zerar}
        onOpenChange={(o) => !o && setZerar(null)}
        titulo={zerar ? `Zerar a senha de ${zerar.nome}?` : ""}
        descricao="A senha atual deixa de funcionar na hora e a pessoa recebe por e-mail o link para criar outra."
        confirmar="Zerar senha"
        destrutivo
        carregando={zerarSenha.isPending}
        onConfirm={() => zerar && zerarSenha.mutate(zerar)}
      />
    </div>
  );
}

// ================================================================ domínios
export function AbaDominios({ estudio }: { estudio: Estudio }) {
  const qc = useQueryClient();
  const [host, setHost] = useState("");
  const [remover, setRemover] = useState<{ id: number; host: string } | null>(null);
  const add = useMutation({
    mutationFn: () => api.post<Estudio>(`/admin/clientes/${estudio.id}/dominios`, { host: host.trim().toLowerCase() }),
    onSuccess: () => {
      toast.success("Domínio cadastrado. Aponte o DNS dele para o servidor do MayaFit.");
      setHost("");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  const del = useMutation({
    mutationFn: (did: number) => api.del<Estudio>(`/admin/clientes/${estudio.id}/dominios/${did}`),
    onSuccess: () => {
      toast.success("Domínio removido");
      setRemover(null);
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  return (
    <div className="card-surface space-y-4 p-5">
      <p className="text-sm text-muted-foreground">
        Quem entra por um destes endereços cai direto no estúdio, com o nome e o logo dele — inclusive o app do aluno e os links de
        assinatura. O endereço <span className="font-mono">{estudio.slug}.&lt;domínio do MayaFit&gt;</span> já vem pronto.
      </p>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (host.trim().length >= 4) add.mutate();
        }}
      >
        <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="app.studioana.com.br" className="max-w-sm font-mono" aria-label="Novo domínio" />
        <Button type="submit" disabled={add.isPending || host.trim().length < 4}>
          <Plus /> Adicionar
        </Button>
      </form>
      {estudio.dominios.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum domínio cadastrado.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {estudio.dominios.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 px-3 py-2">
              <span className="flex min-w-0 items-center gap-2 font-mono text-sm">
                <Globe className="size-4 shrink-0 text-muted-foreground" /> <span className="truncate">{d.host}</span>
              </span>
              <span className="flex gap-1">
                <Button variant="ghost" size="icon-sm" aria-label={`Abrir ${d.host}`} render={<a href={`https://${d.host}`} target="_blank" rel="noopener noreferrer" />}>
                  <ExternalLink />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label={`Remover ${d.host}`} onClick={() => setRemover(d)}>
                  <Trash2 />
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={!!remover}
        onOpenChange={(o) => !o && setRemover(null)}
        titulo={`Remover ${remover?.host ?? ""}?`}
        descricao="Quem entrar por este endereço deixa de cair no estúdio."
        confirmar="Remover"
        destrutivo
        carregando={del.isPending}
        onConfirm={() => remover && del.mutate(remover.id)}
      />
    </div>
  );
}

// ================================================================ contratos do estúdio
export function AbaContratos({ estudio }: { estudio: Estudio }) {
  const qc = useQueryClient();
  const chave = ["admin", "contratos", "estudio", estudio.id];
  const modelos = useQuery({ queryKey: ["admin", "modelos"], queryFn: () => api.get<ModeloContrato[]>("/admin/modelos-contrato") });
  const lista = useQuery({ queryKey: chave, queryFn: () => api.get<ContratoEstudio[]>(`/admin/clientes/${estudio.id}/contratos`) });
  const [modelo, setModelo] = useState("");
  const [aberto, setAberto] = useState<ContratoEstudio | null>(null);
  const [envio, setEnvio] = useState<ContratoEstudio | null>(null);
  const [para, setPara] = useState("");
  const [mensagem, setMensagem] = useState("");
  const atualizar = () => qc.invalidateQueries({ queryKey: ["admin", "contratos"] });
  const gerar = useMutation({
    mutationFn: () => api.post<ContratoEstudio>(`/admin/clientes/${estudio.id}/contratos`, { modelo_id: Number(modelo) }),
    onSuccess: (k) => {
      if (k.variaveis_vazias?.length) toast.warning(`Campos sem valor na ficha: ${k.variaveis_vazias.join(", ")}. Confira o texto.`);
      else toast.success("Contrato gerado. Revise e envie.");
      setAberto(k);
      atualizar();
    },
  });
  const salvar = useMutation({
    mutationFn: (k: ContratoEstudio) => api.put<ContratoEstudio>(`/admin/contratos/${k.id}`, { titulo: k.titulo, corpo: k.corpo }),
    onSuccess: () => {
      toast.success("Contrato salvo");
      setAberto(null);
      atualizar();
    },
  });
  const enviar = useMutation({
    mutationFn: () =>
      api.post<ContratoEstudio>(`/admin/contratos/${envio!.id}/enviar`, {
        para: para.split(/[,;\s]+/).filter(Boolean),
        mensagem: mensagem.trim() || null,
      }),
    onSuccess: (k) => {
      toast.success(`Contrato enviado para ${k.enviado_para.join(", ")}`);
      setEnvio(null);
      atualizar();
    },
  });
  const marcar = useMutation({
    mutationFn: ({ k, s }: { k: ContratoEstudio; s: "assinado" | "cancelado" }) => api.post(`/admin/contratos/${k.id}/status`, { status: s }),
    onSuccess: (_r, v) => {
      toast.success(v.s === "assinado" ? "Contrato marcado como assinado" : "Contrato cancelado");
      atualizar();
    },
  });
  const ativos = (modelos.data ?? []).filter((m) => m.ativo);

  return (
    <div className="card-surface overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        <NativeSelect aria-label="Modelo de contrato" value={modelo} onChange={(e) => setModelo(e.target.value)} className="h-9 w-72">
          <option value="">{ativos.length ? "Escolha o modelo…" : "Cadastre um modelo antes"}</option>
          {ativos.map((m) => (
            <option key={m.id} value={m.id}>
              {m.nome}
            </option>
          ))}
        </NativeSelect>
        <Button size="sm" disabled={!modelo || gerar.isPending} onClick={() => gerar.mutate()}>
          <FileText /> Gerar contrato
        </Button>
        <Link href="/admin/contratos?aba=modelos" className="ml-auto text-xs text-muted-foreground hover:underline">
          Modelos de contrato
        </Link>
      </div>
      {lista.isPending ? (
        <TableSkeleton colunas={3} linhas={2} />
      ) : !lista.data?.length ? (
        <EmptyState icone={FileText} titulo="Nenhum contrato" descricao="Gere a partir de um modelo: os dados da ficha entram sozinhos." />
      ) : (
        <ul className="divide-y">
          {lista.data.map((k) => (
            <li key={k.id} className="flex flex-wrap items-center gap-2 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{k.titulo}</p>
                <p className="text-xs text-muted-foreground">
                  Gerado em {data(k.criado_em)}
                  {k.enviado_em && ` · enviado em ${dataHora(k.enviado_em)} para ${k.enviado_para.join(", ")}`}
                </p>
              </div>
              <Pill tom={ROTULO_CONTRATO[k.status][1]}>{ROTULO_CONTRATO[k.status][0]}</Pill>
              <Button variant="ghost" size="sm" onClick={() => abrirArquivo(`/admin/contratos/${k.id}/pdf`)}>
                PDF
              </Button>
              {k.status === "rascunho" && (
                <Button variant="ghost" size="sm" onClick={() => setAberto(k)}>
                  <Pencil /> Revisar
                </Button>
              )}
              {(k.status === "rascunho" || k.status === "enviado") && (
                <Button
                  size="sm"
                  onClick={() => {
                    setPara(estudio.email_financeiro ?? "");
                    setMensagem("");
                    setEnvio(k);
                  }}
                >
                  <Send /> {k.status === "enviado" ? "Reenviar" : "Enviar"}
                </Button>
              )}
              {k.status === "enviado" && (
                <Button variant="outline" size="sm" disabled={marcar.isPending} onClick={() => marcar.mutate({ k, s: "assinado" })}>
                  Marcar assinado
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <FormDialog
        open={!!aberto}
        onOpenChange={(o) => !o && setAberto(null)}
        titulo="Revisar contrato"
        descricao="O texto já vem com os dados da ficha. Ajuste o que precisar antes de enviar."
        largura="xl"
        salvando={salvar.isPending}
        onSubmit={(e) => {
          e.preventDefault();
          if (aberto) salvar.mutate(aberto);
        }}
      >
        {aberto && (
          <div className="grid gap-4">
            <Field label="Título" htmlFor="ct-titulo">
              <Input id="ct-titulo" value={aberto.titulo} onChange={(e) => setAberto({ ...aberto, titulo: e.target.value })} />
            </Field>
            <Field label="Texto" htmlFor="ct-corpo">
              <Textarea
                id="ct-corpo"
                rows={18}
                value={aberto.corpo}
                onChange={(e) => setAberto({ ...aberto, corpo: e.target.value })}
                className="font-mono text-xs"
              />
            </Field>
          </div>
        )}
      </FormDialog>
      <FormDialog
        open={!!envio}
        onOpenChange={(o) => !o && setEnvio(null)}
        titulo="Enviar contrato por e-mail"
        descricao="O PDF vai em anexo."
        salvando={enviar.isPending}
        rotuloSalvar="Enviar"
        onSubmit={(e) => {
          e.preventDefault();
          if (!para.trim()) return toast.error("Informe o e-mail.");
          enviar.mutate();
        }}
      >
        <div className="grid gap-4">
          <Field label="Para" obrigatorio htmlFor="ct-para" dica="Separe vários e-mails com vírgula.">
            <Input id="ct-para" value={para} onChange={(e) => setPara(e.target.value)} />
          </Field>
          <Field label="Mensagem" htmlFor="ct-msg" dica="Opcional; sem ela vai um texto padrão.">
            <Textarea id="ct-msg" rows={4} value={mensagem} onChange={(e) => setMensagem(e.target.value)} />
          </Field>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Mail className="size-3.5" /> {envio?.titulo}
          </p>
        </div>
      </FormDialog>
    </div>
  );
}
