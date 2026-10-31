"""Clientes dos provedores com transporte FALSO (respostas no formato real da API), erros mapeados e retentativa."""

import base64
import gzip
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.modules.nfse import certificado as certs
from app.modules.nfse.provedores import ProvedorNacional, ProvedorSaoPaulo, descobrir
from app.modules.nfse.provedores.base import (
    DadosNota,
    ErroConfiguracao,
    FalhaComunicacao,
    Prestador,
    RespostaHttp,
    Tomador,
    TransporteHttpx,
)
from app.modules.nfse.provedores.nacional import URLS
from app.modules.nfse.provedores.nacional import erros as erros_nac
from app.modules.nfse.provedores.sao_paulo import erros as erros_sp

PREST = Prestador(cnpj="11222333000181", razao_social="Estudio", inscricao_municipal="123", codigo_municipio="3509502",
                  regime="simples")
CHAVE = "35095022112223330001810000000000042261012345678901"


def nota(**extra):
    base = dict(serie="1", numero=42, competencia=date(2026, 10, 1), discriminacao="Aulas", item_lista_servico="06.04",
                codigo_tributacao_nacional="060401", valor=Decimal("300"), aliquota=Decimal("2"),
                tomador=Tomador("52998224725", "Maria"))
    base.update(extra)
    return DadosNota(**base)


class Falso:
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, metodo, url, *, json=None, conteudo=None, cabecalhos=None):  # noqa: A002
        self.chamadas.append((metodo, url, json, cabecalhos))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _json(status, corpo):
    return RespostaHttp(status, json.dumps(corpo).encode())


def _gz(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode()


def test_nacional_homologacao_envia_dps_gzip_base64_para_producao_restrita_e_le_a_nota():
    nfse = b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><infNFSe><nNFSe>123</nNFSe></infNFSe></NFSe>'
    t = Falso(_json(201, {"chaveAcesso": CHAVE, "idDps": "DPSX", "nfseXmlGZipB64": _gz(nfse),
                          "alertas": [{"Codigo": "A1", "Descricao": "Alerta qualquer"}]}))
    prov = ProvedorNacional(PREST, modo="homologacao", cert=certs.de_simulacao(), transporte=t)
    r = prov.emitir(nota())
    metodo, url, corpo, _ = t.chamadas[0]
    assert (metodo, url) == ("POST", "https://sefin.producaorestrita.nfse.gov.br/SefinNacional/nfse")
    enviado = gzip.decompress(base64.b64decode(corpo["dpsXmlGZipB64"]))
    assert b"<tpAmb>2</tpAmb>" in enviado and b"<Signature" in enviado
    assert r.situacao == "emitida" and r.chave_acesso == CHAVE and r.numero_nfse == "123"
    assert r.link_oficial.endswith(CHAVE)
    assert r.alertas[0].nivel == "aviso"


def test_nacional_producao_usa_sefin_de_producao():
    assert URLS["producao"]["sefin"] == "https://sefin.nfse.gov.br/SefinNacional"
    t = Falso(_json(400, {"erros": [{"Codigo": "E0015", "Descricao": "Competência posterior"}]}))
    r = ProvedorNacional(PREST, modo="producao", cert=certs.de_simulacao(), transporte=t).emitir(nota())
    assert t.chamadas[0][1] == "https://sefin.nfse.gov.br/SefinNacional/nfse"
    assert r.situacao == "rejeitada"
    assert r.erros[0].codigo == "E0015" and "competência" in r.erros[0].mensagem.lower()


def test_nacional_dps_ja_processada_busca_a_nota_existente_em_vez_de_duplicar():
    t = Falso(
        _json(400, {"erros": [{"Codigo": "E0014", "Descricao": "NFS-e já gerada para a DPS"}]}),
        _json(200, {"chaveAcesso": CHAVE}),
        _json(200, {"nfseXmlGZipB64": _gz(b"<NFSe><infNFSe><nNFSe>77</nNFSe></infNFSe></NFSe>")}),
    )
    r = ProvedorNacional(PREST, modo="homologacao", cert=certs.de_simulacao(), transporte=t).emitir(nota())
    assert r.situacao == "emitida" and r.numero_nfse == "77"
    assert [c[0] for c in t.chamadas] == ["POST", "GET", "GET"]
    assert t.chamadas[1][1].endswith("/dps/DPS350950221122233300018100001000000000000042")


def test_nacional_consulta_sem_nota_devolve_none():
    t = Falso(_json(404, {"erros": [{"Codigo": "E2404", "Descricao": "Não foi gerada"}]}))
    assert ProvedorNacional(PREST, modo="homologacao", cert=certs.de_simulacao(), transporte=t).consultar(nota()) is None


def test_nacional_cancelamento_envia_evento():
    t = Falso(_json(201, {"eventoXmlGZipB64": _gz(b"<evento/>")}))
    r = ProvedorNacional(PREST, modo="homologacao", cert=certs.de_simulacao(), transporte=t).cancelar(
        nota(chave_acesso=CHAVE), codigo="2", motivo="Servico nao foi prestado ao aluno")
    assert r.sucesso
    assert t.chamadas[0][1].endswith(f"/nfse/{CHAVE}/eventos")
    evento = gzip.decompress(base64.b64decode(t.chamadas[0][2]["pedidoRegistroEventoXmlGZipB64"]))
    assert b"<cMotivo>2</cMotivo>" in evento


def test_fora_do_simulado_exige_certificado():
    with pytest.raises(ErroConfiguracao):
        ProvedorNacional(PREST, modo="homologacao", cert=None)


def test_transporte_httpx_converte_5xx_e_timeout_em_falha_de_comunicacao(monkeypatch):
    chamadas = []

    class Cliente:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, *a, **k):
            chamadas.append(1)
            if len(chamadas) == 1:
                raise httpx.ConnectTimeout("tempo")
            return httpx.Response(503, text="indisponivel")

    monkeypatch.setattr(httpx, "Client", Cliente)
    monkeypatch.setattr("app.modules.nfse.provedores.base.time.sleep", lambda s: None)
    t = TransporteHttpx(certs.de_simulacao(), tentativas=2)
    with pytest.raises(FalhaComunicacao):
        t("POST", "https://exemplo.invalid/x", json={})
    assert len(chamadas) == 2


def test_sp_le_retorno_soap_com_erro_mapeado():
    retorno = ('<RetornoEnvioLoteRPS xmlns="http://www.prefeitura.sp.gov.br/nfe"><Cabecalho xmlns="" Versao="2">'
               '<Sucesso>false</Sucesso></Cabecalho><Erro xmlns=""><Codigo>1102</Codigo><Descricao>CPF invalido'
               '</Descricao></Erro></RetornoEnvioLoteRPS>')
    from xml.sax.saxutils import escape

    env = ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><R><RetornoXML>'
           f"{escape(retorno)}</RetornoXML></R></soap:Body></soap:Envelope>").encode()
    t = Falso(RespostaHttp(200, env))
    p = Prestador(cnpj="11222333000181", razao_social="E", inscricao_municipal="12345678", codigo_municipio="3550308",
                  regime="simples", extras={"nbs": "109051200", "class_trib": "000001", "ind_operacao": "100301"})
    r = ProvedorSaoPaulo(p, modo="producao", cert=certs.de_simulacao(), transporte=t).emitir(
        nota(codigo_servico_municipal="06298"))
    assert t.chamadas[0][3]["SOAPAction"] == "http://www.prefeitura.sp.gov.br/nfe/ws/envioLoteRPS"
    assert t.chamadas[0][1] == "https://nfews.prefeitura.sp.gov.br/lotenfe.asmx"
    assert r.situacao == "rejeitada" and r.erros[0].codigo == "1102"
    assert r.erros[0].campo == "tomador.documento"


def test_sp_sem_retornoxml_vira_falha_de_comunicacao():
    t = Falso(RespostaHttp(500, b"<html><body>Erro do servidor</body></html>"))
    p = Prestador(cnpj="11222333000181", razao_social="E", inscricao_municipal="12345678", codigo_municipio="3550308",
                  regime="simples", extras={"nbs": "109051200", "class_trib": "000001", "ind_operacao": "100301"})
    with pytest.raises(FalhaComunicacao, match="Erro do servidor"):
        ProvedorSaoPaulo(p, modo="producao", cert=certs.de_simulacao(), transporte=t).emitir(
            nota(codigo_servico_municipal="06298"))


def test_sp_homologacao_usa_teste_de_envio_e_nao_gera_nota():
    p = Prestador(cnpj="11222333000181", razao_social="E", inscricao_municipal="12345678", codigo_municipio="3550308",
                  regime="simples", extras={"nbs": "109051200", "class_trib": "000001", "ind_operacao": "100301"})
    from app.modules.nfse.provedores.sao_paulo import simulador

    chamadas = []

    def t(metodo, url, **k):
        chamadas.append(k["cabecalhos"]["SOAPAction"])
        return simulador.transporte(metodo, url, **k)

    r = ProvedorSaoPaulo(p, modo="homologacao", cert=certs.de_simulacao(), transporte=t).emitir(
        nota(codigo_servico_municipal="06298"))
    assert chamadas == ["http://www.prefeitura.sp.gov.br/nfe/ws/testeenvio"]
    assert r.situacao == "validada" and r.numero_nfse is None


@pytest.mark.parametrize(("codigo", "texto", "campo"), [
    ("E0015", "x", "competencia"),
    ("E0717", "x", "certificado"),
    (None, "CPF do tomador não encontrado na base da RFB", "tomador.documento"),
    (None, "Município sem convênio ativo", "configuracao"),
    (None, "Alíquota divergente da parametrizada", "aliquota"),
])
def test_erros_nacionais_mapeados(codigo, texto, campo):
    e = erros_nac.humanizar(codigo, texto)
    assert e.campo == campo and e.acao and e.tecnico


def test_erro_nacional_desconhecido_mostra_texto_do_provedor():
    e = erros_nac.humanizar("E9876", "Regra nova da Sefin")
    assert "Regra nova da Sefin" in e.mensagem and e.acao


@pytest.mark.parametrize(("codigo", "campo"), [(1101, "tomador.documento"), (1211, "servico"), (1209, None)])
def test_erros_sp_mapeados(codigo, campo):
    e = erros_sp.erro_nota(codigo, "texto")
    assert e.campo == campo and e.codigo == str(codigo)


def test_descobrir_provedor_pelo_municipio():
    assert descobrir("3550308")["provedor"] == "sao_paulo"
    assert descobrir("3509502") == {"provedor": "nacional", "suportado": True, "mensagem": descobrir("3509502")["mensagem"]}
    assert descobrir("3304557")["suportado"] is False
