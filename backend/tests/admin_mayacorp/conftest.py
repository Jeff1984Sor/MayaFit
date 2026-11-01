"""Fixtures do admin MayaFit.

O banco de controle vive num SQLite temporário (engine próprio apontado em `app.controle.models`) e a fundação
multi-tenant é simulada: `ponte.atual/multi` dizem em qual estúdio a requisição está e o `app.controle.service`
(provisionar, domínios, uso...) é trocado por versões falsas. No modo de um banco só, "abrir o banco do estúdio" cai
no banco de testes de sempre — os usuários do estúdio são os usuários do teste.
"""

import re
import sys
import types
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.controle import models as cm
from app.controle import ponte
from app.controle.models import BaseControle, Cliente, Dominio
from tests.conftest import SENHA, auth, criar_usuario, entrar  # noqa: F401

MAYACORP = SimpleNamespace(slug="mayacorp", banco=None, mayacorp=True)


class RegraControle(ValueError):
    pass


def _modulo_service():
    """O `app.controle.service` real (quando a fundação existir) ou um módulo vazio no lugar dele."""
    try:
        from app.controle import service
    except ImportError:
        import app.controle as pacote

        service = types.ModuleType("app.controle.service")
        sys.modules["app.controle.service"] = service
        pacote.service = service
    return service


class Fundacao:
    """Estado da fundação falsa: estúdio atual, fotos de uso coletadas e quem foi provisionado."""

    def __init__(self):
        self.atual = MAYACORP
        self.multi = True
        self.uso: dict[str, dict] = {}
        self.provisionados: list[dict] = []

    def entrar_no(self, slug: str | None) -> None:
        self.atual = MAYACORP if slug is None else SimpleNamespace(slug=slug, banco=f"mayafit_{slug}", mayacorp=False)


@pytest.fixture
def fundacao(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'controle.db').as_posix()}",
                           connect_args={"check_same_thread": False})
    BaseControle.metadata.create_all(engine)
    monkeypatch.setattr(cm, "_engine", engine)
    monkeypatch.setattr(cm, "_fabrica", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))

    f = Fundacao()
    monkeypatch.setattr(ponte, "atual", lambda: f.atual)
    monkeypatch.setattr(ponte, "multi", lambda: f.multi)
    # com a fundação de verdade no código, "abrir o banco do estúdio" apontaria para um arquivo que não existe:
    # aqui todo estúdio usa o banco do teste (banco=None = o principal)
    from app.core import tenancy

    monkeypatch.setattr(ponte, "estudio_de",
                        lambda c: tenancy.Estudio(slug=c.slug, banco=None, mayacorp=c.tipo == "mayacorp"))

    def provisionar(slug, nome, *, admin_email, admin_nome="", dias_teste=None, dominios=None, tipo="estudio",
                    admin_login=None, admin_senha=None, primeiro_acesso=False, **ficha):
        if not re.match(r"^[a-z][a-z0-9-]{1,38}$", slug):
            raise RegraControle("Identificador: letras minúsculas, números e hífen (2 a 39), começando com letra.")
        with cm.SessaoControle() as db:
            if db.scalar(select(Cliente.id).where(Cliente.slug == slug)):
                raise RegraControle(f"Já existe o estúdio {slug}.")
            c = Cliente(slug=slug, nome=nome, banco=f"mayafit_{slug}", tipo=tipo,
                        status="teste" if dias_teste else "ativo",
                        teste_ate=date.today() + timedelta(days=dias_teste) if dias_teste else None, **ficha)
            for host in [f"{slug}.mayafit.test", *(dominios or [])]:
                c.dominios.append(Dominio(host=host))
            db.add(c)
            db.commit()
        f.provisionados.append({"slug": slug, "admin_email": admin_email, "dias_teste": dias_teste,
                                "primeiro_acesso": primeiro_acesso, "ficha": ficha})
        return c, f"http://localhost:3000/primeiro-acesso?token=tk-{slug}"

    def adicionar_dominio(db, cliente, host):
        host = host.strip().lower()
        if db.scalar(select(Dominio.id).where(Dominio.host == host)):
            raise RegraControle(f"O endereço {host} já é usado.")
        d = Dominio(host=host)
        cliente.dominios.append(d)
        db.flush()
        return d

    service = _modulo_service()
    falsos = {
        "RegraControle": RegraControle,
        "provisionar": provisionar,
        "adicionar_dominio": adicionar_dominio,
        "dominio_padrao": lambda slug: f"{slug}.mayafit.test",
        "limpar_cache": lambda: None,
        "coletar_uso": lambda est: f.uso.get(est.slug, {}),
        "estudio_mayacorp": lambda: MAYACORP,  # sem tenancy, "abrir o banco dele" = banco de testes
        "endereco_do_painel": lambda: "admin.mayafit.test",
        "link_primeiro_acesso": lambda slug, email: f"http://localhost:3000/primeiro-acesso?token=novo-{slug}",
    }
    for nome, fn in falsos.items():
        monkeypatch.setattr(service, nome, fn, raising=False)

    with cm.SessaoControle() as db:
        db.add(Cliente(slug="mayacorp", nome="Admin MayaFit", banco="mayafit_mayacorp", tipo="mayacorp"))
        db.commit()
    yield f
    engine.dispose()


@pytest.fixture
def adm(client, db, fundacao):
    """Cabeçalho de um administrador (perfil Full) logado no admin MayaFit."""
    criar_usuario(db, "Full", email="jeff@mayacorp.com.br", login="jeff")
    return auth(entrar(client, "jeff").json()["access_token"])


@pytest.fixture
def emails_admin(monkeypatch):
    """E-mails que o admin mandou: lista de (para, assunto, corpo, anexos)."""
    enviados: list[tuple] = []

    def falso(para, assunto, corpo, anexos=None):
        enviados.append((para, assunto, corpo, anexos))
        return True

    monkeypatch.setattr("app.controle.emails.enviar_email", falso)
    return enviados


def criar_estudio(client, adm, **extra) -> dict:
    corpo = {"nome": "Pilates Lumina", "documento": "12.345.678/0001-95", "responsavel": "Ana Lima",
             "email_financeiro": "fin@lumina.com.br", "admin_nome": "Ana Lima", "admin_email": "ana@lumina.com.br",
             **extra}
    r = client.post("/api/admin/clientes", headers=adm, json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def plano(client, adm, nome: str) -> dict:
    return next(p for p in client.get("/api/admin/planos", headers=adm).json() if p["nome"] == nome)
