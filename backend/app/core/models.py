"""Modelos do núcleo (single-tenant: um estúdio por instalação).

Nomes de tabela FIXOS (contrato com os módulos de negócio, que criam FKs para elas):
`usuario`, `perfil_acesso`, `identidade`, `auditoria`, `config_email`, `config_ia`.
Tabelas auxiliares do core: `refresh_token`, `recuperacao_senha`, `rate_limit_evento`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamped, UtcDateTime, agora


class PerfilAcesso(Base, Timestamped):
    """Grupo de permissões (Configurações › Perfis de acesso). "administrador" pode tudo."""

    __tablename__ = "perfil_acesso"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)
    descricao: Mapped[str | None] = mapped_column(String(300))
    cor: Mapped[str | None] = mapped_column(String(7))
    administrador: Mapped[bool] = mapped_column(Boolean, default=False)
    sistema: Mapped[bool] = mapped_column(Boolean, default=False)  # o Administrador padrão não pode ser excluído
    # Quem usa o perfil só enxerga as PRÓPRIAS aulas/alunos (perfil Professor). Ver app.core.escopo.
    somente_proprias_aulas: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    permissoes: Mapped[list[str]] = mapped_column(JSON, default=list)


class Usuario(Base, Timestamped):
    """Quem opera o sistema. `acesso_sistema=False` = profissional sem login (existe só para vincular aulas etc.)."""

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    login: Mapped[str | None] = mapped_column(String(60), unique=True)  # opcional: entrar com usuário em vez de e-mail
    telefone: Mapped[str | None] = mapped_column(String(20))
    foto_path: Mapped[str | None] = mapped_column(String(500))  # RELATIVO ao storage (nunca absoluto)
    preferencias: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    senha_hash: Mapped[str | None] = mapped_column(String(255))  # nulo = sem login
    perfil_acesso_id: Mapped[int | None] = mapped_column(ForeignKey("perfil_acesso.id"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    acesso_sistema: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Sobe a cada troca/redefinição de senha: invalida access e refresh tokens emitidos antes.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    convite_pendente: Mapped[bool] = mapped_column(Boolean, default=False)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(UtcDateTime())
    ultima_atividade: Mapped[datetime | None] = mapped_column(UtcDateTime())
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(UtcDateTime())

    perfil_acesso: Mapped["PerfilAcesso | None"] = relationship()

    @property
    def administrador(self) -> bool:
        return bool(self.perfil_acesso and self.perfil_acesso.administrador)

    @property
    def permissoes(self) -> set[str]:
        from app.core.permissoes import TODAS

        if self.administrador:
            return set(TODAS)
        # sem perfil de acesso: nenhuma permissão (negar por padrão)
        return set(self.perfil_acesso.permissoes or []) if self.perfil_acesso else set()

    def pode(self, permissao: str) -> bool:
        return self.administrador or permissao in self.permissoes


class Identidade(Base, Timestamped):
    """Identidade do estúdio (white-label). Linha única (id=1)."""

    __tablename__ = "identidade"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    nome_exibicao: Mapped[str] = mapped_column(String(200))
    logo_path: Mapped[str | None] = mapped_column(String(500))  # relativo ao storage
    cor_destaque: Mapped[str | None] = mapped_column(String(9))
    assinatura_email: Mapped[str | None] = mapped_column(Text)


class ConfigEmail(Base, Timestamped):
    """SMTP configurável. A senha fica cifrada (Fernet/MASTER_KEY). Linha única (id=1)."""

    __tablename__ = "config_email"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    remetente_nome: Mapped[str] = mapped_column(String(150), default="MayaFit")
    remetente_email: Mapped[str] = mapped_column(String(200), default="nao-responda@localhost")
    smtp_host: Mapped[str | None] = mapped_column(String(200))
    smtp_porta: Mapped[int] = mapped_column(Integer, default=587)
    smtp_usuario: Mapped[str | None] = mapped_column(String(200))
    smtp_senha_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary)
    copia_padrao: Mapped[list[str]] = mapped_column(JSON, default=list)


class ConfigIA(Base, Timestamped):
    """IA plugável (OpenAI/Gemini). Chave cifrada com a MASTER_KEY. Linha única (id=1)."""

    __tablename__ = "config_ia"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, default=False)
    provedor: Mapped[str] = mapped_column(String(10), default="openai")  # openai | gemini
    modelo: Mapped[str | None] = mapped_column(String(100))
    chave_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary)


class Auditoria(Base):
    """Registro imutável: só aceita INSERT (ver bloqueios em app.core.audit)."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    usuario_nome: Mapped[str | None] = mapped_column(String(150))
    acao: Mapped[str] = mapped_column(String(60), index=True)
    entidade: Mapped[str] = mapped_column(String(60))
    entidade_id: Mapped[str | None] = mapped_column(String(60))
    descricao: Mapped[str | None] = mapped_column(String(500))
    antes_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    depois_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    criado_em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora, index=True)


class RefreshToken(Base):
    """Refresh tokens emitidos (com rotação). Reuso de um já consumido derruba todas as sessões do usuário."""

    __tablename__ = "refresh_token"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    expira_em: Mapped[datetime] = mapped_column(UtcDateTime())
    usado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    criado_em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)


class RecuperacaoSenha(Base):
    """Token de e-mail (link) ou código de WhatsApp para redefinir senha. Uso único; só o digest é guardado."""

    __tablename__ = "recuperacao_senha"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    canal: Mapped[str] = mapped_column(String(10))  # email | whatsapp
    digest: Mapped[str] = mapped_column(String(64), index=True)
    expira_em: Mapped[datetime] = mapped_column(UtcDateTime())
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    usado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    criado_em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)


class RateLimitEvento(Base):
    """Eventos do rate limit com backend em banco (vários processos). Limpeza pelo worker."""

    __tablename__ = "rate_limit_evento"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(200), index=True)
    em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora, index=True)
