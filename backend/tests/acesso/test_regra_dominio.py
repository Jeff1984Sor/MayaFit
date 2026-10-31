"""Regra de acesso (função pura `app.domain.acesso.decidir_acesso`) e utilidades do reconhecimento."""

from datetime import UTC, date, datetime, time

import pytest

from app.domain import acesso as dom

FUSO = dom.FUSO
HOJE = date(2026, 10, 26)  # segunda
ANA = dom.AlunoRef(1, "ana paula souza", True, date(1990, 3, 10))
CONTRATO = dom.ContratoRef(10, date(2026, 10, 1), date(2026, 12, 31), "Pilates 2x")
LIVRE = dom.ContratoRef(11, date(2026, 10, 1), date(2026, 12, 31), "Academia", acesso_livre=True)
AULA9 = dom.AulaRef(100, 200, HOJE, time(9, 0), time(9, 50), "Pilates", "Natalia Souza", contrato_id=10)
FUNC = [dom.Janela(time(6, 0), time(12, 0)), dom.Janela(time(14, 0), time(22, 0))]


def em(h, m=0, dia=HOJE):
    return datetime.combine(dia, time(h, m), tzinfo=FUSO)


def decidir(agora, **kw):
    base = {"aluno": ANA, "contratos": [CONTRATO], "aulas_hoje": [AULA9], "funcionamento_hoje": FUNC}
    base.update(kw)
    return dom.decidir_acesso(agora=agora, **base)


@pytest.mark.parametrize("h,m", [(8, 30), (8, 50), (9, 0), (9, 15)])
def test_aula_dentro_da_janela_libera_e_aponta_a_reserva(h, m):
    d = decidir(em(h, m))
    assert d.permitido and d.codigo == dom.OK_AULA
    assert d.aula.reserva_id == 100
    assert d.motivo == "Aula de Pilates às 09:00"
    assert d.primeiro_nome == "Ana"
    assert d.previsto_sair == em(10, 5)


def test_antes_da_janela_explica_quando_libera():
    d = decidir(em(8, 29))
    assert not d.permitido and d.codigo == dom.NEG_CEDO
    assert d.motivo == "Sua aula de Pilates é às 09:00. A entrada libera a partir das 08:30."


def test_depois_da_janela_nega_com_horario():
    d = decidir(em(9, 16))
    assert not d.permitido and d.codigo == dom.NEG_TARDE
    assert "09:15" in d.motivo


def test_janela_configuravel():
    cfg = dom.ConfigRegra(janela_antes_min=60, janela_depois_min=0)
    assert decidir(em(8, 0), config=cfg).permitido
    assert not decidir(em(9, 1), config=cfg).permitido


def test_sem_aula_marcada():
    d = decidir(em(10), aulas_hoje=[])
    assert not d.permitido and d.codigo == dom.NEG_SEM_AULA and d.motivo == "Sem aula marcada agora."


def test_inativo_nunca_entra():
    d = decidir(em(9), aluno=dom.AlunoRef(1, "Ana", ativo=False))
    assert not d.permitido and d.codigo == dom.NEG_INATIVO


def test_mensalidade_atrasada_alem_da_tolerancia_bloqueia_com_data():
    d = decidir(em(9), vencimentos_em_aberto=[date(2026, 10, 5), date(2026, 10, 20)])
    assert not d.permitido and d.codigo == dom.NEG_ATRASO
    assert d.motivo == "Mensalidade em atraso desde 05/10. Procure a recepção."


def test_atraso_dentro_da_tolerancia_entra_com_aviso_gentil():
    d = decidir(em(9), vencimentos_em_aberto=[date(2026, 10, 22)])  # 4 dias, tolerância 5
    assert d.permitido
    assert d.avisos == ["Sua mensalidade venceu em 22/10. Quando puder, passe na recepção."]


def test_tolerancia_configuravel_no_limite():
    venc = [date(2026, 10, 21)]  # 5 dias
    assert decidir(em(9), vencimentos_em_aberto=venc, config=dom.ConfigRegra(tolerancia_atraso_dias=5)).permitido
    assert not decidir(em(9), vencimentos_em_aberto=venc, config=dom.ConfigRegra(tolerancia_atraso_dias=4)).permitido
    assert decidir(em(9), vencimentos_em_aberto=[HOJE]).permitido  # vence hoje não é atraso


def test_contrato_vencido_nega_aula_do_contrato_e_diz_quando_terminou():
    velho = dom.ContratoRef(10, date(2026, 7, 1), date(2026, 9, 30), "Pilates")
    d = decidir(em(10), contratos=[velho], aulas_hoje=[])
    assert not d.permitido and d.codigo == dom.NEG_SEM_CONTRATO
    assert "30/09/2026" in d.motivo
    # aula do contrato vencido também não libera
    assert not decidir(em(9), contratos=[velho]).permitido


def test_aula_sem_contrato_avulsa_ou_totalpass_libera():
    avulsa = dom.AulaRef(101, 201, HOJE, time(9, 0), time(9, 50), "Pilates", None, contrato_id=None)
    d = decidir(em(9), contratos=[], aulas_hoje=[avulsa])
    assert d.permitido and d.aula.reserva_id == 101


def test_plano_livre_entra_no_horario_de_funcionamento_sem_aula():
    d = decidir(em(15, 30), contratos=[LIVRE], aulas_hoje=[])
    assert d.permitido and d.codigo == dom.OK_LIVRE
    assert d.motivo == "Acesso livre (Academia)"
    assert d.previsto_sair == em(17, 0)


def test_plano_livre_fora_do_horario_diz_quando_abre():
    d = decidir(em(13), contratos=[LIVRE], aulas_hoje=[])
    assert not d.permitido and d.codigo == dom.NEG_FORA_HORARIO
    assert d.motivo.endswith("Abrimos às 14:00.")
    assert decidir(em(23), contratos=[LIVRE], aulas_hoje=[]).motivo == "Fora do horário de funcionamento."


def test_duas_aulas_escolhe_a_mais_proxima():
    a10 = dom.AulaRef(102, 202, HOJE, time(9, 30), time(10, 20), "Funcional", None, contrato_id=10)
    d = decidir(em(9, 20), aulas_hoje=[AULA9, a10])
    assert d.aula.reserva_id == 102


def test_aniversario_e_horario_utc():
    aniv = dom.AlunoRef(1, "Ana", True, date(1990, 10, 26))
    agora_utc = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # 09:00 em Brasília
    d = decidir(agora_utc, aluno=aniv)
    assert d.permitido and d.aniversario
    assert dom.faz_aniversario(date(2000, 2, 29), date(2027, 2, 28))


# ------------------------------------------------------------------------------------------ reconhecimento
def test_normalizar_rejeita_lixo():
    with pytest.raises(dom.DescritorInvalido):
        dom.normalizar_descritor([0.1] * 10)
    with pytest.raises(dom.DescritorInvalido):
        dom.normalizar_descritor([0.0] * 128)
    with pytest.raises(dom.DescritorInvalido):
        dom.normalizar_descritor([float("nan")] * 128)
    v = dom.normalizar_descritor([3.0, 4.0] * 64)
    assert abs(dom.similaridade(v, v) - 1) < 1e-9


def test_correspondencia_limiar_e_ambiguidade():
    a = dom.normalizar_descritor([1.0, 0.0] * 64)
    b = dom.normalizar_descritor([0.0, 1.0] * 64)
    quase_a = dom.normalizar_descritor([1.0, 0.1] * 64)
    r = dom.melhor_correspondencia(quase_a, [(1, a), (2, b)], limiar=0.6)
    assert r.aluno_id == 1 and r.similaridade > 0.99
    assert not dom.melhor_correspondencia(quase_a, [(1, a)], limiar=0.999).reconhecido
    meio = dom.normalizar_descritor([1.0, 1.0] * 64)
    amb = dom.melhor_correspondencia(meio, [(1, a), (2, b)], limiar=0.5)
    assert not amb.reconhecido and "certeza" in amb.motivo
    assert not dom.melhor_correspondencia(a, [], limiar=0.5).reconhecido


def test_qr_assinado_vence_e_nao_aceita_adulteracao():
    k = b"k" * 32
    qr = dom.assinar_qr(k, 7, 1000, "abc")
    assert dom.ler_qr(k, qr, 999) == (7, "abc")
    assert dom.ler_qr(k, qr, 1001) is None
    assert dom.ler_qr(k, qr.replace(".7.", ".8."), 999) is None
    assert dom.ler_qr(b"x" * 32, qr, 999) is None
    assert dom.ler_qr(k, "lixo", 0) is None


@pytest.mark.parametrize("pin,ok", [("2580", True), ("193746", True), ("1234", False), ("1111", False), ("12a4", False), ("123", False), ("4321", False)])
def test_pin_valido(pin, ok):
    assert dom.pin_valido(pin) is ok


def test_prova_de_vida():
    assert dom.prova_de_vida_ok(True, None, None)
    assert dom.prova_de_vida_ok(False, 0.8, 0.7)
    assert not dom.prova_de_vida_ok(False, 0.8, 0.2)
    assert not dom.prova_de_vida_ok(False, None, None)
