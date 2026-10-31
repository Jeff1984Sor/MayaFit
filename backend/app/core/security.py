"""Hash de senha (Argon2, aceitando o PBKDF2 do Django antigo) e tokens JWT.

Cifra de segredos fica em `app.core.segredos`.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

_hasher = PasswordHash.recommended()

TokenTipo = Literal["access", "refresh", "primeiro"]

_DJANGO_ALGS = {"pbkdf2_sha256": "sha256", "pbkdf2_sha1": "sha1"}
_MAX_ITERACOES_DJANGO = 5_000_000  # evita DoS por hash adulterado com iterações absurdas


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def eh_hash_django(senha_hash: str) -> bool:
    return senha_hash.split("$", 1)[0] in _DJANGO_ALGS


def _verificar_django(senha: str, senha_hash: str) -> bool:
    """Formato do Django: `pbkdf2_sha256$<iterações>$<salt>$<hash_base64>`."""
    try:
        algoritmo, iteracoes, salt, esperado = senha_hash.split("$", 3)
        n = int(iteracoes)
        if not 1 <= n <= _MAX_ITERACOES_DJANGO:
            return False
        calculado = hashlib.pbkdf2_hmac(_DJANGO_ALGS[algoritmo], senha.encode(), salt.encode(), n)
        return hmac.compare_digest(base64.b64encode(calculado).decode(), esperado)
    except (ValueError, KeyError):
        return False


def verificar_senha(senha: str, senha_hash: str) -> bool:
    if eh_hash_django(senha_hash):
        return _verificar_django(senha, senha_hash)
    try:
        return _hasher.verify(senha, senha_hash)
    except Exception:
        return False


def precisa_rehash(senha_hash: str) -> bool:
    """Hash do Django: deve ser regravado em Argon2 após um login bem-sucedido."""
    if eh_hash_django(senha_hash):
        return True
    return False


@lru_cache
def _hash_falso() -> str:
    return hash_senha(secrets.token_urlsafe(12))


def gastar_tempo_de_verificacao(senha: str) -> None:
    """Conta inexistente também paga o custo do Argon2: o tempo de resposta não revela se ela existe."""
    verificar_senha(senha, _hash_falso())


def criar_token(sub: str, tipo: TokenTipo, extra: dict[str, Any] | None = None) -> str:
    """No modo um banco por estúdio, todo token leva o estúdio atual na claim `est` (app.core.tenancy)."""
    from app.core import tenancy

    duracao = {
        "access": timedelta(minutes=settings.jwt_access_minutes),
        "refresh": timedelta(days=settings.jwt_refresh_days),
        "primeiro": timedelta(days=7),  # boas-vindas: o dono do estúdio novo cria o usuário master
    }[tipo]
    now = datetime.now(UTC)
    payload = {"sub": sub, "typ": tipo, "iat": now, "exp": now + duracao, "jti": secrets.token_hex(16)}
    payload.update(tenancy.claims())
    payload.update(extra or {})
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decodificar_token(token: str, tipo: TokenTipo) -> dict[str, Any]:
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub", "typ", "jti"]}
    )
    if payload.get("typ") != tipo:
        raise jwt.InvalidTokenError("tipo de token inválido")
    return payload


def hash_token(valor: str) -> str:
    """Digest de tokens/códigos de uso único guardados no banco (nunca o valor em claro)."""
    return hmac.new(settings.jwt_secret.encode(), valor.encode(), hashlib.sha256).hexdigest()


def validar_politica_senha(senha: str) -> str | None:
    if len(senha) < 8:
        return "A senha precisa ter pelo menos 8 caracteres."
    if len(senha) > 128:
        return "A senha pode ter no máximo 128 caracteres."
    if senha.isdigit() or senha.isalpha():
        return "Use letras e números na senha."
    return None
