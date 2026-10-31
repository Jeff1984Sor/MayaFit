"""Autenticação. `publico` = sem login (rate limit); `router` = conta do usuário logado."""

import json
from typing import Any

import jwt
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select

from app.core import audit, perfis, storage, tenancy
from app.core import auth_service as svc
from app.core.db import agora
from app.core.deps import DB, Ctx, ip_cliente
from app.core.estudio_http import definir_pelo_token
from app.core.models import PerfilAcesso, Usuario
from app.core.ratelimit import limitar, verificar
from app.core.schemas import (
    EstudioInfo,
    ForgotIn,
    LoginIn,
    Mensagem,
    MePatch,
    PrimeiroAcessoIn,
    PrimeiroAcessoInfo,
    RefreshIn,
    ResetCodigoIn,
    ResetIn,
    TokenOut,
    TrocarSenhaIn,
    UsuarioMe,
)

publico = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(prefix="/auth", tags=["auth"])

MSG_FORGOT = "Se a conta existir, enviamos as instruções para redefinir a senha."


def foto_url(u: Usuario) -> str | None:
    if not storage.existe(u.foto_path):
        return None
    return f"/auth/usuarios/{u.id}/foto?v={storage.versao(u.foto_path)}"


def estudio_info() -> EstudioInfo | None:
    """O estúdio do pedido (um banco por estúdio); None com um banco só."""
    esc = tenancy.atual()
    if not tenancy.multi() or esc is None:
        return None
    from app.controle import service

    dados = service.info(esc.slug)
    return EstudioInfo(**dados) if dados else None


def estudio_do_login(identificador: str) -> bool:
    """Um banco por estúdio: o estúdio vem do endereço (já definido no pedido) ou, no endereço principal, do catálogo
    de logins. False = login inexistente, de estúdio inativo ou repetido em mais de um estúdio (aí só pelo endereço
    do estúdio). Quem chama responde com a MESMA mensagem genérica (não revela nada)."""
    if not tenancy.multi() or tenancy.atual() is not None:
        return True
    from app.controle import service

    esc = service.por_login(identificador)
    if esc is None:
        return False
    tenancy.definir(esc)
    return True


def me_out(u: Usuario) -> UsuarioMe:
    return UsuarioMe.model_validate(u).model_copy(update={
        "estudio": estudio_info(),
        "foto_url": foto_url(u), "administrador": u.administrador, "permissoes": sorted(u.permissoes),
        "perfil_acesso_nome": u.perfil_acesso.nome if u.perfil_acesso else None,
        "somente_proprias_aulas": bool(u.perfil_acesso and not u.administrador and u.perfil_acesso.somente_proprias_aulas)})


def _tokens(db, u: Usuario) -> TokenOut:
    access, refresh = svc.emitir_tokens(db, u)
    return TokenOut(access_token=access, refresh_token=refresh, usuario=me_out(u))


# ------------------------------------------------------------------------------------------- públicas
@publico.post("/login", response_model=TokenOut, dependencies=[Depends(limitar("login", 20, 60))])
def login(dados: LoginIn, request: Request, db: DB):
    if not estudio_do_login(dados.identificador):
        verificar(request, "login-conta", 30, 900, chave=dados.identificador.strip().lower())
        svc.gastar_tempo_de_verificacao(dados.senha)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, svc.MSG_LOGIN)
    # além do limite por IP, limita por identificador (ataque distribuído contra uma conta)
    verificar(request, "login-conta", 30, 900, chave=dados.identificador.strip().lower(), db=db)
    u = svc.autenticar(db, dados.identificador, dados.senha, ip_cliente(request))
    out = _tokens(db, u)
    db.commit()
    return out


@publico.post("/refresh", response_model=TokenOut, dependencies=[Depends(limitar("refresh", 60, 60))])
def refresh(dados: RefreshIn, request: Request, db: DB):
    if tenancy.multi() and definir_pelo_token(dados.refresh_token) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, svc.MSG_SESSAO)
    u, access, refresh_token = svc.rotacionar_refresh(db, dados.refresh_token, ip_cliente(request))
    return TokenOut(access_token=access, refresh_token=refresh_token, usuario=me_out(u))


@publico.post("/forgot", response_model=Mensagem, dependencies=[Depends(limitar("forgot", 5, 900))])
def forgot(dados: ForgotIn, request: Request, db: DB):
    """Recuperação por e-mail. A resposta é a mesma exista a conta ou não."""
    if not estudio_do_login(dados.identificador):
        return Mensagem(mensagem=MSG_FORGOT)
    verificar(request, "forgot-conta", 3, 3600, chave=dados.identificador.strip().lower(), db=db)
    u = svc.localizar(db, dados.identificador)
    if u and u.ativo and u.acesso_sistema:
        svc.enviar_link_email(db, u)
        db.commit()
    return Mensagem(mensagem=MSG_FORGOT)


@publico.post("/reset", response_model=Mensagem, dependencies=[Depends(limitar("reset", 10, 900))])
def reset(dados: ResetIn, request: Request, db: DB):
    svc.redefinir_por_token(db, dados.token, dados.senha, ip_cliente(request))
    db.commit()
    return Mensagem(mensagem="Senha definida. Você já pode entrar.")


@publico.post("/forgot-codigo", response_model=Mensagem, dependencies=[Depends(limitar("forgot-codigo", 5, 900))])
def forgot_codigo(dados: ForgotIn, request: Request, db: DB):
    """Recuperação por código enviado ao WhatsApp cadastrado. Resposta igual exista a conta (ou o telefone) ou não."""
    msg = Mensagem(mensagem="Se a conta existir e tiver WhatsApp cadastrado, enviamos um código.")
    if not estudio_do_login(dados.identificador):
        return msg
    verificar(request, "forgot-codigo-conta", 3, 3600, chave=dados.identificador.strip().lower(), db=db)
    u = svc.localizar(db, dados.identificador)
    if u and u.ativo and u.acesso_sistema:
        svc.enviar_codigo_whatsapp(db, u)
        db.commit()
    return msg


@publico.post("/reset-codigo", response_model=Mensagem, dependencies=[Depends(limitar("reset-codigo", 10, 900))])
def reset_codigo(dados: ResetCodigoIn, request: Request, db: DB):
    if not estudio_do_login(dados.identificador):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, svc.MSG_RESET_INVALIDO)
    svc.redefinir_por_codigo(db, dados.identificador, dados.codigo, dados.senha, ip_cliente(request))
    db.commit()
    return Mensagem(mensagem="Senha definida. Você já pode entrar.")


# ------------------------------------------------------------------------------- primeiro acesso (estúdio novo)
MSG_PRIMEIRO_INVALIDO = "Link inválido ou expirado. Peça um novo à MayaCorp."


def _estudio_sem_master(token: str, db) -> dict[str, Any]:
    """O link de boas-vindas (token assinado `primeiro`, 7 dias, com o estúdio na claim `est`) vale enquanto o estúdio
    não tem administrador além do usuário Suporte da MayaCorp."""
    erro = HTTPException(status.HTTP_400_BAD_REQUEST, MSG_PRIMEIRO_INVALIDO)
    try:
        payload = svc.decodificar_token(token, "primeiro")
    except jwt.PyJWTError:
        raise erro from None
    if tenancy.multi() and (definir_pelo_token(token) is None or not tenancy.token_do_estudio_atual(payload)):
        raise erro
    tem_master = db.scalar(select(Usuario.id).join(PerfilAcesso, Usuario.perfil_acesso_id == PerfilAcesso.id).where(
        Usuario.suporte.is_(False), PerfilAcesso.administrador.is_(True)).limit(1))
    if tem_master:
        raise HTTPException(status.HTTP_409_CONFLICT, "O usuário master deste estúdio já foi criado. Entre com ele.")
    return payload


@publico.get("/primeiro-acesso", response_model=PrimeiroAcessoInfo,
             dependencies=[Depends(limitar("primeiro-acesso", 30, 900))])
def ler_primeiro_acesso(token: str, db: DB):
    from app.core.models import Identidade

    payload = _estudio_sem_master(token, db)
    ident = db.scalar(select(Identidade).order_by(Identidade.id))
    return PrimeiroAcessoInfo(estudio=ident.nome_exibicao if ident else "", email=payload.get("email"))


@publico.post("/primeiro-acesso", response_model=TokenOut, dependencies=[Depends(limitar("primeiro-acesso", 30, 900))])
def primeiro_acesso(dados: PrimeiroAcessoIn, request: Request, db: DB):
    """Cria o usuário master (perfil administrador) com o login e a senha escolhidos e já entra. Vale uma vez só."""
    _estudio_sem_master(dados.token, db)
    if erro := svc.validar_politica_senha(dados.senha):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, erro)
    email, login = str(dados.email).strip().lower(), dados.login.strip().lower()
    if db.scalar(select(Usuario.id).where(or_(Usuario.email == email, Usuario.login == login))):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este e-mail ou login já existe neste estúdio. Escolha outro.")
    adm = next(p for p in perfis.garantir_padrao(db).values() if p.administrador)
    u = Usuario(nome=dados.nome.strip(), email=email, login=login, perfil_acesso_id=adm.id,
                senha_hash=svc.hash_senha(dados.senha), convite_pendente=False, ultimo_acesso=agora())
    db.add(u)
    db.flush()
    audit.registrar(db, usuario=u, acao="auth.primeiro_acesso", entidade="usuario", entidade_id=u.id,
                    ip=ip_cliente(request), descricao="Usuário master criado pelo link de boas-vindas")
    out = _tokens(db, u)
    db.commit()
    return out


# ------------------------------------------------------------------------------------------- conta logada
@router.post("/trocar-senha", response_model=TokenOut)
def trocar_senha(dados: TrocarSenhaIn, ctx: Ctx):
    """Exige a senha atual. Derruba as outras sessões e devolve tokens novos para esta."""
    svc.trocar_senha(ctx.db, ctx.usuario, dados.senha_atual, dados.nova_senha, ctx.ip)
    out = _tokens(ctx.db, ctx.usuario)
    ctx.db.commit()
    return out


@router.post("/logout", response_model=Mensagem)
def logout(ctx: Ctx):
    """Encerra TODAS as sessões do usuário (invalida access e refresh em circulação)."""
    svc.invalidar_sessoes(ctx.db, ctx.usuario)
    ctx.auditar("auth.logout", "usuario", ctx.usuario.id)
    ctx.db.commit()
    return Mensagem(mensagem="Sessões encerradas.")


@router.get("/me", response_model=UsuarioMe)
def me(ctx: Ctx):
    return me_out(ctx.usuario)


@router.patch("/me", response_model=UsuarioMe)
def alterar_me(dados: MePatch, ctx: Ctx):
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(ctx.usuario, k, v)
    ctx.auditar("usuario.alterar_proprio", "usuario", ctx.usuario.id)
    ctx.db.commit()
    return me_out(ctx.usuario)


@router.put("/me/preferencias", response_model=UsuarioMe)
def salvar_preferencias(dados: dict[str, Any], ctx: Ctx):
    """Mescla as preferências enviadas (ex.: {"menu_recolhido": ["Cadastros"]}). Valor null remove a chave."""
    atual = dict(ctx.usuario.preferencias or {})
    for k, v in dados.items():
        if v is None:
            atual.pop(k, None)
        else:
            atual[str(k)[:60]] = v
    if len(json.dumps(atual)) > 20_000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Preferências grandes demais.")
    ctx.usuario.preferencias = atual
    ctx.db.commit()
    return me_out(ctx.usuario)


async def salvar_foto(u: Usuario, arquivo: UploadFile) -> None:
    conteudo = await arquivo.read(4 * 1024 * 1024 + 1)
    try:
        u.foto_path = storage.salvar("usuarios", arquivo.filename or "", conteudo, nome_base=f"usuario_{u.id}", substituir=True)
    except storage.ArquivoInvalido as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.post("/me/foto", response_model=UsuarioMe)
async def enviar_foto(ctx: Ctx, arquivo: UploadFile = File(...)):
    await salvar_foto(ctx.usuario, arquivo)
    ctx.auditar("usuario.foto", "usuario", ctx.usuario.id, descricao="Nova foto de perfil")
    ctx.db.commit()
    return me_out(ctx.usuario)


@router.delete("/me/foto", response_model=UsuarioMe)
def remover_foto(ctx: Ctx):
    storage.remover(ctx.usuario.foto_path)
    ctx.usuario.foto_path = None
    ctx.db.commit()
    return me_out(ctx.usuario)


def _usuario(ctx, uid: int) -> Usuario:
    u = ctx.db.get(Usuario, uid)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    return u


@router.post("/usuarios/{uid}/foto", response_model=Mensagem)
async def enviar_foto_de(uid: int, ctx: Ctx, arquivo: UploadFile = File(...)):
    """Quem pode editar usuários troca a foto de outro (ex.: profissional sem login)."""
    u = _usuario(ctx, uid)
    await salvar_foto(u, arquivo)
    ctx.auditar("usuario.foto", "usuario", u.id, descricao=f"Foto de {u.nome} trocada por {ctx.usuario.nome}")
    ctx.db.commit()
    return Mensagem(mensagem=f"Foto de {u.nome} atualizada.")


@router.delete("/usuarios/{uid}/foto", response_model=Mensagem)
def remover_foto_de(uid: int, ctx: Ctx):
    u = _usuario(ctx, uid)
    storage.remover(u.foto_path)
    u.foto_path = None
    ctx.auditar("usuario.foto", "usuario", u.id, descricao=f"Foto de {u.nome} removida por {ctx.usuario.nome}")
    ctx.db.commit()
    return Mensagem(mensagem="Foto removida.")


@router.get("/usuarios/{uid}/foto")
def foto(uid: int, ctx: Ctx):
    u = _usuario(ctx, uid)
    if not storage.existe(u.foto_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sem foto.")
    return FileResponse(storage.resolver(u.foto_path), headers={"Cache-Control": "private, max-age=86400"})
