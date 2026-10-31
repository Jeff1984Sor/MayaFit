"""Tarefas ("Minhas tarefas de hoje"), configurações (etapas e motivos), relatório e permissões."""

from datetime import date, datetime, timedelta

from app.core.db import agora
from app.modules.crm.regras import FUSO


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_minhas_tarefas_hoje_atrasadas_e_concluir(client, h, novo_lead, h_secretaria):
    lead = novo_lead()
    atrasada = client.post("/api/crm/tarefas", headers=h, json={
        "titulo": "Ligar de volta", "vence_em": _iso(agora() - timedelta(hours=2)), "lead_id": lead["id"]}).json()
    assert atrasada["situacao"] == "atrasada" and atrasada["lead_nome"] == "Carla Teste" and atrasada["whatsapp_url"]
    fim_dia = datetime.now(FUSO).replace(hour=23, minute=59, second=0, microsecond=0)
    if fim_dia > datetime.now(FUSO) + timedelta(minutes=5):
        client.post("/api/crm/tarefas", headers=h, json={"titulo": "Mandar proposta", "vence_em": _iso(fim_dia)})
    client.post("/api/crm/tarefas", headers=h, json={"titulo": "Semana que vem", "vence_em": _iso(agora() + timedelta(days=8))})
    # tarefa sem responsável aparece para todos; de outra pessoa, não
    client.post("/api/crm/tarefas", headers=h, json={"titulo": "Da equipe", "vence_em": _iso(agora() + timedelta(days=3)), "responsavel_id": None})

    hoje = client.get("/api/crm/tarefas", headers=h, params={"situacao": "hoje"}).json()
    assert hoje["itens"][0]["titulo"] == "Ligar de volta"  # atrasadas primeiro
    assert all(t["situacao"] in ("atrasada", "hoje") for t in hoje["itens"])
    assert hoje["contagens"]["atrasadas"] == 1
    sec = client.get("/api/crm/tarefas", headers=h_secretaria, params={"situacao": "pendentes"}).json()
    assert [t["titulo"] for t in sec["itens"]] == ["Da equipe"]
    todas = client.get("/api/crm/tarefas", headers=h_secretaria, params={"situacao": "pendentes", "escopo": "todas"}).json()
    assert len(todas["itens"]) >= 3

    r = client.post(f"/api/crm/tarefas/{atrasada['id']}/concluir", headers=h).json()
    assert r["concluida"] and r["situacao"] == "concluida"
    f = client.get(f"/api/crm/leads/{lead['id']}", headers=h).json()
    assert any("Tarefa concluída: Ligar de volta" in i["descricao"] for i in f["interacoes"])
    assert client.post(f"/api/crm/tarefas/{atrasada['id']}/reabrir", headers=h).json()["concluida"] is False
    editada = client.put(f"/api/crm/tarefas/{atrasada['id']}", headers=h, json={
        "titulo": "Ligar de volta (2)", "vence_em": _iso(agora() + timedelta(days=1))}).json()
    assert editada["titulo"] == "Ligar de volta (2)" and editada["situacao"] in ("hoje", "futura")
    assert client.delete(f"/api/crm/tarefas/{atrasada['id']}", headers=h).status_code == 200


def test_etapas_criar_reordenar_marco_e_excluir_com_leads(client, h, novo_lead, etapa):
    nova = client.post("/api/crm/etapas", headers=h, json={"nome": "Negociação", "cor": "#123456", "marco": "PROPOSTA"}).json()
    etapas = client.get("/api/crm/etapas", headers=h).json()
    assert [e["nome"] for e in etapas][-3:] == ["Negociação", "Matriculado", "Perdido"]
    assert next(e for e in etapas if e["nome"] == "Proposta")["marco"] is None  # marco é único
    abertas = [e["id"] for e in etapas if e["tipo"] == "ABERTA"]
    nova_ordem = [nova["id"], *[i for i in abertas if i != nova["id"]]]
    assert client.put("/api/crm/etapas/ordem", headers=h, json={"ids": nova_ordem[:2]}).status_code == 422
    r = client.put("/api/crm/etapas/ordem", headers=h, json={"ids": nova_ordem})
    assert r.json()[0]["nome"] == "Negociação"

    lead = novo_lead(etapa_id=nova["id"])
    assert lead["etapa_nome"] == "Negociação"
    assert client.delete(f"/api/crm/etapas/{nova['id']}", headers=h).status_code == 409
    destino = etapa("Novo contato")["id"]
    assert client.delete(f"/api/crm/etapas/{nova['id']}", headers=h, params={"mover_para_id": destino}).status_code == 200
    assert client.get(f"/api/crm/leads/{lead['id']}", headers=h).json()["etapa_nome"] == "Novo contato"
    assert client.delete(f"/api/crm/etapas/{etapa('Perdido')['id']}", headers=h).status_code == 409
    renomeada = client.put(f"/api/crm/etapas/{etapa('Matriculado')['id']}", headers=h, json={"nome": "Aluno novo", "cor": "#1A8F5E"})
    assert renomeada.json()["nome"] == "Aluno novo" and renomeada.json()["tipo"] == "GANHO"


def test_motivos_em_uso_sao_desativados(client, h, novo_lead, etapa):
    m = client.post("/api/crm/motivos", headers=h, json={"nome": "Mudou de cidade"}).json()
    assert client.post("/api/crm/motivos", headers=h, json={"nome": "mudou de cidade"}).status_code == 409
    lead = novo_lead()
    client.post(f"/api/crm/leads/{lead['id']}/mover", headers=h, json={"etapa_id": etapa("Perdido")["id"], "motivo_perda_id": m["id"]})
    r = client.delete(f"/api/crm/motivos/{m['id']}", headers=h)
    assert "desativado" in r.json()["mensagem"]
    lista = {x["nome"]: x for x in client.get("/api/crm/motivos", headers=h).json()}
    assert lista["Mudou de cidade"]["ativo"] is False and lista["Mudou de cidade"]["usos"] == 1
    livre = client.post("/api/crm/motivos", headers=h, json={"nome": "Teste"}).json()
    assert client.delete(f"/api/crm/motivos/{livre['id']}", headers=h).json()["mensagem"] == "Motivo excluído."


def test_relatorio_conversao_origem_tempo_e_motivos(client, h, novo_lead, etapa, opcoes, base):
    a = novo_lead(nome="Lead A", telefone="11911110001", origem="instagram", valor_estimado="300")
    b = novo_lead(nome="Lead B", telefone="11911110002", origem="instagram")
    c = novo_lead(nome="Lead C", telefone="11911110003", origem="site")
    novo_lead(nome="Lead D", telefone="11911110004", origem="site")
    novo_lead(nome="Lead E", telefone="11911110005", origem="instagram")
    client.post(f"/api/crm/leads/{a['id']}/mover", headers=h, json={"etapa_id": etapa("Fez aula experimental")["id"]})
    client.post(f"/api/crm/leads/{a['id']}/converter", headers=h, json={"unidade_id": base["unidade_id"]})
    client.post(f"/api/crm/leads/{b['id']}/mover", headers=h, json={"etapa_id": etapa("Aula experimental agendada")["id"]})
    motivo = opcoes["motivos"][0]
    client.post(f"/api/crm/leads/{c['id']}/mover", headers=h, json={"etapa_id": etapa("Perdido")["id"], "motivo_perda_id": motivo["id"]})

    r = client.get("/api/crm/relatorio", headers=h).json()
    assert r["total_leads"] == 5 and r["ganhos"] == 1 and r["perdidos"] == 1 and r["abertos"] == 3
    assert r["taxa_conversao"] == 20.0 and r["valor_ganho"] == "300.00"
    assert r["tempo_medio_dias"] == 0.0
    funil = [(x["etapa"], x["quantidade"]) for x in r["funil"]]
    assert funil == [("Novo contato", 5), ("Aula experimental agendada", 2), ("Fez aula experimental", 1), ("Proposta", 1), ("Matriculado", 1)]
    assert r["funil"][1]["pct_anterior"] == 40.0
    origens = {x["origem"]: x for x in r["por_origem"]}
    assert origens["instagram"]["total"] == 3 and origens["instagram"]["ganhos"] == 1 and origens["instagram"]["taxa_conversao"] == 33.3
    assert r["perdidos_por_motivo"] == [{"motivo_id": motivo["id"], "motivo": motivo["nome"], "quantidade": 1, "pct": 100.0}]
    assert r["melhor_origem"].startswith("Instagram") and "Novo contato" in r["gargalo"]

    vazio = client.get("/api/crm/relatorio", headers=h, params={"de": "2020-01-01", "ate": "2020-01-31"}).json()
    assert vazio["total_leads"] == 0 and vazio["funil"][0]["quantidade"] == 0
    hoje = date.today()
    assert client.get("/api/crm/relatorio", headers=h, params={"de": str(hoje), "ate": str(hoje - timedelta(days=1))}).status_code == 422


def test_permissoes_professor_nao_ve_secretaria_nao_exclui(client, h_professor, h_secretaria, novo_lead):
    for url in ("/api/crm/funil", "/api/crm/leads", "/api/crm/tarefas", "/api/crm/resumo", "/api/crm/relatorio", "/api/crm/opcoes"):
        assert client.get(url, headers=h_professor).status_code == 403, url
    assert client.post("/api/crm/leads", headers=h_professor, json={"nome": "X Y", "telefone": "11999990000"}).status_code == 403
    lead = novo_lead()
    assert client.get("/api/crm/funil", headers=h_secretaria).status_code == 200
    assert client.put(f"/api/crm/leads/{lead['id']}", headers=h_secretaria, json={"interesse": "Yoga"}).status_code == 200
    assert client.delete(f"/api/crm/leads/{lead['id']}", headers=h_secretaria).status_code == 403
    assert client.post("/api/crm/etapas", headers=h_secretaria, json={"nome": "Nova etapa"}).status_code == 201
    assert client.get("/api/crm/leads").status_code == 401
