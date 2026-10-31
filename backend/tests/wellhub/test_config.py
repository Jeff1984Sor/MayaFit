"""Configuração do Wellhub: credenciais somente escrita e cifradas, testar conexão/webhook, produtos, mapeamento, permissões."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from sqlalchemy import func, select

from app.core import segredos
from app.core.models import Auditoria
from app.modules.cadastros.models import TipoServico, Unidade
from app.modules.wellhub import cliente as cli
from app.modules.wellhub.models import WellhubConfig, WellhubMapeamento
from tests.wellhub.conftest import API_KEY, BASE, GYM, SEGREDO, Wellhub, instalar

URL = "/api/wellhub"


def cfg_url(base):
    return f"{URL}/unidades/{base.uid}"


def test_tela_lista_unidades_sem_criar_nada(client, db, base, full):
    r = client.get(URL, headers=full)
    assert r.status_code == 200
    c = r.json()["configuracoes"][0]
    assert r.json()["webhook_caminho"] == "/api/webhooks/wellhub"
    assert c["configurada"] is False and c["ativo"] is False and c["ambiente"] == "sandbox"
    assert c["api_key"] == {"definido": False, "final": None} and c["mapeamentos"] == []
    assert [s["nome"] for s in r.json()["servicos"]] == ["Pilates"]
    assert db.scalar(select(func.count()).select_from(WellhubConfig)) == 0


def test_segredos_somente_escrita_e_cifrados(client, db, base, full):
    r = client.put(cfg_url(base), headers=full, json={"gym_id": GYM, "api_key": API_KEY, "webhook_secret": SEGREDO})
    assert r.status_code == 200, r.text
    assert r.json()["api_key"] == {"definido": True, "final": "1234"}
    assert r.json()["webhook_secret"] == {"definido": True, "final": "5678"}
    for resp in (r, client.get(URL, headers=full)):
        assert API_KEY not in resp.text and SEGREDO not in resp.text and "_cifrado" not in resp.text
    db.expire_all()
    cfg = db.scalar(select(WellhubConfig))
    assert API_KEY not in cfg.api_key_cifrado and segredos.decifrar_texto(cfg.api_key_cifrado.encode()) == API_KEY
    assert segredos.decifrar_texto(cfg.webhook_secret_cifrado.encode()) == SEGREDO
    # salvar sem os segredos mantém; vazio mantém; limpar é explícito
    r = client.put(cfg_url(base), headers=full, json={"sync_dias": 14, "api_key": "  "})
    assert r.json()["api_key"]["definido"] is True and r.json()["sync_dias"] == 14 and r.json()["gym_id"] == GYM
    r = client.put(cfg_url(base), headers=full, json={"limpar": ["api_key"]})
    assert r.json()["api_key"] == {"definido": False, "final": None} and r.json()["webhook_secret"]["definido"] is True


def test_auditoria_registra_a_troca_sem_o_valor(client, db, base, full):
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM, "api_key": API_KEY, "webhook_secret": SEGREDO})
    gerado = client.post(cfg_url(base) + "/segredo-webhook", headers=full).json()["valor"]
    db.expire_all()
    linhas = list(db.scalars(select(Auditoria).where(Auditoria.entidade == "wellhub_config").order_by(Auditoria.id)))
    assert [a.acao for a in linhas] == ["wellhub.configurar", "wellhub.gerar_segredo_webhook"]
    tudo = " ".join(f"{a.descricao} {a.antes_json} {a.depois_json}" for a in linhas)
    assert API_KEY not in tudo and SEGREDO not in tudo and gerado not in tudo
    assert "api_key: alterado" in tudo and "webhook_secret: alterado" in tudo


def test_segredo_gerado_aparece_uma_vez(client, base, full):
    r = client.post(cfg_url(base) + "/segredo-webhook", headers=full)
    assert r.status_code == 200 and r.json()["valor"].startswith("whs_") and r.json()["final"] == r.json()["valor"][-4:]
    tela = client.get(URL, headers=full)
    assert r.json()["valor"] not in tela.text
    assert tela.json()["configuracoes"][0]["webhook_secret"] == {"definido": True, "final": r.json()["final"]}


def test_validacoes(client, db, base, full):
    assert client.put(f"{URL}/unidades/999", headers=full, json={}).status_code == 404
    assert client.put(cfg_url(base), headers=full, json={"campo_inventado": 1}).status_code == 422
    assert client.put(cfg_url(base), headers=full, json={"gym_id": "com espaço"}).status_code == 422
    assert client.put(cfg_url(base), headers=full, json={"ambiente": "teste"}).status_code == 422
    assert client.put(cfg_url(base), headers=full, json={"valor_repasse_checkin": "-1"}).status_code == 422
    assert client.put(cfg_url(base), headers=full, json={"servico_padrao_id": 999}).status_code == 422
    r = client.put(cfg_url(base), headers=full, json={"webhook_secret": "curto"})
    assert r.status_code == 422 and "16" in r.json()["detail"]
    r = client.put(cfg_url(base), headers=full, json={"ativo": True})
    assert r.status_code == 422 and "segredo" in r.json()["detail"]
    r = client.put(cfg_url(base), headers=full, json={"sync_ativo": True})
    assert r.status_code == 422 and "chave" in r.json()["detail"]
    # gym id é único entre unidades
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM})
    un2 = Unidade(nome="Filial", capacidade=3)
    db.add(un2)
    db.commit()
    assert client.put(f"{URL}/unidades/{un2.id}", headers=full, json={"gym_id": GYM}).status_code == 409


def test_trocar_credencial_zera_o_teste(client, db, base, full, wh):
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM, "api_key": API_KEY})
    assert client.post(cfg_url(base) + "/testar-conexao", headers=full).json()["ok"] is True
    assert client.get(URL, headers=full).json()["configuracoes"][0]["teste_ultimo_ok"] is True
    r = client.put(cfg_url(base), headers=full, json={"ambiente": "producao"})
    assert r.json()["teste_ultimo_ok"] is None


# ------------------------------------------------------------------------------------------------ testar conexão
def test_testar_conexao_ok_usa_bearer_e_x_gym_id(client, base, full, wh):
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM, "api_key": API_KEY})
    r = client.post(cfg_url(base) + "/testar-conexao", headers=full)
    assert r.status_code == 200 and r.json()["ok"] is True and "2 classe" in r.json()["mensagem"]
    chamada = wh.chamadas[0]
    assert chamada.method == "GET" and chamada.url.path == f"/booking/v1/gyms/{GYM}/classes"
    assert chamada.headers["authorization"] == f"Bearer {API_KEY}" and chamada.headers["x-gym-id"] == GYM


def test_testar_conexao_recusada_nao_vaza_a_chave(client, db, base, full, caplog):
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM, "api_key": "chave-errada-9999"})
    instalar(Wellhub())
    with caplog.at_level(logging.DEBUG):
        r = client.post(cfg_url(base) + "/testar-conexao", headers=full)
    assert r.status_code == 502 and "recusou a credencial" in r.json()["detail"]
    assert "chave-errada" not in r.text and "chave-errada" not in caplog.text
    db.expire_all()
    assert db.scalar(select(WellhubConfig.teste_ultimo_ok)) is False


def test_testar_conexao_falhas(client, base, full):
    assert client.post(cfg_url(base) + "/testar-conexao", headers=full).status_code == 409  # nada salvo
    client.put(cfg_url(base), headers=full, json={"ambiente": "sandbox"})
    r = client.post(cfg_url(base) + "/testar-conexao", headers=full)
    assert r.status_code == 502 and "gym id e a chave" in r.json()["detail"]
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM, "api_key": API_KEY})

    def cai(_):
        raise httpx.ConnectError("sem rede")

    cli.definir_fabrica_cliente(lambda: cli.ClienteWellhub(BASE, transport=httpx.MockTransport(cai)))
    assert "Não foi possível falar" in client.post(cfg_url(base) + "/testar-conexao", headers=full).json()["detail"]
    instalar(Wellhub(classes=500))
    assert "erro 500" in client.post(cfg_url(base) + "/testar-conexao", headers=full).json()["detail"]


def test_o_cliente_real_nunca_e_criado_nos_testes(client, base, full):
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM, "api_key": API_KEY})
    with pytest.raises(AssertionError, match="internet proibida"):
        client.post(cfg_url(base) + "/testar-conexao", headers=full)


def test_url_base_por_ambiente(monkeypatch):
    monkeypatch.delenv("WELLHUB_URL_SANDBOX", raising=False)
    monkeypatch.delenv("WELLHUB_URL_PRODUCAO", raising=False)
    assert cli.url_base("producao") == "https://api.partners.gympass.com"
    assert cli.url_base("sandbox") == "https://apitesting.partners.gympass.com"
    monkeypatch.setenv("WELLHUB_URL_SANDBOX", "https://outro.invalid/")
    assert cli.url_base("sandbox") == "https://outro.invalid"


def test_testar_webhook_sem_rede(client, base, full):
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM})
    assert client.post(cfg_url(base) + "/testar-webhook", headers=full).status_code == 422
    client.put(cfg_url(base), headers=full, json={"webhook_secret": SEGREDO})
    r = client.post(cfg_url(base) + "/testar-webhook", headers=full)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["detalhes"]["cabecalho"] == "X-Gympass-Signature"
    assert SEGREDO not in r.text


# ------------------------------------------------------------------------------------------------ produtos e mapeamento
def test_produtos_do_wellhub(client, base, full, wh):
    client.put(cfg_url(base), headers=full, json={"gym_id": GYM, "api_key": API_KEY})
    r = client.post(cfg_url(base) + "/produtos", headers=full)
    assert r.status_code == 200 and r.json() == [{"id": "11", "nome": "Pilates Wellhub"}, {"id": "12", "nome": "Funcional"}]
    instalar(Wellhub(produtos=403))
    assert client.post(cfg_url(base) + "/produtos", headers=full).status_code == 502


def test_mapeamento_cria_atualiza_e_desativa(client, db, base, full):
    funcional = TipoServico(nome="Funcional")
    db.add(funcional)
    db.commit()
    r = client.put(cfg_url(base) + "/mapeamentos", headers=full, json={"itens": [
        {"tipo_servico_id": base.sid, "product_id": "11", "nome_classe": "Pilates no Wellhub"},
        {"tipo_servico_id": funcional.id, "product_id": "12"}]})
    assert r.status_code == 200, r.text
    maps = {m["servico_nome"]: m for m in r.json()["mapeamentos"]}
    assert maps["Pilates"]["product_id"] == "11" and maps["Pilates"]["nome_classe"] == "Pilates no Wellhub"
    r = client.put(cfg_url(base) + "/mapeamentos", headers=full, json={"itens": [{"tipo_servico_id": base.sid, "product_id": "13"}]})
    maps = {m["servico_nome"]: m for m in r.json()["mapeamentos"]}
    assert maps["Pilates"]["product_id"] == "13" and maps["Funcional"]["ativo"] is False
    assert db.scalar(select(func.count()).select_from(WellhubMapeamento)) == 2


def test_mapeamento_validacoes(client, base, full):
    u = cfg_url(base) + "/mapeamentos"
    assert client.put(u, headers=full, json={"itens": [{"tipo_servico_id": 999}]}).status_code == 422
    dup = {"itens": [{"tipo_servico_id": base.sid}, {"tipo_servico_id": base.sid}]}
    assert client.put(u, headers=full, json=dup).status_code == 422
    assert client.put(u, headers=full, json={"itens": [{"tipo_servico_id": base.sid, "product_id": "x y"}]}).status_code == 422


# ------------------------------------------------------------------------------------------------ permissões
@pytest.mark.parametrize("quem", ["secretaria", "professor"])
def test_so_o_perfil_full_ve_e_configura(client, request, base, full, configurado, quem):
    cab = request.getfixturevalue(quem)
    u = cfg_url(base)
    for metodo, url, corpo in (
        ("get", URL, None), ("get", f"{URL}/eventos", None), ("get", f"{URL}/relatorio", None), ("get", u + "/painel", None),
        ("get", f"{URL}/relatorio.csv", None), ("get", f"{URL}/alunos", None),
        ("put", u, {"ativo": False}), ("post", u + "/segredo-webhook", None), ("post", u + "/testar-conexao", None),
        ("post", u + "/testar-webhook", None), ("post", u + "/produtos", None), ("put", u + "/mapeamentos", {"itens": []}),
        ("post", u + "/grade/previa", None), ("post", u + "/grade/publicar", None),
        ("post", f"{URL}/validar-checkin", {"aluno_id": 1}), ("post", f"{URL}/eventos/1/reprocessar", None),
        ("post", f"{URL}/eventos/1/conferido", None),
    ):
        r = getattr(client, metodo)(url, headers=cab, **({"json": corpo} if corpo is not None else {}))
        assert r.status_code == 403, (metodo, url, r.status_code)
    assert client.get(URL, headers=full).json()["configuracoes"][0]["ativo"] is True


def test_sem_login_nao_acessa(client, base):
    for url in (URL, f"{URL}/eventos", f"{URL}/relatorio", f"{URL}/unidades/{base.uid}/painel"):
        assert client.get(url).status_code == 401
    assert client.put(cfg_url(base), json={}).status_code == 401


def test_nenhuma_resposta_devolve_segredo(client, base, full, configurado):
    for resp in (client.get(URL, headers=full), client.get(cfg_url(base) + "/painel", headers=full),
                 client.put(cfg_url(base), headers=full, json={"api_key": "outra-chave-sintetica-0000"})):
        assert "outra-chave" not in resp.text and API_KEY not in resp.text and SEGREDO not in resp.text
        json.loads(resp.text)
