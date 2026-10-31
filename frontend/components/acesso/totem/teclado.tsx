"use client";

import { Delete } from "lucide-react";

import { cn } from "@/lib/utils";

import { somToque } from "./sons";

/** Teclado numérico grande, para tocar com o dedo no tablet. */
export function TecladoNumerico({
  valor,
  onChange,
  max = 11,
  onOk,
  rotuloOk = "Continuar",
  okDesabilitado,
}: {
  valor: string;
  onChange: (v: string) => void;
  max?: number;
  onOk: () => void;
  rotuloOk?: string;
  okDesabilitado?: boolean;
}) {
  const tecla = (t: string) => {
    somToque();
    if (t === "apagar") onChange(valor.slice(0, -1));
    else if (valor.length < max) onChange(valor + t);
  };
  return (
    <div className="grid w-full max-w-sm grid-cols-3 gap-3">
      {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((n) => (
        <Tecla key={n} onClick={() => tecla(n)}>
          {n}
        </Tecla>
      ))}
      <Tecla onClick={() => tecla("apagar")} aria-label="Apagar">
        <Delete className="size-7" />
      </Tecla>
      <Tecla onClick={() => tecla("0")}>0</Tecla>
      <button
        type="button"
        disabled={okDesabilitado}
        onClick={onOk}
        className="h-18 rounded-2xl bg-emerald-500 text-lg font-semibold text-white shadow-lg shadow-emerald-500/30 transition active:scale-95 disabled:opacity-35"
      >
        {rotuloOk}
      </button>
    </div>
  );
}

function Tecla({ className, ...props }: React.ComponentProps<"button">) {
  return (
    <button
      type="button"
      className={cn(
        "grid h-18 place-items-center rounded-2xl bg-white/8 text-3xl font-medium ring-1 ring-white/10 transition active:scale-95 active:bg-white/20",
        className,
      )}
      {...props}
    />
  );
}

/** Mostra o valor digitado com máscara de CPF quando tem 11 dígitos; PIN vira bolinhas. */
export function Visor({ valor, segredo, placeholder }: { valor: string; segredo?: boolean; placeholder: string }) {
  let texto = valor;
  if (segredo) texto = "●".repeat(valor.length);
  else if (valor.length === 11) texto = `${valor.slice(0, 3)}.${valor.slice(3, 6)}.${valor.slice(6, 9)}-${valor.slice(9)}`;
  return (
    <div className="flex h-18 w-full max-w-sm items-center justify-center rounded-2xl bg-black/30 px-4 font-mono text-3xl tracking-widest ring-1 ring-white/15">
      {texto || <span className="font-sans text-lg tracking-normal text-white/40">{placeholder}</span>}
    </div>
  );
}
