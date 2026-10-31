"""Modelos da integração com o Wellhub (antigo Gympass). Migração: `0140_wellhub`.

- `WellhubConfig`: uma por unidade (gym id, ambiente, chave de API e segredo do webhook CIFRADOS, regras).
- `WellhubMapeamento`: serviço do estúdio ↔ produto/classe do Wellhub.
- `WellhubSlot`: aula (sessão) publicada no Wellhub como slot, com a capacidade/vagas enviadas.
- `WellhubAluno`: vínculo aluno ↔ Gympass ID (o `unique_token` de 13 dígitos).
- `WellhubReserva`: reserva vinda do Wellhub (booking_number ↔ reserva da agenda).
- `WellhubEvento`: log de tudo que chegou pelo webhook (idempotente pela `chave`).
- `WellhubCheckin`: check-ins (um por aluno, por dia, por unidade); base do relatório de repasse.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime


class WellhubConfig(Base, Timestamped):
    __tablename__ = "wellhub_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=False)
    ambiente: Mapped[str] = mapped_column(String(10), default="sandbox")  # sandbox | producao
    gym_id: Mapped[str | None] = mapped_column(String(40), index=True)
    api_key_cifrado: Mapped[str | None] = mapped_column(Text)
    webhook_secret_cifrado: Mapped[str | None] = mapped_column(Text)
    criar_aluno_automatico: Mapped[bool] = mapped_column(Boolean, default=True)
    validar_checkin_automatico: Mapped[bool] = mapped_column(Boolean, default=True)
    servico_padrao_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_servico.id", ondelete="SET NULL"))
    valor_repasse_checkin: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    sync_ativo: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_dias: Mapped[int] = mapped_column(Integer, default=7)
    sync_ultimo_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    sync_ultimo_resumo: Mapped[str | None] = mapped_column(String(300))
    sync_ultimo_ok: Mapped[bool | None] = mapped_column(Boolean)
    teste_ultimo_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    teste_ultimo_ok: Mapped[bool | None] = mapped_column(Boolean)
    falhas_assinatura: Mapped[int] = mapped_column(Integer, default=0)
    falha_assinatura_em: Mapped[datetime | None] = mapped_column(UtcDateTime())


class WellhubMapeamento(Base, Timestamped):
    __tablename__ = "wellhub_mapeamento"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("wellhub_config.id", ondelete="CASCADE"), index=True)
    tipo_servico_id: Mapped[int] = mapped_column(ForeignKey("tipo_servico.id", ondelete="CASCADE"))
    product_id: Mapped[str | None] = mapped_column(String(40))
    class_id: Mapped[str | None] = mapped_column(String(40))
    nome_classe: Mapped[str | None] = mapped_column(String(150))
    descricao: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("config_id", "tipo_servico_id"),)


class WellhubSlot(Base, Timestamped):
    __tablename__ = "wellhub_slot"

    id: Mapped[int] = mapped_column(primary_key=True)
    mapeamento_id: Mapped[int] = mapped_column(ForeignKey("wellhub_mapeamento.id", ondelete="CASCADE"), index=True)
    aula_sessao_id: Mapped[int | None] = mapped_column(ForeignKey("aula_sessao.id", ondelete="SET NULL"), unique=True)
    slot_id: Mapped[str] = mapped_column(String(40), index=True)
    capacidade_publicada: Mapped[int] = mapped_column(Integer, default=0)
    reservadas_publicadas: Mapped[int] = mapped_column(Integer, default=0)
    publicado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    situacao: Mapped[str] = mapped_column(String(12), default="publicado")  # publicado | removido


class WellhubAluno(Base, Timestamped):
    __tablename__ = "wellhub_aluno"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), unique=True)
    gympass_id: Mapped[str] = mapped_column(String(20), unique=True)
    config_id: Mapped[int | None] = mapped_column(ForeignKey("wellhub_config.id", ondelete="SET NULL"))


class WellhubReserva(Base, Timestamped):
    __tablename__ = "wellhub_reserva"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("wellhub_config.id", ondelete="CASCADE"), index=True)
    booking_number: Mapped[str] = mapped_column(String(60), unique=True)
    slot_id: Mapped[str | None] = mapped_column(String(40))
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reserva.id", ondelete="SET NULL"), index=True)
    aluno_id: Mapped[int | None] = mapped_column(ForeignKey("aluno.id", ondelete="SET NULL"), index=True)
    situacao: Mapped[str] = mapped_column(String(20), default="reservada")  # reservada|rejeitada|cancelada|cancelada_tarde
    resposta_enviada: Mapped[str | None] = mapped_column(String(20))  # reservado | rejeitado (o que foi enviado no PATCH)
    resposta_em: Mapped[datetime | None] = mapped_column(UtcDateTime())


class WellhubEvento(Base):
    __tablename__ = "wellhub_evento"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(80), unique=True)  # idempotência: id do evento ou hash do corpo
    config_id: Mapped[int | None] = mapped_column(ForeignKey("wellhub_config.id", ondelete="SET NULL"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    gympass_id: Mapped[str | None] = mapped_column(String(20))
    booking_number: Mapped[str | None] = mapped_column(String(60))
    slot_id: Mapped[str | None] = mapped_column(String(40))
    payload: Mapped[Any] = mapped_column(JSON)
    recebido_em: Mapped[datetime] = mapped_column(UtcDateTime())
    processado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    resultado: Mapped[str] = mapped_column(String(20), default="pendente")
    erro: Mapped[str | None] = mapped_column(Text)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    origem: Mapped[str] = mapped_column(String(12), default="webhook")  # webhook | reprocessar | demo
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reserva.id", ondelete="SET NULL"))
    aluno_id: Mapped[int | None] = mapped_column(ForeignKey("aluno.id", ondelete="SET NULL"))
    ignorado: Mapped[bool] = mapped_column(Boolean, default=False)  # erro conferido pela equipe (sai dos alertas)

    __table_args__ = (
        Index("ix_wellhub_evento_recebido_em", "recebido_em"),
        Index("ix_wellhub_evento_resultado", "resultado"),
    )


class WellhubCheckin(Base, Timestamped):
    __tablename__ = "wellhub_checkin"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("wellhub_config.id", ondelete="CASCADE"))
    aluno_id: Mapped[int | None] = mapped_column(ForeignKey("aluno.id", ondelete="SET NULL"), index=True)
    gympass_id: Mapped[str] = mapped_column(String(20))
    dia: Mapped[date] = mapped_column(Date)
    ocorrido_em: Mapped[datetime] = mapped_column(UtcDateTime())
    origem: Mapped[str] = mapped_column(String(12), default="webhook")  # webhook | reserva | validacao | demo
    validado: Mapped[bool] = mapped_column(Boolean, default=False)
    validado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    erro_validacao: Mapped[str | None] = mapped_column(String(300))
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reserva.id", ondelete="SET NULL"))
    produto: Mapped[str | None] = mapped_column(String(150))

    __table_args__ = (
        UniqueConstraint("config_id", "gympass_id", "dia"),
        Index("ix_wellhub_checkin_dia", "dia"),
    )
