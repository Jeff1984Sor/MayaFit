"""Grade (publicar/prévia/atualizar/remover), validar_checkin (API estável), painel, relatório, eventos, demo, tarefa e migração."""

from __future__ import annotations

import importlib.util
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select

from app.core.db import agora
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import Profissional
from app.modules.wellhub import demo, tarefas
from app.modules.wellhub.models import WellhubCheckin, WellhubConfig, WellhubEvento, WellhubMapeamento, WellhubSlot
from app.modules.wellhub.servico import ResultadoValidacao, validar_checkin
from tests.wellhub.conftest import GYM, Wellhub, checkin, enviar, hoje, instalar, sessao

U = "/api/wellhub/unidades/{}"


def total(db, modelo):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo))


# ------------------------------------------------------------------------------------------------ grade
def test_previa_nao_chama_a_rede(client, db, base, full, configurado):
    sessao(db, base)
    sessao(db, base, dias=2)
    r = client.post(U.format(base.uid) + "/grade/previa", headers=full)  # sem Wellhub instalado: explodiria se chamasse
    assert r.status_code == 200 and r.json()["previa"] is True
    assert (r.json()["classes_criadas"], r.json()["slots_criados"]) == (1, 2) and r.json()["resumo"].startswith("Prévia")
    assert total(db, WellhubSlot) == 0


def test_publicar_cria_classe_e_horarios_com_vagas(client, db, base, full, configurado, wh):
    prof = Profissional(nome="Prof. Sintético")
    db.add(prof)
    db.commit()
    s1 = sessao(db, base)
    s1.profissional_id = prof.id
    s1.capacidade = 5
    sessao(db, base, dias=3, hora=time(18, 0))
    sessao(db, base, dias=30)  # fora da janela de 7 dias
    sessao(db, base, dias=-1)  # passado
    db.commit()
    r = client.post(U.format(base.uid) + "/grade/publicar", headers=full)
    assert r.status_code == 200, r.text
    assert (r.json()["classes_criadas"], r.json()["slots_criados"], r.json()["erros"]) == (1, 2, 0)
    classe = wh.corpos("POST", r"/classes$")[0]["classes"][0]
    assert classe["name"] == "Pilates" and classe["product_id"] == 11 and classe["bookable"] is True
    slots = wh.corpos("POST", r"/classes/501/slots$")
    primeiro = slots[0]
    assert primeiro["total_capacity"] == 5 and primeiro["total_booked"] == 0 and primeiro["length_in_minutes"] == 50
    assert primeiro["instructors"] == [{"name": "Prof. Sintético", "substitute": False}]
    assert primeiro["occur_date"].endswith("Z") and primeiro["product_id"] == 11
    assert slots[1]["total_capacity"] == 2  # herda a capacidade da unidade
    db.expire_all()
    assert db.scalar(select(WellhubMapeamento.class_id)) == "501"
    cfg = db.scalar(select(WellhubConfig))
    assert cfg.sync_ultimo_ok is True and "2 horário(s) publicado(s)" in cfg.sync_ultimo_resumo


def test_republicar_so_envia_o_que_mudou(client, db, base, full, configurado, wh):
    s = sessao(db, base)
    sessao(db, base, dias=2)
    client.post(U.format(base.uid) + "/grade/publicar", headers=full)
    wh.chamadas.clear()
    r = client.post(U.format(base.uid) + "/grade/publicar", headers=full).json()
    assert (r["slots_criados"], r["slots_atualizados"], r["sem_mudanca"]) == (0, 0, 2) and wh.chamadas == []
    a = Aluno(nome="Local", sem_cpf=True, unidade_id=base.uid, codigo_legado=7000)
    db.add(a)
    db.flush()
    agenda.criar_reserva(db, a.id, s.id)
    db.commit()
    r = client.post(U.format(base.uid) + "/grade/publicar", headers=full).json()
    assert r["slots_atualizados"] == 1 and wh.corpos("PATCH", r"/slots/\d+$") == [{"total_capacity": 2, "total_booked": 1}]


def test_aula_excluida_sai_do_wellhub(client, db, base, full, configurado, wh):
    s = sessao(db, base)
    client.post(U.format(base.uid) + "/grade/publicar", headers=full)
    slot = db.scalar(select(WellhubSlot))
    slot.aula_sessao_id = None  # a agenda excluiu a aula (FK SET NULL)
    db.delete(db.get(AulaSessao, s.id))
    db.commit()
    r = client.post(U.format(base.uid) + "/grade/publicar", headers=full).json()
    assert r["slots_removidos"] == 1
    assert [c.method for c in wh.chamadas if c.url.path.endswith(f"/slots/{slot.slot_id}")] == ["DELETE"]
    db.expire_all()
    assert db.scalar(select(WellhubSlot.situacao)) == "removido"


def test_publicar_sem_mapeamento_ou_sem_produto(client, db, base, full, wh):
    client.put(U.format(base.uid), headers=full, json={"gym_id": GYM, "api_key": "chave-api-sintetica-wellhub-1234"})
    r = client.post(U.format(base.uid) + "/grade/previa", headers=full)
    assert r.status_code == 422 and "mapeamento" in r.json()["detail"]
    client.put(U.format(base.uid) + "/mapeamentos", headers=full, json={"itens": [{"tipo_servico_id": base.sid}]})
    r = client.post(U.format(base.uid) + "/grade/publicar", headers=full)
    assert r.status_code == 200 and r.json()["erros"] == 1 and "informe o produto" in r.json()["mensagens"][0]


def test_credencial_recusada_interrompe_e_vira_alerta(client, db, base, full, configurado):
    sessao(db, base)
    instalar(Wellhub(criar_classe=401))
    r = client.post(U.format(base.uid) + "/grade/publicar", headers=full)
    assert r.status_code == 502 and "recusou a credencial" in r.json()["detail"]
    painel = client.get(U.format(base.uid) + "/painel", headers=full).json()
    assert any(a["titulo"] == "A última publicação da grade falhou" for a in painel["alertas"])


def test_erro_em_um_horario_nao_para_os_outros(client, db, base, full, configurado):
    sessao(db, base)
    sessao(db, base, dias=2)
    instalar(Wellhub(slot=422))
    r = client.post(U.format(base.uid) + "/grade/publicar", headers=full).json()
    assert r["erros"] == 2 and "recusou os dados" in r["mensagens"][0]


def test_tarefa_agendada(client, db, base, full, configurado):
    sessao(db, base)
    srv = instalar(Wellhub())
    assert tarefas.publicar_agendado() == 0 and srv.chamadas == []  # desligada por padrão
    client.put(U.format(base.uid), headers=full, json={"sync_ativo": True})
    assert tarefas.publicar_agendado() == 1
    assert total(db, WellhubSlot) == 1
    instalar(Wellhub(classes=401, slot=401, vagas=401))
    db.add(AulaSessao(unidade_id=base.uid, tipo_servico_id=base.sid, data=hoje() + timedelta(days=2), hora_inicio=time(7),
                      hora_fim=time(8), reservas_ativas=0))
    db.commit()
    assert tarefas.publicar_agendado() == 1
    db.expire_all()
    assert db.scalar(select(WellhubConfig.sync_ultimo_resumo)).startswith("Erro:")


def test_tarefa_registrada_no_worker():
    from app.worker import TAREFAS

    assert any(t.nome == "wellhub-publicar-grade" and t.intervalo_s >= 300 for t in TAREFAS)


# ------------------------------------------------------------------------------------------------ validar_checkin
def test_validar_checkin_aluno_que_nao_e_do_wellhub(db, base):
    a = Aluno(nome="Comum", sem_cpf=True, unidade_id=base.uid, codigo_legado=8000)
    db.add(a)
    db.commit()
    res = validar_checkin(db, a.id)
    assert isinstance(res, ResultadoValidacao) and res.aplicavel is False and res.ok is False
    assert validar_checkin(db, 99999).aplicavel is False


def test_validar_checkin_ok_e_idempotente_no_dia(client, db, base, configurado, wh):
    enviar(client, checkin())
    aluno_id = db.scalar(select(Aluno.id))
    res = validar_checkin(db, aluno_id)
    assert res.aplicavel and res.ok and not res.ja_validado and res.gympass_id == "1234567890123"
    assert wh.corpos("POST", r"/access/v1/validate$") == [{"gympass_id": "1234567890123"}]
    assert wh.chamadas[-1].headers["x-gym-id"] == GYM
    db.expire_all()
    ck = db.scalar(select(WellhubCheckin))
    assert ck.validado and ck.validado_em and ck.id == res.checkin_id
    de_novo = validar_checkin(db, aluno_id)
    assert de_novo.ok and de_novo.ja_validado and len(wh.corpos("POST", r"/access/v1/validate$")) == 1


def test_validar_checkin_sem_checkin_no_app(client, db, base, configurado):
    enviar(client, checkin())
    instalar(Wellhub(validar=404))
    res = validar_checkin(db, db.scalar(select(Aluno.id)))
    assert res.aplicavel and not res.ok and "app do Wellhub" in res.mensagem
    db.expire_all()
    assert db.scalar(select(WellhubCheckin.erro_validacao)).startswith("O Wellhub não encontrou")


def test_validar_checkin_integracao_desligada_ou_sem_chave(client, db, base, full, configurado):
    enviar(client, checkin())
    aluno_id = db.scalar(select(Aluno.id))
    client.put(U.format(base.uid), headers=full, json={"ativo": False})
    assert "desligada" in validar_checkin(db, aluno_id).mensagem
    client.put(U.format(base.uid), headers=full, json={"ativo": True, "limpar": ["api_key"]})
    res = validar_checkin(db, aluno_id)
    assert res.aplicavel and not res.ok and "chave de API" in res.mensagem


def test_validar_checkin_pela_tela(client, db, base, full, configurado, wh):
    enviar(client, checkin())
    achados = client.get("/api/wellhub/alunos?q=Carla", headers=full).json()
    assert achados[0]["nome"] == "Carla Sintética" and achados[0]["gympass_id"].endswith("0123")
    assert "1234567890123" not in str(achados)
    r = client.post("/api/wellhub/validar-checkin", headers=full, json={"aluno_id": achados[0]["aluno_id"]})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.post("/api/wellhub/validar-checkin", headers=full, json={"aluno_id": 999}).status_code == 404


# ------------------------------------------------------------------------------------------------ painel e relatório
def _checkins(db, cfg_id, aluno_id, gym, dias_validados, dias_pendentes):
    for d in dias_validados:
        db.add(WellhubCheckin(config_id=cfg_id, aluno_id=aluno_id, gympass_id=gym, dia=d, ocorrido_em=agora(), validado=True,
                              validado_em=agora(), origem="webhook"))
    for d in dias_pendentes:
        db.add(WellhubCheckin(config_id=cfg_id, aluno_id=aluno_id, gympass_id=gym, dia=d, ocorrido_em=agora(), validado=False,
                              origem="webhook"))
    db.commit()


def test_relatorio_mensal_e_csv(client, db, base, full, configurado):
    cfg = db.scalar(select(WellhubConfig))
    a = Aluno(nome="=Fórmula Maliciosa", sem_cpf=True, unidade_id=base.uid, codigo_legado=9000)
    db.add(a)
    db.commit()
    from datetime import date

    _checkins(db, cfg.id, a.id, "5550000000001", [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)], [date(2026, 9, 4)])
    _checkins(db, cfg.id, None, "5550000000002", [date(2026, 9, 2)], [])
    _checkins(db, cfg.id, a.id, "5550000000001", [date(2026, 8, 30), date(2026, 8, 31)], [])
    r = client.get("/api/wellhub/relatorio?ano=2026&mes=9", headers=full)
    assert r.status_code == 200, r.text
    rel = r.json()
    assert (rel["total"], rel["validados"], rel["pendentes"], rel["alunos_distintos"]) == (5, 4, 1, 2)
    assert Decimal(rel["valor_estimado"]) == Decimal("50.00") and rel["validados_mes_anterior"] == 2 and rel["variacao"] == 1.0
    assert rel["por_unidade"][0]["unidade_nome"] == "Matriz" and Decimal(rel["por_unidade"][0]["valor_unitario"]) == Decimal("12.50")
    assert rel["por_aluno"][0]["validados"] == 3 and rel["por_aluno"][0]["gympass_id"].endswith("0001")
    assert "5550000000001" not in r.text  # mascarado na tela
    assert [d["dia"] for d in rel["por_dia"]] == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
    csv = client.get("/api/wellhub/relatorio.csv?ano=2026&mes=9", headers=full)
    assert csv.status_code == 200 and "attachment" in csv.headers["content-disposition"]
    linhas = csv.text.lstrip("﻿").strip().splitlines()
    assert linhas[0].startswith("data;unidade;aluno;gympass_id") and len(linhas) == 6
    assert "5550000000001" in csv.text and "'=Fórmula Maliciosa" in csv.text and "12,50" in csv.text
    vazio = client.get("/api/wellhub/relatorio?ano=2025&mes=1", headers=full).json()
    assert vazio["total"] == 0 and Decimal(vazio["valor_estimado"]) == 0
    assert client.get("/api/wellhub/relatorio?mes=13", headers=full).status_code == 422


def test_painel_kpis_alertas_e_passos(client, db, base, full, configurado, wh):
    p0 = client.get(U.format(base.uid) + "/painel", headers=full).json()
    passos = {p["id"]: p["concluido"] for p in p0["passos"]}
    assert passos == {"credenciais": False, "webhook": True, "mapeamento": True, "grade": False, "repasse": True}
    enviar(client, checkin())
    aluno_id = db.scalar(select(Aluno.id))
    validar_checkin(db, aluno_id)
    enviar(client, checkin("9999999999999", nome="Outro Aluno"))
    enviar(client, {"event_type": "booking-requested", "event_data": {"user": {"unique_token": "1"}, "slot": {"gym_id": GYM}}})
    p = client.get(U.format(base.uid) + "/painel", headers=full).json()
    assert (p["checkins_mes"], p["checkins_validados_mes"], p["checkins_pendentes_mes"]) == (2, 1, 1)
    assert Decimal(p["valor_estimado_mes"]) == Decimal("12.50") and p["eventos_com_erro"] == 1
    assert any("com erro" in a["titulo"] for a in p["alertas"])
    assert p["serie"][-1]["dia"] == hoje().isoformat() and p["serie"][-1]["total"] == 2
    assert len(p["ultimos_eventos"]) == 3 and p["ultimos_eventos"][0]["tipo_rotulo"] == "Reserva pedida"


def test_painel_de_unidade_sem_configuracao(client, base, full):
    p = client.get(U.format(base.uid) + "/painel", headers=full).json()
    assert p["configurada"] is False and p["checkins_mes"] == 0 and p["alertas"] == []
    assert client.get(U.format(999) + "/painel", headers=full).status_code == 404


# ------------------------------------------------------------------------------------------------ eventos (tela)
def test_lista_detalhe_filtros_e_conferido(client, db, base, full, configurado):
    enviar(client, checkin())
    enviar(client, {"event_type": "user-updated", "event_data": {"gym_id": GYM}})
    p = {"event_type": "booking-requested", "event_data": {"user": {"unique_token": "1234567890123", "email": "x@y.invalid"},
                                                           "slot": {"id": "1", "gym_id": GYM, "booking_number": "BK-9"}}}
    enviar(client, p)
    lista = client.get("/api/wellhub/eventos", headers=full).json()
    assert lista["total"] == 3 and {e["resultado"] for e in lista["itens"]} == {"processado", "descartado", "erro"}
    assert "1234567890123" not in str(lista)
    erro = client.get("/api/wellhub/eventos?resultado=erro", headers=full).json()["itens"][0]
    assert erro["pode_reprocessar"] is True and erro["booking_number"] == "BK-9"
    assert client.get("/api/wellhub/eventos?q=BK-9", headers=full).json()["total"] == 1
    assert client.get(f"/api/wellhub/eventos?unidade_id={base.uid}&tipo=checkin", headers=full).json()["total"] == 1
    det = client.get(f"/api/wellhub/eventos/{erro['id']}", headers=full).json()
    assert det["payload"]["event_data"]["user"]["email"].endswith("lid") and "x@y" not in str(det)
    assert client.get("/api/wellhub/eventos/999", headers=full).status_code == 404
    r = client.post(f"/api/wellhub/eventos/{erro['id']}/conferido", headers=full)
    assert r.status_code == 200 and r.json()["ignorado"] is True
    assert client.get("/api/wellhub/eventos?resultado=erro", headers=full).json()["total"] == 0
    assert client.get("/api/wellhub/eventos?resultado=ignorado", headers=full).json()["total"] == 1
    assert client.get(U.format(base.uid) + "/painel", headers=full).json()["eventos_com_erro"] == 0
    client.post(f"/api/wellhub/eventos/{erro['id']}/conferido?desfazer=true", headers=full)
    assert client.get("/api/wellhub/eventos?resultado=erro", headers=full).json()["total"] == 1
    ok = next(e for e in lista["itens"] if e["resultado"] == "processado")
    assert client.post(f"/api/wellhub/eventos/{ok['id']}/conferido", headers=full).status_code == 409
    assert client.get("/api/wellhub/eventos?resultado=xyz", headers=full).status_code == 422


# ------------------------------------------------------------------------------------------------ demo
def test_demo_idempotente(client, db, base, full):
    r1 = demo.popular_demo(db)
    assert r1["criado"] is True and r1["alunos"] == 3 and r1["eventos"] == 4 and r1["checkins"] > 0
    r2 = demo.popular_demo(db)
    assert r2["criado"] is False
    assert total(db, WellhubConfig) == 1 and total(db, WellhubEvento) == 4
    p = client.get(U.format(base.uid) + "/painel", headers=full).json()
    assert p["eventos_com_erro"] == 1 and Decimal(p["valor_estimado_mes"]) > 0


def test_demo_sem_unidade_nao_faz_nada(db):
    assert demo.popular_demo(db)["criado"] is False and total(db, WellhubConfig) == 0


# ------------------------------------------------------------------------------------------------ migração
@pytest.mark.filterwarnings("ignore:Skipped unsupported reflection")
def test_migracao_0140_igual_aos_modelos_e_reversivel():
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from app.core.db import Base

    versoes = Path(__file__).resolve().parents[2] / "alembic" / "versions"

    def carregar(nome):
        spec = importlib.util.spec_from_file_location(nome, versoes / f"{nome}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    inicial, wellhub = carregar("0001_esquema_inicial"), carregar("0140_wellhub")
    assert wellhub.revision == "0140_wellhub" and wellhub.down_revision == "0130_acesso"  # fila única da integração
    assert inicial.revision == "0001_pilates_inicial"
    via = create_engine("sqlite://")
    with via.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        inicial.upgrade()
        wellhub.upgrade()
    modelos = create_engine("sqlite://")
    Base.metadata.create_all(modelos, tables=[t for n, t in Base.metadata.tables.items() if n.startswith("wellhub_")]
                             + [t for n, t in Base.metadata.tables.items() if not n.startswith("wellhub_")])
    a, b = inspect(via), inspect(modelos)
    tabelas = sorted(n for n in b.get_table_names() if n.startswith("wellhub_"))
    assert tabelas == sorted(n for n in a.get_table_names() if n.startswith("wellhub_")) and len(tabelas) == 7
    for t in tabelas:
        assert {c["name"]: c["nullable"] for c in a.get_columns(t)} == {c["name"]: c["nullable"] for c in b.get_columns(t)}, t
        assert sorted(u["name"] for u in a.get_unique_constraints(t)) == sorted(u["name"] for u in b.get_unique_constraints(t)), t
        assert sorted(i["name"] for i in a.get_indexes(t)) == sorted(i["name"] for i in b.get_indexes(t)), t
    with via.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        wellhub.downgrade()
    assert not [n for n in inspect(via).get_table_names() if n.startswith("wellhub_")]
