"""Provedor da Prefeitura de São Paulo (NFS-e layout 2, Web Service SOAP `lotenfe.asmx`). Porte do MayaJus.

Aprendizados (validados em produção pelo MayaJus em 09/2026):
- endpoint `https://nfews.prefeitura.sp.gov.br/lotenfe.asmx` (o antigo não aceita V2);
- SOAP 1.1 com `SOAPAction` por operação (mapa `ACOES`), senão o IIS devolve 500 genérico;
- XMLDSig RSA-SHA256, C14N 1.0, prefixo `ds:` (em SHA-1 ou sem prefixo: erro 1057);
- assinatura do RPS (RSA-SHA1) com CCM de 12 posições e o `ValorFinalCobrado`;
- elementos na ORDEM do `tpRPS`; razão social e discriminação sem acento; XSD validado antes de sair.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from lxml import etree

from app.domain.documentos import so_digitos
from app.modules.nfse.provedores.base import (
    DadosNota,
    ErroNota,
    FalhaComunicacao,
    Provedor,
    ResultadoCancelamento,
    ResultadoEmissao,
)
from app.modules.nfse.provedores.sao_paulo import simulador, xml_layout2
from app.modules.nfse.provedores.sao_paulo.erros import erro_nota

URL = "https://nfews.prefeitura.sp.gov.br/lotenfe.asmx"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
ACOES = {
    "EnvioLoteRPS": "http://www.prefeitura.sp.gov.br/nfe/ws/envioLoteRPS",
    "TesteEnvioLoteRPS": "http://www.prefeitura.sp.gov.br/nfe/ws/testeenvio",
    "CancelamentoNFe": "http://www.prefeitura.sp.gov.br/nfe/ws/cancelamentoNFe",
    "ConsultaNFe": "http://www.prefeitura.sp.gov.br/nfe/ws/consultaNFe",
    "ConsultaCNPJ": "http://www.prefeitura.sp.gov.br/nfe/ws/consultaCNPJ",
}
# Parâmetros IBS/CBS do layout 2 (NT 003/004). Sem padrão seguro para estúdios: o contador define (raio-x avisa).
EXTRAS_SP = ("nbs", "class_trib", "ind_operacao")


def link_nota(ccm: str, numero: str | int, cod_verificacao: str) -> str:
    return (
        "https://nfe.prefeitura.sp.gov.br/contribuinte/notaprint.aspx"
        f"?ccm={so_digitos(ccm)}&nf={numero}&cod={cod_verificacao.replace('-', '')}"
    )


def _local(el) -> str:
    return etree.QName(el).localname


def _filho(el, nome):
    for c in el:
        if isinstance(c.tag, str) and _local(c) == nome:
            return c
    return None


def _texto(el, *caminho):
    for nome in caminho:
        if el is None:
            return None
        el = _filho(el, nome)
    return el.text.strip() if el is not None and el.text else None


def _envelope(metodo: str, mensagem: bytes, versao: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}"><soap:Body>'
        f'<{metodo}Request xmlns="http://www.prefeitura.sp.gov.br/nfe">'
        f"<VersaoSchema>{versao}</VersaoSchema>"
        f"<MensagemXML>{escape(mensagem.decode('utf-8'))}</MensagemXML>"
        f"</{metodo}Request></soap:Body></soap:Envelope>"
    ).encode()


class ProvedorSaoPaulo(Provedor):
    nome = "sao_paulo"
    rotulo = "Prefeitura de São Paulo (NFS-e layout 2)"

    @property
    def transporte(self):
        if self.modo == "simulado" and self._transporte is None:
            return simulador.transporte
        return super().transporte

    @property
    def ccm(self) -> str:
        return so_digitos(self.prestador.inscricao_municipal)

    def _rps(self, nota: DadosNota) -> xml_layout2.RpsXml:
        ex = self.prestador.extras
        return xml_layout2.RpsXml(
            serie=nota.serie, numero=nota.numero, tipo="RPS", data_emissao=nota.competencia, status="N",
            tributacao=ex.get("tributacao_sp") or "T", valor=Decimal(nota.valor), deducoes=Decimal(nota.deducoes),
            cod_servico=so_digitos(nota.codigo_servico_municipal) or "0", aliquota=Decimal(nota.aliquota) / 100,
            iss_retido=nota.iss_retido, discriminacao=nota.discriminacao,
            tomador={"cpf_cnpj": nota.tomador.documento, "nome": nota.tomador.nome, "email": nota.tomador.email,
                     **(nota.tomador.endereco or {})},
            layout2={"nbs": nota.nbs or ex.get("nbs"), "class_trib": ex.get("class_trib"),
                     "ind_operacao": ex.get("ind_operacao"), "finalidade": "0", "ind_final": "1"},
        )

    def _pedido(self, nota: DadosNota):
        pedido = xml_layout2.pedido_envio_lote(cnpj_remetente=so_digitos(self.prestador.cnpj), ccm=self.ccm,
                                               rps=[self._rps(nota)], cert=self.cert)
        return pedido, xml_layout2.validar_xsd(pedido, "PedidoEnvioLoteRPS_v02.xsd")

    def montar_xml(self, nota: DadosNota) -> tuple[bytes, list[str]]:
        pedido, erros = self._pedido(nota)
        return xml_layout2.para_bytes(pedido), erros

    def _chamar(self, metodo: str, raiz, versao: str = "1") -> bytes:
        corpo = _envelope(metodo, xml_layout2.para_bytes(raiz), versao)
        r = self.transporte("POST", URL, conteudo=corpo,
                            cabecalhos={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ACOES[metodo]})
        ret = None
        try:
            env = etree.fromstring(r.conteudo)
            ret = next((e for e in env.iter() if isinstance(e.tag, str) and _local(e) == "RetornoXML"), None)
        except etree.XMLSyntaxError:
            pass
        if ret is not None and ret.text:
            return ret.text.encode("utf-8")
        texto = " ".join(" ".join(etree.HTML(r.conteudo).itertext()).split()) if r.conteudo else ""
        raise FalhaComunicacao(f"HTTP {r.status} da Prefeitura sem RetornoXML: {texto[:300]}")

    def emitir(self, nota: DadosNota) -> ResultadoEmissao:
        pedido, erros_xsd = self._pedido(nota)
        xml = xml_layout2.para_bytes(pedido).decode()
        if erros_xsd:
            return ResultadoEmissao("rejeitada", xml_enviado=xml, erros=[
                ErroNota("O XML ficou fora do schema oficial da Prefeitura de SP.",
                         "Confira os dados destacados (código de serviço, NBS e parâmetros IBS/CBS).", tecnico=e)
                for e in erros_xsd])
        teste = self.modo == "homologacao"
        retorno = self._chamar("TesteEnvioLoteRPS" if teste else "EnvioLoteRPS", pedido, xml_layout2.VERSAO)
        raiz = etree.fromstring(retorno)
        erros, alertas, notas = [], [], []
        for el in raiz:
            if not isinstance(el.tag, str):
                continue
            nome = _local(el)
            if nome in ("Erro", "Alerta"):
                cod = _texto(el, "Codigo")
                e = erro_nota(int(cod) if cod and cod.isdigit() else None, _texto(el, "Descricao") or "")
                if nome == "Alerta":
                    e.nivel = "aviso"
                (erros if nome == "Erro" else alertas).append(e)
            elif nome == "ChaveNFeRPS":
                notas.append((_texto(el, "ChaveNFe", "NumeroNFe"), _texto(el, "ChaveNFe", "CodigoVerificacao")))
        if any(e.codigo == "1209" for e in erros):  # RPS já convertido: busca a nota existente
            achada = self.consultar(nota)
            if achada:
                achada.xml_enviado = xml
                return achada
        if erros:
            return ResultadoEmissao("rejeitada", xml_enviado=xml, xml_retorno=retorno.decode(), erros=erros,
                                    alertas=alertas)
        if teste:
            return ResultadoEmissao("validada", xml_enviado=xml, xml_retorno=retorno.decode(), alertas=alertas)
        numero, cod = notas[0] if notas else (None, None)
        return ResultadoEmissao(
            "emitida", xml_enviado=xml, xml_retorno=retorno.decode(), numero_nfse=numero, codigo_verificacao=cod,
            link_oficial=link_nota(self.ccm, numero, cod) if numero and cod else None,
            emitida_em=datetime.now(UTC), alertas=alertas,
        )

    def consultar(self, nota: DadosNota) -> ResultadoEmissao | None:
        if self.modo == "homologacao":
            return None
        pedido = xml_layout2.pedido_consulta_nfe_por_rps(cnpj_remetente=so_digitos(self.prestador.cnpj), ccm=self.ccm,
                                                         serie=nota.serie, numero=nota.numero, cert=self.cert)
        raiz = etree.fromstring(self._chamar("ConsultaNFe", pedido))
        nfe = next((e for e in raiz.iter() if isinstance(e.tag, str) and _local(e) == "NFe"), None)
        if nfe is None:
            return None
        numero = _texto(nfe, "ChaveNFe", "NumeroNFe")
        cod = _texto(nfe, "ChaveNFe", "CodigoVerificacao") or ""
        return ResultadoEmissao("emitida", numero_nfse=numero, codigo_verificacao=cod,
                                link_oficial=link_nota(self.ccm, numero, cod), emitida_em=datetime.now(UTC))

    def cancelar(self, nota: DadosNota, *, codigo: str, motivo: str) -> ResultadoCancelamento:
        if self.modo == "homologacao":
            return ResultadoCancelamento(False, erros=[ErroNota("O modo Teste da Prefeitura de SP não cancela notas.",
                                                                "Notas de teste não têm valor fiscal: nada a fazer.")])
        if not nota.numero_nfse:
            return ResultadoCancelamento(False, erros=[ErroNota("Esta nota não tem número da Prefeitura.",
                                                                "Consulte a nota antes de cancelar.")])
        pedido = xml_layout2.pedido_cancelamento(cnpj_remetente=so_digitos(self.prestador.cnpj), ccm=self.ccm,
                                                 numero_nfe=int(nota.numero_nfse), cert=self.cert)
        retorno = self._chamar("CancelamentoNFe", pedido)
        raiz = etree.fromstring(retorno)
        sucesso = (_texto(raiz, "Cabecalho", "Sucesso") or "").lower() == "true"
        erros = []
        for el in raiz:
            if isinstance(el.tag, str) and _local(el) == "Erro":
                cod = _texto(el, "Codigo")
                erros.append(erro_nota(int(cod) if cod and cod.isdigit() else None, _texto(el, "Descricao") or ""))
        return ResultadoCancelamento(sucesso and not erros, xml_layout2.para_bytes(pedido).decode(), retorno.decode(),
                                     erros)

    def testar(self) -> str:
        pedido = xml_layout2.pedido_consulta_cnpj(cnpj_remetente=so_digitos(self.prestador.cnpj),
                                                  cnpj=so_digitos(self.prestador.cnpj), cert=self.cert)
        if self.modo == "simulado":
            return "Pedido de teste montado e assinado (modo simulado: nada foi enviado à Prefeitura)."
        raiz = etree.fromstring(self._chamar("ConsultaCNPJ", pedido))
        ok = (_texto(raiz, "Cabecalho", "Sucesso") or "").lower() == "true"
        return ("A Prefeitura de SP aceitou o certificado e encontrou o CNPJ." if ok
                else "A Prefeitura respondeu, mas recusou a consulta do CNPJ: confira o certificado e o CCM.")
