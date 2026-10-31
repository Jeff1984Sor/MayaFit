"""E-mails da MayaCorp aos estúdios (boas-vindas, convites, contratos, cobranças, cadastros).

Porte de `service.enviar_email` do MayaJus: saem pelo SMTP configurado no banco do estúdio MayaCorp
(Configurações › E-mail = `ConfigEmail`), com o nome e a logo da `Identidade` dele, no modelo HTML de
`email_modelo`. Sem o estúdio MayaCorp (modo de um banco só, dev e testes), saem pelo SMTP do banco atual / `.env`.
"""

import inspect
import logging
import mimetypes
from contextlib import nullcontext

from sqlalchemy import select

log = logging.getLogger(__name__)


def _estudio_mayacorp():
    try:
        from app.controle import service

        return service.estudio_mayacorp()
    except Exception:  # sem fundação multi-tenant ou sem banco de controle: banco atual
        return None


def _usando(est):
    if est is None:
        return nullcontext()
    try:
        from app.core import tenancy
    except ImportError:
        return nullcontext()
    return tenancy.usando(est)


def enviar_email(para: list[str], assunto: str, corpo: str,
                 anexos: list[tuple[str, bytes, str]] | None = None) -> bool:
    """Devolve True quando a mensagem foi entregue ao SMTP (ou ao outbox em dev)."""
    from app.controle.email_modelo import corpo_html
    from app.core import email as mail
    from app.core import storage
    from app.core.db import SessionLocal
    from app.core.models import Identidade

    para = [p for p in dict.fromkeys(para) if p]
    if not para:
        return False
    with _usando(_estudio_mayacorp()), SessionLocal() as s:
        extras: dict = {"db": s, "anexos": anexos}
        aceita = inspect.signature(mail.enviar).parameters
        if "html" in aceita:  # o core ainda envia só texto; quando aceitar HTML, o modelo com a marca vai junto
            ident = s.scalar(select(Identidade).limit(1))
            imagens = {}
            if ident and ident.logo_path and storage.existe(ident.logo_path):
                caminho = storage.resolver(ident.logo_path)
                imagens["logo-mayacorp"] = (caminho.read_bytes(), mimetypes.guess_type(caminho.name)[0] or "image/png")
            extras["html"] = corpo_html(corpo, titulo=assunto, marca="MayaFit",
                                        logo_cid="logo-mayacorp" if imagens else None)
            if "imagens" in aceita:
                extras["imagens"] = imagens
        ok = mail.enviar(para, assunto, corpo, **extras)
    if not ok:
        log.warning("E-mail '%s' não foi enviado (SMTP do admin MayaCorp)", assunto)
    return ok
