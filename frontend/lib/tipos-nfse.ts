// Tipos da NFS-e (espelham backend/app/modules/nfse/schemas.py). Dinheiro chega como texto ("300.00").

export type StatusNota = "pendente" | "processando" | "emitida" | "validada" | "rejeitada" | "falha" | "cancelada";
export type ProvedorNfse = "nacional" | "sao_paulo";
export type ModoNfse = "simulado" | "homologacao" | "producao";
export type RegimeNfse = "mei" | "simples" | "presumido" | "real";
export type Nivel = "erro" | "aviso" | "info";

export interface Pendencia {
  nivel: Nivel;
  campo?: string;
  mensagem: string;
  acao: string;
  link?: string | null;
}

export interface CertificadoInfo {
  configurado: boolean;
  titular: string | null;
  cnpj: string | null;
  emissor: string | null;
  valido_de: string | null;
  valido_ate: string | null;
  situacao: "ausente" | "valido" | "vencendo" | "vencido";
  dias: number | null;
  mensagem: string;
  cnpj_confere: boolean | null;
}

export interface ConfigNfseIn {
  ativo: boolean;
  provedor: ProvedorNfse;
  modo: ModoNfse;
  cnpj: string | null;
  razao_social: string | null;
  inscricao_municipal: string | null;
  codigo_municipio: string | null;
  municipio_nome: string | null;
  uf: string | null;
  email: string | null;
  telefone: string | null;
  regime: RegimeNfse;
  item_lista_servico: string;
  codigo_servico_municipal: string | null;
  nbs: string | null;
  aliquota_iss: string;
  iss_retido: boolean;
  informar_aliquota: boolean;
  percentual_tributos_sn: string | null;
  discriminacao_modelo: string | null;
  serie: string;
  proximo_numero: number;
  parametros_extras: Record<string, string> | null;
  emissao_automatica: boolean;
  automatica_desde: string | null;
  enviar_email_aluno: boolean;
}

export interface ConfigNfse extends ConfigNfseIn {
  codigo_tributacao_nacional: string;
  certificado: CertificadoInfo;
  emissao_real_liberada: boolean;
  ambiente_servidor: "dev" | "hml" | "prod";
  pendencias: Pendencia[];
  provedor_rotulo: string;
}

export interface OpcoesNfse {
  servicos: { item: string; tributacao_nacional: string; descricao: string; indicado_para: string }[];
  variaveis: Record<string, string>;
  regimes: Record<RegimeNfse, string>;
  discriminacao_padrao: string;
  motivos_cancelamento: Record<string, string>;
  provedores: Record<ProvedorNfse, string>;
}

export interface MunicipioInfo {
  codigo_municipio: string | null;
  municipio_nome: string | null;
  uf: string | null;
  provedor: ProvedorNfse;
  suportado: boolean;
  mensagem: string;
}

export interface ErroNota {
  mensagem: string;
  acao: string;
  codigo: string | null;
  campo: string | null;
  tecnico: string | null;
  nivel: "erro" | "aviso";
}

export interface NotaResumo {
  id: number;
  status: StatusNota;
  origem: "avulsa" | "recebimento" | "automatica" | "demo";
  provedor: ProvedorNfse;
  modo: ModoNfse;
  serie: string;
  numero_dps: number;
  numero_nfse: string | null;
  tomador_nome: string;
  tomador_documento: string | null;
  competencia: string;
  valor_servico: string;
  valor_iss: string;
  emitida_em: string | null;
  criado_em: string;
  conta_receber_id: number | null;
  aluno_id: number | null;
  tentativas: number;
  erro_principal: string | null;
  tem_pdf: boolean;
  link_oficial: string | null;
}

export interface EventoNota {
  id: number;
  tipo: string;
  descricao: string;
  criado_em: string;
}

export interface NotaDetalhe extends NotaResumo {
  chave_emissao: string;
  id_dps: string | null;
  chave_acesso: string | null;
  codigo_verificacao: string | null;
  tomador_email: string | null;
  tomador_tipo: "aluno" | "pessoa" | "empresa";
  discriminacao: string;
  item_lista_servico: string;
  codigo_tributacao_nacional: string;
  codigo_servico_municipal: string | null;
  aliquota: string;
  deducoes: string;
  iss_retido: boolean;
  regime: RegimeNfse;
  erros: ErroNota[];
  alertas: ErroNota[];
  tem_xml_enviado: boolean;
  tem_xml_retorno: boolean;
  cancelada_em: string | null;
  motivo_cancelamento: string | null;
  email_enviado_em: string | null;
  proxima_tentativa_em: string | null;
  eventos: EventoNota[];
  pode_cancelar: boolean;
  pode_reprocessar: boolean;
}

export interface ListaNotas {
  itens: NotaResumo[];
  total: number;
  pagina: number;
  por_pagina: number;
  contagens: Partial<Record<StatusNota, number>>;
}

export interface RecebimentoNfse {
  id: number;
  aluno_id: number;
  aluno_nome: string;
  aluno_cpf: string | null;
  aluno_email: string | null;
  descricao: string | null;
  valor: string;
  vencimento: string;
  pagamento: string | null;
  competencia: string | null;
  nota_id: number | null;
  nota_status: StatusNota | null;
  nota_numero: string | null;
  problema: string | null;
}

export interface LoteNfse {
  lote: string;
  criadas: number;
  ja_existiam: number;
  ignoradas: { id: number; motivo: string }[];
  processadas_agora: number;
  notas: NotaResumo[];
}

export interface AchadoRaioX {
  nivel: Nivel;
  titulo: string;
  mensagem: string;
  acao: string;
  link: string | null;
  itens: number[];
}

export interface RaioX {
  score: number;
  frase: string;
  pode_emitir: boolean;
  achados: AchadoRaioX[];
  quantidade: number;
  valor_total: string;
  iss_estimado: string;
  iss_no_das: boolean;
  aliquota: string;
  modo: ModoNfse;
  provedor: ProvedorNfse;
  previa: { tomador: string; documento: string; valor: string; competencia: string; discriminacao: string }[];
}

export interface PainelNfse {
  mes: string;
  notas_mes: number;
  valor_mes: string;
  iss_estimado_mes: string;
  iss_no_das: boolean;
  ticket_medio: string;
  recebimentos_sem_nota: number;
  valor_sem_nota: string;
  por_status: Partial<Record<StatusNota, number>>;
  serie: { mes: string; valor: string; iss: string; quantidade: number }[];
  pendencias: Pendencia[];
  certificado: CertificadoInfo;
  modo: ModoNfse;
  provedor: ProvedorNfse;
  ativo: boolean;
  emissao_automatica: boolean;
  configurado: boolean;
}

export interface TomadorBusca {
  id: number;
  nome: string;
  cpf_mascarado: string | null;
  tem_cpf: boolean;
  email: string | null;
}

export interface NotaAvulsaIn {
  tomador: {
    tipo: "aluno" | "pessoa" | "empresa";
    aluno_id?: number | null;
    documento?: string | null;
    nome?: string | null;
    email?: string | null;
  };
  valor: string;
  competencia?: string | null;
  descricao?: string | null;
  discriminacao?: string | null;
}
