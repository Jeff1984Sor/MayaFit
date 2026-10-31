"""Início (indicadores), saúde, ações de um clique, dados de demonstração e tarefas do worker."""

from datetime import date, timedelta

from app.controle import cobranca
from app.controle.models import Cliente, Cobranca, SessaoControle
from app.modules.admin_mayacorp import demo, tarefas
from tests.admin_mayacorp.conftest import criar_estudio, plano


def test_inicio_com_dados_de_demonstracao(client, fundacao, adm):
    feito = demo.popular_demo()
    assert feito["estudios"] == 6 and feito["solicitacoes"] == 4 and feito["cobrancas"] == _contar_cobrancas() > 20
    assert demo.popular_demo() == {"estudios": 0, "cobrancas": 0, "solicitacoes": 0}  # idempotente
    r = client.get("/api/admin/resumo", headers=adm).json()
    assert r["clientes"] == 6
    assert r["por_status"] == {"teste": 1, "ativo": 3, "suspenso": 1, "inativo": 1}
    # MRR dos planos: Lumina 89,90 − 5% (indicou o Equilíbrio) = 85,41 + Equilíbrio 1.499/12 = 124,92
    # + Corpo 49,90 + Força (suspenso também paga) 289,90 = 550,13. Excedentes: Lumina 13 alunos × 0,50 = 6,50
    assert r["mrr_planos"] == "550.13" and r["mrr_excedentes"] == "6.50" and r["mrr"] == "556.63"
    assert r["churn"]["saidas_mes"] == 1 and r["churn"]["estudios"][0]["slug"] == "demo-alongar"
    assert r["churn"]["taxa_mes"] == "20.0"  # 1 saída / (4 pagantes + 1)
    assert len(r["receita_por_mes"]) == 12 and r["receita_por_mes"][-1]["mes"] == f"{date.today():%Y-%m}"
    assert sum(float(m["valor"]) for m in r["receita_por_mes"]) > 0
    assert r["cobrancas"]["vencidas"]["quantidade"] == 2 and r["cobrancas"]["inadimplentes"] == 1
    assert r["funil"] == {"recebidas": 4, "novas": 2, "recusadas": 1, "aprovadas": 1, "em_teste": 1,
                          "convertidas": 0, "taxa_conversao": "0.0"}
    assert [t["slug"] for t in r["testes_vencendo"]] == ["demo-respira-pilates"]
    assert r["crescimento"]["serie"][-1]["mes"] == f"{date.today():%Y-%m}"
    # a ficha da demo tem linha do tempo e saúde
    forca = next(c for c in client.get("/api/admin/clientes", headers=adm).json() if c["slug"] == "demo-forca-funcional")
    s = client.get(f"/api/admin/clientes/{forca['id']}/saude", headers=adm).json()
    assert s["nivel"] == "risco" and s["inadimplencia"]["vencidas"] == 2 and s["inadimplencia"]["maior_atraso_dias"] == 35
    assert client.get(f"/api/admin/clientes/{forca['id']}/eventos", headers=adm).json()
    assert demo.remover_demo() == 6
    assert client.get("/api/admin/clientes", headers=adm).json() == []


def _contar_cobrancas() -> int:
    with SessaoControle() as db:
        return db.query(Cobranca).count()


def test_saude_e_acoes_de_um_clique(client, fundacao, adm, emails_admin):
    est = criar_estudio(client, adm, plano_id=plano(client, adm, "Essencial")["id"], dias_teste=5)
    cid = est["id"]
    fundacao.uso["pilates-lumina"] = {"alunos_ativos": 58, "usuarios": 1}
    s = client.get(f"/api/admin/clientes/{cid}/saude", headers=adm).json()
    assert s["nivel"] == "atencao" and "Teste acaba em 5 dia(s)" in s["motivos"]
    assert s["uso"]["pct_alunos"] == 97 and s["teste"]["dias_restantes"] == 5
    assert s["acesso"]["dias_sem_acesso"] == 0  # o "jeff" acabou de entrar (banco de testes = banco do estúdio)
    # estender teste
    r = client.post(f"/api/admin/clientes/{cid}/estender-teste", headers=adm, json={"dias": 15})
    assert r.json()["teste_ate"] == (date.today() + timedelta(days=20)).isoformat()
    # suspender / reativar
    assert client.post(f"/api/admin/clientes/{cid}/suspender", headers=adm,
                       json={"motivo": "pedido do dono"}).json()["status"] == "suspenso"
    assert client.post(f"/api/admin/clientes/{cid}/reativar", headers=adm, json={}).json()["status"] == "ativo"
    assert client.post(f"/api/admin/clientes/{cid}/reativar", headers=adm, json={}).status_code == 400
    # estúdio que saiu do teste sem pagar: estender cancela a mensalidade em aberto
    with SessaoControle() as db:
        c = db.get(Cliente, cid)
        cobranca.primeira_cobranca(db, c)
        db.commit()
    r = client.post(f"/api/admin/clientes/{cid}/estender-teste", headers=adm, json={"dias": 7})
    assert r.json()["status"] == "teste"
    assert [k["status"] for k in client.get("/api/admin/cobrancas", headers=adm,
                                            params={"cliente_id": cid}).json()] == ["cancelada"]
    linha = [e["descricao"] for e in client.get(f"/api/admin/clientes/{cid}/eventos", headers=adm).json()]
    assert "Status: Em teste → Suspenso (avisado) (pedido do dono)" in linha
    assert any(x.startswith("Teste estendido em 15 dia(s)") for x in linha)
    # pagou alguma vez → não estende mais
    with SessaoControle() as db:
        db.get(Cliente, cid).status = "ativo"
        db.add(Cobranca(cliente_id=cid, tipo="avulsa", descricao="x", valor=10, vencimento=date.today(),
                        status="paga", itens=[], avisos=[]))
        db.commit()
    assert client.post(f"/api/admin/clientes/{cid}/estender-teste", headers=adm, json={"dias": 7}).status_code == 400


def test_tarefas_so_no_modo_multi_e_uma_vez_por_dia(fundacao, monkeypatch):
    chamadas = []
    monkeypatch.setattr(cobranca, "encerrar_testes", lambda: chamadas.append("testes") or {})
    monkeypatch.setattr(cobranca, "rotina_diaria", lambda: chamadas.append("rotina") or {})
    monkeypatch.setattr(cobranca, "suspender_atrasados", lambda: chamadas.append("suspender") or [])
    tarefas._feito_em.clear()
    fundacao.multi = False
    tarefas.rotina_cobranca()
    assert chamadas == []
    fundacao.multi = True
    tarefas.rotina_cobranca()
    tarefas.rotina_cobranca()  # de novo no mesmo dia: nada
    assert chamadas == ["testes", "rotina", "suspender"]
    from app import worker

    assert {"admin-cobranca", "admin-fotos-de-uso"} <= {t.nome for t in worker.TAREFAS}


def test_fotos_de_uso(fundacao, client, adm):
    criar_estudio(client, adm)
    fundacao.uso["pilates-lumina"] = {"alunos_ativos": 33, "usuarios": 2}
    assert cobranca.atualizar_fotos_de_uso() == 1
    with SessaoControle() as db:
        foto = db.query(Cliente).filter_by(slug="pilates-lumina").one().uso
    assert foto["alunos_ativos"] == 33 and "em" in foto
