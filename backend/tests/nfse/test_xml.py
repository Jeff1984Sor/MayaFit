"""Geração dos XML, validação contra os XSD OFICIAIS e conferência das assinaturas (sem rede)."""

import base64
import hashlib
from datetime import date
from decimal import Decimal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_der_x509_certificate
from lxml import etree
from signxml import XMLVerifier

from app.modules.nfse.certificado import de_simulacao
from app.modules.nfse.provedores import ProvedorNacional, ProvedorSaoPaulo
from app.modules.nfse.provedores.base import DadosNota, Prestador, Tomador
from app.modules.nfse.provedores.nacional import dps
from app.modules.nfse.provedores.sao_paulo import assinatura as assinatura_sp
from app.modules.nfse.provedores.xmldsig import c14n

NS = {"n": "http://www.sped.fazenda.gov.br/nfse", "ds": "http://www.w3.org/2000/09/xmldsig#"}


def prestador(regime="simples", **extra):
    return Prestador(cnpj="11222333000181", razao_social="Estudio", inscricao_municipal="123456",
                     codigo_municipio="3509502", regime=regime, email="estudio@x.com", telefone="(19) 99999-0000",
                     extras=extra)


def nota(**extra):
    base = dict(serie="1", numero=42, competencia=date(2026, 10, 1), discriminacao="Aulas de Pilates - Maria Souza",
                item_lista_servico="06.04", codigo_tributacao_nacional="060401", valor=Decimal("300.00"),
                aliquota=Decimal("2.00"), percentual_tributos_sn=Decimal("6.00"),
                tomador=Tomador("52998224725", "Maria Souza", "maria@x.com"))
    base.update(extra)
    return DadosNota(**base)


def _verificar_assinatura_independente(xml: bytes) -> etree._Element:
    """Confere a assinatura recalculando tudo com C14N correto (cópia da subárvore) e a chave pública do X509."""
    raiz = etree.fromstring(xml)
    sig = raiz.find("ds:Signature", NS)
    assert sig is not None and sig.prefix is None  # sem prefixo ds:
    alvo = raiz[0]
    ref = sig.find("ds:SignedInfo/ds:Reference", NS)
    assert ref.get("URI") == "#" + alvo.get("Id")
    canon = c14n(alvo)
    assert b'xmlns=""' not in canon  # protege contra o bug de C14N de subárvore do libxml2
    assert base64.b64encode(hashlib.sha256(canon).digest()).decode() == ref.find("ds:DigestValue", NS).text
    cert = load_der_x509_certificate(base64.b64decode(sig.find("ds:KeyInfo/ds:X509Data/ds:X509Certificate", NS).text))
    si = c14n(sig.find("ds:SignedInfo", NS))
    assert si.startswith(b'<SignedInfo xmlns="http://www.w3.org/2000/09/xmldsig#">')
    cert.public_key().verify(base64.b64decode(sig.find("ds:SignatureValue", NS).text), si, padding.PKCS1v15(),
                             hashes.SHA256())
    return raiz


# ------------------------------------------------------------------------------------------------- Nacional
def test_dps_valida_no_xsd_oficial_e_assinatura_confere():
    xml, erros = ProvedorNacional(prestador(), modo="simulado", cert=None).montar_xml(nota())
    assert erros == []
    raiz = _verificar_assinatura_independente(xml)
    assert raiz.prefix is None and raiz.tag == "{http://www.sped.fazenda.gov.br/nfse}DPS"  # E1228: sem prefixo
    inf = raiz.find("n:infDPS", NS)
    assert inf.get("Id") == "DPS350950221122233300018100001000000000000042"
    ordem = [etree.QName(e).localname for e in inf]
    assert ordem == ["tpAmb", "dhEmi", "verAplic", "serie", "nDPS", "dCompet", "tpEmit", "cLocEmi", "prest", "toma",
                     "serv", "valores"]
    assert inf.findtext("n:tpAmb", namespaces=NS) == "2"
    assert inf.findtext("n:prest/n:regTrib/n:opSimpNac", namespaces=NS) == "3"
    assert inf.findtext("n:valores/n:vServPrest/n:vServ", namespaces=NS) == "300.00"
    assert inf.findtext("n:valores/n:trib/n:totTrib/n:pTotTribSN", namespaces=NS) == "6.00"
    assert inf.find("n:prest/n:xNome", NS) is None  # emitente = prestador: nome vem do cadastro nacional


def test_c14n_do_infdps_bate_com_o_texto_canonico_escrito_a_mao():
    """Referência independente do lxml: a forma canônica esperada de um infDPS pequeno, escrita à mão."""
    raiz = etree.fromstring(b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01"><infDPS Id="DPS1">'
                            b"<prest><CNPJ>1</CNPJ></prest><valores b=\"2\" a=\"1\"/></infDPS></DPS>")
    assert c14n(raiz[0]) == (b'<infDPS xmlns="http://www.sped.fazenda.gov.br/nfse" Id="DPS1"><prest><CNPJ>1</CNPJ>'
                             b'</prest><valores a="1" b="2"></valores></infDPS>')


def test_dps_mei_sem_aliquota_e_sem_regime_de_apuracao():
    xml, erros = ProvedorNacional(prestador("mei"), modo="simulado", cert=None).montar_xml(
        nota(informar_aliquota=True, percentual_tributos_sn=None))
    assert erros == []
    inf = etree.fromstring(xml).find("n:infDPS", NS)
    assert inf.findtext("n:prest/n:regTrib/n:opSimpNac", namespaces=NS) == "2"
    assert inf.find("n:prest/n:regTrib/n:regApTribSN", NS) is None
    assert inf.find("n:valores/n:trib/n:tribMun/n:pAliq", NS) is None
    assert inf.findtext("n:valores/n:trib/n:totTrib/n:indTotTrib", namespaces=NS) == "0"


def test_dps_presumido_com_aliquota_retencao_endereco_e_cnpj():
    t = Tomador("11222333000181", "Empresa Parceira Ltda", None,
                {"cep": "13010-000", "codigo_municipio": "3509502", "logradouro": "Rua A", "numero": "10",
                 "bairro": "Centro", "complemento": "Sala 2"})
    xml, erros = ProvedorNacional(prestador("presumido"), modo="producao", cert=de_simulacao()).montar_xml(
        nota(tomador=t, informar_aliquota=True, iss_retido=True, deducoes=Decimal("10")))
    assert erros == []
    inf = etree.fromstring(xml).find("n:infDPS", NS)
    assert inf.findtext("n:tpAmb", namespaces=NS) == "1"
    assert inf.findtext("n:toma/n:CNPJ", namespaces=NS) == "11222333000181"
    assert inf.findtext("n:toma/n:end/n:endNac/n:CEP", namespaces=NS) == "13010000"
    assert inf.findtext("n:valores/n:trib/n:tribMun/n:pAliq", namespaces=NS) == "2.00"
    assert inf.findtext("n:valores/n:trib/n:tribMun/n:tpRetISSQN", namespaces=NS) == "2"
    assert inf.findtext("n:valores/n:vDedRed/n:vDR", namespaces=NS) == "10.00"


def test_dps_competencia_nunca_posterior_a_emissao():
    raiz = dps.montar(prestador(), nota(competencia=date(2099, 1, 1)), tp_amb="2", dh_emi="2026-10-31T10:00:00-03:00")
    assert raiz.find("n:infDPS/n:dCompet", NS).text == "2026-10-31"  # E0015


def test_dps_fora_do_schema_e_detectada():
    xml, erros = ProvedorNacional(prestador(), modo="simulado", cert=None).montar_xml(
        nota(codigo_tributacao_nacional="6.04"))
    assert erros and "cTribNac" in erros[0]


def test_evento_de_cancelamento_valido_e_assinado():
    prov = ProvedorNacional(prestador(), modo="simulado", cert=None)
    chave = "3509502211222333000181000000000004226100123456789"
    chave = chave + "0" * (50 - len(chave))
    raiz, erros = prov.montar_cancelamento(chave, "1", "Valor informado errado na nota")
    assert erros == []
    _verificar_assinatura_independente(etree.tostring(raiz))
    inf = raiz.find("n:infPedReg", NS)
    assert inf.get("Id") == f"PRE{chave}101101"
    assert inf.findtext("n:e101101/n:xDesc", namespaces=NS) == "Cancelamento de NFS-e"


def test_evento_com_motivo_curto_fica_fora_do_schema():
    prov = ProvedorNacional(prestador(), modo="simulado", cert=None)
    _, erros = prov.montar_cancelamento("1" * 50, "1", "curto")
    assert erros


# ------------------------------------------------------------------------------------------------- São Paulo
EXTRAS_SP = {"nbs": "109051200", "class_trib": "000001", "ind_operacao": "100301"}


def test_pedido_sp_valido_no_xsd_e_assinado_com_prefixo_ds():
    p = prestador(**EXTRAS_SP)
    p.inscricao_municipal = "12345678"
    p.codigo_municipio = "3550308"
    xml, erros = ProvedorSaoPaulo(p, modo="simulado", cert=None).montar_xml(
        nota(codigo_servico_municipal="06298", discriminacao="Aulas de Pilates - João"))
    assert erros == []
    assert b"<ds:Signature" in xml
    XMLVerifier().verify(xml, x509_cert=de_simulacao().cert_pem().decode())
    raiz = etree.fromstring(xml)
    rps = next(e for e in raiz if etree.QName(e).localname == "RPS")
    assert rps.findtext("Discriminacao") == "Aulas de Pilates - Joao"  # sem acento
    assert rps.findtext("AliquotaServicos") == "0.0200"  # fração, 4 casas
    ordem = [etree.QName(e).localname for e in rps][:8]
    assert ordem == ["Assinatura", "ChaveRPS", "TipoRPS", "DataEmissao", "StatusRPS", "TributacaoRPS", "ValorDeducoes",
                     "ValorPIS"]


def test_string_de_assinatura_do_rps_layout_2():
    s = assinatura_sp.string_assinatura_rps(
        ccm="12345678", serie="A", numero=7, data_emissao=date(2026, 10, 1), tributacao="T", status="N",
        iss_retido=False, valor=Decimal("300.00"), deducoes=Decimal("0"), cod_servico="6298", ind_tomador="1",
        doc_tomador="52998224725")
    assert s == ("000012345678" "A    " "000000000007" "20261001" "T" "N" "N" "000000000030000" "000000000000000"
                 "06298" "1" "00052998224725")
    assert len(s) == 90
