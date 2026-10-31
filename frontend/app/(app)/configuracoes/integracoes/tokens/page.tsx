"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, MoreHorizontal, Pencil, Plus, Power, PowerOff, RefreshCw, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ValorUnicoDialog } from "@/components/integracoes/valor-unico-dialog";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill, StatusBadge } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora, relativo } from "@/lib/format";
import type { TokenApi, TokenApiComValor } from "@/lib/tipos-integracoes";
import { cn } from "@/lib/utils";

function NomeDialog({ token, open, onOpenChange, onCriado }: { token: TokenApi | null; open: boolean; onOpenChange: (o: boolean) => void; onCriado: (t: TokenApiComValor) => void }) {
  const qc = useQueryClient();
  const [nome, setNome] = useState(token?.nome ?? "");
  const salvar = useMutation({
    mutationFn: () => (token ? api.patch<TokenApi>(`/integracoes/tokens/${token.id}`, { nome }) : api.post<TokenApiComValor>("/integracoes/tokens", { nome })),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["integracao-tokens"] });
      onOpenChange(false);
      if (token) toast.success("Nome atualizado");
      else onCriado(r as TokenApiComValor);
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      titulo={token ? "Renomear token" : "Novo token de API"}
      descricao={token ? undefined : "Um token por empresa ou sistema que vai consultar o estúdio. O valor completo aparece uma única vez, ao criar."}
      rotuloSalvar={token ? "Salvar" : "Criar token"}
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        if (nome.trim().length < 2) return toast.error("Informe um nome com pelo menos 2 letras.");
        salvar.mutate();
      }}
    >
      <Field label="Empresa / descrição" obrigatorio dica="Ex.: Chatbot do WhatsApp, Agência Fulano.">
        <Input value={nome} onChange={(e) => setNome(e.target.value)} maxLength={120} autoFocus required />
      </Field>
    </FormDialog>
  );
}

export default function TokensPage() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("integracoes.editar");
  const [dialogo, setDialogo] = useState<{ t: TokenApi | null } | null>(null);
  const [valor, setValor] = useState<{ valor: string; nome: string; regenerado: boolean } | null>(null);
  const [regenerar, setRegenerar] = useState<TokenApi | null>(null);
  const [excluir, setExcluir] = useState<TokenApi | null>(null);
  const lista = useQuery({ queryKey: ["integracao-tokens"], queryFn: () => api.get<TokenApi[]>("/integracoes/tokens") });

  const alternar = useMutation({
    mutationFn: (t: TokenApi) => api.patch<TokenApi>(`/integracoes/tokens/${t.id}`, { ativo: !t.ativo }),
    onSuccess: (t) => {
      toast.success(t.ativo ? "Token ativado" : "Token desativado: o integrador recebe 401 a partir de agora");
      qc.invalidateQueries({ queryKey: ["integracao-tokens"] });
    },
  });
  const regen = useMutation({
    mutationFn: (t: TokenApi) => api.post<TokenApiComValor>(`/integracoes/tokens/${t.id}/regenerar`),
    onSuccess: (r) => {
      setRegenerar(null);
      setValor({ valor: r.valor, nome: r.nome, regenerado: true });
      qc.invalidateQueries({ queryKey: ["integracao-tokens"] });
    },
  });
  const apagar = useMutation({
    mutationFn: (t: TokenApi) => api.del(`/integracoes/tokens/${t.id}`),
    onSuccess: () => {
      toast.success("Token excluído");
      setExcluir(null);
      qc.invalidateQueries({ queryKey: ["integracao-tokens"] });
    },
  });

  const tokens = lista.data ?? [];
  const pendentes = tokens.filter((t) => t.precisa_regenerar);
  const base = typeof window === "undefined" ? "" : `${window.location.origin}/api/integracao`;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <KeyRound className="size-5 text-info-ink" /> Tokens de API
        </h2>
        <p className="text-sm text-muted-foreground">
          Chaves para empresas e chatbots consultarem alunos, aulas, contratos e faturas e gravarem mensagens de WhatsApp. Enviam o token no cabeçalho{" "}
          <code className="rounded bg-muted px-1 font-mono text-xs">X-API-Key</code> ou <code className="rounded bg-muted px-1 font-mono text-xs">Authorization: Bearer</code>.
        </p>
        {base && (
          <p className="mt-1 text-xs text-muted-foreground">
            Endereço da API: <code className="rounded bg-muted px-1 font-mono">{base}</code>
          </p>
        )}
      </div>

      {pendentes.length > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning-ink" role="alert">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">
              {pendentes.length === 1 ? "1 token veio do sistema antigo sem o valor" : `${pendentes.length} tokens vieram do sistema antigo sem o valor`}
            </p>
            <p className="mt-0.5">
              Por segurança, o sistema novo não guarda o valor dos tokens. Esses integradores <strong>não conseguem acessar</strong> até você usar{" "}
              <strong>Regenerar</strong> e repassar o novo valor a eles: {pendentes.map((t) => t.nome).join(", ")}.
            </p>
          </div>
        </div>
      )}

      <TableCard>
        <Toolbar>
          <p className="text-sm text-muted-foreground">
            {tokens.length === 0 ? "Nenhum token cadastrado" : `${tokens.length} token${tokens.length > 1 ? "s" : ""}`}
          </p>
          {editar && (
            <Button onClick={() => setDialogo({ t: null })}>
              <Plus /> Novo token
            </Button>
          )}
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={5} />
        ) : tokens.length === 0 ? (
          <EmptyState
            icone={KeyRound}
            titulo="Nenhum token de API"
            descricao="Crie um token para cada empresa ou sistema que precisa consultar o estúdio."
            acao={
              editar && (
                <Button onClick={() => setDialogo({ t: null })}>
                  <Plus /> Novo token
                </Button>
              )
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Empresa / descrição</th>
                  <th className="px-3 py-2.5 font-medium">Token</th>
                  <th className="px-3 py-2.5 font-medium">Situação</th>
                  <th className="hidden px-3 py-2.5 font-medium md:table-cell">Último uso</th>
                  <th className="hidden px-3 py-2.5 font-medium lg:table-cell">Criado em</th>
                  <th className="w-12 px-3 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {tokens.map((t) => (
                  <tr key={t.id} className={cn(t.precisa_regenerar && "bg-warning/5", !t.ativo && !t.precisa_regenerar && "opacity-60")}>
                    <td className="px-4 py-3 font-medium">{t.nome}</td>
                    <td className="px-3 py-3 font-mono text-xs text-muted-foreground">
                      {t.token_final ? `mayafit_••••••••${t.token_final}` : <span className="font-sans">sem valor</span>}
                    </td>
                    <td className="px-3 py-3">
                      {t.precisa_regenerar ? (
                        <Pill tom="warning">Precisa regenerar</Pill>
                      ) : t.ativo ? (
                        <StatusBadge status="ativo" />
                      ) : (
                        <StatusBadge label="Desativado" tom="neutral" />
                      )}
                    </td>
                    <td className="hidden px-3 py-3 text-muted-foreground md:table-cell" title={t.ultimo_uso ? dataHora(t.ultimo_uso) : undefined}>
                      {relativo(t.ultimo_uso)}
                    </td>
                    <td className="hidden px-3 py-3 text-muted-foreground lg:table-cell">{dataHora(t.criado_em)}</td>
                    <td className="px-3 py-3 text-right">
                      {editar && (
                        <DropdownMenu>
                          <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Ações do token ${t.nome}`} />}>
                            <MoreHorizontal />
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => setRegenerar(t)}>
                              <RefreshCw /> Regenerar
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setDialogo({ t })}>
                              <Pencil /> Renomear
                            </DropdownMenuItem>
                            {!t.precisa_regenerar && (
                              <DropdownMenuItem onClick={() => alternar.mutate(t)}>
                                {t.ativo ? <PowerOff /> : <Power />} {t.ativo ? "Desativar" : "Ativar"}
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem variant="destructive" onClick={() => setExcluir(t)}>
                              <Trash2 /> Excluir
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </TableCard>

      {dialogo && (
        <NomeDialog
          key={dialogo.t?.id ?? "novo"}
          token={dialogo.t}
          open
          onOpenChange={(o) => !o && setDialogo(null)}
          onCriado={(t) => setValor({ valor: t.valor, nome: t.nome, regenerado: false })}
        />
      )}
      <ValorUnicoDialog
        valor={valor?.valor ?? null}
        titulo={valor?.regenerado ? "Token regenerado" : "Token criado"}
        descricao={
          valor?.regenerado ? (
            <>
              O valor anterior de <strong>{valor.nome}</strong> deixou de valer. Repasse este ao integrador.
            </>
          ) : (
            <>
              Repasse este valor ao integrador de <strong>{valor?.nome}</strong>.
            </>
          )
        }
        onClose={() => setValor(null)}
      />
      <ConfirmDialog
        open={!!regenerar}
        onOpenChange={(o) => !o && setRegenerar(null)}
        titulo={`Regenerar o token de ${regenerar?.nome ?? ""}?`}
        descricao="O valor atual para de funcionar imediatamente. O integrador precisa receber o novo valor, que aparece uma única vez."
        confirmar="Regenerar"
        carregando={regen.isPending}
        onConfirm={() => regenerar && regen.mutate(regenerar)}
      />
      <ConfirmDialog
        open={!!excluir}
        onOpenChange={(o) => !o && setExcluir(null)}
        titulo={`Excluir o token de ${excluir?.nome ?? ""}?`}
        descricao="O integrador perde o acesso na hora e não há como desfazer. Para uma pausa temporária, use Desativar."
        confirmar="Excluir"
        destrutivo
        carregando={apagar.isPending}
        onConfirm={() => excluir && apagar.mutate(excluir)}
      />
    </div>
  );
}
