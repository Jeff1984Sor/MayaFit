"""Esquemas do controle de acesso. Segredos (senha da catraca, token do dispositivo) são só escrita."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


Descritor = list[float]


# ------------------------------------------------------------------------------------------------------ configuração
class ConfigIn(Base):
    tolerancia_atraso_dias: int = Field(ge=0, le=90)
    janela_antes_min: int = Field(ge=0, le=240)
    janela_depois_min: int = Field(ge=0, le=240)
    permanencia_livre_min: int = Field(ge=15, le=600)
    planos_livres: list[int] = Field(default_factory=list, max_length=200)
    limiar_similaridade: float = Field(ge=0.3, le=0.99)
    margem_ambiguidade: float = Field(ge=0.0, le=0.3)
    exigir_prova_vida: bool
    exigir_pin: bool
    registrar_presenca: bool
    termo_biometria: str = Field(min_length=40, max_length=8000)
    mensagem_boas_vindas: str | None = Field(default=None, max_length=200)


class ConfigOut(ConfigIn):
    model_config = ConfigDict(from_attributes=True)


class OpcaoOut(BaseModel):
    id: int
    nome: str


class DriverOut(BaseModel):
    nome: str
    rotulo: str
    suporta_navegador: bool


class OpcoesOut(BaseModel):
    unidades: list[OpcaoOut]
    planos: list[OpcaoOut]
    drivers: list[DriverOut]
    catracas: list[OpcaoOut]


# ------------------------------------------------------------------------------------------------------ catraca
class PassoOut(BaseModel):
    metodo: str
    url: str
    corpo: dict[str, Any] | None = None
    extrair: str | None = None


class PlanoOut(BaseModel):
    driver: str
    passos: list[PassoOut]
    descricao: str = ""


class AcionamentoOut(BaseModel):
    """O que aconteceu (ou o que o navegador deve fazer) com a catraca depois de uma decisão."""

    catraca_id: int | None = None
    catraca_nome: str | None = None
    modo: str | None = None  # totem | agente | servidor
    status: str  # liberada | falhou | pendente | sem_catraca
    mensagem: str = ""
    plano: PlanoOut | None = None  # modo totem: passos HTTP para o navegador executar na rede local
    comando_id: int | None = None  # modo agente


class CatracaIn(Base):
    nome: str = Field(min_length=2, max_length=120)
    unidade_id: int | None = None
    driver: Literal["controlid", "henry", "simulado"]
    modo: Literal["totem", "agente", "servidor"]
    host: str | None = Field(default=None, max_length=200, pattern=r"^[A-Za-z0-9.\-:\[\]]*$")
    porta: int | None = Field(default=None, ge=1, le=65535)
    usar_https: bool = False
    usuario: str | None = Field(default=None, max_length=120)
    senha: str | None = Field(default=None, max_length=200, description="Só escrita. Vazio/None mantém a atual.")
    sentido_entrada: Literal["clockwise", "anticlockwise", "both"] = "clockwise"
    acao_liberacao: Literal["catra", "door"] = "catra"
    porta_rele: int = Field(default=1, ge=1, le=8)
    ativo: bool = True


class CatracaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    unidade_id: int | None
    unidade_nome: str | None = None
    driver: str
    modo: str
    host: str | None
    porta: int | None
    usar_https: bool
    usuario: str | None
    senha_definida: bool
    senha_final: str | None
    sentido_entrada: str
    acao_liberacao: str
    porta_rele: int
    ativo: bool
    ultimo_teste_em: datetime | None
    ultimo_teste_ok: bool | None
    ultimo_teste_detalhe: str | None


class LiberarIn(Base):
    motivo: str = Field(min_length=3, max_length=300)
    sentido: Literal["entrada", "saida"] = "entrada"
    aluno_id: int | None = None


class ResultadoCatracaIn(Base):
    ok: bool
    detalhe: str | None = Field(default=None, max_length=300)


class TesteOut(BaseModel):
    ok: bool | None  # None = o navegador ainda vai executar o plano
    mensagem: str
    acionamento: AcionamentoOut | None = None


# ------------------------------------------------------------------------------------------------------ dispositivos
class DispositivoIn(Base):
    nome: str = Field(min_length=2, max_length=120)
    tipo: Literal["totem", "agente"] = "totem"
    unidade_id: int | None = None
    catraca_id: int | None = None


class DispositivoEditarIn(Base):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    unidade_id: int | None = None
    catraca_id: int | None = None


class DispositivoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    tipo: str
    unidade_id: int | None
    unidade_nome: str | None = None
    catraca_id: int | None
    catraca_nome: str | None = None
    token_final: str | None
    ativo: bool
    revogado_em: datetime | None
    ultimo_contato: datetime | None
    online: bool = False
    criado_em: datetime
    criado_por_nome: str | None


class DispositivoComTokenOut(DispositivoOut):
    """Criar/regenerar: o `token` completo aparece UMA ÚNICA VEZ."""

    token: str


# ------------------------------------------------------------------------------------------------------ biometria
class ConsentimentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    coletado_em: datetime
    coletado_por_nome: str
    canal: str
    hash_termo: str
    revogado_em: datetime | None
    revogado_por_nome: str | None
    motivo_revogacao: str | None


class DescritorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criado_em: datetime
    origem: str
    qualidade: float | None
    modelo: str
    dimensao: int
    criado_por_nome: str | None


class AlunoAcessoOut(BaseModel):
    id: int
    nome: str
    cpf: str | None
    codigo: int | None
    ativo: bool
    foto_url: str | None = None
    consentimento: ConsentimentoOut | None
    descritores: int
    pin_definido: bool


class ListaAlunosAcessoOut(BaseModel):
    itens: list[AlunoAcessoOut]
    total: int
    pagina: int
    por_pagina: int
    com_biometria: int
    sem_biometria: int


class AlunoAcessoDetalheOut(AlunoAcessoOut):
    lista_descritores: list[DescritorOut]
    historico_consentimentos: list[ConsentimentoOut]
    termo_atual: str
    ultimos_acessos: list[RegistroOut]


class ConsentimentoIn(Base):
    aceite: Literal[True]


class ProvaVidaIn(Base):
    piscou: bool = False
    real: float | None = Field(default=None, ge=0, le=1)
    live: float | None = Field(default=None, ge=0, le=1)


class DescritoresIn(Base):
    descritores: list[Descritor] = Field(min_length=1, max_length=5)
    qualidade: float | None = Field(default=None, ge=0, le=1)
    prova_vida: ProvaVidaIn | None = None


class ApagarBiometriaIn(Base):
    motivo: str = Field(min_length=3, max_length=300)


class PinIn(Base):
    pin: str = Field(min_length=4, max_length=6, pattern=r"^\d+$")


class CodigoTotemOut(BaseModel):
    codigo: str
    expira_em: datetime


# ------------------------------------------------------------------------------------------------------ registros
class RegistroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    em: datetime
    aluno_id: int | None
    aluno_nome: str | None
    permitido: bool
    codigo: str
    motivo: str
    metodo: str
    sentido: str
    dispositivo_nome: str | None
    usuario_nome: str | None
    aula_descricao: str | None
    presenca_registrada: bool
    similaridade: float | None
    catraca_status: str | None
    catraca_detalhe: str | None


AlunoAcessoDetalheOut.model_rebuild()


class ListaRegistrosOut(BaseModel):
    itens: list[RegistroOut]
    total: int
    pagina: int
    por_pagina: int


class PresenteOut(BaseModel):
    registro_id: int
    aluno_id: int | None
    nome: str
    primeiro_nome: str
    foto_url: str | None = None
    entrou_em: datetime
    previsto_sair: datetime | None
    aula: str | None
    metodo: str
    aniversario: bool = False


class EquipamentoStatusOut(BaseModel):
    id: int
    nome: str
    tipo: str  # totem | agente | catraca
    online: bool | None
    detalhe: str | None = None


class PainelOut(BaseModel):
    agora: datetime
    presentes: list[PresenteOut]
    entradas_hoje: int
    negados_hoje: int
    alunos_hoje: int
    por_metodo: dict[str, int]
    ultimos: list[RegistroOut]
    equipamentos: list[EquipamentoStatusOut]
    proximas_aulas: list[dict[str, Any]]


class SaidaIn(Base):
    motivo: str | None = Field(default=None, max_length=300)


class RelatorioOut(BaseModel):
    de: date
    ate: date
    total: int
    permitidos: int
    negados: int
    alunos_unicos: int
    por_dia: list[dict[str, Any]]
    por_hora: list[dict[str, Any]]
    por_metodo: list[dict[str, Any]]
    motivos_negacao: list[dict[str, Any]]
    mais_frequentes: list[dict[str, Any]]


# ------------------------------------------------------------------------------------------------------ totem
class AulaOut(BaseModel):
    servico: str
    inicio: time
    fim: time
    profissional: str | None


class CheckinOut(BaseModel):
    permitido: bool
    codigo: str
    motivo: str
    titulo: str
    primeiro_nome: str | None = None
    aniversario: bool = False
    avisos: list[str] = []
    aula: AulaOut | None = None
    registro_id: int | None = None
    presenca_registrada: bool = False
    acionamento: AcionamentoOut | None = None


class IdentificarFacialIn(Base):
    descritor: Descritor = Field(min_length=64, max_length=2048)
    prova_vida: ProvaVidaIn | None = None


class IdentificarDocumentoIn(Base):
    documento: str = Field(min_length=1, max_length=20)
    pin: str | None = Field(default=None, max_length=6)


class IdentificarQrIn(Base):
    qr: str = Field(min_length=10, max_length=200)


class TotemMeOut(BaseModel):
    dispositivo: str
    unidade: str | None
    estudio: str
    cor: str | None = None
    exigir_prova_vida: bool
    exigir_pin: bool
    tem_catraca: bool
    modo_catraca: str | None
    biometria_cadastrada: int
    modelo_facial: str = "human-faceres"


class CadastroTotemInicioIn(Base):
    documento: str = Field(min_length=1, max_length=20)
    codigo: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class CadastroTotemInicioOut(BaseModel):
    primeiro_nome: str
    termo: str


class CadastroTotemConcluirIn(CadastroTotemInicioIn):
    aceite: Literal[True]
    descritores: list[Descritor] = Field(min_length=1, max_length=5)
    prova_vida: ProvaVidaIn | None = None


class QrOut(BaseModel):
    qr: str
    expira_em: datetime


# ------------------------------------------------------------------------------------------------------ agente
class ComandoOut(BaseModel):
    id: int
    acao: str
    sentido: str
    catraca: dict[str, Any]
    expira_em: datetime


class ResultadoComandoIn(Base):
    ok: bool
    mensagem: str = Field(default="", max_length=300)
