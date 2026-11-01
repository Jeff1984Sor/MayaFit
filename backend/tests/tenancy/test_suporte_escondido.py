"""Decisão do Jefferson (31/10/2026): o usuário Suporte fica escondido do estúdio."""

from sqlalchemy import select

from app.core import tenancy
from app.core.db import SessionLocal
from app.core.models import Usuario
from tests.tenancy.conftest import HOST_ALFA, SENHA_SUPORTE, bearer, entrar


def test_suporte_fica_escondido_do_estudio(multi, client):
    """Decisão do Jefferson (31/10/2026): o Suporte não aparece na lista do estúdio nem pode ser mexido por ele."""
    from tests.tenancy.conftest import _usuario

    _usuario("alfa", "Full", "gerente")  # usuário próprio: outros testes bloqueiam a "ana" de propósito
    h = bearer(entrar(client, "gerente", host=HOST_ALFA))
    usuarios = client.get("/api/config/usuarios", headers=h).json()
    assert usuarios and all(not u["login"] or not u["login"].startswith("suporte.") for u in usuarios)
    with tenancy.usando(multi.por_slug("alfa")), SessionLocal() as db:
        sid = db.scalar(select(Usuario.id).where(Usuario.suporte.is_(True)))
    assert client.patch(f"/api/config/usuarios/{sid}", headers=h, json={"ativo": False}).status_code == 404
    # mas ele continua entrando (é a equipe MayaCorp que dá suporte)
    assert entrar(client, "suporte.alfa", senha=SENHA_SUPORTE, host=HOST_ALFA).status_code == 200
