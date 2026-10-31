"use client";

import { CheckCircle2, Loader2, ScanFace } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { abrirCamera, capturar, carregarMotor, erroDeCamera, fecharCamera, type Captura, type Leitura } from "@/components/acesso/motor-facial";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type Etapa = "carregando" | "pronto" | "capturando" | "enviando" | "ok" | "erro";

/**
 * Cadastro do rosto pela recepção: abre a câmera DESTE computador, pede para piscar e gera 3 descritores no navegador.
 * A imagem não sai do navegador; `onCapturado` recebe só os números.
 */
export function CapturaRosto({
  open,
  onOpenChange,
  nome,
  exigirProvaVida,
  onCapturado,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  nome: string;
  exigirProvaVida: boolean;
  onCapturado: (c: Captura) => Promise<void>;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const cancelado = useRef(false);
  const [etapa, setEtapa] = useState<Etapa>("carregando");
  const [erro, setErro] = useState("");
  const [leitura, setLeitura] = useState<Leitura | null>(null);

  useEffect(() => {
    if (!open) return;
    cancelado.current = false;
    let vivo = true;
    (async () => {
      setEtapa("carregando");
      setErro("");
      try {
        // espera o <video> montar dentro do diálogo
        for (let i = 0; i < 20 && !video.current; i++) await new Promise((r) => setTimeout(r, 50));
        if (!video.current) throw new Error("Não foi possível preparar a câmera.");
        stream.current = await abrirCamera(video.current);
        await carregarMotor();
        if (vivo) setEtapa("pronto");
      } catch (e) {
        if (vivo) {
          setErro(e instanceof DOMException ? erroDeCamera(e) : e instanceof Error ? e.message : "Falha ao preparar o reconhecimento.");
          setEtapa("erro");
        }
      }
    })();
    return () => {
      vivo = false;
      cancelado.current = true;
      fecharCamera(stream.current);
      stream.current = null;
    };
  }, [open]);

  const iniciar = async () => {
    if (!video.current) return;
    setEtapa("capturando");
    setErro("");
    try {
      const motor = await carregarMotor();
      const c = await capturar(motor, video.current, { quantidade: 3, exigirProvaVida, aoLer: setLeitura, cancelado: () => cancelado.current });
      setEtapa("enviando");
      await onCapturado(c);
      setEtapa("ok");
      setTimeout(() => onOpenChange(false), 1400);
    } catch (e) {
      if (cancelado.current) return;
      setErro(e instanceof Error ? e.message : "Não foi possível cadastrar.");
      setEtapa("erro");
    }
  };

  const enquadrado = !!leitura?.enquadrado;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Cadastrar o rosto de {nome.split(" ")[0]}</DialogTitle>
          <DialogDescription>Peça para olhar para a câmera, sem boné ou óculos escuros, e piscar devagar. Nenhuma foto é guardada.</DialogDescription>
        </DialogHeader>
        <div className="relative mx-auto aspect-square w-full max-w-80 overflow-hidden rounded-full bg-black">
          <video ref={video} className="size-full scale-x-[-1] object-cover" playsInline muted />
          <div
            className={cn(
              "pointer-events-none absolute inset-0 rounded-full ring-8 transition-colors",
              etapa === "ok" ? "ring-success" : etapa === "capturando" ? (enquadrado ? "ring-brand animate-pulse" : "ring-warning/70") : "ring-white/20",
            )}
          />
          {etapa === "capturando" && <div className="pointer-events-none absolute inset-x-0 h-1 animate-[varrer_1.6s_ease-in-out_infinite] bg-linear-to-r from-transparent via-brand to-transparent" />}
          {(etapa === "carregando" || etapa === "enviando") && (
            <div className="absolute inset-0 grid place-items-center bg-black/50 text-sm text-white">
              <span className="flex items-center gap-2">
                <Loader2 className="size-4 animate-spin" /> {etapa === "carregando" ? "Preparando o reconhecimento…" : "Guardando com segurança…"}
              </span>
            </div>
          )}
          {etapa === "ok" && (
            <div className="absolute inset-0 grid place-items-center bg-success/30 text-white">
              <CheckCircle2 className="size-16" />
            </div>
          )}
        </div>
        <style>{`@keyframes varrer { 0% { top: 10% } 50% { top: 88% } 100% { top: 10% } }`}</style>
        <p className="min-h-5 text-center text-sm text-muted-foreground">
          {etapa === "capturando" && (enquadrado ? (exigirProvaVida ? "Ótimo! Agora pisque devagar." : "Ótimo, fique paradinho…") : "Centralize o rosto no círculo.")}
          {etapa === "erro" && <span className="text-danger-ink">{erro}</span>}
          {etapa === "ok" && <span className="text-success-ink">Rosto cadastrado!</span>}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={iniciar} disabled={etapa !== "pronto" && etapa !== "erro"}>
            <ScanFace /> {etapa === "erro" ? "Tentar de novo" : "Capturar"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
