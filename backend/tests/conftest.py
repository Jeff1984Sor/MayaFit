"""Fixtures do core. As variáveis de ambiente são definidas ANTES de importar o app (o engine é criado na importação)."""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="pilates-tests-"))
os.environ["AMBIENTE"] = "dev"
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(_TMP / "storage")
os.environ["MIGRAR_NA_SUBIDA"] = "false"
os.environ["WORKER_EMBUTIDO"] = "false"
# o .env do servidor (hml/prod) não pode vazar para os testes
os.environ["ALLOWED_HOSTS"] = '["localhost", "127.0.0.1", "testserver"]'
os.environ["CORS_ORIGINS"] = '["http://localhost:3000", "http://127.0.0.1:3000"]'
os.environ["FRONTEND_URL"] = "http://localhost:3000"
os.environ["DOMINIO_BASE"] = ""  # o subdomínio dos estúdios vem de cada teste, não do .env de produção

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import notificador as notif  # noqa: E402
from app.core import perfis, ratelimit  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.models import Usuario  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.main import app  # noqa: E402

SENHA = "Senha@Forte1"


@pytest.fixture(autouse=True)
def _banco_limpo():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    ratelimit.resetar()
    antigo = notif._atual
    yield
    notif.definir_notificador(antigo)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def zap():
    """Notificador falso (WhatsApp) que guarda o que seria enviado."""
    n = notif.NotificadorMemoria()
    notif.definir_notificador(n)
    return n


@pytest.fixture
def emails(monkeypatch):
    """Captura os e-mails enviados pelo core: lista de (para, assunto, corpo)."""
    enviados: list[tuple[list[str], str, str]] = []

    def falso(para, assunto, corpo, **_):
        enviados.append((para, assunto, corpo))
        return True

    monkeypatch.setattr("app.core.email.enviar", falso)
    return enviados


def criar_usuario(db, perfil: str = "Full", *, email="user@exemplo.com", login=None, senha=SENHA,
                  telefone=None, **extra) -> Usuario:
    p = perfis.garantir_padrao(db)[perfil]
    login = login or email.split("@")[0]  # ninguém entra com e-mail: todo usuário tem um login
    u = Usuario(nome=f"Usuário {perfil}", email=email, login=login, telefone=telefone, perfil_acesso_id=p.id,
                senha_hash=hash_senha(senha) if senha else None, **extra)
    db.add(u)
    db.commit()
    return u


def entrar(client, identificador, senha=SENHA):
    """Entra pelo LOGIN. Por conveniência dos testes, um "x@y" vira "x" (o login criado por `criar_usuario`);
    o teste `test_login_por_email_nao_funciona` prova que a API recusa o e-mail de verdade."""
    login = identificador.split("@")[0] if "@" in identificador else identificador
    return client.post("/api/auth/login", json={"identificador": login, "senha": senha})


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(db):
    return criar_usuario(db, "Full", email="admin@exemplo.com", login="admin")


@pytest.fixture
def token_admin(client, admin):
    return entrar(client, "admin@exemplo.com").json()["access_token"]
