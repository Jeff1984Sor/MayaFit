"""Corpos das rotas do admin MayaCorp (mesmos nomes do MayaJus, com estúdio/extras/alunos ativos)."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.controle.planos import DIAS_TESTE_PADRAO


# ---------------------------------------------------------------- planos e política
class PlanoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=60)
    preco_mensal: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    preco_anual: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    usuarios: int | None = Field(default=None, ge=1)  # vazio = ilimitado
    alunos_ativos: int | None = Field(default=None, ge=1)  # vazio = ilimitado
    preco_aluno_excedente: Decimal = Field(default=Decimal("0.50"), ge=0, max_digits=10, decimal_places=2)
    preco_usuario_adicional: Decimal = Field(default=Decimal("14.90"), ge=0, max_digits=10, decimal_places=2)
    recursos: list[str] = []
    ativo: bool = True
    ordem: int = 0


class PoliticaIn(BaseModel):
    desconto_por_indicacao: Decimal = Field(gt=0, le=10)
    desconto_maximo: Decimal = Field(gt=0, le=10)  # nunca acima de 10% da mensalidade


class SenhaSuporteIn(BaseModel):
    senha: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------- estúdios
class FichaIn(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    documento: str | None = None
    responsavel: str | None = Field(default=None, max_length=150)
    email_financeiro: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=30)
    plano_id: int | None = None
    ciclo: Literal["mensal", "anual"] = "mensal"
    inicio_contrato: date | None = None
    teste_ate: date | None = None
    observacao: str | None = None
    indicado_por_id: int | None = None
    extras: list[str] | None = None  # ausente = não mexe nos extras liberados


class ClienteNovoIn(FichaIn):
    slug: str | None = Field(default=None, max_length=39)
    admin_nome: str = Field(default="", max_length=150)  # quem recebe as boas-vindas (opcional)
    admin_email: EmailStr  # recebe o link de boas-vindas e cria o usuário master
    dias_teste: int | None = Field(default=DIAS_TESTE_PADRAO, ge=0, le=120)  # 0 ou vazio = sem teste
    dominios: list[str] = []


class StatusIn(BaseModel):
    status: Literal["teste", "ativo", "suspenso", "inativo"]
    teste_ate: date | None = None  # ao voltar para "teste", até quando


class DominioIn(BaseModel):
    host: str = Field(min_length=4, max_length=253)


class UsuarioEstudioIn(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr
    login: str | None = Field(default=None, max_length=60)  # vazio = gerado do e-mail
    perfil: Literal["Full", "Secretária", "Professor"] = "Full"


class AtivoIn(BaseModel):
    ativo: bool


# ---------------------------------------------------------------- contratos
class ModeloIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    corpo: str = Field(min_length=10)
    ativo: bool = True


class GerarContratoIn(BaseModel):
    modelo_id: int


class ContratoEdicaoIn(BaseModel):
    titulo: str = Field(min_length=2, max_length=200)
    corpo: str = Field(min_length=10)


class EnviarContratoIn(BaseModel):
    para: list[EmailStr] = Field(min_length=1)
    mensagem: str | None = None


class ContratoStatusIn(BaseModel):
    status: Literal["assinado", "cancelado"]


# ---------------------------------------------------------------- IA
class TextoIAIn(BaseModel):
    texto: str = Field(min_length=10, max_length=8000)


class ContratoIAIn(BaseModel):
    instrucao: str | None = Field(default=None, max_length=2000)
    corpo: str | None = Field(default=None, max_length=30000)


class MensagemIAIn(BaseModel):
    titulo: str = Field(max_length=200)
    cliente_id: int
    instrucao: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------- cobrança
class ConfigCobrancaIn(BaseModel):
    token: str | None = Field(default=None, max_length=300)  # vazio = mantém o atual
    segredo: str | None = Field(default=None, max_length=300)
    dia_vencimento: int = Field(ge=1, le=28)
    gerar_automatico: bool
    regua: list[int] = Field(max_length=8)


class AvulsaIn(BaseModel):
    cliente_id: int
    descricao: str = Field(min_length=3, max_length=200)
    valor: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    vencimento: date
    enviar: bool = True


class GerarIn(BaseModel):
    competencia: str = Field(pattern=r"^\d{4}-\d{2}$")
    enviar: bool = True


class BaixaIn(BaseModel):
    forma: str = Field(default="manual", max_length=30)


class FormaIn(BaseModel):
    forma_pagamento: Literal["link", "cartao"]


class TrocaPlanoIn(BaseModel):
    plano_id: int
    ciclo: Literal["mensal", "anual"] = "mensal"


# ---------------------------------------------------------------- cadastro pelo site
class CadastroIn(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    documento: str | None = Field(default=None, max_length=20)
    responsavel: str = Field(min_length=3, max_length=150)
    email: EmailStr
    telefone: str = Field(min_length=8, max_length=30)
    plano_id: int | None = None
    ciclo: Literal["mensal", "anual"] = "mensal"
    alunos: int | None = Field(default=None, ge=0, le=100000)  # quantos alunos ativos tem hoje
    indicacao: str | None = Field(default=None, max_length=200)
    mensagem: str | None = Field(default=None, max_length=2000)
    aceite: bool
    site: str | None = None  # isca para robôs: campo escondido, gente de verdade deixa vazio


class AprovarIn(BaseModel):
    dias_teste: int | None = Field(default=DIAS_TESTE_PADRAO, ge=0, le=120)
    slug: str | None = Field(default=None, max_length=39)


# ---------------------------------------------------------------- ações de um clique (ficha do estúdio)
class EstenderTesteIn(BaseModel):
    dias: int = Field(ge=1, le=90)


class MotivoIn(BaseModel):
    motivo: str | None = Field(default=None, max_length=300)


class TokenIn(BaseModel):
    token: str = Field(max_length=2000)
    dias_teste: int | None = Field(default=DIAS_TESTE_PADRAO, ge=0, le=120)
