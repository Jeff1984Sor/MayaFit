"""Regras puras do Wellhub: assinatura, leitura do payload, idempotência, vagas, repasse, assistente e alertas."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.wellhub import regras as r


def test_assinatura_hmac_sha1_hex_maiusculo():
    corpo = b'{"event_type":"checkin"}'
    esperado = hmac.new(b"segredo", corpo, hashlib.sha1).hexdigest().upper()
    assert r.assinar("segredo", corpo) == esperado
    assert r.assinatura_confere("segredo", corpo, esperado)
    assert r.assinatura_confere("segredo", corpo, esperado.lower())  # tolera minúsculas
    assert r.assinatura_confere("segredo", corpo, "sha1=" + esperado)


@pytest.mark.parametrize("recebida", [None, "", "abc", "ñão-ascii", "0" * 40])
def test_assinatura_invalida(recebida):
    assert not r.assinatura_confere("segredo", b"{}", recebida)


def test_assinatura_muda_com_um_byte_e_com_o_segredo():
    s = r.assinar("segredo", b"{}")
    assert not r.assinatura_confere("segredo", b"{} ", s)
    assert not r.assinatura_confere("outro", b"{}", s)
    assert not r.assinatura_confere("", b"{}", s)


def test_leitura_do_payload_de_reserva():
    p = {"event_type": "booking-requested", "event_data": {
        "user": {"unique_token": " 1234567890123 ", "name": "Ana"}, "slot": {"id": 55, "gym_id": 9, "booking_number": "B-1"},
        "timestamp": 1790000000}}
    assert r.tipo_do_evento(p) == r.RESERVA_PEDIDA
    assert r.gympass_id(p) == "1234567890123" and r.slot_id(p) == "55" and r.gym_id(p) == "9"
    assert r.booking_number(p) == "B-1" and r.nome_do_usuario(p) == "Ana"
    assert r.instante_do_evento(p, datetime(2000, 1, 1, tzinfo=UTC)) == datetime.fromtimestamp(1790000000, UTC)


@pytest.mark.parametrize("bruto,esperado", [("booking-cancelled", r.RESERVA_CANCELADA), ("BOOKING-LATE-CANCELED", r.RESERVA_CANCELADA_TARDE),
                                            ("check-in", r.CHECKIN), ("checkin-booking-occurred", r.CHECKIN_RESERVA),
                                            ("outro", "outro"), ("", "")])
def test_sinonimos_dos_tipos(bruto, esperado):
    assert r.tipo_do_evento({"event_type": bruto}) == esperado


def test_nome_por_partes_e_documento():
    p = {"event_data": {"user": {"first_name": "Carla", "last_name": "Souza", "document": "529.982.247-25"}}}
    assert r.nome_do_usuario(p) == "Carla Souza" and r.documento_do_usuario(p) == "52998224725"


@pytest.mark.parametrize("ts", [1790000000, 1790000000000, "1790000000", "2026-09-21T12:53:20Z"])
def test_instante_em_varios_formatos(ts):
    v = r.instante_do_evento({"event_data": {"timestamp": ts}}, datetime(2000, 1, 1, tzinfo=UTC))
    assert v.year == 2026 and v.tzinfo is not None


def test_instante_invalido_usa_o_padrao():
    padrao = datetime(2000, 1, 1, tzinfo=UTC)
    assert r.instante_do_evento({"event_data": {"timestamp": "ontem"}}, padrao) == padrao
    assert r.instante_do_evento({}, padrao) == padrao


def test_chave_do_evento_explicita_ou_hash_estavel():
    assert r.chave_do_evento({"event_id": "abc"}) == "id:abc"
    a = {"event_type": "checkin", "event_data": {"user": {"unique_token": "1"}, "timestamp": 1}}
    b = {"event_data": {"timestamp": 1, "user": {"unique_token": "1"}}, "event_type": "checkin"}  # outra ordem
    assert r.chave_do_evento(a) == r.chave_do_evento(b) and r.chave_do_evento(a).startswith("sha256:")
    c = {**a, "event_data": {**a["event_data"], "timestamp": 2}}
    assert r.chave_do_evento(a) != r.chave_do_evento(c)
    assert len(r.chave_do_evento(a)) <= 80


def test_acao_do_slot_e_vagas():
    v = r.Vagas(5, 1)
    assert r.acao_do_slot(None, v) == "criar"
    assert r.acao_do_slot(v, r.Vagas(5, 1)) == "manter"
    assert r.acao_do_slot(v, r.Vagas(5, 2)) == "atualizar"
    assert r.acao_do_slot(v, None) == "remover"
    assert r.acao_do_slot(None, None) == "manter"
    assert r.vagas_para_publicar(2, 5) == r.Vagas(2, 2)  # nunca mais reservas que vagas
    assert r.vagas_para_publicar(-1, -3) == r.Vagas(0, 0)


def test_valor_estimado_e_variacao():
    assert r.valor_estimado(10, Decimal("12.50")) == Decimal("125.00")
    assert r.valor_estimado(3, Decimal("0.335")) == Decimal("1.01")
    assert r.valor_estimado(0, Decimal("10")) == Decimal("0.00")
    assert r.valor_estimado(5, None) == Decimal("0.00")
    assert r.variacao(12, 10) == 0.2 and r.variacao(5, 0) is None


def test_passos_do_assistente():
    vazio = r.passos_do_assistente(r.EstadoConfig())
    assert [p.id for p in vazio] == ["credenciais", "webhook", "mapeamento", "grade", "repasse"]
    assert not any(p.concluido for p in vazio) and all(p.pendencia for p in vazio)
    pronto = r.passos_do_assistente(r.EstadoConfig(existe=True, ativo=True, gym_id=True, api_key=True, webhook_secret=True,
                                                   teste_ok=True, mapeamentos_com_produto=1, mapeamentos_publicados=1,
                                                   sync_ok=True, slots_publicados=3, valor_repasse=True))
    assert all(p.concluido for p in pronto)
    sem_teste = r.passos_do_assistente(r.EstadoConfig(gym_id=True, api_key=True))
    assert sem_teste[0].pendencia == "Teste a conexão com o Wellhub."


def test_alertas():
    nada = r.montar_alertas(ativo=True, configurada=True, eventos_com_erro=0, falhas_assinatura_24h=0, sync_ok=True,
                            sync_resumo=None, teste_ok=True, checkins_sem_validacao=0, reservas_sem_resposta=0)
    assert nada == []
    tudo = r.montar_alertas(ativo=False, configurada=True, eventos_com_erro=2, falhas_assinatura_24h=3, sync_ok=False,
                            sync_resumo="Erro: x", teste_ok=False, checkins_sem_validacao=4, reservas_sem_resposta=1)
    assert [a.nivel for a in tudo] == ["danger", "danger", "warning", "danger", "warning", "warning", "info"]
    assert "15 minutos" in tudo[0].descricao and "2 evento" in tudo[1].titulo


def test_mascarar_gympass():
    assert r.mascarar_gympass("1234567890123") == "•••••••••0123"
    assert r.mascarar_gympass(None) is None
