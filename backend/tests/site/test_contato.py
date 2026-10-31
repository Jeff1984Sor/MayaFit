"""Formulário "Agende sua aula experimental": LGPD, anti-spam, rate limit, histórico e CRM."""

import sys
import types

import pytest
from sqlalchemy import select

from app.modules.site.models import SiteContato
from tests.site.conftest import CONTATO_OK, publicar


@pytest.fixture
def no_ar(client, h_admin, estudio):
    publicar(client, h_admin)


def _contatos(db):
    db.expire_all()
    return list(db.scalars(select(SiteContato)))


@pytest.fixture
def sem_crm(monkeypatch):
    """Garante o caminho "CRM ainda não existe" (import falha), mesmo que o módulo exista na integração."""
    monkeypatch.setitem(sys.modules, "app.modules.crm", None)


def test_contato_e_guardado_no_historico(client, no_ar, db, sem_crm):
    r = client.post("/api/site-publico/contato", json=CONTATO_OK)
    assert r.status_code == 201, r.text
    [c] = _contatos(db)
    assert c.nome == "Visitante Teste" and c.quer_aula_experimental and not c.enviado_crm and c.lead_id is None
    assert c.consentimento_em is not None and "política de privacidade" in c.consentimento_texto


def test_sem_consentimento_lgpd_e_recusado(client, no_ar, db):
    r = client.post("/api/site-publico/contato", json={**CONTATO_OK, "consentimento": False})
    assert r.status_code == 422 and "LGPD" in r.json()["detail"]
    assert _contatos(db) == []


@pytest.mark.parametrize("extra", [{"website": "http://spam.example"}, {"tempo_ms": 300}])
def test_robo_recebe_ok_mas_nada_e_gravado(client, no_ar, db, extra):
    r = client.post("/api/site-publico/contato", json={**CONTATO_OK, **extra})
    assert r.status_code == 201
    assert _contatos(db) == []


def test_site_fora_do_ar_nao_recebe_contato(client, estudio, db):
    assert client.post("/api/site-publico/contato", json=CONTATO_OK).status_code == 404


def test_rate_limit_do_formulario(client, no_ar, sem_crm):
    codigos = [client.post("/api/site-publico/contato", json=CONTATO_OK).status_code for _ in range(6)]
    assert codigos[:5] == [201] * 5 and codigos[5] == 429


def _crm_falso(monkeypatch, fn):
    pacote = types.ModuleType("app.modules.crm")
    servico = types.ModuleType("app.modules.crm.servico")
    servico.criar_lead = fn
    pacote.servico = servico
    monkeypatch.setitem(sys.modules, "app.modules.crm", pacote)
    monkeypatch.setitem(sys.modules, "app.modules.crm.servico", servico)


def test_contato_vira_lead_no_crm(client, no_ar, db, monkeypatch):
    chamadas = []

    def criar_lead(db, *, nome, telefone=None, email=None, origem="site", interesse=None, mensagem=None,
                   quer_aula_experimental=False):
        chamadas.append(dict(nome=nome, telefone=telefone, email=email, origem=origem, interesse=interesse,
                             mensagem=mensagem, quer_aula_experimental=quer_aula_experimental))
        return types.SimpleNamespace(id=42)

    _crm_falso(monkeypatch, criar_lead)
    assert client.post("/api/site-publico/contato", json=CONTATO_OK).status_code == 201
    assert chamadas == [dict(nome="Visitante Teste", telefone="(11) 98888-1234", email="visita@exemplo.com",
                             origem="site", interesse="Pilates", mensagem="Quero conhecer", quer_aula_experimental=True)]
    [c] = _contatos(db)
    assert c.enviado_crm and c.lead_id == 42 and c.erro_crm is None


def test_falha_no_crm_nao_perde_o_contato(client, no_ar, db, monkeypatch):
    def quebra(db, **_):
        raise RuntimeError("CRM fora")

    _crm_falso(monkeypatch, quebra)
    assert client.post("/api/site-publico/contato", json=CONTATO_OK).status_code == 201
    [c] = _contatos(db)
    assert not c.enviado_crm and c.erro_crm == "CRM fora"


def test_lista_de_contatos_e_marcar_lido(client, no_ar, h_admin, sem_crm):
    client.post("/api/site-publico/contato", json=CONTATO_OK)
    client.post("/api/site-publico/contato", json={**CONTATO_OK, "nome": "Outra Pessoa"})
    lista = client.get("/api/site/contatos", headers=h_admin).json()
    assert lista["total"] == 2 and lista["nao_lidos"] == 2
    assert lista["itens"][0]["nome"] == "Outra Pessoa"  # mais recente primeiro
    assert client.get("/api/site", headers=h_admin).json()["contatos_nao_lidos"] == 2
    cid = lista["itens"][0]["id"]
    assert client.post(f"/api/site/contatos/{cid}/lido", headers=h_admin).json()["lido"] is True
    assert client.post("/api/site/contatos/lidos", headers=h_admin).status_code == 200
    assert client.get("/api/site/contatos", headers=h_admin).json()["nao_lidos"] == 0
    assert client.post("/api/site/contatos/999/lido", headers=h_admin).status_code == 404
