/** Tipos do CRM de vendas (espelham backend/app/modules/crm/schemas.py). */

export type TipoEtapa = "ABERTA" | "GANHO" | "PERDIDO";
export type MarcoEtapa = "AULA_AGENDADA" | "AULA_REALIZADA" | "PROPOSTA";
export type SituacaoLead = "ABERTO" | "GANHO" | "PERDIDO";
export type OrigemLead = "site" | "instagram" | "indicacao" | "wellhub" | "totalpass" | "passante" | "whatsapp" | "outros";
export type TipoInteracao = "LIGACAO" | "WHATSAPP" | "VISITA" | "EMAIL" | "NOTA" | "SISTEMA";
export type StatusAula = "AGENDADA" | "REALIZADA" | "FALTOU" | "CANCELADA";
export type Temperatura = "quente" | "morno" | "frio" | "encerrado";
export type SituacaoTarefa = "concluida" | "atrasada" | "hoje" | "futura";

export interface UsuarioMini {
  id: number;
  nome: string;
}

export interface Etapa {
  id: number;
  nome: string;
  ordem: number;
  cor: string;
  tipo: TipoEtapa;
  marco: MarcoEtapa | null;
  dias_alerta: number;
  leads: number;
}

export interface Motivo {
  id: number;
  nome: string;
  ativo: boolean;
  usos: number;
}

export interface LeadCartao {
  id: number;
  nome: string;
  telefone: string | null;
  telefone_formatado: string | null;
  email: string | null;
  origem: OrigemLead;
  interesse: string | null;
  responsavel: UsuarioMini | null;
  valor_estimado: string | null;
  tags: string[];
  etapa_id: number;
  situacao: SituacaoLead;
  dias_na_etapa: number;
  parado: boolean;
  temperatura: Temperatura;
  aula_experimental_em: string | null;
  aula_experimental_status: StatusAula | null;
  tarefas_pendentes: number;
  tarefa_atrasada: boolean;
  whatsapp_url: string | null;
  criado_em: string;
  ultima_interacao_em: string | null;
  aluno_id: number | null;
}

export interface ColunaFunil {
  etapa: Etapa;
  leads: LeadCartao[];
  total: number;
  valor_total: string;
}

export interface Funil {
  colunas: ColunaFunil[];
}

export interface ListaLeads {
  itens: LeadCartao[];
  total: number;
  pagina: number;
  por_pagina: number;
  contagens: { abertos: number; ganhos: number; perdidos: number; todos: number };
}

export interface Interacao {
  id: number;
  tipo: TipoInteracao;
  descricao: string;
  usuario: UsuarioMini | null;
  ocorrido_em: string;
}

export interface Tarefa {
  id: number;
  titulo: string;
  descricao: string | null;
  vence_em: string;
  responsavel: UsuarioMini | null;
  concluida: boolean;
  concluida_em: string | null;
  situacao: SituacaoTarefa;
  automatica: boolean;
  lead_id: number | null;
  lead_nome: string | null;
  lead_telefone: string | null;
  whatsapp_url: string | null;
}

export interface ListaTarefas {
  itens: Tarefa[];
  contagens: { atrasadas: number; hoje: number; futuras: number; concluidas_hoje: number };
}

export interface MensagemPronta {
  titulo: string;
  texto: string;
  url: string | null;
}

export interface LeadFicha extends LeadCartao {
  indicado_por: string | null;
  observacoes: string | null;
  etapa_nome: string;
  motivo_perda_id: number | null;
  motivo_perda: string | null;
  motivo_perda_detalhe: string | null;
  perdido_em: string | null;
  ganho_em: string | null;
  aula_experimental_profissional_id: number | null;
  aula_experimental_profissional: string | null;
  aula_experimental_unidade_id: number | null;
  aula_experimental_obs: string | null;
  sugestao: string | null;
  mensagens: MensagemPronta[];
  interacoes: Interacao[];
  tarefas: Tarefa[];
  movimentos: { de: string | null; para: string | null; usuario: string | null; em: string }[];
  aluno_nome: string | null;
}

export interface OpcaoSimples {
  id: number;
  nome: string;
}

export interface OpcoesCrm {
  etapas: Etapa[];
  motivos: Motivo[];
  origens: { valor: OrigemLead; rotulo: string }[];
  usuarios: UsuarioMini[];
  profissionais: OpcaoSimples[];
  unidades: OpcaoSimples[];
  tags: string[];
  estudio: string;
}

export interface ResumoCrm {
  abertos: number;
  novos_7_dias: number;
  valor_em_negociacao: string;
  tarefas_hoje: number;
  tarefas_atrasadas: number;
  parados: number;
  aulas_experimentais_hoje: number;
  conversoes_30_dias: number;
  taxa_conversao_30_dias: number;
  destaque: string | null;
}

export interface PreparoConversao {
  unidades: OpcaoSimples[];
  parecidos: { id: number; nome: string; motivo: string }[];
  pode_criar_aluno: boolean;
}

export interface RelatorioCrm {
  de: string;
  ate: string;
  total_leads: number;
  ganhos: number;
  perdidos: number;
  abertos: number;
  taxa_conversao: number;
  tempo_medio_dias: number | null;
  valor_ganho: string;
  funil: { etapa_id: number; etapa: string; cor: string; tipo: TipoEtapa; quantidade: number; pct_total: number; pct_anterior: number }[];
  por_origem: {
    origem: OrigemLead;
    rotulo: string;
    total: number;
    ganhos: number;
    perdidos: number;
    abertos: number;
    taxa_conversao: number;
    tempo_medio_dias: number | null;
  }[];
  perdidos_por_motivo: { motivo_id: number | null; motivo: string; quantidade: number; pct: number }[];
  melhor_origem: string | null;
  gargalo: string | null;
}

export interface LeadIn {
  nome?: string | null;
  telefone?: string | null;
  email?: string | null;
  origem?: OrigemLead | null;
  indicado_por?: string | null;
  interesse?: string | null;
  responsavel_id?: number | null;
  valor_estimado?: string | null;
  observacoes?: string | null;
  tags?: string[];
  etapa_id?: number | null;
}
