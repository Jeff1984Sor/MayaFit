"""Peças comuns das rotas do admin: guarda de acesso, saídas (dict) e leituras do banco de controle."""

import re
import unicodedata
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import object_session

from app.controle import cobranca, indicacao, ponte
from app.controle.eventos import STATUS  # noqa: F401 (reexportado para as rotas)
from app.controle.models import Cliente, Plano
from app.core.deps import Contexto, Ctx

EXCLUSIVO = "Área exclusiva do admin MayaFit."


def _painel(ctx: Ctx) -> Contexto:
    """Toda rota /api/admin/*: só no estúdio MayaCorp e só para administradores."""
    est = ponte.atual()
    if not (est is not None and getattr(est, "mayacorp", False)) or not ctx.usuario.administrador:
        raise HTTPException(403, EXCLUSIVO)
    return ctx


Painel = Annotated[Contexto, Depends(_painel)]


def erro(e: Exception):
    raise HTTPException(400, str(e)) from e


def regra_controle():
    """Exceção de regra do service (fundação); sem fundação, uma que nunca acontece."""
    try:
        return ponte.service().RegraControle
    except (ImportError, AttributeError):
        return _Nunca


class _Nunca(Exception):
    pass


# ================================================================ saídas
def d(v: Decimal | None) -> str | None:
    """Dinheiro sai como texto ("189.00"), nunca como float."""
    return None if v is None else f"{Decimal(v):.2f}"


def plano_out(p: Plano | None) -> dict | None:
    if not p:
        return None
    return {"id": p.id, "nome": p.nome, "preco_mensal": d(p.preco_mensal), "preco_anual": d(p.preco_anual),
            "usuarios": p.usuarios, "alunos_ativos": p.alunos_ativos,
            "preco_aluno_excedente": d(p.preco_aluno_excedente),
            "preco_usuario_adicional": d(p.preco_usuario_adicional), "recursos": p.recursos or [], "ativo": p.ativo,
            "ordem": p.ordem}


def uso_out(u: dict) -> dict:
    return {**u, "valor_excedente": d(u["valor_excedente"])}


def dominios_out(c: Cliente) -> tuple[list[dict], str | None]:
    padrao = ponte.dominio_padrao(c.slug)
    return [{"id": x.id, "host": x.host, "padrao": x.host == padrao} for x in c.dominios], padrao


def cliente_base(c: Cliente) -> dict:
    doms, padrao = dominios_out(c)
    return {"id": c.id, "slug": c.slug, "nome": c.nome, "status": c.status,
            "status_rotulo": STATUS.get(c.status, c.status), "teste_ate": c.teste_ate, "criado_em": c.criado_em,
            "documento": c.documento, "responsavel": c.responsavel, "email_financeiro": c.email_financeiro,
            "telefone": c.telefone, "plano": plano_out(c.plano), "plano_id": c.plano_id, "ciclo": c.ciclo,
            "valor": d(cobranca.valor_ciclo(c)), "inicio_contrato": c.inicio_contrato, "observacao": c.observacao,
            "banco_principal": c.banco is None, "dominios": doms, "dominio_padrao": padrao,
            "extras": c.extras or [], "forma_pagamento": c.forma_pagamento,
            "assinatura_status": c.mp_assinatura_status}


def cliente_out(c: Cliente) -> dict:
    db = object_session(c)
    n, pct = indicacao.desconto(db, c)
    com_desconto = indicacao.aplicar(cobranca.valor_ciclo(c), pct)
    u = cobranca.calcular_uso(c.plano, c.uso)  # só a foto: a lista não abre o banco de cada estúdio
    estimada = None
    if com_desconto is not None:
        base = com_desconto if c.ciclo == "mensal" and c.forma_pagamento != "cartao" else Decimal(0)
        estimada = base + u["valor_excedente"]
    return {**cliente_base(c),
            "indicado_por": {"id": c.indicado_por.id, "nome": c.indicado_por.nome} if c.indicado_por else None,
            "indicado_por_id": c.indicado_por_id, "indicacoes_ativas": n, "desconto_percentual": d(pct),
            "valor_com_desconto": d(com_desconto), "uso": uso_out(u), "mensalidade_estimada": d(estimada)}


def cliente(db, cid: int) -> Cliente:
    c = db.get(Cliente, cid)
    if not c or c.tipo != "estudio":
        raise HTTPException(404, "Estúdio não encontrado.")
    return c


def slug_de(nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:30].strip("-") or "estudio"
    return base if base[0].isalpha() else f"e-{base}"
