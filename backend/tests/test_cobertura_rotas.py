"""Falha se existir rota no app que não esteja no mapa de permissões nem na lista explícita PUBLICAS.

Este teste é o que sustenta o "negar por padrão": quem criar uma rota nova sem regra em app/core/permissoes.py quebra aqui.
"""

import re

from fastapi.routing import APIRoute

from app.core.deps import get_contexto
from app.core.permissoes import permissao_da_rota, rota_autenticacao_propria, rota_publica
from app.main import app


def _depende_de(dependant, alvo) -> bool:
    if dependant.call is alvo:
        return True
    return any(_depende_de(d, alvo) for d in dependant.dependencies)


def _efetivas():
    """Rotas já com prefixo e dependências do include_router (FastAPI novo inclui routers de forma preguiçosa)."""
    for r in app.routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "effective_route_contexts"):
            yield from r.effective_route_contexts()


def _rotas():
    for r in _efetivas():
        caminho = re.sub(r"\{[^}]+\}", "1", r.path)
        for metodo in r.methods - {"HEAD", "OPTIONS"}:
            yield r, metodo, caminho


def test_ha_rotas_para_verificar():
    assert len(list(_rotas())) > 25


def test_toda_rota_esta_no_mapa_ou_e_publica():
    sem_regra = []
    for r, metodo, caminho in _rotas():
        if rota_publica(metodo, caminho) or rota_autenticacao_propria(caminho):
            continue
        mapeada, _ = permissao_da_rota(metodo, caminho)
        if not mapeada:
            sem_regra.append(f"{metodo} {r.path}")
    assert not sem_regra, "Rotas sem permissão mapeada (adicione em app/core/permissoes.py): " + ", ".join(sem_regra)


def test_toda_rota_protegida_exige_login():
    abertas = []
    for r, metodo, caminho in _rotas():
        if rota_publica(metodo, caminho) or rota_autenticacao_propria(caminho):
            continue
        if not _depende_de(r.dependant, get_contexto):
            abertas.append(f"{metodo} {r.path}")
    assert not abertas, "Rotas protegidas sem login obrigatório: " + ", ".join(abertas)


def test_rotas_publicas_sao_so_as_esperadas():
    publicas = sorted(f"{m} {r.path}" for r, m, c in _rotas() if rota_publica(m, c))
    assert publicas == sorted([
        "GET /api/health", "POST /api/auth/login", "POST /api/auth/refresh", "POST /api/auth/forgot", "POST /api/auth/reset",
        "POST /api/auth/forgot-codigo", "POST /api/auth/reset-codigo", "GET /api/public/identidade", "GET /api/public/logo",
        "GET /api/arquivos-publicos/{token}", "GET /api/auth/primeiro-acesso", "POST /api/auth/primeiro-acesso",
    ])


def test_rotas_publicas_de_credencial_tem_rate_limit():
    from app.core.ratelimit import limitar

    esperadas = {"/api/auth/login", "/api/auth/refresh", "/api/auth/forgot", "/api/auth/reset", "/api/auth/forgot-codigo",
                 "/api/auth/reset-codigo", "/api/arquivos-publicos/{token}", "/api/public/identidade", "/api/public/logo",
                 "/api/auth/primeiro-acesso"}
    sem_limite = []
    for r, _metodo, _caminho in _rotas():
        if r.path in esperadas:
            nomes = [getattr(d.call, "__qualname__", "") for d in r.dependant.dependencies]
            if not any("limitar" in n for n in nomes):
                sem_limite.append(r.path)
    assert not sem_limite, sem_limite
    assert limitar


def test_rotas_de_autenticacao_propria_declaram_alguma_dependencia():
    sem_auth = [f"{m} {r.path}" for r, m, c in _rotas() if rota_autenticacao_propria(c) and not r.dependant.dependencies]
    assert not sem_auth, "Rotas com autenticação própria sem nenhuma dependência de autenticação: " + ", ".join(sem_auth)


def test_docs_desligados_fora_do_debug():
    from app.core.config import settings

    if not settings.debug:
        assert app.docs_url is None and app.openapi_url is None
