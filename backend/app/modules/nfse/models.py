"""NFS-e: configuração fiscal do estúdio (linha única), notas e linha do tempo de cada nota.

Segredos (o .pfx e a senha) ficam cifrados com `app.core.segredos` (Fernet/MASTER_KEY) e nunca saem pela API.
Idempotência: `nota_fiscal.chave_emissao` é UNIQUE (`rec:<id do recebimento>` ou `avulsa:<uuid>`); ao cancelar,
a chave vira `...:x<id>` e libera uma nova emissão para o mesmo recebimento.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime
from app.modules.base import coluna_enum


class Provedor(enum.StrEnum):
    nacional = "nacional"  # Padrão Nacional (Sefin Nacional / ADN)
    sao_paulo = "sao_paulo"  # Prefeitura de São Paulo, layout 2


class Modo(enum.StrEnum):
    simulado = "simulado"  # nada sai do servidor: XML montado, assinado e validado; resposta simulada
    homologacao = "homologacao"  # Nacional: produção restrita · SP: "teste de envio" (valida e não gera nota)
    producao = "producao"  # emissão real (exige também AMBIENTE=prod no servidor)


class StatusNota(enum.StrEnum):
    pendente = "pendente"  # na fila (inclui retentativa após falha de comunicação)
    processando = "processando"
    emitida = "emitida"
    validada = "validada"  # homologação SP: a Prefeitura validou tudo, mas não gera nota
    rejeitada = "rejeitada"  # a prefeitura/Sefin recusou: precisa de correção
    falha = "falha"  # esgotou as tentativas de comunicação
    cancelada = "cancelada"


class OrigemNota(enum.StrEnum):
    avulsa = "avulsa"
    recebimento = "recebimento"
    automatica = "automatica"
    demo = "demo"


class ConfigNfse(Base, Timestamped):
    """Configuração fiscal (linha única, id=1)."""

    __tablename__ = "nfse_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, default=False)
    provedor: Mapped[Provedor] = mapped_column(coluna_enum(Provedor, 20), default=Provedor.nacional)
    modo: Mapped[Modo] = mapped_column(coluna_enum(Modo, 20), default=Modo.simulado)
    # prestador
    cnpj: Mapped[str | None] = mapped_column(String(14))
    razao_social: Mapped[str | None] = mapped_column(String(150))
    inscricao_municipal: Mapped[str | None] = mapped_column(String(15))
    codigo_municipio: Mapped[str | None] = mapped_column(String(7))  # IBGE
    municipio_nome: Mapped[str | None] = mapped_column(String(80))
    uf: Mapped[str | None] = mapped_column(String(2))
    email: Mapped[str | None] = mapped_column(String(80))
    telefone: Mapped[str | None] = mapped_column(String(20))
    regime: Mapped[str] = mapped_column(String(15), default="simples")  # mei | simples | presumido | real
    # serviço e tributação
    item_lista_servico: Mapped[str] = mapped_column(String(5), default="06.04")
    codigo_tributacao_nacional: Mapped[str] = mapped_column(String(6), default="060401")
    codigo_servico_municipal: Mapped[str | None] = mapped_column(String(20))  # SP: código de 5 dígitos
    nbs: Mapped[str | None] = mapped_column(String(9))
    aliquota_iss: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("2.00"))
    iss_retido: Mapped[bool] = mapped_column(Boolean, default=False)
    informar_aliquota: Mapped[bool] = mapped_column(Boolean, default=False)  # Nacional: pAliq na DPS
    percentual_tributos_sn: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # Lei 12.741 (Simples)
    discriminacao_modelo: Mapped[str | None] = mapped_column(Text)
    serie: Mapped[str] = mapped_column(String(5), default="1")
    proximo_numero: Mapped[int] = mapped_column(Integer, default=1)
    parametros_extras: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # IBS/CBS do layout SP etc.
    # automações
    emissao_automatica: Mapped[bool] = mapped_column(Boolean, default=False)
    automatica_desde: Mapped[date | None] = mapped_column(Date)
    enviar_email_aluno: Mapped[bool] = mapped_column(Boolean, default=True)
    # certificado A1 (cifrado)
    certificado_pfx_cifrado: Mapped[bytes | None] = mapped_column(LargeBinary)
    certificado_senha_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary)
    certificado_titular: Mapped[str | None] = mapped_column(String(200))
    certificado_cnpj: Mapped[str | None] = mapped_column(String(14))
    certificado_emissor: Mapped[str | None] = mapped_column(String(200))
    certificado_valido_de: Mapped[date | None] = mapped_column(Date)
    certificado_valido_ate: Mapped[date | None] = mapped_column(Date)
    certificado_enviado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())

    __table_args__ = (
        CheckConstraint("aliquota_iss >= 0 AND aliquota_iss <= 5", name="aliquota_iss_faixa"),
        CheckConstraint("proximo_numero >= 1", name="proximo_numero_positivo"),
    )


class NotaFiscal(Base, Timestamped):
    __tablename__ = "nota_fiscal"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave_emissao: Mapped[str] = mapped_column(String(80), unique=True)
    origem: Mapped[OrigemNota] = mapped_column(coluna_enum(OrigemNota, 15), default=OrigemNota.avulsa)
    lote: Mapped[str | None] = mapped_column(String(36), index=True)
    conta_receber_id: Mapped[int | None] = mapped_column(ForeignKey("conta_receber.id", ondelete="SET NULL"), index=True)
    aluno_id: Mapped[int | None] = mapped_column(ForeignKey("aluno.id", ondelete="SET NULL"), index=True)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))

    provedor: Mapped[Provedor] = mapped_column(coluna_enum(Provedor, 20))
    modo: Mapped[Modo] = mapped_column(coluna_enum(Modo, 20))
    status: Mapped[StatusNota] = mapped_column(coluna_enum(StatusNota, 15), default=StatusNota.pendente, index=True)

    serie: Mapped[str] = mapped_column(String(5))
    numero_dps: Mapped[int] = mapped_column(Integer)
    id_dps: Mapped[str | None] = mapped_column(String(45))

    # tomador (cópia do momento da emissão)
    tomador_tipo: Mapped[str] = mapped_column(String(10), default="aluno")  # aluno | pessoa | empresa
    tomador_documento: Mapped[str | None] = mapped_column(String(14))
    tomador_nome: Mapped[str] = mapped_column(String(150))
    tomador_email: Mapped[str | None] = mapped_column(String(200))
    tomador_endereco: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # serviço e valores
    competencia: Mapped[date] = mapped_column(Date, index=True)
    discriminacao: Mapped[str] = mapped_column(Text)
    item_lista_servico: Mapped[str] = mapped_column(String(5))
    codigo_tributacao_nacional: Mapped[str] = mapped_column(String(6))
    codigo_servico_municipal: Mapped[str | None] = mapped_column(String(20))
    valor_servico: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    deducoes: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    aliquota: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    valor_iss: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    iss_retido: Mapped[bool] = mapped_column(Boolean, default=False)
    regime: Mapped[str] = mapped_column(String(15))

    # retorno
    numero_nfse: Mapped[str | None] = mapped_column(String(20))
    codigo_verificacao: Mapped[str | None] = mapped_column(String(20))
    chave_acesso: Mapped[str | None] = mapped_column(String(50))
    link_oficial: Mapped[str | None] = mapped_column(String(500))
    emitida_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    xml_enviado: Mapped[str | None] = mapped_column(Text)
    xml_retorno: Mapped[str | None] = mapped_column(Text)
    erros: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    alertas: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)

    # fila
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    proxima_tentativa_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    falha_comunicacao: Mapped[bool] = mapped_column(Boolean, default=False)  # consultar antes de reenviar

    # cancelamento e e-mail
    cancelada_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(255))
    codigo_motivo_cancelamento: Mapped[str | None] = mapped_column(String(2))
    email_enviado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())

    __table_args__ = (
        UniqueConstraint("provedor", "serie", "numero_dps", name="uq_nota_fiscal_rps"),
        CheckConstraint("valor_servico > 0", name="valor_positivo"),
        Index("ix_nota_fiscal_status_proxima", "status", "proxima_tentativa_em"),
    )


class NotaEvento(Base):
    """Linha do tempo da nota (enfileirada, enviada, rejeitada, emitida, cancelada, e-mail...)."""

    __tablename__ = "nota_fiscal_evento"

    id: Mapped[int] = mapped_column(primary_key=True)
    nota_id: Mapped[int] = mapped_column(ForeignKey("nota_fiscal.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    descricao: Mapped[str] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    criado_em: Mapped[datetime] = mapped_column(UtcDateTime())
