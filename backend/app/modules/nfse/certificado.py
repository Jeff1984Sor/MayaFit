"""Certificado A1 (.pfx/.p12): leitura, informações para a tela e acesso decifrado SÓ em memória.

Porte de `app/core/certificados.py` do MayaJus, guardando o arquivo cifrado em `nfse_config` (app.core.segredos).
"""

from __future__ import annotations

import os
import re
import ssl
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from app.core import segredos


class CertificadoInvalido(ValueError):
    pass


@dataclass
class InfoCertificado:
    titular: str
    cnpj: str | None
    emissor: str
    valido_de: date
    valido_ate: date
    serial: str


@dataclass
class CertificadoCarregado:
    chave: RSAPrivateKey
    cert: x509.Certificate
    cadeia: list[x509.Certificate]

    def chave_pem(self) -> bytes:
        return self.chave.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )

    def cert_pem(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.PEM)


def _nome(n: x509.Name) -> str:
    attrs = n.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(attrs[0].value) if attrs else n.rfc4514_string()


def carregar_pfx(pfx: bytes, senha: str) -> CertificadoCarregado:
    try:
        chave, cert, cadeia = pkcs12.load_key_and_certificates(pfx, senha.encode() if senha else None)
    except ValueError as e:
        raise CertificadoInvalido("Não foi possível abrir o certificado. Confira a senha e se o arquivo é um .pfx A1.") from e
    if cert is None or chave is None:
        raise CertificadoInvalido("O arquivo não contém um certificado A1 com chave privada.")
    if not isinstance(chave, RSAPrivateKey):
        raise CertificadoInvalido("O certificado precisa usar chave RSA (padrão ICP-Brasil).")
    return CertificadoCarregado(chave=chave, cert=cert, cadeia=list(cadeia or []))


def info(c: CertificadoCarregado) -> InfoCertificado:
    titular = _nome(c.cert.subject)
    # e-CNPJ ICP-Brasil traz "RAZAO SOCIAL:12345678000199" no CN
    m = re.search(r":(\d{14})$", titular)
    return InfoCertificado(
        titular=titular.split(":")[0] if m else titular,
        cnpj=m.group(1) if m else None,
        emissor=_nome(c.cert.issuer),
        valido_de=c.cert.not_valid_before_utc.date(),
        valido_ate=c.cert.not_valid_after_utc.date(),
        serial=format(c.cert.serial_number, "x"),
    )


def cifrar(pfx: bytes, senha: str) -> tuple[bytes, bytes]:
    return segredos.cifrar(pfx), segredos.cifrar_texto(senha)


def abrir(pfx_cifrado: bytes, senha_cifrada: bytes) -> CertificadoCarregado:
    return carregar_pfx(segredos.decifrar(pfx_cifrado), segredos.decifrar_texto(senha_cifrada))


def ssl_context(cert: CertificadoCarregado) -> ssl.SSLContext:
    """TLS mútuo: o ssl do Python só carrega cadeia de arquivo; grava um PEM temporário e apaga em seguida."""
    ctx = ssl.create_default_context()
    pem = cert.cert_pem() + b"".join(c.public_bytes(serialization.Encoding.PEM) for c in cert.cadeia)
    fd, caminho = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pem + cert.chave_pem())
        ctx.load_cert_chain(caminho)
    finally:
        os.remove(caminho)
    return ctx


def gerar_autoassinado(*, cnpj: str = "11222333000181", razao: str = "ESTUDIO SIMULADO", dias: int = 365,
                       senha: str = "1234") -> bytes:
    """.pfx autoassinado no formato ICP (CN "RAZAO:CNPJ"): usado no modo simulado, na demonstração e nos testes."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{razao}:{cnpj}")])
    agora = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=dias)).sign(chave, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        b"mayafit", chave, cert, None, serialization.BestAvailableEncryption(senha.encode())
    )


_simulacao: CertificadoCarregado | None = None


def de_simulacao() -> CertificadoCarregado:
    """Certificado efêmero: no modo simulado sem .pfx o XML ainda é assinado e validado de verdade."""
    global _simulacao
    if _simulacao is None:
        _simulacao = carregar_pfx(gerar_autoassinado(), "1234")
    return _simulacao
