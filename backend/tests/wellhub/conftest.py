"""Fixtures do Wellhub: perfis, cenário (unidade com capacidade 2, serviço), Wellhub FALSO (httpx.MockTransport).

Nenhum teste sai para a rede: o autouse `_sem_internet` troca a fábrica do cliente por uma que explode.
"""

from __future__ import annotations

import json
import re
from datetime import date, time, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.modules import registrar_modelos
from tests.conftest import auth, criar_usuario, entrar

registrar_modelos()

from app.core.db import agora  # noqa: E402
from app.domain.financeiro import hoje_de_negocio  # noqa: E402
from app.modules.agenda import servico as agenda  # noqa: E402
from app.modules.cadastros.models import TipoServico, Unidade  # noqa: E402
from app.modules.wellhub import cliente as cli  # noqa: E402
from app.modules.wellhub import regras  # noqa: E402

API_KEY = "chave-api-sintetica-wellhub-1234"
SEGREDO = "segredo-webhook-sintetico-5678"
GYM = "777"
BASE = "https://wellhub.invalid"


def hoje() -> date:
    return hoje_de_negocio(agora())


@pytest.fixture(autouse=True)
def _sem_internet():
    def proibido():
        raise AssertionError("Teste tentou criar o cliente HTTP REAL do Wellhub (internet proibida nos testes).")

    cli.definir_fabrica_cliente(proibido)
    yield
    cli.definir_fabrica_cliente(None)


@pytest.fixture
def full(client, db):
    criar_usuario(db, "Full", email="full@exemplo.com", login="full")
    return auth(entrar(client, "full@exemplo.com").json()["access_token"])


@pytest.fixture
def secretaria(client, db):
    criar_usuario(db, "Secretária", email="sec@exemplo.com", login="sec")
    return auth(entrar(client, "sec@exemplo.com").json()["access_token"])


@pytest.fixture
def professor(client, db):
    criar_usuario(db, "Professor", email="prof@exemplo.com", login="prof")
    return auth(entrar(client, "prof@exemplo.com").json()["access_token"])


@pytest.fixture
def base(db) -> SimpleNamespace:
    un = Unidade(nome="Matriz", capacidade=2)
    srv = TipoServico(nome="Pilates")
    db.add_all([un, srv])
    db.commit()
    return SimpleNamespace(unidade=un, servico=srv, uid=un.id, sid=srv.id)


class Wellhub:
    """Wellhub falso: confere cabeçalhos de autenticação, registra chamadas e responde conforme o cenário."""

    def __init__(self, **status):
        self.status = {"classes": 200, "produtos": 200, "criar_classe": 200, "slot": 200, "vagas": 200, "remover": 200,
                       "reserva": 200, "validar": 200, **status}
        self.chamadas: list[httpx.Request] = []
        self.proximo_slot = 9000

    def corpos(self, metodo: str, padrao: str) -> list[dict]:
        return [json.loads(c.content or b"{}") for c in self.chamadas if c.method == metodo and re.search(padrao, c.url.path)]

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.chamadas.append(req)
        if req.headers.get("authorization") != f"Bearer {API_KEY}" or req.headers.get("x-gym-id") != GYM:
            return httpx.Response(401, json={"message": "unauthorized"})
        p, m = req.url.path, req.method
        g = f"/booking/v1/gyms/{GYM}"
        if p == "/access/v1/validate" and m == "POST":
            return httpx.Response(self.status["validar"], json={"results": {"validated": True}})
        if p == f"{g}/products" and m == "GET":
            return httpx.Response(self.status["produtos"], json={"products": [{"product_id": 11, "name": "Pilates Wellhub"},
                                                                              {"product_id": 12, "name": "Funcional"}]})
        if p == f"{g}/classes" and m == "GET":
            return httpx.Response(self.status["classes"], json={"classes": [{"id": 1}, {"id": 2}]})
        if p == f"{g}/classes" and m == "POST":
            return httpx.Response(self.status["criar_classe"], json={"classes": [{"id": 501}]})
        if re.fullmatch(rf"{g}/classes/\d+", p) and m == "PUT":
            return httpx.Response(200, json={})
        if re.fullmatch(rf"{g}/classes/\d+/slots", p) and m == "POST":
            self.proximo_slot += 1
            return httpx.Response(self.status["slot"], json={"id": self.proximo_slot})
        if re.fullmatch(rf"{g}/classes/\d+/slots/\d+", p) and m == "PATCH":
            return httpx.Response(self.status["vagas"], json={})
        if re.fullmatch(rf"{g}/classes/\d+/slots/\d+", p) and m == "DELETE":
            return httpx.Response(204 if self.status["remover"] == 200 else self.status["remover"])
        if re.fullmatch(rf"{g}/bookings/[\w-]+", p) and m == "PATCH":
            return httpx.Response(self.status["reserva"], json={})
        return httpx.Response(404, json={})


def instalar(servidor: Wellhub) -> Wellhub:
    cli.definir_fabrica_cliente(lambda: cli.ClienteWellhub(BASE, transport=httpx.MockTransport(servidor)))
    return servidor


@pytest.fixture
def wh() -> Wellhub:
    return instalar(Wellhub())


@pytest.fixture
def configurado(client, base, full):
    """Unidade com Wellhub ativo: gym, chave, segredo e o serviço Pilates ligado ao produto 11."""
    r = client.put(f"/api/wellhub/unidades/{base.uid}", headers=full, json={
        "gym_id": GYM, "api_key": API_KEY, "webhook_secret": SEGREDO, "ativo": True, "valor_repasse_checkin": "12.50"})
    assert r.status_code == 200, r.text
    r = client.put(f"/api/wellhub/unidades/{base.uid}/mapeamentos", headers=full,
                   json={"itens": [{"tipo_servico_id": base.sid, "product_id": "11"}]})
    assert r.status_code == 200, r.text
    return r.json()


def sessao(db, base, dias: int = 1, hora: time = time(9, 0)):
    s, _ = agenda.obter_ou_criar_sessao(db, unidade_id=base.uid, tipo_servico_id=base.sid, profissional_id=None,
                                        data=hoje() + timedelta(days=dias), hora_inicio=hora)
    db.commit()
    return s


def assinado(corpo: dict | bytes, segredo: str = SEGREDO) -> tuple[bytes, dict]:
    bruto = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
    return bruto, {"X-Gympass-Signature": regras.assinar(segredo, bruto), "Content-Type": "application/json"}


def enviar(client, corpo, segredo: str = SEGREDO, headers: dict | None = None):
    bruto, h = assinado(corpo, segredo)
    return client.post("/api/webhooks/wellhub", content=bruto, headers=h if headers is None else headers)


def reserva_pedida(gympass="1234567890123", *, slot="9001", booking="BK-1", nome="Maria Sintética", gym=GYM, ts=1790000000):
    return {"event_type": "booking-requested", "event_data": {
        "user": {"unique_token": gympass, "name": nome, "email": "maria@exemplo.invalid", "phone_number": "11988887777"},
        "slot": {"id": slot, "gym_id": gym, "class_id": 501, "booking_number": booking}, "timestamp": ts}}


def cancelamento(booking="BK-1", *, tardio=False, gympass="1234567890123", slot="9001"):
    return {"event_type": "booking-late-canceled" if tardio else "booking-canceled", "event_data": {
        "user": {"unique_token": gympass}, "slot": {"id": slot, "gym_id": GYM, "booking_number": booking},
        "timestamp": 1790000100}}


def checkin(gympass="1234567890123", *, ts=None, nome="Carla Sintética"):
    return {"event_type": "checkin", "event_data": {
        "user": {"unique_token": gympass, "first_name": nome.split()[0], "last_name": nome.split()[-1]},
        "gym": {"id": int(GYM), "title": "Matriz", "product": {"id": 11, "description": "Pilates"}},
        "timestamp": ts if ts is not None else int(agora().timestamp())}}
