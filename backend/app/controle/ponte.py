"""Ponte entre as regras do admin MayaCorp e a fundação multi-tenant (`app.core.tenancy` e `app.controle.service`).

Tudo que o admin precisa da fundação passa por aqui, com import tardio: assim o admin carrega mesmo onde a fundação
ainda não existe (modo de um banco só, dev e testes dos módulos) e os testes trocam estas funções com monkeypatch.
"""

from contextlib import contextmanager
from types import SimpleNamespace


def service():
    """`app.controle.service` (fundação): provisionar, por_slug, coletar_uso, estudio_mayacorp, ..."""
    from app.controle import service as s

    return s


def _tenancy():
    try:
        from app.core import tenancy
    except ImportError:
        return None
    return tenancy


def atual():
    """Estúdio da requisição/tarefa atual (Estudio(slug, banco, mayacorp)) ou None no modo de um banco só."""
    t = _tenancy()
    return t.atual() if t is not None and hasattr(t, "atual") else None


def multi() -> bool:
    t = _tenancy()
    return bool(t is not None and hasattr(t, "multi") and t.multi())


@contextmanager
def usando(estudio):
    """Abre o banco de outro estúdio (SessionLocal passa a apontar para ele). Sem fundação: banco atual."""
    t = _tenancy()
    if t is None or estudio is None or not hasattr(t, "usando"):
        yield
        return
    with t.usando(estudio):
        yield


def estudio_de(c):
    """Estudio(slug, banco, mayacorp) de um Cliente do controle."""
    t = _tenancy()
    mayacorp = c.tipo == "mayacorp"
    if t is not None and hasattr(t, "Estudio"):
        return t.Estudio(slug=c.slug, banco=c.banco, mayacorp=mayacorp)
    return SimpleNamespace(slug=c.slug, banco=c.banco, mayacorp=mayacorp)


def endereco_do_painel() -> str | None:
    try:
        return service().endereco_do_painel()
    except ImportError:
        return None


def dominio_padrao(slug: str) -> str | None:
    try:
        return service().dominio_padrao(slug)
    except ImportError:
        return None


def limpar_cache() -> None:
    try:
        service().limpar_cache()
    except ImportError:
        pass
