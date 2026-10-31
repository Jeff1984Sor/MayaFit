"""Regras de autenticação: emissão/rotação de tokens, recuperação de senha (e-mail e WhatsApp), troca de senha."""

import hmac
import re
import secrets
from datetime import timedelta

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import audit, tenancy
from app.core import email as mail
from app.core.config import settings
from app.core.db import agora
from app.core.models import RecuperacaoSenha, RefreshToken, Usuario
from app.core.notificador import get_notificador
from app.core.security import (
    criar_token,
    decodificar_token,
    gastar_tempo_de_verificacao,
    hash_senha,
    hash_token,
    precisa_rehash,
    validar_politica_senha,
    verificar_senha,
)

MSG_LOGIN = "Login ou senha incorretos, ou acesso temporariamente bloqueado."
MSG_SESSAO = "Sessão expirada. Entre novamente."
MSG_RESET_INVALIDO = "Link ou código inválido ou expirado."
JANELA_REUSO_REFRESH_S = 15  # duas abas renovando juntas não derrubam a sessão


def localizar(db: Session, identificador: str) -> Usuario | None:
    """Acha o usuário pelo LOGIN. Decisão do Jefferson: ninguém entra com e-mail."""
    ident = identificador.strip().lower()
    if not ident:
        return None
    return db.scalar(select(Usuario).where(Usuario.login == ident))


def pode_entrar(u: Usuario | None) -> bool:
    return bool(u and u.ativo and u.acesso_sistema and u.senha_hash)


# ------------------------------------------------------------------------------------------------ tokens
def emitir_tokens(db: Session, u: Usuario) -> tuple[str, str]:
    """(access, refresh). O refresh fica registrado para permitir rotação e detecção de reuso."""
    now = agora()
    db.execute(RefreshToken.__table__.delete().where(RefreshToken.expira_em < now - timedelta(days=1)))
    access = criar_token(str(u.id), "access", {"tv": u.token_version})
    refresh = criar_token(str(u.id), "refresh", {"tv": u.token_version})
    jti = jwt.decode(refresh, options={"verify_signature": False})["jti"]
    db.add(RefreshToken(jti=jti, usuario_id=u.id, expira_em=now + timedelta(days=settings.jwt_refresh_days)))
    db.flush()
    return access, refresh


def invalidar_sessoes(db: Session, u: Usuario) -> None:
    """Sobe a versão do token (derruba access e refresh em circulação) e apaga os refresh registrados."""
    u.token_version = (u.token_version or 0) + 1
    db.execute(RefreshToken.__table__.delete().where(RefreshToken.usuario_id == u.id))


def rotacionar_refresh(db: Session, token: str, ip: str | None) -> tuple[Usuario, str, str]:
    """Consome o refresh e emite um novo par. Reuso de refresh já consumido = possível roubo: derruba todas as sessões."""
    erro = HTTPException(status.HTTP_401_UNAUTHORIZED, MSG_SESSAO)
    try:
        payload = decodificar_token(token, "refresh")
        uid = int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise erro from None
    if not tenancy.token_do_estudio_atual(payload):
        raise erro
    u = db.get(Usuario, uid)
    linha = db.get(RefreshToken, payload["jti"])
    if not u or not pode_entrar(u) or not linha or linha.usuario_id != u.id or payload.get("tv") != u.token_version:
        raise erro
    now = agora()
    if linha.usado_em is not None:
        if (now - linha.usado_em).total_seconds() > JANELA_REUSO_REFRESH_S:
            invalidar_sessoes(db, u)
            audit.registrar(db, usuario=u, acao="auth.refresh_reutilizado", entidade="usuario", entidade_id=u.id,
                            descricao="Refresh token reutilizado: sessões encerradas", ip=ip)
            db.commit()
        raise erro
    linha.usado_em = now
    access, refresh = emitir_tokens(db, u)
    db.commit()
    return u, access, refresh


# ------------------------------------------------------------------------------------------------ login
def autenticar(db: Session, identificador: str, senha: str, ip: str | None) -> Usuario:
    """Valida credenciais com bloqueio por tentativas. Todas as falhas devolvem a MESMA resposta (não revela a conta)."""
    erro = HTTPException(status.HTTP_401_UNAUTHORIZED, MSG_LOGIN)
    u = localizar(db, identificador)
    now = agora()
    if not pode_entrar(u):
        gastar_tempo_de_verificacao(senha)
        raise erro
    if u.bloqueado_ate and u.bloqueado_ate > now:
        gastar_tempo_de_verificacao(senha)
        raise erro
    if not verificar_senha(senha, u.senha_hash):
        u.tentativas_falhas = (u.tentativas_falhas or 0) + 1
        if u.tentativas_falhas >= settings.login_max_tentativas:
            u.bloqueado_ate = now + timedelta(minutes=settings.login_bloqueio_minutos)
            u.tentativas_falhas = 0
            audit.registrar(db, usuario=u, acao="auth.bloqueio", entidade="usuario", entidade_id=u.id,
                            descricao="Bloqueio temporário por tentativas", ip=ip)
        db.commit()
        raise erro
    if precisa_rehash(u.senha_hash):  # hash do Django antigo: regrava em Argon2 agora que temos a senha em mãos
        u.senha_hash = hash_senha(senha)
    u.tentativas_falhas = 0
    u.bloqueado_ate = None
    u.ultimo_acesso = u.ultima_atividade = now
    audit.registrar(db, usuario=u, acao="auth.login", entidade="usuario", entidade_id=u.id, ip=ip)
    return u


# ------------------------------------------------------------------------------------------------ senha
def definir_senha(db: Session, u: Usuario, nova: str, *, acao: str, ip: str | None, usuario_ator: Usuario | None = None,
                  descricao: str | None = None) -> None:
    """Grava a nova senha, derruba as sessões anteriores e zera o bloqueio. Levanta 400 se a senha não passa na política."""
    if erro := validar_politica_senha(nova):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, erro)
    u.senha_hash = hash_senha(nova)
    u.convite_pendente = False
    u.tentativas_falhas = 0
    u.bloqueado_ate = None
    invalidar_sessoes(db, u)
    audit.registrar(db, usuario=usuario_ator or u, acao=acao, entidade="usuario", entidade_id=u.id, descricao=descricao, ip=ip)


def trocar_senha(db: Session, u: Usuario, atual: str, nova: str, ip: str | None) -> None:
    if not u.senha_hash or not verificar_senha(atual, u.senha_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta.")
    definir_senha(db, u, nova, acao="auth.trocar_senha", ip=ip)


# ------------------------------------------------------------------------------------------------ recuperação
def _invalidar_pendentes(db: Session, u: Usuario, canal: str) -> None:
    db.execute(update(RecuperacaoSenha).where(RecuperacaoSenha.usuario_id == u.id, RecuperacaoSenha.canal == canal,
                                              RecuperacaoSenha.usado_em.is_(None)).values(usado_em=agora()))


def _endereco() -> str:
    """Base dos links: o endereço do estúdio no modo multi (a tela abre com a marca dele); senão o FRONTEND_URL."""
    if tenancy.multi() and tenancy.atual() is not None:
        from app.controle import service

        return service.endereco_do_estudio()
    return settings.frontend_url.rstrip("/")


def criar_link_email(db: Session, u: Usuario, minutos: int | None = None) -> str:
    """Cria o token de uso único e devolve o link para o frontend (o token em claro NUNCA fica no banco)."""
    _invalidar_pendentes(db, u, "email")
    token = secrets.token_urlsafe(32)
    if tenancy.multi() and (esc := tenancy.atual()) is not None:
        token = f"{esc.slug}.{token}"  # um banco por estúdio: o link diz o estúdio (o digest cobre o slug: não se forja)
    db.add(RecuperacaoSenha(usuario_id=u.id, canal="email", digest=hash_token(token),
                            expira_em=agora() + timedelta(minutes=minutos or settings.recuperacao_email_minutos)))
    db.flush()
    return f"{_endereco()}/redefinir-senha?token={token}"


def enviar_link_email(db: Session, u: Usuario, *, convite: bool = False) -> bool:
    horas = settings.recuperacao_email_minutos // 60
    link = criar_link_email(db, u)
    if convite:
        assunto = "Seu acesso ao sistema"
        texto = f"Olá, {u.nome}!\n\nVocê foi convidado(a) para o sistema. Defina sua senha:\n{link}"
    else:
        assunto = "Redefinição de senha"
        texto = f"Olá, {u.nome}.\n\nPara criar uma nova senha, acesse:\n{link}"
    texto += f"\n\nO link vale por {horas} horas e só pode ser usado uma vez. Se não foi você, ignore este e-mail."
    return mail.enviar([u.email], assunto, texto, db=db)


def telefone_whatsapp(telefone: str | None) -> str | None:
    """Só dígitos com DDI 55. (A normalização completa de telefones, R16, fica no domínio; aqui só o necessário.)"""
    d = re.sub(r"\D", "", telefone or "")
    if len(d) in (10, 11):
        d = "55" + d
    return d if 12 <= len(d) <= 13 and d.startswith("55") else None


def enviar_codigo_whatsapp(db: Session, u: Usuario) -> bool:
    fone = telefone_whatsapp(u.telefone)
    if not fone:
        return False
    _invalidar_pendentes(db, u, "whatsapp")
    codigo = f"{secrets.randbelow(10**6):06d}"
    db.add(RecuperacaoSenha(usuario_id=u.id, canal="whatsapp", digest=hash_token(f"{u.id}:{codigo}"),
                            expira_em=agora() + timedelta(minutes=settings.recuperacao_codigo_minutos)))
    db.flush()
    texto = (f"Seu código para redefinir a senha é {codigo}. Vale por {settings.recuperacao_codigo_minutos} minutos. "
             "Não compartilhe com ninguém.")
    return get_notificador().enviar_texto(fone, texto)


def estudio_do_link(token: str) -> bool:
    """Um banco por estúdio: o token do link de redefinição/convite começa com `<slug>.` e define o estúdio do pedido.
    False = link sem estúdio válido (inexistente ou inativo). Com um banco só, não faz nada."""
    if not tenancy.multi():
        return True
    from app.controle import service

    slug, _, resto = (token or "").partition(".")
    esc = service.por_slug(slug) if resto and service.SLUG.match(slug) else None
    if esc is None:
        return False
    tenancy.definir(esc)
    return True


def redefinir_por_token(db: Session, token: str, nova: str, ip: str | None) -> Usuario:
    erro = HTTPException(status.HTTP_400_BAD_REQUEST, MSG_RESET_INVALIDO)
    if not estudio_do_link(token):
        raise erro
    linha = db.scalar(select(RecuperacaoSenha).where(RecuperacaoSenha.digest == hash_token(token),
                                                     RecuperacaoSenha.canal == "email"))
    now = agora()
    if not linha or linha.usado_em is not None or linha.expira_em < now:
        raise erro
    u = db.get(Usuario, linha.usuario_id)
    if not u or not u.ativo or not u.acesso_sistema:
        raise erro
    if erro_senha := validar_politica_senha(nova):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, erro_senha)
    linha.usado_em = now  # uso único
    definir_senha(db, u, nova, acao="auth.reset", ip=ip, descricao="Senha redefinida por link de e-mail")
    return u


def redefinir_por_codigo(db: Session, identificador: str, codigo: str, nova: str, ip: str | None) -> Usuario:
    """Código de 6 dígitos do WhatsApp: no máximo N tentativas por código; erro sempre igual (não revela a conta)."""
    erro = HTTPException(status.HTTP_400_BAD_REQUEST, MSG_RESET_INVALIDO)
    u = localizar(db, identificador)
    now = agora()
    linha = None
    if u and u.ativo and u.acesso_sistema:
        linha = db.scalar(select(RecuperacaoSenha).where(
            RecuperacaoSenha.usuario_id == u.id, RecuperacaoSenha.canal == "whatsapp", RecuperacaoSenha.usado_em.is_(None),
        ).order_by(RecuperacaoSenha.id.desc()))
    if not linha or linha.expira_em < now or linha.tentativas >= settings.recuperacao_codigo_max_tentativas:
        hash_token(codigo)  # mantém custo parecido
        raise erro
    linha.tentativas += 1
    if not hmac.compare_digest(linha.digest, hash_token(f"{u.id}:{codigo.strip()}")):
        if linha.tentativas >= settings.recuperacao_codigo_max_tentativas:
            linha.usado_em = now  # esgotou: o código morre
        db.commit()
        raise erro
    if erro_senha := validar_politica_senha(nova):
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, erro_senha)
    linha.usado_em = now
    definir_senha(db, u, nova, acao="auth.reset", ip=ip, descricao="Senha redefinida por código do WhatsApp")
    return u
