"""Tokens de API dos integradores externos (empresas/chatbots que chamam `/api/integracao/*`).

- Formato do valor: `mayafit_` + texto aleatório URL-safe (32 bytes). O valor completo existe só na resposta de
  criar/regenerar; o banco guarda o SHA-256 (`token_hash`) e os 4 últimos caracteres (`token_final`).
- Token migrado do sistema antigo vem SEM valor (`token_hash` nulo e `precisa_regenerar`): não autentica até regenerar.
- Autenticar = procurar pelo hash entre os tokens ATIVOS. Token desativado ou inexistente dão a mesma resposta (401).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import agora
from app.modules.cadastros.models import IntegracaoToken

PREFIXO = "mayafit_"
#: o "último uso" só é regravado se o anterior tiver mais que isto (evita uma escrita por requisição)
INTERVALO_ULTIMO_USO = timedelta(seconds=30)


def gerar_valor() -> str:
    return PREFIXO + secrets.token_urlsafe(32)


def hash_token(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def _aplicar_valor(t: IntegracaoToken, valor: str) -> None:
    t.token_hash = hash_token(valor)
    t.token_final = valor[-4:]
    t.precisa_regenerar = False


def criar(db: Session, nome: str) -> tuple[IntegracaoToken, str]:
    """Cria o token (ativo). Devolve `(token, valor_completo)`: o valor NÃO é recuperável depois."""
    valor = gerar_valor()
    t = IntegracaoToken(nome=nome.strip(), ativo=True)
    _aplicar_valor(t, valor)
    db.add(t)
    db.flush()
    return t, valor


def regenerar(db: Session, t: IntegracaoToken) -> str:
    """Troca o valor (o antigo para de valer na hora). Mantém nome e situação (ativo/inativo)."""
    valor = gerar_valor()
    _aplicar_valor(t, valor)
    t.ultimo_uso = None
    db.flush()
    return valor


def autenticar(db: Session, valor: str | None) -> IntegracaoToken | None:
    """Token ATIVO que corresponde ao valor, ou None. Marca o último uso."""
    if not valor:
        return None
    h = hash_token(valor)
    t = db.scalar(select(IntegracaoToken).where(IntegracaoToken.token_hash == h, IntegracaoToken.ativo.is_(True)))
    # confere em tempo constante também (defesa em profundidade; a busca já foi por hash)
    if t is None or not t.token_hash or not hmac.compare_digest(t.token_hash, h):
        return None
    agora_ = agora()
    if t.ultimo_uso is None or agora_ - t.ultimo_uso >= INTERVALO_ULTIMO_USO:
        t.ultimo_uso = agora_
        db.commit()
    return t


def valor_do_pedido(x_api_key: str | None, authorization: str | None) -> str | None:
    """`X-API-Key: <token>` ou `Authorization: Bearer <token>` (a chave vence, como no sistema antigo)."""
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None
