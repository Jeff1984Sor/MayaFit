"""XMLDSig enveloped "à moda NF-e": Signature no namespace PADRÃO (sem prefixo), irmã do elemento assinado.

Por que não o signxml aqui: o C14N de uma SUBÁRVORE no lxml/libxml2 (6.x) emite `xmlns=""` nos netos quando o
namespace padrão vem de um ancestral (`<inf xmlns="n"><c><d xmlns="">`). Isso é C14N errado: o validador da Sefin
calcularia outro digest. Canonicalizar uma CÓPIA da subárvore (que vira raiz e herda as declarações) dá o
resultado correto. O cálculo é explícito e curto:

1. DigestValue = SHA-256 do C14N 1.0 (inclusivo) do elemento referenciado (`#Id`);
2. SignatureValue = RSA-SHA256 (PKCS#1 v1.5) do C14N do `SignedInfo` já posicionado no documento;
3. KeyInfo/X509Data/X509Certificate com o certificado do estúdio.

Os testes conferem a assinatura com o verificador independente do signxml.
"""

from __future__ import annotations

import base64
import copy
import hashlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import Encoding
from lxml import etree

from app.modules.nfse.certificado import CertificadoCarregado

DS = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"


def c14n(el: etree._Element) -> bytes:
    """C14N 1.0 inclusivo de um elemento (ver nota do módulo sobre a cópia)."""
    return etree.tostring(copy.deepcopy(el), method="c14n", exclusive=False, with_comments=False)


def _ds(pai: etree._Element, tag: str, texto: str | None = None, **attrs: str) -> etree._Element:
    el = etree.SubElement(pai, f"{{{DS}}}{tag}", **attrs)
    if texto is not None:
        el.text = texto
    return el


def assinar_enveloped(raiz: etree._Element, alvo: etree._Element, cert: CertificadoCarregado) -> etree._Element:
    """Acrescenta `<Signature xmlns="...xmldsig#">` como último filho de `raiz`, assinando `alvo` (que tem `Id`)."""
    ref = alvo.get("Id")
    if not ref:
        raise ValueError("O elemento a assinar precisa do atributo Id.")
    digest = base64.b64encode(hashlib.sha256(c14n(alvo)).digest()).decode()

    sig = etree.SubElement(raiz, f"{{{DS}}}Signature", nsmap={None: DS})
    si = _ds(sig, "SignedInfo")
    _ds(si, "CanonicalizationMethod", Algorithm=C14N)
    _ds(si, "SignatureMethod", Algorithm=RSA_SHA256)
    r = _ds(si, "Reference", URI=f"#{ref}")
    tr = _ds(r, "Transforms")
    _ds(tr, "Transform", Algorithm=ENVELOPED)
    _ds(tr, "Transform", Algorithm=C14N)
    _ds(r, "DigestMethod", Algorithm=SHA256)
    _ds(r, "DigestValue", digest)

    # reabre do texto para o C14N do SignedInfo enxergar o namespace exatamente como o destinatário verá
    doc = etree.fromstring(etree.tostring(raiz))
    si_doc = doc.find(f"{{{DS}}}Signature/{{{DS}}}SignedInfo")
    valor = cert.chave.sign(c14n(si_doc), padding.PKCS1v15(), hashes.SHA256())
    sig_doc = si_doc.getparent()
    _ds(sig_doc, "SignatureValue", base64.b64encode(valor).decode())
    x509 = _ds(_ds(sig_doc, "KeyInfo"), "X509Data")
    _ds(x509, "X509Certificate", base64.b64encode(cert.cert.public_bytes(Encoding.DER)).decode())
    return doc
