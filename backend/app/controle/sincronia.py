"""Mantém o catálogo de logins do controle em dia: usuário criado, alterado (login, ativo, acesso) ou excluído no banco
de um estúdio é refletido no controle depois do commit. Só a chave LOGIN vai para o catálogo (ninguém entra com
e-mail). Importado pela API, pelo worker e pelo terminal. Portado do MayaJus (app/controle/sincronia.py).
"""

from sqlalchemy import event, inspect

from app.core import tenancy
from app.core.db import SessaoDoEstudio
from app.core.models import Usuario

_CHAVE = "catalogo_logins"
_CAMPOS = ("login", "ativo", "acesso_sistema")


@event.listens_for(SessaoDoEstudio, "after_flush")
def _anotar(session, _ctx) -> None:
    if not tenancy.multi() or tenancy.atual() is None:
        return
    from app.controle.service import chave_do_usuario

    pendentes = session.info.setdefault(_CHAVE, {})
    for obj in session.new | session.dirty:
        if not isinstance(obj, Usuario):
            continue
        estado = inspect(obj)
        if obj in session.new or any(estado.attrs[c].history.has_changes() for c in _CAMPOS):
            pendentes[obj.id] = chave_do_usuario(obj)
    for obj in session.deleted:
        if isinstance(obj, Usuario):
            pendentes[obj.id] = None


@event.listens_for(SessaoDoEstudio, "after_commit")
def _gravar(session) -> None:
    pendentes = session.info.pop(_CHAVE, None)
    esc = tenancy.atual()
    if not pendentes or esc is None:
        return
    from app.controle import service

    for uid, chave in pendentes.items():
        service.sincronizar_usuario(esc.slug, uid, chave)


@event.listens_for(SessaoDoEstudio, "after_rollback")
def _descartar(session) -> None:
    session.info.pop(_CHAVE, None)
