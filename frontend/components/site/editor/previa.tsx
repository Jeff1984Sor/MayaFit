"use client";

import { Monitor, Smartphone, Tablet } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { PaginaSite } from "@/components/site/pagina-site";
import type { PaginaPublica } from "@/lib/tipos-site";
import { cn } from "@/lib/utils";

const DISPOSITIVOS = [
  { id: "desktop", nome: "Computador", largura: 1280, I: Monitor },
  { id: "tablet", nome: "Tablet", largura: 820, I: Tablet },
  { id: "celular", nome: "Celular", largura: 390, I: Smartphone },
] as const;

/**
 * Prévia ao vivo: o site real renderizado na largura do aparelho escolhido e reduzido (CSS `zoom`) para caber no painel.
 * Como o site usa container queries, cada aparelho mostra o layout dele. O `transform` faz os elementos fixos
 * (botão do WhatsApp) ficarem presos à moldura, não à tela do editor.
 */
export function Previa({ pagina, endereco }: { pagina: PaginaPublica; endereco: string }) {
  const [disp, setDisp] = useState<(typeof DISPOSITIVOS)[number]["id"]>("desktop");
  const caixa = useRef<HTMLDivElement>(null);
  const [disponivel, setDisponivel] = useState(900);
  useEffect(() => {
    const el = caixa.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setDisponivel(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const d = DISPOSITIVOS.find((x) => x.id === disp)!;
  const escala = Math.min(1, (disponivel - (disp === "desktop" ? 0 : 24)) / d.largura);

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="flex rounded-lg border bg-card p-0.5" role="radiogroup" aria-label="Aparelho da prévia">
          {DISPOSITIVOS.map(({ id, nome, I }) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={disp === id}
              title={nome}
              onClick={() => setDisp(id)}
              className={cn("grid h-7 w-9 place-items-center rounded-md text-muted-foreground transition", disp === id && "bg-brand/12 text-foreground")}
            >
              <I className="size-4" />
            </button>
          ))}
        </div>
        <div className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded-lg border bg-card px-3 text-xs text-muted-foreground">
          <span className="size-2 shrink-0 rounded-full bg-success" />
          <span className="truncate font-mono">{endereco}</span>
        </div>
        <span className="hidden text-xs text-muted-foreground tabular-nums sm:block">{Math.round(escala * 100)}%</span>
      </div>
      <div ref={caixa} className="relative min-h-0 flex-1">
        <div
          className={cn(
            "mx-auto h-full overflow-hidden bg-white shadow-2xl shadow-black/10 transition-[width] duration-300",
            disp === "desktop" ? "rounded-xl border" : "rounded-[2rem] border-[10px] border-[#0f1729]",
          )}
          style={{ width: d.largura * escala + (disp === "desktop" ? 2 : 20), transform: "translateZ(0)" }}
        >
          <div className="h-full overflow-x-hidden overflow-y-auto overscroll-contain">
            <div style={{ width: d.largura, zoom: escala }}>
              <PaginaSite pagina={pagina} previa />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
