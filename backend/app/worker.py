"""Worker de produção (systemd `mayafit-worker`): tarefas periódicas fora do ciclo das requisições.

Cada módulo registra suas tarefas com `registrar_tarefa` (ex.: lembretes de WhatsApp a cada 5 min, conclusão automática
de aulas passadas, alertas). Não há broker: o estado fica no banco. Rodar: `python -m app.worker`.

Um banco por estúdio (app.core.tenancy): cada tarefa roda uma vez para CADA estúdio ativo, dentro de
`tenancy.usando(estudio)` (a lista é relida a cada volta; cada estúdio tem o seu relógio). Tarefas do banco de controle
(`global_=True`) rodam uma vez só, sem estúdio. Com um banco só, tudo roda como sempre.
"""

import importlib
import logging
import pkgutil
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import app.controle.sincronia  # noqa: F401  (catálogo de logins do controle)
import app.modules as modulos_pkg
from app.core import tenancy
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
    global_: bool = False  # True = tarefa do banco de controle: uma vez só, sem estúdio
    proximas: dict[str, float] = field(default_factory=dict)  # um banco por estúdio: o relógio de cada estúdio


TAREFAS: list[Tarefa] = []


def registrar_tarefa(nome: str, intervalo_s: float, fn: Callable[[], None], *, global_: bool = False) -> None:
    TAREFAS.append(Tarefa(nome, intervalo_s, fn, global_=global_))


def _limpar_rate_limit() -> None:
    with SessionLocal() as db:
        LimiteBanco.limpar_antigos(db)


registrar_tarefa("limpar-rate-limit", 3600, _limpar_rate_limit)


def _gravar_uso() -> None:
    """Foto do uso de cada estúdio no controle (Cliente.uso), para o admin e a cobrança."""
    if tenancy.multi():
        from app.controle import service

        service.gravar_uso_todos()


registrar_tarefa("controle-uso-dos-estudios", 3600, _gravar_uso, global_=True)


def _descobrir_tarefas() -> None:
    """Módulos podem expor `app/modules/<nome>/tarefas.py` que chama `registrar_tarefa` ao ser importado."""
    for info in pkgutil.iter_modules(modulos_pkg.__path__):
        try:
            importlib.import_module(f"app.modules.{info.name}.tarefas")
        except ModuleNotFoundError as e:
            if e.name != f"app.modules.{info.name}.tarefas":
                raise


def _estudios() -> list:
    """Os estúdios ativos do controle (relidos a cada volta)."""
    from app.controle import service

    return service.ativos()


def _rodar(tarefa: Tarefa, rotulo: str, feitas: list[str]) -> None:
    try:
        tarefa.fn()
        feitas.append(rotulo)
    except Exception:
        log.exception("Tarefa '%s' falhou", rotulo)


def executar_pendentes(agora_s: float | None = None) -> list[str]:
    """Roda as tarefas vencidas; uma falha não derruba as demais. Devolve os nomes executados (testável); no modo um
    banco por estúdio, as tarefas por estúdio aparecem como "nome@slug"."""
    t = time.monotonic() if agora_s is None else agora_s
    feitas: list[str] = []
    multi = tenancy.multi()
    estudios = _estudios() if multi else []
    for tarefa in TAREFAS:
        if tarefa.global_ or not multi:
            if t < tarefa.proxima:
                continue
            tarefa.proxima = t + tarefa.intervalo_s
            with tenancy.usando(None):
                _rodar(tarefa, tarefa.nome, feitas)
            continue
        for esc in estudios:
            if t < tarefa.proximas.get(esc.slug, 0.0):
                continue
            tarefa.proximas[esc.slug] = t + tarefa.intervalo_s
            with tenancy.usando(esc):
                _rodar(tarefa, f"{tarefa.nome}@{esc.slug}", feitas)
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
