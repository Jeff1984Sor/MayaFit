"""Tarefas periódicas da NFS-e (descobertas pelo `app.worker`).

- `nfse-fila` (60 s): destrava notas presas em "processando" e envia as pendentes vencidas (com retentativa).
- `nfse-automatica` (5 min): recebimentos pagos viram nota sozinhos, se a emissão automática estiver ligada.
- `nfse-certificado` (1 dia): registra no log o certificado vencendo/vencido (o painel mostra o alerta).
"""

import logging

from app.core.db import SessionLocal
from app.modules.nfse import regras, servico
from app.modules.nfse.models import ConfigNfse
from app.worker import registrar_tarefa

log = logging.getLogger(__name__)


def fila() -> None:
    with SessionLocal() as db:
        servico.destravar_processando(db)
        servico.processar_fila(db)


def automatica() -> None:
    with SessionLocal() as db:
        n = servico.emitir_automaticas(db)
        if n:
            log.info("NFS-e automática: %s recebimento(s) na fila", n)
            servico.processar_fila(db)


def certificado() -> None:
    with SessionLocal() as db:
        cfg = db.get(ConfigNfse, 1)
        if cfg and cfg.ativo and cfg.certificado_valido_ate:
            s = regras.situacao_certificado(cfg.certificado_valido_ate, servico.hoje())
            if s["situacao"] in ("vencendo", "vencido"):
                log.warning("NFS-e: %s", s["mensagem"])


registrar_tarefa("nfse-fila", 60, fila)
registrar_tarefa("nfse-automatica", 300, automatica)
registrar_tarefa("nfse-certificado", 86400, certificado)
