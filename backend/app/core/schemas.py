from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

LOGIN_RE = r"^[a-z0-9._-]{3,60}$"


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Pagina[T](Schema):
    itens: list[T]
    total: int
    pagina: int
    por_pagina: int


class Mensagem(Schema):
    mensagem: str


# ---------- Auth ----------
class LoginIn(BaseModel):
    identificador: str = Field(min_length=1, max_length=200, description="E-mail ou nome de usuário")
    senha: str = Field(min_length=1, max_length=256)


class RefreshIn(BaseModel):
    refresh_token: str


class ForgotIn(BaseModel):
    identificador: str = Field(min_length=1, max_length=200, description="E-mail ou nome de usuário")


class ResetIn(BaseModel):
    token: str
    senha: str = Field(max_length=256)


class ResetCodigoIn(BaseModel):
    identificador: str = Field(min_length=1, max_length=200)
    codigo: str = Field(min_length=4, max_length=10)
    senha: str = Field(max_length=256)


class TrocarSenhaIn(BaseModel):
    senha_atual: str = Field(max_length=256)
    nova_senha: str = Field(max_length=256)


class MePatch(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=150)
    telefone: str | None = Field(default=None, max_length=20)


class PrimeiroAcessoIn(BaseModel):
    """Link de boas-vindas de um estúdio novo: o dono cria o usuário master (login + senha)."""

    token: str
    nome: str = Field(min_length=3, max_length=150)
    email: EmailStr
    login: str = Field(pattern=LOGIN_RE, description="Como a pessoa vai entrar (não é o e-mail)")
    senha: str = Field(max_length=256)


class PrimeiroAcessoInfo(BaseModel):
    estudio: str
    email: str | None = None


class EstudioInfo(BaseModel):
    """Estúdio do usuário logado (um banco por estúdio). `recursos` = do plano + extras liberados."""

    slug: str
    nome: str
    mayacorp: bool = False
    status: str
    teste_ate: date | None = None
    recursos: list[str] = []


class UsuarioMe(Schema):
    id: int
    nome: str
    email: str
    login: str | None = None
    telefone: str | None = None
    foto_url: str | None = None  # buscar com o token (fetch -> blob)
    preferencias: dict[str, Any] = {}
    perfil_acesso_id: int | None = None
    perfil_acesso_nome: str | None = None
    administrador: bool = False
    somente_proprias_aulas: bool = False
    permissoes: list[str] = []
    estudio: EstudioInfo | None = None  # None com um banco só


class TokenOut(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    usuario: UsuarioMe


# ---------- Identidade ----------
class IdentidadePublica(Schema):
    nome_exibicao: str
    logo_url: str | None = None
    cor_destaque: str | None = None


class IdentidadeOut(Schema):
    nome_exibicao: str
    logo_url: str | None = None
    cor_destaque: str | None = None
    assinatura_email: str | None = None


class IdentidadeIn(BaseModel):
    nome_exibicao: str = Field(min_length=2, max_length=200)
    cor_destaque: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    assinatura_email: str | None = None


# ---------- Usuários ----------
class UsuarioOut(Schema):
    id: int
    nome: str
    email: str
    login: str | None = None
    telefone: str | None = None
    foto_url: str | None = None
    ativo: bool
    acesso_sistema: bool = True
    convite_pendente: bool
    ultimo_acesso: datetime | None
    online: bool = False
    perfil_acesso_id: int | None = None
    perfil_acesso_nome: str | None = None
    perfil_acesso_cor: str | None = None


class UsuarioIn(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr
    login: str | None = Field(default=None, pattern=LOGIN_RE)
    telefone: str | None = Field(default=None, max_length=20)
    perfil_acesso_id: int | None = None
    senha: str | None = Field(default=None, max_length=256)  # opcional: já define a senha (sem e-mail de convite)
    acesso_sistema: bool = True  # False = profissional sem login (não recebe convite)

    @model_validator(mode="after")
    def _login_obrigatorio_com_acesso(self):
        if self.acesso_sistema and not self.login:
            raise ValueError("Informe o login (ninguém entra com e-mail).")
        return self


class UsuarioPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    login: str | None = Field(default=None, pattern=LOGIN_RE)
    telefone: str | None = Field(default=None, max_length=20)
    ativo: bool | None = None
    acesso_sistema: bool | None = None
    perfil_acesso_id: int | None = None


class DefinirSenhaIn(BaseModel):
    senha: str = Field(max_length=256)


# ---------- Perfis de acesso ----------
class PerfilAcessoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    descricao: str | None = Field(default=None, max_length=300)
    cor: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    administrador: bool = False
    somente_proprias_aulas: bool = False
    permissoes: list[str] = []


class PerfilAcessoOut(Schema):
    id: int
    nome: str
    descricao: str | None
    cor: str | None
    administrador: bool
    sistema: bool
    somente_proprias_aulas: bool
    permissoes: list[str]
    qtd_usuarios: int = 0


# ---------- E-mail ----------
class ConfigEmailOut(Schema):
    remetente_nome: str
    remetente_email: str
    smtp_host: str | None
    smtp_porta: int
    smtp_usuario: str | None
    smtp_senha_definida: bool = False
    copia_padrao: list[str] = []


class ConfigEmailIn(BaseModel):
    remetente_nome: str = Field(min_length=1, max_length=150)
    remetente_email: EmailStr
    smtp_host: str | None = None
    smtp_porta: int = Field(default=587, ge=1, le=65535)
    smtp_usuario: str | None = None
    smtp_senha: str | None = None  # só altera se enviado
    copia_padrao: list[EmailStr] = []


# ---------- IA ----------
class ConfigIAOut(BaseModel):
    ativo: bool
    provedor: str
    modelo: str | None
    chave_definida: bool
    chave_final: str | None  # só os 4 últimos caracteres, para conferência
    provedores: dict[str, str]


class ConfigIAIn(BaseModel):
    ativo: bool
    provedor: str = Field(pattern="^(openai|gemini)$")
    modelo: str | None = None
    chave: str | None = None  # só altera se vier


# ---------- Auditoria ----------
class AuditoriaOut(Schema):
    id: int
    usuario_nome: str | None
    acao: str
    entidade: str
    entidade_id: str | None
    descricao: str | None
    antes_json: dict[str, Any] | None
    depois_json: dict[str, Any] | None
    ip: str | None
    criado_em: datetime
