"""Rotas públicas (sem login): identidade visual para a tela de login e arquivos por link assinado."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core import links, storage
from app.core.deps import DB
from app.core.models import Identidade
from app.core.ratelimit import limitar
from app.core.schemas import IdentidadePublica

router = APIRouter(tags=["público"])

NOME_PADRAO = "MayaFit"


def _identidade(db) -> Identidade | None:
    return db.scalar(select(Identidade).order_by(Identidade.id))


def logo_url(ident: Identidade | None) -> str | None:
    if not ident or not storage.existe(ident.logo_path):
        return None
    return f"/public/logo?v={storage.versao(ident.logo_path)}"


@router.get("/public/identidade", response_model=IdentidadePublica, dependencies=[Depends(limitar("public", 120, 60))])
def identidade(db: DB):
    ident = _identidade(db)
    if not ident:
        return IdentidadePublica(nome_exibicao=NOME_PADRAO)
    return IdentidadePublica(nome_exibicao=ident.nome_exibicao, logo_url=logo_url(ident), cor_destaque=ident.cor_destaque)


def _servir(caminho, nome: str | None = None, cache: str = "private, max-age=300"):
    headers = {"Cache-Control": cache, "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"}
    return FileResponse(caminho, filename=nome, headers=headers)


@router.get("/public/logo", dependencies=[Depends(limitar("public", 120, 60))])
def logo(db: DB):
    ident = _identidade(db)
    if not ident or not storage.existe(ident.logo_path):
        raise HTTPException(404, "Sem logo")
    return _servir(storage.resolver(ident.logo_path), cache="public, max-age=300")


@router.get("/arquivos-publicos/{token}", dependencies=[Depends(limitar("arquivo-publico", 60, 60))])
def arquivo_por_link(token: str):
    """Arquivo servido por link assinado com prazo (PDF de recibo/contrato enviado ao aluno, por exemplo)."""
    try:
        dados = links.verificar(token, "arquivo")
        caminho = storage.resolver(dados["p"])
    except (links.LinkInvalido, storage.ArquivoInvalido, KeyError):
        raise HTTPException(404, "Link inválido ou expirado.") from None
    if not caminho.is_file():
        raise HTTPException(404, "Link inválido ou expirado.")
    return _servir(caminho, nome=dados.get("n"), cache="private, no-store")
