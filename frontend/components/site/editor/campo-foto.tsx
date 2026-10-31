"use client";

/* eslint-disable @next/next/no-img-element */
import { ImagePlus, Loader2, Trash2 } from "lucide-react";
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { urlFoto } from "@/components/site/util";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const LADO_MAX = 1600;

/** Reduz a foto no navegador (lado maior 1600 px, WebP ~82%) antes de enviar: o site fica leve no celular. */
async function comprimir(arquivo: File): Promise<File> {
  try {
    const bmp = await createImageBitmap(arquivo);
    const escala = Math.min(1, LADO_MAX / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * escala);
    canvas.height = Math.round(bmp.height * escala);
    canvas.getContext("2d")?.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/webp", 0.82));
    if (!blob || blob.type !== "image/webp" || blob.size >= arquivo.size) return arquivo;
    return new File([blob], arquivo.name.replace(/\.[^.]+$/, "") + ".webp", { type: "image/webp" });
  } catch {
    return arquivo;
  }
}

export async function enviarFotoSite(arquivo: File): Promise<string> {
  const fd = new FormData();
  fd.append("arquivo", await comprimir(arquivo));
  const r = await api.post<{ foto: string }>("/site/imagens", fd);
  return r.foto;
}

export function CampoFoto({
  valor,
  onChange,
  proporcao = "aspect-[4/3]",
  rotulo = "Enviar foto",
  desabilitado,
  className,
}: {
  valor: string | null;
  onChange: (foto: string | null) => void;
  proporcao?: string;
  rotulo?: string;
  desabilitado?: boolean;
  className?: string;
}) {
  const [enviando, setEnviando] = useState(false);
  const dz = useDropzone({
    multiple: false,
    disabled: desabilitado || enviando,
    accept: { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"], "image/webp": [".webp"] },
    maxSize: 15 * 1024 * 1024,
    onDrop: async (fs) => {
      const f = fs[0];
      if (!f) return;
      setEnviando(true);
      try {
        onChange(await enviarFotoSite(f));
        toast.success("Foto enviada");
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Não foi possível enviar a foto.");
      } finally {
        setEnviando(false);
      }
    },
    onDropRejected: () => toast.error("Use JPG, PNG ou WebP."),
  });
  const src = urlFoto(valor);
  return (
    <div className={cn("group relative overflow-hidden rounded-xl border bg-muted/40", proporcao, className)}>
      <div
        {...dz.getRootProps()}
        className={cn(
          "absolute inset-0 grid cursor-pointer place-items-center text-center text-xs text-muted-foreground transition",
          dz.isDragActive && "bg-brand/10 ring-2 ring-brand",
          desabilitado && "cursor-not-allowed",
        )}
      >
        <input {...dz.getInputProps()} aria-label={rotulo} />
        {src ? (
          <img src={src} alt="" className="absolute inset-0 size-full object-cover" />
        ) : (
          <span className="flex flex-col items-center gap-1 p-2">
            {enviando ? <Loader2 className="size-5 animate-spin" /> : <ImagePlus className="size-5" />}
            {enviando ? "Enviando…" : rotulo}
          </span>
        )}
        {src && enviando && (
          <span className="absolute inset-0 grid place-items-center bg-black/40 text-white">
            <Loader2 className="size-5 animate-spin" />
          </span>
        )}
      </div>
      {src && !desabilitado && (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="absolute top-1.5 right-1.5 grid size-7 place-items-center rounded-full bg-black/55 text-white opacity-0 transition group-hover:opacity-100 focus-visible:opacity-100"
          aria-label="Remover foto"
        >
          <Trash2 className="size-3.5" />
        </button>
      )}
    </div>
  );
}
