"use client";

import { CalendarDays, ChartLine, ShieldCheck, Users } from "lucide-react";
import { motion } from "motion/react";

import { MarcaLogo, MayaCorpAssinatura } from "@/components/mayacorp/brand";
import { FaixaAmbiente } from "@/components/mayacorp/shell";

const DESTAQUES = [
  { i: CalendarDays, t: "Agenda sem conflito", d: "Aulas, reposições e capacidade sempre em dia." },
  { i: Users, t: "Alunos e contratos", d: "Da matrícula à renovação, num só lugar." },
  { i: ChartLine, t: "Financeiro claro", d: "Contas a receber e a pagar, fluxo de caixa e comissões." },
  { i: ShieldCheck, t: "Seguro por padrão", d: "Acesso por perfil e auditoria de ações sensíveis." },
];

const AULAS_EXEMPLO = [
  { h: "07:00", n: "Pilates aparelhos", o: 5, c: 6 },
  { h: "08:00", n: "Funcional", o: 8, c: 10 },
  { h: "18:30", n: "Pilates solo", o: 4, c: 4 },
];

/** Cartões flutuantes que lembram o produto (dados ilustrativos, escondidos do leitor de tela). */
function PreviaAgenda() {
  return (
    <div aria-hidden className="relative hidden justify-end [@media(min-height:820px)]:flex">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6, duration: 0.6 }}
        className="flutuar w-80 rounded-2xl border border-white/10 bg-white/6 p-4 shadow-2xl shadow-black/30 backdrop-blur-xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <p className="flex items-center gap-2 text-sm font-medium">
            <CalendarDays className="size-4 text-brand" /> Aulas de hoje
          </p>
          <span className="rounded-full bg-success/20 px-2 py-0.5 text-[10px] font-semibold text-[#7fe0b4]">ao vivo</span>
        </div>
        <ul className="space-y-2.5">
          {AULAS_EXEMPLO.map((a, k) => {
            const cheia = a.o >= a.c;
            return (
              <li key={a.h} className="flex items-center gap-3">
                <span className="w-11 font-mono text-xs text-white/60">{a.h}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="truncate">{a.n}</span>
                    <span className={cheia ? "font-semibold text-amber-maya" : "text-white/60"}>{cheia ? "lotada" : `${a.o}/${a.c}`}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <motion.div
                      className={cheia ? "h-full rounded-full bg-amber-maya" : "h-full rounded-full bg-brand"}
                      initial={{ width: 0 }}
                      animate={{ width: `${(a.o / a.c) * 100}%` }}
                      transition={{ delay: 0.9 + k * 0.15, duration: 0.7, ease: "easeOut" }}
                    />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </motion.div>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.1, duration: 0.5 }}
        className="flutuar absolute -top-6 right-64 flex items-center gap-2 rounded-xl border border-white/10 bg-dark-maya/80 px-3 py-2 shadow-xl backdrop-blur [animation-delay:-3s]"
      >
        <div className="grid size-7 place-items-center rounded-lg bg-success/20">
          <ChartLine className="size-3.5 text-[#7fe0b4]" />
        </div>
        <div className="leading-tight">
          <p className="text-[10px] text-white/55">Recebido no mês</p>
          <p className="font-mono text-xs font-semibold">+12,4%</p>
        </div>
      </motion.div>
    </div>
  );
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh pt-(--faixa) lg:grid-cols-[1.05fr_1fr]">
      <FaixaAmbiente />
      {/* painel da marca */}
      <aside className="relative hidden overflow-hidden bg-dark-maya text-white lg:flex lg:flex-col">
        <div className="grid-bg absolute inset-0 opacity-60" />
        <div className="absolute -top-32 -left-32 size-[28rem] rounded-full bg-brand/35 blur-[110px]" />
        <div className="absolute -right-24 bottom-0 size-[24rem] rounded-full bg-navy/80 blur-[100px]" />
        <div className="relative flex flex-1 flex-col justify-between p-12">
          <MarcaLogo claro />

          <div className="max-w-lg">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
              className="mb-8 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs backdrop-blur"
            >
              <span className="size-1.5 animate-pulse rounded-full bg-success" />
              <span className="font-semibold">MayaFit</span>
              <span className="text-white/60">· gestão para estúdios e academias</span>
            </motion.div>
            <motion.h1
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.08 }}
              className="text-4xl leading-[1.1] font-semibold tracking-tight xl:text-5xl"
            >
              Seu estúdio organizado,{" "}
              <span className="bg-linear-to-r from-brand to-white bg-clip-text text-transparent">você no controle.</span>
            </motion.h1>
            <div className="mt-10 space-y-4">
              {DESTAQUES.map((d, k) => (
                <motion.div
                  key={d.t}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.25 + k * 0.1 }}
                  className="flex gap-3"
                >
                  <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/8 ring-1 ring-white/10">
                    <d.i className="size-4 text-brand" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{d.t}</p>
                    <p className="text-sm text-white/55">{d.d}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>

          {/* ilustração: prévia da agenda (decorativa); some em telas baixas para não espremer o texto */}
          <PreviaAgenda />
        </div>
      </aside>

      {/* formulário */}
      <main className="relative flex flex-col">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-linear-to-b from-brand/8 to-transparent lg:hidden" />
        <div className="relative flex flex-1 items-center justify-center px-5 py-12">
          <div className="w-full max-w-sm">{children}</div>
        </div>
        <footer className="relative flex justify-center pb-6 text-muted-foreground">
          <MayaCorpAssinatura />
        </footer>
      </main>
    </div>
  );
}
