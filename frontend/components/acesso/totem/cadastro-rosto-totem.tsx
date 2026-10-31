"use client";

import { ArrowLeft, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { abrirCamera, capturar, carregarMotor, erroDeCamera, fecharCamera } from "@/components/acesso/motor-facial";
import type { TotemMe } from "@/lib/tipos-acesso";

import { precisaParear, totemApi } from "./api-totem";
import { MolduraCamera, type EstadoMoldura } from "./moldura";
import { somNegado, somSucesso } from "./sons";
import { TecladoNumerico, Visor } from "./teclado";

type Etapa = "documento" | "codigo" | "termo" | "camera" | "pronto";

/**
 * Cadastro do rosto no próprio totem. A "confirmação da recepção" é o código de 6 dígitos (uso único, 15 min) que a
 * recepção gera na ficha de biometria do aluno. O aluno lê e aceita o termo LGPD aqui mesmo; o consentimento fica
 * registrado em nome de quem gerou o código.
 */
export function CadastroRostoTotem() {
  const router = useRouter();
  const [me, setMe] = useState<TotemMe | null>(null);
  const [etapa, setEtapa] = useState<Etapa>("documento");
  const [doc, setDoc] = useState("");
  const [codigo, setCodigo] = useState("");
  const [termo, setTermo] = useState("");
  const [nome, setNome] = useState("");
  const [leuTudo, setLeuTudo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [moldura, setMoldura] = useState<EstadoMoldura>("ocioso");
  const [dica, setDica] = useState("Preparando a câmera…");
  const [mensagemFinal, setMensagemFinal] = useState("");
  const [tentativa, setTentativa] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    totemApi<TotemMe>("me")
      .then(setMe)
      .catch((e) => {
        if (precisaParear(e)) router.replace("/totem/parear");
      });
    void carregarMotor().catch(() => undefined); // já vai baixando os modelos
  }, [router]);

  // inatividade: volta ao check-in
  useEffect(() => {
    if (etapa === "camera") return;
    const t = setTimeout(() => router.replace("/totem"), etapa === "pronto" ? 6000 : 90_000);
    return () => clearTimeout(t);
  }, [etapa, doc, codigo, leuTudo, router]);

  const iniciar = async () => {
    setOcupado(true);
    setErro(null);
    try {
      const r = await totemApi<{ primeiro_nome: string; termo: string }>("cadastro/iniciar", { documento: doc, codigo });
      setNome(r.primeiro_nome);
      setTermo(r.termo);
      setEtapa("termo");
    } catch (e) {
      if (precisaParear(e)) return router.replace("/totem/parear");
      setErro(e instanceof Error ? e.message : "Não foi possível continuar.");
      setCodigo("");
    } finally {
      setOcupado(false);
    }
  };

  useEffect(() => {
    if (etapa !== "camera") return;
    let ativo = true;
    let stream: MediaStream | null = null;
    (async () => {
      try {
        if (!videoRef.current) return;
        stream = await abrirCamera(videoRef.current);
        setDica("Carregando o reconhecimento…");
        const motor = await carregarMotor();
        if (!ativo) return;
        setDica("Olhe para a câmera e pisque devagar");
        const cap = await capturar(motor, videoRef.current, {
          quantidade: 3,
          exigirProvaVida: me?.exigir_prova_vida ?? true,
          cancelado: () => !ativo,
          aoLer: (l) => {
            if (!ativo) return;
            setMoldura(l.rosto ? (l.enquadrado ? "lendo" : "rosto") : "ocioso");
            if (l.rosto && !l.enquadrado) setDica(l.tamanho < 0.18 ? "Chegue um pouco mais perto" : "Centralize o rosto na moldura");
            else if (l.rosto) setDica("Ótimo! Continue olhando e pisque devagar");
          },
        });
        if (!ativo) return;
        setDica("Salvando…");
        const r = await totemApi<{ mensagem: string }>("cadastro/concluir", {
          documento: doc, codigo, aceite: true, descritores: cap.descritores, prova_vida: cap.prova_vida,
        });
        setMoldura("sucesso");
        somSucesso();
        setMensagemFinal(r.mensagem);
        setTimeout(() => ativo && setEtapa("pronto"), 900);
      } catch (e) {
        if (!ativo || (e instanceof Error && e.message === "cancelado")) return;
        if (precisaParear(e)) return router.replace("/totem/parear");
        somNegado();
        setMoldura("negado");
        setErro(e instanceof DOMException ? erroDeCamera(e) : e instanceof Error ? e.message : "Não foi possível cadastrar.");
      }
    })();
    return () => {
      ativo = false;
      fecharCamera(stream);
    };
  }, [etapa, doc, codigo, me, router, tentativa]);

  return (
    <div className="flex min-h-dvh flex-col px-6 py-[max(1.5rem,env(safe-area-inset-top))]">
      <header className="flex items-center justify-between">
        <Link href="/totem" className="flex items-center gap-2 text-lg text-white/70">
          <ArrowLeft className="size-5" /> Voltar
        </Link>
        <p className="text-sm tracking-[0.2em] text-white/45 uppercase">Cadastro do rosto</p>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-5 py-6">
        {etapa === "documento" && (
          <>
            <h1 className="text-center text-2xl font-semibold sm:text-3xl">Digite seu CPF ou código de aluno</h1>
            <Visor valor={doc} placeholder="CPF ou código" />
            <TecladoNumerico valor={doc} onChange={setDoc} max={11} onOk={() => setEtapa("codigo")} okDesabilitado={!doc} />
          </>
        )}

        {etapa === "codigo" && (
          <>
            <h1 className="text-center text-2xl font-semibold sm:text-3xl">Código da recepção</h1>
            <p className="max-w-md text-center text-white/65">Peça à recepção o código de 6 dígitos para cadastrar seu rosto. Ele vale por 15 minutos.</p>
            <Visor valor={codigo} placeholder="6 dígitos" />
            <TecladoNumerico valor={codigo} onChange={setCodigo} max={6} onOk={iniciar} okDesabilitado={codigo.length !== 6 || ocupado} rotuloOk={ocupado ? "…" : "Continuar"} />
            <button type="button" onClick={() => setEtapa("documento")} className="text-white/60">
              Corrigir CPF/código
            </button>
          </>
        )}

        {etapa === "termo" && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="flex w-full max-w-2xl flex-col gap-4">
            <div className="flex items-center gap-3">
              <ShieldCheck className="size-8 text-emerald-400" />
              <h1 className="text-2xl font-semibold sm:text-3xl">{nome}, antes de começar</h1>
            </div>
            <p className="text-white/70">Leia o termo até o fim. Não guardamos foto: só uma representação numérica do rosto, protegida.</p>
            <div
              className="max-h-[45vh] overflow-y-auto rounded-2xl bg-white/6 p-5 text-base leading-relaxed whitespace-pre-line text-white/85 ring-1 ring-white/10"
              onScroll={(e) => {
                const el = e.currentTarget;
                if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) setLeuTudo(true);
              }}
              ref={(el) => {
                if (el && el.scrollHeight <= el.clientHeight + 24 && !leuTudo) setLeuTudo(true);
              }}
            >
              {termo}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Link href="/totem" className="flex h-16 items-center justify-center rounded-2xl bg-white/8 text-lg ring-1 ring-white/15">
                Não aceito
              </Link>
              <button
                type="button"
                disabled={!leuTudo}
                onClick={() => {
                  setErro(null);
                  setMoldura("ocioso");
                  setEtapa("camera");
                }}
                className="h-16 rounded-2xl bg-emerald-500 text-lg font-semibold shadow-lg shadow-emerald-500/30 disabled:opacity-40"
              >
                {leuTudo ? "Li e concordo" : "Role até o fim"}
              </button>
            </div>
          </motion.div>
        )}

        {etapa === "camera" && (
          <>
            <MolduraCamera videoRef={videoRef} estado={moldura} progresso={moldura === "lendo" ? 0.6 : 0.2} />
            <p className="min-h-9 text-center text-2xl font-medium">{erro ? "" : dica}</p>
            {erro && (
              <div className="flex flex-col items-center gap-3">
                <p className="max-w-md rounded-xl bg-amber-500/15 px-4 py-3 text-center text-amber-100 ring-1 ring-amber-400/30">{erro}</p>
                <button
                  type="button"
                  onClick={() => {
                    setErro(null);
                    setMoldura("ocioso");
                    setDica("Olhe para a câmera e pisque devagar");
                    setTentativa((n) => n + 1);
                  }}
                  className="rounded-2xl bg-white/10 px-6 py-3 text-lg ring-1 ring-white/20"
                >
                  Tentar de novo
                </button>
              </div>
            )}
            {!erro && moldura !== "sucesso" && <Loader2 className="size-6 animate-spin text-white/40" />}
          </>
        )}

        {etapa === "pronto" && (
          <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex flex-col items-center text-center">
            <CheckCircle2 className="size-20 text-emerald-400" />
            <h1 className="mt-4 text-3xl font-semibold">{mensagemFinal || "Rosto cadastrado!"}</h1>
            <p className="mt-2 text-lg text-white/70">Na próxima vez é só olhar para a câmera.</p>
            <Link href="/totem" className="mt-8 rounded-2xl bg-white/10 px-8 py-4 text-lg ring-1 ring-white/20">
              Fazer check-in agora
            </Link>
          </motion.div>
        )}

        {erro && etapa !== "camera" && (
          <p className="max-w-md rounded-xl bg-amber-500/15 px-4 py-3 text-center text-amber-100 ring-1 ring-amber-400/30">{erro}</p>
        )}
      </main>
    </div>
  );
}
