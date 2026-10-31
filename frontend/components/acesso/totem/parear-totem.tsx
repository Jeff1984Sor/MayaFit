"use client";

import { CheckCircle2, Loader2, QrCode, ScanLine, TabletSmartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { abrirCamera, erroDeCamera, fecharCamera } from "@/components/acesso/motor-facial";
import type { TotemMe } from "@/lib/tipos-acesso";

import { totemApi } from "./api-totem";
import { lerQr } from "./leitor-qr";

/** Extrai o token de um texto colado/lido: aceita o token puro ou o link `.../totem/parear#t=<token>`. */
function extrairToken(texto: string): string {
  const t = texto.trim();
  const m = /[#&?]t=([A-Za-z0-9_-]+)/.exec(t);
  return m ? m[1] : t;
}

export function ParearTotem() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [pareado, setPareado] = useState<TotemMe | null>(null);
  const [lendoQr, setLendoQr] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const parear = useCallback(
    async (valor: string) => {
      const t = extrairToken(valor);
      if (!t) return;
      setEnviando(true);
      setErro(null);
      try {
        const me = await totemApi<TotemMe>("parear", { token: t });
        setPareado(me);
        // tira o token da barra de endereço (não fica no histórico)
        window.history.replaceState(null, "", "/totem/parear");
        setTimeout(() => router.replace("/totem"), 1800);
      } catch (e) {
        setErro(e instanceof Error ? e.message : "Não foi possível parear.");
      } finally {
        setEnviando(false);
      }
    },
    [router],
  );

  // link vindo do sistema: /totem/parear#t=<token> (o fragmento não vai para o servidor nem para os logs)
  useEffect(() => {
    const t = extrairToken(window.location.hash);
    if (!t || t === window.location.hash.trim()) return;
    const id = setTimeout(() => void parear(t), 0);
    return () => clearTimeout(id);
  }, [parear]);

  useEffect(() => {
    if (!lendoQr) return;
    let ativo = true;
    let stream: MediaStream | null = null;
    (async () => {
      try {
        if (videoRef.current) stream = await abrirCamera(videoRef.current);
      } catch (e) {
        setErro(erroDeCamera(e));
        setLendoQr(false);
        return;
      }
      const passo = async () => {
        if (!ativo || !videoRef.current) return;
        const v = await lerQr(videoRef.current).catch(() => null);
        if (!ativo) return;
        if (v) {
          setLendoQr(false);
          void parear(v);
          return;
        }
        setTimeout(passo, 250);
      };
      void passo();
    })();
    return () => {
      ativo = false;
      fecharCamera(stream);
    };
  }, [lendoQr, parear]);

  if (pareado) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
        <CheckCircle2 className="size-20 text-emerald-400" />
        <h1 className="mt-5 text-3xl font-semibold">Totem pareado!</h1>
        <p className="mt-2 text-lg text-white/70">
          {pareado.dispositivo} · {pareado.estudio}
        </p>
        <p className="mt-6 text-white/50">Abrindo o check-in…</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-6 px-6 py-10">
      <div className="grid size-16 place-items-center rounded-2xl bg-indigo-500/20 ring-1 ring-indigo-400/40">
        <TabletSmartphone className="size-8 text-indigo-300" />
      </div>
      <div className="max-w-lg text-center">
        <h1 className="text-3xl font-semibold">Parear este totem</h1>
        <p className="mt-2 text-white/65">
          No sistema, abra <b>Controle de acesso › Catracas e totens</b>, cadastre o totem e leia o QR que aparece (ou cole o token).
          O token fica guardado só neste aparelho, de forma protegida.
        </p>
      </div>

      {lendoQr ? (
        <div className="flex flex-col items-center gap-4">
          <div className="relative aspect-square w-[min(80vw,420px)] overflow-hidden rounded-3xl bg-black ring-1 ring-white/15">
            <video ref={videoRef} className="size-full -scale-x-100 object-cover" playsInline muted autoPlay />
            <ScanLine className="absolute inset-0 m-auto size-1/2 text-white/40" />
          </div>
          <button type="button" onClick={() => setLendoQr(false)} className="text-lg text-white/70">
            Cancelar
          </button>
        </div>
      ) : (
        <>
          <button
            type="button"
            onClick={() => setLendoQr(true)}
            className="flex items-center gap-3 rounded-2xl bg-indigo-500 px-7 py-4 text-lg font-semibold shadow-lg shadow-indigo-500/30 active:scale-95"
          >
            <QrCode className="size-6" /> Ler QR de pareamento
          </button>
          <form
            className="flex w-full max-w-lg flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void parear(token);
            }}
          >
            <label htmlFor="token" className="text-sm text-white/60">
              Ou cole o token do dispositivo
            </label>
            <input
              id="token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              placeholder="mfdisp_…"
              className="h-14 rounded-2xl bg-white/8 px-4 font-mono text-base ring-1 ring-white/15 outline-none focus:ring-indigo-400"
            />
            <button type="submit" disabled={enviando || !token.trim()} className="flex h-14 items-center justify-center gap-2 rounded-2xl bg-white/12 text-lg font-medium ring-1 ring-white/15 disabled:opacity-40">
              {enviando && <Loader2 className="size-5 animate-spin" />} Parear
            </button>
          </form>
        </>
      )}
      {erro && <p className="max-w-lg rounded-xl bg-amber-500/15 px-4 py-3 text-center text-amber-100 ring-1 ring-amber-400/30">{erro}</p>}
    </div>
  );
}
