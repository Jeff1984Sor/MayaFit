"""Simulador da API da Sefin Nacional (modo simulado, demonstração e testes). Fala o MESMO JSON da API real,
para que o parser do cliente seja exercitado de ponta a ponta.

Regras de rejeição propositais:
- tomador com CPF/CNPJ inválido -> E0207 (o texto cita CPF/CNPJ do tomador)
- descrição contendo "[REJEITAR]" -> E0310 (código de tributação)
- descrição contendo "[FALHA]" -> a primeira chamada vira falha de comunicação (exercita a retentativa)
"""

from __future__ import annotations

import base64
import gzip
import json
import random
import re
from datetime import UTC, datetime

from lxml import etree

from app.modules.nfse import regras
from app.modules.nfse.provedores.base import FalhaComunicacao, RespostaHttp

NS = "http://www.sped.fazenda.gov.br/nfse"

_emitidas: dict[str, dict] = {}  # id da DPS -> {"chave": ..., "numero": ...}
_canceladas: set[str] = set()
_falhou_uma_vez: set[str] = set()


def resetar() -> None:
    _emitidas.clear()
    _canceladas.clear()
    _falhou_uma_vez.clear()


def _gz(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode()


def _ungz(b64: str) -> bytes:
    return gzip.decompress(base64.b64decode(b64))


def _txt(raiz: etree._Element, caminho: str) -> str | None:
    el = raiz.find(caminho, {"n": NS})
    return el.text if el is not None else None


def _resp(status: int, corpo: dict) -> RespostaHttp:
    return RespostaHttp(status, json.dumps(corpo).encode(), {"content-type": "application/json"})


def _chave(id_dps: str, numero: int, quando: datetime) -> str:
    # cMun(7) + ambiente gerador(1) + tpInsc(1) + inscrição(14) + nNFSe(13) + AAMM(4) + código(9) + DV(1) = 50
    corpo = f"{id_dps[3:10]}2{id_dps[10:25]}{numero:013d}{quando:%y%m}{random.randint(0, 10**9 - 1):09d}"
    soma = sum(int(c) * (2 + i % 8) for i, c in enumerate(reversed(corpo)))
    return corpo + str((11 - soma % 11) % 10)


def transporte(metodo: str, url: str, *, json=None, conteudo=None, cabecalhos=None) -> RespostaHttp:  # noqa: A002
    caminho = re.sub(r"^https?://[^/]+(/API)?/SefinNacional", "", url)
    if metodo == "POST" and caminho == "/nfse":
        return _emitir(_ungz(json["dpsXmlGZipB64"]))
    if metodo == "GET" and caminho.startswith("/dps/"):
        achada = _emitidas.get(caminho.removeprefix("/dps/"))
        if not achada:
            return _resp(404, {"erros": [{"Codigo": "E2404", "Descricao": "Não foi gerada uma NFS-e com o identificador de DPS informado"}]})
        return _resp(200, {"chaveAcesso": achada["chave"], "idDps": caminho.removeprefix("/dps/")})
    m = re.match(r"^/nfse/(\d{50})/eventos$", caminho)
    if metodo == "POST" and m:
        chave = m.group(1)
        if chave in _canceladas:
            return _resp(400, {"erros": [{"Codigo": "E0840", "Descricao": "NFS-e já cancelada"}]})
        _canceladas.add(chave)
        return _resp(201, {"eventoXmlGZipB64": _gz(b"<evento/>"), "dataHoraProcessamento": datetime.now(UTC).isoformat()})
    if metodo == "GET" and caminho.startswith("/parametros_municipais/"):
        return _resp(200, {"parametrosConvenio": {"aderenteEmissorNacional": 1, "situacaoEmissaoPadraoContribuintesRFB": 1}})
    return _resp(404, {"erros": [{"Codigo": "E404", "Descricao": f"Rota não simulada: {metodo} {caminho}"}]})


def _emitir(xml: bytes) -> RespostaHttp:
    raiz = etree.fromstring(xml)
    inf = raiz.find("n:infDPS", {"n": NS})
    id_dps = inf.get("Id")
    desc = _txt(inf, "n:serv/n:cServ/n:xDescServ") or ""
    if "[FALHA]" in desc and id_dps not in _falhou_uma_vez:
        _falhou_uma_vez.add(id_dps)
        raise FalhaComunicacao("Simulador: tempo esgotado (proposital).")
    if id_dps in _emitidas:
        return _resp(400, {"idDPS": id_dps, "erros": [{"Codigo": "E0014", "Descricao": "DPS já gerou NFS-e: NFS-e já gerada para o identificador informado"}]})
    if raiz.find("{http://www.w3.org/2000/09/xmldsig#}Signature") is None:
        return _resp(400, {"idDPS": id_dps, "erros": [{"Codigo": "E0717", "Descricao": "Assinatura obrigatória"}]})
    cpf = _txt(inf, "n:toma/n:CPF")
    cnpj = _txt(inf, "n:toma/n:CNPJ")
    erro = None
    if cpf and not regras.documento_valido(cpf):
        erro = ("E0207", "CPF do tomador inválido")
    elif cnpj and not regras.documento_valido(cnpj):
        erro = ("E0208", "CNPJ do tomador inválido")
    elif "[REJEITAR]" in desc:
        erro = ("E0310", "Código de tributação nacional não permitido para o município")
    if erro:
        return _resp(400, {"idDPS": id_dps, "erros": [{"Codigo": erro[0], "Descricao": erro[1], "Complemento": None}]})
    agora = datetime.now(UTC)
    numero = len(_emitidas) + random.randint(100, 900)
    chave = _chave(id_dps, numero, agora)
    _emitidas[id_dps] = {"chave": chave, "numero": numero}
    nfse = (
        f'<NFSe xmlns="{NS}" versao="1.01"><infNFSe Id="NFS{chave}"><xLocEmi>SIMULADO</xLocEmi>'
        f"<nNFSe>{numero}</nNFSe><cStat>100</cStat><dhProc>{agora:%Y-%m-%dT%H:%M:%S}-03:00</dhProc>"
        f"<nDFSe>{numero}</nDFSe></infNFSe></NFSe>"
    ).encode()
    return _resp(201, {
        "tipoAmbiente": 2, "versaoAplicativo": "SIMULADOR-MAYAFIT", "dataHoraProcessamento": agora.isoformat(),
        "idDps": id_dps, "chaveAcesso": chave, "nfseXmlGZipB64": _gz(nfse),
        "alertas": [{"Codigo": "A001", "Descricao": "Nota gerada pelo SIMULADOR: sem valor fiscal."}],
    })
