"""Controle de acesso: configuração, biometria (LGPD), totens/agentes, catracas, registros e fila de comandos.

LGPD (dado biométrico = dado pessoal SENSÍVEL, art. 11): o servidor nunca recebe nem guarda FOTO do check-in; guarda
só descritores numéricos (embeddings) gerados no navegador, CIFRADOS (Fernet/MASTER_KEY, `app.core.segredos`), e
somente com consentimento explícito registrado (`acesso_consentimento`). Apagar a biometria remove os descritores e
revoga o consentimento (o histórico do consentimento fica, sem biometria, como prova do tratamento).
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime, agora
from app.modules.base import coluna_enum


class MetodoAcesso(enum.StrEnum):
    facial = "facial"
    cpf = "cpf"
    codigo = "codigo"
    qr = "qr"
    manual = "manual"


class Sentido(enum.StrEnum):
    entrada = "entrada"
    saida = "saida"


class TipoDispositivo(enum.StrEnum):
    totem = "totem"
    agente = "agente"


class DriverCatraca(enum.StrEnum):
    controlid = "controlid"
    henry = "henry"
    simulado = "simulado"


class ModoAcionamento(enum.StrEnum):
    """Quem fala com a catraca: o navegador do totem (rede local), o agente local (polling) ou o próprio servidor
    (quando a catraca é alcançável da nuvem, por VPN/IP público)."""

    totem = "totem"
    agente = "agente"
    servidor = "servidor"


class AcessoConfig(Base, Timestamped):
    """Configuração do controle de acesso do estúdio (linha única, id=1)."""

    __tablename__ = "acesso_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    tolerancia_atraso_dias: Mapped[int] = mapped_column(Integer, default=5)
    janela_antes_min: Mapped[int] = mapped_column(Integer, default=30)
    janela_depois_min: Mapped[int] = mapped_column(Integer, default=15)
    permanencia_livre_min: Mapped[int] = mapped_column(Integer, default=90)
    planos_livres: Mapped[list | None] = mapped_column(JSON)  # ids de plano com acesso livre (academia)
    limiar_similaridade: Mapped[float] = mapped_column(Float, default=0.6)
    margem_ambiguidade: Mapped[float] = mapped_column(Float, default=0.03)
    exigir_prova_vida: Mapped[bool] = mapped_column(Boolean, default=True)
    exigir_pin: Mapped[bool] = mapped_column(Boolean, default=True)
    registrar_presenca: Mapped[bool] = mapped_column(Boolean, default=True)
    termo_biometria: Mapped[str | None] = mapped_column(Text)
    mensagem_boas_vindas: Mapped[str | None] = mapped_column(String(200))


class ConsentimentoBiometria(Base):
    """Consentimento explícito (LGPD art. 11, I). Um aluno tem no máximo um ATIVO (`revogado_em` nulo)."""

    __tablename__ = "acesso_consentimento"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), index=True)
    texto_termo: Mapped[str] = mapped_column(Text)
    hash_termo: Mapped[str] = mapped_column(String(64))
    coletado_em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)
    coletado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    coletado_por_nome: Mapped[str] = mapped_column(String(150))
    canal: Mapped[str] = mapped_column(String(20), default="recepcao")  # recepcao | totem
    ip: Mapped[str | None] = mapped_column(String(45))
    revogado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    revogado_por_nome: Mapped[str | None] = mapped_column(String(150))
    motivo_revogacao: Mapped[str | None] = mapped_column(String(300))


class DescritorFacial(Base):
    """Descritor facial (embedding normalizado, float32) CIFRADO. Nunca uma imagem."""

    __tablename__ = "acesso_descritor"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), index=True)
    consentimento_id: Mapped[int] = mapped_column(ForeignKey("acesso_consentimento.id", ondelete="CASCADE"))
    descritor_cifrado: Mapped[bytes] = mapped_column(LargeBinary)
    dimensao: Mapped[int] = mapped_column(Integer)
    modelo: Mapped[str] = mapped_column(String(40), default="human-faceres")
    origem: Mapped[str] = mapped_column(String(20), default="recepcao")  # recepcao | totem
    qualidade: Mapped[float | None] = mapped_column(Float)
    criado_em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)
    criado_por_nome: Mapped[str | None] = mapped_column(String(150))


class CredencialAluno(Base, Timestamped):
    """Alternativa sem biometria: PIN (hash argon2) usado com CPF/código; tentativas erradas bloqueiam por um tempo."""

    __tablename__ = "acesso_credencial"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), unique=True)
    pin_hash: Mapped[str | None] = mapped_column(String(200))
    tentativas_erradas: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(UtcDateTime())
    # código de uso único para o aluno cadastrar o rosto no próprio totem (gerado pela recepção)
    codigo_cadastro_hash: Mapped[str | None] = mapped_column(String(64))
    codigo_cadastro_expira: Mapped[datetime | None] = mapped_column(UtcDateTime())
    codigo_cadastro_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    codigo_cadastro_por_nome: Mapped[str | None] = mapped_column(String(150))


class Catraca(Base, Timestamped):
    __tablename__ = "acesso_catraca"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidade.id", ondelete="SET NULL"))
    driver: Mapped[DriverCatraca] = mapped_column(coluna_enum(DriverCatraca, 20), default=DriverCatraca.simulado)
    modo: Mapped[ModoAcionamento] = mapped_column(coluna_enum(ModoAcionamento, 10), default=ModoAcionamento.totem)
    host: Mapped[str | None] = mapped_column(String(200))
    porta: Mapped[int | None] = mapped_column(Integer)
    usar_https: Mapped[bool] = mapped_column(Boolean, default=False)
    usuario: Mapped[str | None] = mapped_column(String(120))
    senha_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary)
    senha_final: Mapped[str | None] = mapped_column(String(4))
    sentido_entrada: Mapped[str] = mapped_column(String(20), default="clockwise")  # clockwise | anticlockwise | both
    acao_liberacao: Mapped[str] = mapped_column(String(20), default="catra")  # catra (iDBlock) | door (iDAccess/iDFlex)
    porta_rele: Mapped[int] = mapped_column(Integer, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_teste_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    ultimo_teste_ok: Mapped[bool | None] = mapped_column(Boolean)
    ultimo_teste_detalhe: Mapped[str | None] = mapped_column(String(300))


class Dispositivo(Base, Timestamped):
    """Totem (tablet/notebook da recepção) ou agente local. Autentica por token guardado só como SHA-256."""

    __tablename__ = "acesso_dispositivo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[TipoDispositivo] = mapped_column(coluna_enum(TipoDispositivo, 10), default=TipoDispositivo.totem)
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidade.id", ondelete="SET NULL"))
    catraca_id: Mapped[int | None] = mapped_column(ForeignKey("acesso_catraca.id", ondelete="SET NULL"))
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_final: Mapped[str | None] = mapped_column(String(4))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    revogado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    ultimo_contato: Mapped[datetime | None] = mapped_column(UtcDateTime())
    criado_por_nome: Mapped[str | None] = mapped_column(String(150))


class RegistroAcesso(Base):
    """Cada tentativa de acesso (permitida ou negada). Sem foto, sem descritor."""

    __tablename__ = "acesso_registro"

    id: Mapped[int] = mapped_column(primary_key=True)
    em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)
    aluno_id: Mapped[int | None] = mapped_column(ForeignKey("aluno.id", ondelete="SET NULL"))
    aluno_nome: Mapped[str | None] = mapped_column(String(150))
    permitido: Mapped[bool] = mapped_column(Boolean)
    codigo: Mapped[str] = mapped_column(String(40))
    motivo: Mapped[str] = mapped_column(String(300))
    metodo: Mapped[MetodoAcesso] = mapped_column(coluna_enum(MetodoAcesso, 10))
    sentido: Mapped[Sentido] = mapped_column(coluna_enum(Sentido, 10), default=Sentido.entrada)
    dispositivo_id: Mapped[int | None] = mapped_column(ForeignKey("acesso_dispositivo.id", ondelete="SET NULL"))
    dispositivo_nome: Mapped[str | None] = mapped_column(String(120))
    catraca_id: Mapped[int | None] = mapped_column(ForeignKey("acesso_catraca.id", ondelete="SET NULL"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))  # liberação manual
    usuario_nome: Mapped[str | None] = mapped_column(String(150))
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reserva.id", ondelete="SET NULL"))
    aula_descricao: Mapped[str | None] = mapped_column(String(200))
    presenca_registrada: Mapped[bool] = mapped_column(Boolean, default=False)
    similaridade: Mapped[float | None] = mapped_column(Float)
    previsto_sair: Mapped[datetime | None] = mapped_column(UtcDateTime())
    catraca_status: Mapped[str | None] = mapped_column(String(20))  # pendente | liberada | falhou | sem_catraca
    catraca_detalhe: Mapped[str | None] = mapped_column(String(300))
    qr_nonce: Mapped[str | None] = mapped_column(String(40), unique=True)

    __table_args__ = (
        Index("ix_acesso_registro_em", "em"),
        Index("ix_acesso_registro_aluno_em", "aluno_id", "em"),
    )


class ComandoCatraca(Base):
    """Fila para o agente local: o servidor (nuvem) não alcança a rede do estúdio; o agente busca e executa."""

    __tablename__ = "acesso_comando"

    id: Mapped[int] = mapped_column(primary_key=True)
    catraca_id: Mapped[int] = mapped_column(ForeignKey("acesso_catraca.id", ondelete="CASCADE"), index=True)
    acao: Mapped[str] = mapped_column(String(20), default="liberar")  # liberar | status
    sentido: Mapped[str] = mapped_column(String(20), default="entrada")
    registro_id: Mapped[int | None] = mapped_column(ForeignKey("acesso_registro.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente | entregue | ok | erro | expirado
    criado_em: Mapped[datetime] = mapped_column(UtcDateTime(), default=agora)
    expira_em: Mapped[datetime] = mapped_column(UtcDateTime())
    entregue_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    concluido_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    resultado: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (Index("ix_acesso_comando_status", "status", "catraca_id"),)
