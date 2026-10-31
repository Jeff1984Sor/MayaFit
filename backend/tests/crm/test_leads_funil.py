"""Leads pela equipe: cadastro, edição, Kanban, mover entre etapas, perda com motivo, reabrir, interações e lista."""

from sqlalchemy import select

from app.core.models import Auditoria


def test_cadastro_ficha_e_duplicado(client, h, novo_lead):
    lead = novo_lead(email="carla@x.com", valor_estimado="320.50", tags=["VIP", "vip", " manhã "], interesse="Pilates")
    assert lead["telefone"] == "5511988887777" and lead["telefone_formatado"] == "(11) 98888-7777"
    assert lead["tags"] == ["VIP", "manhã"]
    assert lead["etapa_nome"] == "Novo contato" and lead["situacao"] == "ABERTO"
    assert lead["responsavel"]["nome"] == "Usuário Full"  # quem cadastra vira responsável
    assert lead["whatsapp_url"].startswith("https://wa.me/5511988887777")
    assert lead["mensagens"] and all(m["url"].startswith("https://wa.me/5511988887777?text=") for m in lead["mensagens"])
    assert lead["sugestao"]  # primeiro contato
    r = client.post("/api/crm/leads", json={"nome": "Outra", "telefone": "11 98888 7777"}, headers=h)
    assert r.status_code == 409 and "Carla Teste" in r.json()["detail"]


def test_editar_lead_audita_diferenca(client, h, db, novo_lead):
    lead = novo_lead()
    r = client.put(f"/api/crm/leads/{lead['id']}", json={"interesse": "Funcional", "valor_estimado": "250"}, headers=h)
    assert r.status_code == 200 and r.json()["interesse"] == "Funcional" and r.json()["nome"] == "Carla Teste"
    aud = db.scalars(select(Auditoria).where(Auditoria.acao == "crm.lead.alterar")).one()
    assert set(aud.depois_json) == {"interesse", "valor_estimado"}


def test_mover_perder_exige_motivo_e_reabrir(client, h, novo_lead, etapa, opcoes):
    lead = novo_lead()
    perdido = etapa("Perdido")["id"]
    r = client.post(f"/api/crm/leads/{lead['id']}/mover", json={"etapa_id": perdido}, headers=h)
    assert r.status_code == 422 and "motivo" in r.json()["detail"]
    motivo = opcoes["motivos"][0]
    r = client.post(f"/api/crm/leads/{lead['id']}/mover", json={"etapa_id": perdido, "motivo_perda_id": motivo["id"],
                                                               "motivo_perda_detalhe": "achou caro"}, headers=h)
    f = r.json()
    assert f["situacao"] == "PERDIDO" and f["motivo_perda"] == motivo["nome"] and f["perdido_em"]
    assert all(t["concluida"] for t in f["tarefas"])  # encerrar conclui as pendências
    assert any("perdido" in i["descricao"].lower() for i in f["interacoes"])
    r = client.post(f"/api/crm/leads/{lead['id']}/reabrir", headers=h)
    assert r.json()["situacao"] == "ABERTO" and r.json()["etapa_nome"] == "Novo contato" and r.json()["motivo_perda"] is None
    assert [m["para"] for m in r.json()["movimentos"]] == ["Novo contato", "Perdido", "Novo contato"]


def test_kanban_filtros_e_lista(client, h, novo_lead, etapa):
    a = novo_lead(nome="Alice", telefone="11911112222", origem="site")
    novo_lead(nome="Bruno", telefone="11933334444", origem="indicacao", indicado_por="Alice")
    client.post(f"/api/crm/leads/{a['id']}/mover", json={"etapa_id": etapa("Proposta")["id"]}, headers=h)
    colunas = {c["etapa"]["nome"]: c for c in client.get("/api/crm/funil", headers=h).json()["colunas"]}
    assert [x["nome"] for x in colunas["Novo contato"]["leads"]] == ["Bruno"]
    assert [x["nome"] for x in colunas["Proposta"]["leads"]] == ["Alice"]
    assert list(colunas)[-2:] == ["Matriculado", "Perdido"]
    filtrado = client.get("/api/crm/funil", headers=h, params={"origem": "indicacao"}).json()["colunas"]
    assert sum(c["total"] for c in filtrado) == 1
    lista = client.get("/api/crm/leads", headers=h, params={"q": "3333"}).json()
    assert [x["nome"] for x in lista["itens"]] == ["Bruno"]
    lista = client.get("/api/crm/leads", headers=h, params={"situacao": "todos", "ordem": "nome"}).json()
    assert [x["nome"] for x in lista["itens"]] == ["Alice", "Bruno"] and lista["contagens"]["abertos"] == 2


def test_lista_por_tag(client, h, novo_lead):
    novo_lead(nome="Com tag", tags=["Manhã"])
    novo_lead(nome="Sem tag", telefone="11977776666")
    r = client.get("/api/crm/leads", headers=h, params={"tag": "manhã"}).json()
    assert [x["nome"] for x in r["itens"]] == ["Com tag"] and r["total"] == 1


def test_interacoes_atualizam_contato_e_nao_apagam_sistema(client, h, novo_lead):
    lead = novo_lead()
    r = client.post(f"/api/crm/leads/{lead['id']}/interacoes", json={"tipo": "LIGACAO", "descricao": "Ligou, pediu horários"}, headers=h)
    assert r.status_code == 201
    f = r.json()
    assert f["ultima_interacao_em"] and f["temperatura"] == "quente"
    ligacao = next(i for i in f["interacoes"] if i["tipo"] == "LIGACAO")
    sistema = next(i for i in f["interacoes"] if i["tipo"] == "SISTEMA")
    assert client.post(f"/api/crm/leads/{lead['id']}/interacoes", json={"tipo": "SISTEMA", "descricao": "x"}, headers=h).status_code == 422
    assert client.delete(f"/api/crm/leads/{lead['id']}/interacoes/{sistema['id']}", headers=h).status_code == 409
    assert client.delete(f"/api/crm/leads/{lead['id']}/interacoes/{ligacao['id']}", headers=h).status_code == 200


def test_excluir_lead(client, h, db, novo_lead):
    lead = novo_lead()
    assert client.delete(f"/api/crm/leads/{lead['id']}", headers=h).status_code == 200
    assert client.get(f"/api/crm/leads/{lead['id']}", headers=h).status_code == 404
    assert db.scalars(select(Auditoria).where(Auditoria.acao == "crm.lead.excluir")).one()


def test_resumo_do_topo(client, h, novo_lead):
    novo_lead(valor_estimado="300")
    r = client.get("/api/crm/resumo", headers=h).json()
    assert r["abertos"] == 1 and r["novos_7_dias"] == 1 and r["valor_em_negociacao"] == "300.00"
    assert r["tarefas_atrasadas"] == 0
