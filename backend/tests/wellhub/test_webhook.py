"""Webhook do Wellhub: assinatura (válida/ inválida), reservas com capacidade, cancelamento, check-in, idempotência,
resposta ao Wellhub (PATCH), reprocessar. Payloads sintéticos; o Wellhub é um MockTransport.
"""

from __future__ import annotations

from datetime import time

import pytest
from sqlalchemy import func, select

from app.core.models import Auditoria
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno, AlunoTelefone
from app.modules.wellhub import routes as rotas
from app.modules.wellhub.models import (
    WellhubAluno,
    WellhubCheckin,
    WellhubConfig,
    WellhubEvento,
    WellhubReserva,
    WellhubSlot,
)
from tests.wellhub.conftest import (
    GYM,
    SEGREDO,
    Wellhub,
    assinado,
    cancelamento,
    checkin,
    enviar,
    instalar,
    reserva_pedida,
    sessao,
)

URL = "/api/webhooks/wellhub"


def total(db, modelo):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo))


def ultimo(db, **filtros):
    db.expire_all()
    q = select(WellhubEvento).order_by(WellhubEvento.id.desc())
    for k, v in filtros.items():
        q = q.where(getattr(WellhubEvento, k) == v)
    return db.scalars(q).first()


@pytest.fixture
def publicado(client, db, base, full, configurado, wh):
    """Uma aula amanhã às 9h publicada no Wellhub (slot 9001, classe 501)."""
    s = sessao(db, base)
    r = client.post(f"/api/wellhub/unidades/{base.uid}/grade/publicar", headers=full)
    assert r.status_code == 200 and r.json()["slots_criados"] == 1, r.text
    wh.chamadas.clear()
    return s


# ------------------------------------------------------------------------------------------------ assinatura
def test_sem_segredo_configurado_recusa(client, db, base):
    r = enviar(client, checkin())
    assert r.status_code == 403 and "não configurado" in r.json()["detail"]
    assert total(db, WellhubEvento) == 0


def test_assinatura_ausente_401_e_invalida_403(client, db, configurado):
    bruto, _ = assinado(checkin())
    assert client.post(URL, content=bruto, headers={"Content-Type": "application/json"}).status_code == 401
    assert enviar(client, checkin(), segredo="outro-segredo-qualquer-123").status_code == 403
    bruto, h = assinado(checkin())
    assert client.post(URL, content=bruto + b" ", headers=h).status_code == 403  # corpo alterado depois de assinado
    assert client.post(URL, content=bruto, headers={**h, "X-Gympass-Signature": "assinatura-ñ".encode()}).status_code in (400, 403)
    assert total(db, WellhubEvento) == 0 and total(db, Aluno) == 0


def test_assinatura_valida_aceita(client, db, configurado):
    r = enviar(client, checkin())
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["resultado"] == "processado"


def test_assinatura_calculada_sobre_o_corpo_cru(client, db, configurado):
    """Mesmo JSON com outra formatação = outra assinatura: o servidor confere os BYTES recebidos."""
    bruto = b'{ "event_type" : "checkin", "event_data": {"user": {"unique_token": "1234567890123"}, "gym": {"id": 777}}}'
    _, h = assinado(bruto)
    assert client.post(URL, content=bruto, headers=h).status_code == 200


def test_falha_de_assinatura_vira_alerta_no_painel(client, db, base, full, configurado):
    corpo = checkin()
    enviar(client, corpo, segredo="segredo-errado-0000000")
    enviar(client, corpo, segredo="segredo-errado-0000000")
    db.expire_all()
    assert db.scalar(select(WellhubConfig.falhas_assinatura)) == 2
    painel = client.get(f"/api/wellhub/unidades/{base.uid}/painel", headers=full).json()
    assert any(a["titulo"] == "Chamadas com assinatura inválida" for a in painel["alertas"])


def test_token_de_usuario_logado_nao_vale_no_webhook(client, configurado, full):
    bruto, _ = assinado(checkin())
    assert client.post(URL, content=bruto, headers={**full, "Content-Type": "application/json"}).status_code == 401


def test_so_aceita_post_e_json_objeto(client, configurado):
    assert client.get(URL).status_code == 405
    assert enviar(client, b"nao e json").status_code == 422
    assert enviar(client, b"[1, 2]").status_code == 422


def test_payload_grande_demais(client, configurado):
    bruto, h = assinado(b"{}")
    assert client.post(URL, content=bruto, headers={**h, "Content-Length": str(10**7)}).status_code in (400, 413)


def test_rate_limit_das_falhas(client, configurado, monkeypatch):
    monkeypatch.setattr(rotas, "LIMITE_FALHAS_WEBHOOK_POR_IP", 2)
    codigos = [enviar(client, checkin(), segredo=f"chute-{i}-0000000000").status_code for i in range(4)]
    assert codigos == [403, 403, 429, 429]


def test_integracao_desativada_202_e_nao_grava(client, db, base, full, configurado):
    client.put(f"/api/wellhub/unidades/{base.uid}", headers=full, json={"ativo": False})
    r = enviar(client, checkin())
    assert r.status_code == 202 and total(db, WellhubEvento) == 0


def test_gym_de_outro_estudio_e_recusado(client, db, configurado):
    p = checkin()
    p["event_data"]["gym"]["id"] = 999
    r = enviar(client, p)
    assert r.status_code == 400 and total(db, WellhubEvento) == 0


# ------------------------------------------------------------------------------------------------ reservas
def test_reserva_cria_aluno_reserva_e_responde_aceito(client, db, base, publicado, wh):
    r = enviar(client, reserva_pedida(slot="9001", booking="BK-1"))
    assert r.status_code == 200 and r.json()["resultado"] == "processado" and r.json()["reserva_id"], r.text
    db.expire_all()
    aluno = db.scalar(select(Aluno))
    assert aluno.nome == "Maria Sintética" and aluno.sem_cpf is True and aluno.cpf is None and aluno.unidade_id == base.uid
    assert db.scalar(select(WellhubAluno.gympass_id)) == "1234567890123"
    assert db.scalar(select(AlunoTelefone.numero)) == "5511988887777"
    reserva = db.scalar(select(Reserva))
    assert reserva.aula_sessao_id == publicado.id and reserva.status == StatusReserva.RESERVADA
    wr = db.scalar(select(WellhubReserva))
    assert wr.booking_number == "BK-1" and wr.situacao == "reservada" and wr.resposta_enviada == "reservado"
    patches = wh.corpos("PATCH", r"/bookings/BK-1$")
    assert patches == [{"status": 2}]
    # as vagas do horário foram reenviadas (1 reservada de 2)
    assert wh.corpos("PATCH", r"/slots/9001$") == [{"total_capacity": 2, "total_booked": 1}]
    ev = ultimo(db)
    assert ev.resultado == "processado" and ev.processado_em and ev.reserva_id == reserva.id and ev.tentativas == 1


def test_idempotencia_reenvio_nao_duplica(client, db, publicado, wh):
    corpo = reserva_pedida()
    primeira = enviar(client, corpo)
    segunda = enviar(client, corpo)
    assert primeira.status_code == 200 and segunda.json()["duplicado"] is True
    assert total(db, WellhubEvento) == 1 and total(db, Reserva) == 1 and total(db, Aluno) == 1
    assert len(wh.corpos("PATCH", r"/bookings/")) == 1  # não respondeu duas vezes
    db.expire_all()
    assert db.scalar(select(AulaSessao.reservas_ativas)) == 1


def test_idempotencia_por_id_explicito(client, db, configurado):
    a = {**checkin(), "event_id": "evt-1"}
    b = {**checkin(ts=1), "event_id": "evt-1"}  # mesmo id, conteúdo diferente: é o mesmo evento
    enviar(client, a)
    assert enviar(client, b).json()["duplicado"] is True
    assert total(db, WellhubEvento) == 1


def test_mesmo_aluno_reconhecido_pelo_gympass_id(client, db, base, full, publicado, wh):
    s2 = sessao(db, base, hora=time(10, 0))
    client.post(f"/api/wellhub/unidades/{base.uid}/grade/publicar", headers=full)
    slot2 = db.scalar(select(WellhubSlot.slot_id).where(WellhubSlot.aula_sessao_id == s2.id))
    enviar(client, reserva_pedida(booking="BK-1"))
    enviar(client, reserva_pedida(booking="BK-2", slot=slot2, nome="Outro Nome"))
    assert total(db, Aluno) == 1 and total(db, Reserva) == 2


def test_aluno_existente_vinculado_pelo_cpf(client, db, base, publicado, wh):
    a = Aluno(nome="Aluna Antiga", cpf="52998224725", unidade_id=base.uid, codigo_legado=5000)
    db.add(a)
    db.commit()
    p = reserva_pedida()
    p["event_data"]["user"]["document"] = "529.982.247-25"
    assert enviar(client, p).status_code == 200
    db.expire_all()
    assert total(db, Aluno) == 1 and db.scalar(select(WellhubAluno.aluno_id)) == a.id
    assert db.get(Aluno, a.id).nome == "Aluna Antiga"  # não sobrescreve o cadastro


def test_capacidade_cheia_rejeita_no_wellhub(client, db, base, publicado, wh):
    assert enviar(client, reserva_pedida("1000000000001", booking="A")).json()["resultado"] == "processado"
    assert enviar(client, reserva_pedida("1000000000002", booking="B")).json()["resultado"] == "processado"
    r = enviar(client, reserva_pedida("1000000000003", booking="C"))
    assert r.status_code == 200 and r.json()["resultado"] == "rejeitado"
    assert wh.corpos("PATCH", r"/bookings/C$") == [{"status": 3, "reason": "CLASS_IS_FULL"}]
    db.expire_all()
    assert total(db, Reserva) == 2 and db.scalar(select(AulaSessao.reservas_ativas)) == 2
    # o aluno da reserva recusada não ficou criado pela metade
    assert db.scalar(select(WellhubAluno).where(WellhubAluno.gympass_id == "1000000000003")) is None
    ev = ultimo(db, booking_number="C")
    assert ev.resultado == "rejeitado" and "CLASS_IS_FULL" in ev.erro and "Capacidade excedida" in ev.erro
    assert db.scalar(select(WellhubReserva.situacao).where(WellhubReserva.booking_number == "C")) == "rejeitada"


def test_capacidade_respeita_reservas_feitas_pela_agenda(client, db, base, publicado, wh):
    """A vaga é a da agenda (mesma regra de bloqueio): alunos do estúdio também ocupam."""
    from app.modules.agenda import servico as agenda

    for n in range(2):
        a = Aluno(nome=f"Local {n}", sem_cpf=True, unidade_id=base.uid, codigo_legado=6000 + n)
        db.add(a)
        db.flush()
        agenda.criar_reserva(db, a.id, publicado.id)
    db.commit()
    assert enviar(client, reserva_pedida()).json()["resultado"] == "rejeitado"


def test_slot_desconhecido_vira_erro_sem_responder(client, db, publicado, wh):
    r = enviar(client, reserva_pedida(slot="123456"))
    assert r.status_code == 200 and r.json()["ok"] is False and "não foi publicado" in r.json()["erro"]
    assert wh.corpos("PATCH", r"/bookings/") == [] and total(db, Aluno) == 0


def test_resposta_ao_wellhub_falha_e_o_reprocessar_reenvia(client, db, full, publicado, wh):
    instalar(falho := Wellhub(reserva=500))
    r = enviar(client, reserva_pedida())
    assert r.json()["resultado"] == "erro" and "Reserva feita aqui" in r.json()["erro"]
    assert total(db, Reserva) == 1
    ev = ultimo(db)
    assert ev.resultado == "erro" and ev.reserva_id
    assert len(falho.corpos("PATCH", r"/bookings/")) == 1
    instalar(ok := Wellhub())
    rr = client.post(f"/api/wellhub/eventos/{ev.id}/reprocessar", headers=full)
    assert rr.status_code == 200 and rr.json()["resultado"] == "processado", rr.text
    assert ok.corpos("PATCH", r"/bookings/BK-1$") == [{"status": 2}]
    assert total(db, Reserva) == 1 and total(db, WellhubEvento) == 1
    assert ultimo(db).tentativas == 2
    # reprocessar de novo um evento já resolvido é recusado
    assert client.post(f"/api/wellhub/eventos/{ev.id}/reprocessar", headers=full).status_code == 409


def test_cancelamento_libera_a_vaga(client, db, publicado, wh):
    enviar(client, reserva_pedida("1000000000001", booking="A"))
    enviar(client, reserva_pedida("1000000000002", booking="B"))
    r = enviar(client, cancelamento("A"))
    assert r.status_code == 200 and r.json()["resultado"] == "cancelado"
    db.expire_all()
    assert db.scalar(select(AulaSessao.reservas_ativas)) == 1
    assert db.scalar(select(WellhubReserva.situacao).where(WellhubReserva.booking_number == "A")) == "cancelada"
    assert enviar(client, reserva_pedida("1000000000003", booking="C")).json()["resultado"] == "processado"


def test_cancelamento_tardio(client, db, publicado, wh):
    enviar(client, reserva_pedida())
    assert enviar(client, cancelamento(tardio=True)).json()["resultado"] == "cancelado"
    db.expire_all()
    assert db.scalar(select(WellhubReserva.situacao)) == "cancelada_tarde"
    assert db.scalar(select(Reserva.status)) == StatusReserva.CANCELADA


def test_cancelar_sem_reserva_nao_cria_nada(client, db, publicado, wh):
    r = enviar(client, cancelamento("NAO-EXISTE"))
    assert r.json()["resultado"] == "cancelado" and r.json()["reserva_id"] is None
    assert total(db, Aluno) == 0 and total(db, Reserva) == 0


def test_reservar_de_novo_depois_de_cancelar_reativa(client, db, publicado, wh):
    enviar(client, reserva_pedida(booking="A"))
    enviar(client, cancelamento("A"))
    assert enviar(client, reserva_pedida(booking="B")).json()["resultado"] == "processado"
    db.expire_all()
    assert total(db, Reserva) == 1 and db.scalar(select(Reserva.status)) == StatusReserva.RESERVADA


def test_criacao_automatica_desligada(client, db, base, full, publicado, wh):
    client.put(f"/api/wellhub/unidades/{base.uid}", headers=full, json={"criar_aluno_automatico": False})
    r = enviar(client, reserva_pedida())
    assert r.json()["resultado"] == "erro" and "criação automática" in r.json()["erro"]
    assert total(db, Aluno) == 0


def test_reserva_sem_numero_e_sem_gympass(client, db, publicado, wh):
    p = reserva_pedida()
    del p["event_data"]["slot"]["booking_number"]
    assert "booking_number" in enviar(client, p).json()["erro"]
    p = reserva_pedida(gympass="")
    assert "Gympass ID" in enviar(client, p).json()["erro"]


# ------------------------------------------------------------------------------------------------ check-in
def test_checkin_cria_aluno_e_checkin_pendente(client, db, base, configurado):
    r = enviar(client, checkin())
    assert r.json()["resultado"] == "processado"
    db.expire_all()
    ck = db.scalar(select(WellhubCheckin))
    assert ck.validado is False and ck.origem == "webhook" and ck.gympass_id == "1234567890123" and ck.produto == "Pilates"
    assert db.get(Aluno, ck.aluno_id).nome == "Carla Sintética"
    # segundo check-in no mesmo dia não duplica a contagem
    enviar(client, checkin(ts=int(ck.ocorrido_em.timestamp()) + 60))
    assert total(db, WellhubCheckin) == 1 and total(db, WellhubEvento) == 2


def test_checkin_com_validacao_automatica(client, db, base, full, configurado, wh):
    client.put(f"/api/wellhub/unidades/{base.uid}", headers=full, json={"validar_checkin_automatico": True})
    enviar(client, checkin())
    db.expire_all()
    assert db.scalar(select(WellhubCheckin.validado)) is True
    assert wh.corpos("POST", r"/access/v1/validate$") == [{"gympass_id": "1234567890123"}]


def test_checkin_em_aula_reservada_marca_presenca(client, db, publicado, wh):
    enviar(client, reserva_pedida())
    p = {"event_type": "checkin-booking-occurred", "event_data": {
        "user": {"unique_token": "1234567890123"}, "slot": {"id": "9001", "gym_id": GYM, "booking_number": "BK-1"}}}
    r = enviar(client, p)
    assert r.json()["resultado"] == "processado"
    db.expire_all()
    reserva = db.scalar(select(Reserva))
    assert reserva.confirmada_em is not None and reserva.status == StatusReserva.RESERVADA
    ck = db.scalar(select(WellhubCheckin))
    assert ck.reserva_id == reserva.id and ck.origem == "reserva"


def test_tipo_desconhecido_e_descartado(client, db, configurado):
    r = enviar(client, {"event_type": "user-updated", "event_data": {"gym_id": GYM}})
    assert r.status_code == 202 and "não tratado" in r.json()["descartado"]
    assert ultimo(db).resultado == "descartado"


# ------------------------------------------------------------------------------------------------ segurança/auditoria
def test_auditoria_sem_dados_sensiveis(client, db, publicado, wh):
    enviar(client, reserva_pedida())
    enviar(client, cancelamento())
    db.expire_all()
    acoes = [a.acao for a in db.scalars(select(Auditoria).where(Auditoria.acao.like("wellhub.%")))]
    assert {"wellhub.aluno_criar", "wellhub.reserva_criar", "wellhub.reserva_cancelar"} <= set(acoes)
    tudo = " ".join(f"{a.descricao} {a.antes_json} {a.depois_json}" for a in db.scalars(select(Auditoria)))
    assert SEGREDO not in tudo and "1234567890123" not in tudo


def test_resposta_do_webhook_nao_vaza_dados(client, publicado, wh):
    r = enviar(client, reserva_pedida())
    assert set(r.json()) == {"ok", "evento_id", "resultado", "reserva_id"}
    assert "1234567890123" not in r.text and SEGREDO not in r.text
