// Tipos da integração Wellhub (espelham backend/app/modules/wellhub/schemas.py).

export interface Segredo {
  definido: boolean;
  final: string | null;
}

export type Ambiente = "sandbox" | "producao";
export type ResultadoEvento = "processado" | "cancelado" | "rejeitado" | "descartado" | "erro" | "pendente";
export type NivelAlerta = "danger" | "warning" | "info";

export interface Mapeamento {
  id: number;
  tipo_servico_id: number;
  servico_nome: string;
  product_id: string | null;
  class_id: string | null;
  nome_classe: string | null;
  descricao: string | null;
  ativo: boolean;
  slots_publicados: number;
}

export interface WellhubConfig {
  unidade_id: number;
  unidade_nome: string;
  configurada: boolean;
  ativo: boolean;
  ambiente: Ambiente;
  gym_id: string | null;
  criar_aluno_automatico: boolean;
  validar_checkin_automatico: boolean;
  servico_padrao_id: number | null;
  valor_repasse_checkin: string | null;
  sync_ativo: boolean;
  sync_dias: number;
  sync_ultimo_em: string | null;
  sync_ultimo_resumo: string | null;
  sync_ultimo_ok: boolean | null;
  teste_ultimo_em: string | null;
  teste_ultimo_ok: boolean | null;
  api_key: Segredo;
  webhook_secret: Segredo;
  mapeamentos: Mapeamento[];
}

export interface WellhubTela {
  webhook_caminho: string;
  configuracoes: WellhubConfig[];
  servicos: { id: number; nome: string }[];
}

export type SegredoNome = "api_key" | "webhook_secret";

export interface WellhubConfigIn {
  ativo?: boolean;
  ambiente?: Ambiente;
  gym_id?: string | null;
  criar_aluno_automatico?: boolean;
  validar_checkin_automatico?: boolean;
  servico_padrao_id?: number | null;
  valor_repasse_checkin?: string | null;
  sync_ativo?: boolean;
  sync_dias?: number;
  api_key?: string;
  webhook_secret?: string;
  limpar?: SegredoNome[];
}

export interface SegredoGerado {
  valor: string;
  final: string;
}

export interface TesteOut {
  ok: boolean;
  mensagem: string;
  detalhes: Record<string, unknown> | null;
}

export interface Produto {
  id: string;
  nome: string;
}

export interface MapeamentoIn {
  tipo_servico_id: number;
  product_id: string | null;
  nome_classe?: string | null;
  descricao?: string | null;
  ativo: boolean;
}

export interface ResumoGrade {
  resumo: string;
  previa: boolean;
  classes_criadas: number;
  slots_criados: number;
  slots_atualizados: number;
  slots_removidos: number;
  sem_mudanca: number;
  erros: number;
  mensagens: string[];
}

export interface EventoWellhub {
  id: number;
  recebido_em: string;
  processado_em: string | null;
  tipo: string;
  tipo_rotulo: string;
  unidade_nome: string | null;
  gympass_mascarado: string | null;
  booking_number: string | null;
  slot_id: string | null;
  aluno_id: number | null;
  aluno_nome: string | null;
  resultado: ResultadoEvento;
  erro: string | null;
  tentativas: number;
  origem: string;
  reserva_id: number | null;
  ignorado: boolean;
  pode_reprocessar: boolean;
}

export interface EventoDetalhe extends EventoWellhub {
  payload: Record<string, unknown> | null;
}

export interface ListaEventos {
  total: number;
  pagina: number;
  por_pagina: number;
  itens: EventoWellhub[];
}

export interface ReprocessarOut {
  resultado: ResultadoEvento | "duplicado";
  mensagem: string | null;
  evento: EventoWellhub;
}

export interface Passo {
  id: "credenciais" | "webhook" | "mapeamento" | "grade" | "repasse";
  titulo: string;
  concluido: boolean;
  pendencia: string | null;
}

export interface Alerta {
  nivel: NivelAlerta;
  titulo: string;
  descricao: string;
  acao: "eventos" | "assistente" | "relatorio" | null;
}

export interface PontoSerie {
  dia: string;
  total: number;
  validados: number;
}

export interface Painel {
  unidade_id: number;
  unidade_nome: string;
  configurada: boolean;
  ativo: boolean;
  ambiente: Ambiente;
  mes: string;
  checkins_mes: number;
  checkins_validados_mes: number;
  checkins_pendentes_mes: number;
  variacao_checkins: number | null;
  valor_repasse_checkin: string | null;
  valor_estimado_mes: string;
  reservas_mes: number;
  rejeitadas_mes: number;
  cancelamentos_mes: number;
  eventos_com_erro: number;
  slots_futuros: number;
  passos: Passo[];
  alertas: Alerta[];
  serie: PontoSerie[];
  ultimos_eventos: EventoWellhub[];
}

export interface Relatorio {
  ano: number;
  mes: number;
  total: number;
  validados: number;
  pendentes: number;
  valor_estimado: string;
  validados_mes_anterior: number;
  variacao: number | null;
  alunos_distintos: number;
  por_unidade: { unidade_id: number; unidade_nome: string; total: number; validados: number; valor_unitario: string | null; valor_estimado: string }[];
  por_dia: PontoSerie[];
  por_aluno: { aluno_id: number | null; aluno_nome: string; gympass_id: string | null; total: number; validados: number; ultimo: string }[];
}

export interface AlunoWellhub {
  aluno_id: number;
  nome: string;
  gympass_id: string | null;
}

export interface ValidacaoOut {
  aplicavel: boolean;
  ok: boolean;
  mensagem: string;
  ja_validado: boolean;
}
