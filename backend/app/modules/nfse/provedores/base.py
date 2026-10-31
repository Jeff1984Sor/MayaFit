"""Contrato comum dos provedores de NFS-e (emitir, consultar, cancelar).

Cada município/padrão é um pacote irmão (`nacional/`, `sao_paulo/`) com uma classe que herda `Provedor`.
O serviço do módulo só conversa com esta interface: trocar de provedor é trocar a configuração.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import httpx
from lxml import etree

from app.modules.nfse import certificado as certs
from app.modules.nfse.certificado import CertificadoCarregado

TIMEOUT_S = 40.0


class FalhaComunicacao(Exception):
    """Timeout/indisponibilidade/5xx. Diferente de rejeição: a fila tenta de novo (consultando antes de reenviar)."""


class ErroConfiguracao(Exception):
    """Falta algo na configuração para falar com o provedor (ex.: certificado fora do modo simulado)."""


@dataclass
class ErroNota:
    """Erro já traduzido para gente: o que houve + o que fazer. `tecnico` guarda o texto original do provedor."""

    mensagem: str
    acao: str
    codigo: str | None = None
    campo: str | None = None
    tecnico: str | None = None
    nivel: str = "erro"  # erro | aviso

    def como_dict(self) -> dict[str, Any]:
        return {"mensagem": self.mensagem, "acao": self.acao, "codigo": self.codigo, "campo": self.campo,
                "tecnico": self.tecnico, "nivel": self.nivel}


@dataclass
class Prestador:
    cnpj: str
    razao_social: str
    inscricao_municipal: str | None
    codigo_municipio: str
    regime: str  # mei | simples | presumido | real
    email: str | None = None
    telefone: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tomador:
    documento: str | None  # CPF (11) ou CNPJ (14), só dígitos
    nome: str
    email: str | None = None
    endereco: dict[str, Any] | None = None  # cep, logradouro, numero, complemento, bairro, codigo_municipio, uf


@dataclass
class DadosNota:
    serie: str
    numero: int
    competencia: date
    discriminacao: str
    item_lista_servico: str
    codigo_tributacao_nacional: str
    valor: Decimal
    aliquota: Decimal
    tomador: Tomador
    deducoes: Decimal = Decimal("0")
    iss_retido: bool = False
    codigo_servico_municipal: str | None = None
    nbs: str | None = None
    informar_aliquota: bool = False
    percentual_tributos_sn: Decimal | None = None
    # preenchidos pelo provedor nas consultas/cancelamentos
    chave_acesso: str | None = None
    numero_nfse: str | None = None
    id_dps: str | None = None


@dataclass
class ResultadoEmissao:
    situacao: str  # emitida | validada | rejeitada
    xml_enviado: str = ""
    xml_retorno: str = ""
    numero_nfse: str | None = None
    codigo_verificacao: str | None = None
    chave_acesso: str | None = None
    id_dps: str | None = None
    link_oficial: str | None = None
    emitida_em: datetime | None = None
    erros: list[ErroNota] = field(default_factory=list)
    alertas: list[ErroNota] = field(default_factory=list)


@dataclass
class ResultadoCancelamento:
    sucesso: bool
    xml_enviado: str = ""
    xml_retorno: str = ""
    erros: list[ErroNota] = field(default_factory=list)


# ------------------------------------------------------------------------------------------------- transporte
@dataclass
class RespostaHttp:
    status: int
    conteudo: bytes
    cabecalhos: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        import json

        try:
            return json.loads(self.conteudo or b"null")
        except ValueError:
            return None


class Transporte(Protocol):
    def __call__(self, metodo: str, url: str, *, json: Any = None, conteudo: bytes | None = None,
                 cabecalhos: dict[str, str] | None = None) -> RespostaHttp: ...


class TransporteHttpx:
    """HTTP com TLS mútuo (certificado A1). 5xx/429/timeouts viram `FalhaComunicacao` após `tentativas`."""

    def __init__(self, cert: CertificadoCarregado, *, tentativas: int = 2, timeout: float = TIMEOUT_S):
        self.cert = cert
        self.tentativas = tentativas
        self.timeout = timeout

    def __call__(self, metodo, url, *, json=None, conteudo=None, cabecalhos=None) -> RespostaHttp:
        espera = 1.5
        ultimo: Exception | None = None
        for tentativa in range(1, self.tentativas + 1):
            try:
                with httpx.Client(verify=certs.ssl_context(self.cert), timeout=self.timeout) as c:
                    r = c.request(metodo, url, json=json, content=conteudo, headers=cabecalhos)
                if r.status_code >= 500 or r.status_code == 429:
                    raise FalhaComunicacao(f"HTTP {r.status_code}: {r.text[:300]}")
                return RespostaHttp(r.status_code, r.content, dict(r.headers))
            except (httpx.TransportError, FalhaComunicacao) as e:
                ultimo = e
                if tentativa < self.tentativas:
                    time.sleep(espera)
                    espera *= 2
        raise FalhaComunicacao(str(ultimo))


# ------------------------------------------------------------------------------------------------- provedor
class Provedor(ABC):
    nome: str = ""
    rotulo: str = ""

    def __init__(self, prestador: Prestador, *, modo: str, cert: CertificadoCarregado | None,
                 transporte: Transporte | None = None):
        if modo != "simulado" and cert is None:
            raise ErroConfiguracao("Envie o certificado A1 em Configurações › NFS-e antes de sair do modo simulado.")
        self.prestador = prestador
        self.modo = modo
        self.cert = cert or certs.de_simulacao()
        self._transporte = transporte

    @property
    def transporte(self) -> Transporte:
        if self._transporte is None:
            self._transporte = TransporteHttpx(self.cert)
        return self._transporte

    @abstractmethod
    def montar_xml(self, nota: DadosNota) -> tuple[bytes, list[str]]:
        """XML assinado que seria enviado + erros de schema (lista vazia = válido no XSD oficial)."""

    @abstractmethod
    def emitir(self, nota: DadosNota) -> ResultadoEmissao: ...

    @abstractmethod
    def consultar(self, nota: DadosNota) -> ResultadoEmissao | None:
        """A nota desta DPS/RPS já existe no provedor? Usado antes de reenviar após falha de comunicação."""

    @abstractmethod
    def cancelar(self, nota: DadosNota, *, codigo: str, motivo: str) -> ResultadoCancelamento: ...

    def danfse(self, nota: DadosNota) -> bytes | None:
        """PDF oficial, quando o provedor oferece (Nacional: DANFSe do ADN)."""
        return None

    def testar(self) -> str:
        """Teste de configuração sem emitir nada."""
        return "Configuração montada e assinada localmente."


def validar_xsd(raiz: etree._Element, arquivo: Path) -> list[str]:
    schema = _schema(str(arquivo))
    if schema.validate(raiz):
        return []
    return [f"linha {e.line}: {e.message}" for e in schema.error_log][:15]


_SCHEMAS: dict[str, etree.XMLSchema] = {}


def _schema(caminho: str) -> etree.XMLSchema:
    if caminho not in _SCHEMAS:
        _SCHEMAS[caminho] = etree.XMLSchema(etree.parse(caminho))
    return _SCHEMAS[caminho]
