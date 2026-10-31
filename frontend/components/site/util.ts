/** Funções puras do site (servidor e cliente): URLs, cores, formatação e a montagem da prévia. */
import type { ConteudoSite, DadosEstudio, PaginaPublica, Secao, TipoSecao } from "@/lib/tipos-site";

export const NOMES_SECAO: Record<TipoSecao, string> = {
  hero: "Capa (hero)",
  sobre: "Sobre",
  modalidades: "Modalidades",
  planos: "Planos e preços",
  grade: "Grade de horários",
  equipe: "Equipe",
  depoimentos: "Depoimentos",
  galeria: "Galeria de fotos",
  faq: "Perguntas frequentes",
  localizacao: "Localização",
  contato: "Contato",
};

/** Âncora usada no menu do site. */
export const ANCORA: Record<TipoSecao, string> = {
  hero: "inicio",
  sobre: "sobre",
  modalidades: "modalidades",
  planos: "planos",
  grade: "horarios",
  equipe: "equipe",
  depoimentos: "depoimentos",
  galeria: "galeria",
  faq: "duvidas",
  localizacao: "onde-estamos",
  contato: "contato",
};

export const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
export const DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

/** Foto do site (`site/<hex>.<ext>`) → caminho servido pelo Next (que repassa o host do estúdio à API). */
export function urlFoto(foto: string | null | undefined): string | null {
  if (!foto) return null;
  const m = /^site\/([0-9a-f]{32}\.(?:png|jpe?g|webp))$/.exec(foto);
  return m ? `/s/img/${m[1]}` : null;
}

/** Logo da identidade (a API devolve `/public/logo?v=…`) → rota do site. */
export function urlLogo(logo: string | null | undefined): string | null {
  if (!logo) return null;
  const v = /[?&]v=(\d+)/.exec(logo)?.[1];
  return `/s/logo${v ? `?v=${v}` : ""}`;
}

export function hora(h: string) {
  return h.slice(0, 5).replace(/^0/, "");
}

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
export function preco(v: string | null) {
  return v == null ? null : brl.format(Number(v));
}

export function soDigitos(v: string | null | undefined) {
  return (v ?? "").replace(/\D/g, "");
}

export function linkWhatsapp(numero: string, mensagem?: string) {
  let d = soDigitos(numero);
  if (d.length === 10 || d.length === 11) d = `55${d}`;
  if (d.length < 12 || d.length > 13) return null;
  return `https://wa.me/${d}${mensagem ? `?text=${encodeURIComponent(mensagem)}` : ""}`;
}

const REDES: Record<string, string> = {
  instagram: "https://instagram.com/",
  facebook: "https://facebook.com/",
  tiktok: "https://www.tiktok.com/@",
  youtube: "https://youtube.com/@",
};

export function linkRede(rede: keyof typeof REDES, valor: string) {
  const v = valor.trim();
  if (!v) return null;
  if (v.startsWith("https://")) return v;
  if (!/^@?[A-Za-z0-9_.-]{1,60}$/.test(v)) return null;
  return REDES[rede] + v.replace(/^@/, "");
}

/** Cor de texto legível sobre a cor da marca. */
export function corSobre(hex: string) {
  const m = /^#?([0-9a-f]{6})/i.exec(hex);
  if (!m) return "#ffffff";
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 0.45 ? "#0f1729" : "#ffffff";
}

export function iniciais(nome: string) {
  return nome
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function secoesAtivas(c: ConteudoSite): Secao[] {
  return c.secoes.filter((s) => s.ativa);
}

/** Mesmo filtro que a API aplica na página pública (`servico.dados_do_estudio(publico=True)`), para a prévia do editor
 * mostrar exatamente o que o visitante verá. */
export function filtrarParaPublico(c: ConteudoSite, d: DadosEstudio): DadosEstudio {
  const escondidas = new Set(c.modalidades.itens.filter((i) => !i.mostrar).map((i) => i.tipo_servico_id));
  const modalidades = d.modalidades.filter((m) => !escondidas.has(m.id));
  const nomesVisiveis = new Set(modalidades.map((m) => m.nome));
  const ocultos = new Set(c.planos.ocultos);
  const planos = d.planos
    .filter((p) => !ocultos.has(p.id) && (p.modalidade == null || nomesVisiveis.has(p.modalidade)))
    .map((p) => ({ ...p, valor: c.planos.mostrar_precos ? p.valor : null }));
  const marcados = new Set(c.equipe.itens.filter((i) => i.mostrar).map((i) => i.profissional_id));
  const profissionais = d.profissionais.filter((p) => marcados.has(p.id));
  const primeiros = new Map(profissionais.map((p) => [p.nome.split(/\s+/)[0], true]));
  const grade = d.grade
    .filter((h) => nomesVisiveis.has(h.modalidade))
    .map((h) => ({ ...h, professor: c.grade.mostrar_professor && h.professor && primeiros.has(h.professor) ? h.professor : null }));
  return { modalidades, planos, profissionais, grade };
}

/** Mapa para a prévia (a API faz o mesmo na página pública; ver `regras.mapa_da_pagina`). */
export function mapaPrevia(valor: string, endereco: string): { embed: string | null; link: string | null } {
  const end = endereco.trim();
  const porEndereco = end ? `https://www.google.com/maps?q=${encodeURIComponent(end)}&output=embed` : null;
  const busca = end ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(end)}` : null;
  const src = /<iframe[^>]*\ssrc=["']([^"']+)["']/i.exec(valor)?.[1] ?? valor.trim();
  let embed: string | null = null;
  let link: string | null = null;
  try {
    const u = new URL(src);
    const h = u.hostname.toLowerCase();
    const google = u.protocol === "https:" && ["google.com", "google.com.br", "maps.app.goo.gl", "goo.gl"].some((d) => h === d || h.endsWith(`.${d}`));
    if (google && (u.pathname.startsWith("/maps/embed") || u.search.includes("output=embed"))) embed = src;
    else if (google) link = src;
  } catch {
    /* vazio ou inválido */
  }
  return { embed: embed ?? porEndereco, link: link ?? busca };
}

/** Página da prévia do editor, a partir do rascunho e dos cadastros (sem ida ao servidor: atualiza a cada tecla). */
export function paginaDaPrevia(e: {
  tema: PaginaPublica["tema"];
  conteudo: ConteudoSite;
  dados: DadosEstudio;
  identidade: PaginaPublica["identidade"];
}): PaginaPublica {
  const mapa = mapaPrevia(e.conteudo.localizacao.mapa, e.conteudo.localizacao.endereco);
  return {
    tema: e.tema,
    identidade: e.identidade,
    conteudo: e.conteudo,
    dados: filtrarParaPublico(e.conteudo, e.dados),
    publicado_em: null,
    mapa_embed: mapa.embed,
    mapa_link: mapa.link,
  };
}
