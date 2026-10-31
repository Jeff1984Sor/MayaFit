"""Interface dos drivers de catraca.

Todo driver implementa:

- ``liberar(dispositivo, sentido)``: libera UM giro/abertura no sentido pedido ("entrada" ou "saida").
- ``status(dispositivo)``: confere se o equipamento responde (usado no "Testar conexão").
- ``plano_navegador(dispositivo, acao, sentido)``: a MESMA operação descrita como passos HTTP para o navegador do
  totem executar na rede local (o servidor fica na nuvem e não alcança a catraca). Driver que não fala HTTP devolve
  ``None`` (aí só o agente local ou o servidor conseguem acionar).

O ``dispositivo`` é um ``DadosCatraca`` já com a senha DECIFRADA (só em memória, nunca em log).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

SentidoGiro = Literal["entrada", "saida"]


@dataclass(frozen=True)
class DadosCatraca:
    id: int
    nome: str
    host: str | None = None
    porta: int | None = None
    usar_https: bool = False
    usuario: str | None = None
    senha: str | None = None
    sentido_entrada: str = "clockwise"  # sentido do giro que corresponde à ENTRADA (clockwise | anticlockwise | both)
    acao_liberacao: str = "catra"  # catra (catraca iDBlock) | door (relé de porta iDAccess/iDFlex)
    porta_rele: int = 1
    timeout_s: float = 5.0

    @property
    def url_base(self) -> str:
        esquema = "https" if self.usar_https else "http"
        porta = f":{self.porta}" if self.porta else ""
        return f"{esquema}://{self.host}{porta}"


@dataclass
class Resultado:
    ok: bool
    mensagem: str
    detalhes: dict[str, Any] = field(default_factory=dict)


@dataclass
class PassoHttp:
    """Um passo para o navegador: ``{{sessao}}`` no caminho/corpo é trocado pelo valor extraído no passo anterior."""

    metodo: str
    url: str
    corpo: dict[str, Any] | None = None
    extrair: str | None = None  # nome do campo JSON da resposta a guardar como {{sessao}}


@dataclass
class PlanoNavegador:
    driver: str
    passos: list[PassoHttp]
    descricao: str = ""


class ErroDriver(Exception):
    """Falha de comunicação ou resposta inesperada do equipamento (mensagem já em português)."""


class Driver(ABC):
    nome: str = ""
    rotulo: str = ""
    suporta_navegador: bool = False

    @abstractmethod
    def liberar(self, dispositivo: DadosCatraca, sentido: SentidoGiro = "entrada") -> Resultado: ...

    @abstractmethod
    def status(self, dispositivo: DadosCatraca) -> Resultado: ...

    def plano_navegador(self, dispositivo: DadosCatraca, acao: str = "liberar", sentido: SentidoGiro = "entrada") -> PlanoNavegador | None:
        return None


def giro_do_sentido(sentido_entrada: str, sentido: SentidoGiro) -> str:
    """Traduz entrada/saída para o giro físico da catraca, conforme a instalação (para que lado ela gira para entrar)."""
    if sentido_entrada == "both":
        return "both"
    if sentido == "entrada":
        return sentido_entrada
    return "anticlockwise" if sentido_entrada == "clockwise" else "clockwise"
