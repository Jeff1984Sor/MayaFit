"""Dependências FastAPI: sessão, usuário logado e controle de permissão (aplicado no backend, negar por padrão)."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import audit, escopo, tenancy
from app.core.db import agora, get_db
from app.core.models import Usuario
from app.core.permissoes import permissao_da_rota
from app.core.ratelimit import ip_do_cliente
from app.core.security import decodificar_token

log = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


@dataclass
class Contexto:
    db: Session
    usuario: Usuario
    ip: str | None
    permissao: str | None = None  # permissão que a rota exigiu (None = livre para logados)

    def pode(self, permissao: str) -> bool:
        return self.usuario.pode(permissao)

    def exigir(self, permissao: str) -> None:
        """Checagem extra dentro da rota (além da exigida pelo mapa)."""
        if not self.pode(permissao):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Seu perfil de acesso não permite esta ação.")

    # --- escopo "somente as próprias aulas" (perfil Professor); ver app.core.escopo ---
    def somente_proprias_aulas(self) -> bool:
        return escopo.usuario_restrito(self.usuario)

    def profissional_id(self) -> int | None:
        return escopo.resolver_profissional_id(self.db, self.usuario)

    def auditar(self, acao: str, entidade: str, entidade_id=None, descricao=None, antes=None, depois=None):
        audit.registrar(
            self.db,
            usuario=self.usuario,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            descricao=descricao,
            antes=antes,
            depois=depois,
            ip=self.ip,
        )


def ip_cliente(request: Request) -> str | None:
    return ip_do_cliente(request)


def usuario_do_token(db: Session, token: str) -> Usuario:
    """Valida um access token (assinatura, expiração, usuário ativo e token_version). Levanta 401."""
    try:
        payload = decodificar_token(token, "access")
        uid = int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada. Entre novamente.") from None
    if not tenancy.token_do_estudio_atual(payload):  # um banco por estúdio: o token só vale no estúdio que o emitiu
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada. Entre novamente.")
    usuario = db.get(Usuario, uid)
    if not usuario or not usuario.ativo or not usuario.acesso_sistema:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada. Entre novamente.")
    if payload.get("tv") != usuario.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada. Entre novamente.")
    return usuario


def get_contexto(
    request: Request, db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Contexto:
    if not cred:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login para continuar.")
    usuario = usuario_do_token(db, cred.credentials)
    now = agora()
    ultima = usuario.ultima_atividade
    if ultima is None or (now - ultima) > timedelta(minutes=1):
        usuario.ultima_atividade = now
        db.commit()
    mapeada, permissao = permissao_da_rota(request.method, request.url.path)
    if not mapeada:
        # NEGAR POR PADRÃO: rota sem regra em app.core.permissoes não é acessível a ninguém.
        log.warning("Rota sem mapa de permissão: %s %s", request.method, request.url.path)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta rota não tem permissão configurada.")
    if permissao and not usuario.pode(permissao):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seu perfil de acesso não permite esta ação.")
    return Contexto(db=db, usuario=usuario, ip=ip_cliente(request), permissao=permissao)


Ctx = Annotated[Contexto, Depends(get_contexto)]
