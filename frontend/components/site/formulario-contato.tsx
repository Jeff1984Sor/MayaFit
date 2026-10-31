"use client";

import { CheckCircle2, Loader2, Send } from "lucide-react";
import { useRef, useState, useTransition } from "react";

import { enviarContato } from "@/components/site/acoes";

/** Formulário "Agende sua aula experimental": honeypot invisível, tempo de preenchimento e consentimento LGPD.
 * Na prévia do editor (`previa`), não envia nada. */
export function FormularioContato({
  opcoes,
  botao,
  previa,
  whatsapp,
}: {
  opcoes: string[];
  botao: string;
  previa?: boolean;
  whatsapp?: string | null;
}) {
  const inicio = useRef<number | null>(null);
  const [pendente, iniciar] = useTransition();
  const [erro, setErro] = useState<string | null>(null);
  const [enviado, setEnviado] = useState<string | null>(null);

  function marcarInicio() {
    if (inicio.current == null) inicio.current = Date.now();
  }

  function enviar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErro(null);
    const f = new FormData(e.currentTarget);
    const tel = String(f.get("telefone") ?? "").trim();
    const email = String(f.get("email") ?? "").trim();
    if (!tel && !email) return setErro("Informe um telefone ou um e-mail para retornarmos.");
    if (!f.get("consentimento")) return setErro("Marque a autorização de uso dos dados para enviar.");
    if (previa) return setEnviado("Prévia: no site publicado, este contato chega ao CRM do estúdio.");
    iniciar(async () => {
      const r = await enviarContato({
        nome: String(f.get("nome") ?? "").trim(),
        telefone: tel,
        email,
        interesse: String(f.get("interesse") ?? ""),
        mensagem: String(f.get("mensagem") ?? "").trim(),
        quer_aula_experimental: f.get("experimental") === "on",
        consentimento: true,
        website: String(f.get("website") ?? ""),
        tempo_ms: inicio.current ? Date.now() - inicio.current : 0,
      });
      if (r.ok) setEnviado(r.mensagem);
      else setErro(r.erro);
    });
  }

  if (enviado)
    return (
      <div role="status" className="s-card flex flex-col items-center gap-3 p-8 text-center">
        <CheckCircle2 className="size-12 text-(--s-marca)" />
        <p className="s-titulo text-2xl">Contato enviado!</p>
        <p className="text-(--s-suave)">{enviado}</p>
        {whatsapp && (
          <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="s-botao-sec mt-2">
            Prefere adiantar pelo WhatsApp?
          </a>
        )}
      </div>
    );

  return (
    <form onSubmit={enviar} onFocus={marcarInicio} className="s-card grid gap-3 p-5 @md:p-7" noValidate>
      <p className="s-titulo text-xl">Agende sua aula experimental</p>
      <label className="grid gap-1 text-sm font-medium">
        Nome
        <input name="nome" required minLength={2} maxLength={150} autoComplete="name" className="s-campo" placeholder="Como podemos te chamar?" />
      </label>
      <div className="grid gap-3 @lg:grid-cols-2">
        <label className="grid gap-1 text-sm font-medium">
          WhatsApp / telefone
          <input name="telefone" inputMode="tel" maxLength={30} autoComplete="tel" className="s-campo" placeholder="(11) 99999-0000" />
        </label>
        <label className="grid gap-1 text-sm font-medium">
          E-mail
          <input name="email" type="email" maxLength={200} autoComplete="email" className="s-campo" placeholder="voce@email.com" />
        </label>
      </div>
      {opcoes.length > 0 && (
        <label className="grid gap-1 text-sm font-medium">
          Tenho interesse em
          <select name="interesse" className="s-campo" defaultValue="">
            <option value="">Ainda não sei</option>
            {opcoes.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="grid gap-1 text-sm font-medium">
        Mensagem (opcional)
        <textarea name="mensagem" rows={3} maxLength={2000} className="s-campo resize-y" placeholder="Melhores dias e horários, objetivos, alguma limitação…" />
      </label>
      {/* honeypot: invisível para pessoas, irresistível para robôs */}
      <div aria-hidden className="sr-only">
        <label>
          Site
          <input name="website" tabIndex={-1} autoComplete="off" />
        </label>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="experimental" defaultChecked className="mt-1 size-4 accent-(--s-marca)" />
        Quero agendar uma aula experimental
      </label>
      <label className="flex items-start gap-2 text-sm text-(--s-suave)">
        <input type="checkbox" name="consentimento" required className="mt-1 size-4 accent-(--s-marca)" />
        <span>
          Autorizo o uso dos meus dados para retornarem este contato, conforme a{" "}
          <a href="/s/privacidade" className="underline underline-offset-2" target={previa ? "_blank" : undefined}>
            política de privacidade
          </a>
          .
        </span>
      </label>
      {erro && (
        <p role="alert" className="rounded-(--s-raio-sm) bg-red-500/10 px-3 py-2 text-sm text-red-600">
          {erro}
        </p>
      )}
      <button type="submit" className="s-botao mt-1 w-full" disabled={pendente}>
        {pendente ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        {botao}
      </button>
    </form>
  );
}
