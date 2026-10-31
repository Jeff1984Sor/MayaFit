"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, CalendarClock, CreditCard, FileSignature, Flag, HandCoins, Hourglass, LogIn, Sparkles, Users } from "lucide-react";

import { Pill } from "@/components/mayacorp/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { diasAte } from "@/lib/admin";
import { api } from "@/lib/api";
import { data, dataHora, moeda, numero, relativo } from "@/lib/format";
import type { Cobranca, ContratoEstudio, Estudio, Tom, UsoEstudio, UsuarioEstudio } from "@/lib/tipos-admin";
import { cn } from "@/lib/utils";

type Nivel = "bom" | "atencao" | "ruim";
const TOM_NIVEL: Record<Nivel, Tom> = { bom: "success", atencao: "warning", ruim: "danger" };
const ROTULO_NIVEL: Record<Nivel, string> = { bom: "Saudável", atencao: "Atenção", ruim: "Em risco" };
const PESO: Record<Nivel, number> = { bom: 0, atencao: 1, ruim: 2 };

/** As mesmas chaves das abas da ficha: o React Query reaproveita as respostas. */
export function useDadosFicha(e: Estudio) {
  const usuarios = useQuery({ queryKey: ["admin", "usuarios", e.id], queryFn: () => api.get<UsuarioEstudio[]>(`/admin/clientes/${e.id}/usuarios`) });
  const uso = useQuery({ queryKey: ["admin", "uso", e.id], queryFn: () => api.get<UsoEstudio>(`/admin/clientes/${e.id}/uso`) });
  const cobrancas = useQuery({
    queryKey: ["admin", "cobrancas", "estudio", e.id],
    queryFn: () => api.get<Cobranca[]>("/admin/cobrancas", { cliente_id: e.id }),
  });
  const contratos = useQuery({
    queryKey: ["admin", "contratos", "estudio", e.id],
    queryFn: () => api.get<ContratoEstudio[]>(`/admin/clientes/${e.id}/contratos`),
  });
  return { usuarios, uso, cobrancas, contratos };
}

interface Sinal {
  titulo: string;
  nivel: Nivel;
  valor: string;
  detalhe: string;
  icone: React.ComponentType<{ className?: string }>;
}

function sinais(e: Estudio, usuarios: UsuarioEstudio[], uso: UsoEstudio | undefined, cobrancas: Cobranca[]): Sinal[] {
  // último acesso da equipe do estúdio (o Suporte da MayaCorp não conta)
  const ultimo = usuarios
    .filter((u) => !u.equipe_mayacorp && u.ultimo_acesso)
    .map((u) => u.ultimo_acesso!)
    .sort()
    .pop();
  const dias = ultimo ? -(diasAte(ultimo.slice(0, 10)) ?? 0) : null;
  const acesso: Sinal = {
    titulo: "Último acesso",
    icone: LogIn,
    nivel: dias == null ? "ruim" : dias <= 7 ? "bom" : dias <= 30 ? "atencao" : "ruim",
    valor: ultimo ? relativo(ultimo) : "nunca",
    detalhe: ultimo ? `em ${dataHora(ultimo)}` : "ninguém da equipe entrou ainda",
  };

  const alunos = uso?.alunos_ativos ?? e.uso?.alunos_ativos ?? null;
  const limite = uso ? uso.limite_alunos : (e.plano?.alunos_ativos ?? null);
  const ocupacao = alunos != null && limite ? alunos / limite : null;
  const usoSinal: Sinal = {
    titulo: "Uso do plano",
    icone: Users,
    nivel: alunos == null ? "atencao" : alunos === 0 ? "ruim" : ocupacao != null && ocupacao >= 1 ? "atencao" : "bom",
    valor: alunos == null ? "—" : `${numero(alunos)} aluno(s)`,
    detalhe:
      alunos === 0
        ? "nenhum aluno ativo: o estúdio ainda não começou a usar"
        : ocupacao != null && ocupacao >= 1
          ? "acima do limite: bom momento para oferecer upgrade"
          : limite
            ? `${Math.round((ocupacao ?? 0) * 100)}% do limite de ${numero(limite)}`
            : "plano sem limite de alunos",
  };

  const vencidas = cobrancas.filter((k) => k.status === "vencida");
  const valorVencido = vencidas.reduce((s, k) => s + Number(k.valor), 0);
  const pagamento: Sinal = {
    titulo: "Pagamentos",
    icone: CreditCard,
    nivel: vencidas.length ? (vencidas.length > 1 || e.status === "suspenso" ? "ruim" : "atencao") : "bom",
    valor: vencidas.length ? `${vencidas.length} vencida(s)` : "em dia",
    detalhe: vencidas.length ? `${moeda(valorVencido)} em atraso` : `${cobrancas.filter((k) => k.status === "paga").length} cobrança(s) paga(s)`,
  };
  return [acesso, usoSinal, pagamento];
}

/** Saúde do cliente: último acesso, uso e inadimplência, com um selo geral (o pior dos três). */
export function SaudeEstudio({ estudio }: { estudio: Estudio }) {
  const { usuarios, uso, cobrancas } = useDadosFicha(estudio);
  if (usuarios.isPending || cobrancas.isPending || uso.isPending) return <Skeleton className="h-40 rounded-2xl" />;
  const lista = sinais(estudio, usuarios.data ?? [], uso.data, cobrancas.data ?? []);
  const geral = lista.reduce<Nivel>((pior, s) => (PESO[s.nivel] > PESO[pior] ? s.nivel : pior), "bom");
  return (
    <div className="card-surface p-5">
      <div className="mb-4 flex items-center gap-2">
        <Activity className="size-4 text-brand" />
        <h3 className="font-medium">Saúde do cliente</h3>
        <Pill tom={TOM_NIVEL[geral]}>{ROTULO_NIVEL[geral]}</Pill>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {lista.map((s) => (
          <div key={s.titulo} className="rounded-xl border bg-background/50 p-3.5">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">{s.titulo}</p>
              <span
                className={cn(
                  "size-2 rounded-full",
                  s.nivel === "bom" && "bg-success",
                  s.nivel === "atencao" && "bg-warning",
                  s.nivel === "ruim" && "bg-danger",
                )}
              />
            </div>
            <p className="mt-1 flex items-center gap-1.5 font-semibold">
              <s.icone className="size-4 text-muted-foreground" /> {s.valor}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">{s.detalhe}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

interface Evento {
  quando: string;
  titulo: string;
  detalhe?: string;
  icone: React.ComponentType<{ className?: string }>;
  tom: Tom;
  futuro?: boolean;
}

/** Linha do tempo montada com o que o admin já conhece: criação, contrato, teste, contratos, cobranças e acessos. */
export function LinhaDoTempo({ estudio: e }: { estudio: Estudio }) {
  const { usuarios, cobrancas, contratos } = useDadosFicha(e);
  const hoje = new Date().toLocaleDateString("sv-SE");
  const ev: Evento[] = [{ quando: e.criado_em, titulo: "Estúdio criado", detalhe: e.slug, icone: Sparkles, tom: "brand" }];
  if (e.inicio_contrato) ev.push({ quando: e.inicio_contrato, titulo: "Início do contrato", detalhe: e.plano ? `${e.plano.nome} (${e.ciclo})` : undefined, icone: Flag, tom: "info" });
  if (e.teste_ate)
    ev.push({
      quando: e.teste_ate,
      titulo: e.teste_ate >= hoje ? "Fim do teste grátis" : "Teste grátis acabou",
      icone: Hourglass,
      tom: e.teste_ate >= hoje ? "warning" : "neutral",
      futuro: e.teste_ate > hoje,
    });
  for (const k of contratos.data ?? []) {
    ev.push({ quando: k.criado_em, titulo: "Contrato gerado", detalhe: k.titulo, icone: FileSignature, tom: "neutral" });
    if (k.enviado_em) ev.push({ quando: k.enviado_em, titulo: "Contrato enviado", detalhe: k.enviado_para.join(", "), icone: FileSignature, tom: "info" });
  }
  for (const k of cobrancas.data ?? []) {
    if (k.status === "paga" && k.pago_em)
      ev.push({ quando: k.pago_em, titulo: `Pagou ${moeda(k.valor)}`, detalhe: `${k.descricao}${k.forma_paga ? ` · ${k.forma_paga}` : ""}`, icone: HandCoins, tom: "success" });
    else if (k.status === "vencida") ev.push({ quando: k.vencimento, titulo: `Cobrança vencida: ${moeda(k.valor)}`, detalhe: k.descricao, icone: CalendarClock, tom: "danger" });
    else if (k.status === "pendente")
      ev.push({ quando: k.vencimento, titulo: `Cobrança a vencer: ${moeda(k.valor)}`, detalhe: k.descricao, icone: CalendarClock, tom: "info", futuro: k.vencimento > hoje });
  }
  for (const u of usuarios.data ?? []) {
    if (!u.equipe_mayacorp && u.ultimo_acesso) ev.push({ quando: u.ultimo_acesso, titulo: `Último acesso de ${u.nome.split(" ")[0]}`, icone: LogIn, tom: "neutral" });
  }
  ev.sort((a, b) => b.quando.localeCompare(a.quando));
  const mostrar = ev.slice(0, 20);

  return (
    <div className="card-surface p-5">
      <h3 className="mb-4 font-medium">Linha do tempo</h3>
      {usuarios.isPending || cobrancas.isPending || contratos.isPending ? (
        <Skeleton className="h-40" />
      ) : (
        <ol className="relative space-y-4 border-l pl-5">
          {mostrar.map((x, i) => (
            <li key={i} className={cn("relative", x.futuro && "opacity-70")}>
              <span
                className={cn(
                  "absolute top-0.5 -left-[29px] grid size-[18px] place-items-center rounded-full ring-4 ring-card",
                  x.tom === "success" && "bg-success text-white",
                  x.tom === "danger" && "bg-danger text-white",
                  x.tom === "warning" && "bg-warning text-white",
                  x.tom === "info" && "bg-info text-white",
                  x.tom === "brand" && "bg-brand text-white",
                  x.tom === "neutral" && "bg-muted text-muted-foreground",
                )}
              >
                <x.icone className="size-2.5" />
              </span>
              <p className="text-sm font-medium">
                {x.titulo} {x.futuro && <Pill>previsto</Pill>}
              </p>
              <p className="text-xs text-muted-foreground">
                <span className="num">{x.quando.length > 10 ? dataHora(x.quando) : data(x.quando)}</span>
                {x.detalhe && ` · ${x.detalhe}`}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
