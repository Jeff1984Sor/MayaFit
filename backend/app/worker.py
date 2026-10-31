"""Worker de produção (systemd `mayafit-worker`): tarefas periódicas fora do ciclo das requisições.

Cada módulo registra suas tarefas com `registrar_tarefa` (ex.: lembretes de WhatsApp a cada 5 min, conclusão automática
de aulas passadas, alertas). Não há broker: o estado fica no banco. Rodar: `python -m app.worker`.
"""

import importlib
import logging
import pkgutil
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import app.modules as modulos_pkg
from app.core.db import SessionLocal
from app.core.ratelimit import LimiteBanco

log = logging.getLogger("worker")
_parar = threading.Event()


@dataclass
class Tarefa:
    nome: str
    intervalo_s: float
    fn: Callable[[], None]
    proxima: float = field(default=0.0)


TAREFAS: list[Tarefa] = []


def registrar_tarefa(nome: str, intervalo_s: float, fn: Callable[[], None]) -> None:
    TAREFAS.append(Tarefa(nome, intervalo_s, fn))


def _limpar_rate_limit() -> None:
    with SessionLocal() as db:
        LimiteBanco.limpar_antigos(db)


registrar_tarefa("limpar-rate-limit", 3600, _limpar_rate_limit)


def _descobrir_tarefas() -> None:
    """Módulos podem expor `app/modules/<nome>/tarefas.py` que chama `registrar_tarefa` ao ser importado."""
    for info in pkgutil.iter_modules(modulos_pkg.__path__):
        try:
            importlib.import_module(f"app.modules.{info.name}.tarefas")
        except ModuleNotFoundError as e:
            if e.name != f"app.modules.{info.name}.tarefas":
                raise


def executar_pendentes(agora_s: float | None = None) -> list[str]:
    """Roda as tarefas vencidas; uma falha não derruba as demais. Devolve os nomes executados (testável)."""
    t = time.monotonic() if agora_s is None else agora_s
    feitas = []
    for tarefa in TAREFAS:
        if t < tarefa.proxima:
            continue
        tarefa.proxima = t + tarefa.intervalo_s
        try:
            tarefa.fn()
            feitas.append(tarefa.nome)
        except Exception:
            log.exception("Tarefa '%s' falhou", tarefa.nome)
    return feitas


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    signal.signal(signal.SIGTERM, lambda *_: _parar.set())
    signal.signal(signal.SIGINT, lambda *_: _parar.set())
    _descobrir_tarefas()
    log.info("Worker iniciado com %d tarefa(s)", len(TAREFAS))
    while not _parar.is_set():
        executar_pendentes()
        _parar.wait(5)
    log.info("Worker encerrado")


if __name__ == "__main__":
    main()
