"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Pencil } from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { AbaCobrancas } from "@/components/admin/cobranca";
import { EstudioDialog } from "@/components/admin/estudio-dialog";
import { AbaContratos, AbaDominios, AbaUso, AbaUsuarios } from "@/components/admin/ficha-abas";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { chaves, useExtras } from "@/lib/admin";
import { api } from "@/lib/api";
import { data, documento, moeda, toNum } from "@/lib/format";
import { type Estudio, ROTULO_STATUS, type StatusEstudio, TOM_STATUS } from "@/lib/tipos-admin";

const ABAS = ["uso", "usuarios", "dominios", "contratos", "cobrancas"];

const AVISO_STATUS: Record<StatusEstudio, string> = {
  teste: "O estúdio entra normalmente durante o teste grátis. Confira a data de fim do teste na ficha.",
  ativo: "O estúdio entra normalmente e passa a ser cobrado.",
  suspenso: "O estúdio continua entrando, mas vê um aviso de pagamento em atraso.",
  inativo: "Ninguém do estúdio consegue entrar enquanto estiver inativo (nem o app do aluno). Os dados são mantidos.",
};

function FichaConteudo() {
  const { id } = useParams<{ id: string }>();
  const aba = useSearchParams().get("aba");
  const qc = useQueryClient();
  const [editar, setEditar] = useState(false);
  const [mudar, setMudar] = useState<StatusEstudio | null>(null);
  const extras = useExtras();
  const c = useQuery({ queryKey: chaves.estudio(id), queryFn: () => api.get<Estudio>(`/admin/clientes/${id}`) });
  const status = useMutation({
    mutationFn: (s: StatusEstudio) => api.post<Estudio>(`/admin/clientes/${id}/status`, { status: s }),
    onSuccess: (r) => {
      toast.success(`${r.nome}: ${ROTULO_STATUS[r.status]}`);
      setMudar(null);
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  if (c.isPending) return <Skeleton className="h-72 rounded-2xl" />;
  if (!c.data)
    return <EmptyState icone={Building2} titulo="Estúdio não encontrado" descricao="Ele pode ter sido removido. Volte à lista de estúdios." />;
  const e = c.data;
  const rotuloExtra = (k: string) => extras.data?.find((x) => x.chave === k)?.rotulo ?? k;

  return (
    <div>
      <PageHeader
        titulo={e.nome}
        icone={Building2}
        migalhas={[{ label: "MayaCorp", href: "/admin" }, { label: "Estúdios", href: "/admin/estudios" }, { label: e.nome }]}
        descricao={
          <span className="font-mono text-xs">
            {e.slug}
            {e.documento && ` · ${documento(e.documento)}`}
            {e.banco_principal && " · banco principal"}
          </span>
        }
        acoes={
          <>
            <Button variant="outline" onClick={() => setEditar(true)}>
              <Pencil /> Editar ficha
            </Button>
            <NativeSelect
              aria-label="Mudar situação do estúdio"
              value=""
              onChange={(ev) => ev.target.value && setMudar(ev.target.value as StatusEstudio)}
              className="w-48"
            >
              <option value="">Mudar situação…</option>
              {(Object.keys(ROTULO_STATUS) as StatusEstudio[])
                .filter((s) => s !== e.status)
                .map((s) => (
                  <option key={s} value={s}>
                    {ROTULO_STATUS[s]}
                  </option>
                ))}
            </NativeSelect>
          </>
        }
      />

      <div className="card-surface mb-5 flex flex-wrap items-center gap-x-6 gap-y-3 p-4 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">Situação</p>
          <div className="mt-0.5 flex items-center gap-2">
            <Pill tom={TOM_STATUS[e.status]}>{ROTULO_STATUS[e.status]}</Pill>
            {e.status === "teste" && e.teste_ate && <span className="num text-xs text-muted-foreground">até {data(e.teste_ate)}</span>}
          </div>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Plano</p>
          <p className="mt-0.5">
            {e.plano ? (
              <>
                <b>{e.plano.nome}</b> ({e.ciclo}) · <span className="num">{moeda(e.valor_com_desconto ?? e.valor)}</span>
                {toNum(e.desconto_percentual) > 0 && (
                  <span className="text-success-ink">
                    {" "}
                    (−{toNum(e.desconto_percentual)}% por {e.indicacoes_ativas} indicação(ões); cheio <span className="num">{moeda(e.valor)}</span>)
                  </span>
                )}
              </>
            ) : (
              <span className="text-muted-foreground">Sem plano definido</span>
            )}
          </p>
        </div>
        {e.indicado_por && (
          <div>
            <p className="text-xs text-muted-foreground">Indicado por</p>
            <p className="mt-0.5">{e.indicado_por.nome}</p>
          </div>
        )}
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">Extras liberados</p>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {e.extras?.length ? (
              e.extras.map((k) => (
                <Pill key={k} tom="brand">
                  {rotuloExtra(k)}
                </Pill>
              ))
            ) : (
              <span className="text-muted-foreground">nenhum</span>
            )}
          </div>
        </div>
      </div>

      <Tabs defaultValue={aba && ABAS.includes(aba) ? aba : "uso"}>
        <TabsList className="max-w-full overflow-x-auto">
          <TabsTrigger value="uso">Uso e dados</TabsTrigger>
          <TabsTrigger value="usuarios">Usuários</TabsTrigger>
          <TabsTrigger value="dominios">Domínios</TabsTrigger>
          <TabsTrigger value="contratos">Contratos</TabsTrigger>
          <TabsTrigger value="cobrancas">Cobranças</TabsTrigger>
        </TabsList>
        <TabsContent value="uso" className="mt-4">
          <AbaUso estudio={e} />
        </TabsContent>
        <TabsContent value="usuarios" className="mt-4">
          <AbaUsuarios estudio={e} />
        </TabsContent>
        <TabsContent value="dominios" className="mt-4">
          <AbaDominios estudio={e} />
        </TabsContent>
        <TabsContent value="contratos" className="mt-4">
          <AbaContratos estudio={e} />
        </TabsContent>
        <TabsContent value="cobrancas" className="mt-4">
          <AbaCobrancas estudio={e} />
        </TabsContent>
      </Tabs>

      <EstudioDialog open={editar} onOpenChange={setEditar} estudio={e} />
      <ConfirmDialog
        open={!!mudar}
        onOpenChange={(o) => !o && setMudar(null)}
        titulo={mudar ? `Mudar para "${ROTULO_STATUS[mudar]}"?` : ""}
        descricao={mudar ? AVISO_STATUS[mudar] : undefined}
        confirmar="Confirmar"
        destrutivo={mudar === "inativo"}
        carregando={status.isPending}
        onConfirm={() => mudar && status.mutate(mudar)}
      />
    </div>
  );
}

export default function FichaEstudioPage() {
  return (
    <Suspense>
      <FichaConteudo />
    </Suspense>
  );
}
