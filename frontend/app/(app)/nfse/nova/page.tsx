"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Building2, FilePlus2, GraduationCap, Loader2, Send, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/mayacorp/data-table";
import { Field } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { hojeIso } from "@/components/nfse/comum";
import { PainelRaioX } from "@/components/nfse/raio-x";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { NotaAvulsaIn, NotaDetalhe, RaioX, TomadorBusca } from "@/lib/tipos-nfse";
import { cn } from "@/lib/utils";

type Tipo = "aluno" | "pessoa" | "empresa";

export default function NovaNotaPage() {
  const { pode } = useAuth();
  const router = useRouter();
  const [tipo, setTipo] = useState<Tipo>("aluno");
  const [busca, setBusca] = useState("");
  const [aluno, setAluno] = useState<TomadorBusca | null>(null);
  const [doc, setDoc] = useState("");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [valor, setValor] = useState("");
  const [competencia, setCompetencia] = useState(hojeIso());
  const [descricao, setDescricao] = useState("");
  const [discriminacao, setDiscriminacao] = useState("");
  const termo = useDebounce(busca, 250);

  const sugestoes = useQuery({
    queryKey: ["nfse", "tomadores", termo],
    queryFn: () => api.get<TomadorBusca[]>("/nfse/tomadores", { q: termo }),
    enabled: tipo === "aluno" && termo.length >= 2 && !aluno,
  });

  const corpo: NotaAvulsaIn | null = useMemo(() => {
    const v = valor.replace(/\./g, "").replace(",", ".");
    if (!v || Number.isNaN(Number(v)) || Number(v) <= 0) return null;
    if (tipo === "aluno" && !aluno) return null;
    if (tipo !== "aluno" && (!nome.trim() || !doc.trim())) return null;
    return {
      tomador: tipo === "aluno" ? { tipo, aluno_id: aluno!.id } : { tipo, documento: doc, nome, email: email || null },
      valor: Number(v).toFixed(2),
      competencia: competencia || null,
      descricao: descricao || null,
      discriminacao: discriminacao.trim() || null,
    };
  }, [tipo, aluno, doc, nome, email, valor, competencia, descricao, discriminacao]);
  const corpoDebounced = useDebounce(corpo, 500);

  const raio = useQuery({
    queryKey: ["nfse", "raio-x", "avulsa", corpoDebounced],
    queryFn: () => api.post<RaioX>("/nfse/raio-x", { avulsa: corpoDebounced }),
    enabled: !!corpoDebounced,
  });

  const emitir = useMutation({
    mutationFn: () => api.post<NotaDetalhe>("/nfse/notas", corpo),
    onSuccess: (n) => {
      if (n.status === "emitida") toast.success(`NFS-e nº ${n.numero_nfse ?? ""} emitida.`);
      else if (n.status === "rejeitada") toast.error("A nota foi recusada. Veja o raio-x do retorno.");
      else toast.message("Nota enviada para a fila.");
      router.push(`/nfse/${n.id}`);
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Não foi possível emitir."),
  });

  if (!pode("nfse.emitir")) return <SemAcesso />;
  const previa = raio.data?.previa[0];

  return (
    <div>
      <PageHeader
        titulo="Nova nota fiscal"
        descricao="Nota avulsa para um aluno, outra pessoa ou empresa. O raio-x confere tudo enquanto você digita."
        icone={FilePlus2}
        migalhas={[{ label: "Início", href: "/" }, { label: "Notas fiscais", href: "/nfse" }, { label: "Nova" }]}
      />
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <form
          className="card-surface grid gap-5 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (corpo) emitir.mutate();
          }}
        >
          <div>
            <p className="mb-2 text-sm font-semibold">Tomador do serviço</p>
            <Segmented<Tipo>
              value={tipo}
              onChange={(v) => {
                setTipo(v);
                setAluno(null);
              }}
              opcoes={[
                { value: "aluno", label: "Aluno" },
                { value: "pessoa", label: "Outra pessoa" },
                { value: "empresa", label: "Empresa" },
              ]}
            />
          </div>
          {tipo === "aluno" ? (
            aluno ? (
              <div className="flex items-center justify-between gap-3 rounded-xl border bg-background/50 p-3">
                <div className="flex items-center gap-3">
                  <div className="grid size-9 place-items-center rounded-full bg-brand/12 text-navy dark:text-brand">
                    <GraduationCap className="size-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{aluno.nome}</p>
                    <p className={cn("text-xs", aluno.tem_cpf ? "text-muted-foreground" : "text-danger-ink")}>
                      {aluno.tem_cpf ? `CPF ${aluno.cpf_mascarado}` : "Sem CPF: cadastre antes de emitir"} · {aluno.email ?? "sem e-mail"}
                    </p>
                  </div>
                </div>
                <Button type="button" variant="ghost" size="sm" onClick={() => setAluno(null)}>
                  Trocar
                </Button>
              </div>
            ) : (
              <Field label="Buscar aluno" obrigatorio dica="Nome ou início do CPF">
                <div className="relative">
                  <Input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Ex.: Maria" autoFocus />
                  {(sugestoes.data?.length ?? 0) > 0 && (
                    <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border bg-popover shadow-lg">
                      {sugestoes.data!.map((a) => (
                        <button
                          key={a.id}
                          type="button"
                          onClick={() => setAluno(a)}
                          className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                        >
                          <span>{a.nome}</span>
                          <span className={cn("text-xs num", a.tem_cpf ? "text-muted-foreground" : "text-danger-ink")}>
                            {a.cpf_mascarado ?? "sem CPF"}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </Field>
            )
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={tipo === "empresa" ? "CNPJ" : "CPF"} obrigatorio>
                <Input value={doc} onChange={(e) => setDoc(e.target.value)} inputMode="numeric" placeholder={tipo === "empresa" ? "00.000.000/0000-00" : "000.000.000-00"} />
              </Field>
              <Field label={tipo === "empresa" ? "Razão social" : "Nome"} obrigatorio>
                <div className="relative">
                  {tipo === "empresa" ? (
                    <Building2 className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                  ) : (
                    <UserRound className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                  )}
                  <Input className="pl-8" value={nome} onChange={(e) => setNome(e.target.value)} maxLength={150} />
                </div>
              </Field>
              <Field label="E-mail (recebe a nota)" className="sm:col-span-2">
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </Field>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Valor (R$)" obrigatorio>
              <Input value={valor} onChange={(e) => setValor(e.target.value)} inputMode="decimal" placeholder="300,00" className="num" />
            </Field>
            <Field label="Competência" dica="Mês do serviço prestado">
              <Input type="date" value={competencia} max={hojeIso()} onChange={(e) => setCompetencia(e.target.value)} />
            </Field>
            <Field label="Descrição curta" dica="Entra no lugar de {descricao}">
              <Input value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="Pilates 2x por semana" maxLength={200} />
            </Field>
          </div>
          <Field
            label="Discriminação (opcional)"
            dica={previa && !discriminacao ? `Pelo modelo: “${previa.discriminacao}”` : "Em branco = usa o modelo da configuração fiscal."}
          >
            <Textarea rows={3} maxLength={2000} value={discriminacao} onChange={(e) => setDiscriminacao(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button type="button" variant="outline" onClick={() => router.back()}>
              Voltar
            </Button>
            <Button type="submit" disabled={!corpo || emitir.isPending || (raio.data && !raio.data.pode_emitir)}>
              {emitir.isPending ? <Loader2 className="animate-spin" /> : <Send />}
              Emitir nota
            </Button>
          </div>
        </form>
        <PainelRaioX raio={corpo ? raio.data : undefined} carregando={raio.isFetching} className="h-fit lg:sticky lg:top-4" />
      </div>
    </div>
  );
}
