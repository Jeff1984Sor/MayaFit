"""Tarefa periódica do worker: publica a grade no Wellhub (por unidade, só se ativa e com `sync_ativo`; DESLIGADA por padrão)."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.wellhub import grade
from app.modules.wellhub.cliente import ErroWellhub
from app.modules.wellhub.models import WellhubConfig
from app.worker import registrar_tarefa

log = logging.getLogger(__name__)
INTERVALO_S = 30 * 60


def publicar_agendado() -> int:
    """Publica a grade de cada unidade com a publicação automática ligada. Devolve quantas rodaram."""
    rodou = 0
    with SessionLocal() as db:
        ids = list(db.scalars(select(WellhubConfig.id).where(WellhubConfig.ativo.is_(True), WellhubConfig.sync_ativo.is_(True))))
        for cid in ids:
            cfg = db.get(WellhubConfig, cid)
            if cfg is None:
                continue
            try:
                resumo = grade.sincronizar_grade(db, cfg)
                grade.registrar_sync(db, cfg, grade.resumo_texto(resumo), resumo["erros"] == 0)
            except ErroWellhub as e:
                db.rollback()
                grade.registrar_sync(db, cfg, f"Erro: {e}", False)
            except Exception:  # noqa: BLE001 - uma unidade com problema não derruba as outras
                db.rollback()
                log.exception("Publicação da grade no Wellhub falhou (config %s)", cid)
                grade.registrar_sync(db, cfg, "Erro inesperado na publicação da grade.", False)
            rodou += 1
    return rodou


registrar_tarefa("wellhub-publicar-grade", INTERVALO_S, lambda: publicar_agendado() and None)
