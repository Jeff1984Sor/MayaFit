"""Painel "quem está no estúdio agora", histórico, relatório, CSV, configuração, permissões e demonstração."""

from datetime import timedelta

from sqlalchemy import func, select

from app.core.models import Auditoria
from app.modules.acesso import demo
from app.modules.acesso.models import Catraca, Dispositivo, RegistroAcesso
from tests.acesso.conftest import AGORA, criar_totem, h
from tests.conftest import auth, criar_usuario, entrar


def entrar_ana(client, full, cenario):
    t = criar_totem(client, full)
    client.put(f"/api/acesso/alunos/{cenario.ana.id}/pin", headers=full, json={"pin": "2580"})
    j = client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": "4321", "pin": "2580"}).json()
    assert j["permitido"], j
    return t, j


def test_painel_mostra_quem_esta_no_estudio_e_sai_depois_da_aula(client, full, cenario, relogio):
    t, j = entrar_ana(client, full, cenario)
    client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": cenario.bruno.cpf, "pin": "0000"})
    p = client.get("/api/acesso/painel", headers=full).json()
    assert [x["primeiro_nome"] for x in p["presentes"]] == ["Ana"]
    assert p["presentes"][0]["aniversario"] is True and "Pilates" in p["presentes"][0]["aula"]
    assert p["entradas_hoje"] == 1 and p["negados_hoje"] == 1 and p["alunos_hoje"] == 1
    assert p["por_metodo"] == {"codigo": 1}
    assert p["ultimos"][0]["permitido"] is False
    assert any(e["tipo"] == "totem" and e["online"] for e in p["equipamentos"])
    relogio.agora = AGORA + timedelta(hours=2)  # aula 09:00-09:50 (+15 min) já acabou
    assert client.get("/api/acesso/painel", headers=full).json()["presentes"] == []


def test_marcar_saida_tira_do_painel(client, full, cenario):
    _, j = entrar_ana(client, full, cenario)
    r = client.post(f"/api/acesso/presentes/{j['registro_id']}/saida", headers=full, json={})
    assert r.status_code == 200
    assert client.get("/api/acesso/painel", headers=full).json()["presentes"] == []


def test_historico_filtros_e_csv(client, db, full, cenario):
    entrar_ana(client, full, cenario)
    client.post("/api/acesso/liberar", headers=full, json={"motivo": "Visitante"})
    tudo = client.get("/api/acesso/registros", headers=full).json()
    assert tudo["total"] == 2
    so = client.get("/api/acesso/registros", headers=full, params={"metodo": "manual"}).json()
    assert so["total"] == 1 and so["itens"][0]["usuario_nome"] == "Usuário Full"
    assert client.get("/api/acesso/registros", headers=full, params={"q": "ana"}).json()["total"] == 1
    assert client.get("/api/acesso/registros", headers=full, params={"de": "2026-10-27"}).json()["total"] == 0
    csv = client.get("/api/acesso/registros.csv", headers=full)
    assert csv.status_code == 200 and "ANA PAULA SOUZA" in csv.text and csv.text.startswith("﻿Data/hora")
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "exportar")) is not None


def test_relatorio_por_periodo(client, full, cenario):
    entrar_ana(client, full, cenario)
    r = client.get("/api/acesso/relatorio", headers=full, params={"de": "2026-10-20", "ate": "2026-10-26"}).json()
    assert r["permitidos"] == 1 and r["alunos_unicos"] == 1 and len(r["por_dia"]) == 7
    assert next(x for x in r["por_hora"] if x["hora"] == 8)["total"] == 1
    assert r["mais_frequentes"][0]["nome"] == "ANA PAULA SOUZA"
    assert client.get("/api/acesso/relatorio", headers=full, params={"de": "2026-10-27", "ate": "2026-10-20"}).status_code == 422


def test_simular_decisao_para_a_recepcao(client, full, cenario):
    j = client.get(f"/api/acesso/alunos/{cenario.ana.id}/decisao", headers=full).json()
    assert j["permitido"] is True and "Pilates" in j["aula"]
    assert client.get(f"/api/acesso/alunos/{cenario.bruno.id}/decisao", headers=full).json()["codigo"] == "sem_contrato"


def test_config_plano_livre_permite_entrar_sem_aula(client, db, full, cenario, relogio):
    from tests.acesso.conftest import novo_contrato

    novo_contrato(db, cenario.bruno, cenario.plano_livre, cenario.prof)
    db.commit()
    cfg = client.get("/api/acesso/config", headers=full).json()
    assert cfg["janela_antes_min"] == 30 and "LGPD" in cfg["termo_biometria"]
    cfg["planos_livres"] = [cenario.plano_livre.id]
    r = client.put("/api/acesso/config", headers=full, json=cfg)
    assert r.status_code == 200 and r.json()["planos_livres"] == [cenario.plano_livre.id]
    relogio.agora = AGORA + timedelta(hours=6)  # 14:50
    j = client.get(f"/api/acesso/alunos/{cenario.bruno.id}/decisao", headers=full).json()
    assert j["permitido"] and j["codigo"] == "acesso_livre"
    cfg["planos_livres"] = [99999]
    assert client.put("/api/acesso/config", headers=full, json=cfg).status_code == 422


def test_lista_de_alunos_com_status_de_biometria(client, full, cenario):
    from tests.acesso.conftest import cadastrar_rosto, vetor

    cadastrar_rosto(client, full, cenario.ana.id, vetor(1))
    j = client.get("/api/acesso/alunos", headers=full).json()
    assert j["com_biometria"] == 1 and j["sem_biometria"] == 1
    ana = next(a for a in j["itens"] if a["id"] == cenario.ana.id)
    assert ana["descritores"] == 1 and ana["consentimento"]["canal"] == "recepcao" and ana["cpf"].startswith("***")
    assert client.get("/api/acesso/alunos", headers=full, params={"situacao": "sem_biometria"}).json()["total"] == 1
    assert client.get("/api/acesso/alunos", headers=full, params={"q": "4321"}).json()["total"] == 1


def test_permissoes_do_modulo(client, db, full, secretaria, cenario):
    from app.core.models import PerfilAcesso

    assert client.get("/api/acesso/painel", headers=secretaria).status_code == 403
    p = PerfilAcesso(nome="Recepção acesso", permissoes=["acesso.ver", "acesso.liberar_manual"])
    db.add(p)
    db.commit()
    u = criar_usuario(db, "Secretária", email="rec@exemplo.com", login="rec")
    u.perfil_acesso_id = p.id
    db.commit()
    rec = auth(entrar(client, "rec").json()["access_token"])
    assert client.get("/api/acesso/painel", headers=rec).status_code == 200
    assert client.post("/api/acesso/liberar", headers=rec, json={"motivo": "Visita"}).status_code == 200
    assert client.post("/api/acesso/catracas", headers=rec, json={"nome": "X", "driver": "simulado", "modo": "totem"}).status_code == 403
    assert client.put(f"/api/acesso/alunos/{cenario.ana.id}/pin", headers=rec, json={"pin": "2580"}).status_code == 403


def test_demo_idempotente(db, cenario):
    demo.popular_demo(db)
    demo.popular_demo(db)
    db.commit()
    assert db.scalar(select(func.count(Catraca.id))) == 1
    assert db.scalar(select(func.count(Dispositivo.id))) == 1
    n = db.scalar(select(func.count(RegistroAcesso.id)))
    assert n > 10
    demo.popular_demo(db)
    assert db.scalar(select(func.count(RegistroAcesso.id))) == n
