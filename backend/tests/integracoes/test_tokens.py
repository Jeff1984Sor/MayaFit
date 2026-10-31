"""Tokens de API: valor aparece uma vez, só o hash fica no banco, regenerar, desativar = 401, permissões, auditoria."""

from __future__ import annotations

import hashlib

from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.cadastros.models import IntegracaoToken
from app.modules.integracoes import api_externa, tokens
from tests.conftest import auth  # noqa: F401


def criar(client, full, nome="Chatbot da Clínica"):
    r = client.post("/api/integracoes/tokens", json={"nome": nome}, headers=full)
    assert r.status_code == 201, r.text
    return r.json()


def chave(valor):
    return {"X-API-Key": valor}


def test_criar_devolve_o_valor_uma_vez_e_guarda_so_hash(client, db, full):
    t = criar(client, full)
    assert t["valor"].startswith("mayafit_") and len(t["valor"]) > 40
    assert t["token_final"] == t["valor"][-4:] and t["ativo"] is True and t["precisa_regenerar"] is False
    linha = db.scalar(select(IntegracaoToken).where(IntegracaoToken.id == t["id"]))
    assert linha.token_hash == hashlib.sha256(t["valor"].encode()).hexdigest()
    assert t["valor"] not in {str(getattr(linha, c.key)) for c in linha.__mapper__.column_attrs}
    # a listagem e qualquer GET nunca devolvem o valor
    lista = client.get("/api/integracoes/tokens", headers=full)
    assert lista.status_code == 200 and t["valor"] not in lista.text
    assert "valor" not in lista.json()[0] and "token_hash" not in lista.json()[0]


def test_token_novo_autentica_e_marca_ultimo_uso(client, db, full):
    t = criar(client, full)
    assert client.get("/api/integracoes/tokens", headers=full).json()[0]["ultimo_uso"] is None
    assert client.get("/api/integracao/alunos", headers=chave(t["valor"])).status_code == 200
    assert client.get("/api/integracoes/tokens", headers=full).json()[0]["ultimo_uso"] is not None


def test_bearer_funciona_e_x_api_key_tem_prioridade(client, full):
    t = criar(client, full)
    assert client.get("/api/integracao/alunos", headers={"Authorization": f"Bearer {t['valor']}"}).status_code == 200
    # chave ruim em X-API-Key + Bearer bom: vale a chave (como no antigo) => 401
    r = client.get("/api/integracao/alunos", headers={"X-API-Key": "pilates_x", "Authorization": f"Bearer {t['valor']}"})
    assert r.status_code == 401


def test_desativado_da_401_e_reativar_volta(client, full):
    t = criar(client, full)
    assert client.patch(f"/api/integracoes/tokens/{t['id']}", json={"ativo": False}, headers=full).status_code == 200
    r = client.get("/api/integracao/alunos", headers=chave(t["valor"]))
    assert r.status_code == 401 and r.json()["detail"] == "API key invalida"
    assert client.patch(f"/api/integracoes/tokens/{t['id']}", json={"ativo": True}, headers=full).status_code == 200
    assert client.get("/api/integracao/alunos", headers=chave(t["valor"])).status_code == 200


def test_regenerar_invalida_o_valor_antigo(client, db, full):
    t = criar(client, full)
    novo = client.post(f"/api/integracoes/tokens/{t['id']}/regenerar", headers=full)
    assert novo.status_code == 200
    v2 = novo.json()["valor"]
    assert v2 != t["valor"] and v2.startswith("mayafit_") and novo.json()["token_final"] == v2[-4:]
    assert client.get("/api/integracao/alunos", headers=chave(t["valor"])).status_code == 401
    assert client.get("/api/integracao/alunos", headers=chave(v2)).status_code == 200


def test_excluir_remove_e_da_401(client, full):
    t = criar(client, full)
    assert client.delete(f"/api/integracoes/tokens/{t['id']}", headers=full).status_code == 200
    assert client.get("/api/integracao/alunos", headers=chave(t["valor"])).status_code == 401
    assert client.delete(f"/api/integracoes/tokens/{t['id']}", headers=full).status_code == 404


def test_token_migrado_sem_valor_vem_marcado_e_nao_autentica(client, db, full):
    db.add(IntegracaoToken(nome="Empresa antiga", token_hash=None, token_final=None, precisa_regenerar=True, ativo=True))
    db.commit()
    lista = client.get("/api/integracoes/tokens", headers=full).json()
    assert lista[0]["precisa_regenerar"] is True and lista[0]["token_final"] is None
    assert client.get("/api/integracao/alunos").status_code == 401
    assert client.get("/api/integracao/alunos", headers=chave("")).status_code == 401
    # não dá para ativar sem regenerar; regenerando, passa a valer e a marca some
    assert client.patch(f"/api/integracoes/tokens/{lista[0]['id']}", json={"ativo": True}, headers=full).status_code == 409
    v = client.post(f"/api/integracoes/tokens/{lista[0]['id']}/regenerar", headers=full).json()
    assert v["precisa_regenerar"] is False
    assert client.get("/api/integracao/alunos", headers=chave(v["valor"])).status_code == 200


def test_renomear_e_validacoes(client, full):
    t = criar(client, full)
    r = client.patch(f"/api/integracoes/tokens/{t['id']}", json={"nome": "Outro nome"}, headers=full)
    assert r.status_code == 200 and r.json()["nome"] == "Outro nome"
    assert client.post("/api/integracoes/tokens", json={"nome": "x"}, headers=full).status_code == 422
    assert client.patch("/api/integracoes/tokens/999", json={"ativo": False}, headers=full).status_code == 404


def test_somente_full_mexe_em_tokens(client, db, full, secretaria, professor):
    t = criar(client, full)
    for cab in (secretaria, professor):
        assert client.get("/api/integracoes/tokens", headers=cab).status_code == 403
        assert client.post("/api/integracoes/tokens", json={"nome": "Intruso"}, headers=cab).status_code == 403
        assert client.patch(f"/api/integracoes/tokens/{t['id']}", json={"ativo": False}, headers=cab).status_code == 403
        assert client.post(f"/api/integracoes/tokens/{t['id']}/regenerar", headers=cab).status_code == 403
        assert client.delete(f"/api/integracoes/tokens/{t['id']}", headers=cab).status_code == 403
    assert client.get("/api/integracoes/tokens").status_code == 401


def test_token_de_api_nao_abre_rotas_internas_nem_o_inverso(client, full):
    t = criar(client, full)
    assert client.get("/api/integracoes/tokens", headers=chave(t["valor"])).status_code == 401
    assert client.get("/api/alunos", headers=chave(t["valor"])).status_code == 401
    # o JWT de um usuário não vale como chave de API
    jwt = full["Authorization"].removeprefix("Bearer ")
    assert client.get("/api/integracao/alunos", headers=chave(jwt)).status_code == 401


def test_auditoria_nunca_leva_o_valor(client, db, full):
    t = criar(client, full)
    v2 = client.post(f"/api/integracoes/tokens/{t['id']}/regenerar", headers=full).json()["valor"]
    client.patch(f"/api/integracoes/tokens/{t['id']}", json={"ativo": False}, headers=full)
    client.delete(f"/api/integracoes/tokens/{t['id']}", headers=full)
    linhas = list(db.scalars(select(Auditoria).where(Auditoria.entidade == "integracao_token").order_by(Auditoria.id)))
    assert [a.acao for a in linhas] == [
        "integracao_token.criar", "integracao_token.regenerar", "integracao_token.desativar", "integracao_token.excluir"]
    tudo = " ".join(f"{a.descricao} {a.antes_json} {a.depois_json}" for a in linhas)
    assert t["valor"] not in tudo and v2 not in tudo and "token_hash" not in tudo
    assert all(a.usuario_nome == "Usuário Full" for a in linhas)


def test_rate_limit_por_token(client, full, monkeypatch):
    monkeypatch.setattr(api_externa, "LIMITE_POR_TOKEN", 3)
    t = criar(client, full)
    codigos = [client.get("/api/integracao/alunos", headers=chave(t["valor"])).status_code for _ in range(5)]
    assert codigos == [200, 200, 200, 429, 429]
    assert client.get("/api/integracao/alunos", headers=chave(t["valor"])).headers["Retry-After"]
    # outro token não é afetado
    outro = criar(client, full, "Outro integrador")
    assert client.get("/api/integracao/alunos", headers=chave(outro["valor"])).status_code == 200


def test_rate_limit_de_falhas_por_ip(client, monkeypatch):
    monkeypatch.setattr(api_externa, "LIMITE_FALHAS_POR_IP", 4)
    codigos = [client.get("/api/integracao/alunos", headers=chave(f"pilates_chute_{i}")).status_code for i in range(6)]
    assert codigos == [401, 401, 401, 401, 429, 429]


def test_formato_e_unicidade_do_valor():
    a, b = tokens.gerar_valor(), tokens.gerar_valor()
    assert a != b and a.startswith("mayafit_") and len(a) >= 8 + 43
    assert tokens.hash_token(a) != tokens.hash_token(b) and len(tokens.hash_token(a)) == 64


def test_valor_do_pedido():
    assert tokens.valor_do_pedido("k", "Bearer z") == "k"
    assert tokens.valor_do_pedido(None, "Bearer  z ") == "z"
    assert tokens.valor_do_pedido(None, "bearer z") == "z"
    assert tokens.valor_do_pedido(None, "Basic z") is None
    assert tokens.valor_do_pedido(None, "Bearer ") is None
    assert tokens.valor_do_pedido(None, None) is None
