"""Tarefas periódicas do controle de acesso (worker)."""

import logging

from app.core import audit
from app.core.db import SessionLocal
from app.modules.acesso import servico
from app.worker import registrar_tarefa

log = logging.getLogger("acesso.tarefas")

INTERVALO_LGPD_S = 6 * 3600


def apagar_biometria_de_inativos() -> int:
    """LGPD: biometria de aluno inativo é apagada (o termo promete). Idempotente."""
    with SessionLocal() as db:
        try:
            n = servico.apagar_biometria_de_inativos(db)
            if n:
                audit.registrar(db, usuario=None, acao="apagar_biometria", entidade="aluno",
                                descricao=f"Biometria de {n} aluno(s) inativo(s) apagada automaticamente (LGPD)")
            db.commit()
        except Exception:
            db.rollback()
            raise
    if n:
        log.info("LGPD: biometria de %d aluno(s) inativo(s) apagada", n)
    return n


registrar_tarefa("acesso-apagar-biometria-inativos", INTERVALO_LGPD_S, apagar_biometria_de_inativos)
