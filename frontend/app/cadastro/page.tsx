"use client";

import { Check, CheckCircle2, Dumbbell, Gift, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/mayacorp/data-table";
import { Field } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { soDigitos } from "@/lib/admin";
import { api } from "@/lib/api";
import { moeda, numero } from "@/lib/format";
import { type CadastroIn, type Ciclo, type PlanoOut, RECURSOS_PADRAO, type Rotulo } from "@/lib/tipos-admin";
import { cn } from "@/lib/utils";

type PlanoPublico = PlanoOut & { recursos_rotulos?: Rotulo[] };

/**
 * Cadastro público "Quero o MayaFit" (site/anúncios): vira uma solicitação no Admin MayaFit.
 * ?plano=<nome> já deixa o plano marcado · ?ciclo=anual · ?embed=1 tira o cabeçalho (para usar num iframe).
 */
export default function CadastroPage() {
  const [planos, setPlanos] = useState<PlanoPublico[] | null>(null);
  const [ciclo, setCiclo] = useState<Ciclo>("mensal");
  const [embed, setEmbed] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [f, setF] = useState({
    plano_id: null as number | null,
    nome: "",
    documento: "",
    responsavel: "",
    email: "",
    telefone: "",
    alunos: "",
    indicacao: "",
    mensagem: "",
    aceite: false,
    site: "",
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((o) => ({ ...o, [k]: v }));

  /* eslint-disable react-hooks/set-state-in-effect -- lê os planos e os parâmetros do link uma vez */
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    setEmbed(qs.get("embed") === "1");
    if (qs.get("ciclo") === "anual") setCiclo("anual");
    api
      .get<PlanoPublico[]>("/public/planos")
      .then((ps) => {
        setPlanos(ps);
        const pedido = qs.get("plano")?.toLowerCase();
        const p = ps.find((x) => x.nome.toLowerCase() === pedido) ?? ps[0];
        if (p) setF((o) => ({ ...o, plano_id: p.id }));
      })
      .catch(() => {
        setPlanos([]);
        toast.error("Não foi possível carregar os planos. Recarregue a página.");
      });
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  const rotulo = (p: PlanoPublico, k: string) => p.recursos_rotulos?.find((r) => r.chave === k)?.rotulo ?? RECURSOS_PADRAO[k] ?? k;
  const plano = planos?.find((x) => x.id === f.plano_id);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const doc = soDigitos(f.documento);
    if (doc && doc.length !== 11 && doc.length !== 14) return toast.error("Confira o CNPJ ou CPF (ou deixe em branco).");
    if (!f.aceite) return toast.error("Marque a autorização para continuar.");
    setEnviando(true);
    try {
      const corpo: CadastroIn = {
        nome: f.nome.trim(),
        documento: doc || null,
        responsavel: f.responsavel.trim(),
        email: f.email.trim(),
        telefone: f.telefone.trim(),
        plano_id: f.plano_id,
        ciclo,
        alunos: f.alunos ? Number(f.alunos) : null,
        indicacao: f.indicacao.trim() || null,
        mensagem: f.mensagem.trim() || null,
        aceite: f.aceite,
        site: f.site,
      };
      await api.post("/public/cadastro", corpo, { auth: false });
      setEnviado(true);
      window.parent?.postMessage({ mayafit: "cadastro-enviado" }, "*"); // o site pode reagir (ex.: evento de conversão)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Não foi possível enviar. Tente de novo.");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="min-h-dvh bg-background">
      {!embed && (
        <header className="bg-dark-maya text-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-5">
            <div className="flex items-center gap-3">
              <div className="grid size-10 place-items-center rounded-xl brand-gradient shadow-lg shadow-brand/30">
                <Dumbbell className="size-5" />
              </div>
              <div>
                <p className="text-lg leading-tight font-semibold">MayaFit</p>
                <p className="text-xs text-white/60">Gestão para estúdios</p>
              </div>
            </div>
            <span className="hidden text-sm text-white/70 sm:block">Agenda, alunos, contratos e financeiro num lugar só</span>
          </div>
        </header>
      )}
      <main className="mx-auto max-w-5xl px-4 py-8">
        {enviado ? (
          <div className="card-surface mx-auto max-w-lg space-y-4 p-8 text-center">
            <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-success/10">
              <CheckCircle2 className="size-7 text-success" />
            </div>
            <h1 className="text-2xl font-semibold">Recebemos o seu pedido!</h1>
            <p className="text-sm text-muted-foreground">
              Em breve você recebe no e-mail <b>{f.email}</b> o link para criar o seu acesso e começar os <b>2 meses grátis</b>.
            </p>
          </div>
        ) : (
          <form onSubmit={enviar} className="space-y-8">
            <div className="text-center">
              <span className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1 text-sm font-medium text-success-ink ring-1 ring-success/25">
                <Gift className="size-4" /> 2 meses grátis, sem cartão
              </span>
              <h1 className="text-3xl font-semibold tracking-tight">Quero o MayaFit</h1>
              <p className="mt-2 text-muted-foreground">Escolha o plano, conte um pouco do seu estúdio e comece a usar. Você só paga depois do teste.</p>
            </div>

            <section>
              <div className="mb-4 flex justify-center">
                <Segmented
                  value={ciclo}
                  onChange={setCiclo}
                  opcoes={[
                    { value: "mensal", label: "Mensal" },
                    { value: "anual", label: "Anual" },
                  ]}
                />
              </div>
              {planos === null ? (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-48 rounded-2xl" />
                  ))}
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {planos.map((p) => {
                    const sel = f.plano_id === p.id;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => set("plano_id", p.id)}
                        aria-pressed={sel}
                        className={cn(
                          "card-surface flex flex-col gap-2 p-5 text-left transition-colors hover:border-brand/60",
                          sel && "border-brand ring-2 ring-brand",
                        )}
                      >
                        <span className="flex items-center justify-between font-semibold">
                          {p.nome} {sel && <CheckCircle2 className="size-5 text-brand" />}
                        </span>
                        <span className="num text-xl">
                          {moeda(ciclo === "anual" ? p.preco_anual : p.preco_mensal)}
                          <span className="font-sans text-xs text-muted-foreground">/{ciclo === "anual" ? "ano" : "mês"}</span>
                        </span>
                        <ul className="space-y-1 text-xs text-muted-foreground">
                          <li>{p.alunos_ativos != null ? `Até ${numero(p.alunos_ativos)} alunos ativos` : "Alunos ilimitados"}</li>
                          <li>{p.usuarios != null ? `${numero(p.usuarios)} usuário(s)` : "Usuários ilimitados"}</li>
                          {p.recursos.map((r) => (
                            <li key={r} className="flex items-center gap-1">
                              <Check className="size-3 shrink-0 text-success" /> {rotulo(p, r)}
                            </li>
                          ))}
                        </ul>
                      </button>
                    );
                  })}
                </div>
              )}
            </section>

            <section className="card-surface grid gap-4 p-6 sm:grid-cols-2">
              <Field label="Nome do estúdio" obrigatorio htmlFor="cad-nome">
                <Input id="cad-nome" required minLength={2} value={f.nome} onChange={(e) => set("nome", e.target.value)} />
              </Field>
              <Field label="CNPJ ou CPF" htmlFor="cad-doc" dica="Opcional; ajuda no contrato.">
                <Input id="cad-doc" value={f.documento} onChange={(e) => set("documento", e.target.value)} inputMode="numeric" className="num" />
              </Field>
              <Field label="Seu nome" obrigatorio htmlFor="cad-resp">
                <Input id="cad-resp" required minLength={3} value={f.responsavel} onChange={(e) => set("responsavel", e.target.value)} autoComplete="name" />
              </Field>
              <Field label="E-mail" obrigatorio htmlFor="cad-email" dica="Recebe o link de acesso.">
                <Input id="cad-email" type="email" required value={f.email} onChange={(e) => set("email", e.target.value)} autoComplete="email" />
              </Field>
              <Field label="Telefone / WhatsApp" obrigatorio htmlFor="cad-tel">
                <Input
                  id="cad-tel"
                  type="tel"
                  required
                  minLength={8}
                  value={f.telefone}
                  onChange={(e) => set("telefone", e.target.value)}
                  autoComplete="tel"
                  className="num"
                />
              </Field>
              <Field label="Quantos alunos ativos você tem hoje?" htmlFor="cad-alunos" dica="Um número aproximado já ajuda a indicar o plano certo.">
                <Input id="cad-alunos" type="number" min={0} max={100000} value={f.alunos} onChange={(e) => set("alunos", e.target.value)} className="num" />
              </Field>
              <Field label="Como prefere pagar depois do teste?" className="sm:col-span-2">
                <div className="grid gap-2 sm:grid-cols-2">
                  {(["mensal", "anual"] as const).map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setCiclo(c)}
                      aria-pressed={ciclo === c}
                      className={cn("rounded-xl border p-3 text-left text-sm transition-colors hover:border-brand/60", ciclo === c && "border-brand ring-2 ring-brand")}
                    >
                      <span className="font-medium">{c === "mensal" ? "Mensal" : "Anual"}</span>
                      {plano && (
                        <span className="num block text-xs text-muted-foreground">
                          {c === "mensal" ? `${moeda(plano.preco_mensal)} por mês` : `${moeda(plano.preco_anual)} por ano`}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="Quem indicou? (opcional)" htmlFor="cad-ind" className="sm:col-span-2">
                <Input id="cad-ind" value={f.indicacao} onChange={(e) => set("indicacao", e.target.value)} placeholder="Nome do estúdio que indicou" />
              </Field>
              <Field label="Quer contar mais alguma coisa? (opcional)" htmlFor="cad-msg" className="sm:col-span-2">
                <Textarea id="cad-msg" rows={3} value={f.mensagem} onChange={(e) => set("mensagem", e.target.value)} />
              </Field>
              {/* isca para robôs: invisível para pessoas */}
              <input
                type="text"
                name="site"
                tabIndex={-1}
                autoComplete="off"
                value={f.site}
                onChange={(e) => set("site", e.target.value)}
                className="absolute -left-[9999px] h-0 w-0 opacity-0"
                aria-hidden
              />
              <label className="flex items-start gap-2 text-sm sm:col-span-2">
                <Checkbox checked={f.aceite} onCheckedChange={(v) => set("aceite", !!v)} className="mt-0.5" />
                <span>Autorizo o contato da equipe MayaFit e o uso destes dados para criar o ambiente do meu estúdio, conforme a LGPD.</span>
              </label>
              <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
                <Button type="submit" disabled={enviando || !f.plano_id} className="h-11 w-full sm:w-auto sm:px-10">
                  {enviando && <Loader2 className="animate-spin" />}
                  Quero começar os 2 meses grátis
                </Button>
                <span className="text-xs text-muted-foreground">Sem cartão de crédito. Cancele quando quiser.</span>
              </div>
            </section>
          </form>
        )}
      </main>
    </div>
  );
}
