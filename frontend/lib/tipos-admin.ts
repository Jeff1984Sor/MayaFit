// Tipos do admin MayaCorp (/api/admin/*), do cadastro público (/api/public/*) e do "Meu plano" (/api/meu-plano).
// Espelham app/controle/routes_*.py (portados do MayaJus com escritório → estúdio, robôs → extras, notas → alunos).
// Dinheiro chega como texto ("1234.50"), nunca como float.
import type { UsuarioMe } from "./types";

export type Decimal = string;

export type StatusEstudio = "teste" | "ativo" | "suspenso" | "inativo";
export type Ciclo = "mensal" | "anual";
export type Tom = "success" | "warning" | "danger" | "info" | "neutral" | "brand";

export const ROTULO_STATUS: Record<StatusEstudio, string> = {
  teste: "Em teste",
  ativo: "Ativo",
  suspenso: "Suspenso (avisado)",
  inativo: "Inativo (sem acesso)",
};

export const TOM_STATUS: Record<StatusEstudio, Tom> = {
  teste: "info",
  ativo: "success",
  suspenso: "warning",
  inativo: "neutral",
};

/** O /auth/me ganha `estudio` no modo multi (o admin só abre no estúdio "mayacorp"). */
export type UsuarioComEstudio = UsuarioMe & {
  estudio?: { slug?: string; nome?: string; mayacorp?: boolean } | null;
};

export interface Rotulo {
  chave: string;
  rotulo: string;
}

// ---------------------------------------------------------------- planos
export interface PlanoOut {
  id: number;
  nome: string;
  preco_mensal: Decimal;
  preco_anual: Decimal;
  /** limite de usuários com acesso; null = ilimitado */
  usuarios: number | null;
  /** limite de alunos ativos; null = ilimitado */
  alunos_ativos: number | null;
  preco_aluno_excedente: Decimal;
  preco_usuario_adicional: Decimal;
  recursos: string[];
  ativo: boolean;
  ordem: number;
}

export type PlanoIn = Omit<PlanoOut, "id">;

export interface PoliticaIndicacao {
  desconto_por_indicacao: Decimal;
  desconto_maximo: Decimal;
  teto: Decimal;
}

// ---------------------------------------------------------------- estúdios (Cliente no controle)
export interface FichaIn {
  nome: string;
  documento: string | null;
  responsavel: string | null;
  email_financeiro: string | null;
  telefone: string | null;
  plano_id: number | null;
  ciclo: Ciclo;
  inicio_contrato: string | null;
  teste_ate: string | null;
  observacao: string | null;
  indicado_por_id: number | null;
  /** módulos extras liberados (chaves de GET /admin/extras); ausente = não mexe */
  extras?: string[];
}

export interface EstudioNovoIn extends FichaIn {
  slug: string | null;
  admin_nome: string;
  admin_email: string;
  dias_teste: number | null;
  dominios: string[];
}

/** Foto do uso gravada pelo worker no controle (Cliente.uso). */
export interface UsoFoto {
  alunos_ativos?: number;
  usuarios?: number;
  aulas_mes?: number;
  em?: string;
}

export interface Estudio extends FichaIn {
  id: number;
  slug: string;
  status: StatusEstudio;
  status_rotulo: string;
  criado_em: string;
  plano: PlanoOut | null;
  valor: Decimal | null;
  valor_com_desconto: Decimal | null;
  desconto_percentual: Decimal | null;
  indicacoes_ativas: number;
  indicado_por: { id: number; nome: string } | null;
  banco_principal: boolean;
  dominios: { id: number; host: string }[];
  extras: string[];
  uso?: UsoFoto | null;
  forma_pagamento?: "link" | "cartao";
  /** só na criação: link de primeiro acesso enviado ao dono */
  convite?: string;
}

export interface ResumoAdmin {
  clientes: number;
  por_status: Partial<Record<StatusEstudio, number>>;
  mrr: Decimal;
}

/** GET /admin/clientes/{id}/uso e "uso" do Meu plano: alunos ativos e usuários contra os limites do plano. */
export interface UsoEstudio {
  mes: string;
  usuarios: number;
  limite_usuarios: number | null;
  alunos_ativos: number;
  limite_alunos: number | null;
  aulas_mes?: number;
  usuarios_excedentes: number;
  alunos_excedentes: number;
  valor_excedente: Decimal;
}

export interface UsuarioEstudio {
  id: number;
  nome: string;
  email: string | null;
  login: string | null;
  ativo: boolean;
  acesso_sistema?: boolean;
  convite_pendente: boolean;
  perfil: string;
  ultimo_acesso: string | null;
  /** usuário Suporte da MayaCorp (suporte.<slug>) */
  equipe_mayacorp?: boolean;
}

/** Perfis padrão do MayaFit oferecidos ao criar usuário pelo admin. */
export const PERFIS_PADRAO = ["Full", "Secretária", "Professor"] as const;

// ---------------------------------------------------------------- contratos
export interface ModeloContrato {
  id: number;
  nome: string;
  corpo: string;
  ativo: boolean;
  atualizado_em: string;
  variaveis_desconhecidas: string[];
}

export type StatusContrato = "rascunho" | "enviado" | "assinado" | "cancelado";

export interface ContratoEstudio {
  id: number;
  cliente_id: number;
  modelo_id: number | null;
  titulo: string;
  corpo: string;
  status: StatusContrato;
  enviado_para: string[];
  enviado_em: string | null;
  criado_em: string;
  variaveis_vazias?: string[];
  cliente_nome?: string;
}

export const ROTULO_CONTRATO: Record<StatusContrato, [string, Tom]> = {
  rascunho: ["Rascunho", "neutral"],
  enviado: ["Enviado", "info"],
  assinado: ["Assinado", "success"],
  cancelado: ["Cancelado", "danger"],
};

// ---------------------------------------------------------------- solicitações (cadastro pelo site)
export type StatusSolicitacao = "nova" | "aprovada" | "recusada";

export interface Solicitacao {
  id: number;
  nome: string;
  documento: string | null;
  responsavel: string;
  email: string;
  telefone: string | null;
  plano: PlanoOut | null;
  ciclo: Ciclo;
  /** quantos alunos ativos o estúdio tem hoje (informado no formulário) */
  alunos: number | null;
  indicacao: string | null;
  mensagem: string | null;
  status: StatusSolicitacao;
  cliente_id: number | null;
  criado_em: string;
}

export const ROTULO_SOLICITACAO: Record<StatusSolicitacao, [string, Tom]> = {
  nova: ["Nova", "info"],
  aprovada: ["Aprovada", "success"],
  recusada: ["Recusada", "neutral"],
};

export interface CadastroIn {
  nome: string;
  documento: string | null;
  responsavel: string;
  email: string;
  telefone: string;
  plano_id: number | null;
  ciclo: Ciclo;
  alunos: number | null;
  indicacao: string | null;
  mensagem: string | null;
  aceite: boolean;
  /** isca para robôs: pessoas deixam vazio */
  site: string;
}

// ---------------------------------------------------------------- cobrança (Mercado Pago)
export type StatusCobranca = "pendente" | "vencida" | "paga" | "cancelada";

export const TOM_COBRANCA: Record<StatusCobranca, Tom> = {
  pendente: "info",
  vencida: "danger",
  paga: "success",
  cancelada: "neutral",
};

export interface Cobranca {
  id: number;
  cliente_id: number;
  cliente_nome: string;
  tipo: "mensalidade" | "avulsa" | "cartao";
  competencia: string | null;
  descricao: string;
  itens: { descricao: string; valor: Decimal }[];
  valor: Decimal;
  vencimento: string;
  status: StatusCobranca;
  status_rotulo: string;
  link: string | null;
  pago_em: string | null;
  forma_paga: string | null;
  avisos: number[];
  criado_em: string;
}

export const TIPO_COBRANCA: Record<Cobranca["tipo"], string> = {
  mensalidade: "Mensalidade",
  avulsa: "Avulsa",
  cartao: "Cartão (assinatura)",
};

export interface ResumoCobranca {
  em_aberto: Decimal;
  vencido: Decimal;
  recebido_mes: Decimal;
  inadimplentes: number;
}

export interface ConfigCobranca {
  conectado: boolean;
  segredo_definido: boolean;
  conta: string | null;
  dia_vencimento: number;
  gerar_automatico: boolean;
  regua: number[];
  url_notificacao: string | null;
}

export interface PagamentoEstudio {
  forma_pagamento: "link" | "cartao";
  assinatura_id: string | null;
  assinatura_status: string | null;
  link?: string;
}

export const ROTULO_ASSINATURA: Record<string, string> = {
  pending: "aguardando o cadastro do cartão",
  authorized: "ativa",
  paused: "pausada",
  cancelled: "cancelada",
};

export interface MeuPlano {
  nome: string;
  status: StatusEstudio;
  teste_ate: string | null;
  ciclo: Ciclo;
  plano: PlanoOut | null;
  valor: Decimal | null;
  forma_pagamento: "link" | "cartao";
  assinatura_status: string | null;
  pode_alterar: boolean;
  uso: UsoEstudio;
  planos: PlanoOut[];
  recursos: Rotulo[];
  em_aberto: Cobranca[];
  pagas: Cobranca[];
}

// ---------------------------------------------------------------- telas públicas
export interface PrimeiroAcessoInfo {
  /** nome do estúdio (o backend do MayaJus devolvia "escritorio") */
  estudio?: string;
  escritorio?: string;
  email: string | null;
}

/**
 * Rótulos de reserva dos recursos do plano, só para as telas públicas quando a API não manda o rótulo
 * (no admin e no Meu plano os rótulos vêm de GET /admin/recursos e de MeuPlano.recursos).
 */
export const RECURSOS_PADRAO: Record<string, string> = {
  gestao: "Agenda, alunos, contratos e financeiro",
  site: "Site do estúdio",
  crm: "CRM de interessados",
  app_aluno: "App do aluno",
  whatsapp: "Avisos por WhatsApp",
  checkin: "Check-in",
  integracoes: "Integrações (Gympass, TotalPass…)",
  ia: "Assistente com IA",
  nfse: "Nota fiscal de serviço",
  catraca: "Catraca",
};
