/** Tipos do módulo Site do estúdio (espelham `backend/app/modules/site/schemas.py`). */

export type Tema = "aurora" | "zen" | "energia";
export type TipoSecao =
  | "hero"
  | "sobre"
  | "modalidades"
  | "planos"
  | "grade"
  | "equipe"
  | "depoimentos"
  | "galeria"
  | "faq"
  | "localizacao"
  | "contato";

export interface Secao {
  tipo: TipoSecao;
  ativa: boolean;
}

export interface ItemModalidade {
  tipo_servico_id: number;
  mostrar: boolean;
  descricao: string;
  foto: string | null;
}

export interface ItemEquipe {
  profissional_id: number;
  mostrar: boolean;
  cargo: string;
  bio: string;
  foto: string | null;
}

export interface ConteudoSite {
  secoes: Secao[];
  hero: { titulo: string; subtitulo: string; foto: string | null; botao_texto: string };
  sobre: { titulo: string; texto: string; foto: string | null; destaques: string[] };
  modalidades: { titulo: string; subtitulo: string; itens: ItemModalidade[] };
  planos: { titulo: string; subtitulo: string; mostrar_precos: boolean; ocultos: number[]; destaque_id: number | null; observacao: string };
  grade: { titulo: string; subtitulo: string; mostrar_professor: boolean };
  equipe: { titulo: string; subtitulo: string; itens: ItemEquipe[] };
  depoimentos: { titulo: string; itens: { nome: string; texto: string; detalhe: string }[] };
  galeria: { titulo: string; fotos: { foto: string | null; legenda: string }[] };
  faq: { titulo: string; itens: { pergunta: string; resposta: string }[] };
  localizacao: { titulo: string; endereco: string; mapa: string; horario_texto: string };
  contato: {
    titulo: string;
    subtitulo: string;
    whatsapp: string;
    telefone: string;
    email: string;
    instagram: string;
    facebook: string;
    tiktok: string;
    youtube: string;
    mensagem_whatsapp: string;
  };
  seo: { titulo: string; descricao: string; cidade: string; estado: string; categoria: "pilates" | "academia" | "funcional" | "estudio" };
  privacidade: { responsavel: string; documento: string; email: string };
}

export interface PlanoDado {
  id: number;
  nome: string;
  modalidade: string | null;
  valor: string | null;
  aulas_por_semana: number;
  duracao_meses: number;
  avulso: boolean;
}

export interface HorarioDado {
  dia_semana: number;
  hora_inicio: string;
  hora_fim: string;
  modalidade: string;
  professor: string | null;
}

export interface DadosEstudio {
  modalidades: { id: number; nome: string }[];
  planos: PlanoDado[];
  profissionais: { id: number; nome: string }[];
  grade: HorarioDado[];
}

export interface IdentidadeSite {
  nome: string;
  cor: string;
  logo_url: string | null;
}

export interface PaginaPublica {
  tema: Tema;
  identidade: IdentidadeSite;
  conteudo: ConteudoSite;
  dados: DadosEstudio;
  publicado_em: string | null;
  mapa_embed: string | null;
  mapa_link: string | null;
}

export interface EditorSite {
  tema: Tema;
  conteudo: ConteudoSite;
  publicado: boolean;
  publicado_em: string | null;
  alteracoes_pendentes: boolean;
  identidade: IdentidadeSite;
  dados: DadosEstudio;
  endereco: { principal: string | null; dominios: string[] };
  contatos_nao_lidos: number;
}

export interface ContatoSite {
  id: number;
  nome: string;
  telefone: string | null;
  email: string | null;
  interesse: string | null;
  mensagem: string | null;
  quer_aula_experimental: boolean;
  enviado_crm: boolean;
  lead_id: number | null;
  lido: boolean;
  criado_em: string;
}

export interface ListaContatosSite {
  itens: ContatoSite[];
  total: number;
  nao_lidos: number;
}
