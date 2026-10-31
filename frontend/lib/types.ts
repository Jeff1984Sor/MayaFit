// Tipos da API do core (espelham backend/app/core/schemas.py). Módulos de negócio acrescentam os seus em lib/<modulo>.ts.

export interface Pagina<T> {
  itens: T[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface Mensagem {
  mensagem: string;
}

export interface UsuarioMe {
  id: number;
  nome: string;
  email: string;
  login: string | null;
  telefone: string | null;
  foto_url: string | null;
  preferencias: Record<string, unknown> & { menu_recolhido?: string[]; tour_visto?: boolean };
  perfil_acesso_id: number | null;
  perfil_acesso_nome: string | null;
  administrador: boolean;
  somente_proprias_aulas: boolean;
  permissoes: string[];
  /** Estúdio da sessão (modo multi-estúdio). Ausente/null no modo de um banco só. */
  estudio?: EstudioMe | null;
}

export type StatusEstudio = "teste" | "ativo" | "suspenso" | "inativo";

export interface EstudioMe {
  slug: string;
  nome: string;
  /** Admin MayaFit: o menu mostra só a seção Admin MayaFit + Configurações. */
  mayacorp: boolean;
  status: StatusEstudio;
  /** Fim do período de teste (YYYY-MM-DD). */
  teste_ate: string | null;
  /** Recursos do plano + extras liberados (chaves de app/controle/planos.py). */
  recursos: string[] | null;
}

export type EstudioInfo = EstudioMe;

export interface IdentidadePublica {
  nome_exibicao: string;
  logo_url: string | null;
  cor_destaque: string | null;
}

export interface IdentidadeOut extends IdentidadePublica {
  assinatura_email: string | null;
}

export interface UsuarioOut {
  id: number;
  nome: string;
  email: string;
  login: string | null;
  telefone: string | null;
  foto_url: string | null;
  ativo: boolean;
  acesso_sistema: boolean;
  convite_pendente: boolean;
  ultimo_acesso: string | null;
  online: boolean;
  perfil_acesso_id: number | null;
  perfil_acesso_nome: string | null;
  perfil_acesso_cor: string | null;
}

export interface PerfilAcessoOut {
  id: number;
  nome: string;
  descricao: string | null;
  cor: string | null;
  administrador: boolean;
  sistema: boolean;
  somente_proprias_aulas: boolean;
  permissoes: string[];
  qtd_usuarios: number;
}

export interface PerfilAcessoIn {
  nome: string;
  descricao: string | null;
  cor: string | null;
  administrador: boolean;
  somente_proprias_aulas: boolean;
  permissoes: string[];
}

export interface CatalogoPermissoes {
  grupos: { grupo: string; recursos: { id: string; nome: string; acoes: string[] }[] }[];
  acoes: Record<string, string>;
}

export interface ConfigEmailOut {
  remetente_nome: string;
  remetente_email: string;
  smtp_host: string | null;
  smtp_porta: number;
  smtp_usuario: string | null;
  smtp_senha_definida: boolean;
  copia_padrao: string[];
}

export interface ConfigIAOut {
  ativo: boolean;
  provedor: "openai" | "gemini";
  modelo: string | null;
  chave_definida: boolean;
  chave_final: string | null;
  provedores: Record<string, string>;
}

export interface AuditoriaOut {
  id: number;
  usuario_nome: string | null;
  acao: string;
  entidade: string;
  entidade_id: string | null;
  descricao: string | null;
  antes_json: Record<string, unknown> | null;
  depois_json: Record<string, unknown> | null;
  ip: string | null;
  criado_em: string;
}
