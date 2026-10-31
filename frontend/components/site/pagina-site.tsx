/* eslint-disable @next/next/no-img-element -- fotos do site já chegam comprimidas (o editor reduz antes de enviar) */
/**
 * O site one-page do estúdio. Componente SEM estado (renderiza no servidor na página pública e no cliente na prévia
 * do editor). Layout por container queries: a prévia em largura de celular mostra o layout de celular.
 */
import { ArrowRight, CalendarDays, Check, Clock, Mail, MapPin, Menu, Phone, Plus, Quote, Sparkles, X } from "lucide-react";

import { FONTES_SITE } from "@/components/site/fontes";
import { FormularioContato } from "@/components/site/formulario-contato";
import { IconeFacebook, IconeInstagram, IconeTiktok, IconeWhatsapp, IconeYoutube } from "@/components/site/icones";
import {
  ANCORA,
  DIAS,
  corSobre,
  hora,
  iniciais,
  linkRede,
  linkWhatsapp,
  preco,
  secoesAtivas,
  urlFoto,
  urlLogo,
} from "@/components/site/util";
import type { PaginaPublica, TipoSecao } from "@/lib/tipos-site";
import { cn } from "@/lib/utils";

import "./site.css";

type P = { p: PaginaPublica; previa?: boolean };

const ROTULO_MENU: Partial<Record<TipoSecao, string>> = {
  sobre: "Sobre",
  modalidades: "Modalidades",
  planos: "Planos",
  grade: "Horários",
  equipe: "Equipe",
  galeria: "Espaço",
  faq: "Dúvidas",
  localizacao: "Onde estamos",
};

function whatsDe(p: PaginaPublica) {
  return p.conteudo.contato.whatsapp ? linkWhatsapp(p.conteudo.contato.whatsapp, p.conteudo.contato.mensagem_whatsapp) : null;
}

/** Seções que têm o que mostrar (as vazias somem do site; na prévia viram um aviso). */
export function temConteudo(t: TipoSecao, p: PaginaPublica): boolean {
  const { conteudo: c, dados: d } = p;
  switch (t) {
    case "modalidades":
      return d.modalidades.length > 0;
    case "planos":
      return d.planos.length > 0;
    case "grade":
      return d.grade.length > 0;
    case "equipe":
      return d.profissionais.length > 0;
    case "depoimentos":
      return c.depoimentos.itens.length > 0;
    case "galeria":
      return c.galeria.fotos.some((f) => f.foto);
    case "faq":
      return c.faq.itens.length > 0;
    case "localizacao":
      return !!(c.localizacao.endereco || p.mapa_embed);
    case "sobre":
      return !!(c.sobre.texto || c.sobre.titulo);
    default:
      return true;
  }
}

const DICA_VAZIA: Partial<Record<TipoSecao, string>> = {
  modalidades: "Cadastre tipos de serviço (Cadastros › Tipos de serviço) ou ligue alguma modalidade.",
  planos: "Cadastre planos ativos ou desmarque os planos ocultos.",
  grade: "Cadastre a grade fixa de horários ou aulas na agenda.",
  equipe: "Marque quem aparece no site na aba Equipe.",
  depoimentos: "Acrescente depoimentos de alunos (com autorização deles).",
  galeria: "Envie fotos do espaço.",
  faq: "Acrescente perguntas frequentes.",
  localizacao: "Informe o endereço do estúdio.",
};

// ------------------------------------------------------------------------------------------------ peças comuns
function Foto({ foto, alt, className, prioridade, rotulo }: { foto: string | null; alt: string; className?: string; prioridade?: boolean; rotulo?: string }) {
  const src = urlFoto(foto);
  if (!src)
    return (
      <div className={cn("s-arte relative grid place-items-center overflow-hidden", className)} role="img" aria-label={alt}>
        {rotulo && <span className="s-titulo text-6xl text-white/80 mix-blend-overlay select-none">{rotulo}</span>}
      </div>
    );
  return (
    <div className={cn("s-zoom overflow-hidden", className)}>
      <img
        src={src}
        alt={alt}
        className="size-full object-cover"
        loading={prioridade ? "eager" : "lazy"}
        decoding="async"
        fetchPriority={prioridade ? "high" : undefined}
      />
    </div>
  );
}

function Bloco({ id, alt, children, className }: { id: string; alt?: boolean; children: React.ReactNode; className?: string }) {
  return (
    <section id={id} className={cn("scroll-mt-16 px-5 py-16 @3xl:px-8 @3xl:py-24", alt && "bg-(--s-fundo-alt)", className)}>
      <div className="mx-auto max-w-6xl">{children}</div>
    </section>
  );
}

function Cabeca({ sobre, titulo, subtitulo, centro }: { sobre?: string; titulo: string; subtitulo?: string; centro?: boolean }) {
  return (
    <div className={cn("s-revela mb-10 max-w-2xl @3xl:mb-14", centro && "mx-auto text-center")}>
      {sobre && <p className="s-sobrelinha mb-3">{sobre}</p>}
      <h2 className="s-titulo text-[2.1rem] @3xl:text-5xl">{titulo}</h2>
      {subtitulo && <p className="mt-4 text-lg text-(--s-suave)">{subtitulo}</p>}
    </div>
  );
}

function Logo({ p, className }: { p: PaginaPublica; className?: string }) {
  const logo = urlLogo(p.identidade.logo_url);
  if (logo) return <img src={logo} alt={p.identidade.nome} className={cn("h-9 w-auto max-w-[140px] object-contain", className)} />;
  return (
    <span className={cn("grid size-9 place-items-center rounded-(--s-raio-sm) bg-(--s-marca) text-sm font-bold text-(--s-marca-txt)", className)}>
      {iniciais(p.identidade.nome)}
    </span>
  );
}

function Redes({ p, className }: { p: PaginaPublica; className?: string }) {
  const c = p.conteudo.contato;
  const redes = [
    { href: linkRede("instagram", c.instagram), nome: "Instagram", I: IconeInstagram },
    { href: linkRede("facebook", c.facebook), nome: "Facebook", I: IconeFacebook },
    { href: linkRede("tiktok", c.tiktok), nome: "TikTok", I: IconeTiktok },
    { href: linkRede("youtube", c.youtube), nome: "YouTube", I: IconeYoutube },
  ].filter((r) => r.href);
  if (!redes.length) return null;
  return (
    <div className={cn("flex gap-2", className)}>
      {redes.map(({ href, nome, I }) => (
        <a
          key={nome}
          href={href!}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={nome}
          className="grid size-10 place-items-center rounded-full border border-(--s-borda) transition hover:bg-(--s-marca) hover:text-(--s-marca-txt)"
        >
          <I className="size-[18px]" />
        </a>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- topo
function Topo({ p }: P) {
  const links = secoesAtivas(p.conteudo)
    .filter((s) => ROTULO_MENU[s.tipo] && temConteudo(s.tipo, p))
    .slice(0, 6);
  const temContato = p.conteudo.secoes.some((s) => s.tipo === "contato" && s.ativa);
  return (
    <header className="sticky top-0 z-30 border-b border-(--s-borda) bg-(--s-fundo)/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-5 @3xl:px-8">
        <a href="#inicio" className="flex min-w-0 items-center gap-2.5">
          <Logo p={p} />
          <span className="truncate font-semibold">{p.identidade.nome}</span>
        </a>
        <nav aria-label="Seções" className="ml-auto hidden items-center gap-6 text-sm @5xl:flex">
          {links.map((s) => (
            <a key={s.tipo} href={`#${ANCORA[s.tipo]}`} className="text-(--s-suave) transition hover:text-(--s-texto)">
              {ROTULO_MENU[s.tipo]}
            </a>
          ))}
        </nav>
        {temContato && (
          <a href="#contato" className="s-botao ml-auto hidden !px-4 !py-2 text-sm @xl:inline-flex @5xl:ml-0">
            Aula experimental
          </a>
        )}
        {links.length > 0 && (
          <details className="group relative ml-auto @xl:ml-0 @5xl:hidden">
            <summary aria-label="Abrir menu" className="grid size-10 place-items-center rounded-full border border-(--s-borda)">
              <Menu className="size-5 group-open:hidden" />
              <X className="hidden size-5 group-open:block" />
            </summary>
            <nav aria-label="Seções" className="s-card absolute top-12 right-0 grid w-56 gap-1 p-2 text-sm">
              {links.map((s) => (
                <a key={s.tipo} href={`#${ANCORA[s.tipo]}`} className="rounded-(--s-raio-sm) px-3 py-2.5 hover:bg-(--s-fundo-alt)">
                  {ROTULO_MENU[s.tipo]}
                </a>
              ))}
              {temContato && (
                <a href="#contato" className="s-botao mt-1 !py-2.5 text-sm">
                  Aula experimental
                </a>
              )}
            </nav>
          </details>
        )}
      </div>
    </header>
  );
}

// ----------------------------------------------------------------------------------------------------- hero
function Hero({ p }: P) {
  const h = p.conteudo.hero;
  const whats = whatsDe(p);
  const local = [p.conteudo.seo.cidade, p.conteudo.seo.estado].filter(Boolean).join(" · ");
  const titulo = h.titulo || p.identidade.nome;
  const botoes = (
    <div className="s-entra s-entra-3 mt-8 flex flex-wrap gap-3">
      <a href="#contato" className="s-botao">
        <CalendarDays className="size-4" />
        {h.botao_texto || "Agende sua aula experimental"}
      </a>
      {whats && (
        <a href={whats} target="_blank" rel="noopener noreferrer" className="s-botao-sec">
          <IconeWhatsapp className="size-4" /> WhatsApp
        </a>
      )}
    </div>
  );
  const destaques = p.conteudo.sobre.destaques.slice(0, 3);
  const selos = destaques.length > 0 && (
    <ul className="s-entra s-entra-3 mt-8 flex flex-wrap gap-x-5 gap-y-2 text-sm text-(--s-suave)">
      {destaques.map((d) => (
        <li key={d} className="flex items-center gap-1.5">
          <Check className="size-4 text-(--s-marca)" /> {d}
        </li>
      ))}
    </ul>
  );

  if (p.tema === "energia")
    return (
      <section id="inicio" className="relative isolate overflow-hidden">
        <Foto foto={h.foto} alt={titulo} prioridade className="absolute inset-0 -z-20 size-full opacity-60" />
        <div className="absolute inset-0 -z-10 bg-linear-to-t from-(--s-fundo) via-(--s-fundo)/70 to-(--s-fundo)/20" />
        <div className="mx-auto flex min-h-[560px] max-w-6xl flex-col justify-end px-5 pt-28 pb-16 @3xl:min-h-[680px] @3xl:px-8 @3xl:pb-24">
          {local && <p className="s-sobrelinha s-entra">{local}</p>}
          <h1 className="s-titulo s-entra s-entra-2 mt-4 max-w-4xl text-[2.9rem] @3xl:text-7xl @5xl:text-[5.5rem]">{titulo}</h1>
          <span className="s-entra s-entra-2 mt-6 block h-1.5 w-24 bg-(--s-marca)" />
          {h.subtitulo && <p className="s-entra s-entra-3 mt-6 max-w-xl text-lg text-(--s-suave)">{h.subtitulo}</p>}
          {botoes}
          {selos}
        </div>
      </section>
    );

  if (p.tema === "zen")
    return (
      <section id="inicio" className="px-5 pt-12 pb-16 @3xl:px-8 @3xl:pt-20 @3xl:pb-24">
        <div className="mx-auto grid max-w-6xl items-center gap-12 @4xl:grid-cols-[1fr_0.85fr]">
          <div>
            <p className="s-sobrelinha s-entra flex items-center gap-3">
              <span className="h-px w-10 bg-(--s-marca)" /> {local || p.identidade.nome}
            </p>
            <h1 className="s-titulo s-entra s-entra-2 mt-6 text-5xl @3xl:text-7xl">{titulo}</h1>
            {h.subtitulo && <p className="s-entra s-entra-3 mt-6 max-w-lg text-lg leading-relaxed text-(--s-suave)">{h.subtitulo}</p>}
            {botoes}
            {selos}
          </div>
          <div className="s-entra s-entra-2 relative mx-auto w-full max-w-xs @3xl:max-w-md">
            <div className="absolute -inset-3 rounded-t-full border border-(--s-marca)/40" />
            <Foto foto={h.foto} alt={titulo} prioridade className="aspect-[4/5] rounded-t-full" />
          </div>
        </div>
      </section>
    );

  return (
    <section id="inicio" className="relative isolate overflow-hidden px-5 pt-14 pb-20 @3xl:px-8 @3xl:pt-24 @3xl:pb-28">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="s-bolha -top-24 -left-20 size-80" />
        <div className="s-bolha s-bolha-2 top-40 right-[-6rem] size-96" />
      </div>
      <div className="mx-auto grid max-w-6xl items-center gap-12 @4xl:grid-cols-[1.1fr_0.9fr]">
        <div>
          <p className="s-sobrelinha s-entra inline-flex items-center gap-2 rounded-full bg-(--s-card)/70 px-3 py-1.5 shadow-sm">
            <Sparkles className="size-3.5" /> {local || p.identidade.nome}
          </p>
          <h1 className="s-titulo s-entra s-entra-2 mt-5 text-[2.7rem] @3xl:text-6xl @5xl:text-7xl">{titulo}</h1>
          {h.subtitulo && <p className="s-entra s-entra-3 mt-6 max-w-xl text-lg text-(--s-suave)">{h.subtitulo}</p>}
          {botoes}
          {selos}
        </div>
        <Foto
          foto={h.foto}
          alt={titulo}
          prioridade
          className="s-entra s-entra-2 aspect-[4/3] rounded-[2rem_2rem_2rem_5rem] shadow-2xl shadow-(--s-marca)/20 @4xl:aspect-[4/5] @4xl:rounded-[2.5rem_2.5rem_2.5rem_7rem]"
        />
      </div>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------- seções
function Sobre({ p, alt }: P & { alt: boolean }) {
  const s = p.conteudo.sobre;
  return (
    <Bloco id="sobre" alt={alt}>
      <div className="grid items-center gap-12 @4xl:grid-cols-2">
        <Foto foto={s.foto} alt={s.titulo} className="s-revela aspect-[16/10] rounded-(--s-raio) @4xl:aspect-[5/4]" />
        <div className="s-revela">
          <p className="s-sobrelinha mb-3">Quem somos</p>
          <h2 className="s-titulo text-[2.1rem] @3xl:text-5xl">{s.titulo}</h2>
          {s.texto.split(/\n{2,}/).map((par, i) => (
            <p key={i} className="mt-5 text-lg leading-relaxed whitespace-pre-line text-(--s-suave)">
              {par}
            </p>
          ))}
          {s.destaques.length > 0 && (
            <ul className="mt-8 grid gap-3 @xl:grid-cols-2">
              {s.destaques.map((d) => (
                <li key={d} className="flex items-center gap-3 font-medium">
                  <span className="grid size-8 shrink-0 place-items-center rounded-full bg-(--s-marca)/12 text-(--s-marca)">
                    <Check className="size-4" />
                  </span>
                  {d}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Bloco>
  );
}

function Modalidades({ p, alt }: P & { alt: boolean }) {
  const c = p.conteudo.modalidades;
  const itens = p.dados.modalidades.map((m) => ({ ...m, item: c.itens.find((i) => i.tipo_servico_id === m.id) }));
  return (
    <Bloco id="modalidades" alt={alt}>
      <Cabeca sobre="O que oferecemos" titulo={c.titulo} subtitulo={c.subtitulo} />
      <div className="grid gap-5 @xl:grid-cols-2 @4xl:grid-cols-3">
        {itens.map((m) => (
          <article key={m.id} className="s-card s-revela group overflow-hidden">
            <Foto foto={m.item?.foto ?? null} alt={m.nome} rotulo={m.nome.slice(0, 1)} className="aspect-[4/3]" />
            <div className="p-6">
              <h3 className="s-titulo text-2xl">{m.nome}</h3>
              {m.item?.descricao && <p className="mt-2 text-(--s-suave)">{m.item.descricao}</p>}
              <a href="#contato" className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-(--s-marca)">
                Quero experimentar <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
              </a>
            </div>
          </article>
        ))}
      </div>
    </Bloco>
  );
}

function Planos({ p, alt }: P & { alt: boolean }) {
  const c = p.conteudo.planos;
  return (
    <Bloco id="planos" alt={alt}>
      <Cabeca sobre="Planos" titulo={c.titulo} subtitulo={c.subtitulo} centro />
      <div className="mx-auto grid max-w-5xl gap-5 @3xl:grid-cols-2 @5xl:grid-cols-3">
        {p.dados.planos.map((pl) => {
          const destaque = c.destaque_id === pl.id;
          const valor = preco(pl.valor);
          return (
            <article
              key={pl.id}
              className={cn(
                "s-card s-revela relative flex flex-col p-7",
                destaque && "border-(--s-marca) bg-(--s-marca) text-(--s-marca-txt) @5xl:-my-3 @5xl:py-10",
              )}
            >
              {destaque && (
                <span className="absolute -top-3 left-7 rounded-full bg-(--s-texto) px-3 py-1 text-xs font-semibold text-(--s-fundo)">
                  Mais escolhido
                </span>
              )}
              {pl.modalidade && <p className={cn("s-sobrelinha", destaque && "!text-current opacity-80")}>{pl.modalidade}</p>}
              <h3 className="s-titulo mt-2 text-2xl">{pl.nome}</h3>
              <div className="mt-5 flex items-end gap-1">
                {valor ? (
                  <>
                    <span className="text-4xl font-bold tracking-tight tabular-nums">{valor}</span>
                    <span className={cn("pb-1 text-sm", destaque ? "opacity-80" : "text-(--s-suave)")}>{pl.avulso ? "/aula" : "/mês"}</span>
                  </>
                ) : (
                  <span className="text-lg font-semibold">Consulte valores</span>
                )}
              </div>
              <ul className={cn("mt-6 grid gap-2 text-sm", destaque ? "opacity-90" : "text-(--s-suave)")}>
                {pl.avulso ? (
                  <li className="flex gap-2">
                    <Check className="size-4 shrink-0" /> Aula avulsa, sem compromisso
                  </li>
                ) : (
                  <li className="flex gap-2">
                    <Check className="size-4 shrink-0" /> {pl.aulas_por_semana}x por semana
                  </li>
                )}
                {pl.duracao_meses > 1 && (
                  <li className="flex gap-2">
                    <Check className="size-4 shrink-0" /> Plano de {pl.duracao_meses} meses
                  </li>
                )}
              </ul>
              <a
                href="#contato"
                className={cn("mt-8", destaque ? "s-botao-sec !border-current" : "s-botao")}
              >
                Quero este plano
              </a>
            </article>
          );
        })}
      </div>
      {c.observacao && <p className="mt-8 text-center text-sm text-(--s-suave)">{c.observacao}</p>}
    </Bloco>
  );
}

function Grade({ p, alt }: P & { alt: boolean }) {
  const c = p.conteudo.grade;
  const dias = [...new Set(p.dados.grade.map((h) => h.dia_semana))].sort();
  return (
    <Bloco id="horarios" alt={alt}>
      <Cabeca sobre="Grade semanal" titulo={c.titulo} subtitulo={c.subtitulo} />
      <div className="s-rolagem -mx-5 flex gap-4 overflow-x-auto px-5 pb-4 @3xl:mx-0 @3xl:px-0">
        {dias.map((d) => (
          <div key={d} className="s-card s-revela w-[230px] shrink-0 p-5 @5xl:w-auto @5xl:min-w-0 @5xl:flex-1">
            <p className="s-titulo border-b border-(--s-borda) pb-3 text-xl">{DIAS[d]}</p>
            <ul className="mt-3 grid gap-3">
              {p.dados.grade
                .filter((h) => h.dia_semana === d)
                .map((h, i) => (
                  <li key={i} className="grid gap-0.5">
                    <span className="flex items-center gap-1.5 text-sm font-semibold tabular-nums text-(--s-marca)">
                      <Clock className="size-3.5" />
                      {hora(h.hora_inicio)}–{hora(h.hora_fim)}
                    </span>
                    <span className="font-medium">{h.modalidade}</span>
                    {h.professor && <span className="text-xs text-(--s-suave)">com {h.professor}</span>}
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
    </Bloco>
  );
}

function Equipe({ p, alt }: P & { alt: boolean }) {
  const c = p.conteudo.equipe;
  return (
    <Bloco id="equipe" alt={alt}>
      <Cabeca sobre="Quem cuida de você" titulo={c.titulo} subtitulo={c.subtitulo} />
      <div className="grid gap-6 @xl:grid-cols-2 @4xl:grid-cols-3">
        {p.dados.profissionais.map((pr) => {
          const it = c.itens.find((i) => i.profissional_id === pr.id);
          return (
            <article key={pr.id} className="s-revela">
              <Foto foto={it?.foto ?? null} alt={pr.nome} rotulo={iniciais(pr.nome)} className="aspect-[4/5] rounded-(--s-raio)" />
              <h3 className="s-titulo mt-5 text-2xl">{pr.nome}</h3>
              {it?.cargo && <p className="s-sobrelinha mt-1 !tracking-[0.1em]">{it.cargo}</p>}
              {it?.bio && <p className="mt-3 text-(--s-suave)">{it.bio}</p>}
            </article>
          );
        })}
      </div>
    </Bloco>
  );
}

function Depoimentos({ p, alt }: P & { alt: boolean }) {
  const c = p.conteudo.depoimentos;
  return (
    <Bloco id="depoimentos" alt={alt}>
      <Cabeca sobre="Depoimentos" titulo={c.titulo} centro />
      <div className="grid gap-5 @3xl:grid-cols-2 @5xl:grid-cols-3">
        {c.itens.map((d, i) => (
          <figure key={i} className="s-card s-revela flex flex-col p-7">
            <Quote className="size-8 text-(--s-marca)" />
            <blockquote className="mt-4 flex-1 text-lg leading-relaxed">“{d.texto}”</blockquote>
            <figcaption className="mt-6 flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-full bg-(--s-marca)/15 text-sm font-semibold text-(--s-marca)">
                {iniciais(d.nome)}
              </span>
              <span>
                <span className="block font-semibold">{d.nome}</span>
                {d.detalhe && <span className="block text-sm text-(--s-suave)">{d.detalhe}</span>}
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
    </Bloco>
  );
}

function Galeria({ p, alt }: P & { alt: boolean }) {
  const c = p.conteudo.galeria;
  return (
    <Bloco id="galeria" alt={alt}>
      <Cabeca sobre="Galeria" titulo={c.titulo} />
      <div className="columns-2 gap-4 @3xl:columns-3">
        {c.fotos
          .filter((f) => urlFoto(f.foto))
          .map((f, i) => (
            <figure key={i} className="s-revela s-zoom mb-4 break-inside-avoid overflow-hidden rounded-(--s-raio-sm)">
              <img src={urlFoto(f.foto)!} alt={f.legenda || `Foto ${i + 1} do espaço`} loading="lazy" decoding="async" className="w-full" />
              {f.legenda && <figcaption className="bg-(--s-card) px-3 py-2 text-sm text-(--s-suave)">{f.legenda}</figcaption>}
            </figure>
          ))}
      </div>
    </Bloco>
  );
}

function Faq({ p, alt }: P & { alt: boolean }) {
  const c = p.conteudo.faq;
  return (
    <Bloco id="duvidas" alt={alt}>
      <div className="grid gap-10 @4xl:grid-cols-[0.8fr_1.2fr]">
        <Cabeca sobre="Dúvidas" titulo={c.titulo} subtitulo="Não encontrou sua pergunta? Fale com a gente." />
        <div className="grid gap-3">
          {c.itens.map((q, i) => (
            <details key={i} className="s-card s-revela group px-6 py-5">
              <summary className="flex items-center justify-between gap-4 text-lg font-semibold">
                {q.pergunta}
                <Plus className="s-mais size-5 shrink-0 text-(--s-marca)" />
              </summary>
              <p className="mt-3 leading-relaxed whitespace-pre-line text-(--s-suave)">{q.resposta}</p>
            </details>
          ))}
        </div>
      </div>
    </Bloco>
  );
}

function Localizacao({ p, alt, previa }: P & { alt: boolean }) {
  const c = p.conteudo.localizacao;
  return (
    <Bloco id="onde-estamos" alt={alt}>
      <div className="grid items-stretch gap-8 @4xl:grid-cols-[0.8fr_1.2fr]">
        <div className="s-revela flex flex-col">
          <Cabeca sobre="Localização" titulo={c.titulo} />
          <ul className="grid gap-5 text-lg">
            {c.endereco && (
              <li className="flex gap-3">
                <MapPin className="mt-1 size-5 shrink-0 text-(--s-marca)" /> {c.endereco}
              </li>
            )}
            {c.horario_texto && (
              <li className="flex gap-3 whitespace-pre-line">
                <Clock className="mt-1 size-5 shrink-0 text-(--s-marca)" /> {c.horario_texto}
              </li>
            )}
          </ul>
          {p.mapa_link && (
            <a href={p.mapa_link} target="_blank" rel="noopener noreferrer" className="s-botao-sec mt-8 self-start">
              <MapPin className="size-4" /> Como chegar
            </a>
          )}
        </div>
        {p.mapa_embed && (
          <div className="s-card s-revela min-h-[320px] overflow-hidden">
            {previa ? (
              <div className="s-arte grid size-full min-h-[320px] place-items-center text-white">
                <span className="flex items-center gap-2 rounded-full bg-black/40 px-4 py-2 text-sm">
                  <MapPin className="size-4" /> O mapa aparece aqui no site publicado
                </span>
              </div>
            ) : (
              <iframe
                src={p.mapa_embed}
                title={`Mapa: ${c.endereco || p.identidade.nome}`}
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
                className="size-full min-h-[320px] border-0"
                allowFullScreen
              />
            )}
          </div>
        )}
      </div>
    </Bloco>
  );
}

function Contato({ p, alt, previa }: P & { alt: boolean }) {
  const c = p.conteudo.contato;
  const whats = whatsDe(p);
  const opcoes = [...p.dados.modalidades.map((m) => m.nome), ...p.dados.planos.map((pl) => `Plano ${pl.nome}`)];
  return (
    <Bloco id="contato" alt={alt}>
      <div className="grid gap-12 @4xl:grid-cols-2">
        <div className="s-revela">
          <p className="s-sobrelinha mb-3">Contato</p>
          <h2 className="s-titulo text-[2.1rem] @3xl:text-5xl">{c.titulo}</h2>
          {c.subtitulo && <p className="mt-4 text-lg text-(--s-suave)">{c.subtitulo}</p>}
          <div className="mt-8 grid gap-4">
            {whats && (
              <a
                href={whats}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-3 self-start rounded-full bg-[#25D366] px-6 py-3.5 font-semibold text-white shadow-lg shadow-[#25D366]/30 transition hover:brightness-105"
              >
                <IconeWhatsapp className="size-5" /> Chamar no WhatsApp
              </a>
            )}
            {c.telefone && (
              <a href={`tel:+55${c.telefone.replace(/\D/g, "")}`} className="flex items-center gap-3 text-lg">
                <Phone className="size-5 text-(--s-marca)" /> {c.telefone}
              </a>
            )}
            {c.email && (
              <a href={`mailto:${c.email}`} className="flex items-center gap-3 text-lg break-all">
                <Mail className="size-5 shrink-0 text-(--s-marca)" /> {c.email}
              </a>
            )}
          </div>
          <Redes p={p} className="mt-8" />
        </div>
        <div className="s-revela">
          <FormularioContato opcoes={opcoes} botao={p.conteudo.hero.botao_texto || "Quero agendar"} previa={previa} whatsapp={whats} />
        </div>
      </div>
    </Bloco>
  );
}

function Rodape({ p }: P) {
  return (
    <footer className="border-t border-(--s-borda) px-5 py-10 @3xl:px-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 @3xl:flex-row @3xl:items-center @3xl:justify-between">
        <div className="flex items-center gap-3">
          <Logo p={p} />
          <div>
            <p className="font-semibold">{p.identidade.nome}</p>
            {p.conteudo.localizacao.endereco && <p className="text-sm text-(--s-suave)">{p.conteudo.localizacao.endereco}</p>}
          </div>
        </div>
        <Redes p={p} />
      </div>
      <div className="mx-auto mt-8 flex max-w-6xl flex-wrap justify-between gap-3 text-xs text-(--s-suave)">
        <p>
          © {new Date().getFullYear()} {p.identidade.nome}. Todos os direitos reservados.
        </p>
        <p className="flex gap-4">
          <a href="/s/privacidade" className="underline-offset-2 hover:underline">
            Política de privacidade
          </a>
          <span>Site criado com MayaFit</span>
        </p>
      </div>
    </footer>
  );
}

function AvisoVazio({ tipo }: { tipo: TipoSecao }) {
  return (
    <div className="mx-5 my-6 rounded-(--s-raio-sm) border-2 border-dashed border-(--s-borda) p-6 text-center text-sm text-(--s-suave) @3xl:mx-8">
      <strong className="text-(--s-texto)">Seção sem conteúdo — não aparece no site.</strong>
      <br />
      {DICA_VAZIA[tipo]}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------- página
export function PaginaSite({ pagina: p, previa }: { pagina: PaginaPublica; previa?: boolean }) {
  const ativas = secoesAtivas(p.conteudo);
  const whats = whatsDe(p);
  // fundo alternado só entre as seções que realmente aparecem
  const comConteudo = ativas.filter((s) => s.tipo !== "hero" && temConteudo(s.tipo, p)).map((s) => s.tipo);
  return (
    <div
      className={cn("site min-h-full", FONTES_SITE)}
      data-tema={p.tema}
      style={{ ["--s-marca" as string]: p.identidade.cor, ["--s-marca-txt" as string]: corSobre(p.identidade.cor) }}
    >
      <Topo p={p} />
      <main>
        {ativas.map((s) => {
          if (s.tipo === "hero") return <Hero key="hero" p={p} />;
          if (!temConteudo(s.tipo, p)) return previa ? <AvisoVazio key={s.tipo} tipo={s.tipo} /> : null;
          const props = { p, previa, alt: comConteudo.indexOf(s.tipo) % 2 === 1 };
          switch (s.tipo) {
            case "sobre":
              return <Sobre key={s.tipo} {...props} />;
            case "modalidades":
              return <Modalidades key={s.tipo} {...props} />;
            case "planos":
              return <Planos key={s.tipo} {...props} />;
            case "grade":
              return <Grade key={s.tipo} {...props} />;
            case "equipe":
              return <Equipe key={s.tipo} {...props} />;
            case "depoimentos":
              return <Depoimentos key={s.tipo} {...props} />;
            case "galeria":
              return <Galeria key={s.tipo} {...props} />;
            case "faq":
              return <Faq key={s.tipo} {...props} />;
            case "localizacao":
              return <Localizacao key={s.tipo} {...props} />;
            case "contato":
              return <Contato key={s.tipo} {...props} />;
          }
          return null;
        })}
      </main>
      <Rodape p={p} />
      {whats && (
        <a
          href={whats}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Conversar no WhatsApp"
          className="s-whats fixed right-5 bottom-5 z-40 grid size-14 place-items-center rounded-full bg-[#25D366] text-white shadow-xl transition hover:scale-105"
        >
          <IconeWhatsapp className="size-7" />
        </a>
      )}
    </div>
  );
}
