"""Um banco por estúdio, em SQLite: um controle próprio (tenancy.forcar_controle) e dois estúdios provisionados.

Tudo fica isolado: ao sair, o controle volta a ser detectado (não existe nos testes → um banco só), os engines dos
estúdios são fechados e o cache é limpo; os outros testes do projeto continuam no modo de sempre.

Estúdios (ambos com a senha SENHA):
- alfa  (alfa.mayafit.test): logins "ana" (Full) e "carlos" (Professor)
- beta  (beta.mayafit.test): logins "ana" (Full) e "bia" (Secretária)
"ana" existe nos dois: no endereço principal o login é ambíguo.
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.core import tenancy
from tests.conftest import SENHA

HOST_ALFA = "alfa.mayafit.test"
HOST_BETA = "beta.mayafit.test"
SENHA_SUPORTE = "Suporte#Teste1"


def _apagar_bancos(*slugs: str) -> None:
    from app.controle import service

    tenancy.descartar_engines()
    for slug in slugs:
        url = tenancy.url_do_banco(service.nome_do_banco(slug)).removeprefix("sqlite:///")
        for sufixo in ("", "-wal", "-shm"):
            Path(url + sufixo).unlink(missing_ok=True)


@contextmanager
def controle_proprio():
    """Liga o modo multi com um banco de controle novo (e desliga ao sair)."""
    from app.controle import models, service

    pasta = Path(tempfile.mkdtemp(prefix="mayafit-controle-"))
    tenancy.forcar_controle(f"sqlite:///{(pasta / 'controle.db').as_posix()}")
    models.reiniciar_engine()
    service.limpar_cache()
    try:
        service.migrar_controle()
        yield
    finally:
        tenancy.forcar_controle(None)
        models.reiniciar_engine()
        service.limpar_cache()
        tenancy.descartar_engines()


def _usuario(slug: str, perfil: str, login: str) -> None:
    from app.controle import service
    from app.core import perfis
    from app.core.db import SessionLocal
    from app.core.models import Usuario
    from app.core.security import hash_senha

    with tenancy.usando(service.por_slug(slug)), SessionLocal() as db:
        p = perfis.garantir_padrao(db)[perfil]
        db.add(Usuario(nome=f"{login.title()} {slug}", email=f"{login}@{slug}.com", login=login,
                       perfil_acesso_id=p.id, senha_hash=hash_senha(SENHA)))
        db.commit()


@pytest.fixture(scope="module")
def multi():
    """Controle + estúdios alfa e beta (provisionados de verdade: banco, migrations, Suporte, admin)."""
    import app.controle.sincronia  # noqa: F401
    from app.controle import service
    from app.controle.models import PoliticaComercial, SessaoControle
    from app.core.security import hash_senha

    _apagar_bancos("alfa", "beta", "gama")
    with controle_proprio():
        with SessaoControle() as db:
            db.add(PoliticaComercial(id=1, senha_suporte_hash=hash_senha(SENHA_SUPORTE)))
            db.commit()
        service.provisionar("alfa", "Studio Alfa", admin_email="ana@alfa.com", admin_nome="Ana Alfa",
                            admin_login="ana", admin_senha=SENHA, dominios=[HOST_ALFA])
        service.provisionar("beta", "Studio Beta", admin_email="ana@beta.com", admin_nome="Ana Beta",
                            admin_login="ana", admin_senha=SENHA, dominios=[HOST_BETA], dias_teste=15)
        _usuario("alfa", "Professor", "carlos")
        _usuario("beta", "Secretária", "bia")
        yield service
    _apagar_bancos("alfa", "beta", "gama")


def entrar(client, login, senha=SENHA, host=None):
    headers = {"X-Forwarded-Host": host} if host else {}
    return client.post("/api/auth/login", json={"identificador": login, "senha": senha}, headers=headers)


def bearer(r) -> dict:
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
