"""Cadastro pelo site → solicitação → aprovar (no admin ou pelo link assinado do e-mail) → estúdio em teste."""

from datetime import date, timedelta

from app.core import links
from app.modules.admin_mayacorp import rotas_cadastro

BASE = {"nome": "Studio Ramos", "documento": "11.222.333/0001-81", "responsavel": "Paula Ramos",
        "email": "paula@ramos.com.br", "telefone": "(11) 99999-0000", "ciclo": "mensal", "alunos": 85,
        "indicacao": "Pilates Lumina", "aceite": True}


def test_site_e_aprovacao_no_admin(client, fundacao, adm, emails_admin):
    planos = client.get("/api/public/planos").json()  # sem login: o site mostra os planos
    assert [p["nome"] for p in planos] == ["Essencial", "Estúdio", "Pro", "Rede"]
    pro = next(p for p in planos if p["nome"] == "Pro")
    base = {**BASE, "plano_id": pro["id"]}
    assert client.post("/api/public/cadastro", json={**base, "aceite": False}).status_code == 400
    assert client.post("/api/public/cadastro", json={**base, "documento": "123"}).status_code == 400
    assert client.post("/api/public/cadastro", json={**base, "site": "spam.com"}).status_code == 201  # robô: descarta
    assert client.post("/api/public/cadastro", json=base).status_code == 201
    assert ["paula@ramos.com.br"] in [p for p, *_ in emails_admin]  # confirmação para quem se cadastrou
    aviso = next(c for p, a, c, _ in emails_admin if a.startswith("Novo cadastro no MayaFit"))
    assert "/aprovar?token=" in aviso and "Alunos ativos hoje: 85" in aviso
    sols = client.get("/api/admin/solicitacoes", headers=adm, params={"status": "nova"}).json()
    assert [(s["nome"], s["alunos"]) for s in sols] == [("Studio Ramos", 85)]
    r = client.post(f"/api/admin/solicitacoes/{sols[0]['id']}/aprovar", headers=adm, json={})
    assert r.status_code == 200, r.text
    est = r.json()
    assert est["status"] == "teste" and est["plano"]["nome"] == "Pro" and est["slug"] == "studio-ramos"
    assert est["teste_ate"] == (date.today() + timedelta(days=60)).isoformat()  # 2 meses de teste
    assert "Alunos ativos informados no cadastro: 85" in est["observacao"]
    assert client.post(f"/api/admin/solicitacoes/{sols[0]['id']}/aprovar", headers=adm, json={}).status_code == 400
    assert client.get("/api/admin/solicitacoes", headers=adm).json()[0]["status"] == "aprovada"


def test_limite_de_cadastros_por_ip(client, fundacao):
    for i in range(5):
        assert client.post("/api/public/cadastro", json={**BASE, "email": f"p{i}@ramos.com.br"}).status_code == 201
    assert client.post("/api/public/cadastro", json=BASE).status_code == 429


def test_aprovar_e_recusar_pelo_link(client, db, fundacao, adm, emails_admin):
    from app.core.models import Usuario

    assert client.post("/api/public/cadastro", json=BASE).status_code == 201
    assert client.post("/api/public/cadastro", json={**BASE, "nome": "Studio Dois",
                                                     "email": "dois@ramos.com.br"}).status_code == 201
    sols = {s["nome"]: s["id"] for s in client.get("/api/admin/solicitacoes", headers=adm).json()}
    uid = db.query(Usuario).filter_by(login="jeff").one().id
    tk = rotas_cadastro.link_aprovacao(uid, sols["Studio Ramos"]).split("token=")[1]
    assert client.get("/api/public/solicitacao", params={"token": "lixo"}).status_code == 400
    assert client.get("/api/public/solicitacao", params={"token": tk}).json()["nome"] == "Studio Ramos"
    r = client.post("/api/public/solicitacao/aprovar", json={"token": tk, "dias_teste": 30})
    assert r.status_code == 200 and r.json()["status"] == "teste", r.text
    assert r.json()["teste_ate"] == (date.today() + timedelta(days=30)).isoformat()
    assert client.post("/api/public/solicitacao/recusar", json={"token": tk}).status_code == 400  # já tratada
    tk2 = links.assinar(rotas_cadastro.FINALIDADE, {"u": uid, "s": sols["Studio Dois"]}, 60)
    assert client.post("/api/public/solicitacao/recusar", json={"token": tk2}).json()["status"] == "recusada"
    vencido = links.assinar(rotas_cadastro.FINALIDADE, {"u": uid, "s": sols["Studio Dois"]}, -1)
    assert client.get("/api/public/solicitacao", params={"token": vencido}).status_code == 400
    outro = links.assinar("arquivo", {"u": uid, "s": sols["Studio Dois"]}, 60)  # link de outra finalidade
    assert client.get("/api/public/solicitacao", params={"token": outro}).status_code == 400
