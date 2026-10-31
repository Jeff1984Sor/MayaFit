"""Esquemas da integração Wellhub. Segredos: só escrita; a leitura mostra "definido" + os 4 últimos caracteres."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SegredoOut(Base):
    definido: bool
    final: str | None = None


class ServicoOpcao(Base):
    id: int
    nome: str


class MapeamentoOut(Base):
    id: int
    tipo_servico_id: int
    servico_nome: str
    product_id: str | None
    class_id: str | None
    nome_classe: str | None
    descricao: str | None
    ativo: bool
    slots_publicados: int


class ConfigOut(Base):
    unidade_id: int
    unidade_nome: str
    configurada: bool
    ativo: bool
    ambiente: Literal["sandbox", "producao"]
    gym_id: str | None
    criar_aluno_automatico: bool
    validar_checkin_automatico: bool
    servico_padrao_id: int | None
    valor_repasse_checkin: Decimal | None
    sync_ativo: bool
    sync_dias: int
    sync_ultimo_em: datetime | None
    sync_ultimo_resumo: str | None
    sync_ultimo_ok: bool | None
    teste_ultimo_em: datetime | None
    teste_ultimo_ok: bool | None
    api_key: SegredoOut
    webhook_secret: SegredoOut
    mapeamentos: list[MapeamentoOut]


class TelaOut(Base):
    webhook_caminho: str
    configuracoes: list[ConfigOut]
    servicos: list[ServicoOpcao]


class ConfigIn(Base):
    """PUT parcial: campo ausente = mantém. Segredos: ausente/vazio = mantém; para apagar, liste em `limpar`."""

    ativo: bool | None = None
    ambiente: Literal["sandbox", "producao"] | None = None
    gym_id: str | None = Field(default=None, max_length=40, pattern=r"^[0-9A-Za-z_-]*$")
    criar_aluno_automatico: bool | None = None
    validar_checkin_automatico: bool | None = None
    servico_padrao_id: int | None = None
    valor_repasse_checkin: Decimal | None = Field(default=None, ge=0, le=100000, decimal_places=2)
    sync_ativo: bool | None = None
    sync_dias: int | None = Field(default=None, ge=1, le=60)
    api_key: str | None = Field(default=None, max_length=500)
    webhook_secret: str | None = Field(default=None, max_length=300)
    limpar: list[Literal["api_key", "webhook_secret"]] = Field(default_factory=list)


class SegredoGeradoOut(Base):
    """O valor aparece UMA ÚNICA VEZ (para cadastrar no Wellhub)."""

    valor: str
    final: str


class MapeamentoIn(Base):
    tipo_servico_id: int
    product_id: str | None = Field(default=None, max_length=40, pattern=r"^[0-9A-Za-z_-]*$")
    nome_classe: str | None = Field(default=None, max_length=150)
    descricao: str | None = Field(default=None, max_length=1000)
    ativo: bool = True


class MapeamentosIn(Base):
    itens: list[MapeamentoIn] = Field(max_length=200)


class TesteOut(Base):
    ok: bool
    mensagem: str
    detalhes: dict | None = None


class ProdutoOut(Base):
    id: str
    nome: str


class ResumoGradeOut(Base):
    resumo: str
    previa: bool
    classes_criadas: int
    slots_criados: int
    slots_atualizados: int
    slots_removidos: int
    sem_mudanca: int
    erros: int
    mensagens: list[str]


class EventoOut(Base):
    id: int
    recebido_em: datetime
    processado_em: datetime | None
    tipo: str
    tipo_rotulo: str
    unidade_nome: str | None
    gympass_mascarado: str | None
    booking_number: str | None
    slot_id: str | None
    aluno_id: int | None
    aluno_nome: str | None
    resultado: str
    erro: str | None
    tentativas: int
    origem: str
    reserva_id: int | None
    ignorado: bool
    pode_reprocessar: bool


class EventoDetalheOut(EventoOut):
    payload: dict | None


class ListaEventosOut(Base):
    total: int
    pagina: int
    por_pagina: int
    itens: list[EventoOut]


class ReprocessarOut(Base):
    resultado: str
    mensagem: str | None
    evento: EventoOut


class PassoOut(Base):
    id: str
    titulo: str
    concluido: bool
    pendencia: str | None


class AlertaOut(Base):
    nivel: Literal["danger", "warning", "info"]
    titulo: str
    descricao: str
    acao: str | None
    extra: dict = Field(default_factory=dict)


class PontoSerie(Base):
    dia: date
    total: int
    validados: int


class PainelOut(Base):
    unidade_id: int
    unidade_nome: str
    configurada: bool
    ativo: bool
    ambiente: str
    mes: str
    checkins_mes: int
    checkins_validados_mes: int
    checkins_pendentes_mes: int
    variacao_checkins: float | None
    valor_repasse_checkin: Decimal | None
    valor_estimado_mes: Decimal
    reservas_mes: int
    rejeitadas_mes: int
    cancelamentos_mes: int
    eventos_com_erro: int
    slots_futuros: int
    passos: list[PassoOut]
    alertas: list[AlertaOut]
    serie: list[PontoSerie]
    ultimos_eventos: list[EventoOut]


class RelatorioUnidade(Base):
    unidade_id: int
    unidade_nome: str
    total: int
    validados: int
    valor_unitario: Decimal | None
    valor_estimado: Decimal


class RelatorioAluno(Base):
    aluno_id: int | None
    aluno_nome: str
    gympass_id: str | None
    total: int
    validados: int
    ultimo: date


class RelatorioOut(Base):
    ano: int
    mes: int
    total: int
    validados: int
    pendentes: int
    valor_estimado: Decimal
    validados_mes_anterior: int
    variacao: float | None
    alunos_distintos: int
    por_unidade: list[RelatorioUnidade]
    por_dia: list[PontoSerie]
    por_aluno: list[RelatorioAluno]


class ValidarCheckinIn(Base):
    aluno_id: int


class ValidacaoOut(Base):
    aplicavel: bool
    ok: bool
    mensagem: str
    ja_validado: bool
