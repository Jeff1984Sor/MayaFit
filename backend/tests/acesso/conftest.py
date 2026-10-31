"""Fixtures do controle de acesso: cenário sintético (unidade, aula de hoje, aluna com contrato) e relógio congelado.

"Agora" dos testes: segunda 26/10/2026 08:50 em Brasília (11:50 UTC); a aula da Ana é às 09:00.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules import registrar_modelos
from tests.conftest import auth, criar_usuario, entrar

registrar_modelos()

from app.modules.acesso import models as _m  # noqa: E402,F401
from app.modules.acesso import rotas_totem, routes  # noqa: E402
from app.modules.acesso.drivers import controlid  # noqa: E402
from app.modules.alunos.models import Aluno  # noqa: E402
from app.modules.cadastros.models import HorarioFuncionamento, Plano, Recorrencia  # noqa: E402
from app.modules.contratos.models import Contrato  # noqa: E402
from app.modules.financeiro.models import ContaReceber  # noqa: E402
from tests.agenda import fabrica  # noqa: E402

AGORA = datetime(2026, 10, 26, 11, 50, tzinfo=UTC)  # 08:50 em Brasília
HOJE = date(2026, 10, 26)


class Relogio:
    def __init__(self, agora: datetime):
        self.agora = agora

    def __call__(self) -> datetime:
        return self.agora


@pytest.fixture(autouse=True)
def relogio(monkeypatch):
    r = Relogio(AGORA)
    monkeypatch.setattr(routes, "_agora", r)
    monkeypatch.setattr(rotas_totem, "_agora", r)
    return r


@pytest.fixture(autouse=True)
def _sem_rede():
    def proibido(_):
        raise AssertionError("Teste tentou falar com uma catraca de verdade (rede proibida nos testes).")

    controlid.definir_fabrica_cliente(proibido)
    yield
    controlid.definir_fabrica_cliente(None)


@pytest.fixture
def full(client, db):
    criar_usuario(db, "Full", email="full@exemplo.com", login="full")
    return auth(entrar(client, "full").json()["access_token"])


@pytest.fixture
def secretaria(client, db):
    criar_usuario(db, "Secretária", email="sec@exemplo.com", login="sec")
    return auth(entrar(client, "sec").json()["access_token"])


def novo_contrato(db, aluno, plano, prof, inicio=date(2026, 10, 1), fim=date(2026, 12, 31)) -> Contrato:
    c = Contrato(aluno_id=aluno.id, plano_id=plano.id, unidade_id=aluno.unidade_id, profissional_id=prof.id,
                 recorrencia=Recorrencia.MENSAL, valor_parcela=Decimal("300"), valor_total=Decimal("900"), data_inicio=inicio, data_fim=fim)
    db.add(c)
    db.flush()
    return c


def parcela(db, aluno, vencimento: date, contrato=None, valor="300.00") -> ContaReceber:
    p = ContaReceber(aluno_id=aluno.id, contrato_id=contrato.id if contrato else None, valor=Decimal(valor), vencimento=vencimento)
    db.add(p)
    db.flush()
    return p


@pytest.fixture
def cenario(db):
    un = fabrica.unidade(db, capacidade=4)
    srv = fabrica.servico(db, "Pilates")
    prof = fabrica.profissional(db, "Natalia Souza")
    plano = Plano(nome="Pilates 2x", tipo_servico_id=srv.id, valor=Decimal("300"), aulas_por_semana=2, duracao_meses=3)
    plano_livre = Plano(nome="Academia livre", tipo_servico_id=srv.id, valor=Decimal("150"), aulas_por_semana=0, duracao_meses=1)
    db.add_all([plano, plano_livre])
    db.flush()
    ana = fabrica.aluno(db, un, "ANA PAULA SOUZA")
    ana.data_nascimento = date(1990, 10, 26)
    ana.codigo_legado = 4321
    bruno = fabrica.aluno(db, un, "Bruno Lima")
    contrato = novo_contrato(db, ana, plano, prof)
    ses = fabrica.sessao(db, un, srv, prof, dia=HOJE, inicio=time(9, 0))
    from app.modules.agenda import servico as agenda

    reserva = agenda.criar_reserva(db, ana.id, ses.id, contrato_id=contrato.id)
    db.add(HorarioFuncionamento(unidade_id=un.id, dia_semana=0, hora_inicio=time(6, 0), hora_fim=time(22, 0), ativo=True))
    db.commit()
    return SimpleNamespace(un=un, srv=srv, prof=prof, plano=plano, plano_livre=plano_livre, ana=ana, bruno=bruno, contrato=contrato,
                           ses=ses, reserva=reserva)


def vetor(semente: int, dim: int = 128) -> list[float]:
    rnd = random.Random(semente)
    return [rnd.gauss(0, 1) for _ in range(dim)]


def ruido(v: list[float], intensidade: float, semente: int = 99) -> list[float]:
    rnd = random.Random(semente)
    norma = math.sqrt(sum(x * x for x in v))
    return [x + rnd.gauss(0, intensidade) * norma / math.sqrt(len(v)) for x in v]


PROVA_VIDA = {"piscou": True, "real": 0.9, "live": 0.9}


def criar_totem(client, full, catraca_id=None, tipo="totem", unidade_id=None) -> dict:
    r = client.post("/api/acesso/dispositivos", headers=full, json={"nome": f"{tipo} recepção", "tipo": tipo, "catraca_id": catraca_id,
                                                                   "unidade_id": unidade_id})
    assert r.status_code == 201, r.text
    return {"X-Dispositivo-Token": r.json()["token"], "_id": r.json()["id"]}


def h(totem: dict) -> dict:
    return {"X-Dispositivo-Token": totem["X-Dispositivo-Token"]}


def cadastrar_rosto(client, full, aluno_id: int, v: list[float]):
    r = client.post(f"/api/acesso/alunos/{aluno_id}/consentimento", headers=full, json={"aceite": True})
    assert r.status_code == 201, r.text
    r = client.post(f"/api/acesso/alunos/{aluno_id}/descritores", headers=full, json={"descritores": [v], "prova_vida": PROVA_VIDA})
    assert r.status_code == 201, r.text


__all__ = ["AGORA", "HOJE", "Aluno", "PROVA_VIDA", "cadastrar_rosto", "criar_totem", "h", "novo_contrato", "parcela", "ruido", "vetor"]
