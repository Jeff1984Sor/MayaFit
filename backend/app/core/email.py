"""Envio de e-mail. SMTP vem da tela Configurações › E-mail (senha cifrada) ou, na falta, do .env.

Sem SMTP em dev, grava a mensagem em storage/outbox (.eml). Sem SMTP em hml/prod, registra erro e devolve False.
Nunca registra o corpo da mensagem no log (pode conter link de redefinição de senha).
"""

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core import segredos, storage
from app.core.config import settings
from app.core.db import agora
from app.core.models import ConfigEmail

log = logging.getLogger(__name__)


def enviar(
    para: list[str],
    assunto: str,
    corpo: str,
    *,
    db: Session | None = None,
    anexos: list[tuple[str, bytes, str]] | None = None,
    cc: list[str] | None = None,
    cco: list[str] | None = None,
    html: str | None = None,
    imagens: dict[str, tuple[bytes, str]] | None = None,
) -> bool:
    """Devolve True se a mensagem foi entregue ao SMTP (ou gravada no outbox em dev).

    `html`: versão HTML (multipart/alternative; `corpo` fica como texto puro). `imagens`: {cid: (bytes, mime)} embutidas
    no HTML (`<img src="cid:logo">`), em multipart/related."""
    config = db.get(ConfigEmail, 1) if db is not None else None
    msg = EmailMessage()
    if config:
        msg["From"] = f"{config.remetente_nome} <{config.remetente_email}>"
    else:
        msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(para)
    if cc:
        msg["Cc"] = ", ".join(cc)
    todos = list(dict.fromkeys([*para, *(cc or []), *(cco or [])]))  # Cco só entra na lista de entrega
    msg["Subject"] = assunto
    msg.set_content(corpo)
    if html:
        msg.add_alternative(html, subtype="html")
        if imagens:
            parte_html = msg.get_payload()[-1]
            for cid, (dados, mime) in imagens.items():
                maintype, subtype = mime.split("/", 1)
                parte_html.add_related(dados, maintype=maintype, subtype=subtype, cid=f"<{cid}>")
    for nome, dados, mime in anexos or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(dados, maintype=maintype, subtype=subtype, filename=nome)

    host = (config and config.smtp_host) or settings.smtp_host
    if not host:
        if settings.ambiente != "dev":
            log.error("SMTP não configurado: e-mail '%s' não enviado.", assunto)
            return False
        outbox = storage.raiz() / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        arq = outbox / f"{agora():%Y%m%d-%H%M%S-%f}.eml"
        arq.write_bytes(bytes(msg))
        log.info("E-mail gravado em %s (SMTP não configurado)", arq.name)
        return True

    porta = config.smtp_porta if config and config.smtp_host else settings.smtp_port
    usuario = (config and config.smtp_usuario) or settings.smtp_user
    senha = settings.smtp_password
    if config and config.smtp_senha_cifrada:
        senha = segredos.decifrar_texto(config.smtp_senha_cifrada)
    try:
        # 465 = SSL direto; outras portas = STARTTLS
        conexao = smtplib.SMTP_SSL(host, porta, timeout=30) if porta == 465 else smtplib.SMTP(host, porta, timeout=30)
        with conexao as s:
            if porta != 465:
                s.starttls()
            if usuario and senha:
                s.login(usuario, senha)
            s.send_message(msg, to_addrs=todos)
    except (smtplib.SMTPException, OSError) as e:
        log.error("Falha ao enviar e-mail '%s': %s", assunto, type(e).__name__)
        return False
    return True
