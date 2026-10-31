"""CRM de vendas: etapas do funil, motivos de perda, leads, interações, tarefas e histórico de etapas.

O funil é configurável (`crm_etapa`), mas sempre tem UMA etapa de ganho ("Matriculado") e UMA de perda ("Perdido"):
elas definem a `situacao` do lead (ABERTO, GANHO, PERDIDO). Etapas abertas podem ter um `marco` que o sistema usa
para mover o lead sozinho (agendou aula experimental, fez a aula).
"""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime, agora
from app.modules.base import coluna_enum


class TipoEtapa(enum.StrEnum):
    ABERTA = "ABERTA"
    GANHO = "GANHO"
    PERDIDO = "PERDIDO"


class MarcoEtapa(enum.StrEnum):
    """Etapas que o sistema reconhece para automatizar o fluxo da aula experimental."""

    AULA_AGENDADA = "AULA_AGENDADA"
    AULA_REALIZADA = "AULA_REALIZADA"
    PROPOSTA = "PROPOSTA"


class SituacaoLead(enum.StrEnum):
    ABERTO = "ABERTO"
    GANHO = "GANHO"
    PERDIDO = "PERDIDO"


class OrigemLead(enum.StrEnum):
    SITE = "site"
    INSTAGRAM = "instagram"
    INDICACAO = "indicacao"
    WELLHUB = "wellhub"
    TOTALPASS = "totalpass"
    PASSANTE = "passante"
    WHATSAPP = "whatsapp"
    OUTROS = "outros"


class TipoInteracao(enum.StrEnum):
    LIGACAO = "LIGACAO"
    WHATSAPP = "WHATSAPP"
    VISITA = "VISITA"
    EMAIL = "EMAIL"
    NOTA = "NOTA"
    SISTEMA = "SISTEMA"  # registrado pelo sistema (mudança de etapa, contato pelo site, conversão)


class StatusAulaExperimental(enum.StrEnum):
    AGENDADA = "AGENDADA"
    REALIZADA = "REALIZADA"
    FALTOU = "FALTOU"
    CANCELADA = "CANCELADA"


class CrmEtapa(Base, Timestamped):
    __tablename__ = "crm_etapa"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    cor: Mapped[str] = mapped_column(String(9), default="#7C8FFF")
    tipo: Mapped[TipoEtapa] = mapped_column(coluna_enum(TipoEtapa, 10), default=TipoEtapa.ABERTA)
    marco: Mapped[MarcoEtapa | None] = mapped_column(coluna_enum(MarcoEtapa, 20))
    # dias sem andar nesta etapa até o lead aparecer como "parado" (0 = nunca)
    dias_alerta: Mapped[int] = mapped_column(Integer, default=3)


class CrmMotivoPerda(Base, Timestamped):
    __tablename__ = "crm_motivo_perda"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class CrmLead(Base, Timestamped):
    """Pessoa interessada em treinar no estúdio. Telefone guardado na forma canônica (55 + DDD + número)."""

    __tablename__ = "crm_lead"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), index=True)
    telefone: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(200), index=True)
    origem: Mapped[OrigemLead] = mapped_column(coluna_enum(OrigemLead, 20), default=OrigemLead.OUTROS, index=True)
    indicado_por: Mapped[str | None] = mapped_column(String(150))
    interesse: Mapped[str | None] = mapped_column(String(150))
    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), index=True)
    valor_estimado: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    observacoes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    etapa_id: Mapped[int] = mapped_column(ForeignKey("crm_etapa.id"), index=True)
    etapa_desde: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)
    situacao: Mapped[SituacaoLead] = mapped_column(coluna_enum(SituacaoLead, 10), default=SituacaoLead.ABERTO, index=True)
    motivo_perda_id: Mapped[int | None] = mapped_column(ForeignKey("crm_motivo_perda.id", ondelete="SET NULL"))
    motivo_perda_detalhe: Mapped[str | None] = mapped_column(String(300))
    perdido_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    ganho_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    aluno_id: Mapped[int | None] = mapped_column(ForeignKey("aluno.id", ondelete="SET NULL"))
    ultima_interacao_em: Mapped[datetime | None] = mapped_column(UtcDateTime())

    # aula experimental (só data/hora e quem dá; a ligação com a agenda fica para quando o lead virar aluno)
    aula_experimental_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    aula_experimental_status: Mapped[StatusAulaExperimental | None] = mapped_column(coluna_enum(StatusAulaExperimental, 12))
    aula_experimental_profissional_id: Mapped[int | None] = mapped_column(ForeignKey("profissional.id", ondelete="SET NULL"))
    aula_experimental_unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidade.id", ondelete="SET NULL"))
    aula_experimental_obs: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (Index("ix_crm_lead_situacao_etapa", "situacao", "etapa_id"),)


class CrmInteracao(Base):
    __tablename__ = "crm_interacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("crm_lead.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[TipoInteracao] = mapped_column(coluna_enum(TipoInteracao, 10))
    descricao: Mapped[str] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    ocorrido_em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)
    criado_em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)


class CrmTarefa(Base, Timestamped):
    """Tarefa ou lembrete com data/hora e responsável (sem responsável = da equipe toda)."""

    __tablename__ = "crm_tarefa"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("crm_lead.id", ondelete="CASCADE"), index=True)
    titulo: Mapped[str] = mapped_column(String(150))
    descricao: Mapped[str | None] = mapped_column(Text)
    vence_em: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), index=True)
    concluida: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    concluida_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    automatica: Mapped[bool] = mapped_column(Boolean, default=False)


class CrmMovimento(Base):
    """Histórico de etapas (base dos relatórios de conversão). `etapa_origem_id` nulo = entrada no funil."""

    __tablename__ = "crm_movimento"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("crm_lead.id", ondelete="CASCADE"), index=True)
    etapa_origem_id: Mapped[int | None] = mapped_column(ForeignKey("crm_etapa.id", ondelete="SET NULL"))
    etapa_destino_id: Mapped[int | None] = mapped_column(ForeignKey("crm_etapa.id", ondelete="SET NULL"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora, index=True)
