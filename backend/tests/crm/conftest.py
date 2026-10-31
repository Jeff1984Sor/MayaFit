"""Fixtures do CRM: dados sintéticos (nenhum dado real)."""

import pytest

from app.modules import registrar_modelos
from app.modules.cadastros.models import Profissional, Unidade
from app.modules.crm import models as _crm_models  # noqa: F401  (garante as tabelas no create_all)
from tests.conftest import auth, criar_usuario, entrar

registrar_modelos()


@pytest.fixture
def h(token_admin):
    return auth(token_admin)


@pytest.fixture
def base(db):
    un = Unidade(nome="Unidade Centro", capacidade=4)
    prof = Profissional(nome="Prof Bia")
    db.add_all([un, prof])
    db.commit()
    return {"unidade_id": un.id, "profissional_id": prof.id}


@pytest.fixture
def opcoes(client, h):
    return client.get("/api/crm/opcoes", headers=h).json()


@pytest.fixture
def etapa(opcoes):
    """Etapa pelo nome padrão."""
    mapa = {e["nome"]: e for e in opcoes["etapas"]}
    return lambda nome: mapa[nome]


@pytest.fixture
def novo_lead(client, h):
    def _criar(**extra):
        corpo = {"nome": "Carla Teste", "telefone": "(11) 98888-7777", "origem": "instagram"}
        corpo.update(extra)
        r = client.post("/api/crm/leads", json=corpo, headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    return _criar


@pytest.fixture
def h_secretaria(client, db):
    criar_usuario(db, "Secretária", email="sec@exemplo.com")
    return auth(entrar(client, "sec@exemplo.com").json()["access_token"])


@pytest.fixture
def h_professor(client, db):
    criar_usuario(db, "Professor", email="prof@exemplo.com")
    return auth(entrar(client, "prof@exemplo.com").json()["access_token"])
