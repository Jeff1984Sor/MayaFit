"""Regras fiscais puras: ISS em Decimal, documentos, chaves, datas e discriminação."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.modules.nfse import regras


@pytest.mark.parametrize(
    ("valor", "aliquota", "regime", "esperado"),
    [
        ("300.00", "2.00", "simples", "6.00"),
        ("450.50", "2.00", "presumido", "9.01"),
        ("333.33", "5.00", "presumido", "16.67"),  # 16.6665 -> meio para cima
        ("0.10", "2.50", "real", "0.00"),  # 0.0025 -> 0.00
        ("0.30", "2.50", "real", "0.01"),  # 0.0075 -> 0.01
        ("1234.56", "3.00", "simples", "37.04"),  # 37.0368
        ("300.00", "2.00", "mei", "0.00"),  # MEI recolhe no DAS-MEI
    ],
)
def test_calcular_iss(valor, aliquota, regime, esperado):
    c = regras.calcular_iss(Decimal(valor), Decimal(aliquota), regime=regime)
    assert c.valor_iss == Decimal(esperado)
    assert isinstance(c.valor_iss, Decimal)


def test_iss_com_deducoes_e_retencao():
    c = regras.calcular_iss(Decimal("1000"), Decimal("5"), deducoes=Decimal("200"), regime="presumido", retido=True)
    assert c.base == Decimal("800.00")
    assert c.valor_iss == Decimal("40.00")
    assert c.valor_liquido == Decimal("960.00")
    assert not c.recolhido_no_das


def test_iss_simples_e_estimativa_dentro_do_das():
    assert regras.calcular_iss(Decimal("100"), Decimal("2"), regime="simples").recolhido_no_das


@pytest.mark.parametrize("aliq", ["1.99", "5.01", "0"])
def test_aliquota_fora_da_faixa(aliq):
    with pytest.raises(ValueError, match="entre 2% e 5%"):
        regras.calcular_iss(Decimal("100"), Decimal(aliq), regime="simples")


def test_deducao_maior_que_valor():
    with pytest.raises(ValueError):
        regras.calcular_iss(Decimal("100"), Decimal("2"), deducoes=Decimal("101"))


def test_brl():
    assert regras.brl(Decimal("1234.5")) == "R$ 1.234,50"
    assert regras.brl(0) == "R$ 0,00"
    assert regras.brl("1000000") == "R$ 1.000.000,00"


def test_cnpj_e_documentos():
    assert regras.validar_cnpj("11.222.333/0001-81")
    assert not regras.validar_cnpj("11222333000180")
    assert not regras.validar_cnpj("00000000000000")
    assert regras.documento_valido("529.982.247-25")
    assert not regras.documento_valido("12345678900")
    assert not regras.documento_valido("123")
    assert regras.formatar_documento("11222333000181") == "11.222.333/0001-81"
    assert regras.formatar_documento("52998224725") == "529.982.247-25"


def test_codigo_tributacao_nacional():
    assert regras.codigo_tributacao_nacional("06.04") == "060401"
    assert regras.codigo_tributacao_nacional("4.08") == "040801"
    assert regras.codigo_tributacao_nacional("060402") == "060402"
    with pytest.raises(ValueError):
        regras.codigo_tributacao_nacional("6")


def test_id_dps_tem_45_posicoes_no_formato_do_xsd():
    i = regras.id_dps(municipio="3509502", cnpj="11222333000181", serie="1", numero=42)
    assert i == "DPS" + "3509502" + "2" + "11222333000181" + "00001" + "000000000000042"
    assert len(i) == 45
    cpf = regras.id_dps(municipio="3509502", cnpj="52998224725", serie="1", numero=1)
    assert cpf[10] == "1" and cpf[11:25] == "00052998224725"


def test_chaves_de_idempotencia():
    assert regras.chave_recebimento(7) == "rec:7"
    assert regras.chave_liberada("rec:7", 99) == "rec:7:x99"


def test_dh_emissao_no_fuso_de_sp_sem_fracao():
    agora = datetime(2026, 10, 31, 15, 30, 45, 123456, tzinfo=UTC)
    assert regras.dh_emissao(agora) == "2026-10-31T12:29:45-03:00"


def test_discriminacao_variaveis():
    t = regras.renderizar_discriminacao("Aulas de {descricao} - {aluno} - {competencia} - {valor} {desconhecida}",
                                        {"descricao": "Pilates", "aluno": "Ana", "competencia": "10/2026",
                                         "valor": "R$ 1,00"})
    assert t == "Aulas de Pilates - Ana - 10/2026 - R$ 1,00 {desconhecida}"
    assert regras.variaveis_desconhecidas("{aluno} {xpto}") == ["{xpto}"]
    assert len(regras.renderizar_discriminacao("x" * 3000, {})) == 2000
    assert regras.limpar_texto("  a\tb\x00c  ") == "a b c"


def test_situacao_certificado():
    hoje = date(2026, 10, 31)
    assert regras.situacao_certificado(None, hoje)["situacao"] == "ausente"
    assert regras.situacao_certificado(date(2026, 10, 30), hoje)["situacao"] == "vencido"
    assert regras.situacao_certificado(date(2026, 11, 20), hoje)["situacao"] == "vencendo"
    v = regras.situacao_certificado(date(2027, 10, 31), hoje)
    assert v["situacao"] == "valido" and v["dias"] == 365


def test_retentativa_crescente():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    minutos = [(regras.proxima_tentativa(n, t0) - t0).total_seconds() / 60 for n in range(1, 8)]
    assert minutos == [1, 5, 15, 30, 60, 120, 120]


def test_sem_acento_para_sao_paulo():
    assert regras.sem_acento("Ação São João\r") == "Acao Sao Joao"
