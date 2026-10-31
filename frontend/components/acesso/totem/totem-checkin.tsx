"use client";

import confetti from "canvas-confetti";
import { Expand, KeyRound, Loader2, QrCode, ScanFace, Shrink, UserPlus, WifiOff, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { executarPlano } from "@/components/acesso/catraca-local";
import { abrirCamera, carregarMotor, erroDeCamera, fecharCamera, type MotorFacial } from "@/components/acesso/motor-facial";
import type { Checkin, TotemMe } from "@/lib/tipos-acesso";
import { cn } from "@/lib/utils";

import { ErroTotem, precisaParear, totemApi } from "./api-totem";
import { CartaoResultado, type EstadoCatraca } from "./cartao-resultado";
import { lerQr } from "./leitor-qr";
import { MolduraCamera, type EstadoMoldura } from "./moldura";
import { destravarAudio, somAniversario, somNegado, somSucesso } from "./sons";
import { TecladoNumerico, Visor } from "./teclado";

type Modo = "facial" | "documento" | "qr";
type Fase = "ocioso" | "rosto" | "lendo" | "enviando" | "resultado";

const QUADROS_PARA_COMECAR = 3;
const LEITURA_MAX_MS = 7000;
const TEMPO_RESULTADO_OK = 5;
const TEMPO_RESULTADO_NEGADO = 4.5;

function saudacao(d: Date) {
  const h = d.getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

export function TotemCheckin() {
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const motorRef = useRef<MotorFacial | null>(null);

  const [me, setMe] = useState<TotemMe | null>(null);
  const [erroGeral, setErroGeral] = useState<string | null>(null);
  const [erroCamera, setErroCamera] = useState<string | null>(null);
  const [motorPronto, setMotorPronto] = useState(false);
  const [motorFalhou, setMotorFalhou] = useState(false);
  const [modo, setModo] = useState<Modo>("facial");
  const [fase, setFase] = useState<Fase>("ocioso");
  const [dica, setDica] = useState<string | null>(null);
  const [progresso, setProgresso] = useState(0);
  const [resultado, setResultado] = useState<Checkin | null>(null);
  const [catraca, setCatraca] = useState<EstadoCatraca>("nenhuma");
  const [agora, setAgora] = useState(() => new Date());
  const [telaCheia, setTelaCheia] = useState(false);
  const [offline, setOffline] = useState(false);

  // documento + PIN
  const [doc, setDoc] = useState("");
  const [pin, setPin] = useState("");
  const [etapaDoc, setEtapaDoc] = useState<"documento" | "pin">("documento");

  // estado lido dentro dos laços assíncronos
  const faseRef = useRef<Fase>("ocioso");
  const modoRef = useRef<Modo>("facial");
  const bloqueadoAte = useRef(0);
  const exigeSaida = useRef(false);
  useEffect(() => {
    faseRef.current = fase;
    modoRef.current = modo;
  }, [fase, modo]);

  // ---------------------------------------------------------------------------------------------- inicialização
  useEffect(() => {
    let vivo = true;
    totemApi<TotemMe>("me")
      .then((m) => vivo && setMe(m))
      .catch((e) => {
        if (precisaParear(e)) router.replace("/totem/parear");
        else if (vivo) setErroGeral(e instanceof Error ? e.message : "Erro ao iniciar o totem.");
      });
    (async () => {
      try {
        if (videoRef.current) streamRef.current = await abrirCamera(videoRef.current);
      } catch (e) {
        if (vivo) setErroCamera(erroDeCamera(e));
        return;
      }
      try {
        const m = await carregarMotor();
        if (!vivo) return;
        motorRef.current = m;
        setMotorPronto(true);
      } catch {
        if (vivo) setMotorFalhou(true);
      }
    })();
    return () => {
      vivo = false;
      fecharCamera(streamRef.current);
    };
  }, [router]);

  useEffect(() => {
    const t = setInterval(() => setAgora(new Date()), 15_000);
    const on = () => setOffline(!navigator.onLine);
    on();
    window.addEventListener("online", on);
    window.addEventListener("offline", on);
    const fs = () => setTelaCheia(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", fs);
    return () => {
      clearInterval(t);
      window.removeEventListener("online", on);
      window.removeEventListener("offline", on);
      document.removeEventListener("fullscreenchange", fs);
    };
  }, []);

  // tela sempre acesa (quando o navegador permite)
  useEffect(() => {
    type Trava = { release: () => Promise<void> };
    let trava: Trava | null = null;
    const pedir = async () => {
      try {
        const wl = (navigator as unknown as { wakeLock?: { request: (t: "screen") => Promise<Trava> } }).wakeLock;
        if (wl && document.visibilityState === "visible") trava = await wl.request("screen");
      } catch {
        /* sem permissão: segue sem travar */
      }
    };
    void pedir();
    document.addEventListener("visibilitychange", pedir);
    return () => {
      document.removeEventListener("visibilitychange", pedir);
      void trava?.release().catch(() => undefined);
    };
  }, []);

  // ---------------------------------------------------------------------------------------------- resultado
  const voltarAoInicio = useCallback(() => {
    setResultado(null);
    setCatraca("nenhuma");
    setDica(null);
    setProgresso(0);
    setDoc("");
    setPin("");
    setEtapaDoc("documento");
    setModo("facial");
    setFase("ocioso");
  }, []);

  const mostrar = useCallback(
    async (r: Checkin) => {
      setResultado(r);
      setFase("resultado");
      if (r.permitido) {
        if (r.aniversario) {
          somAniversario();
          const cores = ["#7C8FFF", "#F5A623", "#1A8F5E", "#ff6fb5", "#ffffff"];
          void confetti({ particleCount: 160, spread: 100, origin: { y: 0.55 }, colors: cores });
          setTimeout(() => void confetti({ particleCount: 90, angle: 60, spread: 70, origin: { x: 0 }, colors: cores }), 350);
          setTimeout(() => void confetti({ particleCount: 90, angle: 120, spread: 70, origin: { x: 1 }, colors: cores }), 500);
        } else {
          somSucesso();
        }
      } else {
        somNegado();
      }
      const segundos = r.permitido ? TEMPO_RESULTADO_OK + (r.aniversario ? 2 : 0) + (r.avisos.length ? 1.5 : 0) : TEMPO_RESULTADO_NEGADO;
      // mesma pessoa não dispara de novo: precisa sair da frente da câmera (ou esperar)
      exigeSaida.current = true;
      bloqueadoAte.current = Date.now() + segundos * 1000 + (r.permitido ? 4000 : 1500);
      const ac = r.acionamento;
      if (r.permitido && ac) {
        if (ac.status === "liberada") setCatraca("liberada");
        else if (ac.status === "falhou") setCatraca("falhou");
        else if (ac.plano && ac.plano.passos.length) {
          setCatraca("acionando");
          const res = await executarPlano(ac.plano);
          setCatraca(res.ok ? "liberada" : "falhou");
          if (r.registro_id) {
            void totemApi(`registros/${r.registro_id}/catraca`, { ok: res.ok, detalhe: res.detalhe }).catch(() => undefined);
          }
        } else if (ac.status === "pendente") {
          setCatraca("liberada"); // agente local recebe o comando
        }
      }
      setTimeout(voltarAoInicio, segundos * 1000);
    },
    [voltarAoInicio],
  );

  const tratarErro = useCallback(
    (e: unknown) => {
      if (precisaParear(e)) {
        router.replace("/totem/parear");
        return;
      }
      const msg = e instanceof Error ? e.message : "Algo deu errado.";
      if (e instanceof ErroTotem && (e.status === 0 || e.status === 502)) setOffline(true);
      void mostrar({
        permitido: false, codigo: "erro", motivo: msg, titulo: "Não consegui concluir", primeiro_nome: null, aniversario: false,
        avisos: [], aula: null, registro_id: null, presenca_registrada: false, acionamento: null,
      });
    },
    [mostrar, router],
  );

  // ---------------------------------------------------------------------------------------------- laço facial
  useEffect(() => {
    if (!motorPronto || !me || modo !== "facial") return;
    let ativo = true;
    let seguidos = 0;
    let semRosto = 0;
    let inicioLeitura = 0;
    let melhor: { emb: number[]; q: number } | null = null;
    let piscou = false;
    let real = 0;
    let live = 0;

    const reiniciar = () => {
      seguidos = 0;
      inicioLeitura = 0;
      melhor = null;
      piscou = false;
      real = 0;
      live = 0;
    };

    const passo = async () => {
      const video = videoRef.current;
      const motor = motorRef.current;
      if (!ativo || !video || !motor) return;
      const f = faseRef.current;
      if (f === "enviando" || f === "resultado" || modoRef.current !== "facial") {
        if (ativo) setTimeout(passo, 200);
        return;
      }
      let l;
      try {
        l = await motor.ler(video);
      } catch {
        if (ativo) setTimeout(passo, 500);
        return;
      }
      if (!ativo) return;

      if (!l.rosto) {
        semRosto += 1;
        if (semRosto > 6) exigeSaida.current = false;
        if (inicioLeitura && semRosto > 8) {
          reiniciar();
          setFase("ocioso");
          setDica(null);
          setProgresso(0);
        } else if (!inicioLeitura && faseRef.current !== "ocioso") {
          seguidos = 0;
          setFase("ocioso");
          setDica(null);
        }
        setTimeout(passo, 120);
        return;
      }
      semRosto = 0;
      const bloqueado = exigeSaida.current && Date.now() < bloqueadoAte.current;
      if (bloqueado || !l.enquadrado) {
        if (!inicioLeitura) {
          seguidos = 0;
          setFase("rosto");
          setDica(bloqueado ? "Já registrei sua entrada. Até já!" : l.tamanho < 0.18 ? "Chegue um pouco mais perto" : "Centralize o rosto na moldura");
        }
        setTimeout(passo, 120);
        return;
      }

      if (!inicioLeitura) {
        seguidos += 1;
        setFase("rosto");
        setDica("Olhe para a câmera");
        if (seguidos < QUADROS_PARA_COMECAR) {
          setTimeout(passo, 80);
          return;
        }
        inicioLeitura = performance.now();
        setFase("lendo");
      }

      piscou ||= l.piscou;
      real = Math.max(real, l.rosto.real ?? 0);
      live = Math.max(live, l.rosto.live ?? 0);
      if (l.rosto.embedding?.length && (!melhor || l.qualidade > melhor.q)) melhor = { emb: Array.from(l.rosto.embedding), q: l.qualidade };
      const decorrido = performance.now() - inicioLeitura;
      const vivo = !me.exigir_prova_vida || piscou || (real >= 0.5 && live >= 0.5);
      setProgresso(Math.min(0.95, decorrido / (vivo ? 900 : 2500)));
      setDica(vivo ? "Reconhecendo…" : "Pisque devagar 😉");

      if (melhor && vivo && decorrido > 600) {
        const enviar = melhor;
        const prova = { piscou, real: real || null, live: live || null };
        reiniciar();
        setFase("enviando");
        setProgresso(1);
        try {
          const r = await totemApi<Checkin>("identificar/facial", { descritor: enviar.emb, prova_vida: prova });
          setOffline(false);
          if (ativo) await mostrar(r);
        } catch (e) {
          if (ativo) tratarErro(e);
        }
        if (ativo) setTimeout(passo, 200);
        return;
      }
      if (decorrido > LEITURA_MAX_MS) {
        reiniciar();
        setFase("rosto");
        setDica("Não consegui. Tente de novo ou use o CPF");
        exigeSaida.current = true;
        bloqueadoAte.current = Date.now() + 2500;
      }
      setTimeout(passo, 60);
    };
    void passo();
    return () => {
      ativo = false;
    };
  }, [motorPronto, me, modo, mostrar, tratarErro]);

  // ---------------------------------------------------------------------------------------------- laço do QR
  useEffect(() => {
    if (modo !== "qr" || fase !== "ocioso") return;
    let ativo = true;
    const desistir = setTimeout(() => ativo && voltarAoInicio(), 45_000);
    const passo = async () => {
      if (!ativo || !videoRef.current) return;
      const valor = await lerQr(videoRef.current).catch(() => null);
      if (!ativo) return;
      if (valor) {
        setFase("enviando");
        try {
          await mostrar(await totemApi<Checkin>("identificar/qr", { qr: valor }));
        } catch (e) {
          tratarErro(e);
        }
        return;
      }
      setTimeout(passo, 220);
    };
    void passo();
    return () => {
      ativo = false;
      clearTimeout(desistir);
    };
  }, [modo, fase, mostrar, tratarErro, voltarAoInicio]);

  // ---------------------------------------------------------------------------------------------- documento
  useEffect(() => {
    if (modo !== "documento" || fase !== "ocioso") return;
    const t = setTimeout(voltarAoInicio, 60_000); // ninguém mexendo: volta ao início
    return () => clearTimeout(t);
  }, [modo, fase, doc, pin, voltarAoInicio]);

  const enviarDocumento = async () => {
    if (etapaDoc === "documento" && me?.exigir_pin) {
      setEtapaDoc("pin");
      return;
    }
    setFase("enviando");
    try {
      await mostrar(await totemApi<Checkin>("identificar/documento", { documento: doc, pin: pin || null }));
    } catch (e) {
      tratarErro(e);
    }
  };

  const trocarModo = (m: Modo) => {
    destravarAudio();
    setResultado(null);
    setDoc("");
    setPin("");
    setEtapaDoc("documento");
    setDica(null);
    setFase("ocioso");
    setModo(m);
  };

  const alternarTelaCheia = () => {
    destravarAudio();
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen?.().catch(() => undefined);
  };

  // ---------------------------------------------------------------------------------------------- render
  const estadoMoldura: EstadoMoldura =
    fase === "resultado" ? (resultado?.permitido ? "sucesso" : "negado") : fase === "lendo" || fase === "enviando" ? "lendo" : fase === "rosto" ? "rosto" : "ocioso";

  if (erroGeral) {
    return (
      <Centro>
        <WifiOff className="size-14 text-amber-400" />
        <h1 className="mt-4 text-2xl font-semibold">O totem não conseguiu iniciar</h1>
        <p className="mt-2 max-w-md text-white/70">{erroGeral}</p>
        <button type="button" onClick={() => window.location.reload()} className="mt-6 rounded-2xl bg-white/10 px-6 py-3 text-lg ring-1 ring-white/20">
          Tentar de novo
        </button>
      </Centro>
    );
  }

  const hora = agora.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const dataLonga = agora.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
  const destaque = me?.cor && /^#[0-9a-f]{6}$/i.test(me.cor) ? me.cor : "#7C8FFF";

  return (
    <div className="relative flex min-h-dvh flex-col" onPointerDown={destravarAudio}>
      {/* fundo */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 left-1/2 size-[80vmax] -translate-x-1/2 rounded-full opacity-25 blur-3xl" style={{ background: `radial-gradient(circle, ${destaque}, transparent 60%)` }} />
        <div className="absolute -bottom-60 -left-40 size-[60vmax] rounded-full bg-emerald-500/10 blur-3xl" />
      </div>

      {/* topo */}
      <header className="relative z-10 flex items-start justify-between gap-4 px-6 pt-[max(1.25rem,env(safe-area-inset-top))]">
        <div>
          <p className="text-sm tracking-[0.2em] text-white/50 uppercase">{me?.unidade ?? "Check-in"}</p>
          <h1 className="text-2xl font-semibold sm:text-3xl">{me?.estudio ?? " "}</h1>
        </div>
        <div className="flex items-start gap-3">
          <div className="text-right">
            <p className="font-mono text-3xl font-semibold tabular-nums sm:text-4xl">{hora}</p>
            <p className="text-sm text-white/55 capitalize">{dataLonga}</p>
          </div>
          <button type="button" onClick={alternarTelaCheia} className="grid size-11 place-items-center rounded-xl bg-white/8 ring-1 ring-white/10" aria-label="Tela cheia">
            {telaCheia ? <Shrink className="size-5" /> : <Expand className="size-5" />}
          </button>
        </div>
      </header>

      {offline && (
        <div className="relative z-10 mx-6 mt-3 flex items-center gap-2 rounded-xl bg-amber-500/15 px-4 py-2 text-sm text-amber-100 ring-1 ring-amber-400/30">
          <WifiOff className="size-4" /> Sem internet no momento. Assim que voltar, o check-in funciona de novo.
        </div>
      )}

      {/* centro */}
      <main className="relative z-10 flex flex-1 flex-col items-center justify-center gap-6 px-6 py-6 landscape:lg:flex-row landscape:lg:gap-14">
        <div className={cn("flex flex-col items-center gap-5", modo === "documento" && fase !== "resultado" && "hidden")}>
          <MolduraCamera videoRef={videoRef} estado={estadoMoldura} progresso={progresso}>
            {(erroCamera || (!motorPronto && modo === "facial" && !motorFalhou)) && (
              <div className="absolute inset-0 grid place-items-center rounded-[50%] bg-black/70 p-8 text-center">
                {erroCamera ? (
                  <p className="text-base text-amber-100">{erroCamera}</p>
                ) : (
                  <div className="flex flex-col items-center gap-3">
                    <Loader2 className="size-9 animate-spin text-indigo-300" />
                    <p className="text-sm text-white/80">Preparando o reconhecimento facial…</p>
                  </div>
                )}
              </div>
            )}
            {modo === "qr" && fase !== "resultado" && (
              <div className="pointer-events-none absolute inset-[22%] rounded-3xl border-4 border-dashed border-white/70" />
            )}
          </MolduraCamera>

          {fase !== "resultado" && (
            <AnimatePresence mode="wait">
              <motion.p
                key={(modo === "qr" ? "qr" : dica) ?? "ocioso"}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="min-h-9 text-center text-2xl font-medium sm:text-3xl"
              >
                {modo === "qr"
                  ? "Mostre o QR do app para a câmera"
                  : fase === "enviando"
                    ? "Só um instante…"
                    : (dica ?? (motorFalhou ? "Use o CPF ou o QR do app" : `${saudacao(agora)}! Olhe para a câmera`))}
              </motion.p>
            </AnimatePresence>
          )}
        </div>

        <AnimatePresence mode="wait">
          {fase === "resultado" && resultado ? (
            <CartaoResultado
              key="res"
              r={resultado}
              catraca={catraca}
              segundos={resultado.permitido ? TEMPO_RESULTADO_OK + (resultado.aniversario ? 2 : 0) + (resultado.avisos.length ? 1.5 : 0) : TEMPO_RESULTADO_NEGADO}
            />
          ) : modo === "documento" ? (
            <motion.div key="doc" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex w-full flex-col items-center gap-4">
              <h2 className="text-center text-2xl font-semibold">{etapaDoc === "documento" ? "Digite seu CPF ou código de aluno" : "Agora, seu PIN"}</h2>
              <Visor
                valor={etapaDoc === "documento" ? doc : pin}
                segredo={etapaDoc === "pin"}
                placeholder={etapaDoc === "documento" ? "CPF ou código" : "4 a 6 dígitos"}
              />
              <TecladoNumerico
                valor={etapaDoc === "documento" ? doc : pin}
                onChange={etapaDoc === "documento" ? setDoc : setPin}
                max={etapaDoc === "documento" ? 11 : 6}
                onOk={enviarDocumento}
                rotuloOk={fase === "enviando" ? "…" : etapaDoc === "documento" && me?.exigir_pin ? "Continuar" : "Entrar"}
                okDesabilitado={fase === "enviando" || (etapaDoc === "documento" ? doc.length < 1 : pin.length < 4)}
              />
              <button type="button" onClick={() => trocarModo("facial")} className="mt-1 flex items-center gap-2 text-lg text-white/70">
                <X className="size-5" /> Cancelar
              </button>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>

      {/* alternativas */}
      {fase !== "resultado" && modo !== "documento" && (
        <footer className="relative z-10 grid grid-cols-3 gap-3 px-6 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
          <Alternativa icone={modo === "qr" ? ScanFace : KeyRound} onClick={() => trocarModo(modo === "qr" ? "facial" : "documento")}>
            {modo === "qr" ? "Usar o rosto" : "CPF ou código"}
          </Alternativa>
          <Alternativa icone={modo === "qr" ? KeyRound : QrCode} onClick={() => trocarModo(modo === "qr" ? "documento" : "qr")}>
            {modo === "qr" ? "CPF ou código" : "QR do app"}
          </Alternativa>
          <Link href="/totem/cadastro" className="flex flex-col items-center justify-center gap-1.5 rounded-2xl bg-white/6 px-3 py-4 text-center text-base ring-1 ring-white/10 active:scale-95">
            <UserPlus className="size-6 text-indigo-300" />
            Cadastrar meu rosto
          </Link>
        </footer>
      )}
    </div>
  );
}

function Alternativa({ icone: Icone, children, onClick }: { icone: React.ComponentType<{ className?: string }>; children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="flex flex-col items-center justify-center gap-1.5 rounded-2xl bg-white/6 px-3 py-4 text-base ring-1 ring-white/10 transition active:scale-95">
      <Icone className="size-6 text-indigo-300" />
      {children}
    </button>
  );
}

export function Centro({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">{children}</div>;
}
