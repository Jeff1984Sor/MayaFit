// Tipos do módulo Controle de acesso (espelham backend/app/modules/acesso/schemas.py).

export type Metodo = "facial" | "cpf" | "codigo" | "qr" | "manual";
export type ModoCatraca = "totem" | "agente" | "servidor";
export type DriverCatraca = "controlid" | "henry" | "simulado";

export const ROTULO_METODO: Record<Metodo, string> = {
  facial: "Reconhecimento facial",
  cpf: "CPF + PIN",
  codigo: "Código + PIN",
  qr: "QR do app",
  manual: "Liberação manual",
};

export const ROTULO_MODO: Record<ModoCatraca, string> = {
  totem: "Pelo navegador do totem (rede local)",
  agente: "Pelo agente local (programa na recepção)",
  servidor: "Direto do servidor (VPN/IP público)",
};

export interface ConfigAcesso {
  tolerancia_atraso_dias: number;
  janela_antes_min: number;
  janela_depois_min: number;
  permanencia_livre_min: number;
  planos_livres: number[];
  limiar_similaridade: number;
  margem_ambiguidade: number;
  exigir_prova_vida: boolean;
  exigir_pin: boolean;
  registrar_presenca: boolean;
  termo_biometria: string;
  mensagem_boas_vindas: string | null;
}

export interface Opcao {
  id: number;
  nome: string;
}

export interface OpcoesAcesso {
  unidades: Opcao[];
  planos: Opcao[];
  drivers: { nome: DriverCatraca; rotulo: string; suporta_navegador: boolean }[];
  catracas: Opcao[];
}

export interface PassoHttp {
  metodo: string;
  url: string;
  corpo: Record<string, unknown> | null;
  extrair: string | null;
}

export interface PlanoCatraca {
  driver: string;
  passos: PassoHttp[];
  descricao: string;
}

export interface Acionamento {
  catraca_id: number | null;
  catraca_nome: string | null;
  modo: ModoCatraca | null;
  status: "liberada" | "falhou" | "pendente" | "sem_catraca" | "ok";
  mensagem: string;
  plano: PlanoCatraca | null;
  comando_id: number | null;
}

export interface Catraca {
  id: number;
  nome: string;
  unidade_id: number | null;
  unidade_nome: string | null;
  driver: DriverCatraca;
  modo: ModoCatraca;
  host: string | null;
  porta: number | null;
  usar_https: boolean;
  usuario: string | null;
  senha_definida: boolean;
  senha_final: string | null;
  sentido_entrada: "clockwise" | "anticlockwise" | "both";
  acao_liberacao: "catra" | "door";
  porta_rele: number;
  ativo: boolean;
  ultimo_teste_em: string | null;
  ultimo_teste_ok: boolean | null;
  ultimo_teste_detalhe: string | null;
}

export interface TesteCatraca {
  ok: boolean | null;
  mensagem: string;
  acionamento: Acionamento | null;
}

export interface Dispositivo {
  id: number;
  nome: string;
  tipo: "totem" | "agente";
  unidade_id: number | null;
  unidade_nome: string | null;
  catraca_id: number | null;
  catraca_nome: string | null;
  token_final: string | null;
  ativo: boolean;
  revogado_em: string | null;
  ultimo_contato: string | null;
  online: boolean;
  criado_em: string;
  criado_por_nome: string | null;
  token?: string;
}

export interface Consentimento {
  id: number;
  coletado_em: string;
  coletado_por_nome: string;
  canal: string;
  hash_termo: string;
  revogado_em: string | null;
  revogado_por_nome: string | null;
  motivo_revogacao: string | null;
}

export interface DescritorInfo {
  id: number;
  criado_em: string;
  origem: string;
  qualidade: number | null;
  modelo: string;
  dimensao: number;
  criado_por_nome: string | null;
}

export interface AlunoAcesso {
  id: number;
  nome: string;
  cpf: string | null;
  codigo: number | null;
  ativo: boolean;
  foto_url: string | null;
  consentimento: Consentimento | null;
  descritores: number;
  pin_definido: boolean;
}

export interface ListaAlunosAcesso {
  itens: AlunoAcesso[];
  total: number;
  pagina: number;
  por_pagina: number;
  com_biometria: number;
  sem_biometria: number;
}

export interface Registro {
  id: number;
  em: string;
  aluno_id: number | null;
  aluno_nome: string | null;
  permitido: boolean;
  codigo: string;
  motivo: string;
  metodo: Metodo;
  sentido: "entrada" | "saida";
  dispositivo_nome: string | null;
  usuario_nome: string | null;
  aula_descricao: string | null;
  presenca_registrada: boolean;
  similaridade: number | null;
  catraca_status: string | null;
  catraca_detalhe: string | null;
}

export interface AlunoAcessoDetalhe extends AlunoAcesso {
  lista_descritores: DescritorInfo[];
  historico_consentimentos: Consentimento[];
  termo_atual: string;
  ultimos_acessos: Registro[];
}

export interface ListaRegistros {
  itens: Registro[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface Presente {
  registro_id: number;
  aluno_id: number | null;
  nome: string;
  primeiro_nome: string;
  foto_url: string | null;
  entrou_em: string;
  previsto_sair: string | null;
  aula: string | null;
  metodo: Metodo;
  aniversario: boolean;
}

export interface Equipamento {
  id: number;
  nome: string;
  tipo: "totem" | "agente" | "catraca";
  online: boolean | null;
  detalhe: string | null;
}

export interface ProximaAula {
  sessao_id: number;
  servico: string;
  inicio: string;
  fim: string;
  reservas: number;
  chegaram: number;
}

export interface Painel {
  agora: string;
  presentes: Presente[];
  entradas_hoje: number;
  negados_hoje: number;
  alunos_hoje: number;
  por_metodo: Partial<Record<Metodo, number>>;
  ultimos: Registro[];
  equipamentos: Equipamento[];
  proximas_aulas: ProximaAula[];
}

export interface Relatorio {
  de: string;
  ate: string;
  total: number;
  permitidos: number;
  negados: number;
  alunos_unicos: number;
  por_dia: { dia: string; permitidos: number; negados: number }[];
  por_hora: { hora: number; total: number }[];
  por_metodo: { metodo: Metodo; total: number }[];
  motivos_negacao: { codigo: string; rotulo: string; total: number }[];
  mais_frequentes: { aluno_id: number; nome: string; dias: number }[];
}

export interface Decisao {
  permitido: boolean;
  codigo: string;
  motivo: string;
  avisos: string[];
  aula: string | null;
  aniversario: boolean;
}

// ------------------------------------------------------------------------------------------------ totem
export interface AulaCheckin {
  servico: string;
  inicio: string;
  fim: string;
  profissional: string | null;
}

export interface Checkin {
  permitido: boolean;
  codigo: string;
  motivo: string;
  titulo: string;
  primeiro_nome: string | null;
  aniversario: boolean;
  avisos: string[];
  aula: AulaCheckin | null;
  registro_id: number | null;
  presenca_registrada: boolean;
  acionamento: Acionamento | null;
}

export interface TotemMe {
  dispositivo: string;
  unidade: string | null;
  estudio: string;
  cor: string | null;
  exigir_prova_vida: boolean;
  exigir_pin: boolean;
  tem_catraca: boolean;
  modo_catraca: ModoCatraca | null;
  biometria_cadastrada: number;
  modelo_facial: string;
}

export interface ProvaVida {
  piscou: boolean;
  real: number | null;
  live: number | null;
}
