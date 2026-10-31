"""Simulador do Web Service da Prefeitura de SP (porte do MayaJus) exposto como TRANSPORTE: devolve o envelope SOAP
com `RetornoXML`, exatamente como o servidor real, para exercitar o parser do cliente.

Rejeições propositais: tomador com CNPJ/CPF inválido -> 1101/1102 · discriminação com "[REJEITAR]" -> 1211 ·
"[FALHA]" -> a primeira chamada vira falha de comunicação.
"""

from __future__ import annotations

import random
import string
from xml.sax.saxutils import escape, unescape

from lxml import etree

from app.modules.nfse import regras
from app.modules.nfse.provedores.base import FalhaComunicacao, RespostaHttp

NS = "http://www.prefeitura.sp.gov.br/nfe"
_contador = [random.randint(10_000, 20_000)]
_emitidas: dict[tuple[str, str], tuple[int, str]] = {}  # (série, número RPS) -> (número NFS-e, código)
_falhou: set[tuple[str, str]] = set()


def resetar() -> None:
    _emitidas.clear()
    _falhou.clear()


def _l(el):
    return etree.QName(el).localname


def _txt(el, *nomes):
    for n in nomes:
        el = next((c for c in el if isinstance(c.tag, str) and _l(c) == n), None)
        if el is None:
            return None
    return el.text


def _retorno(nome: str, sucesso: bool, filhos: list[str]) -> bytes:
    return (
        f'<{nome} xmlns="{NS}"><Cabecalho Versao="2" xmlns="">'
        f"<Sucesso>{'true' if sucesso else 'false'}</Sucesso></Cabecalho>{''.join(filhos)}</{nome}>"
    ).encode()


def _envelope(metodo: str, retorno: bytes) -> RespostaHttp:
    corpo = (
        '<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<soap:Body><{metodo}Response xmlns="{NS}"><RetornoXML>{escape(retorno.decode())}</RetornoXML>'
        f"</{metodo}Response></soap:Body></soap:Envelope>"
    )
    return RespostaHttp(200, corpo.encode())


def transporte(metodo: str, url: str, *, json=None, conteudo=None, cabecalhos=None) -> RespostaHttp:  # noqa: A002
    acao = (cabecalhos or {}).get("SOAPAction", "")
    env = etree.fromstring(conteudo)
    msg = next(e for e in env.iter() if isinstance(e.tag, str) and _l(e) == "MensagemXML")
    pedido = etree.fromstring(unescape(msg.text).encode())
    if acao.endswith(("envioLoteRPS", "testeenvio")):
        return _envelope("EnvioLoteRPS", _envio_lote(pedido, teste=acao.endswith("testeenvio")))
    if acao.endswith("consultaNFe"):
        serie = _txt(pedido, "Detalhe", "ChaveRPS", "SerieRPS")
        numero = _txt(pedido, "Detalhe", "ChaveRPS", "NumeroRPS")
        achada = _emitidas.get((serie, numero))
        filhos = []
        if achada:
            filhos.append(f"<NFe xmlns=''><ChaveNFe><NumeroNFe>{achada[0]}</NumeroNFe>"
                          f"<CodigoVerificacao>{achada[1]}</CodigoVerificacao></ChaveNFe></NFe>")
        return _envelope("ConsultaNFe", _retorno("RetornoConsulta", True, filhos))
    return _envelope("Generico", _retorno("RetornoCancelamentoNFe", True, []))


def _envio_lote(pedido: etree._Element, teste: bool) -> bytes:
    filhos: list[str] = []
    algum_erro = False
    for rps in (c for c in pedido if isinstance(c.tag, str) and _l(c) == "RPS"):
        serie = _txt(rps, "ChaveRPS", "SerieRPS")
        numero = _txt(rps, "ChaveRPS", "NumeroRPS")
        chave = f"<ChaveRPS><SerieRPS>{serie}</SerieRPS><NumeroRPS>{numero}</NumeroRPS></ChaveRPS>"
        desc = _txt(rps, "Discriminacao") or ""
        if "[FALHA]" in desc and (serie, numero) not in _falhou:
            _falhou.add((serie, numero))
            raise FalhaComunicacao("Simulador: Prefeitura fora do ar (proposital).")
        cnpj = _txt(rps, "CPFCNPJTomador", "CNPJ")
        cpf = _txt(rps, "CPFCNPJTomador", "CPF")
        erro = None
        if (serie, numero) in _emitidas and not teste:
            erro = (1209, "RPS ja convertido em NFS-e.")
        elif cnpj and not regras.documento_valido(cnpj):
            erro = (1101, "CNPJ do tomador inválido.")
        elif cpf and not regras.documento_valido(cpf):
            erro = (1102, "CPF do tomador inválido.")
        elif "[REJEITAR]" in desc:
            erro = (1211, "Código de serviço não permitido para o prestador.")
        if erro:
            algum_erro = True
            filhos.append(f"<Erro xmlns=''><Codigo>{erro[0]}</Codigo><Descricao>{erro[1]}</Descricao>{chave}</Erro>")
            continue
        if teste:
            continue
        _contador[0] += 1
        cod = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        _emitidas[(serie, numero)] = (_contador[0], cod)
        filhos.append(
            f"<ChaveNFeRPS xmlns=''><ChaveNFe><InscricaoPrestador>{_txt(rps, 'ChaveRPS', 'InscricaoPrestador')}"
            f"</InscricaoPrestador><NumeroNFe>{_contador[0]}</NumeroNFe><CodigoVerificacao>{cod}</CodigoVerificacao>"
            f"</ChaveNFe>{chave}</ChaveNFeRPS>"
        )
    return _retorno("RetornoEnvioLoteRPS", not algum_erro, filhos)
