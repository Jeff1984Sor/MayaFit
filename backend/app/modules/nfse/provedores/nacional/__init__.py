"""Provedor do Padrão Nacional (Sefin Nacional + ADN). API REST com TLS mútuo (certificado A1).

Endpoints (Manual de Contribuintes - API Emissor Público Nacional v1.2, out/2025):
  POST /nfse                         {"dpsXmlGZipB64": ...}  -> chaveAcesso, idDps, nfseXmlGZipB64, alertas | erros
  GET  /nfse/{chaveAcesso}           consulta a NFS-e
  GET  /dps/{idDps}                  chave da NFS-e gerada para a DPS (consulta antes de reenviar)
  POST /nfse/{chave}/eventos         {"pedidoRegistroEventoXmlGZipB64": ...} (cancelamento e101101)
  GET  /parametros_municipais/{cMun}/convenio
DANFSe (PDF oficial): ADN `/danfse/{chave}`.
"""

from __future__ import annotations

import base64
import gzip
from datetime import UTC, datetime
from decimal import Decimal

from lxml import etree

from app.core.db import agora
from app.modules.nfse import regras
from app.modules.nfse.provedores.base import (
    DadosNota,
    ErroNota,
    Provedor,
    ResultadoCancelamento,
    ResultadoEmissao,
    Tomador,
)
from app.modules.nfse.provedores.nacional import dps, simulador
from app.modules.nfse.provedores.nacional.erros import humanizar

URLS = {
    "homologacao": {
        "sefin": "https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
        "adn": "https://adn.producaorestrita.nfse.gov.br",
    },
    "producao": {"sefin": "https://sefin.nfse.gov.br/SefinNacional", "adn": "https://adn.nfse.gov.br"},
}
URLS["simulado"] = URLS["homologacao"]
CONSULTA_PUBLICA = "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave={chave}"


def _gz(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode()


def _ungz(b64: str | None) -> bytes:
    return gzip.decompress(base64.b64decode(b64)) if b64 else b""


def _campo(d: dict, *nomes: str):
    """A API devolve chaves em camelCase e, nos erros, em PascalCase: aceita as duas."""
    if not isinstance(d, dict):
        return None
    baixo = {k.lower(): v for k, v in d.items()}
    for n in nomes:
        if n.lower() in baixo:
            return baixo[n.lower()]
    return None


def _erros(corpo) -> list[ErroNota]:
    lista = _campo(corpo, "erros", "erro") if isinstance(corpo, dict) else None
    if isinstance(lista, dict):
        lista = [lista]
    saida = []
    for e in lista or []:
        saida.append(humanizar(_campo(e, "codigo"), _campo(e, "descricao") or "", _campo(e, "complemento")))
    return saida


def _numero_da_nfse(xml: bytes) -> str | None:
    if not xml:
        return None
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return None
    el = next((e for e in raiz.iter() if isinstance(e.tag, str) and etree.QName(e).localname == "nNFSe"), None)
    return el.text if el is not None else None


class ProvedorNacional(Provedor):
    nome = "nacional"
    rotulo = "NFS-e Padrão Nacional (Emissor Nacional / Sefin)"

    @property
    def tp_amb(self) -> str:
        return "1" if self.modo == "producao" else "2"

    @property
    def urls(self) -> dict[str, str]:
        return URLS[self.modo]

    @property
    def transporte(self):
        if self.modo == "simulado" and self._transporte is None:
            return simulador.transporte
        return super().transporte

    # ------------------------------------------------------------------------------------- XML
    def _dps(self, nota: DadosNota):
        raiz = dps.montar(self.prestador, nota, tp_amb=self.tp_amb, dh_emi=regras.dh_emissao(agora()))
        assinado = dps.assinar(raiz, self.cert)
        return assinado, dps.validar_dps(assinado)

    def montar_xml(self, nota: DadosNota) -> tuple[bytes, list[str]]:
        raiz, erros = self._dps(nota)
        return dps.para_bytes(raiz), erros

    # ------------------------------------------------------------------------------------- emissão
    def emitir(self, nota: DadosNota) -> ResultadoEmissao:
        raiz, erros_xsd = self._dps(nota)
        xml = dps.para_bytes(raiz)
        id_dps = raiz[0].get("Id")
        if erros_xsd:
            return ResultadoEmissao(
                "rejeitada", xml_enviado=xml.decode(), id_dps=id_dps,
                erros=[ErroNota("O XML ficou fora do schema oficial da NFS-e Nacional.",
                                "Confira os dados destacados; se persistir, avise o suporte MayaCorp.",
                                tecnico=e) for e in erros_xsd],
            )
        r = self.transporte("POST", f"{self.urls['sefin']}/nfse", json={"dpsXmlGZipB64": _gz(xml)})
        corpo = r.json() or {}
        if r.status in (200, 201) and _campo(corpo, "chaveAcesso"):
            return self._resultado_emitida(corpo, xml.decode(), id_dps)
        erros = _erros(corpo) or [humanizar(None, f"HTTP {r.status}: {r.conteudo[:300].decode(errors='ignore')}")]
        # DPS já processada (reenvio após timeout): busca a nota existente em vez de duplicar
        if any(e.codigo in ("E0014",) or "já" in (e.tecnico or "").lower() and "gerad" in (e.tecnico or "").lower()
               for e in erros):
            achada = self.consultar(DadosNota(**{**nota.__dict__, "id_dps": id_dps}))
            if achada:
                achada.xml_enviado = xml.decode()
                return achada
        return ResultadoEmissao("rejeitada", xml_enviado=xml.decode(), xml_retorno=r.conteudo.decode(errors="ignore"),
                                id_dps=id_dps, erros=erros)

    def _resultado_emitida(self, corpo: dict, xml_enviado: str, id_dps: str | None) -> ResultadoEmissao:
        chave = _campo(corpo, "chaveAcesso")
        nfse_xml = _ungz(_campo(corpo, "nfseXmlGZipB64"))
        alertas = [humanizar(_campo(a, "codigo"), _campo(a, "descricao") or "") for a in (_campo(corpo, "alertas") or [])]
        for a in alertas:
            a.nivel = "aviso"
        return ResultadoEmissao(
            "emitida", xml_enviado=xml_enviado, xml_retorno=nfse_xml.decode(errors="ignore"),
            numero_nfse=_numero_da_nfse(nfse_xml), chave_acesso=chave, id_dps=_campo(corpo, "idDps") or id_dps,
            link_oficial=CONSULTA_PUBLICA.format(chave=chave), emitida_em=datetime.now(UTC), alertas=alertas,
        )

    def consultar(self, nota: DadosNota) -> ResultadoEmissao | None:
        id_dps = nota.id_dps or regras.id_dps(municipio=self.prestador.codigo_municipio, cnpj=self.prestador.cnpj,
                                              serie=nota.serie, numero=nota.numero)
        r = self.transporte("GET", f"{self.urls['sefin']}/dps/{id_dps}")
        corpo = r.json() or {}
        chave = _campo(corpo, "chaveAcesso")
        if r.status != 200 or not chave:
            return None
        r2 = self.transporte("GET", f"{self.urls['sefin']}/nfse/{chave}")
        corpo2 = (r2.json() or {}) if r2.status == 200 else {}
        res = self._resultado_emitida({**corpo2, "chaveAcesso": chave, "idDps": id_dps}, "", id_dps)
        return res

    # ------------------------------------------------------------------------------------- cancelamento
    def montar_cancelamento(self, chave: str, codigo: str, motivo: str):
        raiz = dps.montar_cancelamento(cnpj=self.prestador.cnpj, chave=chave, codigo=codigo, motivo=motivo,
                                       tp_amb=self.tp_amb, dh_evento=regras.dh_emissao(agora()))
        assinado = dps.assinar(raiz, self.cert)
        return assinado, dps.validar_evento(assinado)

    def cancelar(self, nota: DadosNota, *, codigo: str, motivo: str) -> ResultadoCancelamento:
        if not nota.chave_acesso:
            return ResultadoCancelamento(False, erros=[ErroNota("Esta nota não tem chave de acesso.",
                                                                "Consulte a nota antes de cancelar.")])
        raiz, erros_xsd = self.montar_cancelamento(nota.chave_acesso, codigo, motivo)
        xml = dps.para_bytes(raiz)
        if erros_xsd:
            return ResultadoCancelamento(False, xml.decode(), erros=[
                ErroNota("O pedido de cancelamento ficou fora do schema oficial.",
                         "Confira o motivo (de 15 a 255 caracteres).", tecnico=e) for e in erros_xsd])
        r = self.transporte("POST", f"{self.urls['sefin']}/nfse/{nota.chave_acesso}/eventos",
                            json={"pedidoRegistroEventoXmlGZipB64": _gz(xml)})
        corpo = r.json() or {}
        if r.status in (200, 201) and not _campo(corpo, "erros"):
            ret = _ungz(_campo(corpo, "eventoXmlGZipB64"))
            return ResultadoCancelamento(True, xml.decode(), ret.decode(errors="ignore"))
        return ResultadoCancelamento(False, xml.decode(), r.conteudo.decode(errors="ignore"),
                                     erros=_erros(corpo) or [humanizar(None, f"HTTP {r.status}")])

    def danfse(self, nota: DadosNota) -> bytes | None:
        if self.modo == "simulado" or not nota.chave_acesso:
            return None
        r = self.transporte("GET", f"{self.urls['adn']}/danfse/{nota.chave_acesso}")
        return r.conteudo if r.status == 200 and r.conteudo[:4] == b"%PDF" else None

    def verificar_convenio(self, codigo_municipio: str) -> dict:
        r = self.transporte("GET", f"{self.urls['sefin']}/parametros_municipais/{codigo_municipio}/convenio")
        return {"status": r.status, "dados": r.json()}

    def testar(self) -> str:
        nota = DadosNota(serie="1", numero=1, competencia=agora().date(), discriminacao="Teste de configuracao",
                         item_lista_servico="06.04", codigo_tributacao_nacional="060401", valor=Decimal("1.00"),
                         aliquota=Decimal("2.00"), tomador=Tomador(documento=None, nome="Teste"))
        _, erros = self.montar_xml(nota)
        if erros:
            return "XML de teste fora do schema: " + "; ".join(erros[:3])
        if self.modo == "simulado":
            return "DPS de teste montada, assinada e validada no schema oficial (modo simulado: nada foi enviado)."
        conv = self.verificar_convenio(self.prestador.codigo_municipio)
        if conv["status"] == 200:
            return "Certificado aceito pela Sefin Nacional e município encontrado na parametrização nacional."
        return f"A Sefin respondeu HTTP {conv['status']} na consulta do convênio do município."
