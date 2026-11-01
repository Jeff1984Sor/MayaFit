"""Configurações: identidade, usuários, perfis de acesso, e-mail (SMTP) e IA. Permissões vêm de core/permissoes.py."""

from datetime import timedelta

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.core import audit, ia, perfis, segredos, storage
from app.core import auth_service as svc
from app.core import email as mail
from app.core.db import agora
from app.core.deps import Ctx
from app.core.models import ConfigEmail, ConfigIA, Identidade, PerfilAcesso, Usuario
from app.core.permissoes import CATALOGO, ROTULO_ACAO, normalizar
from app.core.routes.auth import foto_url
from app.core.routes.public import NOME_PADRAO, logo_url
from app.core.schemas import (
    ConfigEmailIn,
    ConfigEmailOut,
    ConfigIAIn,
    ConfigIAOut,
    DefinirSenhaIn,
    IdentidadeIn,
    IdentidadeOut,
    Mensagem,
    PerfilAcessoIn,
    PerfilAcessoOut,
    UsuarioIn,
    UsuarioOut,
    UsuarioPatch,
)
from app.core.security import hash_senha, validar_politica_senha

router = APIRouter(prefix="/config", tags=["configurações"])


# ---------------------------------------------------------------- identidade
def _ident(ctx) -> Identidade:
    ident = ctx.db.scalar(select(Identidade).order_by(Identidade.id))
    if not ident:
        ident = Identidade(id=1, nome_exibicao=NOME_PADRAO)
        ctx.db.add(ident)
        ctx.db.flush()
    return ident


def _ident_out(i: Identidade) -> IdentidadeOut:
    return IdentidadeOut(nome_exibicao=i.nome_exibicao, logo_url=logo_url(i), cor_destaque=i.cor_destaque,
                         assinatura_email=i.assinatura_email)


@router.get("/identidade", response_model=IdentidadeOut)
def ler_identidade(ctx: Ctx):
    return _ident_out(_ident(ctx))


@router.put("/identidade", response_model=IdentidadeOut)
def salvar_identidade(dados: IdentidadeIn, ctx: Ctx):
    i = _ident(ctx)
    antes = audit.snapshot(i)
    for k, v in dados.model_dump().items():
        setattr(i, k, v)
    ctx.db.flush()
    a, d = audit.diff(antes, audit.snapshot(i))
    ctx.auditar("identidade.alterar", "identidade", i.id, antes=a, depois=d)
    ctx.db.commit()
    return _ident_out(i)


@router.post("/identidade/logo", response_model=IdentidadeOut)
async def enviar_logo(ctx: Ctx, arquivo: UploadFile = File(...)):
    conteudo = await arquivo.read(3 * 1024 * 1024 + 1)
    i = _ident(ctx)
    try:
        i.logo_path = storage.salvar("identidade", arquivo.filename or "", conteudo, nome_base="logo", substituir=True)
    except storage.ArquivoInvalido as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    ctx.auditar("identidade.logo", "identidade", i.id, descricao=f"Novo logo ({arquivo.filename})")
    ctx.db.commit()
    return _ident_out(i)


# ---------------------------------------------------------------- usuários
def _usuario_out(u: Usuario) -> UsuarioOut:
    now = agora()
    online = bool(u.ultima_atividade and now - u.ultima_atividade < timedelta(minutes=5))
    return UsuarioOut(
        id=u.id, nome=u.nome, email=u.email, login=u.login, telefone=u.telefone, foto_url=foto_url(u), ativo=u.ativo,
        acesso_sistema=u.acesso_sistema, convite_pendente=u.convite_pendente and u.acesso_sistema,
        ultimo_acesso=u.ultimo_acesso, online=online, perfil_acesso_id=u.perfil_acesso_id,
        perfil_acesso_nome=u.perfil_acesso.nome if u.perfil_acesso else None,
        perfil_acesso_cor=u.perfil_acesso.cor if u.perfil_acesso else None)


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios(ctx: Ctx):
    # o usuário Suporte da MayaCorp fica escondido do estúdio (decisão do Jefferson, 31/10/2026); só o Admin MayaFit o vê
    q = select(Usuario).where(Usuario.suporte.is_not(True)).order_by(Usuario.nome)
    return [_usuario_out(u) for u in ctx.db.scalars(q)]


def _usuario(ctx, uid: int) -> Usuario:
    u = ctx.db.get(Usuario, uid)
    if not u or (u.suporte and not ctx.usuario.suporte):  # o estúdio não edita nem desativa o Suporte

        raise HTTPException(404, "Usuário não encontrado.")
    return u


def _perfil(ctx, pid: int | None) -> PerfilAcesso:
    p = ctx.db.get(PerfilAcesso, pid) if pid else None
    if not p:
        raise HTTPException(404, "Perfil de acesso não encontrado.")
    return p


def _checar_unicos(ctx, email: str | None, login: str | None, exceto: int | None = None) -> None:
    if email and ctx.db.scalar(select(Usuario.id).where(Usuario.email == email.lower(), Usuario.id != (exceto or 0))):
        raise HTTPException(409, "Já existe um usuário com este e-mail.")
    if login and ctx.db.scalar(select(Usuario.id).where(Usuario.login == login.lower(), Usuario.id != (exceto or 0))):
        raise HTTPException(409, "Este login já está em uso.")


def _outros_admins(ctx, u: Usuario) -> bool:
    q = (select(Usuario.id).join(PerfilAcesso, Usuario.perfil_acesso_id == PerfilAcesso.id)
         .where(Usuario.id != u.id, Usuario.ativo, Usuario.acesso_sistema, PerfilAcesso.administrador))
    return bool(ctx.db.scalar(q))


@router.post("/usuarios", response_model=UsuarioOut, status_code=201)
def criar_usuario(dados: UsuarioIn, ctx: Ctx):
    """Cadastra o usuário. Com acesso ao sistema, recebe convite por e-mail (ou já sai com senha)."""
    _checar_unicos(ctx, dados.email, dados.login)
    perfil = _perfil(ctx, dados.perfil_acesso_id)
    acesso = dados.acesso_sistema
    if acesso and dados.senha and (erro := validar_politica_senha(dados.senha)):
        raise HTTPException(400, erro)
    u = Usuario(nome=dados.nome, email=dados.email.lower(), login=dados.login.lower() if dados.login else None,
                telefone=dados.telefone, perfil_acesso_id=perfil.id, acesso_sistema=acesso,
                senha_hash=hash_senha(dados.senha) if dados.senha and acesso else None,
                convite_pendente=acesso and not dados.senha)
    ctx.db.add(u)
    ctx.db.flush()
    if acesso and not dados.senha:
        svc.enviar_link_email(ctx.db, u, convite=True)
    ctx.auditar("usuario.criar", "usuario", u.id, descricao=f"{u.nome} ({perfil.nome})", depois=audit.snapshot(u))
    ctx.db.commit()
    return _usuario_out(u)


@router.patch("/usuarios/{uid}", response_model=UsuarioOut)
def alterar_usuario(uid: int, dados: UsuarioPatch, ctx: Ctx):
    u = _usuario(ctx, uid)
    m = dados.model_dump(exclude_unset=True)
    _checar_unicos(ctx, m.get("email"), m.get("login"), exceto=u.id)
    for k in ("email", "login"):
        if m.get(k):
            m[k] = m[k].lower()
    if "perfil_acesso_id" in m:
        novo = _perfil(ctx, m["perfil_acesso_id"])
        if u.administrador and not novo.administrador and not _outros_admins(ctx, u):
            raise HTTPException(400, "É preciso manter pelo menos um Administrador ativo com acesso.")
    sai_do_ar = m.get("ativo") is False or m.get("acesso_sistema") is False
    if sai_do_ar and u.id == ctx.usuario.id:
        raise HTTPException(400, "Você não pode tirar o seu próprio acesso.")
    if sai_do_ar and u.administrador and not _outros_admins(ctx, u):
        raise HTTPException(400, "É preciso manter pelo menos um Administrador ativo com acesso.")
    antes = audit.snapshot(u)
    for k, v in m.items():
        setattr(u, k, v)
    if sai_do_ar or "perfil_acesso_id" in m:
        svc.invalidar_sessoes(ctx.db, u)  # permissões/ativação mudaram: sessões em curso saem
    ctx.db.flush()
    ctx.db.refresh(u)
    a, d = audit.diff(antes, audit.snapshot(u))
    ctx.auditar("usuario.alterar", "usuario", u.id, descricao=u.nome, antes=a, depois=d)
    ctx.db.commit()
    return _usuario_out(u)


@router.delete("/usuarios/{uid}", response_model=Mensagem)
def desativar_usuario(uid: int, ctx: Ctx):
    u = _usuario(ctx, uid)
    if u.id == ctx.usuario.id:
        raise HTTPException(400, "Você não pode desativar a si mesmo.")
    if u.administrador and not _outros_admins(ctx, u):
        raise HTTPException(400, "É preciso manter pelo menos um Administrador ativo com acesso.")
    u.ativo = False
    svc.invalidar_sessoes(ctx.db, u)
    ctx.auditar("usuario.desativar", "usuario", u.id, descricao=u.nome)
    ctx.db.commit()
    return Mensagem(mensagem=f"{u.nome} foi desativado(a).")


@router.post("/usuarios/{uid}/redefinir-senha", response_model=Mensagem)
def redefinir_senha(uid: int, ctx: Ctx):
    u = _usuario(ctx, uid)
    if not (u.ativo and u.acesso_sistema):
        raise HTTPException(400, "Este usuário não tem acesso ao sistema.")
    if not svc.enviar_link_email(ctx.db, u, convite=u.convite_pendente):
        ctx.db.rollback()
        raise HTTPException(502, "Não foi possível enviar o e-mail. Confira a configuração de e-mail.")
    ctx.auditar("usuario.redefinir_senha", "usuario", u.id, descricao=u.nome)
    ctx.db.commit()
    return Mensagem(mensagem=f"Enviamos um link para {u.email}.")


@router.post("/usuarios/{uid}/definir-senha", response_model=Mensagem)
def definir_senha(uid: int, dados: DefinirSenhaIn, ctx: Ctx):
    u = _usuario(ctx, uid)
    if not u.acesso_sistema:
        raise HTTPException(400, "Este usuário não tem acesso ao sistema.")
    svc.definir_senha(ctx.db, u, dados.senha, acao="usuario.definir_senha", ip=ctx.ip, usuario_ator=ctx.usuario,
                      descricao=f"Senha de {u.nome} definida por {ctx.usuario.nome}")
    ctx.db.commit()
    return Mensagem(mensagem=f"Senha de {u.nome} definida.")


# ---------------------------------------------------------------- perfis de acesso
def _perfil_out(ctx, p: PerfilAcesso) -> PerfilAcessoOut:
    qtd = ctx.db.scalar(select(func.count()).select_from(Usuario).where(Usuario.perfil_acesso_id == p.id, Usuario.ativo)) or 0
    return PerfilAcessoOut.model_validate(p).model_copy(update={"qtd_usuarios": qtd})


@router.get("/perfis/catalogo")
def catalogo_permissoes(ctx: Ctx):
    return {"grupos": CATALOGO, "acoes": ROTULO_ACAO}


@router.get("/perfis", response_model=list[PerfilAcessoOut])
def listar_perfis(ctx: Ctx):
    perfis.garantir_padrao(ctx.db)
    ctx.db.commit()
    lista = ctx.db.scalars(select(PerfilAcesso).order_by(PerfilAcesso.administrador.desc(), PerfilAcesso.nome))
    return [_perfil_out(ctx, p) for p in lista]


def _salvar_perfil(ctx, p: PerfilAcesso, dados: PerfilAcessoIn) -> None:
    if ctx.db.scalar(select(PerfilAcesso.id).where(PerfilAcesso.id != (p.id or 0),
                                                   func.lower(PerfilAcesso.nome) == dados.nome.strip().lower())):
        raise HTTPException(409, "Já existe um perfil com este nome.")
    if p.sistema and not dados.administrador:
        raise HTTPException(400, "O perfil Administrador padrão continua com acesso total (duplique para criar outro).")
    p.nome, p.descricao, p.cor = dados.nome.strip(), dados.descricao, dados.cor
    p.administrador = dados.administrador
    p.somente_proprias_aulas = dados.somente_proprias_aulas and not dados.administrador
    p.permissoes = [] if dados.administrador else normalizar(dados.permissoes)
    ctx.db.flush()
    # permissões mudaram: quem usa o perfil precisa de um novo token
    for u in ctx.db.scalars(select(Usuario).where(Usuario.perfil_acesso_id == p.id)):
        svc.invalidar_sessoes(ctx.db, u)


@router.post("/perfis", response_model=PerfilAcessoOut, status_code=201)
def criar_perfil(dados: PerfilAcessoIn, ctx: Ctx):
    p = PerfilAcesso(nome=dados.nome)
    ctx.db.add(p)
    _salvar_perfil(ctx, p, dados)
    ctx.auditar("perfil_acesso.criar", "perfil_acesso", p.id, descricao=p.nome, depois={"permissoes": p.permissoes})
    ctx.db.commit()
    return _perfil_out(ctx, p)


@router.put("/perfis/{pid}", response_model=PerfilAcessoOut)
def alterar_perfil(pid: int, dados: PerfilAcessoIn, ctx: Ctx):
    p = _perfil(ctx, pid)
    antes = {"nome": p.nome, "administrador": p.administrador, "permissoes": list(p.permissoes or [])}
    if p.administrador and not dados.administrador and ctx.usuario.perfil_acesso_id == p.id:
        raise HTTPException(400, "Você usa este perfil: tirar o acesso total dele tiraria o seu também.")
    _salvar_perfil(ctx, p, dados)
    ctx.auditar("perfil_acesso.alterar", "perfil_acesso", p.id, descricao=p.nome, antes=antes,
                depois={"nome": p.nome, "administrador": p.administrador, "permissoes": p.permissoes})
    ctx.db.commit()
    return _perfil_out(ctx, p)


@router.post("/perfis/{pid}/duplicar", response_model=PerfilAcessoOut, status_code=201)
def duplicar_perfil(pid: int, ctx: Ctx):
    from app.core.permissoes import TODAS

    base = _perfil(ctx, pid)
    nome, n = f"{base.nome} (cópia)", 2
    while ctx.db.scalar(select(PerfilAcesso.id).where(PerfilAcesso.nome == nome)):
        nome, n = f"{base.nome} (cópia {n})", n + 1
    p = PerfilAcesso(nome=nome, descricao=base.descricao, cor=base.cor, administrador=False,
                     somente_proprias_aulas=base.somente_proprias_aulas,
                     permissoes=sorted(TODAS) if base.administrador else list(base.permissoes or []))
    ctx.db.add(p)
    ctx.db.flush()
    ctx.auditar("perfil_acesso.criar", "perfil_acesso", p.id, descricao=f"{p.nome} (duplicado de {base.nome})")
    ctx.db.commit()
    return _perfil_out(ctx, p)


@router.delete("/perfis/{pid}", response_model=Mensagem)
def excluir_perfil(pid: int, ctx: Ctx):
    p = _perfil(ctx, pid)
    if p.sistema:
        raise HTTPException(400, "O perfil Administrador padrão não pode ser excluído.")
    qtd = ctx.db.scalar(select(func.count()).select_from(Usuario).where(Usuario.perfil_acesso_id == p.id)) or 0
    if qtd:
        raise HTTPException(400, f"{qtd} usuário(s) usam este perfil: troque o perfil deles antes de excluir.")
    ctx.auditar("perfil_acesso.excluir", "perfil_acesso", p.id, descricao=p.nome)
    ctx.db.delete(p)
    ctx.db.commit()
    return Mensagem(mensagem="Perfil excluído.")


# ---------------------------------------------------------------- e-mail (SMTP)
def _cfg_email(ctx) -> ConfigEmail:
    c = ctx.db.get(ConfigEmail, 1)
    if not c:
        c = ConfigEmail(id=1, copia_padrao=[])
        ctx.db.add(c)
        ctx.db.flush()
    return c


def _email_out(c: ConfigEmail) -> ConfigEmailOut:
    return ConfigEmailOut(remetente_nome=c.remetente_nome, remetente_email=c.remetente_email, smtp_host=c.smtp_host,
                          smtp_porta=c.smtp_porta, smtp_usuario=c.smtp_usuario, smtp_senha_definida=bool(c.smtp_senha_cifrada),
                          copia_padrao=c.copia_padrao or [])


@router.get("/email", response_model=ConfigEmailOut)
def ler_email(ctx: Ctx):
    return _email_out(_cfg_email(ctx))


@router.put("/email", response_model=ConfigEmailOut)
def salvar_email(dados: ConfigEmailIn, ctx: Ctx):
    c = _cfg_email(ctx)
    antes = audit.snapshot(c)
    valores = dados.model_dump()
    senha = valores.pop("smtp_senha")
    for k, v in valores.items():
        setattr(c, k, v)
    if senha:
        c.smtp_senha_cifrada = segredos.cifrar_texto(senha)
    ctx.db.flush()
    a, d = audit.diff(antes, audit.snapshot(c))
    ctx.auditar("email.alterar", "config_email", c.id, antes=a, depois=d,
                descricao="Senha SMTP alterada" if senha else None)
    ctx.db.commit()
    return _email_out(c)


@router.post("/email/testar", response_model=Mensagem)
def testar_email(ctx: Ctx):
    """Envia um e-mail de teste ao próprio usuário logado."""
    ok = mail.enviar([ctx.usuario.email], "Teste de e-mail", "Se você recebeu esta mensagem, o e-mail está configurado.", db=ctx.db)
    if not ok:
        raise HTTPException(502, "Não foi possível enviar. Confira servidor, porta, usuário e senha.")
    return Mensagem(mensagem=f"E-mail de teste enviado para {ctx.usuario.email}.")


# ---------------------------------------------------------------- IA
def _ia_out(cfg: ConfigIA) -> ConfigIAOut:
    final = segredos.decifrar_texto(cfg.chave_cifrada)[-4:] if cfg.chave_cifrada else None
    return ConfigIAOut(ativo=cfg.ativo, provedor=cfg.provedor, modelo=cfg.modelo, chave_definida=bool(cfg.chave_cifrada),
                       chave_final=final, provedores=ia.PROVEDORES)


@router.get("/ia", response_model=ConfigIAOut)
def ler_ia(ctx: Ctx):
    return _ia_out(ia.config(ctx.db))


@router.get("/ia/modelos", response_model=list[str])
def modelos_ia(ctx: Ctx, provedor: str | None = None):
    """Modelos de texto disponíveis para a chave já salva (consulta o próprio provedor)."""
    cfg = ia.config(ctx.db)
    escolhido = provedor or cfg.provedor
    if escolhido not in ia.PROVEDORES:
        raise HTTPException(400, "Provedor desconhecido.")
    if escolhido != cfg.provedor or not cfg.chave_cifrada:
        raise HTTPException(400, "Salve a chave deste provedor primeiro para listar os modelos.")
    try:
        return ia.listar_modelos(escolhido, segredos.decifrar_texto(cfg.chave_cifrada))
    except ia.IAIndisponivel as e:
        raise HTTPException(502, str(e)) from e


@router.put("/ia", response_model=ConfigIAOut)
def salvar_ia(dados: ConfigIAIn, ctx: Ctx):
    cfg = ia.config(ctx.db)
    antes = {"ativo": cfg.ativo, "provedor": cfg.provedor, "modelo": cfg.modelo}
    if dados.provedor != cfg.provedor and not dados.chave:
        cfg.chave_cifrada = None  # chave de um provedor não serve no outro
    cfg.provedor, cfg.modelo = dados.provedor, dados.modelo
    if dados.chave:
        cfg.chave_cifrada = segredos.cifrar_texto(dados.chave.strip())
    if dados.ativo and not (cfg.chave_cifrada and cfg.modelo):
        raise HTTPException(400, "Para ativar, informe a chave e escolha o modelo.")
    cfg.ativo = dados.ativo
    ctx.auditar("ia.configurar", "config_ia", cfg.id, antes=antes,
                depois={"ativo": cfg.ativo, "provedor": cfg.provedor, "modelo": cfg.modelo,
                        "chave": "alterada" if dados.chave else "mantida"})
    ctx.db.commit()
    return _ia_out(cfg)
