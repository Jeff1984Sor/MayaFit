"""Bloqueio por plano (regra P8 de docs/ESPECIFICACAO.md): cada área da API pertence a um recurso do plano
(app/controle/planos.py › RECURSOS e EXTRAS). Estúdio sem o recurso recebe 403 com o plano que o libera; o frontend
mostra o cadeado com "Disponível no plano X" em vez de esconder a tela.

Só vale no modo um banco por estúdio, com o estúdio identificado. Com um banco só, ou no Admin MayaFit, tudo passa.
"""

import json
import re
import time

import anyio

from app.core import tenancy

# (rota, recurso) — a primeira que casar decide; a ordem importa (catraca antes do resto do controle de acesso)
AREAS: list[tuple[re.Pattern, str]] = [(re.compile(rx), recurso) for rx, recurso in [
    (r"^/api/crm(/|$)", "crm"),
    (r"^/api/site(-publico)?(/|$)", "site"),
    (r"^/api/acesso/catracas(/|$)", "catraca"),
    (r"^/api/catraca-agente(/|$)", "catraca"),
    (r"^/api/(acesso|totem)(/|$)", "checkin"),
    (r"^/api/aluno-app/acesso(/|$)", "checkin"),
    (r"^/api/aluno-app(/|$)", "app_aluno"),
    (r"^/api/whatsapp(/|$)", "whatsapp"),
    (r"^/api/(wellhub|integracao)(/|$)", "integracoes"),
    (r"^/api/integracoes/(totalpass|tokens)(/|$)", "integracoes"),
    (r"^/api/webhooks/(totalpass|wellhub)(/|$)", "integracoes"),
    (r"^/api/nfse(/|$)", "nfse"),
    (r"^/api/ia/", "ia"),
    (r"^/api/receita-saude(/|$)", "receita_saude"),
]]


def recurso_da_rota(caminho: str) -> str | None:
    for rx, recurso in AREAS:
        if rx.match(caminho):
            return recurso
    return None


_cache_planos: tuple[float, dict[str, str]] | None = None


def plano_que_libera(recurso: str) -> str | None:
    """Nome do plano mais barato (menor `ordem`) que traz o recurso; None se só existe como extra."""
    global _cache_planos
    agora = time.monotonic()
    if _cache_planos is None or agora - _cache_planos[0] > 300:
        from sqlalchemy import select

        from app.controle.models import Plano, SessaoControle

        mapa: dict[str, str] = {}
        with SessaoControle() as db:
            for p in db.scalars(select(Plano).where(Plano.ativo).order_by(Plano.ordem, Plano.preco_mensal)):
                for r in p.recursos or []:
                    mapa.setdefault(r, p.nome)
        _cache_planos = (agora, mapa)
    return _cache_planos[1].get(recurso)


def bloqueio(caminho: str) -> dict | None:
    """Corpo do 403 quando o estúdio atual não tem o recurso da rota; None = pode seguir."""
    recurso = recurso_da_rota(caminho)
    if recurso is None or not tenancy.multi():
        return None
    esc = tenancy.atual()
    if esc is None or esc.mayacorp:
        return None  # sem estúdio quem decide é a rota (login, público); o admin enxerga tudo
    liberados = tenancy.recursos()
    if liberados is None or recurso in liberados:
        return None
    from app.controle.planos import EXTRAS, RECURSOS

    nome = RECURSOS.get(recurso) or EXTRAS.get(recurso) or recurso
    plano = plano_que_libera(recurso)
    onde = f"Disponível a partir do plano {plano}." if plano else "Fale com o MayaFit para liberar."
    return {"detail": f"{nome} não está no seu plano. {onde}", "recurso": recurso, "plano": plano, "bloqueio": "plano"}


class RecursoDoPlanoMiddleware:
    """Roda depois do EstudioMiddleware (precisa do estúdio já definido)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or recurso_da_rota(scope.get("path", "")) is None:
            await self.app(scope, receive, send)
            return
        corpo = await anyio.to_thread.run_sync(bloqueio, scope["path"])  # consulta o controle (com cache)
        if corpo is None:
            await self.app(scope, receive, send)
            return
        dados = json.dumps(corpo, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"content-length", str(len(dados)).encode())]})
        await send({"type": "http.response.body", "body": dados})
