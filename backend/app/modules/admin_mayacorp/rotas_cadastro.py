"""Cadastro pelo site: formulário público → solicitação no admin → aprovar cria o estúdio (com teste grátis).

Porte de app/controle/routes_cadastro.py do MayaJus. O link "Aprovar ou recusar" do e-mail é um link assinado com
prazo (`app.core.links`, 7 dias) que identifica o administrador do admin MayaFit e a solicitação.
"""

import logging
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.controle import emails, planos, ponte
from app.controle.models import Plano, SessaoControle, Solicitacao
from app.core import links
from app.core.config import settings
from app.core.deps import Contexto, ip_cliente
from app.core.ratelimit import limitar
from app.modules.admin_mayacorp import schemas as sc
from app.modules.admin_mayacorp.servico import Painel, d, plano_out

log = logging.getLogger(__name__)

publico = APIRouter(prefix="/public", tags=["público"])
admin = APIRouter(prefix="/admin", tags=["admin MayaFit"])

FINALIDADE = "aprovar-solicitacao"
VALIDADE_LINK_S = 7 * 24 * 3600


def sol_out(s: Solicitacao) -> dict:
    return {"id": s.id, "nome": s.nome, "documento": s.documento, "responsavel": s.responsavel, "email": s.email,
            "telefone": s.telefone, "plano": plano_out(s.plano), "ciclo": s.ciclo, "alunos": s.alunos,
            "indicacao": s.indicacao, "mensagem": s.mensagem, "status": s.status, "cliente_id": s.cliente_id,
            "criado_em": s.criado_em}


# ================================================================ público (formulário do site)
@publico.get("/planos", dependencies=[Depends(limitar("public", 120, 60))])
def planos_publicos():
    with SessaoControle() as db:
        planos.garantir_padrao(db)
        return [{**plano_out(p), "preco_mensal": d(p.preco_mensal), "preco_anual": d(p.preco_anual)}
                for p in db.scalars(select(Plano).where(Plano.ativo).order_by(Plano.ordem, Plano.id))]


@publico.post("/cadastro", status_code=201, dependencies=[Depends(limitar("cadastro-site", 5, 3600))])
def cadastrar(dados: sc.CadastroIn, request: Request):
    if dados.site:  # robô preencheu o campo escondido: finge que deu certo e descarta
        return {"ok": True}
    if not dados.aceite:
        raise HTTPException(400, "É preciso aceitar os termos para continuar.")
    doc = re.sub(r"\D", "", dados.documento or "") or None
    if doc and len(doc) not in (11, 14):
        raise HTTPException(400, "CNPJ ou CPF inválido.")
    with SessaoControle() as db:
        plano = db.get(Plano, dados.plano_id) if dados.plano_id else None
        if dados.plano_id and (not plano or not plano.ativo):
            raise HTTPException(400, "Plano não disponível.")
        s = Solicitacao(nome=dados.nome.strip(), documento=doc, responsavel=dados.responsavel.strip(),
                        email=str(dados.email).lower(), telefone=dados.telefone.strip(), plano_id=dados.plano_id,
                        ciclo=dados.ciclo, alunos=dados.alunos, indicacao=(dados.indicacao or "").strip() or None,
                        mensagem=(dados.mensagem or "").strip() or None, status="nova", ip=ip_cliente(request))
        db.add(s)
        db.commit()
        plano_nome = plano.nome if plano else "a definir"
    try:
        emails.enviar_email(
            [s.email], "Recebemos seu cadastro no MayaFit",
            f"Olá, {s.responsavel.split()[0]}!\n\nRecebemos o cadastro do {s.nome} (plano {plano_nome}). Em breve "
            f"você recebe um e-mail com o link para criar o seu acesso e começar os {planos.DIAS_TESTE_PADRAO} dias de "
            "teste grátis.\n\nEquipe MayaFit")
        _avisar_admin(s, plano_nome)
    except Exception:
        log.exception("E-mails do cadastro %s falharam", s.id)
    return {"ok": True}


def link_aprovacao(usuario_id: int, sid: int) -> str:
    token = links.assinar(FINALIDADE, {"u": usuario_id, "s": sid}, VALIDADE_LINK_S)
    host = ponte.endereco_do_painel()
    base = f"https://{host}" if host else settings.frontend_url.rstrip("/")
    return f"{base}/aprovar?token={token}"


def _mayacorp():
    try:
        return ponte.service().estudio_mayacorp()
    except ImportError:
        return None


def _avisar_admin(s: Solicitacao, plano_nome: str) -> None:
    """Avisa cada administrador do admin MayaFit, com o link para aprovar sem entrar no sistema."""
    from app.core.db import SessionLocal
    from app.core.models import Usuario

    est = _mayacorp()
    if est is None and ponte.multi():
        return
    with ponte.usando(est), SessionLocal() as db:
        admins = [(u.id, u.email) for u in db.scalars(select(Usuario).where(Usuario.ativo,
                                                                         Usuario.senha_hash.is_not(None)))
                  if u.administrador and not (u.login or "").startswith("suporte.")]
    for uid, email in admins:
        emails.enviar_email(
            [email], f"Novo cadastro no MayaFit: {s.nome}",
            f"{s.nome} ({s.documento or 'sem CNPJ'})\nResponsável: {s.responsavel}\nE-mail: {s.email}\n"
            f"Telefone: {s.telefone}\nPlano: {plano_nome} ({s.ciclo})\nAlunos ativos hoje: {s.alunos or '-'}\n"
            f"Indicação: {s.indicacao or '-'}\n\n{s.mensagem or ''}\n\n"
            f"Aprovar ou recusar (sem precisar entrar no sistema):\n{link_aprovacao(uid, s.id)}\n\n"
            "O link vale por 7 dias. Também dá para aprovar no admin, em Solicitações.")


# ================================================================ aprovar pelo link do e-mail (sem login)
def _pelo_link(token: str):
    """(est, id do usuário, id da solicitação) — o link identifica um administrador do admin MayaFit."""
    try:
        dados = links.verificar(token, FINALIDADE)
    except links.LinkInvalido:
        raise HTTPException(400, "Link inválido ou expirado. Aprove pelo admin, em Solicitações.") from None
    return _mayacorp(), int(dados["u"]), int(dados["s"])


def _com_admin(token: str, request: Request, acao):
    from app.core.db import SessionLocal
    from app.core.models import Usuario

    est, uid, sid = _pelo_link(token)
    with ponte.usando(est), SessionLocal() as db:
        u = db.get(Usuario, uid)
        if not u or not u.ativo or not u.administrador:
            raise HTTPException(403, "Este link não vale mais para o seu usuário.")
        return acao(sid, Contexto(db=db, usuario=u, ip=ip_cliente(request)))


@publico.get("/solicitacao", dependencies=[Depends(limitar("aprovar-link", 30, 60))])
def ver_pelo_link(token: str, request: Request):
    def ver(sid, _ctx):
        with SessaoControle() as ctl:
            s = ctl.get(Solicitacao, sid)
            if not s:
                raise HTTPException(404, "Solicitação não encontrada.")
            return sol_out(s)

    return _com_admin(token, request, ver)


@publico.post("/solicitacao/aprovar", dependencies=[Depends(limitar("aprovar-link", 30, 60))])
def aprovar_pelo_link(dados: sc.TokenIn, request: Request):
    return _com_admin(dados.token, request, lambda sid, ctx: aprovar(sid, sc.AprovarIn(dias_teste=dados.dias_teste), ctx))


@publico.post("/solicitacao/recusar", dependencies=[Depends(limitar("aprovar-link", 30, 60))])
def recusar_pelo_link(dados: sc.TokenIn, request: Request):
    return _com_admin(dados.token, request, recusar)


# ================================================================ admin: Solicitações
@admin.get("/solicitacoes")
def listar(ctx: Painel, status: str | None = None):
    with SessaoControle() as db:
        q = select(Solicitacao).order_by(Solicitacao.id.desc())
        if status:
            q = q.where(Solicitacao.status == status)
        return [sol_out(s) for s in db.scalars(q.limit(300))]


def _sol(db, sid: int) -> Solicitacao:
    s = db.get(Solicitacao, sid)
    if not s:
        raise HTTPException(404, "Solicitação não encontrada.")
    if s.status != "nova":
        raise HTTPException(400, "Esta solicitação já foi tratada.")
    return s


def _observacao(s: Solicitacao) -> str | None:
    partes = [f"Alunos ativos informados no cadastro: {s.alunos}" if s.alunos is not None else None,
              f"Indicação: {s.indicacao}" if s.indicacao else None, s.mensagem]
    return "\n".join(p for p in partes if p) or None


@admin.post("/solicitacoes/{sid}/aprovar")
def aprovar(sid: int, dados: sc.AprovarIn, ctx: Painel):
    """Cria o estúdio com teste grátis e manda as boas-vindas (o dono cria o usuário master pelo link)."""
    from app.modules.admin_mayacorp.rotas_estudios import criar_estudio

    with SessaoControle() as db:
        s = _sol(db, sid)
        novo = sc.ClienteNovoIn(nome=s.nome, documento=s.documento, responsavel=s.responsavel,
                                email_financeiro=s.email, telefone=s.telefone, plano_id=s.plano_id, ciclo=s.ciclo,
                                inicio_contrato=date.today(), observacao=_observacao(s), slug=dados.slug,
                                admin_nome=s.responsavel, admin_email=s.email, dias_teste=dados.dias_teste,
                                dominios=[])
    estudio = criar_estudio(novo, ctx)
    with SessaoControle() as db:
        s = db.get(Solicitacao, sid)
        s.status, s.cliente_id = "aprovada", estudio["id"]
        db.commit()
    ctx.auditar("admin.solicitacao.aprovar", "controle_solicitacao", sid, descricao=estudio["nome"])
    ctx.db.commit()
    return estudio


@admin.post("/solicitacoes/{sid}/recusar")
def recusar(sid: int, ctx: Painel):
    with SessaoControle() as db:
        s = _sol(db, sid)
        s.status = "recusada"
        db.commit()
        ctx.auditar("admin.solicitacao.recusar", "controle_solicitacao", sid, descricao=s.nome)
        ctx.db.commit()
        return sol_out(s)
