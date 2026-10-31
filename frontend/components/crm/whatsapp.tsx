"use client";

import { ChevronDown, MessageCircle } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { MensagemPronta } from "@/lib/tipos-crm";

/** Botão de WhatsApp (wa.me) com mensagens prontas para o momento do lead. Abrir uma mensagem registra o contato. */
export function BotaoWhatsapp({
  url,
  mensagens,
  onEnviada,
}: {
  url: string | null;
  mensagens: MensagemPronta[];
  onEnviada?: (m: MensagemPronta) => void;
}) {
  if (!url) {
    return (
      <Button variant="outline" disabled title="Cadastre um telefone com DDD">
        <MessageCircle /> WhatsApp
      </Button>
    );
  }
  return (
    <div className="inline-flex">
      <Button
        className="rounded-r-none bg-[#1A8F5E] text-white hover:bg-[#1A8F5E]/85"
        render={<a href={url} target="_blank" rel="noopener noreferrer" />}
      >
        <MessageCircle /> WhatsApp
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button className="rounded-l-none border-l border-white/30 bg-[#1A8F5E] px-2 text-white hover:bg-[#1A8F5E]/85" aria-label="Mensagens prontas" />}
        >
          <ChevronDown />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-80">
          <DropdownMenuLabel>Mensagens prontas</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {mensagens.map((m, i) => (
            <DropdownMenuItem
              key={m.titulo}
              className="flex-col items-start gap-0.5"
              onClick={() => {
                if (m.url) window.open(m.url, "_blank", "noopener,noreferrer");
                onEnviada?.(m);
              }}
            >
              <span className="text-sm font-medium">
                {m.titulo}
                {i === 0 && <span className="ml-1.5 rounded-full bg-brand/15 px-1.5 text-[10px] text-info-ink">sugerida</span>}
              </span>
              <span className="line-clamp-2 text-xs text-muted-foreground">{m.texto}</span>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => {
              const m = mensagens[0];
              if (m) void navigator.clipboard?.writeText(m.texto).then(() => toast.success("Mensagem copiada."));
            }}
          >
            Copiar a mensagem sugerida
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
