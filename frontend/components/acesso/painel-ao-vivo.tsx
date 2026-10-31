"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Cake, CalendarClock, DoorOpen, LogOut, MonitorSmartphone, Router, ShieldX, Users, UserCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { CatracaPill, hora, Indicador, MetodoTag, ResultadoPill } from "@/components/acesso/comum";
import { DialogoLiberar } from "@/components/acesso/dialogo-liberar";
import { AnimatedNumber } from "@/components/mayacorp/animated-number";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Pill } from "@/components/mayacorp/status-badge";
import { UserAvatar } from "@/components/mayacorp/user-avatar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Painel, Presente } from "@/lib/tipos-acesso";
import { ROTULO_METODO } from "@/lib/tipos-acesso";
import { cn } from "@/lib/utils";

const ATUALIZAR_MS = 5000;

function useAgora(intervalo = 15000) {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setAgora(Date.now()), intervalo);
    return () => clearInterval(t);
  }, [intervalo]);
  return agora;
}

/** "Quem está no estúdio agora", em tempo real (atualiza a cada 5 s, com animação de chegada e saída). */
export function PainelAoVivo() {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const [liberar, setLiberar] = useState(false);
  const agora = useAgora();
  const painel = useQuery({
    queryKey: ["acesso", "painel"],
    queryFn: () => api.get<Painel>("/acesso/painel"),
    refetchInterval: ATUALIZAR_MS,
    refetchIntervalInBackground: false,
    staleTime: 0,
  });
  const saida = useMutation({
    mutationFn: (registroId: number) => api.post(`/acesso/presentes/${registroId}/saida`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["acesso", "painel"] }),
  });

  const p = painel.data;
  const podeLiberar = pode("acesso.liberar_manual");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="relative flex size-2.5">
            <span className={cn("absolute inline-flex size-full rounded-full bg-success opacity-75", !painel.isError && "animate-ping")} />
            <span className={cn("relative inline-flex size-2.5 rounded-full", painel.isError ? "bg-danger" : "bg-success")} />
          </span>
          {painel.isError ? "Sem conexão: tentando de novo…" : "Ao vivo · atualiza a cada 5 segundos"}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" render={<Link href="/totem" target="_blank" />}>
            <MonitorSmartphone /> Abrir o totem
          </Button>
          {podeLiberar && (
            <Button onClick={() => setLiberar(true)}>
              <DoorOpen /> Liberar agora
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador titulo="No estúdio agora" valor={<AnimatedNumber value={p?.presentes.length ?? 0} />} icone={Users} carregando={!p} legenda="pela entrada e pela aula de cada um" />
        <Indicador titulo="Entradas hoje" valor={<AnimatedNumber value={p?.entradas_hoje ?? 0} />} icone={UserCheck} tom="success" carregando={!p} />
        <Indicador titulo="Alunos diferentes hoje" valor={<AnimatedNumber value={p?.alunos_hoje ?? 0} />} icone={CalendarClock} carregando={!p} />
        <Indicador titulo="Negados hoje" valor={<AnimatedNumber value={p?.negados_hoje ?? 0} />} icone={ShieldX} tom="danger" carregando={!p} legenda="veja os motivos em Últimos acessos" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <section className="card-surface p-4 sm:p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Quem está no estúdio agora</h2>
            {p && !!Object.keys(p.por_metodo).length && (
              <div className="hidden flex-wrap gap-1.5 sm:flex">
                {Object.entries(p.por_metodo).map(([m, n]) => (
                  <Pill key={m} tom="neutral">
                    {ROTULO_METODO[m as keyof typeof ROTULO_METODO] ?? m}: {n}
                  </Pill>
                ))}
              </div>
            )}
          </div>
          {!p ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-24 rounded-xl" />
              ))}
            </div>
          ) : p.presentes.length === 0 ? (
            <EmptyState icone={DoorOpen} titulo="Ninguém no estúdio agora" descricao="Quando alguém fizer check-in no totem ou for liberado pela recepção, aparece aqui na hora." />
          ) : (
            <motion.div layout className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <AnimatePresence initial={false}>
                {p.presentes.map((x) => (
                  <CartaoPresente key={x.registro_id} p={x} agora={agora} podeSair={podeLiberar} onSair={() => saida.mutate(x.registro_id)} />
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </section>

        <div className="space-y-6">
          <section className="card-surface p-4 sm:p-5">
            <h2 className="mb-3 text-base font-semibold">Próximas aulas de hoje</h2>
            {!p ? (
              <Skeleton className="h-20" />
            ) : p.proximas_aulas.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhuma aula com reserva no resto do dia.</p>
            ) : (
              <ul className="space-y-3">
                {p.proximas_aulas.map((a) => (
                  <li key={a.sessao_id}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span className="font-medium">
                        <span className="num">{a.inicio}</span> · {a.servico}
                      </span>
                      <span className="text-xs text-muted-foreground num">
                        {a.chegaram}/{a.reservas} chegaram
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                      <motion.div className="h-full rounded-full bg-success" initial={{ width: 0 }} animate={{ width: `${a.reservas ? (100 * a.chegaram) / a.reservas : 0}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card-surface p-4 sm:p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold">Últimos acessos</h2>
              <Link href="/acesso/historico" className="text-xs text-muted-foreground hover:text-foreground">
                ver histórico
              </Link>
            </div>
            <ul className="divide-y">
              <AnimatePresence initial={false}>
                {p?.ultimos.map((r) => (
                  <motion.li key={r.id} initial={{ opacity: 0, backgroundColor: "rgba(124,143,255,0.18)" }} animate={{ opacity: 1, backgroundColor: "rgba(0,0,0,0)" }} transition={{ duration: 1.2 }} className="py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{r.aluno_nome ?? "Não identificado"}</span>
                      <span className="text-xs text-muted-foreground num">{hora(r.em)}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <ResultadoPill r={r} />
                      <MetodoTag metodo={r.metodo} />
                    </div>
                    {!r.permitido && <p className="mt-1 text-xs text-danger-ink">{r.motivo}</p>}
                  </motion.li>
                ))}
              </AnimatePresence>
              {p && p.ultimos.length === 0 && <li className="py-2 text-sm text-muted-foreground">Nenhum acesso ainda.</li>}
            </ul>
          </section>

          <section className="card-surface p-4 sm:p-5">
            <h2 className="mb-3 text-base font-semibold">Equipamentos</h2>
            {p && p.equipamentos.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nenhum totem ou catraca. <Link className="underline" href="/acesso/equipamentos">Cadastrar</Link>
              </p>
            ) : (
              <ul className="space-y-2">
                {p?.equipamentos.map((e) => (
                  <li key={`${e.tipo}-${e.id}`} className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex min-w-0 items-center gap-2">
                      {e.tipo === "catraca" ? <Router className="size-4 text-muted-foreground" /> : <MonitorSmartphone className="size-4 text-muted-foreground" />}
                      <span className="truncate">{e.nome}</span>
                    </span>
                    {e.tipo === "catraca" ? (
                      <CatracaPill status={e.online == null ? null : e.online ? "liberada" : "falhou"} detalhe={e.detalhe} />
                    ) : (
                      <Pill tom={e.online ? "success" : "neutral"}>{e.online ? "online" : "offline"}</Pill>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
      <DialogoLiberar open={liberar} onOpenChange={setLiberar} />
    </div>
  );
}

function CartaoPresente({ p, agora, podeSair, onSair }: { p: Presente; agora: number; podeSair: boolean; onSair: () => void }) {
  const entrou = new Date(p.entrou_em).getTime();
  const sai = p.previsto_sair ? new Date(p.previsto_sair).getTime() : entrou + 90 * 60000;
  const progresso = Math.min(100, Math.max(0, (100 * (agora - entrou)) / Math.max(1, sai - entrou)));
  const recente = agora - entrou < 2 * 60000;
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      className={cn("group relative overflow-hidden rounded-xl border bg-background/60 p-3", recente && "ring-2 ring-success/50", p.aniversario && "ring-2 ring-warning/60")}
    >
      {recente && <span className="absolute top-2 right-2 rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-semibold text-success-ink">chegou agora</span>}
      <div className="flex items-center gap-3">
        <UserAvatar nome={p.nome} fotoUrl={p.foto_url} className="size-11" />
        <div className="min-w-0">
          <p className="flex items-center gap-1 truncate font-medium">
            {p.primeiro_nome}
            {p.aniversario && <Cake className="size-4 text-warning" aria-label="Aniversariante" />}
          </p>
          <p className="truncate text-xs text-muted-foreground">{p.aula ?? "Acesso livre"}</p>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
        <span className="num">entrou {hora(p.entrou_em)}</span>
        <MetodoTag metodo={p.metodo} className="text-[11px]" />
      </div>
      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted" title={p.previsto_sair ? `Saída prevista ${hora(p.previsto_sair)}` : undefined}>
        <div className="h-full rounded-full bg-brand transition-all duration-1000" style={{ width: `${progresso}%` }} />
      </div>
      {podeSair && (
        <button type="button" onClick={onSair} className="absolute right-2 bottom-2 hidden items-center gap-1 rounded-md bg-card px-2 py-1 text-[11px] shadow ring-1 ring-border group-hover:flex">
          <LogOut className="size-3" /> saiu
        </button>
      )}
    </motion.div>
  );
}
