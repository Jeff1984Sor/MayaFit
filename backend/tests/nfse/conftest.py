"""Fixtures da NFS-e: cenário mínimo (unidade, alunos, recebimentos pagos), usuários por perfil e simuladores zerados.

Nada aqui vai à rede: os provedores rodam no modo simulado ou com transporte falso.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules import registrar_modelos
from tests.conftest import auth, criar_usuario, entrar

registrar_modelos()

from app.modules.alunos.models import Aluno  # noqa: E402
from app.modules.cadastros.models import Unidade  # noqa: E402
from app.modules.financeiro.models import ContaReceber, StatusReceber  # noqa: E402
from app.modules.nfse import servico  # noqa: E402
from app.modules.nfse.models import ConfigNfse, Modo, Provedor  # noqa: E402
from app.modules.nfse.provedores.nacional import simulador as sim_nacional  # noqa: E402
from app.modules.nfse.provedores.sao_paulo import simulador as sim_sp  # noqa: E402

CNPJ = "11222333000181"


def cpf_valido(base: int) -> str:
    d = [int(c) for c in f"{base:09d}"]
    for _ in range(2):
        s = sum(v * w for v, w in zip(d, range(len(d) + 1, 1, -1), strict=False))
        d.append((s * 10 % 11) % 10)
    return "".join(map(str, d))


@pytest.fixture(autouse=True)
def _simuladores_limpos():
    sim_nacional.resetar()
    sim_sp.resetar()
    servico.definir_transporte(None)
    yield
    servico.definir_transporte(None)


def configurar(db, **extra) -> ConfigNfse:
    cfg = servico.obter_config(db)
    valores = dict(ativo=True, provedor=Provedor.nacional, modo=Modo.simulado, cnpj=CNPJ, razao_social="Estudio Teste Ltda",
                   inscricao_municipal="123456", codigo_municipio="3509502", municipio_nome="Campinas", uf="SP",
                   regime="simples", item_lista_servico="06.04", codigo_tributacao_nacional="060401",
                   aliquota_iss=Decimal("2.00"), percentual_tributos_sn=Decimal("6.00"), enviar_email_aluno=True)
    valores.update(extra)
    for k, v in valores.items():
        setattr(cfg, k, v)
    db.commit()
    return cfg


@pytest.fixture
def cenario(db) -> SimpleNamespace:
    un = Unidade(nome="Matriz", capacidade=4)
    db.add(un)
    db.flush()
    maria = Aluno(nome="Maria Souza", cpf=cpf_valido(100000001), unidade_id=un.id, email="maria@exemplo.com")
    joao = Aluno(nome="João Lima", cpf=cpf_valido(100000002), unidade_id=un.id)
    sem_cpf = Aluno(nome="Sem Documento", cpf=None, sem_cpf=True, unidade_id=un.id)
    db.add_all([maria, joao, sem_cpf])
    db.flush()
    hoje = servico.hoje()

    def conta(aluno, valor, pago=True, desc="Pilates 2x"):
        c = ContaReceber(aluno_id=aluno.id, descricao=desc, valor=Decimal(valor), vencimento=hoje,
                         competencia=f"{hoje:%Y-%m}", status=StatusReceber.PAGO if pago else StatusReceber.ABERTO,
                         pagamento=hoje if pago else None)
        db.add(c)
        db.flush()
        return c

    r1 = conta(maria, "300.00")
    r2 = conta(joao, "450.50")
    r3 = conta(sem_cpf, "200.00")
    aberto = conta(maria, "300.00", pago=False)
    db.commit()
    return SimpleNamespace(unidade=un, maria=maria, joao=joao, sem_cpf=sem_cpf, r1=r1, r2=r2, r3=r3, aberto=aberto,
                           hoje=hoje)


def _tk(client, db, perfil, email):
    criar_usuario(db, perfil, email=email)
    return entrar(client, email).json()["access_token"]


@pytest.fixture
def adm(client, db):
    return auth(_tk(client, db, "Full", "adm@x.com"))


@pytest.fixture
def secretaria(client, db):
    return auth(_tk(client, db, "Secretária", "sec@x.com"))


@pytest.fixture
def professor(client, db):
    return auth(_tk(client, db, "Professor", "prof@x.com"))


@pytest.fixture
def hoje() -> date:
    return servico.hoje()
