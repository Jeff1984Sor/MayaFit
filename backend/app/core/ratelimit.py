"""Rate limit por chave (IP por padrão) com janela deslizante, para endpoints públicos.

    from app.core.ratelimit import limitar
    @router.post("/login", dependencies=[Depends(limitar("login", max_eventos=10, janela_s=60))])

Backend "memoria" (padrão; por processo) ou "banco" (RATE_LIMIT_BACKEND=banco; vale para vários processos).
Atrás do nginx o IP vem de X-Forwarded-For (o nginx deve SOBRESCREVER o cabeçalho; ver deploy/nginx).
"""

import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import agora, get_db
from app.core.models import RateLimitEvento


class LimiteMemoria:
    def __init__(self) -> None:
        self._eventos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def registrar(self, chave: str, max_eventos: int, janela_s: float, agora_s: float | None = None) -> float | None:
        """Registra a tentativa. Devolve None se passou, ou os segundos até liberar se estourou o limite."""
        t = time.monotonic() if agora_s is None else agora_s
        with self._lock:
            fila = self._eventos[chave]
            while fila and fila[0] <= t - janela_s:
                fila.popleft()
            if len(fila) >= max_eventos:
                return max(fila[0] + janela_s - t, 1.0)
            fila.append(t)
            return None

    def resetar(self) -> None:
        with self._lock:
            self._eventos.clear()


class LimiteBanco:
    def registrar(self, db: Session, chave: str, max_eventos: int, janela_s: float) -> float | None:
        corte = agora() - timedelta(seconds=janela_s)
        n, primeiro = db.execute(
            select(func.count(), func.min(RateLimitEvento.em)).where(RateLimitEvento.chave == chave, RateLimitEvento.em > corte)
        ).one()
        if n >= max_eventos:
            espera = (primeiro + timedelta(seconds=janela_s) - agora()).total_seconds() if primeiro else janela_s
            return max(espera, 1.0)
        db.add(RateLimitEvento(chave=chave))
        db.commit()
        return None

    @staticmethod
    def limpar_antigos(db: Session, mais_velhos_que_s: float = 3600) -> int:
        r = db.execute(delete(RateLimitEvento).where(RateLimitEvento.em < agora() - timedelta(seconds=mais_velhos_que_s)))
        db.commit()
        return r.rowcount or 0


memoria = LimiteMemoria()
banco = LimiteBanco()


def _ha_banco() -> bool:
    """Um banco por estúdio: antes de o estúdio ser identificado (login no endereço principal) não há banco onde
    contar; nesse caso o limite fica na memória do processo."""
    from app.core import tenancy

    return not tenancy.multi() or tenancy.atual() is not None


def ip_do_cliente(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip() if settings.ambiente != "dev" else fwd.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


def verificar(request: Request, nome: str, max_eventos: int, janela_s: float, chave: str | None = None,
              db: Session | None = None) -> None:
    """Levanta 429 se `chave` (padrão: IP) passou de `max_eventos` em `janela_s` segundos para o limite `nome`."""
    if not settings.rate_limit_ativo:
        return
    k = f"{nome}:{chave or ip_do_cliente(request)}"
    if settings.rate_limit_backend == "banco" and db is not None and _ha_banco():
        espera = banco.registrar(db, k, max_eventos, janela_s)
    else:
        espera = memoria.registrar(k, max_eventos, janela_s)
    if espera is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Aguarde um pouco e tente de novo.",
            headers={"Retry-After": str(int(espera) + 1)},
        )


def limitar(nome: str, max_eventos: int, janela_s: float):
    """Dependência FastAPI reutilizável: limita por IP."""

    def _dep(request: Request, db: Session = Depends(get_db)) -> None:
        verificar(request, nome, max_eventos, janela_s, db=db)

    return _dep


def resetar() -> None:
    """Para testes."""
    memoria.resetar()
