"""Aula experimental (agendar, resultado) e conversão do lead em aluno pelo serviço do módulo alunos."""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.alunos.models import Aluno, AlunoTelefone
from app.modules.crm.regras import FUSO


def _amanha_10h() -> str:
    d = (datetime.now(FUSO) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    return d.isoformat()


def test_agendar_aula_move_etapa_e_cria_lembrete(client, h, novo_lead, base):
    lead = novo_lead()
    r = client.post(f"/api/crm/leads/{lead['id']}/aula-experimental", headers=h,
                    json={"data_hora": _amanha_10h(), "profissional_id": base["profissional_id"], "unidade_id": base["unidade_id"]})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["etapa_nome"] == "Aula experimental agendada"
    assert f["aula_experimental_status"] == "AGENDADA" and f["aula_experimental_profissional"] == "Prof Bia"
    assert any(t["titulo"].startswith("Confirmar aula experimental") and not t["concluida"] for t in f["tarefas"])
    assert f["mensagens"][0]["titulo"] == "Confirmar aula experimental"
    assert f["temperatura"] == "quente"

    # remarcar: o lembrete antigo sai, entra um novo
    r = client.post(f"/api/crm/leads/{lead['id']}/aula-experimental", headers=h, json={"data_hora": _amanha_10h()})
    pendentes = [t for t in r.json()["tarefas"] if not t["concluida"]]
    assert len(pendentes) == 1
    assert any("remarcada" in i["descricao"] for i in r.json()["interacoes"])


def test_resultado_compareceu_e_faltou(client, h, novo_lead):
    lead = novo_lead()
    url = f"/api/crm/leads/{lead['id']}/aula-experimental"
    assert client.post(url + "/resultado", headers=h, json={"compareceu": True}).status_code == 409
    client.post(url, headers=h, json={"data_hora": _amanha_10h()})
    f = client.post(url + "/resultado", headers=h, json={"compareceu": False}).json()
    assert f["aula_experimental_status"] == "FALTOU"
    assert [t["titulo"] for t in f["tarefas"] if not t["concluida"]] == ["Remarcar aula experimental de Carla"]
    f = client.post(url + "/resultado", headers=h, json={"compareceu": True, "observacao": "Adorou"}).json()
    assert f["aula_experimental_status"] == "REALIZADA" and f["etapa_nome"] == "Fez aula experimental"
    assert [t["titulo"] for t in f["tarefas"] if not t["concluida"]] == ["Enviar proposta para Carla"]
    assert "proposta" in f["sugestao"].lower()


def test_nao_agenda_no_passado_nem_lead_encerrado(client, h, novo_lead, etapa, opcoes):
    lead = novo_lead()
    passado = (datetime.now(FUSO) - timedelta(days=3)).isoformat()
    assert client.post(f"/api/crm/leads/{lead['id']}/aula-experimental", headers=h, json={"data_hora": passado}).status_code == 422
    client.post(f"/api/crm/leads/{lead['id']}/mover", headers=h,
                json={"etapa_id": etapa("Perdido")["id"], "motivo_perda_id": opcoes["motivos"][0]["id"]})
    assert client.post(f"/api/crm/leads/{lead['id']}/aula-experimental", headers=h, json={"data_hora": _amanha_10h()}).status_code == 409


def test_converter_cria_aluno_e_marca_matriculado(client, h, db, novo_lead, base):
    lead = novo_lead(email="carla@x.com")
    prep = client.get(f"/api/crm/leads/{lead['id']}/conversao", headers=h).json()
    assert prep["pode_criar_aluno"] and prep["unidades"][0]["nome"] == "Unidade Centro" and prep["parecidos"] == []
    assert client.post(f"/api/crm/leads/{lead['id']}/converter", headers=h, json={}).status_code == 422
    r = client.post(f"/api/crm/leads/{lead['id']}/converter", headers=h, json={"unidade_id": base["unidade_id"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["criado"] and out["aluno_nome"] == "Carla Teste"
    aluno = db.get(Aluno, out["aluno_id"])
    assert aluno.sem_cpf and aluno.email == "carla@x.com"
    assert db.scalar(select(AlunoTelefone.numero).where(AlunoTelefone.aluno_id == aluno.id)) == "5511988887777"
    f = client.get(f"/api/crm/leads/{lead['id']}", headers=h).json()
    assert f["situacao"] == "GANHO" and f["etapa_nome"] == "Matriculado" and f["aluno_nome"] == "Carla Teste"
    assert db.scalars(select(Auditoria).where(Auditoria.acao == "crm.lead.converter")).one()
    assert db.scalars(select(Auditoria).where(Auditoria.acao == "aluno.criar")).one()
    assert client.post(f"/api/crm/leads/{lead['id']}/converter", headers=h, json={"unidade_id": base["unidade_id"]}).status_code == 409


def test_converter_vincula_aluno_existente_sugerido(client, h, novo_lead, base):
    r = client.post("/api/alunos", headers=h, json={"nome": "Carla Antiga", "sem_cpf": True, "unidade_id": base["unidade_id"],
                                                    "telefones": [{"numero": "11988887777"}]})
    aluno_id = r.json()["id"]
    lead = novo_lead()
    prep = client.get(f"/api/crm/leads/{lead['id']}/conversao", headers=h).json()
    assert prep["parecidos"] == [{"id": aluno_id, "nome": "Carla Antiga", "motivo": "mesmo telefone"}]
    out = client.post(f"/api/crm/leads/{lead['id']}/converter", headers=h, json={"aluno_id": aluno_id}).json()
    assert out == {"lead_id": lead["id"], "aluno_id": aluno_id, "aluno_nome": "Carla Antiga", "criado": False}


def test_secretaria_converte_mas_sem_alunos_editar_nao_cria(client, h_secretaria, db, base):
    from app.core.models import PerfilAcesso
    from tests.conftest import auth, criar_usuario, entrar

    r = client.post("/api/crm/leads", headers=h_secretaria, json={"nome": "Lead da Sec", "telefone": "11955554444"})
    lead = r.json()
    assert client.post(f"/api/crm/leads/{lead['id']}/converter", headers=h_secretaria,
                       json={"unidade_id": base["unidade_id"]}).status_code == 200

    p = PerfilAcesso(nome="Vendas", permissoes=["crm.ver", "crm.editar"])
    db.add(p)
    db.flush()
    u = criar_usuario(db, "Secretária", email="vendas@exemplo.com")
    u.perfil_acesso_id = p.id
    db.commit()
    hv = auth(entrar(client, "vendas@exemplo.com").json()["access_token"])
    outro = client.post("/api/crm/leads", headers=hv, json={"nome": "Lead Vendas", "telefone": "11944443333"}).json()
    assert client.get(f"/api/crm/leads/{outro['id']}/conversao", headers=hv).json()["pode_criar_aluno"] is False
    assert client.post(f"/api/crm/leads/{outro['id']}/converter", headers=hv, json={"unidade_id": base["unidade_id"]}).status_code == 403
