"""Rotas do site do estúdio.

- `router` (/api/site, login + `site.ver`/`site.editar`): editor, publicação, fotos e contatos recebidos.
- `router_publico` (/api/site-publico, SEM login, só leitura + formulário com rate limit e anti-spam): o estúdio vem
  do host (middleware de tenancy); declarado em `permissoes.PUBLICAS_AUTENTICACAO_PROPRIA`.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.core import storage
from app.core.deps import DB, Ctx
from app.core.permissoes import adicionar_regras
from app.core.ratelimit import limitar
from app.core.schemas import Mensagem
from app.modules.site import regras, servico
from app.modules.site import schemas as sc
from app.modules.site.models import SiteContato

router = APIRouter(prefix="/site", tags=["site"])
router_publico = APIRouter(prefix="/site-publico", tags=["site-publico"])

adicionar_regras([
    ("GET", r"/site(/|$)", "site.ver"),
    ("*", r"/site(/|$)", "site.editar"),
])


@contextmanager
def traduzir():
    try:
        yield
    except servico.ErroSite as e:
        raise HTTPException(e.status, e.mensagem) from e
    except storage.ArquivoInvalido as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


def _host(request: Request) -> str | None:
    return request.headers.get("x-forwarded-host") or request.headers.get("host")


def _editor(ctx: Ctx, request: Request) -> sc.EditorOut:
    cfg = servico.obter_config(ctx.db)
    c = servico.conteudo_de(cfg)
    out = sc.EditorOut(
        tema=cfg.tema, conteudo=c, publicado=cfg.publicado, publicado_em=cfg.publicado_em,
        alteracoes_pendentes=servico.alteracoes_pendentes(cfg), identidade=servico.identidade_site(ctx.db),
        dados=servico.dados_do_estudio(ctx.db, c, publico=False), endereco=servico.endereco(_host(request)),
        contatos_nao_lidos=servico.contar_nao_lidos(ctx.db),
    )
    ctx.db.commit()  # grava o rascunho inicial na primeira visita
    return out


# ------------------------------------------------------------------------------------------------------ editor
@router.get("", response_model=sc.EditorOut)
def editor(ctx: Ctx, request: Request):
    return _editor(ctx, request)


@router.put("", response_model=sc.EditorOut)
def salvar(dados: sc.SalvarIn, ctx: Ctx, request: Request):
    with traduzir():
        servico.salvar(ctx.db, dados)
    ctx.auditar("site.salvar", "site_config", 1, descricao=f"Rascunho do site salvo (tema {dados.tema})")
    ctx.db.commit()
    return _editor(ctx, request)


@router.post("/publicar", response_model=sc.EditorOut)
def publicar(ctx: Ctx, request: Request):
    with traduzir():
        servico.publicar(ctx.db, ctx.usuario)
    ctx.auditar("site.publicar", "site_config", 1, descricao="Site publicado")
    ctx.db.commit()
    return _editor(ctx, request)


@router.post("/despublicar", response_model=sc.EditorOut)
def despublicar(ctx: Ctx, request: Request):
    servico.despublicar(ctx.db)
    ctx.auditar("site.despublicar", "site_config", 1, descricao="Site tirado do ar")
    ctx.db.commit()
    return _editor(ctx, request)


@router.post("/descartar", response_model=sc.EditorOut)
def descartar(ctx: Ctx, request: Request):
    with traduzir():
        servico.descartar_alteracoes(ctx.db)
    ctx.auditar("site.descartar", "site_config", 1, descricao="Alterações não publicadas descartadas")
    ctx.db.commit()
    return _editor(ctx, request)


@router.post("/imagens", response_model=sc.ImagemOut)
async def enviar_imagem(ctx: Ctx, arquivo: UploadFile = File(...)):
    conteudo = await arquivo.read(5 * 1024 * 1024 + 1)
    with traduzir():
        rel = storage.salvar("site", arquivo.filename or "", conteudo)
    ctx.auditar("site.imagem", "site_config", 1, descricao=f"Foto enviada para o site ({arquivo.filename})")
    ctx.db.commit()
    return sc.ImagemOut(foto=rel, url=regras.url_foto(rel) or "")


# ---------------------------------------------------------------------------------------------------- contatos
@router.get("/contatos", response_model=sc.ListaContatos)
def contatos(ctx: Ctx, pagina: int = Query(1, ge=1), por_pagina: int = Query(20, ge=1, le=100)):
    return servico.listar_contatos(ctx.db, pagina, por_pagina)


@router.post("/contatos/lidos", response_model=Mensagem)
def marcar_todos_lidos(ctx: Ctx):
    for c in ctx.db.query(SiteContato).filter(SiteContato.lido.is_(False)):
        c.lido = True
    ctx.db.commit()
    return Mensagem(mensagem="Contatos marcados como lidos.")


@router.post("/contatos/{contato_id}/lido", response_model=sc.ContatoOut)
def marcar_lido(contato_id: int, ctx: Ctx):
    c = ctx.db.get(SiteContato, contato_id)
    if not c:
        raise HTTPException(404, "Contato não encontrado.")
    c.lido = True
    ctx.db.commit()
    return sc.ContatoOut.model_validate(c)


# ------------------------------------------------------------------------------------------------------ público
@router_publico.get("/pagina", response_model=sc.PaginaPublica, dependencies=[Depends(limitar("site-pagina", 300, 60))])
def pagina(db: DB):
    p = servico.pagina_publica(db)
    if not p:
        raise HTTPException(404, "Site não publicado.")
    return p


@router_publico.get("/imagens/{nome}", dependencies=[Depends(limitar("site-imagem", 900, 60))])
def imagem(nome: str):
    """Só as fotos do site (pasta `site/`, nome aleatório). Cache longo: o nome muda quando a foto muda."""
    if not regras.RX_NOME_FOTO.match(nome):
        raise HTTPException(404, "Imagem não encontrada.")
    rel = f"site/{nome}"
    if not storage.existe(rel):
        raise HTTPException(404, "Imagem não encontrada.")
    return FileResponse(storage.resolver(rel), headers={
        "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
    })


@router_publico.post("/contato", response_model=Mensagem, status_code=201,
                     dependencies=[Depends(limitar("site-contato", 5, 600))])
def contato(dados: sc.ContatoIn, db: DB):
    """Formulário "Agende sua aula experimental". Robôs (honeypot/tempo) recebem a mesma resposta, sem gravar nada."""
    with traduzir():
        servico.registrar_contato(db, dados)
    return Mensagem(mensagem="Recebemos seu contato! Em breve falaremos com você.")
