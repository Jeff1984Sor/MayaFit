"""Um banco por estúdio (cliente do MayaFit). Portado do MayaJus (app/core/tenancy.py).

Sem o banco `mayafit_controle` (no mesmo servidor do DATABASE_URL; no SQLite, `data/mayafit_controle.db`) o sistema
roda como sempre: um banco só, a pasta `storage/`. Quando ele existe, o modo liga sozinho (nada no .env): o banco de
controle (app/controle) diz quais estúdios existem e em qual banco mora cada um; o estúdio do pedido atual fica numa
ContextVar e é ela que decide o banco de toda sessão (`SessionLocal`, `get_db`) e a pasta dos arquivos. Quem define:

- a API, a cada pedido (app/core/estudio_http.py): pelo token (claim `est`) ou pelo endereço do estúdio;
- o login, pelo endereço ou pelo catálogo de logins do controle;
- o worker, que percorre os estúdios ativos.

O estúdio "principal" (banco = None) usa o `DATABASE_URL` e a pasta `storage/` de antes.
"""

import contextvars
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from app.core.config import settings


@dataclass(frozen=True)
class Estudio:
    slug: str
    banco: str | None  # None = o banco principal (DATABASE_URL)
    mayacorp: bool = False  # o admin da MayaCorp (mesmos módulos + o menu MayaCorp)


class EstudioNaoIdentificado(RuntimeError):
    """Pedido sem estúdio no modo multi: vira 401 "Sessão expirada" (main.py)."""


BANCO_CONTROLE = "mayafit_controle"

_atual: contextvars.ContextVar[Estudio | None] = contextvars.ContextVar("estudio", default=None)
_engines: dict[str, Engine] = {}
_trava = threading.Lock()
_url_forcada: str | None = None  # testes apontam para um controle próprio
_multi: bool | None = None


def forcar_controle(url: str | None) -> None:
    """Testes: usa este banco de controle (None = volta a detectar)."""
    global _url_forcada, _multi
    _url_forcada, _multi = url, None


def url_controle() -> str:
    return _url_forcada or url_do_banco(BANCO_CONTROLE)


def _controle_existe() -> bool:
    from sqlalchemy import text

    from app.core.db import engine

    url = make_url(url_do_banco(BANCO_CONTROLE))
    if url.get_backend_name() == "sqlite":
        return Path(url.database or "").exists()
    with engine.connect() as conn:  # se o servidor estiver fora, falha alto (não liga o modo errado)
        return bool(conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": BANCO_CONTROLE}))


def multi() -> bool:
    """Um banco por estúdio? Liga sozinho quando o banco de controle existe (decidido uma vez por processo)."""
    global _multi
    if _multi is None:
        _multi = _url_forcada is not None or _controle_existe()
    return _multi


def atual() -> Estudio | None:
    return _atual.get()


def definir(esc: Estudio | None) -> contextvars.Token:
    return _atual.set(esc)


@contextmanager
def usando(esc: Estudio | None) -> Iterator[None]:
    token = _atual.set(esc)
    try:
        yield
    finally:
        _atual.reset(token)


def url_do_banco(banco: str) -> str:
    """Mesmo servidor e credenciais do DATABASE_URL, outro banco (no SQLite, outro arquivo ao lado)."""
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        return f"sqlite:///{Path(url.database or 'data/dev.db').with_name(f'{banco}.db').as_posix()}"
    return url.set(database=banco).render_as_string(hide_password=False)


def engine_do(banco: str | None) -> Engine:
    from app.core.db import engine, ligar_pragmas_sqlite

    if banco is None:
        return engine
    with _trava:
        if banco not in _engines:
            url = url_do_banco(banco)
            if url.startswith("sqlite"):
                e = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
                ligar_pragmas_sqlite(e)
            else:  # servidor compartilhado: poucas conexões por estúdio
                e = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=3, pool_recycle=1800)
            _engines[banco] = e
        return _engines[banco]


def descartar_engines() -> None:
    """Testes/CLI: fecha as conexões dos bancos dos estúdios."""
    with _trava:
        for e in _engines.values():
            e.dispose()
        _engines.clear()


def engine_atual() -> Engine:
    esc = atual()
    if esc is None:
        if multi():
            raise EstudioNaoIdentificado("Estúdio não identificado para este acesso.")
        return engine_do(None)
    return engine_do(esc.banco)


def pasta_base() -> Path:
    """Raiz dos arquivos do estúdio atual (o principal continua em storage/, os demais em storage/estudios/<slug>)."""
    esc = atual()
    if esc is None or esc.banco is None:
        return Path(settings.storage_dir)
    return Path(settings.storage_dir) / "estudios" / esc.slug


def com_estudio(fn: Callable) -> Callable:
    """Leva o estúdio atual para outra thread (ThreadPoolExecutor/threading não copiam a ContextVar)."""
    ctx = contextvars.copy_context()
    return lambda *a, **kw: ctx.run(fn, *a, **kw)


def claims() -> dict[str, Any]:
    """O estúdio que viaja nos tokens emitidos agora (`est`). Vazio com um banco só."""
    esc = atual()
    return {"est": esc.slug} if esc is not None and multi() else {}


def token_do_estudio_atual(payload: dict[str, Any]) -> bool:
    """O token foi emitido para o estúdio deste pedido? (Sempre True com um banco só.)"""
    if not multi():
        return True
    esc = atual()
    return esc is not None and payload.get("est") == esc.slug


def recursos() -> list[str] | None:
    """Recursos liberados ao estúdio atual (os do plano + `Cliente.extras`). None = um banco só (tudo liberado)."""
    if not multi():
        return None
    esc = atual()
    if esc is None:
        return []
    from app.controle import service

    return service.recursos_do(esc.slug)
