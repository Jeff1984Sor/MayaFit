"use client";

import { CalendarClock, CheckCircle2, Clock, DoorOpen, HeartHandshake, Loader2, PartyPopper, TriangleAlert, XCircle } from "lucide-react";
import { motion } from "motion/react";

import type { Checkin } from "@/lib/tipos-acesso";
import { cn } from "@/lib/utils";

export type EstadoCatraca = "nenhuma" | "acionando" | "liberada" | "falhou";

const hhmm = (t: string) => t.slice(0, 5);

/** Cartão grande do resultado do check-in (boas-vindas ou motivo da negativa). */
export function CartaoResultado({ r, catraca, segundos }: { r: Checkin; catraca: EstadoCatraca; segundos: number }) {
  const ok = r.permitido;
  return (
    <motion.div
      initial={{ opacity: 0, y: 40, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.98 }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      className={cn(
        "relative w-full max-w-xl overflow-hidden rounded-[2rem] p-7 shadow-2xl ring-1 sm:p-9",
        ok ? "bg-gradient-to-br from-emerald-500/25 to-emerald-900/30 ring-emerald-400/40" : "bg-gradient-to-br from-amber-500/20 to-rose-900/25 ring-amber-400/40",
        r.aniversario && "from-fuchsia-500/30 to-amber-600/30 ring-fuchsia-300/50",
      )}
    >
      <div className="flex items-start gap-4">
        <motion.div
          initial={{ scale: 0, rotate: -30 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 14, delay: 0.1 }}
          className={cn("grid size-16 shrink-0 place-items-center rounded-2xl", ok ? "bg-emerald-500 text-white" : "bg-amber-500 text-white")}
        >
          {r.aniversario ? <PartyPopper className="size-9" /> : ok ? <CheckCircle2 className="size-9" /> : <XCircle className="size-9" />}
        </motion.div>
        <div className="min-w-0">
          <h2 className="text-3xl leading-tight font-bold tracking-tight sm:text-4xl">{r.titulo}</h2>
          <p className="mt-1.5 text-lg text-white/80">{ok ? (r.aula ? "Sua presença na aula está confirmada." : r.motivo) : r.motivo}</p>
        </div>
      </div>

      {r.aniversario && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="mt-5 rounded-2xl bg-white/10 px-4 py-3 text-lg"
        >
          🎉 A equipe toda deseja um dia incrível para você!
        </motion.p>
      )}

      {ok && r.aula && (
        <div className="mt-6 grid grid-cols-2 gap-3 text-left">
          <Info icone={CalendarClock} rotulo="Aula" valor={r.aula.servico || "Aula"} />
          <Info icone={Clock} rotulo="Horário" valor={`${hhmm(r.aula.inicio)} às ${hhmm(r.aula.fim)}`} />
          {r.aula.profissional && <Info icone={HeartHandshake} rotulo="Com" valor={r.aula.profissional} className="col-span-2" />}
        </div>
      )}

      {r.avisos.length > 0 && (
        <div className="mt-5 space-y-2">
          {r.avisos.map((a) => (
            <p key={a} className="flex items-start gap-2 rounded-2xl bg-amber-400/15 px-4 py-3 text-base text-amber-100 ring-1 ring-amber-300/25">
              <TriangleAlert className="mt-0.5 size-5 shrink-0" />
              {a}
            </p>
          ))}
        </div>
      )}

      {ok && catraca !== "nenhuma" && (
        <p className="mt-5 flex items-center gap-2 text-base text-white/80">
          {catraca === "acionando" ? <Loader2 className="size-5 animate-spin" /> : <DoorOpen className="size-5" />}
          {catraca === "acionando" && "Liberando a catraca…"}
          {catraca === "liberada" && "Catraca liberada. Pode passar!"}
          {catraca === "falhou" && "A catraca não respondeu. A recepção vai liberar para você."}
        </p>
      )}

      <div className="absolute inset-x-0 bottom-0 h-1 bg-white/10">
        <motion.div
          className={cn("h-full", ok ? "bg-emerald-400" : "bg-amber-400")}
          initial={{ width: "100%" }}
          animate={{ width: "0%" }}
          transition={{ duration: segundos, ease: "linear" }}
        />
      </div>
    </motion.div>
  );
}

function Info({ icone: Icone, rotulo, valor, className }: { icone: React.ComponentType<{ className?: string }>; rotulo: string; valor: string; className?: string }) {
  return (
    <div className={cn("rounded-2xl bg-black/20 px-4 py-3", className)}>
      <p className="flex items-center gap-1.5 text-xs tracking-wide text-white/55 uppercase">
        <Icone className="size-3.5" />
        {rotulo}
      </p>
      <p className="mt-0.5 truncate text-xl font-semibold">{valor}</p>
    </div>
  );
}
