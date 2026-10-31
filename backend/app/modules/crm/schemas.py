"""Entradas e saídas da API do CRM."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.modules.crm.models import (
    MarcoEtapa,
    OrigemLead,
    SituacaoLead,
    StatusAulaExperimental,
    TipoEtapa,
    TipoInteracao,
)


def _vazio(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


# ------------------------------------------------------------------------------------------------ etapas e motivos
class EtapaIn(BaseModel):
    nome: str = Field(min_length=2, max_length=60)
    cor: str = Field(default="#7C8FFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    marco: MarcoEtapa | None = None
    dias_alerta: int = Field(default=3, ge=0, le=90)


class EtapaOut(BaseModel):
    id: int
    nome: str
    ordem: int
    cor: str
    tipo: TipoEtapa
    marco: MarcoEtapa | None
    dias_alerta: int
    leads: int = 0


class OrdemIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=50)


class ExcluirEtapaIn(BaseModel):
    mover_para_id: int | None = None


class MotivoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    ativo: bool = True


class MotivoOut(BaseModel):
    id: int
    nome: str
    ativo: bool
    usos: int = 0


# ------------------------------------------------------------------------------------------------ leads
class LeadIn(BaseModel):
    """Criação e edição (na edição só os campos enviados mudam)."""

    nome: str | None = Field(default=None, min_length=2, max_length=150)
    telefone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    origem: OrigemLead | None = None
    indicado_por: str | None = Field(default=None, max_length=150)
    interesse: str | None = Field(default=None, max_length=150)
    responsavel_id: int | None = None
    valor_estimado: Decimal | None = Field(default=None, ge=0, max_digits=13, decimal_places=2)
    observacoes: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=20)
    etapa_id: int | None = None

    @field_validator("nome", "telefone", "email", "indicado_por", "interesse", "observacoes", mode="before")
    @classmethod
    def _limpa(cls, v):
        return _vazio(v)


class UsuarioMini(BaseModel):
    id: int
    nome: str


class LeadCartao(BaseModel):
    """O que o Kanban e a lista precisam."""

    id: int
    nome: str
    telefone: str | None
    telefone_formatado: str | None
    email: str | None
    origem: OrigemLead
    interesse: str | None
    responsavel: UsuarioMini | None
    valor_estimado: Decimal | None
    tags: list[str]
    etapa_id: int
    situacao: SituacaoLead
    dias_na_etapa: int
    parado: bool
    temperatura: str
    aula_experimental_em: datetime | None
    aula_experimental_status: StatusAulaExperimental | None
    tarefas_pendentes: int
    tarefa_atrasada: bool
    whatsapp_url: str | None
    criado_em: datetime
    ultima_interacao_em: datetime | None
    aluno_id: int | None


class ColunaFunil(BaseModel):
    etapa: EtapaOut
    leads: list[LeadCartao]
    total: int
    valor_total: Decimal


class Funil(BaseModel):
    colunas: list[ColunaFunil]


class ListaLeads(BaseModel):
    itens: list[LeadCartao]
    total: int
    pagina: int
    por_pagina: int
    contagens: dict[str, int]


class InteracaoIn(BaseModel):
    tipo: TipoInteracao
    descricao: str = Field(min_length=1, max_length=4000)
    ocorrido_em: datetime | None = None

    @field_validator("tipo")
    @classmethod
    def _sem_sistema(cls, v):
        if v == TipoInteracao.SISTEMA:
            raise ValueError("tipo reservado ao sistema")
        return v


class InteracaoOut(BaseModel):
    id: int
    tipo: TipoInteracao
    descricao: str
    usuario: UsuarioMini | None
    ocorrido_em: datetime


class TarefaIn(BaseModel):
    titulo: str = Field(min_length=2, max_length=150)
    descricao: str | None = Field(default=None, max_length=2000)
    vence_em: datetime
    responsavel_id: int | None = None
    lead_id: int | None = None

    @field_validator("descricao", mode="before")
    @classmethod
    def _limpa(cls, v):
        return _vazio(v)


class TarefaOut(BaseModel):
    id: int
    titulo: str
    descricao: str | None
    vence_em: datetime
    responsavel: UsuarioMini | None
    concluida: bool
    concluida_em: datetime | None
    situacao: str  # concluida | atrasada | hoje | futura
    automatica: bool
    lead_id: int | None
    lead_nome: str | None
    lead_telefone: str | None
    whatsapp_url: str | None


class ListaTarefas(BaseModel):
    itens: list[TarefaOut]
    contagens: dict[str, int]


class MovimentoOut(BaseModel):
    de: str | None
    para: str | None
    usuario: str | None
    em: datetime


class MensagemPronta(BaseModel):
    titulo: str
    texto: str
    url: str | None


class LeadFicha(LeadCartao):
    indicado_por: str | None
    observacoes: str | None
    etapa_nome: str
    motivo_perda_id: int | None
    motivo_perda: str | None
    motivo_perda_detalhe: str | None
    perdido_em: datetime | None
    ganho_em: datetime | None
    aula_experimental_profissional_id: int | None
    aula_experimental_profissional: str | None
    aula_experimental_unidade_id: int | None
    aula_experimental_obs: str | None
    sugestao: str | None
    mensagens: list[MensagemPronta]
    interacoes: list[InteracaoOut]
    tarefas: list[TarefaOut]
    movimentos: list[MovimentoOut]
    aluno_nome: str | None


class MoverIn(BaseModel):
    etapa_id: int
    motivo_perda_id: int | None = None
    motivo_perda_detalhe: str | None = Field(default=None, max_length=300)


class AulaExperimentalIn(BaseModel):
    data_hora: datetime
    profissional_id: int | None = None
    unidade_id: int | None = None
    observacao: str | None = Field(default=None, max_length=300)
    criar_lembrete: bool = True


class ResultadoAulaIn(BaseModel):
    compareceu: bool
    observacao: str | None = Field(default=None, max_length=1000)


class AlunoParecido(BaseModel):
    id: int
    nome: str
    motivo: str


class OpcaoSimples(BaseModel):
    id: int
    nome: str


class PreparoConversao(BaseModel):
    unidades: list[OpcaoSimples]
    parecidos: list[AlunoParecido]
    pode_criar_aluno: bool


class ConverterIn(BaseModel):
    """Cria o aluno (unidade obrigatória; CPF opcional) ou vincula a um aluno já cadastrado (`aluno_id`)."""

    aluno_id: int | None = None
    unidade_id: int | None = None
    cpf: str | None = Field(default=None, max_length=20)
    data_nascimento: date | None = None

    @field_validator("cpf", mode="before")
    @classmethod
    def _limpa(cls, v):
        return _vazio(v)


class ConverterOut(BaseModel):
    lead_id: int
    aluno_id: int
    aluno_nome: str
    criado: bool


# ------------------------------------------------------------------------------------------------ opções, resumo e relatório
class Opcoes(BaseModel):
    etapas: list[EtapaOut]
    motivos: list[MotivoOut]
    origens: list[dict[str, str]]
    usuarios: list[UsuarioMini]
    profissionais: list[OpcaoSimples]
    unidades: list[OpcaoSimples]
    tags: list[str]
    estudio: str


class Resumo(BaseModel):
    abertos: int
    novos_7_dias: int
    valor_em_negociacao: Decimal
    tarefas_hoje: int
    tarefas_atrasadas: int
    parados: int
    aulas_experimentais_hoje: int
    conversoes_30_dias: int
    taxa_conversao_30_dias: float
    destaque: str | None  # frase "uau" do topo (ex.: "3 leads quentes esperando proposta")


class RelatorioEtapa(BaseModel):
    etapa_id: int
    etapa: str
    cor: str
    tipo: str
    quantidade: int
    pct_total: float
    pct_anterior: float


class RelatorioOrigem(BaseModel):
    origem: OrigemLead
    rotulo: str
    total: int
    ganhos: int
    perdidos: int
    abertos: int
    taxa_conversao: float
    tempo_medio_dias: float | None


class RelatorioMotivo(BaseModel):
    motivo_id: int | None
    motivo: str
    quantidade: int
    pct: float


class Relatorio(BaseModel):
    de: date
    ate: date
    total_leads: int
    ganhos: int
    perdidos: int
    abertos: int
    taxa_conversao: float
    tempo_medio_dias: float | None
    valor_ganho: Decimal
    funil: list[RelatorioEtapa]
    por_origem: list[RelatorioOrigem]
    perdidos_por_motivo: list[RelatorioMotivo]
    melhor_origem: str | None
    gargalo: str | None
