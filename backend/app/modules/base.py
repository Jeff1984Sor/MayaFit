"""Peças comuns aos modelos do MayaFit (mixin do código legado e helper de enum)."""

import enum

from sqlalchemy import Enum, Integer
from sqlalchemy.orm import Mapped, mapped_column


class CodigoLegado:
    """Preserva o código do sistema antigo (`cdXxx`; nas tabelas sem código, o `id` antigo).

    Único e anulável: registros criados no sistema novo nascem com NULL ou recebem um código do
    contador transacional (`proximo_codigo`, em `cadastros.models`). Serve de chave de idempotência
    do ETL e é o `cdAluno` exposto aos integradores externos.
    """

    codigo_legado: Mapped[int | None] = mapped_column(Integer, unique=True)


def coluna_enum(cls: type[enum.Enum], tamanho: int = 30) -> Enum:
    """Enum guardado como texto (sem tipo nativo do banco), validado na escrita."""
    return Enum(cls, native_enum=False, length=tamanho, validate_strings=True)
