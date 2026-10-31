import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { FONTES_SITE } from "@/components/site/fontes";
import { carregarPagina } from "@/components/site/servidor";
import { corSobre } from "@/components/site/util";
import { cn } from "@/lib/utils";

import "@/components/site/site.css";

export async function generateMetadata(): Promise<Metadata> {
  const p = await carregarPagina();
  return {
    title: { absolute: p ? `Política de privacidade · ${p.identidade.nome}` : "Política de privacidade" },
    robots: { index: !!p, follow: true },
  };
}

/** Política de privacidade gerada a partir dos dados do estúdio (formulário de contato do site, LGPD). */
export default async function Privacidade() {
  const p = await carregarPagina();
  if (!p) redirect("/login");
  const nome = p.identidade.nome;
  const pv = p.conteudo.privacidade;
  const controlador = pv.responsavel || nome;
  const email = pv.email || p.conteudo.contato.email;
  const atualizado = p.publicado_em ? new Date(p.publicado_em).toLocaleDateString("pt-BR") : null;

  const secoes: [string, React.ReactNode][] = [
    [
      "Quem cuida dos seus dados",
      <>
        O responsável (controlador) pelos dados enviados neste site é <strong>{controlador}</strong>
        {pv.documento ? `, ${pv.documento}` : ""}. Para qualquer assunto sobre seus dados, fale com a gente
        {email ? (
          <>
            {" "}
            pelo e-mail <a href={`mailto:${email}`}>{email}</a>
          </>
        ) : (
          " pelos canais de contato do site"
        )}
        .
      </>,
    ],
    [
      "Quais dados coletamos",
      "Somente o que você digita no formulário de contato: nome, telefone/WhatsApp, e-mail, a modalidade ou plano de interesse e a mensagem. Também registramos a data e a hora do seu consentimento. Não coletamos dados sensíveis pelo site e não usamos cookies de publicidade.",
    ],
    [
      "Para que usamos",
      "Para responder ao seu contato, agendar a aula experimental e apresentar nossos planos. Não vendemos nem compartilhamos seus dados com terceiros para fins de marketing.",
    ],
    [
      "Base legal",
      "O tratamento é feito com base no seu consentimento (art. 7º, I, da Lei 13.709/2018 — LGPD), dado ao marcar a autorização no formulário, e, se você se matricular, na execução do contrato.",
    ],
    [
      "Por quanto tempo guardamos",
      "Enquanto durar o atendimento do seu pedido e, se você não se matricular, por até 12 meses. Depois disso os dados são excluídos ou anonimizados, salvo obrigação legal de guarda.",
    ],
    [
      "Onde os dados ficam",
      "Em sistema de gestão do estúdio, com acesso restrito à equipe autorizada, conexão criptografada (HTTPS) e controle de acesso por perfil.",
    ],
    [
      "Seus direitos",
      "Você pode, a qualquer momento e sem custo, confirmar se tratamos seus dados, acessá-los, corrigi-los, pedir a exclusão, revogar o consentimento e pedir informações sobre compartilhamento (art. 18 da LGPD). Basta nos procurar pelos canais acima. Você também pode reclamar à Autoridade Nacional de Proteção de Dados (ANPD).",
    ],
  ];

  return (
    <div
      className={cn("site min-h-dvh px-5 py-12", FONTES_SITE)}
      data-tema={p.tema}
      style={{ ["--s-marca" as string]: p.identidade.cor, ["--s-marca-txt" as string]: corSobre(p.identidade.cor) }}
    >
      <article className="mx-auto max-w-2xl">
        {/* navegação completa de propósito: a raiz é reescrita para o site pelo proxy */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a href="/" className="inline-flex items-center gap-1 text-sm text-(--s-suave) hover:text-(--s-texto)">
          <ArrowLeft className="size-4" /> Voltar ao site
        </a>
        <p className="s-sobrelinha mt-10">{nome}</p>
        <h1 className="s-titulo mt-3 text-4xl">Política de privacidade</h1>
        {atualizado && <p className="mt-2 text-sm text-(--s-suave)">Atualizada em {atualizado}</p>}
        <div className="mt-10 grid gap-8 leading-relaxed [&_a]:text-(--s-marca) [&_a]:underline">
          {secoes.map(([t, txt]) => (
            <section key={t}>
              <h2 className="s-titulo text-2xl">{t}</h2>
              <p className="mt-2 text-(--s-suave)">{txt}</p>
            </section>
          ))}
        </div>
      </article>
    </div>
  );
}
