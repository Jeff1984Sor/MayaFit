"""Aulas do aluno: listar, confirmar (R15), desmarcar (R4), isolamento entre alunos e reposição."""

from datetime import date

from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from tests.agenda import fabrica
from tests.app_aluno.conftest import AGORA_FIXO, cab, entrar_aluno

B = "/api/aluno-app"


def _tokens_bruna(client, zap, cenario):
    return cab(entrar_aluno(client, zap, cenario.bruna))


def test_lista_so_as_proprias_aulas_futuras_sem_canceladas(client, db, cenario, ana_logada):
    passada = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 20))
    fabrica.reserva_direta(db, cenario.ana, passada)
    cancelada = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 27))
    rc = fabrica.reserva_direta(db, cenario.ana, cancelada)
    agenda.desmarcar_reserva(db, rc.id, agora=AGORA_FIXO)  # mesmo relógio congelado do app
    db.commit()
    aulas = client.get(f"{B}/aulas", headers=ana_logada).json()
    assert [a["id"] for a in aulas] == [cenario.r_ana.id]
    a = aulas[0]
    assert (a["data"], a["hora_inicio"], a["profissional"], a["servico"]) == ("2026-10-26", "09:00:00", "Natalia Souza", "Pilates")
    assert a["status"] == "aguardando_chegar" and a["pode_confirmar"] and a["pode_desmarcar"] and not a["confirmada"]
    assert a["desmarcar_ate"] == "26/10 às 03:00"


def test_aluna_nao_ve_a_aula_de_outra(client, cenario, ana_logada):
    ids = {a["id"] for a in client.get(f"{B}/aulas", headers=ana_logada).json()}
    assert cenario.r_bruna.id not in ids


def test_confirmar_grava_confirmada_em(client, db, cenario, ana_logada):
    r = client.post(f"{B}/aulas/{cenario.r_ana.id}/confirmar", headers=ana_logada)
    assert r.status_code == 200
    j = r.json()
    assert j["confirmada"] is True and j["pode_confirmar"] is False
    db.expire_all()
    assert db.get(Reserva, cenario.r_ana.id).confirmada_em is not None
    aud = db.scalars(select(Auditoria).where(Auditoria.acao == "aluno_app.confirmar")).one()
    assert aud.entidade_id == str(cenario.r_ana.id) and "Ana" in aud.usuario_nome


def test_desmarcar_aplica_r4_e_libera_a_vaga(client, db, cenario, ana_logada):
    r = client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    assert r.status_code == 200
    # aula de 26/10 -> reposição até 25/11 (30 dias)
    assert r.json()["reposicao_ate"] == "2026-11-25" and "25/11/2026" in r.json()["mensagem"]
    db.expire_all()
    res = db.get(Reserva, cenario.r_ana.id)
    assert res.status == StatusReserva.CANCELADA and res.reposicao_ate == date(2026, 11, 25)
    assert res.desmarcada_em is not None and res.confirmada_em is None
    assert db.get(AulaSessao, cenario.s9.id).reservas_ativas == 0
    assert client.get(f"{B}/aulas", headers=ana_logada).json() == []


def test_desmarcar_de_novo_409_e_nao_estende_o_prazo(client, db, cenario, ana_logada):
    client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    r = client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    assert r.status_code == 409
    assert client.post(f"{B}/aulas/{cenario.r_ana.id}/confirmar", headers=ana_logada).status_code == 409


def test_aula_concluida_ou_passada_nao_confirma_nem_desmarca(client, db, cenario, ana_logada):
    velha = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 20))
    rv = fabrica.reserva_direta(db, cenario.ana, velha)
    db.commit()
    assert client.post(f"{B}/aulas/{rv.id}/confirmar", headers=ana_logada).status_code == 409
    assert client.post(f"{B}/aulas/{rv.id}/desmarcar", headers=ana_logada).status_code == 409
    futura = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 28))
    rf = fabrica.reserva_direta(db, cenario.ana, futura, status=StatusReserva.CONCLUIDA)
    db.commit()
    assert client.post(f"{B}/aulas/{rf.id}/desmarcar", headers=ana_logada).status_code == 409


def test_isolamento_id_alheio_e_404_em_todas_as_acoes(client, db, zap, cenario, ana_logada):
    alheio = cenario.r_bruna.id
    for acao in ("confirmar", "desmarcar"):
        assert client.post(f"{B}/aulas/{alheio}/{acao}", headers=ana_logada).status_code == 404
    assert client.post(f"{B}/reposicoes/{alheio}/pedir", json={}, headers=ana_logada).status_code == 404
    assert client.post(f"{B}/aulas/999999/confirmar", headers=ana_logada).status_code == 404  # inexistente = igual
    db.expire_all()
    assert db.get(Reserva, alheio).status == StatusReserva.RESERVADA and db.get(Reserva, alheio).confirmada_em is None


def test_reposicoes_lista_a_desmarcada_com_prazo(client, cenario, ana_logada):
    assert client.get(f"{B}/reposicoes", headers=ana_logada).json() == []
    client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    lista = client.get(f"{B}/reposicoes", headers=ana_logada).json()
    assert len(lista) == 1
    assert lista[0]["reposicao_ate"] == "2026-11-25" and lista[0]["dias_restantes"] == 31 and lista[0]["dentro_do_prazo"]
