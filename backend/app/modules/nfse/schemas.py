"""Esquemas (entrada/saída) da API de NFS-e. Dinheiro como Decimal; o .pfx nunca sai pela API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.documentos import so_digitos


class ConfigIn(BaseModel):
    ativo: bool = False
    provedor: Literal["nacional", "sao_paulo"] = "nacional"
    modo: Literal["simulado", "homologacao", "producao"] = "simulado"
    cnpj: str | None = None
    razao_social: str | None = Field(None, max_length=150)
    inscricao_municipal: str | None = Field(None, max_length=15)
    codigo_municipio: str | None = None
    municipio_nome: str | None = Field(None, max_length=80)
    uf: str | None = Field(None, max_length=2)
    email: EmailStr | None = None
    telefone: str | None = Field(None, max_length=20)
    regime: Literal["mei", "simples", "presumido", "real"] = "simples"
    item_lista_servico: str = Field("06.04", max_length=5)
    codigo_servico_municipal: str | None = Field(None, max_length=20)
    nbs: str | None = Field(None, max_length=12)
    aliquota_iss: Decimal = Field(Decimal("2.00"), ge=0, le=5)
    iss_retido: bool = False
    informar_aliquota: bool = False
    percentual_tributos_sn: Decimal | None = Field(None, ge=0, le=99)
    discriminacao_modelo: str | None = Field(None, max_length=2000)
    serie: str = Field("1", max_length=5)
    proximo_numero: int = Field(1, ge=1)
    parametros_extras: dict[str, Any] | None = None
    emissao_automatica: bool = False
    automatica_desde: date | None = None
    enviar_email_aluno: bool = True

    @field_validator("cnpj", "codigo_municipio")
    @classmethod
    def _digitos(cls, v: str | None) -> str | None:
        return so_digitos(v) or None

    @field_validator("serie")
    @classmethod
    def _serie(cls, v: str) -> str:
        d = so_digitos(v)
        if not d or int(d) == 0:
            raise ValueError("a série deve ser numérica (ex.: 1)")
        return str(int(d))


class CertificadoOut(BaseModel):
    configurado: bool
    titular: str | None = None
    cnpj: str | None = None
    emissor: str | None = None
    valido_de: date | None = None
    valido_ate: date | None = None
    situacao: str
    dias: int | None = None
    mensagem: str
    cnpj_confere: bool | None = None


class ConfigOut(ConfigIn):
    model_config = ConfigDict(from_attributes=True)

    email: str | None = None
    codigo_tributacao_nacional: str
    certificado: CertificadoOut
    emissao_real_liberada: bool
    ambiente_servidor: str
    pendencias: list[dict[str, Any]]
    provedor_rotulo: str


class MunicipioOut(BaseModel):
    codigo_municipio: str | None
    municipio_nome: str | None
    uf: str | None
    provedor: str
    suportado: bool
    mensagem: str


class TomadorIn(BaseModel):
    tipo: Literal["aluno", "pessoa", "empresa"] = "aluno"
    aluno_id: int | None = None
    documento: str | None = None
    nome: str | None = Field(None, max_length=150)
    email: EmailStr | None = None
    endereco: dict[str, Any] | None = None

    @field_validator("documento")
    @classmethod
    def _doc(cls, v: str | None) -> str | None:
        return so_digitos(v) or None


class NotaAvulsaIn(BaseModel):
    tomador: TomadorIn
    valor: Decimal = Field(gt=0, max_digits=13, decimal_places=2)
    competencia: date | None = None
    descricao: str | None = Field(None, max_length=200)  # vira {descricao} no modelo
    discriminacao: str | None = Field(None, max_length=2000)  # texto final (substitui o modelo)
    conta_receber_id: int | None = None


class RecebimentosIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class RaioXIn(BaseModel):
    avulsa: NotaAvulsaIn | None = None
    recebimentos: list[int] | None = None


class CorrecaoIn(BaseModel):
    """Correção de uma nota rejeitada antes de reenviar."""

    tomador_documento: str | None = None
    tomador_nome: str | None = Field(None, max_length=150)
    tomador_email: EmailStr | None = None
    discriminacao: str | None = Field(None, max_length=2000)
    competencia: date | None = None

    @field_validator("tomador_documento")
    @classmethod
    def _doc(cls, v: str | None) -> str | None:
        return so_digitos(v) or None


class CancelarIn(BaseModel):
    codigo: Literal["1", "2", "9"] = "1"
    motivo: str = Field(min_length=15, max_length=255)


class EventoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo: str
    descricao: str
    criado_em: datetime


class NotaResumo(BaseModel):
    id: int
    status: str
    origem: str
    provedor: str
    modo: str
    serie: str
    numero_dps: int
    numero_nfse: str | None
    tomador_nome: str
    tomador_documento: str | None
    competencia: date
    valor_servico: Decimal
    valor_iss: Decimal
    emitida_em: datetime | None
    criado_em: datetime
    conta_receber_id: int | None
    aluno_id: int | None
    tentativas: int
    erro_principal: str | None
    tem_pdf: bool
    link_oficial: str | None


class NotaDetalhe(NotaResumo):
    chave_emissao: str
    id_dps: str | None
    chave_acesso: str | None
    codigo_verificacao: str | None
    tomador_email: str | None
    tomador_tipo: str
    discriminacao: str
    item_lista_servico: str
    codigo_tributacao_nacional: str
    codigo_servico_municipal: str | None
    aliquota: Decimal
    deducoes: Decimal
    iss_retido: bool
    regime: str
    erros: list[dict[str, Any]]
    alertas: list[dict[str, Any]]
    tem_xml_enviado: bool
    tem_xml_retorno: bool
    cancelada_em: datetime | None
    motivo_cancelamento: str | None
    email_enviado_em: datetime | None
    proxima_tentativa_em: datetime | None
    eventos: list[EventoOut]
    pode_cancelar: bool
    pode_reprocessar: bool


class ListaNotas(BaseModel):
    itens: list[NotaResumo]
    total: int
    pagina: int
    por_pagina: int
    contagens: dict[str, int]


class RecebimentoOut(BaseModel):
    id: int
    aluno_id: int
    aluno_nome: str
    aluno_cpf: str | None
    aluno_email: str | None
    descricao: str | None
    valor: Decimal
    vencimento: date
    pagamento: date | None
    competencia: str | None
    nota_id: int | None
    nota_status: str | None
    nota_numero: str | None
    problema: str | None


class LoteOut(BaseModel):
    lote: str
    criadas: int
    ja_existiam: int
    ignoradas: list[dict[str, Any]]
    processadas_agora: int
    notas: list[NotaResumo]


class TomadorBusca(BaseModel):
    id: int
    nome: str
    cpf_mascarado: str | None
    tem_cpf: bool
    email: str | None
