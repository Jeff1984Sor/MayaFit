"""Cliente HTTP das APIs de parceiros do Wellhub (Booking API e Access Control API).

Baseado na documentação pública (developers.wellhub.com / developers.gympass.com). Pontos marcados com
"A CONFIRMAR" dependem da credencial real (ver `docs/progresso-wellhub.md`):

- Autenticação: `Authorization: Bearer <api key>` (um token para Booking e Access Control) + `X-Gym-Id: <gym id>`.
- URLs: produção `https://api.partners.gympass.com`; sandbox `https://apitesting.partners.gympass.com`.
  Podem ser trocadas por `WELLHUB_URL_PRODUCAO` / `WELLHUB_URL_SANDBOX` (não são segredos).
- Booking: `/booking/v1/gyms/{gym}/classes`, `/classes/{class}/slots`, `/bookings/{booking_number}` (PATCH com o status).
- Access Control: `POST /access/v1/validate` com `{"gympass_id": "..."}`.

A fábrica é trocável (`definir_fabrica_cliente`): os testes injetam um `httpx.MockTransport` e nunca saem para a rede.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

URLS_PADRAO = {"producao": "https://api.partners.gympass.com", "sandbox": "https://apitesting.partners.gympass.com"}
# Status do PATCH de reserva (Booking API v1). A CONFIRMAR com a credencial real.
STATUS_RESERVADO = 2
STATUS_REJEITADO = 3
MOTIVO_LOTADA = "CLASS_IS_FULL"
MOTIVO_OUTRO = "OTHER"


class ErroWellhub(Exception):
    """Falha com mensagem pronta para o usuário (sem segredo)."""


def url_base(ambiente: str) -> str:
    var = "WELLHUB_URL_PRODUCAO" if ambiente == "producao" else "WELLHUB_URL_SANDBOX"
    return (os.environ.get(var) or URLS_PADRAO.get(ambiente) or URLS_PADRAO["sandbox"]).rstrip("/")


def _lista(dados: Any, *chaves: str) -> list[dict]:
    if isinstance(dados, list):
        return [x for x in dados if isinstance(x, dict)]
    if isinstance(dados, dict):
        for k in chaves:
            v = dados.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):
                return _lista(v, *chaves)
    return []


class ClienteWellhub:
    def __init__(self, base_url: str | None = None, *, transport: httpx.BaseTransport | None = None, timeout: float = 20):
        self.base_url = base_url.rstrip("/") if base_url else None
        self._http = httpx.Client(transport=transport, timeout=timeout)
        self._ambiente = "sandbox"
        self._api_key = ""
        self._gym_id = ""

    def configurar(self, *, ambiente: str, api_key: str, gym_id: str) -> ClienteWellhub:
        self._ambiente, self._api_key, self._gym_id = ambiente, api_key, gym_id
        return self

    def fechar(self) -> None:
        self._http.close()

    # ---------------------------------------------------------------------------------------------- básico
    @property
    def raiz(self) -> str:
        return self.base_url or url_base(self._ambiente)

    def _cabecalhos(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "X-Gym-Id": str(self._gym_id),
                "Content-Type": "application/json", "Accept": "application/json"}

    def _req(self, metodo: str, caminho: str, **kw) -> Any:
        resp = self._http.request(metodo, f"{self.raiz}{caminho}", headers=self._cabecalhos(), **kw)
        resp.raise_for_status()
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}

    def _gym(self) -> str:
        return f"/booking/v1/gyms/{self._gym_id}"

    # ---------------------------------------------------------------------------------------------- Booking API
    def listar_produtos(self) -> list[dict]:
        return _lista(self._req("GET", f"{self._gym()}/products"), "products", "results", "data")

    def listar_classes(self) -> list[dict]:
        return _lista(self._req("GET", f"{self._gym()}/classes"), "classes", "results", "data")

    def criar_classe(self, dados: dict) -> str:
        r = self._req("POST", f"{self._gym()}/classes", json={"classes": [dados]})
        itens = _lista(r, "classes", "results", "data")
        cid = (itens[0].get("id") if itens else None) or (r.get("id") if isinstance(r, dict) else None)
        if not cid:
            raise ErroWellhub("O Wellhub não devolveu o identificador da classe criada.")
        return str(cid)

    def atualizar_classe(self, class_id: str, dados: dict) -> None:
        self._req("PUT", f"{self._gym()}/classes/{class_id}", json=dados)

    def criar_slot(self, class_id: str, dados: dict) -> str:
        r = self._req("POST", f"{self._gym()}/classes/{class_id}/slots", json=dados)
        itens = _lista(r, "results", "slots", "data")
        sid = (r.get("id") if isinstance(r, dict) else None) or (itens[0].get("id") if itens else None)
        if not sid:
            raise ErroWellhub("O Wellhub não devolveu o identificador do horário (slot) criado.")
        return str(sid)

    def atualizar_vagas(self, class_id: str, slot_id: str, total_capacity: int, total_booked: int) -> None:
        self._req("PATCH", f"{self._gym()}/classes/{class_id}/slots/{slot_id}",
                  json={"total_capacity": total_capacity, "total_booked": total_booked})

    def remover_slot(self, class_id: str, slot_id: str) -> None:
        self._req("DELETE", f"{self._gym()}/classes/{class_id}/slots/{slot_id}")

    def responder_reserva(self, booking_number: str, *, aceitar: bool, motivo: str | None = None) -> None:
        corpo: dict[str, Any] = {"status": STATUS_RESERVADO if aceitar else STATUS_REJEITADO}
        if not aceitar:
            corpo["reason"] = motivo or MOTIVO_OUTRO
        self._req("PATCH", f"{self._gym()}/bookings/{booking_number}", json=corpo)

    # ---------------------------------------------------------------------------------------------- Access Control
    def validar_acesso(self, gympass_id: str) -> dict:
        r = self._req("POST", "/access/v1/validate", json={"gympass_id": gympass_id})
        return r if isinstance(r, dict) else {}


_fabrica: Callable[[], ClienteWellhub] = ClienteWellhub


def definir_fabrica_cliente(fabrica: Callable[[], ClienteWellhub] | None) -> None:
    """Troca a fábrica do cliente (testes). `None` volta ao cliente real."""
    global _fabrica
    _fabrica = fabrica or ClienteWellhub


def novo_cliente() -> ClienteWellhub:
    return _fabrica()


def traduzir_http(exc: Exception, contexto: str = "") -> ErroWellhub:
    """Erro HTTP → mensagem segura em português (nunca inclui a chave nem o corpo da resposta)."""
    if isinstance(exc, ErroWellhub):
        return exc
    e = _traduzir(exc, f"{contexto}: " if contexto else "")
    texto = str(e)
    return ErroWellhub(texto[:1].upper() + texto[1:])


def _traduzir(exc: Exception, pre: str) -> ErroWellhub:
    if isinstance(exc, httpx.HTTPStatusError):
        c = exc.response.status_code
        if c in (401, 403):
            return ErroWellhub(pre + "o Wellhub recusou a credencial. Confira a chave de API, o gym id e o ambiente.")
        if c == 404:
            return ErroWellhub(pre + "o Wellhub não encontrou o recurso (gym id, classe ou horário inexistente).")
        if c == 422 or c == 400:
            return ErroWellhub(pre + f"o Wellhub recusou os dados enviados (erro {c}).")
        if c == 429:
            return ErroWellhub(pre + "o Wellhub limitou as chamadas (muitas em pouco tempo). Tente de novo em instantes.")
        return ErroWellhub(pre + f"o Wellhub respondeu com erro {c}. Tente de novo mais tarde.")
    if isinstance(exc, httpx.HTTPError):
        return ErroWellhub(pre + "não foi possível falar com o Wellhub. Confira a conexão e tente de novo.")
    return ErroWellhub(pre + "falha inesperada ao falar com o Wellhub.")
