"""Regras puras do CRM."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.crm import regras
from app.modules.crm.models import MarcoEtapa, OrigemLead, SituacaoLead, StatusAulaExperimental

AGORA = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)  # 12h em São Paulo


@pytest.mark.parametrize("entrada,esperado", [
    ("site", OrigemLead.SITE), ("Instagram", OrigemLead.INSTAGRAM), ("indicação", OrigemLead.INDICACAO),
    ("Gympass", OrigemLead.WELLHUB), ("Wellhub/TotalPass", OrigemLead.WELLHUB), ("TotalPass", OrigemLead.TOTALPASS),
    ("panfleto", OrigemLead.OUTROS), (None, OrigemLead.OUTROS), (OrigemLead.PASSANTE, OrigemLead.PASSANTE),
])
def test_normalizar_origem(entrada, esperado):
    assert regras.normalizar_origem(entrada) == esperado


def test_normalizacoes():
    assert regras.normalizar_telefone("(11) 8765-4321") == "5511987654321"  # celular antigo ganha o nono dígito
    assert regras.normalizar_telefone("98765-4321") == "987654321"  # sem DDD: guarda os dígitos
    assert regras.normalizar_telefone("  ") is None
    assert regras.normalizar_email(" A@B.com ") == "a@b.com" and regras.normalizar_email("x") is None
    assert regras.normalizar_tags(["a", "A", " b  c ", "", "x" * 40]) == ["a", "b c", "x" * 30]


def test_classificar_tarefa_no_fuso_de_sao_paulo():
    assert regras.classificar_tarefa(AGORA - timedelta(minutes=1), False, AGORA) == "atrasada"
    assert regras.classificar_tarefa(AGORA + timedelta(hours=11), False, AGORA) == "hoje"  # 23h local
    assert regras.classificar_tarefa(AGORA + timedelta(hours=13), False, AGORA) == "futura"  # 01h do dia seguinte
    assert regras.classificar_tarefa(AGORA - timedelta(days=3), True, AGORA) == "concluida"


def test_horario_comercial():
    noite = datetime(2026, 10, 31, 23, 30, tzinfo=UTC)  # 20h30 local
    assert regras.horario_comercial(noite).astimezone(regras.FUSO).strftime("%d %H:%M") == "01 09:00"
    madrugada = datetime(2026, 10, 31, 7, 0, tzinfo=UTC)  # 04h local
    assert regras.horario_comercial(madrugada).astimezone(regras.FUSO).strftime("%d %H:%M") == "31 09:00"
    assert regras.horario_comercial(AGORA, minutos=15) == AGORA + timedelta(minutes=15)


def test_temperatura():
    t = lambda **k: regras.temperatura(**{"situacao": SituacaoLead.ABERTO, "dias_sem_contato": None, "dias_na_etapa": 0,
                                          "aula_status": None, "aula_em": None, "agora": AGORA, **k})
    assert t(aula_status=StatusAulaExperimental.AGENDADA, aula_em=AGORA + timedelta(days=1), dias_sem_contato=30) == "quente"
    assert t(dias_sem_contato=1) == "quente" and t(dias_sem_contato=5) == "morno" and t(dias_sem_contato=8) == "frio"
    assert t() == "morno" and t(dias_na_etapa=3) == "frio"
    assert t(situacao=SituacaoLead.GANHO) == "encerrado"


def test_esta_parado():
    assert regras.esta_parado(3, 3, SituacaoLead.ABERTO)
    assert not regras.esta_parado(2, 3, SituacaoLead.ABERTO)
    assert not regras.esta_parado(10, 0, SituacaoLead.ABERTO)
    assert not regras.esta_parado(10, 3, SituacaoLead.PERDIDO)


def test_sugestoes():
    s = lambda **k: regras.sugestao_proxima_acao(**{
        "situacao": SituacaoLead.ABERTO, "marco": None, "primeira_etapa": True, "tem_interacao": True, "aula_status": None,
        "aula_em": None, "dias_sem_contato": 0, "tem_telefone": True, "agora": AGORA, **k})
    assert "primeiro contato" in s(tem_interacao=False)
    assert "e-mail" in s(tem_interacao=False, tem_telefone=False)
    assert "aula experimental" in s()
    assert "confirme" in s(aula_status=StatusAulaExperimental.AGENDADA, aula_em=AGORA + timedelta(hours=20))
    assert "registre" in s(aula_status=StatusAulaExperimental.AGENDADA, aula_em=AGORA - timedelta(hours=2))
    assert "proposta" in s(aula_status=StatusAulaExperimental.REALIZADA, marco=MarcoEtapa.AULA_REALIZADA)
    assert "follow-up" in s(marco=MarcoEtapa.PROPOSTA, dias_sem_contato=3, primeira_etapa=False)
    assert s(situacao=SituacaoLead.GANHO) is None


def test_whatsapp_link_e_mensagens():
    assert regras.link_whatsapp("11 98765-4321") == "https://wa.me/5511987654321"
    assert regras.link_whatsapp("12345") is None
    assert regras.link_whatsapp("11987654321", "Oi, Ana!") == "https://wa.me/5511987654321?text=Oi%2C%20Ana%21"
    msgs = regras.mensagens_whatsapp(nome="ana souza", estudio="Studio Teste", interesse="Pilates", marco=MarcoEtapa.AULA_AGENDADA,
                                     situacao=SituacaoLead.ABERTO, aula_status=StatusAulaExperimental.AGENDADA,
                                     aula_em=datetime(2026, 11, 2, 13, 0, tzinfo=UTC))
    assert msgs[0]["titulo"] == "Confirmar aula experimental"
    assert "Oi, Ana!" in msgs[0]["texto"] and "Studio Teste" in msgs[0]["texto"] and "segunda, 02/11, às 10:00" in msgs[0]["texto"]
    assert any("pilates" in m["texto"] for m in msgs)


def test_funil_por_etapa():
    etapas = [regras.EtapaInfo(1, "Novo", 1, "ABERTA"), regras.EtapaInfo(2, "Aula", 2, "ABERTA"),
              regras.EtapaInfo(9, "Ganho", 1000, "GANHO"), regras.EtapaInfo(10, "Perdido", 1001, "PERDIDO")]
    escada = regras.etapas_do_funil(etapas)
    assert [e.id for e in escada] == [1, 2, 9]
    degraus = [regras.degrau_alcancado(escada, v) for v in ({1}, {1, 2}, {1, 2, 10}, {1, 9}, {10})]
    assert degraus == [0, 1, 1, 2, -1]
    r = regras.conversao_por_etapa(escada, [max(d, 0) for d in degraus])
    assert [(x["quantidade"], x["pct_total"], x["pct_anterior"]) for x in r] == [(5, 100.0, 100.0), (3, 60.0, 60.0), (1, 20.0, 33.3)]
    assert regras.conversao_por_etapa(escada, [])[0]["pct_anterior"] == 0.0


def test_medias_e_somas():
    assert regras.media_dias([timedelta(days=1), timedelta(days=2)]) == 1.5
    assert regras.media_dias([]) is None
    assert regras.percentual(1, 3) == 33.3 and regras.percentual(1, 0) == 0.0
