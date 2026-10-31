import type { Metadata, Viewport } from "next";
import { redirect } from "next/navigation";

import { PaginaSite } from "@/components/site/pagina-site";
import { carregarPagina, origemPublica } from "@/components/site/servidor";
import { linkRede, urlFoto, urlLogo } from "@/components/site/util";
import type { PaginaPublica } from "@/lib/tipos-site";

/**
 * Site público do estúdio. Servido na RAIZ do endereço do estúdio (o `proxy.ts` reescreve "/" para "/s" quando o
 * visitante não tem sessão) e também em "/s". Site não publicado → tela de login (comportamento antigo da raiz).
 */

function titulo(p: PaginaPublica) {
  return p.conteudo.seo.titulo || p.identidade.nome;
}

function descricao(p: PaginaPublica) {
  return (p.conteudo.seo.descricao || p.conteudo.hero.subtitulo || `${p.identidade.nome}: agende sua aula experimental.`).slice(0, 170);
}

function imagemPrincipal(p: PaginaPublica) {
  return urlFoto(p.conteudo.hero.foto) ?? urlFoto(p.conteudo.sobre.foto) ?? urlFoto(p.conteudo.galeria.fotos.find((f) => f.foto)?.foto);
}

export async function generateMetadata(): Promise<Metadata> {
  const p = await carregarPagina();
  if (!p) return { title: "Site", robots: { index: false, follow: false } };
  const origem = await origemPublica();
  const img = imagemPrincipal(p);
  const logo = urlLogo(p.identidade.logo_url);
  return {
    metadataBase: new URL(origem),
    title: { absolute: titulo(p) },
    description: descricao(p),
    alternates: { canonical: "/" },
    robots: { index: true, follow: true },
    openGraph: {
      type: "website",
      locale: "pt_BR",
      url: "/",
      siteName: p.identidade.nome,
      title: titulo(p),
      description: descricao(p),
      images: img ? [{ url: img, alt: p.identidade.nome }] : logo ? [{ url: logo, alt: p.identidade.nome }] : undefined,
    },
    twitter: { card: img ? "summary_large_image" : "summary", title: titulo(p), description: descricao(p) },
    icons: logo ? { icon: logo, apple: logo } : undefined,
    referrer: "strict-origin-when-cross-origin",
  };
}

export async function generateViewport(): Promise<Viewport> {
  const p = await carregarPagina();
  return { themeColor: p?.identidade.cor ?? "#7c8fff", colorScheme: p?.tema === "energia" ? "dark" : "light" };
}

const TIPO_SCHEMA: Record<string, string> = { academia: "ExerciseGym", funcional: "ExerciseGym" };

/** Dados estruturados (schema.org): o negócio local e as perguntas frequentes. */
function dadosEstruturados(p: PaginaPublica, origem: string) {
  const c = p.conteudo;
  const abs = (u: string | null | undefined) => (u ? new URL(u, origem).toString() : undefined);
  const ligada = (t: string) => c.secoes.some((s) => s.tipo === t && s.ativa);
  const negocio: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": TIPO_SCHEMA[c.seo.categoria] ?? "SportsActivityLocation",
    "@id": `${origem}/#estudio`,
    name: p.identidade.nome,
    description: descricao(p),
    url: `${origem}/`,
    image: [imagemPrincipal(p), ...c.galeria.fotos.map((f) => urlFoto(f.foto))].filter(Boolean).slice(0, 5).map((u) => abs(u)),
    logo: abs(urlLogo(p.identidade.logo_url)),
    telephone: c.contato.telefone || c.contato.whatsapp || undefined,
    email: c.contato.email || undefined,
    address: c.localizacao.endereco
      ? {
          "@type": "PostalAddress",
          streetAddress: c.localizacao.endereco,
          addressLocality: c.seo.cidade || undefined,
          addressRegion: c.seo.estado || undefined,
          addressCountry: "BR",
        }
      : undefined,
    hasMap: p.mapa_link ?? undefined,
    sameAs: (["instagram", "facebook", "tiktok", "youtube"] as const).map((r) => linkRede(r, c.contato[r])).filter(Boolean),
  };
  if (ligada("planos")) {
    const ofertas = p.dados.planos
      .filter((pl) => pl.valor != null)
      .map((pl) => ({ "@type": "Offer", name: pl.nome, price: pl.valor, priceCurrency: "BRL" }));
    if (ofertas.length) negocio.makesOffer = ofertas;
  }
  const blocos: Record<string, unknown>[] = [negocio];
  if (ligada("faq") && c.faq.itens.length)
    blocos.push({
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: c.faq.itens.map((q) => ({ "@type": "Question", name: q.pergunta, acceptedAnswer: { "@type": "Answer", text: q.resposta } })),
    });
  // "<" escapado: nenhum texto do estúdio consegue fechar a tag <script>
  return JSON.stringify(blocos.length === 1 ? blocos[0] : blocos).replace(/</g, "\\u003c");
}

export default async function SitePublico() {
  const p = await carregarPagina();
  if (!p) redirect("/login");
  const origem = await origemPublica();
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: dadosEstruturados(p, origem) }} />
      <PaginaSite pagina={p} />
    </>
  );
}
