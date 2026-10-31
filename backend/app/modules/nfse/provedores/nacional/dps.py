"""Montagem e assinatura dos XML do Padrão Nacional (leiaute DPS v1.01 e Pedido de Registro de Evento v1.01).

Fonte: esquemas oficiais em ./xsd (pacote "NFSe-ESQUEMAS_XSD v1.01 20260209", gov.br/nfse › Documentação atual).
Regras práticas (fórum ACBr / produção restrita): a raiz NÃO pode ter prefixo de namespace (E1228); assinatura
XMLDSig obrigatória (E0717) referenciando o Id do infDPS; dCompet não pode ser posterior a dhEmi (E0015).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from lxml import etree

from app.domain.documentos import so_digitos
from app.modules.nfse import regras
from app.modules.nfse.certificado import CertificadoCarregado
from app.modules.nfse.provedores.base import DadosNota, Prestador
from app.modules.nfse.provedores.xmldsig import assinar_enveloped

NS = "http://www.sped.fazenda.gov.br/nfse"
VERSAO = "1.01"
VER_APLIC = "MayaFit-1.0"
XSD_DIR = Path(__file__).parent / "xsd"
XSD_DPS = XSD_DIR / "DPS_v1.01.xsd"
XSD_EVENTO = XSD_DIR / "pedRegEvento_v1.01.xsd"

# Motivos de cancelamento aceitos no evento e101101 (TSCodJustCanc)
MOTIVOS_CANCELAMENTO = {"1": "Erro na emissão", "2": "Serviço não prestado", "9": "Outros"}


def _sub(pai: etree._Element, tag: str, texto: object | None = None) -> etree._Element:
    el = etree.SubElement(pai, f"{{{NS}}}{tag}")
    if texto is not None:
        el.text = str(texto)
    return el


def _dec(v: Decimal) -> str:
    """TSDec15V2: "0" ou número com 2 casas sem zero à esquerda."""
    q = regras.centavos(v)
    return "0" if q == 0 else f"{q:.2f}"


def montar(prestador: Prestador, nota: DadosNota, *, tp_amb: str, dh_emi: str) -> etree._Element:
    """Elemento DPS (sem assinatura), elementos na ORDEM do TCInfDPS."""
    id_dps = regras.id_dps(municipio=prestador.codigo_municipio, cnpj=prestador.cnpj, serie=nota.serie,
                           numero=nota.numero)
    raiz = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS})
    raiz.set("versao", VERSAO)
    inf = _sub(raiz, "infDPS")
    inf.set("Id", id_dps)
    _sub(inf, "tpAmb", tp_amb)
    _sub(inf, "dhEmi", dh_emi)
    _sub(inf, "verAplic", VER_APLIC)
    _sub(inf, "serie", str(int(so_digitos(nota.serie) or "1")))
    _sub(inf, "nDPS", str(nota.numero))
    _sub(inf, "dCompet", min(nota.competencia, date.fromisoformat(dh_emi[:10])).isoformat())
    _sub(inf, "tpEmit", "1")  # emitente = prestador
    _sub(inf, "cLocEmi", prestador.codigo_municipio)

    # prestador: quando ele é o emitente, nome e endereço vêm do cadastro nacional (não informar)
    prest = _sub(inf, "prest")
    _sub(prest, "CNPJ", so_digitos(prestador.cnpj))
    if prestador.inscricao_municipal:
        _sub(prest, "IM", so_digitos(prestador.inscricao_municipal) or prestador.inscricao_municipal)
    if so_digitos(prestador.telefone) and 6 <= len(so_digitos(prestador.telefone)) <= 20:
        _sub(prest, "fone", so_digitos(prestador.telefone))
    if prestador.email:
        _sub(prest, "email", prestador.email[:80])
    reg = _sub(prest, "regTrib")
    op = regras.OP_SIMPLES_NACIONAL.get(prestador.regime, "1")
    _sub(reg, "opSimpNac", op)
    if op == "3":
        _sub(reg, "regApTribSN", str(prestador.extras.get("regime_apuracao_sn") or "1"))
    _sub(reg, "regEspTrib", str(prestador.extras.get("regime_especial") or "0"))

    # tomador
    t = nota.tomador
    doc = so_digitos(t.documento)
    if doc or t.nome:
        toma = _sub(inf, "toma")
        if len(doc) == 14:
            _sub(toma, "CNPJ", doc)
        elif len(doc) == 11:
            _sub(toma, "CPF", doc)
        else:
            _sub(toma, "cNaoNIF", "0")
        _sub(toma, "xNome", regras.limpar_texto(t.nome)[:300])
        end = t.endereco or {}
        cep = so_digitos(end.get("cep"))
        cmun = so_digitos(end.get("codigo_municipio"))
        if len(cep) == 8 and len(cmun) == 7 and end.get("logradouro") and end.get("bairro"):
            e = _sub(toma, "end")
            nac = _sub(e, "endNac")
            _sub(nac, "cMun", cmun)
            _sub(nac, "CEP", cep)
            _sub(e, "xLgr", regras.limpar_texto(end["logradouro"])[:255])
            _sub(e, "nro", regras.limpar_texto(str(end.get("numero") or "S/N"))[:60])
            if end.get("complemento"):
                _sub(e, "xCpl", regras.limpar_texto(end["complemento"])[:156])
            _sub(e, "xBairro", regras.limpar_texto(end["bairro"])[:60])
        if t.email:
            _sub(toma, "email", t.email.strip()[:80])

    # serviço
    serv = _sub(inf, "serv")
    _sub(_sub(serv, "locPrest"), "cLocPrestacao", prestador.codigo_municipio)
    cserv = _sub(serv, "cServ")
    _sub(cserv, "cTribNac", nota.codigo_tributacao_nacional)
    if nota.codigo_servico_municipal and so_digitos(nota.codigo_servico_municipal):
        _sub(cserv, "cTribMun", so_digitos(nota.codigo_servico_municipal).zfill(3)[:3])
    _sub(cserv, "xDescServ", regras.limpar_texto(nota.discriminacao)[:2000] or "Servicos prestados")
    if nota.nbs and len(so_digitos(nota.nbs)) == 9:
        _sub(cserv, "cNBS", so_digitos(nota.nbs))

    # valores
    val = _sub(inf, "valores")
    _sub(_sub(val, "vServPrest"), "vServ", _dec(nota.valor))
    if nota.deducoes and nota.deducoes > 0:
        _sub(_sub(val, "vDedRed"), "vDR", _dec(nota.deducoes))
    trib = _sub(val, "trib")
    tm = _sub(trib, "tribMun")
    _sub(tm, "tribISSQN", "1")  # operação tributável
    _sub(tm, "tpRetISSQN", "2" if nota.iss_retido else "1")
    if nota.informar_aliquota and op != "2":
        _sub(tm, "pAliq", f"{Decimal(nota.aliquota):.2f}")
    tot = _sub(trib, "totTrib")
    if op == "3" and nota.percentual_tributos_sn is not None:
        _sub(tot, "pTotTribSN", f"{Decimal(nota.percentual_tributos_sn):.2f}")
    else:
        _sub(tot, "indTotTrib", "0")
    return raiz


def montar_cancelamento(*, cnpj: str, chave: str, codigo: str, motivo: str, tp_amb: str, dh_evento: str) -> etree._Element:
    """Pedido de Registro de Evento e101101 (cancelamento). Id = "PRE" + chave(50) + tipo do evento(6)."""
    raiz = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS})
    raiz.set("versao", VERSAO)
    inf = _sub(raiz, "infPedReg")
    inf.set("Id", f"PRE{chave}101101")
    _sub(inf, "tpAmb", tp_amb)
    _sub(inf, "verAplic", VER_APLIC)
    _sub(inf, "dhEvento", dh_evento)
    _sub(inf, "CNPJAutor", so_digitos(cnpj))
    _sub(inf, "chNFSe", chave)
    ev = _sub(inf, "e101101")
    _sub(ev, "xDesc", "Cancelamento de NFS-e")
    _sub(ev, "cMotivo", codigo)
    _sub(ev, "xMotivo", regras.limpar_texto(motivo)[:255])
    return raiz


def assinar(raiz: etree._Element, cert: CertificadoCarregado) -> etree._Element:
    """XMLDSig enveloped do primeiro filho (infDPS/infPedReg), RSA-SHA256 + C14N 1.0, Signature no namespace
    padrão (sem prefixo `ds:`), como no NF-e. A VALIDAR na produção restrita (ver docs/progresso-nfse.md)."""
    return assinar_enveloped(raiz, raiz[0], cert)


def para_bytes(raiz: etree._Element) -> bytes:
    return etree.tostring(raiz, encoding="utf-8", xml_declaration=True)


class _ResolvedorXsd(etree.Resolver):
    r"""Entrega uma cópia ajustada de tiposSimples: o padrão oficial da série é `^0{0,4}\d{1,5}$`, e em XSD `^`/`$`
    são caracteres literais (o libxml2 recusa "1"; o validador .NET da Sefin aceita). Só para a validação local."""

    def resolve(self, url, pubid, context):
        if url and url.replace("\\", "/").endswith("tiposSimples_v1.01.xsd"):
            texto = (XSD_DIR / "tiposSimples_v1.01.xsd").read_text(encoding="utf-8-sig")
            texto = texto.replace(r'value="^0{0,4}\d{1,5}$"', r'value="0{0,4}\d{1,5}"')
            return self.resolve_string(texto.encode(), context, base_url=str(XSD_DIR / "tiposSimples_v1.01.xsd"))
        return None


_SCHEMAS: dict[str, etree.XMLSchema] = {}


def _schema(arquivo: Path) -> etree.XMLSchema:
    if str(arquivo) not in _SCHEMAS:
        parser = etree.XMLParser()
        parser.resolvers.add(_ResolvedorXsd())
        _SCHEMAS[str(arquivo)] = etree.XMLSchema(etree.parse(str(arquivo), parser))
    return _SCHEMAS[str(arquivo)]


def _validar(raiz: etree._Element, arquivo: Path) -> list[str]:
    schema = _schema(arquivo)
    if schema.validate(raiz):
        return []
    return [f"linha {e.line}: {e.message}" for e in schema.error_log][:15]


def validar_dps(raiz: etree._Element) -> list[str]:
    return _validar(raiz, XSD_DPS)


def validar_evento(raiz: etree._Element) -> list[str]:
    return _validar(raiz, XSD_EVENTO)
